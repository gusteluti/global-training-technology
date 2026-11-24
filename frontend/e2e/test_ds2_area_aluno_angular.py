"""E2E da DS2 (D115, docs/tdd/PLANO_DESIGN.md) — área do aluno: contraste AA completo, piso de 14 px, faixa de números,
status nunca só por cor, laranja só na conversão (D-B), estado vazio com próxima ação, uma ação principal por cartão,
nenhum texto em #0096c7 e as guardas da DS1 (h1, rótulo, 44 px, 390 px).

Regra da D115: só design. Nenhuma rota, API, fluxo, permissão, texto de erro, data-testid ou texto que os e2e antigos
leem muda (E3/E4/E5/B2/D2/X1/X2/F5a/S1 continuam sendo a rede). Tudo é medido no estilo COMPUTADO do Chromium com os
helpers da DS0 (`apoio_contraste.py`) e o verificador da DS1 (`_JS_MEDIR` de `test_ds1_componentes_angular.py`).

Seed (harness isolado D58; como o seed da D2/D3, com dados de tamanho realista):
  aluna principal: matrícula `active` (pagamento aprovado há 1 dia, 2 materiais, 1 concluído -> progresso 1 de 2, sem
                   certificado) e matrícula `pending` (pagamento pendente há 2 dias) em outro curso
  conta vazia:     aluno sem nenhuma matrícula nem pagamento
  catálogo:        os dois cursos acima e um terceiro, sem matrícula, com uma turma aberta (F5a); no /catalogo a turma
                   é escolhida antes da medida, para o botão de compra ficar habilitado

Telas (cada uma a 1366 e a 390 px de largura, mouse parado no canto, movimento reduzido):
  /student                (aluna principal; aba "Meus cursos"; o chat do aluno com uma troca respondida na tela. R3-4, D126: o chat
                           é o painel do botão flutuante, aberto durante a medida desta tela e fechado antes de abrir a aba Financeiro: a 390 px o painel
                           cobre a barra de abas)
  /student (aba Financeiro) (a mesma aluna, depois de clicar na aba "Financeiro": R3-3, D125, só o painel da aba ativa
                           existe no DOM)
  /student (sem matrícula) (conta vazia; estado vazio de "Meus cursos")
  /student (sem matrícula, aba Financeiro) (conta vazia; estado vazio do histórico financeiro)
  /student/perfil
  /student/curso/:id      (matrícula ativa; o chat da sala com uma troca respondida na tela)
  /catalogo
"Uma resposta na tela": a pergunta passa pelo backend de teste (Groq falso); a resposta do POST /api/student/chat é
interceptada só para garantir `sources` (uma fonte) e `pii_masked: true` quando vierem vazios, para a nota de fonte e o
aviso de dados pessoais (`chat-fonte`, `chat-aviso-pii`, `.sala-chat-nota`) estarem na tela — como na GR3 (P1).

test_ds2_apoio_verificador (sem servidor; valida os medidores desta entrega numa página sintética, passa no red):
  V1 faixa de números correta não gera violação; com três cartões soltos, cada defeito é apontado
  V2 badge com ponto aria-hidden, com ::before e com prefixo passa; badge só com cor é apontado
  V3 varredura de #0096c7 pega texto grande; varredura de laranja aceita só os permitidos

test_ds2_area_aluno — cenários (cada um lista TODAS as violações de todas as telas, não para na primeira):
  P0 pré-condição do seed: a aluna vê 2 cartões (Ativa e Pendente), 2 pagamentos (Aprovado e Pendente), o resumo com
     os três valores; a conta vazia vê os dois textos de estado vazio; as duas trocas de chat estão na tela [passa no red]
  A1 contraste AA completo (scanner da DS0 sem filtro de seletor) em todas as telas e larguras: zero falhas
  A2 zero itens ignorados por "texto sobre imagem ou gradiente" (heróis com fundo sólido); demais ignorados só informados
  F1 nenhum texto visível abaixo de 14 px (badges, rótulos do resumo, datas, nota do chat da sala, botões do chat)
  N1 faixa de números (na aluna e na conta vazia): um único [data-testid=aluno-resumo] com os três valores; borda própria nos quatro lados; sem
     `.card` nem sombra dentro; divisória (borda) entre itens vizinhos; nenhum item com borda nos quatro lados
  N2 valores na cor rgb(23, 33, 43) e com `tabular-nums`; cada valor ligado ao seu rótulo ("Cursos ativos",
     "Pagamentos pendentes", "Total investido") por dl/dt/dd, aria-labelledby ou aria-label
  N3 a 390 px (e a 1366): itens sem sobreposição, valores sem estouro (scrollWidth <= clientWidth) e dentro do contêiner,
     contêiner dentro da tela
  S1 cada status de matrícula (.badge do cartão) e de pagamento (.badge do histórico): texto + sinal não cromático
     (filho aria-hidden visível, ::before/::after visível, ou prefixo não alfanumérico) e contraste AA do badge
  L1 conversão em laranja: [data-testid=atalho-catalogo] e cada [data-testid=catalogo-comprar] com fundo
     rgb(255, 122, 24) e texto rgb(23, 33, 43) (>= 4,5:1)
  L2 nenhum outro elemento das telas do aluno com fundo ou texto rgb(255, 122, 24) (imagens ficam de fora)
  E1 conta vazia, "Meus cursos": o texto "Você ainda não tem matrículas." e um link/botão visível que leva a /catalogo
  E2 conta vazia, histórico financeiro: o texto "Você ainda não tem pagamentos registrados." e um link/botão para
     /catalogo
  C1 cartão da matrícula ativa: exatamente um .btn-primary visível, o [data-testid=curso-entrar]; as demais ações sem
     .btn-primary e sem o fundo do botão principal
  C2 cartão da matrícula pendente: no máximo um .btn-primary, e se houver é a ação de retomar/pagar
  T1 nenhum texto (de qualquer tamanho, inclusive grande) com cor #0096c7 = rgb(0, 150, 199); como na DS0 F10, ficam de
     fora elementos aria-hidden (ícones decorativos) e conteúdo gerado por ::before/::after
  G1/G2/G3/G4 guardas da DS1 nessas telas: um h1 / rótulo em todo campo / alvos >= 44 px / sem rolagem a 390 px
  K1 sem exceções de página nem erros 4xx/5xx de /api no console

Escolhas do agente-testes (modo autônomo D40), registradas no relatório:
  - "Borda única" = borda no contêiner nos quatro lados; "divisória" = borda (qualquer lado entre os dois itens) num
    dos itens vizinhos. Divisória feita só com pseudo-elemento ou fundo não é reconhecida.
  - Ícones decorativos aria-hidden e conteúdo de ::before/::after ficam fora da checagem de #0096c7 (o PLANO_DESIGN
    reserva o #0096c7 para "preenchimentos, bordas e ícones").
  - O certificado (outro .btn-primary no cartão ativo) não aparece neste seed (progresso parcial); C1 não cobre o
    cartão com o curso concluído.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds2_area_aluno_angular.py -s
"""

