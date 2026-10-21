"""U1/U2 - busca, paginacao e exportacao CSV (D74, modo autonomo D69).

Escritos ANTES da implementacao. Devem falhar agora: as listas nao tem `q`, `page`, `page_size` nem a chave
`pagination`; a auditoria nao tem `q`, `date_from`, `date_to` nem `offset`; as rotas `.csv` nao existem.

Contrato (D74):
  - GET /api/dashboard/alunos?q=&page=&page_size=  (q em nome ou e-mail, sem caixa; `metrics` continuam globais)
  - GET /api/dashboard/financeiro?q=&status=&page=&page_size=  (lista de pagamentos; q em e-mail, nome ou curso)
    `pagination {page, page_size, total}`; page a partir de 1; page_size padrao 50, maximo 200 (acima vale 200);
    invalidos -> 422. Sem `page`: tudo (como hoje), com page 1 e page_size = total.
  - GET /api/admin/audit-logs ganha `q` (descricao ou e-mail do responsavel), `date_from`/`date_to` (AAAA-MM-DD,
    dias de Sao Paulo, inclusivos) e `offset`; formato igual.
  - CSV (so Gestao e Financeiro; Suporte 403): /api/dashboard/alunos.csv, /api/dashboard/cursos/{id}/alunos.csv,
    /api/dashboard/financeiro.csv. UTF-8 com BOM, `;`, decimal com virgula, datas dd/mm/aaaa HH:MM em Sao Paulo,
    status em portugues, Content-Disposition attachment com filename .csv; celula iniciada por = + - @ tab CR recebe
    `'` na frente; evento de auditoria `export.csv` com o relatorio em `entity_id`; mesmos filtros da lista.

Grupos
  A  Alunos: busca (nome/e-mail sem caixa), metrics globais, paginacao, limites, 422, compatibilidade
  B  Financeiro: busca (e-mail/nome/curso), filtro de status, paginacao, compatibilidade, totais globais
  C  Auditoria: q (descricao/e-mail), date_from/date_to em dias de SP (fronteira 03:00 UTC), offset, formato
  D  CSV: RBAC (Gestao/Financeiro 200, Suporte 403, aluno 403, 401 sem token/forjado), legado
  E  CSV: formato (BOM, `;`, decimal com virgula, datas SP, status em portugues, Content-Disposition)
  F  CSV: injecao de formula neutralizada
  G  CSV: filtros aplicados, 404 de curso inexistente, sem dado de senha/material
  H  CSV: evento `export.csv` com relatorio em entity_id e responsavel do token (nao do cliente)

Escolhas conservadoras (forma, ver relatorio do agente-testes):
  - Pagina alem da ultima: 200 com lista vazia e `total` preservado.
  - `date_from`/`date_to` em formato invalido: 422 (mesma regra dos parametros de paginacao).
  - Colunas e cabecalhos do CSV nao sao fixados: o teste procura a linha pelo e-mail e confere as celulas.
  - `entity_id` do evento `export.csv`: contem "alunos", "financeiro" ou o id do curso, conforme o relatorio.
  - Pedido de CSV recusado (403/401) nao grava evento `export.csv`.
  - Busca da auditoria testada com a caixa do texto gravado (D74 so diz "sem caixa" para as listas).
  - Compatibilidade do financeiro sem `page` testada com menos de 50 pagamentos (hoje a lista corta em 50).

Ajuste mecanico D74 (U1) -> D81 (S6, autoridade 4.3): o cenario gravava o pagamento `pending` do Pedro com data fixa
(2026-09-02), que a S6 (pendente com mais de 7 dias vira `cancelled` nas leituras de dashboard) expira. Pedro, Rita,
Bruno e Carla passam a ter datas relativas a hoje (UTC, 4 a 1 dia atras, ao meio-dia, mesma ordem relativa entre eles).
Joana continua no instante fixo DATA_UTC_VIRADA (aprovado, sem expiracao): ele e a base dos testes de fuso (F2) do CSV.
Intencao dos testes preservada.
"""

import csv
import io
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token
from db import Database


REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"

CURSO_PY = "curso_u1_python"
NOME_PY = "Python Avancado U1"
CURSO_XL = "curso_u1_planilha"
NOME_XL = "Planilhas U1"
URL_MATERIAL = "https://materiais.test/u1/apostila-secreta.pdf"

VALOR_JOANA = 987.65
VALOR_PEDRO = 432.17
VALOR_RITA = 618.29
VALOR_CARLA = 250.40

# 2026-10-08 01:30 UTC = 2026-10-07 22:30 em Sao Paulo (-3 h).
DATA_UTC_VIRADA = "2026-10-08 01:30:00"


