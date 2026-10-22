"""E2E da GR1 — "Fonte: <título>" abaixo da resposta do bot (D95, PLANO_GR secao GR1, "Tela").

Contrato de tela (PLANO_GR): abaixo da resposta do bot, "Fonte: <título>" ([data-testid=chat-fonte]) na Área do
aluno e na landing. O título vem de `sources` da resposta (POST /api/student/chat e POST /api/chat); resposta com
`sources: []` não ganha fonte. O histórico guarda só o texto (a fonte não volta ao recarregar /student).

Escolhas de forma do teste (registradas no relatório do agente-testes):
  - Um elemento [data-testid=chat-fonte] por resposta com fonte; com uma fonte só, o texto (espaços normalizados) é
    exatamente "Fonte: <título>".
  - "Abaixo da resposta": o chat-fonte está DENTRO do balão da resposta do bot ou DEPOIS dele no DOM, sem nenhuma
    mensagem (do usuário ou do bot) entre os dois, e o topo dele não fica acima do topo do balão.
  - Na Área do aluno as mensagens são [data-testid=chat-message] (data-role user/assistant, E5); na landing são
    `#chat-messages .msg` (`.msg-bot` / `.msg-user`, E6).

Harness: `apoio_harness_f5b.ambiente_f5b(..., knowledge=BASE)` (backend do D58 + catálogo do bot temporário + Groq
falso que ecoa "Resposta simulada do assistente a: <mensagem>"), com a base institucional de fixture gravada em
<tmp>/knowledge e KNOWLEDGE_DIR passada só ao processo do backend. Angular: `ng serve` com proxy. Landing: servidor
estático do helper da E6 (`_servidor_da_landing`) com CORS para a origem dele. backend/knowledge não é lido.

Cenários — Área do aluno (test_gr1_fonte_area_do_aluno):
  A0 pré-condição: aluno entra, pergunta comum é respondida sem chat-fonte                        [passa no red]
  A1 pergunta sobre cancelamento: um chat-fonte "Fonte: Cancelamento e reembolso" abaixo da resposta
  A2 pergunta comum em seguida: a resposta nova não ganha fonte (continua uma só, ligada à anterior)
  A3 recarregar /student: o histórico volta sem chat-fonte (a fonte não é persistida)              [passa no red]
  A4 sem erros de console de /api nem exceções de página
Cenários — landing (test_gr1_fonte_landing):
  L0 pré-condição: pergunta comum respondida sem chat-fonte                                       [passa no red]
  L1 pergunta sobre cancelamento: um chat-fonte "Fonte: Cancelamento e reembolso" abaixo da resposta
  L2 pergunta comum em seguida: continua uma fonte só, ligada à resposta anterior
  L3 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_gr1_fonte_chat_angular.py -s
"""

import re
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import SENHA_ALUNO, ambiente_f5b, semear_aluno  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_FONTE = '[data-testid="chat-fonte"]'
SEL_LANDING_MSG = "#chat-messages .msg"
SEL_LANDING_BOT = "#chat-messages .msg-bot"
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "

TITULO = "Cancelamento e reembolso"
TEXTO_FONTE = f"Fonte: {TITULO}"
FONTE = {"id": "cancelamento", "title": TITULO}
PERGUNTA_CANCELAMENTO = "Quero fazer o cancelamento da minha matricula"
PERGUNTA_NEUTRA = "Recomenda leituras introdutorias?"  # sem tema de política e sem token da base

BASE = {
    "cancelamento.md": f"""---
id: cancelamento
titulo: {TITULO}
visibilidade: publico
---

## Pedido de cancelamento
O cancelamento da matricula e pedido pela Area do aluno em ate 7 dias da aprovacao (ref GR1E2E7731).
O financeiro analisa cada pedido de cancelamento antes de concluir.
""",
    "certificado.md": """---
id: certificado
titulo: Certificado de conclusão
visibilidade: publico
---

## Emissao do certificado
O certificado sai em PDF depois que o aluno conclui todos os materiais, com codigo de validacao.

## Natureza do certificado
E um certificado de curso livre, sem valor de diploma do MEC.
""",
    # Documentos a mais só para o corpus ter trechos suficientes: com 2 ou 3 trechos o IDF do bm25 fica perto de
    # zero e o corte de relevância descarta até o acerto.
    "atendimento.md": """---
id: atendimento
titulo: Atendimento humano
visibilidade: publico
---

## Equipe de atendimento
Quando o assistente nao resolve, a equipe humana atende pelo WhatsApp em horario comercial.
""",
    "privacidade.md": """---
id: privacidade
titulo: Privacidade e LGPD
visibilidade: publico
---

## Dados coletados
A plataforma guarda nome, e-mail e o historico do chat, conforme a LGPD.

## Exportar e excluir
Em Meu perfil o aluno exporta ou exclui os proprios dados.
""",
}

