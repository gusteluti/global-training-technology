"""E2E da DS1 (D115, docs/tdd/PLANO_DESIGN.md) — componentes base: janela de confirmação do app, um h1 por tela, rótulo
em todo campo, alvo de toque de 44 px e nenhuma rolagem horizontal a 390 px.

Regra da D115: só design. Nenhuma rota, API, texto de pergunta, data-testid ou fluxo muda. A janela do app substitui o
`confirm()` do navegador: "Confirmar" executa exatamente o que o `confirm()` aceito executava; "Voltar" (e Esc) não faz
nada, nenhuma chamada de API. Os textos das perguntas continuam os de hoje.

Contrato visual da janela (pedido da DS1; o dev implementa):
  [data-testid="confirmacao"]  um único componente na casca (fora das telas roteadas), role="alertdialog",
                               aria-modal="true", aria-labelledby -> título, aria-describedby -> texto com a pergunta;
                               fundo escurecido por trás (o ponto do canto da tela cai na camada da janela, escura)
  [data-testid="confirmacao-voltar"]     "Voltar"; recebe o foco ao abrir
  [data-testid="confirmacao-confirmar"]  rótulo da ação; em ação destrutiva, fundo #b42318 com texto branco (>= 4,5:1)
  Tab e Shift+Tab presos na janela; Esc fecha como "Voltar"; ao fechar, o foco volta ao botão que abriu.

Harness isolado (D58). Telas medidas a 1366 px e a 390 px de largura, com dados semeados (pelo menos uma linha em cada
tabela da Gestão, como nos seeds de U1/F3/L1/U5):
  anônimas:  /login, /cadastro, /esqueci-senha, /definir-senha?token=<setup>, /redefinir-senha?token=<reset>, /termos,
             /privacidade
  aluno:     /student, /student/perfil, /student/curso/<matrícula ativa>, /catalogo
  Gestão:    /admin, cada aba visível (Financeiro, Alunos, Cursos, Cadastro de cursos, Observabilidade de IA, Auditoria,
             Equipe); na aba Cursos o curso do seed é escolhido em "Gerenciar turmas" para a tabela de matrículas aparecer;
             e os dois painéis que hoje estouram no celular (sonda do agente-testes: 488 e 411 px a 390 px), abertos dentro
             das abas: "Alunos > detalhe do aluno" (clique no nome) e "Cursos > alunos do curso" (clique no curso)

test_ds1_apoio_verificador (sem servidor; valida o próprio verificador numa página sintética, passa no red):
  V1 janela correta não gera violação; V2 janela com defeitos tem cada defeito apontado; V3 confirm() nativo apontado;
  V4 medição de h1, rótulo, alvo e largura acerta os casos conhecidos

test_ds1_componentes — cenários (cada um lista TODAS as violações, não para na primeira):
  P1 pré-condição do seed: cada tabela visível das abas da Gestão tem ao menos uma linha de dados (passa no red)
  H1/H2/H3 exatamente um <h1> visível em cada tela (anônimas / aluno / abas da Gestão), nas duas larguras
  (nos dois subpainéis, R e T listam só o que não aparece já na aba de base, para não repetir a lista)
  R1/R2/R3 todo input (exceto hidden), select e textarea visível tem nome acessível por label[for], label envolvendo,
           aria-label não vazio ou aria-labelledby válido (ids existentes, texto não vazio); placeholder e title não
           contam
  T1/T2/T3 todo button, .btn, a.btn, .nav-link e link da barra superior visível tem altura >= 44 px (1366 e 390 px);
           input/select ficam de fora (piso de 16 px da DS0); elementos invisíveis ficam de fora
  X1/X2/X3 a 390 px, document.documentElement.scrollWidth <= 390; rolagem interna de contêiner overflow-x auto/scroll é
           permitida. Escolha do agente-testes: também é violação esconder o estouro com overflow-x hidden/clip no
           <html>/<body> (conteúdo cortado); a mensagem lista os elementos que passam da borda
  C1 aluno, pedir cancelamento (mecanismo completo da janela; Voltar e Esc sem requisição; Confirmar faz o POST
     /api/student/enrollments/<id>/cancel-request e o cartão mostra "Cancelamento em análise")
  C2 aluno, excluir conta (destrutiva; Confirmar faz POST /api/student/me/delete e leva a /login?conta=excluida)
  C3 Gestão, desativar conta na aba Equipe (destrutiva; POST /api/admin/staff/<id>/deactivate; badge "Desativada")
  C4 Gestão, excluir turma na aba Cursos (destrutiva; DELETE /api/admin/classes/<id>; a linha some). Esta aba se
     atualiza sozinha a cada 30 s (X5, D87): GETs durante o Voltar/Esc são tolerados e só listados; qualquer outro
     método é violação
  C5 nenhum diálogo nativo do navegador (page.on("dialog")) em todo o teste
  K1 sem exceções de página nem erros 4xx/5xx de /api no console

Escolha do agente-testes (modo autônomo D40): "pedir cancelamento" não tem a cor destrutiva exigida (o pedido não é
uma exclusão e o reembolso ainda passa pelo financeiro); a cor é só informada. Excluir conta, desativar conta e excluir
turma são destrutivas.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds1_componentes_angular.py -s
"""

import hashlib
import json
import re
import secrets
import sqlite3
import sys
import time
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

from apoio_confirmacao import SEL_CONFIRMAR, SEL_JANELA, SEL_VOLTAR  # noqa: E402
from apoio_contraste import razao_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
LARGURAS = (1366, 390)
SENHA = "senha-aluno-ds1-2026"
VERMELHO = "rgb(180, 35, 24)"  # #b42318
BRANCO = "rgb(255, 255, 255)"
ALVO_MIN = 44.0
SEL_ABA = "ul.nav-tabs button.nav-link"
ABAS_GESTAO = ("Financeiro", "Alunos", "Cursos", "Cadastro de cursos", "Observabilidade de IA", "Auditoria", "Equipe")
SUBPAINEL_ALUNO = "Alunos > detalhe do aluno"
SUBPAINEL_CURSO = "Cursos > alunos do curso"
# Componentes das telas roteadas: a janela não pode estar dentro de nenhum deles ("um único componente na casca").
ROTEADOS = ("app-login", "app-cadastro", "app-termos", "app-definir-senha", "app-esqueci-senha", "app-redefinir-senha",
            "app-student-dashboard", "app-student-profile", "app-course-room", "app-course-catalog",
            "app-admin-dashboard")

PERGUNTA_CANCELAMENTO = "Pedir o cancelamento de {curso}? O reembolso é analisado pelo financeiro."
PERGUNTA_EXCLUIR_CONTA = "Excluir sua conta? Essa ação não pode ser desfeita."
PERGUNTA_DESATIVAR = 'Desativar a conta de "{nome}"?'
PERGUNTA_EXCLUIR_TURMA = 'Excluir a turma "{nome}"?'


