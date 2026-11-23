"""E2E da R3-1 (R3a): chat da landing com endereço da API configurável e erros distintos (Chromium via Playwright).

Problema (relato do PM): o chat da landing não funciona quando ele abre a página. O endereço da API é fixo no script
(`const BACKEND_URL = 'http://localhost:8000'`), o backend só libera no CORS as origens da lista, e todo erro vira
"Desculpe, não foi possível conectar ao servidor". Os e2e antigos (E6, F5b, F6, GR*) trocam o literal na CÓPIA servida
e por isso nunca exercitaram o endereço real. Este arquivo exercita o endereço sem trocar o literal.

Contrato (decidido pelo PM; implementação só no <script> e no <head> da landing):
 1. Endereço da API, no padrão do APP_URL: `<meta name="gtt-api-url" content="">` no head. Ordem:
      (a) meta preenchida -> o valor sem barra final;
      (b) meta vazia e página em file: ou hostname localhost / 127.0.0.1 / vazio -> `http://localhost:8000`;
      (c) senão -> `window.location.origin` (mesmo domínio).
    O literal `http://localhost:8000` continua no script (os e2e antigos trocam esse literal na cópia servida) e a
    constante continua `BACKEND_URL`. Cursos, chat e feedback usam ela.
 2. Erros do chat, texto no balão do bot:
      (i)   fetch rejeita (servidor fora, CORS, offline) -> "Não consegui falar com o servidor. Verifique sua conexão e
            tente de novo em instantes." e status "Offline";
      (ii)  o servidor respondeu, mas não é JSON do chat (502/503/500 de proxy, página HTML) -> "O servidor teve um
            problema para responder. Tente de novo em instantes." e status "Offline";
      (iii) JSON com status "error" -> como hoje ("Erro: <mensagem do servidor>"), status "Online agora".
    Nenhum texto de exceção nem de corpo bruto vai para a tela.
 3. Diagnóstico só no console: em (i) e (ii) um console.error com a URL completa do POST, o status HTTP quando houver e,
    em (i), uma dica com a palavra CORS_ALLOWED_ORIGINS. Nada disso na tela.
 4. Nada mais muda (sessão, feedback, ações, markdown, acessibilidade, layout).

Cenários (cada um com contexto de navegador próprio; o Google Fonts é respondido vazio):
  S1 (estático) o head declara `<meta name="gtt-api-url" content="">`                                        [falha no red]
  S2 (estático) o literal http://localhost:8000 e a constante `const BACKEND_URL` continuam no script       [passa no red]
  P0 pré-condição: o chat funciona com o harness atual (cópia servida com o literal trocado)                [passa no red]
  A1 meta preenchida (valor com barra final) na página em 127.0.0.1: cursos, POST /api/chat e feedback vão
     para esse endereço, sem barra dupla e nada vai para localhost:8000                                      [falha no red]
  A1b meta preenchida vence também em host não local (landing.exemplo.test -> api.exemplo.test)              [falha no red]
  A2 meta vazia, página em 127.0.0.1, literal NÃO trocado: as requisições vão para http://localhost:8000
     (ramo b; protege contra uma implementação que use sempre a origem)                                       [passa no red]
  A3 meta vazia, página em landing.exemplo.test: as requisições vão para https://landing.exemplo.test/api/...
     (mesma origem), nunca para localhost                                                                    [falha no red]
  A4 página por file:// sem meta preenchida: resolve para http://localhost:8000 (ramo b)                     [passa no red]
  E1 falha de rede (abort do POST /api/chat): texto (i) exato, status "Offline", console.error com a URL e
     CORS_ALLOWED_ORIGINS, nenhum texto de exceção nem diagnóstico na tela; com a rede de volta a conversa
     funciona (status "Online agora")                                                                         [falha no red]
  E2 resposta que não é JSON do chat (502 HTML, 503 e 500 em texto, 200 com a página HTML): texto (ii) exato,
     status "Offline", console.error com a URL e o status, nada do corpo na tela, a conversa se recupera     [falha no red]
  E3 JSON com status error (LLM indisponível pelo dublê; 429 do limite): texto do servidor, status "Online
     agora", sem console.error da página, sem os textos (i) e (ii)                                            [passa no red]
  E4 sucesso normal sem regressão: resposta, feedback 👍 (ponta a ponta), fonte, ações, aviso de dado pessoal,
     markdown, status "Online agora", sem console.error                                                       [passa no red]

Escolhas do agente-testes (modo autônomo, D40):
  - A2 e A4 passam no red de propósito: o ramo (b) do contrato é o comportamento de hoje. Eles protegem o ramo contra
    uma implementação que passe a usar sempre `window.location.origin`. O red do endereço está em S1, A1, A1b e A3.
  - O "console.error da página" exclui as mensagens que o próprio Chromium escreve para recurso que falhou ("Failed to
    load resource: ..."), que existem com qualquer código; só conta console.error chamado pelo script.
  - Para ler o texto de um console.error, junto `msg.text` com o valor JSON de cada argumento (um objeto passado ao
    console.error não aparece em `msg.text`).
  - Na dica de (i), exijo a palavra CORS_ALLOWED_ORIGINS e a URL em qualquer console.error da página (não
    necessariamente na mesma chamada).
  - O 502 e os demais respondem com `Access-Control-Allow-Origin` da página, senão o navegador bloqueia a leitura e o
    caso vira (i), como na vida real; é a leitura da resposta que (ii) trata.
  - Um JSON sem `status` (ex.: {"detail": "..."} de um 500 do FastAPI) NÃO é testado: o contrato diz "JSON do chat" e
    não define esse caso; fica a critério do dev (relatado ao orquestrador).

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e6_landing.py (dublê do Groq, banco temporário, CORS só para a origem estática).
  - Landing: http.server em 127.0.0.1, porta livre, com três caminhos (cópia com literal trocado, original e original com
    a meta preenchida). A2/A3/A4 respondem a API por page.route (nenhum cenário depende da porta 8000 da máquina).

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_r3a_landing_chat_config.py -s
"""

