"""F3/F4 - aluno -> cursos e turma; curso -> alunos; turma visivel ao aluno (D73, politica D68).

Escritos ANTES da implementacao. Devem falhar agora: nao existem as rotas
GET /api/dashboard/alunos/{user_id} e GET /api/dashboard/cursos/{course_id}/alunos, e os itens de
/api/student/enrollments ainda nao trazem `class_name` nem `class_starts_on`.

Contrato (D73):
  - GET /api/dashboard/alunos/{user_id} (todos os perfis internos):
      student {id, name, email, created_at}
      enrollments [{enrollment_id, course_id, course_name, class_id, class_name, class_starts_on, status, enrolled_at}]
      payments [{payment_id, enrollment_id, course_id, status, created_at, amount}]  (amount AUSENTE para Suporte)
      chat {messages, last_chat_at}
    Id que nao e aluno (inexistente ou funcionario) -> 404 "Aluno não encontrado".
  - GET /api/dashboard/cursos/{course_id}/alunos (todos os perfis internos), filtros opcionais `status` e `class_id`
    (`none` = sem turma):
      course {id, name, archived}
      students [{user_id, name, email, enrollment_id, status, enrolled_at, class_id, class_name, payment_status,
                 amount}]  (amount AUSENTE para Suporte)
    Curso fora do catalogo -> 404 "Course not found". Ordenacao: matricula mais recente primeiro.
  - /api/student/enrollments: cada item ganha `class_name` e `class_starts_on` (null sem turma); sem IDOR.
  - Politica D68: Suporte ve status, NUNCA valores.

Grupos
  A  Detalhe do aluno: campos, turma, pagamentos com valor (Gestao/Financeiro), chat igual ao do dashboard
  B  Detalhe do aluno: Suporte sem `amount` em lugar nenhum e sem o valor no corpo
  C  Detalhe do aluno: 404 (inexistente, funcionario, id enorme), aluno sem matricula (compatibilidade)
  D  Alunos do curso: campos, valores por perfil, Suporte sem `amount`
  E  Alunos do curso: filtros status / class_id / none / combinados; ordenacao
  F  Alunos do curso: 404 de curso fora do catalogo; curso arquivado (F1) continua consultavel; compatibilidade
     (matricula sem turma e sem pagamento)
  G  Area do aluno: class_name / class_starts_on, null sem turma, sem IDOR, materiais so com `active`
  H  RBAC: 401 sem token e com token forjado; 403 para aluno; todos os perfis internos 200 (JWT e legado)

Convencoes: mesmas fixtures de test_l1_turmas.py (banco temporario via conftest, cursos em diretorio
temporario, JWT montado com create_access_token). O estado (status, turma, datas, pagamento) e montado direto
na camada de banco; os endpoints testados sao sempre chamados pela rota HTTP real. Nada toca backend/db.sqlite
nem backend/courses (a fixture `cursos` confere).

Escolhas conservadoras (ver relatorio do agente-testes):
  - `chat.messages` e `chat.last_chat_at` do detalhe sao comparados com `chat_messages` / `last_chat_at` do
    proprio GET /api/dashboard/alunos (mesma semantica ja usada no projeto), e nao com um numero inventado.
  - Ordem de `enrollments` e `payments` no detalhe nao e fixada (D73 nao fixa); so a lista de alunos do curso
    tem ordem testada. As datas de matricula crescem junto com o id, para nao exigir desempate.
  - Matricula sem pagamento na lista do curso: `payment_status` e `amount` nulos (chave presente para Gestao).
  - Suporte: alem da chave `amount`, o corpo nao pode conter o valor numerico do pagamento em nenhum campo.
  - Os campos exigidos sao um minimo (superconjunto aceito), exceto a ausencia de `amount` para Suporte.

Ajuste mecanico D73 (F3) -> D81 (S6, autoridade 4.3): o cenario gravava pagamentos `pending` com datas fixas de
setembro/2026, que a S6 (pendente com mais de 7 dias vira `cancelled` nas leituras) expirava. As datas passam a ser
relativas ao instante da execucao (UTC): matriculas/pagamentos entre 5 e 1 dia atras (menos de 7 dias, mesma ordem
relativa de antes) e a turma Alfa com inicio em hoje + 30 dias. Os esperados de data sao derivados das mesmas
constantes. Intencao dos testes preservada.
"""

