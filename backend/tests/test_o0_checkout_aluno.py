"""O0 - Checkout do aluno logado + trava do pagamento simulado (PLANO_FEEDBACK_PROF.md, itens H2 e H3; D68/D69).

Origem: o commit `15104c7` (fora do ciclo TDD) criou `POST /api/student/checkout`, `iniciar_checkout_curso` e o modo
`PAYMENTS_MOCK`, sem teste. Este arquivo:
  - CARACTERIZA o checkout do aluno logado (grupos A, B, C): deve passar ja com o codigo atual;
  - fixa o CONTRATO NOVO da trava do mock (grupos M e H), decidido pelo orquestrador: deve falhar agora.

Contrato novo (H3):
  - O mock so vale com PAYMENTS_MOCK ligado E APP_ENV == "development" (sem caixa, aparando espacos). PAYMENTS_MOCK
    ligado sem APP_ENV, ou com APP_ENV de qualquer outro valor -> o mock e IGNORADO: fluxo real (gateway chamado,
    matricula/pagamento `pending`, resposta sem `mocked`). Vale para /api/student/checkout e /api/payments/create-checkout.
  - Mock efetivo: pagamento `approved` com payment_method `mock`, matricula `active`, resposta `mocked: true` e um evento
    de auditoria (E8) `payment.mock_approved`, entity_type `payment`, entity_id = id do pagamento.
  - GET /health ganha `payments_mock` (booleano): true so com o mock efetivo.

Grupos
  A  Autenticacao/perfil: 401 sem token, token forjado ou malformado; 403 para funcionario (JWT de conta e token
     administrativo legado), sem criar nada                                               [caracterizacao]
  B  Validacao: course_id vazio/so espacos/ausente -> 422; curso inexistente -> o mesmo 404 da landing  [caracterizacao]
  C  Fluxo real: matricula e pagamento do dono do JWT, `pending`, valor do catalogo; campos extras do corpo
     (user_id, email, price, amount) ignorados (IDOR); nenhuma conta nova; pendente nao libera material;
     sem MERCADO_PAGO_ACCESS_TOKEN -> 503                                                   [caracterizacao]
  M  Trava do mock (contrato novo) nos dois checkouts                                        [red, exceto M6/M7]
  H  /health com `payments_mock`                                                             [red, exceto H5]

Checklist: IDOR (C2, C3, M7: o aluno vem so do JWT; nenhum id de usuario do corpo e aceito). Recurso pago so com
`active`: C4 e M1 (pendente, inclusive com o mock ignorado, nao expoe URL de material). 401/403: grupo A.
Compatibilidade: H1 (sem nenhuma variavel nova o mock fica desligado e o /health diz false).

Convencoes (padrao de test_e9/test_l1): banco temporario do conftest, cursos em diretorio temporario, Mercado Pago
falso por patch de `payments.routes.requests.post` (nenhuma rede real), PAYMENTS_MOCK e APP_ENV sempre removidos do
ambiente antes de cada teste (o backend/.env local nunca decide o resultado).
"""

import json
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
ROTA_ALUNO = "/api/student/checkout"
ROTA_LANDING = "/api/payments/create-checkout"
CURSO = "curso_o0"
PRECO = 149.9
URL_MATERIAL = "https://materiais.test/o0/apostila.pdf"
URL_GATEWAY = "https://mp.test/o0/checkout"
DETAIL_503 = "Pagamento indisponível no momento."
ACAO_MOCK = "payment.mock_approved"


# =========================================================================================
# Mercado Pago falso
# =========================================================================================

class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []

    def post(self, url, *args, **kwargs):
        self.post_chamadas.append((url, kwargs))
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": "pref-o0", "init_point": URL_GATEWAY}
        resposta.text = '{"id": "pref-o0"}'
        return resposta

    def preferencia(self, i=0):
        return self.post_chamadas[i][1]["json"]


@pytest.fixture(autouse=True)
def ambiente_o0(monkeypatch, tmp_path):
    """Mock desligado por padrao; token do gateway de teste; nada vem do backend/.env local."""
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-o0")
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": "Curso O0", "description": "Curso do checkout do aluno", "price": PRECO,
        "materials": [{"title": "Apostila O0", "url": URL_MATERIAL, "type": "pdf"}],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    # Sem `with`: nao dispara o startup (agente de chat); checkout e /health nao dependem dele.
    return TestClient(fastapi_app, raise_server_exceptions=False)


