"""E2E da entrega S4/S5/U3/U9 - conta do aluno: perfil, troca de senha, desativar/reativar e sessao expirada (D80).

Backend correspondente: backend/tests/test_s4_conta_aluno.py. Modo autonomo: D69.
Teste VERMELHO escrito antes da implementacao: hoje nao existem /student/perfil, o link "Meu perfil", a saudacao com o
primeiro nome, os botoes de desativar/reativar no detalhe do aluno nem o tratamento do 401 na SPA.

Contrato de tela (D80):
  - Cabecalho da area do aluno (/student): "Olá, <primeiro nome>!".
  - Link "Meu perfil" na area do aluno -> /student/perfil, com
      perfil-nome, perfil-telefone, perfil-salvar, perfil-senha-atual, perfil-senha-nova, perfil-senha-salvar,
      mensagens perfil-ok / perfil-erro (data-testid).
  - Troca de senha com a atual errada: perfil-erro com "Senha atual incorreta."; com a certa: perfil-ok e o aluno
    continua logado (a SPA guarda o token novo devolvido pela API; o antigo deixa de valer).
  - Detalhe do aluno (F3) para a Gestao: aluno-desativar / aluno-reativar com confirmacao e o badge aluno-desativado.
  - U9: resposta 401 de /api/student/ (ou /api/dashboard/, /api/admin/) com JWT -> a SPA apaga o token e vai para
    /login?next=<rota atual>, mostrando "Sua sessão expirou. Entre novamente."
  - Login de aluno desativado com a senha certa: a tela mostra "Sua conta está desativada. Fale com o suporte."

Escolhas de forma do teste (nenhuma define politica; ver relatorio do agente-testes):
  - A confirmacao de desativar/reativar e a nativa (window.confirm), padrao das acoes de Gestao do projeto (arquivar
    curso F1, reembolso S7). O teste aceita o dialogo e exige que ele tenha aparecido.
  - O link "Meu perfil" e procurado pelo texto exato (link ou botao). As mensagens de sessao expirada e de conta
    desativada sao procuradas no texto da pagina de login (sem fixar o elemento).
  - O texto de perfil-ok nao e fixado (D80 nao fixa). O cabecalho e conferido depois de abrir /student de novo.
  - "Recarregar dados" da aba aberta do aluno = recarregar /student (page.reload), que refaz GET /api/student/...
  - Os campos de senha usam a senha nova da D14 (8+ caracteres). Nenhum login errado alem de um (limite D79).

Cenarios (checks numerados):
  H1 login do aluno: /student mostra "Olá, Mariana!"
  H2 o link "Meu perfil" leva a /student/perfil
  P1 editar nome e telefone e salvar: PUT /api/student/me 200, perfil-ok visivel, dados gravados
  P2 o cabecalho de /student reflete o nome novo ("Olá, Beatriz!")
  S1 trocar a senha com a atual errada: perfil-erro com "Senha atual incorreta."
  S2 trocar com a certa: perfil-ok, token novo no navegador, o antigo cai na API, a tela continua logada
  D1 Gestao desativa o aluno no detalhe (confirmacao aceita): aparece aluno-desativado
  U1 a aba do aluno, ao recarregar, recebe 401 e vai para /login?next=/student com "Sua sessão expirou. Entre
     novamente." e sem token guardado
  L1 login do aluno desativado com a senha certa: 403 e o texto exato na tela, sem entrar
  R1 Gestao reativa no detalhe (confirmacao aceita): o badge aluno-desativado some
  R2 o login do aluno volta a funcionar e chega a /student
  K1 sem excecoes de pagina nem 4xx/5xx inesperados (permitidos: 400 da troca de senha, 401 de /api/student/ depois
     da desativacao, 403 do login desativado)

Harness isolado (D58): apoio_harness_h1.ambiente_isolado sobe backend (SQLite e cursos temporarios) e ng serve em
portas livres; seed pela camada Database no mesmo SQLite temporario. Nada toca backend/db.sqlite.
Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_s4_conta_aluno_angular.py -s
"""

import json
import os
import re
import sqlite3
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
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_s4_conta"))

SENHA = "senha-aluno-s4-e2e-2026"
SENHA_NOVA = "senha-nova-s4-e2e-2026"
NOME = "Mariana Teste"
NOME_NOVO = "Beatriz Lima"
TELEFONE = "(11) 98765-4321"
TELEFONE_DIGITOS = "11987654321"

