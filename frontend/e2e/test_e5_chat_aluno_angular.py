"""E2E do chat do aluno logado (E5, Chromium via Playwright). Item 1.1 / chatbot autenticado (D35, D36).

Contrato de tela (decidido pelo orquestrador): em /student, aluno logado, existe uma seção com o título
visível "Assistente virtual". Seletores data-testid: chat-panel (contêiner), chat-input (campo),
chat-send (botão enviar), chat-message (uma por mensagem, atributo data-role="user" | "assistant",
em ordem cronológica crescente).

Cenários (checks numerados):
  S1 pré-condição (anterior ao chat): login do aluno em / chega a /student e a tela carrega "Meus cursos".
     Garante que o red do chat é por falta do chat, e não por servidor, login ou fixture.
  C1 /student tem a seção de chat: título "Assistente virtual" visível, chat-panel, chat-input e chat-send
  C2 ao abrir /student o histórico persistido (GET /api/student/chat/history) é carregado e exibido:
     a troca semeada pela API aparece como 2 chat-message (user, depois assistant), em ordem
  C3 enviar uma mensagem: aparecem a mensagem do aluno e, depois, a resposta do bot (4 mensagens no total,
     ordem user/assistant/user/assistant) e o campo é limpo
  C4 mensagem vazia ou só espaços não é enviada: nenhuma requisição POST, nenhuma mensagem nova,
     nada gravado no histórico do servidor
  C5 a requisição do chat leva só {"message": ...} no corpo (nenhum user_id/session_id), nem na URL
  C6 persistência: depois de recarregar a página as mesmas mensagens continuam, na mesma ordem
  C7 persistência: depois de um novo login (contexto novo de navegador) as mesmas mensagens continuam
  C8 isolamento: um segundo aluno logado não vê as mensagens do primeiro (e o primeiro não vê as dele)
  C9 funcionário (admin) não vê a seção de chat do aluno e não consegue abrir /student
  C10 sem erros de console nem exceções de página nas telas acima. Erro reprova quando: HTTP 400,
      HTTP 404 em /api/ ou HTTP 5xx, ou exceção de página. Sem lista de tolerância

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e5.py, num processo próprio, com
      * Groq SUBSTITUÍDO por dublê (GroqChatClient.create_chat_completion): nenhuma chamada real;
      * banco SQLite temporário isolado (o backend/db.sqlite de desenvolvimento não é aberto, D7);
      * variáveis de ambiente de teste fabricadas (nada real, nada gravado em arquivo versionado).
  - Frontend: `npx ng serve` numa porta livre, com proxy /api -> o backend de teste (arquivo de proxy
    temporário, fora do repositório). O proxy fixo de frontend/proxy.conf.json não é usado.
  - Seed só pela API pública do backend de teste: cadastro dos alunos (POST /api/auth/register) e a troca
    semeada do chat (POST /api/student/chat). A conta de funcionário nasce do ADMIN_EMAIL/ADMIN_PASSWORD
    de teste que o servidor lê. O processo do teste não abre banco nenhum.

Pré-requisitos: dependências do backend (fastapi, uvicorn), node_modules do frontend instalados
(cd frontend && npm install) e o Chromium do Playwright: py -3 -m playwright install chromium

Portas: livres e escolhidas pelo próprio teste. Fixe com E2E_BACKEND_PORT / E2E_FRONT_PORT se precisar.
Tempo de espera da compilação do Angular: E2E_NG_TIMEOUT (segundos, padrão 300).
Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_e5_chat_aluno_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD, PREFIXO_RESPOSTA  # noqa: E402

REPO = E2E_DIR.parents[1]
FRONTEND = REPO / "frontend"
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_chat_aluno"))

IS_WINDOWS = os.name == "nt"
SENHA = "senha-aluno-e5-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
TITULO = "Assistente virtual"
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
CAMINHO_CHAT = "/api/student/chat"
CAMINHO_HISTORICO = "/api/student/chat/history"


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


def _iniciar(comando, log, cwd, env=None, shell=False):
    argumentos = {"cwd": str(cwd), "stdout": log, "stderr": subprocess.STDOUT, "shell": shell, "env": env}
    if IS_WINDOWS:
        argumentos["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        argumentos["start_new_session"] = True
    return subprocess.Popen(comando, **argumentos)


def _encerrar(processo):
    """Derruba o processo e toda a árvore de filhos (o ng serve cria vários)."""
    if processo is None or processo.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(os.getpgid(processo.pid), signal.SIGTERM)
        processo.wait(timeout=30)
    except Exception:
        try:
            processo.kill()
        except Exception:
            pass


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
        time.sleep(1)
    raise RuntimeError(f"{rotulo} não respondeu em {limite_s}s em {url}:\n{_final_do_log(log_path)}")


def _final_do_log(caminho, linhas=25):
    try:
        return "\n".join(Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines()[-linhas:])
    except OSError:
        return "(sem log)"


@pytest.fixture(scope="module")
def servidores():
    """Sobe backend (dublê do Groq, banco temporário) e Angular; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_e5_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_FRONT_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://localhost:{porta_web}"
    log_api = tmp / "backend.log"
    log_web = tmp / "ng_serve.log"
    proxy = tmp / "proxy.e2e.json"
    proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}), encoding="utf-8")

    processos = []
    arquivos = []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_e5.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--log-llm", str(tmp / "llm.jsonl")],
            arq_api, REPO / "backend",
        )
        processos.append(backend)
        _esperar_http(api + "/health", 90, backend, "backend de teste", log_api)

        arq_web = open(log_web, "wb")
        arquivos.append(arq_web)
        env_web = dict(os.environ, NG_CLI_ANALYTICS="false", NO_COLOR="1")
        comando_ng = f'npx ng serve --port {porta_web} --proxy-config "{proxy}"'
        front = _iniciar(comando_ng, arq_web, FRONTEND, env=env_web, shell=True)
        processos.append(front)
        _esperar_http(base + "/", int(os.environ.get("E2E_NG_TIMEOUT", "300")), front, "ng serve", log_web)

        yield {"base": base, "api": api, "tmp": tmp, "llm_log": tmp / "llm.jsonl"}
    finally:
        for processo in reversed(processos):
            _encerrar(processo)
        for arquivo in arquivos:
            try:
                arquivo.close()
            except Exception:
                pass
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
# Auxiliares de API (seed e verificações no servidor, sem tocar em banco)
# ---------------------------------------------------------------------------------------------

