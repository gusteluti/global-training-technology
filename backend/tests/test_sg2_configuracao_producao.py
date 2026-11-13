"""SG2 (D109, P3) - configuracao de producao que nao sobe insegura. Testes escritos antes do codigo (red).

Risco que fecha: `POST /api/admin/login` aceita uma senha unica por perfil, sem identidade individual e sem 2FA;
`ADMIN_TOKEN_SECRET` cai para `ADMIN_PASSWORD` (quem descobre a senha forja tokens de funcionario); o app sobe em producao
com segredo curto, mock de pagamento ou CORS de localhost; `codigo_validacao` do certificado tem o fallback fixo "gt".

Contrato (decidido; a forma dos nomes e escolha do agente-testes, ver relatorio):
  - `core/configuracao.py`:
      `validar_configuracao(env=None) -> list[str]`  lista de problemas, cada um uma frase SEM valor de segredo e que
          CITA o nome da variavel. `env` e um mapeamento injetavel (None = os.environ); com `env` injetado nada e lido
          de os.environ. A lista independe de APP_ENV: quem decide se o problema derruba a subida e o
          `exigir_configuracao_segura()`.
      `exigir_configuracao_segura()`  le os.environ; com APP_ENV == production (sem caixa, aparado) e problemas,
          levanta RuntimeError com todos os problemas de uma vez; fora de producao nao levanta.
  - O startup do app chama `exigir_configuracao_segura()`: em producao com problema o startup levanta RuntimeError;
    fora de producao (development, test, ausente, qualquer outro valor) sobe e escreve `[AVISO]` no log para os mesmos
    problemas. A checagem e no STARTUP, nao na importacao de app.py (os testes da SG1 carregam app.py sob production
    sem startup).
  - Problemas (producao):
      JWT_SECRET_KEY ausente/vazia ou < 32 caracteres
      ADMIN_TOKEN_SECRET ausente/vazia ou igual a ADMIN_PASSWORD / FINANCIAL_PASSWORD / SUPPORT_PASSWORD
      senha de perfil definida com < 12 caracteres ou igual a uma senha publica do seed_demo (Senha-Demo-2026)
      PAYMENTS_MOCK ligado (1/true/yes/on, sem caixa, aparado: o que `_pagamento_mockado` aceita como "ligado")
      MERCADO_PAGO_WEBHOOK_SECRET ausente ou vazio
      MERCADO_PAGO_ACCESS_TOKEN ausente ou vazio
      CORS_ALLOWED_ORIGINS ausente/vazia, ou com localhost, 127.0.0.1 ou origem http:// (so https://)
  - `POST /api/admin/login` (legado): 404 com APP_ENV=production; em development e test igual a hoje.
  - `get_admin_secret()`: em producao nao cai para ADMIN_PASSWORD; fora dela mantem o fallback.
  - `codigo_validacao`: sem JWT_SECRET_KEY levanta erro (nada de "gt"); com a chave, valor identico ao de antes.

Grupos
  A  validar_configuracao: valida -> []; um caso por condicao de recusa; limites; todos de uma vez; sem segredo no texto
  B  exigir_configuracao_segura: production levanta (lista completa, sem segredo); normalizacao do APP_ENV; fora de
     producao nao levanta
  C  startup do app: producao valida sobe; producao invalida nao sobe; nao quebra na importacao; fora de producao sobe
     com [AVISO]
  D  login legado: 404 em producao (sem efeitos), igual a hoje em development e test, tokens em producao
  E  get_admin_secret
  F  codigo_validacao: sem chave levanta; guarda verde com valores fixos de referencia; certificado continua valido

Convencoes (padrao da E9 e da SG1): banco temporario do conftest, catalogo do bot temporario (D70), nenhuma rede. Os
testes de producao executam `app.py` de novo sob outro nome de modulo, com o ambiente pedido (nao tocam em
sys.modules['app']), para valer tanto se a implementacao le o APP_ENV na montagem quanto a cada requisicao. Variaveis de
ambiente sao sempre trocadas com monkeypatch; o modulo novo e importado DENTRO de cada teste (antes de a implementacao
existir, o teste falha com mensagem clara, nao como erro de coleta).
"""

import hashlib
import hmac
import importlib
import importlib.util
import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.security import create_admin_token, get_password_hash
from db import Database
from models.user import Role

BACKEND_DIR = Path(__file__).resolve().parent.parent

# --- Configuracao valida de producao (valores fabricados; nenhum e segredo real) ---------------------------------------
JWT_OK = "jwt-prod-Kq83mZx0Lw71PcVb5NsT2uYe9RhDa4Gf"          # 40 caracteres
TOKEN_ADMIN_OK = "staff-prod-Wm27QxLr90VbN4cZs18TyHuE5pKd3GaJ"  # 40 caracteres, diferente de qualquer senha
SENHA_ADMIN = "Gestao-Prod-9xKq2w"
SENHA_FIN = "Financ-Prod-7vBn4z"
SENHA_SUP = "Suporte-Prod-3mTc8y"
WEBHOOK_OK = "whsec-prod-Zp41LkQ7wXe92"
ACCESS_TOKEN_OK = "APP_USR-prod-8841-fabricado-Qw3Er5Ty"
CORS_OK = "https://app.exemplo.test,https://www.exemplo.test"
SENHA_PUBLICA_SEED = "Senha-Demo-2026"