class Falha(Exception):
    pass


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


# ------------------------------------------------------------------------------------------------- medição (JS)
_JS_BASE = r"""
const DS1_APOIO = true;
function visivel(el) {
  if (el.closest('[aria-hidden="true"]')) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility !== 'visible' || cs.display === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  if (el.getClientRects().length === 0) return false;
  return true;
}
function desc(el) {
  let s = el.tagName.toLowerCase();
  const tid = el.getAttribute('data-testid');
  if (tid) s += `[data-testid=${tid}]`;
  else if (el.id) s += '#' + el.id;
  else if (el.getAttribute('name')) s += `[name=${el.getAttribute('name')}]`;
  else if (el.classList.length) s += '.' + Array.from(el.classList).slice(0, 3).join('.');
  if (el.tagName === 'INPUT') s += `(type=${el.type})`;
  return s;
}
function textoCurto(el) {
  return (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '')
    .replace(/\s+/g, ' ').trim().slice(0, 40);
}
"""

_JS_MEDIR = _JS_BASE + r"""
function semNome(el) {
  const ids = (el.getAttribute('aria-labelledby') || '').trim();
  if (ids) {
    const partes = ids.split(/\s+/).map(id => document.getElementById(id));
    if (partes.every(p => p) && partes.map(p => p.textContent).join(' ').trim()) return null;
  }
  if ((el.getAttribute('aria-label') || '').trim()) return null;
  for (const label of (el.labels || [])) {
    if ((label.textContent || '').trim()) return null;
  }
  if (ids) return `aria-labelledby="${ids}" inválido`;
  return 'sem label[for], label envolvendo, aria-label ou aria-labelledby';
}

() => {
  const h1s = Array.from(document.querySelectorAll('h1'));
  const h1 = h1s.filter(visivel).map(e => (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60));

  const campos = [];
  let totalCampos = 0;
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (el.tagName === 'INPUT' && (el.type || '').toLowerCase() === 'hidden') continue;
    if (!visivel(el)) continue;
    totalCampos++;
    const motivo = semNome(el);
    if (motivo) campos.push(`${desc(el)}${el.placeholder ? ` placeholder='${el.placeholder}'` : ''}: ${motivo}`);
  }

  const alvos = [];
  let totalAlvos = 0;
  const vistos = new Set();
  for (const el of document.querySelectorAll('button, .btn, a.btn, .nav-link, [data-testid="app-nav"] a')) {
    if (vistos.has(el)) continue;
    vistos.add(el);
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) continue;
    if (!visivel(el)) continue;
    totalAlvos++;
    const h = el.getBoundingClientRect().height;
    if (h + 0.01 < 44) alvos.push(`${desc(el)} '${textoCurto(el)}' ${Math.round(h * 10) / 10}px`);
  }

  const limite = window.innerWidth;
  const raiz = document.documentElement;
  const clipaRaiz = ['hidden', 'clip'].includes(getComputedStyle(raiz).overflowX)
                 || ['hidden', 'clip'].includes(getComputedStyle(document.body).overflowX);
  const fora = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (fora.length >= 8) break;
    if (!visivel(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right <= limite + 0.5 && r.left >= -0.5) continue;
    let contido = false;
    for (let a = el.parentElement; a && a !== document.body && a !== raiz; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if (['auto', 'scroll', 'hidden', 'clip'].includes(ox)) { contido = true; break; }
    }
    if (contido) continue;
    const pai = el.parentElement;
    if (pai && pai !== document.body && visivel(pai)) {
      const rp = pai.getBoundingClientRect();
      if (rp.right > limite + 0.5 || rp.left < -0.5) continue;
    }
    fora.push(`${desc(el)} '${textoCurto(el)}' de ${Math.round(r.left)} a ${Math.round(r.right)}px`);
  }

  const tabelas = [];
  for (const t of document.querySelectorAll('table')) {
    if (!visivel(t)) continue;
    const card = t.closest('.card');
    const titulo = card ? (card.querySelector('h5, h6, .card-title') || {}).innerText : '';
    const linhas = Array.from(t.querySelectorAll('tbody tr')).filter(tr => {
      const tds = tr.querySelectorAll('td');
      return !(tds.length === 1 && tds[0].hasAttribute('colspan'));
    }).length;
    tabelas.push({ titulo: (titulo || desc(t)).replace(/\s+/g, ' ').trim().slice(0, 50), linhas });
  }

  return { h1, h1Ocultos: h1s.length - h1.length, campos, totalCampos, alvos, totalAlvos,
           scrollWidth: raiz.scrollWidth, clientWidth: raiz.clientWidth, limite, clipaRaiz, fora, tabelas };
}
"""

# Estrutura da janela aberta. Devolve a lista de violações (strings).
_JS_JANELA = _JS_BASE + r"""
(args) => {
  const v = [];
  const todas = document.querySelectorAll(args.sel);
  if (todas.length !== 1) v.push(`${todas.length} elementos [data-testid=confirmacao] no DOM (esperado 1, um componente só na casca)`);
  const raiz = Array.from(todas).find(visivel) || todas[0];
  if (!raiz) return { v: ['janela ausente'], texto: '' };
  for (let a = raiz.parentElement; a; a = a.parentElement) {
    if (args.roteados.includes(a.tagName.toLowerCase())) {
      v.push(`a janela está dentro de <${a.tagName.toLowerCase()}> (tela roteada); deve ficar na casca`);
      break;
    }
  }
  if (raiz.getAttribute('role') !== 'alertdialog') v.push(`role=${JSON.stringify(raiz.getAttribute('role'))} (esperado "alertdialog")`);
  if (raiz.getAttribute('aria-modal') !== 'true') v.push(`aria-modal=${JSON.stringify(raiz.getAttribute('aria-modal'))} (esperado "true")`);
  const norm = s => (s || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
  function referidos(attr) {
    const ids = (raiz.getAttribute(attr) || '').trim();
    if (!ids) { v.push(`sem ${attr}`); return null; }
    const els = ids.split(/\s+/).map(id => document.getElementById(id));
    if (els.some(e => !e)) { v.push(`${attr}="${ids}" aponta para id inexistente`); return null; }
    if (els.some(e => !raiz.contains(e))) v.push(`${attr}="${ids}" aponta para elemento fora da janela`);
    return norm(els.map(e => e.textContent).join(' '));
  }
  const titulo = referidos('aria-labelledby');
  if (titulo !== null && !titulo) v.push('o título (aria-labelledby) está vazio');
  const descricao = referidos('aria-describedby');
  const pergunta = norm(args.pergunta);
  if (descricao !== null && !descricao.includes(pergunta)) v.push(`o texto (aria-describedby) não contém a pergunta: ${JSON.stringify(descricao.slice(0, 120))}`);
  const texto = norm(raiz.innerText);
  if (!texto.includes(pergunta)) v.push(`o texto da janela não contém a pergunta ${JSON.stringify(pergunta)} (texto: ${JSON.stringify(texto.slice(0, 160))})`);

  // fundo escurecido: o canto da tela cai na camada da janela (não na barra, no rodapé ou na tela roteada) e é escuro
  const W = window.innerWidth, H = window.innerHeight;
  for (const [x, y] of [[4, 4], [W - 4, H - 4]]) {
    const hit = document.elementFromPoint(x, y);
    if (!hit) { v.push(`nada no ponto (${x},${y}) com a janela aberta`); continue; }
    const conteudo = hit.closest('[data-testid="app-nav"], [data-testid="app-footer"], ' + args.roteados.join(', '));
    if (conteudo) { v.push(`sem fundo escurecido: o ponto (${x},${y}) cai em ${desc(conteudo)} (${desc(hit)})`); continue; }
    let cor = null;
    if (hit.tagName === 'DIALOG') cor = getComputedStyle(hit, '::backdrop').backgroundColor;
    for (let a = hit; a && !cor; a = a.parentElement) {
      const c = getComputedStyle(a).backgroundColor;
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (m) { const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat); if ((p[3] ?? 1) > 0) cor = c; }
      if (a === document.body) break;
    }
    const m = (cor || '').match(/rgba?\(([^)]+)\)/);
    if (!m) { v.push(`sem fundo escurecido no ponto (${x},${y}) (${desc(hit)}, cor ${cor})`); continue; }
    const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat);
    const a = p[3] ?? 1;
    const sobreBranco = p.slice(0, 3).map(c => c * a + 255 * (1 - a));
    const f = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    const lum = 0.2126 * f(sobreBranco[0]) + 0.7152 * f(sobreBranco[1]) + 0.0722 * f(sobreBranco[2]);
    if (lum > 0.6) v.push(`fundo por trás não escurece a tela no ponto (${x},${y}): ${cor} (${desc(hit)})`);
  }
  return { v, texto };
}
"""