import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_assistente_flutuante import abrir_assistente, fechar_assistente  # noqa: E402
from apoio_contraste import descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402
from test_ds1_componentes_angular import _JS_MEDIR  # noqa: E402  (verificador da DS1: h1, rótulo, alvo, 390 px)

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
LARGURAS = (1366, 390)
SENHA = "senha-aluno-ds2-2026"
TEXTO = "rgb(23, 33, 43)"       # #17212b
LARANJA = "rgb(255, 122, 24)"   # #ff7a18
TEAL = "rgb(0, 150, 199)"       # #0096c7
ALVO_MIN = 44.0
VAZIO_CURSOS = "Você ainda não tem matrículas."
VAZIO_PAGAMENTOS = "Você ainda não tem pagamentos registrados."
RESUMO = (("resumo-cursos-ativos", "Cursos ativos"),
          ("resumo-pagamentos-pendentes", "Pagamentos pendentes"),
          ("resumo-total-investido", "Total investido"))
FONTE_FIXTURE = "Cancelamento e reembolso"
PERGUNTA_CHAT = "Como funciona o cancelamento e o reembolso do curso?"


class Falha(Exception):
    pass


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


# ------------------------------------------------------------------------------------------------- medidores (JS)
_JS_UTIL = r"""
const DS2_APOIO = true;  // o Playwright trata texto que começa com "function" como uma função só
function visivel(el) {
  if (el.closest('[aria-hidden="true"]')) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility !== 'visible' || cs.display === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  if (el.getClientRects().length === 0) return false;
  return true;
}
function textoProprio(el) {
  let t = '';
  for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent;
  return t.replace(/\s+/g, ' ').trim();
}
function desc(el) {
  let s = el.tagName.toLowerCase();
  const tid = el.getAttribute('data-testid');
  if (tid) s += `[data-testid=${tid}]`;
  else if (el.id) s += '#' + el.id;
  else if (el.classList.length) s += '.' + Array.from(el.classList).slice(0, 3).join('.');
  return s;
}
function norm(s) { return (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim(); }
function alfa(cor) {
  const m = (cor || '').match(/rgba?\(([^)]+)\)/);
  if (!m) return 0;
  const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat);
  return p.length > 3 ? p[3] : 1;
}
function borda(el, lado) {
  const cs = getComputedStyle(el);
  const w = parseFloat(cs[`border${lado}Width`]) || 0;
  const st = cs[`border${lado}Style`];
  return w >= 0.9 && st !== 'none' && st !== 'hidden' && alfa(cs[`border${lado}Color`]) > 0;
}
const LADOS = ['Top', 'Right', 'Bottom', 'Left'];
"""

# Faixa de números (N1/N2/N3). Devolve {v, n1, n2, n3} (listas de violações; n1 já inclui v).
_JS_RESUMO = _JS_UTIL + r"""
function valoresSoltos(args, valores, n2, n3, c) {
  const rc = c ? c.getBoundingClientRect() : { left: 0, right: window.innerWidth };
  valores.forEach((el, i) => {
    if (!el) return;
    const [id, rotulo] = args.ids[i];
    const cs = getComputedStyle(el);
    if (cs.color !== args.texto) n2.push(`[data-testid=${id}] com cor ${cs.color} (esperado ${args.texto})`);
    if (!(cs.fontVariantNumeric || '').includes('tabular-nums')) n2.push(`[data-testid=${id}] sem tabular-nums (font-variant-numeric: ${cs.fontVariantNumeric})`);
    // rótulo ligado ao valor
    let ligado = false, como = '';
    const dd = el.closest('dd');
    if (dd && (!c || c.contains(dd)) && dd.closest('dl')) {
      let p = dd.previousElementSibling; while (p && p.tagName !== 'DT') p = p.previousElementSibling;
      if (!p && dd.parentElement && dd.parentElement.tagName === 'DIV') { const dt = dd.parentElement.querySelector(':scope > dt'); if (dt) p = dt; }
      if (p && norm(p.textContent) === rotulo && visivel(p)) { ligado = true; como = 'dl/dt/dd'; }
      else como = `dt ${p ? JSON.stringify(norm(p.textContent)) : 'ausente'}`;
    }
    for (let a = el; !ligado && a && a !== (c ? c.parentElement : document.body); a = a.parentElement) {
      const ids = (a.getAttribute('aria-labelledby') || '').trim();
      if (ids) {
        const t = norm(ids.split(/\s+/).map(x => (document.getElementById(x) || {}).textContent || '').join(' '));
        if (t.includes(rotulo)) { ligado = true; como = 'aria-labelledby'; }
      }
      if (!ligado && norm(a.getAttribute('aria-label')).includes(rotulo)) { ligado = true; como = 'aria-label'; }
    }
    if (!ligado) n2.push(`[data-testid=${id}] sem rótulo "${rotulo}" ligado (dl/dt/dd, aria-labelledby ou aria-label; ${como || 'nenhum'})`);
    if (el.scrollWidth > el.clientWidth + 1) n3.push(`[data-testid=${id}] estoura a caixa (scrollWidth ${el.scrollWidth} > ${el.clientWidth})`);
    const r = el.getBoundingClientRect();
    if (r.left < rc.left - 0.5 || r.right > rc.right + 0.5) n3.push(`[data-testid=${id}] de ${Math.round(r.left)} a ${Math.round(r.right)}px, fora do contêiner/tela (${Math.round(rc.left)} a ${Math.round(rc.right)}px)`);
  });
}

(args) => {
  const v = [];
  const conts = Array.from(document.querySelectorAll('[data-testid="aluno-resumo"]'));
  if (conts.length !== 1) v.push(`${conts.length} [data-testid=aluno-resumo] no DOM (esperado 1 contêiner único)`);
  const c = conts.find(visivel) || conts[0];
  const valores = args.ids.map(([id]) => document.querySelector(`[data-testid="${id}"]`));
  args.ids.forEach(([id], i) => { if (!valores[i]) v.push(`[data-testid=${id}] ausente`); });
  const n1 = v.slice(), n2 = [], n3 = [];
  // Sem o contêiner, N2 e N3 continuam medindo os valores (contra a tela) para listar tudo de uma vez.
  if (!c) { valoresSoltos(args, valores, n2, n3); return { v, n1, n2, n3 }; }
  if (!visivel(c)) n1.push('[data-testid=aluno-resumo] não está visível');
  valores.forEach((el, i) => { if (el && !c.contains(el)) n1.push(`[data-testid=${args.ids[i][0]}] fora do [data-testid=aluno-resumo]`); });

  // borda única no contêiner, sem cartões nem sombras por dentro
  const semBorda = LADOS.filter(l => !borda(c, l));
  if (semBorda.length) n1.push(`contêiner sem borda em ${semBorda.join('/')} (border ${getComputedStyle(c).border})`);
  const cartoes = Array.from(c.querySelectorAll('.card'));
  if (cartoes.length) n1.push(`${cartoes.length} .card dentro da faixa (cartões soltos por item)`);
  const sombras = Array.from(c.querySelectorAll('*')).filter(e => getComputedStyle(e).boxShadow !== 'none');
  if (sombras.length) n1.push(`sombra por item: ${sombras.slice(0, 4).map(e => `${desc(e)} (${getComputedStyle(e).boxShadow})`).join('; ')}`);

  // itens: filho do menor ancestral comum que contém os três valores
  const presentes = valores.filter(Boolean);
  let itens = [];
  if (presentes.length === 3 && valores.every(el => c.contains(el))) {
    let lca = presentes[0].parentElement;
    while (lca && !presentes.every(el => lca.contains(el))) lca = lca.parentElement;
    itens = presentes.map(el => { let a = el; while (a.parentElement !== lca) a = a.parentElement; return a; });
    if (new Set(itens).size !== 3) { n1.push('os três valores não estão em itens separados'); itens = []; }
  }
  // grupo do item: no dl "achatado" (dt, dd, dt, dd) o rótulo dt anterior faz parte do item
  const grupo = it => {
    const g = [it];
    if (it.tagName === 'DD') { let p = it.previousElementSibling; while (p && p.tagName !== 'DT') p = p.previousElementSibling; if (p) g.push(p); }
    return g;
  };
  if (itens.length === 3) {
    for (const it of itens) {
      for (const el of grupo(it)) {
        if (LADOS.every(l => borda(el, l))) n1.push(`item ${desc(el)} com borda nos quatro lados (cartão por item)`);
      }
    }
    const ordem = itens.slice().sort((a, b) => {
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return Math.abs(ra.top - rb.top) > 4 ? ra.top - rb.top : ra.left - rb.left;
    });
    for (let i = 1; i < ordem.length; i++) {
      const atual = grupo(ordem[i]), anterior = grupo(ordem[i - 1]);
      const ok = atual.some(el => borda(el, 'Left') || borda(el, 'Top'))
              || anterior.some(el => borda(el, 'Right') || borda(el, 'Bottom'));
      if (!ok) n1.push(`sem divisória entre ${desc(ordem[i - 1])} e ${desc(ordem[i])}`);
    }
    // N3: sobreposição entre itens
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) {
      const a = itens[i].getBoundingClientRect(), b = itens[j].getBoundingClientRect();
      const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ix > 1 && iy > 1) n3.push(`itens ${desc(itens[i])} e ${desc(itens[j])} se sobrepõem`);
    }
  }

  const rc = c.getBoundingClientRect();
  if (rc.right > window.innerWidth + 0.5 || rc.left < -0.5) n3.push(`contêiner de ${Math.round(rc.left)} a ${Math.round(rc.right)}px (tela ${window.innerWidth}px)`);
  valoresSoltos(args, valores, n2, n3, c);
  return { v, n1, n2, n3 };
}
"""