PRODUCAO_VALIDA = {
    "APP_ENV": "production",
    "JWT_SECRET_KEY": JWT_OK,
    "ADMIN_TOKEN_SECRET": TOKEN_ADMIN_OK,
    "ADMIN_PASSWORD": SENHA_ADMIN,
    "FINANCIAL_PASSWORD": SENHA_FIN,
    "SUPPORT_PASSWORD": SENHA_SUP,
    "MERCADO_PAGO_WEBHOOK_SECRET": WEBHOOK_OK,
    "MERCADO_PAGO_ACCESS_TOKEN": ACCESS_TOKEN_OK,
    "CORS_ALLOWED_ORIGINS": CORS_OK,
}
# Toda variavel que a validacao le: o ambiente do teste parte de "nenhuma delas" (nada vem do shell nem do conftest).
VARIAVEIS_DA_CONFIGURACAO = (
    "APP_ENV", "JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "ADMIN_PASSWORD", "FINANCIAL_PASSWORD", "SUPPORT_PASSWORD",
    "PAYMENTS_MOCK", "MERCADO_PAGO_WEBHOOK_SECRET", "MERCADO_PAGO_ACCESS_TOKEN", "CORS_ALLOWED_ORIGINS",
)
VALORES_SECRETOS_VALIDOS = (JWT_OK, TOKEN_ADMIN_OK, SENHA_ADMIN, SENHA_FIN, SENHA_SUP, WEBHOOK_OK, ACCESS_TOKEN_OK)


def _com(**mudancas):
    """PRODUCAO_VALIDA com alteracoes; valor None remove a variavel."""
    env = dict(PRODUCAO_VALIDA)
    for nome, valor in mudancas.items():
        if valor is None:
            env.pop(nome, None)
        else:
            env[nome] = valor
    return env


def _aplicar_ambiente(monkeypatch, env):
    """Zera as variaveis da configuracao e aplica `env` no os.environ do processo."""
    for nome in VARIAVEIS_DA_CONFIGURACAO:
        monkeypatch.delenv(nome, raising=False)
    for nome, valor in env.items():
        monkeypatch.setenv(nome, valor)


def _configuracao():
    """Importa core.configuracao dentro do teste: ausente -> FAILED com mensagem clara (nao erro de coleta)."""
    try:
        return importlib.import_module("core.configuracao")
    except ImportError as erro:
        pytest.fail(f"SG2: o modulo backend/core/configuracao.py ainda nao existe ({erro})", pytrace=False)


def _problemas(env):
    modulo = _configuracao()
    assert hasattr(modulo, "validar_configuracao"), "SG2: core.configuracao.validar_configuracao nao existe"
    problemas = modulo.validar_configuracao(env)
    assert isinstance(problemas, list), f"validar_configuracao deve devolver list, devolveu {type(problemas).__name__}"
    assert all(isinstance(p, str) and p.strip() for p in problemas), f"problemas devem ser frases: {problemas!r}"
    return problemas


def _exigir(monkeypatch, env):
    """Aplica `env` no os.environ e chama exigir_configuracao_segura()."""
    modulo = _configuracao()  # importa ANTES de mexer no ambiente (um load_dotenv do modulo nao pode repor variaveis)
    assert hasattr(modulo, "exigir_configuracao_segura"), "SG2: core.configuracao.exigir_configuracao_segura nao existe"
    _aplicar_ambiente(monkeypatch, env)
    return modulo.exigir_configuracao_segura()