import http.server
import json
import re
import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from test_e6_landing_chat import (  # noqa: E402  (helpers do harness da E6; nenhum teste é importado)
    BACKEND_URL_DA_LANDING, LANDING, LLM_INDISPONIVEL, MARCADOR_FALHA, PREFIXO_RESPOSTA, REPO, TIMEOUT, _encerrar,
    _esperar_http, _iniciar, _porta_livre,
)

TEXTO_REDE = "Não consegui falar com o servidor. Verifique sua conexão e tente de novo em instantes."
TEXTO_SERVIDOR = "O servidor teve um problema para responder. Tente de novo em instantes."
TEXTO_GENERICO_ANTIGO = "não foi possível conectar ao servidor"
ERRO_429 = "Muitas mensagens em pouco tempo. Aguarde um instante."  # o mesmo de core/rate_limit.ERRO_CHAT
DICA_CORS = "CORS_ALLOWED_ORIGINS"
MARCA_DO_CORPO = "CORPO-BRUTO-R3A"  # texto que só existe no corpo das respostas falsas; nunca pode aparecer na tela

SEL_BOT = "#chat-messages .msg-bot"
SEL_STATUS = ".chat-header-info span"
SEL_UP = '[data-testid="chat-feedback-up"]'
SEL_DOWN = '[data-testid="chat-feedback-down"]'

LANDING_FORA = "https://landing.exemplo.test"
API_FORA = "https://api.exemplo.test"
LOCAL_8000 = "http://localhost:8000"

CURSO_STUB = {"id": "curso_stub_r3a", "name": "Curso Stub R3A", "level": "Básico", "price": 123}
SESSAO_STUB = "a" * 32
REPLY_STUB = "b" * 32


# ---------------------------------------------------------------------------------------------
# Páginas servidas
# ---------------------------------------------------------------------------------------------

def _html_original():
    return LANDING.read_text(encoding="utf-8")


def _html_com_literal_trocado(api):
    """Igual ao helper `_servidor_da_landing` da E6: o literal vira o backend de teste (cópia em memória)."""
    html = _html_original()
    if BACKEND_URL_DA_LANDING not in html:
        raise RuntimeError(f"a landing não declara mais {BACKEND_URL_DA_LANDING}; ajuste o helper de teste")
    return html.replace(BACKEND_URL_DA_LANDING, api)


def _html_com_meta(html, valor):
    """Preenche `<meta name="gtt-api-url">`. Se a landing ainda não tem a meta (red), insere a tag no head: assim o
    cenário falha pelo comportamento (endereço ignorado) e não por erro de harness; a ausência da meta é o S1."""
    tag = f'<meta name="gtt-api-url" content="{valor}">'
    novo, quantas = re.subn(r"""<meta\s+name="gtt-api-url"\s+content="[^"]*"\s*/?>""", lambda _: tag, html, count=1)
    if not quantas:
        novo = html.replace("</head>", tag + "\n</head>", 1)
    if novo == html:
        raise RuntimeError("não consegui preencher a meta gtt-api-url na cópia servida")
    return novo


