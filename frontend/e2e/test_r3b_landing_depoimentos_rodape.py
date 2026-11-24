"""E2E da R3-2 (R3b): aba Depoimentos e rodapé da landing copiados do site antigo (Chromium via Playwright).

Pedido do PM (entrega 2 de 4 da onda R3, só em `frontend/landing_global_training.html`): copiar do site antigo
(https://gtcursos.com.br/) a aba Depoimentos, com os MESMOS depoimentos, e o rodapé, com as mesmas informações. Os textos
literais foram lidos pelo navegador em 23/11/2026; os depoimentos NÃO levam correção ortográfica ("Solidwork",
"pessoal!!!", "dia dia", "Global training Technology" ficam como estão).

Decisões do PM: no rodapé ficam só os links das redes sociais; FORA do rodapé "Global EAD", "A Global Training" e "Contato"
(como links de navegação); Navegação = Home, Cursos e Treinamentos In Company, apontando para seções da própria landing;
"Fale conosco" = laranja do projeto (`.btn-cta`, texto `#17212b`).

Restrições invariantes (D115 + projeto), que os cenários abaixo conferem sobre o estilo COMPUTADO:
  - entrega só de marcação e CSS: o <script> inline não muda um byte (a guarda é o `test_ds4_script_inalterado.py`, agora
    com referência `f7dc262` e sem região aberta); o literal `http://localhost:8000` continua no script; depoimentos e rodapé
    são HTML estático (aparecem com o JavaScript desligado); sem carrossel automático;
  - o servidor estático da landing serve só HTML: imagem só como `data:` URI ou SVG inline; nenhum recurso externo novo e
    nenhuma fonte nova; sem emojis; um único h1; contraste AA; alvos >= 44 px; texto >= 14 px; sem rolagem horizontal em
    390 px; links com nome acessível; títulos sem pular nível;
  - paleta (docs/DESIGN.md): rodapé continua `#212830`; texto de apoio sobre escuro `#cbd5df`; foco sobre escuro `#7fd8f0`;
    laranja `#ff7a18` só no botão "Fale conosco" do rodapé (e nos botões de matrícula que já existiam), texto `#17212b`.

CONTRATO (o que o dev-frontend implementa; tudo o que está abaixo é cobrado por um cenário)

 1. Âncoras. `<body>` ou o primeiro bloco da página ganha `id="topo"` (um só, no início: topo absoluto <= 100 px). A seção
    "Treinamento para a sua empresa" ganha `id="empresas"` (mantém `aria-labelledby="empresas-titulo"`, o h2 e o botão
    `toggleChat()`). `#cursos` já existe.
 2. Depoimentos: `<section id="depoimentos" aria-labelledby="depoimentos-titulo">` dentro do `<main>`, entre a seção
    `#empresas` e `#como-funciona`. Um único h2 `#depoimentos-titulo` com o texto "Depoimentos"; nada de subtítulo (fora
    do h2 e dos cartões a seção não tem texto). Exatamente 5 elementos `data-testid="depoimento-card"`, nesta ordem: Sônia
    Costa, Flavio Antonio de Jesus Serafim, Cláudia Silva, Jeiel Lopes, Rodrigo Andrade. Cada cartão tem um
    `data-testid="depoimento-texto"` (o texto literal, IGUAL ao do site antigo; é o `<blockquote>` ou está dentro de um) e
    um `data-testid="depoimento-autor"` (só o nome, textContent exato; enfeites como o travessão vão em CSS `::before`),
    nessa ordem no DOM. Sem foto, sem estrelas, sem data (nenhum dígito na seção), sem botões, sem rolagem lateral, sem
    animação em repouso. Grade responsiva: em 1280 px pelo menos 2 cartões na primeira linha; em 390 px cartões com no
    mínimo 240 px de largura, dentro da tela e sem sobreposição. Texto >= 14 px, contraste AA, nenhum texto cortado.
    Nenhum elemento `<footer>` dentro dos cartões (a landing tem UM só `<footer>`, o do rodapé; os e2e antigos usam
    `document.querySelector('footer')`).
 3. Rodapé: `<footer data-testid="rodape">` fora do `<main>`, filho de `<body>`, fundo `rgb(33, 40, 48)`, o único `<footer>`
    da página (landmark `contentinfo`). Conteúdo, nesta ordem de DOM:
      logo oficial (um só `<img alt="Global Training Technology">`, `data:` URI, variante de fundo escuro) ->
      `rodape-descricao` (texto literal do site antigo, >= 14 px) ->
      `rodape-social-facebook`, `rodape-social-instagram`, `rodape-social-youtube` (links exatos, `target="_blank"`,
        `rel` com `noopener` e `noreferrer`, `aria-label` "Facebook" / "Instagram" / "YouTube", SVG inline `aria-hidden`
        pintado e visível, alvo >= 44 x 44 px) ->
      título "Contato" (h2, h3 ou h4; NÃO é link) e os links `rodape-endereco`, `rodape-whatsapp-escola`,
        `rodape-whatsapp-empresas`, `rodape-email` (textos e hrefs exatos abaixo; os três primeiros com `target="_blank"` e
        `rel` seguro) ->
      título "Navegação" e UM `<nav aria-label="...">` (nome diferente de "Principal") com exatamente 3 links:
        `rodape-nav-home` "Home" -> `#topo`, `rodape-nav-cursos` "Cursos" -> `#cursos`, `rodape-nav-incompany`
        "Treinamentos In Company" -> `#empresas` (destinos existem; clicar leva até eles) ->
      título "Atendimento" e `rodape-atendimento` com duas linhas, cada uma num elemento próprio: "Seg a Sex: 08h às 21h" e
        "Sábado: 08h às 12h" ->
      `rodape-fale-conosco`: `<a>` com textContent "Fale conosco" (CSS pode pôr em maiúsculas, sem espaçamento >= 2 px),
        classe `btn-cta`, fundo `rgb(255, 122, 24)`, texto `rgb(23, 33, 43)` (razão >= 4,5:1), href exatamente
        `https://wa.me/5519994626940` (sem `?text=`), `target="_blank"`, `rel` com `noopener` e `noreferrer`, >= 44 x 44 px ->
      faixa inferior (abaixo de todas as colunas): `rodape-copyright` com o texto literal "© 2026 Global Training Technology ·
        Escola de Informática em Indaiatuba/SP · Todos os direitos reservados." e `rodape-prototipo` com "Este é um protótipo
        de MVP desenvolvido como TCC" (a nota que já existia); `rodape-area-funcionario` (o link atual "Área do funcionário"
        com `onclick="goToStaffArea(event)"`) fica no rodapé.
    Os links do rodapé são EXATAMENTE estes 12 (nenhum a mais: nada de Global EAD, A Global Training, Contato, Termos...):
    as 3 redes, endereço, 2 WhatsApp, e-mail, 3 da navegação, Fale conosco e Área do funcionário. Cada um >= 44 x 44 px e
    com foco visível (atenção: o alvo de 44 px vale nas DUAS dimensões, então links curtos como "Home" precisam de
    `min-width: 44px`; é a mesma regra do G13 do `test_ds4_landing.py`). Em 1280 px os títulos Contato, Navegação e Atendimento ficam lado a lado, nessa ordem (esquerda para a
    direita); em 390 px empilham, sem rolagem horizontal. Títulos sem pular nível (h1 -> h2 -> h3...; o chat é ignorado).
    Textos literais dos contatos (o travessão é U+2013, o ponto médio é U+00B7):
      endereço   "Rua Pedro Gonçalves, 401 - Jd. Pau Preto, Indaiatuba/SP"  -> https://www.google.com/maps?cid=859323907528355985
      escola     "(19) 99462-6940 (WhatsApp – Escola)"                      -> https://wa.me/5519994626940
      empresas   "(19) 99406-6468 (WhatsApp – Empresas)"                    -> https://wa.me/5519994066468
      e-mail     "contato@gtcursos.com.br"                                  -> mailto:contato@gtcursos.com.br
      redes      Facebook https://www.facebook.com/instrutorclaytonmalta/
                 Instagram https://www.instagram.com/globaltrainingtechnology/
                 YouTube https://www.youtube.com/channel/UCOXPkq1gFW7PPpovPX3dUrw

Cenários (um teste pytest cada um; sufixos entre colchetes dizem como ficam no red de hoje):
  E0a  recursos e script intocados: um só <script> inline, sem src, com o literal http://localhost:8000; nenhum <link>
       além da folha do Google Fonts de hoje (mesmo href); todo src= é data:; sem iframe/embed/video; sem @import nem
       @font-face nem url() externo no CSS                                                                  [passa no red]
  E0b  depoimentos e rodapé são HTML estático (nada disso no script) e existem no HTML servido
  E0c  com o JavaScript desligado os 5 cartões e o rodapé aparecem
  T1   id="topo" único e no início; id="empresas" na seção de empresas com o h2 e o botão de antes
  T2   ordem dos h2 do <main>: Cursos, Treinamento para a sua empresa, Depoimentos, Do interesse à matrícula, Em todos os
       cursos, Dúvidas frequentes, Escolha o seu curso hoje; #depoimentos dentro do <main>
  D1   estrutura da seção (section, aria-labelledby, h2 "Depoimentos", sem subtítulo nem texto solto)
  D2   5 cartões, ordem, autor exato e texto literal (1280 e 390 px)
  D3   texto dentro de <blockquote>, texto antes do autor, sem correção ortográfica, sem <footer> nos cartões
  D4   sem foto, estrela, data, emoji nem botão
  D5   grade responsiva (1280: >= 2 colunas; 390: dentro da tela, >= 240 px, sem sobreposição); nada cortado
  D6   390 px sem rolagem horizontal na seção nem na página
  D7   texto >= 14 px e contraste AA (scanner completo) na seção, em 1280 e 390 px
  D8   sem carrossel nem animação em repouso; cartões parados por 1,5 s; sem laranja na seção
  R1   um só <footer> ([data-testid=rodape]), filho do body, escuro, landmark contentinfo, logo oficial único
  R2   descrição literal (>= 14 px)
  R3   três redes: links exatos, nova aba com rel seguro, aria-label, SVG pintado, alvo >= 44 px
  R4   contato: endereço, dois WhatsApp e e-mail com textos e hrefs exatos
  R5   navegação: um <nav> com nome, exatamente 3 links, textos e hrefs, destinos existem, ausências
  R6   clicar em cada link da navegação leva ao destino
  R7   atendimento: as duas linhas, cada uma no seu elemento
  R8   "Fale conosco": texto, classe, cores, contraste, href exato, nova aba, alvo
  R9   copyright literal, nota de protótipo, "Área do funcionário" (link atual), faixa inferior
  R10  os links do rodapé são exatamente os 12 do contrato; nenhum link "Global EAD", "A Global Training" ou "Contato"
  R11  títulos: h1 único, Contato/Navegação/Atendimento como títulos, ordem sem pular nível, "Depoimentos" em h2
  R12  ordem de DOM dentro do rodapé
  R13a alvos >= 44 x 44 px em 1280 e 390 px
  R13b foco visível em cada link do rodapé
  R13c texto >= 14 px e contraste AA (scanner completo) no rodapé, em 1280 e 390 px
  R13d laranja só no "Fale conosco" (um só `.btn-cta` no rodapé)
  R14  1280 px: colunas lado a lado, nessa ordem
  R15  390 px: colunas empilhadas, sem rolagem horizontal
  R16  sem emojis e sem maiúsculas espaçadas nas regiões novas
  K1   sem exceções de página nem erros 4xx/5xx no console, em 1280 e 390 px

Escolhas do agente-testes (modo autônomo, D40), todas conservadoras:
  - Os testids `rodape-copyright`, `rodape-prototipo` e `rodape-area-funcionario` não estavam no pedido; foram acrescentados
    para que o rodapé novo seja verificável sem depender de texto solto.
  - O hero da landing tem o laranja em `.btn-primary` (não `.btn-cta`); o "Fale conosco" é o primeiro `.btn-cta`. Não há
    contagem global de `.btn-cta`: o teste confere um só `.btn-cta` DENTRO do rodapé e nenhum outro laranja ali.
  - O chat (`#chat-bubble`, com um h4) fica fora da checagem de ordem de títulos: é um diálogo que já existia.
  - O travessão dos WhatsApp é comparado exatamente (U+2013), como está no arquivo de textos lidos do site antigo.
  - Sem backend: a API (`http://localhost:8000`) é respondida por `page.route` com um curso de teste; o literal do script
    não é trocado.
  - Este arquivo conflita, DE PROPÓSITO, com três guardas antigas que o PM contradiz ao pedir o rodapé (G4 e G8 do
    `test_ds4_landing.py` e S5 do `test_ds4_script_inalterado.py`: "um único laranja" e "nenhum WhatsApp"); a proposta de
    ajuste está registrada na D124 e depende de autorização do orquestrador.

IDOR, matrícula ativa, 401/403 e dado antigo não se aplicam (HTML estático, sem endpoint).

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_r3b_landing_depoimentos_rodape.py -s
"""