# Badges de status (S1). Devolve [{texto, sinais, onde}].
_JS_BADGES = _JS_UTIL + r"""
(args) => {
  const out = [];
  for (const b of document.querySelectorAll(args.sel)) {
    if (!visivel(b)) continue;
    const texto = norm(b.innerText);
    const sinais = [];
    for (const f of b.querySelectorAll('[aria-hidden="true"]')) {
      const r = f.getBoundingClientRect(), cs = getComputedStyle(f);
      if (r.width >= 2 && r.height >= 2 && cs.visibility === 'visible' && cs.display !== 'none') sinais.push(`filho aria-hidden ${f.tagName.toLowerCase()}`);
    }
    for (const ps of ['::before', '::after']) {
      const cs = getComputedStyle(b, ps);
      const ct = cs.content;
      if (!ct || ct === 'none' || ct === 'normal' || cs.display === 'none') continue;
      const temTexto = !/^(""|'')$/.test(ct);
      const w = parseFloat(cs.width) || 0, h = parseFloat(cs.height) || 0;
      const desenho = w >= 2 && h >= 2 && (alfa(cs.backgroundColor) > 0 || LADOS.some(l => (parseFloat(cs[`border${l}Width`]) || 0) > 0)
                      || (cs.backgroundImage && cs.backgroundImage !== 'none'));
      if (temTexto || desenho) sinais.push(`${ps} ${ct.slice(0, 12)}`);
    }
    for (const s of b.querySelectorAll('svg, img, i')) {
      const r = s.getBoundingClientRect();
      if (r.width >= 2 && r.height >= 2 && (s.closest('[aria-hidden="true"]') || s.getAttribute('alt') === '')) sinais.push(`ícone ${s.tagName.toLowerCase()}`);
    }
    if (/^[^\p{L}\p{N}]/u.test(texto)) sinais.push(`prefixo ${JSON.stringify(texto[0])}`);
    const card = b.closest('[data-testid="curso-card"]');
    const onde = card ? `cartão "${norm((card.querySelector('.curso-nome, h5, h2') || {}).textContent).slice(0, 40)}"` : 'histórico financeiro';
    out.push({ texto, sinais: Array.from(new Set(sinais)), onde, temLetra: /\p{L}/u.test(texto) });
  }
  return out;
}
"""

# Cor exata em texto ou fundo (T1/L2). `cor`: rgb alvo; `fundo`: também olhar backgroundColor; `permitidos`: seletores.
_JS_COR = _JS_UTIL + r"""
(args) => {
  const achados = [];
  const PULAR = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'IMG', 'PICTURE', 'SOURCE', 'svg']);
  for (const el of document.body.querySelectorAll('*')) {
    if (PULAR.has(el.tagName) || el.closest('svg')) continue;
    if (args.permitidos.length && args.permitidos.some(s => el.matches(s))) continue;
    const cs = getComputedStyle(el);
    const texto = textoProprio(el);
    const comTexto = !!texto && !['INPUT', 'TEXTAREA', 'SELECT', 'OPTION'].includes(el.tagName);
    if (!visivel(el)) continue;
    const tam = parseFloat(cs.fontSize);
    if (comTexto && cs.color === args.cor) achados.push(`texto ${desc(el)} '${texto.slice(0, 40)}' ${tam}px/${cs.fontWeight}`);
    if (args.fundo && cs.backgroundColor === args.cor) achados.push(`fundo ${desc(el)} '${norm(el.innerText).slice(0, 40)}'`);
  }
  return achados;
}
"""

# Cartão de curso (C1/C2): botões visíveis.
_JS_CARTAO = _JS_UTIL + r"""
(card) => {
  const out = [];
  for (const b of card.querySelectorAll('button, .btn, a.btn')) {
    if (!visivel(b)) continue;
    const cs = getComputedStyle(b);
    out.push({ desc: desc(b), texto: norm(b.innerText).slice(0, 40), primario: b.classList.contains('btn-primary'),
               testid: b.getAttribute('data-testid') || '', fundo: cs.backgroundColor });
  }
  return out;
}
"""

# Link para /catalogo visível dentro de uma seção (E1/E2).
_JS_LINK_CATALOGO = _JS_UTIL + r"""
(sel) => {
  const s = document.querySelector(sel);
  if (!s) return { existe: false, links: [], botoes: [] };
  const links = [], botoes = [];
  for (const a of s.querySelectorAll('a[href]')) {
    if (!visivel(a)) continue;
    try { if (new URL(a.href, location.href).pathname.replace(/\/$/, '') === '/catalogo') links.push(`${desc(a)} '${norm(a.innerText).slice(0, 40)}'`); } catch (e) {}
  }
  s.querySelectorAll('button, [role="link"]').forEach((b, i) => { if (visivel(b)) botoes.push(i); });
  return { existe: true, links, botoes, texto: norm(s.innerText) };
}
"""


