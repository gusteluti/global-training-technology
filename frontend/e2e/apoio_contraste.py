"""Apoio de acessibilidade visual dos e2e do plano de design (DS0 a DS5, D115). Não é código de produção.

Funções (todas recebem uma `page` do Playwright já carregada; o cálculo roda no Chromium, sobre o estilo COMPUTADO):

- `varrer_contraste(page, raiz="body", dentro_de=None)`: percorre os elementos visíveis com texto próprio (pelo menos um
  nó de texto filho direto, não vazio) e devolve os que ficam abaixo do mínimo WCAG 2.x AA:
  4,5:1 para texto normal; 3:1 para texto grande (>= 24 px, ou >= 18,66 px com peso >= 700).
  O fundo efetivo é calculado subindo pelos ancestrais até achar um fundo opaco, compondo as camadas com alfa
  (sem nenhum fundo opaco, a base é o branco do canvas). A cor do texto com alfa é composta sobre esse fundo.
  `dentro_de`: lista opcional de seletores CSS; quando dada, só entram os elementos que estão DENTRO de (ou são) um
  elemento que casa com algum dos seletores (`el.closest(sel)`).
  Devolve {"falhas": [...], "ignorados": [...], "verificados": int}. Cada item tem: `seletor` (caminho curto),
  `texto` (até 60 caracteres), `cor`, `fundo`, `razao`, `minimo`, `tamanho_px`, `peso`.
  Ficam de fora (não contam como falha):
    * texto de `input`, `textarea`, `select`/`option` e placeholder (não são nós de texto do DOM);
    * elementos dentro de `[aria-hidden="true"]`, `script`, `style`, `noscript`, `template`, `svg`;
    * elementos invisíveis (sem caixa, caixa de até 1 px, `visibility` diferente de visible, `display: none`);
  E vão para `ignorados` (com `motivo`), para quem chama decidir:
    * texto sobre imagem ou gradiente (`background-image` diferente de none no caminho até o fundo opaco), ou com
      `-webkit-text-fill-color` transparente;
    * elementos desabilitados (`:disabled` ou dentro de `[aria-disabled="true"]`): a WCAG isenta componente inativo;
    * opacidade acumulada menor que 1 (o cálculo não modela a composição do grupo);
    * cor em formato que o apoio não interpreta.
  Limitação conhecida: o fundo é procurado pela árvore do DOM; um elemento posicionado por cima de outro que não é
  seu ancestral (absolute/fixed sobre irmão) é medido contra o fundo do ancestral.

- `fontes_abaixo_de(page, minimo_px, raiz="body")`: elementos visíveis com texto próprio cujo `font-size` computado
  é menor que `minimo_px` (mesmas exclusões de visibilidade e aria-hidden acima).

- `razao_contraste(cor_a, cor_b)`: razão WCAG entre duas cores "rgb(r, g, b)" / "rgba(...)" / "#rrggbb" (opacas).

- `descrever(itens, limite=6)`: texto curto de uma lista de falhas, para a mensagem de erro do cenário.
"""

import re

_JS_COMUM = r"""
const PULAR = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'svg']);

function textoProprio(el) {
  let t = '';
  for (const n of el.childNodes) {
    if (n.nodeType === 3) t += n.textContent;
  }
  return t.replace(/\s+/g, ' ').trim();
}

function caminho(el) {
  const partes = [];
  let atual = el;
  for (let i = 0; atual && atual.nodeType === 1 && i < 4; i++, atual = atual.parentElement) {
    let p = atual.tagName.toLowerCase();
    const tid = atual.getAttribute('data-testid');
    if (tid) { partes.unshift(`${p}[data-testid=${tid}]`); break; }
    if (atual.id) { partes.unshift(`${p}#${atual.id}`); break; }
    const classes = Array.from(atual.classList).slice(0, 2);
    if (classes.length) p += '.' + classes.join('.');
    partes.unshift(p);
  }
  return partes.join(' > ');
}

function visivel(el) {
  if (el.closest('[aria-hidden="true"]')) return false;
  if (el.closest('svg')) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility !== 'visible' || cs.display === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  if (el.getClientRects().length === 0) return false;
  return true;
}

function candidatos(raiz, dentroDe) {
  const base = document.querySelector(raiz);
  if (!base) return [];
  const todos = [base, ...base.querySelectorAll('*')];
  return todos.filter(el => {
    if (PULAR.has(el.tagName)) return false;
    if (el.closest('script,style,noscript,template')) return false;
    if (!textoProprio(el)) return false;
    if (dentroDe && dentroDe.length && !dentroDe.some(sel => el.closest(sel))) return false;
    return visivel(el);
  });
}
"""