def _carregar_app():
    """Executa app.py de novo sob outro nome de modulo (nao toca em sys.modules['app'])."""
    spec = importlib.util.spec_from_file_location(f"app_sg2_{uuid.uuid4().hex}", BACKEND_DIR / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _subir(monkeypatch, env):
    """Aplica o ambiente, carrega app.py e entra no `with TestClient` (dispara o startup). Devolve o GET /health.

    Se a checagem de producao levanta na importacao ou no startup, a excecao sai daqui.
    """
    _aplicar_ambiente(monkeypatch, env)
    modulo = _carregar_app()
    with TestClient(modulo.app, raise_server_exceptions=False) as cliente:
        return cliente.get("/health")


def _app_sem_startup(monkeypatch, env):
    """Cliente SEM `with` (sem startup): so exercita rotas, como a SG1 faz com APP_ENV=production."""
    _aplicar_ambiente(monkeypatch, env)
    modulo = _carregar_app()
    return TestClient(modulo.app, raise_server_exceptions=False)


def _contagem(tabela, onde="1=1"):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {onde}").fetchone()[0]
    finally:
        conn.close()


# =========================================================================================
# Grupo A - validar_configuracao (funcao pura, `env` injetado)
# =========================================================================================

def test_a1_producao_valida_nao_tem_problemas():
    assert _problemas(PRODUCAO_VALIDA) == []


def test_a2_so_a_senha_de_gestao_basta_financeiro_e_suporte_sao_opcionais():
    assert _problemas(_com(FINANCIAL_PASSWORD=None, SUPPORT_PASSWORD=None)) == []


def test_a3_payments_mock_desligado_nao_e_problema():
    for valor in ("0", "false", "no", "off", ""):
        assert _problemas(_com(PAYMENTS_MOCK=valor)) == [], f"PAYMENTS_MOCK={valor!r} nao liga o mock"


# (id, mudancas sobre a producao valida, nomes de variavel que o problema precisa citar)
RECUSAS = [
    ("jwt_ausente", {"JWT_SECRET_KEY": None}, ["JWT_SECRET_KEY"]),
    ("jwt_vazia", {"JWT_SECRET_KEY": ""}, ["JWT_SECRET_KEY"]),
    ("jwt_31_caracteres", {"JWT_SECRET_KEY": "k" * 31}, ["JWT_SECRET_KEY"]),
    ("jwt_curta", {"JWT_SECRET_KEY": "jwt-curto-zz9"}, ["JWT_SECRET_KEY"]),
    ("token_admin_ausente", {"ADMIN_TOKEN_SECRET": None}, ["ADMIN_TOKEN_SECRET"]),
    ("token_admin_vazio", {"ADMIN_TOKEN_SECRET": ""}, ["ADMIN_TOKEN_SECRET"]),
    ("token_admin_igual_senha_admin", {"ADMIN_TOKEN_SECRET": SENHA_ADMIN}, ["ADMIN_TOKEN_SECRET"]),
    ("token_admin_igual_senha_financeiro", {"ADMIN_TOKEN_SECRET": SENHA_FIN}, ["ADMIN_TOKEN_SECRET"]),
    ("token_admin_igual_senha_suporte", {"ADMIN_TOKEN_SECRET": SENHA_SUP}, ["ADMIN_TOKEN_SECRET"]),
    ("senha_admin_11_caracteres", {"ADMIN_PASSWORD": "Abcdefgh-12"}, ["ADMIN_PASSWORD"]),
    ("senha_admin_curta", {"ADMIN_PASSWORD": "admin123"}, ["ADMIN_PASSWORD"]),
    ("senha_financeiro_curta", {"FINANCIAL_PASSWORD": "fin123"}, ["FINANCIAL_PASSWORD"]),
    ("senha_suporte_curta", {"SUPPORT_PASSWORD": "sup123"}, ["SUPPORT_PASSWORD"]),
    ("senha_admin_do_seed_demo", {"ADMIN_PASSWORD": SENHA_PUBLICA_SEED}, ["ADMIN_PASSWORD"]),
    ("senha_financeiro_do_seed_demo", {"FINANCIAL_PASSWORD": SENHA_PUBLICA_SEED}, ["FINANCIAL_PASSWORD"]),
    ("senha_suporte_do_seed_demo", {"SUPPORT_PASSWORD": SENHA_PUBLICA_SEED}, ["SUPPORT_PASSWORD"]),
    ("mock_1", {"PAYMENTS_MOCK": "1"}, ["PAYMENTS_MOCK"]),
    ("mock_true", {"PAYMENTS_MOCK": "true"}, ["PAYMENTS_MOCK"]),
    ("mock_TRUE_maiusculo", {"PAYMENTS_MOCK": "TRUE"}, ["PAYMENTS_MOCK"]),
    ("mock_yes", {"PAYMENTS_MOCK": "yes"}, ["PAYMENTS_MOCK"]),
    ("mock_on_com_espacos", {"PAYMENTS_MOCK": "  On "}, ["PAYMENTS_MOCK"]),
    ("webhook_ausente", {"MERCADO_PAGO_WEBHOOK_SECRET": None}, ["MERCADO_PAGO_WEBHOOK_SECRET"]),
    ("webhook_vazio", {"MERCADO_PAGO_WEBHOOK_SECRET": ""}, ["MERCADO_PAGO_WEBHOOK_SECRET"]),
    ("webhook_so_espacos", {"MERCADO_PAGO_WEBHOOK_SECRET": "   "}, ["MERCADO_PAGO_WEBHOOK_SECRET"]),
    ("access_token_ausente", {"MERCADO_PAGO_ACCESS_TOKEN": None}, ["MERCADO_PAGO_ACCESS_TOKEN"]),
    ("access_token_vazio", {"MERCADO_PAGO_ACCESS_TOKEN": ""}, ["MERCADO_PAGO_ACCESS_TOKEN"]),
    ("access_token_so_espacos", {"MERCADO_PAGO_ACCESS_TOKEN": "  "}, ["MERCADO_PAGO_ACCESS_TOKEN"]),
    ("cors_ausente", {"CORS_ALLOWED_ORIGINS": None}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_vazia", {"CORS_ALLOWED_ORIGINS": ""}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_so_espacos", {"CORS_ALLOWED_ORIGINS": "   "}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_localhost_http", {"CORS_ALLOWED_ORIGINS": "http://localhost:4200"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_localhost_https", {"CORS_ALLOWED_ORIGINS": "https://localhost:4200"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_localhost_maiusculo", {"CORS_ALLOWED_ORIGINS": "https://LocalHost:4200"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_127_0_0_1", {"CORS_ALLOWED_ORIGINS": "https://127.0.0.1:8443"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_http_de_dominio_real", {"CORS_ALLOWED_ORIGINS": "http://app.exemplo.test"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_valida_mais_localhost", {"CORS_ALLOWED_ORIGINS": CORS_OK + ",http://localhost:4200"}, ["CORS_ALLOWED_ORIGINS"]),
    ("cors_valida_mais_http", {"CORS_ALLOWED_ORIGINS": CORS_OK + ",http://outro.exemplo.test"}, ["CORS_ALLOWED_ORIGINS"]),
]


@pytest.mark.parametrize("mudancas,nomes", [(m, n) for _, m, n in RECUSAS], ids=[i for i, _, _ in RECUSAS])
def test_a4_cada_condicao_de_recusa_gera_um_problema_que_cita_a_variavel(mudancas, nomes):
    problemas = _problemas(_com(**mudancas))
    assert len(problemas) == 1, f"esperava exatamente 1 problema, veio {problemas!r}"
    for nome in nomes:
        assert nome in problemas[0], f"o problema deve citar {nome}: {problemas[0]!r}"


def test_a5_limites_exatos_aceitam_32_caracteres_de_jwt_e_12_de_senha():
    assert _problemas(_com(JWT_SECRET_KEY="j" * 32)) == []
    assert _problemas(_com(ADMIN_PASSWORD="Abcdefgh-123")) == []  # 12 caracteres
    assert _problemas(_com(FINANCIAL_PASSWORD="Abcdefgh-123", SUPPORT_PASSWORD="Zyxwvuts-987")) == []


def test_a6_cors_com_varias_origens_https_e_espacos_apos_a_virgula_e_valida():
    assert _problemas(_com(CORS_ALLOWED_ORIGINS="https://a.exemplo.test, https://b.exemplo.test/")) == []


def test_a7_todos_os_problemas_vem_de_uma_vez_e_nao_so_o_primeiro():
    problemas = _problemas({"APP_ENV": "production"})  # nada configurado
    texto = " ".join(problemas)
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "MERCADO_PAGO_WEBHOOK_SECRET", "MERCADO_PAGO_ACCESS_TOKEN",
                 "CORS_ALLOWED_ORIGINS"):
        assert nome in texto, f"{nome} deveria estar entre os problemas: {problemas!r}"
    assert len(problemas) >= 5


def test_a8_varias_falhas_juntas_listam_cada_uma_delas():
    env = _com(JWT_SECRET_KEY="curta-aaa", ADMIN_PASSWORD="admin123", PAYMENTS_MOCK="1",
               CORS_ALLOWED_ORIGINS="http://localhost:4200", MERCADO_PAGO_WEBHOOK_SECRET="")
    problemas = _problemas(env)
    texto = " ".join(problemas)
    for nome in ("JWT_SECRET_KEY", "ADMIN_PASSWORD", "PAYMENTS_MOCK", "CORS_ALLOWED_ORIGINS",
                 "MERCADO_PAGO_WEBHOOK_SECRET"):
        assert nome in texto, f"{nome} deveria estar entre os problemas: {problemas!r}"
    assert len(problemas) >= 5


def test_a9_env_injetado_nao_le_o_os_environ(monkeypatch):
    """O conftest deixa JWT, webhook, token do gateway etc. definidos no os.environ; com `env={}` nada disso vale."""
    assert os.environ.get("JWT_SECRET_KEY"), "pre-condicao: o conftest define JWT_SECRET_KEY"
    texto = " ".join(_problemas({}))
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "MERCADO_PAGO_WEBHOOK_SECRET", "MERCADO_PAGO_ACCESS_TOKEN",
                 "CORS_ALLOWED_ORIGINS"):
        assert nome in texto, f"{nome}: env injetado vazio deve acusar, sem consultar o os.environ"