def _ha(dias):
    """D81: data relativa a hoje (UTC), ao meio-dia; 1 a 4 dias -> pendente com menos de 7 dias (S6)."""
    return (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d 12:00:00")
DATA_SP_VIRADA = "07/10/2026 22:30"

HASH_SECRETO = "$2b$12$HASHSECRETOU1nao.pode.sair.no.csv"
BOM = b"\xef\xbb\xbf"


# --- Fixtures ---------------------------------------------------------------------------

def _foto_repo():
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Diretorio temporario para os cursos; backend/courses nao pode mudar."""
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses (deveria usar o diretorio temporario)"


def _escrever_curso(diretorio, course_id, nome, preco, materiais=None):
    dados = {"id": course_id, "name": nome, "description": "Curso de teste U1", "price": preco,
             "level": "Iniciante", "duration_hours": 10}
    if materiais is not None:
        dados["materials"] = materiais
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def catalogo(cursos):
    _escrever_curso(cursos, CURSO_PY, NOME_PY, VALOR_JOANA,
                    [{"title": "Apostila", "url": URL_MATERIAL, "type": "pdf"}])
    _escrever_curso(cursos, CURSO_XL, NOME_XL, VALOR_PEDRO)  # sem `materials` (dado antigo)
    return cursos


@pytest.fixture
def client(banco, catalogo):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _conta(email, nome, perfil, senha_hash=None):
    user_id = Database.add_user(email, nome, senha_hash, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        gestao=_conta("ana.gestora@u1.test", "Ana Gestora", "admin"),
        fin=_conta("fernanda.fin@u1.test", "Fernanda Financeira", "financial"),
        sup=_conta("sergio.sup@u1.test", "Sergio Suporte", "support"),
        joana=_conta("joana.aluna@u1.test", "Joana Aluna", "student", HASH_SECRETO),
        pedro=_conta("pedro.aluno@u1.test", "Pedro Aluno", "student"),
        rita=_conta("rita.aluna@u1.test", "Rita Aluna", "student"),
        bruno=_conta("bruno.aluno@u1.test", "Bruno Aluno", "student"),
        carla=_conta("carla.aluna@u1.test", "Carla Aluna", "student"),
        davi=_conta("davi.aluno@u1.test", "Davi Aluno", "student"),
        elisa=_conta("elisa.aluna@u1.test", "Elisa Aluna", "student"),
    )


def _matricula(user_id, course_id, status, data, valor=None, status_pagamento=None):
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:u1:{uuid.uuid4().hex}")
    _executar("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, data, enrollment_id))
    payment_id = None
    if valor is not None:
        payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
        if status_pagamento and status_pagamento != "pending":
            Database.update_payment_status(payment_id, status_pagamento, f"mp-u1-{uuid.uuid4().hex[:8]}")
        _executar("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (data, data, payment_id))
    return SimpleNamespace(id=enrollment_id, payment_id=payment_id)


@pytest.fixture
def cenario(contas):
    """
    7 alunos (joana, pedro, rita, bruno, carla, davi, elisa) e 3 funcionarios.
      joana  python    active    pagamento approved 987,65  2026-10-08 01:30 UTC (07/10 22:30 SP); conta tambem
                                                             criada nesse instante
      pedro  planilha  pending   pagamento pending  432,17  ha 4 dias 12:00 UTC (D81: relativo, < 7 dias)
      rita   python    cancelled pagamento rejected 618,29  ha 3 dias 12:00 UTC
      bruno  python    pending   sem pagamento               ha 2 dias 12:00 UTC
      carla  planilha  active    pagamento approved 250,40  ha 1 dia 12:00 UTC
      davi, elisa sem matricula.
    """
    _executar("UPDATE users SET created_at = ? WHERE id = ?", (DATA_UTC_VIRADA, contas.joana.id))
    return SimpleNamespace(
        joana=_matricula(contas.joana.id, CURSO_PY, "active", DATA_UTC_VIRADA, VALOR_JOANA, "approved"),
        pedro=_matricula(contas.pedro.id, CURSO_XL, "pending", _ha(4), VALOR_PEDRO, "pending"),
        rita=_matricula(contas.rita.id, CURSO_PY, "cancelled", _ha(3), VALOR_RITA, "rejected"),
        bruno=_matricula(contas.bruno.id, CURSO_PY, "pending", _ha(2)),
        carla=_matricula(contas.carla.id, CURSO_XL, "active", _ha(1), VALOR_CARLA, "approved"),
    )


def _forjado(role="admin"):
    return jose_jwt.encode({"user_id": 1, "email": "x@u1.test", "role": role},
                           "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")


# --- Helpers de HTTP --------------------------------------------------------------------

def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get(client, token, rota, **params):
    return client.get(rota, params=params or None, headers=_auth(token))


def _ok(r, rotulo):
    assert r.status_code == 200, f"{rotulo}: HTTP {r.status_code} {r.text[:300]}"
    return r.json()


def _emails_alunos(corpo):
    return [s["email"] for s in corpo["students"]]


def _ids_pagamentos(corpo):
    return [p["id"] for p in corpo["payments"]]


def _pagination(corpo, rotulo):
    assert "pagination" in corpo, f"{rotulo}: resposta sem a chave `pagination` (D74): {sorted(corpo)}"
    pag = corpo["pagination"]
    assert {"page", "page_size", "total"} <= set(pag), f"{rotulo}: pagination incompleta: {pag}"
    return pag


def _csv(r, rotulo):
    """Valida o envelope do CSV e devolve as linhas (lista de listas)."""
    assert r.status_code == 200, f"{rotulo}: HTTP {r.status_code} {r.text[:300]}"
    assert r.content.startswith(BOM), f"{rotulo}: CSV sem BOM UTF-8: {r.content[:20]!r}"
    texto = r.content.decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=";"))
    assert linhas and len(linhas[0]) > 1, f"{rotulo}: cabecalho nao usa ';' como separador: {texto[:200]!r}"
    return linhas


def _linha_com(linhas, valor, rotulo):
    achadas = [linha for linha in linhas[1:] if valor in linha]
    assert len(achadas) == 1, f"{rotulo}: esperada 1 linha com a celula {valor!r}, achadas {len(achadas)}"
    return achadas[0]


def _eventos_export():
    return Database.list_audit_logs(limit=500, action="export.csv")


# =====================================================================================
# A  Dashboard de alunos: busca e paginacao
# =====================================================================================

ALUNOS = "/api/dashboard/alunos"
TODOS_ALUNOS = {"joana.aluna@u1.test", "pedro.aluno@u1.test", "rita.aluna@u1.test", "bruno.aluno@u1.test",
                "carla.aluna@u1.test", "davi.aluno@u1.test", "elisa.aluna@u1.test"}


def test_a1_sem_parametros_lista_de_hoje_mais_pagination(client, contas, cenario):
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS), "alunos sem parametros")
    esperado = [s["email"] for s in Database.get_students_overview()]
    assert _emails_alunos(corpo) == esperado, "sem parametros a lista e a mesma de hoje (mesma ordem)"
    assert set(esperado) == TODOS_ALUNOS
    assert _pagination(corpo, "A1") == {"page": 1, "page_size": 7, "total": 7}
    assert corpo["metrics"]["total_students"] == 7


@pytest.mark.parametrize("q", ["joana", "JOANA", "Joana Al", "aLuNa@U1"])
def test_a2_busca_sem_caixa_por_nome_ou_email(client, contas, cenario, q):
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS, q=q), f"alunos q={q}")
    emails = set(_emails_alunos(corpo))
    if q.lower().startswith("joana"):
        assert emails == {"joana.aluna@u1.test"}, f"q={q}: {emails}"
    else:
        assert emails == {"joana.aluna@u1.test", "rita.aluna@u1.test", "carla.aluna@u1.test",
                          "elisa.aluna@u1.test"}, f"q={q} (e-mail): {emails}"
    assert _pagination(corpo, "A2")["total"] == len(emails)


def test_a3_busca_por_email_sem_casar_nome(client, contas, cenario):
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS, q="pedro.aluno@"), "alunos q=email")
    assert _emails_alunos(corpo) == ["pedro.aluno@u1.test"]


def test_a4_busca_sem_resultado_e_metrics_globais(client, contas, cenario):
    global_ = _ok(_get(client, contas.gestao.token, ALUNOS), "alunos")["metrics"]
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS, q="ninguem-com-este-nome"), "alunos q=nada")
    assert corpo["students"] == []
    assert _pagination(corpo, "A4")["total"] == 0
    assert corpo["metrics"] == global_, "metrics continuam globais com busca (D74)"
    filtrado = _ok(_get(client, contas.gestao.token, ALUNOS, q="joana"), "alunos q=joana")
    assert filtrado["metrics"]["total_students"] == 7
    assert filtrado["metrics"]["active_students"] == global_["active_students"]


def test_a5_paginas_concatenadas_igual_a_lista_completa(client, contas, cenario):
    completa = _emails_alunos(_ok(_get(client, contas.gestao.token, ALUNOS), "alunos"))
    paginas = []
    for page in (1, 2, 3):
        corpo = _ok(_get(client, contas.gestao.token, ALUNOS, page=page, page_size=3), f"page={page}")
        assert _pagination(corpo, f"page={page}") == {"page": page, "page_size": 3, "total": 7}
        paginas.append(_emails_alunos(corpo))
    assert [len(p) for p in paginas] == [3, 3, 1]
    assert paginas[0] + paginas[1] + paginas[2] == completa


def test_a6_pagina_alem_da_ultima_vazia(client, contas, cenario):
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS, page=4, page_size=3), "page=4")
    assert corpo["students"] == []
    assert _pagination(corpo, "A6") == {"page": 4, "page_size": 3, "total": 7}


def test_a7_page_size_padrao_50_e_maximo_200(client, contas, cenario):
    padrao = _ok(_get(client, contas.gestao.token, ALUNOS, page=1), "page=1 sem page_size")
    assert _pagination(padrao, "padrao")["page_size"] == 50
    assert len(padrao["students"]) == 7
    acima = _ok(_get(client, contas.gestao.token, ALUNOS, page=1, page_size=500), "page_size=500")
    assert _pagination(acima, "acima")["page_size"] == 200
    exato = _ok(_get(client, contas.gestao.token, ALUNOS, page=1, page_size=200), "page_size=200")
    assert _pagination(exato, "exato")["page_size"] == 200


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page": "abc"}, {"page": 1, "page_size": 0},
    {"page": 1, "page_size": -5}, {"page": 1, "page_size": "dez"},
])
def test_a8_parametros_invalidos_422(client, contas, cenario, params):
    r = _get(client, contas.gestao.token, ALUNOS, **params)
    assert r.status_code == 422, f"{params}: HTTP {r.status_code} {r.text[:200]}"


def test_a9_busca_com_paginacao(client, contas, cenario):
    corpo = _ok(_get(client, contas.gestao.token, ALUNOS, q="ALUNA", page=2, page_size=2), "q+page")
    assert _pagination(corpo, "A9") == {"page": 2, "page_size": 2, "total": 4}
    assert len(corpo["students"]) == 2
    assert all("aluna" in s["email"] for s in corpo["students"])


def test_a10_suporte_continua_com_a_lista(client, contas, cenario):
    corpo = _ok(_get(client, contas.sup.token, ALUNOS, q="joana", page=1), "suporte")
    assert _emails_alunos(corpo) == ["joana.aluna@u1.test"]


# =====================================================================================
# B  Dashboard financeiro: busca, status e paginacao
# =====================================================================================

FIN = "/api/dashboard/financeiro"


def test_b1_sem_parametros_lista_de_hoje_mais_pagination(client, contas, cenario):
    corpo = _ok(_get(client, contas.fin.token, FIN), "financeiro sem parametros")
    esperado = [p["id"] for p in Database.get_payments_overview()]
    assert _ids_pagamentos(corpo) == esperado
    assert len(esperado) == 4
    assert _pagination(corpo, "B1") == {"page": 1, "page_size": 4, "total": 4}
    assert {"totals", "by_status", "monthly_revenue"} <= set(corpo)


@pytest.mark.parametrize("q,esperados", [
    ("JOANA", {"joana"}),                                   # nome, sem caixa
    ("pedro.aluno@u1", {"pedro"}),                          # e-mail
    ("python", {"joana", "rita"}),                          # curso (id e nome contem "python")
    ("PYTHON", {"joana", "rita"}),
])
def test_b2_busca_por_email_nome_ou_curso(client, contas, cenario, q, esperados):
    corpo = _ok(_get(client, contas.gestao.token, FIN, q=q), f"financeiro q={q}")
    ids = {getattr(cenario, nome).payment_id for nome in esperados}
    assert set(_ids_pagamentos(corpo)) == ids, f"q={q}: {corpo['payments']}"
    assert _pagination(corpo, "B2")["total"] == len(ids)


def test_b3_filtro_de_status(client, contas, cenario):
    corpo = _ok(_get(client, contas.gestao.token, FIN, status="approved"), "status=approved")
    assert set(_ids_pagamentos(corpo)) == {cenario.joana.payment_id, cenario.carla.payment_id}
    assert all(p["status"] == "approved" for p in corpo["payments"])
    combinado = _ok(_get(client, contas.gestao.token, FIN, status="approved", q="python"), "status+q")
    assert _ids_pagamentos(combinado) == [cenario.joana.payment_id]


def test_b4_totais_continuam_globais(client, contas, cenario):
    global_ = _ok(_get(client, contas.gestao.token, FIN), "financeiro")
    filtrado = _ok(_get(client, contas.gestao.token, FIN, q="pedro", status="pending"), "financeiro filtrado")
    assert filtrado["totals"] == global_["totals"]
    assert filtrado["by_status"] == global_["by_status"]


def test_b5_paginacao(client, contas, cenario):
    completa = _ids_pagamentos(_ok(_get(client, contas.gestao.token, FIN), "financeiro"))
    p1 = _ok(_get(client, contas.gestao.token, FIN, page=1, page_size=3), "page 1")
    p2 = _ok(_get(client, contas.gestao.token, FIN, page=2, page_size=3), "page 2")
    assert _pagination(p1, "p1") == {"page": 1, "page_size": 3, "total": 4}
    assert _pagination(p2, "p2") == {"page": 2, "page_size": 3, "total": 4}
    assert _ids_pagamentos(p1) + _ids_pagamentos(p2) == completa
    acima = _ok(_get(client, contas.gestao.token, FIN, page=1, page_size=1000), "page_size=1000")
    assert _pagination(acima, "acima")["page_size"] == 200


@pytest.mark.parametrize("params", [{"page": 0}, {"page": "x"}, {"page": 1, "page_size": 0}])
def test_b6_parametros_invalidos_422(client, contas, cenario, params):
    r = _get(client, contas.gestao.token, FIN, **params)
    assert r.status_code == 422, f"{params}: HTTP {r.status_code} {r.text[:200]}"


def test_b7_suporte_continua_sem_financeiro(client, contas, cenario):
    r = _get(client, contas.sup.token, FIN, q="joana")
    assert r.status_code == 403
    assert str(VALOR_JOANA) not in r.text


# =====================================================================================
# C  Auditoria: q, date_from/date_to (dias de Sao Paulo), offset
# =====================================================================================

AUDIT = "/api/admin/audit-logs"


def _evento(acao, detalhe, criado_em, email=None):
    """Insere o evento com data fixa (INSERT e permitido; a trilha so recusa UPDATE/DELETE)."""
    return _executar(
        """INSERT INTO audit_logs (user_id, role, action, detail, actor_email, actor_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (None, "admin", acao, detalhe, email, "Pessoa U1", criado_em),
    )


@pytest.fixture
def eventos(contas):
    return SimpleNamespace(
        e1=_evento("u1.teste", "U1AUD evento um", "2026-10-06 12:00:00", "maria.ops@u1.test"),
        e2=_evento("u1.teste", "U1AUD evento dois (antes da virada)", "2026-10-08 01:30:00", "joao.ops@u1.test"),
        e3=_evento("u1.teste", "U1AUD evento tres (ultimo segundo do dia 07 em SP)", "2026-10-08 02:59:59",
                   "maria.ops@u1.test"),
        e4=_evento("u1.teste", "U1AUD evento quatro (inicio do dia 08 em SP)", "2026-10-08 03:00:00",
                   "joao.ops@u1.test"),
        e5=_evento("u1.teste", "U1AUD evento cinco", "2026-10-09 15:00:00", "maria.ops@u1.test"),
    )


def _ids_logs(corpo):
    return [log["id"] for log in corpo["logs"]]


def test_c1_q_na_descricao(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, q="evento quatro"), "q descricao")
    assert _ids_logs(corpo) == [eventos.e4]