_JS_FOCO_DENTRO = "(sel) => { const a = document.activeElement; return !!(a && a.closest(sel)); }"
_JS_FOCO_DESC = _JS_BASE + "() => { const a = document.activeElement; return a ? desc(a) + ` '${textoCurto(a)}'` : 'nenhum'; }"


# ------------------------------------------------------------------------------------------------- janela
def _novas(reqs, desde, so_nao_get=False):
    itens = reqs[desde:]
    return [r for r in itens if not (so_nao_get and r[0] == "GET")]

def _esperar_janela(page, timeout=5000):
    try:
        page.locator(SEL_JANELA).first.wait_for(state="visible", timeout=timeout)
        return True
    except sync_api.TimeoutError:
        return False

def _esperar_fechar(page, timeout=3000):
    try:
        page.locator(SEL_JANELA).first.wait_for(state="hidden", timeout=timeout)
        return True
    except sync_api.TimeoutError:
        return False

def _foco_na_origem(page):
    try:
        page.wait_for_function(
            "() => document.activeElement && document.activeElement.getAttribute('data-ds1-origem') === '1'",
            timeout=1500)
        return True
    except sync_api.TimeoutError:
        return False

def verificar_janela(page, reqs, nativos, preparar, pergunta, destrutiva, metodo, caminho_re, depois,
                     tolerar_get=False):
    """Mecanismo completo da janela de confirmação numa ação. Devolve a lista de violações (vazia = ok).

    `reqs`: lista viva de (método, caminho) das requisições /api/ da página; `nativos`: lista viva dos diálogos
    nativos (o teste os recusa); `preparar()`: deixa a tela pronta e devolve o Locator do botão que abre a janela;
    `depois()`: confere o fluxo depois de confirmar e devolve uma mensagem de erro ou None."""
    v = []
    nativos_antes = len(nativos)
    origem = preparar()
    origem.evaluate("e => e.setAttribute('data-ds1-origem', '1')")

    def abrir(etapa):
        antes = len(reqs)
        n_antes = len(nativos)
        origem.click(timeout=TIMEOUT)
        if not _esperar_janela(page):
            extra = f"; o navegador abriu o diálogo nativo: {nativos[n_antes:]}" if len(nativos) > n_antes else ""
            v.append(f"{etapa}: a janela [data-testid=confirmacao] não abriu{extra}")
            return False
        abriu = _novas(reqs, antes, so_nao_get=tolerar_get)
        if abriu:
            v.append(f"{etapa}: abrir a janela já fez requisição: {abriu}")
        return True

    # 1. abrir e conferir a estrutura
    if not abrir("abrir"):
        return v
    estrutura = page.evaluate(_JS_JANELA, {"sel": SEL_JANELA, "pergunta": pergunta, "roteados": list(ROTEADOS)})
    v.extend(estrutura["v"])
    janela = page.locator(SEL_JANELA).first
    voltar = janela.locator(SEL_VOLTAR)
    confirmar = janela.locator(SEL_CONFIRMAR)
    if voltar.count() != 1:
        v.append(f"{voltar.count()} [data-testid=confirmacao-voltar] dentro da janela (esperado 1)")
    elif _normalizar(voltar.first.inner_text()) != "Voltar":
        v.append(f"botão voltar com o texto {voltar.first.inner_text()!r} (esperado 'Voltar')")
    if confirmar.count() != 1:
        v.append(f"{confirmar.count()} [data-testid=confirmacao-confirmar] dentro da janela (esperado 1)")
    else:
        rot = _normalizar(confirmar.first.inner_text())
        if not rot or rot.lower() in ("voltar", "ok"):
            v.append(f"botão confirmar com rótulo {rot!r} (esperado o rótulo da ação)")
        page.mouse.move(1, 1)
        fundo = confirmar.first.evaluate("e => getComputedStyle(e).backgroundColor")
        cor = confirmar.first.evaluate("e => getComputedStyle(e).color")
        if destrutiva:
            if fundo != VERMELHO:
                v.append(f"ação destrutiva: fundo do confirmar {fundo} (esperado #b42318 = {VERMELHO})")
            if cor != BRANCO:
                v.append(f"ação destrutiva: texto do confirmar {cor} (esperado branco)")
        else:
            print(f"   [info] confirmar ({rot!r}) com fundo {fundo} e texto {cor}")
        try:
            if razao_contraste(cor, fundo) < 4.5:
                v.append(f"confirmar: contraste {razao_contraste(cor, fundo):.2f}:1 ({cor} sobre {fundo}) < 4,5:1")
        except ValueError:
            pass
    for nome, botao in (("voltar", voltar), ("confirmar", confirmar)):
        if botao.count() == 1:
            altura = botao.first.evaluate("e => e.getBoundingClientRect().height")
            if altura + 0.01 < ALVO_MIN:
                v.append(f"botão {nome} com {altura:.1f}px de altura (mínimo 44)")

    # 2. foco inicial no Voltar
    try:
        page.wait_for_function(
            f"() => document.activeElement && document.activeElement.matches('{SEL_VOLTAR}')", timeout=1500)
    except sync_api.TimeoutError:
        v.append(f"ao abrir, o foco está em {page.evaluate(_JS_FOCO_DESC)} (esperado no Voltar)")

    # 3. Tab e Shift+Tab presos na janela
    for tecla in ("Tab", "Shift+Tab"):
        for i in range(1, 7):
            page.keyboard.press(tecla)
            if not page.evaluate(_JS_FOCO_DENTRO, SEL_JANELA):
                v.append(f"{tecla} nº {i} tirou o foco da janela (foco em {page.evaluate(_JS_FOCO_DESC)})")
                break

    # 4. Voltar: fecha, nenhuma requisição, foco volta ao botão de origem
    if voltar.count() == 1:
        antes = len(reqs)
        voltar.first.click(timeout=TIMEOUT)
        if not _esperar_fechar(page):
            v.append("Voltar não fechou a janela")
            page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        feitas = _novas(reqs, antes, so_nao_get=tolerar_get)
        if feitas:
            v.append(f"Voltar fez requisição: {feitas}")
        elif tolerar_get and _novas(reqs, antes):
            print(f"   [info] GETs da atualização automática durante o Voltar: {_novas(reqs, antes)}")
        if not _foco_na_origem(page):
            v.append(f"depois do Voltar o foco está em {page.evaluate(_JS_FOCO_DESC)} (esperado no botão de origem)")

    # 5. Esc: fecha como Voltar
    if abrir("reabrir para o Esc"):
        antes = len(reqs)
        page.keyboard.press("Escape")
        if not _esperar_fechar(page):
            v.append("Esc não fechou a janela")
            if voltar.count() == 1:
                voltar.first.click(timeout=TIMEOUT)
                _esperar_fechar(page)
        page.wait_for_timeout(800)
        feitas = _novas(reqs, antes, so_nao_get=tolerar_get)
        if feitas:
            v.append(f"Esc fez requisição: {feitas}")
        if not _foco_na_origem(page):
            v.append(f"depois do Esc o foco está em {page.evaluate(_JS_FOCO_DESC)} (esperado no botão de origem)")

    # 6. Confirmar: a mesma requisição de antes, uma vez, e o fluxo segue como hoje
    if confirmar.count() == 1 and abrir("reabrir para confirmar"):
        antes = len(reqs)
        confirmar.first.click(timeout=TIMEOUT)
        limite = time.time() + TIMEOUT / 1000
        alvo = []
        while time.time() < limite:
            alvo = [r for r in _novas(reqs, antes) if r[0] == metodo and caminho_re.fullmatch(r[1])]
            if alvo:
                break
            page.wait_for_timeout(100)
        if not alvo:
            v.append(f"Confirmar não fez {metodo} {caminho_re.pattern} (requisições: {_novas(reqs, antes)})")
        else:
            page.wait_for_timeout(600)
            repetidas = [r for r in _novas(reqs, antes) if r[0] == metodo and caminho_re.fullmatch(r[1])]
            if len(repetidas) != 1:
                v.append(f"Confirmar fez {len(repetidas)} vezes {metodo} {caminho_re.pattern} (esperado 1)")
            if page.locator(SEL_JANELA).count() and page.locator(SEL_JANELA).first.is_visible():
                v.append("a janela continuou aberta depois de confirmar")
            erro_depois = depois()
            if erro_depois:
                v.append(f"depois de confirmar: {erro_depois}")
    if len(nativos) > nativos_antes:
        v.append(f"o navegador abriu diálogo nativo: {nativos[nativos_antes:]}")
    return v


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
        return {"id": cid, "nome": nome}

    principal = curso(f"ds1-{suf}", f"Excel Profissional para Gestão Financeira {suf}", 480.0,
                      [{"title": "Apostila de fórmulas", "url": f"https://materiais.test/ds1-{suf}/apostila.pdf",
                        "type": "pdf"}])
    segundo = curso(f"ds1b-{suf}", f"Power BI Essencial {suf}", 290.0, [])

    def turma(nome, curso_id=None, **extra):
        corpo_turma = {"course_id": curso_id or principal["id"], "name": nome, **extra}
        st, corpo = _api(api, "POST", "/api/admin/classes", corpo_turma, token)
        if st != 200:
            raise RuntimeError(f"seed: turma {nome} HTTP {st}")
        return {"id": corpo["class"]["id"], "nome": nome}

    hoje = _agora().date()
    noturna = turma(f"Turma Noturna {suf}", starts_on=str(hoje + timedelta(days=10)),
                    ends_on=str(hoje + timedelta(days=40)), schedule="Seg e Qua, 19h às 22h", capacity=30)
    excluir = turma(f"Turma Sábado {suf}", capacity=20)
    turma(f"Turma Intensiva de Férias {suf}", curso_id=segundo["id"], starts_on=str(hoje + timedelta(days=5)),
          schedule="Seg a Sex, 8h às 12h", capacity=25)

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
        email = email or f"e2e.ds1.{rotulo}.{uuid.uuid4().hex[:6]}@teste.com"
        uid = Database.add_user(email, nome, senha_hash if com_senha else None, role="student")
        if uid is None:
            raise RuntimeError(f"seed: não foi possível criar {email}")
        return {"uid": uid, "email": email, "nome": nome}

    def matricula(a, c, preco, status="active", turma_id=None, ha=timedelta(days=1)):
        eid = Database.create_enrollment(a["uid"], c["id"], f"{c['id']}:ds1:{uuid.uuid4().hex}")
        pid = Database.record_payment(eid, preco, "mercado_pago")
        quando = _ts(ha)
        if status == "active":
            sql("UPDATE payments SET status = 'approved', transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
                (f"mp-ds1-{uuid.uuid4().hex[:10]}", quando, quando, pid))
        else:
            sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (quando, quando, pid))
        sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, quando, eid))
        if turma_id is not None:
            sql("UPDATE enrollments SET class_id = ? WHERE id = ?", (turma_id, eid))
        return {"eid": eid, "pid": pid}

    # Dados de tamanho realista (nome e e-mail longos), para a medida de 390 px não depender de dado curto.
    tela = aluno("Marina Fernanda Albuquerque dos Santos", "tela",
                 email=f"marina.fernanda.albuquerque.{suf}@empresa-exemplo.com.br")
    tela["mat"] = matricula(tela, principal, 480.0, turma_id=noturna["id"])
    cancela = aluno("Caio Cancela", "cancela")
    cancela["mat"] = matricula(cancela, principal, 480.0)
    exclui = aluno("Elisa Exclui", "exclui")
    pendente = aluno("Otávio Pendente", "pendente", com_senha=False)
    matricula(pendente, segundo, 290.0, status="pending", ha=timedelta(days=2))
    pedido = aluno("Rita Pedido", "pedido")
    pedido["mat"] = matricula(pedido, principal, 480.0)
    sql("""INSERT INTO cancellation_requests (enrollment_id, payment_id, user_id, reason, status, requested_at)
           VALUES (?, ?, ?, ?, 'open', ?)""",
        (pedido["mat"]["eid"], pedido["mat"]["pid"], pedido["uid"],
         "Mudei de cidade por causa do trabalho e não consigo acompanhar as aulas no horário da turma",
         _ts(timedelta(hours=3))))
    # Observabilidade de IA: um tópico não compreendido do chat anônimo (tabela de tópicos da aba).
    sql("""INSERT INTO ai_interactions (created_at, channel, session_hash, outcome, topic)
           VALUES (?, 'anonymous', ?, 'unresolved', ?)""", (_ts(timedelta(hours=1)), "ds1" + suf, "como emitir boleto"))

    # Equipe: uma pessoa convidada para ser desativada no C3.
    email_equipe = f"equipe.ds1.{suf}@teste.com"
    st, corpo = _api(api, "POST", "/api/admin/staff", {"email": email_equipe, "name": f"Pessoa Equipe {suf}",
                                                       "role": "support"}, token)
    if st != 200:
        raise RuntimeError(f"seed: convite de equipe HTTP {st}")
    equipe = {"id": corpo["staff"]["id"], "email": email_equipe, "nome": f"Pessoa Equipe {suf}"}

    # Links de senha válidos para as telas /definir-senha e /redefinir-senha (só o hash vai ao banco).
    def token_senha(uid, finalidade, validade):
        claro = secrets.token_urlsafe(32)
        Database.insert_password_setup_token(uid, hashlib.sha256(claro.encode()).hexdigest(),
                                             (_agora() + validade).isoformat(sep=" ", timespec="seconds"), finalidade)
        return claro

    return {
        "principal": principal, "segundo": segundo, "noturna": noturna, "excluir": excluir,
        "tela": tela, "cancela": cancela, "exclui": exclui, "pendente": pendente, "pedido": pedido, "equipe": equipe,
        "token_setup": token_senha(pendente["uid"], "setup", timedelta(hours=24)),
        "token_reset": token_senha(tela["uid"], "reset", timedelta(minutes=50)),
    }


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
    with ambiente_isolado("ds1") as ambiente:
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
# Valida o próprio verificador numa página sintética (passa no red): uma janela correta não gera violação; uma janela
# com defeitos gera exatamente as violações esperadas; o confirm() nativo é apontado; a medição de h1, rótulo, alvo e
# largura acerta os casos conhecidos.
_PERGUNTA_SINTETICA = "Excluir sua conta? Essa ação não pode ser desfeita."

