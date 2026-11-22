"""E2E da DS0 (D115, docs/tdd/PLANO_DESIGN.md) — fundação do design: logo oficial, contraste AA dos tokens, fonte mínima.

Regra da D115: só design. Nenhuma rota, contrato, texto de fluxo, data-testid ou href muda; o que muda é o visual.
Tudo é verificado pelo estilo COMPUTADO no Chromium (helper `apoio_contraste.py`, reutilizável nas DS1 a DS5).

test_ds0_apoio_contraste (sem servidor; valida o próprio helper numa página sintética, passa no red):
  A1 #0096c7 sobre branco em texto de 16 px é falha (3,39:1); #0077a3 passa (5,04:1)
  A2 texto grande (>= 24 px, ou >= 18,66 px com peso >= 700) usa o mínimo de 3:1
  A3 fundo herdado com alfa é composto; aria-hidden e invisível ficam de fora; gradiente e desabilitado vão para
     `ignorados`; `dentro_de` limita a varredura
  A4 fontes_abaixo_de acha texto de 13 px e ignora 14 px

test_ds0_fundacao (harness isolado D58; 1366 x 900, movimento reduzido):
  F1 logo oficial na barra: [data-testid=app-logo] contém um <img> com alt "Global Training Technology", src com
     "assets/brand/gtt-logo-fundo-escuro" (.png ou .webp), imagem carregada (naturalWidth > 0) e altura renderizada
     entre 40 e 64 px; o href do logo sem login continua "/" (D93)
  F2 o disco "GT" desenhado em CSS saiu: nenhum .gt-logo-circle no DOM (login e /admin)
  F3 --gt-muted e .text-muted com contraste >= 4,5:1 sobre #ffffff e #f7f9fb (guarda: já passa hoje, 5,03 e 4,77)
  F4 cor de link (elemento <a> comum e --bs-link-color) >= 4,5:1 sobre #ffffff e #f7f9fb
  F5 botão primário (.btn-primary "Entrar"): texto branco sobre o fundo do botão >= 4,5:1
  F6 botão de contorno (.btn-outline-primary "Criar conta e matricular-se"): texto >= 4,5:1 sobre o fundo efetivo
  F7 /login: varredura completa de contraste AA sem falhas
  F8 /cadastro (aceite marcado, para o botão "Criar conta" ficar ativo e entrar na conta): varredura completa sem falhas
  F9 /esqueci-senha: varredura completa sem falhas
  F10 nas três telas anônimas, nenhum texto que não seja grande usa a cor #0096c7 = rgb(0, 150, 199)
  F11 nas três telas anônimas (inclui barra superior e rodapé), nenhum texto visível abaixo de 14 px
  F12 /admin (Gestão): contraste AA nos seletores que a DS0 controla (barra superior, links de conteúdo, .btn-primary,
      .btn-outline-primary, .btn-link, .text-muted, .gt-tag, abas .nav-tabs .nav-link) e nenhum texto pequeno em #0096c7
  F13 /student (aluno com matrícula ativa): mesma verificação de F12
  F14 sem erros de console de /api nem exceções de página

O restante das telas /admin e /student (cartões, tabelas, chat) é da DS2/DS3 e não é varrido aqui.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds0_fundacao_angular.py -s
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

from apoio_contraste import descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
TEAL = "rgb(0, 150, 199)"
BRANCO = "rgb(255, 255, 255)"
FUNDO_SUAVE = "rgb(247, 249, 251)"
SENHA_ALUNO = "senha-aluno-ds0-2026"
LOGO_SRC = re.compile(r"assets/brand/gtt-logo-fundo-escuro\.(png|webp)(\?.*)?$")
ALT_LOGO = "Global Training Technology"
TELAS_ANONIMAS = ("/login", "/cadastro", "/esqueci-senha")

# Seletores que a DS0 controla nas telas logadas (D115 / pedido da DS0). O resto da tela é DS2/DS3.
SELETORES_DS0 = (
    '[data-testid="app-nav"]',
    "main a:not(.btn)",
    ".btn-primary",
    ".btn-outline-primary",
    ".btn-link",
    ".text-muted",
    ".gt-tag",
    ".nav-tabs .nav-link",
)

# Texto em #0096c7 que não é grande (o JS devolve os elementos visíveis com texto próprio nessa cor).
_JS_TEAL_PEQUENO = r"""
(args) => {
  const achados = [];
  const base = document.querySelector('body');
  for (const el of [base, ...base.querySelectorAll('*')]) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION'].includes(el.tagName)) continue;
    if (el.closest('[aria-hidden="true"]') || el.closest('svg')) continue;
    let t = '';
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent;
    t = t.replace(/\s+/g, ' ').trim();
    if (!t) continue;
    if (args.dentroDe.length && !args.dentroDe.some(s => el.closest(s))) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.visibility !== 'visible' || r.width <= 1 || r.height <= 1) continue;
    const tam = parseFloat(cs.fontSize), peso = parseInt(cs.fontWeight, 10) || 400;
    const grande = tam >= 24 || (tam >= 18.66 && peso >= 700);
    if (cs.color === args.teal && !grande) achados.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} '${t.slice(0, 40)}' ${tam}px`);
  }
  return achados;
}
"""


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
    print(f"\nRESULTADO: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, f"{len(falhas)} de {len(resultados)} cenários falharam: " + " | ".join(falhas)


# --------------------------------------------------------------------------------------- helper (sem servidor)
PAGINA_SINTETICA = """<!doctype html><html><body style="margin:0;background:#ffffff;font-family:sans-serif">
<p id="teal" style="color:#0096c7;font-size:16px">Texto teal pequeno</p>
<p id="escuro" style="color:#0077a3;font-size:16px">Texto azul escuro</p>
<p id="teal-grande" style="color:#0096c7;font-size:24px">Texto teal grande</p>
<p id="teal-negrito" style="color:#0096c7;font-size:19px;font-weight:700">Teal negrito 19px</p>
<p id="teal-19-normal" style="color:#0096c7;font-size:19px;font-weight:400">Teal 19px normal</p>
<div style="background:rgba(0,0,0,0.5)"><span id="alfa" style="color:#555555;font-size:16px">Sobre preto 50%</span></div>
<p aria-hidden="true" style="color:#eeeeee">Escondido de leitor</p>
<p style="color:#eeeeee;display:none">Invisivel</p>
<div style="background-image:linear-gradient(#000,#fff)"><span id="grad" style="color:#ffffff">Sobre gradiente</span></div>
<button disabled style="color:#dddddd;background:#ffffff">Desabilitado</button>
<div class="area"><span id="dentro" style="color:#0096c7">Dentro da area</span></div>
<p id="pequeno" style="font-size:13px;color:#000">Treze pixels</p>
<p id="catorze" style="font-size:14px;color:#000">Catorze pixels</p>
<input value="valor do campo" style="color:#eeeeee" placeholder="dica">
</body></html>"""


def test_ds0_apoio_contraste(browser):
    ctx = browser.new_context(viewport={"width": 1000, "height": 900})
    page = ctx.new_page()
    page.set_content(PAGINA_SINTETICA)
    try:
        resultado = varrer_contraste(page)
        textos = {f["texto"]: f for f in resultado["falhas"]}
        ignorados = {i["texto"]: i["motivo"] for i in resultado["ignorados"]}

        def a1():
            if "Texto teal pequeno" not in textos:
                raise Falha("#0096c7 a 16 px sobre branco não foi apontado")
            if abs(textos["Texto teal pequeno"]["razao"] - 3.39) > 0.02:
                raise Falha(f"razão calculada {textos['Texto teal pequeno']['razao']} (esperado 3,39)")
            if "Texto azul escuro" in textos:
                raise Falha("#0077a3 sobre branco foi apontado como falha")
            if abs(razao_contraste("#0077a3", BRANCO) - 5.04) > 0.02:
                raise Falha("razao_contraste do Python diverge do esperado (5,04)")

        def a2():
            for texto in ("Texto teal grande", "Teal negrito 19px"):
                if texto in textos:
                    raise Falha(f"{texto!r} é texto grande (mínimo 3:1) e foi apontado")
            if "Teal 19px normal" not in textos:
                raise Falha("19 px com peso 400 não é texto grande e deveria falhar")

        def a3():
            if "Sobre preto 50%" not in textos or textos["Sobre preto 50%"]["fundo"] != "rgb(128, 128, 128)":
                raise Falha(f"fundo com alfa não composto: {textos.get('Sobre preto 50%')}")
            for texto in ("Escondido de leitor", "Invisivel", "valor do campo", "dica"):
                if texto in textos or texto in ignorados:
                    raise Falha(f"{texto!r} deveria ficar de fora da varredura")
            if "gradiente" not in ignorados.get("Sobre gradiente", ""):
                raise Falha("texto sobre gradiente não foi para ignorados")
            if ignorados.get("Desabilitado") != "desabilitado":
                raise Falha("botão desabilitado não foi para ignorados")
            restrito = varrer_contraste(page, dentro_de=[".area"])
            if [f["texto"] for f in restrito["falhas"]] != ["Dentro da area"] or restrito["verificados"] != 1:
                raise Falha(f"dentro_de não limitou a varredura: {restrito}")

        def a4():
            abaixo = [i["texto"] for i in fontes_abaixo_de(page, 14)]
            if "Treze pixels" not in abaixo or "Catorze pixels" in abaixo:
                raise Falha(f"fontes_abaixo_de devolveu {abaixo}")

        _rodar([
            ("A1", "teal pequeno falha, azul escuro passa", a1),
            ("A2", "texto grande usa 3:1", a2),
            ("A3", "alfa composto, exclusões e ignorados", a3),
            ("A4", "fonte mínima", a4),
        ])
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------- SPA
def _api(api, metodo, caminho, corpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def _semear_aluno(ambiente):
    """Aluno com uma matrícula ativa (pagamento aprovado) num curso com material, como no seed da D2/D3."""
    token = _api(ambiente["api"], "POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    cid = f"ds0_{uuid.uuid4().hex[:8]}"
    corpo = {"id": cid, "name": f"Curso DS0 {cid[-6:]}", "description": "Curso DS0", "price": 150.0,
             "duration_hours": 8, "level": "Basico", "target_audience": "Alunos", "objectives": ["o"],
             "topics": ["t"], "benefits": ["b"], "faq": [{"question": "q", "answer": "a"}], "system_prompt": "p",
             "materials": [{"title": "Apostila DS0", "url": f"https://materiais.test/{cid}/1.pdf", "type": "pdf"}]}
    status, _ = _api(ambiente["api"], "POST", "/api/admin/create-course", corpo, token)
    if status != 200:
        raise RuntimeError(f"seed: create-course HTTP {status}")
    Database = abrir_banco(ambiente["db_path"])
    from core.security import get_password_hash

    email = f"e2e.ds0.{uuid.uuid4().hex[:8]}@teste.com"
    uid = Database.add_user(email, "Aluna DS0", get_password_hash(SENHA_ALUNO), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    ref = f"{cid}:ds0:{uuid.uuid4().hex}"
    eid = Database.create_enrollment(uid, cid, ref)
    Database.record_payment(eid, 150.0, "mercado_pago")
    Database.update_payment_status_by_reference(ref, "approved", "tx-ds0")
    return email


@pytest.fixture(scope="module")
def spa():
    with ambiente_isolado("ds0") as ambiente:
        yield ambiente


def test_ds0_fundacao(browser, spa):
    contextos, erros, paginas = [], [], {}
    seed = {}

    def nova():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR", reduced_motion="reduce")
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros.append(f"{msg.text[:100]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        return page

    def anonima(rota):
        if rota not in paginas:
            page = nova()
            page.goto(spa["base"] + rota, wait_until="networkidle")
            page.locator("main .card").first.wait_for(timeout=TIMEOUT)
            if rota == "/cadastro":
                page.locator('[data-testid="cadastro-aceite"]').check()
            paginas[rota] = page
        return paginas[rota]

    def logada(chave, email, senha, destino):
        if chave not in paginas:
            page = nova()
            page.goto(spa["base"] + "/", wait_until="networkidle")
            page.locator("input[name=email]").first.fill(email)
            page.locator("input[name=password]").first.fill(senha)
            page.locator("button[type=submit]").first.click()
            try:
                page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 2)
            except sync_api.TimeoutError:
                raise Falha(f"login não levou a /{destino} (URL {page.url})")
            page.wait_for_load_state("networkidle")
            page.locator("main .card").first.wait_for(timeout=TIMEOUT)
            paginas[chave] = page
        return paginas[chave]

    def gestao():
        return logada("gestao", GESTAO_EMAIL, GESTAO_SENHA, "admin")

    def aluno():
        if "email" not in seed:
            seed["email"] = _semear_aluno(spa)
        return logada("aluno", seed["email"], SENHA_ALUNO, "student")

    def cor_resolvida(page, css_cor, dentro="main .card-body"):
        """Resolve uma cor CSS (pode ser var(--x)) para rgb(...) num elemento temporário."""
        return page.evaluate(
            "([cor, dentro]) => { const pai = document.querySelector(dentro) || document.body;"
            " const s = document.createElement('span'); s.style.color = cor; pai.appendChild(s);"
            " const c = getComputedStyle(s).color; s.remove(); return c; }", [css_cor, dentro])

    def exigir_varredura(page, rotulo, dentro_de=None, minimo_verificados=3):
        resultado = varrer_contraste(page, dentro_de=dentro_de)
        if resultado["ignorados"]:
            print(f"   [info] {rotulo}: ignorados -> {descrever(resultado['ignorados'])}")
        if resultado["verificados"] < minimo_verificados:
            raise Falha(f"{rotulo}: só {resultado['verificados']} textos verificados (esperado >= {minimo_verificados})")
        if resultado["falhas"]:
            raise Falha(f"{rotulo}: {len(resultado['falhas'])} texto(s) abaixo do AA: {descrever(resultado['falhas'])}")

    # --- F1/F2 logo --------------------------------------------------------------------------------------
    def f1():
        page = anonima("/login")
        logo = page.locator('[data-testid="app-logo"]')
        if logo.count() != 1:
            raise Falha(f"{logo.count()} [data-testid=app-logo] na barra (esperado 1)")
        if page.locator('[data-testid="app-nav"] [data-testid="app-logo"]').count() != 1:
            raise Falha("o logo não está dentro da barra superior [data-testid=app-nav]")
        img = logo.locator("img")
        if img.count() != 1:
            raise Falha(f"o logo tem {img.count()} <img> (esperado 1, o arquivo oficial)")
        alt = img.first.get_attribute("alt")
        if alt != ALT_LOGO:
            raise Falha(f"alt do logo {alt!r} (esperado {ALT_LOGO!r})")
        src = img.first.evaluate("e => e.currentSrc || e.src")
        if not LOGO_SRC.search(src or ""):
            raise Falha(f"src do logo {src!r} (esperado assets/brand/gtt-logo-fundo-escuro.png ou .webp)")
        try:
            page.wait_for_function("e => e.complete && e.naturalWidth > 0", arg=img.first.element_handle(),
                                   timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"a imagem do logo não carregou (naturalWidth = 0, src {src!r})")
        altura = img.first.evaluate("e => e.getBoundingClientRect().height")
        if not 40 <= altura <= 64:
            raise Falha(f"logo com {altura:.0f}px de altura a 1366px (esperado entre 40 e 64)")
        if logo.first.get_attribute("href") != "/":
            raise Falha(f"href do logo sem login mudou para {logo.first.get_attribute('href')!r} (D93: '/')")

    def f2():
        for rotulo, page in (("login", anonima("/login")), ("/admin", gestao())):
            if page.locator(".gt-logo-circle").count():
                raise Falha(f"{rotulo}: o disco 'GT' em CSS (.gt-logo-circle) ainda está no DOM")

    # --- F3 a F6 tokens ----------------------------------------------------------------------------------
    def f3():
        page = anonima("/login")
        for rotulo, css in (("--gt-muted", "var(--gt-muted)"),):
            cor = cor_resolvida(page, css)
            for fundo in (BRANCO, FUNDO_SUAVE):
                r = razao_contraste(cor, fundo)
                if r < 4.5:
                    raise Falha(f"{rotulo} = {cor} sobre {fundo}: {r:.2f}:1 (mínimo 4,5:1)")
        muted = page.locator(".text-muted").first
        cor = muted.evaluate("e => getComputedStyle(e).color")
        for fundo in (BRANCO, FUNDO_SUAVE):
            r = razao_contraste(cor, fundo)
            if r < 4.5:
                raise Falha(f".text-muted = {cor} sobre {fundo}: {r:.2f}:1 (mínimo 4,5:1)")

    def f4():
        page = anonima("/login")
        cores = {
            "<a> comum": page.evaluate(
                "() => { const pai = document.querySelector('main .card-body'); const a = document.createElement('a');"
                " a.href = '#ds0'; a.textContent = 'x'; pai.appendChild(a); const c = getComputedStyle(a).color;"
                " a.remove(); return c; }"),
            "--bs-link-color": cor_resolvida(page, "var(--bs-link-color)"),
        }
        for rotulo, cor in cores.items():
            for fundo in (BRANCO, FUNDO_SUAVE):
                r = razao_contraste(cor, fundo)
                if r < 4.5:
                    raise Falha(f"cor de link ({rotulo}) = {cor} sobre {fundo}: {r:.2f}:1 (mínimo 4,5:1)")

    def f5():
        page = anonima("/login")
        botao = page.locator("button.btn-primary[type=submit]").first
        botao.wait_for(timeout=TIMEOUT)
        fundo = botao.evaluate("e => getComputedStyle(e).backgroundColor")
        cor = botao.evaluate("e => getComputedStyle(e).color")
        if cor != BRANCO:
            raise Falha(f"texto do botão primário {cor} (esperado branco)")
        r = razao_contraste(cor, fundo)
        if r < 4.5:
            raise Falha(f"botão primário: branco sobre {fundo} = {r:.2f}:1 (mínimo 4,5:1)")

    def f6():
        page = anonima("/login")
        botao = page.locator(".btn-outline-primary").first
        botao.wait_for(timeout=TIMEOUT)
        resultado = varrer_contraste(page, dentro_de=[".btn-outline-primary"])
        if resultado["verificados"] < 1:
            raise Falha(".btn-outline-primary não teve texto verificado")
        if resultado["falhas"]:
            raise Falha(f"botão de contorno abaixo do AA: {descrever(resultado['falhas'])}")

    # --- F7 a F11 telas anônimas -------------------------------------------------------------------------
    def varredura_completa(rota):
        def cenario():
            exigir_varredura(anonima(rota), rota)
        return cenario

    def f10():
        achados = []
        for rota in TELAS_ANONIMAS:
            for item in anonima(rota).evaluate(_JS_TEAL_PEQUENO, {"teal": TEAL, "dentroDe": []}):
                achados.append(f"{rota}: {item}")
        if achados:
            raise Falha(f"{len(achados)} texto(s) não grande(s) em #0096c7: " + "; ".join(achados[:6]))

    def f11():
        achados = []
        for rota in TELAS_ANONIMAS:
            for item in fontes_abaixo_de(anonima(rota), 14):
                achados.append(f"{rota}: {descrever([item], 1)}")
        if achados:
            raise Falha(f"{len(achados)} texto(s) abaixo de 14 px: " + "; ".join(achados[:8]))

    # --- F12/F13 telas logadas (só seletores da DS0) -----------------------------------------------------
    def logada_ds0(obter, rotulo):
        def cenario():
            page = obter()
            exigir_varredura(page, rotulo, dentro_de=SELETORES_DS0)
            teal = page.evaluate(_JS_TEAL_PEQUENO, {"teal": TEAL, "dentroDe": list(SELETORES_DS0)})
            if teal:
                raise Falha(f"{rotulo}: {len(teal)} texto(s) pequeno(s) em #0096c7: " + "; ".join(teal[:6]))
        return cenario

    def f14():
        if erros:
            raise Falha(f"{len(erros)} erro(s): " + " | ".join(erros[:4]))

    try:
        _rodar([
            ("F1", "logo oficial (img, alt, arquivo da marca, 40-64 px) na barra", f1),
            ("F2", "disco 'GT' em CSS removido", f2),
            ("F3", "--gt-muted e .text-muted >= 4,5:1", f3),
            ("F4", "cor de link >= 4,5:1", f4),
            ("F5", "botão primário com texto branco >= 4,5:1", f5),
            ("F6", "botão de contorno >= 4,5:1", f6),
            ("F7", "/login sem texto abaixo do AA", varredura_completa("/login")),
            ("F8", "/cadastro sem texto abaixo do AA", varredura_completa("/cadastro")),
            ("F9", "/esqueci-senha sem texto abaixo do AA", varredura_completa("/esqueci-senha")),
            ("F10", "nenhum texto pequeno em #0096c7 nas telas anônimas", f10),
            ("F11", "nenhum texto abaixo de 14 px nas telas anônimas", f11),
            ("F12", "/admin: seletores da DS0 no AA", logada_ds0(gestao, "/admin")),
            ("F13", "/student: seletores da DS0 no AA", logada_ds0(aluno, "/student")),
            ("F14", "sem erros de console", f14),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