def _servidor_estatico(porta, paginas):
    """Serve `paginas` ({caminho: bytes}) em 127.0.0.1:porta; qualquer outro caminho dá 404."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            conteudo = paginas.get(self.path.split("?")[0])
            if conteudo is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(conteudo)))
            self.end_headers()
            self.wfile.write(conteudo)

        def log_message(self, *args):
            pass

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


@pytest.fixture(scope="module")
def servidores():
    """Backend de teste (dublê do Groq, banco temporário) e servidor estático; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_r3a_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_LANDING_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://127.0.0.1:{porta_web}"
    log_api = tmp / "backend.log"
    processo = arquivo = estatico = None
    try:
        arquivo = open(log_api, "wb")
        processo = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_e6_landing.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--log-llm", str(tmp / "llm.jsonl"), "--cors-origin", base],
            arquivo, REPO / "backend",
        )
        _esperar_http(api + "/health", 90, processo, "backend de teste", log_api)
        original = _html_original()
        estatico = _servidor_estatico(porta_web, {
            "/landing.html": _html_com_literal_trocado(api).encode("utf-8"),
            "/original.html": original.encode("utf-8"),
            "/meta.html": _html_com_meta(original, api + "/").encode("utf-8"),  # barra final de propósito
        })
        arquivo_file = tmp / "landing_file.html"
        arquivo_file.write_text(original, encoding="utf-8")
        yield {"api": api, "base": base, "file_url": arquivo_file.as_uri()}
    finally:
        if estatico is not None:
            estatico.shutdown()
            estatico.server_close()
        _encerrar(processo)
        if arquivo is not None:
            arquivo.close()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


# ---------------------------------------------------------------------------------------------
# Visitante (contexto próprio, uma aba) e respostas falsas de API
# ---------------------------------------------------------------------------------------------

def _caminho(url):
    return urlsplit(url).path.rstrip("/")


def _eh_post_do_chat(metodo, url):
    return metodo == "POST" and _caminho(url).endswith("/api/chat")


class Pagina:
    """Uma aba em contexto próprio: tudo o que ela pediu, o que o script escreveu no console e o que está na tela."""

    def __init__(self, browser, nome):
        self.nome = nome
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        self.page = self.contexto.new_page()
        self.requisicoes = []  # (metodo, url) em ordem
        self.consoles = []
        self.erros_pagina = []
        self.page.on("request", lambda r: self.requisicoes.append((r.method, r.url)))
        self.page.on("console", lambda m: self.consoles.append(m))
        self.page.on("pageerror", lambda e: self.erros_pagina.append(str(e)))

    # -- navegação e conversa --------------------------------------------------------------

    def abrir(self, url):
        self.page.goto(url, wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto, esperar_fim=True):
        """Digita no chat e envia (Enter). Devolve a requisição do POST /api/chat, ou None se ela não saiu."""
        if not self.page.locator("#chat-bubble.open").count():
            self.page.locator("#chat-btn").click(timeout=TIMEOUT)
        campo = self.page.locator("#chat-input")
        campo.fill(texto, timeout=TIMEOUT)
        requisicao = None
        try:
            with self.page.expect_request(lambda r: _eh_post_do_chat(r.method, r.url), timeout=TIMEOUT) as info:
                campo.press("Enter")
            requisicao = info.value
        except sync_api.TimeoutError:
            pass
        if esperar_fim:
            self.esperar_fim_do_processamento()
        return requisicao

    def esperar_fim_do_processamento(self):
        self.page.wait_for_function("document.querySelectorAll('#chat-messages .msg-processando').length === 0",
                                    timeout=TIMEOUT)

    def baloes_do_bot(self):
        return [t.strip() for t in self.page.locator(SEL_BOT).all_inner_texts()]

    def esperar_balao(self, trecho):
        try:
            self.page.locator(SEL_BOT).filter(has_text=trecho).first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise AssertionError(f"{self.nome}: o bot não mostrou {trecho!r}; balões do bot: {self.baloes_do_bot()}")

    def status(self):
        return (self.page.locator(SEL_STATUS).first.text_content() or "").strip()

    def tela_do_chat(self):
        return self.page.inner_text("#chat-messages")

    def tela_inteira(self):
        return self.page.inner_text("body")

    # -- observação ------------------------------------------------------------------------

    def chamadas_de_api(self):
        """(metodo, url) de tudo o que foi para um caminho /api/ (inclui preflight quando o Playwright o expõe)."""
        return [(m, u) for m, u in self.requisicoes if "/api/" in urlsplit(u).path]

    def urls(self, metodo, sufixo):
        return [u for m, u in self.requisicoes if m == metodo and _caminho(u).endswith(sufixo)]

    def erros_do_script(self):
        """Texto de cada console.error chamado pelo script da página (sem as mensagens do próprio Chromium)."""
        textos = []
        for msg in self.consoles:
            if msg.type != "error" or msg.text.startswith("Failed to load resource"):
                continue
            partes = [msg.text]
            for argumento in msg.args:
                try:
                    valor = argumento.json_value()
                except Exception:
                    continue
                if not isinstance(valor, str):
                    partes.append(json.dumps(valor, ensure_ascii=False, default=str))
            textos.append(" ".join(partes))
        return textos

    def clicar_feedback(self, seletor=SEL_UP):
        """Clica no 👍/👎 da última resposta e devolve a resposta HTTP do POST de feedback."""
        botao = self.page.locator(seletor).last
        botao.wait_for(timeout=TIMEOUT)
        with self.page.expect_response(
            lambda r: r.request.method == "POST" and _caminho(r.url).endswith("/api/chat/feedback"), timeout=TIMEOUT,
        ) as info:
            botao.click()
        return info.value

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


