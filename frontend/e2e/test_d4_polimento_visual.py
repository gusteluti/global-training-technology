"""E2E da D4 (D95) — polimento visual: landing sem os sinais de página genérica, acessibilidade e movimento pontual.

Contrato (D95), verificado por estilo COMPUTADO no Chromium:
Landing (servida estática, backend da F5b sem Angular):
  L1 nenhum rótulo em maiúsculas espaçadas (text-transform uppercase com letter-spacing >= 2 px) no conteúdo
  L2 o h1 não destaca uma palavra com outra cor; há um único h1 e os títulos de seção são h2
  L3 o hero mostra a planilha [data-testid=hero-planilha] com uma linha [data-testid=hero-planilha-linha] por curso
     do catálogo (nomes do backend) e o total de cursos
  L4 nenhum emoji no texto visível da página (ícones são SVG)
  L5 botões só com ícone têm aria-label (#chat-btn, .chat-send, .chat-close) e o campo do chat tem nome acessível
  L6 foco por teclado visível (outline com largura > 0) no botão "Ver todos os cursos"
  L7 nenhum link ou botão anima "all" (transition-property all com duração > 0; o padrão do navegador é all/0s)
  L8 movimento reduzido: o cursor da planilha não anima (animation-name none ou duração 0)
  L9 celular (390 px): sem rolagem horizontal; a planilha cabe na tela
  L10 resposta do chat entra com a revelação (.msg-revelar) e o texto completo já está no DOM
SPA Angular (harness isolado D58):
  S1 rótulo de área (.gt-tag) sem maiúsculas espaçadas nem versalete; texto continua "Área do funcionário"
  S2 KPIs do financeiro com a cor do texto (sem verde/vermelho no número) e algarismos tabulares
  S3 abas do painel: indicador [data-testid=abas-indicador] desliza até a aba clicada (mesma posição e largura)
  S4 foco por teclado visível nos botões (outline ou box-shadow)
  S5 .btn não anima "all"
  S6 movimento reduzido: o indicador das abas não tem transição
  S7 sem erros de console de /api nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_d4_polimento_visual.py -s
"""

import re
import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import ambiente_f5b, semear_cursos_f5b  # noqa: E402
from apoio_harness_h1 import ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
TEXTO = "rgb(23, 33, 43)"
ERRO_HTTP = re.compile(r"status of (\d{3})")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⌛⏳⭐]")