_JANELA_SINTETICA = """<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; font-family: sans-serif; }
#camada { position: fixed; inset: 0; background: rgba(23, 33, 43, 0.6); display: none; align-items: center;
          justify-content: center; }
#camada.aberta { display: flex; }
.caixa { background: #fff; padding: 24px; max-width: 420px; }
.caixa button { min-height: 44px; padding: 0 16px; }
.perigo { background: #b42318; color: #fff; border: 0; }
.fraco { height: 30px !important; min-height: 0 !important; background: #0077a3; color: #fff; }
</style></head><body>
<nav data-testid="app-nav"><a href="#">Logo</a></nav>
<main><app-student-profile>
  <p>Perfil</p><button id="abrir" type="button">Excluir minha conta</button><button type="button">Outro</button>
  <p id="estado">nada</p>
</app-student-profile></main>
<footer data-testid="app-footer">Rodapé</footer>
<div id="camada">
  <div class="caixa" data-testid="confirmacao" role="alertdialog" aria-modal="true" aria-labelledby="ds1-t"
       aria-describedby="ds1-d">
    <h2 id="ds1-t">Excluir conta</h2>
    <p id="ds1-d">PERGUNTA</p>
    <button type="button" data-testid="confirmacao-voltar">Voltar</button>
    <button type="button" class="perigo" data-testid="confirmacao-confirmar">Excluir conta</button>
  </div>
</div>
<script>
const MODO = 'MODO_AQUI';
const camada = document.getElementById('camada');
const janela = camada.querySelector('[data-testid=confirmacao]');
const voltar = janela.querySelector('[data-testid=confirmacao-voltar]');
const confirmar = janela.querySelector('[data-testid=confirmacao-confirmar]');
let origem = null;
if (MODO === 'defeito') {
  janela.removeAttribute('role'); janela.removeAttribute('aria-describedby');
  camada.style.background = 'transparent'; camada.style.pointerEvents = 'none'; janela.style.pointerEvents = 'auto';
  confirmar.className = 'fraco';
}
function fechar() {
  camada.classList.remove('aberta');
  if (MODO !== 'defeito' && origem) origem.focus();
}
document.getElementById('abrir').addEventListener('click', ev => {
  if (MODO === 'nativo') { if (confirm('PERGUNTA')) fetch('/api/acao', { method: 'POST' }); return; }
  origem = ev.currentTarget;
  camada.classList.add('aberta');
  if (MODO !== 'defeito') voltar.focus();
});
voltar.addEventListener('click', () => { if (MODO === 'defeito') fetch('/api/registro', { method: 'POST' }); fechar(); });
confirmar.addEventListener('click', () => {
  fechar();
  fetch('/api/acao', { method: 'POST' }).then(() => { document.getElementById('estado').textContent = 'feito'; });
});
document.addEventListener('keydown', ev => {
  if (!camada.classList.contains('aberta') || MODO === 'defeito') return;
  if (ev.key === 'Escape') { ev.preventDefault(); fechar(); return; }
  if (ev.key === 'Tab') {
    const itens = [voltar, confirmar];
    const i = itens.indexOf(document.activeElement);
    ev.preventDefault();
    itens[(i + (ev.shiftKey ? itens.length - 1 : 1)) % itens.length].focus();
  }
});
</script></body></html>"""

