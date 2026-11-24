"""E2E da DS2b (D115/D118, docs/tdd/PLANO_DESIGN.md) - refazer visualmente a Área do aluno (/student). Só design.

Contexto: depois da DS2 (D118, conservadora) o PM disse "a página do aluno não mudou" e "o botão 'Comprar cursos' está laranja
estático" (pílula laranja no meio de pílulas brancas). Estes testes exigem a página redesenhada como o protótipo
Painel-aluno.dc.html. Nenhuma lógica, rota, API ou dado muda; data-testid, ids, classes e textos dos e2e antigos ficam.
Tudo é medido no estilo COMPUTADO e na geometria do Chromium, a 1366 e a 390 px.

Seed (harness isolado D58; reaproveita o seed da DS2):
  Marina (aluna da DS2):  matrícula ativa com 2 materiais e 1 concluído (progresso 1 de 2 = 50%) e matrícula pendente
  Rafael:                 matrícula ativa COM TURMA, 2 materiais, os dois concluídos (100%, certificado disponível) e
                          matrícula ativa SEM materiais (sem progresso)
  Bruno:                  conta sem matrícula (estado vazio)

Cenários (cada um lista TODAS as violações de todas as telas):
  P0 pré-condição do seed [passa no red]
  C1 CTA "Comprar cursos": fora da fileira de atalhos, à direita do h1 na faixa do cabeçalho, .btn-cta retangular (raio <= 10 px,
     altura >= 48 px), laranja #ff7a18 com texto #17212b, href /catalogo, texto exato
  C2 CTA no hover: fundo #e86a0c e texto legível (>= 4,5:1)
  C3 CTA no celular: largura toda abaixo da saudação
  C4 laranja só no CTA: nenhum outro elemento laranja na tela [passa no red; é a guarda]
  N1 atalhos de seção: 3 elementos (R3-4, D126: o "Assistente" saiu da barra e virou o botão flutuante), mesmos testids e textos,
     dentro de nav[aria-label], altura >= 44 px, sem formato de pílula
     (raio >= 12 px com borda ou fundo), sem o CTA entre eles
     [R3-3/D125: contêiner = ul.nav.nav-tabs.gt-abas; texto da aba atalho-cursos = "Meus cursos"]
  N2 atalhos: sublinhado ou indicador (border-bottom >= 2 px, sublinhado ou sombra) no hover
     [R3-3/D125, PM "igual à gestão": indicador li.gt-abas-indicador visível sob a aba ativa + retorno visual no hover da aba inativa]
  N3 atalhos mantêm a ação: Meu perfil leva a /student/perfil; Financeiro rola até a seção sem sair de /student [passa no red]
     [R3-3/D125: Financeiro seleciona a aba (aria-current), a seção fica à vista, sem sair de /student; scrollY > 0 não é mais exigido]
  H1 cabeçalho: h1 "Olá, <nome>!" direto sobre o fundo (sem .card nem moldura com borda ou sombra ao redor), rótulo "Área do aluno",
     subtítulo "Conectado como <email>", um único h1
  M1 "Meus cursos": cada curso-card com >= 90% da largura da seção e empilhados (a 1366 e a 390 px)
     [R3-3/D125, revogação do PM: só a 390 px; a 1366 px os cartões ficam em grade (<= 50% da seção, mesma linha)]
  M2 cartão em linha (1366): ícone de iniciais, nome, badge de status ao lado do nome, data/turma e barra na coluna à esquerda
     [R3-3/D125, revogação do PM: cartão em coluna; badge, data, turma e barra dentro do cartão e abaixo do nome]
  M3 ação "Entrar no curso": >= 44 px; 1366: à direita e à altura do nome; 390: largura toda abaixo do nome
     [R3-3/D125, revogação do PM: a 1366 px a ação fica abaixo do nome e dentro do cartão]
  M4 sem acesso (pendente): sem "Entrar no curso", mensagem existente no lugar da ação; curso sem materiais mantém o aviso
  P1 progresso: role=progressbar, aria-valuenow/min/max, aria-label "Progresso do curso"; texto "x de y concluídos" mantido;
     curso sem materiais não tem barra
  P2 barra ocupa a largura disponível do corpo do cartão e o "NN%" por extenso fica ao lado, na mesma linha
  P3 preenchimento em #0077a3 (ou #0096c7)
  B1 materiais, avaliação e cancelamento num bloco secundário do cartão: fundo #f7f9fb, divisória, sem o botão principal
  B2 avaliação (comentário, nota, Enviar) numa única linha a 1366 px, comentário cresce
     [R3-3/D125, revogação do PM: sem a linha única (cartões de 3 colunas); comentário >= 200 px, ordem de leitura, dentro do cartão]
  B3 "Baixar certificado" continua secundário (outline) e visível; materiais e checkboxes ficam no bloco
  F1 fluxos: avaliar, abrir/fechar cancelamento, baixar certificado; nenhum confirm()/dialog nativo
  R1 faixa de números: contêiner único, 3 itens, sem regressão (guarda da DS2) [passa no red]
  E1 conta vazia: link "Ver cursos" para /catalogo, azul e não laranja [passa no red]
  A1 contraste AA em todo texto visível   A2 piso de 14 px   G1 um h1   G3 alvos >= 44 px   G4 sem rolagem horizontal a 390 px
  K1 sem emojis, sem erros de console

R3-3 (D125, decisão do PM de 23/11/2026: "deixe em abas igual é na aba da gestão" e "cada curso em formato de cards"): este arquivo
foi ajustado pelo agente-testes (AGENTS.md 4.3). N1, N2 e N3 passam a medir a barra de abas (`ul.nav.nav-tabs.gt-abas`) no lugar
do `nav.aluno-atalhos`; M1, M2, M3 e B2 deixam de exigir o layout de linhas (um curso por linha, ícone-corpo-ação lado a lado,
avaliação numa linha) e passam a afirmar o cartão em grade; as demais ficam como estavam. Ver D125 em docs/tdd/decisoes_tdd.md.

Escolhas do agente-testes (modo autônomo D40), registradas no relatório:
  - "À altura do nome" = a faixa vertical do botão cruza a do nome (com folga de 12 px); não exige centralizar no cartão.
  - "Badge ao lado do nome" é exigido só a 1366 px (a 390 pode quebrar de linha).
  - Divisória do bloco secundário: border-top do bloco, border-bottom do irmão anterior ou um <hr> imediatamente antes.
  - Barra: largura >= 50% do cartão a 1366 e >= 55% a 390 px.
  - A cor do preenchimento é medida no `.progress-bar` (mantido: jornadas e D3 G6 leem essa classe).

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds2b_area_aluno_angular.py -s
"""

import re
import sys
import urllib.parse
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_contraste import descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402
from test_ds1_componentes_angular import _JS_MEDIR  # noqa: E402
from test_ds2_area_aluno_angular import (  # noqa: E402
    LARANJA, RESUMO, SENHA, TEXTO, VAZIO_CURSOS, _JS_COR, _JS_LINK_CATALOGO, _JS_RESUMO, _JS_UTIL, _agora, _api,
    _ts, semear as semear_ds2,
)

TIMEOUT = 8000
LARGURAS = (1366, 390)
HOVER_CTA = "rgb(232, 106, 12)"   # #e86a0c
FUNDO_BLOCO = "rgb(247, 249, 251)"  # #f7f9fb
PREENCHIMENTOS = ("rgb(0, 119, 163)", "rgb(0, 150, 199)")  # #0077a3 (ou #0096c7 só como preenchimento)


class Falha(Exception):
    pass


def _exigir(violacoes, resumo):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões) de {resumo}:\n" + "\n".join(f"- {v}" for v in violacoes))


