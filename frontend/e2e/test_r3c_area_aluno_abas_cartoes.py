"""E2E da R3-3 (D125) - Área do aluno (/student) em ABAS e com cada curso em um CARTÃO. Só design/estrutura de tela.

Pedido do PM (23/11/2026, 19:28 e 19:36): "em vez de deixar todas as funcionalidades em um monólito, deixe em abas igual é na
aba da gestão"; "na aba de cursos matriculados coloque cada curso em formato de cards em vez de um em cima do outro" e, sobre
onde ficam materiais, avaliação e cancelamento: "Coloque tudo dentro de cada cartão". O assistente flutuante é a entrega 4
(NÃO faz parte desta). Nenhuma lógica de negócio, endpoint ou texto de negócio muda. A decisão do PM de cartões REVOGA o layout
de linhas da DS2b/D122 (um curso por linha, ícone-corpo-ação lado a lado).

CONTRATO (o dev-frontend implementa; a FORMA é do orquestrador, este arquivo é a fonte)
  1. Abas, no mesmo padrão do painel da gestão (`admin-dashboard.component.html`, linhas 1-12):
       <ul class="nav nav-tabs gt-abas mb-3" #abas>
         <li class="nav-item"> <button type="button" class="nav-link" [class.active] [attr.aria-current]="... ? 'page' : null"
                                       [attr.data-aba]="chave" data-testid="atalho-<chave>" (click)> rótulo </button> </li>
         ... <li class="gt-abas-indicador" data-testid="abas-indicador" aria-hidden="true" #indicador></li>
       </ul>
     Exatamente duas abas reais, nesta ordem: "Meus cursos" (data-testid=atalho-cursos, data-aba=cursos) e "Financeiro"
     (data-testid=atalho-financeiro, data-aba=financeiro). Aba inicial = Meus cursos. A aba ativa tem a classe `active` e
     `aria-current="page"`; a inativa não tem `aria-current` (ausente). O indicador (`li.gt-abas-indicador`) fica na base da aba
     ativa (mesmo x e mesma largura, tolerância 2 px), é movido ao trocar de aba e recalculado em `window:resize`
     (`moverIndicador()` com offsetWidth/offsetLeft, como na gestão).
     No FIM da mesma `ul` ficam o link "Meu perfil" (data-testid=atalho-perfil, routerLink /student/perfil, <a>) e,
     TRANSITORIAMENTE (a entrega 4 o remove), o botão "Assistente" (data-testid=atalho-assistente, <button type=button>) que
     continua rolando até a seção do chat. Esses dois NÃO são abas (sem data-aba, sem aria-current, sem `active`), mas têm a mesma
     aparência da barra (mesma fonte, peso, padding, raio e fundo das abas inativas) e alvo >= 44 px. O `nav.aluno-atalhos`
     antigo (e as classes `.aluno-atalhos` / `.aluno-atalho`) deixam de existir. A rota `/student/perfil` continua.
  2. Só o painel da aba ativa existe no DOM (`*ngIf`, como na gestão): `[data-testid=secao-cursos]` (id secao-cursos, h3
     "Meus cursos") na aba Meus cursos; `[data-testid=secao-financeiro]` (id secao-financeiro, h3 "Histórico financeiro") na aba
     Financeiro. A faixa `.aluno-resumo` (data-testid=aluno-resumo, 3 KPIs `resumo-*`) fica ACIMA da barra de abas e visível nas
     duas, com os mesmos valores. A seção do assistente (`#secao-assistente`, data-testid=chat-panel, chat inteiro com todos os
     testids intactos) NÃO muda de lugar: continua sempre visível ABAIXO do painel das abas. O carregamento dos dados continua no
     `ngOnInit`/resolver: trocar de aba NÃO faz nenhuma chamada nova a /api/.
  3. Estado que sobrevive à troca de aba: o recibo aberto continua aberto quando o aluno volta ao Financeiro (a propriedade
     `receipt` do componente não é limpa). Avaliação em edição ou cancelamento aberto: a troca não pode dar erro de console.
  4. Ações `open` do chat (`chat-acao-abrir`): alvo `financeiro` seleciona a aba Financeiro; alvo `cursos` seleciona a aba Meus
     cursos (indicador movido, `aria-current` correto, seção visível e rolada para a vista: topo entre -5 px e 60% da altura da
     janela); alvo `perfil` navega para /student/perfil. Com a aba já ativa, só rola.
  5. Cartões na aba Meus cursos: `.cursos-lista` contém todos os `[data-testid=curso-card]` (um por matrícula), em grade: >= 3
     colunas em 1280 px, 2 em 768 px, 1 em 390 px (sugestão: `repeat(auto-fill, minmax(~320px, 1fr))` com `gap` de 16 px e cartão
     com `height: 100%`). Cartões da mesma linha têm o mesmo topo e a mesma altura (esticados), sem sobreposição e com >= 8 px
     entre si. Sem rolagem horizontal em 390 px. TUDO dentro de cada cartão (descendentes do próprio `curso-card`, também na
     geometria): `.curso-icone` (iniciais), `.curso-nome`, `.badge` de status, `curso-data`, `curso-turma`, `curso-progresso` e
     `[role=progressbar]`, `curso-entrar` (ou a mensagem `.curso-aviso` de sem acesso), links de materiais (`a[target=_blank]`),
     `material-concluido`, `curso-certificado`, avaliação (`curso-avaliacao-comentario|nota|enviar`, `-ok`, `-erro`, `-atual`) e
     cancelamento (`curso-cancelamento-status`, `curso-cancelar`, `curso-cancelar-motivo`, `curso-cancelar-enviar`, "Voltar").
     "Entrar no curso": alvo >= 44 px, visível sem rolagem interna do cartão (o cartão e seus filhos não têm overflow que corte
     ou role), na parte de baixo do cartão (mesma distância da base em todos os cartões da mesma linha) ou na metade superior.
     Layout vertical dentro do cartão (não mais ícone-corpo-ação lado a lado). A linha de avaliação (input, select, botão) quebra
     em 390 px sem estourar o cartão (comentário com >= 200 px, sem sobreposição). Um aluno com um só curso: o cartão tem a
     largura de UMA coluna da grade (não estica a linha toda).
  6. Mantidos: todos os data-testid, ids, classes e textos que os e2e antigos usam (curso-card, curso-entrar, curso-data,
     curso-turma, curso-progresso, curso-progresso-sala, material-concluido, curso-certificado, curso-avaliacao-*, curso-cancelar*,
     curso-cancelamento-status, pagamento-status, recibo-pdf, aluno-resumo, resumo-*, atalho-*, aluno-email, chat-*). D115:
     contraste AA, alvos >= 44 px, texto >= 14 px, foco visível, um único h1, campos rotulados, sem confirm(), sem emoji novo,
     sem animação em repouso.
  7. Estados: aluno sem matrículas (alerta "Você ainda não tem matrículas." + "Ver cursos" para /catalogo), matrícula
     pending/cancelled/refunded (selo + a mensagem de sem acesso de sempre, nenhum link nem URL de material: AGENTS.md, item 4),
     erro de carga (alerta "Não foi possível carregar suas matrículas." no painel, sem cartões) e aluno com um só curso.

Seed (harness isolado D58; reaproveita o semeador da DS2b e acrescenta quatro alunos), todos com a mesma senha da DS2:
  Marina (DS2b): ativa 1 de 2 (Excel) + pendente (Power BI)             -> 2 cartões; pagamentos Aprovado e Pendente
  Rafael (DS2b): ativa com turma, 2 de 2, certificado + ativa sem materiais -> 2 cartões
  Bruno  (DS2b): sem matrícula                                          -> estado vazio
  Carla: ativa Excel (pedido de cancelamento aberto) + ativa sem materiais + pendente (Power BI) + cancelada (Gestão de
         Projetos Ágeis, com materiais no catálogo) + reembolsada (Python)            -> 5 cartões
  Sofia: uma só matrícula ativa (Excel)                                 -> 1 cartão
  Davi:  duas matrículas ativas com materiais, 0 de 2 (só para os fluxos que alteram dados, uma por cartão)

Testes (cada um lista TODAS as violações, não só a primeira; ids no nome do teste):
  P0  pré-condição do seed [passa no red: é o estado de hoje]
  T1  barra de abas no padrão da gestão (ul, 2 abas, indicador, sem nav.aluno-atalhos)
  T2  estado inicial: Meus cursos ativa, só o painel de cursos no DOM
  T3  troca para Financeiro e volta: aria-current, painel único no DOM
  T4  indicador sob a aba ativa (inicial e após cada troca) a 1280, 768 e 390 px
  T5  indicador acompanha o resize (recalcula quando a geometria muda)
  T6  Meu perfil e Assistente: na mesma barra, fora do conjunto de abas, mesma aparência
  T7  Assistente rola até o chat sem trocar de aba; Meu perfil navega para /student/perfil
  T8  KPIs acima das abas, visíveis nas duas, mesmos valores
  T9  chat sempre abaixo do painel, testids intactos, e funciona com a aba Financeiro ativa
  T10 trocar de aba não faz chamada nova à API
  T11 recibo aberto continua aberto ao voltar ao Financeiro
  T12 troca de aba com avaliação em edição e cancelamento aberto: sem erro de console
  T13 erro de carga das matrículas não impede a aba Financeiro
  O1  ação open/financeiro seleciona a aba Financeiro
  O2  ação open/cursos seleciona a aba Meus cursos (e, já nela, só rola)
  O3  ação open/perfil navega para /student/perfil
  C1  grade: 3+ colunas (1280), 2 (768), 1 (390), dentro de .cursos-lista
  C2  mesma linha, mesmo topo e mesma altura; sem sobreposição; espaço entre cartões
  C3  tudo dentro de cada cartão (DOM e geometria), por estado da matrícula
  C4  "Entrar no curso": alvo >= 44 px, visível sem rolagem interna, alinhado na linha; mensagem de sem acesso
  C5  avaliação sem sobreposição e sem estourar o cartão; comentário usável em 390 px; sem rolagem horizontal em 390 px
  C6  cancelamento aberto continua dentro do cartão (3 larguras) e Voltar fecha
  C7  nenhuma URL de material fora de matrícula ativa (checklist item 4)
  C8  estado sem matrículas (alerta e "Ver cursos")
  C9  um só curso: o cartão tem a largura de uma coluna da grade
  C10 erro de carga: alerta sem cartões
  F1  avaliar grava no cartão certo (Davi: dois cartões)
  F2  marcar aula concluída atualiza o progresso do cartão certo
  F3  cancelamento completo (janela de confirmação) no cartão certo
  F4  baixar certificado pelo cartão (Rafael)
  F5  "Entrar no curso" leva a /student/curso/<id>
  A1  contraste AA (cursos e financeiro, 1280 e 390)
  A2  piso de 14 px
  A3  um h1, campos rotulados, alvos >= 44 px
  A4  sem rolagem horizontal a 390 px nas duas abas
  A8  sem rolagem horizontal a 320 px nas duas abas (o qa_istqb CT-UI-11 já exercita 320 px em /student)
  A5  foco visível nas abas e em "Entrar no curso"
  A6  sem animação em repouso
  A7  sem emoji novo
  K1  sem erro de console (4xx/5xx de /api, exceção de página) nem diálogo nativo, em todas as telas do arquivo [último]

Escolhas do agente-testes (modo autônomo, D40), registradas no relatório:
  - "Rolada para a vista" = topo da seção entre -5 px e 60% da altura da janela e seção visível; não exige scrollY > 0 (a página
    pode ser curta), só que a seção não fique cortada nem fora da janela.
  - "Na parte de baixo" do "Entrar no curso" = mesma distância da base do cartão em todos os cartões da mesma linha (2 px); a
    alternativa "no topo" = centro do botão na metade superior (40%) do cartão. Só vale com 2+ botões na linha.
  - "Mesma aparência" de Meu perfil/Assistente com as abas = fonte, peso, família, padding lateral, raio e fundo iguais aos da
    aba inativa (a cor não é comparada: o contraste é medido em A1).
  - Indicador: base da aba ativa = o fundo do indicador a até 4 px da base da aba, largura e x com tolerância de 2 px.
  - O teste do resize injeta CSS que muda o padding das abas (o indicador fica velho) e só depois redimensiona a janela.
  - Cartão de curso com `overflow: hidden` e conteúdo cortado conta como violação ("sem rolagem interna").
  - Sem animação em repouso = nenhuma CSSAnimation/CSSTransition em execução 1,5 s depois de abrir a tela.
  - Não se afirma que o `nav` envolva a barra nem `role=tablist` (não estão no contrato; a gestão também não tem).

Execução (de frontend/e2e): PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 -m pytest test_r3c_area_aluno_abas_cartoes.py -s
"""

