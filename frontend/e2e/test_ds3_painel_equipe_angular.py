"""E2E da DS3 (D115, docs/tdd/PLANO_DESIGN.md) — painel da equipe (/admin): contraste AA completo, piso de 14 px, nenhum
texto em #0096c7, abas com estado claro, um h2 por aba e por subpainel, toda tabela com nome acessível e cabeçalho com
scope, status nunca só por cor, faixa de números no Financeiro, ações destrutivas pela janela da DS1 e as guardas da DS1
(h1, rótulo, 44 px, 390 px).

Regra da D115: só design. Nenhuma rota, API, permissão, texto de erro, fluxo, data-testid ou texto que os e2e antigos
leem muda; as abas que cada perfil vê continuam as mesmas (P1). Os e2e antigos do painel são a rede. Tudo é medido no
estilo COMPUTADO do Chromium com os helpers da DS0 (`apoio_contraste.py`), o verificador da DS1 (`_JS_MEDIR`) e os
medidores da DS2 (`_JS_UTIL`, `_JS_BADGES`, `_JS_COR`), importados.

Seed (harness isolado D58; dados em todas as tabelas, como os seeds de DS1/U1/F3/L1/U5/E7/E8/F7/C2):
  cursos:   principal (1 material do cadastro, 2 turmas, matrículas ativas/pedido de cancelamento/desativado, 3 conteúdos
            da sala: link, vídeo e arquivo), segundo (pendente e reembolsada, 1 turma), terceiro (sem aluno, 1 turma;
            Excluir habilitado) e arquivado (sem aluno, 1 turma; badge "Arquivado")
  alunos:   Marina (ativa, turma, 2 mensagens de chat), Caio (ativo), Otávio (pendente, sem senha), Rita (ativa, pedido
            de cancelamento aberto), Renato (reembolsado), Davi (ativo, conta desativada)
  IA:       uso com custo (ai_usage), interações respondida e não compreendida com tópico, um encaminhamento ao WhatsApp
  equipe:   as três contas do harness, uma pessoa convidada (Suporte) e uma conta convidada já desativada
  auditoria: os eventos gerados pelas chamadas de seed

Telas (cada uma a 1366 e a 390 px, mouse parado no canto, movimento reduzido):
  Gestão:     Financeiro, Alunos, Cursos (curso do seed escolhido em "Gerenciar turmas"), Cadastro de cursos,
              Observabilidade de IA, Auditoria, Equipe; e os subpainéis
                Alunos > detalhe do aluno                (Marina)
                Alunos > detalhe do aluno desativado     (Davi; badge "Desativado")
                Cursos > alunos do curso                 (curso principal, com o formulário de matrícula manual aberto)
                Cadastro de cursos > criar a partir de arquivo  (JSON incompleto escolhido; avisos na tela)
                Cadastro de cursos > conteúdos do curso
                Cadastro de cursos > editar curso
  Financeiro: Financeiro, Alunos, Cursos, Observabilidade de IA
  Suporte:    Alunos, Cursos, Observabilidade de IA

test_ds3_apoio_verificador (sem servidor; valida os medidores novos numa página sintética, passa no red):
  V1 abas: role=tab/aria-selected e aria-current corretos passam; estado ausente, duplicado e indicador desalinhado
     são apontados
  V2 títulos: h2 com o nome da aba e do subpainel passa; h5 como primeiro título e texto errado são apontados
  V3 tabelas: caption visível, aria-labelledby -> título e aria-label passam; sem nome, caption escondido, labelledby
     para não título e th sem scope são apontados
  V4 faixa de números: faixa correta passa; quatro cartões soltos têm cada defeito apontado

test_ds3_painel_equipe — cenários (cada um lista TODAS as violações de todas as telas, não para na primeira):
  P0 pré-condição do seed: cada tabela visível das abas da Gestão tem linha de dados; os subpainéis abriram; os badges
     do seed estão na tela (Aprovado/Pendente/Reembolsado, Arquivado, Ativa/Desativada, Desativado, saúde) [passa no red]
  P1 permissões inalteradas: Gestão vê as 7 abas, Financeiro 4, Suporte 3, nesta ordem, nas duas larguras [passa no red]
  A1 contraste AA completo (scanner da DS0 sem filtro) em todas as telas e larguras: zero falhas; canvas fica de fora
     (não tem nó de texto), os textos ao redor contam
  A2 zero itens ignorados por "texto sobre imagem ou gradiente"; os demais ignorados só são informados
  F1 nenhum texto visível abaixo de 14 px (cabeçalho de tabela, badge, legenda, metadado, paginação, rótulo de KPI,
     texto de ajuda de formulário)
  T1 nenhum texto (qualquer tamanho) em #0096c7 = rgb(0, 150, 199); aria-hidden e ::before/::after ficam de fora
  B1 abas com estado claro: a aba ativa expõe o estado (aria-selected="true" em role="tab" dentro de role="tablist",
     ou aria-current="page"), e só ela; `.nav-tabs .nav-link` e [data-testid=abas-indicador] mantidos, indicador
     alinhado à aba ativa (posição e largura, 2 px)
  H1 título de cada aba: o primeiro título visível depois da lista de abas é um h2 que contém o nome da aba
  H2 título de cada subpainel: o primeiro título do subpainel é um h2 com o nome do subpainel (nome do aluno, nome do
     curso; "Novo curso"/"Editar curso" no formulário de cursos, inclusive na aba Cadastro de cursos e no estado de
     arquivo escolhido)
  M1 toda tabela visível do painel tem nome acessível: caption visível com texto, aria-labelledby apontando para um
     título (h1-h6/role=heading) com texto, ou aria-label não vazio
  M2 todo th do thead tem scope="col"
  S1 todo .badge do painel (exceto o marcador "você" da Equipe, que não é status) tem texto + sinal não cromático
     (filho aria-hidden visível, ::before/::after visível ou prefixo não alfanumérico) e passa AA
  N1 faixa de números do Financeiro (Gestão e Financeiro): >= 4 [data-testid=kpi-valor] num contêiner com borda única
     (o contêiner comum dos valores ou um dos 2 ancestrais com borda nos quatro lados), sem .card nem sombra por dentro,
     divisória entre itens vizinhos, nenhum item com borda nos quatro lados
  N2 valores na cor rgb(23, 33, 43), `tabular-nums` e ligados ao rótulo ("Receita aprovada", "Pendente", "Reembolsado",
     "Projeção próximo mês") por dl/dt/dd, aria-labelledby ou aria-label
  N3 a 390 e a 1366 px: valores sem estouro, dentro do contêiner; itens sem sobreposição; contêiner dentro da tela
  D1 ações destrutivas (Gestão, 1366 px), uma por tabela/subpainel que tem ação destrutiva: abrir e voltar sem nenhuma
     requisição que não seja GET (o painel se atualiza sozinho a cada 30 s, X5) e a linha continua lá.
       com a janela da DS1 (role=alertdialog; confirmar com fundo #b42318 e texto branco): Aprovar e reembolsar
       (Solicitações de cancelamento), Reembolsar (Transações), Desativar conta (detalhe do aluno), Excluir turma
       (Turmas por curso), Desativar (Equipe)
       Excluir curso (Cursos cadastrados) e Excluir conteúdo (Conteúdos): aceitam a janela OU a confirmação na linha que
       existe hoje ([data-testid=curso-delete-confirm] / [data-testid=conteudo-excluir-confirmar]), sempre com
       "Cancelar"/"Voltar" sem requisição
     nenhum diálogo nativo do navegador
  G1/G2/G3/G4 guardas da DS1 nessas telas: um h1 / rótulo em todo campo / alvos >= 44 px / sem rolagem a 390 px
  K1 sem exceções de página nem erros 4xx/5xx de /api no console

Escolhas do agente-testes (modo autônomo D40), registradas no relatório:
  - Excluir curso e excluir conteúdo usam hoje uma confirmação de dois passos na própria linha (não o `confirm()`
    nativo, por isso a DS1 não os trocou). Trocar por janela mudaria o fluxo que L2/F1/C/jornadas usam; D1 aceita as
    duas formas e só exige que nada aconteça sem confirmar.
  - O badge "você" da Equipe marca a própria conta, não é status: fica fora de S1 (o contraste dele conta em A1).
  - O status de matrícula no detalhe do aluno e em alunos do curso é texto de célula (não `.badge`): já não depende de
    cor e fica fora de S1.
  - A faixa de números vale onde há [data-testid=kpi-valor] (Financeiro). Os números das abas Alunos e Observabilidade
    de IA (`.gt-kpi` sem esse testid) não entram em N1-N3; o contraste e o piso de 14 px deles contam em A1/F1.
  - Subpainel tem h2 próprio (pedido do orquestrador), além do h2 da aba.
  - aria-labelledby de tabela precisa apontar para um título (h1-h6, role=heading ou caption); aria-label vale se não
    estiver vazio.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds3_painel_equipe_angular.py -s
"""

