"""E3 - Painel de inscrições e materiais didáticos (item 1.1 e RF22). Testes de comportamento.

Escritos ANTES da implementação (D28). Devem falhar agora: as rotas /api/student/* ainda não
existem (404) e o curso ainda não aceita o campo materials.

Requisitos cobertos:
  T1  GET /api/student/enrollments: só as matrículas do próprio aluno; campos id, course_id,
      course_name, status, enrolled_at.
  T2  matrícula 'active' traz materials (title, url, type) do curso.
  T3  matrículas 'pending', 'cancelled' e 'refunded': nenhuma URL de material em nenhum lugar da resposta.
  T4  curso sem o campo materials: item ativo traz materials == [] e a rota não quebra.
  T5  IDOR: matrícula de outro aluno em GET /api/student/enrollments/{id} -> 404 (não 403), sem vazar dados.
  T6  IDOR por lista: a lista do aluno não contém matrícula de outro aluno no mesmo curso.
  T7  user_id enviado pelo cliente (query ou body) é ignorado; o alvo é sempre o dono do token.
  T8  perfis de funcionário (admin, financial, support) com JWT (e com o token administrativo) -> 403.
  T9  sem token -> 401.
  T10 token de aluno forjado (segredo errado) -> 401.
  T11 POST /api/admin/create-course aceita o campo materials; curso sem o campo continua aceito.
  T12 parametrizado nos 4 status: só 'active' libera URLs de material.

Convenções: mesmo padrão de test_e1/test_e2. Banco temporário (tmp_path via conftest), rotas HTTP
reais, token real por POST /api/token, matrícula criada por Database (create_enrollment com user_id,
record_payment) e levada ao status pelo webhook real com a consulta ao Mercado Pago mockada.

Limitações:
  - T11 grava o arquivo do curso em backend/courses, porque create-course usa esse diretório fixo
    (admin/routes.py). Os arquivos com id único são removidos ao final do teste.
  - Interpretação de formato (D28 diz "lista"): a lista pode vir como array no corpo ou dentro de
    {"enrollments": [...]}. O item pode vir direto ou dentro de {"enrollment": {...}}. Os dois são aceitos.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from core.security import get_password_hash
from db import Database

import admin.routes as admin_routes


SENHA = "senha-aluno-e3-2026"
CURSO_MAT = "curso_e3_materiais"
CURSO_SEM = "curso_e3_sem_materiais"
NOME_MAT = "Curso com Materiais"
NOME_SEM = "Curso sem Materiais"
MATERIAIS = [
    {"title": "Apostila 1", "url": "https://materiais.test/e3/apostila-1.pdf", "type": "pdf"},
    {"title": "Video 1", "url": "https://materiais.test/e3/video-1.mp4", "type": "video"},
]
URL_1 = MATERIAIS[0]["url"]
URL_2 = MATERIAIS[1]["url"]
PAGAMENTO_DE_STATUS = {"active": "approved", "refunded": "refunded", "cancelled": "cancelled"}
PERFIS_FUNCIONARIO = ["admin", "financial", "support"]
COURSES_DIR_REPO = Path(__file__).resolve().parent.parent / "courses"
ROTA_LISTA = "/api/student/enrollments"


# --- Fixtures ---------------------------------------------------------------------------

@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Dois cursos em diretório temporário: um com materials, outro sem o campo."""
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    base = {"description": "Curso de teste E3", "price": 100.0}
    (diretorio / f"{CURSO_MAT}.json").write_text(json.dumps(
        {"id": CURSO_MAT, "name": NOME_MAT, "materials": MATERIAIS, **base}), encoding="utf-8")
    (diretorio / f"{CURSO_SEM}.json").write_text(json.dumps(
        {"id": CURSO_SEM, "name": NOME_SEM, **base}), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return {"mat": CURSO_MAT, "sem": CURSO_SEM}


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco -------------------------------------------------------------------

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


def _status_no_banco(enrollment_id):
    return _sql("SELECT status FROM enrollments WHERE id = ?", (enrollment_id,))[0]["status"]


def _conta_aluno(email, nome="Aluno E3"):
    """Conta de aluno com senha (para login real por POST /api/token)."""
    user_id = Database.get_or_create_user(email, nome)
    _executar("UPDATE users SET password_hash = ? WHERE id = ?", (get_password_hash(SENHA), user_id))
    return user_id


def _conta_funcionario(email, perfil):
    user_id = Database.add_user(email, f"Funcionario {perfil}", get_password_hash(SENHA), role=perfil)
    assert user_id is not None, f"seed: conta {email} já existe"
    return user_id


def _webhook(client, status_pagamento, ref, pagamento_id):
    resposta = MagicMock(status_code=200)
    resposta.json.return_value = {"id": pagamento_id, "status": status_pagamento, "external_reference": ref}
    with patch("payments.routes.requests.get", return_value=resposta):
        r = client.post("/api/payments/webhook", json={"data": {"id": pagamento_id}})
    assert r.status_code == 200, r.text


def _matricula(client, user_id, course_id, status):
    """Matrícula real: create_enrollment + record_payment; o status vem do webhook (pending é o inicial)."""
    ref = f"{course_id}:e3:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    Database.record_payment(enrollment_id, 100.0, "mercado_pago")
    if status != "pending":
        _webhook(client, PAGAMENTO_DE_STATUS[status], ref, f"pg-{uuid.uuid4().hex[:10]}")
    assert _status_no_banco(enrollment_id) == status, "seed: o webhook não levou a matrícula ao status pedido"
    return enrollment_id


# --- Helpers de HTTP --------------------------------------------------------------------

def _login(client, email, senha=SENHA):
    r = client.post("/api/token", data={"username": email, "password": senha})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _cabecalho(token):
    return {"Authorization": f"Bearer {token}"}


def _lista(resposta):
    corpo = resposta.json()
    if isinstance(corpo, dict) and "enrollments" in corpo:
        corpo = corpo["enrollments"]
    assert isinstance(corpo, list), f"lista de matrículas esperada, veio {corpo!r}"
    return corpo


def _item(resposta):
    corpo = resposta.json()
    if isinstance(corpo, dict) and "enrollment" in corpo:
        corpo = corpo["enrollment"]
    assert isinstance(corpo, dict), f"matrícula esperada, veio {corpo!r}"
    return corpo


def _minha_lista(client, token):
    r = client.get(ROTA_LISTA, headers=_cabecalho(token))
    assert r.status_code == 200, f"GET {ROTA_LISTA}: HTTP {r.status_code} {r.text[:200]}"
    return r, _lista(r)


def _do_id(itens, enrollment_id):
    encontrados = [i for i in itens if i.get("id") == enrollment_id]
    assert len(encontrados) == 1, f"matrícula {enrollment_id} deveria estar na lista; ids={[i.get('id') for i in itens]}"
    return encontrados[0]


def _payload_curso(course_id):
    return {
        "id": course_id, "name": f"Curso {course_id}", "description": "Curso E3 criado pelo teste",
        "price": 150.0, "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
    }


# --- T1 - T4 : lista e materiais ----------------------------------------------------------

def test_t1_lista_traz_so_as_matriculas_do_proprio_aluno(client, cursos):
    a = _conta_aluno("aluno.a.t1@e3.test")
    b = _conta_aluno("aluno.b.t1@e3.test")
    ma1 = _matricula(client, a, cursos["mat"], "active")
    ma2 = _matricula(client, a, cursos["sem"], "pending")
    _matricula(client, b, cursos["mat"], "active")

    _, itens = _minha_lista(client, _login(client, "aluno.a.t1@e3.test"))

    assert {i["id"] for i in itens} == {ma1, ma2}
    for item in itens:
        for campo in ("id", "course_id", "course_name", "status", "enrolled_at"):
            assert campo in item, f"campo '{campo}' ausente no item {item}"
    assert {i["course_id"]: i["course_name"] for i in itens} == {CURSO_MAT: NOME_MAT, CURSO_SEM: NOME_SEM}


def test_t2_matricula_ativa_traz_materiais_do_curso(client, cursos):
    a = _conta_aluno("aluno.t2@e3.test")
    m = _matricula(client, a, cursos["mat"], "active")

    _, itens = _minha_lista(client, _login(client, "aluno.t2@e3.test"))
    item = _do_id(itens, m)

    assert item["status"] == "active"
    materiais = item.get("materials")
    assert isinstance(materiais, list), f"materials deveria ser lista, veio {materiais!r}"
    assert {(x["title"], x["url"], x["type"]) for x in materiais} == {(x["title"], x["url"], x["type"]) for x in MATERIAIS}


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_t3_sem_status_active_nenhuma_url_aparece_na_resposta(client, cursos, status):
    email = f"aluno.t3.{status}@e3.test"
    a = _conta_aluno(email)
    m = _matricula(client, a, cursos["mat"], status)

    r, itens = _minha_lista(client, _login(client, email))
    item = _do_id(itens, m)

    assert item["status"] == status
    assert not item.get("materials"), f"matrícula {status} não pode trazer materiais: {item.get('materials')}"
    assert URL_1 not in r.text, f"URL de material vazou na resposta da matrícula {status}"
    assert URL_2 not in r.text, f"URL de material vazou na resposta da matrícula {status}"


def test_t4_curso_sem_campo_materials_retorna_lista_vazia_sem_quebrar(client, cursos):
    email = "aluno.t4@e3.test"
    a = _conta_aluno(email)
    m = _matricula(client, a, cursos["sem"], "active")

    _, itens = _minha_lista(client, _login(client, email))
    item = _do_id(itens, m)

    assert item["status"] == "active"
    assert "materials" in item, "item ativo deve trazer o campo materials"
    assert item["materials"] == []


# --- T5 - T7 : IDOR e user_id do cliente -------------------------------------------------

def test_t5_idor_matricula_de_outro_aluno_responde_404_sem_vazar_dados(client, cursos):
    a = _conta_aluno("aluno.a.t5@e3.test")
    b = _conta_aluno("aluno.b.t5@e3.test")
    minha = _matricula(client, a, cursos["sem"], "pending")
    alheia = _matricula(client, b, cursos["mat"], "active")
    cabecalho = _cabecalho(_login(client, "aluno.a.t5@e3.test"))

    propria = client.get(f"{ROTA_LISTA}/{minha}", headers=cabecalho)
    assert propria.status_code == 200, f"a própria matrícula deve abrir (HTTP {propria.status_code})"

    r_alheia = client.get(f"{ROTA_LISTA}/{alheia}", headers=cabecalho)
    r_inexistente = client.get(f"{ROTA_LISTA}/999999", headers=cabecalho)

    assert r_alheia.status_code == 404, f"IDOR: esperado 404 (não 403), veio {r_alheia.status_code}"
    assert r_alheia.status_code == r_inexistente.status_code, "matrícula alheia deve responder igual a inexistente"
    assert NOME_MAT not in r_alheia.text
    assert "course_name" not in r_alheia.text
    assert "course_id" not in r_alheia.text
    assert '"status"' not in r_alheia.text


def test_t6_lista_nao_contem_matricula_de_outro_aluno_no_mesmo_curso(client, cursos):
    a = _conta_aluno("aluno.a.t6@e3.test")
    b = _conta_aluno("aluno.b.t6@e3.test")
    ma = _matricula(client, a, cursos["mat"], "active")
    mb = _matricula(client, b, cursos["mat"], "active")

    _, itens = _minha_lista(client, _login(client, "aluno.a.t6@e3.test"))

    ids = {i["id"] for i in itens}
    assert ma in ids
    assert mb not in ids, "a lista do aluno A contém matrícula do aluno B no mesmo curso"


def test_t7_user_id_do_cliente_e_ignorado_na_query_e_no_corpo(client, cursos):
    a = _conta_aluno("aluno.a.t7@e3.test")
    b = _conta_aluno("aluno.b.t7@e3.test")
    ma = _matricula(client, a, cursos["mat"], "active")
    _matricula(client, b, cursos["sem"], "pending")
    cabecalho = _cabecalho(_login(client, "aluno.a.t7@e3.test"))

    _, itens = _minha_lista(client, _login(client, "aluno.a.t7@e3.test"))
    assert {i["id"] for i in itens} == {ma}

    r_query = client.get(f"{ROTA_LISTA}?user_id={b}", headers=cabecalho)
    assert r_query.status_code == 200, r_query.text
    assert {i["id"] for i in _lista(r_query)} == {ma}, "user_id na query foi aceito"

    r_corpo = client.request("GET", ROTA_LISTA, headers=cabecalho, json={"user_id": b})
    assert r_corpo.status_code == 200, r_corpo.text
    assert {i["id"] for i in _lista(r_corpo)} == {ma}, "user_id no corpo foi aceito"

    r_post = client.post(ROTA_LISTA, headers=cabecalho, json={"user_id": b})
    assert r_post.status_code < 500
    assert NOME_SEM not in r_post.text, "POST com user_id de outro aluno devolveu dados dele"


# --- T8 - T10 : perfil, ausência e forja de token ----------------------------------------

@pytest.mark.parametrize("perfil", PERFIS_FUNCIONARIO)
@pytest.mark.parametrize("rota", [ROTA_LISTA, f"{ROTA_LISTA}/1"])
def test_t8_funcionario_com_jwt_recebe_403_nas_rotas_de_aluno(client, perfil, rota):
    email = f"{perfil}.t8@gt.test"
    _conta_funcionario(email, perfil)
    cabecalho = _cabecalho(_login(client, email))

    r = client.get(rota, headers=cabecalho)

    assert r.status_code == 403, f"{perfil} em {rota}: esperado 403, veio {r.status_code}"


@pytest.mark.parametrize("senha_env, perfil", [
    ("admin123", "admin"),
    ("fin123", "financial"),
    ("sup123", "support"),
])
def test_t8b_funcionario_com_token_administrativo_recebe_403(client, senha_env, perfil):
    r_login = client.post("/api/admin/login", json={"password": senha_env})
    assert r_login.status_code == 200, r_login.text
    cabecalho = _cabecalho(r_login.json()["token"])

    r = client.get(ROTA_LISTA, headers=cabecalho)

    assert r.status_code == 403, f"{perfil} com token administrativo: esperado 403, veio {r.status_code}"


def test_t9_sem_token_recebe_401(client, cursos):
    a = _conta_aluno("aluno.t9@e3.test")
    _matricula(client, a, cursos["mat"], "active")
    assert client.get(ROTA_LISTA, headers=_cabecalho(_login(client, "aluno.t9@e3.test"))).status_code == 200

    r = client.get(ROTA_LISTA)

    assert r.status_code == 401


def test_t10_token_de_aluno_forjado_recebe_401(client, cursos):
    a = _conta_aluno("aluno.t10@e3.test")
    _matricula(client, a, cursos["mat"], "active")
    valido = _login(client, "aluno.t10@e3.test")
    assert client.get(ROTA_LISTA, headers=_cabecalho(valido)).status_code == 200

    forjado = jose_jwt.encode(
        {"user_id": a, "email": "aluno.t10@e3.test", "role": "student",
         "exp": datetime.utcnow() + timedelta(hours=1)},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )
    r = client.get(ROTA_LISTA, headers=_cabecalho(forjado))

    assert r.status_code == 401


# --- T11 : cadastro de curso com materials ------------------------------------------------

def _token_admin(client):
    r = client.post("/api/admin/login", json={"password": "admin123"})
    assert r.status_code == 200, r.text
    return _cabecalho(r.json()["token"])


def test_t11a_create_course_grava_o_campo_materials(client):
    cabecalho = _token_admin(client)
    id_com = f"curso_e3_com_{uuid.uuid4().hex[:8]}"
    arquivo = COURSES_DIR_REPO / f"{id_com}.json"
    try:
        r = client.post("/api/admin/create-course", headers=cabecalho,
                        json={**_payload_curso(id_com), "materials": MATERIAIS})
        assert r.status_code == 200, r.text
        gravado = json.loads(arquivo.read_text(encoding="utf-8"))
        assert gravado.get("materials") == MATERIAIS, "create-course descartou o campo materials"
    finally:
        arquivo.unlink(missing_ok=True)


def test_t11b_create_course_sem_materials_continua_aceito(client):
    """Guarda de compatibilidade: curso sem o campo continua sendo cadastrado."""
    cabecalho = _token_admin(client)
    id_sem = f"curso_e3_sem_{uuid.uuid4().hex[:8]}"
    arquivo = COURSES_DIR_REPO / f"{id_sem}.json"
    try:
        r = client.post("/api/admin/create-course", headers=cabecalho, json=_payload_curso(id_sem))
        assert r.status_code == 200, f"curso sem materials deve continuar aceito: {r.text}"
    finally:
        arquivo.unlink(missing_ok=True)


# --- T12 : só active libera material -------------------------------------------------------

@pytest.mark.parametrize("status", ["pending", "active", "cancelled", "refunded"])
def test_t12_so_status_active_libera_material(client, cursos, status):
    email = f"aluno.t12.{status}@e3.test"
    a = _conta_aluno(email)
    m = _matricula(client, a, cursos["mat"], status)

    r, itens = _minha_lista(client, _login(client, email))
    item = _do_id(itens, m)
    assert item["status"] == status
    urls = {x["url"] for x in (item.get("materials") or [])}

    if status == "active":
        assert urls == {URL_1, URL_2}
    else:
        assert urls == set(), f"status {status} não pode liberar material"
        assert URL_1 not in r.text and URL_2 not in r.text
