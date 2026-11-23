"""E2E da DS4 (D115, docs/tdd/PLANO_DESIGN.md seção DS4 e "Decisões resolvidas") — landing como catálogo que converte.

Regra (D115, D-B, D-C, D-D, D-E, D-F): só design e conteúdo de vitrine. O script inline não muda (guarda estática em
`test_ds4_script_inalterado.py`); nenhuma funcionalidade nova (sem filtros no catálogo) e nenhum campo novo da API (o
cartão mostra só nome, tipo, nível e preço). Os e2e antigos da landing (D4 L1–L10, D3, E6, F5b, F6, GR2, GR3, SG4)
continuam valendo; a D4 já cobre emojis (L4), movimento reduzido (L8) e a planilha no hero (L3, L9).

Harness: o da D4 (`ambiente_f5b(..., angular=False)` + `semear_cursos_f5b`: Omega Analytics R$ 300 e Sigma Design
R$ 150, nível "Basico"), landing servida por `_servidor_da_landing` da E6 (só o HTML: imagem tem de vir embutida como
`data:` URI), fontes do Google cortadas. Medidas a 1440 x 900 e a 390 x 844, sobre o estilo COMPUTADO no Chromium.

Contrato de marcação usado pelo teste (já existe hoje, o dev mantém):
  barra = nav[aria-label="Principal"]; rodapé = footer; hero = o ancestral mais próximo do h1 com fundo opaco;
  cartão = .course-card dentro de #cursos, com h3, .course-price, .btn-enroll e .btn-contact; chat = #chat-*.

Cenários (cada um lista TODAS as violações, nas duas larguras quando faz sentido):
  G1  logo oficial na barra e no rodapé: <img alt="Global Training Technology">, src data:image/webp|png com os bytes de
      um arquivo de frontend/src/assets/brand/ (variante de fundo escuro sobre fundo escuro, de fundo claro sobre
      claro), carregado (naturalWidth > 0); altura 44–64 px na barra a 1440; nenhum .logo-circle nem disco "GT" na
      barra ou no rodapé
  G2  barra: "Área do aluno" (goToStudentArea) visível nas duas larguras; "Área do funcionário" fora da barra e no
      rodapé com onclick goToStaffArea(event) (D-E); links para #cursos, #duvidas e para a seção de "Do interesse à
      matrícula em minutos" na barra a 1440, cada um >= 44 x 44 px; a 390 nada da barra passa da tela
  G3  topo escuro: o hero tem background-color rgb(33, 40, 48), sem background-image no caminho do h1 até ele; h1
      branco rgb(255, 255, 255) com "Aprenda as ferramentas que o mercado cobra."
  G4  laranja só na conversão (D-B): "Ver cursos abertos" no hero e todo .btn-enroll com fundo rgb(255, 122, 24) e
      texto rgb(23, 33, 43); "Tirar dúvidas no chat" e .btn-contact sem laranja; nenhum outro elemento visível com
      fundo laranja nem texto laranja (inclusive com o chat aberto e uma resposta)
  G5  garantias no lugar dos números (D-C): "10k+", "500+", "100%", "alunos formados", "empresas parceiras", "de
      aprovação" e "Certificado reconhecido pelo mercado" fora da página; no hero, uma lista (li) com "Certificado de
      conclusão", "Pagamento pelo Mercado Pago" e "Cancelamento em até 7 dias"
  G6  catálogo: o primeiro h2 depois do h1 é o de #cursos, que vem antes de "Do interesse à matrícula em minutos";
      um cartão por curso da API com h3 = nome, o tipo e o nível que o script já monta, preço "R$ x,yy" em
      .course-price com tabular-nums e cor rgb(23, 33, 43) ou rgb(0, 119, 163), "Matricular agora" e "Tirar dúvidas
      com IA"; borda rgb(216, 224, 232) nos quatro lados e sem sombra pesada (none, ou cada camada com alfa <= 0,10 e
      desfoque <= 16 px)
  G7  #duvidas com h2 e >= 4 perguntas (summary, dt, h3 ou h4 terminando em "?") com resposta; quatro temas em itens
      distintos, fiéis a backend/knowledge: cancelamento ("7 dias" e "aprovação do pagamento"), acesso aos materiais
      ("aprovação do pagamento"), pagamento ("Mercado Pago"), certificado ("certificado" e "conclu…")
  G8  bloco para empresas: uma section/aside com "turmas fechadas" e "empresa", com um botão (onclick toggleChat())
      secundário (sem laranja) que abre o chat; nenhum número nem link de WhatsApp/telefone na página
  G9  faixa final: a última section antes do rodapé (distinta de #cursos, #duvidas e do bloco de empresas) tem um h2 e
      um a[href="#cursos"] que leva a #cursos
  G10 contraste AA com o scanner completo (apoio_contraste, sem filtro), a 1440 e 390, em três estados: página (com as
      respostas das dúvidas abertas), chat aberto e chat com uma resposta (ações de matrícula e feedback); nenhum item
      ignorado (gradiente, opacidade ou cor não lida); só "desabilitado" é aceito
  G11 nenhum texto visível com menos de 14 px nos mesmos estados (inclui rodapé, planilha e chat)
  G12 um único h1 visível nas duas larguras; h2 "Cursos com matrículas abertas" e "Do interesse à matrícula em minutos"
  G13 alvos >= 44 x 44 px nos mesmos estados: todo button visível, links da barra e do rodapé, links do chat,
      a[href="#cursos"]
  G14 390 px sem rolagem horizontal (scrollWidth <= 390 e nenhum elemento passando da borda fora de um contêiner com
      rolagem própria; overflow-x hidden no body não conta como contêiner), com e sem o chat aberto
  G15 foco por teclado visível (outline > 0 ou box-shadow) no link #cursos da barra, em "Área do funcionário" no rodapé,
      no primeiro .btn-enroll, no botão do bloco de empresas e no link da faixa final
  K1  sem exceções de página nem erros 4xx/5xx no console

Escolhas do agente-testes (modo autônomo D40), todas conservadoras:
  - O fundo do hero é exigido sólido: a grade, se houver, fica num pseudo-elemento ou elemento aria-hidden fora do
    caminho do texto (o scanner não pode ignorar nenhum texto do hero por gradiente).
  - O botão da faixa final não pode ser laranja (o pedido lista só o CTA do hero e o .btn-enroll; D-B libera o laranja
    "só para o botão principal de matrícula").
  - A 390 os links de seção da barra podem ficar ocultos (menu por CSS), mas o que estiver visível precisa ter 44 px e
    caber na tela; "Área do aluno" fica visível. Um menu com JavaScript seria script novo (proibido pela D-F).
  - O avatar "GT" do cabeçalho do chat (aria-hidden) não é cobrado: o pedido fala do logo na barra e no rodapé.
  - Emojis dos botões de feedback do chat (👍/👎) não são cobrados aqui: estão numa string do script, fora das templates
    (mudar seria mexer no script); a D4 L4 mede a página e o chat sem resposta.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds4_landing.py -s
"""

