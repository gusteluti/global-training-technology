"""E2E do limite de tentativas de login (S2, D79; Chromium via Playwright).

Teste VERMELHO escrito antes da implementacao: hoje o POST /api/token nao limita tentativas, entao a 6a tentativa
(com a senha certa) entra em /student em vez de mostrar o 429.

Contrato de tela (D79): "login e chat mostram o texto do 429 como erro, sem travar a tela".
  - 5 senhas erradas na tela de login: cada uma mostra o erro de credenciais de sempre (detail do 400);
  - a 6a tentativa, mesmo com a senha certa, recebe 429 e a tela mostra o texto exato
    "Muitas tentativas. Tente novamente em alguns minutos." como erro (.alert-danger), sem entrar e sem token;
  - a aba continua usavel: na mesma pagina, outra conta com a senha certa entra em /student.

Escolhas de forma do teste (nenhuma define politica):
  - campos e botao da tela de login: input[name=email], input[name=password], button[type=submit] (como no B1);
  - o erro e procurado em .alert-danger (padrao atual da tela de login);
  - "sem token": localStorage nao tem `gtt_token` depois do 429.
  - O chat da landing (31a mensagem) NAO e coberto aqui: o pedido do orquestrador limita o e2e ao login.

Cenarios (checks numerados):
  S1 pre-condicao: login de aluno com a senha certa chega a /student pela tela (servidor, seed e tela funcionam)
  L1 cinco senhas erradas: cada POST /api/token responde 400 e a tela mostra o erro de credenciais
  L2 a 6a tentativa com a senha certa: POST /api/token 429, texto exato em .alert-danger, URL continua no login,
     sem gtt_token
  L3 a aba continua usavel: outra conta, senha certa, na mesma pagina -> /student
  L4 sem erros de console nem 4xx/5xx inesperados (os unicos permitidos: 400 e 429 do POST /api/token na tela /)

Harness isolado (D58): frontend/e2e/apoio_harness_h1.ambiente_isolado sobe backend (SQLite e cursos temporarios) e
ng serve em portas livres; seed pela camada Database no mesmo SQLite temporario. Nada toca backend/db.sqlite.
Execucao (da raiz do repo): py -3 -m pytest frontend/e2e/test_s2_limites_angular.py -s
"""

import os
import re
import sys
import tempfile
import urllib.parse
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_s2_limites"))

ERRO_LOGIN = "Muitas tentativas. Tente novamente em alguns minutos."
ERRO_CREDENCIAIS = "Usuário ou senha inválidos"
SENHA = "senha-certa-s2-e2e-2026"
SENHA_ERRADA = "senha-errada-s2-e2e"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
URL_LOGIN = "/api/token"
ERROS_ESPERADOS = {("POST", URL_LOGIN, "/", 400), ("POST", URL_LOGIN, "/", 429)}


class Falha(Exception):
    pass


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"s2.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    Database.add_user(email, "Aluno S2", get_password_hash(SENHA), role="student")
    if Database.get_user_by_email(email) is None:
        raise Falha(f"seed: conta {email} nao foi criada")
    return email


def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/")


def caminho_da_tela(url):
    return caminho_da_url(url) or "/"


def abrir_login(page, rotulo):
    page.goto(ALVO["base"] + "/", wait_until="networkidle")
    if caminho_da_tela(page.url) != "/":
        raise Falha(f"{rotulo}: a tela de login nao abriu em / (URL {page.url})")


def tentar_login(page, email, senha, rotulo):
    """Preenche e envia o login; devolve o status HTTP do POST /api/token."""
    page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
    page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)

    def e_o_login(resposta):
        return resposta.request.method == "POST" and caminho_da_url(resposta.url) == URL_LOGIN

    try:
        with page.expect_response(e_o_login, timeout=TIMEOUT * 2) as info:
            page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: enviar o login nao gerou POST {URL_LOGIN}")
    return info.value.status


def texto_do_erro(page, rotulo):
    loc = page.locator(".alert-danger").first
    try:
        loc.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: nenhum erro (.alert-danger) visivel; corpo: {page.inner_text('body')[:200]!r}")
    return loc.inner_text().strip()


def esperar_student(page, rotulo):
    try:
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /student)")