def test_c2_q_no_email_do_responsavel(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, q="maria.ops@"), "q email")
    assert _ids_logs(corpo) == [eventos.e5, eventos.e3, eventos.e1]


def test_c3_q_sem_resultado(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, q="texto-que-nao-existe-u1"), "q nada")
    assert corpo["logs"] == []


def test_c4_dia_de_sao_paulo_inclui_evento_de_0130_utc_do_dia_seguinte(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", date_from="2026-10-07", date_to="2026-10-07"),
                "dia 07")
    assert set(_ids_logs(corpo)) == {eventos.e2, eventos.e3}, \
        "2026-10-08 01:30 e 02:59:59 UTC pertencem ao dia 07 de Sao Paulo; 03:00 UTC ja e dia 08"


def test_c5_dia_08_comeca_as_0300_utc(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", date_from="2026-10-08", date_to="2026-10-08"),
                "dia 08")
    assert _ids_logs(corpo) == [eventos.e4]


def test_c6_intervalo_inclusivo_e_limites_abertos(client, contas, eventos):
    intervalo = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", date_from="2026-10-06",
                         date_to="2026-10-08"), "06..08")
    assert set(_ids_logs(intervalo)) == {eventos.e1, eventos.e2, eventos.e3, eventos.e4}
    so_inicio = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", date_from="2026-10-08"), "desde 08")
    assert set(_ids_logs(so_inicio)) == {eventos.e4, eventos.e5}
    so_fim = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", date_to="2026-10-06"), "ate 06")
    assert _ids_logs(so_fim) == [eventos.e1]