import json
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

CURSO_A = "curso_f3_a"
CURSO_B = "curso_f3_b"
NOME_A = "Curso F3 A"
NOME_B = "Curso F3 B"
URL_A = "https://materiais.test/f3/apostila-a.pdf"

# Valores improvaveis, para procurar no corpo da resposta do Suporte.
VALOR_A = 987.65
VALOR_B = 432.17
VALOR_C = 618.29

# Datas relativas ao instante da execucao (UTC), D81: pendentes com menos de 7 dias; turma Alfa no futuro.
_AGORA = datetime.now(timezone.utc).replace(microsecond=0)


def _ha(dias):
    """Dia de hoje menos `dias`, ao meio-dia UTC (como o cenario original): 1 a 5 dias -> idade < 6 dias."""
    return (_AGORA - timedelta(days=dias)).strftime("%Y-%m-%d 12:00:00")


DATA_JOANA_A = _ha(5)
DATA_PEDRO_A = _ha(4)
DATA_RITA_CANCELADA = _ha(3)
DATA_RITA_PENDENTE = _ha(2)
DATA_JOANA_B = _ha(1)
DATA_CURSO_REMOVIDO = _ha(1)
INICIO_ALFA = (_AGORA + timedelta(days=30)).strftime("%Y-%m-%d")

ERR_ALUNO = "Aluno não encontrado"
ERR_CURSO = "Course not found"

CAMPOS_STUDENT = {"id", "name", "email", "created_at"}
CAMPOS_MATRICULA = {"enrollment_id", "course_id", "course_name", "class_id", "class_name", "class_starts_on",
                    "status", "enrolled_at"}
CAMPOS_PAGAMENTO = {"payment_id", "enrollment_id", "course_id", "status", "created_at", "amount"}
CAMPOS_CHAT = {"messages", "last_chat_at"}
CAMPOS_CURSO = {"id", "name", "archived"}
CAMPOS_ALUNO_CURSO = {"user_id", "name", "email", "enrollment_id", "status", "enrolled_at", "class_id", "class_name",
                      "payment_status", "amount"}


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


def _escrever_curso(diretorio, course_id, nome, preco=100.0, materiais=None, **extra):
    dados = {
        "id": course_id, "name": nome, "description": "Curso de teste F3", "price": preco,
        "level": "Iniciante", "duration_hours": 10, **extra,
    }
    if materiais is not None:
        dados["materials"] = materiais
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def catalogo(cursos):
    """Curso A (com materiais) e curso B (sem `materials` e sem `archived`, dado antigo)."""
    _escrever_curso(cursos, CURSO_A, NOME_A, VALOR_A, [{"title": "Apostila A", "url": URL_A, "type": "pdf"}])
    _escrever_curso(cursos, CURSO_B, NOME_B, VALOR_B)
    return cursos


@pytest.fixture
def client(banco, catalogo):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(email, nome, perfil):
    user_id = Database.add_user(email, nome, None, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        gestao=_conta("ana.gestora@f3.test", "Ana Gestora", "admin"),
        fin=_conta("fernanda.fin@f3.test", "Fernanda Financeira", "financial"),
        sup=_conta("sergio.sup@f3.test", "Sergio Suporte", "support"),
        joana=_conta("joana.aluna@f3.test", "Joana Aluna", "student"),
        pedro=_conta("pedro.aluno@f3.test", "Pedro Aluno", "student"),
        rita=_conta("rita.aluna@f3.test", "Rita Aluna", "student"),
        vazio=_conta("vazio.aluno@f3.test", "Aluno Sem Matricula", "student"),
    )


