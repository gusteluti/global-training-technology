"""F5a - Turma no checkout, reserva de vaga de 30 min e lotacao (inclui S8) (D75, modo autonomo D69).

Escritos ANTES da implementacao. Contrato (D75):
  - GET /api/courses/{course_id}/turmas (publico): turmas abertas do curso nao arquivado (`starts_on` nulo ou >= hoje
    em Sao Paulo), corpo = lista `[{id, name, starts_on, capacity, seats_left}]` (`seats_left` nulo sem capacidade),
    ordem por `starts_on` (nulos por ultimo) e nome. Nenhum dado de aluno. Curso inexistente ou arquivado -> 404
    `Course not found`.
  - Ocupacao para venda: `active` + `pending` com `reserved_until` > agora + `pending` sem `reserved_until`.
    Nova coluna `enrollments.reserved_until`. Os numeros de turma do dashboard (L1) nao mudam.
  - Checkouts (aluno e landing) aceitam `class_id` opcional; sem ele, comportamento de hoje (sem turma). Com ele:
    turma de outro curso, inexistente ou ja iniciada -> 404 `Turma não encontrada`; lotada -> 409 `Esta turma está
    lotada. Escolha outra turma.`; senao a matricula nasce com a turma e `reserved_until` = agora + 30 min.
    Conferencia e gravacao atomicas.
  - Retomada (D72) com `class_id`: troca a turma da pendente (mesma conferencia de vaga) e renova a reserva.
  - S8: webhook aprovado depois de a reserva expirar, com a turma lotada por outros -> pagamento e matricula ativados,
    `class_id` nulo, evento `enrollment.class_overflow`. Com vaga, mantem a turma.

Grupos
  T  endpoint publico de turmas (abertas por dia de SP, seats_left, ordem, 404, nenhum dado de aluno)      [red]
  K  checkout com turma nos dois fluxos (nasce com turma e reserva de ~30 min; 404; 409)                 [red]
  C  compatibilidade: sem `class_id` (ou null) segue sem turma; schema/migracao da coluna nova      [caract./red]
  O  ocupacao: reserva expirada libera; pendente sem reserva, ativa ocupam; baixadas nao ocupam             [red]
  X  concorrencia da ultima vaga (barreira no gateway falso: duas compras ao mesmo tempo, uma vende)        [red]
  R  retomada com troca de turma e renovacao da reserva                                                     [red]
  S  S8: webhook apos expirar, turma lotada -> active sem turma + evento; com vaga mantem                   [red]
  D  numeros de turma do dashboard L1 inalterados                                                [caracterizacao]
  M  mock efetivo (PAYMENTS_MOCK=1 + APP_ENV=development) respeita as mesmas regras                          [red]
  I  IDOR / 401 / 403 / recurso pago so com active                                               [caract./red]

Controle do relogio: o teste nao congela o relogio do servidor. `reserved_until` e conferido dentro da janela
[antes da requisicao + 30 min, depois da requisicao + 30 min] (com 2 s de folga pelo truncamento em segundos), em UTC
(D71: banco e API em UTC). Para "expirar" uma reserva, o teste reescreve `reserved_until` no passado no MESMO formato
em que o backend gravou (o formato e escolha do dev; o teste so exige que seja data/hora ISO ou epoch).

Convencoes (padrao de test_s1/test_l1): banco temporario do conftest, cursos em diretorio temporario, Mercado Pago
falso por patch de `payments.routes.requests.post/get`, webhook assinado com o segredo de teste, PAYMENTS_MOCK e
APP_ENV removidos do ambiente. Turmas criadas por Database.create_class (camada existente da L1).
"""

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from apoio_mercado_pago import SEGREDO_WEBHOOK, corpo_pagamento_mp, id_de_pagamento, post_webhook
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
ROTA_ALUNO = "/api/student/checkout"
ROTA_LANDING = "/api/payments/create-checkout"
CURSO = "curso_f5a"
OUTRO_CURSO = "curso_f5a_outro"
ARQUIVADO = "curso_f5a_arquivado"
SEM_TURMA = "curso_f5a_sem_turma"
PRECO = 149.9
PRECO_OUTRO = 89.9
URL_MATERIAL = "https://materiais.test/f5a/apostila.pdf"
URL_GATEWAY = "https://mp.test/f5a/checkout"
ERR_TURMA = "Turma não encontrada"
ERR_LOTADA = "Esta turma está lotada. Escolha outra turma."
ERR_CURSO = "Course not found"
EVENTO_OVERFLOW = "enrollment.class_overflow"
ACAO_MOCK = "payment.mock_approved"
CAMPOS_TURMA_PUBLICA = {"id", "name", "starts_on", "capacity", "seats_left"}
STATUS_PAGAMENTO = {"pending": "pending", "active": "approved", "cancelled": "cancelled", "refunded": "refunded"}
RESERVA = timedelta(minutes=30)
FOLGA = timedelta(seconds=2)


# =========================================================================================
# Relogio: dia de Sao Paulo (-3 h fixo, D71) e leitura/escrita de reserved_until
# =========================================================================================

def _agora():
    return datetime.now(timezone.utc)


def _hoje_sp():
    return (_agora() - timedelta(hours=3)).date()


def _dia_sp(delta_dias):
    return (_hoje_sp() + timedelta(days=delta_dias)).isoformat()


