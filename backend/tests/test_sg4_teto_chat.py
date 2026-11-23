"""SG4 - Teto de custo e abuso do chat anonimo (D109 P5; PLANO_SG, secao SG4; decisao de numero D114 a registrar).

Escritos ANTES da implementacao. Hoje o chat anonimo (`POST /api/chat`) gasta a chave do Groq sem teto global: cada IP novo
recomeca o limite por minuto (30/min, S9) e sessoes novas podem ser abertas em massa. A SG4 acrescenta tres tetos, todos
com padrao DESLIGADO (D109 P5; 300000, 200 e 20 sao so a sugestao de producao):

  - `CHAT_ANON_DAILY_TOKEN_BUDGET` (inteiro; lida a CADA requisicao; ausente, vazia, 0, invalida ou negativa = desligado,
    nunca bloqueia). Soma `ai_usage.total_tokens` do canal anonimo (todas as sessoes, `route` e `answer`) no dia corrente
    de Sao Paulo (`core/fuso.py`). Quando a soma ja e >= ao teto, a proxima mensagem do chat ANONIMO recebe a resposta fixa
    `CHAT_INDISPONIVEL` (HTTP 200, formato das demais respostas fixas, `session_id` efetivo), SEM chamar o LLM (nem o de
    roteamento), `outcome='unresolved'`, `guard='budget'` (valor novo do vocabulario fechado), registrada em
    `ai_interactions` e com a acao de handoff da F6 quando `WHATSAPP_HANDOFF_NUMBER` esta configurado. O chat do aluno
    (`/api/student/chat`) NAO e afetado e seus tokens nao somam.
  - `CHAT_ANON_DAILY_MESSAGES_PER_IP` (0/ausente/invalida = desligado): acima do teto de mensagens do mesmo IP efetivo
    (`core.cliente_ip.ip_do_cliente`) em 24 h -> 429 com `rate_limit.ERRO_CHAT`, sem chegar ao LLM.
  - `CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR` (0/ausente/invalida = desligado): abrir sessao nova (sem `session_id` valido
    emitido pelo servidor, ou com id desconhecido: D38.1) acima do teto por IP efetivo em 1 hora -> 429 com `ERRO_CHAT`;
    continuar uma sessao existente nao conta.
  - Ordem: 429 por IP (por minuto, depois diario, depois sessoes novas) antes de qualquer outra coisa; o teto de tokens so
    depois e produz a resposta 200 fixa. Estado dos limites por IP em memoria (zerado em `redefinir_limites()`); o teto de
    tokens usa o banco (sobrevive a restart).
  - Painel: o endpoint `GET /api/dashboard/observabilidade-ia` traz `guards.by_type["budget"]` (o cartao Guardrails
    mostra "Teto diario atingido"; a tela e coberta pelo e2e).

Escolhas de forma do teste (conservadoras; ver o relatorio do agente-testes):
  [forma] "acima do teto" = N mensagens passam e a (N+1)-esima e barrada; idem para sessoes novas. Janela DESLIZANTE de
          24 h (mensagens) e de 1 h (sessoes), como a janela do minuto do `rate_limit`: mensagem barrada nao conta.
  [forma] o relogio dos limites por IP e `time.monotonic`/`time.time` (padrao do `rate_limit`); os testes de janela
          avancam os dois com um deslocamento (fixture `relogio`). Se o dev usar outro relogio, reportar, nao contornar.
  [forma] o dia de Sao Paulo do teto de tokens usa o relogio Python (`datetime.now(timezone.utc)` + `core/fuso.py`), como
          a serie diaria da E7 (F2/D71): o teste congela a classe `datetime` dos modulos do backend (fixture
          `agora_congelado`, mesmo seam do F2). Dois testes usam o relogio REAL (linhas do dia, de ontem e de amanha em SP)
          e valem para qualquer implementacao; se so o congelado falhar, a causa e o relogio usado, nao a regra.
  [forma] o motivo do handoff na resposta fixa do teto e qualquer um do vocabulario fechado da D77 (`user_request`,
          `llm_failures`, `token_budget`, `unresolved`); o PM nao fixou qual (padrao da GR1: 'unresolved').
  [forma] a resposta fixa do teto tem as chaves status, message, session_id, actions, sources e reply_id (as das demais
          respostas fixas); `sources` vazio; `reply_id` valido para o feedback da GR5.
  [forma] as tres variaveis sao lidas a cada requisicao (o contrato diz isso so do teto de tokens; os testes dos tetos por
          IP definem a variavel ANTES de abrir o app, entao valem tambem se o dev ler no startup).
  [forma] os tetos por IP valem so no chat anonimo; o chat do aluno (limite por aluno, GR3) e as demais rotas nao contam.

Nao definido pelo PM, portanto NAO testado (ver duvidas no relatorio): mensagem vazia/longa/injecao contam no teto de
mensagens?; a resposta fixa do teto consome o teto de mensagens e o de sessoes do IP?; prioridade entre injecao/fora do
assunto e o teto de tokens; falha de leitura do banco no teto de tokens (abre ou fecha?).

Grupos
  A  guarda verde: teto de tokens desligado (ausente, vazio, 0, invalido, negativo) nunca bloqueia
  B  limiar: abaixo/igual/acima; acumulo natural pelo uso do duble; variavel lida a cada requisicao
  C  resposta fixa: formato, 0 chamadas ao LLM, ai_interactions, handoff com e sem numero, feedback, session_id efetivo
  D  soma so do canal anonimo e so do dia de Sao Paulo (relogio real e relogio congelado; virada do dia)
  E  chat do aluno intacto
  F  teto de mensagens por IP (24 h)
  G  teto de sessoes novas por IP (1 h)
  H  IP efetivo com TRUSTED_PROXIES (SG3) nos dois tetos por IP
  O  ordem: 429 por IP antes do teto de tokens
  I  painel: `budget` em guards.by_type; papeis e IDOR do dashboard intactos

Convencoes: banco temporario e catalogo do bot isolado do conftest; SDK do Groq falso (seam da E7) com CONTADOR de
chamadas, nunca rede; o app sobe sempre com startup (`with TestClient`), entao o agente do chat e novo e usa o falso (um
`app.state.manager_agent` real de outra suite chamaria o Groq: cuidado aprendido na SG1/SG3). Outros IPs: clientes sem
`with` (nao refazem o startup e dividem o estado do app). Enderecos de documentacao (RFC 5737) fazem o papel dos IPs.
Numero de WhatsApp FABRICADO (5511900000000).
"""