def test_a10_sem_env_injetado_le_o_os_environ(monkeypatch):
    modulo = _configuracao()
    _aplicar_ambiente(monkeypatch, PRODUCAO_VALIDA)
    assert modulo.validar_configuracao() == []
    monkeypatch.setenv("JWT_SECRET_KEY", "curta-bbb")
    problemas = modulo.validar_configuracao()
    assert len(problemas) == 1 and "JWT_SECRET_KEY" in problemas[0]


def test_a11_a_lista_de_problemas_independe_do_app_env():
    ruim = _com(JWT_SECRET_KEY="curta-ccc", PAYMENTS_MOCK="1")
    em_producao = _problemas(ruim)
    assert len(em_producao) == 2
    for outro in ("development", "test", "staging", ""):
        assert _problemas({**ruim, "APP_ENV": outro}) == em_producao, f"APP_ENV={outro!r}"
    sem_app_env = {k: v for k, v in ruim.items() if k != "APP_ENV"}
    assert _problemas(sem_app_env) == em_producao


def test_a12_nenhum_problema_traz_valor_de_segredo():
    segredos = ["jwt-curto-SEGREDO-q1", "Igual-Senha-Admin-Prod9", "fin-curta-Zk7", SENHA_PUBLICA_SEED,
                "webhook-SEGREDO-mp-77"]
    env = _com(
        JWT_SECRET_KEY=segredos[0],
        ADMIN_PASSWORD=segredos[1], ADMIN_TOKEN_SECRET=segredos[1],  # token igual a senha
        FINANCIAL_PASSWORD=segredos[2],
        SUPPORT_PASSWORD=segredos[3],
        MERCADO_PAGO_WEBHOOK_SECRET=segredos[4],  # presente: nao e problema, mas tambem nao pode vazar
        PAYMENTS_MOCK="1", CORS_ALLOWED_ORIGINS="http://localhost:4200",
    )
    problemas = _problemas(env)
    assert len(problemas) >= 5
    texto = "\n".join(problemas)
    for segredo in segredos + [ACCESS_TOKEN_OK]:
        assert segredo not in texto, "um valor de segredo apareceu na lista de problemas"


# =========================================================================================
# Grupo B - exigir_configuracao_segura
# =========================================================================================

def test_b1_producao_valida_nao_levanta(monkeypatch):
    _exigir(monkeypatch, PRODUCAO_VALIDA)


@pytest.mark.parametrize("mudancas,nomes", [(m, n) for _, m, n in RECUSAS], ids=[i for i, _, _ in RECUSAS])
def test_b2_producao_com_problema_levanta_runtime_error_citando_a_variavel(monkeypatch, mudancas, nomes):
    with pytest.raises(RuntimeError) as erro:
        _exigir(monkeypatch, _com(**mudancas))
    for nome in nomes:
        assert nome in str(erro.value), f"a mensagem deve citar {nome}: {erro.value!s}"


def test_b3_producao_lista_todos_os_problemas_de_uma_vez(monkeypatch):
    with pytest.raises(RuntimeError) as erro:
        _exigir(monkeypatch, {"APP_ENV": "production"})
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "MERCADO_PAGO_WEBHOOK_SECRET", "MERCADO_PAGO_ACCESS_TOKEN",
                 "CORS_ALLOWED_ORIGINS"):
        assert nome in str(erro.value), f"{nome} faltou na mensagem: {erro.value!s}"