_RE_DATA = re.compile(r"^(\d{4}-\d{2}-\d{2})([T ])(\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def _partes(valor):
    m = _RE_DATA.match(str(valor).strip())
    assert m, f"reserved_until em formato inesperado: {valor!r}"
    fuso = m[5]
    if fuso in (None, "Z"):
        fuso = "+00:00"
    elif ":" not in fuso:
        fuso = f"{fuso[:3]}:{fuso[3:]}"
    return m, datetime.fromisoformat(f"{m[1]}T{m[3]}{m[4] or ''}{fuso}")


def _ler_instante(valor):
    """reserved_until gravado pelo backend -> datetime UTC. Aceita ISO ('T' ou espaco, fracao e fuso opcionais;
    sem fuso = UTC, D71) ou epoch em segundos."""
    assert valor is not None, "reserved_until esta nulo"
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor, timezone.utc)
    return _partes(valor)[1].astimezone(timezone.utc)


def _escrever_como(modelo, instante_utc):
    """Formata `instante_utc` no mesmo formato de `modelo` (o valor que o backend gravou)."""
    if isinstance(modelo, (int, float)):
        return type(modelo)(instante_utc.timestamp())
    m, original = _partes(modelo)
    local = instante_utc.astimezone(original.tzinfo)
    texto = local.strftime("%Y-%m-%d") + m[2] + local.strftime("%H:%M:%S")
    if m[4]:
        casas = len(m[4]) - 1
        texto += "." + f"{local.microsecond:06d}"[:casas].ljust(casas, "0")
    if m[5]:
        texto += m[5]
    return texto


# =========================================================================================
# Mercado Pago falso (mesmo padrao da S1)
# =========================================================================================

class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []
        self.get_chamadas = []
        self.pagamentos = {}
        self.barreira = None
        self._trava = threading.Lock()

    def post(self, url, *args, **kwargs):
        with self._trava:
            self.post_chamadas.append((url, kwargs))
            n = len(self.post_chamadas)
        if self.barreira is not None:
            # Concorrencia (grupo X): as duas compras chegam ao gateway e seguem juntas.
            try:
                self.barreira.wait()
            except threading.BrokenBarrierError:
                pass
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": f"pref-f5a-{n}", "init_point": f"{URL_GATEWAY}/{n}"}
        resposta.text = json.dumps({"id": f"pref-f5a-{n}"})
        return resposta

    def get(self, url, *args, **kwargs):
        self.get_chamadas.append((url, kwargs))
        corpo = self.pagamentos.get(str(url).rsplit("/", 1)[-1])
        resposta = MagicMock()
        if corpo is None:
            resposta.status_code = 404
            resposta.json.return_value = {"message": "not found"}
            resposta.text = '{"message": "not found"}'
        else:
            resposta.status_code = 200
            resposta.json.return_value = corpo
            resposta.text = json.dumps(corpo)
        return resposta

    def definir(self, mp_id, status, referencia, valor):
        self.pagamentos[str(mp_id)] = corpo_pagamento_mp(status, referencia, valor, mp_id)


@pytest.fixture(autouse=True)
def ambiente_f5a(monkeypatch, tmp_path):
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-f5a")
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", SEGREDO_WEBHOOK)
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


def _gravar_curso(diretorio, course_id, nome, preco, materiais=None, arquivado=False):
    dados = {"id": course_id, "name": nome, "description": f"{nome} da F5a", "price": preco,
             "materials": materiais or []}
    if arquivado:
        dados["archived"] = True
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _gravar_curso(diretorio, CURSO, "Curso F5a", PRECO, [{"title": "Apostila F5a", "url": URL_MATERIAL, "type": "pdf"}])
    _gravar_curso(diretorio, OUTRO_CURSO, "Outro Curso F5a", PRECO_OUTRO)
    _gravar_curso(diretorio, ARQUIVADO, "Curso Arquivado F5a", PRECO, arquivado=True)
    _gravar_curso(diretorio, SEM_TURMA, "Curso Sem Turma F5a", PRECO_OUTRO)
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    # Sem `with`: nao dispara o startup (agente de chat); checkout, turmas e webhook nao dependem dele.
    return TestClient(fastapi_app, raise_server_exceptions=False)


@pytest.fixture
def gw():
    falso = GatewayFalso()
    with patch("payments.routes.requests.post", side_effect=falso.post), \
         patch("payments.routes.requests.get", side_effect=falso.get):
        yield falso


# =========================================================================================
# Helpers
# =========================================================================================

def _sql(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _colunas(tabela):
    return {r["name"] for r in _sql(f"PRAGMA table_info({tabela})")}


def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _conta(email, nome, perfil="student"):
    user_id = Database.add_user(email, nome, get_password_hash("senha-f5a-123"), role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        ana=_conta("ana.aluna@f5a.test", "Ana Aluna"),
        bia=_conta("bia.aluna@f5a.test", "Bia Aluna"),
        caio=_conta("caio.aluno@f5a.test", "Caio Aluno"),
        sup=_conta("sergio.sup@f5a.test", "Sergio Suporte", "support"),
    )


def _turma(nome, course_id=CURSO, starts_on=None, capacity=None):
    if starts_on is None:
        starts_on = _dia_sp(10)
    elif starts_on == "nulo":
        starts_on = None
    class_id = Database.create_class(course_id, nome, starts_on, capacity)
    assert class_id is not None, f"seed: turma {nome} ja existe"
    return class_id


def _semear(user_id, status, course_id=CURSO, class_id=None, valor=PRECO):
    """Matricula com status e pagamento coerentes, SEM reserved_until (como a Gestao ou antes da F5a)."""
    referencia = f"{course_id}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(user_id, course_id, referencia)
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    _executar("UPDATE enrollments SET status = ?, class_id = ? WHERE id = ?", (status, class_id, enrollment_id))
    _executar("UPDATE payments SET status = ? WHERE id = ?", (STATUS_PAGAMENTO[status], payment_id))
    return SimpleNamespace(id=enrollment_id, payment_id=payment_id, ref=referencia)


def _aluno_avulso(status, class_id, course_id=CURSO):
    sufixo = uuid.uuid4().hex[:8]
    user_id = Database.get_or_create_user(f"avulso.{sufixo}@f5a.test", f"Avulso {sufixo}")
    return _semear(user_id, status, course_id=course_id, class_id=class_id)


def _comprar(client, token, **corpo):
    payload = {"course_id": CURSO}
    payload.update(corpo)
    return client.post(ROTA_ALUNO, json=payload, headers=_auth(token))


def _comprar_landing(client, email, course_id=CURSO, nome="Comprador Landing", **extra):
    payload = {"course_id": course_id, "payer": {"name": nome, "email": email}}
    payload.update(extra)
    return client.post(ROTA_LANDING, json=payload)


def _matricula_por_ref(ref):
    linhas = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))
    assert len(linhas) == 1, linhas
    return linhas[0]