# ------------------------------------------------------------------------------------------------- seed
def _api(api, metodo, caminho, corpo=None, token=None, formulario=None):
    cab = {}
    dados = None
    if formulario is not None:
        dados = urllib.parse.urlencode(formulario).encode()
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        cab["Content-Type"] = "application/json"
    if token:
        cab["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api + caminho, data=dados, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def _agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ts(delta=timedelta(0)):
    return (_agora() - delta).strftime("%Y-%m-%d %H:%M:%S")


def semear(amb):
    api, db_path = amb["api"], amb["db_path"]
    st, corpo = _api(api, "POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if st != 200:
        raise RuntimeError(f"seed: login da Gestão HTTP {st}")
    token = corpo["access_token"]
    suf = uuid.uuid4().hex[:6]

    def curso(cid, nome, preco, materiais):
        dados = {"id": cid, "name": nome, "description": f"Descrição do {nome}", "price": preco, "duration_hours": 20,
                 "level": "Intermediario", "target_audience": "Profissionais", "objectives": ["Objetivo"],
                 "topics": ["Tópico"], "benefits": ["Benefício"], "faq": [{"question": "Pergunta", "answer": "Resposta"}],
                 "system_prompt": "Prompt", "materials": materiais}
        st, _ = _api(api, "POST", "/api/admin/create-course", dados, token)
        if st != 200:
            raise RuntimeError(f"seed: create-course {cid} HTTP {st}")
        return {"id": cid, "nome": nome, "materiais": materiais}

    ativo = curso(f"ds2-{suf}", f"Excel Profissional para Gestão Financeira {suf}", 480.0, [
        {"title": "Apostila de fórmulas", "url": f"https://materiais.test/ds2-{suf}/apostila.pdf", "type": "pdf"},
        {"title": "Planilha de exercícios", "url": f"https://materiais.test/ds2-{suf}/exercicios.pdf", "type": "pdf"},
    ])
    pendente = curso(f"ds2b-{suf}", f"Power BI Essencial {suf}", 290.0,
                     [{"title": "Guia do Power BI", "url": f"https://materiais.test/ds2b-{suf}/guia.pdf", "type": "pdf"}])
    novo = curso(f"ds2c-{suf}", f"Python para Análise de Dados {suf}", 350.0, [])
    hoje = _agora().date()
    st, _ = _api(api, "POST", "/api/admin/classes",
                 {"course_id": novo["id"], "name": f"Turma Noturna {suf}", "starts_on": str(hoje + timedelta(days=10)),
                  "ends_on": str(hoje + timedelta(days=40)), "schedule": "Seg e Qua, 19h às 22h", "capacity": 30}, token)
    if st != 200:
        raise RuntimeError(f"seed: turma HTTP {st}")

    Database = abrir_banco(db_path)
    from core.security import get_password_hash  # noqa: PLC0415  (backend no sys.path depois de abrir_banco)
    senha_hash = get_password_hash(SENHA)

    def sql(comando, params=()):
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(comando, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def aluno(nome, email):
        uid = Database.add_user(email, nome, senha_hash, role="student")
        if uid is None:
            raise RuntimeError(f"seed: não foi possível criar {email}")
        return {"uid": uid, "email": email, "nome": nome}

    def matricula(a, c, preco, status, ha):
        eid = Database.create_enrollment(a["uid"], c["id"], f"{c['id']}:ds2:{uuid.uuid4().hex}")
        pid = Database.record_payment(eid, preco, "mercado_pago")
        quando = _ts(ha)
        if status == "active":
            sql("UPDATE payments SET status = 'approved', transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
                (f"mp-ds2-{uuid.uuid4().hex[:10]}", quando, quando, pid))
        else:
            sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (quando, quando, pid))
        sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, quando, eid))
        return eid

    principal = aluno("Marina Fernanda Albuquerque dos Santos", f"marina.fernanda.albuquerque.{suf}@empresa-exemplo.com.br")
    principal["ativa"] = matricula(principal, ativo, 480.0, "active", timedelta(days=1))
    principal["pendente"] = matricula(principal, pendente, 290.0, "pending", timedelta(days=2))
    vazio = aluno("Bruno Sem Matrícula", f"bruno.sem.matricula.{suf}@teste.com")

    # Progresso parcial (X1): 1 de 2 materiais concluído, pela própria API do aluno.
    st, corpo = _api(api, "POST", "/api/token", formulario={"username": principal["email"], "password": SENHA})
    if st != 200:
        raise RuntimeError(f"seed: login da aluna HTTP {st}")
    st, _ = _api(api, "POST", f"/api/student/enrollments/{principal['ativa']}/progress",
                 {"url": ativo["materiais"][0]["url"], "done": True}, corpo["access_token"])
    if st != 200:
        raise RuntimeError(f"seed: progresso HTTP {st}")

    return {"ativo": ativo, "pendente": pendente, "novo": novo, "principal": principal, "vazio": vazio}


# ------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


@pytest.fixture(scope="module")
def spa():
    with ambiente_isolado("ds2") as ambiente:
        yield ambiente