import json
import re
import struct
import sys
import types
import unicodedata
import urllib.request
import zlib
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_contraste import _lum, _rgb, descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from test_e6_landing_chat import BACKEND_URL_DA_LANDING, _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
ESCURO = "rgb(33, 40, 48)"
LARANJA = "rgb(255, 122, 24)"
TEXTO = "rgb(23, 33, 43)"
ALT_LOGO = "Global Training Technology"
CURSO_STUB = {"id": "curso_stub_r3b", "name": "Curso Stub R3B", "level": "Básico", "price": 123}
FONTES_GOOGLE = ("https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;900"
                 "&family=Barlow+Condensed:wght@700;900&display=swap")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⌛⏳⭐]")

# Textos literais lidos de https://gtcursos.com.br/ (sem correção ortográfica).
DEPOIMENTOS = (
    ("Sônia Costa",
     "Fiz Excel Completo na escola e amei o curso, ótimo conteúdo e de fácil entendimento, super recomendo."),
    ("Flavio Antonio de Jesus Serafim",
     "Essa escola Global Training Technology foi a melhor escola que já fiz curso, Conteúdo top, tanto teórico como na "
     "prática, recepção do Professor Clayton Malta, sem palavras, sem contar que ele ensina muito bem! O ambiente da "
     "escola é muito bom, excelente computadores, internet etc, não tenho do que reclamar e indico pra qualquer "
     "pessoal!!!"),
    ("Cláudia Silva",
     "Clayton é um excelente professor, com uma didática clara e objetiva, conteúdo voltado as necessidades do dia dia do "
     "profissional que utiliza o Excel, recomendo a todos que façam os seus cursos, pois será um ótimo investimento para "
     "sua carreira e se você sempre treinar o que aprendeu, ficará um especialista no assunto. Agradeço a Global Training "
     "Technology por essa oportunidade de ampliar o conhecimento e aprendizado."),
    ("Jeiel Lopes",
     "Melhor escola que oferece cursos como Excel, Power BI, Solidwork e mais, já fiz alguns cursos com eles e recomendo "
     "pra quem quer a melhor qualidade em conhecimentos a Global training Technology tem o melhor a oferecer!"),
    ("Rodrigo Andrade",
     "Ambiente de muito conhecimento, professores capacitados tecnicamente. Todas as informações dos cursos são passadas "
     "de forma dinâmica e didática, deixando os alunos (as) confortáveis em seguir com as metodologias ensinadas."),
)
TRECHOS_SEM_CORRECAO = ("Solidwork e mais", "pessoal!!!", "dia dia", "Global training Technology tem o melhor")

DESCRICAO = ("Na Global Training Technology, transformamos conhecimento em resultados. Somos um centro de formação e "
             "soluções que une tecnologia, atualização constante e prática profissional para capacitar pessoas e empresas.")
REDES = (
    ("facebook", "Facebook", "https://www.facebook.com/instrutorclaytonmalta/"),
    ("instagram", "Instagram", "https://www.instagram.com/globaltrainingtechnology/"),
    ("youtube", "YouTube", "https://www.youtube.com/channel/UCOXPkq1gFW7PPpovPX3dUrw"),
)
URL_WA_ESCOLA = "https://wa.me/5519994626940"
URL_WA_EMPRESAS = "https://wa.me/5519994066468"
CONTATOS = (  # (testid, texto, href, nova aba?)
    ("rodape-endereco", "Rua Pedro Gonçalves, 401 - Jd. Pau Preto, Indaiatuba/SP",
     "https://www.google.com/maps?cid=859323907528355985", True),
    ("rodape-whatsapp-escola", "(19) 99462-6940 (WhatsApp – Escola)", URL_WA_ESCOLA, True),
    ("rodape-whatsapp-empresas", "(19) 99406-6468 (WhatsApp – Empresas)", URL_WA_EMPRESAS, True),
    ("rodape-email", "contato@gtcursos.com.br", "mailto:contato@gtcursos.com.br", False),
)
NAVEGACAO = (  # (testid, texto, href, id do destino)
    ("rodape-nav-home", "Home", "#topo", "topo"),
    ("rodape-nav-cursos", "Cursos", "#cursos", "cursos"),
    ("rodape-nav-incompany", "Treinamentos In Company", "#empresas", "empresas"),
)
ATENDIMENTO = ("Seg a Sex: 08h às 21h", "Sábado: 08h às 12h")
COPYRIGHT = ("© 2026 Global Training Technology · Escola de Informática em Indaiatuba/SP · "
             "Todos os direitos reservados.")
PROTOTIPO = "Este é um protótipo de MVP desenvolvido como TCC"
TESTIDS_DE_LINK_DO_RODAPE = (
    "rodape-social-facebook", "rodape-social-instagram", "rodape-social-youtube", "rodape-endereco",
    "rodape-whatsapp-escola", "rodape-whatsapp-empresas", "rodape-email", "rodape-nav-home", "rodape-nav-cursos",
    "rodape-nav-incompany", "rodape-fale-conosco", "rodape-area-funcionario",
)
H2_DO_MAIN = ("Cursos com matrículas abertas", "Treinamento para a sua empresa", "Depoimentos",
              "Do interesse à matrícula em minutos", "Em todos os cursos", "Dúvidas frequentes", "Escolha o seu curso hoje")
TITULOS_DAS_COLUNAS = ("Contato", "Navegação", "Atendimento")
PROIBIDOS_COMO_LINK = ("global ead", "a global training", "contato")


class Falha(Exception):
    pass


def _norm(texto):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", (texto or "").replace("\xa0", " "))).strip()


def _exigir(violacoes):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões): " + " ; ".join(violacoes[:12])
                    + (f" ; e mais {len(violacoes) - 12}" if len(violacoes) > 12 else ""))


# ------------------------------------------------------------------------------------------------- medição (JS)
_JS_BASE = r"""
const R3B_APOIO = true;  // começa com const: o Playwright avalia a expressão e chama a função do fim
function visivel(el) {
  if (!el || el.closest('[aria-hidden="true"]')) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility !== 'visible' || cs.display === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  return el.getClientRects().length > 0;
}
function norm(t) { return (t || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim(); }
function txt(el) { return norm(el.textContent); }
function desc(el) {
  let s = el.tagName.toLowerCase();
  const tid = el.getAttribute('data-testid');
  if (tid) s += `[data-testid=${tid}]`;
  else if (el.id) s += '#' + el.id;
  else if (el.classList.length) s += '.' + Array.from(el.classList).slice(0, 3).join('.');
  return s;
}
function caixa(el) {
  const r = el.getBoundingClientRect();
  return { left: r.left + scrollX, right: r.right + scrollX, top: r.top + scrollY, bottom: r.bottom + scrollY,
           w: r.width, h: r.height };
}
"""

