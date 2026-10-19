"""E2E da entrega D1 — design da landing page aplicado ao Angular (área do funcionário, área do aluno e telas públicas).

Fonte: pedido do PM (07/10/2026) "copie o design da landing page para o resto do sistema" e a landing
`frontend/landing_global_training.html` (a mesma da `main`). Contrato visual em docs/tdd/decisoes_tdd.md, D66.

Tokens copiados da landing (verificados pelo estilo COMPUTADO no Chromium, não pelo CSS-fonte):
  nav escura #212830 = rgb(33, 40, 48); teal #0096c7 = rgb(0, 150, 199); laranja do logo #ff7a18 = rgb(255, 122, 24);
  texto #17212b = rgb(23, 33, 43); família Barlow no corpo e Barlow Condensed nos títulos.

Cenários:
  V1 tela de login (/): barra superior [data-testid=app-nav] visível com fundo rgb(33, 40, 48)
  V2 logo [data-testid=app-logo]: círculo "GT" e o texto "Global Training" em laranja rgb(255, 122, 24)
  V3 corpo da página em Barlow (font-family computada contém "Barlow") e cor de texto rgb(23, 33, 43)
  V4 botão primário (Entrar) com fundo teal rgb(0, 150, 199) e texto branco
  V5 título do cartão de login em Barlow Condensed
  V6 rodapé [data-testid=app-footer] visível, fundo rgb(33, 40, 48), com "Global Training Technology"
  V7 Gestão em /admin: aba ativa (ul.nav-tabs .nav-link.active) em teal rgb(0, 150, 199); "Sair" na barra superior
  V8 aluno em /student: barra superior e rodapé presentes; botão "Sair" visível na barra
  V9 regressão de seletores: o login continua com input[name=email], input[name=password], button[type=submit] e
     o link [data-testid=esqueci-link]
  V10 sem erros de console (4xx/5xx de /api) nem exceções de página

Harness isolado (D58): sobe e derruba os próprios servidores. Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_d1_design_landing_angular.py -s
"""

import re
import sys
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
SENHA = "senha-aluno-d1-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")

NAV = "rgb(33, 40, 48)"
TEAL = "rgb(0, 150, 199)"
LARANJA = "rgb(255, 122, 24)"
TEXTO = "rgb(23, 33, 43)"
BRANCO = "rgb(255, 255, 255)"


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def estilo(page, seletor, propriedade):
    loc = page.locator(seletor).first
    loc.wait_for(state="visible", timeout=TIMEOUT)
    return loc.evaluate(f"e => getComputedStyle(e).getPropertyValue('{propriedade}')").strip()


def semear_aluno():
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.d1.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, "Aluno D1", get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return email


def entrar(page, email, senha, destino, rotulo):
    try:
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 2)
        page.wait_for_load_state("networkidle")
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: login não levou a /{destino} (URL atual {page.url})")


@pytest.fixture(scope="module")
def servidores():
    with ambiente_isolado("d1") as ambiente:
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


