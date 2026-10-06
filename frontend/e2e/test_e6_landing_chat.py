"""E2E do chat da landing page estática (E6, Chromium via Playwright). D38.1: sessão anônima emitida pelo servidor.

A landing (frontend/landing_global_training.html) hoje envia `session_id: 'web-chat-session'` fixo. Contrato
decidido pelo orquestrador: o JavaScript guarda em `sessionStorage` (chave `gt_chat_session_id`) o
`session_id` devolvido pelo servidor e o reenvia nas mensagens seguintes da mesma aba (inclusive depois de
recarregar a página). NUNCA envia 'web-chat-session', 'default' nem id inventado pelo cliente. Na primeira
mensagem de uma aba nova o corpo do POST não leva `session_id` (ausente, vazio ou null).

Cenários (cada um independente, com contexto de navegador próprio):
  P0 pré-condição (anterior ao contrato; passa no red): o chat da landing funciona contra o backend de teste,
     a mensagem do visitante e a resposta do bot aparecem. Garante que o red é por falta do contrato, e não
     por servidor, página ou fixture.
  C1 primeira mensagem de uma aba nova: o POST não leva session_id e, depois da resposta, o sessionStorage
     guarda um id de 32 hex igual ao devolvido pelo servidor
  C2 segunda mensagem na mesma aba: o POST leva o id guardado, a resposta do bot aparece e o contexto que
     chegou ao LLM (dublê) inclui a primeira mensagem
  C3 depois de recarregar a página, a mesma aba continua a conversa com o mesmo id e o contexto do LLM
     ainda inclui as mensagens de antes do reload
  C4 um segundo contexto de navegador começa sem id, recebe id diferente, e o contexto enviado ao LLM nunca
     contém texto do primeiro visitante (nem o do primeiro ao segundo, nem o do segundo ao primeiro)
  C5 'web-chat-session' e 'default' nunca aparecem em nenhuma requisição (URL, cabeçalhos ou corpo), nem como
     session_id, em um fluxo com mensagens, reload e um segundo visitante
  C6 com erro do LLM (dublê levanta), a landing mostra a mensagem do servidor "O assistente está indisponível
     no momento. Tente novamente em instantes." e o id guardado permanece; a conversa continua com o mesmo id
  C7 sem erros de console nem exceções de página no fluxo completo (mensagens, reload, erro do LLM). Erro
     reprova quando há console.error, exceção de página ou resposta HTTP 4xx/5xx de recurso da própria página

Como a landing é estática: o teste a serve com um servidor HTTP em porta livre (thread do próprio teste) e
troca, SÓ NA CÓPIA SERVIDA, a constante `BACKEND_URL` (http://localhost:8000) pelo backend de teste. O
arquivo da landing não é lido para escrita. O JavaScript do chat roda exatamente como está. A folha de estilo
do Google Fonts é respondida vazia (sem depender da internet).

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e6_landing.py (reaproveita servidor_e2e_e5.py) num processo próprio, com
      * Groq SUBSTITUÍDO por dublê (nenhuma chamada real; falha sob demanda com o marcador FALHAR-LLM);
      * banco SQLite temporário isolado (o backend/db.sqlite de desenvolvimento não é aberto, D7);
      * variáveis de ambiente de teste fabricadas (nada real, nada gravado em arquivo versionado).
  - Landing: http.server em 127.0.0.1, porta livre.
  - O processo do teste não abre banco nenhum; o contexto enviado ao LLM é lido do log do dublê.

Pré-requisitos: dependências do backend (fastapi, uvicorn) e o Chromium do Playwright:
  py -3 -m playwright install chromium
Não precisa de ng serve nem de node_modules.

Portas: livres e escolhidas pelo próprio teste. Fixe com E2E_BACKEND_PORT / E2E_LANDING_PORT se precisar.
Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_e6_landing_chat.py -s
"""

import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
REPO = E2E_DIR.parents[1]
LANDING = REPO / "frontend" / "landing_global_training.html"

IS_WINDOWS = os.name == "nt"
TIMEOUT = 8000
CHAVE_SESSAO = "gt_chat_session_id"
HEX32 = re.compile(r"^[0-9a-f]{32}$")
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "  # o mesmo do dublê (servidor_e2e_e5.PREFIXO_RESPOSTA)
MARCADOR_FALHA = "FALHAR-LLM"  # o mesmo do dublê (servidor_e2e_e6_landing.MARCADOR_FALHA)
LLM_INDISPONIVEL = "O assistente está indisponível no momento. Tente novamente em instantes."
ID_FIXO_ANTIGO = "web-chat-session"
ID_PADRAO = "default"
BACKEND_URL_DA_LANDING = "http://localhost:8000"
SEL_BOT = "#chat-messages .msg-bot"


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