def test_c7_offset_com_limit(client, contas, eventos):
    todos = _ids_logs(_ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD"), "todos"))
    assert todos == [eventos.e5, eventos.e4, eventos.e3, eventos.e2, eventos.e1]
    pagina = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", limit=2, offset=2), "offset 2")
    assert _ids_logs(pagina) == todos[2:4]
    fim = _ok(_get(client, contas.gestao.token, AUDIT, q="U1AUD", limit=2, offset=4), "offset 4")
    assert _ids_logs(fim) == todos[4:]


def test_c8_formato_igual_e_filtros_antigos(client, contas, eventos):
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, action="u1.teste", q="U1AUD", limit=1), "formato")
    assert corpo["status"] == "success"
    assert isinstance(corpo["logs"], list) and len(corpo["logs"]) == 1
    assert {"id", "action", "detail", "actor_email", "created_at", "changes"} <= set(corpo["logs"][0])


@pytest.mark.parametrize("params", [{"date_from": "07/10/2026"}, {"date_to": "2026-13-40"}])
def test_c9_data_invalida_422(client, contas, eventos, params):
    r = _get(client, contas.gestao.token, AUDIT, **params)
    assert r.status_code == 422, f"{params}: HTTP {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("perfil", ["fin", "sup", "joana"])
def test_c10_auditoria_continua_so_gestao(client, contas, eventos, perfil):
    r = _get(client, getattr(contas, perfil).token, AUDIT, q="U1AUD")
    assert r.status_code == 403
    assert "U1AUD" not in r.text


