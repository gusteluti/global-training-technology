"""E2E da D3 (D93) — ajustes de design das telas novas para seguir a landing (itens 1 a 8 e 10 da revisão de 21/10).

Contrato de tela (D93), verificado por estilo COMPUTADO no Chromium:
  G1 logo: aluno logado -> href /student e clicar mantém em /student; Gestão -> /admin; sem login -> "/"
  G2 atalhos "Comprar cursos" e "Meu perfil" sem sublinhado, iguais aos botões de rolagem (mesma borda e fonte)
  G3 avaliação: sem avaliação, o seletor já mostra "5 ★"; enviar mostra [data-testid=curso-avaliacao-ok];
     com avaliação 4, ao recarregar o seletor mostra "4 ★"; o comentário tem largura útil (>= 200 px)
  G4 aviso de gravação do chat com respiro lateral (padding-left >= 12 px, igual ao das mensagens)
  G5 catálogo: rótulo de seção "Catálogo", ícone com as iniciais em cada cartão e preço em Barlow Condensed teal
  G6 paleta: barra de progresso em teal; status "Em análise" com fundo da paleta (não o azul padrão do Bootstrap)
  G7 observabilidade: custo "US$ 0,0000" (vírgula) numa linha só; percentuais com vírgula
  G8 financeiro: a coluna Curso mostra o NOME do curso, não o id
  G10 celular (390 px): abas do painel numa linha só, com rolagem lateral
  G11 sem erros de console de /api nem exceções de página

Harness isolado (D58). Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_d3_ajustes_design_angular.py -s
"""

import json
import re
import sys
import urllib.error
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
SENHA = "senha-aluno-d3-2026"
TIMEOUT = 6000
ERRO_HTTP = re.compile(r"status of (\d{3})")
TEAL = "rgb(0, 150, 199)"
AZUL_BOOTSTRAP = "rgb(13, 202, 240)"


class Falha(Exception):
    pass