# ------------------------------------------------------------------------------------------------- medidor (JS)
_JS_GEO = _JS_UTIL + r"""
(args) => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const q = s => document.querySelector(s);
  const out = {};
  const h1s = Array.from(document.querySelectorAll('h1')).filter(visivel);
  out.h1n = h1s.length;
  const h1 = h1s[0];
  const email = q('[data-testid="aluno-email"]');
  const cta = q('[data-testid="atalho-catalogo"]');
  const secao = q('[data-testid="secao-cursos"]');
  out.secao = secao ? R(secao) : null;
  if (h1) {
    const rg = document.createRange(); rg.selectNodeContents(h1);
    const rr = rg.getBoundingClientRect();
    out.h1 = { texto: norm(h1.innerText), rect: R(h1), texto_rect: { l: rr.left, r: rr.right, t: rr.top, b: rr.bottom } };
    // ancestrais do h1 até (sem incluir) o contêiner que também tem a seção de cursos
    const molduras = [];
    for (let a = h1.parentElement; a && secao && !a.contains(secao); a = a.parentElement) {
      const cs = getComputedStyle(a);
      const bordas = LADOS.filter(l => borda(a, l));
      const sombra = cs.boxShadow !== 'none';
      if (a.classList.contains('card') || bordas.length || sombra) {
        molduras.push(`${desc(a)} (bordas ${bordas.join('/') || 'nenhuma'}; sombra ${sombra ? 'sim' : 'não'}; card ${a.classList.contains('card')})`);
      }
    }
    out.molduras = molduras;
  }
  const tag = Array.from(document.querySelectorAll('.gt-tag')).find(e => visivel(e) && /Área do aluno/i.test(e.innerText));
  out.rotulo = !!tag;
  if (email) {
    out.email = { texto: norm(email.innerText), rect: R(email), pai: norm(email.parentElement.innerText) };
  }
  if (cta) {
    const cs = getComputedStyle(cta);
    out.cta = { rect: R(cta), tag: cta.tagName.toLowerCase(), texto: norm(cta.innerText), classes: Array.from(cta.classList),
                href: cta.getAttribute('href'), fundo: cs.backgroundColor, cor: cs.color,
                raio: parseFloat(cs.borderTopLeftRadius) || 0, noNav: !!cta.closest('nav') };
  }
  // atalhos de seção
  const ids = ['atalho-cursos', 'atalho-financeiro', 'atalho-perfil'];  // R3-4 (D126): sem 'atalho-assistente' (botão flutuante)
  out.atalhos = ids.map(id => {
    const els = document.querySelectorAll(`[data-testid="${id}"]`);
    if (els.length !== 1) return { id, n: els.length };
    const el = els[0], cs = getComputedStyle(el), nav = el.closest('ul.nav.nav-tabs.gt-abas');  // R3-3 (D125): era nav[aria-label]
    const algumaBorda = LADOS.some(l => borda(el, l));
    return { id, n: 1, texto: norm(el.innerText), rect: R(el), tag: el.tagName.toLowerCase(), raio: parseFloat(cs.borderTopLeftRadius) || 0,
             algumaBorda, fundoAlfa: alfa(cs.backgroundColor), fundo: cs.backgroundColor, nav: nav ? 'abas' : null,
             navId: nav ? Array.from(document.querySelectorAll('ul.nav.nav-tabs.gt-abas')).indexOf(nav) : -1, visivel: visivel(el),
             contemCta: nav ? !!(cta && nav.contains(cta)) : false, href: el.getAttribute('href') };
  });
  // cartões de curso
  const cards = Array.from(document.querySelectorAll('[data-testid="curso-card"]'));
  out.cards = cards.map(card => {
    const c = {};
    const nome = card.querySelector('.curso-nome');
    c.nome = nome ? norm(nome.innerText) : '';
    c.rect = R(card);
    const pegar = (sel) => { const e = card.querySelector(sel); return e && visivel(e) ? R(e) : null; };
    c.nomeRect = nome ? R(nome) : null;
    if (nome) { const rg = document.createRange(); rg.selectNodeContents(nome); const rr = rg.getBoundingClientRect(); c.nomeTexto = { l: rr.left, r: rr.right, t: rr.top, b: rr.bottom }; }
    const icn = card.querySelector('.curso-icone');  // decorativo (aria-hidden): mede a geometria mesmo assim
    c.icone = icn && getComputedStyle(icn).display !== 'none' && icn.getBoundingClientRect().width > 1 ? R(icn) : null;
    const ic = card.querySelector('.curso-icone'); c.iconeTexto = ic ? norm(ic.textContent) : '';
    c.badge = pegar('.badge'); c.badgeTexto = (card.querySelector('.badge') || {}).innerText || '';
    c.data = pegar('[data-testid="curso-data"]');
    c.turma = pegar('[data-testid="curso-turma"]');
    const ent = card.querySelector('[data-testid="curso-entrar"]');
    c.entrar = ent && visivel(ent) ? { ...R(ent), texto: norm(ent.innerText), href: ent.getAttribute('href'), classes: Array.from(ent.classList) } : null;
    const av = card.querySelector('.curso-aviso');
    c.aviso = av && visivel(av) ? { texto: norm(av.innerText) } : null;
    c.semMateriais = /Este curso ainda não tem materiais/.test(card.innerText);
    const bars = Array.from(card.querySelectorAll('[role="progressbar"]'));
    c.barras = bars.length; c.barra = null; c.bloco = null; c.aval = null;
    if (bars[0]) {
      const b = bars[0];
      c.barra = { ...R(b), now: b.getAttribute('aria-valuenow'), min: b.getAttribute('aria-valuemin'), max: b.getAttribute('aria-valuemax'),
                  label: b.getAttribute('aria-label') };
    }
    const fill = card.querySelector('.progress-bar');
    c.fill = fill ? { fundo: getComputedStyle(fill).backgroundColor, estilo: fill.getAttribute('style') || '' } : null;
    const pct = Array.from(card.querySelectorAll('*')).filter(e => visivel(e) && /^\d{1,3}%$/.test(textoProprio(e)));
    c.pct = pct.map(e => ({ texto: textoProprio(e), ...R(e) }));
    const prog = card.querySelector('[data-testid="curso-progresso"]');
    c.progressoTexto = prog ? norm(prog.innerText) : null;
    // bloco secundário a partir do campo de comentário da avaliação
    const com = card.querySelector('[data-testid="curso-avaliacao-comentario"]');
    const nota = card.querySelector('[data-testid="curso-avaliacao-nota"]');
    const env = card.querySelector('[data-testid="curso-avaliacao-enviar"]');
    c.aval = com && nota && env ? { com: R(com), nota: R(nota), env: R(env) } : null;
    c.certificado = (() => { const e = card.querySelector('[data-testid="curso-certificado"]'); return e ? { visivel: visivel(e), classes: Array.from(e.classList) } : null; })();
    c.cancelar = card.querySelector('[data-testid="curso-cancelar"]') ? true : false;
    c.nCheck = card.querySelectorAll('[data-testid="material-concluido"]').length;
    c.nLinks = card.querySelectorAll('a[target="_blank"]').length;
    if (com) {
      let bloco = null;
      for (let a = com.parentElement; a && a !== card; a = a.parentElement) {
        if (getComputedStyle(a).backgroundColor === args.fundoBloco) { bloco = a; break; }
      }
      if (bloco) {
        const ant = bloco.previousElementSibling;
        const cs = getComputedStyle(bloco);
        const divisoria = borda(bloco, 'Top') || (ant && (borda(ant, 'Bottom') || ant.tagName === 'HR'));
        const dentro = e => !!e && bloco.contains(e);
        c.bloco = {
          fundo: cs.backgroundColor, divisoria: !!divisoria,
          temComentario: dentro(com), temNota: dentro(nota), temEnviar: dentro(env),
          temEntrar: dentro(ent), temNome: dentro(nome),
          temCheckboxes: card.querySelectorAll('[data-testid="material-concluido"]').length === bloco.querySelectorAll('[data-testid="material-concluido"]').length,
          temLinks: card.querySelectorAll('a[target="_blank"]').length === bloco.querySelectorAll('a[target="_blank"]').length,
          temCancelar: !card.querySelector('[data-testid="curso-cancelar"]') || dentro(card.querySelector('[data-testid="curso-cancelar"]')),
          rect: R(bloco),
        };
      } else c.bloco = null;
    }
    return c;
  });
  out.nDialog = 0;
  out.emoji = (document.body.innerText.match(/\p{Emoji_Presentation}/gu) || []);
  return out;
}
"""

