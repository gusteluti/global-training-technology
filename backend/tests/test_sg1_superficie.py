"""SG1 (D109, P1 e P2) - superficie de descoberta e cabecalhos de seguranca da API. Testes escritos antes do codigo (red).

Risco que fecha: `/docs` e `/openapi.json` entregam o mapa completo da API; `/api/chat/courses-debug` e rota de depuracao
publica; `/health` revela o modo de pagamento simulado e a configuracao dos servicos; nenhuma resposta traz cabecalho de
seguranca.

Contrato (decidido pelo PM, D109):
  - `/docs`, `/redoc` e `/openapi.json` respondem 404, exceto quando `APP_ENV` (sem caixa, aparado) e `development` ou
    `test`. `APP_ENV` ausente conta como producao (404).
  - `GET /api/chat/courses-debug` removido: 404.
  - `GET /health` e `GET /api/health` publicos devolvem exatamente `{"status": "ok" | "degraded"}` (mesma regra atual; o
    ramo de excecao devolve `{"status": "error"}` sem texto da excecao). O detalhe (`services`, `courses_loaded`, `llm`,
    `payments_mock`) vai para `GET /api/dashboard/saude`: 401 sem token ou token forjado, 403 para Financeiro, Suporte e
    aluno, 200 so para a Gestao (Role.ADMIN).
  - Toda resposta da API (inclusive 401, 404, 405, 422, 429 e de arquivos) leva `X-Content-Type-Options: nosniff`,
    `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` e `Permissions-Policy: camera=(), microphone=(),
    geolocation=()`.
  - Respostas com Content-Type JSON levam tambem `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`.
    PDF e downloads NAO levam essa CSP (quebraria o visualizador de PDF) e mantem `nosniff`.
  - `Cache-Control: no-store` em `/api/token`, `/api/auth/*`, `/api/admin/*`, `/api/dashboard/*` e `/api/student/*`
    (inclusive nas respostas de erro); ausente em `GET /api/courses`.
  - `Strict-Transport-Security` (max-age >= 15552000) so com `APP_ENV=production`; ausente nos demais.

Grupos
  A  docs/redoc/openapi: 404 em producao e com APP_ENV ausente/invalido; 200 em development e test  [red nos 404]
  B  courses-debug removido                                                                           [red]
  C  /health e /api/health publicos: corpo exato, sem payments_mock, degraded, error                  [red, exceto degraded]
  D  GET /api/dashboard/saude: 401, 403 (financeiro, suporte, aluno), 200 so Gestao com o detalhe    [red]
  E  cabecalhos base em amostras (GET, POST, 401, 404, 405, 422, 429, 500, preflight CORS, arquivos)  [red]
  F  CSP: presente em JSON; ausente no PDF do recibo e no CSV, que mantem os demais cabecalhos        [red, exceto as guardas]
  G  HSTS so em producao                                                                              [red so em producao]
  H  Cache-Control: no-store nas rotas de conta e ausente em /api/courses                             [red nas rotas sem no-store]

Convencoes (padrao de test_o0/test_e9/test_b2): banco temporario do conftest, cursos em diretorio temporario, rotas HTTP
reais com TestClient e contas de teste criadas com Database.* (tokens por create_access_token; o login real por POST /api/token
só nos testes de /api/token). Os testes de APP_ENV
executam `app.py` de novo sob outro nome de modulo (como a E9 faz com o CORS), para valer tanto se a implementacao ler o
APP_ENV na montagem do app quanto se ler a cada requisicao. Nada toca backend/db.sqlite nem backend/courses.
"""

import importlib
import importlib.util
import json
import re
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core import operacao
from core.security import create_access_token, get_password_hash
from db import Database

BACKEND_DIR = Path(__file__).resolve().parent.parent

SENHA = "senha-sg1-2026"
CURSO = "curso-sg1"
NOME_CURSO = "Curso SG1"

CABECALHOS_BASE = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
CSP_JSON = "default-src 'none'; frame-ancestors 'none'"
HSTS_MINIMO = 15552000
CHAVES_DO_DETALHE = {"services", "courses_loaded", "llm", "payments_mock"}
SERVICOS = {"database", "llm", "payment_gateway", "email", "backup"}


# =========================================================================================
# Fixtures e helpers
# =========================================================================================

@pytest.fixture
def cursos(tmp_path, monkeypatch):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": NOME_CURSO, "description": "Curso do SG1", "price": 100.0, "materials": [],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return diretorio