import contextlib
import json
import re
import sqlite3
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_contraste import descrever, fontes_abaixo_de, varrer_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from test_ds1_componentes_angular import _JS_MEDIR  # noqa: E402
from test_ds2_area_aluno_angular import SENHA, VAZIO_CURSOS, _JS_UTIL, _agora, _api, _ts  # noqa: E402
from test_ds2b_area_aluno_angular import semear as semear_ds2b  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
LARGURAS = (1280, 768, 390)
PERGUNTA_CHAT = "Como funciona o cancelamento e o reembolso do curso?"
MSG_ERRO_MATRICULAS = "Não foi possível carregar suas matrículas."
MENSAGENS_SEM_ACESSO = {
    "Pendente": "Pagamento em análise. Os materiais ficam disponíveis após a confirmação.",
    "Cancelada": "Matrícula cancelada. Os materiais não estão disponíveis.",
    "Reembolsada": "Pagamento reembolsado. Os materiais não estão mais disponíveis.",
}
SEL_BARRA = "ul.nav.nav-tabs.gt-abas"
SEL_ABA = f"{SEL_BARRA} [data-aba]"
SEL_CARD = '[data-testid="curso-card"]'
SELETORES = {
    "icone": ".curso-icone",
    "nome": ".curso-nome",
    "selo": '.badge:not([data-testid="pagamento-status"])',
    "data": '[data-testid="curso-data"]',
    "turma": '[data-testid="curso-turma"]',
    "progresso": '[data-testid="curso-progresso"]',
    "barra": '[role="progressbar"]',
    "entrar": '[data-testid="curso-entrar"]',
    "aviso": ".curso-aviso",
    "material": 'a[target="_blank"]',
    "concluido": '[data-testid="material-concluido"]',
    "certificado": '[data-testid="curso-certificado"]',
    "comentario": '[data-testid="curso-avaliacao-comentario"]',
    "nota": '[data-testid="curso-avaliacao-nota"]',
    "enviar": '[data-testid="curso-avaliacao-enviar"]',
    "ok": '[data-testid="curso-avaliacao-ok"]',
    "atual": '[data-testid="curso-avaliacao-atual"]',
    "cancelar": '[data-testid="curso-cancelar"]',
    "cancelamento": '[data-testid="curso-cancelamento-status"]',
}


class Falha(Exception):
    pass


def _exigir(violacoes, resumo):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões) de {resumo}:\n" + "\n".join(f"- {v}" for v in violacoes))


def _r(d):
    return f"[{d['l']:.0f},{d['t']:.0f} -> {d['r']:.0f},{d['b']:.0f}] ({d['w']:.0f}x{d['h']:.0f})"


def _norm(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


# ------------------------------------------------------------------------------------------------- medidores (JS)
_JS_ABAS = _JS_UTIL + r"""
() => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const qa = s => Array.from(document.querySelectorAll(s));
  const out = {};
  const uls = qa('ul.nav.nav-tabs.gt-abas');
  out.nUl = uls.length;
  out.antigos = qa('.aluno-atalhos, .aluno-atalho, nav[aria-label="Seções da área do aluno"]').length;
  const ul = uls[0];
  const resumo = document.querySelector('[data-testid="aluno-resumo"]');
  const chat = document.querySelector('[data-testid="chat-panel"]');
  out.resumo = resumo ? R(resumo) : null;
  out.chat = chat ? R(chat) : null;
  out.resumoAntes = !!(ul && resumo && (resumo.compareDocumentPosition(ul) & Node.DOCUMENT_POSITION_FOLLOWING));
  if (!ul) return out;
  const cs = getComputedStyle(ul);
  out.ul = { rect: R(ul), overflowX: cs.overflowX, scrollW: ul.scrollWidth, clientW: ul.clientWidth };
  out.filhos = Array.from(ul.children).map(li => li.tagName.toLowerCase() + (li.className ? '.' + li.className.trim().split(/\s+/).join('.') : ''));
  const info = el => {
    const c = getComputedStyle(el);
    return { tag: el.tagName.toLowerCase(), tipo: el.getAttribute('type'), texto: norm(el.innerText), testid: el.getAttribute('data-testid'),
             aba: el.getAttribute('data-aba'), atual: el.getAttribute('aria-current'), ativa: el.classList.contains('active'),
             classes: Array.from(el.classList), href: el.getAttribute('href'), rect: R(el), fonte: c.fontSize, peso: c.fontWeight,
             familia: c.fontFamily, padE: c.paddingLeft, padD: c.paddingRight, raio: c.borderTopLeftRadius, fundo: c.backgroundColor,
             noLi: !!(el.parentElement && el.parentElement.tagName === 'LI' && el.parentElement.parentElement === ul),
             liNavItem: !!(el.parentElement && el.parentElement.classList.contains('nav-item')) };
  };
  out.abas = qa('ul.nav-tabs.gt-abas [data-aba]').map(info);
  const todos = Array.from(ul.querySelectorAll('button, a'));
  out.itens = todos.map(info);
  const pega = id => { const e = qa(`[data-testid="${id}"]`); return { n: e.length, dentro: e.length ? ul.contains(e[0]) : false, info: e.length ? info(e[0]) : null,
                       depois: e.length ? !!(qa('ul.nav-tabs.gt-abas [data-aba]').every(a => a.compareDocumentPosition(e[0]) & Node.DOCUMENT_POSITION_FOLLOWING)) : false }; };
  out.perfil = pega('atalho-perfil');
  out.assistente = pega('atalho-assistente');
  const ind = qa('[data-testid="abas-indicador"]');
  out.ind = { n: ind.length, dentro: ind.length ? ul.contains(ind[0]) : false, tag: ind[0] ? ind[0].tagName.toLowerCase() : null,
              classes: ind[0] ? Array.from(ind[0].classList) : [], ariaHidden: ind[0] ? ind[0].getAttribute('aria-hidden') : null,
              rect: ind[0] ? R(ind[0]) : null };
  return out;
}
"""

_JS_INDICADOR = r"""
(chave) => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const ul = document.querySelector('ul.nav.nav-tabs.gt-abas');
  const aba = ul && ul.querySelector(`[data-aba="${chave}"]`);
  const ind = document.querySelectorAll('[data-testid="abas-indicador"]');
  return { n: ind.length, ind: ind[0] ? R(ind[0]) : null, aba: aba ? R(aba) : null, ul: ul ? R(ul) : null };
}
"""

_JS_PAINEIS = r"""
() => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const um = s => { const e = Array.from(document.querySelectorAll(s)); return { n: e.length, rect: e[0] ? R(e[0]) : null,
                    visivel: !!(e[0] && e[0].getClientRects().length && getComputedStyle(e[0]).visibility !== 'hidden'),
                    h3: e[0] && e[0].querySelector('h3') ? (e[0].querySelector('h3').innerText || '').replace(/\s+/g, ' ').trim() : null }; };
  const porId = id => { const e = document.getElementById(id); return e ? e.getAttribute('data-testid') : null; };
  return { cursos: um('[data-testid="secao-cursos"]'), financeiro: um('[data-testid="secao-financeiro"]'),
           chat: um('[data-testid="chat-panel"]'), idCursos: porId('secao-cursos'), idFinanceiro: porId('secao-financeiro'),
           idAssistente: porId('secao-assistente'),
           cards: document.querySelectorAll('[data-testid="curso-card"]').length,
           pagamentos: Array.from(document.querySelectorAll('[data-testid="pagamento-status"]')).map(e => (e.innerText || '').trim()),
           recibos: document.querySelectorAll('.aluno-recibo').length, janela: window.innerHeight, rolagem: window.scrollY };
}
"""

_JS_CARTOES = _JS_UTIL + r"""
(args) => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const geo = el => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
                      return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const CARD = '[data-testid="curso-card"]';
  const secao = document.querySelector('[data-testid="secao-cursos"]');
  const cards = Array.from(document.querySelectorAll(CARD));
  const out = { n: cards.length, docW: document.documentElement.scrollWidth, janela: window.innerWidth,
                secao: secao ? R(secao) : null, cards: [], fora: {} };
  const lista = document.querySelector('.cursos-lista');
  out.lista = lista ? { rect: R(lista), display: getComputedStyle(lista).display, contem: cards.every(c => lista.contains(c)) } : null;
  for (const [k, sel] of Object.entries(args.sel)) {
    out.fora[k] = secao ? Array.from(secao.querySelectorAll(sel)).filter(e => !e.closest(CARD)).length : 0;
  }
  for (const card of cards) {
    const cr = card.getBoundingClientRect();
    const nome = card.querySelector('.curso-nome');
    const c = { rect: R(card), nome: nome ? norm(nome.innerText) : '', pecas: {}, estouros: [], rolagens: [], temUrlMaterial: false };
    for (const [k, sel] of Object.entries(args.sel)) {
      c.pecas[k] = Array.from(card.querySelectorAll(sel)).map(e => ({
        texto: norm(e.innerText || e.textContent), rect: R(e), geo: geo(e), href: e.getAttribute('href'),
        classes: Array.from(e.classList), tag: e.tagName.toLowerCase() }));
    }
    for (const el of card.querySelectorAll('*')) {
      if (!geo(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.left < cr.left - 1 || r.right > cr.right + 1 || r.top < cr.top - 1 || r.bottom > cr.bottom + 1) {
        if (c.estouros.length < 6) {
          c.estouros.push(`${desc(el)} [${Math.round(r.left)},${Math.round(r.top)} -> ${Math.round(r.right)},${Math.round(r.bottom)}] `
                          + `fora do cartão [${Math.round(cr.left)},${Math.round(cr.top)} -> ${Math.round(cr.right)},${Math.round(cr.bottom)}]`);
        }
      }
      const cs = getComputedStyle(el);
      if (['auto', 'scroll'].includes(cs.overflowY) && el.scrollHeight > el.clientHeight + 1) c.rolagens.push(`${desc(el)}: rolagem vertical interna`);
      if (['auto', 'scroll'].includes(cs.overflowX) && el.scrollWidth > el.clientWidth + 1) c.rolagens.push(`${desc(el)}: rolagem horizontal interna`);
    }
    if (card.scrollHeight > card.clientHeight + 1 || card.scrollWidth > card.clientWidth + 1) {
      c.rolagens.push(`o próprio cartão: conteúdo ${card.scrollWidth}x${card.scrollHeight} maior que a caixa ${card.clientWidth}x${card.clientHeight}`);
    }
    c.temUrlMaterial = /materiais\.test/.test(card.innerHTML);
    out.cards.push(c);
  }
  return out;
}
"""

_JS_FOCO = r"""
(sel) => {
  const e = document.querySelector(sel);
  if (!e) return null;
  const c = getComputedStyle(e);
  return { match: e.matches(':focus-visible'), estilo: c.outlineStyle, largura: parseFloat(c.outlineWidth) || 0, cor: c.outlineColor,
           sombra: c.boxShadow };
}
"""

_JS_ANIMACOES = _JS_UTIL + r"""
() => document.getAnimations().filter(a => a.playState === 'running').map(a => {
  const alvo = a.effect && a.effect.target;
  return `${a.constructor.name} ${a.animationName || a.transitionProperty || ''} em ${alvo ? desc(alvo) : '?'}`;
})
"""

_JS_NA_VISTA = r"""
(sel) => {
  const e = document.querySelector(sel);
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return { topo: r.top, base: r.bottom, janela: window.innerHeight, rolagem: window.scrollY,
           visivel: r.bottom > 0 && r.top < window.innerHeight };
}
"""


# ------------------------------------------------------------------------------------------------- seed
def semear(amb):
    seed = semear_ds2b(amb)  # Marina, Bruno, Rafael; cursos ativo, pendente, novo, turma_curso, vazio_curso
    db_path = amb["db_path"]
    suf = uuid.uuid4().hex[:6]
    Database = abrir_banco(db_path)
    from core.security import get_password_hash  # noqa: PLC0415  (backend no sys.path depois de abrir_banco)
    senha_hash = get_password_hash(SENHA)

    def sql(comando, params=()):
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(comando, params)
            conn.commit()
        finally:
            conn.close()

    def aluno(nome, email):
        uid = Database.add_user(email, nome, senha_hash, role="student")
        if uid is None:
            raise RuntimeError(f"seed: não foi possível criar {email}")
        return {"uid": uid, "email": email, "nome": nome}

    def matricula(a, curso, preco, status, dias):
        eid = Database.create_enrollment(a["uid"], curso["id"], f"{curso['id']}:r3c:{uuid.uuid4().hex}")
        pid = Database.record_payment(eid, preco, "mercado_pago")
        quando = _ts(timedelta(days=dias))
        pagamento = {"active": "approved", "pending": "pending", "cancelled": "cancelled", "refunded": "refunded"}[status]
        if status == "pending":
            sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (quando, quando, pid))
        else:
            sql("UPDATE payments SET status = ?, transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
                (pagamento, f"mp-r3c-{uuid.uuid4().hex[:10]}", quando, quando, pid))
        sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, quando, eid))
        return eid

    ativo, pend, turma, novo, vazio = (seed["ativo"], seed["pendente"], seed["turma_curso"], seed["novo"],
                                       seed["vazio_curso"])
    carla = aluno("Carla Mendes de Oliveira", f"carla.r3c.{suf}@teste.com")
    carla["ativa"] = matricula(carla, ativo, 480.0, "active", 1)
    carla["lideranca"] = matricula(carla, vazio, 150.0, "active", 1)
    matricula(carla, pend, 290.0, "pending", 2)
    matricula(carla, turma, 520.0, "cancelled", 3)
    matricula(carla, novo, 350.0, "refunded", 4)
    sofia = aluno("Sofia Ribeiro Campos", f"sofia.r3c.{suf}@teste.com")
    sofia["ativa"] = matricula(sofia, ativo, 480.0, "active", 1)
    davi = aluno("Davi Tavares Lima", f"davi.r3c.{suf}@teste.com")
    davi["excel"] = matricula(davi, ativo, 480.0, "active", 1)
    davi["gestao"] = matricula(davi, turma, 520.0, "active", 1)

    st, corpo = _api(amb["api"], "POST", "/api/token", formulario={"username": carla["email"], "password": SENHA})
    if st != 200:
        raise RuntimeError(f"seed: login da Carla HTTP {st}")
    st, _ = _api(amb["api"], "POST", f"/api/student/enrollments/{carla['ativa']}/cancel-request",
                 {"reason": "Pedido do seed R3C"}, corpo["access_token"])
    if st != 200:
        raise RuntimeError(f"seed: pedido de cancelamento da Carla HTTP {st}")
    seed.update({"carla": carla, "sofia": sofia, "davi": davi})
    return seed