# =====================================================================================
# D  CSV: RBAC
# =====================================================================================

def _rotas_csv():
    return {
        "alunos": "/api/dashboard/alunos.csv",
        "curso": f"/api/dashboard/cursos/{CURSO_PY}/alunos.csv",
        "financeiro": "/api/dashboard/financeiro.csv",
    }


@pytest.mark.parametrize("relatorio", ["alunos", "curso", "financeiro"])
@pytest.mark.parametrize("perfil", ["gestao", "fin", "gestao_legado", "fin_legado"])
def test_d1_gestao_e_financeiro_exportam(client, contas, cenario, relatorio, perfil):
    token = {"gestao_legado": create_admin_token(Role.ADMIN),
             "fin_legado": create_admin_token(Role.FINANCIAL)}.get(perfil) or getattr(contas, perfil).token
    r = _get(client, token, _rotas_csv()[relatorio])
    _csv(r, f"{perfil} {relatorio}")


@pytest.mark.parametrize("relatorio", ["alunos", "curso", "financeiro"])
@pytest.mark.parametrize("perfil", ["sup", "sup_legado", "joana"])
def test_d2_suporte_e_aluno_recebem_403_sem_evento(client, contas, cenario, relatorio, perfil):
    token = create_admin_token(Role.SUPPORT) if perfil == "sup_legado" else getattr(contas, perfil).token
    r = _get(client, token, _rotas_csv()[relatorio])
    assert r.status_code == 403, f"{perfil} {relatorio}: HTTP {r.status_code} {r.text[:200]}"
    assert "joana.aluna@u1.test" not in r.text
    assert _eventos_export() == [], "exportacao recusada nao grava export.csv"


