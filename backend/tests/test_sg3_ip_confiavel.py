"""SG3 - IP real atras de proxy confiavel (D109 P4; revisa a D79).

Escritos ANTES da implementacao. Hoje o IP de qualquer limite e `request.client.host` (o par TCP). Atras de nginx,
Caddy ou NAT todo mundo chega com o IP do proxy: 20 falhas de login bloqueiam todos e o limite de 30 mensagens/min do
chat vira global. A SG3 passa a confiar em `X-Forwarded-For` SOMENTE quando o par TCP esta em `TRUSTED_PROXIES`.

Contrato (decidido pelo PM, P4; formas escolhidas pelo agente-testes estao marcadas com [forma]):
  - `TRUSTED_PROXIES`: IPs e CIDRs (IPv4 e IPv6) separados por virgula, lida a CADA requisicao. Vazia ou ausente =
    comportamento de hoje (cabecalho ignorado, vale `request.client.host`).
  - Funcao unica `core.cliente_ip.ip_do_cliente(request) -> Optional[str]` [forma: nome e modulo]; `login_limit.
    ip_do_cliente` e `rate_limit._ip` passam a usa-la. Regra: se o par TCP esta em `TRUSTED_PROXIES`, o IP do cliente
    e o mais a direita de `X-Forwarded-For` que NAO pertence a `TRUSTED_PROXIES` (se todos pertencem, o mais a
    esquerda); se o par TCP nao esta na lista, o cabecalho e ignorado (anti-spoof). Cabecalho ausente, vazio ou com
    item malformado volta ao par TCP. IPv6 sai na forma comprimida, minuscula.
  - Valores invalidos em `TRUSTED_PROXIES` sao ignorados (o resto vale) e nunca derrubam o app.
  - Efeitos: limite de chat por IP (30/min), de checkout (10/min), de checagem do token de senha (30/min) e o bloqueio de
    login por IP (20 falhas/15 min; /api/token e /api/admin/login) usam o IP efetivo; `login_attempts` e o evento
    `auth.locked` gravam o IP efetivo.

Escolhas de forma do teste (conservadoras; ver relatorio):
  [forma] item malformado = qualquer item que `ipaddress.ip_address` nao aceite depois de aparado: vazio, texto,
          `unknown`, IP com porta (`1.2.3.4:443`), IPv6 entre colchetes (`[2001:db8::1]`, com ou sem porta).
  [decisao do orquestrador, contrato da SG3] leitura da DIREITA para a ESQUERDA: pula os itens que pertencem a
          `TRUSTED_PROXIES`; o primeiro item que NAO e proxy e o cliente; se ele for malformado, vale o par TCP; tudo
          a ESQUERDA dele e ignorado (controlado pelo atacante), inclusive itens malformados. Se todos os itens sao
          proxies, vale o mais a esquerda.
  [forma] apenas `X-Forwarded-For` conta; `X-Real-IP` e `Forwarded` sao ignorados.
  [forma] par TCP que nao e IP (ex.: "testclient") ou ausente nunca e proxy confiavel: devolve o par como esta
          (None se nao houver par), como hoje.
  [forma] entrada de `TRUSTED_PROXIES` invalida (texto, octeto > 255, mascara fora do intervalo, porta, separador que
          nao seja virgula) e ignorada; se nenhuma sobra, o cabecalho e ignorado.

Grupos
  A  guarda verde: sem `TRUSTED_PROXIES` (ausente, vazia ou so com lixo), XFF forjado nao muda a chave
  B  vermelho: par TCP na lista, clientes distintos atras do mesmo proxy tem contadores separados (chat, login,
     login legado, checkout da landing, checkout do aluno, checagem do token de senha); CIDR; IPv6; cadeia
  C  guarda verde: par TCP fora da lista, com `TRUSTED_PROXIES` preenchida, tem o cabecalho ignorado
  D  unitarios de `ip_do_cliente` com requisicoes falsas (ASGI scope, sem rede): cadeias, malformado, IPv6, CIDR,
     entradas invalidas, leitura a cada requisicao, consistencia com `login_attempts`/`login_limit`
  G  gravacao: `login_attempts` e `auth.locked` com o IP efetivo (e sem o IP do proxy)
  R  o app nao cai com `TRUSTED_PROXIES` invalida; producao nao recusa a subida por causa dela

Convencoes: o par TCP e simulado com `TestClient(app, client=(host, porta))`, sem `with` (sem startup: nao carrega o
agente do chat nem toca o Groq); o agente do chat e removido do app (`manager_agent = None`, cuidado da SG1), o Groq e o
Mercado Pago sao dubles que contam chamadas, e cada teste termina provando 0 chamadas externas. O chat responde 200
("Manager agent not initialized") dentro do limite e 429 acima; so o limite de taxa interessa. Os checkouts usam um
curso inexistente: o limite e consumido antes de qualquer outra coisa e nada e criado. Banco temporario do conftest.
`from core.cliente_ip import ...` fica DENTRO de cada teste unitario (falha como FAILED, nao como erro de coleta).
Os enderecos de documentacao (RFC 5737/3849) fazem o papel dos clientes.
"""

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from agents.groq_client import GroqChatClient
from core.security import create_access_token, get_password_hash
from db import Database

PROXY = "10.77.0.1"
PROXY2 = "10.77.0.2"
FORA = "10.99.0.9"  # par TCP que NAO esta em TRUSTED_PROXIES
CLI_A = "198.51.100.1"
CLI_B = "198.51.100.2"
CLI_C = "198.51.100.3"

ROTA_CHAT = "/api/chat"
ROTA_LOGIN = "/api/token"
ROTA_LEGADO = "/api/admin/login"
ROTA_LANDING = "/api/payments/create-checkout"
ROTA_ALUNO = "/api/student/checkout"
ROTA_TOKEN_SENHA = "/api/auth/password-token/check"
CURSO_INEXISTENTE = "curso-inexistente-sg3"
SENHA = "senha-certa-sg3-2026"
SENHA_ERRADA = "senha-errada-sg3"
SENHA_LEGADO = "admin123"  # ADMIN_PASSWORD do conftest
ERRO_LOGIN = "Muitas tentativas. Tente novamente em alguns minutos."
ERRO_CHAT = "Muitas mensagens em pouco tempo. Aguarde um instante."
ERRO_CHECKOUT = "Muitas tentativas de compra em pouco tempo. Aguarde um instante."


# =========================================================================================
# Fixtures
# =========================================================================================