def _forjado(role="admin"):
    return jose_jwt.encode(
        {"user_id": 1, "email": "x@f3.test", "role": role},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


# --- Helpers de banco -------------------------------------------------------------------

def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _turma(course_id, nome, starts_on=None, capacity=None):
    class_id = Database.create_class(course_id, nome, starts_on, capacity)
    assert class_id is not None, f"seed: turma {nome} ja existe"
    return class_id


def _matricula(user_id, course_id, status, enrolled_at, class_id=None, valor=None, status_pagamento=None):
    """Matricula real (create_enrollment); status, data, turma e pagamento montados na camada de banco."""
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:f3:{uuid.uuid4().hex}")
    _executar("UPDATE enrollments SET status = ?, enrolled_at = ?, class_id = ? WHERE id = ?",
              (status, enrolled_at, class_id, enrollment_id))
    payment_id = None
    if valor is not None:
        payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
        if status_pagamento and status_pagamento != "pending":
            Database.update_payment_status(payment_id, status_pagamento, f"mp-f3-{uuid.uuid4().hex[:8]}")
        _executar("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?",
                  (enrolled_at, enrolled_at, payment_id))
    return SimpleNamespace(id=enrollment_id, payment_id=payment_id)


@pytest.fixture
def cenario(contas):
    """
    Curso A: turmas Alfa (inicio INICIO_ALFA = hoje + 30 dias) e Beta (sem inicio).
      joana  A active    Alfa  pagamento approved VALOR_A   ha 5 dias
      pedro  A pending   Beta  pagamento pending  VALOR_C   ha 4 dias
      rita   A cancelled -     pagamento rejected VALOR_C   ha 3 dias
      rita   A pending   -     sem pagamento              ha 2 dias  (compatibilidade)
    Curso B: joana B pending sem turma, pagamento pending VALOR_B, ha 1 dia.
    (Datas relativas, D81: nenhum pendente passa dos 7 dias da S6.)
    Chat: joana com 2 trocas (2 mensagens do aluno + 2 do bot).
    """
    alfa = _turma(CURSO_A, "Turma Alfa", INICIO_ALFA, 30)
    beta = _turma(CURSO_A, "Turma Beta")
    m = SimpleNamespace(
        joana_a=_matricula(contas.joana.id, CURSO_A, "active", DATA_JOANA_A, alfa, VALOR_A, "approved"),
        pedro_a=_matricula(contas.pedro.id, CURSO_A, "pending", DATA_PEDRO_A, beta, VALOR_C, "pending"),
        rita_a_cancelada=_matricula(contas.rita.id, CURSO_A, "cancelled", DATA_RITA_CANCELADA, None, VALOR_C,
                                    "rejected"),
        rita_a_pendente=_matricula(contas.rita.id, CURSO_A, "pending", DATA_RITA_PENDENTE),
        joana_b=_matricula(contas.joana.id, CURSO_B, "pending", DATA_JOANA_B, None, VALOR_B, "pending"),
    )
    Database.add_chat_exchange(contas.joana.id, "Quando começa a turma?", "Em novembro.")
    Database.add_chat_exchange(contas.joana.id, "E o material?", "Está na área do aluno.")
    return SimpleNamespace(alfa=alfa, beta=beta, m=m)


# --- Helpers de HTTP --------------------------------------------------------------------

def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _detalhe(client, token, user_id):
    return client.get(f"/api/dashboard/alunos/{user_id}", headers=_auth(token))


def _alunos_curso(client, token, course_id, **filtros):
    return client.get(f"/api/dashboard/cursos/{course_id}/alunos", params=filtros or None, headers=_auth(token))


def _ok(r, rotulo):
    assert r.status_code == 200, f"{rotulo}: HTTP {r.status_code} {r.text[:300]}"
    return r.json()


def _chaves(obj):
    """Todas as chaves de dicionario, em qualquer nivel da resposta."""
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            yield chave
            yield from _chaves(valor)
    elif isinstance(obj, list):
        for item in obj:
            yield from _chaves(item)


def _sem_valores(r, valores):
    """Suporte (D68): nenhuma chave `amount` e nenhum dos valores em texto no corpo."""
    corpo = r.json()
    assert "amount" not in set(_chaves(corpo)), f"Suporte recebeu a chave amount: {r.text[:400]}"
    for valor in valores:
        for forma in (f"{valor}", f"{valor:.2f}", f"{valor:.2f}".replace(".", ",")):
            assert forma not in r.text, f"Suporte recebeu o valor {forma} no corpo: {r.text[:400]}"


def _por_matricula(itens, chave="enrollment_id"):
    return {item[chave]: item for item in itens}


# =====================================================================================
# A  Detalhe do aluno (Gestao / Financeiro)
# =====================================================================================

@pytest.mark.parametrize("perfil", ["gestao", "fin"])
def test_a1_detalhe_do_aluno_traz_student_matriculas_pagamentos_e_chat(client, contas, cenario, perfil):
    corpo = _ok(_detalhe(client, getattr(contas, perfil).token, contas.joana.id), "detalhe joana")
    for chave in ("student", "enrollments", "payments", "chat"):
        assert chave in corpo, f"falta a chave {chave!r}: {list(corpo)}"
    aluno = corpo["student"]
    assert CAMPOS_STUDENT <= set(aluno), f"student sem campos {CAMPOS_STUDENT - set(aluno)}"
    assert aluno["id"] == contas.joana.id
    assert aluno["name"] == "Joana Aluna"
    assert aluno["email"] == "joana.aluna@f3.test"
    assert aluno["created_at"]
    assert CAMPOS_CHAT <= set(corpo["chat"]), f"chat sem campos {CAMPOS_CHAT - set(corpo['chat'])}"


def test_a2_detalhe_matriculas_com_curso_turma_status_e_data(client, contas, cenario):
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.joana.id), "detalhe joana")
    itens = corpo["enrollments"]
    for item in itens:
        assert CAMPOS_MATRICULA <= set(item), f"matricula sem campos {CAMPOS_MATRICULA - set(item)}: {item}"
    por_id = _por_matricula(itens)
    assert set(por_id) == {cenario.m.joana_a.id, cenario.m.joana_b.id}, \
        f"o detalhe deve trazer exatamente as matriculas da Joana: {sorted(por_id)}"
    a = por_id[cenario.m.joana_a.id]
    assert (a["course_id"], a["course_name"], a["status"]) == (CURSO_A, NOME_A, "active")
    assert (a["class_id"], a["class_name"], a["class_starts_on"]) == (cenario.alfa, "Turma Alfa", INICIO_ALFA)
    assert str(a["enrolled_at"]).startswith(DATA_JOANA_A[:10])
    b = por_id[cenario.m.joana_b.id]
    assert (b["course_id"], b["course_name"], b["status"]) == (CURSO_B, NOME_B, "pending")
    assert (b["class_id"], b["class_name"], b["class_starts_on"]) == (None, None, None), \
        f"matricula sem turma deve ter class_* nulos: {b}"


