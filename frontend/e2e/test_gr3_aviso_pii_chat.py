"""E2E da GR3 — aviso de dados pessoais removidos (D95, PLANO_GR seção GR3, "PII").

Contrato de tela (PLANO_GR): quando a resposta de POST /api/student/chat (Área do aluno, Angular) ou de POST /api/chat
(landing) traz `pii_masked: true`, a tela mostra AVISO_PII ([data-testid=chat-aviso-pii]) abaixo da mensagem;
com `pii_masked: false` (ou ausente) não mostra.

Escolhas de forma do teste (registradas no relatório do agente-testes):
  - Um [data-testid=chat-aviso-pii] por resposta com `pii_masked: true`; texto (espaços normalizados) exatamente
    AVISO_PII.
  - "Abaixo da mensagem": a "dona" do aviso (a última mensagem que o contém ou vem antes dele no DOM) é a mensagem do
    usuário OU a resposta do bot da MESMA troca (o PLANO não diz qual das duas), e o topo do aviso não fica acima do
    topo da dona. Uma troca seguinte sem PII não ganha aviso e não "rouba" o anterior.
  - Controle da resposta: os cenários "interceptados" usam `page.route` em POST /api/student/chat (mesma origem, via
    proxy do ng serve) ou POST /api/chat (landing, com CORS da origem estática), devolvendo o JSON escolhido pelo
    teste; assim a tela é exercitada independentemente do backend. Os cenários "ponta a ponta" vão ao backend de
    teste (eco) e conferem a GR3 inteira: o backend devolve `pii_masked: true` e o eco do bot (que repete a mensagem
    que chegou ao LLM) não traz o CPF cru.
  - Mensagens do Angular: [data-testid=chat-message] (data-role user/assistant, E5); landing: `#chat-messages .msg`
    (`.msg-user` / `.msg-bot`, E6).

Harness: `apoio_harness_f5b.ambiente_f5b(..., knowledge={})` (backend D58 + catálogo do bot temporário vazio + Groq
falso que ecoa "Resposta simulada do assistente a: <mensagem>"; KNOWLEDGE_DIR vazia, backend/knowledge não é lido).
Angular: `ng serve` com proxy. Landing: servidor estático do helper da E6 (`_servidor_da_landing`).

Cenários — Área do aluno (test_gr3_aviso_pii_area_do_aluno):
  P0 pré-condição: aluno entra, pergunta comum respondida sem chat-aviso-pii                      [passa no red]
  P1 resposta interceptada com pii_masked: true -> um aviso com AVISO_PII abaixo da troca
  P2 resposta interceptada com pii_masked: false -> nenhum aviso novo (continua um, ligado à P1)
  P3 ponta a ponta: CPF na mensagem -> backend devolve pii_masked: true, o eco não traz o CPF cru, novo aviso
  P4 recarregar /student: o histórico (do banco) não mostra o CPF cru da P3
  P5 sem erros de console de /api nem exceções de página
Cenários — landing (test_gr3_aviso_pii_landing):
  L0 pré-condição: pergunta comum respondida sem chat-aviso-pii                                   [passa no red]
  L1 resposta interceptada com pii_masked: true -> um aviso com AVISO_PII abaixo da troca
  L2 resposta interceptada com pii_masked: false -> nenhum aviso novo
  L3 ponta a ponta: CPF na mensagem -> backend devolve pii_masked: true, o eco não traz o CPF cru, novo aviso
  L4 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_gr3_aviso_pii_chat.py -s
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import SENHA_ALUNO, ambiente_f5b, semear_aluno  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_AVISO = '[data-testid="chat-aviso-pii"]'
SEL_LANDING_MSG = "#chat-messages .msg"
SEL_LANDING_BOT = "#chat-messages .msg-bot"
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "

AVISO_PII = (
    "Para sua segurança, removemos dados pessoais (CPF, cartão, telefone ou e-mail) da sua mensagem antes de "
    "enviá-la ao assistente."
)
PERGUNTA_NEUTRA = "Recomenda leituras introdutorias?"
PERGUNTA_P1 = "Meu CPF e 529.982.247-25, recomenda leituras?"
RESPOSTA_P1 = "Resposta interceptada GR3 com dado removido"
PERGUNTA_P2 = "Recomenda leituras avancadas?"
RESPOSTA_P2 = "Resposta interceptada GR3 sem dado pessoal"
CPF_P3 = "111.444.777-35"
PERGUNTA_P3 = f"Recomenda leituras introdutorias? Meu CPF e {CPF_P3}"
CRUS_P3 = (CPF_P3, "11144477735", "444.777")

# JS: para cada aviso, a última mensagem que o contém ou vem antes dele no DOM (a "dona"), e se o topo do aviso não
# fica acima do topo da dona. Também devolve as mensagens (papel e texto) para o Python localizar a troca.
_AVISOS_JS = """([selMsg, selAviso]) => {
  const msgs = [...document.querySelectorAll(selMsg)];
  const avisos = [...document.querySelectorAll(selAviso)].map(a => {
    let dona = -1;
    msgs.forEach((m, i) => {
      if (m.contains(a) || (m.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) dona = i;
    });
    const ra = a.getBoundingClientRect();
    const rm = dona >= 0 ? msgs[dona].getBoundingClientRect() : null;
    return {texto: a.innerText, dona, abaixo: !!rm && ra.top >= rm.top - 1};
  });
  return {avisos, msgs: msgs.map(m => ({papel: m.getAttribute('data-role') || m.className, texto: m.innerText}))};
}"""


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _eh_usuario(papel):
    return papel == "user" or "msg-user" in (papel or "")


def _eh_bot(papel):
    return papel == "assistant" or "msg-bot" in (papel or "")


def _troca(msgs, pergunta):
    """Índices (usuário, bot) da última troca cuja mensagem do usuário contém `pergunta`."""
    usuario = max((i for i, m in enumerate(msgs) if _eh_usuario(m["papel"]) and pergunta in m["texto"]), default=-1)
    if usuario < 0:
        return -1, -1
    bot = next((i for i in range(usuario + 1, len(msgs)) if _eh_bot(msgs[i]["papel"])), -1)
    return usuario, bot


def _exigir_avisos(page, sel_msg, trocas, rotulo, espera=6):
    """Exatamente len(trocas) avisos, cada um com AVISO_PII, abaixo da troca correspondente (na ordem)."""
    fim = time.time() + espera
    while time.time() < fim and page.locator(SEL_AVISO).count() < len(trocas):
        page.wait_for_timeout(150)
    page.wait_for_timeout(300)
    estado = page.evaluate(_AVISOS_JS, [sel_msg, SEL_AVISO])
    avisos, msgs = estado["avisos"], estado["msgs"]
    if len(avisos) != len(trocas):
        raise Falha(f"{rotulo}: esperava {len(trocas)} [data-testid=chat-aviso-pii], há {len(avisos)}")
    for aviso, pergunta in zip(avisos, trocas):
        if _normalizar(aviso["texto"]) != AVISO_PII:
            raise Falha(f"{rotulo}: chat-aviso-pii com texto {_normalizar(aviso['texto'])!r}, esperado {AVISO_PII!r}")
        usuario, bot = _troca(msgs, pergunta)
        if usuario < 0:
            raise Falha(f"{rotulo}: a mensagem do usuário {pergunta[:40]!r} não está na tela")
        if aviso["dona"] not in (usuario, bot):
            raise Falha(f"{rotulo}: o aviso não está abaixo da troca de {pergunta[:40]!r} "
                        f"(dona {aviso['dona']}, troca {usuario}/{bot})")
        if not aviso["abaixo"]:
            raise Falha(f"{rotulo}: o aviso aparece acima da mensagem")


class Interceptador:
    """Resposta controlada pelo teste para o POST do chat; None deixa a requisição ir ao backend de teste."""

    def __init__(self, cors_origem=None):
        self.resposta = None
        self.cabecalhos = {}
        if cors_origem:
            self.cabecalhos = {
                "Access-Control-Allow-Origin": cors_origem,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }

    def __call__(self, rota):
        if self.resposta is None:
            rota.continue_()
        elif rota.request.method == "OPTIONS":
            rota.fulfill(status=204, headers=self.cabecalhos, body="")
        elif rota.request.method == "POST":
            rota.fulfill(status=200, headers=dict(self.cabecalhos, **{"Content-Type": "application/json"}),
                         body=json.dumps(self.resposta, ensure_ascii=False))
        else:
            rota.continue_()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _rodar(resultados, codigo, nome, funcao, pre=None):
    try:
        if pre:
            pre()
        funcao()
        resultados.append((codigo, nome, True, ""))
        print(f"[PASS] {codigo} {nome}")
    except Exception as erro:
        linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
        resultados.append((codigo, nome, False, linha))
        print(f"[FAIL] {codigo} {nome} -> {linha}")


# =========================================================================================
# Área do aluno (Angular)
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_angular():
    with ambiente_f5b("gr3_angular", knowledge={}) as ambiente:
        yield ambiente


def _rota_do_chat_do_aluno(url):
    return urlsplit(url).path.rstrip("/") == "/api/student/chat"


def test_gr3_aviso_pii_area_do_aluno(servidores_angular, browser):
    base = servidores_angular["base"]
    resultados, erros_console, contextos = [], [], []
    estado = {}
    interceptar = Interceptador()

    seed = {"ok": False, "erro": ""}
    try:
        email, _ = semear_aluno(servidores_angular["db_path"], "gr3")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def exigir_seed():
        if not seed["ok"]:
            raise Falha(f"seed falhou: {seed['erro']}")

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros_console.append(f"{msg.text[:120]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        page.route(_rota_do_chat_do_aluno, interceptar)
        return page

    def entrar_no_student():
        page = nova_pagina()
        page.goto(base + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA_ALUNO, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /student (URL {page.url})")
        page.wait_for_load_state("networkidle")
        try:
            page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("[data-testid=chat-panel] não está visível em /student")
        return page

    def pagina():
        if "page" not in estado:
            estado["page"] = entrar_no_student()
        return estado["page"]

    def enviar(texto, esperado_no_bot, rotulo):
        page = pagina()
        antes = page.locator(SEL_MENSAGEM).count()
        with page.expect_response(
            lambda r: r.request.method == "POST" and _rota_do_chat_do_aluno(r.url), timeout=TIMEOUT * 2,
        ) as info:
            page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
            page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        dados = info.value.json()
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and esperado_no_bot in msgs[-1]["text"]:
                page.wait_for_timeout(400)
                return dados, msgs[-1]["text"]
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def p0():
        dados, _ = enviar(PERGUNTA_NEUTRA, PREFIXO_RESPOSTA, "P0")
        if dados.get("pii_masked") not in (False, None):
            raise Falha(f"P0: pré-condição: pergunta comum sem PII ({dados.get('pii_masked')!r})")
        if pagina().locator(SEL_AVISO).count():
            raise Falha("P0: resposta sem PII mostrou [data-testid=chat-aviso-pii]")

    def p1():
        interceptar.resposta = {"status": "success", "message": RESPOSTA_P1, "actions": [], "sources": [],
                                "pii_masked": True}
        try:
            enviar(PERGUNTA_P1, RESPOSTA_P1, "P1")
        finally:
            interceptar.resposta = None
        _exigir_avisos(pagina(), SEL_MENSAGEM, [PERGUNTA_P1], "P1")
        estado["p1"] = True

    def p2():
        if not estado.get("p1"):
            raise Falha("P2 depende de P1")
        interceptar.resposta = {"status": "success", "message": RESPOSTA_P2, "actions": [], "sources": [],
                                "pii_masked": False}
        try:
            enviar(PERGUNTA_P2, RESPOSTA_P2, "P2")
        finally:
            interceptar.resposta = None
        _exigir_avisos(pagina(), SEL_MENSAGEM, [PERGUNTA_P1], "P2")

    def p3():
        dados, texto_bot = enviar(PERGUNTA_P3, PREFIXO_RESPOSTA, "P3")
        if dados.get("pii_masked") is not True:
            raise Falha(f"P3: o backend devolveu pii_masked={dados.get('pii_masked')!r} para mensagem com CPF")
        for cru in CRUS_P3:
            if cru in texto_bot or cru in (dados.get("message") or ""):
                raise Falha(f"P3: o CPF cru chegou ao LLM (o eco do bot traz {cru!r})")
        trocas = [PERGUNTA_P1, PERGUNTA_P3] if estado.get("p1") else [PERGUNTA_P3]
        _exigir_avisos(pagina(), SEL_MENSAGEM, trocas, "P3")

    def p4():
        page = pagina()
        page.reload(wait_until="networkidle")
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        fim = time.time() + 8
        while time.time() < fim and page.locator(SEL_MENSAGEM).count() == 0:
            page.wait_for_timeout(150)
        textos = page.locator(SEL_MENSAGEM).all_inner_texts()
        if not textos:
            raise Falha("P4: o histórico não voltou depois de recarregar")
        if not any("Recomenda leituras introdutorias? Meu CPF e" in t for t in textos):
            raise Falha("P4: a mensagem da P3 não voltou no histórico")
        for cru in CRUS_P3:
            if any(cru in t for t in textos):
                raise Falha(f"P4: o histórico gravado mostra o CPF cru ({cru!r})")

    def p5():
        if erros_console:
            raise Falha(f"P5: erros de console: {erros_console[:3]}")

    try:
        _rodar(resultados, "P0", "pré-condição: pergunta comum sem chat-aviso-pii", p0, exigir_seed)
        _rodar(resultados, "P1", "pii_masked: true (interceptado) mostra AVISO_PII abaixo da troca", p1, exigir_seed)
        _rodar(resultados, "P2", "pii_masked: false (interceptado) não mostra aviso novo", p2, exigir_seed)
        _rodar(resultados, "P3", "ponta a ponta: CPF mascarado no backend e aviso na tela", p3, exigir_seed)
        _rodar(resultados, "P4", "histórico recarregado sem o CPF cru", p4, exigir_seed)
        _rodar(resultados, "P5", "sem erros de console de /api nem exceções de página", p5)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR3 Área do aluno: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)


# =========================================================================================
# Landing estática
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    origem = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("gr3_landing", cors_origin=origem, angular=False, knowledge={}) as ambiente:
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, origem=origem, landing=origem + "/landing_global_training.html")
        finally:
            estatico.shutdown()
            estatico.server_close()


class Visitante:
    def __init__(self, browser, servidores):
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        self.interceptar = Interceptador(servidores["origem"])
        self.contexto.route(f"{servidores['api']}/api/chat", self.interceptar)
        self.page = self.contexto.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))
        self.page.goto(servidores["landing"], wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto, esperado_no_bot, resposta=None):
        self.interceptar.resposta = resposta
        try:
            if not self.page.locator("#chat-bubble.open").count():
                self.page.locator("#chat-btn").click(timeout=TIMEOUT)
            campo = self.page.locator("#chat-input")
            campo.fill(texto, timeout=TIMEOUT)
            with self.page.expect_response(
                lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/chat"), timeout=TIMEOUT,
            ) as info:
                campo.press("Enter")
            dados = info.value.json()
        finally:
            self.interceptar.resposta = None
        fim = time.time() + 8
        while time.time() < fim:
            textos = self.page.locator(SEL_LANDING_BOT).all_inner_texts()
            if textos and esperado_no_bot in textos[-1]:
                self.page.wait_for_timeout(400)
                return dados, textos[-1]
            self.page.wait_for_timeout(100)
        raise Falha("a resposta do bot não apareceu na landing")

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


def _sucesso(mensagem, pii_masked):
    return {"status": "success", "message": mensagem, "session_id": "0" * 32, "actions": [], "sources": [],
            "pii_masked": pii_masked}


def test_gr3_aviso_pii_landing(servidores_landing, browser):
    v = Visitante(browser, servidores_landing)
    resultados, estado = [], {}

    def l0():
        dados, _ = v.enviar(PERGUNTA_NEUTRA, PREFIXO_RESPOSTA + PERGUNTA_NEUTRA)
        if dados.get("status") != "success" or dados.get("pii_masked") not in (False, None):
            raise Falha(f"L0: pré-condição: resposta comum sem PII ({dados})")
        if v.page.locator(SEL_AVISO).count():
            raise Falha("L0: resposta sem PII mostrou [data-testid=chat-aviso-pii]")

    def l1():
        v.enviar(PERGUNTA_P1, RESPOSTA_P1, _sucesso(RESPOSTA_P1, True))
        _exigir_avisos(v.page, SEL_LANDING_MSG, [PERGUNTA_P1], "L1")
        estado["l1"] = True

    def l2():
        if not estado.get("l1"):
            raise Falha("L2 depende de L1")
        v.enviar(PERGUNTA_P2, RESPOSTA_P2, _sucesso(RESPOSTA_P2, False))
        _exigir_avisos(v.page, SEL_LANDING_MSG, [PERGUNTA_P1], "L2")

    def l3():
        dados, texto_bot = v.enviar(PERGUNTA_P3, PREFIXO_RESPOSTA)
        if dados.get("pii_masked") is not True:
            raise Falha(f"L3: o backend devolveu pii_masked={dados.get('pii_masked')!r} para mensagem com CPF")
        for cru in CRUS_P3:
            if cru in texto_bot or cru in (dados.get("message") or ""):
                raise Falha(f"L3: o CPF cru chegou ao LLM (o eco do bot traz {cru!r})")
        trocas = [PERGUNTA_P1, PERGUNTA_P3] if estado.get("l1") else [PERGUNTA_P3]
        _exigir_avisos(v.page, SEL_LANDING_MSG, trocas, "L3")

    def l4():
        if v.erros:
            raise Falha(f"L4: erros de console: {v.erros[:3]}")

    try:
        _rodar(resultados, "L0", "pré-condição: pergunta comum sem chat-aviso-pii", l0)
        _rodar(resultados, "L1", "pii_masked: true (interceptado) mostra AVISO_PII abaixo da troca", l1)
        _rodar(resultados, "L2", "pii_masked: false (interceptado) não mostra aviso novo", l2)
        _rodar(resultados, "L3", "ponta a ponta: CPF mascarado no backend e aviso na tela", l3)
        _rodar(resultados, "L4", "sem erros de console nem exceções de página", l4)
    finally:
        v.fechar()

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR3 landing: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