class Externos:
    """Conta chamadas que NUNCA podem acontecer nesta suite: LLM (Groq) e gateway de pagamento."""

    def __init__(self):
        self.llm = 0
        self.gateway = 0


@pytest.fixture(autouse=True)
def ambiente_sg3(monkeypatch, tmp_path):
    """Hermetico: sem TRUSTED_PROXIES herdada do shell ou do backend/.env; pagamento simulado desligado; dubles
    de LLM e gateway; nenhuma chamada externa escapa."""
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-sg3")
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    externos = Externos()

    def llm_falso(self, messages, max_tokens=1024, temperature=0.7):
        externos.llm += 1
        return "GENERAL"

    def gateway_falso(*args, **kwargs):
        externos.gateway += 1
        raise AssertionError("o gateway de pagamento nao pode ser chamado na SG3")

    monkeypatch.setattr(GroqChatClient, "create_chat_completion", llm_falso)
    monkeypatch.setattr("payments.routes.requests.post", gateway_falso)
    monkeypatch.setattr("payments.routes.requests.get", gateway_falso)
    yield externos
    assert externos.llm == 0, "o LLM foi chamado (as mensagens deviam parar no limite ou no agente ausente)"
    assert externos.gateway == 0, "o gateway de pagamento foi chamado"


@pytest.fixture
def app_sg3(banco, monkeypatch):
    """App compartilhado, sem startup e SEM agente de chat (outra suite pode ter deixado um carregado: SG1)."""
    from app import app as fastapi_app

    monkeypatch.setattr(fastapi_app.state, "manager_agent", None, raising=False)
    return fastapi_app


def _cliente(app, host, porta=50000):
    """Cliente cujo par TCP e (host, porta). Sem `with`: nao dispara startup e compartilha o estado do app."""
    return TestClient(app, client=(host, porta), raise_server_exceptions=False)


def _proxies(monkeypatch, valor):
    monkeypatch.setenv("TRUSTED_PROXIES", valor)


# =========================================================================================
# Helpers HTTP
# =========================================================================================

def _resumo(r):
    try:
        corpo = r.json()
    except Exception:
        corpo = r.text
    return r.status_code, corpo


def _xff(valor):
    return {"X-Forwarded-For": valor} if valor is not None else {}


def _texto(r):
    corpo = r.json()
    if isinstance(corpo.get("detail"), str):
        return corpo["detail"]
    return corpo.get("message")


def _chat(c, xff=None, texto="oi"):
    return c.post(ROTA_CHAT, json={"message": texto}, headers=_xff(xff))


def _chat_n(c, n, xff, ctx=""):
    """`n` mensagens, todas dentro do limite (nunca 429). `xff` pode ser texto ou funcao do indice."""
    for i in range(n):
        valor = xff(i) if callable(xff) else xff
        r = _chat(c, valor)
        assert r.status_code == 200, f"{ctx} mensagem {i + 1}: esperado 200, veio {_resumo(r)}"


def _assert_chat_429(r, ctx=""):
    assert r.status_code == 429, f"{ctx}: esperado 429 (limite), veio {_resumo(r)}"
    assert _texto(r) == ERRO_CHAT, r.json()


def _assert_chat_livre(r, ctx=""):
    assert r.status_code == 200, f"{ctx}: esperado 200 (livre), veio {_resumo(r)}"


def _login(c, email, senha, xff=None):
    return c.post(ROTA_LOGIN, data={"username": email, "password": senha}, headers=_xff(xff))


def _falhas_de_login(c, xff, prefixo, n=20):
    """`n` logins com senha errada de e-mails distintos (o limite por e-mail nao entra); cada um tem de ser a falha
    comum (400), nunca o bloqueio. `xff` pode ser texto ou funcao do indice."""
    for i in range(n):
        valor = xff(i) if callable(xff) else xff
        r = _login(c, f"{prefixo}{i}@sg3.test", SENHA_ERRADA, valor)
        assert r.status_code == 400, f"{prefixo} falha {i + 1}: esperado 400, veio {_resumo(r)}"


def _assert_login_429(r, ctx=""):
    assert r.status_code == 429, f"{ctx}: esperado 429 (bloqueado), veio {_resumo(r)}"
    assert r.json().get("detail") == ERRO_LOGIN, r.json()
    assert "access_token" not in r.text


def _assert_login_ok(r, ctx=""):
    assert r.status_code == 200, f"{ctx}: esperado 200, veio {_resumo(r)}"
    assert r.json().get("access_token")


def _conta(email, nome="Aluno SG3", senha=SENHA):
    user_id = Database.add_user(email, nome, get_password_hash(senha), role="student")
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": "student"})
    return SimpleNamespace(id=user_id, email=email, token=token)


def _landing(c, i, xff=None):
    corpo = {"course_id": CURSO_INEXISTENTE, "payer": {"name": "Comprador SG3", "email": f"c{i}.sg3@sg3.test"}}
    return c.post(ROTA_LANDING, json=corpo, headers=_xff(xff))


def _aluno_compra(c, token, xff=None):
    headers = {"Authorization": f"Bearer {token}", **_xff(xff)}
    return c.post(ROTA_ALUNO, json={"course_id": CURSO_INEXISTENTE}, headers=headers)


def _checar_token(c, xff=None, token="token-que-nao-existe"):
    return c.post(ROTA_TOKEN_SENHA, json={"token": token}, headers=_xff(xff))