@pytest.mark.parametrize("relatorio", ["alunos", "curso", "financeiro"])
@pytest.mark.parametrize("cabecalho", ["sem_token", "forjado", "forjado_fin"])
def test_d3_sem_token_ou_forjado_401(client, contas, cenario, relatorio, cabecalho):
    headers = {"sem_token": {}, "forjado": _auth(_forjado()), "forjado_fin": _auth(_forjado("financial"))}[cabecalho]
    r = client.get(_rotas_csv()[relatorio], headers=headers)
    assert r.status_code == 401, f"{cabecalho} {relatorio}: HTTP {r.status_code} {r.text[:200]}"
    assert "joana.aluna@u1.test" not in r.text
    assert _eventos_export() == []


# =====================================================================================
# E  CSV: formato Excel pt-BR
# =====================================================================================

@pytest.mark.parametrize("relatorio", ["alunos", "curso", "financeiro"])
def test_e1_content_type_e_content_disposition(client, contas, cenario, relatorio):
    r = _get(client, contas.gestao.token, _rotas_csv()[relatorio])
    _csv(r, relatorio)
    assert r.headers.get("content-type", "").startswith("text/csv"), r.headers.get("content-type")
    disposicao = r.headers.get("content-disposition", "")
    assert re.match(r'^attachment;\s*filename="?[^";/\\]+\.csv"?$', disposicao), disposicao