# ---------------------------------------------------------------------------------------------
# Servidores de teste
# ---------------------------------------------------------------------------------------------

def _porta_livre(variavel):
    fixa = os.environ.get(variavel)
    if fixa:
        return int(fixa)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iniciar(comando, log, cwd):
    argumentos = {"cwd": str(cwd), "stdout": log, "stderr": subprocess.STDOUT}
    if IS_WINDOWS:
        argumentos["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        argumentos["start_new_session"] = True
    return subprocess.Popen(comando, **argumentos)


def _encerrar(processo):
    if processo is None or processo.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            import signal
            os.killpg(os.getpgid(processo.pid), signal.SIGTERM)
        processo.wait(timeout=30)
    except Exception:
        try:
            processo.kill()
        except Exception:
            pass


def _final_do_log(caminho, linhas=25):
    try:
        return "\n".join(Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines()[-linhas:])
    except OSError:
        return "(sem log)"


def _esperar_http(url, limite_s, processo, rotulo, log_path):
    fim = time.time() + limite_s
    while time.time() < fim:
        if processo.poll() is not None:
            raise RuntimeError(f"{rotulo} terminou antes de ficar pronto (código {processo.returncode}):\n{_final_do_log(log_path)}")
        try:
            with urllib.request.urlopen(url, timeout=3) as resposta:
                if resposta.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{rotulo} não respondeu em {limite_s}s em {url}:\n{_final_do_log(log_path)}")


def _servidor_da_landing(porta, api):
    """Serve a landing (cópia em memória com BACKEND_URL apontando para o backend de teste)."""
    html = LANDING.read_text(encoding="utf-8")
    if BACKEND_URL_DA_LANDING not in html:
        raise RuntimeError(f"a landing não declara mais {BACKEND_URL_DA_LANDING}; ajuste o helper de teste")
    conteudo = html.replace(BACKEND_URL_DA_LANDING, api).encode("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/landing_global_training.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(conteudo)))
                self.end_headers()
                self.wfile.write(conteudo)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *args):
            pass

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor


@pytest.fixture(scope="module")
def servidores():
    """Sobe backend (dublê do Groq, banco temporário) e o servidor estático da landing; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_e6_landing_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_LANDING_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://127.0.0.1:{porta_web}"
    log_api = tmp / "backend.log"
    processo = None
    arquivo = None
    estatico = None
    try:
        arquivo = open(log_api, "wb")
        processo = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_e6_landing.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--log-llm", str(tmp / "llm.jsonl")],
            arquivo, REPO / "backend",
        )
        _esperar_http(api + "/health", 90, processo, "backend de teste", log_api)
        estatico = _servidor_da_landing(porta_web, api)
        yield {"base": base, "api": api, "llm_log": tmp / "llm.jsonl"}
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
# Visitante (uma aba em um contexto de navegador próprio) e leitura do log do dublê
# ---------------------------------------------------------------------------------------------

class Visitante:
    """Um visitante da landing: contexto próprio, uma aba, e tudo o que a aba pediu ao backend."""

    def __init__(self, browser, servidores, nome):
        self.nome = nome
        self.url = servidores["base"] + "/landing_global_training.html"
        self.api = servidores["api"]
        self.contexto = browser.new_context()
        # a folha de estilo do Google Fonts não é do escopo do teste; evita depender da internet
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        self.page = self.contexto.new_page()
        self.requisicoes = []  # (metodo, url, cabecalhos, corpo)
        self.respostas_chat = []  # JSON de cada resposta de POST /api/chat
        self.erros_console = []
        self.erros_pagina = []
        self.erros_http = []
        self.page.on("request", lambda r: self.requisicoes.append((r.method, r.url, dict(r.headers), r.post_data or "")))
        self.page.on("console", self._console)
        self.page.on("pageerror", lambda e: self.erros_pagina.append(str(e)))
        self.page.on("response", self._resposta)

    def _console(self, msg):
        if msg.type == "error":
            self.erros_console.append(msg.text)

    def _resposta(self, resposta):
        if resposta.status >= 400:
            self.erros_http.append(f"HTTP {resposta.status} {resposta.url}")

    # -- navegação e conversa --------------------------------------------------------------

    def abrir(self):
        self.page.goto(self.url, wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def recarregar(self):
        self.page.reload(wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto):
        """Digita no chat da landing, envia (Enter) e devolve (corpo_enviado_ou_None, resposta_json)."""
        if not self.page.locator("#chat-bubble.open").count():
            self.page.locator("#chat-btn").click(timeout=TIMEOUT)
        campo = self.page.locator("#chat-input")
        campo.fill(texto, timeout=TIMEOUT)
        try:
            with self.page.expect_response(
                lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/chat"),
                timeout=TIMEOUT,
            ) as info:
                campo.press("Enter")
        except sync_api.TimeoutError:
            raise Falha(f"{self.nome}: a landing não enviou POST /api/chat ao enviar {texto!r}")
        resposta = info.value
        corpo_enviado = resposta.request.post_data_json
        dados = resposta.json()
        self.respostas_chat.append(dados)
        return corpo_enviado, dados

    def textos_do_bot(self):
        return self.page.locator(SEL_BOT).all_inner_texts()

    def esperar_texto_do_bot(self, trecho):
        try:
            self.page.locator(SEL_BOT).filter(has_text=trecho).first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{self.nome}: o bot não mostrou {trecho!r}; textos do bot na tela: {self.textos_do_bot()}")

    def id_guardado(self):
        return self.page.evaluate(f"sessionStorage.getItem({json.dumps(CHAVE_SESSAO)})")

    def posts_de_chat(self):
        return [r for r in self.requisicoes if r[0] == "POST" and r[1].rstrip("/").endswith("/api/chat")]

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


def texto_unico(rotulo):
    """Mensagem de visitante sem palavras de curso, filtro ou preço, com marca única para rastrear no log do LLM."""
    return f"Mensagem {rotulo} {uuid.uuid4().hex} sobre a plataforma"


def chamadas_llm(servidores):
    """Todas as chamadas que o dublê recebeu (lista de listas de mensagens), em ordem."""
    caminho = servidores["llm_log"]
    if not caminho.exists():
        return []
    return [json.loads(linha)["messages"] for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _conteudos(mensagens):
    return [m.get("content") or "" for m in mensagens]


def chamada_de_resposta_para(servidores, marca):
    """Chamada de resposta (não a de roteamento) cuja última mensagem de usuário contém `marca`."""
    achadas = []
    for mensagens in chamadas_llm(servidores):
        sistema = " ".join(m.get("content") or "" for m in mensagens if m.get("role") == "system")
        if "identifica intenções" in sistema:
            continue
        usuarios = [m.get("content") or "" for m in mensagens if m.get("role") == "user"]
        if usuarios and marca in usuarios[-1]:
            achadas.append(mensagens)
    return achadas


def _sessao_enviada(corpo):
    """Valor de session_id do corpo do POST, ou None se ausente/vazio/null."""
    valor = (corpo or {}).get("session_id")
    return valor if valor else None


@pytest.fixture
def visitantes(browser, servidores):
    criados = []

    def novo(nome):
        v = Visitante(browser, servidores, nome)
        criados.append(v)
        return v

    try:
        yield novo
    finally:
        for v in criados:
            v.fechar()


# ---------------------------------------------------------------------------------------------
# P0 - pré-condição
# ---------------------------------------------------------------------------------------------

def test_p0_chat_da_landing_funciona_com_o_backend_de_teste(servidores, visitantes):
    v = visitantes("P0")
    v.abrir()
    texto = texto_unico("p0")
    corpo, dados = v.enviar(texto)
    assert dados.get("status") == "success", dados
    v.esperar_texto_do_bot(PREFIXO_RESPOSTA + texto)
    assert any(t.strip() == texto for t in v.page.locator("#chat-messages .msg-user").all_inner_texts())
    assert re.fullmatch(r"[0-9a-f]{32}", dados.get("session_id", "")), dados  # o backend da E6 está de pé


# ---------------------------------------------------------------------------------------------
# C1 a C7 - contrato da landing
# ---------------------------------------------------------------------------------------------

def test_c1_primeira_mensagem_sem_session_id_e_id_guardado_no_session_storage(servidores, visitantes):
    v = visitantes("C1")
    v.abrir()
    assert v.id_guardado() is None, "aba nova deveria começar sem id em sessionStorage"
    corpo, dados = v.enviar(texto_unico("c1"))
    assert _sessao_enviada(corpo) is None, f"primeira mensagem não deveria levar session_id; corpo enviado: {corpo}"
    emitido = dados["session_id"]
    assert HEX32.match(emitido), dados
    guardado = v.id_guardado()
    assert guardado is not None, f"a landing não guardou o id em sessionStorage[{CHAVE_SESSAO}]"
    assert HEX32.match(guardado), f"id guardado não tem 32 hex: {guardado!r}"
    assert guardado == emitido, "o id guardado deve ser o que o servidor emitiu"


def test_c2_segunda_mensagem_envia_o_id_guardado_e_o_llm_ve_a_primeira(servidores, visitantes):
    v = visitantes("C2")
    v.abrir()
    t1, t2 = texto_unico("c2-primeira"), texto_unico("c2-segunda")
    _, d1 = v.enviar(t1)
    v.esperar_texto_do_bot(PREFIXO_RESPOSTA + t1)
    id1 = d1["session_id"]
    corpo2, d2 = v.enviar(t2)
    assert _sessao_enviada(corpo2) == id1, f"a 2ª mensagem deveria levar o id emitido ({id1}); corpo enviado: {corpo2}"
    assert d2.get("status") == "success", d2
    assert d2["session_id"] == id1, "o servidor deveria continuar a mesma sessão"
    v.esperar_texto_do_bot(PREFIXO_RESPOSTA + t2)
    chamadas = chamada_de_resposta_para(servidores, t2)
    assert chamadas, "o dublê não recebeu a chamada de resposta da 2ª mensagem"
    assert any(t1 in c for c in _conteudos(chamadas[-1])), "o contexto da 2ª mensagem não inclui a 1ª"


def test_c3_depois_de_recarregar_a_mesma_aba_continua_com_o_mesmo_id(servidores, visitantes):
    v = visitantes("C3")
    v.abrir()
    t1, t2 = texto_unico("c3-antes"), texto_unico("c3-depois")
    _, d1 = v.enviar(t1)
    id1 = d1["session_id"]
    assert v.id_guardado() == id1, "pré-condição: o id emitido deve estar em sessionStorage antes do reload"
    v.recarregar()
    assert v.id_guardado() == id1, "o id sumiu de sessionStorage depois de recarregar a página"
    corpo2, d2 = v.enviar(t2)
    assert _sessao_enviada(corpo2) == id1, f"depois do reload a landing deveria enviar {id1}; corpo enviado: {corpo2}"
    assert d2["session_id"] == id1
    chamadas = chamada_de_resposta_para(servidores, t2)
    assert chamadas, "o dublê não recebeu a chamada de resposta da mensagem pós-reload"
    assert any(t1 in c for c in _conteudos(chamadas[-1])), "o contexto pós-reload não inclui a mensagem de antes do reload"


def test_c4_outro_visitante_nao_compartilha_id_nem_historico(servidores, visitantes):
    a = visitantes("A")
    a.abrir()
    a1, a2 = texto_unico("c4-a1"), texto_unico("c4-a2")
    _, da = a.enviar(a1)
    id_a = da["session_id"]

    b = visitantes("B")
    b.abrir()
    assert b.id_guardado() is None, "o 2º visitante (contexto novo) deveria começar sem id"
    b1, b2 = texto_unico("c4-b1"), texto_unico("c4-b2")
    corpo_b, db = b.enviar(b1)
    assert _sessao_enviada(corpo_b) is None, f"o 2º visitante não deveria enviar session_id na 1ª mensagem; corpo: {corpo_b}"
    id_b = db["session_id"]
    assert HEX32.match(id_b) and id_b != id_a, f"B recebeu id igual ao de A ({id_a}) ou inválido ({id_b})"
    assert b.id_guardado() == id_b

    _, db2 = b.enviar(b2)
    _, da2 = a.enviar(a2)
    assert db2["session_id"] == id_b and da2["session_id"] == id_a

    for marca, proibidos in ((b1, (a1, a2)), (b2, (a1, a2)), (a2, (b1, b2))):
        chamadas = chamada_de_resposta_para(servidores, marca)
        assert chamadas, f"o dublê não recebeu a chamada de resposta de {marca}"
        for proibido in proibidos:
            assert not any(proibido in c for c in _conteudos(chamadas[-1])), \
                f"o contexto enviado ao LLM para {marca!r} vazou {proibido!r} de outro visitante"
    # o contexto legítimo de cada um continua presente (o isolamento não pode custar a própria sessão)
    assert any(b1 in c for c in _conteudos(chamada_de_resposta_para(servidores, b2)[-1]))
    assert any(a1 in c for c in _conteudos(chamada_de_resposta_para(servidores, a2)[-1]))


def test_c5_web_chat_session_e_default_nunca_saem_da_landing(servidores, visitantes):
    a = visitantes("A")
    a.abrir()
    a.enviar(texto_unico("c5-a1"))
    a.enviar(texto_unico("c5-a2"))
    a.recarregar()
    a.enviar(texto_unico("c5-a3"))
    b = visitantes("B")
    b.abrir()
    b.enviar(texto_unico("c5-b1"))

    chamadas = a.posts_de_chat() + b.posts_de_chat()
    assert len(chamadas) == 4, f"esperava 4 POSTs ao chat, vieram {len(chamadas)}"
    for visitante in (a, b):
        for metodo, url, cabecalhos, corpo in visitante.requisicoes:
            alvo = " ".join([url, json.dumps(cabecalhos), corpo]).lower()
            assert ID_FIXO_ANTIGO not in alvo, f"{metodo} {url} carrega {ID_FIXO_ANTIGO!r}: {corpo}"
            assert not re.search(r'"session_id"\s*:\s*"default"', alvo), f"{metodo} {url} carrega session_id 'default': {corpo}"
        for _, _, _, corpo in visitante.posts_de_chat():
            sessao = _sessao_enviada(json.loads(corpo))
            assert sessao is None or HEX32.match(sessao), f"session_id inventado pelo cliente: {sessao!r}"
    emitidos = {d["session_id"] for d in a.respostas_chat + b.respostas_chat}
    for _, _, _, corpo in a.posts_de_chat() + b.posts_de_chat():
        sessao = _sessao_enviada(json.loads(corpo))
        assert sessao is None or sessao in emitidos, f"a landing enviou um id que o servidor nunca emitiu: {sessao!r}"


def test_c6_erro_do_llm_mostra_a_mensagem_do_servidor_e_mantem_o_id(servidores, visitantes):
    v = visitantes("C6")
    v.abrir()
    t1, t3 = texto_unico("c6-ok"), texto_unico("c6-depois")
    _, d1 = v.enviar(t1)
    id1 = d1["session_id"]
    assert v.id_guardado() == id1, "pré-condição: o id emitido deve estar guardado antes do erro"

    t_falha = f"{texto_unico('c6-falha')} {MARCADOR_FALHA}"
    corpo_f, d_f = v.enviar(t_falha)
    assert d_f.get("status") == "error" and d_f.get("message") == LLM_INDISPONIVEL, d_f
    assert _sessao_enviada(corpo_f) == id1, f"a mensagem do erro deveria levar o id guardado; corpo: {corpo_f}"
    v.esperar_texto_do_bot(LLM_INDISPONIVEL)
    assert not any("Processando" in t for t in v.textos_do_bot()), "o indicador 'Processando...' ficou na tela"
    assert not any("não foi possível conectar" in t for t in v.textos_do_bot()), \
        "a landing tratou erro do LLM como falha de conexão em vez de mostrar a mensagem do servidor"
    assert v.id_guardado() == id1, "o id guardado mudou ou sumiu depois do erro do LLM"

    corpo3, d3 = v.enviar(t3)
    assert _sessao_enviada(corpo3) == id1, f"depois do erro a landing deveria continuar com {id1}; corpo: {corpo3}"
    assert d3["session_id"] == id1
    chamadas = chamada_de_resposta_para(servidores, t3)
    assert chamadas and any(t1 in c for c in _conteudos(chamadas[-1])), "a sessão perdeu o contexto depois do erro do LLM"


def test_c7_sem_erros_de_console_no_fluxo_completo(servidores, visitantes):
    v = visitantes("C7")
    v.abrir()
    v.enviar(texto_unico("c7-a"))
    v.enviar(texto_unico("c7-b"))
    v.recarregar()
    v.enviar(texto_unico("c7-c"))
    v.enviar(f"{texto_unico('c7-falha')} {MARCADOR_FALHA}")
    v.esperar_texto_do_bot(LLM_INDISPONIVEL)
    assert v.erros_console == [], f"erros de console: {v.erros_console}"
    assert v.erros_pagina == [], f"exceções de página: {v.erros_pagina}"
    assert v.erros_http == [], f"respostas HTTP de erro: {v.erros_http}"