def _sql(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _chaves_de_ip():
    return [linha["key"] for linha in _sql("SELECT key FROM login_attempts WHERE scope = 'ip'")]


# =========================================================================================
# A - guarda verde: sem TRUSTED_PROXIES o cabecalho forjado nao muda a chave (D79 intacta)
# =========================================================================================

def test_a1_sem_trusted_proxies_xff_forjado_nao_escapa_do_limite_do_chat(app_sg3):
    c = _cliente(app_sg3, PROXY)
    _chat_n(c, 30, lambda i: f"203.0.113.{i + 1}", "A1")
    _assert_chat_429(_chat(c, "203.0.113.200"), "A1 31a com outro IP forjado")


def test_a2_sem_trusted_proxies_xff_forjado_nao_escapa_do_bloqueio_de_login(app_sg3):
    c = _cliente(app_sg3, PROXY)
    conta = _conta("ana.a2@sg3.test")
    _falhas_de_login(c, lambda i: f"203.0.113.{i + 1}", "falha-a2-")
    _assert_login_429(_login(c, conta.email, SENHA, "203.0.113.200"), "A2 a 21a com outro IP forjado")


def test_a3_sem_trusted_proxies_xff_forjado_nao_escapa_do_limite_de_checkout(app_sg3):
    c = _cliente(app_sg3, PROXY)
    for i in range(10):
        r = _landing(c, i, f"203.0.113.{i + 1}")
        assert r.status_code != 429, f"A3 tentativa {i + 1} nao pode ser barrada: {_resumo(r)}"
    r = _landing(c, 10, "203.0.113.200")
    assert r.status_code == 429 and _texto(r) == ERRO_CHECKOUT, f"A3 11a: {_resumo(r)}"


def test_a4_sem_trusted_proxies_xff_forjado_nao_escapa_do_limite_da_checagem_de_token(app_sg3):
    c = _cliente(app_sg3, PROXY)
    for i in range(30):
        r = _checar_token(c, f"203.0.113.{i + 1}")
        assert r.status_code == 200, f"A4 checagem {i + 1}: {_resumo(r)}"
    r = _checar_token(c, "203.0.113.200")
    assert r.status_code == 429, f"A4 31a: esperado 429, veio {_resumo(r)}"


def test_a5_sem_trusted_proxies_xff_nao_faz_um_cliente_carregar_o_limite_de_outro(app_sg3):
    """Quem declara o IP de outro nao consome o limite dele: o contador e o do par TCP de quem fala."""
    atacante = _cliente(app_sg3, "198.51.100.50")
    _chat_n(atacante, 30, "203.0.113.77", "A5 atacante")
    _assert_chat_429(_chat(atacante, "203.0.113.77"), "A5 atacante 31a")
    vitima = _cliente(app_sg3, "203.0.113.77")
    _assert_chat_livre(_chat(vitima), "A5 vitima (par TCP 203.0.113.77, sem cabecalho)")


@pytest.mark.parametrize("valor", ["", "   ", ",", " , ,"], ids=["vazia", "espacos", "virgula", "virgulas"])
def test_a6_trusted_proxies_vazia_equivale_a_ausente(app_sg3, monkeypatch, valor):
    _proxies(monkeypatch, valor)
    c = _cliente(app_sg3, PROXY)
    _chat_n(c, 30, lambda i: f"203.0.113.{i + 1}", "A6")
    _assert_chat_429(_chat(c, "203.0.113.200"), "A6 31a")


@pytest.mark.parametrize("valor", ["lixo", "999.1.1.1", "10.0.0.0/99", "10.77.0.1:8080", "10.77.0.1;10.77.0.2"],
                         ids=["texto", "octeto", "mascara", "porta", "separador-errado"])
def test_a7_trusted_proxies_so_com_valor_invalido_nao_confia_em_ninguem(app_sg3, monkeypatch, valor):
    _proxies(monkeypatch, valor)
    c = _cliente(app_sg3, PROXY)
    _chat_n(c, 30, lambda i: f"203.0.113.{i + 1}", "A7")
    _assert_chat_429(_chat(c, "203.0.113.200"), "A7 31a: entrada invalida nao pode virar 'confie em todos'")


# =========================================================================================
# B - vermelho: par TCP na lista, clientes distintos atras do mesmo proxy
# =========================================================================================

def test_b1_chat_o_31o_de_um_cliente_nao_bloqueia_outro_atras_do_mesmo_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _chat_n(proxy, 30, CLI_A, "B1 cliente A")
    _assert_chat_429(_chat(proxy, CLI_A), "B1 31a do cliente A")
    _assert_chat_livre(_chat(proxy, CLI_B), "B1 primeira do cliente B (outro IP real atras do mesmo proxy)")
    _chat_n(proxy, 29, CLI_B, "B1 cliente B (restante)")
    _assert_chat_429(_chat(proxy, CLI_B), "B1 31a do cliente B (contador proprio)")


def test_b2_login_bloqueio_por_ip_de_um_cliente_nao_bloqueia_outro_atras_do_mesmo_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    conta_a, conta_b = _conta("ana.b2@sg3.test"), _conta("bia.b2@sg3.test")
    _falhas_de_login(proxy, CLI_A, "falha-b2-")
    _assert_login_429(_login(proxy, conta_a.email, SENHA, CLI_A), "B2 cliente A bloqueado, mesmo com a senha certa")
    _assert_login_ok(_login(proxy, conta_b.email, SENHA, CLI_B), "B2 cliente B (outro IP real) entra")


def test_b3_login_legado_bloqueio_por_ip_de_um_cliente_nao_bloqueia_outro(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    for i in range(20):
        r = proxy.post(ROTA_LEGADO, json={"password": f"errada-{i}"}, headers=_xff(CLI_A))
        assert r.status_code == 401, f"B3 falha {i + 1}: {_resumo(r)}"
    r = proxy.post(ROTA_LEGADO, json={"password": SENHA_LEGADO}, headers=_xff(CLI_A))
    assert r.status_code == 429 and r.json().get("detail") == ERRO_LOGIN, f"B3 cliente A: {_resumo(r)}"
    r = proxy.post(ROTA_LEGADO, json={"password": SENHA_LEGADO}, headers=_xff(CLI_B))
    assert r.status_code == 200, f"B3 cliente B (outro IP real): esperado 200, veio {_resumo(r)}"
    assert r.json().get("token")


def test_b4_checkout_da_landing_limite_por_cliente_atras_do_mesmo_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    for i in range(10):
        r = _landing(proxy, i, CLI_A)
        assert r.status_code != 429, f"B4 cliente A tentativa {i + 1}: {_resumo(r)}"
    r = _landing(proxy, 10, CLI_A)
    assert r.status_code == 429 and _texto(r) == ERRO_CHECKOUT, f"B4 cliente A 11a: {_resumo(r)}"
    r = _landing(proxy, 11, CLI_B)
    assert r.status_code != 429, f"B4 cliente B (outro IP real) nao pode ser barrado: {_resumo(r)}"


def test_b5_checkout_do_aluno_limite_por_ip_efetivo_atras_do_mesmo_proxy(app_sg3, monkeypatch):
    """O limite do aluno logado e por IP E por aluno: dois alunos em IPs reais distintos atras do mesmo proxy."""
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    ana, bia = _conta("ana.b5@sg3.test"), _conta("bia.b5@sg3.test")
    for i in range(10):
        r = _aluno_compra(proxy, ana.token, CLI_A)
        assert r.status_code != 429, f"B5 aluna ana tentativa {i + 1}: {_resumo(r)}"
    r = _aluno_compra(proxy, ana.token, CLI_A)
    assert r.status_code == 429 and _texto(r) == ERRO_CHECKOUT, f"B5 ana 11a: {_resumo(r)}"
    r = _aluno_compra(proxy, bia.token, CLI_B)
    assert r.status_code != 429, f"B5 bia (outro IP real, outro aluno) nao pode ser barrada: {_resumo(r)}"


def test_b6_checagem_do_token_de_senha_limite_por_cliente_atras_do_mesmo_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    for i in range(30):
        r = _checar_token(proxy, CLI_A)
        assert r.status_code == 200, f"B6 cliente A checagem {i + 1}: {_resumo(r)}"
    assert _checar_token(proxy, CLI_A).status_code == 429, "B6 cliente A 31a"
    r = _checar_token(proxy, CLI_B)
    assert r.status_code == 200 and r.json() == {"valid": False}, f"B6 cliente B (outro IP real): {_resumo(r)}"


def test_b7_a_chave_e_o_cliente_e_nao_o_proxy_por_onde_ele_passou(app_sg3, monkeypatch):
    """O mesmo cliente por dois proxies confiaveis diferentes divide UM contador."""
    _proxies(monkeypatch, f"{PROXY}, {PROXY2}")
    _chat_n(_cliente(app_sg3, PROXY), 30, CLI_A, "B7 via proxy 1")
    _assert_chat_429(_chat(_cliente(app_sg3, PROXY2), CLI_A), "B7 31a do cliente A, agora pelo proxy 2")


def test_b8_cabecalho_forjado_a_esquerda_nao_troca_o_cliente_atras_de_proxy_confiavel(app_sg3, monkeypatch):
    """O proxy (nginx) acrescenta o IP que viu a direita: `forjado, real`. Vale o `real`; o forjado nao escapa do
    limite nem faz um cliente carregar o contador de outro."""
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _chat_n(proxy, 30, lambda i: f"203.0.113.{i + 1}, {CLI_A}", "B8 cliente A com prefixo forjado variavel")
    _assert_chat_429(_chat(proxy, f"203.0.113.250, {CLI_A}"), "B8 31a do cliente A (outro prefixo forjado)")
    # o cliente B declara o IP do A no prefixo: nao herda o contador dele
    _assert_chat_livre(_chat(proxy, f"{CLI_A}, {CLI_B}"), "B8 cliente B declarando o IP do A")


def test_b9_cidr_ipv4_confia_em_qualquer_par_do_bloco(app_sg3, monkeypatch):
    _proxies(monkeypatch, "10.77.0.0/24")
    _chat_n(_cliente(app_sg3, "10.77.0.5"), 30, CLI_A, "B9 via 10.77.0.5")
    _assert_chat_429(_chat(_cliente(app_sg3, "10.77.0.200"), CLI_A), "B9 31a do cliente A, por outro proxy do bloco")
    _assert_chat_livre(_chat(_cliente(app_sg3, "10.77.0.200"), CLI_B), "B9 cliente B por proxy do bloco")


def test_b10_cidr_ipv4_par_fora_do_bloco_tem_o_cabecalho_ignorado(app_sg3, monkeypatch):
    _proxies(monkeypatch, "10.77.0.0/24")
    c = _cliente(app_sg3, "10.77.1.5")  # fora do /24
    _chat_n(c, 30, lambda i: f"203.0.113.{i + 1}", "B10")
    _assert_chat_429(_chat(c, "203.0.113.200"), "B10 31a (par fora do bloco: cabecalho ignorado)")


def test_b11_ipv6_normalizado_e_cidr_ipv6(app_sg3, monkeypatch):
    """Par IPv6 dentro de um /48 confiavel; o mesmo cliente IPv6 escrito de formas diferentes e UM contador."""
    _proxies(monkeypatch, "2001:db8:ffff::/48")
    proxy = _cliente(app_sg3, "2001:db8:ffff::1")
    _chat_n(proxy, 15, "2001:DB8::1", "B11 forma maiuscula")
    _chat_n(proxy, 15, "2001:db8:0:0:0:0:0:1", "B11 forma expandida")
    _assert_chat_429(_chat(proxy, "2001:db8::1"), "B11 31a (as tres escritas sao o mesmo cliente)")
    _assert_chat_livre(_chat(proxy, "2001:db8::2"), "B11 outro cliente IPv6")


def test_b12_proxy_ipv6_na_lista_com_cliente_ipv4(app_sg3, monkeypatch):
    _proxies(monkeypatch, "2001:0DB8:FFFF:0:0:0:0:1")  # forma expandida e maiuscula do proxy
    proxy = _cliente(app_sg3, "2001:db8:ffff::1")
    _chat_n(proxy, 30, CLI_A, "B12")
    _assert_chat_429(_chat(proxy, CLI_A), "B12 31a do cliente A")
    _assert_chat_livre(_chat(proxy, CLI_B), "B12 cliente B")


def test_b13_cadeia_com_dois_proxies_confiaveis_usa_o_cliente_real(app_sg3, monkeypatch):
    _proxies(monkeypatch, f"{PROXY}, {PROXY2}")
    proxy = _cliente(app_sg3, PROXY)
    cadeia_a, cadeia_b = f"{CLI_A}, {PROXY2}", f"{CLI_B}, {PROXY2}"
    _chat_n(proxy, 30, cadeia_a, "B13 cliente A")
    _assert_chat_429(_chat(proxy, cadeia_a), "B13 31a do cliente A")
    _assert_chat_livre(_chat(proxy, cadeia_b), "B13 cliente B")


def test_b14_cabecalho_ausente_ou_malformado_atras_de_proxy_confiavel_cai_no_par_tcp(app_sg3, monkeypatch):
    """Sem IP utilizavel, a chave volta a ser o proxy (comportamento de hoje): nao abre brecha de bypass."""
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _chat_n(proxy, 10, None, "B14 sem cabecalho")
    _chat_n(proxy, 10, "lixo", "B14 malformado")
    _chat_n(proxy, 10, f"{CLI_A}:443", "B14 com porta")
    _assert_chat_429(_chat(proxy, None), "B14 31a (tres formas, uma so chave: o par TCP)")
    _assert_chat_429(_chat(proxy, "outro-lixo"), "B14 31a malformado")


def test_b15_lixo_a_esquerda_nao_joga_o_cliente_no_balde_do_proxy(app_sg3, monkeypatch):
    """O atacante que manda `lixo` no XFF nao pode encher o contador do proxy (que seria de todos): o proxy anexa o
    IP real a direita e so ele conta."""
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _chat_n(proxy, 30, lambda i: f"lixo-{i}, {CLI_A}", "B15 cliente A com lixo a esquerda")
    _assert_chat_429(_chat(proxy, f"lixo, {CLI_A}"), "B15 31a do cliente A")
    _assert_chat_livre(_chat(proxy, None), "B15 o balde do proprio proxy (sem cabecalho) esta livre")
    _assert_chat_livre(_chat(proxy, f"lixo, {CLI_B}"), "B15 cliente B")


# =========================================================================================
# C - guarda verde: par TCP fora da lista tem o cabecalho ignorado, mesmo com TRUSTED_PROXIES preenchida
# =========================================================================================

def test_c1_par_fora_da_lista_nao_escapa_do_limite_do_chat_com_xff_forjado(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    c = _cliente(app_sg3, FORA)
    _chat_n(c, 30, lambda i: f"203.0.113.{i + 1}", "C1")
    _assert_chat_429(_chat(c, "203.0.113.200"), "C1 31a")


def test_c2_par_fora_da_lista_nao_escapa_do_bloqueio_de_login_com_xff_forjado(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    c = _cliente(app_sg3, FORA)
    conta = _conta("ana.c2@sg3.test")
    _falhas_de_login(c, lambda i: f"203.0.113.{i + 1}", "falha-c2-")
    _assert_login_429(_login(c, conta.email, SENHA, "203.0.113.200"), "C2 a 21a")


def test_c3_par_fora_da_lista_nao_se_passa_por_outro_cliente_nem_pelo_proprio_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    atacante = _cliente(app_sg3, FORA)
    _chat_n(atacante, 30, CLI_A, "C3 atacante declarando o IP de A")
    _assert_chat_429(_chat(atacante, PROXY), "C3 atacante declarando o IP do proxy")
    _assert_chat_livre(_chat(_cliente(app_sg3, CLI_A)), "C3 cliente A de verdade (par TCP 198.51.100.1)")
    _assert_chat_livre(_chat(_cliente(app_sg3, PROXY)), "C3 o proxy de verdade nao herdou o contador do atacante")


# =========================================================================================
# D - unitarios de ip_do_cliente (requisicao ASGI falsa, sem rede)
# =========================================================================================

def _req(peer, xff=None, extras=()):
    """Request do Starlette montada direto do escopo ASGI. `peer=None` = sem par TCP."""
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    headers.extend((nome.lower().encode(), valor.encode()) for nome, valor in extras)
    scope = {"type": "http", "method": "POST", "path": "/", "query_string": b"", "headers": headers,
             "client": (peer, 40000) if peer is not None else None}
    return Request(scope)


def _efetivo(peer, xff=None, extras=()):
    from core.cliente_ip import ip_do_cliente

    return ip_do_cliente(_req(peer, xff, extras))


def test_d1_sem_trusted_proxies_vale_o_par_tcp_e_o_cabecalho_e_ignorado():
    assert _efetivo(PROXY, CLI_A) == PROXY
    assert _efetivo(PROXY, f"{CLI_A}, {PROXY}") == PROXY
    assert _efetivo(PROXY) == PROXY
    assert _efetivo("2001:db8::7", "203.0.113.9") == "2001:db8::7"


def test_d2_trusted_proxies_vazia_ou_so_espacos_e_como_ausente(monkeypatch):
    for valor in ("", "   ", ",", " , , "):
        monkeypatch.setenv("TRUSTED_PROXIES", valor)
        assert _efetivo(PROXY, CLI_A) == PROXY, f"TRUSTED_PROXIES={valor!r}"


def test_d3_par_confiavel_com_um_ip_no_cabecalho_usa_esse_ip(monkeypatch):
    _proxies(monkeypatch, PROXY)
    assert _efetivo(PROXY, CLI_A) == CLI_A


CADEIAS = [
    pytest.param("198.51.100.7", "198.51.100.7", id="um-item"),
    pytest.param("203.0.113.5, 198.51.100.7", "198.51.100.7", id="forjado-a-esquerda-real-a-direita"),
    pytest.param("203.0.113.5, 198.51.100.7, 10.77.0.1", "198.51.100.7", id="a-b-proxy-usa-b"),
    pytest.param("203.0.113.5, 198.51.100.7, 10.77.0.2, 10.77.0.1", "198.51.100.7", id="a-b-proxy2-proxy1-usa-b"),
    pytest.param("203.0.113.5, 10.77.0.2, 198.51.100.7, 10.77.0.1", "198.51.100.7", id="proxy-no-meio-vale-o-mais-a-direita"),
    pytest.param("198.51.100.7, 10.77.0.2, 203.0.113.5", "203.0.113.5", id="usa-o-ultimo-nao-proxy"),
    pytest.param("10.77.0.2, 10.77.0.1", "10.77.0.2", id="so-proxies-usa-o-mais-a-esquerda"),
    pytest.param("10.77.0.1", "10.77.0.1", id="so-um-proxy"),
    pytest.param("10.77.0.1,10.77.0.2", "10.77.0.1", id="so-proxies-sem-espacos"),
    pytest.param("  198.51.100.7  ,  10.77.0.1  ", "198.51.100.7", id="espacos-aparados"),
    pytest.param("198.51.100.7,10.77.0.1", "198.51.100.7", id="sem-espacos"),
]


@pytest.mark.parametrize("cabecalho,esperado", CADEIAS)
def test_d4_cadeia_de_x_forwarded_for_o_mais_a_direita_que_nao_e_proxy(monkeypatch, cabecalho, esperado):
    _proxies(monkeypatch, f"{PROXY}, {PROXY2}")
    assert _efetivo(PROXY, cabecalho) == esperado


def test_d5_cadeia_a_b_proxy_com_um_unico_proxy_na_lista_usa_b(monkeypatch):
    _proxies(monkeypatch, PROXY)
    assert _efetivo(PROXY, f"203.0.113.5, {CLI_B}, {PROXY}") == CLI_B


def test_d6_par_fora_da_lista_ignora_o_cabecalho_mesmo_com_a_lista_preenchida(monkeypatch):
    _proxies(monkeypatch, f"{PROXY}, 10.88.0.0/16")
    assert _efetivo(FORA, CLI_A) == FORA
    assert _efetivo(FORA, f"{CLI_A}, {PROXY}") == FORA
    assert _efetivo("10.89.0.1", CLI_A) == "10.89.0.1"  # perto do /16, mas fora dele
    assert _efetivo(CLI_B, PROXY) == CLI_B  # declarar o IP do proxy no cabecalho nao faz dele um proxy


MALFORMADOS = [
    pytest.param("", id="vazio"),
    pytest.param("   ", id="so-espacos"),
    pytest.param(",", id="so-virgula"),
    pytest.param("lixo", id="texto"),
    pytest.param("unknown", id="unknown"),
    pytest.param("999.1.1.1", id="octeto-maior-que-255"),
    pytest.param("198.51.100", id="ipv4-incompleto"),
    pytest.param("198.51.100.1:443", id="ipv4-com-porta"),
    pytest.param("[2001:db8::1]", id="ipv6-entre-colchetes"),
    pytest.param("[2001:db8::1]:443", id="ipv6-colchetes-e-porta"),
    pytest.param("2001:db8::1::2", id="ipv6-invalido"),
    pytest.param("198.51.100.1, lixo", id="item-malformado-a-direita"),
    pytest.param("198.51.100.1, , 10.77.0.1", id="item-vazio-no-meio"),
    pytest.param("198.51.100.1, 10.77.0.1, lixo", id="malformado-depois-do-proxy"),
]


@pytest.mark.parametrize("cabecalho", MALFORMADOS)
def test_d7_cabecalho_malformado_ou_vazio_volta_ao_par_tcp(monkeypatch, cabecalho):
    _proxies(monkeypatch, PROXY)
    assert _efetivo(PROXY, cabecalho) == PROXY


ESQUERDA_MALFORMADA = [
    pytest.param("lixo, 198.51.100.1", "198.51.100.1", id="lixo-a-esquerda-real-a-direita"),
    pytest.param("198.51.100.1, lixo", PROXY, id="lixo-a-direita-vale-o-par-tcp"),
    pytest.param("1.1.1.1, lixo, 198.51.100.1", "198.51.100.1", id="forjado-e-lixo-a-esquerda"),
    pytest.param("lixo, 10.77.0.2, 10.77.0.1", PROXY, id="lixo-a-esquerda-de-cadeia-so-de-proxies"),
    pytest.param(", 198.51.100.1", "198.51.100.1", id="item-vazio-a-esquerda"),
    pytest.param("1.1.1.1:443, [2001:db8::1], 198.51.100.1, 10.77.0.1", "198.51.100.1", id="porta-e-colchetes-a-esquerda"),
    pytest.param("lixo, 198.51.100.1, 10.77.0.2, 10.77.0.1", "198.51.100.1", id="lixo-a-esquerda-com-dois-proxies"),
    pytest.param("198.51.100.1, 10.77.0.2, lixo", PROXY, id="lixo-entre-o-proxy-e-a-direita"),
]


@pytest.mark.parametrize("cabecalho,esperado", ESQUERDA_MALFORMADA)
def test_d7b_item_malformado_a_esquerda_do_primeiro_nao_proxy_e_ignorado(monkeypatch, cabecalho, esperado):
    """Decisao do orquestrador: so importa o primeiro item que nao e proxy, lendo da direita para a esquerda."""
    _proxies(monkeypatch, f"{PROXY}, {PROXY2}")
    assert _efetivo(PROXY, cabecalho) == esperado


def test_d8_cabecalho_ausente_volta_ao_par_tcp(monkeypatch):
    _proxies(monkeypatch, PROXY)
    assert _efetivo(PROXY, None) == PROXY


def test_d9_so_x_forwarded_for_conta_x_real_ip_e_forwarded_sao_ignorados(monkeypatch):
    _proxies(monkeypatch, PROXY)
    extras = (("X-Real-IP", CLI_A), ("Forwarded", f"for={CLI_A}"), ("X-Client-IP", CLI_A), ("True-Client-IP", CLI_A))
    assert _efetivo(PROXY, None, extras) == PROXY
    assert _efetivo(PROXY, CLI_B, extras) == CLI_B


def test_d10_ipv6_normalizado_comprimido_e_minusculo(monkeypatch):
    _proxies(monkeypatch, "2001:db8:ffff::/48")
    peer = "2001:db8:ffff::1"
    assert _efetivo(peer, "2001:DB8::ABCD") == "2001:db8::abcd"
    assert _efetivo(peer, "2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"
    assert _efetivo(peer, "2001:db8::1, 2001:db8:ffff::5") == "2001:db8::1"  # o proxy do /48 e pulado
    assert _efetivo(peer, "198.51.100.7") == "198.51.100.7"  # cliente IPv4 atras de proxy IPv6
    assert _efetivo(peer, "::1") == "::1"
    assert _efetivo(peer, "2001:db8:ffff::5, 2001:db8:ffff::6") == "2001:db8:ffff::5"  # todos proxies: o mais a esquerda


def test_d11_ipv6_na_lista_e_no_par_casam_em_qualquer_grafia(monkeypatch):
    _proxies(monkeypatch, "2001:0DB8:FFFF:0:0:0:0:1")
    assert _efetivo("2001:db8:ffff::1", CLI_A) == CLI_A
    assert _efetivo("2001:DB8:FFFF:0:0:0:0:1", CLI_A) == CLI_A
    assert _efetivo("2001:db8:ffff::2", CLI_A) == "2001:db8:ffff::2"  # vizinho: fora da lista, cabecalho ignorado
    _proxies(monkeypatch, "2001:db8:ffff::1")
    assert _efetivo("2001:0db8:ffff:0000:0000:0000:0000:0001", CLI_A) == CLI_A


def test_d12_cidr_ipv4_limites_do_bloco(monkeypatch):
    _proxies(monkeypatch, "10.77.0.0/24")
    assert _efetivo("10.77.0.0", CLI_A) == CLI_A
    assert _efetivo("10.77.0.255", CLI_A) == CLI_A
    assert _efetivo("10.77.1.0", CLI_A) == "10.77.1.0"
    assert _efetivo("10.76.255.255", CLI_A) == "10.76.255.255"
    assert _efetivo("10.77.0.5", f"{CLI_A}, 10.77.0.9") == CLI_A  # proxy do mesmo bloco no fim da cadeia e pulado


def test_d13_ipv4_sem_mascara_e_um_host_e_barra_32_tambem(monkeypatch):
    _proxies(monkeypatch, "10.77.0.9, 10.78.0.9/32")
    assert _efetivo("10.77.0.9", CLI_A) == CLI_A
    assert _efetivo("10.77.0.10", CLI_A) == "10.77.0.10"
    assert _efetivo("10.78.0.9", CLI_A) == CLI_A
    assert _efetivo("10.78.0.8", CLI_A) == "10.78.0.8"


def test_d14_cidr_ipv6_e_familias_misturadas_na_lista(monkeypatch):
    _proxies(monkeypatch, "10.77.0.0/24, 2001:db8:ffff::/48")
    assert _efetivo("2001:db8:ffff:1::1", CLI_A) == CLI_A
    assert _efetivo("2001:db8:fffe::1", CLI_A) == "2001:db8:fffe::1"
    assert _efetivo("10.77.0.3", CLI_A) == CLI_A
    _proxies(monkeypatch, "10.77.0.0/24")  # familia diferente da do par: nao casa e nao quebra
    assert _efetivo("2001:db8:ffff::1", CLI_A) == "2001:db8:ffff::1"
    _proxies(monkeypatch, "2001:db8:ffff::/48")
    assert _efetivo("10.77.0.3", CLI_A) == "10.77.0.3"


def test_d15_entrada_invalida_e_ignorada_e_o_resto_vale(monkeypatch):
    _proxies(monkeypatch, f"lixo, {PROXY}, 999.1.1.1, 10.0.0.0/99, , 2001:db8::/200, 10.77.0.1/abc, {PROXY2}:8080")
    assert _efetivo(PROXY, CLI_A) == CLI_A  # o item valido continua confiavel
    assert _efetivo(PROXY2, CLI_A) == PROXY2  # o item com porta e invalido: PROXY2 nao e proxy
    _proxies(monkeypatch, f"  {PROXY}  ,   10.88.0.0/16 ")
    assert _efetivo(PROXY, CLI_A) == CLI_A and _efetivo("10.88.4.4", CLI_A) == CLI_A


def test_d16_so_entradas_invalidas_nao_confiam_em_ninguem_e_nao_levantam_erro(monkeypatch):
    for valor in ("lixo", "999.1.1.1", "10.0.0.0/99", "10.77.0.1;10.77.0.2", "0.0.0.0/abc", "\n"):
        monkeypatch.setenv("TRUSTED_PROXIES", valor)
        assert _efetivo(PROXY, CLI_A) == PROXY, f"TRUSTED_PROXIES={valor!r}"


def test_d17_a_lista_e_lida_a_cada_chamada(monkeypatch):
    from core.cliente_ip import ip_do_cliente

    requisicao = _req(PROXY, CLI_A)
    assert ip_do_cliente(requisicao) == PROXY
    monkeypatch.setenv("TRUSTED_PROXIES", PROXY)
    assert ip_do_cliente(requisicao) == CLI_A
    monkeypatch.setenv("TRUSTED_PROXIES", PROXY2)
    assert ip_do_cliente(requisicao) == PROXY
    monkeypatch.delenv("TRUSTED_PROXIES")
    assert ip_do_cliente(requisicao) == PROXY
    monkeypatch.setenv("TRUSTED_PROXIES", f"{PROXY}, {PROXY2}")
    assert ip_do_cliente(requisicao) == CLI_A


def test_d18_sem_par_tcp_nao_ha_o_que_confiar_devolve_none(monkeypatch):
    assert _efetivo(None, CLI_A) is None
    _proxies(monkeypatch, "0.0.0.0/0, ::/0")
    assert _efetivo(None, CLI_A) is None
    assert _efetivo(None) is None


def test_d19_par_vazio_continua_sendo_none_como_hoje(monkeypatch):
    assert _efetivo("", CLI_A) is None
    _proxies(monkeypatch, PROXY)
    assert _efetivo("", CLI_A) is None


def test_d20_par_que_nao_e_ip_nunca_e_proxy_e_sai_como_esta(monkeypatch):
    """O TestClient padrao usa o host 'testclient'; os outros testes do projeto dependem disso."""
    assert _efetivo("testclient", CLI_A) == "testclient"
    _proxies(monkeypatch, f"{PROXY}, 0.0.0.0/0, ::/0")
    assert _efetivo("testclient", CLI_A) == "testclient"


def test_d21_o_resultado_e_texto(monkeypatch):
    _proxies(monkeypatch, PROXY)
    assert isinstance(_efetivo(PROXY, CLI_A), str)
    assert isinstance(_efetivo(PROXY, "2001:db8::1"), str)
    assert isinstance(_efetivo(PROXY), str)


CASOS_CONSISTENCIA = [
    pytest.param(PROXY, CLI_A, id="proxy-confiavel-com-cliente"),
    pytest.param(PROXY, f"{CLI_A}, {PROXY2}", id="cadeia"),
    pytest.param(PROXY, "2001:DB8::1", id="ipv6-no-cabecalho"),
    pytest.param(PROXY, "lixo", id="malformado"),
    pytest.param(PROXY, None, id="sem-cabecalho"),
    pytest.param(FORA, CLI_A, id="par-fora-da-lista"),
]


@pytest.mark.parametrize("peer,xff", CASOS_CONSISTENCIA)
def test_d22_login_limit_e_cliente_ip_dao_o_mesmo_ip(monkeypatch, peer, xff):
    """O login e o limite de taxa usam a MESMA regra: `login_limit.ip_do_cliente` (nome que ja existe) coincide com
    a funcao compartilhada em todos os casos."""
    from core import login_limit
    from core.cliente_ip import ip_do_cliente

    _proxies(monkeypatch, f"{PROXY}, {PROXY2}")
    requisicao = _req(peer, xff)
    assert login_limit.ip_do_cliente(requisicao) == ip_do_cliente(requisicao)


def test_d23_login_limit_ip_do_cliente_usa_o_ip_efetivo(monkeypatch):
    from core import login_limit

    _proxies(monkeypatch, PROXY)
    assert login_limit.ip_do_cliente(_req(PROXY, f"203.0.113.5, {CLI_A}")) == CLI_A
    assert login_limit.ip_do_cliente(_req(FORA, CLI_A)) == FORA


def test_d24_login_limit_sem_trusted_proxies_continua_igual_a_hoje(monkeypatch):
    from core import login_limit

    assert login_limit.ip_do_cliente(_req(PROXY, CLI_A)) == PROXY
    assert login_limit.ip_do_cliente(_req(None, CLI_A)) is None
    assert login_limit.ip_do_cliente(_req("", CLI_A)) is None


# =========================================================================================
# G - gravacao: login_attempts e auth.locked com o IP efetivo
# =========================================================================================

def test_g1_login_attempts_guarda_o_ip_efetivo_e_nunca_o_do_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _falhas_de_login(proxy, CLI_A, "falha-g1-")
    chaves = _chaves_de_ip()
    assert chaves, "nenhuma linha de IP em login_attempts"
    assert set(chaves) == {CLI_A}, f"login_attempts deve guardar so o IP efetivo {CLI_A}: {sorted(set(chaves))}"
    # 20 falhas + 1 bloqueio, todas do IP efetivo
    assert len(chaves) == 21, f"esperado 20 falhas + 1 bloqueio, vieram {len(chaves)}"


def test_g2_auth_locked_por_ip_traz_o_ip_efetivo_e_nao_o_do_proxy(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _falhas_de_login(proxy, CLI_A, "falha-g2-")
    _falhas_de_login(proxy, CLI_B, "falha-g2b-", n=3)  # outro cliente, abaixo do limite
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1, f"esperado 1 auth.locked, vieram {len(eventos)}: {eventos}"
    evento = eventos[0]
    assert evento["entity_id"] == CLI_A, f"entity_id deve ser o IP efetivo: {evento}"
    assert evento["entity_type"] == "login_ip"
    assert CLI_A in (evento["detail"] or ""), evento
    texto = " | ".join(str(v) for v in evento.values() if v is not None)
    assert PROXY not in texto, f"o IP do proxy apareceu no evento: {evento}"
    assert CLI_B not in texto, f"o IP de outro cliente apareceu no evento: {evento}"
    assert SENHA_ERRADA not in texto


def test_g3_ipv6_e_gravado_normalizado(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    _falhas_de_login(proxy, "2001:DB8:0:0:0:0:0:1", "falha-g3-")
    assert set(_chaves_de_ip()) == {"2001:db8::1"}, sorted(set(_chaves_de_ip()))
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1 and eventos[0]["entity_id"] == "2001:db8::1", eventos


def test_g4_login_legado_grava_o_ip_efetivo(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    proxy = _cliente(app_sg3, PROXY)
    for i in range(20):
        r = proxy.post(ROTA_LEGADO, json={"password": f"errada-{i}"}, headers=_xff(CLI_A))
        assert r.status_code == 401, f"falha {i + 1}: {_resumo(r)}"
    assert set(_chaves_de_ip()) == {CLI_A}, sorted(set(_chaves_de_ip()))
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1 and eventos[0]["entity_id"] == CLI_A, eventos
    assert PROXY not in " | ".join(str(v) for v in eventos[0].values() if v is not None)


def test_g5_guarda_sem_trusted_proxies_grava_o_par_tcp_e_nunca_o_cabecalho(app_sg3):
    c = _cliente(app_sg3, PROXY)
    _falhas_de_login(c, lambda i: f"203.0.113.{i + 1}", "falha-g5-")
    assert set(_chaves_de_ip()) == {PROXY}, f"sem TRUSTED_PROXIES vale o par TCP: {sorted(set(_chaves_de_ip()))}"
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1 and eventos[0]["entity_id"] == PROXY, eventos
    assert "203.0.113" not in " | ".join(str(v) for v in eventos[0].values() if v is not None)


def test_g6_par_fora_da_lista_grava_o_par_tcp_mesmo_com_cabecalho(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    c = _cliente(app_sg3, FORA)
    _falhas_de_login(c, CLI_A, "falha-g6-")
    assert set(_chaves_de_ip()) == {FORA}, sorted(set(_chaves_de_ip()))
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1 and eventos[0]["entity_id"] == FORA, eventos


# =========================================================================================
# R - o app nao cai com TRUSTED_PROXIES invalida; producao nao recusa a subida por causa dela
# =========================================================================================

LIXO_NA_LISTA = "lixo, 999.1.1.1, 10.0.0.0/99, \x01, 10.77.0.1:80, ;;;"


def test_r1_requisicoes_com_trusted_proxies_invalida_nao_dao_500(app_sg3, monkeypatch):
    _proxies(monkeypatch, LIXO_NA_LISTA)
    c = _cliente(app_sg3, PROXY)
    assert _chat(c, CLI_A).status_code == 200
    assert _checar_token(c, CLI_A).status_code == 200
    assert _login(c, "ninguem@sg3.test", SENHA_ERRADA, CLI_A).status_code == 400
    assert _landing(c, 1, CLI_A).status_code != 500


def test_r2_cabecalho_estranho_com_proxy_confiavel_nao_da_500(app_sg3, monkeypatch):
    _proxies(monkeypatch, PROXY)
    c = _cliente(app_sg3, PROXY)
    for valor in ("", "lixo", ",,,", "a" * 4000, "ção", f"{CLI_A}, " * 200):
        try:
            r = _chat(c, valor)
        except UnicodeEncodeError:  # o cliente de teste nao envia esse valor; nao e problema do app
            continue
        assert r.status_code in (200, 429), f"XFF {valor[:30]!r}: {_resumo(r)}"


def _env_producao_valida():
    return {
        "APP_ENV": "production",
        "JWT_SECRET_KEY": "j" * 40,
        "ADMIN_TOKEN_SECRET": "segredo-proprio-de-token-sg3",
        "ADMIN_PASSWORD": "senha-admin-sg3-longa-1",
        "FINANCIAL_PASSWORD": "senha-financeiro-sg3-longa",
        "SUPPORT_PASSWORD": "senha-suporte-sg3-longa-1",
        "MERCADO_PAGO_WEBHOOK_SECRET": "webhook-sg3-secreto",
        "MERCADO_PAGO_ACCESS_TOKEN": "APP_USR-sg3-fake",
        "CORS_ALLOWED_ORIGINS": "https://app.exemplo.test",
    }


def test_r3_trusted_proxies_invalida_nao_vira_problema_de_configuracao_em_producao():
    from core.configuracao import validar_configuracao

    base = _env_producao_valida()
    assert validar_configuracao(base) == [], "a base de producao do teste deveria ser valida"
    assert validar_configuracao({**base, "TRUSTED_PROXIES": LIXO_NA_LISTA}) == []
    assert validar_configuracao({**base, "TRUSTED_PROXIES": PROXY}) == []
    assert validar_configuracao({**base, "TRUSTED_PROXIES": ""}) == []