@pytest.fixture
def gw():
    falso = GatewayFalso()
    with patch("payments.routes.requests.post", side_effect=falso.post):
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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _conta(email, nome, perfil, senha=None):
    hash_senha = get_password_hash(senha) if senha else None
    user_id = Database.add_user(email, nome, hash_senha, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        ana=_conta("ana.aluna@o0.test", "Ana Aluna", "student", "senha-o0-ana"),
        bia=_conta("bia.aluna@o0.test", "Bia Aluna", "student", "senha-o0-bia"),
        gestao=_conta("gestao@o0.test", "Gestora O0", "admin"),
        fin=_conta("fin@o0.test", "Financeiro O0", "financial"),
        sup=_conta("sup@o0.test", "Suporte O0", "support"),
    )


def _forjado(role="student", user_id=1):
    return jose_jwt.encode(
        {"user_id": user_id, "email": "x@o0.test", "role": role},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


def _comprar(client, token, **corpo):
    payload = {"course_id": CURSO}
    payload.update(corpo)
    return client.post(ROTA_ALUNO, json=payload, headers=_auth(token))


def _comprar_landing(client, email="comprador.landing@o0.test"):
    return client.post(ROTA_LANDING, json={
        "course_id": CURSO, "payer": {"name": "Comprador Landing", "email": email},
    })


def _contagens():
    return {
        "users": len(_sql("SELECT id FROM users")),
        "enrollments": len(_sql("SELECT id FROM enrollments")),
        "payments": len(_sql("SELECT id FROM payments")),
    }


def _matriculas(user_id):
    return _sql("SELECT * FROM enrollments WHERE user_id = ? ORDER BY id", (user_id,))


def _pagamentos_da_matricula(enrollment_id):
    return _sql("SELECT * FROM payments WHERE enrollment_id = ? ORDER BY id", (enrollment_id,))


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _ligar_mock(monkeypatch, valor_mock, app_env):
    """valor_mock/app_env None = variavel ausente."""
    if valor_mock is None:
        monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    else:
        monkeypatch.setenv("PAYMENTS_MOCK", valor_mock)
    if app_env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", app_env)


def _assert_fluxo_real(r, gw, chamadas_esperadas=1):
    """Resposta e efeito do fluxo real (gateway): sem `mocked`, pending, gateway chamado."""
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert not corpo.get("mocked"), f"o mock nao podia valer aqui: {corpo}"
    assert corpo.get("checkout_url") == URL_GATEWAY, corpo
    assert len(gw.post_chamadas) == chamadas_esperadas, "o gateway real tinha de ser chamado"
    ref = corpo["external_reference"]
    matricula = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))
    assert len(matricula) == 1 and matricula[0]["status"] == "pending", matricula
    pagamentos = _pagamentos_da_matricula(matricula[0]["id"])
    assert len(pagamentos) == 1, pagamentos
    assert pagamentos[0]["status"] == "pending", pagamentos
    assert pagamentos[0]["payment_method"] == "mercado_pago", pagamentos
    assert _eventos(ACAO_MOCK) == [], "fluxo real nao pode registrar payment.mock_approved"
    return matricula[0], pagamentos[0]


def _assert_mock_efetivo(r, gw):
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo.get("mocked") is True, corpo
    assert gw.post_chamadas == [], "com o mock efetivo o gateway nao pode ser chamado"
    ref = corpo["external_reference"]
    matricula = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))
    assert len(matricula) == 1 and matricula[0]["status"] == "active", matricula
    pagamentos = _pagamentos_da_matricula(matricula[0]["id"])
    assert len(pagamentos) == 1, pagamentos
    pagamento = pagamentos[0]
    assert pagamento["status"] == "approved", pagamento
    assert pagamento["payment_method"] == "mock", pagamento
    assert pagamento["amount"] == PRECO, pagamento
    eventos = _eventos(ACAO_MOCK)
    assert len(eventos) == 1, f"esperado 1 evento {ACAO_MOCK}, obtido {eventos}"
    assert eventos[0]["entity_type"] == "payment", eventos[0]
    assert str(eventos[0]["entity_id"]) == str(pagamento["id"]), eventos[0]
    return matricula[0], pagamento