_JS_INFO = _JS_BASE + r"""
(tid) => {
  const els = document.querySelectorAll(`[data-testid="${tid}"]`);
  if (els.length !== 1) return { n: els.length };
  const e = els[0], cs = getComputedStyle(e), c = caixa(e);
  return { n: 1, tag: e.tagName, texto: txt(e), href: e.getAttribute('href'), target: e.getAttribute('target'),
           rel: e.getAttribute('rel'), aria: e.getAttribute('aria-label'), onclick: e.getAttribute('onclick'),
           classes: Array.from(e.classList), visivel: visivel(e), w: c.w, h: c.h, left: c.left, right: c.right,
           top: c.top, bottom: c.bottom, fonte: parseFloat(cs.fontSize), cor: cs.color, fundo: cs.backgroundColor,
           svgs: e.querySelectorAll('svg').length, imgs: e.querySelectorAll('img').length,
           svgOculto: Array.from(e.querySelectorAll('svg')).every(s => s.getAttribute('aria-hidden') === 'true'),
           transform: cs.textTransform, espaco: parseFloat(cs.letterSpacing) || 0,
           noRodape: !!e.closest('footer[data-testid="rodape"]') };
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
    fora.push(`${desc(el)} '${txt(el).slice(0, 30)}' de ${Math.round(r.left)} a ${Math.round(r.right)}px`);
  }
  return { scrollWidth: raiz.scrollWidth, fora };
}
"""

_JS_CARTOES = _JS_BASE + r"""
() => {
  const s = document.getElementById('depoimentos');
  if (!s) return null;
  return Array.from(s.querySelectorAll('[data-testid="depoimento-card"]')).map(c => {
    const t = c.querySelectorAll('[data-testid="depoimento-texto"]'), a = c.querySelectorAll('[data-testid="depoimento-autor"]');
    const cx = caixa(c), cs = getComputedStyle(c);
    const tx = t.length === 1 ? t[0] : null, au = a.length === 1 ? a[0] : null;
    const dentro = (el) => { if (!el) return true; const r = caixa(el);
      return r.right <= cx.right + 1 && r.left >= cx.left - 1 && r.bottom <= cx.bottom + 1; };
    return { nTexto: t.length, nAutor: a.length, texto: tx ? txt(tx) : null, autor: au ? txt(au) : null,
             textoNoBlockquote: !!(tx && tx.closest('blockquote') && c.contains(tx.closest('blockquote'))),
             textoAntes: !!(tx && au && (tx.compareDocumentPosition(au) & Node.DOCUMENT_POSITION_FOLLOWING)),
             footerDentro: c.querySelectorAll('footer').length, visivel: visivel(c), box: cx,
             fonteTexto: tx ? parseFloat(getComputedStyle(tx).fontSize) : 0,
             fonteAutor: au ? parseFloat(getComputedStyle(au).fontSize) : 0,
             cortado: !!((tx && (tx.scrollHeight > tx.clientHeight + 1 || getComputedStyle(tx).webkitLineClamp !== 'none'))
                         || !dentro(tx) || !dentro(au)) };
  });
}
"""

_JS_TITULOS = _JS_BASE + r"""
() => Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(h => !h.closest('#chat-bubble') && visivel(h))
  .map(h => ({ nivel: Number(h.tagName[1]), texto: txt(h), noRodape: !!h.closest('footer'), box: caixa(h) }))
"""

_JS_LINKS_DO_RODAPE = _JS_BASE + r"""
() => {
  const f = document.querySelector('footer[data-testid="rodape"]');
  if (!f) return null;
  return Array.from(f.querySelectorAll('a')).map(a => ({ tid: a.getAttribute('data-testid'), href: a.getAttribute('href'),
    texto: txt(a), aria: a.getAttribute('aria-label'), visivel: visivel(a), box: caixa(a), onclick: a.getAttribute('onclick') }));
}
"""

_JS_LARANJA = _JS_BASE + r"""
(args) => {
  const raiz = document.querySelector(args.raiz);
  if (!raiz) return null;
  const permitidos = args.permitido ? Array.from(raiz.querySelectorAll(args.permitido)) : [];
  const v = [];
  for (const el of raiz.querySelectorAll('*')) {
    if (!visivel(el) || permitidos.some(p => p === el || p.contains(el))) continue;
    const cs = getComputedStyle(el);
    if (cs.backgroundColor === args.laranja) v.push(`fundo laranja em ${desc(el)} '${txt(el).slice(0, 30)}'`);
    if (cs.color === args.laranja && Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim()))
      v.push(`texto laranja em ${desc(el)} '${txt(el).slice(0, 30)}'`);
  }
  return v;
}
"""

_JS_REGIAO = _JS_BASE + r"""
(sel) => {
  const r = document.querySelector(sel);
  if (!r) return null;
  const texto = norm(r.innerText || r.textContent);
  const atributos = Array.from(r.querySelectorAll('*')).map(e => (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '')
                    + ' ' + (e.getAttribute('alt') || '')).join(' ');
  const espacados = Array.from(r.querySelectorAll('*')).filter(e => {
    const s = getComputedStyle(e);
    return visivel(e) && norm(e.innerText) && s.textTransform === 'uppercase' && (parseFloat(s.letterSpacing) || 0) >= 2;
  }).map(e => norm(e.innerText).slice(0, 30));
  return { texto, atributos, espacados };
}
"""


# ---------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def landing():
    porta = _porta_livre("E2E_LANDING_PORT")
    # Passa o próprio literal como "api": a cópia servida fica igual ao original (e o helper recusa uma landing sem o literal).
    servidor = _servidor_da_landing(porta, BACKEND_URL_DA_LANDING)
    try:
        yield f"http://127.0.0.1:{porta}/landing_global_training.html"
    finally:
        servidor.shutdown()
        servidor.server_close()


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _responder_api(route):
    route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                  body=json.dumps({"status": "success", "courses": [CURSO_STUB]}))


@pytest.fixture
def abrir(navegador, landing):
    """abrir(largura, altura, js=True, movimento='reduce') -> objeto com .page e .erros (carregada e pronta)."""
    contextos = []

    def _abrir(largura=1280, altura=900, js=True, movimento="reduce"):
        ctx = navegador.new_context(viewport={"width": largura, "height": altura}, java_script_enabled=js,
                                    reduced_motion=movimento)
        contextos.append(ctx)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        ctx.route("http://localhost:8000/**", _responder_api)
        page = ctx.new_page()
        erros = []
        page.on("console", lambda m: erros.append(f"{largura}px: {m.text[:120]}")
                if m.type == "error" and re.search(r"status of (\d{3})", m.text) else None)
        page.on("pageerror", lambda e: erros.append(f"{largura}px pageerror: {e}"[:160]))
        page.goto(landing, wait_until="networkidle" if js else "load")
        if js:
            page.locator(".course-card").first.wait_for(timeout=TIMEOUT)
        return types.SimpleNamespace(page=page, erros=erros)

    yield _abrir
    for ctx in contextos:
        ctx.close()


def _html_servido(landing):
    with urllib.request.urlopen(landing, timeout=10) as resposta:
        return resposta.read().decode("utf-8")


def _marcacao(html):
    sem = re.sub(r"<script\b.*?</script\s*>", "", html, flags=re.S | re.I)
    return re.sub(r"<style\b.*?</style\s*>", "", sem, flags=re.S | re.I)


def _info(page, testid):
    d = page.evaluate(_JS_INFO, testid)
    if d["n"] != 1:
        raise Falha(f"[data-testid={testid}]: {d['n']} elemento(s) na página (esperado exatamente 1)")
    return d


def _tem_rel_seguro(rel):
    partes = (rel or "").lower().split()
    return "noopener" in partes and "noreferrer" in partes


def _alvo_ok(d):
    return d["w"] + 0.01 >= 44 and d["h"] + 0.01 >= 44