def _api(api, metodo, caminho, corpo=None, token=None, formulario=None):
    """Chamada HTTP direta à API de teste. Devolve (status, corpo_json_ou_None)."""
    cabecalhos = {}
    if formulario is not None:
        dados = urllib.parse.urlencode(formulario).encode()
        cabecalhos["Content-Type"] = "application/x-www-form-urlencoded"
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        cabecalhos["Content-Type"] = "application/json"
    else:
        dados = None
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


def semear_aluno(api, tag):
    """Cadastra o aluno pela API pública. Devolve (email, token)."""
    email = f"e2e.e5.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    status, _ = _api(api, "POST", "/api/auth/register", {"name": f"Aluno E5 {tag}", "email": email, "password": SENHA})
    if status != 200:
        raise RuntimeError(f"seed: cadastro de {tag} respondeu HTTP {status}")
    return email, token_do_aluno(api, email)


def token_do_aluno(api, email):
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": email, "password": SENHA})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise RuntimeError(f"seed: login por API de {email} respondeu HTTP {status}")
    return corpo["access_token"]


def historico_da_api(api, token):
    status, corpo = _api(api, "GET", CAMINHO_HISTORICO, token=token)
    if status != 200:
        raise RuntimeError(f"GET {CAMINHO_HISTORICO} respondeu HTTP {status} (backend da E5 deveria estar pronto)")
    return corpo["messages"]