_JS_ESTILO_ATALHO = r"""
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  const m = (cs.borderBottomColor.match(/[\d.]+/g) || []).map(Number);
  const alfaBorda = m.length > 3 ? m[3] : 1;
  const bw = parseFloat(cs.borderBottomWidth) || 0;
  return { sublinhado: cs.textDecorationLine.includes('underline'),
           bordaTodas: [cs.borderTopColor, cs.borderRightColor, cs.borderBottomColor, cs.borderLeftColor].join('|'),
           bordaInf: bw >= 2 && cs.borderBottomStyle !== 'none' && alfaBorda > 0,
           bordaInfTxt: `${cs.borderBottomWidth} ${cs.borderBottomStyle} ${cs.borderBottomColor}`,
           sombra: cs.boxShadow !== 'none', sombraTxt: cs.boxShadow, cor: cs.color, fundo: cs.backgroundColor };
}
"""

_JS_INDICADOR = r"""
() => {
  const el = document.querySelector('[data-testid="abas-indicador"]');
  if (!el) return null;
  const cs = getComputedStyle(el), r = el.getBoundingClientRect();
  const m = (cs.backgroundColor.match(/[\d.]+/g) || []).map(Number);
  return { h: r.height, w: r.width, fundo: cs.backgroundColor, alfa: m.length > 3 ? m[3] : 1 };
}
"""