def _matricula(enrollment_id):
    return _sql("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,))[0]


def _comprar_ok(client, token, class_id, **extra):
    """Compra do aluno com turma; devolve a matricula criada/retomada e a janela de tempo da requisicao."""
    antes = _agora()
    r = _comprar(client, token, class_id=class_id, **extra)
    depois = _agora()
    assert r.status_code == 200, r.text
    m = _matricula_por_ref(r.json()["external_reference"])
    return SimpleNamespace(m=m, antes=antes, depois=depois, corpo=r.json())


def _assert_reserva_de_30_min(valor, antes, depois):
    instante = _ler_instante(valor)
    minimo = (antes + RESERVA - FOLGA).replace(microsecond=0)
    maximo = depois + RESERVA + FOLGA
    assert minimo <= instante <= maximo, (
        f"reserved_until={valor!r} ({instante.isoformat()}) fora de [{minimo.isoformat()}, {maximo.isoformat()}] "
        "(agora + 30 min, em UTC)")


def _mover_reserva(enrollment_id, minutos_a_partir_de_agora):
    """Reescreve reserved_until em agora + N min (N negativo = vencida), no mesmo formato gravado pelo backend."""
    atual = _matricula(enrollment_id).get("reserved_until")
    assert atual is not None, "pre-condicao: a matricula deveria ter reserved_until"
    novo = _escrever_como(atual, _agora() + timedelta(minutes=minutos_a_partir_de_agora))
    _executar("UPDATE enrollments SET reserved_until = ? WHERE id = ?", (novo, enrollment_id))
    return _ler_instante(_matricula(enrollment_id)["reserved_until"])


def _vencer_reserva(enrollment_id, minutos_atras=1):
    assert _mover_reserva(enrollment_id, -minutos_atras) < _agora()


def _contagens():
    return {
        "users": len(_sql("SELECT id FROM users")),
        "enrollments": len(_sql("SELECT id FROM enrollments")),
        "payments": len(_sql("SELECT id FROM payments")),
    }


def _foto():
    return (
        _sql("SELECT * FROM enrollments ORDER BY id"),
        _sql("SELECT * FROM payments ORDER BY id"),
        len(_sql("SELECT id FROM users")),
    )


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _assert_erro(r, status, texto):
    assert r.status_code == status, r.text
    assert r.json() == {"detail": texto}, r.text


def _turmas_publicas(client, course_id=CURSO):
    r = client.get(f"/api/courses/{course_id}/turmas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert isinstance(corpo, list), f"D75: o corpo e a lista de turmas: {corpo!r}"
    return corpo


def _publica(client, class_id, course_id=CURSO):
    achadas = [t for t in _turmas_publicas(client, course_id) if t["id"] == class_id]
    assert len(achadas) == 1, f"turma {class_id} deveria estar aberta na lista publica"
    return achadas[0]


def _aprovar_pelo_webhook(client, gw, referencia, valor=PRECO):
    mp_id = id_de_pagamento(referencia)
    gw.definir(mp_id, "approved", referencia, valor)
    r = post_webhook(client, mp_id)
    assert r.status_code == 200, r.text
    return r


def _ligar_mock_efetivo(monkeypatch):
    monkeypatch.setenv("PAYMENTS_MOCK", "1")
    monkeypatch.setenv("APP_ENV", "development")


# =========================================================================================
# Grupo T - GET /api/courses/{course_id}/turmas (publico)
# =========================================================================================

def test_t1_lista_turmas_abertas_sem_token_com_campos_exatos(client):
    t = _turma("Turma Manha", starts_on=_dia_sp(7), capacity=20)
    r = client.get(f"/api/courses/{CURSO}/turmas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert isinstance(corpo, list), corpo
    assert corpo == [{"id": t, "name": "Turma Manha", "starts_on": _dia_sp(7), "capacity": 20, "seats_left": 20}]


def test_t2_turma_ja_iniciada_fica_de_fora_e_a_de_hoje_em_sp_entra(client):
    ontem = _turma("Ontem", starts_on=_dia_sp(-1), capacity=10)
    hoje = _turma("Hoje", starts_on=_dia_sp(0), capacity=10)
    sem_data = _turma("Sem data", starts_on="nulo", capacity=10)
    ids = [t["id"] for t in _turmas_publicas(client)]
    assert ontem not in ids, "turma com inicio antes de hoje (Sao Paulo) nao esta aberta"
    assert hoje in ids, "turma que comeca hoje (Sao Paulo) ainda esta aberta"
    assert sem_data in ids, "turma sem data esta aberta"


def test_t3_ordem_por_inicio_com_nulos_por_ultimo_e_depois_nome(client):
    b = _turma("B", starts_on=_dia_sp(5))
    a = _turma("A", starts_on=_dia_sp(5))
    z = _turma("Z", starts_on=_dia_sp(2))
    c = _turma("C", starts_on="nulo")
    a2 = _turma("A2", starts_on="nulo")
    assert [t["id"] for t in _turmas_publicas(client)] == [z, a, b, a2, c]


def test_t4_seats_left_desconta_so_a_ocupacao_de_venda(client, gw, contas):
    t = _turma("Cheia de casos", capacity=6)
    _aluno_avulso("active", t)                    # ocupa
    _aluno_avulso("pending", t)                   # pendente sem reserved_until: ocupa
    _aluno_avulso("cancelled", t)                 # nao ocupa
    _aluno_avulso("refunded", t)                  # nao ocupa
    valida = _comprar_ok(client, contas.ana.token, t)    # reserva valida: ocupa
    vencida = _comprar_ok(client, contas.bia.token, t)   # reserva vencida: nao ocupa
    _vencer_reserva(vencida.m["id"])
    assert valida.m["class_id"] == t
    assert _publica(client, t)["seats_left"] == 6 - 3


def test_t5_turma_sem_capacidade_tem_seats_left_nulo(client):
    t = _turma("Livre", capacity=None)
    _aluno_avulso("active", t)
    item = _publica(client, t)
    assert item["capacity"] is None and item["seats_left"] is None, item


def test_t6_lotada_aparece_com_zero_vagas(client):
    t = _turma("Lotada", capacity=1)
    _aluno_avulso("active", t)
    assert _publica(client, t)["seats_left"] == 0


def test_t7_so_turmas_do_proprio_curso(client):
    minha = _turma("Minha")
    outra = _turma("Outra", course_id=OUTRO_CURSO)
    ids = [t["id"] for t in _turmas_publicas(client)]
    assert minha in ids and outra not in ids
    assert [t["id"] for t in _turmas_publicas(client, OUTRO_CURSO)] == [outra]


def test_t8_curso_sem_turmas_devolve_lista_vazia(client):
    assert _turmas_publicas(client, SEM_TURMA) == []


@pytest.mark.parametrize("course_id", ["curso_que_nao_existe", ARQUIVADO])
def test_t9_curso_inexistente_ou_arquivado_404(client, course_id):
    if course_id == ARQUIVADO:
        _turma("Turma do arquivado", course_id=ARQUIVADO)
    r = client.get(f"/api/courses/{course_id}/turmas")
    _assert_erro(r, 404, ERR_CURSO)


def test_t10_nenhum_dado_de_aluno_nem_material_na_resposta(client, gw, contas):
    t = _turma("Com alunos", capacity=5)
    _semear(contas.bia.id, "active", class_id=t)
    _comprar_ok(client, contas.ana.token, t)
    r = client.get(f"/api/courses/{CURSO}/turmas")
    assert r.status_code == 200, r.text
    for item in r.json():
        assert set(item) == CAMPOS_TURMA_PUBLICA, item
    for proibido in (contas.ana.email, contas.bia.email, "Ana Aluna", "Bia Aluna", URL_MATERIAL, "external_reference"):
        assert proibido not in r.text, f"{proibido!r} vazou na lista publica de turmas"


# =========================================================================================
# Grupo K - checkout com turma (aluno e landing)
# =========================================================================================

def test_k1_aluno_compra_com_turma_nasce_pendente_com_turma_e_reserva_de_30_min(client, gw, contas):
    t = _turma("K1", capacity=10)
    compra = _comprar_ok(client, contas.ana.token, t)
    assert compra.m["user_id"] == contas.ana.id
    assert compra.m["status"] == "pending"
    assert compra.m["class_id"] == t
    _assert_reserva_de_30_min(compra.m["reserved_until"], compra.antes, compra.depois)
    assert compra.corpo.get("checkout_url") == f"{URL_GATEWAY}/1"
    assert _publica(client, t)["seats_left"] == 9


def test_k2_landing_compra_com_turma_nasce_pendente_com_turma_e_reserva_de_30_min(client, gw):
    t = _turma("K2", capacity=10)
    antes = _agora()
    r = _comprar_landing(client, "novo.k2@f5a.test", class_id=t)
    depois = _agora()
    assert r.status_code == 200, r.text
    m = _matricula_por_ref(r.json()["external_reference"])
    assert m["status"] == "pending" and m["class_id"] == t, m
    _assert_reserva_de_30_min(m["reserved_until"], antes, depois)


@pytest.mark.parametrize("fluxo", ["aluno", "landing"])
@pytest.mark.parametrize("caso", ["outro_curso", "inexistente", "ja_iniciada", "id_enorme"])
def test_k3_turma_de_outro_curso_inexistente_ou_iniciada_404(client, gw, contas, fluxo, caso):
    if caso == "outro_curso":
        class_id = _turma("De outro curso", course_id=OUTRO_CURSO, capacity=10)
    elif caso == "inexistente":
        class_id = _turma("Existe", capacity=10) + 999
    elif caso == "ja_iniciada":
        class_id = _turma("Iniciada", starts_on=_dia_sp(-1), capacity=10)
    else:
        class_id = 2 ** 63
    antes = _foto()
    if fluxo == "aluno":
        r = _comprar(client, contas.ana.token, class_id=class_id)
    else:
        r = _comprar_landing(client, "anon.k3@f5a.test", class_id=class_id)
    _assert_erro(r, 404, ERR_TURMA)
    assert _foto() == antes, "turma invalida nao pode criar nem alterar nada"


@pytest.mark.parametrize("fluxo", ["aluno", "landing"])
def test_k4_turma_lotada_409(client, gw, contas, fluxo):
    t = _turma("Lotada K4", capacity=2)
    _aluno_avulso("active", t)
    _aluno_avulso("pending", t)
    antes = _foto()
    if fluxo == "aluno":
        r = _comprar(client, contas.ana.token, class_id=t)
    else:
        r = _comprar_landing(client, "anon.k4@f5a.test", class_id=t)
    _assert_erro(r, 409, ERR_LOTADA)
    assert _foto() == antes, "turma lotada nao pode criar nem alterar nada"


def test_k5_turma_que_comeca_hoje_em_sp_vende(client, gw, contas):
    t = _turma("Hoje K5", starts_on=_dia_sp(0), capacity=3)
    compra = _comprar_ok(client, contas.ana.token, t)
    assert compra.m["class_id"] == t


def test_k6_turma_sem_data_e_sem_capacidade_vende(client, gw, contas):
    t = _turma("Livre K6", starts_on="nulo", capacity=None)
    compra = _comprar_ok(client, contas.ana.token, t)
    assert compra.m["class_id"] == t
    _assert_reserva_de_30_min(compra.m["reserved_until"], compra.antes, compra.depois)


# =========================================================================================
# Grupo C - compatibilidade
# =========================================================================================

@pytest.mark.parametrize("fluxo", ["aluno", "landing"])
@pytest.mark.parametrize("enviar_null", [False, True])
def test_c1_sem_class_id_compra_sem_turma_mesmo_com_turmas_abertas(client, gw, contas, fluxo, enviar_null):
    """[caracterizacao] sem class_id (ausente ou null): comportamento de hoje, matricula sem turma."""
    t = _turma("Aberta C1", capacity=1)
    extra = {"class_id": None} if enviar_null else {}
    if fluxo == "aluno":
        r = _comprar(client, contas.ana.token, **extra)
    else:
        r = _comprar_landing(client, "anon.c1@f5a.test", **extra)
    assert r.status_code == 200, r.text
    m = _matricula_por_ref(r.json()["external_reference"])
    assert m["status"] == "pending" and m["class_id"] is None, m
    # E a compra sem turma nao consome a vaga da turma.
    r2 = _comprar(client, contas.bia.token, class_id=t)
    assert r2.status_code == 200, r2.text


def test_c2_schema_tem_a_coluna_reserved_until(banco):
    assert "reserved_until" in _colunas("enrollments"), "coluna enrollments.reserved_until ausente"


def test_c3_banco_anterior_a_f5a_e_migrado_e_pendente_antiga_ocupa_vaga(db_path, cursos, gw):
    """Banco sem reserved_until: init_db acrescenta a coluna, a pendente antiga fica com reserva nula e ocupa a vaga."""
    Database.init_db()
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        for tipo, nome, sql in conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL"
        ).fetchall():
            if "reserved_until" in sql:
                conn.execute(f"DROP {tipo.upper()} {nome}")
        colunas = {r[1] for r in conn.execute("PRAGMA table_info(enrollments)").fetchall()}
        if "reserved_until" in colunas:
            conn.execute("ALTER TABLE enrollments DROP COLUMN reserved_until")
        conn.commit()
    finally:
        conn.close()
    assert "reserved_until" not in _colunas("enrollments"), "pre-condicao: banco anterior a F5a"
    t = _turma("Antiga", capacity=1)
    antiga = _aluno_avulso("pending", t)

    Database.init_db()
    assert "reserved_until" in _colunas("enrollments"), "init_db deve acrescentar enrollments.reserved_until"
    m = _matricula(antiga.id)
    assert m["reserved_until"] is None and m["class_id"] == t and m["status"] == "pending", m
    Database.init_db()  # idempotente
    assert "reserved_until" in _colunas("enrollments")

    from app import app as fastapi_app
    c = TestClient(fastapi_app, raise_server_exceptions=False)
    assert _publica(c, t)["seats_left"] == 0, "pendente antiga sem reserva ocupa a vaga"
    _assert_erro(_comprar_landing(c, "anon.c3@f5a.test", class_id=t), 409, ERR_LOTADA)


# =========================================================================================
# Grupo O - ocupacao para venda
# =========================================================================================

def test_o1_reserva_expirada_libera_a_vaga(client, gw, contas):
    t = _turma("O1", capacity=1)
    primeira = _comprar_ok(client, contas.ana.token, t)
    _assert_erro(_comprar(client, contas.bia.token, class_id=t), 409, ERR_LOTADA)
    _vencer_reserva(primeira.m["id"])
    assert _publica(client, t)["seats_left"] == 1
    segunda = _comprar_ok(client, contas.bia.token, t)
    assert segunda.m["class_id"] == t
    assert _matricula(primeira.m["id"])["status"] == "pending", "a reserva vencida nao cancela a matricula"


def test_o2_pendente_sem_reserved_until_ocupa_vaga(client, gw, contas):
    t = _turma("O2", capacity=1)
    _aluno_avulso("pending", t)
    _assert_erro(_comprar(client, contas.ana.token, class_id=t), 409, ERR_LOTADA)


def test_o3_ativa_ocupa_vaga_mesmo_com_reserva_vencida(client, gw, contas):
    t = _turma("O3", capacity=1)
    compra = _comprar_ok(client, contas.ana.token, t)
    _executar("UPDATE enrollments SET status = 'active' WHERE id = ?", (compra.m["id"],))
    _vencer_reserva(compra.m["id"])
    _assert_erro(_comprar(client, contas.bia.token, class_id=t), 409, ERR_LOTADA)


@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_o4_cancelada_ou_reembolsada_nao_ocupa(client, gw, contas, status):
    t = _turma(f"O4 {status}", capacity=1)
    _aluno_avulso(status, t)
    assert _comprar_ok(client, contas.ana.token, t).m["class_id"] == t


def test_o5_reserva_valida_de_outro_aluno_ocupa(client, gw, contas):
    t = _turma("O5", capacity=2)
    _comprar_ok(client, contas.ana.token, t)
    _comprar_ok(client, contas.bia.token, t)
    _assert_erro(_comprar(client, contas.caio.token, class_id=t), 409, ERR_LOTADA)


# =========================================================================================
# Grupo X - concorrencia da ultima vaga
# =========================================================================================

@pytest.mark.parametrize("fluxo", ["aluno", "landing"])
def test_x1_duas_compras_simultaneas_da_ultima_vaga_uma_vende_outra_409(banco, cursos, gw, contas, fluxo):
    """As duas compras chegam juntas ao gateway (barreira no gateway falso); uma conferencia feita antes do gateway e
    uma gravacao depois, fora de uma transacao, venderiam as duas. Conferencia e gravacao atomicas: so uma vende."""
    from app import app as fastapi_app

    t = _turma("Ultima vaga", capacity=1)
    gw.barreira = threading.Barrier(2, timeout=3)
    respostas = {}

    def comprar(quem):
        c = TestClient(fastapi_app, raise_server_exceptions=False)
        if fluxo == "aluno":
            token = getattr(contas, quem).token
            respostas[quem] = c.post(ROTA_ALUNO, json={"course_id": CURSO, "class_id": t}, headers=_auth(token))
        else:
            respostas[quem] = c.post(ROTA_LANDING, json={
                "course_id": CURSO, "class_id": t,
                "payer": {"name": f"Comprador {quem}", "email": f"{quem}.x1@f5a.test"}})

    threads = [threading.Thread(target=comprar, args=(quem,)) for quem in ("ana", "bia")]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert set(respostas) == {"ana", "bia"}, f"as duas requisicoes precisam terminar: {respostas}"
    codigos = sorted(r.status_code for r in respostas.values())
    assert codigos == [200, 409], {q: (r.status_code, r.text[:200]) for q, r in respostas.items()}
    perdedora = [r for r in respostas.values() if r.status_code == 409][0]
    assert perdedora.json() == {"detail": ERR_LOTADA}
    na_turma = _sql("SELECT * FROM enrollments WHERE class_id = ? AND status IN ('pending', 'active')", (t,))
    assert len(na_turma) == 1, f"a ultima vaga foi vendida {len(na_turma)} vezes"
    assert _publica(TestClient(fastapi_app), t)["seats_left"] == 0


# =========================================================================================
# Grupo R - retomada (D72) com class_id
# =========================================================================================

def test_r1_retomada_troca_a_turma_e_renova_a_reserva(client, gw, contas):
    t1 = _turma("R1 primeira", capacity=5)
    t2 = _turma("R1 segunda", capacity=5)
    primeira = _comprar_ok(client, contas.ana.token, t1)
    _vencer_reserva(primeira.m["id"], minutos_atras=10)
    contagens = _contagens()
    segunda = _comprar_ok(client, contas.ana.token, t2)
    assert _contagens() == contagens, "a retomada nao cria matricula nem pagamento"
    assert segunda.m["id"] == primeira.m["id"]
    assert segunda.m["external_reference"] == primeira.m["external_reference"]
    assert segunda.m["class_id"] == t2
    _assert_reserva_de_30_min(segunda.m["reserved_until"], segunda.antes, segunda.depois)
    assert _publica(client, t1)["seats_left"] == 5
    assert _publica(client, t2)["seats_left"] == 4


def test_r2_retomada_na_mesma_turma_com_a_propria_reserva_na_ultima_vaga_renova(client, gw, contas):
    """A propria reserva nao conta contra a retomada (senao o aluno nunca conseguiria retomar a ultima vaga)."""
    t = _turma("R2", capacity=1)
    primeira = _comprar_ok(client, contas.ana.token, t)
    assert _mover_reserva(primeira.m["id"], 5) > _agora()  # ainda valida, com 5 min restantes
    segunda = _comprar_ok(client, contas.ana.token, t)
    assert segunda.m["id"] == primeira.m["id"] and segunda.m["class_id"] == t
    _assert_reserva_de_30_min(segunda.m["reserved_until"], segunda.antes, segunda.depois)


def test_r3_retomada_para_turma_lotada_409_sem_alterar_a_pendente(client, gw, contas):
    t1 = _turma("R3 minha", capacity=5)
    cheia = _turma("R3 cheia", capacity=1)
    _semear(contas.bia.id, "active", class_id=cheia)
    primeira = _comprar_ok(client, contas.ana.token, t1)
    antes = _foto()
    _assert_erro(_comprar(client, contas.ana.token, class_id=cheia), 409, ERR_LOTADA)
    assert _foto() == antes, "retomada recusada nao altera turma, reserva nem pagamento"
    assert _matricula(primeira.m["id"])["class_id"] == t1


@pytest.mark.parametrize("caso", ["outro_curso", "ja_iniciada"])
def test_r4_retomada_para_turma_invalida_404_sem_alterar_a_pendente(client, gw, contas, caso):
    t1 = _turma("R4 minha", capacity=5)
    if caso == "outro_curso":
        alvo = _turma("R4 alheia", course_id=OUTRO_CURSO, capacity=5)
    else:
        alvo = _turma("R4 iniciada", starts_on=_dia_sp(-2), capacity=5)
    _comprar_ok(client, contas.ana.token, t1)
    antes = _foto()
    _assert_erro(_comprar(client, contas.ana.token, class_id=alvo), 404, ERR_TURMA)
    assert _foto() == antes


def test_r5_retomada_de_pendente_sem_turma_ganha_turma(client, gw, contas):
    """Pendente criada sem turma (antes da F5a ou sem escolha) e retomada com class_id: passa a ter a turma."""
    pendente = _semear(contas.ana.id, "pending")
    t = _turma("R5", capacity=3)
    compra = _comprar_ok(client, contas.ana.token, t)
    assert compra.m["id"] == pendente.id and compra.m["class_id"] == t
    _assert_reserva_de_30_min(compra.m["reserved_until"], compra.antes, compra.depois)


def test_r6_retomada_pela_landing_troca_a_turma(client, gw, contas):
    t1 = _turma("R6 primeira", capacity=5)
    t2 = _turma("R6 segunda", capacity=5)
    primeira = _comprar_ok(client, contas.ana.token, t1)
    antes = _agora()
    r = _comprar_landing(client, contas.ana.email, class_id=t2)
    depois = _agora()
    assert r.status_code == 200, r.text
    m = _matricula(primeira.m["id"])
    assert r.json()["external_reference"] == m["external_reference"]
    assert m["class_id"] == t2
    _assert_reserva_de_30_min(m["reserved_until"], antes, depois)


# =========================================================================================
# Grupo S - S8: webhook aprovado depois de a reserva expirar
# =========================================================================================

@pytest.mark.parametrize("ocupante", ["pendente_com_reserva", "ativa", "pendente_da_gestao"])
def test_s1_expirada_e_turma_lotada_por_outro_ativa_sem_turma_e_grava_evento(client, gw, contas, ocupante):
    t = _turma("S8 lotada", capacity=1)
    da_ana = _comprar_ok(client, contas.ana.token, t)
    _vencer_reserva(da_ana.m["id"])
    if ocupante == "pendente_com_reserva":
        outro = _comprar_ok(client, contas.bia.token, t).m["id"]
    elif ocupante == "ativa":
        outro = _semear(contas.bia.id, "active", class_id=t).id
    else:
        outro = _semear(contas.bia.id, "pending", class_id=t).id

    _aprovar_pelo_webhook(client, gw, da_ana.m["external_reference"])

    m = _matricula(da_ana.m["id"])
    assert m["status"] == "active", "o dinheiro entrou: a matricula e ativada"
    assert m["class_id"] is None, "sem vaga: a matricula fica sem turma para a Gestao realocar"
    pagamento = _sql("SELECT status FROM payments WHERE enrollment_id = ?", (da_ana.m["id"],))
    assert [p["status"] for p in pagamento] == ["approved"]
    assert _matricula(outro)["class_id"] == t, "quem ocupava a vaga continua na turma"
    eventos = _eventos(EVENTO_OVERFLOW)
    assert len(eventos) == 1, eventos
    na_turma = _sql("SELECT id FROM enrollments WHERE class_id = ? AND status IN ('pending', 'active')", (t,))
    assert len(na_turma) == 1, "a turma nao pode passar da capacidade"


def test_s2_expirada_com_vaga_mantem_a_turma_sem_evento(client, gw, contas):
    t = _turma("S8 com vaga", capacity=2)
    da_ana = _comprar_ok(client, contas.ana.token, t)
    _vencer_reserva(da_ana.m["id"])
    _comprar_ok(client, contas.bia.token, t)
    _aprovar_pelo_webhook(client, gw, da_ana.m["external_reference"])
    m = _matricula(da_ana.m["id"])
    assert m["status"] == "active" and m["class_id"] == t, m
    assert _eventos(EVENTO_OVERFLOW) == []


def test_s3_aprovado_dentro_da_reserva_mantem_a_turma_sem_evento(client, gw, contas):
    t = _turma("S8 dentro", capacity=1)
    da_ana = _comprar_ok(client, contas.ana.token, t)
    _aprovar_pelo_webhook(client, gw, da_ana.m["external_reference"])
    m = _matricula(da_ana.m["id"])
    assert m["status"] == "active" and m["class_id"] == t, m
    assert _eventos(EVENTO_OVERFLOW) == []
    assert _publica(client, t)["seats_left"] == 0


def test_s4_aprovacao_sem_turma_nao_grava_evento(client, gw, contas):
    r = _comprar(client, contas.ana.token)
    assert r.status_code == 200, r.text
    _aprovar_pelo_webhook(client, gw, r.json()["external_reference"])
    assert _matricula_por_ref(r.json()["external_reference"])["status"] == "active"
    assert _eventos(EVENTO_OVERFLOW) == []


def test_s5_webhook_repetido_nao_duplica_o_evento(client, gw, contas):
    t = _turma("S8 repetido", capacity=1)
    da_ana = _comprar_ok(client, contas.ana.token, t)
    _vencer_reserva(da_ana.m["id"])
    _semear(contas.bia.id, "active", class_id=t)
    _aprovar_pelo_webhook(client, gw, da_ana.m["external_reference"])
    _aprovar_pelo_webhook(client, gw, da_ana.m["external_reference"])
    assert len(_eventos(EVENTO_OVERFLOW)) == 1
    assert _matricula(da_ana.m["id"])["class_id"] is None


# =========================================================================================
# Grupo D - numeros de turma do dashboard L1 inalterados [caracterizacao]
# =========================================================================================

def test_d1_dashboard_e_lista_da_gestao_contam_pendente_vencida_como_antes(client, gw, contas):
    t = _turma("D1", capacity=3)
    vencida = _comprar_ok(client, contas.ana.token, t)
    _vencer_reserva(vencida.m["id"])
    _comprar_ok(client, contas.bia.token, t)
    _semear(contas.caio.id, "active", class_id=t)
    token = create_admin_token(Role.ADMIN)

    r = client.get("/api/dashboard/cursos", headers=_auth(token))
    assert r.status_code == 200, r.text
    curso = [c for c in r.json()["courses"] if c["id"] == CURSO][0]
    turma = [c for c in curso["classes"] if c["id"] == t][0]
    assert (turma["enrolled"], turma["pending"], turma["total"]) == (1, 2, 3), turma

    r = client.get("/api/admin/classes", params={"course_id": CURSO}, headers=_auth(token))
    assert r.status_code == 200, r.text
    turma = [c for c in r.json()["classes"] if c["id"] == t][0]
    assert (turma["enrolled"], turma["pending"], turma["total"]) == (1, 2, 3), turma
    # Para venda, a pendente vencida nao ocupa.
    assert _publica(client, t)["seats_left"] == 1


# =========================================================================================
# Grupo M - mock efetivo
# =========================================================================================

def test_m1_mock_com_turma_ativa_com_a_turma(client, gw, contas, monkeypatch):
    t = _turma("M1", capacity=2)
    _ligar_mock_efetivo(monkeypatch)
    r = _comprar(client, contas.ana.token, class_id=t)
    assert r.status_code == 200, r.text
    assert r.json().get("mocked") is True
    m = _matricula_por_ref(r.json()["external_reference"])
    assert m["status"] == "active" and m["class_id"] == t, m
    assert gw.post_chamadas == []


@pytest.mark.parametrize("fluxo", ["aluno", "landing"])
def test_m2_mock_com_turma_lotada_409_sem_aprovar_nada(client, gw, contas, monkeypatch, fluxo):
    t = _turma("M2", capacity=1)
    _aluno_avulso("active", t)
    _ligar_mock_efetivo(monkeypatch)
    antes = _foto()
    if fluxo == "aluno":
        r = _comprar(client, contas.ana.token, class_id=t)
    else:
        r = _comprar_landing(client, "anon.m2@f5a.test", class_id=t)
    _assert_erro(r, 409, ERR_LOTADA)
    assert _foto() == antes
    assert _eventos(ACAO_MOCK) == [], "nenhum pagamento simulado pode ser registrado"


@pytest.mark.parametrize("caso", ["outro_curso", "ja_iniciada"])
def test_m3_mock_com_turma_invalida_404(client, gw, contas, monkeypatch, caso):
    if caso == "outro_curso":
        alvo = _turma("M3 alheia", course_id=OUTRO_CURSO, capacity=5)
    else:
        alvo = _turma("M3 iniciada", starts_on=_dia_sp(-1), capacity=5)
    _ligar_mock_efetivo(monkeypatch)
    antes = _foto()
    _assert_erro(_comprar(client, contas.ana.token, class_id=alvo), 404, ERR_TURMA)
    assert _foto() == antes
    assert _eventos(ACAO_MOCK) == []


# =========================================================================================
# Grupo I - IDOR, 401/403 e recurso pago
# =========================================================================================

def test_i1_idor_id_e_email_de_outro_aluno_no_corpo_sao_ignorados(client, gw, contas):
    t = _turma("I1", capacity=5)
    compra = _comprar_ok(client, contas.ana.token, t, user_id=contas.bia.id, email=contas.bia.email,
                         payer={"email": contas.bia.email, "name": "Bia"})
    assert compra.m["user_id"] == contas.ana.id
    assert compra.m["class_id"] == t
    assert _sql("SELECT id FROM enrollments WHERE user_id = ?", (contas.bia.id,)) == []


def test_i2_retomada_com_turma_nunca_mexe_na_pendente_de_outro_aluno(client, gw, contas):
    t1 = _turma("I2 a", capacity=5)
    t2 = _turma("I2 b", capacity=5)
    da_bia = _comprar_ok(client, contas.bia.token, t1)
    foto_bia = _matricula(da_bia.m["id"])
    _comprar_ok(client, contas.ana.token, t2, user_id=contas.bia.id, email=contas.bia.email)
    assert _matricula(da_bia.m["id"]) == foto_bia


def _forjado():
    return jose_jwt.encode({"user_id": 1, "email": "x@f5a.test", "role": "student"},
                           "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")


@pytest.mark.parametrize("token", [None, "forjado"])
def test_i3_checkout_do_aluno_com_turma_sem_token_ou_forjado_401(client, gw, contas, token):
    t = _turma("I3", capacity=5)
    antes = _foto()
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO, "class_id": t},
                    headers=_auth(_forjado() if token else None))
    assert r.status_code == 401, r.text
    assert _foto() == antes


def test_i4_checkout_do_aluno_com_turma_por_funcionario_403(client, gw, contas):
    t = _turma("I4", capacity=5)
    antes = _foto()
    r = _comprar(client, contas.sup.token, class_id=t)
    assert r.status_code == 403, r.text
    assert _foto() == antes


def test_i5_pendente_com_turma_nao_libera_material(client, gw, contas):
    t = _turma("I5", capacity=5)
    _comprar_ok(client, contas.ana.token, t)
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert URL_MATERIAL not in r.text, "matricula pendente com turma nao pode expor material"