def _api(metodo, caminho, corpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(ALVO["api"] + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def semear():
    token = _api("POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    sufixo = uuid.uuid4().hex[:6]
    cursos = {}
    for chave, nome, preco in (("ativo", f"Analise de Dados {sufixo}", 250.0),
                               ("analise", f"Gestao Agil {sufixo}", 99.0),
                               ("livre", f"Excel Avancado {sufixo}", 120.0)):
        cid = f"d3_{chave}_{sufixo}"
        corpo = {"id": cid, "name": nome, "description": "Curso D3", "price": preco, "duration_hours": 8,
                 "level": "Intermediario", "target_audience": "Alunos", "objectives": ["o"], "topics": ["t"],
                 "benefits": ["b"], "faq": [{"question": "q", "answer": "a"}], "system_prompt": "p",
                 "materials": [{"title": "Apostila 1", "url": f"https://materiais.test/{cid}/1.pdf", "type": "pdf"},
                               {"title": "Apostila 2", "url": f"https://materiais.test/{cid}/2.pdf", "type": "pdf"}]}
        status, _ = _api("POST", "/api/admin/create-course", corpo, token)
        if status != 200:
            raise RuntimeError(f"seed: create-course {cid} HTTP {status}")
        cursos[chave] = {"id": cid, "nome": nome}
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.d3.{uuid.uuid4().hex[:8]}@teste.com"
    uid = Database.add_user(email, "Aluna D3", get_password_hash(SENHA), role="student")
    for chave, status_pg in (("ativo", "approved"), ("analise", "in_process")):
        ref = f"{cursos[chave]['id']}:d3:{uuid.uuid4().hex}"
        eid = Database.create_enrollment(uid, cursos[chave]["id"], ref)
        pid = Database.record_payment(eid, 100.0, "mercado_pago")
        if status_pg == "approved":
            Database.update_payment_status_by_reference(ref, "approved", "tx-d3")
        else:
            Database.update_payment_status(pid, status_pg)
    return email, cursos


@pytest.fixture(scope="module")
def servidores():
    with ambiente_isolado("d3") as ambiente:
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


def test_d3_ajustes_design_angular_e2e(servidores, browser):
    resultados, erros, contextos = [], [], []
    seed = {"ok": False, "erro": ""}
    try:
        email, cursos = semear()
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(largura=1366, altura=900):
        ctx = browser.new_context(viewport={"width": largura, "height": altura}, locale="pt-BR")
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros.append(f"{msg.text[:100]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        return page

    def entrar(page, usuario, senha, destino):
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(usuario)
        page.locator("input[name=password]").first.fill(senha)
        page.locator("button[type=submit]").first.click()
        try:
            page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login não levou a /{destino} (URL {page.url})")
        page.wait_for_load_state("networkidle")

    def estilo(loc, prop, estado_esperado="visible"):
        loc.first.wait_for(state=estado_esperado, timeout=TIMEOUT)
        return loc.first.evaluate(f"e => getComputedStyle(e).getPropertyValue('{prop}')").strip()

    def caminho(url):
        return "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("?")[0] if "://" in url else url

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

    estado = {}

    def aluno():
        if "aluno" not in estado:
            page = nova_pagina()
            entrar(page, email, SENHA, "student")
            estado["aluno"] = page
        page = estado["aluno"]
        if caminho(page.url) != "/student":
            page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        return page

    def gestao():
        if "gestao" not in estado:
            page = nova_pagina()
            entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
            estado["gestao"] = page
        return estado["gestao"]

    def card_ativo(page):
        return page.locator('[data-testid="curso-card"]').filter(has_text=cursos["ativo"]["nome"]).first

    # --- G1 logo ------------------------------------------------------------------------------------------
    def g1():
        anonimo = nova_pagina()
        anonimo.goto(ALVO["base"] + "/", wait_until="networkidle")
        if anonimo.locator('[data-testid="app-logo"]').first.get_attribute("href") != "/":
            raise Falha("sem login, o logo deveria levar a '/'")
        page = aluno()
        logo = page.locator('[data-testid="app-logo"]').first
        if logo.get_attribute("href") != "/student":
            raise Falha(f"aluno logado: href do logo = {logo.get_attribute('href')!r} (esperado /student)")
        logo.click()
        page.wait_for_timeout(600)
        if caminho(page.url) != "/student" or page.locator("input[name=password]").count():
            raise Falha(f"aluno logado: clicar no logo levou a {page.url} (esperado ficar em /student)")
        href = gestao().locator('[data-testid="app-logo"]').first.get_attribute("href")
        if href != "/admin":
            raise Falha(f"Gestão logada: href do logo = {href!r} (esperado /admin)")

    # --- G2 atalhos ---------------------------------------------------------------------------------------
    def g2():
        page = aluno()
        referencia = page.locator('[data-testid="atalho-cursos"]')
        for testid in ("atalho-catalogo", "atalho-perfil"):
            alvo = page.locator(f'[data-testid="{testid}"]')
            if estilo(alvo, "text-decoration-line") != "none":
                raise Falha(f"{testid} está sublinhado")
            for prop in ("border-top-color", "font-weight", "color", "border-radius"):
                if estilo(alvo, prop) != estilo(referencia, prop):
                    raise Falha(f"{testid}: {prop} = {estilo(alvo, prop)!r}, diferente do atalho Cursos "
                                f"({estilo(referencia, prop)!r})")

    # --- G3 avaliação -------------------------------------------------------------------------------------
    def g3():
        page = aluno()
        card = card_ativo(page)
        seletor = card.locator('[data-testid="curso-avaliacao-nota"]')
        selecionado = seletor.first.evaluate("s => s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : ''")
        if selecionado.strip() != "5 ★":
            raise Falha(f"sem avaliação, o seletor mostra {selecionado!r} (esperado '5 ★')")
        largura = card.locator('[data-testid="curso-avaliacao-comentario"]').first.evaluate(
            "e => e.getBoundingClientRect().width")
        if largura < 200:
            raise Falha(f"campo de comentário com {largura:.0f}px (esperado >= 200px)")
        seletor.first.select_option(label="4 ★")
        card.locator('[data-testid="curso-avaliacao-enviar"]').first.click()
        try:
            card.locator('[data-testid="curso-avaliacao-ok"]').first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("depois de enviar, nenhuma confirmação [data-testid=curso-avaliacao-ok]")
        page.reload(wait_until="networkidle")
        seletor = card_ativo(page).locator('[data-testid="curso-avaliacao-nota"]')
        selecionado = seletor.first.evaluate("s => s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : ''")
        if selecionado.strip() != "4 ★":
            raise Falha(f"com avaliação 4, ao recarregar o seletor mostra {selecionado!r}")

    # --- G4 aviso do chat ---------------------------------------------------------------------------------
    def g4():
        page = aluno()
        aviso = page.locator('[data-testid="chat-aviso-gravacao"]')
        borda = aviso.first.evaluate(
            "e => e.getBoundingClientRect().left - e.closest('.card').getBoundingClientRect().left"
            " + parseFloat(getComputedStyle(e).paddingLeft)")
        if borda < 12:
            raise Falha(f"aviso do chat a {borda:.0f}px da borda do cartão (esperado >= 12px)")

    # --- G5 catálogo --------------------------------------------------------------------------------------
    def g5():
        page = aluno()
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        page.locator('[data-testid="catalogo-card"]').first.wait_for(timeout=TIMEOUT)
        tag = page.locator(".gt-tag").first
        if tag.count() == 0 or "catálogo" not in tag.inner_text().lower():
            raise Falha("o catálogo não tem o rótulo de seção 'Catálogo'")
        card = page.locator('[data-testid="catalogo-card"]').filter(has_text=cursos["livre"]["nome"]).first
        icone = card.locator('[data-testid="catalogo-icone"]')
        if icone.count() != 1 or icone.first.inner_text().strip() != "EA":
            raise Falha("o cartão não mostra o ícone com as iniciais do curso ('EA')")
        preco = card.locator('[data-testid="catalogo-preco"]')
        if "Barlow Condensed" not in estilo(preco, "font-family") or estilo(preco, "color") != TEAL:
            raise Falha(f"preço em {estilo(preco, 'font-family')!r} / {estilo(preco, 'color')}")

    # --- G6 paleta ----------------------------------------------------------------------------------------
    def g6():
        page = aluno()
        barra = card_ativo(page).locator(".progress-bar")
        # Com 0% a barra tem largura zero (não "visível" para o Playwright): basta estar no DOM.
        cor = estilo(barra, "background-color", "attached")
        if cor != TEAL:
            raise Falha(f"barra de progresso com {cor} (esperado teal)")
        linha = page.locator("tbody tr").filter(has_text=cursos["analise"]["nome"])
        badge = linha.locator('[data-testid="pagamento-status"]')
        if badge.first.inner_text().strip() != "Em análise":
            raise Falha(f"status mostrado {badge.first.inner_text()!r}")
        if estilo(badge, "background-color") == AZUL_BOOTSTRAP:
            raise Falha("'Em análise' usa o azul padrão do Bootstrap (bg-info)")

    # --- G7 observabilidade -------------------------------------------------------------------------------
    def g7():
        page = gestao()
        page.locator("ul.nav-tabs button", has_text="Observabilidade de IA").first.click()
        custo = page.locator('[data-testid="obs-cost"]')
        custo.first.wait_for(timeout=TIMEOUT)
        texto = custo.first.inner_text().strip()
        if not re.fullmatch(r"US\$ \d+,\d{4}", texto):
            raise Falha(f"custo mostrado {texto!r} (esperado 'US$ 0,0000')")
        linhas = custo.first.evaluate("e => e.getClientRects().length")
        altura = custo.first.evaluate("e => e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight)")
        if linhas != 1 or altura > 1.5:
            raise Falha(f"o custo quebra em mais de uma linha (altura = {altura:.1f} linhas)")
        for testid in ("obs-resolution-rate", "obs-conversion"):
            valor = page.locator(f'[data-testid="{testid}"]').first.inner_text().strip()
            if not re.fullmatch(r"\d+,\d %", valor.replace(" ", " ")) and not re.fullmatch(r"\d+,\d%", valor):
                raise Falha(f"{testid} mostra {valor!r} (esperado vírgula decimal, ex.: 0,0%)")

    # --- G8 financeiro ------------------------------------------------------------------------------------
    def g8():
        page = gestao()
        page.locator("ul.nav-tabs button", has_text="Financeiro").first.click()
        page.wait_for_load_state("networkidle")
        linha = page.locator("tbody tr").filter(has_text=cursos["ativo"]["nome"])
        if linha.count() == 0:
            raise Falha("a tabela de transações não mostra o nome do curso")
        if page.locator("tbody td", has_text=re.compile(rf"^\s*{re.escape(cursos['ativo']['id'])}\s*$")).count():
            raise Falha("a tabela de transações ainda mostra o id do curso")

    # --- G10 abas no celular ------------------------------------------------------------------------------
    def g10():
        page = nova_pagina(390, 844)
        entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
        abas = page.locator("ul.nav-tabs .nav-link")
        topos = {round(abas.nth(i).evaluate("e => e.getBoundingClientRect().top")) for i in range(abas.count())}
        if len(topos) != 1:
            raise Falha(f"as abas ocupam {len(topos)} linhas no celular (esperado 1, com rolagem lateral)")
        if estilo(page.locator("ul.nav-tabs"), "overflow-x") not in ("auto", "scroll"):
            raise Falha("a lista de abas não rola na horizontal")
        larguras = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if larguras[0] > larguras[1] + 1:
            raise Falha("a página inteira rola na horizontal no celular")

    def g11():
        if erros:
            raise Falha(f"{len(erros)} erro(s): " + " | ".join(erros[:4]))

    cenario("G1", "logo leva à área do perfil logado", g1)
    cenario("G2", "atalhos de link iguais aos botões, sem sublinhado", g2)
    cenario("G3", "avaliação começa em 5, confirma o envio e lembra a nota", g3)
    cenario("G4", "aviso do chat com margem lateral", g4)
    cenario("G5", "catálogo com rótulo, ícone e preço no estilo da landing", g5)
    cenario("G6", "barra de progresso e 'Em análise' na paleta", g6)
    cenario("G7", "custo numa linha e números com vírgula", g7)
    cenario("G8", "financeiro mostra o nome do curso", g8)
    cenario("G10", "abas do painel numa linha no celular", g10)
    cenario("G11", "sem erros de console", g11)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass
    passou = sum(1 for r in resultados if r[2])
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