@pytest.fixture
def paginas(browser):
    criadas = []

    def nova(nome):
        pagina = Pagina(browser, nome)
        criadas.append(pagina)
        return pagina

    try:
        yield nova
    finally:
        for pagina in criadas:
            pagina.fechar()


def texto_unico(rotulo):
    """Mensagem sem palavras de curso, filtro ou preço, com marca única."""
    return f"Mensagem {rotulo} {uuid.uuid4().hex} sobre a plataforma"


def _cabecalhos_cors(origem):
    return {
        "Access-Control-Allow-Origin": origem,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Private-Network": "true",
    }


def _json(rota, corpo, origem, status=200):
    rota.fulfill(status=status, headers=dict(_cabecalhos_cors(origem), **{"Content-Type": "application/json"}),
                 body=json.dumps(corpo, ensure_ascii=False))


def _corpo_do_chat(**extra):
    corpo = {"status": "success", "message": "Resposta do stub R3A", "session_id": SESSAO_STUB, "actions": [],
             "sources": [], "pii_masked": False, "reply_id": REPLY_STUB}
    corpo.update(extra)
    return corpo


def api_falsa(origem_cors):
    """Handler de page.route que faz o papel do backend inteiro (cursos, chat e feedback), com CORS para `origem_cors`."""

    def tratar(rota):
        requisicao = rota.request
        caminho = _caminho(requisicao.url)
        if requisicao.method == "OPTIONS":
            rota.fulfill(status=204, headers=_cabecalhos_cors(origem_cors), body="")
        elif requisicao.method == "GET" and caminho == "/api/courses":
            _json(rota, {"status": "success", "total": 1, "courses": [CURSO_STUB]}, origem_cors)
        elif requisicao.method == "POST" and caminho == "/api/chat":
            _json(rota, _corpo_do_chat(), origem_cors)
        elif requisicao.method == "POST" and caminho == "/api/chat/feedback":
            _json(rota, {"status": "success", "reply_id": REPLY_STUB, "rating": "up"}, origem_cors)
        else:
            rota.fulfill(status=404, headers=_cabecalhos_cors(origem_cors), body="")

    return tratar


def pagina_estatica(html, api_handler=None):
    """Handler de page.route que serve `html` em qualquer caminho fora de /api/ (e a API falsa em /api/)."""

    def tratar(rota):
        if "/api/" in urlsplit(rota.request.url).path:
            if api_handler is None:
                rota.abort()
            else:
                api_handler(rota)
        elif _caminho(rota.request.url) in ("", "/landing_global_training.html"):
            rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            rota.fulfill(status=404, body="")

    return tratar


def bloquear(rota):
    rota.abort()


def _conferir_cursos_e_chat(p, esperado_api, texto):
    """Cursos e POST do chat foram para `esperado_api` (sem barra dupla) e a resposta aparece; devolve o texto enviado."""
    cursos = p.urls("GET", "/api/courses")
    assert cursos == [f"{esperado_api}/api/courses"], (
        f"{p.nome}: GET de cursos foi para {cursos}, esperado {esperado_api}/api/courses; "
        f"chamadas de API: {p.chamadas_de_api()}")
    p.enviar(texto)
    posts = p.urls("POST", "/api/chat")
    assert posts == [f"{esperado_api}/api/chat"], (
        f"{p.nome}: POST do chat foi para {posts}, esperado {esperado_api}/api/chat; chamadas de API: {p.chamadas_de_api()}")


# ---------------------------------------------------------------------------------------------
# S1, S2 - marcação e script (sem navegador)
# ---------------------------------------------------------------------------------------------

