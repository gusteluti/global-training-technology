"""E2E da GR5 — feedback 👍/👎 nas respostas do bot (D95, PLANO_GR seção GR5, "Feedback").

Contrato de tela (PLANO_GR e pedido do orquestrador):
  - Cada resposta do bot que traz `reply_id` ganha dois botões, [data-testid=chat-feedback-up] e
    [data-testid=chat-feedback-down], logo depois do balão (Área do aluno: [data-testid=chat-message][data-role=
    assistant]; landing: `#chat-messages .msg-bot`). Resposta sem `reply_id` (erro, histórico, saudação) não tem botões.
  - O clique envia o feedback daquela resposta: Área do aluno -> POST /api/student/chat/feedback {reply_id, rating}
    (JWT no Authorization, nunca user_id no corpo); landing -> POST <API>/api/chat/feedback {session_id, reply_id,
    rating}, com o session_id da conversa. rating = "up" | "down".

Escolhas de forma do teste (registradas no relatório do agente-testes):
  - "Dono" do botão = a última mensagem que o contém ou vem antes dele no DOM (mesma regra do aviso da GR3); o dono
    tem de ser a resposta do bot com aquele reply_id. Um par por resposta.
  - Depois de um feedback aceito (200), os DOIS botões daquela resposta ficam desabilitados (`disabled` ou
    aria-disabled="true") e o escolhido fica marcado com aria-pressed="true" (o outro não). Os botões de outras
    respostas não mudam.
  - Erro de rede no envio (requisição abortada): a tela não quebra (sem exceção de página, o chat continua
    respondendo) e nada fica marcado: o botão volta a ficar habilitado e sem aria-pressed="true" (dá para tentar de
    novo). Sem mensagem de erro obrigatória.
  - Histórico recarregado do banco (GET /api/student/chat/history) não tem reply_id: sem botões.
  - Cenários "interceptados" usam page.route (padrão GR1/GR3/GR4) no POST do chat e no POST do feedback; os
    "ponta a ponta" vão ao backend de teste (D58, Groq falso que ecoa) e conferem a GR5 inteira (reply_id do backend,
    feedback aceito com 200).

Harness: `apoio_harness_f5b.ambiente_f5b(..., knowledge={})` (backend D58, catálogo temporário, KNOWLEDGE_DIR vazia).
Angular: `ng serve` com proxy. Landing: servidor estático do helper da E6 (CORS do backend libera a origem estática).

Cenários — Área do aluno (test_gr5_feedback_area_do_aluno):
  A0 pré-condição: aluno entra, pergunta comum respondida                                          [passa no red]
  A1 ponta a ponta: a resposta do backend traz reply_id e a resposta do bot tem 👍 e 👎 habilitados
  A2 clique 👍 (ponta a ponta): POST /api/student/chat/feedback {reply_id, rating: up} -> 200; par desabilitado, 👍 marcado
  A3 duas respostas interceptadas: 👎 na primeira envia o reply_id dela; a segunda continua habilitada
  A4 resposta interceptada sem reply_id: nenhum botão de feedback nela                            [passa no red]
  A5 erro de rede no feedback: sem exceção, nada marcado, botão habilitado de novo, o chat continua respondendo
  A6 recarregar /student: o histórico não mostra botões de feedback                                [passa no red]
  A7 sem erros de console de /api nem exceções de página
Cenários — landing (test_gr5_feedback_landing):
  L0 pré-condição: pergunta comum respondida                                                       [passa no red]
  L1 ponta a ponta: reply_id na resposta e 👍/👎 na resposta do bot; a saudação estática não tem botões
  L2 clique 👎 (ponta a ponta): POST /api/chat/feedback {session_id, reply_id, rating: down} -> 200; par desabilitado
  L3 resposta interceptada sem reply_id: nenhum botão                                              [passa no red]
  L4 duas respostas interceptadas: 👍 na primeira envia o reply_id dela; a segunda continua habilitada
  L5 sem erros de console nem exceções de página
  L6 erro de rede no feedback: sem exceção, nada marcado, a landing continua respondendo

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_gr5_feedback_chat.py -s
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
from test_gr3_aviso_pii_chat import Falha, Interceptador, Visitante, _rodar  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_UP = '[data-testid="chat-feedback-up"]'
SEL_DOWN = '[data-testid="chat-feedback-down"]'
SEL_LANDING_MSG = "#chat-messages .msg"
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
REPLY_ID = re.compile(r"[0-9a-f]{32}")

ROTA_FB_ALUNO = "/api/student/chat/feedback"
ROTA_FB_ANONIMO = "/api/chat/feedback"

# JS: para cada mensagem (na ordem do DOM), os botões de feedback cujo "dono" é ela (a última mensagem que contém o
# botão ou vem antes dele). Para cada botão: desabilitado e aria-pressed.
_FEEDBACK_JS = """([selMsg, selUp, selDown]) => {
  const msgs = [...document.querySelectorAll(selMsg)];
  const info = msgs.map(m => ({papel: m.getAttribute('data-role') || m.className, texto: m.innerText, up: [], down: []}));
  const dono = b => {
    let d = -1;
    msgs.forEach((m, i) => { if (m.contains(b) || (m.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)) d = i; });
    return d;
  };
  const estado = b => ({
    desabilitado: !!b.disabled || b.getAttribute('aria-disabled') === 'true',
    marcado: b.getAttribute('aria-pressed') === 'true',
    visivel: !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length),
  });
  const soltos = [];
  for (const [sel, chave] of [[selUp, 'up'], [selDown, 'down']]) {
    document.querySelectorAll(sel).forEach(b => {
      const d = dono(b);
      if (d < 0) soltos.push(chave); else info[d][chave].push(estado(b));
    });
  }
  return {msgs: info, soltos};
}"""


def _estado(page, sel_msg):
    return page.evaluate(_FEEDBACK_JS, [sel_msg, SEL_UP, SEL_DOWN])


def _eh_bot(papel):
    return papel == "assistant" or "msg-bot" in (papel or "")


def _indice_bot(msgs, texto):
    """Índice da última resposta do bot que contém `texto`."""
    return max((i for i, m in enumerate(msgs) if _eh_bot(m["papel"]) and texto in m["texto"]), default=-1)


def _par(page, sel_msg, texto, rotulo, espera=6):
    """Estado dos botões da resposta do bot com `texto`; exige exatamente um 👍 e um 👎, visíveis."""
    fim = time.time() + espera
    while True:
        estado = _estado(page, sel_msg)
        i = _indice_bot(estado["msgs"], texto)
        if i >= 0 and estado["msgs"][i]["up"] and estado["msgs"][i]["down"]:
            break
        if time.time() > fim:
            if i < 0:
                raise Falha(f"{rotulo}: a resposta do bot com {texto[:40]!r} não está na tela")
            raise Falha(f"{rotulo}: a resposta do bot não tem [data-testid=chat-feedback-up] e "
                        f"[data-testid=chat-feedback-down] logo depois do balão")
        page.wait_for_timeout(150)
    msg = estado["msgs"][i]
    if len(msg["up"]) != 1 or len(msg["down"]) != 1:
        raise Falha(f"{rotulo}: esperava um par de botões na resposta, há {len(msg['up'])} 👍 e {len(msg['down'])} 👎")
    if not (msg["up"][0]["visivel"] and msg["down"][0]["visivel"]):
        raise Falha(f"{rotulo}: os botões de feedback não estão visíveis")
    return i, msg["up"][0], msg["down"][0]


def _sem_botoes(page, sel_msg, texto, rotulo):
    page.wait_for_timeout(500)
    estado = _estado(page, sel_msg)
    i = _indice_bot(estado["msgs"], texto)
    if i < 0:
        raise Falha(f"{rotulo}: a resposta do bot com {texto[:40]!r} não está na tela")
    msg = estado["msgs"][i]
    if msg["up"] or msg["down"]:
        raise Falha(f"{rotulo}: resposta sem reply_id mostrou botões de feedback")


def _exigir_habilitado(botao, rotulo):
    if botao["desabilitado"]:
        raise Falha(f"{rotulo}: o botão de feedback está desabilitado antes do clique")
    if botao["marcado"]:
        raise Falha(f"{rotulo}: o botão de feedback já está marcado (aria-pressed) antes do clique")


def _esperar_marcado(page, sel_msg, texto, escolhido, rotulo, espera=5):
    """Depois do 200: o par da resposta fica desabilitado e só o `escolhido` (up|down) fica com aria-pressed=true."""
    outro = "down" if escolhido == "up" else "up"
    fim = time.time() + espera
    while True:
        _, up, down = _par(page, sel_msg, texto, rotulo)
        estado = {"up": up, "down": down}
        pronto = (estado[escolhido]["marcado"] and not estado[outro]["marcado"]
                  and up["desabilitado"] and down["desabilitado"])
        if pronto:
            return
        if time.time() > fim:
            raise Falha(f"{rotulo}: depois do feedback aceito, o par devia ficar desabilitado e só o "
                        f"{escolhido} marcado (aria-pressed=true); está up={up} down={down}")
        page.wait_for_timeout(150)


def _clicar(page, sel_msg, texto, qual, rotulo):
    """Clica no 👍/👎 (qual = up|down) da resposta do bot com `texto`."""
    i, _, _ = _par(page, sel_msg, texto, rotulo)
    seletor = SEL_UP if qual == "up" else SEL_DOWN
    indice = page.evaluate(
        """([selMsg, sel, alvo]) => {
          const msgs = [...document.querySelectorAll(selMsg)];
          const botoes = [...document.querySelectorAll(sel)];
          return botoes.findIndex(b => {
            let d = -1;
            msgs.forEach((m, i) => { if (m.contains(b) || (m.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)) d = i; });
            return d === alvo;
          });
        }""",
        [sel_msg, seletor, i],
    )
    if indice < 0:
        raise Falha(f"{rotulo}: botão {qual} da resposta não encontrado")
    page.locator(seletor).nth(indice).click(timeout=TIMEOUT)


class EspiaoFeedback:
    """Rota do POST de feedback: registra os corpos; modo 'continuar' (backend de teste), 'ok' (200 do teste) ou
    'abortar' (erro de rede). Com `cors_origem`, responde o preflight e devolve os cabeçalhos de CORS."""

    def __init__(self, cors_origem=None):
        self.modo = "continuar"
        self.corpos = []
        self.cabecalhos_vistos = []
        self.cors = {}
        if cors_origem:
            self.cors = {
                "Access-Control-Allow-Origin": cors_origem,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }

    def __call__(self, rota):
        pedido = rota.request
        if pedido.method == "POST":
            try:
                self.corpos.append(json.loads(pedido.post_data or "null"))
            except ValueError:
                self.corpos.append(pedido.post_data)
            self.cabecalhos_vistos.append(dict(pedido.headers))
        if self.modo == "continuar":
            rota.continue_()
        elif self.modo == "abortar":
            if pedido.method == "OPTIONS" and self.cors:
                rota.fulfill(status=204, headers=self.cors, body="")
            else:
                rota.abort("failed")
        elif pedido.method == "OPTIONS":
            rota.fulfill(status=204, headers=self.cors, body="")
        else:
            rota.fulfill(status=200, headers=dict(self.cors, **{"Content-Type": "application/json"}),
                         body=json.dumps({"status": "success"}))


def _exigir_corpo(espiao, esperado, rotulo, espera=5):
    fim = time.time() + espera
    while time.time() < fim and not espiao.corpos:
        time.sleep(0.1)
    if not espiao.corpos:
        raise Falha(f"{rotulo}: o clique não enviou o POST de feedback")
    corpo = espiao.corpos[-1]
    if corpo != esperado:
        raise Falha(f"{rotulo}: corpo do feedback {corpo!r}, esperado {esperado!r}")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _resposta_aluno(mensagem, reply_id):
    corpo = {"status": "success", "message": mensagem, "actions": [], "sources": [], "pii_masked": False}
    if reply_id:
        corpo["reply_id"] = reply_id
    return corpo


# =========================================================================================
# Área do aluno (Angular)
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_angular():
    with ambiente_f5b("gr5_angular", knowledge={}) as ambiente:
        yield ambiente


def _rota_do_chat_do_aluno(url):
    return urlsplit(url).path.rstrip("/") == "/api/student/chat"


def _rota_do_feedback_do_aluno(url):
    return urlsplit(url).path.rstrip("/") == ROTA_FB_ALUNO


def test_gr5_feedback_area_do_aluno(servidores_angular, browser):
    base = servidores_angular["base"]
    resultados, erros_console, contextos = [], [], []
    estado = {}
    interceptar = Interceptador()
    espiao = EspiaoFeedback()

    seed = {"ok": False, "erro": ""}
    try:
        email, _uid = semear_aluno(servidores_angular["db_path"], "gr5")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def exigir_seed():
        if not seed["ok"]:
            raise Falha(f"seed falhou: {seed['erro']}")

    def entrar_no_student():
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
        page.route(_rota_do_feedback_do_aluno, espiao)
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

    def enviar(texto, rotulo, resposta=None, esperado_no_bot=None):
        page = pagina()
        interceptar.resposta = resposta
        try:
            antes = page.locator(SEL_MENSAGEM).count()
            with page.expect_response(
                lambda r: r.request.method == "POST" and _rota_do_chat_do_aluno(r.url), timeout=TIMEOUT * 2,
            ) as info:
                page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
                page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
            dados = info.value.json()
        finally:
            interceptar.resposta = None
        esperado = esperado_no_bot if esperado_no_bot is not None else (resposta or {}).get("message", "")
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and esperado in msgs[-1]["text"]:
                page.wait_for_timeout(300)
                return dados
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def a0():
        enviar("Recomenda leituras introdutorias? (A0)", "A0", esperado_no_bot=PREFIXO_RESPOSTA)

    def a1():
        texto = "Recomenda leituras sobre a plataforma? (A1)"
        dados = enviar(texto, "A1", esperado_no_bot=texto)
        rid = dados.get("reply_id")
        if not isinstance(rid, str) or not REPLY_ID.fullmatch(rid):
            raise Falha(f"A1: a resposta do backend devia trazer reply_id (32 hex), veio {dados!r}"[:300])
        _, up, down = _par(pagina(), SEL_MENSAGEM, texto, "A1")
        _exigir_habilitado(up, "A1")
        _exigir_habilitado(down, "A1")
        estado["a1"] = (texto, rid)

    def a2():
        if "a1" not in estado:
            raise Falha("A2 depende de A1")
        texto, rid = estado["a1"]
        page = pagina()
        espiao.modo, espiao.corpos = "continuar", []
        with page.expect_response(
            lambda r: r.request.method == "POST" and _rota_do_feedback_do_aluno(r.url), timeout=TIMEOUT,
        ) as info:
            _clicar(page, SEL_MENSAGEM, texto, "up", "A2")
        if info.value.status != 200:
            raise Falha(f"A2: o backend respondeu {info.value.status} ao feedback")
        _exigir_corpo(espiao, {"reply_id": rid, "rating": "up"}, "A2")
        auth = (espiao.cabecalhos_vistos[-1] or {}).get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise Falha("A2: o feedback do aluno foi sem o JWT no Authorization")
        _esperar_marcado(page, SEL_MENSAGEM, texto, "up", "A2")

    def a3():
        page = pagina()
        r1, r2 = "1" * 32, "2" * 32
        t1, t2 = "Resposta interceptada GR5 A3 primeira", "Resposta interceptada GR5 A3 segunda"
        enviar("Primeira pergunta (A3)", "A3", _resposta_aluno(t1, r1))
        enviar("Segunda pergunta (A3)", "A3", _resposta_aluno(t2, r2))
        espiao.modo, espiao.corpos = "ok", []
        _clicar(page, SEL_MENSAGEM, t1, "down", "A3")
        _exigir_corpo(espiao, {"reply_id": r1, "rating": "down"}, "A3")
        _esperar_marcado(page, SEL_MENSAGEM, t1, "down", "A3")
        _, up2, down2 = _par(page, SEL_MENSAGEM, t2, "A3 (segunda)")
        _exigir_habilitado(up2, "A3: a segunda resposta")
        _exigir_habilitado(down2, "A3: a segunda resposta")

    def a4():
        texto = "Resposta interceptada GR5 A4 sem reply_id"
        enviar("Pergunta sem reply (A4)", "A4", _resposta_aluno(texto, None))
        _sem_botoes(pagina(), SEL_MENSAGEM, texto, "A4")

    def a5():
        page = pagina()
        texto = "Resposta interceptada GR5 A5 rede"
        enviar("Pergunta com rede ruim (A5)", "A5", _resposta_aluno(texto, "5" * 32))
        espiao.modo, espiao.corpos = "abortar", []
        erros_antes = len([e for e in erros_console if e.startswith("pageerror")])
        _clicar(page, SEL_MENSAGEM, texto, "up", "A5")
        _exigir_corpo(espiao, {"reply_id": "5" * 32, "rating": "up"}, "A5")
        fim = time.time() + 5
        while True:
            _, up, _down = _par(page, SEL_MENSAGEM, texto, "A5")
            if not up["marcado"] and not up["desabilitado"]:
                break
            if time.time() > fim:
                raise Falha(f"A5: depois do erro de rede o 👍 devia voltar habilitado e sem marca ({up})")
            page.wait_for_timeout(150)
        if len([e for e in erros_console if e.startswith("pageerror")]) != erros_antes:
            raise Falha("A5: o erro de rede no feedback gerou exceção de página")
        espiao.modo = "continuar"
        enviar("A tela continua respondendo? (A5)", "A5", esperado_no_bot=PREFIXO_RESPOSTA)

    def a6():
        page = pagina()
        page.reload(wait_until="networkidle")
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        fim = time.time() + 8
        while time.time() < fim and page.locator(SEL_MENSAGEM).count() < 2:
            page.wait_for_timeout(150)
        if page.locator(SEL_MENSAGEM).count() < 2:
            raise Falha("A6: o histórico não voltou depois de recarregar")
        page.wait_for_timeout(500)
        if page.locator(f"{SEL_UP}, {SEL_DOWN}").count():
            raise Falha("A6: o histórico recarregado (sem reply_id) mostrou botões de feedback")

    def a7():
        if erros_console:
            raise Falha(f"A7: erros de console: {erros_console[:3]}")

    try:
        _rodar(resultados, "A0", "pré-condição: pergunta comum respondida", a0, exigir_seed)
        _rodar(resultados, "A1", "ponta a ponta: reply_id do backend e 👍/👎 na resposta", a1, exigir_seed)
        _rodar(resultados, "A2", "👍 envia {reply_id, rating: up} com JWT; par desabilitado e 👍 marcado", a2, exigir_seed)
        _rodar(resultados, "A3", "👎 na primeira de duas respostas envia o reply_id dela; a outra segue", a3, exigir_seed)
        _rodar(resultados, "A4", "resposta sem reply_id não tem botões", a4, exigir_seed)
        _rodar(resultados, "A5", "erro de rede no feedback não quebra a tela nem marca", a5, exigir_seed)
        _rodar(resultados, "A6", "histórico recarregado sem botões de feedback", a6, exigir_seed)
        _rodar(resultados, "A7", "sem erros de console de /api nem exceções de página", a7)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR5 Área do aluno: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)


# =========================================================================================
# Landing estática
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    origem = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("gr5_landing", cors_origin=origem, angular=False, knowledge={}) as ambiente:
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, origem=origem, landing=origem + "/landing_global_training.html")
        finally:
            estatico.shutdown()
            estatico.server_close()


def _sucesso_anonimo(mensagem, reply_id, session_id="0" * 32):
    corpo = {"status": "success", "message": mensagem, "session_id": session_id, "actions": [], "sources": [],
             "pii_masked": False}
    if reply_id:
        corpo["reply_id"] = reply_id
    return corpo


def test_gr5_feedback_landing(servidores_landing, browser):
    v = Visitante(browser, servidores_landing)
    espiao = EspiaoFeedback(servidores_landing["origem"])
    v.contexto.route(f"{servidores_landing['api']}{ROTA_FB_ANONIMO}", espiao)
    resultados, estado = [], {}

    def l0():
        v.enviar("Recomenda leituras introdutorias? (L0)", PREFIXO_RESPOSTA)

    def l1():
        texto = "Recomenda leituras sobre a plataforma? (L1)"
        dados, _ = v.enviar(texto, texto)
        rid = dados.get("reply_id")
        if not isinstance(rid, str) or not REPLY_ID.fullmatch(rid):
            raise Falha(f"L1: a resposta do backend devia trazer reply_id (32 hex), veio {dados!r}"[:300])
        _, up, down = _par(v.page, SEL_LANDING_MSG, texto, "L1")
        _exigir_habilitado(up, "L1")
        _exigir_habilitado(down, "L1")
        saudacao = _estado(v.page, SEL_LANDING_MSG)["msgs"][0]
        if saudacao["up"] or saudacao["down"]:
            raise Falha("L1: a saudação estática (sem reply_id) mostrou botões de feedback")
        estado["l1"] = (texto, rid, dados.get("session_id"))

    def l2():
        if "l1" not in estado:
            raise Falha("L2 depende de L1")
        texto, rid, sid = estado["l1"]
        espiao.modo, espiao.corpos = "continuar", []
        with v.page.expect_response(
            lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith(ROTA_FB_ANONIMO), timeout=TIMEOUT,
        ) as info:
            _clicar(v.page, SEL_LANDING_MSG, texto, "down", "L2")
        if info.value.status != 200:
            raise Falha(f"L2: o backend respondeu {info.value.status} ao feedback")
        _exigir_corpo(espiao, {"session_id": sid, "reply_id": rid, "rating": "down"}, "L2")
        _esperar_marcado(v.page, SEL_LANDING_MSG, texto, "down", "L2")

    def l3():
        texto = "Resposta interceptada GR5 L3 sem reply_id"
        v.enviar("Pergunta sem reply (L3)", texto, _sucesso_anonimo(texto, None))
        _sem_botoes(v.page, SEL_LANDING_MSG, texto, "L3")

    def l4():
        r1, r2 = "3" * 32, "4" * 32
        t1, t2 = "Resposta interceptada GR5 L4 primeira", "Resposta interceptada GR5 L4 segunda"
        v.enviar("Primeira pergunta (L4)", t1, _sucesso_anonimo(t1, r1))
        v.enviar("Segunda pergunta (L4)", t2, _sucesso_anonimo(t2, r2))
        espiao.modo, espiao.corpos = "ok", []
        _clicar(v.page, SEL_LANDING_MSG, t1, "up", "L4")
        _exigir_corpo(espiao, {"session_id": "0" * 32, "reply_id": r1, "rating": "up"}, "L4")
        _esperar_marcado(v.page, SEL_LANDING_MSG, t1, "up", "L4")
        _, up2, down2 = _par(v.page, SEL_LANDING_MSG, t2, "L4 (segunda)")
        _exigir_habilitado(up2, "L4: a segunda resposta")
        _exigir_habilitado(down2, "L4: a segunda resposta")

    def l5():
        if v.erros:
            raise Falha(f"L5: erros de console: {v.erros[:3]}")

    def l6():
        texto = "Resposta interceptada GR5 L6 rede"
        v.enviar("Pergunta com rede ruim (L6)", texto, _sucesso_anonimo(texto, "6" * 32))
        espiao.modo, espiao.corpos = "abortar", []
        excecoes = len([e for e in v.erros if e.startswith("pageerror")])
        _clicar(v.page, SEL_LANDING_MSG, texto, "down", "L6")
        _exigir_corpo(espiao, {"session_id": "0" * 32, "reply_id": "6" * 32, "rating": "down"}, "L6")
        fim = time.time() + 5
        while True:
            _, _up, down = _par(v.page, SEL_LANDING_MSG, texto, "L6")
            if not down["marcado"] and not down["desabilitado"]:
                break
            if time.time() > fim:
                raise Falha(f"L6: depois do erro de rede o 👎 devia voltar habilitado e sem marca ({down})")
            v.page.wait_for_timeout(150)
        if len([e for e in v.erros if e.startswith("pageerror")]) != excecoes:
            raise Falha("L6: o erro de rede no feedback gerou exceção de página")
        espiao.modo = "continuar"
        v.enviar("A landing continua respondendo? (L6)", PREFIXO_RESPOSTA)

    try:
        _rodar(resultados, "L0", "pré-condição: pergunta comum respondida", l0)
        _rodar(resultados, "L1", "ponta a ponta: reply_id e 👍/👎 na resposta; saudação sem botões", l1)
        _rodar(resultados, "L2", "👎 envia {session_id, reply_id, rating: down}; par desabilitado e 👎 marcado", l2)
        _rodar(resultados, "L3", "resposta sem reply_id não tem botões", l3)
        _rodar(resultados, "L4", "👍 na primeira de duas respostas envia o reply_id dela; a outra segue", l4)
        _rodar(resultados, "L5", "sem erros de console nem exceções de página", l5)
        _rodar(resultados, "L6", "erro de rede no feedback não quebra a landing nem marca", l6)
    finally:
        v.fechar()

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR5 landing: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