def _esperado(seed):
    """Conteúdo esperado de cada cartão, por conta e nome do curso (estado do seed, igual ao de hoje)."""
    ativo, pend, turma, novo, vazio = (seed["ativo"]["nome"], seed["pendente"]["nome"], seed["turma_curso"]["nome"],
                                       seed["novo"]["nome"], seed["vazio_curso"]["nome"])
    return {
        "marina": {ativo: dict(selo="Ativa", materiais=2, progresso="1 de 2 concluídos", cancelar=True),
                   pend: dict(selo="Pendente")},
        "rafael": {turma: dict(selo="Ativa", materiais=2, progresso="2 de 2 concluídos", turma=True, certificado=True,
                               cancelar=True),
                   vazio: dict(selo="Ativa", materiais=0, cancelar=True)},
        "carla": {ativo: dict(selo="Ativa", materiais=2, progresso="0 de 2 concluídos",
                              cancelamento="Cancelamento em análise", cancelar=False),
                  vazio: dict(selo="Ativa", materiais=0, cancelar=True),
                  pend: dict(selo="Pendente"), turma: dict(selo="Cancelada"), novo: dict(selo="Reembolsada")},
        "sofia": {ativo: dict(selo="Ativa", materiais=2, progresso="0 de 2 concluídos", cancelar=True)},
    }