def test_b4_a_mensagem_do_erro_nao_traz_valor_de_segredo(monkeypatch):
    segredos = ["jwt-curto-SEGREDO-q1", "Igual-Senha-Admin-Prod9", "fin-curta-Zk7", SENHA_PUBLICA_SEED,
                "webhook-SEGREDO-mp-77"]
    env = _com(
        JWT_SECRET_KEY=segredos[0], ADMIN_PASSWORD=segredos[1], ADMIN_TOKEN_SECRET=segredos[1],
        FINANCIAL_PASSWORD=segredos[2], SUPPORT_PASSWORD=segredos[3], MERCADO_PAGO_WEBHOOK_SECRET=segredos[4],
        PAYMENTS_MOCK="1", CORS_ALLOWED_ORIGINS="http://localhost:4200",
    )
    with pytest.raises(RuntimeError) as erro:
        _exigir(monkeypatch, env)
    mensagem = str(erro.value) + repr(erro.value) + repr(erro.value.args)
    for segredo in segredos + [ACCESS_TOKEN_OK]:
        assert segredo not in mensagem, "um valor de segredo apareceu na mensagem do erro"


@pytest.mark.parametrize("app_env", ["production", "PRODUCTION", "  production  ", "Production\t"],
                         ids=["minusculo", "maiusculo", "com_espacos", "capitalizado_com_tab"])
def test_b5_app_env_production_e_normalizado_sem_caixa_e_aparado(monkeypatch, app_env):
    with pytest.raises(RuntimeError):
        _exigir(monkeypatch, _com(APP_ENV=app_env, JWT_SECRET_KEY="curta-ddd"))


@pytest.mark.parametrize("app_env", ["development", "test", "staging", "prod", "producao", "", None],
                         ids=["development", "test", "staging", "prod", "producao_pt", "vazio", "ausente"])
def test_b6_fora_de_producao_nao_levanta_mesmo_com_tudo_errado(monkeypatch, app_env):
    env = {"JWT_SECRET_KEY": "curta-eee", "ADMIN_PASSWORD": "admin123", "ADMIN_TOKEN_SECRET": "admin123",
           "PAYMENTS_MOCK": "1", "CORS_ALLOWED_ORIGINS": "http://localhost:4200"}
    if app_env is not None:
        env["APP_ENV"] = app_env
    _exigir(monkeypatch, env)  # nao levanta


# =========================================================================================
# Grupo C - startup do app
# =========================================================================================

def test_c1_producao_valida_sobe_normalmente(banco, catalogo_bot, monkeypatch):
    resposta = _subir(monkeypatch, PRODUCAO_VALIDA)
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_c2_producao_valida_somente_com_senha_de_gestao_sobe(banco, catalogo_bot, monkeypatch):
    assert _subir(monkeypatch, _com(FINANCIAL_PASSWORD=None, SUPPORT_PASSWORD=None)).status_code == 200


# um caso por variavel (a cobertura de todas as condicoes esta em A e B; aqui basta provar a ligacao com o startup)
RECUSAS_NO_STARTUP = [
    ("jwt_curta", {"JWT_SECRET_KEY": "jwt-curto-zz9"}, "JWT_SECRET_KEY"),
    ("token_igual_senha", {"ADMIN_TOKEN_SECRET": SENHA_ADMIN}, "ADMIN_TOKEN_SECRET"),
    ("senha_curta", {"FINANCIAL_PASSWORD": "fin123"}, "FINANCIAL_PASSWORD"),
    ("senha_do_seed", {"SUPPORT_PASSWORD": SENHA_PUBLICA_SEED}, "SUPPORT_PASSWORD"),
    ("mock_ligado", {"PAYMENTS_MOCK": "1"}, "PAYMENTS_MOCK"),
    ("webhook_vazio", {"MERCADO_PAGO_WEBHOOK_SECRET": ""}, "MERCADO_PAGO_WEBHOOK_SECRET"),
    ("access_token_ausente", {"MERCADO_PAGO_ACCESS_TOKEN": None}, "MERCADO_PAGO_ACCESS_TOKEN"),
    ("cors_localhost", {"CORS_ALLOWED_ORIGINS": "http://localhost:4200"}, "CORS_ALLOWED_ORIGINS"),
]


@pytest.mark.parametrize("mudancas,nome", [(m, n) for _, m, n in RECUSAS_NO_STARTUP],
                         ids=[i for i, _, _ in RECUSAS_NO_STARTUP])
def test_c3_producao_insegura_nao_sobe(banco, catalogo_bot, monkeypatch, mudancas, nome):
    with pytest.raises(RuntimeError) as erro:
        _subir(monkeypatch, _com(**mudancas))
    assert nome in str(erro.value)


def test_c4_o_startup_lista_todos_os_problemas_e_nenhum_segredo(banco, catalogo_bot, monkeypatch):
    segredos = ["jwt-curto-SEGREDO-q1", "Igual-Senha-Admin-Prod9", "fin-curta-Zk7", SENHA_PUBLICA_SEED]
    env = _com(
        JWT_SECRET_KEY=segredos[0], ADMIN_PASSWORD=segredos[1], ADMIN_TOKEN_SECRET=segredos[1],
        FINANCIAL_PASSWORD=segredos[2], SUPPORT_PASSWORD=segredos[3], PAYMENTS_MOCK="true",
        MERCADO_PAGO_WEBHOOK_SECRET="", CORS_ALLOWED_ORIGINS="http://localhost:4200",
    )
    with pytest.raises(RuntimeError) as erro:
        _subir(monkeypatch, env)
    mensagem = str(erro.value)
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "ADMIN_PASSWORD", "FINANCIAL_PASSWORD", "SUPPORT_PASSWORD",
                 "PAYMENTS_MOCK", "MERCADO_PAGO_WEBHOOK_SECRET", "CORS_ALLOWED_ORIGINS"):
        assert nome in mensagem, f"{nome} faltou na mensagem de recusa"
    for segredo in segredos + [ACCESS_TOKEN_OK]:
        assert segredo not in mensagem