@pytest.fixture
def client(banco, cursos):
    """Sem `with`: nao dispara o startup (agente de chat). Rotas HTTP reais do app padrao (APP_ENV=test do conftest)."""
    from app import app as fastapi_app

    return TestClient(fastapi_app, raise_server_exceptions=False)


_HASH_SENHA = []


def _hash_da_senha():
    """bcrypt e lento: o hash da senha de teste e calculado uma vez por processo."""
    if not _HASH_SENHA:
        _HASH_SENHA.append(get_password_hash(SENHA))
    return _HASH_SENHA[0]


@pytest.fixture
def contas(client):
    """Uma conta por perfil. So o aluno tem senha (os testes de login usam ele); os tokens saem de
    create_access_token, o mesmo caminho dos tokens que POST /api/token emite (padrao de test_o0)."""
    def criar(papel, com_senha=False):
        email = f"{papel}@sg1.test"
        user_id = Database.add_user(email, f"Conta {papel}", _hash_da_senha() if com_senha else None, role=papel)
        assert user_id is not None, f"seed: {email} ja existe"
        token = create_access_token({"user_id": user_id, "email": email, "role": papel})
        return SimpleNamespace(id=user_id, email=email, token=token)

    return SimpleNamespace(
        gestao=criar("admin"), fin=criar("financial"), sup=criar("support"), aluno=criar("student", com_senha=True),
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _forjado(papel="admin", user_id=1):
    return jose_jwt.encode(
        {"user_id": user_id, "email": "x@sg1.test", "role": papel},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


def _app_novo(monkeypatch, app_env):
    """Executa app.py de novo sob outro nome de modulo, com APP_ENV pedido (None remove a variavel).

    Nao toca em sys.modules['app']: os demais testes seguem com o app padrao.
    """
    if app_env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", app_env)
    spec = importlib.util.spec_from_file_location(f"app_sg1_{uuid.uuid4().hex}", BACKEND_DIR / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return TestClient(modulo.app, raise_server_exceptions=False)


def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _pagamento_aprovado(user_id, transaction_id="mp-sg1"):
    """Pagamento aprovado e matricula ativa pelo caminho real (create_enrollment + record_payment + update)."""
    enrollment_id = Database.create_enrollment(user_id, CURSO, f"{CURSO}:sg1:{uuid.uuid4().hex}")
    pid = Database.record_payment(enrollment_id, 100.0, "mercado_pago")
    Database.update_payment_status(pid, "approved", transaction_id)
    return pid


def _resumo(r):
    return f"HTTP {r.status_code} {r.headers.get('content-type')!r} {r.text[:120]!r}"


def _assert_cabecalhos_base(r, rotulo=""):
    faltando = {nome: (r.headers.get(nome), esperado) for nome, esperado in CABECALHOS_BASE.items()
                if r.headers.get(nome) != esperado}
    assert not faltando, f"{rotulo} ({_resumo(r)}): cabecalhos ausentes ou diferentes (obtido, esperado): {faltando}"


def _eh_json(r):
    return "application/json" in (r.headers.get("content-type") or "").lower()


def _no_store(r):
    return r.headers.get("cache-control", "").strip().lower() == "no-store"


# =========================================================================================
# Grupo A - /docs, /redoc e /openapi.json
# =========================================================================================

DOCS = ["/docs", "/redoc", "/openapi.json"]
ENV_SEM_DOCS = [None, "", "   ", "production", "Production", "staging", "prod", "dev", "developmentx", "testing"]
ENV_SEM_DOCS_IDS = [f"APP_ENV={'ausente' if e is None else repr(e)}" for e in ENV_SEM_DOCS]
ENV_COM_DOCS = ["development", "test", "Development", "TEST", "  development  ", " Test "]
ENV_COM_DOCS_IDS = [f"APP_ENV={e!r}" for e in ENV_COM_DOCS]


@pytest.mark.parametrize("caminho", DOCS)
@pytest.mark.parametrize("app_env", ENV_SEM_DOCS, ids=ENV_SEM_DOCS_IDS)
def test_a1_docs_respondem_404_fora_de_development_e_test(banco, monkeypatch, caminho, app_env):
    c = _app_novo(monkeypatch, app_env)
    r = c.get(caminho)
    assert r.status_code == 404, f"{caminho} com APP_ENV={app_env!r}: esperado 404, veio {_resumo(r)}"
    texto = r.text.lower()
    assert "swagger" not in texto and "redoc" not in texto and '"paths"' not in texto, \
        "o 404 nao pode carregar a documentacao nem o mapa da API"


@pytest.mark.parametrize("app_env", ["production", None], ids=["APP_ENV=production", "APP_ENV=ausente"])
def test_a2_openapi_em_producao_nao_vaza_a_rota_admin(banco, monkeypatch, app_env):
    c = _app_novo(monkeypatch, app_env)
    for caminho in DOCS:
        assert "/api/admin" not in c.get(caminho).text, f"{caminho} nao pode listar /api/admin"


@pytest.mark.parametrize("app_env", ENV_COM_DOCS, ids=ENV_COM_DOCS_IDS)
def test_a3_docs_swagger_abre_em_development_e_test(banco, monkeypatch, app_env):
    r = _app_novo(monkeypatch, app_env).get("/docs")
    assert r.status_code == 200, _resumo(r)
    assert "swagger" in r.text.lower()


@pytest.mark.parametrize("app_env", ENV_COM_DOCS, ids=ENV_COM_DOCS_IDS)
def test_a4_redoc_abre_em_development_e_test(banco, monkeypatch, app_env):
    r = _app_novo(monkeypatch, app_env).get("/redoc")
    assert r.status_code == 200, _resumo(r)
    assert "redoc" in r.text.lower()


@pytest.mark.parametrize("app_env", ENV_COM_DOCS, ids=ENV_COM_DOCS_IDS)
def test_a5_openapi_json_abre_em_development_e_test(banco, monkeypatch, app_env):
    r = _app_novo(monkeypatch, app_env).get("/openapi.json")
    assert r.status_code == 200, _resumo(r)
    assert "/api/health" in r.json()["paths"] or "/health" in r.json()["paths"]


def test_a6_app_padrao_da_suite_roda_com_app_env_test_e_abre_docs(client):
    """[guarda] o conftest define APP_ENV=test: o app padrao abre a documentacao (os demais testes dependem disso)."""
    assert client.get("/openapi.json").status_code == 200


# =========================================================================================
# Grupo B - courses-debug removido (P1)
# =========================================================================================

def test_b1_courses_debug_responde_404(client):
    r = client.get("/api/chat/courses-debug")
    assert r.status_code == 404, f"rota de depuracao removida: esperado 404, veio {_resumo(r)}"


def test_b2_courses_debug_404_mesmo_com_o_agente_de_chat_carregado(banco, cursos, catalogo_bot):
    from app import app as fastapi_app

    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        r = c.get("/api/chat/courses-debug")
    assert r.status_code == 404, _resumo(r)
    assert "courses" not in r.text and "price" not in r.text, "nenhum dado do catalogo do bot pode sair por aqui"


def test_b3_courses_debug_nao_consta_no_mapa_da_api(client):
    """O mapa em desenvolvimento tambem nao pode listar a rota."""
    assert "/api/chat/courses-debug" not in client.get("/openapi.json").text


# =========================================================================================
# Grupo C - /health e /api/health publicos (P2)
# =========================================================================================

ROTAS_HEALTH = ["/health", "/api/health"]


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
def test_c1_health_publico_devolve_exatamente_o_status(client, rota):
    r = client.get(rota)
    assert r.status_code == 200, _resumo(r)
    assert r.json() == {"status": "ok"}, f"corpo publico so pode ter 'status': {r.json()}"


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
def test_c2_health_publico_nao_tem_o_detalhe_nem_payments_mock(client, rota):
    texto = client.get(rota).text
    for chave in ("payments_mock", "services", "courses_loaded", "llm", "groq", "available_models", "payment_gateway",
                  "database", "backup", "email"):
        assert chave not in texto, f"{rota} nao pode expor {chave!r}: {texto}"


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
@pytest.mark.parametrize("valor_mock,app_env", [("1", "development"), ("1", "production"), (None, "development")],
                         ids=["mock-efetivo", "mock-ignorado", "sem-mock"])
def test_c3_health_publico_nao_revela_o_modo_de_pagamento(client, monkeypatch, rota, valor_mock, app_env):
    if valor_mock is None:
        monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    else:
        monkeypatch.setenv("PAYMENTS_MOCK", valor_mock)
    monkeypatch.setenv("APP_ENV", app_env)
    r = client.get(rota)
    assert r.status_code == 200, _resumo(r)
    assert r.json() == {"status": "ok"}, r.text
    assert "payments_mock" not in r.text


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
def test_c4_health_degradado_quando_o_banco_cai(client, monkeypatch, tmp_path, rota):
    """A regra atual de ok/degraded continua; so o corpo encolhe."""
    monkeypatch.setattr(Database, "DB_PATH", tmp_path / "nao" / "existe" / "db.sqlite")
    r = client.get(rota)
    assert r.json() == {"status": "degraded"}, _resumo(r)


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
def test_c5_health_no_ramo_de_excecao_devolve_so_status_error_sem_o_texto(client, monkeypatch, rota):
    segredo = "texto-interno-da-excecao-sg1-segredo"

    def quebrar():
        raise RuntimeError(segredo)

    monkeypatch.setattr(operacao, "verificar_servicos", quebrar)
    r = client.get(rota)
    assert r.json() == {"status": "error"}, f"o ramo de excecao nao pode vazar a mensagem: {_resumo(r)}"
    assert segredo not in r.text


@pytest.mark.parametrize("rota", ROTAS_HEALTH)
def test_c6_health_continua_publico_sem_token(client, rota):
    """[guarda] o contrato mantem /health e /api/health sem autenticacao (os e2e e o balanceador dependem disso)."""
    assert client.get(rota).status_code == 200


# =========================================================================================
# Grupo D - GET /api/dashboard/saude (so a Gestao)
# =========================================================================================

ROTA_SAUDE = "/api/dashboard/saude"


def test_d1_saude_sem_token_recebe_401(client):
    r = client.get(ROTA_SAUDE)
    assert r.status_code == 401, f"sem token: esperado 401, veio {_resumo(r)}"


@pytest.mark.parametrize("token", [_forjado("admin"), _forjado("financial"), "lixo.sem.sentido", "abc"],
                         ids=["jwt-forjado-admin", "jwt-forjado-financeiro", "malformado", "curto"])
def test_d2_saude_com_token_forjado_recebe_401(client, token):
    r = client.get(ROTA_SAUDE, headers=_auth(token))
    assert r.status_code == 401, f"token forjado: esperado 401, veio {_resumo(r)}"


@pytest.mark.parametrize("perfil", ["fin", "sup", "aluno"], ids=["financeiro", "suporte", "aluno"])
def test_d3_saude_para_financeiro_suporte_e_aluno_recebe_403(client, contas, perfil):
    r = client.get(ROTA_SAUDE, headers=_auth(getattr(contas, perfil).token))
    assert r.status_code == 403, f"{perfil}: esperado 403, veio {_resumo(r)}"
    for chave in CHAVES_DO_DETALHE:
        assert chave not in r.text, f"o 403 nao pode carregar o detalhe ({chave})"


def test_d4_saude_para_a_gestao_devolve_o_detalhe(client, contas, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.teste.local")
    r = client.get(ROTA_SAUDE, headers=_auth(contas.gestao.token))
    assert r.status_code == 200, _resumo(r)
    corpo = r.json()
    assert corpo["status"] == "ok"
    assert CHAVES_DO_DETALHE <= set(corpo), f"faltam chaves no detalhe: {CHAVES_DO_DETALHE - set(corpo)}"
    assert isinstance(corpo["courses_loaded"], int)
    assert corpo["llm"] == "groq"
    servicos = corpo["services"]
    assert SERVICOS <= set(servicos), f"faltam servicos: {SERVICOS - set(servicos)}"
    assert servicos["database"] == "ok"
    assert servicos["email"] == "configurado" and servicos["payment_gateway"] == "configurado"
    assert servicos["backup"] == "desligado"
    texto = r.text
    assert "TEST-fake" not in texto and "smtp.teste.local" not in texto and "dummy" not in texto, \
        "o detalhe diz se o servico esta configurado, nunca o valor do segredo"


def test_d5_saude_traz_payments_mock_booleano_false_por_padrao(client, contas):
    corpo = client.get(ROTA_SAUDE, headers=_auth(contas.gestao.token)).json()
    assert corpo["payments_mock"] is False, corpo


def test_d6_saude_traz_payments_mock_true_so_com_o_mock_efetivo(client, contas, monkeypatch):
    monkeypatch.setenv("PAYMENTS_MOCK", "1")
    monkeypatch.setenv("APP_ENV", "development")
    corpo = client.get(ROTA_SAUDE, headers=_auth(contas.gestao.token)).json()
    assert corpo["payments_mock"] is True, corpo
    monkeypatch.setenv("APP_ENV", "production")
    corpo = client.get(ROTA_SAUDE, headers=_auth(contas.gestao.token)).json()
    assert corpo["payments_mock"] is False, "mock ligado fora de development e ignorado"


def test_d7_saude_nao_aceita_identificador_de_usuario_do_cliente(client, contas):
    """[IDOR/escopo] o perfil vem so do JWT: user_id e role na query nao concedem acesso a quem nao e Gestao."""
    r = client.get(ROTA_SAUDE, headers=_auth(contas.sup.token),
                   params={"user_id": contas.gestao.id, "role": "admin"})
    assert r.status_code == 403, _resumo(r)


def test_d8_saude_so_aceita_get(client, contas):
    r = client.post(ROTA_SAUDE, headers=_auth(contas.gestao.token))
    assert r.status_code == 405, _resumo(r)


# =========================================================================================
# Grupo E - cabecalhos base em toda resposta
# =========================================================================================

def _chat_ate_429(client, monkeypatch):
    """Envia mensagens ao chat ate o limite (S9) responder 429; devolve (ultima resposta antes do 429, a 429).

    O agente de chat e tirado do app (`app.state.manager_agent = None`, como no app sem startup): outra suite pode
    ter deixado um agente carregado no app compartilhado, e a mensagem chegaria ao LLM (rede). Assim a mensagem
    dentro do limite responde "Manager agent not initialized" sem chamar nada; so o limite de taxa interessa aqui.
    """
    monkeypatch.setattr(importlib.import_module("app").app.state, "manager_agent", None, raising=False)
    anterior = None
    for _ in range(60):
        r = client.post("/api/chat", json={"message": "oi"})
        if r.status_code == 429:
            return anterior, r
        anterior = r
    pytest.fail("o limite do chat nao respondeu 429 em 60 mensagens")


def test_e1_get_publico_de_cursos_tem_os_cabecalhos(client):
    r = client.get("/api/courses")
    assert r.status_code == 200, _resumo(r)
    _assert_cabecalhos_base(r, "GET /api/courses")


@pytest.mark.parametrize("rota", ["/", "/health", "/api/health", "/api/courses/inexistente/turmas"])
def test_e2_outros_gets_publicos_tem_os_cabecalhos(client, rota):
    _assert_cabecalhos_base(client.get(rota), f"GET {rota}")


def test_e3_post_token_com_sucesso_tem_os_cabecalhos(client, contas):
    r = client.post("/api/token", data={"username": contas.aluno.email, "password": SENHA})
    assert r.status_code == 200, _resumo(r)
    _assert_cabecalhos_base(r, "POST /api/token 200")


def test_e4_post_token_com_senha_errada_400_tem_os_cabecalhos(client, contas):
    r = client.post("/api/token", data={"username": contas.aluno.email, "password": "errada-sg1"})
    assert r.status_code == 400, _resumo(r)
    _assert_cabecalhos_base(r, "POST /api/token 400")


def test_e5_post_token_com_email_inexistente_tem_os_cabecalhos(client):
    r = client.post("/api/token", data={"username": "ninguem@sg1.test", "password": "qualquer-sg1"})
    assert r.status_code == 400, _resumo(r)
    _assert_cabecalhos_base(r, "POST /api/token (e-mail inexistente)")


def test_e6_post_token_bloqueado_429_do_login_tem_os_cabecalhos(client, contas):
    for _ in range(5):
        client.post("/api/token", data={"username": contas.aluno.email, "password": "errada-sg1"})
    r = client.post("/api/token", data={"username": contas.aluno.email, "password": SENHA})
    assert r.status_code == 429, _resumo(r)
    _assert_cabecalhos_base(r, "POST /api/token 429")


def test_e7_rota_de_aluno_sem_token_401_tem_os_cabecalhos(client):
    r = client.get("/api/student/me")
    assert r.status_code == 401, _resumo(r)
    _assert_cabecalhos_base(r, "GET /api/student/me sem token")


def test_e8_rota_de_funcionario_com_perfil_errado_403_tem_os_cabecalhos(client, contas):
    r = client.get("/api/admin/audit-logs", headers=_auth(contas.sup.token))
    assert r.status_code == 403, _resumo(r)
    _assert_cabecalhos_base(r, "GET /api/admin/audit-logs 403")


@pytest.mark.parametrize("rota", ["/rota-que-nao-existe", "/api/nada/aqui", "/api/admin/nao-existe"])
def test_e9_rota_inexistente_404_tem_os_cabecalhos(client, rota):
    r = client.get(rota)
    assert r.status_code == 404, _resumo(r)
    _assert_cabecalhos_base(r, f"GET {rota}")


def test_e10_metodo_nao_permitido_405_tem_os_cabecalhos(client):
    r = client.delete("/api/courses")
    assert r.status_code == 405, _resumo(r)
    _assert_cabecalhos_base(r, "DELETE /api/courses")


def test_e11_corpo_invalido_422_tem_os_cabecalhos(client):
    r = client.post("/api/chat", json={})
    assert r.status_code == 422, _resumo(r)
    _assert_cabecalhos_base(r, "POST /api/chat {} 422")


def test_e12_limite_do_chat_429_tem_os_cabecalhos(client, monkeypatch):
    anterior, limitada = _chat_ate_429(client, monkeypatch)
    assert anterior is not None
    _assert_cabecalhos_base(anterior, "POST /api/chat (dentro do limite)")
    _assert_cabecalhos_base(limitada, "POST /api/chat 429")


def test_e13_erro_interno_500_tem_os_cabecalhos(client, monkeypatch):
    """Excecao nao tratada: o 500 vem do handler de erro do Starlette, que fica FORA dos middlewares comuns. A
    implementacao precisa cobrir esse caso (por exemplo, com um handler de Exception ou middleware ASGI externo)."""
    app_modulo = importlib.import_module("app")

    def quebrar():
        raise RuntimeError("falha interna sg1")

    monkeypatch.setattr(app_modulo, "list_course_summaries", quebrar)
    r = client.get("/api/courses")
    assert r.status_code == 500, _resumo(r)
    _assert_cabecalhos_base(r, "GET /api/courses 500")
    assert "falha interna sg1" not in r.text


def test_e14_preflight_cors_tem_os_cabecalhos(client):
    r = client.options("/api/courses", headers={
        "Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET",
    })
    assert r.status_code == 200, _resumo(r)
    _assert_cabecalhos_base(r, "OPTIONS /api/courses (preflight)")


def test_e15_cors_continua_funcionando_com_a_middleware_de_cabecalhos(client):
    """[guarda] a origem do Angular continua autorizada e uma origem estranha continua sem autorizacao."""
    ok = client.get("/api/courses", headers={"Origin": "http://localhost:4200"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:4200"
    estranha = client.get("/api/courses", headers={"Origin": "https://evil.example"})
    assert estranha.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")


def test_e16_pdf_do_recibo_tem_os_cabecalhos(client, contas):
    pid = _pagamento_aprovado(contas.aluno.id)
    r = client.get(f"/api/student/payments/{pid}/receipt.pdf", headers=_auth(contas.aluno.token))
    assert r.status_code == 200, _resumo(r)
    _assert_cabecalhos_base(r, "GET receipt.pdf")


def test_e17_cada_cabecalho_aparece_uma_so_vez_com_o_valor_exato(client):
    """Evita valor duplicado ('nosniff, nosniff') quando mais de uma camada acrescenta o cabecalho."""
    r = client.get("/api/courses")
    bruto = r.headers.raw
    for nome, esperado in CABECALHOS_BASE.items():
        valores = [v.decode("latin-1") for k, v in bruto if k.decode("latin-1").lower() == nome]
        assert valores == [esperado], f"{nome}: {valores}"


# =========================================================================================
# Grupo F - Content-Security-Policy so em JSON
# =========================================================================================

def test_f1_json_publico_leva_a_csp(client):
    r = client.get("/api/courses")
    assert _eh_json(r), _resumo(r)
    assert r.headers.get("content-security-policy") == CSP_JSON


@pytest.mark.parametrize("rota", ["/health", "/api/health", "/"])
def test_f2_outros_json_publicos_levam_a_csp(client, rota):
    r = client.get(rota)
    assert _eh_json(r), _resumo(r)
    assert r.headers.get("content-security-policy") == CSP_JSON, f"{rota}: {r.headers.get('content-security-policy')!r}"


def test_f3_json_de_erro_leva_a_csp(client):
    """401, 404 e 422 sao JSON: levam a CSP."""
    amostras = {
        "401": client.get("/api/student/me"),
        "404": client.get("/rota-que-nao-existe"),
        "422": client.post("/api/chat", json={}),
    }
    for codigo, r in amostras.items():
        assert str(r.status_code) == codigo, _resumo(r)
        assert _eh_json(r), _resumo(r)
        assert r.headers.get("content-security-policy") == CSP_JSON, f"{codigo}: sem a CSP"


def test_f4_json_autenticado_da_gestao_leva_a_csp(client, contas):
    r = client.get(ROTA_SAUDE, headers=_auth(contas.gestao.token))
    assert r.status_code == 200 and _eh_json(r), _resumo(r)
    assert r.headers.get("content-security-policy") == CSP_JSON


def test_f5_pdf_do_recibo_nao_leva_csp_e_mantem_nosniff(client, contas):
    """[guarda da CSP] a CSP `default-src 'none'` quebraria o visualizador de PDF do navegador."""
    pid = _pagamento_aprovado(contas.aluno.id)
    r = client.get(f"/api/student/payments/{pid}/receipt.pdf", headers=_auth(contas.aluno.token))
    assert r.status_code == 200, _resumo(r)
    assert r.headers["content-type"].split(";")[0].strip() == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert "content-security-policy" not in r.headers, "PDF nao pode levar a CSP"
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_f6_pdf_do_recibo_mantem_content_disposition_e_no_store(client, contas):
    """[guarda] a middleware nao pode alterar o que o recibo ja devolvia (B2/D63)."""
    pid = _pagamento_aprovado(contas.aluno.id)
    r = client.get(f"/api/student/payments/{pid}/receipt.pdf", headers=_auth(contas.aluno.token))
    assert r.headers["content-disposition"] == f'attachment; filename="recibo-{pid}.pdf"'
    assert r.headers["cache-control"] == "no-store"
    assert int(r.headers["content-length"]) == len(r.content)


def test_f7_csv_de_download_nao_leva_csp_e_mantem_os_demais_cabecalhos(client, contas):
    r = client.get("/api/dashboard/alunos.csv", headers=_auth(contas.gestao.token))
    assert r.status_code == 200, _resumo(r)
    assert "text/csv" in r.headers["content-type"]
    assert "content-security-policy" not in r.headers, "download CSV nao leva a CSP de JSON"
    _assert_cabecalhos_base(r, "GET alunos.csv")


# =========================================================================================
# Grupo G - Strict-Transport-Security so em producao
# =========================================================================================

def _max_age(r):
    valor = r.headers.get("strict-transport-security") or ""
    achado = re.search(r"max-age\s*=\s*(\d+)", valor, re.IGNORECASE)
    return int(achado.group(1)) if achado else None


@pytest.mark.parametrize("rota", ["/health", "/rota-que-nao-existe", "/api/courses"])
def test_g1_hsts_presente_em_producao(banco, cursos, monkeypatch, rota):
    r = _app_novo(monkeypatch, "production").get(rota)
    assert _max_age(r) is not None, f"APP_ENV=production, {rota}: sem Strict-Transport-Security ({_resumo(r)})"
    assert _max_age(r) >= HSTS_MINIMO, f"max-age abaixo de {HSTS_MINIMO}: {r.headers['strict-transport-security']}"


def test_g2_producao_mantem_os_cabecalhos_base_e_a_csp(banco, cursos, monkeypatch):
    r = _app_novo(monkeypatch, "production").get("/api/courses")
    _assert_cabecalhos_base(r, "producao")
    assert r.headers.get("content-security-policy") == CSP_JSON


@pytest.mark.parametrize("app_env", [None, "", "development", "test", "staging", "dev", "Development"],
                         ids=lambda e: f"APP_ENV={'ausente' if e is None else repr(e)}")
def test_g3_hsts_ausente_fora_de_producao(banco, cursos, monkeypatch, app_env):
    r = _app_novo(monkeypatch, app_env).get("/api/courses")
    assert r.status_code == 200, _resumo(r)
    assert "strict-transport-security" not in r.headers, \
        f"APP_ENV={app_env!r}: HSTS so com production ({r.headers.get('strict-transport-security')!r})"


def test_g4_app_padrao_de_teste_nao_envia_hsts(client):
    assert "strict-transport-security" not in client.get("/api/courses").headers


# =========================================================================================
# Grupo H - Cache-Control: no-store
# =========================================================================================

def _requisicao(client, contas, metodo, rota, quem, **kw):
    token = {"anon": None, "gestao": contas.gestao.token, "fin": contas.fin.token, "sup": contas.sup.token,
             "aluno": contas.aluno.token}[quem]
    cabecalhos = _auth(token) if token else {}
    return client.request(metodo, rota, headers=cabecalhos, **kw)


# (metodo, rota, quem, argumentos extras, status esperado)
CASOS_NO_STORE = [
    ("POST", "/api/token", "anon", {"data": {"username": "ninguem@sg1.test", "password": "x"}}, 400),
    ("POST", "/api/token", "anon", {}, 422),
    ("POST", "/api/auth/register", "anon", {"json": {}}, 422),
    ("POST", "/api/auth/password-reset/request", "anon", {"json": {"email": "ninguem@sg1.test"}}, None),
    ("POST", "/api/auth/password-token/check", "anon", {"json": {"token": "abc"}}, None),
    ("POST", "/api/auth/password-setup", "anon", {"json": {}}, 422),
    ("POST", "/api/admin/login", "anon", {"json": {"password": "senha-errada-sg1"}}, None),
    ("GET", "/api/admin/courses", "gestao", {}, 200),
    ("GET", "/api/admin/courses", "anon", {}, 401),
    ("GET", "/api/admin/audit-logs", "sup", {}, 403),
    ("GET", "/api/admin/audit-logs", "gestao", {}, 200),
    ("GET", "/api/admin/nao-existe", "gestao", {}, 404),
    ("GET", "/api/dashboard/alunos", "gestao", {}, 200),
    ("GET", "/api/dashboard/alunos", "anon", {}, 401),
    ("GET", "/api/dashboard/financeiro", "sup", {}, 403),
    ("GET", "/api/dashboard/saude", "gestao", {}, 200),
    ("GET", "/api/dashboard/saude", "anon", {}, 401),
    ("GET", "/api/dashboard/saude", "fin", {}, 403),
    ("GET", "/api/student/me", "aluno", {}, 200),
    ("GET", "/api/student/me", "anon", {}, 401),
    ("GET", "/api/student/payments", "aluno", {}, 200),
    ("GET", "/api/student/enrollments", "gestao", {}, 403),
    ("GET", "/api/student/payments/999999/receipt", "aluno", {}, 404),
]
CASOS_NO_STORE_IDS = [f"{m}-{r}-{q}-{s or 'qualquer'}" for m, r, q, _, s in CASOS_NO_STORE]


@pytest.mark.parametrize("metodo,rota,quem,extra,status", CASOS_NO_STORE, ids=CASOS_NO_STORE_IDS)
def test_h1_rotas_de_conta_levam_no_store_inclusive_nos_erros(client, contas, metodo, rota, quem, extra, status):
    r = _requisicao(client, contas, metodo, rota, quem, **extra)
    if status is not None:
        assert r.status_code == status, f"{metodo} {rota} ({quem}): esperado {status}, veio {_resumo(r)}"
    assert _no_store(r), f"{metodo} {rota} ({quem}) {r.status_code}: Cache-Control={r.headers.get('cache-control')!r}"


def test_h2_login_com_sucesso_leva_no_store(client, contas):
    r = client.post("/api/token", data={"username": contas.aluno.email, "password": SENHA})
    assert r.status_code == 200 and "access_token" in r.json()
    assert _no_store(r), "a resposta com o JWT nunca pode ser guardada em cache"


def test_h3_pdf_do_recibo_leva_no_store(client, contas):
    """[guarda] rota de /api/student/*: o recibo ja era no-store (B2) e continua."""
    pid = _pagamento_aprovado(contas.aluno.id)
    r = client.get(f"/api/student/payments/{pid}/receipt.pdf", headers=_auth(contas.aluno.token))
    assert r.status_code == 200 and _no_store(r)


def test_h4_csv_de_dashboard_leva_no_store(client, contas):
    r = client.get("/api/dashboard/alunos.csv", headers=_auth(contas.gestao.token))
    assert r.status_code == 200, _resumo(r)
    assert _no_store(r), f"Cache-Control={r.headers.get('cache-control')!r}"


def test_h5_lista_publica_de_cursos_nao_leva_no_store(client):
    r = client.get("/api/courses")
    assert r.status_code == 200, _resumo(r)
    assert "no-store" not in r.headers.get("cache-control", "").lower(), \
        f"o catalogo publico nao e dado de conta: Cache-Control={r.headers.get('cache-control')!r}"


def test_h6_rota_de_prefixo_parecido_nao_leva_no_store(client):
    """[guarda] o no-store e por prefixo de caminho inteiro: `/api/courses/x/turmas` (publica) nao entra."""
    r = client.get("/api/courses/inexistente/turmas")
    assert "no-store" not in r.headers.get("cache-control", "").lower()