import base64
import itertools
import json
import re
import sys
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_contraste import _lum, _rgb, descrever, fontes_abaixo_de, varrer_contraste  # noqa: E402
from apoio_harness_f5b import ambiente_f5b, semear_cursos_f5b  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
LARGURAS = ((1440, 900), (390, 844))
ERRO_HTTP = re.compile(r"status of (\d{3})")
BRAND = E2E_DIR.parent / "src" / "assets" / "brand"
ALT_LOGO = "Global Training Technology"
ESCURO = "rgb(33, 40, 48)"
BRANCO = "rgb(255, 255, 255)"
LARANJA = "rgb(255, 122, 24)"
TEXTO = "rgb(23, 33, 43)"
LINK = "rgb(0, 119, 163)"
BORDA = "rgb(216, 224, 232)"
H1_TEXTO = "Aprenda as ferramentas que o mercado cobra."
H2_CURSOS = "Cursos com matrículas abertas"
H2_PASSOS = "Do interesse à matrícula em minutos"
SEL_BARRA = 'nav[aria-label="Principal"]'
PROIBIDOS = ("10k+", "500+", "100%", "alunos formados", "empresas parceiras", "de aprovação",
             "Certificado reconhecido pelo mercado")
GARANTIAS = ("Certificado de conclusão", "Pagamento pelo Mercado Pago", "Cancelamento em até 7 dias")
PERGUNTA_OMEGA = "Quais sao as turmas e as datas de Omega Analytics?"
ALVO_MIN = 44.0


class Falha(Exception):
    pass