def _script_inline(html):
    achados = [m.group(2) for m in re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", html, re.S | re.I)
               if "src=" not in m.group(1).lower()]
    assert len(achados) == 1, f"{len(achados)} <script> inline na landing (esperado 1)"
    return achados[0]


def test_s1_head_declara_a_meta_gtt_api_url_vazia():
    html = _html_original()
    head = re.search(r"<head\b.*?</head\s*>", html, re.S | re.I)
    assert head, "a landing não tem <head>"
    meta = re.search(r"""<meta\s+name="gtt-api-url"\s+content="([^"]*)"\s*/?>""", head.group(0))
    assert meta, '<head> sem <meta name="gtt-api-url" content="">'
    assert meta.group(1) == "", f"a landing deve ser entregue com a meta vazia (endereço automático); veio {meta.group(1)!r}"


def test_s2_literal_e_constante_do_script_continuam():
    script = _script_inline(_html_original())
    assert BACKEND_URL_DA_LANDING in script, (
        f"o script perdeu o literal {BACKEND_URL_DA_LANDING}; os e2e E6/F5b/F6/GR* trocam esse literal na cópia servida")
    declaracoes = re.findall(r"\bconst\s+BACKEND_URL\b", script)
    assert len(declaracoes) == 1, f"`const BACKEND_URL` aparece {len(declaracoes)} vezes (esperado 1)"


# ---------------------------------------------------------------------------------------------
# P0 - pré-condição
# ---------------------------------------------------------------------------------------------

def test_p0_chat_funciona_com_o_harness_atual(servidores, paginas):
    p = paginas("P0")
    p.abrir(servidores["base"] + "/landing.html")
    texto = texto_unico("p0")
    requisicao = p.enviar(texto)
    assert requisicao is not None, "a landing não enviou POST /api/chat"
    assert requisicao.url == f"{servidores['api']}/api/chat", requisicao.url
    p.esperar_balao(PREFIXO_RESPOSTA + texto)
    assert p.status() == "Online agora", p.status()


# ---------------------------------------------------------------------------------------------
# A1 a A4 - endereço da API
# ---------------------------------------------------------------------------------------------

def test_a1_meta_preenchida_leva_cursos_chat_e_feedback_ao_endereco_sem_barra_final(servidores, paginas):
    api = servidores["api"]
    p = paginas("A1")
    p.contexto.route(f"{LOCAL_8000}/**", bloquear)  # hermético: nada sai para a porta 8000 da máquina
    p.abrir(servidores["base"] + "/meta.html")  # meta = api + "/" (o literal da landing NÃO foi trocado)
    texto = texto_unico("a1")
    _conferir_cursos_e_chat(p, api, texto)
    p.esperar_balao(PREFIXO_RESPOSTA + texto)
    resposta = p.clicar_feedback()
    assert resposta.url == f"{api}/api/chat/feedback", f"o feedback foi para {resposta.url}"
    assert resposta.status == 200, f"feedback respondeu {resposta.status}"
    nunca = [u for _, u in p.chamadas_de_api() if "localhost:8000" in u or "//api" in u.split("://", 1)[1]]
    assert not nunca, f"requisição para localhost:8000 ou com barra dupla: {nunca}"
    assert p.status() == "Online agora"


def test_a1b_meta_preenchida_vence_tambem_fora_do_localhost(servidores, paginas):
    p = paginas("A1b")
    html = _html_com_meta(_html_original(), API_FORA + "/")
    p.contexto.route(f"{LOCAL_8000}/**", bloquear)
    p.contexto.route(f"{API_FORA}/**", api_falsa(LANDING_FORA))
    p.contexto.route(f"{LANDING_FORA}/**", pagina_estatica(html))
    p.abrir(LANDING_FORA + "/")
    _conferir_cursos_e_chat(p, API_FORA, texto_unico("a1b"))
    p.esperar_balao("Resposta do stub R3A")
    resposta = p.clicar_feedback()
    assert resposta.url == f"{API_FORA}/api/chat/feedback", resposta.url
    fora = [u for _, u in p.chamadas_de_api() if not u.startswith(API_FORA + "/api/")]
    assert not fora, f"requisições fora de {API_FORA}: {fora}"


def test_a2_meta_vazia_em_127_0_0_1_usa_localhost_8000(servidores, paginas):
    p = paginas("A2")
    p.contexto.route(f"{LOCAL_8000}/**", api_falsa("*"))
    p.abrir(servidores["base"] + "/original.html")  # literal da landing intacto
    _conferir_cursos_e_chat(p, LOCAL_8000, texto_unico("a2"))
    p.esperar_balao("Resposta do stub R3A")
    resposta = p.clicar_feedback()
    assert resposta.url == f"{LOCAL_8000}/api/chat/feedback", resposta.url
    fora = [u for _, u in p.chamadas_de_api() if not u.startswith(LOCAL_8000 + "/api/")]
    assert not fora, f"em host local a API deve ser {LOCAL_8000}; foram para {fora}"