import contextlib
import re
import sqlite3
import sys
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import agents.groq_client as groq_client_mod
from agents.ai_observability import hash_da_sessao
from core import rate_limit
from core.security import create_access_token, get_password_hash
from db import Database

BACKEND_DIR = Path(__file__).resolve().parent.parent

ROTA_ANONIMO = "/api/chat"
ROTA_ALUNO = "/api/student/chat"
ROTA_FEEDBACK = "/api/chat/feedback"
ROTA_PAINEL = "/api/dashboard/observabilidade-ia"
SENHAS_ADMINISTRATIVAS = {"admin": "admin123", "financial": "fin123", "support": "sup123"}

VAR_TETO = "CHAT_ANON_DAILY_TOKEN_BUDGET"
VAR_MSG_IP = "CHAT_ANON_DAILY_MESSAGES_PER_IP"
VAR_SESSOES_IP = "CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR"
VAR_NUMERO = "WHATSAPP_HANDOFF_NUMBER"
NUMERO = "5511900000000"  # fabricado
LABEL = "Falar com um atendente no WhatsApp"
CHAVES_HANDOFF = {"type", "reason", "url", "label"}
MOTIVOS = {"user_request", "llm_failures", "token_budget", "unresolved"}

CHAT_INDISPONIVEL = (
    "O assistente está com muitas conversas agora. Fale com a nossa equipe pelo WhatsApp ou tente de novo amanhã."
)
ERRO_CHAT = rate_limit.ERRO_CHAT
MODELO = "modelo-sg4-teste"

# Mensagem sem palavra de pedido de humano, sem palavra-chave de curso e sem tema de politica (como no F6).
GERAL = "Gostaria de uma recomendacao geral da plataforma"
PEDIDO = "Quero falar com um atendente"
RESPOSTA_DUBLE = "Resposta do duble SG4"
USAGE_ROTA = (40, 10, 50)
USAGE_RESPOSTA = (150, 25, 175)
TOKENS_POR_MENSAGEM = USAGE_ROTA[2] + USAGE_RESPOSTA[2]  # 225: uma mensagem geral = rota + resposta

IP_A, IP_B, IP_C = "198.51.100.1", "198.51.100.2", "198.51.100.3"
PROXY, PROXY2 = "10.77.0.1", "10.77.0.2"
FORA_DA_LISTA = "10.99.0.9"
SESSION_ID = re.compile(r"[0-9a-f]{32}")

GUARDS = [
    "no_source", "input_injection", "input_off_topic", "input_login", "input_pii",
    "output_leak", "output_offer", "output_link", "output_promise", "output_unverified",
]
GUARDS_PAINEL = GUARDS + ["budget"]

VALORES_DESLIGADOS = [None, "", "   ", "0", "abc", "12abc", "-1", "-300000"]


# =========================================================================================
# Falso do SDK do Groq (seam da E7, D42) com contador de chamadas
# =========================================================================================

class GroqFalso:
    def __init__(self):
        self.chamadas = []

    def create(self, **kw):
        limite = kw.get("max_completion_tokens", kw.get("max_tokens"))
        tipo = "rota" if limite is not None and limite <= 300 else "resposta"
        self.chamadas.append(tipo)
        conteudo = "GENERAL" if tipo == "rota" else f"{RESPOSTA_DUBLE} {uuid.uuid4().hex[:8]}"
        p, c, t = USAGE_ROTA if tipo == "rota" else USAGE_RESPOSTA
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=conteudo))],
            usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=t),
        )

    @property
    def total(self):
        return len(self.chamadas)

    def respostas(self):
        return [c for c in self.chamadas if c == "resposta"]


@pytest.fixture
def groq(monkeypatch):
    controlador = GroqFalso()

    class GroqSDKFalso:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=controlador.create))

    monkeypatch.setattr(groq_client_mod, "Groq", GroqSDKFalso)
    monkeypatch.setenv("GROQ_MODEL", MODELO)
    return controlador


@pytest.fixture(autouse=True)
def ambiente_sg4(monkeypatch):
    """Hermetico: nenhum teto, proxy ou numero herdado do shell ou do backend/.env."""
    for variavel in (VAR_TETO, VAR_MSG_IP, VAR_SESSOES_IP, VAR_NUMERO, "CHAT_TOKEN_BUDGET", "TRUSTED_PROXIES"):
        monkeypatch.delenv(variavel, raising=False)


@pytest.fixture
def abrir(banco, catalogo_bot, groq, monkeypatch):
    """Sobe o app COM startup (agente novo, que usa o falso do Groq). O IP do par TCP e `host`."""
    pilha = contextlib.ExitStack()

    def _abrir(host=IP_A, numero=None):
        if numero is not None:
            monkeypatch.setenv(VAR_NUMERO, numero)
        from app import app as fastapi_app

        return pilha.enter_context(TestClient(fastapi_app, client=(host, 50000), raise_server_exceptions=False))

    try:
        yield _abrir
    finally:
        pilha.close()


def _outro(host, porta=50000):
    """Cliente de outro IP: sem `with` (nao refaz o startup; divide o estado e o agente do app)."""
    from app import app as fastapi_app

    return TestClient(fastapi_app, client=(host, porta), raise_server_exceptions=False)


def _manager():
    from app import app as fastapi_app

    return fastapi_app.state.manager_agent


@pytest.fixture
def relogio(monkeypatch):
    """Desloca `time.monotonic` e `time.time` (relogio dos limites em memoria). Avance so entre requisicoes."""
    estado = SimpleNamespace(deslocamento=0.0)
    monotonico, tempo = time.monotonic, time.time
    monkeypatch.setattr(time, "monotonic", lambda: monotonico() + estado.deslocamento)
    monkeypatch.setattr(time, "time", lambda: tempo() + estado.deslocamento)

    def avancar(segundos):
        estado.deslocamento += segundos

    return SimpleNamespace(avancar=avancar)