def test_e2_financeiro_decimal_com_virgula_data_sp_status_pt(client, contas, cenario):
    linhas = _csv(_get(client, contas.fin.token, _rotas_csv()["financeiro"]), "financeiro.csv")
    assert len(linhas) == 1 + 4, f"cabecalho + 4 pagamentos: {linhas}"
    joana = _linha_com(linhas, "joana.aluna@u1.test", "financeiro joana")
    assert "987,65" in joana, f"valor com virgula decimal: {joana}"
    assert not any("987.65" in c for c in joana), f"valor com ponto decimal: {joana}"
    assert DATA_SP_VIRADA in joana, f"data em Sao Paulo dd/mm/aaaa HH:MM: {joana}"
    assert not any("2026-10-08" in c for c in joana), f"data crua em UTC: {joana}"
    assert "Aprovado" in joana, joana
    assert "Pendente" in _linha_com(linhas, "pedro.aluno@u1.test", "pedro")
    assert "Recusado" in _linha_com(linhas, "rita.aluna@u1.test", "rita")
    assert "250,40" in _linha_com(linhas, "carla.aluna@u1.test", "carla")
    crus = {"approved", "pending", "rejected"}
    assert not any(c in crus for linha in linhas[1:] for c in linha), "status cru no CSV"


def test_e3_curso_status_pt_e_data_sp(client, contas, cenario):
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["curso"]), "curso.csv")
    assert len(linhas) == 1 + 3, f"cabecalho + joana, rita, bruno: {linhas}"
    joana = _linha_com(linhas, "joana.aluna@u1.test", "curso joana")
    assert "Ativa" in joana and DATA_SP_VIRADA in joana, joana
    assert "Aprovado" in joana, f"status do pagamento em portugues: {joana}"
    assert "987,65" in joana, f"valor com virgula (Gestao ve valores): {joana}"
    assert "Cancelada" in _linha_com(linhas, "rita.aluna@u1.test", "rita")
    assert "Pendente" in _linha_com(linhas, "bruno.aluno@u1.test", "bruno")
    crus = {"active", "cancelled", "pending", "approved", "rejected"}
    assert not any(c in crus for linha in linhas[1:] for c in linha), "status cru no CSV"


def test_e4_alunos_data_sp(client, contas, cenario):
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["alunos"]), "alunos.csv")
    assert len(linhas) == 1 + 7, f"cabecalho + 7 alunos: {len(linhas)}"
    joana = _linha_com(linhas, "joana.aluna@u1.test", "alunos joana")
    assert "Joana Aluna" in joana
    assert DATA_SP_VIRADA in joana, f"data em Sao Paulo: {joana}"
    assert not any("2026-10-08" in c for c in joana), joana
    emails = {linha[i] for linha in linhas[1:] for i in range(len(linha)) if "@" in linha[i]}
    assert not emails & {"ana.gestora@u1.test", "fernanda.fin@u1.test", "sergio.sup@u1.test"}, \
        "funcionario nao entra no CSV de alunos"


# =====================================================================================
# F  CSV: injecao de formula
# =====================================================================================

NOMES_PERIGOSOS = [
    '=HYPERLINK("http://evil.test","clique")',
    "+SOMA(1;2)",
    "-2+3",
    "@SUM(A1:A2)",
    "\tTabulado",
    "\rRetorno",
]


@pytest.mark.parametrize("indice", range(len(NOMES_PERIGOSOS)))
def test_f1_celula_perigosa_recebe_apostrofo(client, contas, cenario, indice):
    nome = NOMES_PERIGOSOS[indice]
    email = f"formula{indice}@u1.test"
    aluno = _conta(email, nome, "student")
    _matricula(aluno.id, CURSO_PY, "active", "2026-09-10 12:00:00", 100.0, "approved")
    for relatorio in ("alunos", "curso", "financeiro"):
        linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()[relatorio]), f"{relatorio}.csv")
        linha = _linha_com(linhas, email, f"{relatorio} formula{indice}")
        assert "'" + nome in linha, f"{relatorio}: nome {nome!r} sem apostrofo: {linha}"
        assert nome not in linha, f"{relatorio}: celula {nome!r} saiu crua: {linha}"


def test_f2_hyperlink_exato(client, contas, cenario):
    nome = '=HYPERLINK("http://evil.test","x")'
    aluno = _conta("hyperlink@u1.test", nome, "student")
    _matricula(aluno.id, CURSO_XL, "pending", "2026-09-11 12:00:00")
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["alunos"]), "alunos.csv")
    linha = _linha_com(linhas, "hyperlink@u1.test", "hyperlink")
    assert "'=HYPERLINK(\"http://evil.test\",\"x\")" in linha
    for celula in (c for l in linhas for c in l):
        assert not celula.startswith(("=", "+", "@", "\t", "\r")), f"celula perigosa sem apostrofo: {celula!r}"


# =====================================================================================
# G  CSV: filtros, 404, sem dado sensivel
# =====================================================================================