import io
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_confirmacao import SEL_CONFIRMAR, SEL_JANELA, SEL_VOLTAR  # noqa: E402
from apoio_contraste import descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)
from test_ds1_componentes_angular import _JS_MEDIR  # noqa: E402  (verificador da DS1: h1, rótulo, alvo, 390 px)
from test_ds2_area_aluno_angular import _JS_BADGES, _JS_COR, _JS_UTIL  # noqa: E402  (medidores da DS2)

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
LARGURAS = (1366, 390)
SENHA = "senha-aluno-ds3-2026"
TEXTO = "rgb(23, 33, 43)"       # #17212b
TEAL = "rgb(0, 150, 199)"       # #0096c7
VERMELHO = "rgb(180, 35, 24)"   # #b42318
BRANCO = "rgb(255, 255, 255)"
ALVO_MIN = 44.0
RAIZ = "app-admin-dashboard"
SEL_ABA = "ul.nav-tabs button.nav-link"
MARCADOR_PROPRIO = "você"
ROTULOS_KPI = ("Receita aprovada", "Pendente", "Reembolsado", "Projeção próximo mês")

ABAS = {
    "Gestão": ("Financeiro", "Alunos", "Cursos", "Cadastro de cursos", "Observabilidade de IA", "Auditoria", "Equipe"),
    "Financeiro": ("Financeiro", "Alunos", "Cursos", "Observabilidade de IA"),
    "Suporte": ("Alunos", "Cursos", "Observabilidade de IA"),
}
CONTAS = {
    "Gestão": (GESTAO_EMAIL, GESTAO_SENHA),
    "Financeiro": (FINANCEIRO_EMAIL, FINANCEIRO_SENHA),
    "Suporte": (SUPORTE_EMAIL, SUPORTE_SENHA),
}
PERFIS = tuple(ABAS)

SUB_DETALHE = "Alunos > detalhe do aluno"
SUB_DESATIVADO = "Alunos > detalhe do aluno desativado"
SUB_CURSO_ALUNOS = "Cursos > alunos do curso"
SUB_ARQUIVO = "Cadastro de cursos > criar a partir de arquivo"
SUB_CONTEUDOS = "Cadastro de cursos > conteúdos do curso"
SUB_EDITAR = "Cadastro de cursos > editar curso"
SUBPAINEIS = (SUB_DETALHE, SUB_DESATIVADO, SUB_CURSO_ALUNOS, SUB_ARQUIVO, SUB_CONTEUDOS, SUB_EDITAR)
FORM_CURSO = ['[data-testid="curso-anexo-input"]', '[data-testid="curso-form"]']
RASCUNHO_INCOMPLETO = {"name": "Rascunho DS3 a partir de arquivo", "description": "Só nome e descrição"}


class Falha(Exception):
    pass


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


# ------------------------------------------------------------------------------------------------- medidores (JS)
_JS_TITULO_UTIL = r"""
function ehTitulo(h) { return /^H[1-6]$/.test(h.tagName) || h.getAttribute('role') === 'heading'; }
function nivel(h) {
  const al = h.getAttribute('aria-level');
  if (h.getAttribute('role') === 'heading') return al ? parseInt(al, 10) : 2;
  return /^H[1-6]$/.test(h.tagName) ? parseInt(h.tagName[1], 10) : 0;
}
function descTitulo(h) {
  const role = h.getAttribute('role') ? ` role=${h.getAttribute('role')}` : '';
  return `<${h.tagName.toLowerCase()}${role}> "${norm(h.innerText).slice(0, 60)}"`;
}
function titulosVisiveis() {
  return Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')).filter(visivel);
}
function antes(a, b) { return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING); }
"""

# B1: estado das abas. args: {raiz, ativa}. Devolve lista de violações.
_JS_ABAS = _JS_UTIL + r"""
(args) => {
  const v = [];
  const raiz = document.querySelector(args.raiz);
  if (!raiz) return [`${args.raiz} ausente`];
  const abas = Array.from(raiz.querySelectorAll('.nav-tabs .nav-link'));
  if (!abas.length) return ['nenhuma aba .nav-tabs .nav-link'];
  const nome = a => norm(a.innerText || a.textContent);
  const ind = raiz.querySelector('[data-testid="abas-indicador"]');
  if (!ind) v.push('indicador [data-testid=abas-indicador] ausente');
  const ativa = abas.find(a => nome(a) === args.ativa);
  if (!ativa) { v.push(`aba "${args.ativa}" não encontrada entre ${JSON.stringify(abas.map(nome))}`); return v; }
  const comRole = abas.filter(a => a.getAttribute('role') === 'tab');
  if (comRole.length) {
    if (comRole.length !== abas.length) v.push(`${comRole.length} de ${abas.length} abas com role="tab" (todas ou nenhuma)`);
    const listas = comRole.map(a => a.closest('[role="tablist"]'));
    if (listas.some(l => !l)) v.push('aba com role="tab" fora de um role="tablist"');
    else if (new Set(listas).size !== 1) v.push('abas em role="tablist" diferentes');
  }
  const atual = a => { const c = a.getAttribute('aria-current'); return c !== null && c !== 'false'; };
  const selecionada = a => a.getAttribute('role') === 'tab' && a.getAttribute('aria-selected') === 'true'
                           && !!a.closest('[role="tablist"]');
  if (!(selecionada(ativa) || ativa.getAttribute('aria-current') === 'page')) {
    v.push(`aba ativa "${args.ativa}" não expõe o estado (role=${JSON.stringify(ativa.getAttribute('role'))}, `
           + `aria-selected=${JSON.stringify(ativa.getAttribute('aria-selected'))}, `
           + `aria-current=${JSON.stringify(ativa.getAttribute('aria-current'))}; esperado aria-selected="true" em `
           + `role="tab" dentro de role="tablist", ou aria-current="page")`);
  }
  for (const a of abas) {
    if (a === ativa) continue;
    if (a.getAttribute('aria-selected') === 'true') v.push(`aba inativa "${nome(a)}" com aria-selected="true"`);
    if (atual(a)) v.push(`aba inativa "${nome(a)}" com aria-current="${a.getAttribute('aria-current')}"`);
  }
  if (ind) {
    const ra = ativa.getBoundingClientRect(), ri = ind.getBoundingClientRect();
    if (Math.abs(ra.left - ri.left) > 2 || Math.abs(ra.width - ri.width) > 2) {
      v.push(`indicador em x=${Math.round(ri.left)} largura ${Math.round(ri.width)} e aba ativa em x=${Math.round(ra.left)} `
             + `largura ${Math.round(ra.width)} (tolerância 2 px)`);
    }
  }
  return v;
}
"""

_JS_LISTA_ABAS = r"""
(raiz) => Array.from(document.querySelectorAll(`${raiz} .nav-tabs .nav-link`))
  .map(a => (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim())
"""

# H1/H2: títulos. args: {raiz, aba, subs: [{nome, container?, antes?: [sel...], contem: [...]}]}.
# Devolve {aba: [violações], subs: [violações]}.
_JS_TITULOS = _JS_UTIL + _JS_TITULO_UTIL + r"""
(args) => {
  const out = { aba: [], subs: [] };
  const raiz = document.querySelector(args.raiz);
  if (!raiz) { out.aba.push(`${args.raiz} ausente`); return out; }
  const titulos = titulosVisiveis();
  function checar(lista, h, contem, onde) {
    if (!h) { lista.push(`${onde}: nenhum título visível`); return; }
    if (nivel(h) !== 2) lista.push(`${onde}: o primeiro título é ${descTitulo(h)} (esperado h2)`);
    const t = norm(h.innerText).toLowerCase();
    for (const c of contem) {
      if (!t.includes(norm(c).toLowerCase())) lista.push(`${onde}: o título ${descTitulo(h)} não contém "${c}"`);
    }
  }
  const abas = raiz.querySelector('.nav-tabs');
  if (!abas) out.aba.push('lista de abas .nav-tabs ausente');
  else {
    const depois = titulos.filter(h => raiz.contains(h) && !abas.contains(h) && antes(abas, h));
    checar(out.aba, depois[0], [args.aba], `aba ${args.aba} (primeiro título depois das abas)`);
  }
  for (const s of args.subs) {
    if (s.container) {
      const c = document.querySelector(s.container);
      if (!c || !visivel(c)) { out.subs.push(`${s.nome}: ${s.container} ausente ou invisível`); continue; }
      checar(out.subs, titulos.find(h => c.contains(h)), s.contem, `${s.nome} (primeiro título de ${s.container})`);
    } else {
      const sel = s.antes.find(x => document.querySelector(x));
      if (!sel) { out.subs.push(`${s.nome}: ${s.antes.join(' / ')} ausente`); continue; }
      const alvo = document.querySelector(sel);
      const anteriores = titulos.filter(h => antes(h, alvo) && !h.contains(alvo));
      checar(out.subs, anteriores[anteriores.length - 1], s.contem, `${s.nome} (título logo antes de ${sel})`);
    }
  }
  return out;
}
"""