@pytest.fixture
def agora_congelado(monkeypatch):
    """Congela o "agora" do backend (seam do F2: a classe `datetime` importada pelos modulos do backend). Pode ser
    chamada varias vezes no mesmo teste: cada chamada so muda o instante."""
    import app  # noqa: F401  (garante que os modulos do backend ja estao importados)

    estado = {"fixo": None, "instalado": False}

    class DatetimeCongelado(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return estado["fixo"].astimezone().replace(tzinfo=None)
            return estado["fixo"].astimezone(tz)

        @classmethod
        def utcnow(cls):
            return estado["fixo"].replace(tzinfo=None)

        @classmethod
        def today(cls):
            return cls.now()

    def congelar(instante_utc: datetime):
        estado["fixo"] = instante_utc.replace(tzinfo=timezone.utc)
        if not estado["instalado"]:
            trocados = 0
            for nome, modulo in list(sys.modules.items()):
                arquivo = getattr(modulo, "__file__", None) or ""
                try:
                    dentro = Path(arquivo).resolve().is_relative_to(BACKEND_DIR) and "tests" not in Path(arquivo).parts
                except (OSError, ValueError):
                    dentro = False
                if dentro and getattr(modulo, "datetime", None) is datetime:
                    monkeypatch.setattr(modulo, "datetime", DatetimeCongelado)
                    trocados += 1
            assert trocados, "seam: nenhum modulo do backend importa a classe datetime"
            estado["instalado"] = True
        return estado["fixo"]

    return congelar


# =========================================================================================
# Banco e contas
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


def _uso(tokens, *, canal="anonymous", created_at=None, call_type="answer", session_hash=None, user_id=None):
    """Semeia uma linha de ai_usage. `created_at` em UTC ('AAAA-MM-DD HH:MM:SS'); sem ele, vale o padrao do banco (agora)."""
    if session_hash is None and canal == "anonymous":
        session_hash = uuid.uuid4().hex[:16]
    colunas = "channel, user_id, session_hash, call_type, model, prompt_tokens, completion_tokens, total_tokens, " \
              "cost_usd, latency_ms, status"
    valores = (canal, user_id, session_hash, call_type, "modelo-seed", tokens, 0, tokens, 0.0, 10, "ok")
    if created_at is None:
        _executar(f"INSERT INTO ai_usage ({colunas}) VALUES (?,?,?,?,?,?,?,?,?,?,?)", valores)
    else:
        _executar(f"INSERT INTO ai_usage (created_at, {colunas}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (created_at, *valores))


def _interacao(guard, outcome="answered", channel="anonymous"):
    _executar(
        "INSERT INTO ai_interactions (channel, user_id, session_hash, course_id, outcome, topic, guard) "
        "VALUES (?, NULL, ?, NULL, ?, NULL, ?)",
        (channel, uuid.uuid4().hex[:16], outcome, guard),
    )


def _interacoes():
    return _sql("SELECT * FROM ai_interactions ORDER BY id")


def _usos():
    return _sql("SELECT * FROM ai_usage ORDER BY id")


def _handoffs():
    return _sql("SELECT * FROM ai_handoffs ORDER BY id")


def _com_budget():
    return [i for i in _interacoes() if i["guard"] == "budget"]


def _conta(tag, role="student"):
    email = f"{tag}.{uuid.uuid4().hex[:8]}@sg4.test"
    user_id = Database.add_user(email, f"Conta SG4 {tag}", get_password_hash("senha-sg4-123456"), role=role)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": role})
    return SimpleNamespace(id=user_id, email=email, token=token)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _forjado(role="admin", user_id=1):
    return jose_jwt.encode(
        {"user_id": user_id, "email": "x@sg4.test", "role": role, "exp": datetime.utcnow() + timedelta(hours=1)},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


def _token_staff(c, perfil, via="staff"):
    if via == "staff":
        r = c.post("/api/admin/login", json={"password": SENHAS_ADMINISTRATIVAS[perfil]})
        assert r.status_code == 200, r.text
        return r.json()["token"]
    return _conta(f"staff-{perfil}", role=perfil).token


def _painel(c, token):
    r = c.get(ROTA_PAINEL, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["metrics"]


# =========================================================================================
# Envio e conferencias
# =========================================================================================

def _enviar(c, texto=GERAL, sid=None, headers=None):
    corpo = {"message": texto}
    if sid is not None:
        corpo["session_id"] = sid
    return c.post(ROTA_ANONIMO, json=corpo, headers=headers or {})


def _aluno_envia(c, conta, texto=GERAL):
    return c.post(ROTA_ALUNO, json={"message": texto}, headers=_auth(conta.token))


def _normal(r):
    """Resposta normal do assistente (o duble respondeu): 200 success, texto do duble, sem ser o texto do teto."""
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert corpo.get("message") != CHAT_INDISPONIVEL, f"bloqueou sem dever: {corpo}"
    assert str(corpo.get("message", "")).startswith(RESPOSTA_DUBLE), corpo
    return corpo


def _bloqueada(r):
    """Resposta fixa do teto de tokens: 200 success com CHAT_INDISPONIVEL."""
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert corpo.get("message") == CHAT_INDISPONIVEL, f"esperava CHAT_INDISPONIVEL: {corpo}"
    return corpo


def _429(r):
    assert r.status_code == 429, f"esperava 429, veio {r.status_code}: {r.text[:300]}"
    assert r.json() == {"status": "error", "message": ERRO_CHAT}, r.text


def _estado():
    """(linhas de ai_usage, de ai_interactions, sessoes em memoria) para provar que a mensagem barrada nao andou."""
    return (len(_usos()), len(_interacoes()), len(_manager().sessions))


# =========================================================================================
# Grupo A - teto de tokens desligado nunca bloqueia (guarda verde)
# =========================================================================================

@pytest.mark.parametrize("valor", VALORES_DESLIGADOS)
def test_a1_teto_desligado_nunca_bloqueia(abrir, groq, monkeypatch, valor):
    if valor is not None:
        monkeypatch.setenv(VAR_TETO, valor)
    client = abrir()
    _uso(10**9)  # uso anonimo gigante hoje: so um teto ligado poderia bloquear

    for _ in range(4):
        _normal(_enviar(client))

    assert len(groq.respostas()) == 4
    assert _com_budget() == []


def test_a2_tetos_por_ip_ausentes_nao_mudam_nada(abrir, groq):
    """Guarda: sem os tetos por IP, as mensagens e as sessoes novas passam (so vale o limite por minuto da S9)."""
    client = abrir()
    sids = set()
    for _ in range(12):
        corpo = _normal(_enviar(client))
        sids.add(corpo["session_id"])
    assert len(sids) == 12


# =========================================================================================
# Grupo B - limiar
# =========================================================================================

@pytest.mark.parametrize("teto, gasto, bloqueia", [
    (1000, 0, False),
    (1000, 999, False),
    (1000, 1000, True),     # igual ao teto: a soma JA e >= ao teto
    (1000, 1001, True),
    (1000, 50000, True),
    (1, 1, True),
    (300000, 299999, False),
    (300000, 300000, True),
])
def test_b1_limiar_do_teto_de_tokens(abrir, groq, monkeypatch, teto, gasto, bloqueia):
    monkeypatch.setenv(VAR_TETO, str(teto))
    client = abrir()
    if gasto:
        _uso(gasto)

    r = _enviar(client)

    if bloqueia:
        _bloqueada(r)
        assert groq.total == 0
    else:
        _normal(r)
        assert len(groq.respostas()) == 1


def test_b2_acumulo_natural_pelo_uso_do_duble(abrir, groq, monkeypatch):
    """Teto 300: a 1a mensagem gasta 225 (rota 50 + resposta 175) e passa; a 2a ainda passa (225 < 300) e leva a soma a
    450; a 3a ja encontra a soma >= teto e recebe a resposta fixa, sem nenhuma chamada nova."""
    assert TOKENS_POR_MENSAGEM == 225
    monkeypatch.setenv(VAR_TETO, "300")
    client = abrir()

    _normal(_enviar(client))
    _normal(_enviar(client))
    chamadas = groq.total
    assert sum(u["total_tokens"] for u in _usos()) == 2 * TOKENS_POR_MENSAGEM

    _bloqueada(_enviar(client))

    assert groq.total == chamadas, "a mensagem barrada nao pode chamar o LLM (nem o de roteamento)"
    assert sum(u["total_tokens"] for u in _usos()) == 2 * TOKENS_POR_MENSAGEM, "a resposta fixa nao gasta tokens"


def test_b3_a_mensagem_que_cruza_o_teto_e_respondida_e_a_proxima_barrada(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(999)

    _normal(_enviar(client))  # soma 999 < 1000: passa, e passa a 1224
    _bloqueada(_enviar(client))
    assert len(groq.respostas()) == 1


def test_b4_soma_de_varias_sessoes_e_dos_dois_tipos_de_chamada(abrir, groq, monkeypatch):
    """A soma e global (todas as sessoes anonimas) e conta roteamento e resposta."""
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(400, call_type="route")
    _uso(300, call_type="answer")
    _normal(_enviar(client))  # 700 < 1000
    _uso(300, call_type="answer", session_hash="outra-sessao-sg4")  # 1000 >= teto

    _bloqueada(_enviar(client))
    assert len(groq.respostas()) == 1


def test_b5_teto_lido_a_cada_requisicao(abrir, groq, monkeypatch):
    client = abrir()
    _uso(5000)
    _normal(_enviar(client))  # sem teto
    monkeypatch.setenv(VAR_TETO, "1000")
    _bloqueada(_enviar(client))
    monkeypatch.setenv(VAR_TETO, "1000000")  # subiu
    _normal(_enviar(client))
    monkeypatch.setenv(VAR_TETO, "1000")
    _bloqueada(_enviar(client))
    monkeypatch.setenv(VAR_TETO, "0")  # desligou
    _normal(_enviar(client))
    monkeypatch.delenv(VAR_TETO)
    _normal(_enviar(client))


def test_b6_o_teto_sobrevive_a_restart_vem_do_banco(abrir, groq, monkeypatch):
    """A soma vem do banco: um app novo (restart: novo startup, estado em memoria zerado) continua bloqueando."""
    monkeypatch.setenv(VAR_TETO, "1000")
    _uso(2000)
    _bloqueada(_enviar(abrir()))
    _bloqueada(_enviar(abrir()))
    assert groq.total == 0


# =========================================================================================
# Grupo C - a resposta fixa
# =========================================================================================

@pytest.fixture
def estourado(abrir, monkeypatch):
    """App com o teto ligado (1000) e ja estourado por dados semeados; sem numero de WhatsApp."""
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(1000)
    return client


def test_c1_formato_da_resposta_fixa(estourado, groq):
    corpo = _bloqueada(_enviar(estourado))

    assert {"status", "message", "session_id", "actions", "sources", "reply_id"} <= set(corpo), corpo
    assert SESSION_ID.fullmatch(corpo["session_id"]), corpo["session_id"]
    assert corpo["sources"] == []
    assert corpo["actions"] == []  # sem WHATSAPP_HANDOFF_NUMBER nao ha acao
    assert SESSION_ID.fullmatch(corpo["reply_id"]), corpo["reply_id"]
    assert "masked_message" not in corpo and "detail" not in corpo


def test_c2_nao_chama_o_llm_nem_o_de_roteamento(estourado, groq):
    for texto in (GERAL, "Quais cursos de Python voces tem?", "Tem curso de Excel?", PEDIDO):
        _bloqueada(_enviar(estourado, texto))
    assert groq.chamadas == [], f"o LLM foi chamado: {groq.chamadas}"
    assert _usos()[-1]["total_tokens"] == 1000 and len(_usos()) == 1, "nenhum uso novo foi gravado"


def test_c3_interacao_registrada_como_as_outras_respostas_fixas(estourado, groq):
    corpo = _bloqueada(_enviar(estourado))

    linhas = _interacoes()
    assert len(linhas) == 1, linhas
    linha = linhas[0]
    assert linha["channel"] == "anonymous" and linha["user_id"] is None
    assert linha["session_hash"] == hash_da_sessao(corpo["session_id"])
    assert linha["outcome"] == "unresolved"
    assert linha["guard"] == "budget"
    assert linha["course_id"] is None


def test_c4_a_resposta_fixa_nao_grava_texto_cru_nem_chat_messages(estourado, groq):
    segredo = "Meu e-mail é fulano.sg4@example.com, recomenda leituras introdutorias?"
    corpo = _bloqueada(_enviar(estourado, segredo))

    linha = _interacoes()[0]
    assert "fulano.sg4@example.com" not in str(linha)
    assert corpo["session_id"] not in str(linha)
    assert _sql("SELECT COUNT(*) AS n FROM chat_messages")[0]["n"] == 0


def test_c5_handoff_da_f6_quando_ha_numero(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir(numero=NUMERO)
    _uso(1000)

    corpo = _bloqueada(_enviar(client))

    handoffs = [a for a in corpo["actions"] if a.get("type") == "handoff"]
    assert len(handoffs) == 1 and len(corpo["actions"]) == 1, corpo["actions"]
    acao = handoffs[0]
    assert set(acao) == CHAVES_HANDOFF, acao
    assert acao["label"] == LABEL
    assert acao["reason"] in MOTIVOS, acao["reason"]
    prefixo = f"https://wa.me/{NUMERO}?text="
    assert acao["url"].startswith(prefixo), acao["url"]
    texto = urllib.parse.parse_qs(urllib.parse.urlsplit(acao["url"]).query)["text"]
    assert texto == ["Olá! Vim do assistente virtual da Global Training e gostaria de falar com um atendente "
                     "sobre os cursos."], texto
    assert groq.total == 0
    linhas = _handoffs()
    assert len(linhas) == 1, linhas
    assert linhas[0]["channel"] == "anonymous" and linhas[0]["user_id"] is None
    assert linhas[0]["session_hash"] == hash_da_sessao(corpo["session_id"])
    assert linhas[0]["reason"] == acao["reason"]
    assert NUMERO not in str(linhas[0])


@pytest.mark.parametrize("numero", ["", "12345", "abc", "+55 (11) 9"])
def test_c6_sem_numero_valido_nao_ha_acao_de_handoff(abrir, groq, monkeypatch, numero):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir(numero=numero)
    _uso(1000)

    corpo = _bloqueada(_enviar(client))

    assert corpo["actions"] == []
    assert _handoffs() == []


def test_c7_pedido_de_atendente_com_teto_estourado_tambem_recebe_a_fixa_e_o_handoff(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir(numero=NUMERO)
    _uso(1000)

    corpo = _bloqueada(_enviar(client, PEDIDO))

    acoes = [a for a in corpo["actions"] if a.get("type") == "handoff"]
    assert len(acoes) == 1 and acoes[0]["reason"] in MOTIVOS, corpo["actions"]
    assert groq.total == 0


def test_c8_session_id_efetivo(estourado, groq):
    """Sem id ou com id desconhecido: sessao nova (id novo, nunca o do cliente). Com o id emitido: a mesma sessao."""
    primeiro = _bloqueada(_enviar(estourado))
    sid = primeiro["session_id"]
    assert SESSION_ID.fullmatch(sid)

    assert _bloqueada(_enviar(estourado, sid=sid))["session_id"] == sid
    for invalido in ("web-chat-session", "default", uuid.uuid4().hex):
        efetivo = _bloqueada(_enviar(estourado, sid=invalido))["session_id"]
        assert SESSION_ID.fullmatch(efetivo) and efetivo not in (invalido, sid), efetivo


def test_c9_a_resposta_fixa_aceita_feedback_da_gr5(estourado, groq):
    corpo = _bloqueada(_enviar(estourado))

    r = estourado.post(ROTA_FEEDBACK, json={"session_id": corpo["session_id"], "reply_id": corpo["reply_id"],
                                            "rating": "down"})

    assert r.status_code == 200, r.text


def test_c10_o_bloqueio_se_repete_enquanto_a_soma_estiver_no_teto(estourado, groq):
    for _ in range(5):
        _bloqueada(_enviar(estourado))
    assert len(_com_budget()) == 5
    assert len(_usos()) == 1 and groq.total == 0


def test_c11_com_o_teto_estourado_o_painel_conta_o_bloqueio_do_pipeline_real(estourado, groq):
    _bloqueada(_enviar(estourado))
    _bloqueada(_enviar(estourado))

    metricas = _painel(estourado, _token_staff(estourado, "admin"))

    assert metricas["guards"]["by_type"]["budget"] == 2
    assert metricas["no_source"] == 0, "o teto nao e 'sem fonte'"


# =========================================================================================
# Grupo D - so o canal anonimo e so o dia de Sao Paulo
# =========================================================================================

def test_d1_tokens_do_canal_do_aluno_nao_somam(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    aluno = _conta("d1")
    _uso(10**7, canal="student", user_id=aluno.id)

    _normal(_enviar(client))


def test_d2_so_a_parte_anonima_entra_na_soma(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    aluno = _conta("d2")
    _uso(600)
    _uso(600, canal="student", user_id=aluno.id)
    _normal(_enviar(client))  # anonimo 600 < 1000; se os 600 do aluno somassem (1200), bloquearia aqui

    _uso(400)  # anonimo: 600 + 225 do duble + 400 >= 1000
    _bloqueada(_enviar(client))


def _inicio_do_dia_sp_em_utc():
    """Meia-noite de hoje em Sao Paulo (UTC -3 fixo), como instante UTC. Relogio real."""
    sp = datetime.now(timezone.utc) - timedelta(hours=3)
    return datetime(sp.year, sp.month, sp.day, tzinfo=timezone.utc) + timedelta(hours=3)


def _texto_utc(instante):
    return instante.strftime("%Y-%m-%d %H:%M:%S")


def test_d3_dia_de_sp_com_o_relogio_real_ontem_e_amanha_nao_contam(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    inicio = _inicio_do_dia_sp_em_utc()
    _uso(10**6, created_at=_texto_utc(inicio - timedelta(seconds=1)))   # ultimo segundo de ontem em SP
    _uso(10**6, created_at=_texto_utc(inicio - timedelta(hours=20)))    # ontem
    _uso(10**6, created_at=_texto_utc(inicio + timedelta(hours=24)))    # primeiro segundo de amanha em SP
    _uso(10**6, created_at=_texto_utc(inicio + timedelta(days=3)))      # futuro

    _normal(_enviar(client))  # nada de hoje: soma 0


def test_d4_dia_de_sp_com_o_relogio_real_o_inicio_do_dia_conta(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    inicio = _inicio_do_dia_sp_em_utc()
    _uso(600, created_at=_texto_utc(inicio))                     # 00:00:00 de hoje em SP: conta
    _uso(10**6, created_at=_texto_utc(inicio - timedelta(seconds=1)))  # nao conta
    _normal(_enviar(client))  # 600 < 1000

    _uso(400, created_at=_texto_utc(inicio))  # soma de hoje 1000
    _bloqueada(_enviar(client))


def test_d5_dia_de_sp_relogio_congelado_fronteiras(abrir, groq, monkeypatch, agora_congelado):
    """Agora = 2026-10-08 15:00 UTC (12:00 de 08/10 em SP). 02:59:59 UTC de 08/10 ainda e 07/10 em SP (nao conta);
    03:00:00 UTC e 00:00:00 de 08/10 (conta); 03:00:00 UTC de 09/10 ja e 09/10 em SP (amanha, nao conta)."""
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    agora_congelado(datetime(2026, 10, 8, 15, 0, 0))
    _uso(10**6, created_at="2026-10-08 02:59:59")
    _uso(10**6, created_at="2026-10-09 03:00:00")
    _normal(_enviar(client))  # nada de 08/10 em SP

    _uso(1000, created_at="2026-10-08 03:00:00")
    _bloqueada(_enviar(client))


def test_d6_virada_do_dia_de_sp_zera_a_soma(abrir, groq, monkeypatch, agora_congelado):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(600, created_at="2026-10-08 05:00:00")
    _uso(400, created_at="2026-10-08 14:00:00")

    agora_congelado(datetime(2026, 10, 8, 15, 0, 0))
    _bloqueada(_enviar(client))

    agora_congelado(datetime(2026, 10, 9, 2, 59, 59))  # 23:59:59 de 08/10 em SP: ainda o mesmo dia
    _bloqueada(_enviar(client))

    agora_congelado(datetime(2026, 10, 9, 3, 0, 0))  # 00:00:00 de 09/10 em SP: virou o dia
    _normal(_enviar(client))
    assert len(groq.respostas()) == 1


# =========================================================================================
# Grupo E - o chat do aluno nao e afetado
# =========================================================================================

def test_e1_chat_do_aluno_responde_normalmente_com_o_teto_estourado(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir(numero=NUMERO)
    aluno = _conta("e1")
    _uso(10**6)  # teto anonimo estourado

    r = _aluno_envia(client, aluno)

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo.get("status") == "success" and corpo["message"] != CHAT_INDISPONIVEL, corpo
    assert corpo["message"].startswith(RESPOSTA_DUBLE), corpo
    assert groq.total >= 1
    assert not [i for i in _interacoes() if i["channel"] == "student" and i["guard"] == "budget"]
    # e o anonimo continua barrado
    _bloqueada(_enviar(client))


def test_e2_tokens_gastos_pelo_aluno_nao_estouram_o_teto_do_anonimo(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "300")
    client = abrir()
    aluno = _conta("e2")
    for _ in range(4):  # 4 x 225 = 900 tokens do canal do aluno, bem acima do teto de 300
        r = _aluno_envia(client, aluno)
        assert r.status_code == 200 and r.json()["message"] != CHAT_INDISPONIVEL, r.text
    assert sum(u["total_tokens"] for u in _usos() if u["channel"] == "student") >= 900

    _normal(_enviar(client))  # o anonimo ainda tem o teto inteiro


def test_e3_o_chat_do_aluno_nao_e_barrado_pelos_tetos_por_ip(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "2")
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir()
    aluno = _conta("e3")
    for _ in range(6):
        r = _aluno_envia(client, aluno)
        assert r.status_code == 200 and r.json()["message"].startswith(RESPOSTA_DUBLE), r.text

    # as 6 mensagens do aluno, do mesmo IP, nao gastaram o teto do anonimo (2 mensagens, 1 sessao nova)
    sid = _normal(_enviar(client))["session_id"]
    _normal(_enviar(client, sid=sid))
    _429(_enviar(client, sid=sid))


# =========================================================================================
# Grupo F - teto de mensagens por IP (24 h)
# =========================================================================================

@pytest.mark.parametrize("valor", [None, "", "   ", "0", "abc", "12abc", "-1", "-5"])
def test_f1_teto_de_mensagens_desligado_nunca_bloqueia(abrir, groq, monkeypatch, valor):
    if valor is not None:
        monkeypatch.setenv(VAR_MSG_IP, valor)
    client = abrir()
    for _ in range(12):
        _normal(_enviar(client))
    assert len(groq.respostas()) == 12


def test_f2_acima_do_teto_do_mesmo_ip_429_sem_chegar_ao_llm(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "3")
    client = abrir()
    for _ in range(3):
        _normal(_enviar(client))
    antes = (groq.total, _estado())

    for _ in range(4):
        _429(_enviar(client))

    assert (groq.total, _estado()) == antes, "a mensagem barrada nao chega ao LLM, ao banco nem abre sessao"


def test_f3_o_teto_vale_tambem_para_a_sessao_existente(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "3")
    client = abrir()
    sid = _normal(_enviar(client))["session_id"]
    _normal(_enviar(client, sid=sid))
    _normal(_enviar(client, sid=sid))

    _429(_enviar(client, sid=sid))


def test_f4_ips_diferentes_sao_independentes(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "3")
    a = abrir(IP_A)
    b, c = _outro(IP_B), _outro(IP_C)
    for _ in range(3):
        _normal(_enviar(a))
    _429(_enviar(a))

    for _ in range(3):  # B nao herda o consumo de A
        _normal(_enviar(b))
    _429(_enviar(b))
    _normal(_enviar(c))  # C ainda tem o teto inteiro
    _429(_enviar(a))


def test_f5_o_429_de_um_ip_nao_consome_o_limite_por_minuto_de_outro(abrir, groq, monkeypatch):
    """A usa os 30/min e insiste (429); B, de outro IP, ainda envia os seus 30/min inteiros (e so o 31o e barrado)."""
    monkeypatch.setenv(VAR_MSG_IP, "40")
    a = abrir(IP_A)
    b = _outro(IP_B)
    for _ in range(30):
        _normal(_enviar(a))
    for _ in range(10):
        _429(_enviar(a))

    for _ in range(30):
        _normal(_enviar(b))
    _429(_enviar(b))


def test_f6_so_o_chat_anonimo_conta_outras_rotas_nao(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "3")
    client = abrir()
    for _ in range(10):
        assert client.get("/api/courses").status_code == 200
        client.get("/health")
    for _ in range(3):
        _normal(_enviar(client))
    _429(_enviar(client))


def test_f7_a_janela_e_deslizante_de_24_h_e_a_barrada_nao_conta(abrir, groq, monkeypatch, relogio):
    monkeypatch.setenv(VAR_MSG_IP, "2")
    client = abrir()
    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))

    relogio.avancar(23 * 3600)
    _429(_enviar(client))  # ainda dentro das 24 h; esta tentativa barrada nao pode estender o bloqueio
    relogio.avancar(3600 + 5)  # passaram mais de 24 h desde as duas mensagens aceitas
    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))


def test_f8_barrada_pelo_minuto_nao_consome_o_teto_diario(abrir, groq, monkeypatch, relogio):
    """Teto diario 31 e limite por minuto 30: a 31a no mesmo minuto e barrada pelo MINUTO; ao fim da janela do minuto ela
    ainda e a 31a mensagem aceita (a barrada nao contou), e so a 32a bate no teto diario."""
    monkeypatch.setenv(VAR_MSG_IP, "31")
    client = abrir()
    for _ in range(30):
        _normal(_enviar(client))
    _429(_enviar(client))

    relogio.avancar(61)
    _normal(_enviar(client))
    _429(_enviar(client))


def test_f9_redefinir_limites_zera_o_teto_de_mensagens(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "2")
    client = abrir()
    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))

    rate_limit.redefinir_limites()

    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))


# =========================================================================================
# Grupo G - teto de sessoes novas por IP (1 hora)
# =========================================================================================

@pytest.mark.parametrize("valor", [None, "", "   ", "0", "abc", "12abc", "-1", "-5"])
def test_g1_teto_de_sessoes_desligado_nunca_bloqueia(abrir, groq, monkeypatch, valor):
    if valor is not None:
        monkeypatch.setenv(VAR_SESSOES_IP, valor)
    client = abrir()
    for _ in range(12):
        _normal(_enviar(client))
    assert len(_manager().sessions) == 12


def test_g2_acima_do_teto_de_sessoes_novas_429(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "2")
    client = abrir()
    _normal(_enviar(client))
    _normal(_enviar(client))
    antes = (groq.total, _estado())

    for _ in range(3):
        _429(_enviar(client))

    assert (groq.total, _estado()) == antes, "a sessao barrada nao abre sessao, nao chama o LLM e nao grava"


def test_g3_continuar_sessao_existente_nao_conta(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "2")
    client = abrir()
    s1 = _normal(_enviar(client))["session_id"]
    s2 = _normal(_enviar(client))["session_id"]
    _429(_enviar(client))  # teto de sessoes novas atingido

    for _ in range(4):  # as sessoes que ja existem continuam sem limite de sessao
        _normal(_enviar(client, sid=s1))
        _normal(_enviar(client, sid=s2))
    _429(_enviar(client))


@pytest.mark.parametrize("desconhecido", ["web-chat-session", "default", "", "0" * 32, "abc123"])
def test_g4_id_desconhecido_conta_como_sessao_nova(abrir, groq, monkeypatch, desconhecido):
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir()
    corpo = _normal(_enviar(client, sid=desconhecido))
    assert corpo["session_id"] != desconhecido

    # inventar outro id (ou nenhum) nao contorna o teto
    _429(_enviar(client, sid=uuid.uuid4().hex))
    _429(_enviar(client, sid="web-chat-session"))
    _429(_enviar(client))


def test_g5_ips_diferentes_tem_tetos_de_sessao_independentes(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "2")
    a = abrir(IP_A)
    b = _outro(IP_B)
    _normal(_enviar(a))
    _normal(_enviar(a))
    _429(_enviar(a))

    _normal(_enviar(b))
    _normal(_enviar(b))
    _429(_enviar(b))


def test_g6_barrada_pelo_teto_de_sessoes_nao_consome_o_teto_de_mensagens(abrir, groq, monkeypatch):
    """Mensagens 3 e sessoes 1: 1a (sessao nova) passa; 2a (outra sessao nova) e barrada pelas SESSOES e nao pode contar
    como mensagem; 3a e 4a (sessao existente) passam; so a 5a bate no teto de mensagens."""
    monkeypatch.setenv(VAR_MSG_IP, "3")
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir()
    sid = _normal(_enviar(client))["session_id"]
    _429(_enviar(client))
    _normal(_enviar(client, sid=sid))
    _normal(_enviar(client, sid=sid))
    _429(_enviar(client, sid=sid))


def test_g7_a_janela_e_de_1_hora(abrir, groq, monkeypatch, relogio):
    monkeypatch.setenv(VAR_SESSOES_IP, "2")
    client = abrir()
    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))

    relogio.avancar(59 * 60)
    _429(_enviar(client))  # a barrada nao estende o bloqueio
    relogio.avancar(2 * 60)  # passou 1 h desde as duas sessoes abertas
    _normal(_enviar(client))
    _normal(_enviar(client))
    _429(_enviar(client))


def test_g8_redefinir_limites_zera_o_teto_de_sessoes(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir()
    _normal(_enviar(client))
    _429(_enviar(client))

    rate_limit.redefinir_limites()

    _normal(_enviar(client))
    _429(_enviar(client))


# =========================================================================================
# Grupo H - IP efetivo com TRUSTED_PROXIES (SG3)
# =========================================================================================

def _xff(ip):
    return {"X-Forwarded-For": ip}


def test_h1_atras_de_proxy_confiavel_cada_cliente_tem_o_seu_teto_de_mensagens(abrir, groq, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", PROXY)
    monkeypatch.setenv(VAR_MSG_IP, "2")
    client = abrir(PROXY)
    for _ in range(2):
        _normal(_enviar(client, headers=_xff(IP_A)))
    _429(_enviar(client, headers=_xff(IP_A)))

    for _ in range(2):  # o cliente B, atras do mesmo proxy, nao herda o consumo de A
        _normal(_enviar(client, headers=_xff(IP_B)))
    _429(_enviar(client, headers=_xff(IP_B)))
    _normal(_enviar(client, headers=_xff(IP_C)))


def test_h2_sem_trusted_proxies_xff_forjado_nao_contorna_o_teto(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "2")
    client = abrir(IP_A)
    _normal(_enviar(client, headers=_xff(IP_B)))
    _normal(_enviar(client, headers=_xff(IP_C)))

    _429(_enviar(client, headers=_xff("203.0.113.77")))
    _429(_enviar(client))


def test_h3_par_tcp_fora_da_lista_tem_o_cabecalho_ignorado(abrir, groq, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", PROXY)
    monkeypatch.setenv(VAR_MSG_IP, "2")
    client = abrir(FORA_DA_LISTA)
    _normal(_enviar(client, headers=_xff(IP_A)))
    _normal(_enviar(client, headers=_xff(IP_B)))

    _429(_enviar(client, headers=_xff(IP_C)))


def test_h4_o_mesmo_cliente_por_dois_proxies_confiaveis_divide_o_teto(abrir, groq, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", f"{PROXY}, {PROXY2}")
    monkeypatch.setenv(VAR_MSG_IP, "2")
    por_proxy1 = abrir(PROXY)
    por_proxy2 = _outro(PROXY2)
    _normal(_enviar(por_proxy1, headers=_xff(IP_A)))
    _normal(_enviar(por_proxy2, headers=_xff(IP_A)))

    _429(_enviar(por_proxy1, headers=_xff(IP_A)))
    _429(_enviar(por_proxy2, headers=_xff(IP_A)))


def test_h5_atras_de_proxy_confiavel_cada_cliente_tem_o_seu_teto_de_sessoes(abrir, groq, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", PROXY)
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir(PROXY)
    _normal(_enviar(client, headers=_xff(IP_A)))
    _429(_enviar(client, headers=_xff(IP_A)))

    _normal(_enviar(client, headers=_xff(IP_B)))
    _429(_enviar(client, headers=_xff(IP_B)))


def test_h6_sem_trusted_proxies_xff_forjado_nao_abre_sessoes_alem_do_teto(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    client = abrir(IP_A)
    _normal(_enviar(client, headers=_xff(IP_B)))

    _429(_enviar(client, headers=_xff(IP_C)))
    _429(_enviar(client, headers=_xff("203.0.113.78")))


# =========================================================================================
# Grupo O - ordem: 429 por IP antes do teto de tokens
# =========================================================================================

def test_o1_teto_de_mensagens_do_ip_vem_antes_do_teto_de_tokens(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_MSG_IP, "1")
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _normal(_enviar(client))
    _uso(10**6)  # agora os dois tetos estao estourados
    antes = (groq.total, _estado())

    _429(_enviar(client))  # 429, nao a resposta fixa 200

    assert (groq.total, _estado()) == antes
    assert _com_budget() == []


def test_o2_teto_de_sessoes_novas_vem_antes_do_teto_de_tokens(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_SESSOES_IP, "1")
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    sid = _normal(_enviar(client))["session_id"]
    _uso(10**6)

    _429(_enviar(client))  # sessao nova acima do teto: 429
    assert _bloqueada(_enviar(client, sid=sid))["session_id"] == sid  # sessao existente: so o teto de tokens
    assert len(_com_budget()) == 1


def test_o3_teto_de_tokens_so_responde_para_quem_passou_nos_limites_por_ip(abrir, groq, monkeypatch):
    """Cada IP dentro dos seus limites recebe a resposta fixa; o IP que passou do teto de mensagens recebe 429."""
    monkeypatch.setenv(VAR_MSG_IP, "2")
    monkeypatch.setenv(VAR_TETO, "1000")
    a = abrir(IP_A)
    b = _outro(IP_B)
    _uso(1000)

    _bloqueada(_enviar(a))
    _bloqueada(_enviar(a))
    _429(_enviar(a))
    _bloqueada(_enviar(b))
    assert groq.total == 0


# =========================================================================================
# Grupo I - painel (endpoint do cartao Guardrails)
# =========================================================================================

def test_i1_vocabulario_do_painel_ganha_budget_zerado_no_banco_vazio(abrir, groq):
    client = abrir()

    metricas = _painel(client, _token_staff(client, "admin"))

    assert set(metricas["guards"]["by_type"]) == set(GUARDS_PAINEL), metricas["guards"]["by_type"]
    assert metricas["guards"] == {"total": 0, "by_type": {g: 0 for g in GUARDS_PAINEL}}, metricas["guards"]


def test_i2_contagem_de_budget_e_do_total(abrir, groq):
    client = abrir()
    for _ in range(3):
        _interacao("budget", outcome="unresolved")
    _interacao("input_injection", outcome="input_blocked")
    _interacao("no_source", outcome="unresolved")
    _interacao(None)
    _interacao("guard_desconhecido_legado")

    metricas = _painel(client, _token_staff(client, "admin"))

    esperado = {g: 0 for g in GUARDS_PAINEL}
    esperado.update({"budget": 3, "input_injection": 1, "no_source": 1})
    assert metricas["guards"] == {"total": 5, "by_type": esperado}, metricas["guards"]
    assert metricas["no_source"] == 1


@pytest.mark.parametrize("perfil, via", [("admin", "staff"), ("admin", "jwt"), ("financial", "staff"),
                                         ("financial", "jwt"), ("support", "staff"), ("support", "jwt")])
def test_i3_todos_os_perfis_internos_veem_o_mesmo_budget(abrir, groq, monkeypatch, perfil, via):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(1000)
    _bloqueada(_enviar(client))
    _bloqueada(_enviar(client))
    admin = _painel(client, _token_staff(client, "admin"))

    metricas = _painel(client, _token_staff(client, perfil, via))

    assert metricas["guards"] == admin["guards"]
    assert metricas["guards"]["by_type"]["budget"] == 2 and metricas["guards"]["total"] == 2


def test_i4_aluno_403_sem_token_401_forjado_401(abrir, groq):
    client = abrir()
    aluno = _conta("i4")
    _interacao("budget", outcome="unresolved")

    r = client.get(ROTA_PAINEL, headers=_auth(aluno.token))
    assert r.status_code == 403 and "budget" not in r.text and "guards" not in r.text
    r = client.get(ROTA_PAINEL)
    assert r.status_code == 401 and "budget" not in r.text
    r = client.get(ROTA_PAINEL, headers=_auth(_forjado("admin")))
    assert r.status_code == 401 and "budget" not in r.text


def test_i5_o_painel_nao_vaza_sessao_nem_hash_do_bloqueio(abrir, groq, monkeypatch):
    monkeypatch.setenv(VAR_TETO, "1000")
    client = abrir()
    _uso(1000)
    sid = _bloqueada(_enviar(client))["session_id"]

    r = client.get(ROTA_PAINEL, headers=_auth(_token_staff(client, "admin")))

    assert r.status_code == 200
    assert sid not in r.text and hash_da_sessao(sid) not in r.text


def test_i6_linhas_antigas_sem_guard_nao_quebram_o_painel(abrir, groq):
    """Compatibilidade: interacoes antigas (guard nulo) continuam validas e nao contam em nenhum tipo."""
    client = abrir()
    for _ in range(4):
        _interacao(None)

    metricas = _painel(client, _token_staff(client, "admin"))

    assert metricas["guards"]["total"] == 0 and metricas["guards"]["by_type"]["budget"] == 0