def _norm(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _logos_oficiais():
    variantes = {}
    for nome in ("gtt-logo-fundo-escuro.webp", "gtt-logo-fundo-escuro.png",
                 "gtt-logo-fundo-claro.webp", "gtt-logo-fundo-claro.png"):
        arquivo = BRAND / nome
        if arquivo.exists():
            variantes[arquivo.read_bytes()] = "escuro" if "escuro" in nome else "claro"
    return variantes


# ------------------------------------------------------------------------------------------------- medição (JS)
_JS_BASE = r"""
const DS4_APOIO = true;  // começa com const: o Playwright avalia a expressão e chama a função do fim
function visivel(el) {
  if (!el || el.closest('[aria-hidden="true"]')) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility !== 'visible' || cs.display === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  return el.getClientRects().length > 0;
}
function desc(el) {
  let s = el.tagName.toLowerCase();
  const tid = el.getAttribute('data-testid');
  if (tid) s += `[data-testid=${tid}]`;
  else if (el.id) s += '#' + el.id;
  else if (el.classList.length) s += '.' + Array.from(el.classList).slice(0, 3).join('.');
  return s;
}
function txt(el) { return (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim(); }
function textoProprio(el) {
  let t = '';
  for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent;
  return t.replace(/\s+/g, ' ').trim();
}
function heroDe() {
  const h1 = document.querySelector('h1');
  if (!h1) return null;
  for (let a = h1; a && a.nodeType === 1; a = a.parentElement) {
    const m = getComputedStyle(a).backgroundColor.match(/rgba?\(([^)]+)\)/);
    if (!m) continue;
    const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat);
    if ((p[3] ?? 1) >= 1) return a;
  }
  return null;
}
"""

_JS_LOGOS = _JS_BASE + r"""
(sel) => {
  const raiz = document.querySelector(sel);
  if (!raiz) return null;
  const imgs = Array.from(raiz.querySelectorAll('img')).map(img => ({
    alt: img.getAttribute('alt'), src: img.getAttribute('src') || '', natural: img.naturalWidth,
    completo: img.complete, altura: img.getBoundingClientRect().height, visivel: visivel(img)
  }));
  const discos = Array.from(raiz.querySelectorAll('*')).filter(e => e.classList.contains('logo-circle')
      || textoProprio(e) === 'GT').map(desc);
  return { imgs, discos, fundo: getComputedStyle(raiz).backgroundColor };
}
"""

_JS_ALVOS = _JS_BASE + r"""
(seletores) => {
  const vistos = new Set(), pequenos = [];
  let total = 0;
  for (const el of document.querySelectorAll(seletores)) {
    if (vistos.has(el) || el.classList.contains('pular')) continue;
    vistos.add(el);
    if (!visivel(el)) continue;
    total++;
    const r = el.getBoundingClientRect();
    if (r.height + 0.01 < 44 || r.width + 0.01 < 44)
      pequenos.push(`${desc(el)} '${txt(el).slice(0, 30)}' ${Math.round(r.width)}x${Math.round(r.height)}px`);
  }
  return { total, pequenos };
}
"""

_JS_LARGURA = _JS_BASE + r"""
(raizSel) => {
  const limite = window.innerWidth, raiz = document.documentElement;
  const base = raizSel ? document.querySelector(raizSel) : document.body;
  const fora = [];
  if (!base) return { scrollWidth: raiz.scrollWidth, fora: ['raiz ausente'] };
  for (const el of base.querySelectorAll('*')) {
    if (fora.length >= 8) break;
    if (!visivel(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right <= limite + 0.5 && r.left >= -0.5) continue;
    let contido = false;
    for (let a = el.parentElement; a && a !== document.body && a !== raiz; a = a.parentElement) {
      if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(a).overflowX)) { contido = true; break; }
    }
    if (contido) continue;
    const pai = el.parentElement;
    if (pai && pai !== document.body && visivel(pai)) {
      const rp = pai.getBoundingClientRect();
      if (rp.right > limite + 0.5 || rp.left < -0.5) continue;
    }
    fora.push(`${desc(el)} '${txt(el).slice(0, 30)}' de ${Math.round(r.left)} a ${Math.round(r.right)}px`);
  }
  return { scrollWidth: raiz.scrollWidth, fora };
}
"""

_JS_LARANJA = _JS_BASE + r"""
(args) => {
  const permitidos = Array.from(document.querySelectorAll('.btn-enroll'));
  const hero = heroDe();
  if (hero) permitidos.push(...Array.from(hero.querySelectorAll('a, button')).filter(e => txt(e) === 'Ver cursos abertos'));
  const v = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (!visivel(el)) continue;
    if (permitidos.some(p => p === el || p.contains(el))) continue;
    const cs = getComputedStyle(el);
    if (cs.backgroundColor === args.laranja) v.push(`fundo laranja em ${desc(el)} '${txt(el).slice(0, 30)}'`);
    if (cs.color === args.laranja && textoProprio(el)) v.push(`texto laranja em ${desc(el)} '${textoProprio(el).slice(0, 30)}'`);
    if (v.length >= 8) break;
  }
  return v;
}
"""

_JS_DUVIDAS = _JS_BASE + r"""
() => {
  const raiz = document.getElementById('duvidas');
  if (!raiz) return null;
  const h2 = Array.from(raiz.querySelectorAll('h2')).filter(visivel).map(txt);
  const itens = [];
  for (const q of raiz.querySelectorAll('summary, dt, h3, h4')) {
    const pergunta = (q.textContent || '').replace(/\s+/g, ' ').trim();
    if (!pergunta.endsWith('?')) continue;
    let resposta = '';
    if (q.tagName === 'SUMMARY') {
      resposta = Array.from(q.parentElement.childNodes).filter(n => n !== q).map(n => n.textContent).join(' ');
    } else if (q.tagName === 'DT') {
      for (let s = q.nextElementSibling; s && s.tagName !== 'DT'; s = s.nextElementSibling) resposta += ' ' + s.textContent;
    } else {
      for (let s = q.nextElementSibling; s && !['H2', 'H3', 'H4'].includes(s.tagName); s = s.nextElementSibling) resposta += ' ' + s.textContent;
      if (!resposta.trim() && q.parentElement && q.parentElement !== raiz) {
        resposta = Array.from(q.parentElement.children).filter(n => n !== q).map(n => n.textContent).join(' ');
      }
    }
    itens.push({ pergunta, resposta: resposta.replace(/\s+/g, ' ').trim() });
  }
  return { h2, itens };
}
"""

_JS_TEXTO_SEM_SCRIPT = """() => { const c = document.body.cloneNode(true);
  c.querySelectorAll('script, style, template').forEach(e => e.remove()); return c.textContent; }"""


def _esperar_animacoes(page):
    """Espera as animações finitas (revelação da resposta, cursor da planilha, transições) terminarem."""
    page.wait_for_function("() => document.getAnimations().filter(a => a.playState === 'running'"
                           " && a.effect && a.effect.getComputedTiming().iterations !== Infinity).length === 0",
                           timeout=TIMEOUT)
    page.wait_for_timeout(150)


def _abrir_respostas(page):
    page.evaluate("() => document.querySelectorAll('#duvidas details').forEach(d => { d.open = true; })")


def _foco_visivel(page, loc):
    """Leva o foco ao elemento pelo teclado (Tab a partir de um botão inserido antes dele); (outline, box-shadow)."""
    loc.wait_for(state="attached", timeout=TIMEOUT)
    loc.scroll_into_view_if_needed(timeout=TIMEOUT)
    loc.evaluate("e => { const t = document.createElement('button'); t.id = '__ancora_foco';"
                 " t.style.cssText = 'position:absolute;opacity:0'; e.parentNode.insertBefore(t, e); t.focus(); }")
    page.keyboard.press("Tab")
    foco = page.evaluate("document.activeElement === document.querySelector('#__ancora_foco').nextElementSibling")
    largura = loc.evaluate("e => getComputedStyle(e).outlineStyle !== 'none' ? (parseFloat(getComputedStyle(e).outlineWidth) || 0) : 0")
    sombra = loc.evaluate("e => getComputedStyle(e).boxShadow")
    page.evaluate("document.querySelector('#__ancora_foco').remove()")
    if not foco:
        return None
    return largura, sombra


def _sombra_pesada(sombra):
    if not sombra or sombra == "none":
        return False
    for camada in re.split(r",(?![^(]*\))", sombra):
        m = re.search(r"rgba?\(([^)]+)\)", camada)
        alfa = 1.0
        if m:
            partes = [p for p in re.split(r"[,\s/]+", m.group(1)) if p]
            alfa = float(partes[3]) if len(partes) > 3 else 1.0
        medidas = [float(x) for x in re.findall(r"(-?[\d.]+)px", camada)]
        desfoque = medidas[2] if len(medidas) > 2 else 0.0
        if alfa > 0 and (alfa > 0.10 or desfoque > 16):
            return True
    return False


# ---------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


@pytest.fixture(scope="module")
def landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("ds4_landing", cors_origin=base, angular=False) as ambiente:
        dados = semear_cursos_f5b(ambiente["api"], ambiente["db_path"])
        with urllib.request.urlopen(ambiente["api"] + "/api/courses", timeout=10) as resposta:
            cursos = json.loads(resposta.read().decode("utf-8")).get("courses") or []
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, landing=base + "/landing_global_training.html", dados=dados, cursos=cursos)
        finally:
            estatico.shutdown()
            estatico.server_close()