# ------------------------------------------------------------------------------------------------- seed
def semear(amb):
    seed = semear_ds2(amb)  # Marina (ativa 1 de 2 + pendente), Bruno (vazio), cursos e uma turma no 3º curso
    api, db_path = amb["api"], amb["db_path"]
    st, corpo = _api(api, "POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if st != 200:
        raise RuntimeError(f"seed: login da Gestão HTTP {st}")
    gestao = corpo["access_token"]
    suf = uuid.uuid4().hex[:6]

    def curso(cid, nome, preco, materiais):
        dados = {"id": cid, "name": nome, "description": f"Descrição do {nome}", "price": preco, "duration_hours": 12,
                 "level": "Intermediario", "target_audience": "Profissionais", "objectives": ["Objetivo"],
                 "topics": ["Tópico"], "benefits": ["Benefício"], "faq": [{"question": "Pergunta", "answer": "Resposta"}],
                 "system_prompt": "Prompt", "materials": materiais}
        st_, _ = _api(api, "POST", "/api/admin/create-course", dados, gestao)
        if st_ != 200:
            raise RuntimeError(f"seed: create-course {cid} HTTP {st_}")
        return {"id": cid, "nome": nome, "materiais": materiais}

    turma_curso = curso(f"ds2bt-{suf}", f"Gestão de Projetos Ágeis {suf}", 520.0, [
        {"title": "Guia do Scrum", "url": f"https://materiais.test/ds2bt-{suf}/scrum.pdf", "type": "pdf"},
        {"title": "Modelos de backlog", "url": f"https://materiais.test/ds2bt-{suf}/backlog.pdf", "type": "pdf"}])
    vazio_curso = curso(f"ds2bv-{suf}", f"Introdução à Liderança {suf}", 150.0, [])
    hoje = _agora().date()
    st, corpo = _api(api, "POST", "/api/admin/classes",
                     {"course_id": turma_curso["id"], "name": f"Turma Manhã {suf}", "starts_on": str(hoje + timedelta(days=5)),
                      "ends_on": str(hoje + timedelta(days=35)), "schedule": "Ter e Qui, 8h às 10h", "capacity": 30}, gestao)
    if st != 200:
        raise RuntimeError(f"seed: turma HTTP {st}")
    turma_id = corpo["class"]["id"]

    import sqlite3  # noqa: PLC0415
    Database = abrir_banco(db_path)
    from core.security import get_password_hash  # noqa: PLC0415
    hash_ = get_password_hash(SENHA)

    def sql(comando, params=()):
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(comando, params)
            conn.commit()
        finally:
            conn.close()

    uid = Database.add_user(f"rafael.ds2b.{suf}@teste.com", "Rafael Almeida Nogueira", hash_, role="student")
    if uid is None:
        raise RuntimeError("seed: não foi possível criar o Rafael")
    rafael = {"uid": uid, "email": f"rafael.ds2b.{suf}@teste.com"}

    def matricula(c, preco):
        eid = Database.create_enrollment(uid, c["id"], f"{c['id']}:ds2b:{uuid.uuid4().hex}")
        pid = Database.record_payment(eid, preco, "mercado_pago")
        quando = _ts(timedelta(days=1))
        sql("UPDATE payments SET status = 'approved', transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
            (f"mp-ds2b-{uuid.uuid4().hex[:10]}", quando, quando, pid))
        sql("UPDATE enrollments SET status = 'active', enrolled_at = ? WHERE id = ?", (quando, eid))
        return eid

    e_turma = matricula(turma_curso, 520.0)
    matricula(vazio_curso, 150.0)
    st, _ = _api(api, "PUT", f"/api/admin/enrollments/{e_turma}/class", {"class_id": turma_id}, gestao)
    if st != 200:
        raise RuntimeError(f"seed: atribuir turma HTTP {st}")
    st, corpo = _api(api, "POST", "/api/token", formulario={"username": rafael["email"], "password": SENHA})
    if st != 200:
        raise RuntimeError(f"seed: login do Rafael HTTP {st}")
    for mat in turma_curso["materiais"]:
        st, _ = _api(api, "POST", f"/api/student/enrollments/{e_turma}/progress", {"url": mat["url"], "done": True},
                     corpo["access_token"])
        if st != 200:
            raise RuntimeError(f"seed: progresso do Rafael HTTP {st}")
    seed.update({"rafael": rafael, "turma_curso": turma_curso, "vazio_curso": vazio_curso})
    return seed


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
    with ambiente_isolado("ds2b") as ambiente:
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


def _r(d):
    return f"[{d['l']:.0f},{d['t']:.0f} -> {d['r']:.0f},{d['b']:.0f}] ({d['w']:.0f}x{d['h']:.0f})"


# ------------------------------------------------------------------------------------------------- teste
def test_ds2b_area_aluno(browser, spa):
    contextos, erros, dialogos = [], [], []
    seed = {}
    try:
        seed.update(semear(spa))
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova(largura):
        ctx = browser.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR", reduced_motion="reduce",
                                  accept_downloads=True)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and re.search(r"status of (\d{3})", msg.text) and "/api/" in (url + msg.text):
                erros.append(f"{msg.text[:100]} ({url})")

        def ao_dialogo(d):
            dialogos.append(f"{d.type}: {d.message[:80]}")
            d.dismiss()

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"[:160]))
        page.on("dialog", ao_dialogo)
        return page

    def entrar(page, email):
        page.goto(spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        page.wait_for_load_state("networkidle")

    medidas = {}  # (conta, largura) -> dict
    fluxos = {}

    def medir(conta, largura, page):
        try:
            page.wait_for_load_state("networkidle")
            page.locator('[data-testid="secao-cursos"]').wait_for(state="visible", timeout=TIMEOUT)
            page.mouse.move(1, 1)
            page.wait_for_timeout(400)
            m = page.evaluate(_JS_GEO, {"fundoBloco": FUNDO_BLOCO})
            m["contraste"] = varrer_contraste(page)
            m["fontes"] = fontes_abaixo_de(page, 14)
            m["laranja"] = page.evaluate(_JS_COR, {"cor": LARANJA, "fundo": True, "permitidos": ['[data-testid="atalho-catalogo"]']})
            m["ds1"] = page.evaluate(_JS_MEDIR)
            m["resumo"] = page.evaluate(_JS_RESUMO, {"ids": [list(p) for p in RESUMO], "texto": TEXTO})
            m["vazio"] = page.evaluate(_JS_LINK_CATALOGO, '[data-testid="secao-cursos"]')
            link = page.locator('[data-testid="secao-cursos"] a.btn', has_text="Ver cursos")
            m["ver_cursos"] = link.first.evaluate(
                "e => { const cs = getComputedStyle(e); return {cor: cs.color, fundo: cs.backgroundColor,"
                " cta: e.classList.contains('btn-cta'), href: e.getAttribute('href')}; }") if link.count() else None
            medidas[(conta, largura)] = m
        except Exception as erro:
            medidas[(conta, largura)] = {"erro": f"{type(erro).__name__}: {str(erro).splitlines()[0][:160]}"}

    def sonda_marina(page):
        """Interações a 1366 px: hover do CTA e dos atalhos; clique no atalho Financeiro; perfil."""
        f = {}
        try:
            cta = page.locator('[data-testid="atalho-catalogo"]')
            cta.hover()
            page.wait_for_timeout(450)
            f["cta_hover"] = cta.evaluate("e => { const cs = getComputedStyle(e); return {fundo: cs.backgroundColor, cor: cs.color}; }")
            page.mouse.move(1, 1)
            page.wait_for_timeout(200)
            # R3-3 (D125): a aba Cursos é a ativa; o retorno do hover mede-se na aba inativa (Financeiro).
            f["indicador"] = page.evaluate(_JS_INDICADOR)
            f["atalho_repouso"] = page.evaluate(_JS_ESTILO_ATALHO, '[data-testid="atalho-financeiro"]')
            page.locator('[data-testid="atalho-financeiro"]').hover()
            page.wait_for_timeout(450)
            f["atalho_hover"] = page.evaluate(_JS_ESTILO_ATALHO, '[data-testid="atalho-financeiro"]')
            page.mouse.move(1, 1)
            page.locator('[data-testid="atalho-financeiro"]').click()
            page.wait_for_timeout(900)
            f["fin"] = page.evaluate("() => { const e = document.querySelector('[data-testid=\"secao-financeiro\"]');"
                                     " if (!e) return {ausente: true, url: location.pathname};"
                                     " const r = e.getBoundingClientRect(), a = document.querySelector('[data-testid=\"atalho-financeiro\"]');"
                                     " return {topo: r.top, altura: window.innerHeight, scroll: window.scrollY, url: location.pathname,"
                                     " ativa: !!a && a.getAttribute('aria-current') === 'page'}; }")
            page.evaluate("() => window.scrollTo(0, 0)")
        except Exception as erro:
            f["erro"] = f"{type(erro).__name__}: {str(erro).splitlines()[0][:160]}"
        return f

    def fluxo_avaliar_cancelar_certificado(page, nome_marina, nome_rafael):
        """F1: mesmos fluxos de avaliação, cancelamento e certificado."""
        r = {}
        try:
            card = page.locator('[data-testid="curso-card"]').filter(has=page.locator(".curso-nome", has_text=nome_marina)).first
            card.locator('[data-testid="curso-avaliacao-nota"]').select_option(label="4 ★")
            card.locator('[data-testid="curso-avaliacao-comentario"]').fill("Muito bom, conteúdo claro.")
            card.locator('[data-testid="curso-avaliacao-enviar"]').click()
            card.locator('[data-testid="curso-avaliacao-ok"]').wait_for(state="visible", timeout=TIMEOUT)
            r["avaliar"] = True
        except Exception as erro:
            r["avaliar"] = f"{type(erro).__name__}: {str(erro).splitlines()[0][:120]}"
        try:
            card = page.locator('[data-testid="curso-card"]').filter(has=page.locator(".curso-nome", has_text=nome_marina)).first
            card.locator('[data-testid="curso-cancelar"]').click(timeout=3000)
            motivo = card.locator('[data-testid="curso-cancelar-motivo"]')
            motivo.wait_for(state="visible", timeout=3000)
            card.get_by_role("button", name="Voltar").click()
            page.wait_for_timeout(300)
            r["cancelar"] = (motivo.count() == 0) or (not motivo.first.is_visible())
        except Exception as erro:
            r["cancelar"] = f"{type(erro).__name__}: {str(erro).splitlines()[0][:120]}"
        return r

    def coletar():
        if "erro" in seed:
            return
        for largura in LARGURAS:
            for conta, email in (("marina", seed["principal"]["email"]), ("rafael", seed["rafael"]["email"]),
                                 ("bruno", seed["vazio"]["email"])):
                page = nova(largura)
                try:
                    entrar(page, email)
                except Exception as erro:
                    medidas[(conta, largura)] = {"erro": f"login de {conta}: {str(erro).splitlines()[0][:120]}"}
                    continue
                medir(conta, largura, page)
                if conta == "marina" and largura == 1366 and "erro" not in medidas[(conta, largura)]:
                    fluxos["sonda"] = sonda_marina(page)
                    page.goto(spa["base"] + "/student", wait_until="networkidle")
                    page.locator('[data-testid="secao-cursos"]').wait_for(state="visible", timeout=TIMEOUT)
                    fluxos["f1"] = fluxo_avaliar_cancelar_certificado(page, seed["ativo"]["nome"], seed["turma_curso"]["nome"])
                if conta == "rafael" and largura == 1366 and "erro" not in medidas[(conta, largura)]:
                    try:
                        card = page.locator('[data-testid="curso-card"]').filter(
                            has=page.locator(".curso-nome", has_text=seed["turma_curso"]["nome"])).first
                        with page.expect_download(timeout=TIMEOUT) as baixado:
                            card.locator('[data-testid="curso-certificado"]').click()
                        fluxos["certificado"] = baixado.value.suggested_filename or "arquivo"
                    except Exception as erro:
                        fluxos["certificado"] = f"ERRO {type(erro).__name__}: {str(erro).splitlines()[0][:120]}"

    coletar()

    # ---------------------------------------------------------------------------------------- helpers de cenário
    def exigir_seed():
        if "erro" in seed:
            raise Falha(f"seed falhou: {seed['erro']}")
        if not medidas:
            raise Falha("nenhuma tela foi medida")

    def cartao(m, parte):
        return next((c for c in m.get("cards", []) if parte in c["nome"]), None)

    def para(contas, larguras, funcao, resumo):
        """Aplica `funcao(m, rotulo)` -> lista de violações a cada (conta, largura)."""
        def cenario():
            exigir_seed()
            v = []
            for conta in contas:
                for largura in larguras:
                    m = medidas.get((conta, largura), {"erro": "não medida"})
                    rotulo = f"{conta} @{largura}px"
                    if "erro" in m:
                        v.append(f"{rotulo}: {m['erro']}")
                        continue
                    v.extend(f"{rotulo}: {x}" for x in funcao(m, rotulo))
            _exigir(v, resumo)
        return cenario

    N_MARINA, N_PEND = lambda: seed["ativo"]["nome"], lambda: seed["pendente"]["nome"]  # noqa: E731
    N_TURMA, N_VAZIO = lambda: seed["turma_curso"]["nome"], lambda: seed["vazio_curso"]["nome"]  # noqa: E731

    # --- P0 ---------------------------------------------------------------------------------------------------
    def p0():
        exigir_seed()
        v = []
        for largura in LARGURAS:
            for conta, esperado in (("marina", 2), ("rafael", 2), ("bruno", 0)):
                m = medidas.get((conta, largura), {"erro": "não medida"})
                if "erro" in m:
                    v.append(f"{conta} @{largura}px: {m['erro']}")
                    continue
                if len(m["cards"]) != esperado:
                    v.append(f"{conta} @{largura}px: {len(m['cards'])} cartões (esperado {esperado})")
            m = medidas.get(("marina", largura), {})
            if "cards" in m:
                a, p = cartao(m, N_MARINA()), cartao(m, N_PEND())
                if not a or a["progressoTexto"] != "1 de 2 concluídos":
                    v.append(f"marina @{largura}px: progresso do cartão ativo = {a and a['progressoTexto']!r} (esperado '1 de 2 concluídos')")
                if not p or p["entrar"] is not None:
                    v.append(f"marina @{largura}px: cartão pendente ausente ou com 'Entrar no curso'")
                if a and not a["cancelar"]:
                    v.append(f"marina @{largura}px: o cartão ativo não oferece 'Pedir cancelamento' (seed não exercita o cancelamento)")
            m = medidas.get(("rafael", largura), {})
            if "cards" in m:
                t, s = cartao(m, N_TURMA()), cartao(m, N_VAZIO())
                if not t or t["turma"] is None or not t["certificado"]:
                    v.append(f"rafael @{largura}px: cartão com turma e certificado ausente (turma {t and t['turma']}, cert {t and t['certificado']})")
                if not s or not s["semMateriais"]:
                    v.append(f"rafael @{largura}px: cartão sem materiais ausente")
        _exigir(v, "pré-condição do seed")

    # --- C CTA ---------------------------------------------------------------------------------------------------
    def c1(m, rotulo):
        c, h1 = m.get("cta"), m.get("h1")
        if not c:
            return ["[data-testid=atalho-catalogo] ausente"]
        v = []
        if c["texto"] != "Comprar cursos":
            v.append(f"texto {c['texto']!r} (esperado 'Comprar cursos')")
        if c["href"] != "/catalogo":
            v.append(f"href {c['href']!r} (esperado /catalogo)")
        if "btn-cta" not in c["classes"]:
            v.append(f"sem a classe .btn-cta ({c['classes']})")
        if c["noNav"]:
            v.append("o CTA está dentro de um <nav>: deveria estar no cabeçalho, fora da barra de atalhos")
        if any(a.get("contemCta") for a in m["atalhos"]):
            v.append("o CTA está dentro da mesma navegação dos atalhos de seção")
        if c["raio"] > 10:
            v.append(f"border-radius {c['raio']:.0f}px (esperado <= 10px, retangular; pílula não)")
        if c["rect"]["h"] < 48:
            v.append(f"altura {c['rect']['h']:.0f}px (esperado >= 48px)")
        if c["fundo"] != LARANJA:
            v.append(f"fundo {c['fundo']} (esperado {LARANJA})")
        if c["cor"] != TEXTO:
            v.append(f"texto {c['cor']} (esperado {TEXTO})")
        if h1 and "@1366" in rotulo:
            band_t, band_b = h1["rect"]["t"], (m.get("email") or {"rect": h1["rect"]})["rect"]["b"]
            cy = (c["rect"]["t"] + c["rect"]["b"]) / 2
            if c["rect"]["l"] < h1["texto_rect"]["r"] + 8:
                v.append(f"CTA em x={c['rect']['l']:.0f}, não está à direita da saudação (texto do h1 termina em x={h1['texto_rect']['r']:.0f})")
            if not (band_t - 6 <= cy <= band_b + 6):
                v.append(f"centro vertical do CTA y={cy:.0f} fora da faixa do cabeçalho (h1 topo {band_t:.0f} a e-mail fim {band_b:.0f})")
            if c["rect"]["r"] < 0.8 * 1366 - 20:
                v.append(f"CTA termina em x={c['rect']['r']:.0f}: não está alinhado à direita da página")
        return v

    def c2():
        exigir_seed()
        f = fluxos.get("sonda", {})
        if "erro" in f or "cta_hover" not in f:
            raise Falha(f"hover não medido: {f.get('erro')}")
        h = f["cta_hover"]
        v = []
        if h["fundo"] != HOVER_CTA:
            v.append(f"fundo no hover {h['fundo']} (esperado {HOVER_CTA})")
        try:
            r = razao_contraste(h["cor"], h["fundo"])
            if r < 4.5:
                v.append(f"contraste no hover {r:.2f}:1 ({h['cor']} sobre {h['fundo']})")
        except ValueError:
            v.append(f"cor do hover não interpretada: {h}")
        _exigir(v, "hover do CTA")

    def c3(m, rotulo):
        c, h1 = m.get("cta"), m.get("h1")
        if not c or not h1:
            return ["CTA ou h1 ausente"]
        v = []
        if c["rect"]["w"] < 0.85 * 390:
            v.append(f"largura {c['rect']['w']:.0f}px (esperado a largura toda, >= {0.85 * 390:.0f}px)")
        if c["rect"]["t"] < h1["rect"]["b"] - 1:
            v.append(f"CTA em y={c['rect']['t']:.0f} acima do fim do h1 (y={h1['rect']['b']:.0f}): deveria ficar abaixo da saudação")
        return v

    def c4(m, rotulo):
        return list(m["laranja"])

    # --- N atalhos ---------------------------------------------------------------------------------------------
    TEXTOS = {"atalho-cursos": "Meus cursos",  # R3-3 (D125): o rótulo da aba é "Meus cursos" (contrato do orquestrador)
              "atalho-financeiro": "Financeiro", "atalho-perfil": "Meu perfil"}  # R3-4 (D126): sem "Assistente"

    def n1(m, rotulo):
        v = []
        for a in m["atalhos"]:
            if a["n"] != 1:
                v.append(f"[data-testid={a['id']}] aparece {a['n']} vez(es) (esperado 1)")
                continue
            if a["texto"] != TEXTOS[a["id"]]:
                v.append(f"{a['id']}: texto {a['texto']!r} (esperado {TEXTOS[a['id']]!r})")
            if not a["nav"]:
                v.append(f"{a['id']}: fora da barra ul.nav.nav-tabs.gt-abas")
            if a["rect"]["h"] < 44:
                v.append(f"{a['id']}: altura {a['rect']['h']:.0f}px (esperado >= 44px)")
            if a["raio"] >= 12 and (a["algumaBorda"] or a["fundoAlfa"] > 0):
                v.append(f"{a['id']}: formato de pílula (raio {a['raio']:.0f}px com "
                         f"{'borda' if a['algumaBorda'] else 'fundo ' + a['fundo']}); esperado link/aba em texto")
        navs = {a["navId"] for a in m["atalhos"] if a["n"] == 1}
        if len(navs) != 1:
            v.append(f"os 3 atalhos não estão na mesma barra de abas ({navs})")
        if any(a.get("contemCta") for a in m["atalhos"]):
            v.append("o CTA 'Comprar cursos' continua dentro da navegação dos atalhos")
        return v

    def n2():
        """R3-3 (D125): o retorno visual dos atalhos passa a ser o das abas da gestão: indicador (li.gt-abas-indicador) sob a aba
        ativa e retorno no hover da aba inativa (sublinhado, borda inferior, sombra, ou mudança de cor, fundo ou borda)."""
        exigir_seed()
        f = fluxos.get("sonda", {})
        if "atalho_hover" not in f:
            raise Falha(f"hover dos atalhos não medido: {f.get('erro')}")
        v = []
        ind = f.get("indicador")
        if not ind:
            v.append("indicador da aba ativa ([data-testid=abas-indicador]) ausente")
        elif ind["h"] < 2 or ind["w"] <= 0 or ind["alfa"] <= 0:
            v.append(f"indicador da aba ativa invisível (altura {ind['h']:.0f}px, largura {ind['w']:.0f}px, fundo {ind['fundo']})")
        r, h = f["atalho_repouso"], f["atalho_hover"]
        mudou = any(r[k] != h[k] for k in ("cor", "fundo", "bordaTodas", "sombraTxt", "sublinhado"))
        if not (h["sublinhado"] or h["bordaInf"] or h["sombra"] or mudou):
            v.append(f"aba Financeiro no hover sem retorno visual (text-decoration sublinhado: {h['sublinhado']}; "
                     f"border-bottom {h['bordaInfTxt']}; box-shadow {h['sombraTxt']}; cor {h['cor']}; fundo {h['fundo']})")
        _exigir(v, "indicador e hover das abas")

    def n3():
        exigir_seed()
        f = fluxos.get("sonda", {})
        v = []
        m = medidas[("marina", 1366)]
        perfil = next(a for a in m["atalhos"] if a["id"] == "atalho-perfil")
        if perfil.get("href") != "/student/perfil":
            v.append(f"Meu perfil com href {perfil.get('href')!r} (esperado /student/perfil)")
        fin = f.get("fin")
        if not fin:
            v.append(f"clique em Financeiro não medido: {f.get('erro')}")
        else:
            # R3-3 (D125): Financeiro é uma aba; levar à seção = selecionar a aba e ela ficar à vista, sem sair de /student.
            if fin["url"] != "/student":
                v.append(f"Financeiro navegou para {fin['url']} (esperado ficar em /student)")
            if fin.get("ausente"):
                v.append("Financeiro: a seção [data-testid=secao-financeiro] não apareceu depois do clique")
            else:
                if not fin["ativa"]:
                    v.append("Financeiro: a aba não ficou ativa (aria-current=page ausente)")
                if not (-5 <= fin["topo"] < fin["altura"] * 0.6):
                    v.append(f"Financeiro não levou a seção para a vista (topo {fin['topo']:.0f}px, janela {fin['altura']:.0f}px)")
        _exigir(v, "ação dos atalhos")

    # --- H cabeçalho ---------------------------------------------------------------------------------------------
    def h1_(m, rotulo):
        v = []
        if m["h1n"] != 1:
            v.append(f"{m['h1n']} h1 visíveis (esperado 1)")
        h1 = m.get("h1")
        if h1 and not re.fullmatch(r"Olá, \S+!", h1["texto"]) and not h1["texto"].startswith("Olá!"):
            v.append(f"h1 {h1['texto']!r}")
        if m.get("molduras"):
            v.append("saudação dentro de cartão/moldura: " + "; ".join(m["molduras"]))
        if not m["rotulo"]:
            v.append("rótulo 'Área do aluno' não está visível")
        e = m.get("email")
        if not e or "Conectado como" not in e["pai"] or "@" not in e["texto"]:
            v.append(f"subtítulo 'Conectado como <email>' ausente ({e and e['pai']!r})")
        return v

    # --- M meus cursos --------------------------------------------------------------------------------------------
    def m1(m, rotulo):
        """R3-3 (D125, revogação decidida pelo PM: "cada curso em formato de cards em vez de um em cima do outro").
        A 390 px continua 1 cartão por linha na largura toda (como era). A 1366 px os cartões ficam em GRADE: lado a lado, na mesma
        linha, sem passar de metade da seção (a exigência de >= 3 colunas está no arquivo da R3-3, C1)."""
        v, secao, cards = [], m["secao"], m["cards"]
        if "@390" in rotulo:
            for c in cards:
                if c["rect"]["w"] < 0.9 * secao["w"]:
                    v.append(f"cartão '{c['nome'][:30]}' com {c['rect']['w']:.0f}px de {secao['w']:.0f}px da seção "
                             f"({100 * c['rect']['w'] / secao['w']:.0f}%; esperado >= 90%)")
            for a, b in zip(cards, cards[1:]):
                if b["rect"]["t"] < a["rect"]["b"] - 1:
                    v.append(f"cartões '{a['nome'][:20]}' e '{b['nome'][:20]}' lado a lado no celular (esperado empilhados)")
        else:
            for c in cards:
                if c["rect"]["w"] > 0.5 * secao["w"]:
                    v.append(f"cartão '{c['nome'][:30]}' com {c['rect']['w']:.0f}px de {secao['w']:.0f}px da seção "
                             f"({100 * c['rect']['w'] / secao['w']:.0f}%; esperado <= 50%: cartões em grade, não um por linha)")
            for a, b in zip(cards, cards[1:]):
                if abs(b["rect"]["t"] - a["rect"]["t"]) > 2:
                    v.append(f"cartões '{a['nome'][:20]}' e '{b['nome'][:20]}' em linhas diferentes (topos {a['rect']['t']:.0f} e "
                             f"{b['rect']['t']:.0f}); esperado lado a lado na grade")
        return v

    def m2(m, rotulo):
        """R3-3 (D125, revogação decidida pelo PM): o cartão deixa de ser uma LINHA (ícone à esquerda, corpo na coluna do meio, badge
        ao lado do nome, ação à direita) e passa a ser um cartão em coluna. Mantém-se o que o cartão mostra: ícone de iniciais, nome,
        selo de status, linha de matrícula, turma e barra, tudo dentro do cartão; a linha de matrícula e a barra ficam ABAIXO do nome."""
        v = []
        for c in m["cards"]:
            n = c["nome"][:30]
            if not c["icone"] or not re.fullmatch(r"[^\W_]{1,3}", c["iconeTexto"] or ""):
                v.append(f"'{n}': ícone de iniciais ausente ({c['iconeTexto']!r})")
                continue
            nr, cr = c["nomeRect"], c["rect"]
            if not c["badge"]:
                v.append(f"'{n}': badge de status ausente")
            elif not (cr["l"] - 1 <= c["badge"]["l"] and c["badge"]["r"] <= cr["r"] + 1):
                v.append(f"'{n}': badge '{c['badgeTexto'].strip()}' {_r(c['badge'])} fora do cartão {_r(cr)}")
            for chave, nome_ in (("data", "linha de matrícula"), ("turma", "linha de turma")):
                if chave == "turma" and not c["turma"]:
                    continue
                r = c[chave]
                if not r:
                    v.append(f"'{n}': {nome_} ausente")
                elif r["t"] < nr["b"] - 2 or not (cr["l"] - 1 <= r["l"] and r["r"] <= cr["r"] + 1):
                    v.append(f"'{n}': {nome_} {_r(r)} não está abaixo do nome e dentro do cartão (nome termina em y={nr['b']:.0f}, cartão {_r(cr)})")
            if c["barra"] and c["barra"]["t"] < nr["b"] - 2:
                v.append(f"'{n}': barra em y={c['barra']['t']:.0f} acima do fim do nome (y={nr['b']:.0f}); esperado abaixo")
        return v

    def m3(m, rotulo):
        v = []
        for c in m["cards"]:
            if c["nome"] in (N_PEND(),):
                continue
            n = c["nome"][:30]
            e = c["entrar"]
            if not e:
                v.append(f"'{n}': [data-testid=curso-entrar] ausente")
                continue
            if e["texto"] != "Entrar no curso":
                v.append(f"'{n}': texto {e['texto']!r} (esperado 'Entrar no curso')")
            if e["h"] < 44:
                v.append(f"'{n}': 'Entrar no curso' com {e['h']:.0f}px de altura (esperado >= 44px)")
            nr = c["nomeRect"]
            if "@1366" in rotulo:
                # R3-3 (D125, revogação decidida pelo PM): no cartão em coluna a ação fica ABAIXO do nome e dentro do cartão
                # (não mais à direita e à altura do nome). A posição na base do cartão é exigida no arquivo da R3-3 (C4).
                if e["t"] < nr["b"] - 1:
                    v.append(f"'{n}': 'Entrar no curso' em y={e['t']:.0f} acima do fim do nome (y={nr['b']:.0f}); esperado abaixo, no cartão em coluna")
                if not (c["rect"]["l"] - 1 <= e["l"] and e["r"] <= c["rect"]["r"] + 1):
                    v.append(f"'{n}': 'Entrar no curso' em x={e['l']:.0f}-{e['r']:.0f} fora do cartão (x {c['rect']['l']:.0f}-{c['rect']['r']:.0f})")
            else:
                if e["w"] < 0.8 * c["rect"]["w"]:
                    v.append(f"'{n}': 'Entrar no curso' com {e['w']:.0f}px de {c['rect']['w']:.0f}px (esperado largura toda no celular)")
                if e["t"] < nr["b"] - 1:
                    v.append(f"'{n}': 'Entrar no curso' acima do fim do nome no celular")
        return v

    def m4(m, rotulo):
        v = []
        if "bruno" in rotulo:
            return v
        if "marina" in rotulo:
            p = cartao(m, N_PEND())
            if not p:
                return ["cartão pendente não encontrado"]
            if p["entrar"]:
                v.append("cartão pendente mostra 'Entrar no curso'")
            if not p["aviso"] or len(p["aviso"]["texto"]) < 10:
                v.append(f"cartão pendente sem a mensagem de acesso no lugar da ação ({p['aviso']})")
            if p["bloco"]:
                v.append("cartão pendente mostra bloco de avaliação/materiais")
        if "rafael" in rotulo:
            s = cartao(m, N_VAZIO())
            if not s or not s["semMateriais"]:
                v.append("curso sem materiais não mostra 'Este curso ainda não tem materiais.'")
        return v

    # --- P progresso ---------------------------------------------------------------------------------------------
    ESPERADO_PCT = (("marina", "ativo", "1 de 2 concluídos", "50"), ("rafael", "turma", "2 de 2 concluídos", "100"))

    def com_progresso(m, rotulo):
        out = []
        for conta, qual, texto, pct in ESPERADO_PCT:
            if conta in rotulo:
                nome = N_MARINA() if qual == "ativo" else N_TURMA()
                out.append((cartao(m, nome), texto, pct))
        return out

    def p1(m, rotulo):
        v = []
        for c, texto, pct in com_progresso(m, rotulo):
            if not c:
                v.append("cartão com progresso não encontrado")
                continue
            if c["progressoTexto"] != texto:
                v.append(f"[data-testid=curso-progresso] = {c['progressoTexto']!r} (esperado {texto!r})")
            if c["barras"] != 1:
                v.append(f"'{c['nome'][:25]}': {c['barras']} [role=progressbar] (esperado 1)")
                continue
            b = c["barra"]
            if (b["now"], b["min"], b["max"]) != (pct, "0", "100"):
                v.append(f"'{c['nome'][:25]}': aria-valuenow/min/max = {b['now']}/{b['min']}/{b['max']} (esperado {pct}/0/100)")
            if b["label"] != "Progresso do curso":
                v.append(f"'{c['nome'][:25]}': aria-label {b['label']!r} (esperado 'Progresso do curso')")
        if "rafael" in rotulo:
            s = cartao(m, N_VAZIO())
            if s and s["barras"]:
                v.append("curso sem materiais mostra barra de progresso (dado inventado)")
        return v

    def p2(m, rotulo):
        v = []
        for c, texto, pct in com_progresso(m, rotulo):
            if not c or not c["barra"]:
                v.append("cartão ou barra ausente (ver P1)")
                continue
            b, n = c["barra"], c["nome"][:25]
            minimo = 0.5 if "@1366" in rotulo else 0.55
            if b["w"] < minimo * c["rect"]["w"]:
                v.append(f"'{n}': barra com {b['w']:.0f}px de {c['rect']['w']:.0f}px do cartão ({100 * b['w'] / c['rect']['w']:.0f}%; esperado >= {minimo * 100:.0f}%)")
            alvo = [p for p in c["pct"] if p["texto"] == f"{pct}%"]
            if not alvo:
                v.append(f"'{n}': percentual por extenso '{pct}%' ausente (achados: {[p['texto'] for p in c['pct']]})")
                continue
            p = alvo[0]
            if abs((p["t"] + p["b"]) / 2 - (b["t"] + b["b"]) / 2) > 14:
                v.append(f"'{n}': '{pct}%' fora da linha da barra (y {p['t']:.0f}-{p['b']:.0f} contra a barra {b['t']:.0f}-{b['b']:.0f})")
            if p["l"] < b["r"] - 2:
                v.append(f"'{n}': '{pct}%' não fica ao lado direito da barra (x={p['l']:.0f} < fim da barra {b['r']:.0f})")
            if c["fill"] and f"width: {pct}%" not in c["fill"]["estilo"]:
                v.append(f"'{n}': preenchimento sem 'width: {pct}%' (style {c['fill']['estilo']!r})")
        return v

    def p3(m, rotulo):
        v = []
        for c, texto, pct in com_progresso(m, rotulo):
            if not c or not c["fill"]:
                v.append("preenchimento (.progress-bar) ausente")
            elif c["fill"]["fundo"] not in PREENCHIMENTOS:
                v.append(f"'{c['nome'][:25]}': preenchimento {c['fill']['fundo']} (esperado #0077a3 ou #0096c7)")
            elif c["barras"] == 1 and c["barra"] is None:
                v.append("sem role=progressbar")
        # sem role=progressbar não há barra acessível: P3 também exige a barra
        for c, texto, pct in com_progresso(m, rotulo):
            if c and c["barras"] == 0:
                v.append(f"'{c['nome'][:25]}': preenchimento sem [role=progressbar] (barra não acessível)")
        return v

    # --- B bloco secundário ---------------------------------------------------------------------------------------
    def b1(m, rotulo):
        v = []
        if "bruno" in rotulo:
            return v
        alvos = [cartao(m, N_MARINA())] if "marina" in rotulo else [cartao(m, N_TURMA())]
        for c in alvos:
            if not c:
                v.append("cartão não encontrado")
                continue
            b, n = c["bloco"], c["nome"][:25]
            if not b:
                v.append(f"'{n}': a avaliação não está num bloco com fundo #f7f9fb dentro do cartão")
                continue
            if not b["divisoria"]:
                v.append(f"'{n}': bloco sem divisória (border-top, border-bottom do irmão anterior ou hr)")
            for chave, nome_ in (("temComentario", "comentário"), ("temNota", "nota"), ("temEnviar", "Enviar"),
                                 ("temCheckboxes", "checkboxes dos materiais"), ("temLinks", "links dos materiais"),
                                 ("temCancelar", "cancelamento")):
                if not b[chave]:
                    v.append(f"'{n}': {nome_} fora do bloco secundário")
            if b["temEntrar"] or b["temNome"]:
                v.append(f"'{n}': o bloco secundário contém a ação principal ou o nome do curso")
        return v

    def b2(m, rotulo):
        """R3-3 (D125, revogação decidida pelo PM): "avaliação numa única linha" não cabe em cartões de 3 colunas (cartão de ~375 px:
        comentário >= 200 px + nota + Enviar passam do corpo do cartão). Passa a valer: comentário continua crescendo (>= 200 px),
        ordem de leitura comentário, nota, Enviar (na mesma linha ou em linhas seguintes) e nada fora do cartão. A quebra sem
        sobreposição e a 390 px estão em C5 do arquivo da R3-3."""
        v = []
        if "@1366" not in rotulo:
            return v
        for conta in ("marina", "rafael"):
            if conta not in rotulo:
                continue
            c = cartao(m, N_MARINA() if conta == "marina" else N_TURMA())
            a = c and c["aval"]
            if not a:
                v.append("avaliação ausente")
                continue
            for antes, depois, nome_ in ((a["com"], a["nota"], "nota"), (a["nota"], a["env"], "Enviar")):
                mesma_linha = abs((antes["t"] + antes["b"]) / 2 - (depois["t"] + depois["b"]) / 2) <= 12
                if not ((mesma_linha and antes["l"] < depois["l"]) or depois["t"] >= antes["b"] - 2):
                    v.append(f"ordem de leitura esperada: comentário, nota, Enviar ({nome_} {_r(depois)} vem antes do item anterior {_r(antes)})")
            if a["com"]["w"] < 200:
                v.append(f"comentário com {a['com']['w']:.0f}px (nota {a['nota']['w']:.0f}px): o campo deve continuar usável (>= 200 px)")
            cr = c["rect"]
            for nome_, r in (("comentário", a["com"]), ("nota", a["nota"]), ("Enviar", a["env"])):
                if r["l"] < cr["l"] - 1 or r["r"] > cr["r"] + 1:
                    v.append(f"{nome_} {_r(r)} estoura o cartão {_r(cr)}")
        return v

    def b3(m, rotulo):
        v = []
        if "rafael" not in rotulo:
            return v
        c = cartao(m, N_TURMA())
        cert = c and c["certificado"]
        if not cert or not cert["visivel"]:
            return ["'Baixar certificado' ausente ou invisível"]
        if "btn-outline-primary" not in cert["classes"] and "btn-outline-secondary" not in cert["classes"]:
            v.append(f"'Baixar certificado' sem estilo outline ({cert['classes']})")
        if "btn-primary" in cert["classes"]:
            v.append("'Baixar certificado' é .btn-primary (a ação principal do cartão é Entrar no curso)")
        b = c["bloco"]
        if not b or not (b["temCheckboxes"] and b["temLinks"]) or c["nCheck"] != 2 or c["nLinks"] != 2:
            v.append(f"materiais/checkboxes não estão no bloco secundário (check {c['nCheck']}, links {c['nLinks']}, bloco {bool(b)})")
        return v

    def f1():
        exigir_seed()
        v = []
        f = fluxos.get("f1", {})
        if f.get("avaliar") is not True:
            v.append(f"avaliar o curso: {f.get('avaliar', 'não executado')}")
        if f.get("cancelar") is not True:
            v.append(f"abrir e fechar o pedido de cancelamento: {f.get('cancelar', 'não executado')}")
        cert = fluxos.get("certificado", "não executado")
        if not str(cert).lower().endswith(".pdf"):
            v.append(f"baixar certificado: {cert}")
        if dialogos:
            v.append(f"diálogo nativo (confirm/alert) aberto: {dialogos}")
        _exigir(v, "fluxos de avaliação, cancelamento e certificado")

    # --- R, E, A, G, K --------------------------------------------------------------------------------------------
    def r1(m, rotulo):
        r = m["resumo"]
        return r["n1"] + r["n2"] + r["n3"]

    def e1(m, rotulo):
        if "bruno" not in rotulo:
            return []
        v = []
        if VAZIO_CURSOS not in m["vazio"].get("texto", ""):
            v.append(f"sem o texto {VAZIO_CURSOS!r}")
        lk = m["ver_cursos"]
        if not lk or lk["href"] != "/catalogo":
            v.append(f"link 'Ver cursos' ausente ou sem href /catalogo ({lk})")
        else:
            if lk["cta"] or lk["fundo"] == LARANJA or lk["cor"] == LARANJA:
                v.append(f"'Ver cursos' em laranja/.btn-cta ({lk}); a tela deve ter um só laranja")
            nums = [int(x) for x in re.findall(r"\d+", lk["cor"])[:3]]
            if not nums[2] > nums[0] + 60:
                v.append(f"'Ver cursos' com cor {lk['cor']} (esperado azul)")
        return v

    def a1(m, rotulo):
        c = m["contraste"]
        out = [] if c["verificados"] >= 10 or "bruno" in rotulo else [f"só {c['verificados']} textos verificados"]
        out.extend(descrever([f], 1) for f in c["falhas"])
        return out

    def a2(m, rotulo):
        return [descrever([i], 1) for i in m["fontes"]]

    def g1(m, rotulo):
        d = m["ds1"]
        return [f"{len(d['h1'])} h1 visíveis {d['h1']}"] if len(d["h1"]) != 1 else []

    def g3(m, rotulo):
        return list(m["ds1"]["alvos"])

    def g4(m, rotulo):
        d = m["ds1"]
        fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
        if d["scrollWidth"] > 390:
            return [f"scrollWidth {d['scrollWidth']}px (> 390). Passam da borda: {fora}"]
        if d["clipaRaiz"] and d["fora"]:
            return [f"estouro escondido por overflow-x hidden. Passam da borda: {fora}"]
        return []

    def k1():
        exigir_seed()
        v = list(erros)
        for chave, m in medidas.items():
            if "erro" not in m and m["emoji"]:
                v.append(f"{chave}: emoji no texto da página {m['emoji']}")
        _exigir(v, "emoji ou erro de console")

    COM = ("marina", "rafael", "bruno")
    D, M = (1366,), (390,)
    try:
        _rodar([
            ("P0", "pré-condição do seed (cartões, turma, certificado, vazio)", p0),
            ("C1", "CTA no cabeçalho, à direita do h1, retangular, laranja com texto escuro",
             para(("marina", "rafael", "bruno"), LARGURAS, c1, "CTA 'Comprar cursos'")),
            ("C2", "CTA no hover: #e86a0c e texto legível", c2),
            ("C3", "CTA no celular: largura toda abaixo da saudação", para(COM, M, c3, "CTA no celular")),
            ("C4", "laranja só no CTA", para(COM, LARGURAS, c4, "laranja fora do CTA")),
            ("N1", "3 atalhos na barra de abas, em texto (sem pílula, sem CTA)", para(COM, LARGURAS, n1, "atalhos de seção")),
            ("N2", "abas com indicador sob a ativa e retorno no hover da inativa", n2),
            ("N3", "atalhos mantêm a ação (perfil, aba Financeiro à vista)", n3),
            ("H1", "cabeçalho sem cartão: h1 direto, rótulo, e-mail", para(COM, LARGURAS, h1_, "cabeçalho")),
            ("M1", "cartões de curso: 1 por linha a 390 px, em grade a 1366 px", para(("marina", "rafael"), LARGURAS, m1, "largura dos cartões")),
            ("M2", "cartão em coluna: ícone, nome, badge, linhas e barra abaixo do nome", para(("marina", "rafael"), D, m2, "layout em linha do cartão")),
            ("M3", "ação 'Entrar no curso': 44 px, abaixo do nome (desktop) / largura toda (celular)",
             para(("marina", "rafael"), LARGURAS, m3, "ação principal do cartão")),
            ("M4", "sem acesso mostra a mensagem; curso sem materiais mantém o aviso", para(("marina", "rafael"), LARGURAS, m4, "cartão sem acesso")),
            ("P1", "progressbar acessível e texto 'x de y' mantido", para(("marina", "rafael"), LARGURAS, p1, "barra de progresso (a11y)")),
            ("P2", "barra na largura do corpo e NN% ao lado", para(("marina", "rafael"), LARGURAS, p2, "barra e percentual")),
            ("P3", "preenchimento em #0077a3 (ou #0096c7)", para(("marina", "rafael"), LARGURAS, p3, "cor do preenchimento")),
            ("B1", "materiais, avaliação e cancelamento em bloco secundário #f7f9fb com divisória",
             para(("marina", "rafael"), LARGURAS, b1, "bloco secundário")),
            ("B2", "avaliação a 1366 px: comentário usável, ordem de leitura, dentro do cartão", para(("marina", "rafael"), D, b2, "linha da avaliação")),
            ("B3", "certificado secundário e materiais no bloco", para(("rafael",), LARGURAS, b3, "certificado e materiais")),
            ("F1", "fluxos de avaliar, cancelar e certificado; sem dialog nativo", f1),
            ("R1", "faixa de números sem regressão", para(("marina", "bruno"), LARGURAS, r1, "faixa de números")),
            ("E1", "conta vazia: 'Ver cursos' azul para /catalogo", para(("bruno",), LARGURAS, e1, "estado vazio")),
            ("A1", "contraste AA em todo texto visível", para(COM, LARGURAS, a1, "contraste AA")),
            ("A2", "piso de 14 px", para(COM, LARGURAS, a2, "texto abaixo de 14 px")),
            ("G1", "um h1 por tela", para(COM, LARGURAS, g1, "um h1")),
            ("G3", "alvos >= 44 px", para(COM, LARGURAS, g3, "alvo de toque < 44 px")),
            ("G4", "sem rolagem horizontal a 390 px", para(COM, M, g4, "rolagem horizontal a 390 px")),
            ("K1", "sem emojis nem erros de console", k1),
        ])
    finally:
        for ctx in contextos:
            ctx.close()