def test_g1_alunos_csv_aplica_busca(client, contas, cenario):
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["alunos"], q="JOANA"), "alunos.csv?q")
    assert len(linhas) == 2, f"cabecalho + joana: {linhas}"
    _linha_com(linhas, "joana.aluna@u1.test", "joana")


def test_g2_financeiro_csv_aplica_busca_e_status(client, contas, cenario):
    linhas = _csv(_get(client, contas.fin.token, _rotas_csv()["financeiro"], status="approved"), "status")
    emails = {c for l in linhas[1:] for c in l if c.endswith("@u1.test")}
    assert emails == {"joana.aluna@u1.test", "carla.aluna@u1.test"}, emails
    linhas = _csv(_get(client, contas.fin.token, _rotas_csv()["financeiro"], q="python"), "q")
    emails = {c for l in linhas[1:] for c in l if c.endswith("@u1.test")}
    assert emails == {"joana.aluna@u1.test", "rita.aluna@u1.test"}, emails


def test_g3_curso_csv_aplica_status(client, contas, cenario):
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["curso"], status="active"), "curso status")
    assert len(linhas) == 2, f"cabecalho + joana: {linhas}"
    _linha_com(linhas, "joana.aluna@u1.test", "joana")


def test_g4_curso_inexistente_404(client, contas, cenario):
    r = _get(client, contas.gestao.token, "/api/dashboard/cursos/curso_que_nao_existe/alunos.csv")
    assert r.status_code == 404, f"HTTP {r.status_code} {r.text[:200]}"
    assert _eventos_export() == [], "CSV de curso inexistente nao grava export.csv"


@pytest.mark.parametrize("relatorio", ["alunos", "curso", "financeiro"])
def test_g5_sem_senha_nem_material(client, contas, cenario, relatorio):
    r = _get(client, contas.gestao.token, _rotas_csv()[relatorio])
    linhas = _csv(r, relatorio)
    texto = r.content.decode("utf-8-sig")
    assert HASH_SECRETO not in texto and "$2b$" not in texto, "hash de senha no CSV"
    assert URL_MATERIAL not in texto and "materiais.test" not in texto, "URL de material no CSV"
    cabecalho = " ".join(linhas[0]).lower()
    for proibido in ("password", "senha", "hash", "token", "material"):
        assert proibido not in cabecalho, f"coluna {proibido!r} no CSV: {linhas[0]}"


def test_g6_vazio_so_cabecalho(client, contas, cenario):
    linhas = _csv(_get(client, contas.gestao.token, _rotas_csv()["alunos"], q="ninguem-u1"), "vazio")
    assert len(linhas) == 1, f"so o cabecalho: {linhas}"


# =====================================================================================
# H  CSV: evento export.csv
# =====================================================================================

@pytest.mark.parametrize("relatorio,perfil,marca", [
    ("alunos", "gestao", "alunos"),
    ("financeiro", "fin", "financeiro"),
    ("curso", "gestao", CURSO_PY),
])
def test_h1_exportacao_grava_evento_com_responsavel_do_token(client, contas, cenario, relatorio, perfil, marca):
    conta = getattr(contas, perfil)
    # Parametros que tentam trocar o responsavel: devem ser ignorados (IDOR, D45).
    r = _get(client, conta.token, _rotas_csv()[relatorio], user_id=contas.joana.id,
             actor_email="joana.aluna@u1.test")
    _csv(r, relatorio)
    eventos = _eventos_export()
    assert len(eventos) == 1, f"um evento export.csv por exportacao: {eventos}"
    evento = eventos[0]
    assert marca in (evento.get("entity_id") or ""), f"relatorio em entity_id: {evento}"
    assert evento["user_id"] == conta.id, evento
    assert evento["actor_email"] == conta.email, evento
    assert evento["role"] == conta.role, evento


def test_h2_cada_exportacao_um_evento(client, contas, cenario):
    for _ in range(2):
        _csv(_get(client, contas.gestao.token, _rotas_csv()["alunos"]), "alunos")
    _csv(_get(client, contas.fin.token, _rotas_csv()["financeiro"]), "financeiro")
    eventos = _eventos_export()
    assert len(eventos) == 3
    assert {e["actor_email"] for e in eventos} == {contas.gestao.email, contas.fin.email}


def test_h3_evento_visivel_na_auditoria(client, contas, cenario):
    _csv(_get(client, contas.gestao.token, _rotas_csv()["financeiro"]), "financeiro")
    corpo = _ok(_get(client, contas.gestao.token, AUDIT, action="export.csv"), "audit export")
    assert len(corpo["logs"]) == 1
    assert "financeiro" in (corpo["logs"][0]["entity_id"] or "")