# JS: para cada chat-fonte, a última mensagem que o contém ou vem antes dele no DOM (a "dona"), e se o topo do
# chat-fonte não fica acima do topo da dona.
_FONTES_JS = """([selMsg, selFonte]) => {
  const msgs = [...document.querySelectorAll(selMsg)];
  return [...document.querySelectorAll(selFonte)].map(f => {
    let dona = -1;
    msgs.forEach((m, i) => {
      if (m.contains(f) || (m.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING)) dona = i;
    });
    const rf = f.getBoundingClientRect();
    const rm = dona >= 0 ? msgs[dona].getBoundingClientRect() : null;
    return {texto: f.innerText, dona, abaixo: !!rm && rf.top >= rm.top - 1, total: msgs.length,
            papel: dona >= 0 ? (msgs[dona].getAttribute('data-role') || msgs[dona].className) : null,
            dona_texto: dona >= 0 ? msgs[dona].innerText : null};
  });
}"""


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _fontes(page, sel_msg):
    return page.evaluate(_FONTES_JS, [sel_msg, SEL_FONTE])


def _exigir_uma_fonte_da_resposta(page, sel_msg, eco, rotulo, eh_bot):
    """Exatamente um chat-fonte, com TEXTO_FONTE, abaixo da resposta do bot que ecoa `eco`."""
    fim = time.time() + 6
    while time.time() < fim and page.locator(SEL_FONTE).count() == 0:
        page.wait_for_timeout(150)
    fontes = _fontes(page, sel_msg)
    if len(fontes) != 1:
        raise Falha(f"{rotulo}: esperava 1 [data-testid=chat-fonte], há {len(fontes)}")
    f = fontes[0]
    if _normalizar(f["texto"]) != TEXTO_FONTE:
        raise Falha(f"{rotulo}: chat-fonte com texto {_normalizar(f['texto'])!r}, esperado {TEXTO_FONTE!r}")
    if f["dona"] < 0 or not eh_bot(f["papel"]) or eco not in (f["dona_texto"] or ""):
        raise Falha(f"{rotulo}: chat-fonte não está logo depois da resposta do bot (dona: {f['papel']!r}, "
                    f"{(f['dona_texto'] or '')[:80]!r})")
    if not f["abaixo"]:
        raise Falha(f"{rotulo}: chat-fonte aparece acima da resposta do bot")
    return f


# =========================================================================================
# Área do aluno (Angular)
# =========================================================================================

@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


@pytest.fixture(scope="module")
def servidores_angular():
    with ambiente_f5b("gr1_angular", knowledge=BASE) as ambiente:
        yield ambiente


def _eh_assistente(papel):
    return papel == "assistant"


def test_gr1_fonte_area_do_aluno(servidores_angular, browser):
    base = servidores_angular["base"]
    resultados, erros_console, contextos = [], [], []
    estado = {}

    seed = {"ok": False, "erro": ""}
    try:
        email, _ = semear_aluno(servidores_angular["db_path"], "gr1")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

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
        return page

    def cenario(codigo, nome, funcao):
        try:
            if not seed["ok"]:
                raise Falha(f"seed falhou: {seed['erro']}")
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")

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

    def enviar(page, texto, rotulo):
        antes = page.locator(SEL_MENSAGEM).count()
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/student/chat"),
            timeout=TIMEOUT * 3,
        ) as info:
            page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
            page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        dados = info.value.json()
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and PREFIXO_RESPOSTA in msgs[-1]["text"]:
                page.wait_for_timeout(400)
                return dados
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def a0():
        page = entrar_no_student()
        estado["page"] = page
        dados = enviar(page, PERGUNTA_NEUTRA, "A0")
        if dados.get("sources") not in ([], None):
            raise Falha(f"A0: pré-condição: a pergunta comum não deveria ter fonte ({dados.get('sources')})")
        if page.locator(SEL_FONTE).count():
            raise Falha("A0: resposta sem fonte mostrou [data-testid=chat-fonte]")

    def a1():
        page = estado.get("page") or entrar_no_student()
        estado["page"] = page
        dados = enviar(page, PERGUNTA_CANCELAMENTO, "A1")
        if dados.get("sources") != [FONTE]:
            raise Falha(f"A1: pré-condição do backend: sources={dados.get('sources')!r}, esperado [{FONTE}]")
        _exigir_uma_fonte_da_resposta(page, SEL_MENSAGEM, PERGUNTA_CANCELAMENTO, "A1", _eh_assistente)
        estado["a1"] = True

    def a2():
        if not estado.get("a1"):
            raise Falha("A2 depende de A1")
        page = estado["page"]
        enviar(page, PERGUNTA_NEUTRA, "A2")
        f = _exigir_uma_fonte_da_resposta(page, SEL_MENSAGEM, PERGUNTA_CANCELAMENTO, "A2", _eh_assistente)
        if f["dona"] >= f["total"] - 2:
            raise Falha("A2: a fonte apareceu na resposta nova (sem fonte)")

    def a3():
        page = estado.get("page") or entrar_no_student()
        page.reload(wait_until="networkidle")
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        fim = time.time() + 8
        while time.time() < fim and page.locator(SEL_MENSAGEM).count() == 0:
            page.wait_for_timeout(150)
        if page.locator(SEL_MENSAGEM).count() == 0:
            raise Falha("A3: o histórico não voltou depois de recarregar")
        page.wait_for_timeout(400)
        if page.locator(SEL_FONTE).count():
            raise Falha("A3: a fonte voltou com o histórico (não deve ser persistida)")

    def a4():
        if erros_console:
            raise Falha(f"A4: erros de console: {erros_console[:3]}")

    try:
        cenario("A0", "pré-condição: pergunta comum respondida sem chat-fonte", a0)
        cenario("A1", "pergunta de cancelamento mostra 'Fonte: <título>' abaixo da resposta", a1)
        cenario("A2", "pergunta comum seguinte não ganha fonte", a2)
        cenario("A3", "histórico recarregado sem chat-fonte", a3)
        cenario("A4", "sem erros de console de /api nem exceções de página", a4)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR1 Área do aluno: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)