# ------------------------------------------------------------------------------------------------- sessão (navegador)
class Sessao:
    """Contextos do Chromium por (conta, largura, movimento): o login é feito uma vez; cada teste abre uma página nova."""

    def __init__(self, browser, spa, seed):
        self.browser, self.spa, self.seed = browser, spa, seed
        self.contextos = {}
        self.erros = []
        self.dialogos = []
        self.cache = {}

    def exigir_seed(self):
        if "erro" in self.seed:
            raise Falha(f"seed falhou: {self.seed['erro']}")

    def conta(self, nome):
        self.exigir_seed()
        s = self.seed
        return {"marina": s["principal"], "rafael": s["rafael"], "bruno": s["vazio"], "carla": s["carla"],
                "sofia": s["sofia"], "davi": s["davi"]}[nome]

    def _anexar(self, page, registrar=True):
        def ao_console(msg):
            url = msg.location.get("url") or ""
            if registrar and msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
                self.erros.append(f"{msg.text[:100]} ({url})")

        def ao_dialogo(d):
            self.dialogos.append(f"{d.type}: {d.message[:80]}")
            d.dismiss()

        page.on("console", ao_console)
        page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"[:160]))
        page.on("dialog", ao_dialogo)

    def _novo_contexto(self, largura, reduzido):
        ctx = self.browser.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR",
                                       reduced_motion="reduce" if reduzido else "no-preference", accept_downloads=True)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        return ctx

    def _entrar(self, page, email):
        page.goto(self.spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /student (URL {page.url})")
        page.wait_for_load_state("networkidle")

    def _contexto(self, conta, largura, reduzido):
        chave = (conta, largura, reduzido)
        if chave not in self.contextos:
            ctx = self._novo_contexto(largura, reduzido)
            page = ctx.new_page()
            self._anexar(page)
            self._entrar(page, self.conta(conta)["email"])
            page.close()
            self.contextos[chave] = ctx
        return self.contextos[chave]

    @contextlib.contextmanager
    def pagina(self, conta, largura=1280, reduzido=True, secao='[data-testid="secao-cursos"]'):
        ctx = self._contexto(conta, largura, reduzido)
        page = ctx.new_page()
        self._anexar(page)
        try:
            page.goto(self.spa["base"] + "/student", wait_until="networkidle")
            page.locator(secao).wait_for(state="visible", timeout=TIMEOUT)
            page.mouse.move(1, 1)
            page.wait_for_timeout(450)
            yield page
        finally:
            page.close()

    @contextlib.contextmanager
    def pagina_com_falha_de_matriculas(self, largura=1280):
        """Conta Marina com GET /api/student/enrollments devolvendo 500 (o erro esperado não entra em `erros`)."""
        ctx = self._novo_contexto(largura, True)
        try:
            page = ctx.new_page()
            self._anexar(page, registrar=False)
            page.route("**/api/student/enrollments", lambda r: r.fulfill(status=500, content_type="application/json",
                                                                          body='{"detail":"erro simulado R3C"}'))
            self._entrar(page, self.conta("marina")["email"])
            page.locator('[data-testid="secao-cursos"]').wait_for(state="visible", timeout=TIMEOUT)
            page.wait_for_timeout(450)
            yield page
        finally:
            ctx.close()

    def cartoes(self, conta, largura):
        chave = ("cartoes", conta, largura)
        if chave not in self.cache:
            with self.pagina(conta, largura) as page:
                self.cache[chave] = page.evaluate(_JS_CARTOES, {"sel": SELETORES})
        return self.cache[chave]

    def fechar(self):
        for ctx in self.contextos.values():
            ctx.close()


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
    with ambiente_isolado("r3c") as ambiente:
        yield ambiente


@pytest.fixture(scope="module")
def sessao(browser, spa):
    seed = {}
    try:
        seed.update(semear(spa))
    except Exception as erro:  # o P0 mostra a falha do seed
        seed["erro"] = f"{type(erro).__name__}: {erro}"
    s = Sessao(browser, spa, seed)
    try:
        yield s
    finally:
        s.fechar()


# ------------------------------------------------------------------------------------------------- auxiliares de tela
def _abas_existem(page):
    n = page.locator(SEL_ABA).count()
    if n != 2:
        raise Falha(f"a barra de abas não existe como no painel da gestão: {n} elemento(s) [data-aba] dentro de "
                    f"{SEL_BARRA} (esperado 2: cursos e financeiro)")


def _ir_para_aba(page, chave, espera=500):
    _abas_existem(page)
    page.locator(f'[data-testid="atalho-{chave}"]').click(timeout=TIMEOUT)
    page.wait_for_timeout(espera)


def _estado_abas(page):
    return page.eval_on_selector_all(
        SEL_ABA, "els => Object.fromEntries(els.map(e => [e.getAttribute('data-aba'), "
                 "{atual: e.getAttribute('aria-current'), ativa: e.classList.contains('active')}]))")


def _violacoes_estado_abas(page, ativa, rotulo):
    v = []
    estado = _estado_abas(page)
    for chave in ("cursos", "financeiro"):
        e = estado.get(chave)
        if e is None:
            v.append(f"{rotulo}: aba {chave} ausente")
            continue
        if chave == ativa:
            if e["atual"] != "page":
                v.append(f"{rotulo}: aba {chave} ativa com aria-current={e['atual']!r} (esperado 'page')")
            if not e["ativa"]:
                v.append(f"{rotulo}: aba {chave} ativa sem a classe active")
        else:
            if e["atual"] not in (None, "false"):
                v.append(f"{rotulo}: aba {chave} inativa com aria-current={e['atual']!r} (esperado ausente)")
            if e["ativa"]:
                v.append(f"{rotulo}: aba {chave} inativa com a classe active")
    return v


def _violacoes_paineis(page, ativa, rotulo):
    p = page.evaluate(_JS_PAINEIS)
    outra = "financeiro" if ativa == "cursos" else "cursos"
    v = []
    if p[ativa]["n"] != 1 or not p[ativa]["visivel"]:
        v.append(f"{rotulo}: [data-testid=secao-{ativa}] aparece {p[ativa]['n']} vez(es), visível={p[ativa]['visivel']} (esperado 1 e visível)")
    esperado_h3 = "Meus cursos" if ativa == "cursos" else "Histórico financeiro"
    if p[ativa]["n"] and p[ativa]["h3"] != esperado_h3:
        v.append(f"{rotulo}: h3 do painel = {p[ativa]['h3']!r} (esperado {esperado_h3!r})")
    if p[outra]["n"] != 0:
        v.append(f"{rotulo}: [data-testid=secao-{outra}] está no DOM {p[outra]['n']} vez(es) com a aba {ativa} ativa (esperado 0: "
                 "só o painel da aba ativa existe, como na gestão)")
    if ativa == "cursos" and (p["pagamentos"] or p["recibos"]):
        v.append(f"{rotulo}: conteúdo do Financeiro (pagamentos {p['pagamentos']}, recibos {p['recibos']}) no DOM da aba Meus cursos")
    if ativa == "financeiro" and p["cards"]:
        v.append(f"{rotulo}: {p['cards']} cartão(ões) de curso no DOM da aba Financeiro")
    if p["idCursos" if ativa == "cursos" else "idFinanceiro"] != f"secao-{ativa}":
        v.append(f"{rotulo}: #secao-{ativa} não é o [data-testid=secao-{ativa}] (id mantido)")
    if p["idAssistente"] != "chat-panel":
        v.append(f"{rotulo}: #secao-assistente não é o [data-testid=chat-panel] (id mantido)")
    return v


def _violacoes_indicador(page, chave, rotulo):
    d = page.evaluate(_JS_INDICADOR, chave)
    if d["n"] != 1 or not d["ind"]:
        return [f"{rotulo}: {d['n']} [data-testid=abas-indicador] (esperado 1)"]
    if not d["aba"]:
        return [f"{rotulo}: aba {chave} não encontrada"]
    i, a, v = d["ind"], d["aba"], []
    if i["w"] < 1:
        v.append(f"{rotulo}: indicador sem largura {_r(i)}")
    if abs(i["l"] - a["l"]) > 2 or abs(i["w"] - a["w"]) > 2:
        v.append(f"{rotulo}: indicador em x={i['l']:.0f} largura {i['w']:.0f} e aba {chave} em x={a['l']:.0f} largura {a['w']:.0f} "
                 "(tolerância de 2 px)")
    if i["b"] < a["b"] - 4 or i["b"] > a["b"] + 4 or i["t"] < a["t"]:
        v.append(f"{rotulo}: indicador {_r(i)} não está na base da aba {chave} {_r(a)}")
    return v


def _rota_chat(url):
    return urlsplit(url).path.rstrip("/") == "/api/student/chat"


def _pedir_acao(page, acao, texto="Quero abrir (R3C)"):
    """Envia uma mensagem; a resposta do POST /api/student/chat é interceptada para trazer a ação `open` pedida."""
    corpo = {"status": "success", "message": f"Resposta interceptada R3C {acao['target']}", "actions": [acao], "sources": [],
             "pii_masked": False}

    def tratar(rota):
        if rota.request.method == "POST":
            rota.fulfill(status=200, content_type="application/json", body=json.dumps(corpo))
        else:
            rota.continue_()

    page.route(_rota_chat, tratar)
    try:
        page.locator('[data-testid="chat-input"]').fill(texto, timeout=TIMEOUT)
        with page.expect_response(lambda r: r.request.method == "POST" and _rota_chat(r.url), timeout=TIMEOUT * 2):
            page.locator('[data-testid="chat-send"]').click(timeout=TIMEOUT)
        botao = page.locator('[data-testid="chat-acao-abrir"]').filter(has_text=acao["label"])
        botao.first.wait_for(state="visible", timeout=TIMEOUT)
        return botao.first
    finally:
        page.unroute(_rota_chat, tratar)


def _no_fim_da_pagina(page):
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_timeout(300)


def _violacoes_na_vista(page, seletor, rotulo):
    d = page.evaluate(_JS_NA_VISTA, seletor)
    if not d:
        return [f"{rotulo}: {seletor} ausente"]
    if not d["visivel"] or d["topo"] < -5 or d["topo"] > 0.6 * d["janela"]:
        return [f"{rotulo}: {seletor} com topo em {d['topo']:.0f}px (janela de {d['janela']}px, rolagem {d['rolagem']:.0f}px): "
                "esperado visível e rolado para a vista (topo entre -5 px e 60% da janela)"]
    return []


def _card_de(page, nome):
    """Cartão pelo nome do curso (estável: filtros por botões que somem ao clicar deixam de casar)."""
    return page.locator(SEL_CARD).filter(has=page.locator(".curso-nome", has_text=nome)).first


def _linhas(cards):
    """Agrupa cartões por linha visual: o cartão entra na linha enquanto começa antes do fim do mais baixo da linha."""
    linhas = []
    for c in sorted(cards, key=lambda c: (c["rect"]["t"], c["rect"]["l"])):
        if linhas and c["rect"]["t"] < min(x["rect"]["b"] for x in linhas[-1]) - 2:
            linhas[-1].append(c)
        else:
            linhas.append([c])
    return linhas


def _cartao(medida, nome):
    return next((c for c in medida["cards"] if c["nome"] == nome), None)


def _peca(c, chave):
    return c["pecas"][chave]


# ------------------------------------------------------------------------------------------------- P0
def test_p0_precondicao_do_seed(sessao):
    sessao.exigir_seed()
    esperado = {"marina": 2, "rafael": 2, "bruno": 0, "carla": 5, "sofia": 1, "davi": 2}
    v = []
    for conta, n in esperado.items():
        with sessao.pagina(conta, 1280) as page:
            m = page.evaluate(_JS_CARTOES, {"sel": SELETORES})
            if m["n"] != n:
                v.append(f"{conta}: {m['n']} cartões (esperado {n})")
                continue
            if conta == "carla":
                selos = sorted(_peca(c, "selo")[0]["texto"] for c in m["cards"] if _peca(c, "selo"))
                if selos != ["Ativa", "Ativa", "Cancelada", "Pendente", "Reembolsada"]:
                    v.append(f"carla: selos {selos}")
                if sum(len(_peca(c, "cancelamento")) for c in m["cards"]) != 1:
                    v.append("carla: esperado um 'Cancelamento em análise' (pedido aberto do seed)")
            if conta == "davi" and sum(len(_peca(c, "cancelar")) for c in m["cards"]) != 2:
                v.append("davi: os dois cartões deveriam oferecer 'Pedir cancelamento'")
            if conta == "rafael" and sum(len(_peca(c, "certificado")) for c in m["cards"]) != 1:
                v.append("rafael: esperado um 'Baixar certificado'")
    _exigir(v, "pré-condição do seed")


# ------------------------------------------------------------------------------------------------- T abas
def test_t1_barra_de_abas_no_padrao_da_gestao(sessao):
    v = []
    for largura in (1280, 390):
        with sessao.pagina("marina", largura) as page:
            m = page.evaluate(_JS_ABAS)
        r = f"@{largura}px"
        if m["nUl"] != 1:
            v.append(f"{r}: {m['nUl']} elemento(s) {SEL_BARRA} (esperado 1, como no painel da gestão)")
        if m["antigos"]:
            v.append(f"{r}: o nav.aluno-atalhos antigo continua na tela ({m['antigos']} elemento(s) .aluno-atalho/.aluno-atalhos)")
        if m["nUl"] != 1:
            continue
        if [a["aba"] for a in m["abas"]] != ["cursos", "financeiro"]:
            v.append(f"{r}: abas {[a['aba'] for a in m['abas']]} (esperado ['cursos', 'financeiro'], nesta ordem)")
        textos = {"cursos": "Meus cursos", "financeiro": "Financeiro"}
        for a in m["abas"]:
            if a["texto"] != textos.get(a["aba"]):
                v.append(f"{r}: aba {a['aba']} com o texto {a['texto']!r} (esperado {textos.get(a['aba'])!r})")
            if a["testid"] != f"atalho-{a['aba']}":
                v.append(f"{r}: aba {a['aba']} com data-testid={a['testid']!r} (esperado 'atalho-{a['aba']}')")
            if a["tag"] != "button" or a["tipo"] != "button" or "nav-link" not in a["classes"]:
                v.append(f"{r}: aba {a['aba']} deveria ser <button type=\"button\" class=\"nav-link\"> (é <{a['tag']} type={a['tipo']!r} {a['classes']}>)")
            if not a["noLi"] or not a["liNavItem"]:
                v.append(f"{r}: aba {a['aba']} fora de um li.nav-item filho direto da ul")
        i = m["ind"]
        if i["n"] != 1 or not i["dentro"]:
            v.append(f"{r}: {i['n']} [data-testid=abas-indicador], dentro da barra={i['dentro']} (esperado 1 dentro da ul)")
        else:
            if i["tag"] != "li" or "gt-abas-indicador" not in i["classes"]:
                v.append(f"{r}: indicador deveria ser li.gt-abas-indicador (é <{i['tag']}> {i['classes']})")
            if i["ariaHidden"] != "true":
                v.append(f"{r}: indicador sem aria-hidden=\"true\" ({i['ariaHidden']!r})")
        for a in m["itens"]:
            if a["rect"]["h"] < 44:
                v.append(f"{r}: '{a['texto']}' com {a['rect']['h']:.0f}px de altura (esperado >= 44px)")
            if float(a["fonte"].replace("px", "")) < 14:
                v.append(f"{r}: '{a['texto']}' com fonte de {a['fonte']} (esperado >= 14px)")
    _exigir(v, "barra de abas")


def test_t2_estado_inicial_meus_cursos(sessao):
    v = []
    for largura in (1280, 390):
        with sessao.pagina("marina", largura) as page:
            _abas_existem(page)
            v += _violacoes_estado_abas(page, "cursos", f"@{largura}px")
            v += _violacoes_paineis(page, "cursos", f"@{largura}px")
    _exigir(v, "estado inicial das abas")


def test_t3_troca_para_financeiro_e_volta(sessao):
    v = []
    with sessao.pagina("marina", 1280) as page:
        _ir_para_aba(page, "financeiro")
        v += _violacoes_estado_abas(page, "financeiro", "Financeiro")
        v += _violacoes_paineis(page, "financeiro", "Financeiro")
        p = page.evaluate(_JS_PAINEIS)
        if sorted(p["pagamentos"]) != ["Aprovado", "Pendente"]:
            v.append(f"Financeiro: status de pagamento {p['pagamentos']} (esperado ['Aprovado', 'Pendente'] da Marina)")
        if not page.locator('[data-testid="secao-financeiro"] table tbody tr').count() == 2:
            v.append("Financeiro: a tabela de pagamentos deveria ter 2 linhas dentro de secao-financeiro")
        _ir_para_aba(page, "cursos")
        v += _violacoes_estado_abas(page, "cursos", "de volta a Meus cursos")
        v += _violacoes_paineis(page, "cursos", "de volta a Meus cursos")
        if page.evaluate(_JS_PAINEIS)["cards"] != 2:
            v.append("de volta a Meus cursos: esperado 2 cartões da Marina")
    _exigir(v, "troca de aba")


@pytest.mark.parametrize("largura", LARGURAS)
def test_t4_indicador_sob_a_aba_ativa(sessao, largura):
    v = []
    with sessao.pagina("marina", largura, reduzido=False) as page:
        _abas_existem(page)
        v += _violacoes_indicador(page, "cursos", f"@{largura}px inicial")
        for chave in ("financeiro", "cursos", "financeiro"):
            _ir_para_aba(page, chave, espera=800)
            v += _violacoes_indicador(page, chave, f"@{largura}px aba {chave}")
    _exigir(v, "posição do indicador")


def test_t5_indicador_acompanha_o_resize(sessao):
    v = []
    with sessao.pagina("marina", 1280, reduzido=False) as page:
        _ir_para_aba(page, "financeiro", espera=800)
        v += _violacoes_indicador(page, "financeiro", "antes do resize")
        # Muda a geometria das abas sem disparar evento: o indicador fica velho até a janela ser redimensionada.
        page.add_style_tag(content=".nav-tabs.gt-abas .nav-link { padding-left: 56px !important; padding-right: 56px !important; }")
        page.wait_for_timeout(300)
        page.set_viewport_size({"width": 1180, "height": 900})
        page.wait_for_timeout(900)
        v += _violacoes_indicador(page, "financeiro", "depois de mudar o padding e redimensionar para 1180 px")
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(900)
        v += _violacoes_indicador(page, "financeiro", "depois de redimensionar para 390 px")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_timeout(900)
        v += _violacoes_indicador(page, "financeiro", "depois de voltar para 1280 px")
    _exigir(v, "indicador no resize (window:resize)")


@pytest.mark.parametrize("largura", (1280, 390))
def test_t6_perfil_e_assistente_na_barra_fora_das_abas(sessao, largura):
    with sessao.pagina("marina", largura) as page:
        m = page.evaluate(_JS_ABAS)
    r = f"@{largura}px"
    if m["nUl"] != 1:
        raise Falha(f"{r}: {m['nUl']} elemento(s) {SEL_BARRA}: os dois itens extras ficam no fim da mesma barra de abas")
    v = []
    for chave, tag, texto in (("perfil", "a", "Meu perfil"), ("assistente", "button", "Assistente")):
        x = m[chave]
        if x["n"] != 1:
            v.append(f"{r}: [data-testid=atalho-{chave}] aparece {x['n']} vez(es) (esperado 1)")
            continue
        i = x["info"]
        if not x["dentro"]:
            v.append(f"{r}: atalho-{chave} fora da ul.gt-abas das abas (deve ficar no fim da mesma barra)")
        if not x["depois"]:
            v.append(f"{r}: atalho-{chave} antes das abas no DOM (deve vir depois das duas abas)")
        if i["texto"] != texto or i["tag"] != tag:
            v.append(f"{r}: atalho-{chave} é <{i['tag']}> {i['texto']!r} (esperado <{tag}> {texto!r})")
        if chave == "perfil" and i["href"] != "/student/perfil":
            v.append(f"{r}: Meu perfil com href {i['href']!r} (esperado /student/perfil)")
        if chave == "assistente" and i["tipo"] != "button":
            v.append(f"{r}: Assistente sem type=\"button\" ({i['tipo']!r})")
        if i["aba"] is not None:
            v.append(f"{r}: atalho-{chave} com data-aba={i['aba']!r} (não é uma aba)")
        if i["atual"] not in (None, "false") or i["ativa"]:
            v.append(f"{r}: atalho-{chave} com aria-current={i['atual']!r} / active={i['ativa']} (não é uma aba)")
        if i["rect"]["h"] < 44:
            v.append(f"{r}: atalho-{chave} com {i['rect']['h']:.0f}px de altura (esperado >= 44px)")
        inativa = next((a for a in m["abas"] if not a["ativa"]), None)
        if inativa:
            for campo, nome in (("fonte", "fonte"), ("peso", "peso"), ("familia", "família"), ("padE", "padding esquerdo"),
                                ("padD", "padding direito"), ("raio", "raio"), ("fundo", "fundo")):
                if i[campo] != inativa[campo]:
                    v.append(f"{r}: atalho-{chave} com {nome} {i[campo]!r} diferente do da aba inativa {inativa[campo]!r} "
                             "(deve parecer a mesma barra)")
        if largura == 1280:
            financeiro = next((a for a in m["abas"] if a["aba"] == "financeiro"), None)
            if financeiro:
                cy_a = (financeiro["rect"]["t"] + financeiro["rect"]["b"]) / 2
                cy_i = (i["rect"]["t"] + i["rect"]["b"]) / 2
                if abs(cy_a - cy_i) > 6 or i["rect"]["l"] < financeiro["rect"]["r"] - 1:
                    v.append(f"{r}: atalho-{chave} em {_r(i['rect'])} deveria ficar na mesma faixa e à direita da aba Financeiro "
                             f"{_r(financeiro['rect'])}")
        else:
            alcancavel = i["rect"]["l"] >= 0 and i["rect"]["r"] <= 390 + 0.5
            if not alcancavel and m["ul"]["overflowX"] not in ("auto", "scroll"):
                v.append(f"{r}: atalho-{chave} fora da janela ({_r(i['rect'])}) e a barra não rola na horizontal "
                         f"(overflow-x {m['ul']['overflowX']!r}): o item ficaria inalcançável")
    if len([a for a in m["abas"]]) != 2:
        v.append(f"{r}: {len(m['abas'])} elementos com data-aba (esperado 2: perfil e assistente não são abas)")
    _exigir(v, "Meu perfil e Assistente na barra")


def test_t7_assistente_rola_e_perfil_navega(sessao):
    v = []
    with sessao.pagina("carla", 1280) as page:
        _abas_existem(page)
        page.set_viewport_size({"width": 1280, "height": 600})
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        antes = page.evaluate(_JS_NA_VISTA, '[data-testid="chat-panel"]')
        if antes["visivel"]:
            raise Falha("pré-condição: o chat já está na janela antes do clique em Assistente (página curta demais para provar a rolagem)")
        page.locator('[data-testid="atalho-assistente"]').click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_na_vista(page, '[data-testid="chat-panel"]', "Assistente")
        if urlsplit(page.url).path != "/student":
            v.append(f"Assistente navegou para {page.url} (deveria só rolar)")
        v += _violacoes_estado_abas(page, "cursos", "depois de Assistente")
        v += _violacoes_indicador(page, "cursos", "depois de Assistente")
        page.evaluate("window.scrollTo(0, 0)")
        page.locator('[data-testid="atalho-perfil"]').click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student/perfil", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            v.append(f"Meu perfil não levou a /student/perfil (URL {page.url})")
        else:
            if page.locator("h1").count() != 1:
                v.append("tela do perfil sem um único h1")
    _exigir(v, "Assistente e Meu perfil")


def test_t8_kpis_acima_das_abas_e_visiveis_nas_duas(sessao):
    v = []
    for largura in (1280, 390):
        with sessao.pagina("marina", largura) as page:
            _abas_existem(page)
            valores = {}
            for chave in ("cursos", "financeiro"):
                if chave != "cursos":
                    _ir_para_aba(page, chave)
                m = page.evaluate(_JS_ABAS)
                r = f"@{largura}px aba {chave}"
                if not m["resumo"] or not m["resumoAntes"] or m["resumo"]["b"] > m["ul"]["rect"]["t"] + 1:
                    v.append(f"{r}: [data-testid=aluno-resumo] {m['resumo'] and _r(m['resumo'])} não está acima da barra de abas "
                             f"{_r(m['ul']['rect'])}")
                visiveis = page.locator('[data-testid="aluno-resumo"]').is_visible()
                if not visiveis:
                    v.append(f"{r}: a faixa de KPIs não está visível")
                valores[chave] = [_norm(page.locator(f'[data-testid="{t}"]').inner_text())
                                  for t in ("resumo-cursos-ativos", "resumo-pagamentos-pendentes", "resumo-total-investido")]
            if valores["cursos"] != valores["financeiro"]:
                v.append(f"@{largura}px: KPIs mudaram com a aba: {valores['cursos']} -> {valores['financeiro']}")
            if valores["cursos"] != ["1", "1", "R$ 480,00"]:
                v.append(f"@{largura}px: KPIs da Marina {valores['cursos']} (esperado ['1', '1', 'R$ 480,00'])")
    _exigir(v, "faixa de KPIs")


def test_t9_chat_abaixo_do_painel_e_funcional(sessao):
    v = []
    with sessao.pagina("marina", 1280) as page:
        _abas_existem(page)
        for chave in ("cursos", "financeiro"):
            if chave != "cursos":
                _ir_para_aba(page, chave)
            p = page.evaluate(_JS_PAINEIS)
            r = f"aba {chave}"
            if p["chat"]["n"] != 1 or not p["chat"]["visivel"]:
                v.append(f"{r}: [data-testid=chat-panel] aparece {p['chat']['n']} vez(es), visível={p['chat']['visivel']}")
                continue
            if p[chave]["rect"] and p["chat"]["rect"]["t"] < p[chave]["rect"]["b"] - 1:
                v.append(f"{r}: o chat {_r(p['chat']['rect'])} não está abaixo do painel {_r(p[chave]['rect'])}")
            if p["chat"]["h3"] != "Assistente virtual":
                v.append(f"{r}: h3 do chat {p['chat']['h3']!r} (esperado 'Assistente virtual')")
            for tid in ("chat-input", "chat-send", "chat-aviso-gravacao"):
                if page.locator(f'[data-testid="{tid}"]').count() != 1:
                    v.append(f"{r}: [data-testid={tid}] aparece {page.locator(f'[data-testid={tid}]').count()} vez(es) (esperado 1)")
        # Com a aba Financeiro ativa o chat funciona de ponta a ponta (resposta do backend de teste).
        antes = page.locator('[data-testid="chat-message"]').count()
        page.locator('[data-testid="chat-input"]').fill(PERGUNTA_CHAT)
        page.locator('[data-testid="chat-send"]').click(timeout=TIMEOUT)
        try:
            page.wait_for_function("n => document.querySelectorAll('[data-testid=\"chat-message\"]').length >= n + 2", arg=antes,
                                   timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            v.append("Financeiro: o chat não mostrou a pergunta e a resposta")
        else:
            papeis = page.eval_on_selector_all('[data-testid="chat-message"]', "els => els.map(e => e.getAttribute('data-role'))")
            if papeis[-2:] != ["user", "assistant"]:
                v.append(f"Financeiro: papéis das duas últimas mensagens do chat {papeis[-2:]} (esperado ['user', 'assistant'])")
    _exigir(v, "chat abaixo das abas")


def test_t10_trocar_de_aba_nao_chama_a_api(sessao):
    with sessao.pagina("marina", 1280) as page:
        _abas_existem(page)
        chamadas = []
        page.on("request", lambda req: chamadas.append(f"{req.method} {urlsplit(req.url).path}") if "/api/" in req.url else None)
        for chave in ("financeiro", "cursos", "financeiro", "cursos"):
            _ir_para_aba(page, chave, espera=400)
        page.wait_for_timeout(600)
    _exigir([f"requisição nova: {c}" for c in chamadas], "chamadas à API ao trocar de aba (o carregamento fica no ngOnInit)")


def test_t11_recibo_aberto_sobrevive_a_troca_de_aba(sessao):
    v = []
    with sessao.pagina("marina", 1280) as page:
        _ir_para_aba(page, "financeiro")
        linha = page.locator('[data-testid="secao-financeiro"] tbody tr').filter(
            has=page.locator('[data-testid="pagamento-status"]', has_text="Aprovado")).first
        linha.get_by_role("button", name="Ver recibo").click(timeout=TIMEOUT)
        recibo = page.locator(".aluno-recibo")
        recibo.wait_for(state="visible", timeout=TIMEOUT)
        texto = _norm(recibo.inner_text())
        if not re.search(r"Recibo #\d+", texto):
            v.append(f"recibo aberto sem 'Recibo #<id>': {texto[:80]!r}")
        _ir_para_aba(page, "cursos")
        if page.locator(".aluno-recibo").count():
            v.append("o recibo aparece na aba Meus cursos (pertence ao Financeiro)")
        _ir_para_aba(page, "financeiro")
        if page.locator(".aluno-recibo").count() != 1 or not page.locator(".aluno-recibo").is_visible():
            v.append("o recibo aberto sumiu ao voltar para o Financeiro")
        elif _norm(page.locator(".aluno-recibo").inner_text()) != texto:
            v.append("o recibo mudou de conteúdo ao voltar para o Financeiro")
        if page.locator('[data-testid="recibo-pdf"]').count() != 1:
            v.append("a linha do pagamento aprovado deveria manter um único 'Baixar PDF' (recibo-pdf)")
    _exigir(v, "recibo aberto ao trocar de aba")


def test_t12_troca_de_aba_com_edicao_aberta_sem_erro(sessao):
    with sessao.pagina("marina", 1280) as page:
        _abas_existem(page)
        antes = len(sessao.erros)
        card = _card_de(page, sessao.seed["ativo"]["nome"])
        card.locator('[data-testid="curso-avaliacao-comentario"]').fill("rascunho da avaliação")
        card.locator('[data-testid="curso-avaliacao-nota"]').select_option(label="3 ★")
        card.locator('[data-testid="curso-cancelar"]').click()
        card.locator('[data-testid="curso-cancelar-motivo"]').fill("rascunho do motivo")
        for chave in ("financeiro", "cursos", "financeiro", "cursos"):
            _ir_para_aba(page, chave, espera=350)
        if page.locator(SEL_CARD).count() != 2:
            raise Falha("depois de trocar de aba, a aba Meus cursos não mostra os 2 cartões da Marina")
    _exigir(sessao.erros[antes:], "erros de console ao trocar de aba com avaliação e cancelamento em edição")


# ------------------------------------------------------------------------------------------------- O ações open
def test_o1_acao_open_financeiro_seleciona_a_aba(sessao):
    v = []
    with sessao.pagina("carla", 1280) as page:
        _abas_existem(page)
        botao = _pedir_acao(page, {"type": "open", "target": "financeiro", "label": "Abrir Financeiro R3C"})
        _no_fim_da_pagina(page)
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_estado_abas(page, "financeiro", "depois da ação open/financeiro")
        v += _violacoes_paineis(page, "financeiro", "depois da ação open/financeiro")
        v += _violacoes_indicador(page, "financeiro", "depois da ação open/financeiro")
        v += _violacoes_na_vista(page, '[data-testid="secao-financeiro"]', "open/financeiro")
        if urlsplit(page.url).path != "/student":
            v.append(f"a ação trocou a rota para {page.url} (deveria só selecionar a aba)")
    _exigir(v, "ação open/financeiro")


def test_o2_acao_open_cursos_seleciona_a_aba(sessao):
    v = []
    with sessao.pagina("carla", 1280) as page:
        _ir_para_aba(page, "financeiro")
        botao = _pedir_acao(page, {"type": "open", "target": "cursos", "label": "Abrir Cursos R3C"})
        _no_fim_da_pagina(page)
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_estado_abas(page, "cursos", "depois da ação open/cursos (vindo do Financeiro)")
        v += _violacoes_paineis(page, "cursos", "depois da ação open/cursos (vindo do Financeiro)")
        v += _violacoes_indicador(page, "cursos", "depois da ação open/cursos (vindo do Financeiro)")
        v += _violacoes_na_vista(page, '[data-testid="secao-cursos"]', "open/cursos")
        # Já na aba Meus cursos: a ação só rola, sem trocar nada.
        botao = _pedir_acao(page, {"type": "open", "target": "cursos", "label": "Abrir Cursos de novo R3C"})
        _no_fim_da_pagina(page)
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_estado_abas(page, "cursos", "ação open/cursos já na aba")
        v += _violacoes_na_vista(page, '[data-testid="secao-cursos"]', "open/cursos já na aba")
    _exigir(v, "ação open/cursos")


def test_o3_acao_open_perfil_navega(sessao):
    with sessao.pagina("carla", 1280) as page:
        _abas_existem(page)
        botao = _pedir_acao(page, {"type": "open", "target": "perfil", "label": "Abrir Perfil R3C"})
        botao.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student/perfil", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"a ação open/perfil não levou a /student/perfil (URL {page.url})")


# ------------------------------------------------------------------------------------------------- C cartões
COLUNAS = {1280: lambda n: n >= 3, 768: lambda n: n == 2, 390: lambda n: n == 1}
DESCRICAO_COLUNAS = {1280: ">= 3", 768: "2", 390: "1"}


@pytest.mark.parametrize("largura", LARGURAS)
def test_c1_grade_de_cartoes(sessao, largura):
    m = sessao.cartoes("carla", largura)
    v = []
    if not m["lista"]:
        v.append(".cursos-lista ausente")
    elif not m["lista"]["contem"]:
        v.append(".cursos-lista não contém todos os [data-testid=curso-card]")
    linhas = _linhas(m["cards"])
    colunas = max(len(x) for x in linhas) if linhas else 0
    if not COLUNAS[largura](colunas):
        v.append(f"{colunas} coluna(s) a {largura}px com 5 cartões (esperado {DESCRICAO_COLUNAS[largura]}); linhas: "
                 f"{[len(x) for x in linhas]}; cartões em {[_r(c['rect']) for c in m['cards']][:3]}")
    for x in linhas:
        if len({round(c["rect"]["l"]) for c in x}) != len(x):
            v.append(f"cartões da mesma linha com o mesmo x: {[_r(c['rect']) for c in x]}")
    _exigir(v, f"grade de cartões a {largura}px")


@pytest.mark.parametrize("conta", ("carla", "marina", "rafael"))
def test_c2_mesma_linha_mesmo_topo_e_altura(sessao, conta):
    v = []
    maior_linha = 0
    for largura in LARGURAS:
        m = sessao.cartoes(conta, largura)
        r = f"{conta} @{largura}px"
        linhas = _linhas(m["cards"])
        maior_linha = max([maior_linha] + [len(x) for x in linhas]) if largura != 390 else maior_linha
        for x in linhas:
            tops = [c["rect"]["t"] for c in x]
            alts = [c["rect"]["h"] for c in x]
            if max(tops) - min(tops) > 2:
                v.append(f"{r}: cartões da mesma linha com topos diferentes {[round(t) for t in tops]}")
            if max(alts) - min(alts) > 1:
                v.append(f"{r}: cartões da mesma linha com alturas diferentes {[round(h) for h in alts]} (devem esticar à mesma altura)")
            for a, b in zip(sorted(x, key=lambda c: c["rect"]["l"]), sorted(x, key=lambda c: c["rect"]["l"])[1:]):
                if b["rect"]["l"] - a["rect"]["r"] < 8:
                    v.append(f"{r}: só {b['rect']['l'] - a['rect']['r']:.0f}px entre '{a['nome'][:20]}' e '{b['nome'][:20]}' (esperado >= 8px)")
        for a, b in zip(linhas, linhas[1:]):
            base = max(c["rect"]["b"] for c in a)
            topo = min(c["rect"]["t"] for c in b)
            if topo < base + 8 - 0.5:
                v.append(f"{r}: só {topo - base:.0f}px entre duas linhas de cartões (esperado >= 8px)")
        for i, a in enumerate(m["cards"]):
            for b in m["cards"][i + 1:]:
                dx = min(a["rect"]["r"], b["rect"]["r"]) - max(a["rect"]["l"], b["rect"]["l"])
                dy = min(a["rect"]["b"], b["rect"]["b"]) - max(a["rect"]["t"], b["rect"]["t"])
                if dx > 1 and dy > 1:
                    v.append(f"{r}: cartões '{a['nome'][:20]}' e '{b['nome'][:20]}' se sobrepõem ({dx:.0f}x{dy:.0f}px)")
    if conta == "carla" and maior_linha < 2:
        v.append("pré-condição: nenhuma linha com 2+ cartões a 1280 e 768 px (cartões não estão em grade)")
    _exigir(v, f"alinhamento dos cartões de {conta}")


def _violacoes_dentro_do_cartao(m, esperado, rotulo):
    v = []
    for chave, n in m["fora"].items():
        if n:
            v.append(f"{rotulo}: {n} elemento(s) '{SELETORES[chave]}' dentro de secao-cursos mas FORA de qualquer curso-card")
    for c in m["cards"]:
        nome = c["nome"]
        e = esperado.get(nome)
        r = f"{rotulo} '{nome[:28]}'"
        if e is None:
            v.append(f"{rotulo}: cartão inesperado '{nome[:40]}'")
            continue
        for texto in c["estouros"]:
            v.append(f"{r}: {texto}")
        selo, entrar, aviso = _peca(c, "selo"), _peca(c, "entrar"), _peca(c, "aviso")
        icone = _peca(c, "icone")
        if len(icone) != 1 or not re.fullmatch(r"[^\W_]{1,3}", icone[0]["texto"] or ""):
            v.append(f"{r}: ícone de iniciais ausente ou inválido ({[i['texto'] for i in icone]})")
        if len(_peca(c, "nome")) != 1:
            v.append(f"{r}: {len(_peca(c, 'nome'))} .curso-nome (esperado 1)")
        if len(selo) != 1 or selo[0]["texto"] != e["selo"]:
            v.append(f"{r}: selo {[s['texto'] for s in selo]} (esperado ['{e['selo']}'])")
        dados = _peca(c, "data")
        if len(dados) != 1 or not re.fullmatch(r"Matrícula em \d{2}/\d{2}/\d{4}", dados[0]["texto"]):
            v.append(f"{r}: data da matrícula {[d['texto'] for d in dados]}")
        if len(_peca(c, "turma")) != (1 if e.get("turma") else 0):
            v.append(f"{r}: {len(_peca(c, 'turma'))} linha(s) de turma (esperado {1 if e.get('turma') else 0})")
        if e["selo"] == "Ativa":
            if len(entrar) != 1 or entrar[0]["texto"] != "Entrar no curso" or not (entrar[0]["href"] or "").startswith("/student/curso/"):
                v.append(f"{r}: 'Entrar no curso' = {[(x['texto'], x['href']) for x in entrar]}")
            if aviso:
                v.append(f"{r}: matrícula ativa com mensagem de sem acesso")
            if len(_peca(c, "material")) != e["materiais"]:
                v.append(f"{r}: {len(_peca(c, 'material'))} link(s) de material (esperado {e['materiais']})")
            if len(_peca(c, "concluido")) != e["materiais"]:
                v.append(f"{r}: {len(_peca(c, 'concluido'))} caixa(s) de aula concluída (esperado {e['materiais']})")
            if e["materiais"]:
                prog = _peca(c, "progresso")
                if len(prog) != 1 or prog[0]["texto"] != e["progresso"]:
                    v.append(f"{r}: progresso {[p['texto'] for p in prog]} (esperado '{e['progresso']}')")
                if len(_peca(c, "barra")) != 1:
                    v.append(f"{r}: {len(_peca(c, 'barra'))} [role=progressbar] (esperado 1)")
            elif _peca(c, "barra") or _peca(c, "progresso"):
                v.append(f"{r}: curso sem materiais com barra ou texto de progresso")
            if len(_peca(c, "certificado")) != (1 if e.get("certificado") else 0):
                v.append(f"{r}: {len(_peca(c, 'certificado'))} 'Baixar certificado' (esperado {1 if e.get('certificado') else 0})")
            for chave in ("comentario", "nota", "enviar"):
                if len(_peca(c, chave)) != 1:
                    v.append(f"{r}: {len(_peca(c, chave))} controle(s) de avaliação '{chave}' (esperado 1 por cartão)")
            if len(_peca(c, "cancelar")) != (1 if e["cancelar"] else 0):
                v.append(f"{r}: {len(_peca(c, 'cancelar'))} 'Pedir cancelamento' (esperado {1 if e['cancelar'] else 0})")
            status = _peca(c, "cancelamento")
            if e.get("cancelamento"):
                if len(status) != 1 or status[0]["texto"] != e["cancelamento"]:
                    v.append(f"{r}: status de cancelamento {[s['texto'] for s in status]} (esperado '{e['cancelamento']}')")
            elif status:
                v.append(f"{r}: status de cancelamento inesperado {[s['texto'] for s in status]}")
        else:
            esperado_aviso = MENSAGENS_SEM_ACESSO[e["selo"]]
            if entrar:
                v.append(f"{r}: matrícula {e['selo']} com 'Entrar no curso'")
            if len(aviso) != 1 or aviso[0]["texto"] != esperado_aviso:
                v.append(f"{r}: mensagem de sem acesso {[a['texto'] for a in aviso]} (esperado '{esperado_aviso}')")
            for chave in ("material", "concluido", "barra", "comentario", "nota", "enviar", "certificado", "cancelar"):
                if _peca(c, chave):
                    v.append(f"{r}: matrícula {e['selo']} com '{SELETORES[chave]}' ({len(_peca(c, chave))})")
            if c["temUrlMaterial"]:
                v.append(f"{r}: matrícula {e['selo']} com URL de material no HTML do cartão")
        for chave, lista in c["pecas"].items():
            for x in lista:
                if not x["geo"] and chave not in ("icone",) and not (chave == "ok" or chave == "atual"):
                    v.append(f"{r}: '{SELETORES[chave]}' sem caixa visível")
    return v


@pytest.mark.parametrize("largura", LARGURAS)
def test_c3_tudo_dentro_de_cada_cartao(sessao, largura):
    esperado = _esperado(sessao.seed)
    v = []
    for conta in ("carla", "marina", "rafael", "sofia"):
        m = sessao.cartoes(conta, largura)
        if m["n"] != len(esperado[conta]):
            v.append(f"{conta} @{largura}px: {m['n']} cartões (esperado {len(esperado[conta])})")
            continue
        v += _violacoes_dentro_do_cartao(m, esperado[conta], f"{conta} @{largura}px")
    _exigir(v, f"conteúdo dentro de cada cartão a {largura}px")


@pytest.mark.parametrize("largura", LARGURAS)
def test_c4_entrar_no_curso_visivel_44px_e_alinhado(sessao, largura):
    v = []
    for conta in ("carla", "marina", "rafael"):
        m = sessao.cartoes(conta, largura)
        r = f"{conta} @{largura}px"
        for c in m["cards"]:
            n = c["nome"][:28]
            for texto in c["rolagens"]:
                v.append(f"{r} '{n}': {texto} (o cartão não pode cortar nem rolar o conteúdo)")
            entrar = _peca(c, "entrar")
            if entrar:
                e = entrar[0]["rect"]
                if not entrar[0]["geo"] or e["h"] < 44 or e["w"] < 44:
                    v.append(f"{r} '{n}': 'Entrar no curso' {_r(e)} (esperado visível, altura e largura >= 44px)")
                if e["b"] > c["rect"]["b"] + 1 or e["t"] < c["rect"]["t"] - 1:
                    v.append(f"{r} '{n}': 'Entrar no curso' {_r(e)} fora do cartão {_r(c['rect'])}")
            else:
                aviso = _peca(c, "aviso")
                if aviso and (not aviso[0]["geo"] or aviso[0]["rect"]["b"] > c["rect"]["b"] + 1):
                    v.append(f"{r} '{n}': a mensagem de sem acesso não está visível dentro do cartão")
        for linha in _linhas(m["cards"]):
            com = [c for c in linha if _peca(c, "entrar")]
            if len(com) < 2:
                continue
            bases = [c["rect"]["b"] - _peca(c, "entrar")[0]["rect"]["b"] for c in com]
            if max(bases) - min(bases) <= 2:
                continue
            for c in com:
                e = _peca(c, "entrar")[0]["rect"]
                centro = (e["t"] + e["b"]) / 2 - c["rect"]["t"]
                if centro > 0.4 * c["rect"]["h"]:
                    v.append(f"{r}: 'Entrar no curso' de '{c['nome'][:24]}' não está alinhado na linha: distâncias da base "
                             f"{[round(b) for b in bases]} e centro a {centro:.0f}px do topo de {c['rect']['h']:.0f}px "
                             "(esperado a mesma distância da base, ou na metade superior do cartão)")
                    break
    _exigir(v, f"'Entrar no curso' a {largura}px")


@pytest.mark.parametrize("largura", LARGURAS)
def test_c5_avaliacao_sem_estourar_o_cartao(sessao, largura):
    v = []
    for conta in ("carla", "marina", "rafael", "sofia"):
        m = sessao.cartoes(conta, largura)
        r = f"{conta} @{largura}px"
        if largura == 390 and m["docW"] > 390:
            v.append(f"{r}: rolagem horizontal da página (scrollWidth {m['docW']}px > 390px)")
        for c in m["cards"]:
            if not _peca(c, "comentario"):
                continue
            n = c["nome"][:26]
            com, nota, env = (_peca(c, k)[0]["rect"] for k in ("comentario", "nota", "enviar"))
            caixas = (("comentário", com), ("nota", nota), ("Enviar", env))
            for nome, x in caixas:
                if x["l"] < c["rect"]["l"] - 1 or x["r"] > c["rect"]["r"] + 1:
                    v.append(f"{r} '{n}': {nome} {_r(x)} estoura o cartão {_r(c['rect'])}")
                if x["h"] < 44 - 0.01:
                    v.append(f"{r} '{n}': {nome} com {x['h']:.0f}px de altura (esperado >= 44px)")
            for (na, a), (nb, b) in ((caixas[0], caixas[1]), (caixas[0], caixas[2]), (caixas[1], caixas[2])):
                dx = min(a["r"], b["r"]) - max(a["l"], b["l"])
                dy = min(a["b"], b["b"]) - max(a["t"], b["t"])
                if dx > 1 and dy > 1:
                    v.append(f"{r} '{n}': {na} e {nb} se sobrepõem ({dx:.0f}x{dy:.0f}px)")
            if largura == 390 and com["w"] < 200:
                v.append(f"{r} '{n}': comentário com {com['w']:.0f}px (esperado >= 200px: a linha deve quebrar, não espremer)")
    _exigir(v, f"avaliação a {largura}px")


@pytest.mark.parametrize("largura", LARGURAS)
def test_c6_cancelamento_aberto_continua_dentro_do_cartao(sessao, largura):
    v = []
    with sessao.pagina("marina", largura) as page:
        card = _card_de(page, sessao.seed["ativo"]["nome"])
        card.locator('[data-testid="curso-cancelar"]').click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        m = page.evaluate(_JS_CARTOES, {"sel": {**SELETORES, "motivo": '[data-testid="curso-cancelar-motivo"]',
                                                  "enviar_pedido": '[data-testid="curso-cancelar-enviar"]',
                                                  "voltar": "button.btn-outline-secondary"}})
        r = f"@{largura}px"
        abertos = [c for c in m["cards"] if _peca(c, "motivo")]
        if len(abertos) != 1:
            raise Falha(f"{r}: {len(abertos)} cartões com o campo de motivo (esperado 1: o do cartão clicado)")
        c = abertos[0]
        for chave, nome in (("motivo", "motivo"), ("enviar_pedido", "Enviar pedido")):
            x = _peca(c, chave)
            if len(x) != 1 or not x[0]["geo"]:
                v.append(f"{r}: {nome} ausente ou invisível dentro do cartão")
        voltar = [x for x in _peca(c, "voltar") if x["texto"] == "Voltar"]
        if len(voltar) != 1:
            v.append(f"{r}: botão 'Voltar' do cancelamento ausente dentro do cartão")
        if m["fora"].get("motivo") or m["fora"].get("enviar_pedido"):
            v.append(f"{r}: campo de motivo ou 'Enviar pedido' fora de qualquer cartão")
        for texto in c["estouros"]:
            v.append(f"{r}: {texto}")
        if largura == 390 and m["docW"] > 390:
            v.append(f"{r}: rolagem horizontal com o cancelamento aberto (scrollWidth {m['docW']}px)")
        outros = [x for x in m["cards"] if x is not c and _peca(x, "motivo")]
        if outros:
            v.append(f"{r}: o campo de motivo aparece em mais de um cartão")
        card.get_by_role("button", name="Voltar").click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        if card.locator('[data-testid="curso-cancelar-motivo"]').count():
            v.append(f"{r}: 'Voltar' não fechou o formulário de cancelamento")
        if card.locator('[data-testid="curso-cancelar"]').count() != 1:
            v.append(f"{r}: depois do 'Voltar', o botão 'Pedir cancelamento' não voltou ao cartão")
    _exigir(v, f"cancelamento aberto no cartão a {largura}px")


def test_c7_nenhuma_url_de_material_sem_matricula_ativa(sessao):
    s = sessao.seed
    sessao.exigir_seed()
    proibidas = [s["pendente"]["materiais"][0]["url"]] + [m["url"] for m in s["turma_curso"]["materiais"]]
    permitidas = [m["url"] for m in s["ativo"]["materiais"]]
    v = []
    with sessao.pagina("carla", 1280) as page:
        html = page.content()
        for url in proibidas:
            if url in html:
                v.append(f"URL de material de matrícula pendente/cancelada no HTML da tela: {url}")
        for url in permitidas:
            if url not in html:
                v.append(f"URL de material da matrícula ativa ausente da aba Meus cursos: {url}")
        todos = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        for url in proibidas:
            if url in todos:
                v.append(f"link para material sem matrícula ativa: {url}")
    _exigir(v, "URL de material sem matrícula ativa")


def test_c8_sem_matriculas_mostra_o_estado_vazio(sessao):
    v = []
    for largura in LARGURAS:
        with sessao.pagina("bruno", largura) as page:
            p = page.evaluate(_JS_PAINEIS)
            r = f"sem matrículas @{largura}px"
            if p["cards"]:
                v.append(f"{r}: {p['cards']} cartões (esperado 0)")
            texto = _norm(page.locator('[data-testid="secao-cursos"]').inner_text())
            if VAZIO_CURSOS not in texto:
                v.append(f"{r}: sem o texto {VAZIO_CURSOS!r}")
            # `.first`: hoje a seção do Financeiro está aninhada em secao-cursos (a `</section>` do código atual não fecha) e traz o
            # seu próprio "Ver cursos"; o aninhamento é coberto por T2 (o painel de Cursos não contém o do Financeiro).
            link = page.locator('[data-testid="secao-cursos"] a', has_text="Ver cursos")
            if link.count() < 1 or link.first.get_attribute("href") != "/catalogo":
                v.append(f"{r}: link 'Ver cursos' para /catalogo ausente")
    _exigir(v, "estado sem matrículas")


@pytest.mark.parametrize("largura", LARGURAS)
def test_c9_um_so_curso_nao_estica_o_cartao(sessao, largura):
    """Um aluno com 1 curso: o cartão tem a largura de UMA coluna da grade (a mesma dos cartões da Carla) e fica à esquerda."""
    sofia, carla = sessao.cartoes("sofia", largura), sessao.cartoes("carla", largura)
    if sofia["n"] != 1:
        raise Falha(f"{sofia['n']} cartões (esperado 1)")
    s, c0 = sofia["cards"][0]["rect"], carla["cards"][0]["rect"]
    v = []
    if abs(s["w"] - c0["w"]) > 2:
        v.append(f"cartão com {s['w']:.0f}px; uma coluna da grade tem {c0['w']:.0f}px (devem ser iguais: o cartão não estica)")
    if abs(s["l"] - c0["l"]) > 2:
        v.append(f"cartão em x={s['l']:.0f}; a primeira coluna da grade começa em x={c0['l']:.0f}")
    _exigir(v, f"um só curso a {largura}px")


def test_c10_erro_de_carga_mostra_o_alerta_sem_cartoes(sessao):
    v = []
    with sessao.pagina_com_falha_de_matriculas(1280) as page:
        texto = _norm(page.locator('[data-testid="secao-cursos"]').inner_text())
        if MSG_ERRO_MATRICULAS not in texto:
            v.append(f"sem o alerta {MSG_ERRO_MATRICULAS!r} ({texto[:80]!r})")
        if not page.locator('[data-testid="secao-cursos"] .alert-danger').count():
            v.append("o alerta não é um .alert-danger dentro de secao-cursos")
        if page.locator(SEL_CARD).count():
            v.append("há cartões de curso na tela")
    _exigir(v, "erro de carga das matrículas")


def test_t13_erro_de_matriculas_nao_impede_o_financeiro(sessao):
    with sessao.pagina_com_falha_de_matriculas(1280) as page:
        _ir_para_aba(page, "financeiro")
        p = page.evaluate(_JS_PAINEIS)
        v = _violacoes_estado_abas(page, "financeiro", "com as matrículas em erro")
        if p["financeiro"]["n"] != 1 or not p["financeiro"]["visivel"]:
            v.append("a aba Financeiro não abre quando as matrículas falham")
    _exigir(v, "Financeiro com as matrículas em erro")


# ------------------------------------------------------------------------------------------------- F fluxos
def test_f1_avaliar_grava_no_cartao_certo(sessao):
    v = []
    s = sessao.seed
    with sessao.pagina("davi", 1280) as page:
        a, b = _card_de(page, s["ativo"]["nome"]), _card_de(page, s["turma_curso"]["nome"])
        a.locator('[data-testid="curso-avaliacao-nota"]').select_option(label="4 ★")
        a.locator('[data-testid="curso-avaliacao-comentario"]').fill("Muito bom, conteúdo claro.")
        a.locator('[data-testid="curso-avaliacao-enviar"]').click(timeout=TIMEOUT)
        a.locator('[data-testid="curso-avaliacao-ok"]').wait_for(state="visible", timeout=TIMEOUT)
        if "Avaliação enviada" not in a.locator('[data-testid="curso-avaliacao-ok"]').inner_text():
            v.append("mensagem de avaliação enviada ausente no cartão avaliado")
        if "4" not in _norm(a.locator('[data-testid="curso-avaliacao-atual"]').inner_text()):
            v.append("a nota atual (curso-avaliacao-atual) não mostra 4 no cartão avaliado")
        if b.locator('[data-testid="curso-avaliacao-ok"]').count() or b.locator('[data-testid="curso-avaliacao-atual"]').count():
            v.append("a avaliação apareceu no OUTRO cartão")
        if page.locator('[data-testid="curso-avaliacao-ok"]').count() != 1:
            v.append(f"{page.locator('[data-testid=curso-avaliacao-ok]').count()} mensagens de avaliação na tela (esperado 1, dentro do cartão)")
    _exigir(v, "avaliação no cartão certo")


def test_f2_marcar_aula_atualiza_o_cartao_certo(sessao):
    v = []
    s = sessao.seed
    with sessao.pagina("davi", 1280) as page:
        a, b = _card_de(page, s["ativo"]["nome"]), _card_de(page, s["turma_curso"]["nome"])
        b.locator('[data-testid="material-concluido"]').first.check(timeout=TIMEOUT)
        page.wait_for_timeout(800)
        if _norm(b.locator('[data-testid="curso-progresso"]').inner_text()) != "1 de 2 concluídos":
            v.append(f"progresso do cartão marcado: {b.locator('[data-testid=curso-progresso]').inner_text()!r} (esperado '1 de 2 concluídos')")
        if b.locator('[role="progressbar"]').get_attribute("aria-valuenow") != "50":
            v.append("a barra do cartão marcado não foi para 50%")
        if _norm(a.locator('[data-testid="curso-progresso"]').inner_text()) != "0 de 2 concluídos":
            v.append("o progresso do OUTRO cartão mudou")
    _exigir(v, "progresso no cartão certo")


def test_f3_cancelamento_completo_no_cartao_certo(sessao):
    v = []
    s = sessao.seed
    with sessao.pagina("davi", 1280) as page:
        antes = len(sessao.dialogos)
        a, b = _card_de(page, s["ativo"]["nome"]), _card_de(page, s["turma_curso"]["nome"])
        a.locator('[data-testid="curso-cancelar"]').click(timeout=TIMEOUT)
        a.locator('[data-testid="curso-cancelar-motivo"]').fill("Teste de cancelamento no cartão (R3C)")
        if b.locator('[data-testid="curso-cancelar-motivo"]').count():
            v.append("o campo de motivo abriu também no OUTRO cartão")
        a.locator('[data-testid="curso-cancelar-enviar"]').click(timeout=TIMEOUT)
        page.locator('[data-testid="confirmacao"]').wait_for(state="visible", timeout=TIMEOUT)
        page.locator('[data-testid="confirmacao-confirmar"]').click(timeout=TIMEOUT)
        a.locator('[data-testid="curso-cancelamento-status"]').wait_for(state="visible", timeout=TIMEOUT)
        if _norm(a.locator('[data-testid="curso-cancelamento-status"]').inner_text()) != "Cancelamento em análise":
            v.append("status 'Cancelamento em análise' ausente no cartão cancelado")
        if a.locator('[data-testid="curso-cancelar"]').count():
            v.append("o botão 'Pedir cancelamento' continua no cartão que já tem pedido aberto")
        if b.locator('[data-testid="curso-cancelamento-status"]').count() or b.locator('[data-testid="curso-cancelar"]').count() != 1:
            v.append("o OUTRO cartão mudou (status de cancelamento ou perda do botão)")
        if page.locator('[data-testid="curso-cancelamento-status"]').count() != 1:
            v.append("mais de um status de cancelamento na tela (esperado 1, dentro do cartão)")
        if len(sessao.dialogos) != antes:
            v.append(f"diálogo nativo aberto: {sessao.dialogos[antes:]}")
    _exigir(v, "cancelamento no cartão certo")


def test_f4_baixar_certificado_pelo_cartao(sessao):
    s = sessao.seed
    with sessao.pagina("rafael", 1280) as page:
        card = _card_de(page, s["turma_curso"]["nome"])
        try:
            with page.expect_download(timeout=TIMEOUT) as baixado:
                card.locator('[data-testid="curso-certificado"]').click(timeout=TIMEOUT)
        except sync_api.Error as erro:
            raise Falha(f"'Baixar certificado' no cartão não baixou o arquivo: {str(erro).splitlines()[0]}")
        nome = baixado.value.suggested_filename or ""
        if not nome.lower().endswith(".pdf"):
            raise Falha(f"arquivo baixado {nome!r} (esperado um .pdf)")


def test_f5_entrar_no_curso_leva_a_sala(sessao):
    s = sessao.seed
    with sessao.pagina("sofia", 1280) as page:
        card = _card_de(page, s["ativo"]["nome"])
        card.locator('[data-testid="curso-entrar"]').click(timeout=TIMEOUT)
        try:
            page.wait_for_url(re.compile(r".*/student/curso/\d+$"), timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"'Entrar no curso' não levou a /student/curso/<id> (URL {page.url})")


# ------------------------------------------------------------------------------------------------- A D115
def _telas_das_abas(sessao, largura, reduzido=True):
    """Gera (rótulo, page) para a aba Meus cursos (Carla) e a aba Financeiro (Marina) na largura dada."""
    @contextlib.contextmanager
    def cursos():
        with sessao.pagina("carla", largura, reduzido) as page:
            yield page

    @contextlib.contextmanager
    def financeiro():
        with sessao.pagina("marina", largura, reduzido) as page:
            _ir_para_aba(page, "financeiro")
            yield page

    return (("Meus cursos", cursos), ("Financeiro", financeiro))


@pytest.mark.parametrize("largura", (1280, 390))
def test_a1_contraste_aa(sessao, largura):
    v = []
    for nome, abrir in _telas_das_abas(sessao, largura):
        with abrir() as page:
            c = varrer_contraste(page)
            if c["verificados"] < 10:
                v.append(f"{nome} @{largura}px: só {c['verificados']} textos verificados")
            v.extend(f"{nome} @{largura}px: {descrever([f], 1)}" for f in c["falhas"])
    _exigir(v, "contraste AA")


@pytest.mark.parametrize("largura", (1280, 390))
def test_a2_piso_de_14px(sessao, largura):
    v = []
    for nome, abrir in _telas_das_abas(sessao, largura):
        with abrir() as page:
            v.extend(f"{nome} @{largura}px: {descrever([i], 1)}" for i in fontes_abaixo_de(page, 14))
    _exigir(v, "texto abaixo de 14 px")


@pytest.mark.parametrize("largura", (1280, 390))
def test_a3_um_h1_campos_rotulados_alvos_44px(sessao, largura):
    v = []
    for nome, abrir in _telas_das_abas(sessao, largura):
        with abrir() as page:
            d = page.evaluate(_JS_MEDIR)
            r = f"{nome} @{largura}px"
            if len(d["h1"]) != 1:
                v.append(f"{r}: {len(d['h1'])} h1 visíveis {d['h1']}")
            v.extend(f"{r}: campo sem rótulo {c}" for c in d["campos"])
            v.extend(f"{r}: alvo pequeno {a}" for a in d["alvos"])
    _exigir(v, "h1, rótulos e alvos de toque")


def test_a4_sem_rolagem_horizontal_a_390px(sessao):
    v = []
    for nome, abrir in _telas_das_abas(sessao, 390):
        with abrir() as page:
            d = page.evaluate(_JS_MEDIR)
            fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
            if d["scrollWidth"] > 390:
                v.append(f"{nome}: scrollWidth {d['scrollWidth']}px (> 390). Passam da borda: {fora}")
            elif d["clipaRaiz"] and d["fora"]:
                v.append(f"{nome}: estouro escondido por overflow-x hidden. Passam da borda: {fora}")
    _exigir(v, "rolagem horizontal a 390 px")


def test_a8_sem_rolagem_horizontal_a_320px(sessao):
    """Menor celular que o CT-UI-11 do qa_istqb exercita (320 px). Uma grade com `minmax(320px, 1fr)` puro estoura aqui, porque a
    coluna mínima (320 px) é maior que a área útil do cartão (320 px menos o recuo da página): use `minmax(min(100%, 320px), 1fr)`."""
    v = []
    for nome, abrir in _telas_das_abas(sessao, 320):
        with abrir() as page:
            d = page.evaluate(_JS_MEDIR)
            fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
            if d["scrollWidth"] > 320:
                v.append(f"{nome}: scrollWidth {d['scrollWidth']}px (> 320). Passam da borda: {fora}")
            elif d["clipaRaiz"] and d["fora"]:
                v.append(f"{nome}: estouro escondido por overflow-x hidden. Passam da borda: {fora}")
    _exigir(v, "rolagem horizontal a 320 px")


def test_a5_foco_visivel_nas_abas_e_em_entrar(sessao):
    v = []
    with sessao.pagina("carla", 1280) as page:
        _abas_existem(page)
        page.keyboard.press("Tab")
        for sel, nome in ((f'{SEL_BARRA} [data-aba="financeiro"]', "aba Financeiro"),
                          ('[data-testid="atalho-perfil"]', "Meu perfil"),
                          ('[data-testid="curso-entrar"]', "Entrar no curso")):
            page.locator(sel).first.focus()
            f = page.evaluate(_JS_FOCO, sel)
            if not f or not f["match"]:
                v.append(f"{nome}: o foco por teclado não casa com :focus-visible")
            elif not ((f["estilo"] != "none" and f["largura"] >= 2) or f["sombra"] != "none"):
                v.append(f"{nome}: foco sem contorno visível (outline {f['estilo']} {f['largura']}px, sombra {f['sombra']})")
    _exigir(v, "foco visível")


def test_a6_sem_animacao_em_repouso(sessao):
    with sessao.pagina("carla", 1280, reduzido=False) as page:
        page.wait_for_timeout(1500)
        rodando = page.evaluate(_JS_ANIMACOES)
    _exigir(rodando, "animações em execução 1,5 s depois de abrir a tela (sem animação em repouso)")


def test_a7_sem_emoji_novo(sessao):
    v = []
    for largura in (1280, 390):
        for nome, abrir in _telas_das_abas(sessao, largura):
            with abrir() as page:
                emoji = page.evaluate("() => (document.body.innerText.match(/\\p{Emoji_Presentation}/gu) || [])")
                if emoji:
                    v.append(f"{nome} @{largura}px: emoji no texto da página {emoji}")
    _exigir(v, "emoji no texto")


# ------------------------------------------------------------------------------------------------- K1 (último)
def test_k1_sem_erro_de_console_nem_dialogo_nativo(sessao):
    sessao.exigir_seed()
    v = list(sessao.erros)
    v += [f"diálogo nativo (confirm/alert) aberto: {d}" for d in sessao.dialogos]
    _exigir(v, "erro de console (4xx/5xx de /api, exceção de página) ou diálogo nativo em todo o arquivo")