def test_a3_meta_vazia_em_host_nao_local_usa_a_mesma_origem(servidores, paginas):
    p = paginas("A3")
    p.contexto.route(f"{LOCAL_8000}/**", bloquear)
    p.contexto.route(f"{LANDING_FORA}/**", pagina_estatica(_html_original(), api_falsa(LANDING_FORA)))
    p.abrir(LANDING_FORA + "/")
    assert urlsplit(p.page.url).hostname == "landing.exemplo.test", p.page.url
    _conferir_cursos_e_chat(p, LANDING_FORA, texto_unico("a3"))
    p.esperar_balao("Resposta do stub R3A")
    resposta = p.clicar_feedback()
    assert resposta.url == f"{LANDING_FORA}/api/chat/feedback", resposta.url
    locais = [u for _, u in p.chamadas_de_api() if "localhost" in u or "127.0.0.1" in u]
    assert not locais, f"fora de localhost a landing nunca pode chamar localhost: {locais}"
    assert p.status() == "Online agora"


def test_a4_pagina_por_file_resolve_para_localhost_8000(servidores, paginas):
    p = paginas("A4")
    p.contexto.route(f"{LOCAL_8000}/**", api_falsa("*"))
    p.abrir(servidores["file_url"])
    assert p.page.url.startswith("file://"), p.page.url
    cursos = p.urls("GET", "/api/courses")
    assert cursos == [f"{LOCAL_8000}/api/courses"], f"por file:// os cursos foram para {cursos}: {p.chamadas_de_api()}"
    p.enviar(texto_unico("a4"))
    posts = p.urls("POST", "/api/chat")
    assert posts == [f"{LOCAL_8000}/api/chat"], f"por file:// o chat foi para {posts}: {p.chamadas_de_api()}"


# ---------------------------------------------------------------------------------------------
# E1 a E4 - erros distintos
# ---------------------------------------------------------------------------------------------

class Chave:
    """Liga e desliga a falha do POST /api/chat de dentro do teste."""

    def __init__(self):
        self.ligada = False


def _rota_do_chat_com_falha(chave, falha):
    """`falha(rota)` responde o POST enquanto a chave está ligada; fora disso (e no preflight) a requisição vai ao backend."""

    def tratar(rota):
        if rota.request.method == "POST" and chave.ligada:
            falha(rota)
        else:
            rota.continue_()

    return tratar


def _nao_vazou_nada_na_tela(p, api, proibidos=()):
    tela = p.tela_inteira()
    for proibido in ("TypeError", "SyntaxError", "NetworkError", "Failed to fetch", "Unexpected token", "<html", "<!doctype",
                     DICA_CORS, "localhost:8000", api, "/api/chat", *proibidos):
        assert proibido.lower() not in tela.lower(), f"{p.nome}: {proibido!r} apareceu na tela: {tela[-400:]!r}"


def test_e1_falha_de_rede_mostra_texto_proprio_offline_e_diagnostico_so_no_console(servidores, paginas):
    api = servidores["api"]
    p = paginas("E1")
    chave = Chave()
    p.contexto.route(f"{api}/api/chat", _rota_do_chat_com_falha(chave, lambda rota: rota.abort()))
    p.abrir(servidores["base"] + "/landing.html")

    chave.ligada = True
    requisicao = p.enviar(texto_unico("e1-sem-rede"))
    assert requisicao is not None, "a landing não tentou o POST /api/chat"
    baloes = p.baloes_do_bot()
    assert TEXTO_REDE in baloes, f"o balão de falha de rede não é o do contrato; balões do bot: {baloes}"
    assert not any(TEXTO_GENERICO_ANTIGO in b.lower() for b in baloes), f"mensagem genérica antiga na tela: {baloes}"
    assert p.status() == "Offline", f"status {p.status()!r}, esperado 'Offline'"
    erros = p.erros_do_script()
    assert any(f"{api}/api/chat" in e for e in erros), (
        f"nenhum console.error com a URL completa do POST ({api}/api/chat); console.error da página: {erros}")
    assert any(DICA_CORS in e for e in erros), f"nenhum console.error com a dica {DICA_CORS}; console.error da página: {erros}"
    _nao_vazou_nada_na_tela(p, api)
    assert p.erros_pagina == [], f"exceções de página: {p.erros_pagina}"

    chave.ligada = False  # a rede volta
    texto = texto_unico("e1-com-rede")
    p.enviar(texto)
    p.esperar_balao(PREFIXO_RESPOSTA + texto)
    assert p.status() == "Online agora", f"depois da rede voltar o status é {p.status()!r}"