def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/")


# ---------------------------------------------------------------------------------------------
# Auxiliares de tela
# ---------------------------------------------------------------------------------------------

def login_na_tela(page, base, email, senha, rotulo):
    try:
        page.goto(base + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campos de login não encontrados na tela /")


def entrar_no_student(page, base, email, rotulo):
    login_na_tela(page, base, email, SENHA, rotulo)
    try:
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /student)")
    page.wait_for_load_state("networkidle")


def mensagens_na_tela(page):
    return page.eval_on_selector_all(
        SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))"
    )


def esperar_mensagens(page, quantidade, rotulo, limite_s=10):
    """Espera exatamente `quantidade` chat-message na tela. Devolve a lista [{role, text}]."""
    fim = time.time() + limite_s
    atual = []
    while time.time() < fim:
        atual = mensagens_na_tela(page)
        if len(atual) == quantidade:
            return atual
        page.wait_for_timeout(150)
    raise Falha(f"{rotulo}: esperava {quantidade} chat-message na tela, há {len(atual)} "
                f"(papéis={[m['role'] for m in atual]})")


def exigir_painel(page, rotulo):
    try:
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: [data-testid=chat-panel] não está visível em {page.url}; a seção de chat não existe na tela")


def papeis(lista):
    return [m["role"] for m in lista]