@pytest.fixture(scope="module")
def servidores():
    with ambiente_isolado("s2") as ambiente:
        ALVO.update(base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"])
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_s2_limite_de_login_angular_e2e(servidores, browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    respostas_erro = []
    consoles_http = []
    contextos = []
    atual = {"page": None}
    estado = {}

    def nova_pagina(rotulo):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()
        atual["page"] = page

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
                consoles_http.append((rotulo, int(m.group(1)), msg.text))
                return
            erros_console.append(f"{rotulo}: {msg.text}")

        page.on("response", ao_resposta)
        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: {e}"))
        return page

    def cenario(codigo, nome, fn):
        try:
            fn()
            resultados.append((codigo, nome, True, ""))
            print(f"[OK]   {codigo} {nome}")
        except Exception as erro:
            page = atual["page"]
            if page is not None:
                try:
                    page.screenshot(path=str(OUT / f"{codigo}_falha.png"), full_page=True)
                except Exception:
                    pass
            detalhe = str(erro) if isinstance(erro, Falha) else f"{type(erro).__name__}: {str(erro).splitlines()[0] if str(erro) else ''}"
            resultados.append((codigo, nome, False, detalhe))
            print(f"[FAIL] {codigo} {nome} -> {detalhe}")

    def s1():
        email = semear_aluno("pre")
        page = nova_pagina("S1")
        abrir_login(page, "S1")
        status = tentar_login(page, email, SENHA, "S1")
        if status != 200:
            raise Falha(f"S1: login certo respondeu HTTP {status}")
        esperar_student(page, "S1")

    cenario("S1", "pre-condicao: login de aluno pela tela chega a /student", s1)

    def l1():
        email = semear_aluno("bloqueio")
        estado["email"] = email
        page = nova_pagina("L1")
        estado["page"] = page
        abrir_login(page, "L1")
        for i in range(5):
            status = tentar_login(page, email, SENHA_ERRADA, f"L1 tentativa {i + 1}")
            if status != 400:
                raise Falha(f"L1: tentativa errada {i + 1} respondeu HTTP {status} (esperado 400)")
            texto = texto_do_erro(page, f"L1 tentativa {i + 1}")
            if texto != ERRO_CREDENCIAIS:
                raise Falha(f"L1: tentativa {i + 1} mostrou {texto!r} (esperado {ERRO_CREDENCIAIS!r})")

    cenario("L1", "cinco senhas erradas mostram o erro de credenciais", l1)

    def l2():
        page = estado.get("page")
        if page is None:
            raise Falha("L2: depende de L1")
        atual["page"] = page
        status = tentar_login(page, estado["email"], SENHA, "L2 sexta tentativa")
        if status != 429:
            raise Falha(f"L2: a 6a tentativa (senha certa) respondeu HTTP {status} (esperado 429); URL {page.url}")
        texto = texto_do_erro(page, "L2")
        if texto != ERRO_LOGIN:
            raise Falha(f"L2: a tela mostrou {texto!r} (esperado o texto exato {ERRO_LOGIN!r})")
        page.wait_for_timeout(500)
        if caminho_da_tela(page.url) != "/":
            raise Falha(f"L2: a tela saiu do login apos o 429 (URL {page.url})")
        token = page.evaluate("() => localStorage.getItem('gtt_token')")
        if token:
            raise Falha("L2: ficou um gtt_token no navegador apos o 429")

    cenario("L2", "6a tentativa com a senha certa: 429 com o texto exato, sem entrar", l2)

    def l3():
        page = estado.get("page")
        if page is None:
            raise Falha("L3: depende de L1")
        atual["page"] = page
        outra = semear_aluno("livre")
        status = tentar_login(page, outra, SENHA, "L3")
        if status != 200:
            raise Falha(f"L3: outra conta com a senha certa respondeu HTTP {status} (esperado 200)")
        esperar_student(page, "L3")

    cenario("L3", "a aba continua usavel: outra conta entra em /student", l3)

    for contexto in contextos:
        try:
            contexto.close()
        except Exception:
            pass

    problemas = []
    for r in respostas_erro:
        if (r["metodo"], r["caminho"], r["tela"], r["status"]) not in ERROS_ESPERADOS:
            problemas.append(f"{r['rotulo']}: HTTP {r['status']} {r['metodo']} {r['caminho']} na tela {r['tela']}")
    for rotulo, status, texto in consoles_http:
        if status not in (400, 429):
            problemas.append(f"{rotulo}: erro de console inesperado: {texto}")
    problemas.extend(erros_console)
    resultados.append(("L4", "sem erros de console nem 4xx/5xx inesperados", not problemas, " | ".join(problemas[:5])))
    print(f"[{'OK' if not problemas else 'FAIL'}]   L4 sem erros de console nem 4xx/5xx inesperados")

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