CORPO_HTML_502 = ("<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1>"
                  f"<p>nginx {MARCA_DO_CORPO}</p></body></html>")
CASOS_NAO_JSON = [
    pytest.param(502, "text/html; charset=utf-8", CORPO_HTML_502, id="502-html"),
    pytest.param(503, "text/plain", f"Service Unavailable {MARCA_DO_CORPO}", id="503-texto"),
    pytest.param(500, "text/plain", f"Internal Server Error {MARCA_DO_CORPO}", id="500-texto"),
    pytest.param(200, "text/html; charset=utf-8", CORPO_HTML_502.replace("502", "200"), id="200-pagina-html"),
]


@pytest.mark.parametrize("status,tipo,corpo", CASOS_NAO_JSON)
def test_e2_resposta_que_nao_e_json_do_chat_mostra_texto_do_servidor_e_nao_vaza_o_corpo(servidores, paginas, status, tipo, corpo):
    api, base = servidores["api"], servidores["base"]
    p = paginas(f"E2-{status}")
    chave = Chave()

    def responder(rota):
        rota.fulfill(status=status, headers=dict(_cabecalhos_cors(base), **{"Content-Type": tipo}), body=corpo)

    p.contexto.route(f"{api}/api/chat", _rota_do_chat_com_falha(chave, responder))
    p.abrir(base + "/landing.html")

    chave.ligada = True
    requisicao = p.enviar(texto_unico("e2"))
    assert requisicao is not None, "a landing não enviou o POST /api/chat"
    baloes = p.baloes_do_bot()
    assert TEXTO_SERVIDOR in baloes, f"o balão de resposta inválida não é o do contrato; balões do bot: {baloes}"
    assert TEXTO_REDE not in baloes, "resposta do servidor tratada como falha de rede"
    assert not any(TEXTO_GENERICO_ANTIGO in b.lower() for b in baloes), f"mensagem genérica antiga na tela: {baloes}"
    assert p.status() == "Offline", f"status {p.status()!r}, esperado 'Offline'"
    erros = p.erros_do_script()
    assert any(f"{api}/api/chat" in e for e in erros), (
        f"nenhum console.error com a URL completa do POST ({api}/api/chat); console.error da página: {erros}")
    assert any(re.search(rf"(?<!\d){status}(?!\d)", e) for e in erros), (
        f"nenhum console.error com o status HTTP {status}; console.error da página: {erros}")
    _nao_vazou_nada_na_tela(p, api, proibidos=(MARCA_DO_CORPO, "Bad Gateway", "Service Unavailable", "Internal Server Error", "nginx"))
    assert p.erros_pagina == [], f"exceções de página: {p.erros_pagina}"

    chave.ligada = False  # o servidor volta
    texto = texto_unico("e2-depois")
    p.enviar(texto)
    p.esperar_balao(PREFIXO_RESPOSTA + texto)
    assert p.status() == "Online agora", f"depois do servidor voltar o status é {p.status()!r}"


def _conferir_erro_json_do_servidor(p, api, esperado_no_balao):
    baloes = p.baloes_do_bot()
    assert any(esperado_no_balao in b for b in baloes), f"o texto do servidor sumiu; balões do bot: {baloes}"
    assert any(b.startswith("Erro:") and esperado_no_balao in b for b in baloes), f"o texto não veio como 'Erro: ...': {baloes}"
    assert TEXTO_REDE not in baloes and TEXTO_SERVIDOR not in baloes, f"erro de JSON tratado como (i) ou (ii): {baloes}"
    assert not any(TEXTO_GENERICO_ANTIGO in b.lower() for b in baloes), baloes
    assert p.status() == "Online agora", f"status {p.status()!r}, esperado 'Online agora' (o servidor respondeu)"
    erros = p.erros_do_script()
    assert erros == [], f"console.error de diagnóstico num erro JSON do servidor: {erros}"
    assert p.erros_pagina == [], f"exceções de página: {p.erros_pagina}"


def test_e3a_llm_indisponivel_continua_com_o_texto_do_servidor_e_online(servidores, paginas):
    api = servidores["api"]
    p = paginas("E3a")
    p.abrir(servidores["base"] + "/landing.html")
    requisicao = p.enviar(f"{texto_unico('e3a')} {MARCADOR_FALHA}")
    assert requisicao is not None, "a landing não enviou o POST /api/chat"
    _conferir_erro_json_do_servidor(p, api, LLM_INDISPONIVEL)