_MEDIDA_SINTETICA = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<nav data-testid="app-nav"><a href="#" style="display:inline-block;height:52px">Logo</a></nav>
<h1>Título da tela</h1><h1 style="display:none">Oculto</h1>
<label for="a">Nome</label><input id="a">
<label>E-mail <input id="b" type="email"></label>
<input id="c" aria-label="Busca">
<span id="rot">Telefone</span><input id="d" aria-labelledby="rot">
<input id="e" placeholder="Só placeholder">
<input id="f" aria-labelledby="nao-existe">
<select id="g"><option>x</option></select>
<input type="hidden" name="h"><input id="i" style="display:none">
<button id="b31" style="height:31px">Baixo</button><button id="b44" style="height:44px">Alto</button>
<button style="display:none;height:10px">Invisível</button>
<p>Texto com <a href="#">link corrido</a>.</p>
<div style="overflow-x:auto;width:300px"><div style="width:800px">tabela larga com rolagem interna</div></div>
<div id="largo" style="width:520px;height:20px">bloco largo</div>
</body></html>"""


def _pagina_sintetica(browser, html, largura=1000):
    ctx = browser.new_context(viewport={"width": largura, "height": 800})
    page = ctx.new_page()
    reqs, nativos = [], []

    def servir(rota):
        caminho = urllib.parse.urlparse(rota.request.url).path
        if caminho.startswith("/api/"):
            rota.fulfill(status=200, content_type="application/json", body="{}")
        else:
            rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)

    page.route("http://ds1.test/**", servir)
    page.on("request", lambda r: reqs.append((r.method, urllib.parse.urlparse(r.url).path))
            if urllib.parse.urlparse(r.url).path.startswith("/api/") else None)

    def ao_dialogo(d):
        nativos.append(f"{d.type}: {d.message}")
        d.dismiss()

    page.on("dialog", ao_dialogo)
    page.goto("http://ds1.test/", wait_until="load")
    return ctx, page, reqs, nativos


def test_ds1_apoio_verificador(browser):
    contextos = []

    def janela(modo):
        html = _JANELA_SINTETICA.replace("PERGUNTA", _PERGUNTA_SINTETICA).replace("MODO_AQUI", modo)
        ctx, page, reqs, nativos = _pagina_sintetica(browser, html)
        contextos.append(ctx)
        v = verificar_janela(
            page, reqs, nativos, lambda: page.locator("#abrir"), _PERGUNTA_SINTETICA, True, "POST",
            re.compile(r"/api/acao"),
            lambda: None if page.locator("#estado").inner_text() == "feito" else "estado não mudou")
        return v

    def v1():
        v = janela("correto")
        if v:
            raise Falha(f"janela correta gerou violações: {v}")

    def v2():
        v = " | ".join(janela("defeito"))
        esperadas = ["role=null", "sem aria-describedby", "sem fundo escurecido", "ação destrutiva: fundo do confirmar",
                     "botão confirmar com 30.0px", "ao abrir, o foco está em", "Tab nº 1 tirou o foco",
                     "Voltar fez requisição", "depois do Voltar o foco está em", "Esc não fechou a janela"]
        faltam = [e for e in esperadas if e not in v]
        if faltam:
            raise Falha(f"violações não apontadas {faltam}; obtidas: {v}")

    def v3():
        v = " | ".join(janela("nativo"))
        if "não abriu" not in v or "diálogo nativo" not in v:
            raise Falha(f"confirm() nativo não foi apontado: {v}")

    def v4():
        ctx, page, _, _ = _pagina_sintetica(browser, _MEDIDA_SINTETICA, largura=390)
        contextos.append(ctx)
        m = page.evaluate(_JS_MEDIR)
        erros = []
        if m["h1"] != ["Título da tela"] or m["h1Ocultos"] != 1:
            erros.append(f"h1 {m['h1']} / ocultos {m['h1Ocultos']}")
        sem_nome = " | ".join(m["campos"])
        for ok in ("input#a", "input#b", "input#c", "input#d", "[name=h]", "input#i"):
            if ok in sem_nome:
                erros.append(f"{ok} apontado sem nome")
        for ruim in ("input#e", "input#f", "select#g"):
            if ruim not in sem_nome:
                erros.append(f"{ruim} não apontado")
        alvos = " | ".join(m["alvos"])
        if "button#b31" not in alvos or "button#b44" in alvos or "Invisível" in alvos or "link corrido" in alvos:
            erros.append(f"alvos {m['alvos']}")
        fora = " | ".join(m["fora"])
        if m["scrollWidth"] <= 390 or "div#largo" not in fora or "rolagem interna" in fora:
            erros.append(f"largura {m['scrollWidth']} / fora {m['fora']}")
        page.evaluate("() => { document.documentElement.style.overflowX = 'hidden'; }")
        m2 = page.evaluate(_JS_MEDIR)
        if not m2["clipaRaiz"] or "div#largo" not in " | ".join(m2["fora"]):
            erros.append(f"overflow-x hidden no html não detectado: {m2['clipaRaiz']} {m2['fora']}")
        if erros:
            raise Falha("; ".join(erros))

    try:
        _rodar([
            ("V1", "janela correta: nenhuma violação", v1),
            ("V2", "janela com defeitos: cada defeito apontado", v2),
            ("V3", "confirm() nativo: apontado", v3),
            ("V4", "medição de h1, rótulo, alvo e largura", v4),
        ])
    finally:
        for ctx in contextos:
            ctx.close()


# ------------------------------------------------------------------------------------------------- teste
def test_ds1_componentes(browser, spa):
    contextos, erros, nativos = [], [], []
    requisicoes = {}  # id(page) -> [(método, caminho)] de /api/
    seed = {}
    try:
        seed.update(semear(spa))
    except Exception as erro:  # o cenário P1 mostra a falha do seed
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
            dialogo.dismiss()  # recusado: nada é executado (como Voltar)

        def ao_pedido(req):
            caminho = urllib.parse.urlparse(req.url).path
            if caminho.startswith("/api/"):
                lista.append((req.method, caminho))

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        page.on("dialog", ao_dialogo)
        page.on("request", ao_pedido)
        return page

    def entrar(page, email, senha, destino):
        page.goto(spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /{destino} (URL {page.url})")
        page.wait_for_load_state("networkidle")

    def clicar_aba(page, nome):
        aba = page.locator(SEL_ABA, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$"))
        try:
            aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"a aba '{nome}' não aparece para a Gestão")
        aba.first.click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(700)

    # --- coleta das medidas ------------------------------------------------------------------------------
    medidas = {}  # (grupo, tela, largura) -> dict do _JS_MEDIR ou {"erro": ...}

    def medir(grupo, tela, largura, page):
        try:
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)
            medidas[(grupo, tela, largura)] = page.evaluate(_JS_MEDIR)
        except Exception as erro:
            medidas[(grupo, tela, largura)] = {"erro": f"{type(erro).__name__}: {str(erro).splitlines()[0][:140]}"}

    def falha_de_tela(grupo, tela, largura, erro):
        medidas[(grupo, tela, largura)] = {"erro": str(erro).splitlines()[0][:160]}

    def coletar():
        if "erro" in seed:
            return
        anonimas = [
            ("/login", "/login", "main .card"),
            ("/cadastro", "/cadastro", "main .card"),
            ("/esqueci-senha", "/esqueci-senha", "main .card"),
            ("/definir-senha", f"/definir-senha?token={seed['token_setup']}", "main form input[type=password]"),
            ("/redefinir-senha", f"/redefinir-senha?token={seed['token_reset']}", '[data-testid="redefinir-senha"]'),
            ("/termos", "/termos", '[data-testid="termos-texto"]'),
            ("/privacidade", "/privacidade", '[data-testid="termos-texto"]'),
        ]
        aluno = [
            ("/student", "/student", '[data-testid="secao-cursos"]'),
            ("/student/perfil", "/student/perfil", '[data-testid="perfil-excluir"]'),
            ("/student/curso/:id", f"/student/curso/{seed['tela']['mat']['eid']}", '[data-testid="sala-curso"]'),
            ("/catalogo", "/catalogo", '[data-testid="catalogo-card"]'),
        ]
        for largura in LARGURAS:
            page = nova(largura)
            for tela, rota, marcador in anonimas:
                try:
                    page.goto(spa["base"] + rota, wait_until="networkidle")
                    page.locator(marcador).first.wait_for(state="visible", timeout=TIMEOUT)
                except Exception as erro:
                    falha_de_tela("anon", tela, largura, f"{rota} não carregou ({marcador}): {erro}")
                    continue
                medir("anon", tela, largura, page)

            page = nova(largura)
            try:
                entrar(page, seed["tela"]["email"], SENHA, "student")
            except Exception as erro:
                for tela, _, _ in aluno:
                    falha_de_tela("aluno", tela, largura, erro)
            else:
                for tela, rota, marcador in aluno:
                    try:
                        page.goto(spa["base"] + rota, wait_until="networkidle")
                        page.locator(marcador).first.wait_for(state="visible", timeout=TIMEOUT)
                    except Exception as erro:
                        falha_de_tela("aluno", tela, largura, f"{rota} não carregou ({marcador}): {erro}")
                        continue
                    medir("aluno", tela, largura, page)

            page = nova(largura)
            try:
                entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
                page.locator(SEL_ABA).first.wait_for(state="visible", timeout=TIMEOUT)
            except Exception as erro:
                for aba in ABAS_GESTAO:
                    falha_de_tela("gestao", aba, largura, erro)
                continue
            for aba in ABAS_GESTAO:
                try:
                    clicar_aba(page, aba)
                    if aba == "Cursos":
                        escolha = page.locator('[data-testid="turma-new-course"]')
                        escolha.first.select_option(seed["principal"]["id"], timeout=TIMEOUT)
                        page.locator('[data-testid="enrollment-row"]').first.wait_for(state="visible", timeout=TIMEOUT)
                except Exception as erro:
                    falha_de_tela("gestao", aba, largura, f"aba {aba}: {erro}")
                    continue
                medir("gestao", aba, largura, page)
                # Os dois painéis que estouram hoje no celular (PLANO_DESIGN: 411 px) abrem dentro das abas.
                painel = None
                try:
                    if aba == "Alunos":
                        painel = SUBPAINEL_ALUNO
                        page.locator("app-students-dashboard button", has_text=seed["tela"]["nome"]).first.click(
                            timeout=TIMEOUT)
                        page.locator('[data-testid="aluno-detalhe-matricula"]').first.wait_for(state="visible",
                                                                                                 timeout=TIMEOUT)
                    elif aba == "Cursos":
                        painel = SUBPAINEL_CURSO
                        page.locator('[data-testid="curso-alunos-link"]', has_text=seed["principal"]["nome"]).first.click(
                            timeout=TIMEOUT)
                        page.locator('[data-testid="curso-aluno-row"]').first.wait_for(state="visible", timeout=TIMEOUT)
                except Exception as erro:
                    falha_de_tela("gestao", painel, largura, f"{painel}: {erro}")
                    continue
                if painel:
                    medir("gestao", painel, largura, page)

    coletar()

    def telas(grupo):
        return sorted({(t, w) for g, t, w in medidas if g == grupo}, key=lambda x: (x[0], -x[1]))

    def exigir_coleta(grupo):
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")
        if not telas(grupo):
            raise Falha(f"nenhuma tela do grupo {grupo} foi medida")

    def rotulo(grupo, tela):
        return f"/admin aba {tela}" if grupo == "gestao" else tela

    # --- P1 seed -----------------------------------------------------------------------------------------
    def p1():
        exigir_coleta("gestao")
        v = []
        for tela, largura in telas("gestao"):
            m = medidas[("gestao", tela, largura)]
            if largura != 1366 or tela not in ABAS_GESTAO:
                continue
            if "erro" in m:
                v.append(f"aba {tela}: não medida ({m['erro']})")
                continue
            if not m["tabelas"]:
                v.append(f"aba {tela}: nenhuma tabela visível")
            for t in m["tabelas"]:
                print(f"   [info] aba {tela}: tabela '{t['titulo']}' com {t['linhas']} linha(s)")
                if t["linhas"] < 1:
                    v.append(f"aba {tela}: tabela '{t['titulo']}' sem linha de dados")
        _exigir(v, "seed (tabelas vazias)")

    # --- H, R, T, X --------------------------------------------------------------------------------------
    def grupo_h(grupo):
        def cenario():
            exigir_coleta(grupo)
            v = []
            for tela, largura in telas(grupo):
                m = medidas[(grupo, tela, largura)]
                if "erro" in m:
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {m['erro']}")
                elif len(m["h1"]) != 1:
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {len(m['h1'])} h1 visíveis {m['h1']}"
                             + (f" (+{m['h1Ocultos']} oculto(s))" if m["h1Ocultos"] else ""))
            _exigir(v, "um h1 por tela")
        return cenario

    def novos_do_painel(grupo, tela, largura, chave):
        """Itens da medida; num subpainel, só os que não aparecem já na aba de base (evita repetir a lista)."""
        itens = medidas[(grupo, tela, largura)][chave]
        base = {SUBPAINEL_ALUNO: "Alunos", SUBPAINEL_CURSO: "Cursos"}.get(tela)
        if grupo != "gestao" or base is None:
            return itens
        ja = medidas.get((grupo, base, largura), {}).get(chave, [])
        return [i for i in itens if i not in ja]

    def grupo_r(grupo):
        def cenario():
            exigir_coleta(grupo)
            v = []
            for tela, largura in telas(grupo):
                m = medidas[(grupo, tela, largura)]
                if "erro" in m:
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {m['erro']}")
                    continue
                for campo in novos_do_painel(grupo, tela, largura, "campos"):
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {campo}")
            _exigir(v, "rótulo de campo")
        return cenario

    def grupo_t(grupo):
        def cenario():
            exigir_coleta(grupo)
            v = []
            for tela, largura in telas(grupo):
                m = medidas[(grupo, tela, largura)]
                if "erro" in m:
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {m['erro']}")
                    continue
                for alvo in novos_do_painel(grupo, tela, largura, "alvos"):
                    v.append(f"{rotulo(grupo, tela)} @{largura}px: {alvo}")
            _exigir(v, f"alvo de toque < {ALVO_MIN:.0f} px")
        return cenario

    def grupo_x(grupo):
        def cenario():
            exigir_coleta(grupo)
            v = []
            for tela, largura in telas(grupo):
                if largura != 390:
                    continue
                m = medidas[(grupo, tela, largura)]
                if "erro" in m:
                    v.append(f"{rotulo(grupo, tela)}: {m['erro']}")
                    continue
                fora = "; ".join(m["fora"]) or "nenhum elemento identificado"
                print(f"   [info] {rotulo(grupo, tela)} @390px: scrollWidth {m['scrollWidth']}, "
                      f"clientWidth {m['clientWidth']}, campos {m['totalCampos']}, alvos {m['totalAlvos']}")
                if m["scrollWidth"] > 390:
                    v.append(f"{rotulo(grupo, tela)}: scrollWidth {m['scrollWidth']}px (> 390). Passam da borda: {fora}")
                elif m["clipaRaiz"] and m["fora"]:
                    v.append(f"{rotulo(grupo, tela)}: estouro escondido por overflow-x hidden no html/body (conteúdo "
                             f"cortado). Passam da borda: {fora}")
            _exigir(v, "rolagem horizontal a 390 px")
        return cenario

    # --- C: janela de confirmação --------------------------------------------------------------------------
    def mecanismo(page, *args, **kwargs):
        return verificar_janela(page, requisicoes[id(page)], nativos, *args, **kwargs)

    def exigir_seed():
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")

    def c1():
        exigir_seed()
        page = nova(1366)
        entrar(page, seed["cancela"]["email"], SENHA, "student")
        nome = seed["principal"]["nome"]
        cartao = page.locator('[data-testid="curso-card"]').filter(has_text=nome).first

        def preparar():
            cartao.wait_for(state="visible", timeout=TIMEOUT)
            cartao.locator('[data-testid="curso-cancelar"]').click(timeout=TIMEOUT)
            cartao.locator('[data-testid="curso-cancelar-motivo"]').fill("Mudança de horário no trabalho")
            return cartao.locator('[data-testid="curso-cancelar-enviar"]')

        def depois():
            status = cartao.locator('[data-testid="curso-cancelamento-status"]')
            try:
                status.first.wait_for(state="visible", timeout=TIMEOUT)
            except sync_api.TimeoutError:
                return "o cartão não mostrou o status do pedido"
            if _normalizar(status.first.inner_text()) != "Cancelamento em análise":
                return f"status {status.first.inner_text()!r} (esperado 'Cancelamento em análise')"
            return None

        eid = seed["cancela"]["mat"]["eid"]
        v = mecanismo(page, preparar, PERGUNTA_CANCELAMENTO.format(curso=nome), False, "POST",
                      re.compile(rf"/api/student/enrollments/{eid}/cancel-request"), depois)
        _exigir(v, "janela de confirmação (aluno: pedir cancelamento)")

    def c2():
        exigir_seed()
        page = nova(1366)
        entrar(page, seed["exclui"]["email"], SENHA, "student")

        def preparar():
            page.goto(spa["base"] + "/student/perfil", wait_until="networkidle")
            page.locator('[data-testid="perfil-excluir-senha"]').fill(SENHA, timeout=TIMEOUT)
            return page.locator('[data-testid="perfil-excluir"]')

        def depois():
            try:
                page.wait_for_url("**/login?conta=excluida", timeout=TIMEOUT)
            except sync_api.TimeoutError:
                return f"não levou a /login?conta=excluida (URL {page.url})"
            return None

        v = mecanismo(page, preparar, PERGUNTA_EXCLUIR_CONTA, True, "POST", re.compile(r"/api/student/me/delete"),
                      depois)
        _exigir(v, "janela de confirmação (aluno: excluir conta)")

    def c3():
        exigir_seed()
        page = nova(1366)
        entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
        equipe = seed["equipe"]
        linha = page.locator('[data-testid="equipe-row"]').filter(has_text=equipe["email"]).first

        def preparar():
            clicar_aba(page, "Equipe")
            linha.wait_for(state="visible", timeout=TIMEOUT)
            return linha.locator('[data-testid="equipe-desativar"]')

        def depois():
            try:
                linha.locator('[data-testid="equipe-desativada"]').first.wait_for(state="visible", timeout=TIMEOUT)
            except sync_api.TimeoutError:
                return "a linha não mostrou o badge Desativada"
            return None

        v = mecanismo(page, preparar, PERGUNTA_DESATIVAR.format(nome=equipe["nome"]), True, "POST",
                      re.compile(rf"/api/admin/staff/{equipe['id']}/deactivate"), depois)
        _exigir(v, "janela de confirmação (Gestão: desativar conta da equipe)")

    def c4():
        exigir_seed()
        page = nova(1366)
        entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
        turma = seed["excluir"]
        linhas = page.locator('[data-testid="turma-row"]').filter(has_text=turma["nome"])

        def preparar():
            clicar_aba(page, "Cursos")
            linhas.first.wait_for(state="visible", timeout=TIMEOUT)
            return linhas.first.locator('[data-testid="turma-excluir"]')

        def depois():
            try:
                linhas.first.wait_for(state="detached", timeout=TIMEOUT)
            except sync_api.TimeoutError:
                return "a linha da turma excluída continua na tela"
            return None

        v = mecanismo(page, preparar, PERGUNTA_EXCLUIR_TURMA.format(nome=turma["nome"]), True, "DELETE",
                      re.compile(rf"/api/admin/classes/{turma['id']}"), depois, tolerar_get=True)
        _exigir(v, "janela de confirmação (Gestão: excluir turma)")

    def c5():
        _exigir(list(nativos), "diálogo nativo do navegador")

    def k1():
        _exigir(list(erros), "erro de console ou exceção de página")

    try:
        _rodar([
            ("P1", "seed: cada tabela da Gestão com ao menos uma linha", p1),
            ("H1", "um h1 por tela (anônimas)", grupo_h("anon")),
            ("H2", "um h1 por tela (aluno)", grupo_h("aluno")),
            ("H3", "um h1 por aba (Gestão)", grupo_h("gestao")),
            ("R1", "rótulo em todo campo (anônimas)", grupo_r("anon")),
            ("R2", "rótulo em todo campo (aluno)", grupo_r("aluno")),
            ("R3", "rótulo em todo campo (Gestão)", grupo_r("gestao")),
            ("T1", "alvos >= 44 px (anônimas)", grupo_t("anon")),
            ("T2", "alvos >= 44 px (aluno)", grupo_t("aluno")),
            ("T3", "alvos >= 44 px (Gestão)", grupo_t("gestao")),
            ("X1", "sem rolagem horizontal a 390 px (anônimas)", grupo_x("anon")),
            ("X2", "sem rolagem horizontal a 390 px (aluno)", grupo_x("aluno")),
            ("X3", "sem rolagem horizontal a 390 px (Gestão)", grupo_x("gestao")),
            ("C1", "janela do app: aluno pede cancelamento", c1),
            ("C2", "janela do app: aluno exclui a conta", c2),
            ("C3", "janela do app: Gestão desativa conta da equipe", c3),
            ("C4", "janela do app: Gestão exclui turma", c4),
            ("C5", "nenhum diálogo nativo do navegador", c5),
            ("K1", "sem erros de console", k1),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