# M1/M2: tabelas. args: {raiz}. Devolve [{ident, nome, motivo, semScope, nTh}].
_JS_TABELAS = _JS_UTIL + _JS_TITULO_UTIL + r"""
(args) => {
  const out = [];
  const raiz = document.querySelector(args.raiz) || document.body;
  const titulos = titulosVisiveis();
  for (const t of raiz.querySelectorAll('table')) {
    if (!visivel(t)) continue;
    const ths = Array.from(t.querySelectorAll('thead th'));
    const anteriores = titulos.filter(h => antes(h, t) && !h.contains(t));
    const perto = anteriores.length ? norm(anteriores[anteriores.length - 1].innerText).slice(0, 50) : '(nenhum título antes)';
    const cols = ths.map(th => norm(th.textContent)).filter(Boolean).slice(0, 3).join('/');
    const ident = `tabela após "${perto}"` + (cols ? ` [${cols}]` : ' [sem thead]');
    let nome = null;
    const motivos = [];
    const cap = t.querySelector(':scope > caption');
    if (cap) {
      if (visivel(cap) && norm(cap.textContent)) nome = 'caption';
      else motivos.push(visivel(cap) ? 'caption vazio' : 'caption invisível (display/visibility/1 px)');
    }
    const lb = (t.getAttribute('aria-labelledby') || '').trim();
    if (!nome && lb) {
      const els = lb.split(/\s+/).map(id => document.getElementById(id));
      if (els.some(e => !e)) motivos.push(`aria-labelledby="${lb}" com id inexistente`);
      else if (!norm(els.map(e => e.textContent).join(' '))) motivos.push(`aria-labelledby="${lb}" aponta para texto vazio`);
      else if (!els.some(e => ehTitulo(e) || e.tagName === 'CAPTION')) motivos.push(`aria-labelledby="${lb}" não aponta para um título (${els.map(e => e.tagName.toLowerCase()).join(', ')})`);
      else nome = 'aria-labelledby';
    }
    if (!nome && norm(t.getAttribute('aria-label'))) nome = 'aria-label';
    if (!nome && !motivos.length) motivos.push('sem caption, aria-labelledby nem aria-label');
    const semScope = ths.filter(th => (th.getAttribute('scope') || '').toLowerCase() !== 'col')
                        .map(th => norm(th.textContent) || '(vazio)');
    out.push({ ident, nome, motivo: motivos.join('; '), semScope, nTh: ths.length });
  }
  return out;
}
"""

# N1/N2/N3: faixa de números a partir dos [data-testid=kpi-valor] visíveis. args: {rotulos, texto, minimo}.
_JS_FAIXA = _JS_UTIL + r"""
(args) => {
  const n1 = [], n2 = [], n3 = [];
  const valores = Array.from(document.querySelectorAll('[data-testid="kpi-valor"]')).filter(visivel);
  if (valores.length < args.minimo) n1.push(`${valores.length} [data-testid=kpi-valor] visíveis (esperado >= ${args.minimo})`);
  if (!valores.length) return { n1, n2, n3 };
  let lca = valores.length > 1 ? valores[0].parentElement : valores[0].parentElement;
  while (lca && !valores.every(el => lca.contains(el))) lca = lca.parentElement;
  let faixa = null;
  for (let a = lca, i = 0; a && i < 3 && a !== document.body; a = a.parentElement, i++) {
    if (LADOS.every(l => borda(a, l))) { faixa = a; break; }
  }
  if (!faixa) n1.push(`sem borda única: nem o contêiner comum dos KPIs (${desc(lca)}) nem os 2 ancestrais têm borda nos quatro lados`);
  const c = faixa || lca;
  const cartoes = Array.from(c.querySelectorAll('.card'));
  if (cartoes.length) n1.push(`${cartoes.length} .card dentro da faixa (cartão por KPI)`);
  const sombras = Array.from(c.querySelectorAll('*')).filter(e => getComputedStyle(e).boxShadow !== 'none');
  if (sombras.length) n1.push(`sombra dentro da faixa: ${sombras.slice(0, 4).map(e => `${desc(e)} (${getComputedStyle(e).boxShadow})`).join('; ')}`);

  let itens = valores.map(el => { let a = el; while (a.parentElement && a.parentElement !== lca) a = a.parentElement; return a; });
  if (valores.length > 1 && new Set(itens).size !== valores.length) { n1.push('os valores não estão em itens separados'); itens = []; }
  const grupo = it => {
    const g = [it];
    if (it.tagName === 'DD') { let p = it.previousElementSibling; while (p && p.tagName !== 'DT') p = p.previousElementSibling; if (p) g.push(p); }
    return g;
  };
  if (itens.length > 1) {
    for (const it of itens) for (const el of grupo(it)) {
      if (LADOS.every(l => borda(el, l))) n1.push(`item ${desc(el)} com borda nos quatro lados (cartão por KPI)`);
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
    for (let i = 0; i < itens.length; i++) for (let j = i + 1; j < itens.length; j++) {
      const a = itens[i].getBoundingClientRect(), b = itens[j].getBoundingClientRect();
      const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ix > 1 && iy > 1) n3.push(`itens ${desc(itens[i])} e ${desc(itens[j])} se sobrepõem`);
    }
  }
  const rc = c.getBoundingClientRect();
  if (rc.right > window.innerWidth + 0.5 || rc.left < -0.5) n3.push(`faixa de ${Math.round(rc.left)} a ${Math.round(rc.right)}px (tela ${window.innerWidth}px)`);
  valores.forEach((el, i) => {
    const rotulo = args.rotulos[i] || '?';
    const id = `kpi-valor nº ${i + 1} (${rotulo})`;
    const cs = getComputedStyle(el);
    if (cs.color !== args.texto) n2.push(`${id} com cor ${cs.color} (esperado ${args.texto})`);
    if (!(cs.fontVariantNumeric || '').includes('tabular-nums')) n2.push(`${id} sem tabular-nums (font-variant-numeric: ${cs.fontVariantNumeric})`);
    let ligado = false, como = '';
    const dd = el.closest('dd');
    if (dd && c.contains(dd) && dd.closest('dl')) {
      let p = dd.previousElementSibling; while (p && p.tagName !== 'DT') p = p.previousElementSibling;
      if (!p && dd.parentElement && dd.parentElement.tagName === 'DIV') { const dt = dd.parentElement.querySelector(':scope > dt'); if (dt) p = dt; }
      if (p && norm(p.textContent) === rotulo && visivel(p)) { ligado = true; como = 'dl/dt/dd'; }
      else como = `dt ${p ? JSON.stringify(norm(p.textContent)) : 'ausente'}`;
    }
    for (let a = el; !ligado && a && a !== c.parentElement; a = a.parentElement) {
      const ids = (a.getAttribute('aria-labelledby') || '').trim();
      if (ids) {
        const t = norm(ids.split(/\s+/).map(x => (document.getElementById(x) || {}).textContent || '').join(' '));
        if (t.includes(rotulo)) { ligado = true; como = 'aria-labelledby'; }
      }
      if (!ligado && norm(a.getAttribute('aria-label')).includes(rotulo)) { ligado = true; como = 'aria-label'; }
    }
    if (!ligado) n2.push(`${id} sem rótulo "${rotulo}" ligado (dl/dt/dd, aria-labelledby ou aria-label; ${como || 'nenhum'})`);
    if (el.scrollWidth > el.clientWidth + 1) n3.push(`${id} estoura a caixa (scrollWidth ${el.scrollWidth} > ${el.clientWidth})`);
    const r = el.getBoundingClientRect();
    if (r.left < rc.left - 0.5 || r.right > rc.right + 0.5) n3.push(`${id} de ${Math.round(r.left)} a ${Math.round(r.right)}px, fora da faixa (${Math.round(rc.left)} a ${Math.round(rc.right)}px)`);
  });
  return { n1, n2, n3 };
}
"""

# P0: textos dos badges visíveis do painel.
_JS_TEXTOS_BADGES = r"""
(sel) => Array.from(document.querySelectorAll(sel))
  .filter(b => b.getBoundingClientRect().width > 1 && getComputedStyle(b).visibility === 'visible')
  .map(b => (b.innerText || '').replace(/\s+/g, ' ').trim())
"""