def _decodificar_png(dados):
    """PNG 8 bits, RGB ou RGBA, sem entrelaçamento (o que o Playwright devolve) -> (largura, altura, canais, linhas)."""
    assert dados[:8] == b"\x89PNG\r\n\x1a\n", "captura não é PNG"
    pos, idat = 8, b""
    largura = altura = canais = 0
    while pos < len(dados):
        n = struct.unpack(">I", dados[pos:pos + 4])[0]
        tipo, corpo = dados[pos + 4:pos + 8], dados[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tipo == b"IHDR":
            largura, altura, profundidade, cor, _, _, entrelacado = struct.unpack(">IIBBBBB", corpo)
            assert profundidade == 8 and entrelacado == 0 and cor in (2, 6), "PNG fora do formato esperado"
            canais = 3 if cor == 2 else 4
        elif tipo == b"IDAT":
            idat += corpo
    bruto, linhas = zlib.decompress(idat), []
    stride, anterior, i = largura * canais, bytearray(largura * canais), 0
    for _ in range(altura):
        filtro, linha = bruto[i], bytearray(bruto[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = linha[x - canais] if x >= canais else 0
            b = anterior[x]
            c = anterior[x - canais] if x >= canais else 0
            if filtro == 1:
                linha[x] = (linha[x] + a) & 255
            elif filtro == 2:
                linha[x] = (linha[x] + b) & 255
            elif filtro == 3:
                linha[x] = (linha[x] + ((a + b) >> 1)) & 255
            elif filtro == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                linha[x] = (linha[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        linhas.append(linha)
        anterior = linha
    return largura, altura, canais, linhas


def _pixels_que_contrastam_no_centro(png, minimo=3.0):
    """Quantos pixels do quarto central da imagem têm contraste >= `minimo` com a cor dominante (o fundo)."""
    largura, altura, canais, linhas = _decodificar_png(png)
    x0, x1, y0, y1 = largura // 4, largura - largura // 4, altura // 4, altura - altura // 4
    pixels = [tuple(linhas[y][x * canais:x * canais + 3]) for y in range(y0, y1) for x in range(x0, x1)]
    fundo = max(set(pixels), key=pixels.count)
    lf = _lum(fundo)
    return sum(1 for p in pixels if (max(_lum(p), lf) + 0.05) / (min(_lum(p), lf) + 0.05) >= minimo)


# ------------------------------------------------------------------------------------------------- E0: estático
def test_e0a_recursos_externos_e_script_intocados(landing):
    html = _html_servido(landing)
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script\s*>", html, flags=re.S | re.I)
    v = []
    if len(scripts) != 1 or "src=" in scripts[0][0].lower():
        v.append(f"{len(scripts)} <script> na landing (esperado 1 inline, sem src)")
    elif BACKEND_URL_DA_LANDING not in scripts[0][1]:
        v.append(f"o literal {BACKEND_URL_DA_LANDING} sumiu do script (os helpers e2e quebram sem ele)")
    marcacao = _marcacao(html)
    css = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style\s*>", html, flags=re.S | re.I))
    links = re.findall(r"<link\b[^>]*>", marcacao, flags=re.I)
    hrefs = [re.search(r"""href\s*=\s*["']([^"']*)["']""", t).group(1) for t in links if re.search(r"href\s*=", t)]
    if links and (len(links) != 1 or hrefs != [FONTES_GOOGLE]):
        v.append(f"<link> da landing mudou (esperado só a folha do Google Fonts de hoje): {hrefs}")
    externos = [s for s in re.findall(r"""\ssrc\s*=\s*["']([^"']*)["']""", marcacao, flags=re.I) if not s.startswith("data:")]
    if externos:
        v.append(f"src= que não é data: URI: {externos[:3]}")
    if re.findall(r"""\ssrcset\s*=""", marcacao, flags=re.I):
        v.append("srcset na marcação (imagem só como data: URI ou SVG inline)")
    if re.findall(r"<(?:iframe|embed|object|video|audio|source)\b", marcacao, flags=re.I):
        v.append("iframe, embed, object, video, audio ou source na marcação")
    if re.search(r"@import|@font-face", css, flags=re.I):
        v.append("@import ou @font-face no CSS (nenhuma fonte nova)")
    urls = [u for u in re.findall(r"url\(\s*['\"]?([^'\")\s]+)", css, flags=re.I) if not u.startswith(("data:", "#"))]
    if urls:
        v.append(f"url() externo no CSS: {urls[:3]}")
    _exigir(v)


def test_e0b_depoimentos_e_rodape_sao_html_estatico(landing):
    html = _html_servido(landing)
    script = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.S | re.I)
    marcacao = _marcacao(html)
    v = []
    cartoes = len(re.findall(r"""data-testid\s*=\s*["']depoimento-card["']""", marcacao))
    if cartoes != 5:
        v.append(f"{cartoes} cartões data-testid=depoimento-card no HTML servido (esperado 5, escritos na marcação)")
    for tid in ("rodape", "rodape-descricao", "rodape-fale-conosco"):
        if len(re.findall(rf"""data-testid\s*=\s*["']{tid}["']""", marcacao)) != 1:
            v.append(f"data-testid={tid} ausente ou repetido no HTML servido")
    for ident in ("depoimentos", "empresas", "topo"):
        if len(re.findall(rf"""\sid\s*=\s*["']{ident}["']""", marcacao)) != 1:
            v.append(f"id={ident} ausente ou repetido no HTML servido")
    if any(re.search(r"depoimento|rodape", corpo, flags=re.I) for corpo in script):
        v.append("o script menciona depoimento/rodape: a entrega é só marcação e CSS (nada gerado por JavaScript)")
    _exigir(v)


def test_e0c_sem_javascript_cartoes_e_rodape_aparecem(abrir):
    p = abrir(1280, 900, js=False)
    cartoes = p.page.locator('[data-testid="depoimento-card"]')
    v = []
    if cartoes.count() != 5:
        v.append(f"com o JavaScript desligado há {cartoes.count()} cartões (esperado 5)")
    elif not all(cartoes.nth(i).is_visible() for i in range(5)):
        v.append("com o JavaScript desligado nem todos os cartões estão visíveis")
    rodape = p.page.locator('footer[data-testid="rodape"]')
    if rodape.count() != 1 or not rodape.is_visible():
        v.append("com o JavaScript desligado o rodapé não aparece")
    elif not p.page.locator('[data-testid="rodape-fale-conosco"]').is_visible():
        v.append("com o JavaScript desligado o botão Fale conosco não aparece")
    _exigir(v)


# ------------------------------------------------------------------------------------------------- âncoras e ordem
def test_t1_ids_topo_e_empresas(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const topos = document.querySelectorAll('[id="topo"]');
      const emp = document.getElementById('empresas');
      const t = topos[0];
      return { nTopo: topos.length, topoY: t ? t.getBoundingClientRect().top + scrollY : null,
               topoNoRodape: !!(t && t.closest('footer')),
               emp: emp ? { tag: emp.tagName, labelled: emp.getAttribute('aria-labelledby'),
                            h2: Array.from(emp.querySelectorAll('h2')).map(txt),
                            h2Id: (emp.querySelector('h2') || {}).id || null,
                            botao: !!emp.querySelector('button[onclick*="toggleChat"]'), visivel: visivel(emp) } : null,
               nEmpresas: document.querySelectorAll('[id="empresas"]').length };
    }""")
    v = []
    if info["nTopo"] != 1:
        v.append(f"{info['nTopo']} elementos com id=topo (esperado 1, no início da página)")
    elif info["topoY"] > 100 or info["topoNoRodape"]:
        v.append(f"id=topo fora do início da página (topo absoluto {info['topoY']:.0f}px, no rodapé: {info['topoNoRodape']})")
    if info["nEmpresas"] != 1 or not info["emp"]:
        v.append(f"{info['nEmpresas']} elementos com id=empresas (esperado 1, a seção 'Treinamento para a sua empresa')")
    else:
        e = info["emp"]
        if e["tag"] != "SECTION" or e["h2"] != ["Treinamento para a sua empresa"]:
            v.append(f"#empresas é {e['tag']} com h2 {e['h2']} (esperado a section com o h2 'Treinamento para a sua empresa')")
        if e["labelled"] != "empresas-titulo" or e["h2Id"] != "empresas-titulo":
            v.append(f"#empresas perdeu o aria-labelledby/id do título ({e['labelled']!r}, {e['h2Id']!r})")
        if not e["botao"]:
            v.append("#empresas perdeu o botão toggleChat() de 'Falar sobre turmas fechadas'")
    _exigir(v)


def test_t2_ordem_das_secoes_e_posicao_dos_depoimentos(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const h2 = Array.from(document.querySelectorAll('main h2')).map(txt);
      const dep = document.getElementById('depoimentos'), emp = document.getElementById('empresas');
      const como = document.getElementById('como-funciona');
      const antes = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) && !a.contains(b));
      return { h2, dentroDoMain: !!(dep && dep.closest('main')), empAntes: antes(emp, dep), comoDepois: antes(dep, como),
               secoesEntre: dep && emp && como ? Array.from(document.querySelectorAll('main section')).filter(s =>
                 antes(emp, s) && antes(s, como) && s !== dep && !dep.contains(s)).map(desc) : null };
    }""")
    v = []
    if info["h2"] != list(H2_DO_MAIN):
        v.append(f"h2 do <main> {info['h2']} (esperado nesta ordem: {list(H2_DO_MAIN)})")
    if not info["dentroDoMain"]:
        v.append("#depoimentos não está dentro do <main>")
    if not info["empAntes"] or not info["comoDepois"]:
        v.append(f"#depoimentos não fica depois de #empresas ({info['empAntes']}) e antes de #como-funciona ({info['comoDepois']})")
    if info["secoesEntre"]:
        v.append(f"há outra seção entre #empresas e #como-funciona além dos depoimentos: {info['secoesEntre']}")
    _exigir(v)


# ------------------------------------------------------------------------------------------------- depoimentos
def test_d1_estrutura_da_secao(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const s = document.getElementById('depoimentos');
      if (!s) return null;
      const t = document.getElementById('depoimentos-titulo');
      const resto = s.cloneNode(true);
      resto.querySelectorAll('[data-testid="depoimento-card"], h2').forEach(e => e.remove());
      return { tag: s.tagName, labelled: s.getAttribute('aria-labelledby'), titulo: t ? txt(t) : null,
               tituloTag: t ? t.tagName : null, tituloDentro: !!(t && s.contains(t)), tituloVisivel: visivel(t),
               nH2: s.querySelectorAll('h2').length, resto: norm(resto.textContent), visivel: visivel(s) };
    }""")
    if info is None:
        _exigir(["não existe a seção #depoimentos"])
    v = []
    if info["tag"] != "SECTION":
        v.append(f"#depoimentos é <{info['tag'].lower()}> (esperado <section>)")
    if info["labelled"] != "depoimentos-titulo":
        v.append(f"aria-labelledby {info['labelled']!r} (esperado 'depoimentos-titulo')")
    if info["tituloTag"] != "H2" or info["titulo"] != "Depoimentos" or not info["tituloDentro"] or not info["tituloVisivel"]:
        v.append(f"#depoimentos-titulo: <{(info['tituloTag'] or '?').lower()}> {info['titulo']!r} (esperado h2 visível 'Depoimentos' dentro da seção)")
    if info["nH2"] != 1:
        v.append(f"{info['nH2']} h2 na seção (esperado 1)")
    if info["resto"]:
        v.append(f"texto na seção fora do título e dos cartões (subtítulo inventado?): {info['resto'][:80]!r}")
    if not info["visivel"]:
        v.append("a seção não está visível")
    _exigir(v)


@pytest.mark.parametrize("largura,altura", [(1280, 900), (390, 844)])
def test_d2_cinco_cartoes_em_ordem_com_texto_literal(abrir, largura, altura):
    p = abrir(largura, altura)
    cartoes = p.page.evaluate(_JS_CARTOES)
    if cartoes is None:
        _exigir(["não existe a seção #depoimentos"])
    v = []
    if len(cartoes) != 5:
        v.append(f"{len(cartoes)} cartões data-testid=depoimento-card (esperado 5)")
    for i, (autor, texto) in enumerate(DEPOIMENTOS[:len(cartoes)]):
        c = cartoes[i]
        if c["nTexto"] != 1 or c["nAutor"] != 1:
            v.append(f"cartão {i + 1}: {c['nTexto']} depoimento-texto e {c['nAutor']} depoimento-autor (esperado 1 de cada)")
            continue
        if _norm(c["autor"]) != autor:
            v.append(f"cartão {i + 1}: autor {c['autor']!r} (esperado {autor!r})")
        if _norm(c["texto"]) != texto:
            ref = _norm(c["texto"])
            k = next((j for j in range(min(len(ref), len(texto))) if ref[j] != texto[j]), min(len(ref), len(texto)))
            v.append(f"cartão {i + 1} ({autor}): texto difere do site antigo no caractere {k}: "
                     f"agora {ref[max(0, k - 20):k + 25]!r} / esperado {texto[max(0, k - 20):k + 25]!r}")
        if not c["visivel"]:
            v.append(f"cartão {i + 1} ({autor}) não está visível")
    _exigir(v)


def test_d3_blockquote_ordem_interna_e_sem_correcao(abrir):
    p = abrir(1280, 900)
    cartoes = p.page.evaluate(_JS_CARTOES)
    if cartoes is None or len(cartoes) != 5:
        _exigir([f"esperados 5 cartões, achados {None if cartoes is None else len(cartoes)}"])
    v = []
    for i, c in enumerate(cartoes):
        if not c["textoNoBlockquote"]:
            v.append(f"cartão {i + 1}: depoimento-texto não é (nem está dentro de) um <blockquote> do cartão")
        if not c["textoAntes"]:
            v.append(f"cartão {i + 1}: o texto não vem antes do autor no DOM")
        if c["footerDentro"]:
            v.append(f"cartão {i + 1}: <footer> dentro do cartão (a landing tem um só <footer>, o do rodapé)")
    todos = " ".join(c["texto"] or "" for c in cartoes)
    for trecho in TRECHOS_SEM_CORRECAO:
        if trecho not in todos:
            v.append(f"trecho original {trecho!r} não está nos depoimentos (a ortografia do site antigo foi 'corrigida'?)")
    for corrigido in ("Solidworks", "do dia a dia"):
        if corrigido.lower() in todos.lower() and corrigido not in " ".join(t for _, t in DEPOIMENTOS):
            v.append(f"forma corrigida {corrigido!r} nos depoimentos (copiar sem correção)")
    _exigir(v)


def test_d4_sem_foto_estrela_data_emoji_nem_botao(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const s = document.getElementById('depoimentos');
      if (!s) return null;
      const todos = Array.from(s.querySelectorAll('*'));
      const atributos = todos.map(e => [e.getAttribute('class') || '', e.getAttribute('data-testid') || '',
        e.getAttribute('aria-label') || '', e.getAttribute('title') || '', e.getAttribute('alt') || ''].join(' ')).join(' ');
      const comFundo = todos.filter(e => getComputedStyle(e).backgroundImage !== 'none').map(desc);
      return { texto: norm(s.textContent), atributos, imgs: s.querySelectorAll('img, picture, video, canvas').length,
               svgVisivel: Array.from(s.querySelectorAll('svg')).filter(sv => sv.getAttribute('aria-hidden') !== 'true').length,
               times: s.querySelectorAll('time').length, botoes: s.querySelectorAll('button, [role="button"], [role="tab"]').length,
               comFundo };
    }""")
    if info is None:
        _exigir(["não existe a seção #depoimentos"])
    v = []
    if info["imgs"] or info["comFundo"]:
        v.append(f"foto/imagem na seção ({info['imgs']} img/picture/video/canvas; background-image em {info['comFundo'][:3]})")
    if info["svgVisivel"]:
        v.append(f"{info['svgVisivel']} SVG sem aria-hidden na seção (ícone decorativo tem de ser aria-hidden)")
    if re.search(r"[★☆⭐✰✯]", info["texto"]) or re.search(r"estrela|star|rating|\bnota\b", info["atributos"], re.I):
        v.append("estrelas ou nota na seção (o site antigo não tem)")
    if info["times"] or re.search(r"\d", info["texto"]) or re.search(
            r"janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro", info["texto"], re.I):
        v.append("data na seção (nenhum dígito nem mês pode aparecer; o site antigo não mostra data)")
    if EMOJI.search(info["texto"]) or EMOJI.search(info["atributos"]):
        v.append("emoji na seção")
    if info["botoes"]:
        v.append(f"{info['botoes']} botão(ões) na seção (sem carrossel, sem controles)")
    _exigir(v)


def test_d5_grade_responsiva_e_nada_cortado(abrir):
    v = []
    for largura, altura in ((1280, 900), (390, 844)):
        cartoes = abrir(largura, altura).page.evaluate(_JS_CARTOES)
        if cartoes is None or len(cartoes) != 5:
            v.append(f"{largura}px: esperados 5 cartões, achados {None if cartoes is None else len(cartoes)}")
            continue
        caixas = [c["box"] for c in cartoes]
        if any(c["w"] < 240 for c in caixas):
            v.append(f"{largura}px: cartão com menos de 240 px de largura ({[round(c['w']) for c in caixas]})")
        if largura == 1280:
            primeira_linha = sum(1 for c in caixas if abs(c["top"] - caixas[0]["top"]) <= 2)
            if primeira_linha < 2:
                v.append(f"1280px: só {primeira_linha} cartão na primeira linha (esperado >= 2, grade responsiva)")
        else:
            fora = [round(c["left"]) for c in caixas if c["left"] < -0.5 or c["right"] > 390.5]
            if fora:
                v.append(f"390px: cartões fora da tela (left {fora})")
        for a in range(5):
            for b in range(a + 1, 5):
                x, y = caixas[a], caixas[b]
                if x["left"] < y["right"] - 1 and y["left"] < x["right"] - 1 and x["top"] < y["bottom"] - 1 and y["top"] < x["bottom"] - 1:
                    v.append(f"{largura}px: cartões {a + 1} e {b + 1} se sobrepõem")
        for i, c in enumerate(cartoes):
            if c["cortado"]:
                v.append(f"{largura}px: texto do cartão {i + 1} cortado (overflow, line-clamp ou fora do cartão)")
    _exigir(v)


def test_d6_celular_sem_rolagem_horizontal_na_secao(abrir):
    p = abrir(390, 844)
    medida = p.page.evaluate(_JS_LARGURA, "#depoimentos")
    geral = p.page.evaluate(_JS_LARGURA, None)
    v = []
    if medida["fora"] == ["raiz ausente"]:
        _exigir(["não existe a seção #depoimentos"])
    if medida["fora"]:
        v.append(f"na seção, fora da tela: {medida['fora'][:4]}")
    if geral["scrollWidth"] > 390 or geral["fora"]:
        v.append(f"a página tem rolagem horizontal (scrollWidth {geral['scrollWidth']}; fora: {geral['fora'][:4]})")
    _exigir(v)


@pytest.mark.parametrize("largura,altura", [(1280, 900), (390, 844)])
def test_d7_fonte_14px_e_contraste_aa_na_secao(abrir, largura, altura):
    p = abrir(largura, altura)
    cartoes = p.page.evaluate(_JS_CARTOES)
    if cartoes is None or len(cartoes) != 5:
        _exigir([f"esperados 5 cartões, achados {None if cartoes is None else len(cartoes)}"])
    v = []
    for i, c in enumerate(cartoes):
        if c["fonteTexto"] < 14 or c["fonteAutor"] < 14:
            v.append(f"cartão {i + 1}: texto {c['fonteTexto']}px e autor {c['fonteAutor']}px (mínimo 14 px)")
    medida = varrer_contraste(p.page, raiz="#depoimentos")
    if medida["verificados"] < 11:
        v.append(f"só {medida['verificados']} textos medidos na seção (esperado >= 11: título, 5 textos e 5 autores)")
    if medida["falhas"]:
        v.append(f"{len(medida['falhas'])} abaixo de AA: {descrever(medida['falhas'], 4)}")
    ignorados = [i for i in medida["ignorados"] if i.get("motivo") != "desabilitado"]
    if ignorados:
        v.append(f"{len(ignorados)} ignorado(s) pelo scanner (gradiente, opacidade...): {descrever(ignorados, 3)}")
    pequenos = fontes_abaixo_de(p.page, 14, raiz="#depoimentos")
    if pequenos:
        v.append(f"texto abaixo de 14 px: {descrever(pequenos, 3)}")
    _exigir([f"{largura}px: {x}" for x in v])


def test_d8_sem_carrossel_nem_animacao_nem_laranja(abrir):
    p = abrir(1280, 900, movimento="no-preference")
    if not p.page.locator("#depoimentos").count():
        _exigir(["não existe a seção #depoimentos"])
    p.page.locator("#depoimentos").scroll_into_view_if_needed(timeout=TIMEOUT)
    p.page.wait_for_timeout(800)
    medir = _JS_BASE + r"""
    () => {
      const s = document.getElementById('depoimentos');
      const todos = Array.from(s.querySelectorAll('*'));
      return {
        rolantes: todos.filter(e => ['auto', 'scroll'].includes(getComputedStyle(e).overflowX) && e.scrollWidth > e.clientWidth + 1).map(desc),
        snap: todos.filter(e => getComputedStyle(e).scrollSnapType !== 'none').map(desc),
        controles: s.querySelectorAll('button, [role="tab"], [role="tablist"], [aria-roledescription], input[type="radio"]').length,
        animacoes: document.getAnimations().filter(a => a.effect && a.effect.target && s.contains(a.effect.target)).length,
        caixas: Array.from(s.querySelectorAll('[data-testid="depoimento-card"]')).map(c => {
          const r = c.getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round).join(','); }) };
    }"""
    antes = p.page.evaluate(medir)
    p.page.wait_for_timeout(1500)
    depois = p.page.evaluate(medir)
    v = []
    if antes["rolantes"] or antes["snap"] or antes["controles"]:
        v.append(f"carrossel: rolagem lateral em {antes['rolantes'][:3]}, scroll-snap em {antes['snap'][:3]}, "
                 f"{antes['controles']} controle(s)")
    if antes["animacoes"] or depois["animacoes"]:
        v.append(f"{max(antes['animacoes'], depois['animacoes'])} animação(ões) rodando na seção em repouso")
    if antes["caixas"] != depois["caixas"]:
        v.append(f"os cartões se moveram em 1,5 s (carrossel automático?): {antes['caixas'][:2]} -> {depois['caixas'][:2]}")
    laranja = p.page.evaluate(_JS_LARANJA, {"raiz": "#depoimentos", "permitido": None, "laranja": LARANJA})
    if laranja:
        v.append(f"laranja na seção de depoimentos: {laranja[:3]}")
    _exigir(v)


# ---------------------------------------------------------------------------------------------------------- rodapé
def test_r1_um_so_footer_escuro_com_logo_oficial(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const f = document.querySelector('footer[data-testid="rodape"]');
      const todos = document.querySelectorAll('footer');
      const imgs = f ? Array.from(f.querySelectorAll('img')).map(i => ({ alt: i.getAttribute('alt'), src: (i.getAttribute('src') || '').slice(0, 24),
        natural: i.naturalWidth, visivel: visivel(i) })) : [];
      return { nFooters: todos.length, primeiroEhORodape: todos[0] === f, existe: !!f, paiBody: !!(f && f.parentElement === document.body),
               dentroDoMain: !!(f && f.closest('main')), fundo: f ? getComputedStyle(f).backgroundColor : null,
               visivel: visivel(f), imgs, discos: f ? Array.from(f.querySelectorAll('.logo-circle')).length : 0,
               depoisDoMain: !!(f && document.querySelector('main') && (document.querySelector('main').compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING)) };
    }""")
    v = []
    if not info["existe"]:
        _exigir(["não existe <footer data-testid=\"rodape\">"])
    if info["nFooters"] != 1 or not info["primeiroEhORodape"]:
        v.append(f"{info['nFooters']} elementos <footer> na página (esperado só o do rodapé)")
    if not info["paiBody"] or info["dentroDoMain"] or not info["depoisDoMain"]:
        v.append("o rodapé tem de ser filho direto do <body>, fora e depois do <main>")
    if info["fundo"] != ESCURO:
        v.append(f"fundo do rodapé {info['fundo']} (esperado {ESCURO})")
    if not info["visivel"]:
        v.append("o rodapé não está visível")
    logos = [i for i in info["imgs"] if i["alt"] == ALT_LOGO and i["visivel"]]
    if len(logos) != 1 or not logos[0]["natural"] or not logos[0]["src"].startswith("data:image/"):
        v.append(f"logo do rodapé: {info['imgs']} (esperado 1 <img alt={ALT_LOGO!r}> data: URI carregada)")
    if info["discos"]:
        v.append("disco 'GT' (.logo-circle) no rodapé")
    if p.page.get_by_role("contentinfo").count() != 1:
        v.append(f"{p.page.get_by_role('contentinfo').count()} landmark(s) contentinfo (esperado 1)")
    _exigir(v)


def test_r2_descricao_literal_do_site_antigo(abrir):
    p = abrir(1280, 900)
    d = _info(p.page, "rodape-descricao")
    v = []
    if not d["noRodape"] or not d["visivel"]:
        v.append("rodape-descricao fora do rodapé ou invisível")
    if _norm(d["texto"]) != DESCRICAO:
        v.append(f"texto {d['texto']!r} (esperado o do site antigo: {DESCRICAO!r})")
    if d["fonte"] < 14:
        v.append(f"fonte {d['fonte']}px (mínimo 14)")
    _exigir(v)


def test_r3_redes_sociais(abrir):
    p = abrir(1280, 900)
    v = []
    for chave, nome, url in REDES:
        tid = f"rodape-social-{chave}"
        d = p.page.evaluate(_JS_INFO, tid)
        if d["n"] != 1:
            v.append(f"{tid}: {d['n']} elemento(s) (esperado 1)")
            continue
        if d["tag"] != "A" or d["href"] != url:
            v.append(f"{tid}: <{d['tag'].lower()}> href {d['href']!r} (esperado <a> {url!r})")
        if d["target"] != "_blank" or not _tem_rel_seguro(d["rel"]):
            v.append(f"{tid}: target {d['target']!r}, rel {d['rel']!r} (esperado _blank com noopener noreferrer)")
        if d["aria"] != nome:
            v.append(f"{tid}: aria-label {d['aria']!r} (esperado {nome!r})")
        elif p.page.locator("footer").get_by_role("link", name=nome, exact=True).count() != 1:
            v.append(f"{tid}: o link não tem o nome acessível {nome!r}")
        if not d["svgs"] or d["imgs"] or not d["svgOculto"]:
            v.append(f"{tid}: ícone tem de ser SVG inline com aria-hidden ({d['svgs']} svg, {d['imgs']} img)")
        if not d["noRodape"] or not d["visivel"]:
            v.append(f"{tid}: fora do rodapé ou invisível")
        elif not _alvo_ok(d):
            v.append(f"{tid}: alvo {d['w']:.0f}x{d['h']:.0f}px (mínimo 44x44)")
        elif d["svgs"]:
            alvo = p.page.locator(f'[data-testid="{tid}"]')
            alvo.scroll_into_view_if_needed(timeout=TIMEOUT)
            if _pixels_que_contrastam_no_centro(alvo.screenshot()) < 25:
                v.append(f"{tid}: o ícone SVG não aparece pintado com contraste >= 3:1 sobre o fundo")
    _exigir(v)


def test_r4_contato_enderecos_e_links_exatos(abrir):
    p = abrir(1280, 900)
    v = []
    for tid, texto, href, nova_aba in CONTATOS:
        d = p.page.evaluate(_JS_INFO, tid)
        if d["n"] != 1:
            v.append(f"{tid}: {d['n']} elemento(s) (esperado 1)")
            continue
        if d["tag"] != "A" or d["href"] != href:
            v.append(f"{tid}: <{d['tag'].lower()}> href {d['href']!r} (esperado <a> {href!r})")
        if _norm(d["texto"]) != texto:
            v.append(f"{tid}: texto {d['texto']!r} (esperado {texto!r})")
        if nova_aba and (d["target"] != "_blank" or not _tem_rel_seguro(d["rel"])):
            v.append(f"{tid}: target {d['target']!r}, rel {d['rel']!r} (esperado _blank com noopener noreferrer)")
        if not d["noRodape"] or not d["visivel"]:
            v.append(f"{tid}: fora do rodapé ou invisível")
        if d["fonte"] < 14:
            v.append(f"{tid}: fonte {d['fonte']}px (mínimo 14)")
    _exigir(v)


def test_r5_navegacao_um_nav_com_tres_links_e_destinos(abrir):
    p = abrir(1280, 900)
    info = p.page.evaluate(_JS_BASE + r"""
    () => {
      const f = document.querySelector('footer[data-testid="rodape"]');
      if (!f) return null;
      const navs = Array.from(f.querySelectorAll('nav'));
      const n = navs[0];
      const links = n ? Array.from(n.querySelectorAll('a')).map(a => ({ tid: a.getAttribute('data-testid'), texto: txt(a),
        href: a.getAttribute('href'), existe: !!document.getElementById((a.getAttribute('href') || '').slice(1)),
        topoY: (document.getElementById((a.getAttribute('href') || '').slice(1)) || { getBoundingClientRect: () => ({ top: -1 }) })
                 .getBoundingClientRect().top + scrollY })) : [];
      return { nNavs: navs.length, aria: n ? n.getAttribute('aria-label') : null, links,
               navsDaPagina: Array.from(document.querySelectorAll('nav')).map(x => x.getAttribute('aria-label')) };
    }""")
    if info is None:
        _exigir(["não existe o rodapé"])
    v = []
    if info["nNavs"] != 1:
        v.append(f"{info['nNavs']} <nav> no rodapé (esperado 1)")
    elif not (info["aria"] or "").strip() or _norm(info["aria"]) == "Principal":
        v.append(f"aria-label do <nav> do rodapé {info['aria']!r} (esperado um nome, diferente de 'Principal')")
    elif len(set(info["navsDaPagina"])) != len(info["navsDaPagina"]):
        v.append(f"dois <nav> com o mesmo nome: {info['navsDaPagina']}")
    if len(info["links"]) != 3:
        v.append(f"{len(info['links'])} links no <nav> do rodapé (esperado exatamente 3): {[l['texto'] for l in info['links']]}")
    for tid, texto, href, destino in NAVEGACAO:
        d = p.page.evaluate(_JS_INFO, tid)
        if d["n"] != 1:
            v.append(f"{tid}: {d['n']} elemento(s) (esperado 1)")
            continue
        if d["tag"] != "A" or d["href"] != href or _norm(d["texto"]) != texto:
            v.append(f"{tid}: <{d['tag'].lower()}> {d['texto']!r} -> {d['href']!r} (esperado <a> {texto!r} -> {href!r})")
        achado = next((l for l in info["links"] if l["tid"] == tid), None)
        if not achado:
            v.append(f"{tid}: não está dentro do <nav> do rodapé")
        elif not achado["existe"]:
            v.append(f"{tid}: o destino {href} não existe no DOM")
    for l in info["links"]:
        if _norm(l["texto"]).lower() in PROIBIDOS_COMO_LINK:
            v.append(f"link proibido na navegação: {l['texto']!r}")
    _exigir(v)


@pytest.mark.parametrize("testid,href,destino", [(t, h, d) for t, _, h, d in NAVEGACAO])
def test_r6_clicar_na_navegacao_leva_ao_destino(abrir, testid, href, destino):
    p = abrir(1280, 900)
    link = p.page.locator(f'[data-testid="{testid}"]')
    if link.count() != 1:
        _exigir([f"{testid}: {link.count()} elemento(s) (esperado 1)"])
    link.scroll_into_view_if_needed(timeout=TIMEOUT)
    antes = p.page.evaluate("scrollY")
    assert antes > 500, f"pré-condição: o rodapé fica no fim da página (scrollY {antes})"
    link.click(timeout=TIMEOUT)
    p.page.wait_for_timeout(500)
    estado = p.page.evaluate("""(id) => { const e = document.getElementById(id); const r = e ? e.getBoundingClientRect() : null;
        return { hash: location.hash, existe: !!e, top: r ? r.top : null, scrollY }; }""", destino)
    v = []
    if not estado["existe"]:
        v.append(f"o destino #{destino} não existe")
    if estado["hash"] != href:
        v.append(f"depois do clique o hash é {estado['hash']!r} (esperado {href!r})")
    if destino == "topo":
        if estado["scrollY"] > 4:
            v.append(f"'Home' não levou ao topo (scrollY {estado['scrollY']:.0f})")
    elif estado["existe"] and not (-4 <= estado["top"] <= 240):
        v.append(f"#{destino} ficou a {estado['top']:.0f}px do topo da janela (esperado entre 0 e 240)")
    _exigir(v)


def test_r7_atendimento_duas_linhas(abrir):
    p = abrir(1280, 900)
    d = _info(p.page, "rodape-atendimento")
    linhas = p.page.evaluate(_JS_BASE + r"""
    (alvos) => {
      const raiz = document.querySelector('[data-testid="rodape-atendimento"]');
      return alvos.map(t => {
        const el = [raiz, ...raiz.querySelectorAll('*')].filter(e => txt(e) === t && visivel(e)).pop();
        return el ? caixa(el) : null; });
    }""", list(ATENDIMENTO))
    v = []
    if not d["noRodape"] or not d["visivel"]:
        v.append("rodape-atendimento fora do rodapé ou invisível")
    for texto, caixa in zip(ATENDIMENTO, linhas):
        if caixa is None:
            v.append(f"não há um elemento visível só com o texto {texto!r} dentro de rodape-atendimento (textContent: {d['texto']!r})")
    if all(linhas) and linhas[1]["top"] < linhas[0]["bottom"] - 1:
        v.append("as duas linhas do atendimento não estão uma embaixo da outra")
    if d["fonte"] < 14:
        v.append(f"fonte {d['fonte']}px (mínimo 14)")
    _exigir(v)


def test_r8_botao_fale_conosco(abrir):
    p = abrir(1280, 900)
    d = _info(p.page, "rodape-fale-conosco")
    v = []
    if d["tag"] != "A" or _norm(d["texto"]) != "Fale conosco":
        v.append(f"<{d['tag'].lower()}> com texto {d['texto']!r} (esperado <a> 'Fale conosco')")
    if "btn-cta" not in d["classes"]:
        v.append(f"classes {d['classes']} (esperado btn-cta)")
    if d["href"] != URL_WA_ESCOLA:
        v.append(f"href {d['href']!r} (esperado exatamente {URL_WA_ESCOLA!r}, sem ?text=)")
    if d["target"] != "_blank" or not _tem_rel_seguro(d["rel"]):
        v.append(f"target {d['target']!r}, rel {d['rel']!r} (esperado _blank com noopener noreferrer)")
    if d["fundo"] != LARANJA or d["cor"] != TEXTO:
        v.append(f"fundo {d['fundo']} e texto {d['cor']} (esperado {LARANJA} e {TEXTO})")
    else:
        razao = razao_contraste(d["cor"], d["fundo"])
        if razao < 4.5:
            v.append(f"contraste do texto sobre o laranja {razao:.2f}:1 (mínimo 4,5:1)")
    if not d["noRodape"] or not d["visivel"]:
        v.append("fora do rodapé ou invisível")
    elif not _alvo_ok(d):
        v.append(f"alvo {d['w']:.0f}x{d['h']:.0f}px (mínimo 44x44)")
    if d["fonte"] < 14:
        v.append(f"fonte {d['fonte']}px (mínimo 14)")
    if d["transform"] == "uppercase" and d["espaco"] >= 2:
        v.append("maiúsculas com espaçamento >= 2 px (D4 L1 e DESIGN.md)")
    _exigir(v)


def test_r9_copyright_prototipo_area_funcionario_e_faixa_inferior(abrir):
    v = []
    for largura, altura in ((1280, 900), (390, 844)):
        p = abrir(largura, altura)
        cop, pro = p.page.evaluate(_JS_INFO, "rodape-copyright"), p.page.evaluate(_JS_INFO, "rodape-prototipo")
        func = p.page.evaluate(_JS_INFO, "rodape-area-funcionario")
        for nome, d in (("rodape-copyright", cop), ("rodape-prototipo", pro), ("rodape-area-funcionario", func)):
            if d["n"] != 1:
                v.append(f"{largura}px: {nome}: {d['n']} elemento(s) (esperado 1)")
        if cop["n"] == 1:
            if _norm(cop["texto"]) != COPYRIGHT:
                v.append(f"{largura}px: copyright {cop['texto']!r} (esperado {COPYRIGHT!r})")
            if not cop["noRodape"] or not cop["visivel"] or cop["fonte"] < 14:
                v.append(f"{largura}px: copyright fora do rodapé, invisível ou com fonte {cop['fonte']}px")
        if pro["n"] == 1:
            if PROTOTIPO not in _norm(pro["texto"]):
                v.append(f"{largura}px: nota de protótipo {pro['texto']!r} (esperado conter {PROTOTIPO!r})")
            if not pro["noRodape"] or not pro["visivel"] or pro["fonte"] < 14:
                v.append(f"{largura}px: nota de protótipo fora do rodapé, invisível ou com fonte {pro['fonte']}px")
        if func["n"] == 1:
            if func["tag"] != "A" or _norm(func["texto"]) != "Área do funcionário" or (func["onclick"] or "").strip() != "goToStaffArea(event)":
                v.append(f"{largura}px: Área do funcionário <{func['tag'].lower()}> {func['texto']!r} onclick {func['onclick']!r} "
                         f"(esperado <a> 'Área do funcionário' com onclick 'goToStaffArea(event)')")
            if not func["noRodape"] or not func["visivel"]:
                v.append(f"{largura}px: Área do funcionário fora do rodapé ou invisível")
        # faixa inferior: copyright e nota abaixo de todas as colunas
        if cop["n"] == 1 and pro["n"] == 1:
            colunas = [p.page.evaluate(_JS_INFO, t) for t in
                       ("rodape-endereco", "rodape-whatsapp-escola", "rodape-whatsapp-empresas", "rodape-email", "rodape-nav-home",
                        "rodape-nav-cursos", "rodape-nav-incompany", "rodape-atendimento", "rodape-fale-conosco")]
            if all(c["n"] == 1 for c in colunas):
                fundo_das_colunas = max(c["bottom"] for c in colunas)
                for nome, d in (("copyright", cop), ("nota de protótipo", pro)):
                    if d["top"] < fundo_das_colunas - 1:
                        v.append(f"{largura}px: {nome} começa em {d['top']:.0f}px, acima do fim das colunas ({fundo_das_colunas:.0f}px); "
                                 f"tem de ficar numa faixa inferior")
    _exigir(v)


def test_r10_links_do_rodape_sao_exatamente_os_do_contrato(abrir):
    p = abrir(1280, 900)
    links = p.page.evaluate(_JS_LINKS_DO_RODAPE)
    if links is None:
        _exigir(["não existe o rodapé"])
    v = []
    achados = sorted((l["tid"] or "(sem testid)") for l in links)
    esperados = sorted(TESTIDS_DE_LINK_DO_RODAPE)
    if achados != esperados:
        faltam = [t for t in esperados if t not in achados]
        sobram = [t for t in achados if t not in esperados]
        v.append(f"links do rodapé: faltam {faltam}; sobram {sobram} (esperados exatamente os 12 do contrato)")
    for l in links:
        texto = _norm(l["texto"]).lower()
        if texto in PROIBIDOS_COMO_LINK or _norm(l["aria"] or "").lower() in PROIBIDOS_COMO_LINK:
            v.append(f"link proibido no rodapé: {l['texto'] or l['aria']!r} -> {l['href']!r}")
        if re.search(r"^tel:|twitter\.com|x\.com|linkedin|tiktok|whatsapp\.com|api\.whatsapp", l["href"] or "", re.I):
            v.append(f"link fora do pedido no rodapé: {l['href']!r}")
    todos = p.page.evaluate(_JS_BASE + r"""() => Array.from(document.querySelectorAll('a')).filter(visivel).map(a => txt(a) || a.getAttribute('aria-label') || '')""")
    for t in todos:
        if _norm(t).lower() in ("global ead", "a global training", "contato"):
            v.append(f"link {t!r} na landing (decisão do PM: fora)")
    wa = p.page.evaluate("() => Array.from(document.querySelectorAll('a[href*=\"wa.me\"]')).map(a => a.getAttribute('href'))")
    if sorted(wa) != sorted([URL_WA_ESCOLA, URL_WA_ESCOLA, URL_WA_EMPRESAS]):
        v.append(f"links wa.me da página: {wa} (esperado: escola e Fale conosco para {URL_WA_ESCOLA}, empresas para {URL_WA_EMPRESAS})")
    _exigir(v)


def test_r11_titulos_um_h1_colunas_e_ordem(abrir):
    p = abrir(1280, 900)
    titulos = p.page.evaluate(_JS_TITULOS)
    v = []
    if sum(1 for t in titulos if t["nivel"] == 1) != 1 or titulos[0]["nivel"] != 1:
        v.append(f"h1: {[t['texto'] for t in titulos if t['nivel'] == 1]} (esperado um só, primeiro título da página)")
    anterior = 0
    for t in titulos:
        if anterior and t["nivel"] > anterior + 1:
            v.append(f"título h{t['nivel']} {t['texto']!r} depois de h{anterior}: pulou nível")
        anterior = t["nivel"]
    no_rodape = {t["texto"]: t for t in titulos if t["noRodape"]}
    for nome in TITULOS_DAS_COLUNAS:
        t = no_rodape.get(nome)
        if t is None:
            v.append(f"o rodapé não tem o título {nome!r} (h2, h3 ou h4; título, não link)")
        elif t["nivel"] not in (2, 3, 4):
            v.append(f"título {nome!r} é h{t['nivel']} (esperado h2, h3 ou h4)")
    dep = [t for t in titulos if t["texto"] == "Depoimentos"]
    if len(dep) != 1 or dep[0]["nivel"] != 2:
        v.append(f"título 'Depoimentos': {[(t['nivel'], t['texto']) for t in dep]} (esperado um h2)")
    _exigir(v)


def test_r12_ordem_de_dom_dentro_do_rodape(abrir):
    p = abrir(1280, 900)
    ordem = p.page.evaluate(_JS_BASE + r"""
    (args) => {
      const f = document.querySelector('footer[data-testid="rodape"]');
      if (!f) return null;
      const busca = (chave) => {
        if (chave.startsWith('h:')) return Array.from(f.querySelectorAll('h2,h3,h4')).find(h => txt(h) === chave.slice(2)) || null;
        if (chave === 'logo') return f.querySelector('img');
        return f.querySelector(`[data-testid="${chave}"]`);
      };
      const elementos = args.map(busca);
      const faltam = args.filter((c, i) => !elementos[i]);
      const desordem = [];
      for (let i = 1; i < elementos.length; i++) {
        const a = elementos[i - 1], b = elementos[i];
        if (!a || !b) continue;
        const depois = (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) || (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_CONTAINED_BY);
        if (!depois) desordem.push(`${args[i]} não vem depois de ${args[i - 1]}`);
      }
      return { faltam, desordem };
    }""", ["logo", "rodape-descricao", "rodape-social-facebook", "rodape-social-instagram", "rodape-social-youtube",
           "h:Contato", "rodape-endereco", "rodape-whatsapp-escola", "rodape-whatsapp-empresas", "rodape-email",
           "h:Navegação", "rodape-nav-home", "rodape-nav-cursos", "rodape-nav-incompany",
           "h:Atendimento", "rodape-atendimento", "rodape-fale-conosco", "rodape-copyright", "rodape-prototipo"])
    if ordem is None:
        _exigir(["não existe o rodapé"])
    _exigir([f"falta no rodapé: {c}" for c in ordem["faltam"]] + ordem["desordem"])


@pytest.mark.parametrize("largura,altura", [(1280, 900), (390, 844)])
def test_r13a_alvos_de_44px_nos_links_do_rodape(abrir, largura, altura):
    p = abrir(largura, altura)
    links = p.page.evaluate(_JS_LINKS_DO_RODAPE)
    if not links:
        _exigir(["não há links no rodapé"])
    v = []
    visiveis = [l for l in links if l["visivel"]]
    if len(visiveis) != len(TESTIDS_DE_LINK_DO_RODAPE):
        v.append(f"{len(visiveis)} links visíveis no rodapé (esperado {len(TESTIDS_DE_LINK_DO_RODAPE)})")
    for l in visiveis:
        if l["box"]["w"] + 0.01 < 44 or l["box"]["h"] + 0.01 < 44:
            v.append(f"{l['tid']} '{l['texto'][:30]}' {l['box']['w']:.0f}x{l['box']['h']:.0f}px (mínimo 44x44)")
        nome = l["texto"] or l["aria"]
        if not (nome or "").strip():
            v.append(f"{l['tid']}: link sem nome acessível")
    _exigir([f"{largura}px: {x}" for x in v])


def test_r13b_foco_visivel_em_cada_link_do_rodape(abrir):
    p = abrir(1280, 900)
    links = p.page.evaluate(_JS_LINKS_DO_RODAPE)
    if not links:
        _exigir(["não há links no rodapé"])
    v = []
    for l in links:
        if not l["tid"]:
            v.append("link do rodapé sem data-testid")
            continue
        alvo = p.page.locator(f'[data-testid="{l["tid"]}"]')
        alvo.scroll_into_view_if_needed(timeout=TIMEOUT)
        alvo.evaluate("e => { const t = document.createElement('button'); t.id = '__ancora_foco';"
                      " t.style.cssText = 'position:absolute;opacity:0'; e.parentNode.insertBefore(t, e); t.focus(); }")
        p.page.keyboard.press("Tab")
        foco = p.page.evaluate("document.activeElement === document.querySelector('#__ancora_foco').nextElementSibling")
        medida = alvo.evaluate("""e => { const s = getComputedStyle(e);
            return { largura: s.outlineStyle !== 'none' ? (parseFloat(s.outlineWidth) || 0) : 0, cor: s.outlineColor, sombra: s.boxShadow }; }""")
        p.page.evaluate("document.querySelector('#__ancora_foco').remove()")
        if not foco:
            v.append(f"{l['tid']}: o Tab não levou o foco ao link")
        elif medida["largura"] <= 0 and medida["sombra"] in ("", "none"):
            v.append(f"{l['tid']}: sem foco visível (outline 0 e sem box-shadow)")
        elif medida["largura"] > 0:
            razao = razao_contraste(medida["cor"], ESCURO)
            if razao < 3:
                v.append(f"{l['tid']}: contorno de foco {medida['cor']} com {razao:.2f}:1 sobre o rodapé (mínimo 3:1; use #7fd8f0)")
    _exigir(v)


@pytest.mark.parametrize("largura,altura", [(1280, 900), (390, 844)])
def test_r13c_fonte_14px_e_contraste_aa_no_rodape(abrir, largura, altura):
    p = abrir(largura, altura)
    raiz = 'footer[data-testid="rodape"]'
    medida = varrer_contraste(p.page, raiz=raiz)
    v = []
    if medida["verificados"] < 12:
        v.append(f"só {medida['verificados']} textos medidos no rodapé (esperado >= 12)")
    if medida["falhas"]:
        v.append(f"{len(medida['falhas'])} abaixo de AA: {descrever(medida['falhas'], 4)}")
    ignorados = [i for i in medida["ignorados"] if i.get("motivo") != "desabilitado"]
    if ignorados:
        v.append(f"{len(ignorados)} ignorado(s) pelo scanner (gradiente, opacidade...): {descrever(ignorados, 3)}")
    pequenos = fontes_abaixo_de(p.page, 14, raiz=raiz)
    if pequenos:
        v.append(f"texto abaixo de 14 px: {descrever(pequenos, 4)}")
    _exigir([f"{largura}px: {x}" for x in v])


def test_r13d_laranja_so_no_fale_conosco(abrir):
    p = abrir(1280, 900)
    if not p.page.locator('footer[data-testid="rodape"]').count():
        _exigir(["não existe o rodapé"])
    v = []
    n_cta = p.page.evaluate("document.querySelectorAll('footer[data-testid=\"rodape\"] .btn-cta').length")
    if n_cta != 1:
        v.append(f"{n_cta} elementos .btn-cta no rodapé (esperado 1, o Fale conosco)")
    laranja = p.page.evaluate(_JS_LARANJA, {"raiz": 'footer[data-testid="rodape"]',
                                            "permitido": '[data-testid="rodape-fale-conosco"]', "laranja": LARANJA})
    if laranja:
        v.append(f"laranja fora do Fale conosco no rodapé: {laranja[:3]}")
    _exigir(v)


def test_r14_desktop_colunas_lado_a_lado(abrir):
    p = abrir(1280, 900)
    titulos = {t["texto"]: t for t in p.page.evaluate(_JS_TITULOS) if t["noRodape"]}
    faltam = [n for n in TITULOS_DAS_COLUNAS if n not in titulos]
    if faltam:
        _exigir([f"faltam os títulos de coluna {faltam} no rodapé"])
    c, n, a = (titulos[x]["box"] for x in TITULOS_DAS_COLUNAS)
    v = []
    if max(c["top"], n["top"], a["top"]) - min(c["top"], n["top"], a["top"]) > 8:
        v.append(f"1280px: títulos em alturas diferentes (Contato {c['top']:.0f}, Navegação {n['top']:.0f}, "
                 f"Atendimento {a['top']:.0f}); as colunas têm de ficar lado a lado")
    if not (c["left"] + 60 <= n["left"] and n["left"] + 60 <= a["left"]):
        v.append(f"1280px: ordem horizontal errada (left Contato {c['left']:.0f}, Navegação {n['left']:.0f}, "
                 f"Atendimento {a['left']:.0f}); esperado Contato, Navegação, Atendimento da esquerda para a direita")
    geral = p.page.evaluate(_JS_LARGURA, None)
    if geral["scrollWidth"] > 1280:
        v.append(f"1280px: rolagem horizontal (scrollWidth {geral['scrollWidth']})")
    _exigir(v)


def test_r15_celular_colunas_empilhadas_sem_rolagem_horizontal(abrir):
    p = abrir(390, 844)
    titulos = {t["texto"]: t for t in p.page.evaluate(_JS_TITULOS) if t["noRodape"]}
    faltam = [n for n in TITULOS_DAS_COLUNAS if n not in titulos]
    if faltam:
        _exigir([f"faltam os títulos de coluna {faltam} no rodapé"])
    caixas = [titulos[x]["box"] for x in TITULOS_DAS_COLUNAS]
    v = []
    for anterior, atual, nome in zip(caixas, caixas[1:], TITULOS_DAS_COLUNAS[1:]):
        if atual["top"] < anterior["bottom"] - 1:
            v.append(f"390px: {nome} não fica abaixo da coluna anterior (top {atual['top']:.0f} < {anterior['bottom']:.0f})")
        if abs(atual["left"] - caixas[0]["left"]) > 8:
            v.append(f"390px: {nome} não está alinhado à primeira coluna (left {atual['left']:.0f} vs {caixas[0]['left']:.0f})")
    medida = p.page.evaluate(_JS_LARGURA, 'footer[data-testid="rodape"]')
    geral = p.page.evaluate(_JS_LARGURA, None)
    if medida["fora"]:
        v.append(f"390px: no rodapé, fora da tela: {medida['fora'][:4]}")
    if geral["scrollWidth"] > 390 or geral["fora"]:
        v.append(f"390px: rolagem horizontal (scrollWidth {geral['scrollWidth']}; fora: {geral['fora'][:4]})")
    _exigir(v)


def test_r16_sem_emojis_e_sem_maiusculas_espacadas_nas_regioes_novas(abrir):
    p = abrir(1280, 900)
    v = []
    for nome, sel in (("depoimentos", "#depoimentos"), ("rodapé", 'footer[data-testid="rodape"]')):
        info = p.page.evaluate(_JS_REGIAO, sel)
        if info is None:
            v.append(f"não existe {nome} ({sel})")
            continue
        if EMOJI.search(info["texto"]) or EMOJI.search(info["atributos"]):
            v.append(f"emoji em {nome}")
        if info["espacados"]:
            v.append(f"rótulo em maiúsculas espaçadas em {nome}: {info['espacados'][:3]}")
    _exigir(v)


@pytest.mark.parametrize("largura,altura", [(1280, 900), (390, 844)])
def test_k1_sem_erros_de_console_nas_duas_larguras(abrir, largura, altura):
    p = abrir(largura, altura)
    existe = p.page.evaluate("() => !!document.querySelector('footer[data-testid=\"rodape\"]') && "
                             "!!document.getElementById('depoimentos')")
    v = list(dict.fromkeys(p.erros))
    if not existe:
        v.append("a landing ainda não tem o rodapé novo e a seção de depoimentos (nada a medir)")
    _exigir(v)