def test_e5_chat_aluno_angular_e2e(servidores, browser):
    base = servidores["base"]
    api = servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    estado = {"page": None}
    rede = {"posts_chat": [], "historico_ok": 0}
    memoria = {}

    # --- seed pela API pública do backend de teste -------------------------------------
    seed = {"ok": False, "erro": ""}
    try:
        email_a, token_a = semear_aluno(api, "a")
        email_b, token_b = semear_aluno(api, "b")
        texto_semente = f"Pergunta semeada A {uuid.uuid4().hex[:8]}"
        status, _ = _api(api, "POST", CAMINHO_CHAT, {"message": texto_semente}, token=token_a)
        if status != 200:
            raise RuntimeError(f"seed: POST {CAMINHO_CHAT} do aluno A respondeu HTTP {status}")
        seed["ok"] = True
    except Exception as erro:  # seed falhando deixa o cenário vermelho, com a causa
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(rotulo):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()
        estado["page"] = page

        def ao_request(requisicao):
            if requisicao.method == "POST" and caminho_da_url(requisicao.url) == CAMINHO_CHAT:
                rede["posts_chat"].append({
                    "rotulo": rotulo, "url": requisicao.url, "corpo": requisicao.post_data,
                })

        def ao_response(resposta):
            if resposta.request.method == "GET" and caminho_da_url(resposta.url) == CAMINHO_HISTORICO \
                    and resposta.status == 200:
                rede["historico_ok"] += 1

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is None:
                return
            codigo = int(m.group(1))
            url = msg.location.get("url") or ""
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_console.append(f"{rotulo}: {msg.text} [{url}]")

        page.on("request", ao_request)
        page.on("response", ao_response)
        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: exceção de página: {e}"))
        return page

    def captura_de_falha(codigo):
        page = estado["page"]
        if page is None:
            return
        try:
            page.screenshot(path=str(OUT / f"{codigo}_falha.png"), full_page=True)
        except Exception:
            pass

    def cenario(codigo, nome, fn):
        if not seed["ok"]:
            resultados.append((codigo, nome, False, f"seed falhou: {seed['erro']}"))
            print(f"[FAIL] {codigo} {nome} -> seed falhou: {seed['erro']}")
            return
        try:
            fn()
            resultados.append((codigo, nome, True, ""))
            print(f"[OK]   {codigo} {nome}")
        except Falha as erro:
            captura_de_falha(codigo)
            resultados.append((codigo, nome, False, str(erro)))
            print(f"[FAIL] {codigo} {nome} -> {erro}")
        except Exception as erro:
            captura_de_falha(codigo)
            linha = str(erro).splitlines()[0] if str(erro) else ""
            detalhe = f"{type(erro).__name__}: {linha}"
            resultados.append((codigo, nome, False, detalhe))
            print(f"[FAIL] {codigo} {nome} -> {detalhe}")

    def pagina_a():
        page = memoria.get("page_a")
        if page is None or caminho_da_url(page.url) != "/student":
            raise Falha("pré-requisito: o aluno A não está em /student (S1 não deixou a tela pronta)")
        return page

    # --- S1 ---------------------------------------------------------------------------
    def s1():
        page = nova_pagina("S1")
        memoria["page_a"] = page
        entrar_no_student(page, base, email_a, "S1 login do aluno A")
        if "Meus cursos" not in page.inner_text("body"):
            raise Falha("S1: /student carregou sem o 'Meus cursos' (tela da E3 deveria estar intacta)")

    cenario("S1", "pré-condição: login do aluno chega a /student e a tela carrega (sem depender do chat)", s1)

    # --- C1 ---------------------------------------------------------------------------
    def c1():
        page = pagina_a()
        exigir_painel(page, "C1 seção de chat")
        painel = page.locator(SEL_PAINEL).first
        titulo = page.get_by_text(TITULO, exact=True)
        if titulo.count() == 0 or not any(titulo.nth(i).is_visible() for i in range(titulo.count())):
            raise Falha(f"C1: o título visível '{TITULO}' não aparece na tela")
        for seletor, nome in ((SEL_CAMPO, "chat-input"), (SEL_ENVIAR, "chat-send")):
            alvo = painel.locator(seletor)
            if alvo.count() == 0 or not alvo.first.is_visible():
                raise Falha(f"C1: [data-testid={nome}] não está visível dentro do chat-panel")

    cenario("C1", "/student tem a seção 'Assistente virtual' com painel, campo e botão de envio", c1)

    # --- C2 ---------------------------------------------------------------------------
    def c2():
        page = pagina_a()
        exigir_painel(page, "C2 histórico")
        lista = esperar_mensagens(page, 2, "C2 histórico semeado")
        if papeis(lista) != ["user", "assistant"]:
            raise Falha(f"C2: papéis do histórico {papeis(lista)} (esperado ['user', 'assistant'], nessa ordem)")
        if texto_semente not in lista[0]["text"]:
            raise Falha("C2: a primeira mensagem não é a pergunta semeada do aluno")
        if (PREFIXO_RESPOSTA + texto_semente) not in lista[1]["text"]:
            raise Falha("C2: a segunda mensagem não é a resposta do bot persistida")
        if rede["historico_ok"] < 1:
            raise Falha(f"C2: a tela não buscou GET {CAMINHO_HISTORICO} (com 200) ao abrir /student")

    cenario("C2", "ao abrir /student o histórico persistido é carregado e exibido, em ordem", c2)

    # --- C3 ---------------------------------------------------------------------------
    def c3():
        page = pagina_a()
        exigir_painel(page, "C3 envio")
        memoria["texto_enviado"] = f"Quero saber mais sobre os cursos {uuid.uuid4().hex[:8]}"
        page.locator(SEL_CAMPO).first.fill(memoria["texto_enviado"], timeout=TIMEOUT)
        page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        lista = esperar_mensagens(page, 4, "C3 envio")
        if papeis(lista) != ["user", "assistant", "user", "assistant"]:
            raise Falha(f"C3: papéis após o envio {papeis(lista)} (esperado user/assistant/user/assistant)")
        if memoria["texto_enviado"] not in lista[2]["text"]:
            raise Falha("C3: a mensagem do aluno enviada não aparece como terceira chat-message")
        if (PREFIXO_RESPOSTA + memoria["texto_enviado"]) not in lista[3]["text"]:
            raise Falha("C3: a resposta do bot não aparece como quarta chat-message")
        valor = page.locator(SEL_CAMPO).first.input_value()
        if valor != "":
            raise Falha(f"C3: o campo não foi limpo depois do envio (valor={valor!r})")
        memoria["lista_apos_envio"] = lista

    cenario("C3", "enviar mensagem: aparecem a do aluno e a resposta do bot; o campo é limpo", c3)

    # --- C4 ---------------------------------------------------------------------------
    def c4():
        page = pagina_a()
        exigir_painel(page, "C4 vazio")
        posts_antes = len(rede["posts_chat"])
        na_tela_antes = len(mensagens_na_tela(page))
        no_servidor_antes = len(historico_da_api(api, token_a))
        campo = page.locator(SEL_CAMPO).first
        botao = page.locator(SEL_ENVIAR).first
        for valor in ("", "   ", " \t "):
            campo.fill(valor, timeout=TIMEOUT)
            try:
                botao.click(force=True, timeout=TIMEOUT)  # botão desabilitado também vale: não envia
            except sync_api.TimeoutError:
                pass
            page.wait_for_timeout(500)
            if len(rede["posts_chat"]) != posts_antes:
                raise Falha(f"C4: o chat enviou uma requisição com a mensagem {valor!r} (vazia ou só espaços)")
        if len(mensagens_na_tela(page)) != na_tela_antes:
            raise Falha("C4: apareceu chat-message nova depois de enviar mensagem vazia ou só espaços")
        if len(historico_da_api(api, token_a)) != no_servidor_antes:
            raise Falha("C4: o servidor gravou mensagem vazia ou só espaços")
        campo.fill("", timeout=TIMEOUT)

    cenario("C4", "mensagem vazia ou só espaços não é enviada (sem POST, sem mensagem, nada gravado)", c4)

    # --- C5 ---------------------------------------------------------------------------
    def c5():
        enviados = [p for p in rede["posts_chat"] if p["rotulo"] == "S1"]
        if not enviados:
            raise Falha(f"C5: nenhuma requisição POST {CAMINHO_CHAT} foi observada (C3 não enviou)")
        for envio in enviados:
            try:
                corpo = json.loads(envio["corpo"] or "null")
            except ValueError:
                raise Falha(f"C5: o corpo do POST não é JSON: {envio['corpo']!r}")
            if not isinstance(corpo, dict) or set(corpo.keys()) != {"message"}:
                raise Falha(f"C5: o corpo do POST deve ter só 'message'; chaves enviadas: "
                            f"{sorted(corpo.keys()) if isinstance(corpo, dict) else corpo!r}")
            if corpo["message"] != memoria.get("texto_enviado"):
                raise Falha("C5: o campo 'message' não é o texto digitado pelo aluno")
            consulta = urllib.parse.urlparse(envio["url"]).query
            if "user_id" in consulta or "session_id" in consulta:
                raise Falha(f"C5: identificador de usuário/sessão na URL do POST ({envio['url']})")

    cenario("C5", "o POST do chat leva só {'message'} no corpo (sem user_id/session_id)", c5)

    # --- C6 ---------------------------------------------------------------------------
    def c6():
        page = pagina_a()
        esperado = memoria.get("lista_apos_envio")
        if not esperado:
            raise Falha("C6 pré-requisito: C3 não deixou as mensagens para comparar")
        page.reload(wait_until="networkidle")
        exigir_painel(page, "C6 recarregar")
        lista = esperar_mensagens(page, len(esperado), "C6 depois de recarregar")
        if lista != esperado:
            raise Falha(f"C6: as mensagens mudaram depois de recarregar (antes={esperado}, depois={lista})")

    cenario("C6", "persistência: depois de recarregar a página as mesmas mensagens continuam", c6)

    # --- C7 ---------------------------------------------------------------------------
    def c7():
        esperado = memoria.get("lista_apos_envio")
        if not esperado:
            raise Falha("C7 pré-requisito: C3 não deixou as mensagens para comparar")
        page = nova_pagina("C7")
        entrar_no_student(page, base, email_a, "C7 novo login do aluno A")
        exigir_painel(page, "C7 novo login")
        lista = esperar_mensagens(page, len(esperado), "C7 depois do novo login")
        if lista != esperado:
            raise Falha(f"C7: as mensagens mudaram depois de um novo login (antes={esperado}, depois={lista})")

    cenario("C7", "persistência: depois de um novo login as mesmas mensagens continuam", c7)

    # --- C8 ---------------------------------------------------------------------------
    def c8():
        textos_de_a = [texto_semente, memoria.get("texto_enviado") or texto_semente]
        page_b = nova_pagina("C8")
        entrar_no_student(page_b, base, email_b, "C8 login do aluno B")
        exigir_painel(page_b, "C8 aluno B")
        esperar_mensagens(page_b, 0, "C8 aluno B sem conversa")
        corpo_b = page_b.inner_text("body")
        for texto in textos_de_a:
            if texto in corpo_b:
                raise Falha("C8: o aluno B vê, na tela, texto da conversa do aluno A")
        # B conversa; A não pode ver, e B vê só a própria troca
        texto_b = f"Mensagem exclusiva do aluno B {uuid.uuid4().hex[:8]}"
        page_b.locator(SEL_CAMPO).first.fill(texto_b, timeout=TIMEOUT)
        page_b.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        lista_b = esperar_mensagens(page_b, 2, "C8 aluno B depois de enviar")
        if papeis(lista_b) != ["user", "assistant"] or texto_b not in lista_b[0]["text"]:
            raise Falha(f"C8: conversa do aluno B inesperada: {lista_b}")
        page_a = pagina_a()
        page_a.reload(wait_until="networkidle")
        exigir_painel(page_a, "C8 aluno A depois de B conversar")
        lista_a = esperar_mensagens(page_a, len(memoria["lista_apos_envio"]), "C8 aluno A")
        if texto_b in page_a.inner_text("body"):
            raise Falha("C8: o aluno A vê, na tela, texto da conversa do aluno B")
        if lista_a != memoria["lista_apos_envio"]:
            raise Falha("C8: a conversa do aluno A mudou depois de o aluno B conversar")

    cenario("C8", "isolamento: o segundo aluno não vê as mensagens do primeiro (e vice-versa)", c8)

    # --- C9 ---------------------------------------------------------------------------
    def c9():
        page = nova_pagina("C9")
        login_na_tela(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "C9 login do funcionário")
        try:
            page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"C9 login do funcionário: URL final {page.url} (esperado /admin)")
        page.wait_for_load_state("networkidle")
        if page.locator(SEL_PAINEL).count() != 0 or page.locator(SEL_MENSAGEM).count() != 0:
            raise Falha("C9: o funcionário vê o chat-panel/mensagens de aluno em /admin")
        if TITULO in page.inner_text("body"):
            raise Falha(f"C9: o funcionário vê o título '{TITULO}' em /admin")
        page.goto(base + "/student", wait_until="networkidle")
        if caminho_da_url(page.url) == "/student":
            raise Falha("C9: o funcionário conseguiu abrir /student")
        if page.locator(SEL_PAINEL).count() != 0 or TITULO in page.inner_text("body"):
            raise Falha("C9: a seção de chat de aluno apareceu para o funcionário depois de tentar /student")

    cenario("C9", "funcionário (admin) não vê o chat do aluno e não abre /student", c9)

    # --- C10 --------------------------------------------------------------------------
    def c10():
        if erros_console:
            raise Falha(f"C10 console: {len(erros_console)} erro(s): " + " | ".join(erros_console[:5]))

    cenario("C10", "sem erros de console (400, 404 em /api, 5xx) nem exceções nas telas acima", c10)

    # --- limpeza dos contextos ---------------------------------------------------------
    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