# =========================================================================================
# Landing estática
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    origem = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("gr1_landing", cors_origin=origem, angular=False, knowledge=BASE) as ambiente:
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, landing=origem + "/landing_global_training.html")
        finally:
            estatico.shutdown()
            estatico.server_close()


def _eh_bot_da_landing(papel):
    return "msg-bot" in (papel or "")


class Visitante:
    def __init__(self, browser, servidores):
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        self.page = self.contexto.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))
        self.page.goto(servidores["landing"], wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto):
        if not self.page.locator("#chat-bubble.open").count():
            self.page.locator("#chat-btn").click(timeout=TIMEOUT)
        campo = self.page.locator("#chat-input")
        campo.fill(texto, timeout=TIMEOUT)
        with self.page.expect_response(
            lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/chat"), timeout=TIMEOUT * 2,
        ) as info:
            campo.press("Enter")
        dados = info.value.json()
        fim = time.time() + 8
        while time.time() < fim:
            textos = self.page.locator(SEL_LANDING_BOT).all_inner_texts()
            if textos and PREFIXO_RESPOSTA + texto in textos[-1]:
                break
            self.page.wait_for_timeout(100)
        self.page.wait_for_timeout(400)
        return dados

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


def test_gr1_fonte_landing(servidores_landing, browser):
    v = Visitante(browser, servidores_landing)
    resultados, estado = [], {}

    def cenario(codigo, nome, funcao):
        try:
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")

    def l0():
        dados = v.enviar(PERGUNTA_NEUTRA)
        if dados.get("status") != "success" or dados.get("sources") not in ([], None):
            raise Falha(f"L0: pré-condição: resposta comum sem fonte ({dados})")
        if not any(PREFIXO_RESPOSTA + PERGUNTA_NEUTRA in t for t in v.page.locator(SEL_LANDING_BOT).all_inner_texts()):
            raise Falha("L0: a resposta do bot não apareceu na landing")
        if v.page.locator(SEL_FONTE).count():
            raise Falha("L0: resposta sem fonte mostrou [data-testid=chat-fonte]")

    def l1():
        dados = v.enviar(PERGUNTA_CANCELAMENTO)
        if dados.get("sources") != [FONTE]:
            raise Falha(f"L1: pré-condição do backend: sources={dados.get('sources')!r}, esperado [{FONTE}]")
        _exigir_uma_fonte_da_resposta(v.page, SEL_LANDING_MSG, PERGUNTA_CANCELAMENTO, "L1", _eh_bot_da_landing)
        estado["l1"] = True

    def l2():
        if not estado.get("l1"):
            raise Falha("L2 depende de L1")
        v.enviar(PERGUNTA_NEUTRA)
        f = _exigir_uma_fonte_da_resposta(v.page, SEL_LANDING_MSG, PERGUNTA_CANCELAMENTO, "L2", _eh_bot_da_landing)
        if f["dona"] >= f["total"] - 2:
            raise Falha("L2: a fonte apareceu na resposta nova (sem fonte)")

    def l3():
        if v.erros:
            raise Falha(f"L3: erros de console: {v.erros[:3]}")

    try:
        cenario("L0", "pré-condição: pergunta comum respondida sem chat-fonte", l0)
        cenario("L1", "pergunta de cancelamento mostra 'Fonte: <título>' abaixo da resposta", l1)
        cenario("L2", "pergunta comum seguinte não ganha fonte", l2)
        cenario("L3", "sem erros de console nem exceções de página", l3)
    finally:
        v.fechar()

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR1 landing: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