def test_d1_design_landing_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    paginas = {}

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            # Só erros da própria API contam: recursos de terceiros (fontes, CDN) podem estar bloqueados no ambiente
            # de teste e não são defeito da tela.
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros_console.append(f"{msg.text[:120]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        return page

    def cenario(codigo, nome, funcao):
        try:
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")

    def login_page():
        if "login" not in paginas:
            page = nova_pagina()
            page.goto(ALVO["base"] + "/", wait_until="networkidle")
            paginas["login"] = page
        return paginas["login"]

    def v1():
        page = login_page()
        fundo = estilo(page, '[data-testid="app-nav"]', "background-color")
        if fundo != NAV:
            raise Falha(f"V1: fundo da barra superior {fundo} (esperado {NAV})")

    def v2():
        page = login_page()
        logo = page.locator('[data-testid="app-logo"]').first
        logo.wait_for(state="visible", timeout=TIMEOUT)
        texto = logo.inner_text()
        if "GT" not in texto or "Global Training" not in texto:
            raise Falha(f"V2: o logo mostra {texto!r} (esperado o círculo 'GT' e 'Global Training')")
        cor = estilo(page, '[data-testid="app-logo-nome"]', "color")
        if cor != LARANJA:
            raise Falha(f"V2: cor do nome no logo {cor} (esperado {LARANJA})")

    def v3():
        page = login_page()
        familia = estilo(page, "body", "font-family")
        if "Barlow" not in familia:
            raise Falha(f"V3: font-family do corpo {familia!r} (esperado Barlow)")
        cor = estilo(page, "body", "color")
        if cor != TEXTO:
            raise Falha(f"V3: cor do texto {cor} (esperado {TEXTO})")

    def v4():
        page = login_page()
        fundo = estilo(page, "button[type=submit]", "background-color")
        cor = estilo(page, "button[type=submit]", "color")
        if fundo != TEAL or cor != BRANCO:
            raise Falha(f"V4: botão Entrar com fundo {fundo} e texto {cor} (esperado {TEAL} / {BRANCO})")

    def v5():
        page = login_page()
        familia = estilo(page, ".card-title", "font-family")
        if "Barlow Condensed" not in familia:
            raise Falha(f"V5: título do cartão em {familia!r} (esperado Barlow Condensed)")

    def v6():
        page = login_page()
        rodape = page.locator('[data-testid="app-footer"]').first
        try:
            rodape.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("V6: rodapé [data-testid=app-footer] não está visível")
        fundo = estilo(page, '[data-testid="app-footer"]', "background-color")
        if fundo != NAV:
            raise Falha(f"V6: fundo do rodapé {fundo} (esperado {NAV})")
        if "Global Training Technology" not in rodape.inner_text():
            raise Falha("V6: o rodapé não mostra 'Global Training Technology'")

    def v7():
        page = nova_pagina()
        entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin", "V7 login da Gestão")
        page.locator("ul.nav-tabs .nav-link.active").first.wait_for(state="visible", timeout=TIMEOUT)
        cor = estilo(page, "ul.nav-tabs .nav-link.active", "color")
        if cor != TEAL:
            raise Falha(f"V7: aba ativa com cor {cor} (esperado {TEAL})")
        sair = page.locator('[data-testid="app-nav"]').get_by_role("button", name="Sair")
        if sair.count() != 1 or not sair.first.is_visible():
            raise Falha("V7: o botão 'Sair' não está na barra superior")

    def v8():
        page = nova_pagina()
        entrar(page, semear_aluno(), SENHA, "student", "V8 login do aluno")
        for testid in ("app-nav", "app-footer"):
            alvo = page.locator(f'[data-testid="{testid}"]')
            if alvo.count() != 1 or not alvo.first.is_visible():
                raise Falha(f"V8: [data-testid={testid}] não aparece em /student")
        sair = page.locator('[data-testid="app-nav"]').get_by_role("button", name="Sair")
        if sair.count() != 1 or not sair.first.is_visible():
            raise Falha("V8: o botão 'Sair' não está na barra superior em /student")

    def v9():
        page = login_page()
        for seletor in ("input[name=email]", "input[name=password]", "button[type=submit]", '[data-testid="esqueci-link"]'):
            if page.locator(seletor).count() == 0:
                raise Falha(f"V9: o login perdeu o seletor {seletor}")

    def v10():
        if erros_console:
            raise Falha(f"V10: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("V1", "barra superior com o fundo escuro da landing", v1)
    cenario("V2", "logo 'GT' + 'Global Training' em laranja", v2)
    cenario("V3", "corpo em Barlow com a cor de texto da landing", v3)
    cenario("V4", "botão primário teal com texto branco", v4)
    cenario("V5", "título do cartão em Barlow Condensed", v5)
    cenario("V6", "rodapé escuro com 'Global Training Technology'", v6)
    cenario("V7", "Gestão: aba ativa teal e 'Sair' na barra", v7)
    cenario("V8", "aluno: barra e rodapé em /student, 'Sair' na barra", v8)
    cenario("V9", "login mantém os seletores dos e2e anteriores", v9)
    cenario("V10", "sem erros de console", v10)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