def test_a3_turma_sem_inicio_tem_class_starts_on_nulo(client, contas, cenario):
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.pedro.id), "detalhe pedro")
    (item,) = corpo["enrollments"]
    assert (item["class_id"], item["class_name"], item["class_starts_on"]) == (cenario.beta, "Turma Beta", None)


@pytest.mark.parametrize("perfil", ["gestao", "fin"])
def test_a4_pagamentos_com_valor_para_gestao_e_financeiro(client, contas, cenario, perfil):
    corpo = _ok(_detalhe(client, getattr(contas, perfil).token, contas.joana.id), "detalhe joana")
    itens = corpo["payments"]
    for item in itens:
        assert CAMPOS_PAGAMENTO <= set(item), f"pagamento sem campos {CAMPOS_PAGAMENTO - set(item)}: {item}"
    por_id = _por_matricula(itens, "payment_id")
    assert set(por_id) == {cenario.m.joana_a.payment_id, cenario.m.joana_b.payment_id}
    pa = por_id[cenario.m.joana_a.payment_id]
    assert (pa["enrollment_id"], pa["course_id"], pa["status"]) == (cenario.m.joana_a.id, CURSO_A, "approved")
    assert pa["amount"] == pytest.approx(VALOR_A)
    assert str(pa["created_at"]).startswith(DATA_JOANA_A[:10])
    pb = por_id[cenario.m.joana_b.payment_id]
    assert (pb["enrollment_id"], pb["course_id"], pb["status"]) == (cenario.m.joana_b.id, CURSO_B, "pending")
    assert pb["amount"] == pytest.approx(VALOR_B)


def test_a5_chat_do_detalhe_igual_ao_do_dashboard_de_alunos(client, contas, cenario):
    lista = _ok(client.get("/api/dashboard/alunos", headers=_auth(contas.gestao.token)), "dashboard alunos")
    linha = next(s for s in lista["students"] if s["id"] == contas.joana.id)
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.joana.id), "detalhe joana")
    assert linha["chat_messages"] == 2, "pre-condicao: o dashboard conta as 2 mensagens do aluno"
    assert corpo["chat"]["messages"] == linha["chat_messages"]
    assert corpo["chat"]["last_chat_at"] == linha["last_chat_at"]