TXT_OLA = "Olá, Mariana!"
TXT_OLA_NOVO = "Olá, Beatriz!"
TXT_SENHA_ATUAL = "Senha atual incorreta."
TXT_SESSAO = "Sua sessão expirou. Entre novamente."
TXT_DESATIVADA = "Sua conta está desativada. Fale com o suporte."

TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_ABA = "ul.nav-tabs button.nav-link"


def _sel(testid):
    return f'[data-testid="{testid}"]'


class Falha(Exception):
    """Falha de um passo de cenario; a mensagem diz o que faltou na tela."""


# ---------------------------------------------------------------------------------------------
# API e banco
# ---------------------------------------------------------------------------------------------

def _api(metodo, caminho, corpo=None, token=None):
    cabecalhos = {}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        cabecalhos["Content-Type"] = "application/json"
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(ALVO["api"] + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read() or b"null")
        except Exception:
            return erro.code, None


def _linha_usuario(user_id):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    conn.row_factory = sqlite3.Row
    try:
        linha = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(linha) if linha else None
    finally:
        conn.close()


def semear():
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.s4.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, NOME, get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: nao foi possivel criar {email}")
    return {"uid": uid, "email": email}


# ---------------------------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------------------------

def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/") or "/"


def esperar_condicao(fn, codigo, limite_ms=TIMEOUT * 2):
    """Repete fn() ate devolver None; uma string e o motivo da divergencia."""
    passos = max(1, limite_ms // 250)
    motivo = "sem leitura"
    for _ in range(passos):
        try:
            motivo = fn()
        except sync_api.Error as erro:
            motivo = f"erro do navegador: {str(erro).splitlines()[0] if str(erro) else type(erro).__name__}"
        if motivo is None:
            return
        time.sleep(0.25)
    raise Falha(f"{codigo}: {motivo}")


def esperar(locator, codigo, descricao):
    try:
        locator.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: {descricao} nao aparece na tela")
    return locator.first


def texto_na_pagina(page, texto, codigo, onde):
    def leitura():
        corpo = _normalizar(page.inner_text("body"))
        return None if texto in corpo else f"{onde} nao mostra {texto!r}; corpo: {corpo[:300]!r}"
    esperar_condicao(leitura, codigo)


def token_no_navegador(page):
    return page.evaluate("() => localStorage.getItem('gtt_token')")


def enviar_login(page, email, senha, codigo):
    """Preenche e envia o login na pagina atual; devolve o status do POST /api/token."""
    page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
    page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)

    def e_o_login(resposta):
        return resposta.request.method == "POST" and caminho_da_url(resposta.url) == "/api/token"

    try:
        with page.expect_response(e_o_login, timeout=TIMEOUT * 2) as info:
            page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: enviar o login nao gerou POST /api/token")
    return info.value.status


def entrar(page, email, senha, destino, codigo):
    page.goto(ALVO["base"] + "/", wait_until="networkidle")
    status = enviar_login(page, email, senha, codigo)
    if status != 200:
        raise Falha(f"{codigo}: login de {email} respondeu HTTP {status}")
    try:
        page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 3)
        page.wait_for_load_state("networkidle")
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: login de {email} nao levou a /{destino} (URL atual {page.url})")


def clicar_e_esperar_resposta(page, locator, metodo, caminho, codigo):
    def e_a_chamada(resposta):
        return resposta.request.method == metodo and caminho_da_url(resposta.url) == caminho

    try:
        with page.expect_response(e_a_chamada, timeout=TIMEOUT * 2) as info:
            locator.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: o clique nao gerou {metodo} {caminho}")
    return info.value.status