class Falha(Exception):
    pass


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _rodar(cenarios):
    resultados = []
    for codigo, nome, funcao in cenarios:
        try:
            funcao()
            resultados.append((codigo, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")
    falhas = [f"{c}: {m}" for c, ok, m in resultados if not ok]
    assert not falhas, f"{len(falhas)} de {len(resultados)} cenários falharam: " + " | ".join(falhas)


def _estilo(loc, prop):
    loc.first.wait_for(state="attached", timeout=TIMEOUT)
    return loc.first.evaluate(f"e => getComputedStyle(e).getPropertyValue('{prop}')").strip()


def _foco_visivel(page, loc):
    """Leva o foco ao elemento pelo teclado (Tab a partir do anterior) e devolve (outline-width, box-shadow)."""
    loc.first.wait_for(timeout=TIMEOUT)
    loc.first.evaluate("e => { const t = document.createElement('button'); t.id = '__ancora_foco';"
                       " t.style.cssText = 'position:absolute;opacity:0'; e.parentNode.insertBefore(t, e); t.focus(); }")
    page.keyboard.press("Tab")
    foco = page.evaluate("document.activeElement === document.querySelector('#__ancora_foco').nextElementSibling")
    if not foco:
        raise Falha("o Tab não levou o foco ao elemento esperado")
    largura = loc.first.evaluate("e => parseFloat(getComputedStyle(e).outlineWidth) || 0")
    estilo = loc.first.evaluate("e => getComputedStyle(e).outlineStyle")
    sombra = loc.first.evaluate("e => getComputedStyle(e).boxShadow")
    page.evaluate("document.querySelector('#__ancora_foco').remove()")
    return (largura if estilo != "none" else 0), sombra


# ------------------------------------------------------------------------------------------------- landing
@pytest.fixture(scope="module")
def landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("d4_landing", cors_origin=base, angular=False) as ambiente:
        dados = semear_cursos_f5b(ambiente["api"], ambiente["db_path"])
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, landing=base + "/landing_global_training.html", dados=dados)
        finally:
            estatico.shutdown()
            estatico.server_close()


def test_d4_landing(browser, landing):
    contextos = []

    def pagina(largura=1440, altura=900, movimento="no-preference"):
        ctx = browser.new_context(viewport={"width": largura, "height": altura}, reduced_motion=movimento)
        contextos.append(ctx)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        page = ctx.new_page()
        page.goto(landing["landing"], wait_until="networkidle")
        page.locator(".course-card").first.wait_for(timeout=TIMEOUT)
        return page

    principal = pagina()
    nomes = [landing["dados"]["omega"]["nome"], landing["dados"]["sigma"]["nome"]]

    def l1():
        achados = principal.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => {
            const s = getComputedStyle(e);
            return e.offsetParent !== null && e.innerText && e.innerText.trim() && s.textTransform === 'uppercase'
                   && (parseFloat(s.letterSpacing) || 0) >= 2;
        }).map(e => e.innerText.trim().slice(0, 30))""")
        if achados:
            raise Falha(f"rótulos em maiúsculas espaçadas: {achados[:4]}")

    def l2():
        if principal.locator("h1").count() != 1:
            raise Falha(f"{principal.locator('h1').count()} h1 na página (esperado 1)")
        cor_h1 = _estilo(principal.locator("h1"), "color")
        cores = principal.locator("h1 *").evaluate_all("els => els.map(e => getComputedStyle(e).color)")
        if any(c != cor_h1 for c in cores):
            raise Falha(f"o h1 destaca uma parte com outra cor ({set(cores)} vs {cor_h1})")
        titulos = principal.locator("h2").all_inner_texts()
        for esperado in ("Do interesse à matrícula em minutos", "Cursos com matrículas abertas"):
            if not any(esperado.lower() in t.lower() for t in titulos):
                raise Falha(f"o título {esperado!r} não é um h2 (h2 na página: {titulos})")

    def l3():
        planilha = principal.locator('[data-testid="hero-planilha"]')
        if not planilha.count() or not planilha.first.is_visible():
            raise Falha("o hero não mostra a planilha de cursos")
        linhas = planilha.locator('[data-testid="hero-planilha-linha"]').all_inner_texts()
        if len(linhas) != len(nomes) or not all(any(n in l for l in linhas) for n in nomes):
            raise Falha(f"linhas da planilha {linhas} (esperado uma por curso: {nomes})")
        total = planilha.locator('[data-testid="hero-planilha-total"]').inner_text()
        if str(len(nomes)) not in total:
            raise Falha(f"total da planilha {total!r} (esperado {len(nomes)} cursos)")

    def l4():
        texto = principal.locator("body").inner_text()
        achados = EMOJI.findall(texto)
        if achados:
            raise Falha(f"emojis no texto visível: {sorted(set(achados))}")
        principal.locator("#chat-btn").click()
        achados = EMOJI.findall(principal.locator("#chat-bubble").inner_text())
        principal.locator(".chat-close").click()
        if achados:
            raise Falha(f"emojis no chat: {sorted(set(achados))}")

    def l5():
        for seletor in ("#chat-btn", ".chat-send", ".chat-close"):
            rotulo = principal.locator(seletor).first.get_attribute("aria-label")
            if not rotulo or not rotulo.strip():
                raise Falha(f"{seletor} não tem aria-label")
        campo = principal.locator("#chat-input")
        if not (campo.get_attribute("aria-label") or principal.locator("label[for=chat-input]").count()):
            raise Falha("o campo do chat não tem nome acessível")

    def l6():
        largura, _ = _foco_visivel(principal, principal.locator(".hero .btn-primary"))
        if largura <= 0:
            raise Falha("o botão 'Ver todos os cursos' não mostra foco por teclado")

    def l7():
        animam_tudo = principal.evaluate("""() => [...document.querySelectorAll('a, button')]
            .filter(e => { const s = getComputedStyle(e);
                return s.transitionProperty.split(',').map(p => p.trim()).includes('all')
                       && s.transitionDuration.split(',').some(d => parseFloat(d) > 0); })
            .map(e => (e.className || e.id || e.tagName).toString().slice(0, 30))""")
        if animam_tudo:
            raise Falha(f"elementos com transition: all -> {sorted(set(animam_tudo))[:5]}")

    def l8():
        page = pagina(movimento="reduce")
        cursor = page.locator('[data-testid="hero-planilha-cursor"]')
        if not cursor.count():
            raise Falha("a planilha não tem o cursor de célula")
        nome = _estilo(cursor, "animation-name")
        duracao = _estilo(cursor, "animation-duration")
        if nome != "none" and duracao not in ("0s", "1e-05s", "0.00001s"):
            raise Falha(f"com movimento reduzido o cursor ainda anima ({nome}, {duracao})")

    def l9():
        page = pagina(390, 844)
        largura = page.evaluate("document.documentElement.scrollWidth")
        if largura > 390:
            raise Falha(f"rolagem horizontal no celular (scrollWidth {largura})")
        planilha = page.locator('[data-testid="hero-planilha"]')
        if not planilha.count():
            raise Falha("o hero não mostra a planilha de cursos")
        caixa = planilha.bounding_box()
        if not caixa or caixa["x"] < 0 or caixa["x"] + caixa["width"] > 390:
            raise Falha(f"a planilha não cabe na tela do celular ({caixa})")

    def l10():
        page = pagina()
        page.locator("#chat-btn").click()
        page.locator("#chat-input").fill("Quais cursos vocês têm?")
        page.locator("#chat-input").press("Enter")
        ultima = page.locator("#chat-messages .msg-bot").last
        page.wait_for_function("""() => { const m = [...document.querySelectorAll('#chat-messages .msg-bot')].pop();
            return m && !m.textContent.includes('Processando'); }""", timeout=TIMEOUT)
        if "msg-revelar" not in (ultima.get_attribute("class") or ""):
            raise Falha("a resposta do chat não entra com a revelação (.msg-revelar)")
        if len(ultima.inner_text().strip()) < 5:
            raise Falha("o texto da resposta não está completo no DOM")

    try:
        _rodar([
            ("L1", "sem rótulos em maiúsculas espaçadas", l1),
            ("L2", "h1 sem palavra colorida; títulos de seção em h2", l2),
            ("L3", "planilha do hero com os cursos do catálogo", l3),
            ("L4", "sem emojis no texto visível", l4),
            ("L5", "botões de ícone com aria-label", l5),
            ("L6", "foco visível por teclado", l6),
            ("L7", "nenhum transition: all", l7),
            ("L8", "movimento reduzido respeitado", l8),
            ("L9", "celular sem rolagem horizontal", l9),
            ("L10", "resposta do chat com revelação", l10),
        ])
    finally:
        for ctx in contextos:
            ctx.close()


# ----------------------------------------------------------------------------------------------------- SPA
@pytest.fixture(scope="module")
def spa():
    with ambiente_isolado("d4") as ambiente:
        yield ambiente


def test_d4_spa(browser, spa):
    contextos, erros = [], []

    def nova(movimento="no-preference", largura=1366):
        ctx = browser.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR", reduced_motion=movimento)
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros.append(f"{msg.text[:100]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        page.goto(spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(GESTAO_EMAIL)
        page.locator("input[name=password]").first.fill(GESTAO_SENHA)
        page.locator("button[type=submit]").first.click()
        page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
        page.wait_for_load_state("networkidle")
        return page

    page = nova()

    def s1():
        tag = page.locator(".gt-tag").first
        if "área do funcionário" not in tag.inner_text().lower():
            raise Falha(f"rótulo {tag.inner_text()!r}")
        transform, espaco, caps = (_estilo(tag, p) for p in ("text-transform", "letter-spacing", "font-variant-caps"))
        if transform == "uppercase" or caps != "normal" or (espaco != "normal" and float(espaco.rstrip("px")) >= 1):
            raise Falha(f"rótulo ainda em caixa alta espaçada ({transform}, {espaco}, {caps})")

    def s2():
        valores = page.locator('[data-testid="kpi-valor"]')
        valores.first.wait_for(timeout=TIMEOUT)
        if valores.count() < 4:
            raise Falha(f"{valores.count()} KPIs com data-testid=kpi-valor (esperado 4)")
        for i in range(valores.count()):
            cor = valores.nth(i).evaluate("e => getComputedStyle(e).color")
            num = valores.nth(i).evaluate("e => getComputedStyle(e).fontVariantNumeric")
            if cor != TEXTO:
                raise Falha(f"KPI {i} na cor {cor} (esperado a cor do texto {TEXTO})")
            if "tabular-nums" not in num:
                raise Falha(f"KPI {i} sem algarismos tabulares ({num})")

    def s3():
        indicador = page.locator('[data-testid="abas-indicador"]')
        if not indicador.count():
            raise Falha("as abas não têm o indicador deslizante")
        abas = page.locator(".nav-tabs .nav-link")
        alvo = abas.nth(2)
        alvo.click()
        page.wait_for_timeout(700)
        a = alvo.bounding_box()
        b = indicador.first.bounding_box()
        if not a or not b or abs(a["x"] - b["x"]) > 2 or abs(a["width"] - b["width"]) > 2:
            raise Falha(f"indicador em {b} e aba ativa em {a}")
        abas.nth(0).click()
        page.wait_for_timeout(700)

    def s4():
        largura, sombra = _foco_visivel(page, page.locator(".nav-tabs .nav-link").nth(1))
        if largura <= 0 and (not sombra or sombra == "none"):
            raise Falha("a aba não mostra foco por teclado")

    def s5():
        botao = page.locator(".btn").first
        duracoes = [float(d.strip().rstrip("s")) for d in _estilo(botao, "transition-duration").split(",")]
        if "all" in [p.strip() for p in _estilo(botao, "transition-property").split(",")] and max(duracoes) > 0:
            raise Falha(".btn ainda usa transition: all")

    def s6():
        reduzida = nova(movimento="reduce")
        duracao = _estilo(reduzida.locator('[data-testid="abas-indicador"]'), "transition-duration")
        if any(float(d.strip().rstrip("s")) > 0.001 for d in duracao.split(",")):
            raise Falha(f"com movimento reduzido o indicador ainda tem transição ({duracao})")

    def s7():
        if erros:
            raise Falha(f"erros: {erros[:3]}")

    try:
        _rodar([
            ("S1", "rótulo de área sem caixa alta espaçada", s1),
            ("S2", "KPIs na cor do texto, algarismos tabulares", s2),
            ("S3", "indicador das abas desliza até a aba ativa", s3),
            ("S4", "foco visível por teclado", s4),
            ("S5", ".btn sem transition: all", s5),
            ("S6", "movimento reduzido respeitado", s6),
            ("S7", "sem erros de console", s7),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