def _rodar(cenarios):
    resultados = []
    for codigo, nome, funcao in cenarios:
        try:
            funcao()
            resultados.append((codigo, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            texto = str(erro) or type(erro).__name__
            linha = texto.splitlines()[0]
            resultados.append((codigo, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")
    falhas = [f"{c}: {m}" for c, ok, m in resultados if not ok]
    assert not falhas, f"{len(falhas)} de {len(resultados)} cenários falharam: " + " | ".join(falhas)


def _exigir(violacoes):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões): " + " ; ".join(violacoes[:14])
                    + (f" ; e mais {len(violacoes) - 14}" if len(violacoes) > 14 else ""))


# ------------------------------------------------------------------------------------------------------- teste
def test_ds4_landing(browser, landing):
    contextos, erros = [], []
    oficiais = _logos_oficiais()
    cursos_api = landing["cursos"]

    def pagina(largura=1440, altura=900):
        ctx = browser.new_context(viewport={"width": largura, "height": altura})
        contextos.append(ctx)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        ctx.route("http://localhost:4200/**", lambda r: r.fulfill(status=200, content_type="text/html", body="spa"))
        page = ctx.new_page()

        def ao_console(msg):
            if msg.type == "error" and ERRO_HTTP.search(msg.text):
                erros.append(f"{largura}px: {msg.text[:120]}")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"{largura}px pageerror: {e}"[:160]))
        page.goto(landing["landing"], wait_until="networkidle")
        page.locator(".course-card").first.wait_for(timeout=TIMEOUT)
        return page

    paginas = {w: pagina(w, h) for w, h in LARGURAS}

    # ---------------------------------------------------------------- coleta dos três estados (G4b, G10, G11, G13, G14)
    coleta = {}
    alvos_sel = ("button, " + SEL_BARRA + " a, footer a, #chat-bubble a, a[href='#cursos']")

    def medir(page, largura, estado):
        _esperar_animacoes(page)
        coleta[(largura, estado)] = {
            "contraste": varrer_contraste(page),
            "fontes": fontes_abaixo_de(page, 14),
            "alvos": page.evaluate(_JS_ALVOS, alvos_sel),
            "largura": page.evaluate(_JS_LARGURA, None),
            "laranja": page.evaluate(_JS_LARANJA, {"laranja": LARANJA}),
        }

    def coletar():
        if coleta:
            return
        for largura, altura in LARGURAS:
            page = pagina(largura, altura)
            _abrir_respostas(page)
            medir(page, largura, "página")
            page.locator("#chat-btn").click()
            page.locator("#chat-bubble.open").wait_for(timeout=TIMEOUT)
            medir(page, largura, "chat aberto")
            page.locator("#chat-input").fill(PERGUNTA_OMEGA)
            page.locator("#chat-input").press("Enter")
            page.wait_for_function("""() => { const m = [...document.querySelectorAll('#chat-messages .msg-bot')].pop();
                return m && !m.textContent.includes('Processando'); }""", timeout=TIMEOUT)
            page.locator('[data-testid="chat-acao-matricular"]').first.wait_for(timeout=TIMEOUT)
            page.wait_for_timeout(900)
            medir(page, largura, "resposta")

    def por_estado(chave, formatar):
        coletar()
        violacoes = []
        for (largura, estado), dados in coleta.items():
            item = formatar(dados[chave], largura, estado)
            if item:
                violacoes.append(item)
        return violacoes

    # ------------------------------------------------------------------------------------------------ cenários
    def g1():
        v = []
        for largura, _ in LARGURAS:
            page = paginas[largura]
            for rotulo, sel in (("barra", SEL_BARRA), ("rodapé", "footer")):
                info = page.evaluate(_JS_LOGOS, sel)
                if info is None:
                    v.append(f"{largura}px: {rotulo} ({sel}) não existe")
                    continue
                if info["discos"]:
                    v.append(f"{largura}px: {rotulo} ainda tem disco 'GT' / .logo-circle ({info['discos'][:3]})")
                logos = [i for i in info["imgs"] if i["alt"] == ALT_LOGO and i["visivel"]]
                if len(logos) != 1:
                    v.append(f"{largura}px: {rotulo} com {len(logos)} <img alt={ALT_LOGO!r}> visível (esperado 1; "
                             f"imagens: {[(i['alt'], i['src'][:30]) for i in info['imgs']]})")
                    continue
                logo = logos[0]
                m = re.match(r"data:image/(webp|png);base64,(.+)$", logo["src"], re.S)
                if not m:
                    v.append(f"{largura}px: logo da {rotulo} com src {logo['src'][:40]!r} (esperado data:image/webp|png;base64)")
                    continue
                try:
                    variante = oficiais.get(base64.b64decode(re.sub(r"\s+", "", m.group(2))))
                except ValueError:
                    variante = None
                transparente = info["fundo"] in ("transparent", "rgba(0, 0, 0, 0)")
                fundo_escuro = None if transparente else _lum(_rgb(info["fundo"])) < 0.2
                if variante is None:
                    v.append(f"{largura}px: logo da {rotulo} não é um arquivo oficial de assets/brand/ (bytes diferentes)")
                elif fundo_escuro is not None and (variante == "escuro") != fundo_escuro:
                    v.append(f"{largura}px: logo da {rotulo} na variante de fundo {variante} sobre fundo {info['fundo']}")
                if not logo["completo"] or not logo["natural"]:
                    v.append(f"{largura}px: logo da {rotulo} não carregou (naturalWidth {logo['natural']})")
                if rotulo == "barra" and largura == 1440 and not (44 - 0.5 <= logo["altura"] <= 64 + 0.5):
                    v.append(f"1440px: logo da barra com {logo['altura']:.1f}px de altura (esperado 44–64)")
        _exigir(v)

    def g2():
        v = []
        for largura, _ in LARGURAS:
            page = paginas[largura]
            barra = page.locator(SEL_BARRA)
            if not barra.count():
                v.append(f"{largura}px: barra {SEL_BARRA} não existe")
                continue
            aluno = barra.locator("a, button", has_text="Área do aluno")
            if not aluno.count() or not aluno.first.is_visible():
                v.append(f"{largura}px: 'Área do aluno' não está visível na barra")
            elif "goToStudentArea" not in (aluno.first.get_attribute("onclick") or ""):
                v.append(f"{largura}px: 'Área do aluno' da barra sem onclick goToStudentArea")
            if barra.get_by_text("Área do funcionário").count():
                v.append(f"{largura}px: 'Área do funcionário' ainda está na barra (D-E: só no rodapé)")
            func = page.locator("footer").locator("a, button", has_text="Área do funcionário")
            if not func.count() or not func.first.is_visible():
                v.append(f"{largura}px: 'Área do funcionário' não está visível no rodapé")
            elif (func.first.get_attribute("onclick") or "").strip() != "goToStaffArea(event)":
                v.append(f"{largura}px: 'Área do funcionário' do rodapé com onclick "
                         f"{func.first.get_attribute('onclick')!r} (esperado 'goToStaffArea(event)')")
            if largura == 1440:
                alvos_secao = page.evaluate(_JS_BASE + r"""
                (args) => {
                  const barra = document.querySelector(args.barra);
                  const passos = Array.from(document.querySelectorAll('h2')).find(h => h.textContent.includes(args.passos));
                  const links = Array.from(barra.querySelectorAll('a[href^="#"]')).filter(a => a.getAttribute('href').length > 1);
                  const achar = (teste) => links.find(a => { const alvo = document.getElementById(a.getAttribute('href').slice(1));
                                                            return alvo && teste(alvo); });
                  const out = {};
                  const res = { cursos: achar(a => a.id === 'cursos'), duvidas: achar(a => a.id === 'duvidas'),
                                passos: passos ? achar(a => a === passos || a.contains(passos)) : null };
                  for (const [k, a] of Object.entries(res)) {
                    if (!a) { out[k] = null; continue; }
                    const r = a.getBoundingClientRect();
                    out[k] = { visivel: visivel(a), w: r.width, h: r.height, texto: txt(a) };
                  }
                  return out;
                }""", {"barra": SEL_BARRA, "passos": H2_PASSOS})
                for chave, nome in (("cursos", "#cursos"), ("passos", f"seção de {H2_PASSOS!r}"), ("duvidas", "#duvidas")):
                    item = alvos_secao[chave]
                    if not item:
                        v.append(f"1440px: a barra não tem link para {nome}")
                    elif not item["visivel"]:
                        v.append(f"1440px: o link da barra para {nome} não está visível")
                    elif item["h"] + 0.01 < ALVO_MIN or item["w"] + 0.01 < ALVO_MIN:
                        v.append(f"1440px: link da barra para {nome} ({item['texto']!r}) com "
                                 f"{item['w']:.0f}x{item['h']:.0f}px (mínimo 44x44)")
            else:
                medida = page.evaluate(_JS_LARGURA, SEL_BARRA)
                v += [f"390px: na barra, {f}" for f in medida["fora"]]
                pequenos = page.evaluate(_JS_ALVOS, f"{SEL_BARRA} a, {SEL_BARRA} button")["pequenos"]
                v += [f"390px: alvo pequeno na barra {p}" for p in pequenos]
        _exigir(v)

    def g3():
        v = []
        for largura, _ in LARGURAS:
            info = paginas[largura].evaluate(_JS_BASE + r"""
            () => {
              const h1 = document.querySelector('h1'), hero = heroDe();
              if (!h1) return null;
              const imagens = [];
              for (let a = h1; a && a !== (hero ? hero.parentElement : null); a = a.parentElement)
                if (getComputedStyle(a).backgroundImage !== 'none') imagens.push(desc(a));
              return { hero: hero ? desc(hero) : null, tag: hero ? hero.tagName : null,
                       fundo: hero ? getComputedStyle(hero).backgroundColor : null, imagens,
                       cor: getComputedStyle(h1).color, texto: h1.textContent.replace(/\s+/g, ' ').trim() };
            }""")
            if info is None:
                v.append(f"{largura}px: sem h1")
                continue
            if info["tag"] in (None, "BODY", "HTML") or info["fundo"] != ESCURO:
                v.append(f"{largura}px: o fundo do hero ({info['hero']}) é {info['fundo']} (esperado {ESCURO} numa "
                         f"seção do hero, não no body)")
            if info["imagens"]:
                v.append(f"{largura}px: background-image no caminho do h1 até o hero ({info['imagens']}); a grade "
                         f"fica num pseudo-elemento ou elemento aria-hidden")
            if info["cor"] != BRANCO:
                v.append(f"{largura}px: h1 na cor {info['cor']} (esperado {BRANCO})")
            if info["texto"] != H1_TEXTO:
                v.append(f"{largura}px: h1 {info['texto']!r} (esperado {H1_TEXTO!r})")
        _exigir(v)

    def g4():
        v = []
        for largura, _ in LARGURAS:
            page = paginas[largura]
            info = page.evaluate(_JS_BASE + r"""
            () => {
              const hero = heroDe();
              const estilo = e => ({ texto: txt(e), fundo: getComputedStyle(e).backgroundColor, cor: getComputedStyle(e).color,
                                     visivel: visivel(e) });
              const noHero = t => hero ? Array.from(hero.querySelectorAll('a, button')).filter(e => txt(e) === t).map(estilo) : [];
              return { cta: noHero('Ver cursos abertos'), chat: noHero('Tirar dúvidas no chat'),
                       enroll: Array.from(document.querySelectorAll('.btn-enroll')).map(estilo),
                       contato: Array.from(document.querySelectorAll('.btn-contact')).map(estilo) };
            }""")
            if len(info["cta"]) != 1:
                v.append(f"{largura}px: {len(info['cta'])} botões 'Ver cursos abertos' no hero (esperado 1)")
            if len(info["chat"]) != 1:
                v.append(f"{largura}px: {len(info['chat'])} botões 'Tirar dúvidas no chat' no hero (esperado 1)")
            if not info["enroll"]:
                v.append(f"{largura}px: nenhum .btn-enroll")
            for nome, itens in (("'Ver cursos abertos'", info["cta"]), (".btn-enroll", info["enroll"])):
                for item in itens:
                    if item["fundo"] != LARANJA or item["cor"] != TEXTO:
                        v.append(f"{largura}px: {nome} com fundo {item['fundo']} e texto {item['cor']} "
                                 f"(esperado {LARANJA} e {TEXTO})")
            for nome, itens in (("'Tirar dúvidas no chat'", info["chat"]), (".btn-contact", info["contato"])):
                for item in itens:
                    if LARANJA in (item["fundo"], item["cor"]):
                        v.append(f"{largura}px: {nome} em laranja (fundo {item['fundo']}, texto {item['cor']}); "
                                 f"é ação secundária")
        v += por_estado("laranja", lambda d, w, e: f"{w}px/{e}: " + "; ".join(d[:5]) if d else None)
        _exigir(v)

    def g5():
        v = []
        for largura, _ in LARGURAS:
            page = paginas[largura]
            texto = _norm(page.evaluate(_JS_TEXTO_SEM_SCRIPT))
            for proibido in PROIBIDOS:
                if proibido.lower() in texto.lower():
                    v.append(f"{largura}px: a página ainda mostra {proibido!r} (D-C)")
            itens = page.evaluate(_JS_BASE + r"""
                () => { const hero = heroDe();
                        return hero ? Array.from(hero.querySelectorAll('li')).filter(visivel).map(txt) : []; }""")
            for garantia in GARANTIAS:
                if not any(garantia.lower() in _norm(i).lower() for i in itens):
                    v.append(f"{largura}px: o hero não tem o item de lista {garantia!r} (itens: {itens[:6]})")
        _exigir(v)

    def g6():
        v = []
        for largura, _ in LARGURAS:
            ordem = paginas[largura].evaluate(_JS_BASE + r"""
            (args) => {
              const h1 = document.querySelector('h1');
              const h2s = Array.from(document.querySelectorAll('h2')).filter(visivel);
              const depois = h2s.filter(h => h1 && (h1.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING));
              const cursos = document.getElementById('cursos');
              const passos = h2s.find(h => h.textContent.includes(args.passos));
              return { primeiro: depois.length ? txt(depois[0]) : null,
                       primeiroEmCursos: !!(depois.length && cursos && cursos.contains(depois[0])),
                       cursosAntes: !!(cursos && passos && (cursos.compareDocumentPosition(passos) & Node.DOCUMENT_POSITION_FOLLOWING)
                                       && !cursos.contains(passos)) };
            }""", {"passos": H2_PASSOS})
            if not ordem["primeiroEmCursos"]:
                v.append(f"{largura}px: o primeiro h2 depois do hero é {ordem['primeiro']!r} (esperado o de #cursos, "
                         f"{H2_CURSOS!r})")
            if not ordem["cursosAntes"]:
                v.append(f"{largura}px: #cursos não vem antes de {H2_PASSOS!r}")
        page = paginas[1440]
        cartoes = page.locator("#cursos .course-card")
        if cartoes.count() != len(cursos_api):
            v.append(f"#cursos com {cartoes.count()} cartões (esperado {len(cursos_api)}, um por curso da API)")
        for curso in cursos_api:
            nome = curso["name"]
            cartao = page.locator("#cursos .course-card").filter(has=page.locator("h3", has_text=nome))
            if cartao.count() != 1:
                v.append(f"cartão de {nome!r}: {cartao.count()} cartões com h3 {nome!r} (esperado 1)")
                continue
            c = cartao.first
            texto = _norm(c.inner_text()).lower()
            nivel = curso.get("level") or ""
            tipo = f"Nível {nivel.lower()}" if nivel else "Curso disponível"
            if tipo.lower() not in texto:
                v.append(f"cartão de {nome!r} sem o tipo {tipo!r}")
            if nivel and nivel.lower() not in texto:
                v.append(f"cartão de {nome!r} sem o nível {nivel!r}")
            preco = c.locator(".course-price")
            esperado = "R$ " + f"{float(curso['price']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if not preco.count():
                v.append(f"cartão de {nome!r} sem .course-price")
            else:
                estilo = preco.first.evaluate("e => [getComputedStyle(e).fontVariantNumeric, getComputedStyle(e).color]")
                if _norm(preco.first.inner_text()) != esperado:
                    v.append(f"cartão de {nome!r}: preço {_norm(preco.first.inner_text())!r} (esperado {esperado!r})")
                if "tabular-nums" not in estilo[0]:
                    v.append(f"cartão de {nome!r}: preço sem tabular-nums ({estilo[0]})")
                if estilo[1] not in (TEXTO, LINK):
                    v.append(f"cartão de {nome!r}: preço na cor {estilo[1]} (esperado {TEXTO} ou {LINK})")
            for sel, rotulo in ((".btn-enroll", "Matricular agora"), (".btn-contact", "Tirar dúvidas com IA")):
                botao = c.locator(sel)
                if botao.count() != 1 or _norm(botao.first.inner_text()) != rotulo:
                    v.append(f"cartão de {nome!r}: {sel} {botao.count()}x / texto "
                             f"{_norm(botao.first.inner_text()) if botao.count() else None!r} (esperado 1x {rotulo!r})")
            bordas = c.evaluate("e => { const s = getComputedStyle(e); return [s.borderTopColor, s.borderRightColor,"
                                " s.borderBottomColor, s.borderLeftColor, s.borderTopWidth, s.boxShadow]; }")
            if any(b != BORDA for b in bordas[:4]) or bordas[4] in ("0px", ""):
                v.append(f"cartão de {nome!r}: borda {bordas[:5]} (esperado {BORDA} nos quatro lados)")
            if _sombra_pesada(bordas[5]):
                v.append(f"cartão de {nome!r}: sombra pesada ({bordas[5]})")
        _exigir(v)

    def g7():
        v = []
        page = paginas[1440]
        info = page.evaluate(_JS_DUVIDAS)
        if info is None:
            _exigir(["não existe a seção #duvidas"])
        if not info["h2"]:
            v.append("#duvidas sem h2 visível")
        itens = [i for i in info["itens"] if len(i["resposta"]) >= 20]
        if len(itens) < 4:
            v.append(f"#duvidas com {len(itens)} pergunta(s) com resposta (esperado >= 4; perguntas achadas: "
                     f"{[i['pergunta'][:40] for i in info['itens']]})")
        temas = {
            "cancelamento": (r"cancel", ("7 dias", "aprovação do pagamento")),
            "acesso aos materiais": (r"acesso|materia", ("aprovação do pagamento",)),
            "pagamento": (r"pag", ("mercado pago",)),
            "certificado": (r"certificado", ("certificado", "conclu")),
        }
        candidatos = {}
        for tema, (padrao, trechos) in temas.items():
            candidatos[tema] = [k for k, i in enumerate(itens) if re.search(padrao, i["pergunta"], re.I)
                                and all(t in i["resposta"].lower() for t in trechos)]
            if not candidatos[tema]:
                v.append(f"#duvidas sem pergunta sobre {tema} cuja resposta traga {list(trechos)}")
        if all(candidatos.values()):
            nomes = list(candidatos)
            if not any(len(set(escolha)) == len(escolha) for escolha in itertools.product(*(candidatos[t] for t in nomes))):
                v.append(f"os quatro temas não estão em perguntas distintas ({candidatos})")
        for i in itens:
            if "reconhecido pelo mercado" in i["resposta"].lower() or re.search(r"(?<!não é )reconhecido pelo mec", i["resposta"].lower()):
                v.append(f"resposta de {i['pergunta'][:40]!r} contradiz certificado.md (curso livre, não reconhecido pelo MEC)")
        _exigir(v)

    def g8():
        v = []
        page = pagina(1440, 900)
        info = page.evaluate(_JS_BASE + r"""
        () => {
          const botoes = Array.from(document.querySelectorAll('button, a')).filter(b =>
            (b.getAttribute('onclick') || '').replace(/\s+/g, '') === 'toggleChat()' && !b.closest('#chat-bubble')
            && b.id !== 'chat-btn' && !(document.querySelector('h1') && b.closest('section') === document.querySelector('h1').closest('section')));
          const blocos = botoes.map(b => ({ b, bloco: b.closest('section, aside') })).filter(x => x.bloco
            && /turmas fechadas/i.test(x.bloco.textContent) && /empresa/i.test(x.bloco.textContent));
          if (!blocos.length) return { achou: false, botoes: botoes.map(desc) };
          const x = blocos[0];
          x.b.setAttribute('data-ds4-empresas', '1');
          return { achou: true, texto: txt(x.b), fundo: getComputedStyle(x.b).backgroundColor, cor: getComputedStyle(x.b).color,
                   visivel: visivel(x.b), bloco: desc(x.bloco),
                   distinto: !['cursos', 'duvidas'].includes(x.bloco.id) };
        }""")
        if not info["achou"]:
            v.append(f"nenhum bloco (section/aside) com 'turmas fechadas' e 'empresa' e um botão toggleChat() "
                     f"(botões toggleChat fora do hero e do chat: {info['botoes']})")
        else:
            if not info["visivel"]:
                v.append(f"o botão do bloco de empresas ({info['texto']!r}) não está visível")
            if not info["distinto"]:
                v.append(f"o bloco de empresas é {info['bloco']} (esperado um bloco próprio)")
            if LARANJA in (info["fundo"], info["cor"]):
                v.append(f"o botão do bloco de empresas está em laranja (fundo {info['fundo']}, texto {info['cor']})")
            if info["visivel"]:
                page.locator("[data-ds4-empresas]").click()
                try:
                    page.locator("#chat-bubble.open").wait_for(timeout=3000)
                except Exception:
                    v.append("o botão do bloco de empresas não abriu o chat")
        texto = page.evaluate(_JS_TEXTO_SEM_SCRIPT)
        numeros = re.findall(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}", texto)
        links = page.locator('a[href*="wa.me"], a[href*="whatsapp.com"], a[href^="tel:"]').count()
        if numeros or links:
            v.append(f"número ou link de WhatsApp/telefone na página ({numeros[:3]}, {links} link(s))")
        _exigir(v)

    def g9():
        v = []
        page = pagina(1440, 900)
        info = page.evaluate(_JS_BASE + r"""
        () => {
          const secoes = Array.from(document.querySelectorAll('section')).filter(s => !s.closest('footer, #chat-bubble') && visivel(s));
          const ultima = secoes[secoes.length - 1];
          if (!ultima) return null;
          const empresas = Array.from(secoes).find(s => /turmas fechadas/i.test(s.textContent) && s.querySelector('[onclick*="toggleChat"]'));
          const footer = document.querySelector('footer');
          const link = Array.from(ultima.querySelectorAll('a[href="#cursos"]')).find(visivel);
          if (link) link.setAttribute('data-ds4-final', '1');
          return { secao: desc(ultima), id: ultima.id, h2: Array.from(ultima.querySelectorAll('h2')).filter(visivel).map(txt),
                   link: !!link, empresas: ultima === empresas,
                   antesDoRodape: !!(footer && (ultima.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING)) };
        }""")
        if info is None:
            _exigir(["a página não tem section"])
        if info["id"] in ("cursos", "duvidas") or info["empresas"]:
            v.append(f"a última seção antes do rodapé é {info['secao']} (esperado uma faixa final própria)")
        if not info["antesDoRodape"]:
            v.append("a faixa final não vem antes do rodapé")
        if not info["h2"]:
            v.append(f"a faixa final {info['secao']} não tem h2 visível")
        if not info["link"]:
            v.append(f"a faixa final {info['secao']} não tem um a[href='#cursos'] visível")
        else:
            page.locator("[data-ds4-final]").click()
            page.wait_for_timeout(300)
            if page.evaluate("location.hash") != "#cursos":
                v.append(f"o botão da faixa final levou a {page.evaluate('location.hash')!r} (esperado #cursos)")
        _exigir(v)

    def g10():
        def fmt(medida, largura, estado):
            partes = []
            if medida["falhas"]:
                partes.append(f"{len(medida['falhas'])} abaixo de AA: {descrever(medida['falhas'], 5)}")
            ignorados = [i for i in medida["ignorados"] if i.get("motivo") != "desabilitado"]
            if ignorados:
                partes.append(f"{len(ignorados)} ignorado(s): {descrever(ignorados, 4)}")
            return f"{largura}px/{estado} ({medida['verificados']} textos): " + " | ".join(partes) if partes else None
        _exigir(por_estado("contraste", fmt))

    def g11():
        _exigir(por_estado("fontes", lambda d, w, e: f"{w}px/{e}: {len(d)} abaixo de 14px: {descrever(d, 6)}" if d else None))

    def g12():
        v = []
        for largura, _ in LARGURAS:
            page = paginas[largura]
            h1s = page.evaluate(_JS_BASE + "() => Array.from(document.querySelectorAll('h1')).filter(visivel).map(txt)")
            if len(h1s) != 1:
                v.append(f"{largura}px: {len(h1s)} h1 visíveis {h1s} (esperado 1)")
            h2s = page.evaluate(_JS_BASE + "() => Array.from(document.querySelectorAll('h2')).filter(visivel).map(txt)")
            for esperado in (H2_CURSOS, H2_PASSOS):
                if not any(esperado.lower() in h.lower() for h in h2s):
                    v.append(f"{largura}px: sem h2 {esperado!r} (h2: {h2s})")
        _exigir(v)

    def g13():
        _exigir(por_estado("alvos", lambda d, w, e: f"{w}px/{e}: {len(d['pequenos'])} de {d['total']} alvos < 44x44: "
                           + "; ".join(d["pequenos"][:6]) if d["pequenos"] else None))

    def g14():
        def fmt(d, largura, estado):
            if largura != 390 or estado == "resposta":
                return None
            if d["scrollWidth"] > 390 or d["fora"]:
                return f"390px/{estado}: scrollWidth {d['scrollWidth']}; fora da tela: {d['fora'][:5]}"
            return None
        _exigir(por_estado("largura", fmt))

    def g15():
        v = []
        page = pagina(1440, 900)
        page.evaluate(_JS_BASE + r"""
        () => {
          const marcar = (el, nome) => { if (el) el.setAttribute('data-ds4-foco', nome); };
          const barra = document.querySelector('nav[aria-label="Principal"]');
          marcar(barra && barra.querySelector('a[href="#cursos"]'), 'link #cursos da barra');
          marcar(Array.from(document.querySelectorAll('footer a, footer button')).find(e => txt(e) === 'Área do funcionário'),
                 'Área do funcionário no rodapé');
          marcar(document.querySelector('.btn-enroll'), 'primeiro .btn-enroll');
          marcar(Array.from(document.querySelectorAll('section button, aside button')).find(b =>
            (b.getAttribute('onclick') || '').replace(/\s+/g, '') === 'toggleChat()' && /turmas fechadas/i.test(b.closest('section, aside').textContent)),
            'botão do bloco de empresas');
          const secoes = Array.from(document.querySelectorAll('section')).filter(s => !s.closest('footer, #chat-bubble') && visivel(s));
          const ultima = secoes[secoes.length - 1];
          marcar(ultima && ultima.querySelector('a[href="#cursos"]'), 'link da faixa final');
        }""")
        for nome in ("link #cursos da barra", "Área do funcionário no rodapé", "primeiro .btn-enroll",
                     "botão do bloco de empresas", "link da faixa final"):
            alvo = page.locator(f'[data-ds4-foco="{nome}"]')
            if not alvo.count():
                v.append(f"{nome}: elemento não encontrado")
                continue
            medida = _foco_visivel(page, alvo.first)
            if medida is None:
                v.append(f"{nome}: o Tab não levou o foco ao elemento")
            elif medida[0] <= 0 and (not medida[1] or medida[1] == "none"):
                v.append(f"{nome}: sem foco visível (outline 0 e sem box-shadow)")
        _exigir(v)

    def k1():
        _exigir(list(dict.fromkeys(erros)))

    try:
        _rodar([
            ("G1", "logo oficial na barra e no rodapé", g1),
            ("G2", "barra: Área do aluno, links de seção; Área do funcionário no rodapé", g2),
            ("G3", "topo escuro com h1 branco", g3),
            ("G4", "laranja só na conversão", g4),
            ("G5", "garantias no lugar dos números", g5),
            ("G6", "catálogo logo depois do hero, cartões", g6),
            ("G7", "seção de dúvidas fiel à base", g7),
            ("G8", "bloco para empresas abre o chat", g8),
            ("G9", "faixa final leva a #cursos", g9),
            ("G10", "contraste AA completo, sem ignorados", g10),
            ("G11", "nenhum texto abaixo de 14 px", g11),
            ("G12", "um h1 e os h2 esperados", g12),
            ("G13", "alvos de 44 x 44 px", g13),
            ("G14", "390 px sem rolagem horizontal", g14),
            ("G15", "foco visível nos controles novos", g15),
            ("K1", "sem erros de console", k1),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