# ------------------------------------------------------------------------------------------------- seed
def _api(api, metodo, caminho, corpo=None, token=None, formulario=None, multipart=None):
    cab = {}
    dados = None
    if multipart is not None:
        campos, arquivo = multipart
        fronteira = "----ds3" + uuid.uuid4().hex
        partes = []
        for nome, valor in campos.items():
            partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
        nome_arq, tipo, conteudo = arquivo
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="file"; filename="{nome_arq}"\r\n'
                      f"Content-Type: {tipo}\r\n\r\n".encode() + conteudo + b"\r\n")
        partes.append(f"--{fronteira}--\r\n".encode())
        dados = b"".join(partes)
        cab["Content-Type"] = f"multipart/form-data; boundary={fronteira}"
    elif formulario is not None:
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
        return {"id": cid, "nome": nome}

    principal = curso(f"ds3-{suf}", f"Excel Profissional para Gestão Financeira {suf}", 480.0,
                      [{"title": "Apostila de fórmulas", "url": f"https://materiais.test/ds3-{suf}/apostila.pdf",
                        "type": "pdf"}])
    segundo = curso(f"ds3b-{suf}", f"Power BI Essencial {suf}", 290.0, [])
    terceiro = curso(f"ds3c-{suf}", f"Python para Análise de Dados {suf}", 350.0, [])
    arquivado = curso(f"ds3d-{suf}", f"Access Básico {suf}", 120.0, [])
    st, _ = _api(api, "POST", f"/api/admin/course/{arquivado['id']}/archive", {}, token)
    if st != 200:
        raise RuntimeError(f"seed: arquivar curso HTTP {st}")

    def turma(nome, curso_id, **extra):
        st, corpo_t = _api(api, "POST", "/api/admin/classes", {"course_id": curso_id, "name": nome, **extra}, token)
        if st != 200:
            raise RuntimeError(f"seed: turma {nome} HTTP {st}")
        return {"id": corpo_t["class"]["id"], "nome": nome}

    hoje = _agora().date()
    noturna = turma(f"Turma Noturna {suf}", principal["id"], starts_on=str(hoje + timedelta(days=10)),
                    ends_on=str(hoje + timedelta(days=40)), schedule="Seg e Qua, 19h às 22h", capacity=30)
    sabado = turma(f"Turma Sábado {suf}", principal["id"], capacity=20)
    turma(f"Turma Intensiva de Férias {suf}", segundo["id"], starts_on=str(hoje + timedelta(days=5)),
          schedule="Seg a Sex, 8h às 12h", capacity=25)
    turma(f"Turma Única {suf}", terceiro["id"], capacity=15)
    turma(f"Turma Antiga {suf}", arquivado["id"], capacity=10)

    # Conteúdos da sala do curso principal (C2): link, vídeo (sem abrir a prévia) e arquivo.
    for item in ({"module": "Módulo 1", "title": "Planilha modelo de fluxo de caixa", "kind": "link",
                  "url": f"https://materiais.test/ds3-{suf}/fluxo.xlsx"},
                 {"module": "Módulo 1", "title": "Aula 1: fórmulas essenciais", "kind": "video",
                  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}):
        st, _ = _api(api, "POST", f"/api/admin/courses/{principal['id']}/contents", item, token)
        if st != 201:
            raise RuntimeError(f"seed: conteúdo {item['title']} HTTP {st}")
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("leia-me.txt", "Exercícios do módulo 2")
    st, _ = _api(api, "POST", f"/api/admin/courses/{principal['id']}/contents/file", token=token,
                 multipart=({"module": "Módulo 2", "title": "Exercícios do módulo 2"},
                            ("exercicios.zip", "application/zip", pacote.getvalue())))
    if st != 201:
        raise RuntimeError(f"seed: conteúdo de arquivo HTTP {st}")

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

    def aluno(nome, rotulo, com_senha=True, email=None):
        email = email or f"e2e.ds3.{rotulo}.{uuid.uuid4().hex[:6]}@teste.com"
        uid = Database.add_user(email, nome, senha_hash if com_senha else None, role="student")
        if uid is None:
            raise RuntimeError(f"seed: não foi possível criar {email}")
        return {"uid": uid, "email": email, "nome": nome}

    def matricula(a, c, preco, status="active", turma_id=None, ha=timedelta(days=1)):
        eid = Database.create_enrollment(a["uid"], c["id"], f"{c['id']}:ds3:{uuid.uuid4().hex}")
        pid = Database.record_payment(eid, preco, "mercado_pago")
        quando = _ts(ha)
        pagamento = {"active": "approved", "refunded": "refunded"}.get(status)
        if pagamento:
            sql("UPDATE payments SET status = ?, transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
                (pagamento, f"mp-ds3-{uuid.uuid4().hex[:10]}", quando, quando, pid))
        else:
            sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (quando, quando, pid))
        sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, quando, eid))
        if turma_id is not None:
            sql("UPDATE enrollments SET class_id = ? WHERE id = ?", (turma_id, eid))
        return {"eid": eid, "pid": pid}

    tela = aluno("Marina Fernanda Albuquerque dos Santos", "tela",
                 email=f"marina.fernanda.albuquerque.{suf}@empresa-exemplo.com.br")
    tela["mat"] = matricula(tela, principal, 480.0, turma_id=noturna["id"])
    for papel, texto, ha in (("user", "Como faço para baixar o certificado do curso?", timedelta(hours=5)),
                             ("assistant", "Você baixa o certificado na sua área quando concluir todos os materiais.",
                              timedelta(hours=5) - timedelta(seconds=20))):
        sql("INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (tela["uid"], papel, texto, _ts(ha)))
    caio = aluno("Caio Cancela", "caio")
    caio["mat"] = matricula(caio, principal, 480.0)
    pendente = aluno("Otávio Pendente", "pendente", com_senha=False)
    matricula(pendente, segundo, 290.0, status="pending", ha=timedelta(days=2))
    pedido = aluno("Rita Pedido", "pedido")
    pedido["mat"] = matricula(pedido, principal, 480.0)
    sql("""INSERT INTO cancellation_requests (enrollment_id, payment_id, user_id, reason, status, requested_at)
           VALUES (?, ?, ?, ?, 'open', ?)""",
        (pedido["mat"]["eid"], pedido["mat"]["pid"], pedido["uid"],
         "Mudei de cidade por causa do trabalho e não consigo acompanhar as aulas no horário da turma",
         _ts(timedelta(hours=3))))
    reembolso = aluno("Renato Reembolso", "reembolso")
    matricula(reembolso, segundo, 290.0, status="refunded", ha=timedelta(days=4))
    desativado = aluno("Davi Desativado", "desativado")
    desativado["mat"] = matricula(desativado, principal, 480.0, ha=timedelta(days=6))
    sql("UPDATE users SET is_active = 0 WHERE id = ?", (desativado["uid"],))

    # Observabilidade de IA (E7/F6): uso com custo, interações e um encaminhamento.
    sql("""INSERT INTO ai_usage (created_at, channel, session_hash, call_type, model, prompt_tokens, completion_tokens,
                                 total_tokens, cost_usd, latency_ms, status)
           VALUES (?, 'anonymous', ?, 'answer', 'modelo-teste', 900, 300, 1200, 0.0004, 820, 'ok')""",
        (_ts(timedelta(hours=2)), "ds3" + suf))
    sql("""INSERT INTO ai_interactions (created_at, channel, session_hash, outcome, topic)
           VALUES (?, 'anonymous', ?, 'answered', NULL)""", (_ts(timedelta(hours=2)), "ds3" + suf))
    sql("""INSERT INTO ai_interactions (created_at, channel, session_hash, outcome, topic)
           VALUES (?, 'anonymous', ?, 'unresolved', ?)""", (_ts(timedelta(hours=1)), "ds3" + suf, "como emitir boleto"))
    sql("""INSERT INTO ai_handoffs (created_at, channel, session_hash, reason)
           VALUES (?, 'anonymous', ?, 'user_request')""", (_ts(timedelta(hours=1)), "ds3" + suf))

    email_equipe = f"equipe.ds3.{suf}@teste.com"
    st, corpo = _api(api, "POST", "/api/admin/staff", {"email": email_equipe, "name": f"Pessoa Equipe {suf}",
                                                       "role": "support"}, token)
    if st != 200:
        raise RuntimeError(f"seed: convite de equipe HTTP {st}")
    equipe = {"id": corpo["staff"]["id"], "email": email_equipe, "nome": f"Pessoa Equipe {suf}"}
    # Uma conta da equipe já desativada (badge "Desativada" na tabela da Equipe).
    st, corpo = _api(api, "POST", "/api/admin/staff", {"email": f"desativada.ds3.{suf}@teste.com",
                                                       "name": f"Pessoa Desativada {suf}", "role": "financial"}, token)
    if st != 200:
        raise RuntimeError(f"seed: convite de equipe (desativada) HTTP {st}")
    st, _ = _api(api, "POST", f"/api/admin/staff/{corpo['staff']['id']}/deactivate", {}, token)
    if st != 200:
        raise RuntimeError(f"seed: desativar conta da equipe HTTP {st}")

    return {"principal": principal, "segundo": segundo, "terceiro": terceiro, "arquivado": arquivado,
            "noturna": noturna, "sabado": sabado, "tela": tela, "caio": caio, "pendente": pendente, "pedido": pedido,
            "reembolso": reembolso, "desativado": desativado, "equipe": equipe}


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
    with ambiente_isolado("ds3") as ambiente:
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
.nav-tabs { display: flex; list-style: none; padding: 0; margin: 0; position: relative; }
.nav-tabs .nav-link { display: block; padding: 10px 14px; background: none; border: 0; font-size: 16px; }
.ind { position: absolute; bottom: 0; left: 0; height: 2px; background: #0096c7; }
.faixa { display: flex; border: 1px solid #d8e0e8; margin: 0; }
.faixa > div { flex: 1; padding: 12px; }
.faixa > div + div { border-left: 1px solid #d8e0e8; }
.faixa dd { margin: 0; color: #17212b; font-variant-numeric: tabular-nums; font-size: 28px; }
.solto { display: flex; gap: 8px; }
.solto .card { flex: 1; border: 1px solid #d8e0e8; box-shadow: 0 2px 6px rgba(0,0,0,.1); padding: 12px; }
.solto .valor { color: #1e7e34; font-size: 28px; }
.oculto { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style></head><body>
<div id="boa">
  <ul class="nav-tabs" role="tablist">
    <li><button class="nav-link" role="tab" aria-selected="true">Financeiro</button></li>
    <li><button class="nav-link" role="tab" aria-selected="false">Alunos</button></li>
    <li class="ind" data-testid="abas-indicador" aria-hidden="true"></li>
  </ul>
  <h2>Financeiro</h2>
  <div data-testid="painel-sub"><h2>Alunos de Curso X</h2><p>texto</p></div>
  <h2 id="t-trans">Transações</h2>
  <table aria-labelledby="t-trans"><thead><tr><th scope="col">Aluno</th><th scope="col">Valor</th></tr></thead>
    <tbody><tr><td>a</td><td>1</td></tr></tbody></table>
  <table><caption>Turmas do curso</caption><thead><tr><th scope="col">Turma</th></tr></thead><tbody><tr><td>t</td></tr></tbody></table>
  <table aria-label="Motivos de encaminhamento"><tbody><tr><td>m</td><td>1</td></tr></tbody></table>
  <h2>Novo curso</h2><input data-testid="curso-anexo-input" aria-label="arquivo"><form data-testid="curso-form"></form>
  <dl class="faixa">
    <div><dt>Receita aprovada</dt><dd data-testid="kpi-valor">R$ 1,00</dd></div>
    <div><dt>Pendente</dt><dd data-testid="kpi-valor">R$ 2,00</dd></div>
    <div><dt>Reembolsado</dt><dd data-testid="kpi-valor">R$ 3,00</dd></div>
    <div><dt>Projeção próximo mês</dt><dd data-testid="kpi-valor">R$ 4,00</dd></div>
  </dl>
</div>
<div id="atual">
  <ul class="nav-tabs">
    <li><button class="nav-link" aria-current="page">Financeiro</button></li>
    <li><button class="nav-link">Alunos</button></li>
    <li class="ind" data-testid="abas-indicador" aria-hidden="true"></li>
  </ul>
  <h2>Financeiro</h2>
</div>
<div id="ruim">
  <ul class="nav-tabs">
    <li><button class="nav-link">Financeiro</button></li>
    <li><button class="nav-link" aria-current="page">Alunos</button></li>
    <li><button class="nav-link" aria-selected="true">Cursos</button></li>
    <li class="ind" data-testid="abas-indicador" aria-hidden="true" style="width: 300px; left: 200px"></li>
  </ul>
  <h5>Transações</h5>
  <div data-testid="painel-ruim"><h5>Alunos de Curso X</h5></div>
  <h2>Outro título</h2><input data-testid="anexo-ruim" aria-label="arquivo">
  <h2 id="p-ruim">Rótulo</h2><p id="par">parágrafo</p>
  <table><thead><tr><th>Aluno</th><th scope="row">Valor</th></tr></thead><tbody><tr><td>a</td><td>1</td></tr></tbody></table>
  <table><caption class="oculto">Escondido</caption><tbody><tr><td>x</td></tr></tbody></table>
  <table aria-labelledby="par"><tbody><tr><td>y</td></tr></tbody></table>
</div>
<div id="cartoes" class="solto">
  <div class="card"><div>Receita aprovada</div><div class="valor" data-testid="x-kpi">R$ 1,00</div></div>
  <div class="card"><div>Pendente</div><div class="valor" data-testid="x-kpi">R$ 2,00</div></div>
  <div class="card"><div>Reembolsado</div><div class="valor" data-testid="x-kpi">R$ 3,00</div></div>
  <div class="card"><div>Projeção próximo mês</div><div class="valor" data-testid="x-kpi">R$ 4,00</div></div>
</div>
<script>
for (const raiz of document.querySelectorAll('#boa, #atual')) {
  const ativa = raiz.querySelector('.nav-link'), ind = raiz.querySelector('.ind');
  ind.style.width = ativa.offsetWidth + 'px'; ind.style.transform = 'translateX(' + ativa.offsetLeft + 'px)';
}
</script>
</body></html>"""


def test_ds3_apoio_verificador(browser):
    ctx = browser.new_context(viewport={"width": 1200, "height": 900})
    page = ctx.new_page()
    page.set_content(_SINTETICA)
    try:
        def v1():
            erros = []
            for raiz in ("#boa", "#atual"):
                v = page.evaluate(_JS_ABAS, {"raiz": raiz, "ativa": "Financeiro"})
                if v:
                    erros.append(f"{raiz} correto gerou violações: {v}")
            ruim = " | ".join(page.evaluate(_JS_ABAS, {"raiz": "#ruim", "ativa": "Financeiro"}))
            for esperado in ('aba ativa "Financeiro" não expõe o estado', 'aba inativa "Alunos" com aria-current',
                             'aba inativa "Cursos" com aria-selected="true"', "indicador em x="):
                if esperado not in ruim:
                    erros.append(f"não apontado: {esperado!r}")
            if erros:
                raise Falha(f"{erros}; obtido no #ruim: {ruim}")

        def v2():
            boa = page.evaluate(_JS_TITULOS, {"raiz": "#boa", "aba": "Financeiro", "subs": [
                {"nome": "sub", "container": '[data-testid="painel-sub"]', "contem": ["Curso X"]},
                {"nome": "form", "antes": ['[data-testid="curso-anexo-input"]'], "contem": ["Novo curso"]}]})
            if boa["aba"] or boa["subs"]:
                raise Falha(f"títulos corretos geraram violações: {boa}")
            ruim = page.evaluate(_JS_TITULOS, {"raiz": "#ruim", "aba": "Financeiro", "subs": [
                {"nome": "sub", "container": '[data-testid="painel-ruim"]', "contem": ["Curso X"]},
                {"nome": "form", "antes": ['[data-testid="anexo-ruim"]'], "contem": ["Novo curso"]}]})
            tudo = " | ".join(ruim["aba"] + ruim["subs"])
            faltam = [e for e in ('o primeiro título é <h5> "Transações" (esperado h2)', 'não contém "Financeiro"',
                                  'sub (primeiro título de [data-testid="painel-ruim"]): o primeiro título é <h5>',
                                  'o título <h2> "Outro título" não contém "Novo curso"') if e not in tudo]
            if faltam:
                raise Falha(f"não apontados {faltam}; obtido: {tudo}")

        def v3():
            boa = page.evaluate(_JS_TABELAS, {"raiz": "#boa"})
            erros = [f"{t['ident']}: {t}" for t in boa if not t["nome"] or t["semScope"]]
            if len(boa) != 3 or erros:
                raise Falha(f"tabelas corretas: {boa}")
            ruim = page.evaluate(_JS_TABELAS, {"raiz": "#ruim"})
            tudo = json.dumps(ruim, ensure_ascii=False)
            faltam = [e for e in ("sem caption, aria-labelledby nem aria-label", "caption invisível",
                                  'não aponta para um título (p)', '"Aluno"', '"Valor"') if e not in tudo]
            if faltam or any(t["nome"] for t in ruim):
                raise Falha(f"não apontados {faltam}; obtido: {tudo}")

        def v4():
            args = {"rotulos": list(ROTULOS_KPI), "texto": TEXTO, "minimo": 4}
            boa = page.evaluate(_JS_FAIXA, args)
            if boa["n1"] or boa["n2"] or boa["n3"]:
                raise Falha(f"faixa correta gerou violações: {boa}")
            page.evaluate("""() => {
              document.querySelectorAll('#boa [data-testid=kpi-valor]').forEach(e => e.removeAttribute('data-testid'));
              document.querySelectorAll('[data-testid=x-kpi]').forEach(e => e.setAttribute('data-testid', 'kpi-valor'));
            }""")
            ruim = page.evaluate(_JS_FAIXA, args)
            tudo = " | ".join(ruim["n1"] + ruim["n2"] + ruim["n3"])
            faltam = [e for e in ("sem borda única", ".card dentro da faixa", "sombra dentro da faixa",
                                  "borda nos quatro lados", "com cor rgb(30, 126, 52)", "sem tabular-nums",
                                  'sem rótulo "Receita aprovada"') if e not in tudo]
            if faltam:
                raise Falha(f"não apontados {faltam}; obtido: {tudo}")

        _rodar([
            ("V1", "abas: estado correto passa; ausente, duplicado e indicador desalinhado apontados", v1),
            ("V2", "títulos: h2 com o nome passa; h5 e texto errado apontados", v2),
            ("V3", "tabelas: nome acessível e scope reconhecidos; defeitos apontados", v3),
            ("V4", "faixa de números: correta passa; cartões soltos apontados", v4),
        ])
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------- teste
def test_ds3_painel_equipe(browser, spa):
    contextos, erros, nativos = [], [], []
    requisicoes = {}  # id(page) -> [(método, caminho)] de /api/
    seed = {}
    try:
        seed.update(semear(spa))
    except Exception as erro:  # o cenário P0 mostra a falha do seed
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova(largura):
        ctx = browser.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR", reduced_motion="reduce",
                                  accept_downloads=True)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        contextos.append(ctx)
        page = ctx.new_page()
        lista = requisicoes.setdefault(id(page), [])

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
                erros.append(f"{msg.text[:100]} ({url})")

        def ao_dialogo(dialogo):
            nativos.append(f"{dialogo.type}: {dialogo.message[:120]}")
            dialogo.dismiss()  # recusado: nada é executado

        def ao_pedido(req):
            caminho = urllib.parse.urlparse(req.url).path
            if caminho.startswith("/api/"):
                lista.append((req.method, caminho))

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        page.on("dialog", ao_dialogo)
        page.on("request", ao_pedido)
        return page

    def entrar(page, perfil):
        email, senha = CONTAS[perfil]
        page.goto(spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login de {perfil} não levou a /admin (URL {page.url})")
        page.wait_for_load_state("networkidle")
        page.locator(SEL_ABA).first.wait_for(state="visible", timeout=TIMEOUT)

    def clicar_aba(page, nome):
        aba = page.locator(SEL_ABA, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$"))
        try:
            aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"a aba '{nome}' não aparece")
        aba.first.click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(700)

    # --- coleta das medidas ------------------------------------------------------------------------------
    medidas = {}       # (perfil, tela, largura) -> dict
    abas_vistas = {}   # (perfil, largura) -> [rótulos]

    def subs_de(tela):
        form_novo = {"nome": "formulário de novo curso", "antes": FORM_CURSO, "contem": ["Novo curso"]}
        return {
            "Cadastro de cursos": [form_novo],
            SUB_ARQUIVO: [form_novo],
            SUB_DETALHE: [{"nome": SUB_DETALHE, "container": '[data-testid="aluno-detalhe"]',
                           "contem": [seed["tela"]["nome"]]}],
            SUB_DESATIVADO: [{"nome": SUB_DESATIVADO, "container": '[data-testid="aluno-detalhe"]',
                              "contem": [seed["desativado"]["nome"]]}],
            SUB_CURSO_ALUNOS: [{"nome": SUB_CURSO_ALUNOS, "container": '[data-testid="curso-alunos"]',
                                "contem": [seed["principal"]["nome"]]}],
            SUB_CONTEUDOS: [{"nome": SUB_CONTEUDOS, "container": '[data-testid="conteudos-painel"]',
                             "contem": [seed["principal"]["nome"]]}, form_novo],
            SUB_EDITAR: [{"nome": "formulário de editar curso", "antes": FORM_CURSO, "contem": ["Editar curso"]}],
        }.get(tela, [])

    def medir(perfil, tela, largura, page):
        aba = tela.split(" > ")[0]
        try:
            page.wait_for_load_state("networkidle")
            page.mouse.move(1, 1)
            page.wait_for_timeout(400)
            m = {
                "contraste": varrer_contraste(page),
                "fontes": fontes_abaixo_de(page, 14),
                "teal": page.evaluate(_JS_COR, {"cor": TEAL, "fundo": False, "permitidos": []}),
                "ds1": page.evaluate(_JS_MEDIR),
                "abas": page.evaluate(_JS_ABAS, {"raiz": RAIZ, "ativa": aba}),
                "titulos": page.evaluate(_JS_TITULOS, {"raiz": RAIZ, "aba": aba, "subs": subs_de(tela)}),
                "tabelas": page.evaluate(_JS_TABELAS, {"raiz": RAIZ}),
                "badges": page.evaluate(_JS_BADGES, {"sel": f"{RAIZ} .badge"}),
                "badges_contraste": varrer_contraste(page, dentro_de=[f"{RAIZ} .badge"]),
                "textos_badges": page.evaluate(_JS_TEXTOS_BADGES, f"{RAIZ} .badge"),
                "faixa": (page.evaluate(_JS_FAIXA, {"rotulos": list(ROTULOS_KPI), "texto": TEXTO, "minimo": 4})
                          if tela == "Financeiro" else None),
            }
            medidas[(perfil, tela, largura)] = m
        except Exception as erro:
            medidas[(perfil, tela, largura)] = {"erro": f"{type(erro).__name__}: {str(erro).splitlines()[0][:160]}"}

    def falha_de_tela(perfil, tela, largura, erro):
        medidas[(perfil, tela, largura)] = {"erro": str(erro).splitlines()[0][:180]}

    def preparar_cursos(page):
        escolha = page.locator('[data-testid="turma-new-course"]')
        escolha.first.select_option(seed["principal"]["id"], timeout=TIMEOUT)
        page.locator('[data-testid="enrollment-row"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def abrir_detalhe(page, nome):
        page.locator("app-students-dashboard button", has_text=nome).first.click(timeout=TIMEOUT)
        detalhe = page.locator('[data-testid="aluno-detalhe"]')
        detalhe.filter(has_text=nome).first.wait_for(state="visible", timeout=TIMEOUT)
        page.locator('[data-testid="aluno-detalhe-matricula"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def abrir_alunos_curso(page):
        page.locator('[data-testid="curso-alunos-link"]', has_text=seed["principal"]["nome"]).first.click(
            timeout=TIMEOUT)
        page.locator('[data-testid="curso-aluno-row"]').first.wait_for(state="visible", timeout=TIMEOUT)
        page.locator('[data-testid="matricula-manual-abrir"]').first.click(timeout=TIMEOUT)
        page.locator('[data-testid="matricula-manual-email"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def linha_do_curso(page, curso_id):
        return page.locator(f'[data-testid="curso-row"][data-course-id="{curso_id}"]').first

    def escolher_arquivo(page):
        controle = page.locator('[data-testid="curso-anexo-input"]').first
        with page.expect_response(lambda r: urllib.parse.urlparse(r.url).path == "/api/admin/course-draft"
                                  and r.request.method == "POST", timeout=TIMEOUT * 3):
            controle.set_input_files(files=[{"name": "rascunho.json", "mimeType": "application/json",
                                             "buffer": json.dumps(RASCUNHO_INCOMPLETO, ensure_ascii=False).encode()}],
                                     timeout=TIMEOUT)
        page.locator('[data-testid="curso-anexo-avisos"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def abrir_conteudos(page):
        linha_do_curso(page, seed["principal"]["id"]).locator('[data-testid="curso-conteudos"]').click(timeout=TIMEOUT)
        page.locator('[data-testid="conteudo-linha"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def fechar_conteudos(page):
        page.locator('[data-testid="conteudos-fechar"]').first.click(timeout=TIMEOUT)
        page.locator('[data-testid="conteudos-painel"]').first.wait_for(state="detached", timeout=TIMEOUT)

    def abrir_edicao(page):
        linha_do_curso(page, seed["principal"]["id"]).locator('[data-testid="curso-edit"]').click(timeout=TIMEOUT)
        page.locator('[data-testid="curso-cancel-edit"]').first.wait_for(state="visible", timeout=TIMEOUT)

    def subpaineis_gestao(aba):
        if aba == "Alunos":
            return [(SUB_DETALHE, lambda p: abrir_detalhe(p, seed["tela"]["nome"])),
                    (SUB_DESATIVADO, lambda p: abrir_detalhe(p, seed["desativado"]["nome"]))]
        if aba == "Cursos":
            return [(SUB_CURSO_ALUNOS, abrir_alunos_curso)]
        if aba == "Cadastro de cursos":
            return [(SUB_ARQUIVO, escolher_arquivo), (SUB_CONTEUDOS, abrir_conteudos),
                    (SUB_EDITAR, lambda p: (fechar_conteudos(p), abrir_edicao(p)))]
        return []

    def coletar():
        if "erro" in seed:
            return
        for largura in LARGURAS:
            for perfil in PERFIS:
                page = nova(largura)
                try:
                    entrar(page, perfil)
                    abas_vistas[(perfil, largura)] = page.evaluate(_JS_LISTA_ABAS, RAIZ)
                except Exception as erro:
                    for aba in ABAS[perfil]:
                        falha_de_tela(perfil, aba, largura, erro)
                    continue
                for aba in ABAS[perfil]:
                    try:
                        clicar_aba(page, aba)
                        if aba == "Cursos" and perfil == "Gestão":
                            preparar_cursos(page)
                    except Exception as erro:
                        falha_de_tela(perfil, aba, largura, f"aba {aba}: {erro}")
                        continue
                    medir(perfil, aba, largura, page)
                    if perfil != "Gestão":
                        continue
                    for sub, preparar in subpaineis_gestao(aba):
                        try:
                            preparar(page)
                        except Exception as erro:
                            falha_de_tela(perfil, sub, largura, f"{sub} não abriu: {erro}")
                            continue
                        medir(perfil, sub, largura, page)

    coletar()

    ordem_telas = []
    for perfil in PERFIS:
        for aba in ABAS[perfil]:
            ordem_telas.append((perfil, aba))
            if perfil == "Gestão":
                ordem_telas.extend((perfil, s) for s in SUBPAINEIS if s.startswith(aba + " > "))

    def chaves():
        def pos(k):
            return (ordem_telas.index((k[0], k[1])) if (k[0], k[1]) in ordem_telas else 999, -k[2])
        return sorted(medidas, key=pos)

    def exigir_seed():
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")
        if not medidas:
            raise Falha("nenhuma tela foi medida")

    def por_tela(funcao, resumo, filtro=None, larguras=LARGURAS):
        """Aplica `funcao(m, chave)` -> lista de violações em cada (perfil, tela, largura) medida."""
        def cenario():
            exigir_seed()
            v = []
            for chave in chaves():
                perfil, tela, largura = chave
                if largura not in larguras or (filtro and not filtro(perfil, tela)):
                    continue
                m = medidas[chave]
                rotulo = f"{perfil} /admin {tela} @{largura}px"
                if "erro" in m:
                    v.append(f"{rotulo}: {m['erro']}")
                    continue
                v.extend(f"{rotulo}: {item}" for item in funcao(m, chave))
            _exigir(v, resumo)
        return cenario

    # --- P0/P1 ---------------------------------------------------------------------------------------------
    def p0():
        exigir_seed()
        v = []
        largura = 1366
        for aba in ABAS["Gestão"]:
            m = medidas.get(("Gestão", aba, largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"aba {aba}: {m['erro']}")
                continue
            if not m["ds1"]["tabelas"]:
                v.append(f"aba {aba}: nenhuma tabela visível")
            for t in m["ds1"]["tabelas"]:
                print(f"   [info] Gestão aba {aba}: tabela '{t['titulo']}' com {t['linhas']} linha(s)")
                if t["linhas"] < 1:
                    v.append(f"aba {aba}: tabela '{t['titulo']}' sem linha de dados")
        for sub in SUBPAINEIS:
            for w in LARGURAS:
                m = medidas.get(("Gestão", sub, w), {"erro": "não medida"})
                if "erro" in m:
                    v.append(f"{sub} @{w}px: {m['erro']}")
        esperados = {("Gestão", "Financeiro"): ("Aprovado", "Pendente", "Reembolsado"),
                     ("Financeiro", "Financeiro"): ("Aprovado", "Pendente", "Reembolsado"),
                     ("Gestão", "Cadastro de cursos"): ("Arquivado",),
                     ("Gestão", "Equipe"): ("Ativa", "Desativada", MARCADOR_PROPRIO),
                     ("Gestão", SUB_DESATIVADO): ("Desativado",)}
        for (perfil, tela), textos in esperados.items():
            m = medidas.get((perfil, tela, largura), {"erro": "não medida"})
            if "erro" in m:
                v.append(f"{perfil} {tela}: {m['erro']}")
                continue
            print(f"   [info] {perfil} {tela}: badges {sorted(set(m['textos_badges']))}")
            for texto in textos:
                if not any(texto in b for b in m["textos_badges"]):
                    v.append(f"{perfil} {tela}: badge {texto!r} não encontrado ({sorted(set(m['textos_badges']))})")
        m = medidas.get(("Gestão", "Observabilidade de IA", largura), {})
        if "erro" not in m and not any(t in ("No ar", "Com problema") for t in m.get("textos_badges", [])):
            v.append(f"Gestão Observabilidade de IA: badge de saúde não encontrado ({m.get('textos_badges')})")
        _exigir(v, "pré-condição do seed")

    def p1():
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")
        v = []
        for perfil in PERFIS:
            for largura in LARGURAS:
                vistas = abas_vistas.get((perfil, largura))
                if vistas is None:
                    v.append(f"{perfil} @{largura}px: login ou abas não medidos")
                elif tuple(vistas) != ABAS[perfil]:
                    v.append(f"{perfil} @{largura}px: abas {vistas} (esperado {list(ABAS[perfil])})")
        _exigir(v, "abas por perfil (permissões)")

    # --- A/F/T ---------------------------------------------------------------------------------------------
    def a1(m, chave):
        c = m["contraste"]
        out = []
        if c["verificados"] < 10:
            out.append(f"só {c['verificados']} textos verificados (esperado >= 10)")
        out.extend(descrever([f], 1) for f in c["falhas"])
        return out

    def a2(m, chave):
        gradiente = [i for i in m["contraste"]["ignorados"] if "gradiente" in i["motivo"] or "imagem" in i["motivo"]]
        outros = [i for i in m["contraste"]["ignorados"] if i not in gradiente]
        if outros:
            print(f"   [info] {chave[0]} {chave[1]} @{chave[2]}px: ignorados (não contam) -> {descrever(outros, 8)}")
        return [descrever([i], 1) for i in gradiente]

    def f1(m, chave):
        return [descrever([i], 1) for i in m["fontes"]]

    def t1(m, chave):
        return m["teal"]

    # --- B/H/M ---------------------------------------------------------------------------------------------
    def b1(m, chave):
        return m["abas"]

    def h1(m, chave):
        return m["titulos"]["aba"]

    def h2(m, chave):
        return m["titulos"]["subs"]

    def m1(m, chave):
        out = []
        if not m["tabelas"]:
            out.append("nenhuma tabela visível no painel")
        for t in m["tabelas"]:
            if not t["nome"]:
                out.append(f"{t['ident']} sem nome acessível ({t['motivo']})")
        return out

    def m2(m, chave):
        return [f"{t['ident']}: th sem scope=\"col\": {t['semScope']}" for t in m["tabelas"] if t["semScope"]]

    # --- S -------------------------------------------------------------------------------------------------
    def s1(m, chave):
        out = []
        for b in m["badges"]:
            if _normalizar(b["texto"]) == MARCADOR_PROPRIO:
                continue
            if not b["temLetra"]:
                out.append(f"badge sem texto ({b['texto']!r})")
            if not b["sinais"]:
                out.append(f"badge {b['texto']!r} só com cor (sem ícone/ponto aria-hidden, ::before/::after ou prefixo)")
        bc = m["badges_contraste"]
        out.extend(f"badge abaixo do AA: {descrever([f], 1)}" for f in bc["falhas"])
        out.extend(f"badge não medido: {descrever([i], 1)}" for i in bc["ignorados"])
        return out

    # --- N -------------------------------------------------------------------------------------------------
    def n(chave_faixa):
        def funcao(m, chave):
            if m["faixa"] is None:
                return ["faixa não medida"]
            return m["faixa"][chave_faixa]
        return funcao

    # --- G -------------------------------------------------------------------------------------------------
    def g1(m, chave):
        d = m["ds1"]
        if len(d["h1"]) != 1:
            return [f"{len(d['h1'])} h1 visíveis {d['h1']}" + (f" (+{d['h1Ocultos']} oculto(s))" if d["h1Ocultos"] else "")]
        return []

    def g2(m, chave):
        return list(m["ds1"]["campos"])

    def g3(m, chave):
        return list(m["ds1"]["alvos"])

    def g4(m, chave):
        d = m["ds1"]
        fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
        if d["scrollWidth"] > 390:
            return [f"scrollWidth {d['scrollWidth']}px (> 390). Passam da borda: {fora}"]
        if d["clipaRaiz"] and d["fora"]:
            return [f"estouro escondido por overflow-x hidden no html/body. Passam da borda: {fora}"]
        return []

    # --- D1 ações destrutivas ------------------------------------------------------------------------------
    def abrir_e_voltar(page, nome, botao, inline=None, linha=None):
        """Abre a confirmação da ação destrutiva e volta. Devolve a lista de violações."""
        reqs = requisicoes[id(page)]
        v = []
        try:
            botao.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            return [f"{nome}: botão não visível"]
        if botao.is_disabled():
            return [f"{nome}: botão desabilitado (seed)"]
        n_nativos = len(nativos)
        antes = len(reqs)
        botao.click(timeout=TIMEOUT)
        janela = page.locator(SEL_JANELA).first
        forma = None
        limite = time.time() + 5
        while time.time() < limite and forma is None:
            if page.locator(SEL_JANELA).count() and janela.is_visible():
                forma = "janela"
            elif inline and inline[0].count() and inline[0].first.is_visible():
                forma = "linha"
            else:
                page.wait_for_timeout(100)
        if forma == "janela":
            confirmar = janela.locator(SEL_CONFIRMAR)
            if confirmar.count() == 1:
                fundo = confirmar.first.evaluate("e => getComputedStyle(e).backgroundColor")
                cor = confirmar.first.evaluate("e => getComputedStyle(e).color")
                if fundo != VERMELHO or cor != BRANCO:
                    v.append(f"{nome}: confirmar com fundo {fundo} e texto {cor} (destrutiva: {VERMELHO} e branco)")
                try:
                    if razao_contraste(cor, fundo) < 4.5:
                        v.append(f"{nome}: confirmar com contraste {razao_contraste(cor, fundo):.2f}:1")
                except ValueError:
                    pass
            else:
                v.append(f"{nome}: {confirmar.count()} botões de confirmar na janela")
            voltar = janela.locator(SEL_VOLTAR)
            if voltar.count() != 1:
                v.append(f"{nome}: {voltar.count()} botões Voltar na janela")
                page.keyboard.press("Escape")
            else:
                voltar.first.click(timeout=TIMEOUT)
            try:
                page.locator(SEL_JANELA).first.wait_for(state="hidden", timeout=3000)
            except sync_api.TimeoutError:
                v.append(f"{nome}: a janela não fechou com Voltar")
        elif forma == "linha":
            print(f"   [info] D1 {nome}: confirmação na própria linha (forma de hoje, aceita)")
            inline[1].first.click(timeout=TIMEOUT)
        else:
            extra = f"; diálogo nativo: {nativos[n_nativos:]}" if len(nativos) > n_nativos else ""
            v.append(f"{nome}: nenhuma confirmação apareceu (nem a janela {SEL_JANELA}"
                     + (" nem a confirmação na linha" if inline else "") + f"){extra}")
        page.wait_for_timeout(800)
        feitas = [r for r in reqs[antes:] if r[0] != "GET"]
        if feitas:
            v.append(f"{nome}: requisição sem confirmar: {feitas}")
        if len(nativos) > n_nativos:
            v.append(f"{nome}: diálogo nativo do navegador: {nativos[n_nativos:]}")
        if linha is not None:
            try:
                linha.wait_for(state="visible", timeout=2000)
            except sync_api.TimeoutError:
                v.append(f"{nome}: a linha sumiu depois de voltar")
        return v

    def d1():
        exigir_seed()
        v = []
        page = nova(1366)
        entrar(page, "Gestão")

        def passo(nome, funcao):
            try:
                v.extend(funcao())
            except Exception as erro:
                v.append(f"{nome}: {type(erro).__name__}: {str(erro).splitlines()[0][:160]}")

        def financeiro_cancelamento():
            clicar_aba(page, "Financeiro")
            linha = page.locator('[data-testid="cancelamento-row"]').filter(has_text=seed["pedido"]["email"]).first
            return abrir_e_voltar(page, "Aprovar e reembolsar (Solicitações de cancelamento)",
                                  linha.locator('[data-testid="cancelamento-aprovar"]'), linha=linha)

        def financeiro_reembolso():
            linha = page.locator("app-financial-dashboard tr").filter(has_text=seed["tela"]["email"]).filter(
                has=page.locator("button", has_text="Reembolsar")).first
            return abrir_e_voltar(page, "Reembolsar (Transações)", linha.locator("button", has_text="Reembolsar"),
                                  linha=linha)

        def alunos_desativar():
            clicar_aba(page, "Alunos")
            abrir_detalhe(page, seed["tela"]["nome"])
            return abrir_e_voltar(page, "Desativar conta (detalhe do aluno)",
                                  page.locator('[data-testid="aluno-desativar"]').first,
                                  linha=page.locator('[data-testid="aluno-desativar"]').first)

        def cursos_turma():
            clicar_aba(page, "Cursos")
            linha = page.locator('[data-testid="turma-row"]').filter(has_text=seed["sabado"]["nome"]).first
            return abrir_e_voltar(page, "Excluir turma (Turmas por curso)",
                                  linha.locator('[data-testid="turma-excluir"]'), linha=linha)

        def cadastro_curso():
            clicar_aba(page, "Cadastro de cursos")
            linha = linha_do_curso(page, seed["terceiro"]["id"])
            return abrir_e_voltar(page, "Excluir curso (Cursos cadastrados)", linha.locator('[data-testid="curso-delete"]'),
                                  inline=(linha.locator('[data-testid="curso-delete-confirm"]'),
                                          linha.locator('[data-testid="curso-cancel-delete"]')),
                                  linha=linha)

        def cadastro_conteudo():
            abrir_conteudos(page)
            linha = page.locator('[data-testid="conteudo-linha"]').first
            return abrir_e_voltar(page, "Excluir conteúdo (Conteúdos do curso)",
                                  linha.locator('[data-testid="conteudo-excluir"]'),
                                  inline=(linha.locator('[data-testid="conteudo-excluir-confirmar"]'),
                                          linha.locator("button", has_text=re.compile(r"^\s*Cancelar\s*$"))),
                                  linha=linha)

        def equipe_desativar():
            clicar_aba(page, "Equipe")
            linha = page.locator('[data-testid="equipe-row"]').filter(has_text=seed["equipe"]["email"]).first
            return abrir_e_voltar(page, "Desativar (Equipe)", linha.locator('[data-testid="equipe-desativar"]'),
                                  linha=linha)

        for nome, funcao in (("financeiro/cancelamento", financeiro_cancelamento),
                             ("financeiro/reembolso", financeiro_reembolso),
                             ("alunos/desativar", alunos_desativar), ("cursos/turma", cursos_turma),
                             ("cadastro/curso", cadastro_curso), ("cadastro/conteúdo", cadastro_conteudo),
                             ("equipe/desativar", equipe_desativar)):
            passo(nome, funcao)
        _exigir(v, "ação destrutiva sem passar pela confirmação")

    def k1():
        _exigir(list(erros) + [f"diálogo nativo: {d}" for d in nativos], "erro de console, exceção ou diálogo nativo")

    gestao_financeiro = (lambda p, t: t == "Financeiro")
    try:
        _rodar([
            ("P0", "pré-condição do seed (tabelas, subpainéis, badges)", p0),
            ("P1", "permissões: abas por perfil inalteradas", p1),
            ("A1", "contraste AA completo em todas as telas do painel", por_tela(a1, "contraste AA")),
            ("A2", "nenhum texto sobre gradiente/imagem", por_tela(a2, "texto sobre gradiente")),
            ("F1", "nenhum texto abaixo de 14 px", por_tela(f1, "texto abaixo de 14 px")),
            ("T1", "nenhum texto em #0096c7", por_tela(t1, "texto em #0096c7")),
            ("B1", "abas com estado claro (aria) e indicador na aba ativa", por_tela(b1, "estado das abas")),
            ("H1", "h2 com o nome da aba como primeiro título", por_tela(h1, "título da aba")),
            ("H2", "h2 com o nome do subpainel/formulário",
             por_tela(h2, "título do subpainel", filtro=lambda p, t: bool(subs_de(t)))),
            ("M1", "toda tabela com nome acessível", por_tela(m1, "tabela sem nome acessível")),
            ("M2", "th do cabeçalho com scope=col", por_tela(m2, "cabeçalho de tabela sem scope")),
            ("S1", "status com texto e sinal não cromático, AA", por_tela(s1, "status só por cor")),
            ("N1", "faixa de números: borda única, divisórias, sem cartão nem sombra",
             por_tela(n("n1"), "faixa de números (estrutura)", filtro=gestao_financeiro)),
            ("N2", "faixa de números: cor do texto, tabular-nums, rótulo ligado",
             por_tela(n("n2"), "faixa de números (valores e rótulos)", filtro=gestao_financeiro)),
            ("N3", "faixa de números: sem estouro nem sobreposição",
             por_tela(n("n3"), "faixa de números (largura)", filtro=gestao_financeiro)),
            ("D1", "ações destrutivas: abrir e voltar sem requisição", d1),
            ("G1", "guarda DS1: um h1 por tela", por_tela(g1, "um h1 por tela")),
            ("G2", "guarda DS1: rótulo em todo campo", por_tela(g2, "rótulo de campo")),
            ("G3", "guarda DS1: alvos >= 44 px", por_tela(g3, f"alvo de toque < {ALVO_MIN:.0f} px")),
            ("G4", "guarda DS1: sem rolagem horizontal a 390 px",
             por_tela(g4, "rolagem horizontal a 390 px", larguras=(390,))),
            ("K1", "sem erros de console nem diálogo nativo", k1),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