def _rodar(cenarios):
    resultados = []
    for codigo, nome, funcao in cenarios:
        try:
            funcao()
            resultados.append((codigo, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            texto = str(erro) or type(erro).__name__
            resultados.append((codigo, False, texto.splitlines()[0]))
            print(f"[FAIL] {codigo} {nome}")
            for linha in texto.splitlines():
                print(f"       {linha}")
    falhas = [f"{c}: {m}" for c, ok, m in resultados if not ok]
    print(f"\nRESULTADO: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, f"{len(falhas)} de {len(resultados)} cenários falharam: " + " | ".join(falhas)


def _exigir(violacoes, resumo):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões) de {resumo}:\n" + "\n".join(f"- {v}" for v in violacoes))


# ------------------------------------------------------------------------------------------------- autoteste (sem servidor)
_SINTETICA = """<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; font-family: sans-serif; color: #17212b; background: #fff; }
.faixa { display: flex; border: 1px solid #d8e0e8; margin: 0; }
.faixa > div { flex: 1; padding: 12px; }
.faixa > div + div { border-left: 1px solid #d8e0e8; }
.faixa dd { margin: 0; color: #17212b; font-variant-numeric: tabular-nums; font-size: 28px; }
.solto { display: flex; gap: 8px; }
.solto .card { flex: 1; border: 1px solid #d8e0e8; box-shadow: 0 2px 6px rgba(0,0,0,.1); padding: 12px; }
.solto .valor { color: #0096c7; font-size: 28px; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 20px; background: #e6f4ea; color: #17212b; font-size: 14px; }
.ponto-css::before { content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #1e7e34; margin-right: 6px; }
.cta { background: #ff7a18; color: #17212b; }
.ruim { color: #ff7a18; }
</style></head><body>
<div id="boa"><dl class="faixa" data-testid="aluno-resumo">
  <div><dt>Cursos ativos</dt><dd data-testid="resumo-cursos-ativos">1</dd></div>
  <div><dt>Pagamentos pendentes</dt><dd data-testid="resumo-pagamentos-pendentes">1</dd></div>
  <div><dt>Total investido</dt><dd data-testid="resumo-total-investido">R$ 480,00</dd></div>
</dl></div>
<div id="cartoes" class="solto">
  <div class="card"><div>Cursos ativos</div><div class="valor" data-testid="x-cursos">1</div></div>
  <div class="card"><div>Pagamentos pendentes</div><div class="valor" data-testid="x-pend">1</div></div>
  <div class="card"><div>Total investido</div><div class="valor" data-testid="x-total">R$ 480,00</div></div>
</div>
<div data-testid="curso-card">
  <h5 class="curso-nome">Curso A</h5>
  <span class="badge" id="b1"><span aria-hidden="true" style="display:inline-block;width:8px;height:8px;background:#1e7e34"></span> Ativa</span>
  <span class="badge ponto-css" id="b2">Pendente</span>
  <span class="badge" id="b3">✓ Aprovado</span>
  <span class="badge" id="b4" style="background:#b42318;color:#fff">Cancelada</span>
</div>
<p style="color:#0096c7;font-size:30px;font-weight:900">R$ 350,00</p>
<p aria-hidden="true" style="color:#0096c7">EP</p>
<a class="cta" data-testid="atalho-catalogo" href="#">Comprar cursos</a>
<span class="ruim">Laranja indevido</span>
<div style="background:#ff7a18;width:20px;height:20px"></div>
</body></html>"""


def test_ds2_apoio_verificador(browser):
    ctx = browser.new_context(viewport={"width": 1000, "height": 900})
    page = ctx.new_page()
    page.set_content(_SINTETICA)
    try:
        def v1():
            ids = [list(par) for par in RESUMO]
            boa = page.evaluate(_JS_RESUMO, {"ids": ids, "texto": TEXTO})
            if boa["v"] or boa["n1"] or boa["n2"] or boa["n3"]:
                raise Falha(f"faixa correta gerou violações: {boa}")
            page.evaluate("() => document.querySelectorAll('.faixa > div').forEach(d => d.style.borderLeft = '0')")
            sem = page.evaluate(_JS_RESUMO, {"ids": ids, "texto": TEXTO})
            if sum("sem divisória" in x for x in sem["n1"]) != 2:
                raise Falha(f"faixa sem divisórias não apontada: {sem['n1']}")
            # troca os testids para medir os cartões soltos
            page.evaluate("""() => {
              document.querySelectorAll('#boa [data-testid]').forEach(e => e.removeAttribute('data-testid'));
              const m = {'x-cursos': 'resumo-cursos-ativos', 'x-pend': 'resumo-pagamentos-pendentes', 'x-total': 'resumo-total-investido'};
              for (const [a, b] of Object.entries(m)) document.querySelector(`[data-testid=${a}]`).setAttribute('data-testid', b);
            }""")
            ruim = page.evaluate(_JS_RESUMO, {"ids": ids, "texto": TEXTO})
            tudo = " | ".join(ruim["v"] + ruim["n1"] + ruim["n2"] + ruim["n3"])
            esperadas = ["0 [data-testid=aluno-resumo]"]
            faltam = [e for e in esperadas if e not in tudo]
            # com o contêiner marcado nos cartões, aparecem os demais defeitos
            page.evaluate("() => document.getElementById('cartoes').setAttribute('data-testid', 'aluno-resumo')")
            ruim2 = page.evaluate(_JS_RESUMO, {"ids": ids, "texto": TEXTO})
            tudo2 = " | ".join(ruim2["n1"] + ruim2["n2"] + ruim2["n3"])
            for e in ("contêiner sem borda", ".card dentro da faixa", "sombra por item", "borda nos quatro lados",
                      "com cor rgb(0, 150, 199)", "sem tabular-nums", 'sem rótulo "Cursos ativos"'):
                if e not in tudo2:
                    faltam.append(e)
            if faltam:
                raise Falha(f"defeitos não apontados {faltam}; obtidos: {tudo} || {tudo2}")

        def v2():
            badges = page.evaluate(_JS_BADGES, {"sel": '[data-testid="curso-card"] .badge'})
            por = {b["texto"]: b["sinais"] for b in badges}
            erros = []
            for texto in ("Ativa", "Pendente", "✓ Aprovado"):
                if not por.get(texto):
                    erros.append(f"{texto!r} sem sinal reconhecido ({por.get(texto)})")
            if por.get("Cancelada"):
                erros.append(f"badge só com cor teve sinal reconhecido: {por['Cancelada']}")
            if erros:
                raise Falha("; ".join(erros))

        def v3():
            teal = page.evaluate(_JS_COR, {"cor": TEAL, "fundo": False, "permitidos": []})
            if not any("R$ 350,00" in t for t in teal) or any("'EP'" in t for t in teal):
                raise Falha(f"varredura de #0096c7: {teal}")
            laranja = page.evaluate(_JS_COR, {"cor": LARANJA, "fundo": True,
                                              "permitidos": ['[data-testid="atalho-catalogo"]']})
            tudo = " | ".join(laranja)
            if "Comprar cursos" in tudo or "Laranja indevido" not in tudo or "fundo div" not in tudo:
                raise Falha(f"varredura de laranja: {laranja}")

        _rodar([
            ("V1", "faixa de números: correta passa, cartões soltos apontados", v1),
            ("V2", "badge: sinal não cromático reconhecido; só cor apontado", v2),
            ("V3", "varredura de #0096c7 (inclui grande) e de laranja", v3),
        ])
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------- teste
# R3-3 (D125): /student tem duas abas (só o painel da aba ativa existe no DOM); cada estado é uma "tela" medida.
TELA_FIN = "/student (aba Financeiro)"
TELA_VAZIO = "/student (sem matrícula)"
TELA_VAZIO_FIN = "/student (sem matrícula, aba Financeiro)"
TELAS = ("/student", TELA_FIN, TELA_VAZIO, TELA_VAZIO_FIN, "/student/perfil", "/student/curso/:id", "/catalogo")


def test_ds2_area_aluno(browser, spa):
    contextos, erros = [], []
    seed = {}
    try:
        seed.update(semear(spa))
    except Exception as erro:  # o cenário P0 mostra a falha do seed
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def interceptar_chat(rota):
        """Resposta real do backend de teste; só garante uma fonte e `pii_masked` para as notas aparecerem."""
        if rota.request.method != "POST":
            rota.continue_()
            return
        resposta = rota.fetch()
        try:
            corpo = resposta.json()
        except Exception:
            rota.fulfill(response=resposta)
            return
        if isinstance(corpo, dict) and resposta.status == 200:
            if not corpo.get("sources"):
                corpo["sources"] = [{"title": FONTE_FIXTURE}]
            corpo["pii_masked"] = True
        rota.fulfill(response=resposta, json=corpo)

    def nova(largura):
        ctx = browser.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR", reduced_motion="reduce",
                                  accept_downloads=True)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        ctx.route("**/api/student/chat", interceptar_chat)
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
                erros.append(f"{msg.text[:100]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        return page

    def entrar(page, email):
        page.goto(spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /student (URL {page.url})")
        page.wait_for_load_state("networkidle")

    # --- preparo de cada tela ------------------------------------------------------------------------------
    def chat_aluno(page):
        # R3-4 (D126): o chat abre pelo botão flutuante; o painel fica aberto durante a medida de /student (as mesmas regras de
        # contraste, fonte, alvo e rolagem valem com o painel aberto e com a troca respondida) e é fechado em abrir_financeiro.
        abrir_assistente(page, TIMEOUT)
        antes = page.locator('[data-testid="chat-message"][data-role="assistant"]').count()
        page.locator('[data-testid="chat-input"]').fill(PERGUNTA_CHAT)
        page.locator('[data-testid="chat-send"]').click(timeout=TIMEOUT)
        page.wait_for_function(
            "n => document.querySelectorAll('[data-testid=\"chat-message\"][data-role=\"assistant\"]').length > n",
            arg=antes, timeout=TIMEOUT * 2)
        page.locator('[data-testid="chat-fonte"]').last.wait_for(state="visible", timeout=TIMEOUT)

    def chat_sala(page):
        page.locator('[data-testid="sala-chat-input"]').fill(PERGUNTA_CHAT, timeout=TIMEOUT)
        page.locator('[data-testid="sala-chat-enviar"]').click(timeout=TIMEOUT)
        page.locator('[data-testid="sala-chat-msg"][data-role="assistant"]').last.wait_for(state="visible",
                                                                                           timeout=TIMEOUT * 2)
        page.locator(".sala-chat-nota").last.wait_for(state="visible", timeout=TIMEOUT)

    def escolher_turmas(page):
        for sel in page.locator('[data-testid="catalogo-turma"]').all():
            if not sel.is_visible():
                continue
            valores = sel.evaluate("s => Array.from(s.options).filter(o => o.value && !o.disabled).map(o => o.value)")
            if valores:
                sel.select_option(valores[0])
        page.wait_for_timeout(200)

    # --- coleta das medidas --------------------------------------------------------------------------------
    medidas = {}  # (tela, largura) -> dict

    def medir(tela, largura, page, extra=None):
        try:
            page.wait_for_load_state("networkidle")
            page.mouse.move(1, 1)
            page.wait_for_timeout(400)
            m = {
                "contraste": varrer_contraste(page),
                "fontes": fontes_abaixo_de(page, 14),
                "teal": page.evaluate(_JS_COR, {"cor": TEAL, "fundo": False, "permitidos": []}),
                "laranja": page.evaluate(_JS_COR, {"cor": LARANJA, "fundo": True, "permitidos": [
                    '[data-testid="atalho-catalogo"]', '[data-testid="catalogo-comprar"]']}),
                "ds1": page.evaluate(_JS_MEDIR),
            }
            if extra:
                m.update(extra(page))
            medidas[(tela, largura)] = m
        except Exception as erro:
            medidas[(tela, largura)] = {"erro": f"{type(erro).__name__}: {str(erro).splitlines()[0][:160]}"}

    def falha_de_tela(tela, largura, erro):
        medidas[(tela, largura)] = {"erro": str(erro).splitlines()[0][:180]}

    def extra_student(page):
        cartoes = {}
        for chave in ("ativo", "pendente"):
            card = page.locator('[data-testid="curso-card"]').filter(has_text=seed[chave]["nome"])
            cartoes[chave] = card.first.evaluate(_JS_CARTAO) if card.count() else None
        return {
            "resumo": page.evaluate(_JS_RESUMO, {"ids": [list(p) for p in RESUMO], "texto": TEXTO}),
            "badges": page.evaluate(_JS_BADGES, {"sel": '[data-testid="curso-card"] .badge'}),
            "badges_contraste": varrer_contraste(page, dentro_de=[".badge"]),
            "cartoes": cartoes,
            "n_cartoes": page.locator('[data-testid="curso-card"]').count(),
            "atalho": botao_cores(page, '[data-testid="atalho-catalogo"]'),
            "chat": page.locator('[data-testid="chat-message"][data-role="assistant"]').count(),
        }

    def extra_financeiro(page):
        # R3-3 (D125): o histórico financeiro é a aba "Financeiro" (antes dividia a tela com os cursos).
        return {
            "resumo": page.evaluate(_JS_RESUMO, {"ids": [list(p) for p in RESUMO], "texto": TEXTO}),
            "badges": page.evaluate(_JS_BADGES, {"sel": '[data-testid="secao-financeiro"] .badge'}),
            "badges_contraste": varrer_contraste(page, dentro_de=[".badge"]),
            "pagamentos": [_normalizar(t) for t in page.locator('[data-testid="pagamento-status"]').all_inner_texts()],
            "atalho": botao_cores(page, '[data-testid="atalho-catalogo"]'),
        }

    def extra_vazio(page):
        return {
            "resumo": page.evaluate(_JS_RESUMO, {"ids": [list(p) for p in RESUMO], "texto": TEXTO}),
            "vazio_cursos": page.evaluate(_JS_LINK_CATALOGO, '[data-testid="secao-cursos"]'),
            "atalho": botao_cores(page, '[data-testid="atalho-catalogo"]'),
        }

    def extra_vazio_financeiro(page):
        return {
            "resumo": page.evaluate(_JS_RESUMO, {"ids": [list(p) for p in RESUMO], "texto": TEXTO}),
            "vazio_financeiro": page.evaluate(_JS_LINK_CATALOGO, '[data-testid="secao-financeiro"]'),
            "atalho": botao_cores(page, '[data-testid="atalho-catalogo"]'),
        }

    def abrir_financeiro(page):
        fechar_assistente(page, TIMEOUT)  # R3-4 (D126): a 390 px o painel aberto cobre a barra de abas; o aluno o fecha antes
        page.locator('[data-testid="atalho-financeiro"]').click(timeout=TIMEOUT)
        page.locator('[data-testid="secao-financeiro"]').wait_for(state="visible", timeout=TIMEOUT)

    def extra_catalogo(page):
        return {"comprar": botao_cores(page, '[data-testid="catalogo-comprar"]')}

    def extra_sala(page):
        return {"chat_sala": page.locator('[data-testid="sala-chat-msg"][data-role="assistant"]').count()}

    def botao_cores(page, sel):
        return page.evaluate(
            "sel => Array.from(document.querySelectorAll(sel)).filter(e => e.getBoundingClientRect().width > 1)"
            ".map(e => ({texto: (e.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40),"
            " fundo: getComputedStyle(e).backgroundColor, cor: getComputedStyle(e).color, desabilitado: e.disabled === true}))",
            sel)

    def coletar():
        if "erro" in seed:
            return
        telas_aluna = [
            ("/student", "/student", '[data-testid="secao-cursos"]', chat_aluno, extra_student),
            ("/student/perfil", "/student/perfil", '[data-testid="perfil-excluir"]', None, None),
            ("/student/curso/:id", f"/student/curso/{seed['principal']['ativa']}", '[data-testid="sala-curso"]',
             chat_sala, extra_sala),
            ("/catalogo", "/catalogo", '[data-testid="catalogo-card"]', escolher_turmas, extra_catalogo),
        ]
        for largura in LARGURAS:
            page = nova(largura)
            try:
                entrar(page, seed["principal"]["email"])
            except Exception as erro:
                for tela, *_ in telas_aluna:
                    falha_de_tela(tela, largura, erro)
            else:
                for tela, rota, marcador, preparar, extra in telas_aluna:
                    try:
                        page.goto(spa["base"] + rota, wait_until="networkidle")
                        page.locator(marcador).first.wait_for(state="visible", timeout=TIMEOUT)
                        if preparar:
                            preparar(page)
                    except Exception as erro:
                        falha_de_tela(tela, largura, f"{rota} não ficou pronta: {erro}")
                        continue
                    medir(tela, largura, page, extra)
                    if tela == "/student":
                        try:
                            abrir_financeiro(page)
                        except Exception as erro:
                            falha_de_tela(TELA_FIN, largura, f"a aba Financeiro não abriu: {erro}")
                        else:
                            medir(TELA_FIN, largura, page, extra_financeiro)

            page = nova(largura)
            tela = TELA_VAZIO
            try:
                entrar(page, seed["vazio"]["email"])
                page.locator('[data-testid="secao-cursos"]').wait_for(state="visible", timeout=TIMEOUT)
            except Exception as erro:
                falha_de_tela(tela, largura, erro)
                falha_de_tela(TELA_VAZIO_FIN, largura, erro)
            else:
                medir(tela, largura, page, extra_vazio)
                if largura == 1366:
                    medidas[(tela, largura)]["navega"] = navegacao_vazio(
                        page, (("vazio_cursos", '[data-testid="secao-cursos"]'),))
                try:
                    abrir_financeiro(page)
                except Exception as erro:
                    falha_de_tela(TELA_VAZIO_FIN, largura, f"a aba Financeiro não abriu: {erro}")
                else:
                    medir(TELA_VAZIO_FIN, largura, page, extra_vazio_financeiro)
                    if largura == 1366:
                        medidas[(TELA_VAZIO_FIN, largura)]["navega"] = navegacao_vazio(
                            page, (("vazio_financeiro", '[data-testid="secao-financeiro"]'),))

    def navegacao_vazio(page, secoes):
        """E1/E2: sem link com href, tenta cada botão visível da seção e vê se leva a /catalogo."""
        resultado = {}
        for chave, sel in secoes:
            info = page.evaluate(_JS_LINK_CATALOGO, sel)
            resultado[chave] = bool(info.get("links"))
            if resultado[chave]:
                continue
            for i in info.get("botoes", []):
                try:
                    page.locator(sel).locator('button, [role="link"]').nth(i).click(timeout=2000)
                    page.wait_for_timeout(500)
                    if urllib.parse.urlparse(page.url).path.rstrip("/") == "/catalogo":
                        resultado[chave] = True
                    if "/student" not in page.url:
                        page.goto(spa["base"] + "/student", wait_until="networkidle")
                    if resultado[chave]:
                        break
                except Exception:
                    continue
        return resultado

    coletar()

    def chaves():
        return sorted(medidas, key=lambda x: (TELAS.index(x[0]) if x[0] in TELAS else 99, -x[1]))

    def exigir_seed():
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")
        if not medidas:
            raise Falha("nenhuma tela foi medida")

    def por_tela(funcao, resumo, telas=None, larguras=LARGURAS):
        """Aplica `funcao(m, rotulo)` -> lista de violações em cada (tela, largura) medida."""
        def cenario():
            exigir_seed()
            v = []
            for tela, largura in chaves():
                if (telas and tela not in telas) or largura not in larguras:
                    continue
                m = medidas[(tela, largura)]
                rotulo = f"{tela} @{largura}px"
                if "erro" in m:
                    v.append(f"{rotulo}: {m['erro']}")
                    continue
                v.extend(f"{rotulo}: {item}" for item in funcao(m, rotulo))
            _exigir(v, resumo)
        return cenario

    # --- P0 ------------------------------------------------------------------------------------------------
    def p0():
        exigir_seed()
        v = []
        for largura in LARGURAS:
            m = medidas.get(("/student", largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"/student @{largura}px: {m['erro']}")
            else:
                if m["n_cartoes"] != 2:
                    v.append(f"/student @{largura}px: {m['n_cartoes']} cartões (esperado 2)")
                textos = sorted(b["texto"] for b in m["badges"])
                print(f"   [info] /student @{largura}px: badges {textos}")
                for esperado in ("Ativa", "Pendente"):
                    if not any(esperado in b["texto"] for b in m["badges"]):
                        v.append(f"/student @{largura}px: badge {esperado!r} não encontrado ({textos})")
                mf = medidas.get((TELA_FIN, largura), {"erro": "não medida"})
                if "erro" in mf:
                    v.append(f"{TELA_FIN} @{largura}px: {mf['erro']}")
                else:
                    for esperado in ("Aprovado", "Pendente"):
                        if not any(esperado in p for p in mf["pagamentos"]):
                            v.append(f"{TELA_FIN} @{largura}px: pagamento {esperado!r} não encontrado ({mf['pagamentos']})")
                if m["chat"] < 1:
                    v.append(f"/student @{largura}px: nenhuma resposta do assistente na tela")
                if None in m["cartoes"].values():
                    v.append(f"/student @{largura}px: cartão ativo ou pendente não achado pelo nome")
            m = medidas.get(("/student/curso/:id", largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"/student/curso/:id @{largura}px: {m['erro']}")
            elif m["chat_sala"] < 1:
                v.append(f"/student/curso/:id @{largura}px: nenhuma resposta do assistente da sala")
            m = medidas.get((TELA_VAZIO, largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"{TELA_VAZIO} @{largura}px: {m['erro']}")
            elif VAZIO_CURSOS not in m["vazio_cursos"].get("texto", ""):
                v.append(f"conta vazia @{largura}px: sem o texto {VAZIO_CURSOS!r}")
            m = medidas.get((TELA_VAZIO_FIN, largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"{TELA_VAZIO_FIN} @{largura}px: {m['erro']}")
            elif VAZIO_PAGAMENTOS not in m["vazio_financeiro"].get("texto", ""):
                v.append(f"conta vazia @{largura}px: sem o texto {VAZIO_PAGAMENTOS!r}")
            m = medidas.get(("/catalogo", largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"/catalogo @{largura}px: {m['erro']}")
            elif len(m["comprar"]) < 2:
                v.append(f"/catalogo @{largura}px: {len(m['comprar'])} botões de compra (esperado 2: retomar e comprar)")
        _exigir(v, "pré-condição do seed")

    # --- A1/A2 contraste -----------------------------------------------------------------------------------
    def a1(m, rotulo):
        c = m["contraste"]
        out = []
        if c["verificados"] < 10:
            out.append(f"só {c['verificados']} textos verificados (esperado >= 10)")
        out.extend(descrever([f], 1) for f in c["falhas"])
        return out

    def a2(m, rotulo):
        gradiente = [i for i in m["contraste"]["ignorados"] if "gradiente" in i["motivo"] or "imagem" in i["motivo"]]
        outros = [i for i in m["contraste"]["ignorados"] if i not in gradiente]
        if outros:
            print(f"   [info] {rotulo}: ignorados (não contam) -> {descrever(outros, 8)}")
        return [descrever([i], 1) for i in gradiente]

    # --- F1 fonte mínima -----------------------------------------------------------------------------------
    def f1(m, rotulo):
        return [descrever([i], 1) for i in m["fontes"]]

    # --- N faixa de números --------------------------------------------------------------------------------
    def n(chave):
        def funcao(m, rotulo):
            r = m["resumo"]
            return r[chave]
        return funcao

    # --- S1 status ------------------------------------------------------------------------------------------
    def s1(m, rotulo):
        out = []
        if not m["badges"]:
            out.append("nenhum .badge de status visível")
        for b in m["badges"]:
            if not b["temLetra"]:
                out.append(f"{b['onde']}: badge sem texto ({b['texto']!r})")
            if not b["sinais"]:
                out.append(f"{b['onde']}: badge {b['texto']!r} só com cor (sem ícone/ponto aria-hidden, "
                           f"::before/::after ou prefixo)")
        bc = m["badges_contraste"]
        out.extend(f"badge abaixo do AA: {descrever([f], 1)}" for f in bc["falhas"])
        out.extend(f"badge não medido: {descrever([i], 1)}" for i in bc["ignorados"])
        return out

    # --- L laranja ------------------------------------------------------------------------------------------
    def cores_conversao(botoes, nome):
        out = []
        if not botoes:
            out.append(f"{nome} ausente ou invisível")
        for b in botoes:
            if b["fundo"] != LARANJA:
                out.append(f"{nome} '{b['texto']}' com fundo {b['fundo']} (esperado {LARANJA})"
                           + (" [desabilitado]" if b["desabilitado"] else ""))
            if b["cor"] != TEXTO:
                out.append(f"{nome} '{b['texto']}' com texto {b['cor']} (esperado {TEXTO})")
            try:
                r = razao_contraste(b["cor"], b["fundo"])
            except ValueError:
                continue
            if r < 4.5:
                out.append(f"{nome} '{b['texto']}' com contraste {r:.2f}:1 ({b['cor']} sobre {b['fundo']})")
        return out

    def l1(m, rotulo):
        if "atalho" in m:
            return cores_conversao(m["atalho"], "[data-testid=atalho-catalogo]")
        if "comprar" in m:
            return cores_conversao(m["comprar"], "[data-testid=catalogo-comprar]")
        return []

    def l2(m, rotulo):
        return m["laranja"]

    # --- E estado vazio -------------------------------------------------------------------------------------
    def e(chave, texto, tela):
        def cenario():
            exigir_seed()
            v = []
            for largura in LARGURAS:
                m = medidas.get((tela, largura), {"erro": "não medida"})
                rotulo = f"conta vazia @{largura}px"
                if "erro" in m:
                    v.append(f"{rotulo}: {m['erro']}")
                    continue
                info = m[chave]
                if texto not in info.get("texto", ""):
                    v.append(f"{rotulo}: o texto {texto!r} sumiu da seção")
                # link com href na própria largura; botão sem href conferido por clique a 1366 px
                por_clique = medidas.get((tela, 1366), {}).get("navega", {}).get(chave)
                if not (info.get("links") or por_clique):
                    v.append(f"{rotulo}: nenhum link/botão visível na seção leva a /catalogo "
                             f"(links: {info.get('links')}; botões visíveis: {len(info.get('botoes', []))})")
            _exigir(v, f"estado vazio ({chave.replace('vazio_', '')})")
        return cenario

    # --- C ação principal por cartão ------------------------------------------------------------------------
    def c1(m, rotulo):
        botoes = m["cartoes"].get("ativo")
        if botoes is None:
            return ["cartão da matrícula ativa não encontrado"]
        out = []
        primarios = [b for b in botoes if b["primario"]]
        if len(primarios) != 1 or primarios[0]["testid"] != "curso-entrar":
            out.append(f"{len(primarios)} .btn-primary no cartão ativo (esperado só [data-testid=curso-entrar]): "
                       + "; ".join(f"{b['desc']} '{b['texto']}'" for b in primarios))
        entrar_fundo = next((b["fundo"] for b in botoes if b["testid"] == "curso-entrar"), None)
        for b in botoes:
            if b["testid"] == "curso-entrar" or b["primario"]:
                continue
            if entrar_fundo and b["fundo"] == entrar_fundo:
                out.append(f"ação secundária {b['desc']} '{b['texto']}' com o fundo do botão principal ({b['fundo']})")
        return out

    def c2(m, rotulo):
        botoes = m["cartoes"].get("pendente")
        if botoes is None:
            return ["cartão da matrícula pendente não encontrado"]
        primarios = [b for b in botoes if b["primario"]]
        out = []
        if len(primarios) > 1:
            out.append(f"{len(primarios)} .btn-primary no cartão pendente (máximo 1)")
        for b in primarios:
            if not re.search(r"retomar|pagar|pagamento", b["texto"], re.I):
                out.append(f"principal do cartão pendente não é retomar/pagar: {b['desc']} '{b['texto']}'")
        print(f"   [info] {rotulo}: ações do cartão pendente -> {[b['texto'] for b in botoes]}")
        return out

    # --- T1 #0096c7 -----------------------------------------------------------------------------------------
    def t1(m, rotulo):
        return m["teal"]

    # --- G guardas da DS1 -----------------------------------------------------------------------------------
    def g1(m, rotulo):
        d = m["ds1"]
        if len(d["h1"]) != 1:
            return [f"{len(d['h1'])} h1 visíveis {d['h1']}" + (f" (+{d['h1Ocultos']} oculto(s))" if d["h1Ocultos"] else "")]
        return []

    def g2(m, rotulo):
        return list(m["ds1"]["campos"])

    def g3(m, rotulo):
        return list(m["ds1"]["alvos"])

    def g4(m, rotulo):
        d = m["ds1"]
        fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
        if d["scrollWidth"] > 390:
            return [f"scrollWidth {d['scrollWidth']}px (> 390). Passam da borda: {fora}"]
        if d["clipaRaiz"] and d["fora"]:
            return [f"estouro escondido por overflow-x hidden no html/body. Passam da borda: {fora}"]
        return []

    def k1():
        _exigir(list(erros), "erro de console ou exceção de página")

    student = ("/student",)
    com_pagamentos_ou_cursos = ("/student", TELA_FIN)
    com_resumo = ("/student", TELA_FIN, TELA_VAZIO, TELA_VAZIO_FIN)
    try:
        _rodar([
            ("P0", "pré-condição do seed (cartões, pagamentos, vazio, chats)", p0),
            ("A1", "contraste AA completo em todas as telas do aluno", por_tela(a1, "contraste AA")),
            ("A2", "nenhum texto sobre gradiente/imagem (fundo sólido)", por_tela(a2, "texto sobre gradiente")),
            ("F1", "nenhum texto abaixo de 14 px", por_tela(f1, "texto abaixo de 14 px")),
            ("N1", "faixa de números: contêiner único, borda única, divisórias, sem sombra",
             por_tela(n("n1"), "faixa de números (estrutura)", telas=com_resumo)),
            ("N2", "faixa de números: cor do texto, tabular-nums, rótulo ligado",
             por_tela(n("n2"), "faixa de números (valores e rótulos)", telas=com_resumo)),
            ("N3", "faixa de números: sem estouro nem sobreposição",
             por_tela(n("n3"), "faixa de números (largura)", telas=com_resumo)),
            ("S1", "status com texto e sinal não cromático, AA",
             por_tela(s1, "status só por cor", telas=com_pagamentos_ou_cursos)),
            ("L1", "conversão em laranja com texto escuro",
             por_tela(l1, "botão de conversão", telas=com_resumo + ("/catalogo",))),
            ("L2", "laranja só na conversão", por_tela(l2, "laranja fora da conversão")),
            ("E1", "estado vazio de Meus cursos com link para o catálogo", e("vazio_cursos", VAZIO_CURSOS, TELA_VAZIO)),
            ("E2", "estado vazio do histórico com link para o catálogo",
             e("vazio_financeiro", VAZIO_PAGAMENTOS, TELA_VAZIO_FIN)),
            ("C1", "cartão ativo: uma ação principal (Entrar no curso)",
             por_tela(c1, "ação principal (cartão ativo)", telas=student)),
            ("C2", "cartão pendente: principal só se for retomar/pagar",
             por_tela(c2, "ação principal (cartão pendente)", telas=student)),
            ("T1", "nenhum texto em #0096c7 (inclui texto grande)", por_tela(t1, "texto em #0096c7")),
            ("G1", "guarda DS1: um h1 por tela", por_tela(g1, "um h1 por tela")),
            ("G2", "guarda DS1: rótulo em todo campo", por_tela(g2, "rótulo de campo")),
            ("G3", "guarda DS1: alvos >= 44 px", por_tela(g3, f"alvo de toque < {ALVO_MIN:.0f} px")),
            ("G4", "guarda DS1: sem rolagem horizontal a 390 px",
             por_tela(g4, "rolagem horizontal a 390 px", larguras=(390,))),
            ("K1", "sem erros de console", k1),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