def clicar_aba(page, nome):
    aba = page.locator(SEL_ABA, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$"))
    try:
        aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"a aba '{nome}' nao aparece")
    aba.first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def abrir_detalhe(page, email, nome, codigo):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
    clicar_aba(page, "Alunos")
    linha = esperar(page.locator("tr", has_text=email), codigo, f"a linha do aluno {email}")
    try:
        linha.get_by_text(nome, exact=True).first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: o nome {nome!r} nao esta clicavel na linha do aluno")
    page.wait_for_load_state("networkidle")
    detalhe = esperar(page.locator(_sel("aluno-detalhe")), codigo, "o detalhe do aluno (aluno-detalhe)")
    return detalhe


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("s4") as ambiente:
            ALVO.update(base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"])
            yield ambiente
    finally:
        os.environ.update(salvos)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


# ---------------------------------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------------------------------

def test_s4_conta_aluno_angular_e2e(servidores, browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_pagina = []
    respostas_erro = []
    contextos = []
    paginas = {}
    dialogos = []
    estado = {"desativado": False}

    seed = {"ok": False, "erro": ""}
    s = {}
    try:
        s.update(semear())
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(rotulo):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_resposta(resposta):
            if resposta.status >= 400 and "/api/" in resposta.url:
                respostas_erro.append({
                    "rotulo": rotulo, "status": resposta.status, "metodo": resposta.request.method,
                    "caminho": caminho_da_url(resposta.url), "desativado": estado["desativado"],
                })

        def ao_dialogo(dialogo):
            dialogos.append((rotulo, dialogo.type, dialogo.message))
            dialogo.accept()

        page.on("response", ao_resposta)
        page.on("dialog", ao_dialogo)
        page.on("pageerror", lambda e: erros_pagina.append(f"{rotulo}: {e}"[:200]))
        return page

    def pagina(perfil):
        if perfil not in paginas:
            page = nova_pagina(perfil)
            if perfil == "gestao":
                entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin", "login da Gestao")
            else:
                entrar(page, s["email"], SENHA, "student", "login do aluno")
            paginas[perfil] = page
        return paginas[perfil]

    def cenario(codigo, nome, funcao):
        try:
            if not seed["ok"]:
                raise Falha(f"seed falhou: {seed['erro']}")
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            texto = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            for perfil, page in paginas.items():
                try:
                    page.screenshot(path=str(OUT / f"{codigo}_{perfil}_falha.png"), full_page=True)
                except Exception:
                    pass
            resultados.append((codigo, nome, False, texto))
            print(f"[FAIL] {codigo} {nome} -> {texto}")

    def h1():
        page = pagina("aluno")
        texto_na_pagina(page, TXT_OLA, "H1", "o cabecalho de /student")

    def h2():
        page = pagina("aluno")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        link = page.get_by_text("Meu perfil", exact=True)
        esperar(link, "H2", 'o link "Meu perfil"').click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student/perfil", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"H2: o link 'Meu perfil' nao levou a /student/perfil (URL {page.url})")
        esperar(page.locator(_sel("perfil-nome")), "H2", "perfil-nome")

    def abrir_perfil(page, codigo):
        page.goto(ALVO["base"] + "/student/perfil", wait_until="networkidle")
        if caminho_da_url(page.url) != "/student/perfil":
            raise Falha(f"{codigo}: /student/perfil nao abriu (URL {page.url})")
        esperar(page.locator(_sel("perfil-nome")), codigo, "perfil-nome")

    def p1():
        page = pagina("aluno")
        abrir_perfil(page, "P1")
        page.locator(_sel("perfil-nome")).first.fill(NOME_NOVO, timeout=TIMEOUT)
        page.locator(_sel("perfil-telefone")).first.fill(TELEFONE, timeout=TIMEOUT)
        status = clicar_e_esperar_resposta(page, page.locator(_sel("perfil-salvar")).first, "PUT", "/api/student/me",
                                           "P1")
        if status != 200:
            raise Falha(f"P1: PUT /api/student/me respondeu HTTP {status}")
        esperar(page.locator(_sel("perfil-ok")), "P1", "perfil-ok depois de salvar")
        status, corpo = _api("GET", "/api/student/me", token=token_no_navegador(page))
        if status != 200 or not corpo:
            raise Falha(f"P1: GET /api/student/me respondeu HTTP {status}")
        digitos = "".join(ch for ch in str(corpo.get("phone")) if ch.isdigit())
        if corpo.get("name") != NOME_NOVO or digitos != TELEFONE_DIGITOS:
            raise Falha(f"P1: dados gravados {corpo!r} (esperado nome {NOME_NOVO!r}, telefone {TELEFONE_DIGITOS})")

    def p2():
        page = pagina("aluno")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        texto_na_pagina(page, TXT_OLA_NOVO, "P2", "o cabecalho de /student depois de salvar o nome")
        if TXT_OLA in _normalizar(page.inner_text("body")):
            raise Falha(f"P2: o cabecalho ainda mostra {TXT_OLA!r}")

    def trocar_senha(page, atual, nova, codigo):
        abrir_perfil(page, codigo)
        page.locator(_sel("perfil-senha-atual")).first.fill(atual, timeout=TIMEOUT)
        page.locator(_sel("perfil-senha-nova")).first.fill(nova, timeout=TIMEOUT)
        return clicar_e_esperar_resposta(page, page.locator(_sel("perfil-senha-salvar")).first, "POST",
                                         "/api/student/me/password", codigo)

    def s1():
        page = pagina("aluno")
        antes = token_no_navegador(page)
        status = trocar_senha(page, "senha-que-nao-e-a-atual", SENHA_NOVA, "S1")
        if status != 400:
            raise Falha(f"S1: a troca com a senha atual errada respondeu HTTP {status} (esperado 400)")
        erro = esperar(page.locator(_sel("perfil-erro")), "S1", "perfil-erro")
        texto = _normalizar(erro.inner_text())
        if TXT_SENHA_ATUAL not in texto:
            raise Falha(f"S1: perfil-erro mostra {texto!r} (esperado {TXT_SENHA_ATUAL!r})")
        if token_no_navegador(page) != antes:
            raise Falha("S1: a troca recusada mudou o token do navegador")

    def s2():
        page = pagina("aluno")
        antigo = token_no_navegador(page)
        s["token_antigo"] = antigo
        status = trocar_senha(page, SENHA, SENHA_NOVA, "S2")
        if status != 200:
            raise Falha(f"S2: a troca com a senha certa respondeu HTTP {status}")
        esperar(page.locator(_sel("perfil-ok")), "S2", "perfil-ok depois de trocar a senha")
        novo = token_no_navegador(page)
        if not novo or novo == antigo:
            raise Falha("S2: o navegador nao guardou o token novo devolvido pela troca")
        status_antigo, corpo = _api("GET", "/api/student/me", token=antigo)
        if status_antigo != 401:
            raise Falha(f"S2: o token antigo ainda vale na API (HTTP {status_antigo})")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        if caminho_da_url(page.url) != "/student/perfil":
            raise Falha(f"S2: depois da troca o aluno nao continua logado (URL {page.url})")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        texto_na_pagina(page, TXT_OLA_NOVO, "S2", "/student depois da troca de senha")

    def d1():
        page = pagina("gestao")
        detalhe = abrir_detalhe(page, s["email"], NOME_NOVO, "D1")
        antes = len(dialogos)
        botao = esperar(detalhe.locator(_sel("aluno-desativar")), "D1", "o botao aluno-desativar")
        estado["desativado"] = True
        status = clicar_e_esperar_resposta(page, botao, "POST", f"/api/admin/students/{s['uid']}/deactivate", "D1")
        if len(dialogos) == antes:
            raise Falha("D1: desativar nao pediu confirmacao (window.confirm)")
        if status != 200:
            raise Falha(f"D1: POST deactivate respondeu HTTP {status}")
        esperar(page.locator(_sel("aluno-desativado")), "D1", "o badge aluno-desativado")
        if (_linha_usuario(s["uid"]) or {}).get("is_active") != 0:
            raise Falha("D1: a conta nao ficou inativa no banco")

    def u1():
        page = pagina("aluno")
        page.reload(wait_until="networkidle")
        def leitura():
            if caminho_da_url(page.url) != "/login":
                return f"a aba do aluno nao foi para /login depois do 401 (URL {page.url})"
            proximo = urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query).get("next", [""])[0]
            if not proximo.startswith("/student"):
                return f"/login sem next=/student (URL {page.url})"
            return None
        esperar_condicao(leitura, "U1", TIMEOUT * 3)
        texto_na_pagina(page, TXT_SESSAO, "U1", "a tela de login depois do 401")
        if token_no_navegador(page):
            raise Falha("U1: o token continua guardado no navegador depois do 401")

    def l1():
        page = pagina("aluno")
        if caminho_da_url(page.url) != "/login":
            page.goto(ALVO["base"] + "/login", wait_until="networkidle")
        status = enviar_login(page, s["email"], SENHA_NOVA, "L1")
        if status != 403:
            raise Falha(f"L1: login do desativado com a senha certa respondeu HTTP {status} (esperado 403)")
        texto_na_pagina(page, TXT_DESATIVADA, "L1", "a tela de login")
        page.wait_for_timeout(500)
        if caminho_da_url(page.url) != "/login":
            raise Falha(f"L1: a tela saiu do login (URL {page.url})")
        if token_no_navegador(page):
            raise Falha("L1: ficou token no navegador depois do 403")

    def r1():
        page = pagina("gestao")
        detalhe = abrir_detalhe(page, s["email"], NOME_NOVO, "R1")
        esperar(detalhe.locator(_sel("aluno-desativado")), "R1", "o badge aluno-desativado antes de reativar")
        antes = len(dialogos)
        botao = esperar(detalhe.locator(_sel("aluno-reativar")), "R1", "o botao aluno-reativar")
        status = clicar_e_esperar_resposta(page, botao, "POST", f"/api/admin/students/{s['uid']}/reactivate", "R1")
        if len(dialogos) == antes:
            raise Falha("R1: reativar nao pediu confirmacao (window.confirm)")
        if status != 200:
            raise Falha(f"R1: POST reactivate respondeu HTTP {status}")
        def leitura():
            n = page.locator(_sel("aluno-desativado")).count()
            visivel = n and page.locator(_sel("aluno-desativado")).first.is_visible()
            return f"o badge aluno-desativado continua visivel" if visivel else None
        esperar_condicao(leitura, "R1")
        if (_linha_usuario(s["uid"]) or {}).get("is_active") != 1:
            raise Falha("R1: a conta nao voltou a ficar ativa no banco")
        estado["desativado"] = False

    def r2():
        page = pagina("aluno")
        if caminho_da_url(page.url) != "/login":
            page.goto(ALVO["base"] + "/login?next=%2Fstudent", wait_until="networkidle")
        status = enviar_login(page, s["email"], SENHA_NOVA, "R2")
        if status != 200:
            raise Falha(f"R2: login depois de reativar respondeu HTTP {status}")
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 3)
            page.wait_for_load_state("networkidle")
        except sync_api.TimeoutError:
            raise Falha(f"R2: o login depois de reativar nao levou a /student (URL {page.url})")
        texto_na_pagina(page, TXT_OLA_NOVO, "R2", "/student depois de reativar")

    cenario("H1", 'area do aluno mostra "Olá, <primeiro nome>!"', h1)
    cenario("H2", 'o link "Meu perfil" leva a /student/perfil', h2)
    cenario("P1", "editar nome e telefone salva e mostra perfil-ok", p1)
    cenario("P2", "o cabecalho reflete o nome novo", p2)
    cenario("S1", "troca de senha com a atual errada mostra perfil-erro com o texto exato", s1)
    cenario("S2", "troca de senha com a atual certa mostra perfil-ok e o aluno continua logado", s2)
    cenario("D1", "Gestao desativa o aluno no detalhe (confirmacao) e aparece aluno-desativado", d1)
    cenario("U1", "a aba aberta do aluno recebe 401 e vai para /login?next= com a mensagem de sessao", u1)
    cenario("L1", "login do desativado com a senha certa mostra o texto do 403", l1)
    cenario("R1", "Gestao reativa no detalhe (confirmacao) e o badge some", r1)
    cenario("R2", "o login do aluno volta a funcionar", r2)

    def esperado(r):
        if r["metodo"] == "POST" and r["caminho"] == "/api/student/me/password" and r["status"] == 400:
            return True
        if r["status"] == 401 and r["caminho"].startswith("/api/student/") and r["desativado"]:
            return True
        if r["metodo"] == "POST" and r["caminho"] == "/api/token" and r["status"] == 403:
            return True
        return False

    problemas = [f"{r['rotulo']}: HTTP {r['status']} {r['metodo']} {r['caminho']}"
                 for r in respostas_erro if not esperado(r)]
    problemas.extend(erros_pagina)
    resultados.append(("K1", "sem excecoes de pagina nem 4xx/5xx inesperados", not problemas,
                       " | ".join(problemas[:6])))
    print(f"[{'PASS' if not problemas else 'FAIL'}] K1 sem excecoes de pagina nem 4xx/5xx inesperados"
          + (f" -> {' | '.join(problemas[:6])}" if problemas else ""))

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