def test_e3b_429_com_json_de_erro_continua_com_o_texto_do_servidor_e_online(servidores, paginas):
    api, base = servidores["api"], servidores["base"]
    p = paginas("E3b")

    def limite(rota):
        if rota.request.method == "POST":
            _json(rota, {"status": "error", "message": ERRO_429}, base, status=429)
        else:
            rota.continue_()

    p.contexto.route(f"{api}/api/chat", limite)
    p.abrir(base + "/landing.html")
    requisicao = p.enviar(texto_unico("e3b"))
    assert requisicao is not None, "a landing não enviou o POST /api/chat"
    _conferir_erro_json_do_servidor(p, api, ERRO_429)


def test_e4a_sucesso_normal_ponta_a_ponta_com_feedback(servidores, paginas):
    api = servidores["api"]
    p = paginas("E4a")
    p.abrir(servidores["base"] + "/landing.html")
    texto = texto_unico("e4a")
    requisicao = p.enviar(texto)
    assert requisicao is not None and requisicao.url == f"{api}/api/chat"
    p.esperar_balao(PREFIXO_RESPOSTA + texto)
    assert any(t.strip() == texto for t in p.page.locator("#chat-messages .msg-user").all_inner_texts())
    assert p.status() == "Online agora"
    resposta = p.clicar_feedback(SEL_UP)
    assert resposta.status == 200 and resposta.url == f"{api}/api/chat/feedback", (resposta.status, resposta.url)
    assert p.page.locator(SEL_UP).last.get_attribute("aria-pressed") == "true"
    assert p.page.locator(SEL_DOWN).last.get_attribute("aria-pressed") == "false"
    assert p.erros_do_script() == [], p.erros_do_script()
    assert p.erros_pagina == [], p.erros_pagina
    for esperado in (TEXTO_REDE, TEXTO_SERVIDOR):
        assert esperado not in p.baloes_do_bot(), f"texto de erro na tela depois de um sucesso: {esperado!r}"


def test_e4b_sucesso_com_fonte_acoes_aviso_e_markdown_sem_regressao(servidores, paginas):
    api, base = servidores["api"], servidores["base"]
    p = paginas("E4b")
    corpo = _corpo_do_chat(
        message="Texto com **negrito**.\n\n- item um\n- item dois",
        sources=[{"title": "Política de reembolso"}],
        pii_masked=True,
        actions=[
            {"type": "enroll", "course_id": "excel_profissional", "label": "Matricular no curso", "class_id": None},
            {"type": "handoff", "label": "Falar com um atendente no WhatsApp", "url": "https://wa.me/5511900000000?text=Ola"},
            {"type": "login", "label": "Entrar na Área do aluno"},
        ],
    )

    def resposta(rota):
        if rota.request.method == "POST":
            _json(rota, corpo, base)
        else:
            rota.continue_()

    p.contexto.route(f"{api}/api/chat", resposta)
    p.abrir(base + "/landing.html")
    requisicao = p.enviar(texto_unico("e4b"))
    assert requisicao is not None and requisicao.url == f"{api}/api/chat"
    p.esperar_balao("Texto com")
    assert p.page.locator(f"{SEL_BOT} strong", has_text="negrito").count() == 1, "o markdown (negrito) não foi renderizado"
    assert p.page.locator(f"{SEL_BOT} li").count() == 2, "o markdown (lista) não foi renderizado"
    assert p.page.locator('[data-testid="chat-fonte"]').inner_text().strip() == "Fonte: Política de reembolso"
    assert p.page.locator('[data-testid="chat-aviso-pii"]').count() == 1, "sem o aviso de dado pessoal removido"
    matricular = p.page.locator('[data-testid="chat-acao-matricular"]')
    assert matricular.count() == 1 and matricular.inner_text().strip() == "Matricular no curso"
    assert "/login?area=aluno&next=" in (matricular.get_attribute("href") or ""), matricular.get_attribute("href")
    whatsapp = p.page.locator('[data-testid="chat-acao-whatsapp"]')
    assert whatsapp.count() == 1 and (whatsapp.get_attribute("href") or "").startswith("https://wa.me/")
    assert p.page.locator('[data-testid="chat-acao-login"]').count() == 1, "sem a ação de login da Área do aluno"
    assert p.page.locator(SEL_UP).count() == 1 and p.page.locator(SEL_DOWN).count() == 1, "sem os botões de feedback"
    assert p.status() == "Online agora"
    assert p.erros_do_script() == [], p.erros_do_script()
    assert p.erros_pagina == [], p.erros_pagina