def test_a6_detalhe_nao_mistura_matriculas_nem_pagamentos_de_outro_aluno(client, contas, cenario):
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.rita.id), "detalhe rita")
    assert {i["enrollment_id"] for i in corpo["enrollments"]} == {cenario.m.rita_a_cancelada.id,
                                                                   cenario.m.rita_a_pendente.id}
    assert {p["payment_id"] for p in corpo["payments"]} == {cenario.m.rita_a_cancelada.payment_id}
    assert "joana" not in json.dumps(corpo).lower()
    assert corpo["chat"]["messages"] == 0
    assert corpo["chat"]["last_chat_at"] is None


def test_a7_detalhe_nao_expoe_hash_de_senha_nem_material(client, contas, cenario):
    r = _detalhe(client, contas.gestao.token, contas.joana.id)
    _ok(r, "detalhe joana")
    assert "password" not in r.text.lower()
    assert URL_A not in r.text


# =====================================================================================
# B  Detalhe do aluno: Suporte nunca ve valores (D68)
# =====================================================================================

def test_b1_suporte_ve_detalhe_sem_amount_em_lugar_nenhum(client, contas, cenario):
    r = _detalhe(client, contas.sup.token, contas.joana.id)
    corpo = _ok(r, "detalhe joana (suporte)")
    _sem_valores(r, (VALOR_A, VALOR_B))
    assert len(corpo["payments"]) == 2, "Suporte continua vendo os pagamentos (status)"
    for item in corpo["payments"]:
        assert CAMPOS_PAGAMENTO - {"amount"} <= set(item), item
    assert {p["status"] for p in corpo["payments"]} == {"approved", "pending"}
    assert len(corpo["enrollments"]) == 2


def test_b2_suporte_com_token_legado_tambem_sem_valores(client, contas, cenario):
    r = _detalhe(client, create_admin_token(Role.SUPPORT), contas.joana.id)
    _ok(r, "detalhe joana (suporte legado)")
    _sem_valores(r, (VALOR_A, VALOR_B))


# =====================================================================================
# C  Detalhe do aluno: 404 e compatibilidade
# =====================================================================================

@pytest.mark.parametrize("quem", ["inexistente", "gestao", "fin", "sup", "enorme", "negativo"])
def test_c1_id_que_nao_e_aluno_devolve_404_aluno_nao_encontrado(client, contas, cenario, quem):
    alvo = {
        "inexistente": 999999,
        "enorme": 2 ** 70,
        "negativo": -1,
    }.get(quem) or getattr(contas, quem).id
    r = _detalhe(client, contas.gestao.token, alvo)
    assert r.status_code == 404, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    assert r.json() == {"detail": ERR_ALUNO}


def test_c2_funcionario_e_inexistente_tem_a_mesma_resposta(client, contas, cenario):
    r1 = _detalhe(client, contas.sup.token, contas.fin.id)
    r2 = _detalhe(client, contas.sup.token, 999999)
    assert (r1.status_code, r1.json()) == (r2.status_code, r2.json()) == (404, {"detail": ERR_ALUNO})


def test_c3_aluno_sem_matricula_devolve_listas_vazias(client, contas, cenario):
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.vazio.id), "detalhe aluno sem matricula")
    assert corpo["student"]["id"] == contas.vazio.id
    assert corpo["enrollments"] == []
    assert corpo["payments"] == []
    assert corpo["chat"]["messages"] == 0
    assert corpo["chat"]["last_chat_at"] is None


def test_c4_matricula_de_curso_arquivado_continua_no_detalhe(client, contas, cenario, catalogo):
    _escrever_curso(catalogo, CURSO_B, NOME_B, VALOR_B, archived=True)
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.joana.id), "detalhe joana (curso B arquivado)")
    b = _por_matricula(corpo["enrollments"])[cenario.m.joana_b.id]
    assert (b["course_id"], b["course_name"]) == (CURSO_B, NOME_B)


# =====================================================================================
# D  Alunos do curso: campos e valores por perfil
# =====================================================================================