def test_c5_a_checagem_e_no_startup_e_nao_na_importacao(banco, catalogo_bot, monkeypatch):
    """Os testes da SG1 (e qualquer ferramenta que importe app.py) carregam o app sob production sem startup."""
    _aplicar_ambiente(monkeypatch, _com(JWT_SECRET_KEY="curta-fff", PAYMENTS_MOCK="1"))
    modulo = _carregar_app()  # nao levanta
    with pytest.raises(RuntimeError):
        with TestClient(modulo.app, raise_server_exceptions=False):
            pass


@pytest.mark.parametrize("app_env", ["development", "test", None, "staging"],
                         ids=["development", "test", "ausente", "staging"])
def test_c6_fora_de_producao_sobe_com_aviso_no_log_e_sem_segredo(banco, catalogo_bot, monkeypatch, capsys, caplog,
                                                                 app_env):
    segredos = ["jwt-curto-SEGREDO-q1", "Igual-Senha-Admin-Prod9", "fin-curta-Zk7", SENHA_PUBLICA_SEED,
                "webhook-SEGREDO-mp-77"]
    env = _com(
        JWT_SECRET_KEY=segredos[0], ADMIN_PASSWORD=segredos[1], ADMIN_TOKEN_SECRET=segredos[1],
        FINANCIAL_PASSWORD=segredos[2], SUPPORT_PASSWORD=segredos[3], MERCADO_PAGO_WEBHOOK_SECRET=segredos[4],
        PAYMENTS_MOCK="1", CORS_ALLOWED_ORIGINS="http://localhost:4200",
    )
    env.pop("APP_ENV")
    if app_env is not None:
        env["APP_ENV"] = app_env
    capsys.readouterr()
    with caplog.at_level("DEBUG"):
        resposta = _subir(monkeypatch, env)
    assert resposta.status_code == 200, "fora de producao nada impede a subida"
    saida = capsys.readouterr()
    log = saida.out + "\n" + saida.err + "\n" + caplog.text
    avisos = "\n".join(linha for linha in log.splitlines() if "[AVISO]" in linha)
    assert avisos, "SG2: fora de producao a configuracao insegura deve gerar [AVISO] no log"
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "ADMIN_PASSWORD", "FINANCIAL_PASSWORD", "SUPPORT_PASSWORD",
                 "PAYMENTS_MOCK", "CORS_ALLOWED_ORIGINS"):
        assert nome in avisos, f"{nome}: faltou [AVISO] para o mesmo problema"
    for segredo in segredos + [ACCESS_TOKEN_OK]:
        assert segredo not in log, "um valor de segredo apareceu no log"


def test_c7_fora_de_producao_com_configuracao_valida_nao_gera_aviso_de_configuracao(banco, catalogo_bot, monkeypatch,
                                                                                    capsys, caplog):
    env = _com(APP_ENV="development")
    env["CORS_ALLOWED_ORIGINS"] = CORS_OK
    capsys.readouterr()
    with caplog.at_level("DEBUG"):
        assert _subir(monkeypatch, env).status_code == 200
    saida = capsys.readouterr()
    log = saida.out + "\n" + saida.err + "\n" + caplog.text
    avisos = [linha for linha in log.splitlines() if "[AVISO]" in linha]
    for nome in ("JWT_SECRET_KEY", "ADMIN_TOKEN_SECRET", "ADMIN_PASSWORD", "PAYMENTS_MOCK", "CORS_ALLOWED_ORIGINS",
                 "MERCADO_PAGO_WEBHOOK_SECRET", "MERCADO_PAGO_ACCESS_TOKEN"):
        assert not any(nome in linha for linha in avisos), f"aviso espurio sobre {nome}: {avisos!r}"


# =========================================================================================
# Grupo D - login legado (POST /api/admin/login)
# =========================================================================================

def _conta_gestao(email="gestao.sg2@teste.com", senha="Senha-Conta-Gestao-9"):
    user_id = Database.add_user(email, "Gestao SG2", get_password_hash(senha), role="admin")
    assert user_id
    return email, senha


@pytest.mark.parametrize("app_env", ["production", "PRODUCTION", "  production "],
                         ids=["minusculo", "maiusculo", "com_espacos"])
