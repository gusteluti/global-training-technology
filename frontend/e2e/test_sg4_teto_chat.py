"""E2E da SG4 (D109 P5; PLANO_SG, secao SG4) - teto diario de tokens do chat anonimo na landing e no painel.

Contrato de tela (PLANO_SG/SG4, decisoes do PM na D109; o texto e o rotulo sao exatos):
  - Teto estourado (`CHAT_ANON_DAILY_TOKEN_BUDGET` ligado e soma anonima do dia de Sao Paulo >= teto): a landing mostra,
    no balao do bot, o texto fixo
        "O assistente está com muitas conversas agora. Fale com a nossa equipe pelo WhatsApp ou tente de novo amanhã."
    e o botao/link de WhatsApp da F6 ([data-testid=chat-acao-whatsapp], label `Falar com um atendente no WhatsApp`,
    href `https://wa.me/<numero>?text=<texto>`, target=_blank, rel noopener noreferrer). O servidor nao chama o LLM.
  - Painel (Gestao e Suporte, que ja veem o cartao): no cartao "Guardrails" da aba Observabilidade de IA, a linha
    "Teto diário atingido" com a contagem de `guards.by_type.budget` em [data-testid=obs-guard-budget] (mesmo padrao dos
    outros tipos: `obs-guard-<tipo>`); `obs-guard-total` passa a incluir `budget`.
  - Sem teto (variavel ausente/vazia = desligado), o chat da landing responde normalmente [guarda].

Harness (D58, padrao do `servidor_e2e_h1`): DOIS backends de teste, cada um com banco SQLite temporario, cursos
temporarios, Groq falso (duble da E7) e Mercado Pago falso, e numero de WhatsApp FABRICADO (5511900000000):
  - backend "com teto": `CHAT_ANON_DAILY_TOKEN_BUDGET=5000`, uso anonimo de 5000 tokens SEMEADO hoje em `ai_usage`
    (soma >= teto) + `ng serve` para o painel;
  - backend "sem teto": variavel vazia, mesmo uso gigante semeado, so a landing (nao precisa de `ng serve`).
A landing e servida pelo helper da E6 (`_servidor_da_landing`: copia em memoria com BACKEND_URL trocado, em 127.0.0.1; o
arquivo da landing nao e alterado) e a origem dela entra no CORS do backend de teste (junto com a do `ng serve`, quando
ha). Nada toca db.sqlite.

Cenarios:
  L0 [guarda] sem teto, a landing responde normalmente (texto do duble), sem link de WhatsApp e sem linha `budget`
  L1 com teto estourado: texto fixo exato no balao do bot + 1 link de WhatsApp correto; resposta 200 `success`
  L2 segunda mensagem da mesma aba: continua barrada, mesmo session_id, e o duble do Groq continua sem ser chamado
  P1 Gestao: no cartao Guardrails, a linha "Teto diário atingido" com a mesma contagem da API (>= 3) e o total igual
  P2 Suporte: o mesmo
  K1 sem erros de console nem excecoes de pagina (landing e painel)

Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_sg4_teto_chat.py -s
"""

import contextlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f6 import LABEL_WHATSAPP, conferir_atributos, conferir_link_whatsapp  # noqa: E402
from servidor_e2e_e7 import TEXTO_RESPOSTA  # noqa: E402
from servidor_e2e_f6 import NUMERO_FABRICADO  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA  # noqa: E402
from test_e5_chat_aluno_angular import (  # noqa: E402
    FRONTEND, REPO, _api, _encerrar, _esperar_http, _iniciar, _porta_livre,
)
from test_e6_landing_chat import _servidor_da_landing  # noqa: E402
from test_e7_observabilidade_angular import abrir_aba_ia, so_digitos, texto_do_testid  # noqa: E402

TIMEOUT = 8000
ORCAMENTO = 5000
CHAT_INDISPONIVEL = (
    "O assistente está com muitas conversas agora. Fale com a nossa equipe pelo WhatsApp ou tente de novo amanhã."
)
ROTULO_BUDGET = "Teto diário atingido"
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"
SEL_BOT = "#chat-messages .msg-bot"
SEL_WHATSAPP = '[data-testid="chat-acao-whatsapp"]'
CAMINHO_PAINEL = "/api/dashboard/observabilidade-ia"
ERRO_HTTP = re.compile(r"status of (\d{3})")

# Erros de console e excecoes de pagina de todos os cenarios (conferidos em K1, o ultimo).
ERROS_DE_PAGINA = []


# =========================================================================================
# Ambiente: backend de teste (H1) com variaveis do SG4 + origem da landing (+ ng serve opcional)
# =========================================================================================