# =========================================================================================
# Grupo A - autenticacao e perfil [caracterizacao]
# =========================================================================================

@pytest.mark.parametrize("cabecalhos", [
    {},
    {"Authorization": "Bearer " + _forjado()},
    {"Authorization": "Bearer nao-e-um-token"},
    {"Authorization": "Basic YWx1bm86c2VuaGE="},
], ids=["sem_token", "jwt_forjado", "token_malformado", "esquema_errado"])
def test_a1_sem_token_ou_token_invalido_e_401_e_nada_e_criado(client, gw, contas, cabecalhos):
    antes = _contagens()
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO}, headers=cabecalhos)
    assert r.status_code == 401, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


def test_a1b_jwt_forjado_com_id_de_aluno_real_e_401(client, gw, contas):
    antes = _contagens()
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO},
                    headers=_auth(_forjado(user_id=contas.ana.id)))
    assert r.status_code == 401, r.text
    assert _matriculas(contas.ana.id) == []
    assert _contagens() == antes


@pytest.mark.parametrize("perfil", ["gestao", "fin", "sup"])
def test_a2_funcionario_com_jwt_de_conta_recebe_403(client, gw, contas, perfil):
    pessoa = getattr(contas, perfil)
    antes = _contagens()
    r = _comprar(client, pessoa.token)
    assert r.status_code == 403, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


@pytest.mark.parametrize("role", [Role.ADMIN, Role.FINANCIAL, Role.SUPPORT])
def test_a3_token_administrativo_legado_recebe_403(client, gw, contas, role):
    antes = _contagens()
    r = _comprar(client, create_admin_token(role))
    assert r.status_code == 403, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


# =========================================================================================
# Grupo B - validacao [caracterizacao]
# =========================================================================================

@pytest.mark.parametrize("corpo", [
    {"course_id": ""}, {"course_id": "   "}, {}, {"course_id": None},
], ids=["vazio", "so_espacos", "ausente", "nulo"])
def test_b1_course_id_vazio_ou_ausente_e_422(client, gw, contas, corpo):
    antes = _contagens()
    r = client.post(ROTA_ALUNO, json=corpo, headers=_auth(contas.ana.token))
    assert r.status_code == 422, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


def test_b2_curso_inexistente_devolve_o_mesmo_404_da_landing(client, gw, contas):
    antes = _contagens()
    r_aluno = _comprar(client, contas.ana.token, course_id="curso_que_nao_existe_o0")
    r_landing = client.post(ROTA_LANDING, json={
        "course_id": "curso_que_nao_existe_o0", "payer": {"name": "Comprador Landing", "email": "x@o0.test"},
    })
    assert r_landing.status_code == 404, r_landing.text
    assert r_landing.json() == {"detail": "Course not found"}, r_landing.text
    assert r_aluno.status_code == r_landing.status_code, r_aluno.text
    assert r_aluno.json() == r_landing.json(), r_aluno.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


# =========================================================================================
# Grupo C - fluxo real do checkout do aluno [caracterizacao]
# =========================================================================================

def test_c1_matricula_e_pagamento_gravados_para_o_dono_do_jwt_pending_com_valor_do_catalogo(client, gw, contas):
    r = _comprar(client, contas.ana.token)
    matricula, pagamento = _assert_fluxo_real(r, gw)
    assert matricula["user_id"] == contas.ana.id, matricula
    assert matricula["course_id"] == CURSO, matricula
    assert pagamento["amount"] == PRECO, pagamento
    preferencia = gw.preferencia()
    assert preferencia["items"][0]["unit_price"] == PRECO, preferencia["items"]
    assert preferencia["payer"]["email"] == contas.ana.email, preferencia["payer"]
    assert preferencia["external_reference"] == matricula["external_reference"]


