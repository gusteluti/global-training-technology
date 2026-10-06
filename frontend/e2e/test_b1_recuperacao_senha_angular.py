"""E2E das telas de recuperação de senha do aluno (B1, D60/D61; Chromium via Playwright).

O backend (POST /api/auth/password-reset/request e POST /api/auth/password-reset) já está pronto (commit b7b1390).
Este arquivo é o teste VERMELHO do frontend: o link "Esqueci minha senha" no login, a tela /esqueci-senha e a tela
/redefinir-senha?token=. As duas rotas são públicas (sem guard), inclusive com outra sessão aberta no navegador.

Contrato de tela (D60), data-testid:
  login:             esqueci-link ("Esqueci minha senha"; leva a /esqueci-senha)
  /esqueci-senha:    esqueci-email, esqueci-enviar, esqueci-mensagem
                     (SEMPRE "Se o e-mail estiver cadastrado, enviaremos um link para redefinir a senha.")
  /redefinir-senha:  redefinir-senha, redefinir-confirmar (devem coincidir; senão "As senhas não coincidem." e
                     nada é enviado), redefinir-enviar, redefinir-mensagem (sucesso exato "Senha redefinida. Faça
                     login para entrar." com link para o login), redefinir-erro (texto do `detail` da API).
                     Sem `token` na URL: "Link inválido ou incompleto. Use o link enviado para você." e o envio
                     fica bloqueado.
  Interceptor (D56): as chamadas /api/auth/password-reset* nunca levam Authorization.

Escolhas de forma do teste (nenhuma define política):
  - os campos esqueci-email, redefinir-senha e redefinir-confirmar são <input> (o teste usa fill);
  - "As senhas não coincidem." e "Link inválido ou incompleto..." podem estar em redefinir-erro ou em outro
    elemento visível da tela: o teste exige o texto exato visível na tela e que nada tenha sido enviado /
    que redefinir-mensagem (sucesso) não apareça;
  - "link para o login" = um <a> visível com href "/" ou "/login" (na tela inteira de sucesso).

Cenários (checks numerados):
  S1 pré-condição (anterior às telas novas): login de aluno com senha chega a /student pela tela; o seed
     (aluno sem senha, aluno com senha, funcionário admin@gt.com) existe no banco temporário; o outbox de
     desenvolvimento é lido do arquivo temporário (um cadastro por API gera o registro "Conta criada").
     Garante que o red é por falta das telas, não por servidor, login, seed ou leitura do outbox
  B1 na tela de login, esqueci-link leva a /esqueci-senha
  B2 aluno com senha pede o link pela tela: mensagem uniforme exata; o outbox ganha exatamente um registro
     "Redefinição de senha" com o link {base}/redefinir-senha?token=...; e-mail inexistente e e-mail de
     funcionário mostram a MESMA mensagem e o outbox não ganha registro
  B3 abrir o link do outbox: senhas diferentes mostram "As senhas não coincidem." e não enviam nada; senha curta
     mostra o `detail` da API em redefinir-erro; senha válida mostra a mensagem exata de sucesso com link para o
     login; senha antiga falha e a nova entra em /student; "Sua senha foi alterada" no outbox (sem senha, sem token)
  B4 reusar o mesmo link mostra o erro genérico exato do backend e não troca a senha
  B5 sem token (e com token vazio): mensagem exata e envio bloqueado (nenhuma requisição password-reset)
  B6 aluno sem senha (link de compra expirado): pede o link, recebe o de definição (/definir-senha?token=),
     define a senha pela tela já existente e entra em /student
  B7 limite: 4 pedidos seguidos pela tela, só 3 registros no outbox e a mesma mensagem nos 4
  B8 com token de sessão antigo no navegador (localStorage gtt_token): as rotas ficam públicas (sem redirecionar) e
     /api/auth/password-reset/request e /api/auth/password-reset saem SEM Authorization
  B9 sem erros de console (400, 404 em /api, 5xx) nem exceções de página; os ÚNICOS 400 permitidos são os provocados
     de propósito: POST /api/auth/password-reset na tela /redefinir-senha (senha curta, B3; reuso, B4)

Harness isolado (D58, H1): o teste sobe e derruba os próprios servidores; nada precisa estar de pé antes.
  - Backend: frontend/e2e/servidor_e2e_h1.py em processo próprio, porta livre, SQLite temporário, diretório de cursos
    temporário, `PASSWORD_LINK_OUTBOX` = <tmp>/outbox.jsonl (arquivo temporário de `ambiente_isolado`, uma linha JSON por
    mensagem: email, assunto?, mensagem?, link?, criado_em) e FRONTEND_BASE_URL = origem do ng serve do teste (por isso
    o link do outbox abre direto na tela do teste). O teste lê esse arquivo como o aluno leria o e-mail.
  - Frontend: `npx ng serve` em porta livre, com proxy temporário /api -> backend de teste.
  - Seed de contas pela camada Database no MESMO SQLite temporário (apoio_harness_h1.abrir_banco), contas com e-mail
    único por cenário (o limite de 3 pedidos por hora é por conta).
  - backend/db.sqlite e backend/courses de desenvolvimento não são abertos nem alterados. Nenhum servidor de fora
    (E2E_BASE_URL / E2E_API_URL) é usado.

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas fixas opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT;
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_b1_recuperacao_senha_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
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

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL  # noqa: E402

# Preenchido pela fixture `servidores` (URLs, banco e outbox do ambiente isolado deste módulo).
ALVO = {"base": "", "api": "", "db_path": None, "outbox": None}
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_b1_recuperacao"))

MSG_PEDIDO = "Se o e-mail estiver cadastrado, enviaremos um link para redefinir a senha."
MSG_SUCESSO = "Senha redefinida. Faça login para entrar."
MSG_NAO_COINCIDEM = "As senhas não coincidem."
MSG_SEM_TOKEN = "Link inválido ou incompleto. Use o link enviado para você."
ERRO_DEFINICAO_SENHA = "Não foi possível definir a senha. Verifique o link e a senha informada."
ASSUNTO_REDEFINICAO = "Redefinição de senha"
ASSUNTO_ALTERADA = "Sua senha foi alterada"

SENHA_ANTIGA = "senha-antiga-2026"
SENHA_NOVA = "senha-nova-forte-2026"
SENHA_OUTRA = "outra-senha-forte-2027"
SENHA_CURTA = "curta1"  # 6 caracteres (mínimo 8)
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
URL_PEDIDO = "/api/auth/password-reset/request"
URL_REDEFINIR = "/api/auth/password-reset"

# Únicos erros HTTP tolerados: (método, caminho da API, tela, status). Lista exata; só os provocados de propósito.
ERROS_ESPERADOS = {
    ("POST", URL_REDEFINIR, "/redefinir-senha", 400),
}


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


# --- seed e leitura do banco / outbox ------------------------------------------------------------------------

def _database():
    """Camada de banco apontada para o arquivo temporário do backend de teste (nunca backend/db.sqlite)."""
    return abrir_banco(ALVO["db_path"])


def novo_email(tag):
    return f"b1.{tag}.{uuid.uuid4().hex[:10]}@teste.com"


def semear_aluno_com_senha(tag, senha=SENHA_ANTIGA):
    Database = _database()  # antes do import: põe backend/ no sys.path
    from core.security import get_password_hash

    email = novo_email(tag)
    Database.add_user(email, "Aluno B1 Senha", get_password_hash(senha), role="student")
    return email


def semear_aluno_sem_senha(tag):
    Database = _database()
    email = novo_email(tag)
    Database.get_or_create_user(email, "Aluno B1 Sem Senha")
    return email


def conta_no_banco(email):
    return _database().get_user_by_email(email)


def ler_outbox(email=None):
    """Registros do outbox de desenvolvimento (arquivo temporário), como o aluno leria no e-mail."""
    caminho = Path(ALVO["outbox"])
    if not caminho.exists():
        return []
    registros = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            registros.append(json.loads(linha))
    if email is not None:
        registros = [r for r in registros if r.get("email") == email]
    return registros


def registros_de(email, assunto=None):
    registros = ler_outbox(email)
    if assunto is not None:
        registros = [r for r in registros if r.get("assunto") == assunto]
    return registros


def aguardar_registros(email, quantidade, assunto=None, limite_s=5):
    """Espera o outbox ter pelo menos `quantidade` registros do e-mail; devolve os que houver."""
    fim = time.time() + limite_s
    while True:
        registros = registros_de(email, assunto)
        if len(registros) >= quantidade or time.time() > fim:
            return registros
        time.sleep(0.2)


def confirmar_sem_registro_novo(email, antes, assunto=None, espera_s=1.5):
    """Dá tempo ao backend e confirma que o outbox NÃO ganhou registro além dos `antes`."""
    time.sleep(espera_s)
    depois = registros_de(email, assunto)
    return len(depois) == antes


def login_api(email, senha):
    """POST /api/token direto. Devolve (status_http, corpo_json_ou_None)."""
    dados = urllib.parse.urlencode({"username": email, "password": senha}).encode()
    req = urllib.request.Request(
        ALVO["api"] + "/api/token", data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


def cadastrar_por_api(email, senha):
    corpo = json.dumps({"name": "Aluno B1 Cadastro", "email": email, "password": senha}).encode()
    req = urllib.request.Request(
        ALVO["api"] + "/api/auth/register", data=corpo, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resposta:
        return resposta.status


# --- ajudantes de tela ---------------------------------------------------------------------------------------

def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/")


def caminho_da_tela(url):
    return caminho_da_url(url) or "/"


def exigir_rota(page, caminho_com_query, rotulo):
    """Abre a rota e exige que a URL final continue nela (o curinga '**' redireciona para '/')."""
    page.goto(ALVO["base"] + caminho_com_query, wait_until="networkidle")
    esperado = urllib.parse.urlparse(caminho_com_query).path.rstrip("/")
    if caminho_da_url(page.url) != esperado:
        raise Falha(f"{rotulo}: rota {esperado} não existe (URL final {page.url}; o curinga redirecionou)")


def por_id(page, testid, rotulo):
    """Localizador por data-testid; falha com mensagem clara se não aparecer visível."""
    loc = page.get_by_test_id(testid).first
    try:
        loc.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: elemento data-testid={testid} não ficou visível na tela ({page.url})")
    return loc


def preencher_id(page, testid, valor, rotulo):
    por_id(page, testid, rotulo).fill(valor, timeout=TIMEOUT)


def clicar_id(page, testid, rotulo):
    try:
        por_id(page, testid, rotulo).click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: data-testid={testid} não pôde ser clicado (ausente ou desabilitado)")


def texto_id(page, testid, rotulo):
    return por_id(page, testid, rotulo).inner_text().strip()


def id_visivel(page, testid):
    loc = page.get_by_test_id(testid)
    return loc.count() > 0 and any(loc.nth(i).is_visible() for i in range(loc.count()))


def esperar_texto_na_tela(page, texto, rotulo):
    try:
        page.get_by_text(texto, exact=False).first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: o texto exato {texto!r} não apareceu na tela; corpo: {page.inner_text('body')[:200]!r}")


def enviar_e_esperar(page, testid_botao, sufixo_url, rotulo):
    """Clica no botão e espera a resposta do POST a `sufixo_url` (como no L2). Devolve (status, corpo_json)."""
    def e_a_chamada(resposta):
        return resposta.request.method == "POST" and caminho_da_url(resposta.url) == sufixo_url

    botao = por_id(page, testid_botao, rotulo)
    try:
        with page.expect_response(e_a_chamada, timeout=TIMEOUT * 2) as info:
            botao.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: clicar em {testid_botao} não gerou POST {sufixo_url} (nada foi enviado)")
    resposta = info.value
    try:
        corpo = resposta.json()
    except Exception:
        corpo = None
    return resposta.status, corpo


def pedir_link_pela_tela(page, email, rotulo):
    """Preenche /esqueci-senha (já aberta) e envia. Devolve (status, texto de esqueci-mensagem)."""
    preencher_id(page, "esqueci-email", email, rotulo)
    status, _ = enviar_e_esperar(page, "esqueci-enviar", URL_PEDIDO, rotulo)
    por_id(page, "esqueci-mensagem", rotulo)
    return status, texto_id(page, "esqueci-mensagem", rotulo)


def link_do_registro(registro, rotulo):
    link = registro.get("link") or ""
    if not link:
        raise Falha(f"{rotulo}: o registro do outbox não tem link: {registro}")
    return link


def abrir_link_do_email(page, link, rotulo):
    """Abre o link do e-mail do aluno: ele precisa apontar para a origem do ng serve do teste."""
    if not link.startswith(ALVO["base"] + "/"):
        raise Falha(f"{rotulo}: o link do e-mail {link!r} não aponta para o frontend do teste ({ALVO['base']})")
    page.goto(link, wait_until="networkidle")
    return urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("token", [""])[0]


def login_na_tela(page, email, senha, rotulo):
    exigir_rota(page, "/", rotulo)
    page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
    page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
    page.locator("button[type=submit]").first.click(timeout=TIMEOUT)


def esperar_student(page, rotulo):
    try:
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /student)")


def link_para_login_visivel(page):
    for href in ("/", "/login"):
        loc = page.locator(f'a[href="{href}"]')
        if loc.count() > 0 and any(loc.nth(i).is_visible() for i in range(loc.count())):
            return True
    return False


def alerta_de_erro_visivel(page):
    loc = page.locator(".alert-danger")
    return loc.count() > 0 and any(loc.nth(i).is_visible() for i in range(loc.count()))


def pedir_link_por_api(email):
    corpo = json.dumps({"email": email}).encode()
    req = urllib.request.Request(
        ALVO["api"] + URL_PEDIDO, data=corpo, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code


def requisicoes_password_reset(lista):
    return [r for r in lista if "/api/auth/password-reset" in r["caminho"]]


@pytest.fixture(scope="module")
def servidores():
    """Backend de teste (banco, cursos e outbox temporários) e Angular; derruba tudo ao final."""
    with ambiente_isolado("b1") as ambiente:
        ALVO.update(
            base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"],
            outbox=Path(ambiente["tmp"]) / "outbox.jsonl",
        )
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_b1_recuperacao_senha_angular_e2e(servidores, browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    respostas_erro = []   # todas as respostas HTTP >= 400 de todas as páginas
    consoles_http = []    # (rótulo, status, caminho do recurso, texto) dos erros de console "status of NNN"
    contextos = []
    atual = {"rotulo": "", "page": None}

    def nova_pagina(rotulo, token_antigo=None):
        atual["rotulo"] = rotulo
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        if token_antigo is not None:
            ctx.add_init_script(
                f"try {{ localStorage.setItem('gtt_token', {json.dumps(token_antigo)}); }} catch (e) {{}}"
            )
        page = ctx.new_page()
        atual["page"] = page
        page.requisicoes = []  # requisições à API desta página, com os cabeçalhos efetivamente enviados

        def ao_requisicao(req):
            if "/api/" in req.url:
                try:
                    cabecalhos = {k.lower(): v for k, v in req.all_headers().items()}
                except Exception:
                    cabecalhos = {k.lower(): v for k, v in req.headers.items()}
                page.requisicoes.append({
                    "metodo": req.method, "caminho": caminho_da_url(req.url), "cabecalhos": cabecalhos,
                })

        def ao_resposta(resposta):
            if resposta.status >= 400:
                respostas_erro.append({
                    "rotulo": rotulo, "status": resposta.status, "metodo": resposta.request.method,
                    "caminho": caminho_da_url(resposta.url), "tela": caminho_da_tela(page.url),
                })

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is not None:
                consoles_http.append((rotulo, int(m.group(1)), caminho_da_url(msg.location.get("url") or ""), msg.text))
                return
            erros_console.append(f"{rotulo}: {msg.text}")

        page.on("request", ao_requisicao)
        page.on("response", ao_resposta)
        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: {e}"))
        return page

    def captura_de_falha(codigo):
        page = atual["page"]
        if page is None:
            return
        try:
            page.screenshot(path=str(OUT / f"{codigo}_falha.png"), full_page=True)
        except Exception:
            pass

    def cenario(codigo, nome, fn):
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
        finally:
            atual["page"] = None

    # --- S1 pré-condição --------------------------------------------------------------------------------------
    def s1():
        aluno = semear_aluno_com_senha("pre", SENHA_ANTIGA)
        if conta_no_banco(aluno) is None or conta_no_banco(GESTAO_EMAIL) is None:
            raise Falha("S1: seed ausente (aluno de teste ou admin@gt.com não existe no banco temporário)")
        if conta_no_banco(semear_aluno_sem_senha("pre-sem")).get("password_hash"):
            raise Falha("S1: aluno sem senha foi semeado com senha")
        page = nova_pagina("S1")
        login_na_tela(page, aluno, SENHA_ANTIGA, "S1 login")
        esperar_student(page, "S1 login")
        # leitura do outbox: um cadastro por API gera o registro "Conta criada" do e-mail novo
        email = novo_email("pre-outbox")
        cadastrar_por_api(email, SENHA_ANTIGA)
        registros = aguardar_registros(email, 1)
        if len(registros) != 1 or "Conta criada" not in (registros[0].get("assunto") or ""):
            raise Falha(f"S1: o outbox temporário não foi lido como esperado: {registros}")

    cenario("S1", "pré-condição: login de aluno, seed e leitura do outbox temporário funcionam", s1)

    # --- B1 ---------------------------------------------------------------------------------------------------
    def b1():
        page = nova_pagina("B1")
        exigir_rota(page, "/", "B1 login")
        link = por_id(page, "esqueci-link", "B1 login")
        if "esqueci minha senha" not in link.inner_text().lower():
            raise Falha(f"B1: texto do link é {link.inner_text()!r}, esperado 'Esqueci minha senha'")
        link.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/esqueci-senha", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"B1: esqueci-link levou a {page.url} (esperado /esqueci-senha)")
        for testid in ("esqueci-email", "esqueci-enviar"):
            por_id(page, testid, "B1 tela /esqueci-senha")

    cenario("B1", "esqueci-link na tela de login leva a /esqueci-senha", b1)

    # --- B2 ---------------------------------------------------------------------------------------------------
    def b2():
        aluno = semear_aluno_com_senha("pedido", SENHA_ANTIGA)
        inexistente = novo_email("inexistente")
        page = nova_pagina("B2")
        exigir_rota(page, "/esqueci-senha", "B2 pedido")

        status, mensagem = pedir_link_pela_tela(page, aluno, "B2 aluno com senha")
        if status != 200 or mensagem != MSG_PEDIDO:
            raise Falha(f"B2 aluno: HTTP {status}, mensagem {mensagem!r} (esperado 200 e {MSG_PEDIDO!r})")
        registros = aguardar_registros(aluno, 1, ASSUNTO_REDEFINICAO)
        if len(registros) != 1:
            raise Falha(f"B2 aluno: o outbox tem {len(registros)} registro(s) 'Redefinição de senha' (esperado 1)")
        if len(registros_de(aluno)) != 1:
            raise Falha(f"B2 aluno: o outbox tem registros extras para a conta: {registros_de(aluno)}")
        link = link_do_registro(registros[0], "B2 aluno")
        if not link.startswith(f"{ALVO['base']}/redefinir-senha?token="):
            raise Falha(f"B2 aluno: link {link!r} não é {ALVO['base']}/redefinir-senha?token=...")

        for rotulo, email in (("e-mail inexistente", inexistente), ("e-mail de funcionário", GESTAO_EMAIL)):
            antes = len(registros_de(email))
            exigir_rota(page, "/esqueci-senha", f"B2 {rotulo}")
            status, outra = pedir_link_pela_tela(page, email, f"B2 {rotulo}")
            if status != 200 or outra != MSG_PEDIDO:
                raise Falha(f"B2 {rotulo}: HTTP {status}, mensagem {outra!r} (esperado a MESMA {MSG_PEDIDO!r})")
            if not confirmar_sem_registro_novo(email, antes):
                raise Falha(f"B2 {rotulo}: o outbox ganhou registro para {email} (não pode haver e-mail)")
            if alerta_de_erro_visivel(page):
                raise Falha(f"B2 {rotulo}: a tela mostrou erro; deve responder como o aluno existente")

    cenario("B2", "pedido pela tela: mensagem uniforme; 1 registro só para aluno com senha", b2)

    # --- B3 -------------------------------------------------------------------------------------------------
    referencias = {}  # e-mail e link do B3, reaproveitados pelo B4 (mesmo link)

    def b3():
        email = semear_aluno_com_senha("redefinir", SENHA_ANTIGA)
        # o pedido é feito por API só para obter o link; a tela de pedido é coberta em B2
        pedir_link_por_api(email)
        registros = aguardar_registros(email, 1, ASSUNTO_REDEFINICAO)
        if len(registros) != 1:
            raise Falha(f"B3 pré-condição: sem link de redefinição no outbox para {email}")
        link = link_do_registro(registros[0], "B3")
        referencias.update(email=email, link=link)

        page = nova_pagina("B3")
        token = abrir_link_do_email(page, link, "B3")
        if caminho_da_url(page.url) != "/redefinir-senha":
            raise Falha(f"B3: o link do e-mail abriu {page.url} (esperado /redefinir-senha)")
        for testid in ("redefinir-senha", "redefinir-confirmar", "redefinir-enviar"):
            por_id(page, testid, "B3 tela /redefinir-senha")

        # senhas diferentes: texto exato, nada enviado
        preencher_id(page, "redefinir-senha", SENHA_NOVA, "B3 divergentes")
        preencher_id(page, "redefinir-confirmar", SENHA_OUTRA, "B3 divergentes")
        por_id(page, "redefinir-enviar", "B3 divergentes").click(timeout=TIMEOUT)
        esperar_texto_na_tela(page, MSG_NAO_COINCIDEM, "B3 divergentes")
        time.sleep(1)
        if requisicoes_password_reset(page.requisicoes):
            raise Falha(f"B3 divergentes: foi enviada requisição: {requisicoes_password_reset(page.requisicoes)}")
        if id_visivel(page, "redefinir-mensagem"):
            raise Falha("B3 divergentes: o sucesso apareceu com senhas diferentes")

        # senha curta (igual nos dois campos): o detail da API em redefinir-erro
        preencher_id(page, "redefinir-senha", SENHA_CURTA, "B3 senha curta")
        preencher_id(page, "redefinir-confirmar", SENHA_CURTA, "B3 senha curta")
        status, corpo = enviar_e_esperar(page, "redefinir-enviar", URL_REDEFINIR, "B3 senha curta")
        detalhe = (corpo or {}).get("detail")
        if status != 400 or detalhe != ERRO_DEFINICAO_SENHA:
            raise Falha(f"B3 senha curta: API devolveu HTTP {status} detail {detalhe!r} (esperado 400 e o texto genérico)")
        erro = texto_id(page, "redefinir-erro", "B3 senha curta")
        if erro != detalhe:
            raise Falha(f"B3 senha curta: redefinir-erro é {erro!r}, esperado o detail da API {detalhe!r}")
        if id_visivel(page, "redefinir-mensagem"):
            raise Falha("B3 senha curta: o sucesso apareceu com senha curta")
        if login_api(email, SENHA_ANTIGA)[0] != 200:
            raise Falha("B3 senha curta: a senha antiga deixou de valer mesmo sem redefinição")

        # senha válida: sucesso exato com link para o login
        preencher_id(page, "redefinir-senha", SENHA_NOVA, "B3 válida")
        preencher_id(page, "redefinir-confirmar", SENHA_NOVA, "B3 válida")
        status, _ = enviar_e_esperar(page, "redefinir-enviar", URL_REDEFINIR, "B3 válida")
        if status != 200:
            raise Falha(f"B3 válida: API devolveu HTTP {status} (esperado 200)")
        sucesso = texto_id(page, "redefinir-mensagem", "B3 válida")
        if MSG_SUCESSO not in sucesso:
            raise Falha(f"B3 válida: redefinir-mensagem é {sucesso!r}, esperado conter {MSG_SUCESSO!r}")
        if not link_para_login_visivel(page):
            raise Falha("B3 válida: não há link visível para o login (href '/' ou '/login') na tela de sucesso")

        if login_api(email, SENHA_ANTIGA)[0] == 200:
            raise Falha("B3: a senha antiga ainda loga depois da redefinição")
        status_nova, corpo_nova = login_api(email, SENHA_NOVA)
        if status_nova != 200 or not (corpo_nova or {}).get("access_token"):
            raise Falha(f"B3: login com a senha nova falhou (HTTP {status_nova})")
        avisos = aguardar_registros(email, 1, ASSUNTO_ALTERADA)
        if len(avisos) != 1:
            raise Falha(f"B3: o outbox tem {len(avisos)} aviso(s) 'Sua senha foi alterada' (esperado 1)")
        texto_aviso = json.dumps(avisos[0], ensure_ascii=False)
        for segredo in (SENHA_NOVA, SENHA_ANTIGA, token):
            if segredo and segredo in texto_aviso:
                raise Falha("B3: o aviso de senha alterada contém senha ou token")

        # entrar pela tela com a nova senha
        login_na_tela(page, email, SENHA_NOVA, "B3 login novo")
        esperar_student(page, "B3 login novo")

    cenario("B3", "redefinição pela tela: divergentes, senha curta, válida, login novo e aviso", b3)

    # --- B4 -------------------------------------------------------------------------------------------------
    def b4():
        if "link" not in referencias:
            raise Falha("B4: sem o link do B3 (o B3 não chegou a obter o link do outbox)")
        email, link = referencias["email"], referencias["link"]
        page = nova_pagina("B4")  # outro contexto do navegador, sem sessão
        abrir_link_do_email(page, link, "B4")
        preencher_id(page, "redefinir-senha", SENHA_OUTRA, "B4 reuso")
        preencher_id(page, "redefinir-confirmar", SENHA_OUTRA, "B4 reuso")
        status, corpo = enviar_e_esperar(page, "redefinir-enviar", URL_REDEFINIR, "B4 reuso")
        if status != 400:
            raise Falha(f"B4 reuso: o link já usado devolveu HTTP {status} (esperado 400)")
        erro = texto_id(page, "redefinir-erro", "B4 reuso")
        if erro != ERRO_DEFINICAO_SENHA or (corpo or {}).get("detail") != ERRO_DEFINICAO_SENHA:
            raise Falha(f"B4 reuso: redefinir-erro é {erro!r}, esperado exatamente {ERRO_DEFINICAO_SENHA!r}")
        if id_visivel(page, "redefinir-mensagem"):
            raise Falha("B4 reuso: o sucesso apareceu para link já usado")
        if login_api(email, SENHA_OUTRA)[0] == 200 or login_api(email, SENHA_NOVA)[0] != 200:
            raise Falha("B4 reuso: o link já usado alterou a senha")

    cenario("B4", "reusar o mesmo link mostra o erro genérico exato e não troca a senha", b4)

    # --- B5 ---------------------------------------------------------------------------------------------------
    def b5():
        for sufixo, rotulo in (("", "sem token"), ("?token=", "token vazio")):
            page = nova_pagina("B5")
            exigir_rota(page, "/redefinir-senha" + sufixo, f"B5 {rotulo}")
            esperar_texto_na_tela(page, MSG_SEM_TOKEN, f"B5 {rotulo}")
            if id_visivel(page, "redefinir-mensagem"):
                raise Falha(f"B5 {rotulo}: o sucesso apareceu na tela sem token")
            # envio bloqueado: botão desabilitado ou, se clicável, nenhuma requisição
            for testid, valor in (("redefinir-senha", SENHA_NOVA), ("redefinir-confirmar", SENHA_NOVA)):
                campo = page.get_by_test_id(testid).first
                try:
                    if campo.is_enabled():
                        campo.fill(valor, timeout=TIMEOUT)
                except Exception:
                    pass
            botao = page.get_by_test_id("redefinir-enviar").first
            if botao.count() > 0 and botao.is_visible() and not botao.is_disabled():
                try:
                    botao.click(timeout=TIMEOUT)
                except Exception:
                    pass
            time.sleep(1)
            if requisicoes_password_reset(page.requisicoes):
                raise Falha(f"B5 {rotulo}: foi enviada requisição: {requisicoes_password_reset(page.requisicoes)}")
            if id_visivel(page, "redefinir-mensagem"):
                raise Falha(f"B5 {rotulo}: o sucesso apareceu depois da tentativa de envio")
            atual["page"] = None

    cenario("B5", "sem token: mensagem exata e envio bloqueado", b5)

    # --- B6 ---------------------------------------------------------------------------------------------------
    def b6():
        email = semear_aluno_sem_senha("compra-expirada")
        page = nova_pagina("B6")
        exigir_rota(page, "/esqueci-senha", "B6 pedido")
        status, mensagem = pedir_link_pela_tela(page, email, "B6 pedido")
        if status != 200 or mensagem != MSG_PEDIDO:
            raise Falha(f"B6: HTTP {status}, mensagem {mensagem!r} (esperado a mesma {MSG_PEDIDO!r})")
        registros = aguardar_registros(email, 1)
        if len(registros) != 1:
            raise Falha(f"B6: o outbox tem {len(registros)} registro(s) para a conta sem senha (esperado 1)")
        link = link_do_registro(registros[0], "B6")
        if not link.startswith(f"{ALVO['base']}/definir-senha?token="):
            raise Falha(f"B6: o link {link!r} não é de definição ({ALVO['base']}/definir-senha?token=...)")
        abrir_link_do_email(page, link, "B6")
        if caminho_da_url(page.url) != "/definir-senha":
            raise Falha(f"B6: o link abriu {page.url} (esperado /definir-senha)")
        page.locator("input[name=password]").first.fill(SENHA_NOVA, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.locator(".alert-success").first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("B6: a tela de definição de senha não mostrou sucesso")
        login_na_tela(page, email, SENHA_NOVA, "B6 login")
        esperar_student(page, "B6 login")

    cenario("B6", "aluno sem senha: pede o link, recebe o de definição, define a senha e entra", b6)

    # --- B7 ---------------------------------------------------------------------------------------------------
    def b7():
        email = semear_aluno_com_senha("limite", SENHA_ANTIGA)
        page = nova_pagina("B7")
        exigir_rota(page, "/esqueci-senha", "B7 limite")
        mensagens = []
        for numero in range(1, 5):
            status, mensagem = pedir_link_pela_tela(page, email, f"B7 pedido {numero}")
            if status != 200:
                raise Falha(f"B7 pedido {numero}: HTTP {status} (esperado 200 nos 4 pedidos)")
            mensagens.append(mensagem)
        if any(m != MSG_PEDIDO for m in mensagens):
            raise Falha(f"B7: mensagens diferentes nos 4 pedidos: {mensagens}")
        registros = aguardar_registros(email, 3, ASSUNTO_REDEFINICAO)
        time.sleep(1.5)
        registros = registros_de(email, ASSUNTO_REDEFINICAO)
        if len(registros) != 3:
            raise Falha(f"B7: o outbox tem {len(registros)} registro(s) 'Redefinição de senha' (esperado exatamente 3)")

    cenario("B7", "limite: 4 pedidos pela tela, só 3 registros no outbox, mesma mensagem nos 4", b7)

    # --- B8 ---------------------------------------------------------------------------------------------------
    def b8():
        outro = semear_aluno_com_senha("sessao-aberta", SENHA_ANTIGA)
        alvo = semear_aluno_com_senha("sessao-alvo", SENHA_ANTIGA)
        status, corpo = login_api(outro, SENHA_ANTIGA)
        token_antigo = (corpo or {}).get("access_token")
        if status != 200 or not token_antigo:
            raise Falha("B8 pré-condição: não obteve token de sessão do aluno semeado")

        page = nova_pagina("B8", token_antigo=token_antigo)
        exigir_rota(page, "/esqueci-senha", "B8 pedido com sessão aberta")
        if page.evaluate("localStorage.getItem('gtt_token')") != token_antigo:
            raise Falha("B8 pré-condição: o token antigo não está guardado no navegador")
        status, mensagem = pedir_link_pela_tela(page, alvo, "B8 pedido")
        if status != 200 or mensagem != MSG_PEDIDO:
            raise Falha(f"B8 pedido: HTTP {status}, mensagem {mensagem!r}")
        registros = aguardar_registros(alvo, 1, ASSUNTO_REDEFINICAO)
        if len(registros) != 1:
            raise Falha("B8: o pedido pela tela não gerou o registro no outbox")
        link = link_do_registro(registros[0], "B8")

        abrir_link_do_email(page, link, "B8")
        if caminho_da_url(page.url) != "/redefinir-senha":
            raise Falha(f"B8: com sessão aberta o link abriu {page.url} (a rota deve ser pública)")
        preencher_id(page, "redefinir-senha", SENHA_NOVA, "B8 redefinição")
        preencher_id(page, "redefinir-confirmar", SENHA_NOVA, "B8 redefinição")
        status, _ = enviar_e_esperar(page, "redefinir-enviar", URL_REDEFINIR, "B8 redefinição")
        if status != 200:
            raise Falha(f"B8 redefinição: HTTP {status} (esperado 200)")

        chamadas = requisicoes_password_reset(page.requisicoes)
        caminhos = {c["caminho"] for c in chamadas}
        for esperado in (URL_PEDIDO, URL_REDEFINIR):
            if esperado not in caminhos:
                raise Falha(f"B8: nenhuma chamada a {esperado} foi observada (vistas: {sorted(caminhos)})")
        com_auth = [c["caminho"] for c in chamadas if "authorization" in c["cabecalhos"]]
        if com_auth:
            raise Falha(f"B8: chamadas password-reset saíram com Authorization: {com_auth}")

    cenario("B8", "sessão aberta: rotas públicas e password-reset* sem Authorization", b8)

    # --- B9 ---------------------------------------------------------------------------------------------------
    for contexto in contextos:
        try:
            contexto.close()
        except Exception:
            pass

    problemas = []
    for r in respostas_erro:
        chave = (r["metodo"], r["caminho"], r["tela"], r["status"])
        if chave not in ERROS_ESPERADOS:
            problemas.append(f"{r['rotulo']}: HTTP {r['status']} {r['metodo']} {r['caminho']} na tela {r['tela']}")
    for rotulo, status, caminho, texto in consoles_http:
        if not any(
            e["status"] == status and e["caminho"] == caminho and (e["metodo"], e["caminho"], e["tela"], e["status"]) in ERROS_ESPERADOS
            for e in respostas_erro
        ):
            problemas.append(f"{rotulo}: erro de console sem resposta esperada: {texto}")
    problemas.extend(erros_console)
    if problemas:
        resultados.append(("B9", "sem erros de console nem 4xx/5xx inesperados", False, " | ".join(problemas[:5])))
        print(f"[FAIL] B9 sem erros de console nem 4xx/5xx inesperados -> {len(problemas)} problema(s)")
    else:
        resultados.append(("B9", "sem erros de console nem 4xx/5xx inesperados", True, ""))
        print("[OK]   B9 sem erros de console nem 4xx/5xx inesperados")

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