@pytest.mark.parametrize("perfil", ["gestao", "fin"])
def test_d1_alunos_do_curso_com_todos_os_campos(client, contas, cenario, perfil):
    corpo = _ok(_alunos_curso(client, getattr(contas, perfil).token, CURSO_A), "alunos do curso A")
    curso = corpo["course"]
    assert CAMPOS_CURSO <= set(curso), f"course sem campos {CAMPOS_CURSO - set(curso)}"
    assert (curso["id"], curso["name"]) == (CURSO_A, NOME_A)
    assert curso["archived"] is False
    itens = corpo["students"]
    for item in itens:
        assert CAMPOS_ALUNO_CURSO <= set(item), f"aluno sem campos {CAMPOS_ALUNO_CURSO - set(item)}: {item}"
    por_id = _por_matricula(itens)
    assert set(por_id) == {cenario.m.joana_a.id, cenario.m.pedro_a.id, cenario.m.rita_a_cancelada.id,
                           cenario.m.rita_a_pendente.id}, "so as matriculas do curso A, em todos os status"
    j = por_id[cenario.m.joana_a.id]
    assert (j["user_id"], j["name"], j["email"], j["status"]) == (
        contas.joana.id, "Joana Aluna", "joana.aluna@f3.test", "active")
    assert (j["class_id"], j["class_name"]) == (cenario.alfa, "Turma Alfa")
    assert j["payment_status"] == "approved"
    assert j["amount"] == pytest.approx(VALOR_A)
    assert str(j["enrolled_at"]).startswith(DATA_JOANA_A[:10])
    p = por_id[cenario.m.pedro_a.id]
    assert (p["user_id"], p["status"], p["class_id"], p["class_name"], p["payment_status"]) == (
        contas.pedro.id, "pending", cenario.beta, "Turma Beta", "pending")
    assert p["amount"] == pytest.approx(VALOR_C)
    rc = por_id[cenario.m.rita_a_cancelada.id]
    assert (rc["status"], rc["class_id"], rc["class_name"], rc["payment_status"]) == (
        "cancelled", None, None, "rejected")


def test_d2_suporte_ve_alunos_do_curso_sem_amount(client, contas, cenario):
    r = _alunos_curso(client, contas.sup.token, CURSO_A)
    corpo = _ok(r, "alunos do curso A (suporte)")
    _sem_valores(r, (VALOR_A, VALOR_C))
    assert len(corpo["students"]) == 4
    for item in corpo["students"]:
        assert CAMPOS_ALUNO_CURSO - {"amount"} <= set(item), item
    j = _por_matricula(corpo["students"])[cenario.m.joana_a.id]
    assert j["payment_status"] == "approved", "Suporte ve o status do pagamento"


def test_d3_suporte_legado_sem_valores_e_gestao_legado_com_valores(client, contas, cenario):
    r = _alunos_curso(client, create_admin_token(Role.SUPPORT), CURSO_A)
    _ok(r, "alunos do curso A (suporte legado)")
    _sem_valores(r, (VALOR_A, VALOR_C))
    corpo = _ok(_alunos_curso(client, create_admin_token(Role.ADMIN), CURSO_A), "alunos do curso A (gestao legado)")
    j = _por_matricula(corpo["students"])[cenario.m.joana_a.id]
    assert j["amount"] == pytest.approx(VALOR_A)


def test_d4_alunos_do_curso_nao_expoem_material(client, contas, cenario):
    r = _alunos_curso(client, contas.gestao.token, CURSO_A)
    _ok(r, "alunos do curso A")
    assert URL_A not in r.text
    assert "password" not in r.text.lower()


# =====================================================================================
# E  Alunos do curso: filtros e ordenacao
# =====================================================================================

def _ids(corpo):
    return [item["enrollment_id"] for item in corpo["students"]]


def test_e1_ordenacao_matricula_mais_recente_primeiro(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A), "alunos do curso A")
    assert _ids(corpo) == [cenario.m.rita_a_pendente.id, cenario.m.rita_a_cancelada.id, cenario.m.pedro_a.id,
                           cenario.m.joana_a.id]


@pytest.mark.parametrize("status,esperado", [
    ("active", ["joana_a"]),
    ("pending", ["rita_a_pendente", "pedro_a"]),
    ("cancelled", ["rita_a_cancelada"]),
    ("refunded", []),
])
def test_e2_filtro_por_status(client, contas, cenario, status, esperado):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, status=status), f"status={status}")
    assert _ids(corpo) == [getattr(cenario.m, nome).id for nome in esperado]
    assert all(item["status"] == status for item in corpo["students"])


def test_e3_filtro_por_turma(client, contas, cenario):
    alfa = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, class_id=cenario.alfa), "class_id=alfa")
    assert _ids(alfa) == [cenario.m.joana_a.id]
    beta = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, class_id=cenario.beta), "class_id=beta")
    assert _ids(beta) == [cenario.m.pedro_a.id]