def test_d1_producao_login_legado_com_senha_certa_responde_404_sem_token(banco, monkeypatch, app_env):
    c = _app_sem_startup(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    r = c.post("/api/admin/login", json={"password": "admin123"})
    assert r.status_code == 404, r.text
    assert "token" not in r.text.lower().replace("not found", "")
    assert r.json().get("token") is None


def test_d2_producao_login_legado_com_senha_errada_tambem_e_404_sem_efeitos(banco, monkeypatch):
    c = _app_sem_startup(monkeypatch, {"APP_ENV": "production", "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    auditorias = _contagem("audit_logs")
    tentativas = _contagem("login_attempts")
    for _ in range(25):  # mais que o limite de 20 por IP: nunca vira 401 nem 429, porque a rota nao existe
        r = c.post("/api/admin/login", json={"password": "errada-sg2"})
        assert r.status_code == 404, r.text
    assert _contagem("audit_logs") == auditorias, "rota inexistente nao audita"
    assert _contagem("login_attempts") == tentativas, "rota inexistente nao conta tentativa"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_d3_fora_de_producao_login_legado_continua_200_com_a_senha_certa(banco, monkeypatch, app_env):
    c = _app_sem_startup(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "FINANCIAL_PASSWORD": "fin123", "SUPPORT_PASSWORD": "sup123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    r = c.post("/api/admin/login", json={"password": "admin123"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "success" and corpo["role"] == "admin" and corpo["token"]
    assert c.post("/api/admin/login", json={"password": "fin123"}).json()["role"] == "financial"
    assert c.post("/api/admin/login", json={"password": "sup123"}).json()["role"] == "support"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_d4_fora_de_producao_senha_errada_continua_401(banco, monkeypatch, app_env):
    c = _app_sem_startup(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    r = c.post("/api/admin/login", json={"password": "errada-sg2"})
    assert r.status_code == 401, r.text
    assert _contagem("login_attempts") >= 1


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_d5_fora_de_producao_o_limite_por_ip_da_s2_segue_valendo(banco, monkeypatch, app_env):
    c = _app_sem_startup(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    for _ in range(20):
        assert c.post("/api/admin/login", json={"password": "errada-sg2"}).status_code == 401
    r = c.post("/api/admin/login", json={"password": "admin123"})  # bloqueado mesmo com a senha certa
    assert r.status_code == 429, r.text


def test_d6_em_producao_o_login_por_conta_continua_funcionando(banco, monkeypatch):
    """Guarda verde: o caminho real de producao (conta de funcionario + POST /api/token + JWT) nao muda."""
    email, senha = _conta_gestao()
    c = _app_sem_startup(monkeypatch, PRODUCAO_VALIDA)
    r = c.post("/api/token", data={"username": email, "password": senha})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert c.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_d7_em_producao_o_token_do_login_legado_nao_abre_rotas(banco, monkeypatch):
    """OPCIONAL (orquestrador): token de funcionario assinado por create_admin_token nao e aceito em producao
    (`_user_from_staff_token`). Coerente com o 404 do login: em producao esse formato de token nao deve existir."""
    monkeypatch.setenv("ADMIN_TOKEN_SECRET", TOKEN_ADMIN_OK)
    token = create_admin_token(Role.ADMIN)  # emitido antes de ligar o ambiente de producao
    c = _app_sem_startup(monkeypatch, PRODUCAO_VALIDA)
    r = c.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_d8_fora_de_producao_o_token_legado_continua_aceito(banco, monkeypatch, app_env):
    """Guarda verde do d7: fora de producao o token legado abre as rotas como hoje."""
    monkeypatch.setenv("ADMIN_TOKEN_SECRET", "staff-secret-123")
    token = create_admin_token(Role.ADMIN)
    c = _app_sem_startup(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": "admin123",
                                       "ADMIN_TOKEN_SECRET": "staff-secret-123",
                                       "JWT_SECRET_KEY": "jwt-secret-456-long-enough"})
    r = c.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


# =========================================================================================
# Grupo E - get_admin_secret
# =========================================================================================

def _admin_secret_com(monkeypatch, env):
    from core import security

    _aplicar_ambiente(monkeypatch, env)
    return security.get_admin_secret()


@pytest.mark.parametrize("app_env", ["production", "PRODUCTION", " production "],
                         ids=["minusculo", "maiusculo", "com_espacos"])
def test_e1_producao_sem_admin_token_secret_nao_cai_para_admin_password(monkeypatch, app_env):
    senha = "Gestao-Prod-9xKq2w-E1"
    with pytest.raises(Exception) as erro:
        resultado = _admin_secret_com(monkeypatch, {"APP_ENV": app_env, "ADMIN_PASSWORD": senha})
        pytest.fail("get_admin_secret devolveu um valor em producao sem ADMIN_TOKEN_SECRET"
                    + (" (caiu para ADMIN_PASSWORD)" if resultado == senha else ""), pytrace=False)
    assert senha not in str(erro.value) and senha not in repr(getattr(erro.value, "detail", ""))


def test_e2_producao_com_admin_token_secret_vazio_tambem_nao_cai_para_admin_password(monkeypatch):
    senha = "Gestao-Prod-9xKq2w-E2"
    with pytest.raises(Exception):
        resultado = _admin_secret_com(monkeypatch, {"APP_ENV": "production", "ADMIN_PASSWORD": senha,
                                                    "ADMIN_TOKEN_SECRET": ""})
        pytest.fail("get_admin_secret devolveu um valor em producao com ADMIN_TOKEN_SECRET vazio"
                    + (" (caiu para ADMIN_PASSWORD)" if resultado == senha else ""), pytrace=False)


def test_e3_producao_sem_admin_token_secret_nao_assina_token_de_funcionario(monkeypatch):
    _aplicar_ambiente(monkeypatch, {"APP_ENV": "production", "ADMIN_PASSWORD": "Gestao-Prod-9xKq2w-E3"})
    with pytest.raises(Exception):
        create_admin_token(Role.ADMIN)
        pytest.fail("create_admin_token assinou um token em producao usando ADMIN_PASSWORD como chave", pytrace=False)


def test_e4_producao_com_admin_token_secret_usa_o_proprio_segredo(monkeypatch):
    env = {"APP_ENV": "production", "ADMIN_PASSWORD": SENHA_ADMIN, "ADMIN_TOKEN_SECRET": TOKEN_ADMIN_OK}
    assert _admin_secret_com(monkeypatch, env) == TOKEN_ADMIN_OK


@pytest.mark.parametrize("app_env", ["development", "test", "staging", None],
                         ids=["development", "test", "staging", "ausente"])
def test_e5_fora_de_producao_mantem_o_fallback_para_admin_password(monkeypatch, app_env):
    env = {"ADMIN_PASSWORD": "admin123"}
    if app_env is not None:
        env["APP_ENV"] = app_env
    assert _admin_secret_com(monkeypatch, env) == "admin123"


@pytest.mark.parametrize("app_env", ["development", "test", None], ids=["development", "test", "ausente"])
def test_e6_fora_de_producao_o_admin_token_secret_tem_precedencia(monkeypatch, app_env):
    env = {"ADMIN_PASSWORD": "admin123", "ADMIN_TOKEN_SECRET": "staff-secret-123"}
    if app_env is not None:
        env["APP_ENV"] = app_env
    assert _admin_secret_com(monkeypatch, env) == "staff-secret-123"


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_e7_sem_nenhum_dos_dois_segredos_continua_500(monkeypatch, app_env):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        _admin_secret_com(monkeypatch, {"APP_ENV": app_env})
    assert erro.value.status_code == 500


# =========================================================================================
# Grupo F - codigo_validacao (certificado)
# =========================================================================================

# Valores calculados com a funcao ATUAL (fallback "gt" ainda no codigo), antes da mudanca da SG2:
#   JWT_SECRET_KEY = "jwt-secret-456-long-enough" e "K" * 40, para (enrollment_id, user_id).
CHAVE_A = "jwt-secret-456-long-enough"
CHAVE_B = "K" * 40
REFERENCIAS = [
    (CHAVE_A, 1, 1, "33A4213D344D"),
    (CHAVE_A, 2, 1, "449D722AC2F2"),
    (CHAVE_A, 1, 2, "5DBF79F0D9E5"),
    (CHAVE_A, 7, 42, "04F4E43677A9"),
    (CHAVE_A, 123, 9, "64DA1EF67393"),
    (CHAVE_B, 1, 2, "6E4C8A55FADF"),
    (CHAVE_B, 7, 42, "0B5738F3FDEC"),
    (CHAVE_B, 123, 9, "7E35DA798335"),
]


@pytest.mark.parametrize("chave,matricula,usuario,esperado", REFERENCIAS,
                         ids=[f"{c[:3]}-{m}-{u}" for c, m, u, _ in REFERENCIAS])
def test_f1_guarda_com_a_chave_definida_o_codigo_e_identico_ao_de_antes(monkeypatch, chave, matricula, usuario,
                                                                         esperado):
    """Certificados ja emitidos continuam validos: valor fixo de referencia, nao recalculado pelo teste."""
    from core import progresso

    monkeypatch.setenv("JWT_SECRET_KEY", chave)
    assert progresso.codigo_validacao(matricula, usuario) == esperado


def test_f2_guarda_o_codigo_segue_a_formula_publicada_hmac_sha256_de_12_maiusculas(monkeypatch):
    from core import progresso

    monkeypatch.setenv("JWT_SECRET_KEY", CHAVE_B)
    for matricula, usuario in ((3, 5), (10, 10), (99, 1)):
        oraculo = hmac.new(CHAVE_B.encode(), f"certificado:{matricula}:{usuario}".encode(),
                           hashlib.sha256).hexdigest()[:12].upper()
        assert progresso.codigo_validacao(matricula, usuario) == oraculo


def test_f3_sem_jwt_secret_key_levanta_erro_em_vez_de_usar_gt(monkeypatch):
    from core import progresso

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    codigo_do_fallback = hmac.new(b"gt", b"certificado:1:1", hashlib.sha256).hexdigest()[:12].upper()
    with pytest.raises(Exception):
        resultado = progresso.codigo_validacao(1, 1)
        pytest.fail(f"codigo_validacao devolveu {resultado!r} sem JWT_SECRET_KEY"
                    f"{' (o codigo do fallback fixo gt)' if resultado == codigo_do_fallback else ''}", pytrace=False)


def test_f4_com_jwt_secret_key_vazia_tambem_levanta_erro(monkeypatch):
    from core import progresso

    monkeypatch.setenv("JWT_SECRET_KEY", "")
    with pytest.raises(Exception):
        resultado = progresso.codigo_validacao(1, 1)
        pytest.fail(f"codigo_validacao devolveu {resultado!r} com JWT_SECRET_KEY vazia", pytrace=False)


def test_f5_o_erro_sem_chave_nao_traz_valor_de_segredo(monkeypatch):
    from core import progresso

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "Gestao-Prod-9xKq2w-F5")
    with pytest.raises(Exception) as erro:
        resultado = progresso.codigo_validacao(1, 1)
        pytest.fail(f"codigo_validacao devolveu {resultado!r} sem JWT_SECRET_KEY", pytrace=False)
    assert "Gestao-Prod-9xKq2w-F5" not in str(erro.value)


def test_f6_guarda_a_rota_do_certificado_emite_o_mesmo_codigo_de_antes(banco, tmp_path, monkeypatch):
    """Com a chave definida a rota existente do certificado segue funcionando e o PDF traz o codigo da formula atual."""
    import json

    import admin.routes as admin_routes

    pasta = tmp_path / "courses"
    pasta.mkdir()
    url = "https://materiais.test/sg2/aula1.pdf"
    (pasta / "curso_sg2.json").write_text(json.dumps({
        "id": "curso_sg2", "name": "Curso SG2", "price": 100.0, "duration_hours": 8,
        "materials": [{"title": "Aula 1", "url": url, "type": "pdf"}],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", pasta)
    monkeypatch.setenv("JWT_SECRET_KEY", CHAVE_A)

    senha = "senha-sg2-2026-aluno"
    user_id = Database.add_user("aluna.sg2@teste.com", "Aluna Certificada SG2", get_password_hash(senha), role="student")
    conn = sqlite3.connect(Database.DB_PATH)
    matricula = conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_sg2', 'active')",
                             (user_id,)).lastrowid
    conn.commit()
    conn.close()

    from app import app as fastapi_app

    c = TestClient(fastapi_app)
    token = c.post("/api/token", data={"username": "aluna.sg2@teste.com", "password": senha}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert c.post(f"/api/student/enrollments/{matricula}/progress", json={"url": url}, headers=auth).status_code == 200
    r = c.get(f"/api/student/enrollments/{matricula}/certificate.pdf", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    esperado = hmac.new(CHAVE_A.encode(), f"certificado:{matricula}:{user_id}".encode(),
                        hashlib.sha256).hexdigest()[:12].upper()
    assert esperado.encode() in r.content, "o PDF deve trazer o codigo de validacao calculado com a chave do JWT"