@contextlib.contextmanager
def ambiente_sg4(prefixo, *, teto, angular, variavel_porta, variavel_landing):
    tmp = Path(tempfile.mkdtemp(prefix=f"gt_e2e_{prefixo}_"))
    porta_api = _porta_livre(variavel_porta)
    api = f"http://127.0.0.1:{porta_api}"
    porta_landing = _porta_livre(variavel_landing)
    origem_landing = f"http://127.0.0.1:{porta_landing}"
    origens = [origem_landing]
    base = None
    if angular:
        porta_web = _porta_livre("E2E_FRONT_PORT")
        base = f"http://localhost:{porta_web}"
        origens.insert(0, base)
    db_path = tmp / "db.sqlite"
    cursos_tmp = tmp / "courses"
    log_api = tmp / "backend.log"
    # Variaveis definidas a forca no processo do backend (inclusive vazias): um backend/.env nao as sobrescreve.
    env_api = dict(
        os.environ,
        CHAT_ANON_DAILY_TOKEN_BUDGET=str(teto) if teto else "",
        CHAT_ANON_DAILY_MESSAGES_PER_IP="",
        CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR="",
        WHATSAPP_HANDOFF_NUMBER=NUMERO_FABRICADO if teto else "",
        TRUSTED_PROXIES="",
    )
    processos, arquivos = [], []
    estatico = None
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_h1.py"), "--port", str(porta_api),
             "--db-path", str(db_path), "--outbox", str(tmp / "outbox.jsonl"),
             "--courses-dir", str(cursos_tmp), "--cors-origin", ",".join(origens)],
            arq_api, REPO / "backend", env=env_api,
        )
        processos.append(backend)
        _esperar_http(api + "/health", 90, backend, "backend de teste", log_api)
        estatico = _servidor_da_landing(porta_landing, api)

        if angular:
            log_web = tmp / "ng_serve.log"
            proxy = tmp / "proxy.e2e.json"
            proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}),
                             encoding="utf-8")
            arq_web = open(log_web, "wb")
            arquivos.append(arq_web)
            env_web = dict(os.environ, NG_CLI_ANALYTICS="false", NO_COLOR="1")
            comando_ng = f'npx ng serve --port {porta_web} --proxy-config "{proxy}"'
            front = _iniciar(comando_ng, arq_web, FRONTEND, env=env_web, shell=True)
            processos.append(front)
            _esperar_http(base + "/", int(os.environ.get("E2E_NG_TIMEOUT", "300")), front, "ng serve", log_web)

        yield {"base": base, "api": api, "db_path": db_path, "tmp": tmp,
               "landing": origem_landing + "/landing_global_training.html"}
    finally:
        if estatico is not None:
            estatico.shutdown()
            estatico.server_close()
        for processo in reversed(processos):
            _encerrar(processo)
        for arquivo in arquivos:
            try:
                arquivo.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _semear_uso_anonimo(db_path, tokens):
    """Uso anonimo de hoje (created_at = agora, UTC, padrao do banco): soma do dia de SP >= teto."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ai_usage (channel, user_id, session_hash, call_type, model, prompt_tokens, completion_tokens, "
            "total_tokens, cost_usd, latency_ms, status) VALUES ('anonymous', NULL, 'semente-sg4', 'answer', "
            "'modelo-seed', ?, 0, ?, 0, 10, 'ok')", (tokens, tokens))
        conn.commit()
    finally:
        conn.close()


def _linhas_budget(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM ai_interactions WHERE guard = 'budget'").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def com_teto():
    with ambiente_sg4("sg4_teto", teto=ORCAMENTO, angular=True, variavel_porta="E2E_BACKEND_PORT",
                      variavel_landing="E2E_LANDING_PORT") as ambiente:
        _semear_uso_anonimo(ambiente["db_path"], ORCAMENTO)
        yield ambiente


@pytest.fixture(scope="module")
def sem_teto():
    with ambiente_sg4("sg4_sem_teto", teto=None, angular=False, variavel_porta="E2E_BACKEND_SEM_TETO_PORT",
                      variavel_landing="E2E_LANDING_SEM_TETO_PORT") as ambiente:
        _semear_uso_anonimo(ambiente["db_path"], 10**7)  # uso gigante: so um teto LIGADO bloquearia
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


# =========================================================================================
# Landing (estatica, servida em 127.0.0.1 pelo helper da E6; a origem esta no CORS do backend de teste)
# =========================================================================================

class Visitante:
    def __init__(self, browser, ambiente):
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        self.page = self.contexto.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))
        self.page.goto(ambiente["landing"], wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto):
        if not self.page.locator("#chat-bubble.open").count():
            self.page.locator("#chat-btn").click(timeout=TIMEOUT)
        campo = self.page.locator("#chat-input")
        campo.fill(texto, timeout=TIMEOUT)
        with self.page.expect_response(
            lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/chat"), timeout=TIMEOUT,
        ) as info:
            campo.press("Enter")
        dados = info.value.json()
        fim = time.time() + 8
        while time.time() < fim:
            textos = self.page.locator(SEL_BOT).all_inner_texts()
            if textos and "Processando" not in textos[-1]:
                break
            self.page.wait_for_timeout(100)
        self.page.wait_for_timeout(300)
        return dados

    def textos_do_bot(self):
        return [" ".join(t.split()) for t in self.page.locator(SEL_BOT).all_inner_texts()]

    def links(self):
        alvo = self.page.locator(SEL_WHATSAPP)
        return [{"texto": " ".join(alvo.nth(i).inner_text().split()), "href": alvo.nth(i).get_attribute("href"),
                 "target": alvo.nth(i).get_attribute("target"), "rel": alvo.nth(i).get_attribute("rel")}
                for i in range(alvo.count())]

    def fechar(self):
        ERROS_DE_PAGINA.extend(f"landing: {e}" for e in self.erros)
        try:
            self.contexto.close()
        except Exception:
            pass


@pytest.fixture
def visitante(browser):
    criados = []

    def novo(ambiente):
        v = Visitante(browser, ambiente)
        criados.append(v)
        return v

    try:
        yield novo
    finally:
        for v in criados:
            v.fechar()


# =========================================================================================
# Cenarios da landing
# =========================================================================================

def test_l0_guarda_sem_teto_a_landing_responde_normalmente(sem_teto, visitante):
    v = visitante(sem_teto)

    dados = v.enviar(PERGUNTA_GERAL)

    assert dados.get("status") == "success", dados
    assert dados.get("message") != CHAT_INDISPONIVEL and TEXTO_RESPOSTA in dados.get("message", ""), dados
    textos = v.textos_do_bot()
    assert any(TEXTO_RESPOSTA in t for t in textos), textos
    assert not any(CHAT_INDISPONIVEL in t for t in textos), textos
    assert v.links() == [], "sem teto e sem numero configurado, nao ha link de WhatsApp"
    assert _linhas_budget(sem_teto["db_path"]) == 0


def test_l1_teto_estourado_a_landing_mostra_o_texto_fixo_e_o_botao_de_whatsapp(com_teto, visitante):
    v = visitante(com_teto)

    dados = v.enviar(PERGUNTA_GERAL)

    assert dados.get("status") == "success" and dados.get("message") == CHAT_INDISPONIVEL, dados
    textos = v.textos_do_bot()
    assert any(CHAT_INDISPONIVEL in t for t in textos), f"o balao do bot deve mostrar o texto fixo: {textos}"
    assert not any(TEXTO_RESPOSTA in t for t in textos), f"o duble do LLM nao pode ter respondido: {textos}"
    links = v.links()
    assert len(links) == 1, f"esperava 1 [data-testid=chat-acao-whatsapp], ha {len(links)}: {links}"
    assert links[0]["texto"] == LABEL_WHATSAPP, links[0]
    problema = conferir_link_whatsapp(links[0]["href"], "os cursos")
    assert not problema, problema
    problema = conferir_atributos(links[0]["target"], links[0]["rel"])
    assert not problema, problema
    assert _linhas_budget(com_teto["db_path"]) >= 1


def test_l2_segunda_mensagem_continua_barrada_na_mesma_sessao(com_teto, visitante):
    v = visitante(com_teto)

    primeira = v.enviar(PERGUNTA_GERAL)
    segunda = v.enviar("Pode me indicar um curso?")

    assert primeira.get("message") == CHAT_INDISPONIVEL and segunda.get("message") == CHAT_INDISPONIVEL
    assert primeira.get("session_id") and primeira["session_id"] == segunda.get("session_id")
    textos = v.textos_do_bot()
    assert sum(CHAT_INDISPONIVEL in t for t in textos) == 2, textos
    assert not any(TEXTO_RESPOSTA in t for t in textos), textos


# =========================================================================================
# Cenarios do painel (cartao Guardrails)
# =========================================================================================

def _token(api, email, senha):
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": email, "password": senha})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise RuntimeError(f"seed: login por API de {email} respondeu HTTP {status}")
    return corpo["access_token"]


def _metricas(api, email, senha):
    status, corpo = _api(api, "GET", CAMINHO_PAINEL, token=_token(api, email, senha))
    assert status == 200, f"GET {CAMINHO_PAINEL} respondeu HTTP {status}"
    return corpo["metrics"]


def _semear_bloqueios(db_path, quantos):
    """Linhas de ai_interactions com guard='budget' (como as que o chat grava), para o painel nao depender da landing."""
    conn = sqlite3.connect(str(db_path))
    try:
        for i in range(quantos):
            conn.execute(
                "INSERT INTO ai_interactions (channel, user_id, session_hash, course_id, outcome, topic, guard) "
                "VALUES ('anonymous', NULL, ?, NULL, 'unresolved', NULL, 'budget')", (f"semente-sg4-{i:04d}",))
        conn.commit()
    finally:
        conn.close()


def _abrir_painel(browser, com_teto, email, senha, rotulo):
    contexto = browser.new_context(viewport={"width": 1366, "height": 900})
    page = contexto.new_page()

    def ao_console(msg):
        if msg.type != "error":
            return
        m = ERRO_HTTP.search(msg.text)
        url = msg.location.get("url") or ""
        if m and (int(m.group(1)) == 400 or int(m.group(1)) >= 500 or (int(m.group(1)) == 404 and "/api/" in url)):
            ERROS_DE_PAGINA.append(f"{rotulo}: {msg.text[:120]} [{url}]")

    page.on("console", ao_console)
    page.on("pageerror", lambda e: ERROS_DE_PAGINA.append(f"{rotulo}: exceção de página: {e}"[:200]))
    abrir_aba_ia(page, com_teto["base"], email, senha, rotulo)
    return contexto, page


def _conferir_linha_do_teto(page, metricas, rotulo):
    cartao = page.locator('[data-testid="obs-guardrails"]')
    cartao.first.wait_for(state="visible", timeout=TIMEOUT)
    assert "Guardrails" in cartao.first.inner_text(), f"{rotulo}: o cartão não tem o título 'Guardrails'"
    assert ROTULO_BUDGET in cartao.first.inner_text(), \
        f"{rotulo}: o cartão Guardrails não tem a linha {ROTULO_BUDGET!r}: {cartao.first.inner_text()[:400]!r}"
    linhas = cartao.first.locator("tr", has_text=ROTULO_BUDGET)
    assert linhas.count() == 1, f"{rotulo}: esperava 1 linha {ROTULO_BUDGET!r}, há {linhas.count()}"
    esperado = metricas["guards"]["by_type"]["budget"]
    mostrado = texto_do_testid(page, '[data-testid="obs-guard-budget"]', rotulo)
    assert so_digitos(mostrado) == str(esperado), f"{rotulo}: obs-guard-budget mostra {mostrado!r}, a API tem {esperado}"
    assert linhas.first.locator('[data-testid="obs-guard-budget"]').count() == 1, \
        f"{rotulo}: a contagem do teto deve estar na linha {ROTULO_BUDGET!r}"
    total = texto_do_testid(page, '[data-testid="obs-guard-total"]', rotulo)
    assert so_digitos(total) == str(metricas["guards"]["total"]), \
        f"{rotulo}: obs-guard-total mostra {total!r}, a API tem {metricas['guards']['total']}"
    for proibido in ("NaN", "null", "undefined"):
        assert proibido not in cartao.first.inner_text(), f"{rotulo}: o cartão mostra {proibido!r}"


def test_p1_gestao_ve_a_linha_teto_diario_atingido_com_a_contagem(com_teto, browser):
    _semear_bloqueios(com_teto["db_path"], 3)  # somam-se as da landing (L1, L2): a contagem e >= 3
    metricas = _metricas(com_teto["api"], GESTAO_EMAIL, GESTAO_SENHA)
    assert metricas["guards"]["by_type"]["budget"] >= 3, \
        f"pré-condição: a API deve contar as respostas barradas em guards.by_type.budget: {metricas['guards']}"

    contexto, page = _abrir_painel(browser, com_teto, GESTAO_EMAIL, GESTAO_SENHA, "Gestão")
    try:
        _conferir_linha_do_teto(page, metricas, "Gestão")
    finally:
        contexto.close()


def test_p2_suporte_ve_a_mesma_linha(com_teto, browser):
    metricas = _metricas(com_teto["api"], SUPORTE_EMAIL, SUPORTE_SENHA)
    assert metricas["guards"]["by_type"]["budget"] >= 3, metricas["guards"]

    contexto, page = _abrir_painel(browser, com_teto, SUPORTE_EMAIL, SUPORTE_SENHA, "Suporte")
    try:
        _conferir_linha_do_teto(page, metricas, "Suporte")
    finally:
        contexto.close()


def test_k1_sem_erros_de_console_nem_excecoes_de_pagina(com_teto):
    assert ERROS_DE_PAGINA == [], f"{len(ERROS_DE_PAGINA)} erro(s): " + " | ".join(ERROS_DE_PAGINA[:4])