def test_e4_filtro_sem_turma(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, class_id="none"), "class_id=none")
    assert _ids(corpo) == [cenario.m.rita_a_pendente.id, cenario.m.rita_a_cancelada.id]
    assert all(item["class_id"] is None for item in corpo["students"])


def test_e5_filtros_combinados(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, status="pending", class_id="none"),
                "status=pending&class_id=none")
    assert _ids(corpo) == [cenario.m.rita_a_pendente.id]
    vazio = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A, status="active", class_id=cenario.beta),
                "status=active&class_id=beta")
    assert vazio["students"] == []


def test_e6_filtro_de_turma_nao_traz_matricula_de_outro_curso(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_B, class_id="none"), "curso B class_id=none")
    assert _ids(corpo) == [cenario.m.joana_b.id]


# =====================================================================================
# F  Alunos do curso: 404, arquivado e compatibilidade
# =====================================================================================

def test_f1_curso_fora_do_catalogo_devolve_404(client, contas, cenario):
    course_id = "curso_que_nao_existe"
    r = _alunos_curso(client, contas.gestao.token, course_id)
    assert r.status_code == 404, f"HTTP {r.status_code} {r.text[:200]}"
    assert r.json() == {"detail": ERR_CURSO}


def test_f2_curso_fora_do_catalogo_com_matricula_antiga_devolve_404(client, contas, cenario):
    """Matricula de um curso cujo JSON nao existe mais (dado antigo): o curso nao esta no catalogo."""
    _matricula(contas.vazio.id, "curso_removido_f3", "active", DATA_CURSO_REMOVIDO)
    r = _alunos_curso(client, contas.gestao.token, "curso_removido_f3")
    assert r.status_code == 404
    assert r.json() == {"detail": ERR_CURSO}


def test_f3_curso_arquivado_continua_consultavel(client, contas, cenario, catalogo):
    _escrever_curso(catalogo, CURSO_A, NOME_A, VALOR_A, [{"title": "Apostila A", "url": URL_A, "type": "pdf"}],
                    archived=True)
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A), "alunos do curso A arquivado")
    assert corpo["course"]["archived"] is True
    assert len(corpo["students"]) == 4


def test_f4_curso_sem_chave_archived_vale_false(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.sup.token, CURSO_B), "alunos do curso B")
    assert corpo["course"]["archived"] is False
    assert corpo["course"]["name"] == NOME_B


def test_f5_curso_sem_matricula_devolve_lista_vazia(client, contas, cenario, catalogo):
    _escrever_curso(catalogo, "curso_f3_vazio", "Curso F3 Vazio", 50.0)
    corpo = _ok(_alunos_curso(client, contas.gestao.token, "curso_f3_vazio"), "curso sem matricula")
    assert corpo["students"] == []
    assert corpo["course"]["id"] == "curso_f3_vazio"


def test_f6_matricula_sem_turma_e_sem_pagamento(client, contas, cenario):
    corpo = _ok(_alunos_curso(client, contas.gestao.token, CURSO_A), "alunos do curso A")
    r = _por_matricula(corpo["students"])[cenario.m.rita_a_pendente.id]
    assert (r["class_id"], r["class_name"]) == (None, None)
    assert r["payment_status"] is None
    assert r["amount"] is None


# =====================================================================================
# G  Area do aluno: turma no /api/student/enrollments
# =====================================================================================

def _minhas(client, token, **params):
    return client.get("/api/student/enrollments", params=params or None, headers=_auth(token))


def test_g1_aluno_ve_nome_e_inicio_da_turma(client, contas, cenario):
    corpo = _ok(_minhas(client, contas.joana.token), "enrollments joana")
    por_id = {item["id"]: item for item in corpo["enrollments"]}
    a = por_id[cenario.m.joana_a.id]
    assert a["class_name"] == "Turma Alfa"
    assert a["class_starts_on"] == INICIO_ALFA


def test_g2_sem_turma_campos_nulos(client, contas, cenario):
    corpo = _ok(_minhas(client, contas.joana.token), "enrollments joana")
    b = {item["id"]: item for item in corpo["enrollments"]}[cenario.m.joana_b.id]
    assert "class_name" in b and "class_starts_on" in b, f"chaves ausentes: {b}"
    assert (b["class_name"], b["class_starts_on"]) == (None, None)