_JS_CONTRASTE = _JS_COMUM + r"""
function parseCor(txt) {
  if (!txt) return null;
  let m = txt.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
  if (m) {
    let a = m[4] === undefined ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return [parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3]), a];
  }
  m = txt.match(/^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/);
  if (m) {
    let a = m[4] === undefined ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return [parseFloat(m[1]) * 255, parseFloat(m[2]) * 255, parseFloat(m[3]) * 255, a];
  }
  if (txt === 'transparent') return [0, 0, 0, 0];
  return null;
}

function compor(cima, baixo) {
  const a = cima[3];
  return [cima[0] * a + baixo[0] * (1 - a), cima[1] * a + baixo[1] * (1 - a), cima[2] * a + baixo[2] * (1 - a), 1];
}

function lum(c) {
  const f = v => { v = v / 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
}

function razao(a, b) {
  const la = lum(a), lb = lum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function rgbTxt(c) { return `rgb(${Math.round(c[0])}, ${Math.round(c[1])}, ${Math.round(c[2])})`; }

function fundoEfetivo(el) {
  const camadas = [];
  for (let atual = el; atual && atual.nodeType === 1; atual = atual.parentElement) {
    const cs = getComputedStyle(atual);
    if (cs.backgroundImage && cs.backgroundImage !== 'none') return { motivo: 'texto sobre imagem ou gradiente' };
    const c = parseCor(cs.backgroundColor);
    if (c === null) return { motivo: `cor de fundo não interpretada (${cs.backgroundColor})` };
    if (c[3] > 0) {
      camadas.push(c);
      if (c[3] >= 1) break;
    }
  }
  let fundo = [255, 255, 255, 1];
  for (let i = camadas.length - 1; i >= 0; i--) fundo = compor(camadas[i], fundo);
  return { fundo };
}

function opacidade(el) {
  let o = 1;
  for (let atual = el; atual && atual.nodeType === 1; atual = atual.parentElement) {
    o *= parseFloat(getComputedStyle(atual).opacity);
  }
  return o;
}

(args) => {
  const falhas = [], ignorados = [];
  let verificados = 0;
  for (const el of candidatos(args.raiz, args.dentroDe)) {
    const cs = getComputedStyle(el);
    const base = { seletor: caminho(el), texto: textoProprio(el).slice(0, 60) };
    if (el.matches(':disabled') || el.closest('[aria-disabled="true"]') || el.closest('fieldset:disabled')) {
      ignorados.push({ ...base, motivo: 'desabilitado' });
      continue;
    }
    const preench = cs.webkitTextFillColor;
    if (preench && parseCor(preench) && parseCor(preench)[3] === 0) {
      ignorados.push({ ...base, motivo: 'texto com preenchimento transparente (gradiente)' });
      continue;
    }
    const op = opacidade(el);
    if (op < 0.999) {
      ignorados.push({ ...base, motivo: `opacidade acumulada ${op.toFixed(2)}` });
      continue;
    }
    const cor = parseCor(cs.color);
    if (cor === null) { ignorados.push({ ...base, motivo: `cor não interpretada (${cs.color})` }); continue; }
    const f = fundoEfetivo(el);
    if (!f.fundo) { ignorados.push({ ...base, motivo: f.motivo }); continue; }
    const corFinal = cor[3] < 1 ? compor(cor, f.fundo) : cor;
    const tamanho = parseFloat(cs.fontSize);
    const peso = parseInt(cs.fontWeight, 10) || 400;
    const grande = tamanho >= 24 || (tamanho >= 18.66 && peso >= 700);
    const minimo = grande ? 3 : 4.5;
    const r = razao(corFinal, f.fundo);
    verificados++;
    if (r + 1e-9 < minimo) {
      falhas.push({ ...base, cor: rgbTxt(corFinal), fundo: rgbTxt(f.fundo), razao: Math.round(r * 100) / 100,
                    minimo, tamanho_px: tamanho, peso });
    }
  }
  return { falhas, ignorados, verificados };
}
"""

_JS_FONTES = _JS_COMUM + r"""
(args) => {
  const abaixo = [];
  for (const el of candidatos(args.raiz, null)) {
    const tamanho = parseFloat(getComputedStyle(el).fontSize);
    if (tamanho + 1e-6 < args.minimo) {
      abaixo.push({ seletor: caminho(el), texto: textoProprio(el).slice(0, 60), tamanho_px: tamanho });
    }
  }
  return abaixo;
}
"""


def varrer_contraste(page, raiz="body", dentro_de=None):
    """Falhas de contraste AA do texto visível (ver docstring do módulo)."""
    return page.evaluate(_JS_CONTRASTE, {"raiz": raiz, "dentroDe": list(dentro_de or [])})


def fontes_abaixo_de(page, minimo_px, raiz="body"):
    """Elementos visíveis com texto próprio e font-size computado menor que `minimo_px`."""
    return page.evaluate(_JS_FONTES, {"raiz": raiz, "minimo": float(minimo_px)})


def _rgb(cor):
    cor = cor.strip()
    if cor.startswith("#"):
        h = cor.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", cor)
    if not m:
        raise ValueError(f"cor não interpretada: {cor!r}")
    return tuple(float(m.group(i)) for i in (1, 2, 3))


def _lum(rgb):
    def canal(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao_contraste(cor_a, cor_b):
    """Razão de contraste WCAG entre duas cores opacas ('rgb(...)', 'rgba(...)' ou '#rrggbb')."""
    la, lb = _lum(_rgb(cor_a)), _lum(_rgb(cor_b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def descrever(itens, limite=6):
    partes = []
    for item in itens[:limite]:
        if "razao" in item:
            partes.append(f"{item['seletor']} {item['texto']!r} {item['cor']} sobre {item['fundo']} = "
                          f"{item['razao']}:1 (mín. {item['minimo']}:1, {item['tamanho_px']}px/{item['peso']})")
        elif "motivo" in item:
            partes.append(f"{item['seletor']} {item['texto']!r} ({item['motivo']})")
        else:
            partes.append(f"{item['seletor']} {item['texto']!r} {item['tamanho_px']}px")
    resto = len(itens) - limite
    return "; ".join(partes) + (f"; e mais {resto}" if resto > 0 else "")