def test_c2_campos_extras_do_corpo_sao_ignorados_idor(client, gw, contas):
    r = _comprar(client, contas.ana.token, user_id=contas.bia.id, email=contas.bia.email,
                 price=1, amount=0.01, unit_price=0.01, payer={"email": contas.bia.email, "name": "Bia"})
    matricula, pagamento = _assert_fluxo_real(r, gw)
    assert matricula["user_id"] == contas.ana.id, "a matricula tinha de ser do dono do JWT, nao do corpo"
    assert _matriculas(contas.bia.id) == [], "o aluno indicado no corpo nao pode ganhar matricula"
    assert pagamento["amount"] == PRECO, "o valor vem do catalogo, nunca do corpo"
    preferencia = gw.preferencia()
    assert preferencia["items"][0]["unit_price"] == PRECO
    assert preferencia["payer"]["email"] == contas.ana.email, preferencia["payer"]


def test_c3_nenhuma_conta_nova_e_criada(client, gw, contas):
    usuarios_antes = _sql("SELECT id, email, role FROM users ORDER BY id")
    r = _comprar(client, contas.ana.token, email="email.novo.nunca.visto@o0.test")
    _assert_fluxo_real(r, gw)
    assert _sql("SELECT id, email, role FROM users ORDER BY id") == usuarios_antes
    assert _sql("SELECT id FROM users WHERE email = ?", ("email.novo.nunca.visto@o0.test",)) == []


def test_c4_matricula_pendente_nao_libera_material(client, gw, contas):
    _assert_fluxo_real(_comprar(client, contas.ana.token), gw)
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    itens = r.json()["enrollments"]
    assert len(itens) == 1 and itens[0]["status"] == "pending", itens
    assert URL_MATERIAL not in r.text, "material de curso pago nao pode aparecer com matricula pending"