def test_g3_turma_sem_inicio(client, contas, cenario):
    corpo = _ok(_minhas(client, contas.pedro.token), "enrollments pedro")
    (item,) = corpo["enrollments"]
    assert (item["class_name"], item["class_starts_on"]) == ("Turma Beta", None)


def test_g4_aluno_nao_ve_turma_nem_matricula_de_outro_aluno(client, contas, cenario):
    corpo = _ok(_minhas(client, contas.pedro.token, user_id=contas.joana.id), "enrollments pedro ?user_id=joana")
    assert [item["id"] for item in corpo["enrollments"]] == [cenario.m.pedro_a.id]
    assert "Turma Alfa" not in json.dumps(corpo, ensure_ascii=False)


def test_g5_materiais_so_com_matricula_ativa_mesmo_com_turma(client, contas, cenario):
    r_pedro = _minhas(client, contas.pedro.token)
    corpo = _ok(r_pedro, "enrollments pedro")
    (item,) = corpo["enrollments"]
    assert item["status"] == "pending" and item["class_name"] == "Turma Beta"
    assert "materials" not in item
    assert URL_A not in r_pedro.text, "matricula pendente com turma nao libera material"
    for status in ("cancelled", "refunded"):
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, cenario.m.pedro_a.id))
        r = _minhas(client, contas.pedro.token)
        assert URL_A not in r.text, f"{status} com turma nao libera material"
    r_joana = _ok(_minhas(client, contas.joana.token), "enrollments joana")
    a = {i["id"]: i for i in r_joana["enrollments"]}[cenario.m.joana_a.id]
    assert [m["url"] for m in a["materials"]] == [URL_A]


def test_g6_detalhe_da_matricula_do_aluno_continua_com_404_para_alheia(client, contas, cenario):
    r = client.get(f"/api/student/enrollments/{cenario.m.joana_a.id}", headers=_auth(contas.pedro.token))
    inexistente = client.get("/api/student/enrollments/999999", headers=_auth(contas.pedro.token))
    assert r.status_code == inexistente.status_code == 404
    assert r.json() == inexistente.json()
    assert "Turma Alfa" not in r.text


# =====================================================================================
# H  RBAC
# =====================================================================================

def _rotas(contas, cenario):
    return [
        f"/api/dashboard/alunos/{contas.joana.id}",
        f"/api/dashboard/cursos/{CURSO_A}/alunos",
    ]


@pytest.mark.parametrize("rota", [0, 1])
@pytest.mark.parametrize("token", ["sem_token", "forjado", "forjado_aluno"])
def test_h1_sem_token_ou_forjado_devolve_401(client, contas, cenario, rota, token):
    cabecalho = {"sem_token": {}, "forjado": _auth(_forjado()), "forjado_aluno": _auth(_forjado("student"))}[token]
    r = client.get(_rotas(contas, cenario)[rota], headers=cabecalho)
    assert r.status_code == 401, f"HTTP {r.status_code} {r.text[:200]}"
    assert "Joana" not in r.text


@pytest.mark.parametrize("rota", [0, 1])
def test_h2_aluno_recebe_403(client, contas, cenario, rota):
    r = client.get(_rotas(contas, cenario)[rota], headers=_auth(contas.joana.token))
    assert r.status_code == 403, f"HTTP {r.status_code} {r.text[:200]}"
    assert "Joana" not in r.text


@pytest.mark.parametrize("rota", [0, 1])
@pytest.mark.parametrize("perfil", ["gestao", "fin", "sup", "gestao_legado", "fin_legado", "sup_legado"])
def test_h3_todos_os_perfis_internos_tem_acesso(client, contas, cenario, rota, perfil):
    token = {
        "gestao_legado": create_admin_token(Role.ADMIN),
        "fin_legado": create_admin_token(Role.FINANCIAL),
        "sup_legado": create_admin_token(Role.SUPPORT),
    }.get(perfil) or getattr(contas, perfil).token
    r = client.get(_rotas(contas, cenario)[rota], headers=_auth(token))
    assert r.status_code == 200, f"{perfil}: HTTP {r.status_code} {r.text[:200]}"


def test_h4_funcionario_nao_usa_area_do_aluno(client, contas, cenario):
    r = _minhas(client, contas.gestao.token)
    assert r.status_code == 403