@pytest.mark.parametrize("configuracao", ["ausente", "vazio", "espacos"])
def test_c5_sem_token_do_gateway_responde_503_e_nada_e_criado(client, gw, contas, monkeypatch, configuracao):
    if configuracao == "ausente":
        monkeypatch.delenv("MERCADO_PAGO_ACCESS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "" if configuracao == "vazio" else "   ")
    antes = _contagens()
    r = _comprar(client, contas.ana.token)
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": DETAIL_503}, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


# =========================================================================================
# Grupo M - trava do mock (contrato novo)
# =========================================================================================

MOCK_IGNORADO = [
    ("1", None), ("1", ""), ("1", "production"), ("1", "PRODUCTION"), ("1", "staging"),
    ("1", "dev"), ("1", "developmentx"), ("1", "test"), ("true", "prod"), ("on", None),
]
MOCK_IGNORADO_IDS = [f"PAYMENTS_MOCK={m}-APP_ENV={'ausente' if e is None else repr(e)}" for m, e in MOCK_IGNORADO]

MOCK_EFETIVO = [
    ("1", "development"), ("true", "development"), ("1", "  Development  "), ("1", "DEVELOPMENT"),
]
MOCK_EFETIVO_IDS = [f"PAYMENTS_MOCK={m}-APP_ENV={e!r}" for m, e in MOCK_EFETIVO]


@pytest.mark.parametrize("valor_mock,app_env", MOCK_IGNORADO, ids=MOCK_IGNORADO_IDS)
def test_m1_aluno_mock_sem_app_env_development_e_ignorado(client, gw, contas, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    r = _comprar(client, contas.ana.token)
    matricula, pagamento = _assert_fluxo_real(r, gw)
    assert matricula["user_id"] == contas.ana.id
    rm = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert URL_MATERIAL not in rm.text, "mock ignorado nao pode liberar material"


@pytest.mark.parametrize("valor_mock,app_env", MOCK_IGNORADO, ids=MOCK_IGNORADO_IDS)
def test_m2_landing_mock_sem_app_env_development_e_ignorado(client, gw, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    _assert_fluxo_real(_comprar_landing(client), gw)


@pytest.mark.parametrize("rota", ["aluno", "landing"])
@pytest.mark.parametrize("app_env", [None, "production"], ids=["APP_ENV_ausente", "APP_ENV_production"])
def test_m3_mock_ignorado_sem_token_do_gateway_responde_503_sem_liberar_nada(
        client, gw, contas, monkeypatch, rota, app_env):
    _ligar_mock(monkeypatch, "1", app_env)
    monkeypatch.delenv("MERCADO_PAGO_ACCESS_TOKEN", raising=False)
    antes = _contagens()
    r = _comprar(client, contas.ana.token) if rota == "aluno" else _comprar_landing(client)
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": DETAIL_503}, r.text
    assert _contagens() == antes, "mock ignorado nao pode criar matricula nem pagamento"
    assert _sql("SELECT id FROM payments WHERE status = 'approved'") == []
    assert _sql("SELECT id FROM enrollments WHERE status = 'active'") == []


@pytest.mark.parametrize("valor_mock,app_env", MOCK_EFETIVO, ids=MOCK_EFETIVO_IDS)
def test_m4_aluno_mock_efetivo_aprova_ativa_e_audita(client, gw, contas, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    r = _comprar(client, contas.ana.token)
    matricula, _ = _assert_mock_efetivo(r, gw)
    assert matricula["user_id"] == contas.ana.id


@pytest.mark.parametrize("valor_mock,app_env", MOCK_EFETIVO, ids=MOCK_EFETIVO_IDS)
def test_m5_landing_mock_efetivo_aprova_ativa_e_audita(client, gw, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    _assert_mock_efetivo(_comprar_landing(client), gw)


@pytest.mark.parametrize("rota", ["aluno", "landing"])
@pytest.mark.parametrize("valor_mock", [None, "", "0", "false", "off"], ids=lambda v: f"PAYMENTS_MOCK={v!r}")
def test_m6_mock_desligado_com_app_env_development_segue_fluxo_real(
        client, gw, contas, monkeypatch, rota, valor_mock):
    """[caracterizacao] sem PAYMENTS_MOCK ligado, APP_ENV=development sozinho nao faz nada."""
    _ligar_mock(monkeypatch, valor_mock, "development")
    r = _comprar(client, contas.ana.token) if rota == "aluno" else _comprar_landing(client)
    _assert_fluxo_real(r, gw)


def test_m7_mock_efetivo_grava_para_o_dono_do_jwt_e_ignora_campos_extras(client, gw, contas, monkeypatch):
    """[caracterizacao do IDOR no caminho do mock; a auditoria e conferida em M4]"""
    _ligar_mock(monkeypatch, "1", "development")
    usuarios_antes = _contagens()["users"]
    r = _comprar(client, contas.ana.token, user_id=contas.bia.id, email=contas.bia.email, price=1, amount=0.01)
    assert r.status_code == 200, r.text
    assert r.json().get("mocked") is True, r.text
    assert len(_matriculas(contas.ana.id)) == 1
    assert _matriculas(contas.bia.id) == []
    assert _contagens()["users"] == usuarios_antes
    assert _sql("SELECT amount FROM payments")[0]["amount"] == PRECO


# =========================================================================================
# Grupo H - /health com payments_mock
# =========================================================================================

def _health(client):
    r = client.get("/health")
    assert r.status_code == 200, r.text
    return r.json()


def test_h1_health_sem_variaveis_diz_mock_desligado(client):
    corpo = _health(client)
    assert "payments_mock" in corpo, corpo
    assert corpo["payments_mock"] is False, corpo


@pytest.mark.parametrize("valor_mock,app_env", MOCK_IGNORADO, ids=MOCK_IGNORADO_IDS)
def test_h2_health_mock_ligado_sem_development_diz_false(client, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    corpo = _health(client)
    assert corpo.get("payments_mock") is False, corpo


@pytest.mark.parametrize("valor_mock", [None, "", "0", "false"], ids=lambda v: f"PAYMENTS_MOCK={v!r}")
def test_h3_health_development_sem_mock_diz_false(client, monkeypatch, valor_mock):
    _ligar_mock(monkeypatch, valor_mock, "development")
    corpo = _health(client)
    assert corpo.get("payments_mock") is False, corpo


@pytest.mark.parametrize("valor_mock,app_env", MOCK_EFETIVO, ids=MOCK_EFETIVO_IDS)
def test_h4_health_mock_efetivo_diz_true(client, monkeypatch, valor_mock, app_env):
    _ligar_mock(monkeypatch, valor_mock, app_env)
    corpo = _health(client)
    assert corpo.get("payments_mock") is True, corpo


def test_h5_health_mantem_as_chaves_antigas(client):
    """[caracterizacao] o campo novo nao remove nada do /health."""
    corpo = _health(client)
    assert corpo.get("status") == "ok", corpo
    for chave in ("courses_loaded", "llm"):
        assert chave in corpo, corpo
