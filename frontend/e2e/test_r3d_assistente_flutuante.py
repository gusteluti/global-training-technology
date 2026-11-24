"""E2E da R3-4 (D126) - O assistente da Área do aluno (/student) vira um BOTÃO FLUTUANTE à direita da tela, como na landing.

Só design e estrutura de tela: nenhuma lógica de negócio, endpoint ou texto de negócio muda.

Pedido do PM (23/11/2026): "Troque onde está a funcionalidade do assistente: em vez de ficar como se fosse um chat embaixo da tela,
deixe um botão na direita da tela igual é na landing page." Decisões do PM: o assistente vira um botão verde flutuante à direita
da tela, como na landing; a barra de abas fica só com as duas abas e "Meu perfil". Referência visual e de comportamento: o chat da
landing (`frontend/landing_global_training.html`: `#chat-btn` / `#chat-bubble` / `toggleChat()`), que NÃO muda e não é testado aqui.

CONTRATO (o dev-frontend implementa; a FORMA é do orquestrador, este arquivo é a fonte)
  1. Sai da tela: a seção `#secao-assistente` e o botão `atalho-assistente` da barra de abas deixam de existir. Ao abrir `/student`
     o painel do chat NÃO existe no DOM (`[data-testid=chat-panel]` com 0 elementos; nenhum `[data-testid^=chat-]`). A barra
     `ul.nav.nav-tabs.gt-abas` fica com "Meus cursos", "Financeiro" e, no fim, "Meu perfil" (continua `<a>`, `atalho-perfil`, sem
     `data-aba`/`aria-current`/`active`, mesma aparência das abas inativas).
  2. Botão flutuante (FAB): `<button type="button" id="assistente-btn" data-testid="assistente-botao"
     aria-controls="assistente-painel" aria-expanded="false|true">` visível em `/student` (SOMENTE nesta rota; `/student/perfil`, a
     sala do curso, o catálogo, o login e o painel da equipe não têm), `position: fixed`, canto inferior direito: `bottom: 28px;
     right: 28px` e, com a janela <= 600 px, `bottom: 16px; right: 16px` (valores da landing). Círculo de 58x58 px, ícone SVG de
     balão desenhado à mão e `aria-hidden` (sem emoji, sem biblioteca externa de ícones), sombra, `z-index` acima do conteúdo e abaixo
     de modais do Bootstrap (entre 10 e 1049). Cor: verde da landing ESCURECIDO, fundo `#1f9d3a` com ícone branco (o `#40c351` da
     landing dá só 2,3:1 com ícone branco; a D115 pede >= 3:1 para ícone; aqui o contraste do ícone contra o fundo é medido, >= 3:1).
     `aria-label` "Abrir o chat com o assistente" fechado e "Fechar o chat com o assistente" aberto. Foco visível (outline ou anel
     que muda em relação ao repouso). Alvo >= 44 px nas duas dimensões. Nenhuma animação em repouso (a transição de hover é permitida;
     `prefers-reduced-motion` respeitado).
  3. Painel (diálogo): ao clicar no botão surge `<div id="assistente-painel" role="dialog" aria-label="Chat com o assistente"
     data-testid="chat-panel">`, existente no DOM só enquanto aberto (`*ngIf`), `position: fixed` acima do botão: `right: 28px;
     bottom: 96px; width: 360px; max-width: calc(100vw - 32px); max-height: calc(100vh - 112px)` e, com janela <= 600 px, `right:
     16px; bottom: 84px; max-height: calc(100vh - 100px)`. Dentro, de cima para baixo: cabeçalho com o título "Assistente virtual"
     (heading, texto exato) e um botão de fechar (`data-testid="assistente-fechar"`, `aria-label="Fechar o chat"`, alvo >= 44x44);
     área de mensagens rolável (`aria-live="polite"`) com TODOS os testids de hoje intactos (`chat-message` com `data-role`,
     `chat-fonte`, `chat-aviso-pii`, `chat-feedback-up|down`, `chat-acao-abrir`, `chat-acao-matricular`, `chat-acao-whatsapp`,
     mensagem inicial "Nenhuma mensagem ainda. Pergunte algo ao assistente."); aviso de gravação (`chat-aviso-gravacao`, texto de
     hoje); formulário com `chat-input` e `chat-send` (rótulos de hoje). O formulário (campo e Enviar) fica SEMPRE visível dentro do
     painel e da janela, mesmo com muitas mensagens (a área de mensagens rola, o painel não estoura). Painel inteiro dentro da
     janela (margem >= 8 px) em 1280, 768, 390 e 320 px; sem rolagem horizontal da página com o painel aberto.
  4. Comportamento: clicar no botão abre e leva o foco ao `chat-input`; clicar de novo no botão ou em `assistente-fechar` fecha e
     devolve o foco ao botão; `Esc` fecha e devolve o foco ao botão. O histórico (mensagens, fontes, ações, feedback, recibo etc.)
     sobrevive a fechar e reabrir o painel e a trocar de aba (o estado é do componente; não há chamada nova à API ao abrir, fechar ou
     trocar de aba). Ações `open` do chat (`chat-acao-abrir`): continuam selecionando a aba `financeiro`/`cursos` (indicador,
     `aria-current`, seção à vista: topo entre -5 px e 60% da janela) ou navegando para `/student/perfil`; com janela <= 600 px o
     painel FECHA após uma ação `open` (ele cobriria a tela); acima de 600 px permanece aberto. Trocar de aba não fecha o painel.
  5. Não pode cobrir conteúdo: com a página rolada até o fim, em 1280, 768, 390 e 320 px, e com o painel fechado, o botão não cobre
     nenhum texto visível nem controle (link, botão, campo) da página (geometria: nenhum retângulo de texto ou de controle, exceto o
     próprio botão, intersecta o retângulo do botão). Isso inclui o rodapé da aplicação ("Global Training Technology · Plataforma
     educacional"). O dev resolve com folga embaixo; os testes só medem.
  6. Mantido: o chat funciona como hoje (enviar, resposta, fonte, aviso de PII, feedback, ações de matrícula e de WhatsApp,
     handoff, erros). D115: contraste AA em todo texto do painel (aberto, com mensagens do usuário e do bot), texto >= 14 px, alvos
     >= 44 px, um único h1 na tela, campo com rótulo, sem `confirm()`, sem emoji NOVO (os 👍👎 do feedback já existem e ficam), sem
     animação em repouso, foco visível em botão, fechar, campo e Enviar. Não se afirma `aria-modal` nem trava de foco (diálogo não
     modal).
  7. Fora de escopo: a landing (já tem o seu chat), a sala do curso (`chat-sala`) e o backend.

Seed (harness isolado D58; é o semeador da R3-3, `test_r3c_area_aluno_abas_cartoes.semear`): Marina (2 cartões; pagamentos Aprovado e
Pendente), Rafael (2), Bruno (sem matrícula: o chat nunca recebe mensagem), Carla (5 cartões, página alta), Sofia (1), Davi (2). Contas
que enviam mensagens pelo backend de teste (o Groq falso do harness h1, que responde sempre "Resposta fixa do dublê e7."): Davi (P4, 10
trocas), Sofia (P7a), Carla e Rafael (P8). As respostas "controladas" (fonte, aviso de PII, feedback, ações) são interceptadas por
`page.route` no POST /api/student/chat e NÃO são gravadas no servidor.

Testes (cada um lista TODAS as violações, não só a primeira; ids no nome do teste):
  P0  pré-condição do seed: cartões por conta e histórico do chat do Bruno vazio (API)            [passa no red: é o estado de hoje]
  B1  botão: um só, `#assistente-btn` = `assistente-botao`, fixo, offsets (28/28; <=600 px: 16/16; fronteira 600/601), 58x58, círculo,
      fundo #1f9d3a, ícone SVG branco com contraste >= 3:1, aria-*, alvo, z-index, nada por cima dele, sombra, foco visível
  B2  sem animação em repouso (botão fechado e painel aberto, 1,5 s depois) e `prefers-reduced-motion` sem transição no botão
  B3  presença só em /student: ausente em /student/perfil, na sala do curso, em /catalogo, no /login e em /admin (equipe)
  X1  sem #secao-assistente, sem atalho-assistente, chat-panel com 0 elementos ao abrir a tela; barra com 2 abas + "Meu perfil"
  P1  abrir: role=dialog, rótulo, título "Assistente virtual", fechar, aria-expanded/aria-label trocados, foco no chat-input, ordem
      cabeçalho > mensagens (aria-live) > aviso > formulário, textos de hoje, sem aria-modal
  P2  fechar pelo botão, pelo X e por Esc (do campo e do X): painel sai do DOM, aria-* de volta, foco devolvido ao botão; reabre
  P3  geometria do painel a 1280, 768, 601, 600, 390 e 320 px: dentro da janela (margem >= 8), offsets, largura, acima do botão,
      sem rolagem horizontal da página, nada cobre o painel nem o botão
  P4  formulário sempre visível com muitas mensagens (10 trocas pelo Groq falso): campo e Enviar dentro do painel e da janela, a área
      de mensagens rola, o painel não passa da altura máxima, a 1280, 390 e 320 px
  P5  o histórico (mensagens, fonte, aviso de PII, ações, feedback) e o recibo sobrevivem a fechar/reabrir (botão, X e Esc) e a trocar
      de aba, sem chamada nova à API; trocar de aba não fecha o painel
  P6  ações `open`: financeiro/cursos selecionam a aba e o painel fica aberto a 1280 mas FECHA a 390; perfil navega; Esc/aba
  P7a o chat funciona de ponta a ponta no painel (Groq falso): resposta, ordem, campo limpo, vazio não envia, corpo só com `message`
  P7b fonte, aviso de PII, feedback (POST com reply_id e rating), ações de matrícula e de WhatsApp dentro do painel
  P7c erro de envio (500 e 429) aparece dentro do painel e o chat continua utilizável
  P8  isolamento (IDOR na tela): a conversa de um aluno não aparece no painel do outro
  A1  contraste AA da tela com o painel aberto e mensagens do aluno e do assistente, fonte, aviso de PII, feedback e ações de abrir e de
      matricular (1280 e 390); o botão do WhatsApp fica em A1b (ver "Escolhas")
  A1b contraste AA do botão "Falar com um atendente" (chat-acao-whatsapp) no painel (1280): hoje é branco sobre #40c351, 2,3:1
  A2  piso de 14 px com o painel aberto (1280 e 390)
  A3  um h1, campo rotulado, alvos >= 44 px (botão, fechar, campo, Enviar, ações, feedback) com o painel aberto
  A4  sem rolagem horizontal a 390 e 320 px com o painel fechado e aberto
  A5  foco visível no fechar, no campo e no Enviar
  A6  sem emoji novo (só 👍 e 👎 do feedback) e sem animação em repouso com mensagens
  C1  o botão não cobre texto nem controle no fim da página (1280, 768, 390, 320 px; Meus cursos, Financeiro e conta vazia), inclusive o
      rodapé da aplicação
  K1  sem erro de console (4xx/5xx de /api, exceção de página) nem diálogo nativo, em todo o arquivo [último]

Escolhas do agente-testes (modo autônomo, D40), registradas no relatório:
  - Tamanhos de janela: 1280x800, 768x1024, 601x800, 600x800, 390x844 e 320x568 (altura típica de cada aparelho).
  - "Ícone branco": toda tinta (fill ou stroke) das formas do SVG é branca ou igual ao fundo do botão (detalhes vazados), com pelo
    menos uma branca; contraste do branco contra o fundo >= 3:1.
  - Foco visível = `:focus-visible` com outline (estilo != none, >= 2 px) OU com `box-shadow` DIFERENTE do de repouso (o botão tem sombra
    própria, então uma sombra igual à de repouso não conta).
  - Esc é medido com o foco DENTRO do painel (campo e botão de fechar); com o foco fora do painel o contrato não diz nada.
  - A ação `open` a <= 600 px fecha o painel; não se afirma onde fica o foco depois (o contrato não diz).
  - O texto digitado e ainda não enviado não faz parte do histórico que "sobrevive" (o contrato lista mensagens, fontes, ações,
    feedback e recibo).
  - "Não cobre conteúdo": retângulos de texto (nós de texto visíveis, cortados pelos ancestrais com overflow) e de controles (a[href],
    button, input, select, textarea, [role=button]) que intersectam o botão em mais de 1 px nas duas direções, só com o painel fechado.
  - Altura do painel com muitas mensagens: só se exige que NÃO passe da máxima (calc(100vh - 112px), ou - 100px a <= 600 px); o contrato
    não diz que ele a atinja (a área de mensagens pode ter altura máxima própria). O z-index do painel também não é medido (o contrato só
    dá o do botão); mede-se que nada o cubra.
  - A janela de apenas 420 px de altura não é medida (o contrato fala de 1280, 768, 390 e 320 px).
  - O botão do WhatsApp (`btn-whatsapp`, D93: branco sobre #40c351 = 2,3:1) já viola o AA da D115 hoje, mas nenhum teste antigo o media
    (o chat medido nunca tinha ação de WhatsApp). Como a D115 (maior número) vale sobre a D93, o AA do painel o inclui; ficou num teste
    PRÓPRIO (A1b) para o orquestrador ou o PM poderem dispensá-lo sem mexer em A1, se preferirem manter o #40c351 com texto branco.

Execução (de frontend/e2e): PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 -m pytest test_r3d_assistente_flutuante.py -s
"""

import contextlib
import json
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_assistente_flutuante import abrir_assistente  # noqa: E402
from apoio_contraste import descrever, fontes_abaixo_de, razao_contraste, varrer_contraste  # noqa: E402
from apoio_harness_h1 import ambiente_isolado  # noqa: E402
from servidor_e2e_e7 import TEXTO_RESPOSTA as RESPOSTA_DO_DUBLE  # noqa: E402  ("Resposta fixa do dublê e7.")
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402
from test_ds1_componentes_angular import _JS_MEDIR  # noqa: E402
from test_ds2_area_aluno_angular import SENHA, _JS_UTIL, _api  # noqa: E402
from test_r3c_area_aluno_abas_cartoes import (  # noqa: E402
    SEL_ABA, SEL_BARRA, _abas_existem, _ir_para_aba, _norm, _pedir_acao, _r, _rota_chat, _violacoes_estado_abas,
    _violacoes_indicador, _violacoes_na_vista, _violacoes_paineis, semear,
)

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
BOTAO = '[data-testid="assistente-botao"]'
PAINEL = '[data-testid="chat-panel"]'
FECHAR = '[data-testid="assistente-fechar"]'
ALTURAS = {1280: 800, 768: 1024, 601: 800, 600: 800, 390: 844, 320: 568}
LARGURAS_PAINEL = (1280, 768, 601, 600, 390, 320)
LARGURAS_COBERTURA = (1280, 768, 390, 320)
FUNDO_BOTAO = "rgb(31, 157, 58)"  # #1f9d3a
BRANCO = "rgb(255, 255, 255)"
ROTULO_FECHADO = "Abrir o chat com o assistente"
ROTULO_ABERTO = "Fechar o chat com o assistente"
TITULO = "Assistente virtual"
VAZIO_CHAT = "Nenhuma mensagem ainda. Pergunte algo ao assistente."
AVISO_GRAVACAO = ("As conversas com o assistente são gravadas para melhorar o atendimento. "
                  "Não envie dados sensíveis (documentos, cartões, senhas).")
FONTE = "Cancelamento e reembolso"
REPLY_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
WHATSAPP = "https://wa.me/5511999999999"
CORPO_RICO = {
    "status": "success", "message": "Resposta controlada da R3D com fonte, aviso e ações", "reply_id": REPLY_ID,
    "sources": [{"title": FONTE}], "pii_masked": True,
    "actions": [{"type": "open", "target": "financeiro", "label": "Abrir Financeiro R3D"},
                {"type": "enroll", "course_id": "curso-r3d", "class_id": None, "label": "Matricular no curso R3D"},
                {"type": "handoff", "url": WHATSAPP, "label": "Falar com um atendente R3D"}],
}
TEXTO_LONGO = ("Quero entender como funciona o cancelamento, o reembolso, o certificado e a turma do curso, com todos os detalhes "
               "possíveis, porque preciso decidir ainda hoje e quero ter certeza de cada passo do processo. ") * 2


class Falha(Exception):
    pass


def _exigir(violacoes, resumo):
    if violacoes:
        raise Falha(f"{len(violacoes)} violação(ões) de {resumo}:\n" + "\n".join(f"- {v}" for v in violacoes))


# ------------------------------------------------------------------------------------------------- medidores (JS)
_JS_BOTAO = _JS_UTIL + r"""
() => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const out = {};
  const porId = document.querySelectorAll('#assistente-btn');
  const porTid = document.querySelectorAll('[data-testid="assistente-botao"]');
  out.nId = porId.length; out.nTid = porTid.length;
  const b = porTid[0];
  out.mesmo = !!(b && porId[0] === b);
  out.janela = { w: document.documentElement.clientWidth, h: window.innerHeight };
  if (!b) return out;
  const cs = getComputedStyle(b), r = b.getBoundingClientRect();
  out.tag = b.tagName.toLowerCase(); out.tipo = b.getAttribute('type');
  out.aria = { controls: b.getAttribute('aria-controls'), expanded: b.getAttribute('aria-expanded'), label: b.getAttribute('aria-label') };
  out.pos = cs.position; out.zIndex = cs.zIndex; out.fundo = cs.backgroundColor; out.sombra = cs.boxShadow; out.raio = cs.borderTopLeftRadius;
  out.opacidade = cs.opacity; out.visibilidade = cs.visibility; out.display = cs.display;
  out.rect = R(b);
  out.direita = out.janela.w - r.right; out.baixo = out.janela.h - r.bottom;
  out.texto = norm(b.innerText);
  const svgs = b.querySelectorAll('svg');
  out.nSvg = svgs.length;
  out.estranhos = b.querySelectorAll('img, picture, canvas, video, iframe, i, object, embed').length;
  out.classesFonte = Array.from(b.querySelectorAll('*')).flatMap(e => Array.from(e.classList)).filter(c => /^(fa|fas|far|fab|bi|mdi|material|icon)([-_ ]|$)/.test(c));
  out.refExterna = Array.from(b.querySelectorAll('use')).map(u => u.getAttribute('href') || u.getAttribute('xlink:href') || '').filter(h => /^(https?:)?\/\//.test(h));
  const svg = svgs[0];
  if (svg) {
    const formas = Array.from(svg.querySelectorAll('path, circle, rect, line, polyline, polygon, ellipse'));
    const tintas = [];
    let semTinta = 0, comGradiente = [];
    for (const f of formas) {
      const c = getComputedStyle(f);
      let tinta = false;
      if (c.fill && c.fill !== 'none') {
        if (/^url\(/.test(c.fill)) comGradiente.push(c.fill);
        else if (alfa(c.fill) > 0) { tintas.push(c.fill); tinta = true; }
      }
      if (c.stroke && c.stroke !== 'none' && (parseFloat(c.strokeWidth) || 0) > 0) {
        if (/^url\(/.test(c.stroke)) comGradiente.push(c.stroke);
        else if (alfa(c.stroke) > 0) { tintas.push(c.stroke); tinta = true; }
      }
      if (!tinta) semTinta++;
    }
    out.svg = { ariaHidden: svg.getAttribute('aria-hidden'), rect: R(svg), nFormas: formas.length, tintas: Array.from(new Set(tintas)),
                semTinta, comGradiente, visivel: svg.getBoundingClientRect().width > 1, fillSvg: getComputedStyle(svg).fill };
  }
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const topo = document.elementFromPoint(cx, cy);
  out.topoNoCentro = !!(topo && (topo === b || b.contains(topo)));
  out.topoDesc = topo ? desc(topo) : null;
  return out;
}
"""

_JS_PAINEL = _JS_UTIL + r"""
() => {
  const R = el => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
  const out = {};
  const porId = document.querySelectorAll('#assistente-painel');
  const porTid = document.querySelectorAll('[data-testid="chat-panel"]');
  out.nId = porId.length; out.nTid = porTid.length; out.mesmo = !!(porTid[0] && porId[0] === porTid[0]);
  const W = document.documentElement.clientWidth, H = window.innerHeight;
  out.janela = { w: W, h: H }; out.docW = document.documentElement.scrollWidth;
  const btn = document.querySelector('[data-testid="assistente-botao"]');
  out.botao = btn ? R(btn) : null;
  const p = porTid[0];
  if (!p) return out;
  const cs = getComputedStyle(p), r = p.getBoundingClientRect();
  out.tag = p.tagName.toLowerCase(); out.role = p.getAttribute('role'); out.label = p.getAttribute('aria-label'); out.modal = p.getAttribute('aria-modal');
  out.pos = cs.position; out.zIndex = cs.zIndex; out.rect = R(p); out.direita = W - r.right; out.baixo = H - r.bottom;
  out.overflowX = cs.overflowX; out.overflowY = cs.overflowY;
  out.scrollW = p.scrollWidth; out.clientW = p.clientWidth; out.scrollH = p.scrollHeight; out.clientH = p.clientHeight;
  out.titulos = Array.from(p.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')).map(h => ({ tag: h.tagName.toLowerCase(), texto: norm(h.innerText), rect: R(h) }));
  const f = p.querySelectorAll('[data-testid="assistente-fechar"]');
  out.fechar = { n: f.length, tag: f[0] ? f[0].tagName.toLowerCase() : null, tipo: f[0] ? f[0].getAttribute('type') : null,
                 label: f[0] ? f[0].getAttribute('aria-label') : null, rect: f[0] ? R(f[0]) : null };
  out.live = Array.from(p.querySelectorAll('[aria-live]')).map(e => { const c = getComputedStyle(e);
    return { valor: e.getAttribute('aria-live'), rect: R(e), overflowY: c.overflowY, scrollH: e.scrollHeight, clientH: e.clientHeight,
             nMsg: e.querySelectorAll('[data-testid="chat-message"]').length, texto: norm(e.innerText).slice(0, 90) }; });
  const q = id => p.querySelector(`[data-testid="${id}"]`);
  const ret = (el, extra) => el ? { rect: R(el), visivel: visivel(el), ...(extra ? extra(el) : {}) } : null;
  out.aviso = ret(q('chat-aviso-gravacao'), e => ({ texto: norm(e.innerText) }));
  out.campo = ret(q('chat-input'), e => ({ label: e.getAttribute('aria-label'), placeholder: e.getAttribute('placeholder'), tag: e.tagName.toLowerCase() }));
  out.enviar = ret(q('chat-send'), e => ({ texto: norm(e.innerText), desabilitado: e.disabled === true }));
  out.vazio = Array.from(p.querySelectorAll('*')).some(e => norm(e.innerText) === 'Nenhuma mensagem ainda. Pergunte algo ao assistente.');
  out.nMsg = p.querySelectorAll('[data-testid="chat-message"]').length;
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const topo = document.elementFromPoint(cx, cy);
  out.topoNoCentro = !!(topo && p.contains(topo));
  out.topoDesc = topo ? desc(topo) : null;
  out.fora = Array.from(p.querySelectorAll('*')).filter(e => visivel(e) && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1))
    .slice(0, 5).map(e => desc(e));
  return out;
}
"""

_JS_ESTADO_CHAT = _JS_UTIL + r"""
() => {
  const q = s => Array.from(document.querySelectorAll(s));
  return {
    mensagens: q('[data-testid="chat-message"]').map(e => ({ papel: e.getAttribute('data-role'), texto: norm(e.innerText) })),
    fontes: q('[data-testid="chat-fonte"]').map(e => norm(e.innerText)),
    avisos: q('[data-testid="chat-aviso-pii"]').map(e => norm(e.innerText)),
    abrir: q('[data-testid="chat-acao-abrir"]').map(e => norm(e.innerText)),
    matricular: q('[data-testid="chat-acao-matricular"]').map(e => norm(e.innerText)),
    whatsapp: q('[data-testid="chat-acao-whatsapp"]').map(e => ({ texto: norm(e.innerText), href: e.getAttribute('href') })),
    feedback: ['up', 'down'].map(k => q(`[data-testid="chat-feedback-${k}"]`).map(e => ({ pressionado: e.getAttribute('aria-pressed'), desabilitado: e.disabled === true }))),
  };
}
"""

_JS_FOCO = r"""
(sel) => {
  const e = document.querySelector(sel);
  if (!e) return null;
  const c = getComputedStyle(e);
  const m = (c.outlineColor || '').match(/rgba?\(([^)]+)\)/);
  const partes = m ? m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat) : [0, 0, 0, 1];
  return { match: e.matches(':focus-visible'), estilo: c.outlineStyle, largura: parseFloat(c.outlineWidth) || 0, cor: c.outlineColor,
           alfa: partes.length > 3 ? partes[3] : 1, sombra: c.boxShadow, ativo: document.activeElement === e };
}
"""

_JS_ATIVO = r"""
() => { const a = document.activeElement; return a && a !== document.body ? { tid: a.getAttribute('data-testid'), id: a.id, tag: a.tagName.toLowerCase() } : null; }
"""

_JS_ANIMACOES = _JS_UTIL + r"""
() => document.getAnimations().filter(a => a.playState === 'running').map(a => {
  const alvo = a.effect && a.effect.target;
  return `${a.constructor.name} ${a.animationName || a.transitionProperty || ''} em ${alvo ? desc(alvo) : '?'}`;
})
"""

# Texto e controles que o botão cobre (painel fechado). Retângulos cortados pelos ancestrais com overflow.
_JS_COBERTURA = _JS_UTIL + r"""
() => {
  const btn = document.querySelector('[data-testid="assistente-botao"]');
  const out = { semBotao: !btn, cobertos: [], textosVerificados: 0, controlesVerificados: 0, rodape: { existe: false, textos: 0 } };
  if (!btn) return out;
  const br = btn.getBoundingClientRect();
  out.botao = { l: br.left, t: br.top, r: br.right, b: br.bottom };
  out.janela = { w: document.documentElement.clientWidth, h: window.innerHeight };
  out.rolagem = window.scrollY; out.docH = document.documentElement.scrollHeight;
  const cortar = (el, rect) => {
    let r = { l: rect.left, t: rect.top, r: rect.right, b: rect.bottom };
    for (let a = el; a && a !== document.documentElement; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return null;
      if (a !== el && (cs.overflowX !== 'visible' || cs.overflowY !== 'visible')) {
        const ar = a.getBoundingClientRect();
        r = { l: Math.max(r.l, ar.left), t: Math.max(r.t, ar.top), r: Math.min(r.r, ar.right), b: Math.min(r.b, ar.bottom) };
      }
    }
    return (r.r - r.l >= 1 && r.b - r.t >= 1) ? r : null;
  };
  const cobre = r => (Math.min(r.r, br.right) - Math.max(r.l, br.left)) > 1 && (Math.min(r.b, br.bottom) - Math.max(r.t, br.top)) > 1;
  const rodape = document.querySelector('[data-testid="app-footer"]');
  out.rodape.existe = !!rodape;
  const ign = el => !!el.closest('script, style, noscript, template, svg') || btn.contains(el);
  const andador = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = andador.nextNode(); n; n = andador.nextNode()) {
    const texto = (n.textContent || '').trim();
    const pai = n.parentElement;
    if (!texto || !pai || ign(pai)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    for (const rc of range.getClientRects()) {
      const r = cortar(pai, rc);
      if (!r) continue;
      out.textosVerificados++;
      if (rodape && rodape.contains(pai)) out.rodape.textos++;
      if (cobre(r)) out.cobertos.push(`texto ${JSON.stringify(texto.slice(0, 40))} em ${desc(pai)} [${Math.round(r.l)},${Math.round(r.t)} -> ${Math.round(r.r)},${Math.round(r.b)}]`);
    }
  }
  for (const el of document.querySelectorAll('a[href], button, input:not([type="hidden"]), select, textarea, [role="button"]')) {
    if (ign(el)) continue;
    const r = cortar(el, el.getBoundingClientRect());
    if (!r) continue;
    out.controlesVerificados++;
    if (cobre(r)) out.cobertos.push(`controle ${desc(el)} '${norm(el.innerText || el.value || el.getAttribute('aria-label') || '').slice(0, 30)}' [${Math.round(r.l)},${Math.round(r.t)} -> ${Math.round(r.r)},${Math.round(r.b)}]`);
  }
  return out;
}
"""


# ------------------------------------------------------------------------------------------------- sessão (navegador)
class Sessao:
    """Contextos do Chromium por (conta, largura, altura, movimento): o login é feito uma vez; cada teste abre uma página nova."""

    def __init__(self, browser, spa, seed):
        self.browser, self.spa, self.seed = browser, spa, seed
        self.contextos = {}
        self.erros = []
        self.dialogos = []

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

    def _novo_contexto(self, largura, altura, reduzido):
        ctx = self.browser.new_context(viewport={"width": largura, "height": altura}, locale="pt-BR",
                                       reduced_motion="reduce" if reduzido else "no-preference", accept_downloads=True)
        ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        return ctx

    def _entrar(self, page, email, senha=SENHA, destino="**/student"):
        page.goto(self.spa["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url(destino, timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a {destino} (URL {page.url})")
        page.wait_for_load_state("networkidle")

    def _contexto(self, conta, largura, altura, reduzido):
        chave = (conta, largura, altura, reduzido)
        if chave not in self.contextos:
            ctx = self._novo_contexto(largura, altura, reduzido)
            page = ctx.new_page()
            self._anexar(page)
            self._entrar(page, self.conta(conta)["email"])
            page.close()
            self.contextos[chave] = ctx
        return self.contextos[chave]

    @contextlib.contextmanager
    def pagina(self, conta, largura=1280, altura=None, reduzido=True, registrar=True, rota="/student",
               espera='[data-testid="secao-cursos"]'):
        altura = altura or ALTURAS.get(largura, 800)
        ctx = self._contexto(conta, largura, altura, reduzido)
        page = ctx.new_page()
        self._anexar(page, registrar)
        try:
            page.goto(self.spa["base"] + rota, wait_until="networkidle")
            page.locator(espera).first.wait_for(state="visible", timeout=TIMEOUT)
            page.mouse.move(1, 1)
            page.wait_for_timeout(450)
            yield page
        finally:
            page.close()

    @contextlib.contextmanager
    def pagina_anonima(self, largura=1280, altura=800):
        ctx = self._novo_contexto(largura, altura, True)
        try:
            page = ctx.new_page()
            self._anexar(page)
            yield page
        finally:
            ctx.close()

    @contextlib.contextmanager
    def pagina_da_equipe(self, largura=1280, altura=800):
        ctx = self._novo_contexto(largura, altura, True)
        try:
            page = ctx.new_page()
            self._anexar(page)
            self._entrar(page, GESTAO_EMAIL, GESTAO_SENHA, destino="**/admin")
            yield page
        finally:
            ctx.close()

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
    with ambiente_isolado("r3d") as ambiente:
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
def _exigir_botao(page):
    n = page.locator(BOTAO).count()
    if n != 1:
        raise Falha(f"[data-testid=assistente-botao] aparece {n} vez(es) em {page.url} (esperado 1): o botão flutuante do "
                    "assistente não existe")


def _abrir(page, espera_ms=350):
    """Abre o painel clicando no botão (sempre pelo clique, para medir a abertura). Falha se o botão ou o painel não existem."""
    _exigir_botao(page)
    page.locator(BOTAO).click(timeout=TIMEOUT)
    try:
        page.locator(PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha("o clique em [data-testid=assistente-botao] não abriu [data-testid=chat-panel]")
    page.wait_for_timeout(espera_ms)


def _ativo(page):
    return page.evaluate(_JS_ATIVO)


def _esperar_ativo(page, tid=None, id_=None, limite_ms=1500):
    """Espera o foco chegar ao elemento (o foco pode ser dado no ciclo seguinte). Devolve o elemento ativo no fim."""
    fim = limite_ms
    ativo = _ativo(page)
    while fim > 0:
        ativo = _ativo(page)
        if ativo and ((tid and ativo["tid"] == tid) or (id_ and ativo["id"] == id_)):
            return ativo
        page.wait_for_timeout(100)
        fim -= 100
    return ativo


def _painel(page):
    return page.evaluate(_JS_PAINEL)


def _responder_chat(page, corpo, status=200):
    """Intercepta o POST /api/student/chat com `corpo` (o GET do histórico segue ao servidor). Devolve o tratador, para desligar."""
    def tratar(rota):
        if rota.request.method == "POST":
            rota.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
        else:
            rota.continue_()
    page.route(_rota_chat, tratar)
    return tratar


def _enviar(page, texto, corpo=None, status=200, esperar_resposta=True):
    """Digita e envia no painel aberto. Com `corpo`, a resposta do servidor é interceptada (não é gravada no servidor)."""
    tratador = _responder_chat(page, corpo, status) if corpo is not None else None
    try:
        antes = page.locator('[data-testid="chat-message"]').count()
        page.locator('[data-testid="chat-input"]').fill(texto, timeout=TIMEOUT)
        with page.expect_response(lambda r: r.request.method == "POST" and _rota_chat(r.url), timeout=TIMEOUT * 2) as info:
            page.locator('[data-testid="chat-send"]').click(timeout=TIMEOUT)
        if esperar_resposta and status == 200:
            page.wait_for_function("n => document.querySelectorAll('[data-testid=\"chat-message\"]').length >= n + 2", arg=antes,
                                   timeout=TIMEOUT * 2)
        return info.value
    finally:
        if tratador:
            page.unroute(_rota_chat, tratador)


def _pagina_com_conversa(sessao, conta, largura):
    """Contexto: página aberta, painel aberto e uma troca controlada (aluno + assistente com fonte, aviso, feedback e ações)."""
    @contextlib.contextmanager
    def _gerar():
        with sessao.pagina(conta, largura) as page:
            _abrir(page)
            _enviar(page, "Quero cancelar o curso, meu CPF é 529.982.247-25", corpo=CORPO_RICO)
            page.wait_for_timeout(300)
            yield page
    return _gerar()


def _foco_visivel(foco, repouso):
    if not foco or not foco["match"]:
        return "o foco por teclado não casa com :focus-visible"
    if foco["estilo"] not in ("none", "hidden") and foco["largura"] >= 2 and foco["alfa"] > 0:
        return None
    if foco["sombra"] != "none" and (not repouso or foco["sombra"] != repouso["sombra"]):
        return None
    return (f"foco sem contorno visível (outline {foco['estilo']} {foco['largura']}px, sombra {foco['sombra']}; "
            f"sombra em repouso {repouso and repouso['sombra']})")


def _medir_foco(page, seletor):
    """Devolve (repouso, foco) do elemento: primeiro sem foco, depois focado por teclado."""
    page.locator(seletor).first.evaluate("e => e.blur()")
    repouso = page.evaluate(_JS_FOCO, seletor)
    page.keyboard.press("Tab")
    page.locator(seletor).first.focus()
    return repouso, page.evaluate(_JS_FOCO, seletor)


def _no_fim_da_pagina(page):
    page.evaluate("window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' })")
    page.wait_for_timeout(400)


# ------------------------------------------------------------------------------------------------- P0
def test_p0_precondicao_do_seed(sessao):
    sessao.exigir_seed()
    esperado = {"marina": 2, "rafael": 2, "bruno": 0, "carla": 5, "sofia": 1, "davi": 2}
    v = []
    for conta, n in esperado.items():
        with sessao.pagina(conta, 1280) as page:
            achados = page.locator('[data-testid="curso-card"]').count()
            if achados != n:
                v.append(f"{conta}: {achados} cartões (esperado {n})")
    st, corpo = _api(sessao.spa["api"], "POST", "/api/token", formulario={"username": sessao.conta("bruno")["email"], "password": SENHA})
    if st != 200:
        v.append(f"login do Bruno pela API: HTTP {st}")
    else:
        st, hist = _api(sessao.spa["api"], "GET", "/api/student/chat/history", token=corpo["access_token"])
        if st != 200 or hist.get("messages") != []:
            v.append(f"histórico do chat do Bruno deveria estar vazio: HTTP {st} {str(hist)[:80]}")
    _exigir(v, "pré-condição do seed")


# ------------------------------------------------------------------------------------------------- B botão
@pytest.mark.parametrize("largura", LARGURAS_PAINEL)
def test_b1_botao_flutuante(sessao, largura):
    r = f"@{largura}px"
    with sessao.pagina("marina", largura) as page:
        m = page.evaluate(_JS_BOTAO)
        if m["nTid"] != 1:
            raise Falha(f"{r}: [data-testid=assistente-botao] aparece {m['nTid']} vez(es) (esperado 1: o botão flutuante não existe)")
        v = []
        if m["nId"] != 1 or not m["mesmo"]:
            v.append(f"{r}: #assistente-btn aparece {m['nId']} vez(es) e {'é' if m['mesmo'] else 'NÃO é'} o assistente-botao (esperado 1, o mesmo)")
        if m["tag"] != "button" or m["tipo"] != "button":
            v.append(f"{r}: deveria ser <button type=\"button\"> (é <{m['tag']} type={m['tipo']!r}>)")
        a = m["aria"]
        if a["controls"] != "assistente-painel":
            v.append(f"{r}: aria-controls={a['controls']!r} (esperado 'assistente-painel')")
        if a["expanded"] != "false":
            v.append(f"{r}: aria-expanded={a['expanded']!r} com o painel fechado (esperado 'false')")
        if a["label"] != ROTULO_FECHADO:
            v.append(f"{r}: aria-label={a['label']!r} (esperado {ROTULO_FECHADO!r})")
        if m["pos"] != "fixed":
            v.append(f"{r}: position={m['pos']!r} (esperado fixed)")
        if m["display"] == "none" or m["visibilidade"] != "visible" or float(m["opacidade"]) < 1:
            v.append(f"{r}: botão não visível (display {m['display']}, visibility {m['visibilidade']}, opacity {m['opacidade']})")
        folga = 16 if largura <= 600 else 28
        if abs(m["direita"] - folga) > 1 or abs(m["baixo"] - folga) > 1:
            v.append(f"{r}: a {m['direita']:.1f}px da borda direita e {m['baixo']:.1f}px da inferior (esperado {folga}px e {folga}px)")
        rc = m["rect"]
        if abs(rc["w"] - 58) > 0.6 or abs(rc["h"] - 58) > 0.6:
            v.append(f"{r}: tamanho {rc['w']:.1f}x{rc['h']:.1f}px (esperado 58x58px)")
        raio = m["raio"]
        circulo = (raio.endswith("%") and float(raio[:-1]) >= 50) or (raio.endswith("px") and float(raio[:-2]) >= 29)
        if not circulo:
            v.append(f"{r}: border-radius {raio!r} (esperado círculo: 50% ou >= 29px)")
        if m["fundo"] != FUNDO_BOTAO:
            v.append(f"{r}: fundo {m['fundo']} (esperado {FUNDO_BOTAO}, #1f9d3a: o #40c351 da landing dá só 2,3:1 com ícone branco)")
        if m["sombra"] in ("none", ""):
            v.append(f"{r}: sem sombra (box-shadow {m['sombra']!r})")
        z = int(m["zIndex"]) if re.fullmatch(r"-?\d+", m["zIndex"] or "") else None
        if z is None or not (10 <= z < 1050):
            v.append(f"{r}: z-index {m['zIndex']!r} (esperado inteiro entre 10 e 1049: acima do conteúdo e abaixo dos modais do Bootstrap)")
        if not m["topoNoCentro"]:
            v.append(f"{r}: no centro do botão há {m['topoDesc']} por cima (nada pode cobrir o botão)")
        if rc["w"] < 44 or rc["h"] < 44:
            v.append(f"{r}: alvo {rc['w']:.0f}x{rc['h']:.0f}px (esperado >= 44px nas duas dimensões)")
        if m["texto"]:
            v.append(f"{r}: o botão tem texto {m['texto']!r} (esperado só o ícone; o nome vem do aria-label)")
        if m["estranhos"] or m["classesFonte"] or m["refExterna"]:
            v.append(f"{r}: ícone não é um SVG desenhado à mão ({m['estranhos']} img/i/canvas..., classes {m['classesFonte']}, "
                     f"use externo {m['refExterna']})")
        if m["nSvg"] != 1:
            v.append(f"{r}: {m['nSvg']} elementos svg dentro do botão (esperado 1)")
        else:
            s = m["svg"]
            if s["ariaHidden"] != "true":
                v.append(f"{r}: svg sem aria-hidden=\"true\" ({s['ariaHidden']!r})")
            if not s["visivel"] or s["rect"]["w"] < 16 or s["rect"]["w"] > 44:
                v.append(f"{r}: svg com {s['rect']['w']:.0f}x{s['rect']['h']:.0f}px (esperado visível, entre 16 e 44 px)")
            if s["nFormas"] < 1:
                v.append(f"{r}: o svg não tem formas desenhadas (path, circle, rect...); o ícone não pode vir de fora")
            if s["comGradiente"]:
                v.append(f"{r}: ícone com gradiente/padrão {s['comGradiente']} (esperado cor sólida branca)")
            tintas = s["tintas"]
            if BRANCO not in tintas:
                v.append(f"{r}: nenhuma tinta branca no ícone (tintas {tintas}): esperado ícone branco")
            for t in tintas:
                if t not in (BRANCO, m["fundo"]):
                    v.append(f"{r}: tinta {t} no ícone (esperado branco; só detalhes vazados na cor do fundo)")
            try:
                razao = razao_contraste(BRANCO, m["fundo"])
                if razao < 3:
                    v.append(f"{r}: contraste do ícone branco sobre {m['fundo']} = {razao:.2f}:1 (D115 pede >= 3:1)")
            except ValueError:
                v.append(f"{r}: fundo {m['fundo']!r} não interpretado")
        repouso, foco = _medir_foco(page, BOTAO)
        problema = _foco_visivel(foco, repouso)
        if problema:
            v.append(f"{r}: botão do assistente: {problema}")
    _exigir(v, f"botão flutuante do assistente a {largura}px")


def test_b2_sem_animacao_em_repouso(sessao):
    v = []
    with sessao.pagina("marina", 1280, reduzido=False) as page:
        _exigir_botao(page)
        page.wait_for_timeout(1500)
        v += [f"botão fechado: {a}" for a in page.evaluate(_JS_ANIMACOES)]
        _abrir(page, espera_ms=1500)
        v += [f"painel aberto: {a}" for a in page.evaluate(_JS_ANIMACOES)]
    with sessao.pagina("marina", 1280, reduzido=True) as page:
        _exigir_botao(page)
        page.locator(BOTAO).hover()
        page.wait_for_timeout(100)
        d = page.evaluate("""() => { const c = getComputedStyle(document.querySelector('[data-testid="assistente-botao"]'));
            return { td: c.transitionDuration, an: c.animationName, ad: c.animationDuration,
                     rodando: document.getAnimations().filter(a => a.playState === 'running').length }; }""")
        if any(t.strip() not in ("0s", "0ms") for t in d["td"].split(",")):
            v.append(f"com prefers-reduced-motion: reduce o botão ainda tem transition-duration {d['td']!r} (esperado 0s)")
        if d["an"] != "none" and not all(t.strip() in ("0s", "0ms") for t in d["ad"].split(",")):
            v.append(f"com prefers-reduced-motion: reduce o botão tem animação {d['an']!r} de {d['ad']!r}")
        if d["rodando"]:
            v.append(f"com prefers-reduced-motion: reduce há {d['rodando']} animação(ões)/transição(ões) rodando depois do hover")
    _exigir(v, "animação em repouso e movimento reduzido")


def test_b3_botao_so_em_student(sessao):
    v = []

    def conferir(page, onde):
        n, painel = page.locator(BOTAO).count(), page.locator("#assistente-painel, " + PAINEL).count()
        if n or painel:
            v.append(f"{onde}: {n} botão(ões) do assistente e {painel} painel(is) (esperado 0: o botão é só de /student)")

    with sessao.pagina("sofia", 1280, rota="/student/perfil", espera='[data-testid="perfil-excluir"]') as page:
        conferir(page, "/student/perfil")
    with sessao.pagina("sofia", 1280, rota="/catalogo", espera='[data-testid="catalogo-card"]') as page:
        conferir(page, "/catalogo")
    with sessao.pagina("sofia", 1280) as page:
        page.locator('[data-testid="curso-entrar"]').first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url(re.compile(r".*/student/curso/\d+$"), timeout=TIMEOUT)
            page.locator('[data-testid="sala-curso"]').wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            v.append(f"a sala do curso não abriu (URL {page.url})")
        else:
            conferir(page, "sala do curso")
        page.go_back()
        page.locator('[data-testid="secao-cursos"]').wait_for(state="visible", timeout=TIMEOUT)
        if page.locator(BOTAO).count() != 1:
            v.append("ao voltar da sala para /student, o botão do assistente não está de volta (esperado 1)")
    with sessao.pagina_anonima() as page:
        page.goto(sessao.spa["base"] + "/login", wait_until="networkidle")
        page.locator("input[name=email]").first.wait_for(state="visible", timeout=TIMEOUT)
        conferir(page, "/login")
    with sessao.pagina_da_equipe() as page:
        page.wait_for_timeout(500)
        conferir(page, "/admin (equipe)")
    _exigir(v, "presença do botão fora de /student")


# ------------------------------------------------------------------------------------------------- X sai da tela
@pytest.mark.parametrize("largura", (1280, 390))
def test_x1_sem_secao_antiga_e_barra_so_com_tres_itens(sessao, largura):
    r = f"@{largura}px"
    v = []
    with sessao.pagina("marina", largura) as page:
        d = page.evaluate(r"""() => {
            const q = s => Array.from(document.querySelectorAll(s));
            const ul = document.querySelector('ul.nav.nav-tabs.gt-abas');
            const itens = ul ? Array.from(ul.querySelectorAll('button, a')).map(e => ({ texto: (e.innerText || '').replace(/\s+/g, ' ').trim(),
                tag: e.tagName.toLowerCase(), aba: e.getAttribute('data-aba'), atual: e.getAttribute('aria-current'),
                ativa: e.classList.contains('active'), tid: e.getAttribute('data-testid') })) : null;
            return { secao: !!document.getElementById('secao-assistente'), atalho: q('[data-testid="atalho-assistente"]').length,
                     painel: q('[data-testid="chat-panel"]').length, painelId: q('#assistente-painel').length,
                     chatTestids: q('[data-testid^="chat-"]').map(e => e.getAttribute('data-testid')),
                     tituloNoDom: q('h1, h2, h3, h4, h5, h6').filter(h => (h.innerText || '').trim() === 'Assistente virtual').length,
                     botoesDeAssistente: q('button, a').filter(e => /assistente/i.test(e.innerText || '') && e.getAttribute('data-testid') !== 'assistente-botao').length,
                     itens };
        }""")
        if d["secao"]:
            v.append(f"{r}: #secao-assistente continua no DOM (a seção sempre visível abaixo do painel das abas deve sair)")
        if d["atalho"]:
            v.append(f"{r}: [data-testid=atalho-assistente] continua na barra de abas ({d['atalho']})")
        if d["painel"] or d["painelId"]:
            v.append(f"{r}: o painel do chat existe no DOM ao abrir a tela ({d['painel']} [data-testid=chat-panel], {d['painelId']} "
                     "#assistente-painel; esperado 0: ele só existe enquanto aberto)")
        if d["chatTestids"]:
            v.append(f"{r}: elementos do chat no DOM com o painel fechado: {sorted(set(d['chatTestids']))} (esperado nenhum chat-*)")
        if d["tituloNoDom"]:
            v.append(f"{r}: o título 'Assistente virtual' está na tela com o chat fechado")
        if d["botoesDeAssistente"]:
            v.append(f"{r}: {d['botoesDeAssistente']} botão(ões)/link(s) com 'Assistente' no texto fora do botão flutuante")
        if d["itens"] is None:
            v.append(f"{r}: a barra {SEL_BARRA} não existe")
        else:
            textos = [i["texto"] for i in d["itens"]]
            if textos != ["Meus cursos", "Financeiro", "Meu perfil"]:
                v.append(f"{r}: a barra de abas tem {textos} (esperado ['Meus cursos', 'Financeiro', 'Meu perfil'])")
            perfil = next((i for i in d["itens"] if i["tid"] == "atalho-perfil"), None)
            if perfil and (perfil["tag"] != "a" or perfil["aba"] is not None or perfil["atual"] not in (None, "false") or perfil["ativa"]):
                v.append(f"{r}: 'Meu perfil' deveria ser <a> sem data-aba, aria-current nem active (é {perfil})")
        v += _violacoes_paineis(page, "cursos", r)
    _exigir(v, f"o que sai da tela a {largura}px")


# ------------------------------------------------------------------------------------------------- P comportamento
def test_p1_abrir_o_painel(sessao):
    v = []
    with sessao.pagina("bruno", 1280) as page:
        _exigir_botao(page)
        page.locator(BOTAO).click(timeout=TIMEOUT)
        try:
            page.locator(PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("o clique em [data-testid=assistente-botao] não fez aparecer [data-testid=chat-panel]")
        page.wait_for_timeout(400)
        p = _painel(page)
        if p["nTid"] != 1 or p["nId"] != 1 or not p["mesmo"]:
            v.append(f"painel: {p['nTid']} [data-testid=chat-panel], {p['nId']} #assistente-painel, mesmo elemento={p['mesmo']} (esperado 1, 1, sim)")
        if p["role"] != "dialog":
            v.append(f"painel com role={p['role']!r} (esperado 'dialog')")
        if p["label"] != "Chat com o assistente":
            v.append(f"painel com aria-label={p['label']!r} (esperado 'Chat com o assistente')")
        if p["modal"] == "true":
            v.append("painel com aria-modal=\"true\" (diálogo não modal: o contrato não afirma aria-modal)")
        if p["pos"] != "fixed":
            v.append(f"painel com position={p['pos']!r} (esperado fixed)")
        titulos = [t for t in p["titulos"] if t["texto"] == TITULO]
        if len(titulos) != 1:
            v.append(f"{len(titulos)} título(s) exatamente {TITULO!r} dentro do painel (headings: {[t['texto'] for t in p['titulos']]})")
        f = p["fechar"]
        if f["n"] != 1:
            v.append(f"[data-testid=assistente-fechar] aparece {f['n']} vez(es) dentro do painel (esperado 1)")
        else:
            if f["tag"] != "button" or f["tipo"] != "button":
                v.append(f"fechar deveria ser <button type=\"button\"> (é <{f['tag']} type={f['tipo']!r}>)")
            if f["label"] != "Fechar o chat":
                v.append(f"fechar com aria-label={f['label']!r} (esperado 'Fechar o chat')")
        b = page.evaluate(_JS_BOTAO)
        if b["aria"]["expanded"] != "true":
            v.append(f"com o painel aberto o botão tem aria-expanded={b['aria']['expanded']!r} (esperado 'true')")
        if b["aria"]["label"] != ROTULO_ABERTO:
            v.append(f"com o painel aberto o botão tem aria-label={b['aria']['label']!r} (esperado {ROTULO_ABERTO!r})")
        ativo = _esperar_ativo(page, tid="chat-input")
        if not ativo or ativo["tid"] != "chat-input":
            v.append(f"depois de abrir, o foco está em {ativo} (esperado [data-testid=chat-input])")
        # Estrutura de cima para baixo: cabeçalho (título + fechar) > mensagens rolável aria-live > aviso > formulário.
        lives = [x for x in p["live"] if x["valor"] == "polite"]
        if len(lives) != 1:
            v.append(f"{len(lives)} região(ões) aria-live=\"polite\" dentro do painel (esperado 1: a área de mensagens; todas: {p['live']})")
        elif not p["aviso"] or not p["campo"] or not p["enviar"]:
            v.append(f"faltam peças: aviso={bool(p['aviso'])}, campo={bool(p['campo'])}, enviar={bool(p['enviar'])}")
        else:
            msgs = lives[0]["rect"]
            if titulos and f["rect"] and (titulos[0]["rect"]["b"] > msgs["t"] + 1 or f["rect"]["b"] > msgs["t"] + 1):
                v.append(f"o cabeçalho (título {_r(titulos[0]['rect'])}, fechar {_r(f['rect'])}) não está acima da área de mensagens {_r(msgs)}")
            if msgs["b"] > p["aviso"]["rect"]["t"] + 1:
                v.append(f"a área de mensagens {_r(msgs)} não está acima do aviso de gravação {_r(p['aviso']['rect'])}")
            if p["aviso"]["rect"]["b"] > min(p["campo"]["rect"]["t"], p["enviar"]["rect"]["t"]) + 1:
                v.append(f"o aviso de gravação {_r(p['aviso']['rect'])} não está acima do formulário "
                         f"(campo {_r(p['campo']['rect'])}, Enviar {_r(p['enviar']['rect'])})")
            if not p["vazio"] or VAZIO_CHAT not in lives[0]["texto"]:
                v.append(f"a área de mensagens da conta sem conversa deveria mostrar {VAZIO_CHAT!r} ({lives[0]['texto']!r})")
            if p["nMsg"]:
                v.append(f"{p['nMsg']} chat-message na conta sem conversa (esperado 0)")
            if p["aviso"]["texto"] != AVISO_GRAVACAO:
                v.append(f"aviso de gravação {p['aviso']['texto']!r} (esperado o texto de hoje: {AVISO_GRAVACAO!r})")
            c = p["campo"]
            if c["tag"] != "input" or c["label"] != "Digite sua mensagem" or c["placeholder"] != "Digite sua mensagem":
                v.append(f"campo do chat: <{c['tag']}> aria-label={c['label']!r} placeholder={c['placeholder']!r} (esperado input com 'Digite sua mensagem')")
            if p["enviar"]["texto"] != "Enviar":
                v.append(f"botão de envio com o texto {p['enviar']['texto']!r} (esperado 'Enviar')")
            if not p["enviar"]["desabilitado"]:
                v.append("com o campo vazio o botão Enviar deveria estar desabilitado (comportamento de hoje)")
    _exigir(v, "abertura do painel")


def _estado_fechado(page, rotulo):
    v = []
    if page.locator(PAINEL).count() or page.locator("#assistente-painel").count():
        v.append(f"{rotulo}: o painel continua no DOM (esperado 0: existe só enquanto aberto)")
    b = page.evaluate(_JS_BOTAO)
    if b.get("aria", {}).get("expanded") != "false":
        v.append(f"{rotulo}: aria-expanded={b.get('aria', {}).get('expanded')!r} (esperado 'false')")
    if b.get("aria", {}).get("label") != ROTULO_FECHADO:
        v.append(f"{rotulo}: aria-label={b.get('aria', {}).get('label')!r} (esperado {ROTULO_FECHADO!r})")
    ativo = _esperar_ativo(page, tid="assistente-botao")
    if not ativo or ativo["tid"] != "assistente-botao":
        v.append(f"{rotulo}: o foco está em {ativo} (esperado devolvido ao botão do assistente)")
    return v


def test_p2_fechar_e_devolver_o_foco(sessao):
    v = []
    with sessao.pagina("bruno", 1280) as page:
        _exigir_botao(page)
        # (a) clicar de novo no botão
        _abrir(page)
        page.locator(BOTAO).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        v += _estado_fechado(page, "fechar pelo botão")
        # (b) pelo X
        _abrir(page)
        if page.locator(FECHAR).count() != 1:
            raise Falha(f"[data-testid=assistente-fechar] aparece {page.locator(FECHAR).count()} vez(es) com o painel aberto (esperado 1)")
        page.locator(FECHAR).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        v += _estado_fechado(page, "fechar pelo X")
        # (c) Esc, com o foco no campo
        _abrir(page)
        if (_esperar_ativo(page, tid="chat-input") or {}).get("tid") != "chat-input":
            v.append("antes do Esc: o foco não está no chat-input")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        v += _estado_fechado(page, "Esc com o foco no campo")
        # (d) Esc, com o foco no botão de fechar
        _abrir(page)
        page.locator(FECHAR).focus()
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        v += _estado_fechado(page, "Esc com o foco no botão de fechar")
        # reabre depois de fechar
        _abrir(page)
        if page.locator(PAINEL).count() != 1:
            v.append("depois de fechar, o painel não abre de novo")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # Esc com o painel fechado não faz nada (nem erro)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        if page.locator(PAINEL).count():
            v.append("Esc com o painel fechado abriu o painel")
    _exigir(v, "fechar o painel e devolver o foco")


@pytest.mark.parametrize("largura", LARGURAS_PAINEL)
def test_p3_geometria_do_painel(sessao, largura):
    r = f"@{largura}px"
    v = []
    with sessao.pagina("marina", largura) as page:
        _abrir(page)
        p = _painel(page)
        rc, W, H = p["rect"], p["janela"]["w"], p["janela"]["h"]
        movel = largura <= 600
        folga_d, folga_b, desc_max = (16, 84, 100) if movel else (28, 96, 112)
        if p["pos"] != "fixed":
            v.append(f"{r}: position={p['pos']!r} (esperado fixed)")
        for lado, valor, limite in (("esquerda", rc["l"], 8), ("topo", rc["t"], 8), ("direita", W - rc["r"], 8), ("base", H - rc["b"], 8)):
            if valor < limite - 0.01:
                v.append(f"{r}: painel a {valor:.1f}px da borda ({lado}); esperado >= {limite}px. Painel {_r(rc)} em janela {W}x{H}")
        if abs(p["direita"] - folga_d) > 1 or abs(p["baixo"] - folga_b) > 1:
            v.append(f"{r}: painel a {p['direita']:.1f}px da direita e {p['baixo']:.1f}px da base (esperado {folga_d}px e {folga_b}px)")
        esperada = min(360, W - 32)
        if abs(rc["w"] - esperada) > 1:
            v.append(f"{r}: largura {rc['w']:.1f}px (esperado {esperada}px = min(360, 100vw - 32))")
        if rc["h"] > H - desc_max + 1:
            v.append(f"{r}: altura {rc['h']:.1f}px passa do máximo calc(100vh - {desc_max}px) = {H - desc_max}px")
        if p["botao"] and rc["b"] > p["botao"]["t"] + 0.5:
            v.append(f"{r}: o painel {_r(rc)} não fica acima do botão {_r(p['botao'])}")
        if p["docW"] > W + 0.5:
            v.append(f"{r}: rolagem horizontal da página com o painel aberto (scrollWidth {p['docW']}px > {W}px)")
        if p["scrollW"] > p["clientW"] + 1:
            v.append(f"{r}: conteúdo do painel mais largo que o painel (scrollWidth {p['scrollW']} > {p['clientW']})")
        if p["fora"]:
            v.append(f"{r}: elementos fora das bordas do painel: {p['fora']}")
        if not p["topoNoCentro"]:
            v.append(f"{r}: no centro do painel há {p['topoDesc']} por cima (nada pode cobrir o painel)")
        b = page.evaluate(_JS_BOTAO)
        if not b["topoNoCentro"]:
            v.append(f"{r}: com o painel aberto, o botão está coberto por {b['topoDesc']} (precisa ficar clicável para fechar)")
        if page.locator(FECHAR).count() == 1:
            fr = page.locator(FECHAR).bounding_box()
            if fr and (fr["x"] < 0 or fr["y"] < 0 or fr["x"] + fr["width"] > W or fr["y"] + fr["height"] > H):
                v.append(f"{r}: o botão de fechar está fora da janela: {fr}")
    _exigir(v, f"geometria do painel a {largura}px")


@pytest.mark.parametrize("largura", (1280, 390, 320))
def test_p4_formulario_sempre_visivel_com_muitas_mensagens(sessao, largura):
    r = f"@{largura}px"
    v = []
    if largura == 1280:
        with sessao.pagina("davi", 1280) as page:
            _abrir(page)
            for i in range(10):
                _enviar(page, f"({i + 1}/10) {TEXTO_LONGO}")
            if page.locator('[data-testid="chat-message"]').count() < 20:
                raise Falha(f"pré-condição: {page.locator('[data-testid=chat-message]').count()} mensagens depois de 10 trocas (esperado >= 20)")
    with sessao.pagina("davi", largura) as page:
        _abrir(page)
        if page.locator('[data-testid="chat-message"]').count() < 20:
            raise Falha(f"pré-condição: o histórico do Davi tem {page.locator('[data-testid=chat-message]').count()} mensagens "
                        "(esperado >= 20: o P4 a 1280 px envia as 10 trocas e roda primeiro)")
        p = _painel(page)
        rc, W, H = p["rect"], p["janela"]["w"], p["janela"]["h"]
        desc_max = 100 if largura <= 600 else 112
        for nome in ("campo", "enviar"):
            x = p[nome]
            if not x or not x["visivel"]:
                v.append(f"{r}: chat-{'input' if nome == 'campo' else 'send'} não está visível com o painel cheio")
                continue
            xr = x["rect"]
            if xr["l"] < rc["l"] - 1 or xr["r"] > rc["r"] + 1 or xr["t"] < rc["t"] - 1 or xr["b"] > rc["b"] + 1:
                v.append(f"{r}: {nome} {_r(xr)} fora do painel {_r(rc)}")
            if xr["l"] < 0 or xr["t"] < 0 or xr["r"] > W or xr["b"] > H:
                v.append(f"{r}: {nome} {_r(xr)} fora da janela {W}x{H}")
        lives = [x for x in p["live"] if x["valor"] == "polite"]
        if len(lives) != 1:
            v.append(f"{r}: {len(lives)} região(ões) aria-live=polite (esperado 1)")
        else:
            m = lives[0]
            if m["scrollH"] <= m["clientH"] + 2:
                v.append(f"{r}: pré-condição: a área de mensagens não está cheia (scrollHeight {m['scrollH']} <= clientHeight {m['clientH']})")
            elif m["overflowY"] not in ("auto", "scroll"):
                v.append(f"{r}: a área de mensagens tem overflow-y={m['overflowY']!r} (esperado auto ou scroll: ela rola, o painel não estoura)")
            if p["campo"] and m["rect"]["b"] > p["campo"]["rect"]["t"] + 1:
                v.append(f"{r}: a área de mensagens {_r(m['rect'])} invade o formulário {_r(p['campo']['rect'])}")
        if rc["h"] > H - desc_max + 1:
            v.append(f"{r}: o painel cresceu até {rc['h']:.0f}px, passa do máximo de {H - desc_max}px")
        if rc["t"] < 8 or rc["l"] < 8 or W - rc["r"] < 8 or H - rc["b"] < 8:
            v.append(f"{r}: painel {_r(rc)} a menos de 8 px de uma borda da janela {W}x{H}")
        if p["docW"] > W + 0.5:
            v.append(f"{r}: rolagem horizontal da página (scrollWidth {p['docW']}px > {W}px)")
        if p["scrollH"] > p["clientH"] + 1 and p["overflowY"] in ("auto", "scroll"):
            v.append(f"{r}: o PRÓPRIO painel rola ({p['scrollH']} > {p['clientH']}): o formulário pode sair da vista; só a área de mensagens deve rolar")
        # Depois de rolar a área de mensagens ao topo, o formulário continua à vista.
        page.evaluate("() => { for (const e of document.querySelectorAll('[data-testid=\"chat-panel\"] [aria-live]')) e.scrollTop = 0; }")
        page.wait_for_timeout(150)
        depois = _painel(page)
        for nome in ("campo", "enviar"):
            x = depois[nome]
            if not x or x["rect"]["b"] > H or x["rect"]["t"] < 0:
                v.append(f"{r}: com a lista rolada ao topo, {nome} saiu da janela")
    _exigir(v, f"formulário sempre visível com muitas mensagens a {largura}px")


def test_p5_historico_sobrevive_a_fechar_reabrir_e_trocar_de_aba(sessao):
    v = []
    with sessao.pagina("marina", 1280) as page:
        _abas_existem(page)
        _abrir(page)
        feedback = []
        page.route("**/api/student/chat/feedback", lambda rota: (feedback.append(rota.request.post_data),
                                                                 rota.fulfill(status=200, content_type="application/json", body='{"status":"success"}')))
        _enviar(page, "Quero cancelar o curso, meu CPF é 529.982.247-25 (P5)", corpo=CORPO_RICO)
        page.locator('[data-testid="chat-feedback-up"]').last.click(timeout=TIMEOUT)
        page.wait_for_timeout(500)
        base = page.evaluate(_JS_ESTADO_CHAT)
        if not base["fontes"] or not base["avisos"] or not base["abrir"] or not base["matricular"] or not base["whatsapp"]:
            raise Falha(f"pré-condição: a troca controlada não mostrou fonte, aviso e ações no painel: {base}")
        if base["feedback"][0][-1]["pressionado"] != "true":
            raise Falha(f"pré-condição: o 👍 não ficou marcado depois do clique: {base['feedback']}")
        # Recibo aberto no Financeiro (o painel não pode mexer nele). A 1280 px o painel cobre a coluna de ações da tabela:
        # como o aluno faria, ele fecha o painel antes de abrir o recibo.
        page.locator(BOTAO).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        if page.locator(PAINEL).count():
            raise Falha("pré-condição: o clique no botão não fechou o painel (P2 mede isso)")
        _ir_para_aba(page, "financeiro")
        linha = page.locator('[data-testid="secao-financeiro"] tbody tr').filter(
            has=page.locator('[data-testid="pagamento-status"]', has_text="Aprovado")).first
        linha.get_by_role("button", name="Ver recibo").click(timeout=TIMEOUT)
        page.locator(".aluno-recibo").wait_for(state="visible", timeout=TIMEOUT)
        recibo = _norm(page.locator(".aluno-recibo").inner_text())
        chamadas = []
        page.on("request", lambda req: chamadas.append(f"{req.method} {urlsplit(req.url).path}") if "/api/" in req.url else None)

        def conferir(rotulo):
            if page.locator(PAINEL).count() != 1:
                v.append(f"{rotulo}: o painel não está aberto")
                return
            agora = page.evaluate(_JS_ESTADO_CHAT)
            for campo in base:
                if agora[campo] != base[campo]:
                    v.append(f"{rotulo}: {campo} mudou: antes {base[campo]!r}, depois {agora[campo]!r}")

        # Reabre e fecha pelas três formas (o painel começa fechado).
        anterior = "o botão (para abrir o recibo)"
        for como in ("botão", "X", "Esc"):
            _abrir(page)
            conferir(f"depois de fechar por {anterior} e reabrir")
            if como == "botão":
                page.locator(BOTAO).click(timeout=TIMEOUT)
            elif como == "X":
                page.locator(FECHAR).click(timeout=TIMEOUT)
            else:
                page.locator('[data-testid="chat-input"]').focus()
                page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            if page.locator(PAINEL).count():
                v.append(f"fechar pelo {como}: o painel não fechou")
                page.locator(BOTAO).click(timeout=TIMEOUT)
                page.wait_for_timeout(300)
            anterior = como
        _abrir(page)
        conferir(f"depois de fechar pelo {anterior} e reabrir")
        # Trocar de aba com o painel aberto: ele não fecha e o histórico continua.
        for chave in ("cursos", "financeiro"):
            page.locator(f'[data-testid="atalho-{chave}"]').click(timeout=TIMEOUT)
            page.wait_for_timeout(350)
            conferir(f"depois de trocar para a aba {chave} com o painel aberto")
        # Trocar de aba com o painel fechado e reabrir.
        page.locator(BOTAO).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        page.locator('[data-testid="atalho-cursos"]').click(timeout=TIMEOUT)
        page.wait_for_timeout(350)
        page.locator('[data-testid="atalho-financeiro"]').click(timeout=TIMEOUT)
        page.wait_for_timeout(350)
        _abrir(page)
        conferir("depois de trocar de aba com o painel fechado e reabrir")
        # O recibo do Financeiro continua aberto depois de abrir e fechar o painel.
        page.locator(BOTAO).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        if page.locator(".aluno-recibo").count() != 1 or _norm(page.locator(".aluno-recibo").inner_text()) != recibo:
            v.append("o recibo aberto no Financeiro mudou ou sumiu depois de abrir e fechar o painel do assistente")
        page.wait_for_timeout(500)
        if chamadas:
            v.append(f"chamadas à API ao abrir, fechar ou trocar de aba (esperado nenhuma): {chamadas}")
        if len(feedback) != 1:
            v.append(f"{len(feedback)} POST de feedback (esperado 1, o do clique no 👍)")
    _exigir(v, "histórico do chat ao fechar, reabrir e trocar de aba")


@pytest.mark.parametrize("largura", (1280, 390))
def test_p6_acoes_open(sessao, largura):
    r = f"@{largura}px"
    v = []
    movel = largura <= 600
    with sessao.pagina("carla", largura) as page:
        _abas_existem(page)
        # financeiro
        botao = _pedir_acao(page, {"type": "open", "target": "financeiro", "label": "Abrir Financeiro P6"})
        _no_fim_da_pagina(page)
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_estado_abas(page, "financeiro", f"{r} open/financeiro")
        v += _violacoes_paineis(page, "financeiro", f"{r} open/financeiro")
        v += _violacoes_indicador(page, "financeiro", f"{r} open/financeiro")
        v += _violacoes_na_vista(page, '[data-testid="secao-financeiro"]', f"{r} open/financeiro")
        if urlsplit(page.url).path != "/student":
            v.append(f"{r}: a ação open/financeiro trocou a rota para {page.url}")
        aberto = page.locator(PAINEL).count() == 1
        if movel and aberto:
            v.append(f"{r}: com a janela de {largura}px (<= 600) o painel deveria FECHAR depois da ação open/financeiro (ele cobriria a tela)")
        if not movel and not aberto:
            v.append(f"{r}: com a janela de {largura}px (> 600) o painel deveria continuar aberto depois da ação open/financeiro")
        b = page.evaluate(_JS_BOTAO)
        if b["aria"]["expanded"] != ("true" if aberto else "false"):
            v.append(f"{r}: aria-expanded={b['aria']['expanded']!r} não acompanha o estado do painel (aberto={aberto})")
        # cursos (vindo do Financeiro)
        botao = _pedir_acao(page, {"type": "open", "target": "cursos", "label": "Abrir Cursos P6"})
        _no_fim_da_pagina(page)
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        v += _violacoes_estado_abas(page, "cursos", f"{r} open/cursos")
        v += _violacoes_paineis(page, "cursos", f"{r} open/cursos")
        v += _violacoes_indicador(page, "cursos", f"{r} open/cursos")
        v += _violacoes_na_vista(page, '[data-testid="secao-cursos"]', f"{r} open/cursos")
        aberto = page.locator(PAINEL).count() == 1
        if movel and aberto:
            v.append(f"{r}: o painel deveria FECHAR depois da ação open/cursos a {largura}px")
        if not movel and not aberto:
            v.append(f"{r}: o painel deveria continuar aberto depois da ação open/cursos a {largura}px")
        # perfil
        botao = _pedir_acao(page, {"type": "open", "target": "perfil", "label": "Abrir Perfil P6"})
        botao.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student/perfil", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            v.append(f"{r}: a ação open/perfil não levou a /student/perfil (URL {page.url})")
        else:
            if page.locator(BOTAO).count() or page.locator(PAINEL).count():
                v.append(f"{r}: em /student/perfil ainda há botão ou painel do assistente")
    if not movel:
        # Trocar de aba NÃO fecha o painel (a 1280 o painel não cobre a barra de abas).
        with sessao.pagina("carla", largura) as page:
            _abrir(page)
            for chave in ("financeiro", "cursos", "financeiro"):
                page.locator(f'[data-testid="atalho-{chave}"]').click(timeout=TIMEOUT)
                page.wait_for_timeout(350)
                if page.locator(PAINEL).count() != 1:
                    v.append(f"{r}: trocar para a aba {chave} fechou o painel (esperado: continua aberto)")
                    break
    _exigir(v, f"ações open do chat a {largura}px")


def test_p7a_chat_de_ponta_a_ponta_no_painel(sessao):
    v = []
    marca = f"MARCA-SOFIA-R3D-{uuid.uuid4().hex[:6]}"
    with sessao.pagina("sofia", 1280) as page:
        _abrir(page)
        corpos = []
        page.on("request", lambda req: corpos.append((req.method, req.url, req.post_data)) if req.method == "POST" and _rota_chat(req.url) else None)
        antes = page.locator('[data-testid="chat-message"]').count()
        enviar = page.locator('[data-testid="chat-send"]')
        for vazio in ("", "   "):
            page.locator('[data-testid="chat-input"]').fill(vazio)
            if enviar.is_enabled():
                v.append(f"o botão Enviar está habilitado com o campo {vazio!r}")
        resposta = _enviar(page, f"Quais cursos vocês têm? {marca}")
        dados = resposta.json()
        msgs = page.evaluate(_JS_ESTADO_CHAT)["mensagens"][antes:]
        if [m["papel"] for m in msgs] != ["user", "assistant"]:
            v.append(f"papéis das duas mensagens novas {[m['papel'] for m in msgs]} (esperado ['user', 'assistant'])")
        else:
            if marca not in msgs[0]["texto"]:
                v.append("a mensagem do aluno não aparece no painel")
            if msgs[1]["texto"] != RESPOSTA_DO_DUBLE:
                v.append(f"a resposta do assistente não é a do backend de teste: {msgs[1]['texto'][:80]!r} (esperado {RESPOSTA_DO_DUBLE!r})")
        if page.locator('[data-testid="chat-input"]').input_value() != "":
            v.append("o campo não foi limpo depois do envio")
        if dados.get("status") != "success":
            v.append(f"o backend de teste não respondeu com sucesso: {str(dados)[:100]}")
        if len(corpos) != 1:
            v.append(f"{len(corpos)} POST ao chat (esperado 1; o vazio e o espaço não enviam)")
        else:
            corpo = json.loads(corpos[0][2] or "null")
            if not isinstance(corpo, dict) or set(corpo) != {"message"}:
                v.append(f"o POST do chat deve levar só 'message'; levou {sorted(corpo) if isinstance(corpo, dict) else corpo!r}")
            consulta = urlsplit(corpos[0][1]).query
            if "user_id" in consulta or "session_id" in consulta or "student" in consulta:
                v.append(f"identificador de usuário na URL do POST: {corpos[0][1]}")
        # Depois de fechar e reabrir a conversa continua, e depois de recarregar o histórico volta do servidor.
        page.locator(FECHAR).click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        _abrir(page)
        if marca not in page.locator(PAINEL).inner_text():
            v.append("a conversa sumiu do painel depois de fechar e reabrir")
        page.reload(wait_until="networkidle")
        _abrir(page)
        page.wait_for_function("m => document.querySelector('[data-testid=\"chat-panel\"]').innerText.includes(m)", arg=marca, timeout=TIMEOUT)
        if page.locator('[data-testid="chat-message"]').count() < antes + 2:
            v.append("depois de recarregar, o histórico do servidor não voltou ao painel")
    _exigir(v, "chat de ponta a ponta no painel")


def test_p7b_fonte_aviso_feedback_e_acoes_no_painel(sessao):
    v = []
    with sessao.pagina("sofia", 1280) as page:
        _abrir(page)
        feedback = []
        page.route("**/api/student/chat/feedback", lambda rota: (feedback.append((rota.request.method, rota.request.post_data)),
                                                                 rota.fulfill(status=200, content_type="application/json", body='{"status":"success"}')))
        _enviar(page, "Quero cancelar o curso, meu CPF é 529.982.247-25 (P7b)", corpo=CORPO_RICO)
        page.wait_for_timeout(300)
        e = page.evaluate(_JS_ESTADO_CHAT)
        painel = page.locator(PAINEL)
        if e["fontes"] != [f"Fonte: {FONTE}"]:
            v.append(f"chat-fonte {e['fontes']} (esperado ['Fonte: {FONTE}'])")
        if len(e["avisos"]) != 1 or "removemos dados pessoais" not in e["avisos"][0]:
            v.append(f"chat-aviso-pii {e['avisos']} (esperado 1 aviso com 'removemos dados pessoais')")
        if e["abrir"] != ["Abrir Financeiro R3D"]:
            v.append(f"chat-acao-abrir {e['abrir']}")
        if e["matricular"] != ["Matricular no curso R3D"]:
            v.append(f"chat-acao-matricular {e['matricular']}")
        if len(e["whatsapp"]) != 1 or e["whatsapp"][0]["href"] != WHATSAPP or e["whatsapp"][0]["texto"] != "Falar com um atendente R3D":
            v.append(f"chat-acao-whatsapp {e['whatsapp']}")
        else:
            w = page.locator('[data-testid="chat-acao-whatsapp"]')
            if w.get_attribute("target") != "_blank" or not {"noopener", "noreferrer"} <= set((w.get_attribute("rel") or "").split()):
                v.append(f"link do WhatsApp com target={w.get_attribute('target')!r} rel={w.get_attribute('rel')!r} (esperado _blank com noopener noreferrer)")
        # Tudo isso está DENTRO do painel (não solto na página).
        for tid in ("chat-message", "chat-fonte", "chat-aviso-pii", "chat-feedback-up", "chat-feedback-down", "chat-acao-abrir",
                    "chat-acao-matricular", "chat-acao-whatsapp", "chat-aviso-gravacao", "chat-input", "chat-send"):
            total, dentro = page.locator(f'[data-testid="{tid}"]').count(), painel.locator(f'[data-testid="{tid}"]').count()
            if total == 0 or total != dentro:
                v.append(f"[data-testid={tid}]: {total} na página, {dentro} dentro do painel (esperado todos dentro e pelo menos 1)")
        # Feedback.
        up, down = page.locator('[data-testid="chat-feedback-up"]').last, page.locator('[data-testid="chat-feedback-down"]').last
        if not up.is_enabled() or not down.is_enabled():
            v.append("os botões de feedback deveriam estar habilitados antes do clique")
        up.click(timeout=TIMEOUT)
        page.wait_for_timeout(500)
        if len(feedback) != 1 or json.loads(feedback[0][1] or "{}") != {"reply_id": REPLY_ID, "rating": "up"}:
            v.append(f"POST de feedback {feedback} (esperado 1 com {{reply_id, rating: up}})")
        if up.get_attribute("aria-pressed") != "true" or not up.is_disabled() or not down.is_disabled():
            v.append("depois do 👍 o par deveria ficar desabilitado com o 👍 marcado (aria-pressed=true)")
        # Ação de matrícula leva ao catálogo com o curso.
        page.locator('[data-testid="chat-acao-matricular"]').click(timeout=TIMEOUT)
        try:
            page.wait_for_url(re.compile(r".*/catalogo\?.*curso=curso-r3d.*"), timeout=TIMEOUT)
        except sync_api.TimeoutError:
            v.append(f"'Matricular no curso' não levou a /catalogo?curso=curso-r3d (URL {page.url})")
    _exigir(v, "fonte, aviso, feedback e ações no painel")


def test_p7c_erros_de_envio_dentro_do_painel(sessao):
    v = []
    with sessao.pagina("rafael", 1280, registrar=False) as page:
        _abrir(page)
        _enviar(page, "Mensagem com erro 500 (P7c)", corpo={"detail": "erro simulado R3D"}, status=500, esperar_resposta=False)
        page.wait_for_timeout(500)
        alerta = page.locator(PAINEL).locator(".alert-danger")
        if alerta.count() != 1 or "Não foi possível enviar a mensagem. Tente novamente." not in _norm(alerta.first.inner_text()):
            v.append(f"erro 500: o aviso 'Não foi possível enviar a mensagem. Tente novamente.' não está (uma vez) dentro do painel "
                     f"({[_norm(t) for t in alerta.all_inner_texts()]})")
        if page.locator('[data-testid="chat-input"]').input_value() == "":
            v.append("erro 500: o texto digitado foi apagado (esperado preservado para tentar de novo)")
        if not page.locator('[data-testid="chat-send"]').is_enabled():
            v.append("erro 500: o botão Enviar ficou desabilitado")
        _enviar(page, "Mensagem com limite (P7c)", corpo={"message": "Muitas mensagens em pouco tempo. Aguarde um minuto (R3D)."},
                status=429, esperar_resposta=False)
        page.wait_for_timeout(500)
        alerta = page.locator(PAINEL).locator(".alert-danger")
        if alerta.count() != 1 or "Muitas mensagens em pouco tempo. Aguarde um minuto (R3D)." not in _norm(alerta.first.inner_text()):
            v.append(f"erro 429: o aviso do servidor não está dentro do painel ({[_norm(t) for t in alerta.all_inner_texts()]})")
        if page.locator(PAINEL).count() != 1:
            v.append("o painel fechou sozinho com o erro de envio")
    _exigir(v, "erros de envio dentro do painel")


def test_p8_isolamento_entre_alunos(sessao):
    v = []
    carla, rafael = f"MARCA-CARLA-R3D-{uuid.uuid4().hex[:6]}", f"MARCA-RAFAEL-R3D-{uuid.uuid4().hex[:6]}"
    with sessao.pagina("carla", 1280) as page:
        _abrir(page)
        _enviar(page, f"Pergunta da Carla {carla}")
    with sessao.pagina("rafael", 1280) as page:
        _abrir(page)
        _enviar(page, f"Pergunta do Rafael {rafael}")
    for conta, minha, alheia in (("carla", carla, rafael), ("rafael", rafael, carla)):
        with sessao.pagina(conta, 1280) as page:
            _abrir(page)
            page.wait_for_function("m => document.querySelector('[data-testid=\"chat-panel\"]').innerText.includes(m)", arg=minha, timeout=TIMEOUT)
            texto = page.locator(PAINEL).inner_text()
            corpo = page.inner_text("body")
            if alheia in texto or alheia in corpo:
                v.append(f"{conta}: o painel mostra a conversa de outro aluno ({alheia})")
    _exigir(v, "isolamento do chat entre alunos")


# ------------------------------------------------------------------------------------------------- A D115
@pytest.mark.parametrize("largura", (1280, 390))
def test_a1_contraste_aa_do_painel_aberto(sessao, largura):
    v = []
    with _pagina_com_conversa(sessao, "sofia", largura) as page:
        tela = varrer_contraste(page)
        painel = varrer_contraste(page, raiz=PAINEL)
        if painel["verificados"] < 8:
            v.append(f"@{largura}px: só {painel['verificados']} textos do painel verificados (esperado >= 8)")
        # O botão do WhatsApp tem teste próprio (A1b).
        v.extend(f"@{largura}px: {descrever([f], 1)}" for f in tela["falhas"] if "chat-acao-whatsapp" not in f["seletor"])
    _exigir(v, "contraste AA com o painel aberto")


def test_a1b_contraste_aa_do_botao_do_whatsapp(sessao):
    v = []
    with _pagina_com_conversa(sessao, "sofia", 1280) as page:
        if page.locator('[data-testid="chat-acao-whatsapp"]').count() != 1:
            raise Falha("pré-condição: a troca controlada não mostrou o botão do WhatsApp no painel")
        tela = varrer_contraste(page, raiz=PAINEL)
        v.extend(f"@1280px: {descrever([f], 1)} (D115 vale sobre a D93)" for f in tela["falhas"] if "chat-acao-whatsapp" in f["seletor"])
        v.extend(f"@1280px: o botão do WhatsApp não foi medido: {descrever([i], 1)}" for i in tela["ignorados"]
                 if "chat-acao-whatsapp" in i.get("seletor", ""))
    _exigir(v, "contraste AA do botão do WhatsApp")


@pytest.mark.parametrize("largura", (1280, 390))
def test_a2_piso_de_14px_com_o_painel_aberto(sessao, largura):
    v = []
    with _pagina_com_conversa(sessao, "sofia", largura) as page:
        v.extend(f"@{largura}px: {descrever([i], 1)}" for i in fontes_abaixo_de(page, 14))
    _exigir(v, "texto abaixo de 14 px com o painel aberto")


@pytest.mark.parametrize("largura", (1280, 390))
def test_a3_um_h1_campo_rotulado_e_alvos_de_44px(sessao, largura):
    v = []
    r = f"@{largura}px"
    with _pagina_com_conversa(sessao, "sofia", largura) as page:
        d = page.evaluate(_JS_MEDIR)
        if len(d["h1"]) != 1:
            v.append(f"{r}: {len(d['h1'])} h1 visíveis {d['h1']} (esperado 1: o título do painel não é h1)")
        v.extend(f"{r}: campo sem rótulo {c}" for c in d["campos"])
        v.extend(f"{r}: alvo pequeno {a}" for a in d["alvos"])
        alvos = page.evaluate(r"""() => {
            const out = [];
            const alvo = (rotulo, el) => { if (!el) { out.push({ rotulo, falta: true }); return; } const r = el.getBoundingClientRect(); out.push({ rotulo, w: r.width, h: r.height }); };
            alvo('botão do assistente', document.querySelector('[data-testid="assistente-botao"]'));
            alvo('fechar', document.querySelector('[data-testid="assistente-fechar"]'));
            alvo('campo', document.querySelector('[data-testid="chat-input"]'));
            alvo('Enviar', document.querySelector('[data-testid="chat-send"]'));
            for (const t of ['chat-feedback-up', 'chat-feedback-down', 'chat-acao-abrir', 'chat-acao-matricular', 'chat-acao-whatsapp'])
              document.querySelectorAll(`[data-testid="${t}"]`).forEach((el, i) => alvo(`${t}#${i}`, el));
            return out; }""")
        for a in alvos:
            if a.get("falta"):
                v.append(f"{r}: {a['rotulo']} ausente")
            elif a["h"] < 43.99 or (a["rotulo"] != "campo" and a["w"] < 43.99):
                v.append(f"{r}: alvo {a['rotulo']} com {a['w']:.0f}x{a['h']:.0f}px (esperado >= 44px)")
    _exigir(v, "h1, rótulos e alvos de 44 px com o painel aberto")


@pytest.mark.parametrize("largura", (390, 320))
def test_a4_sem_rolagem_horizontal(sessao, largura):
    v = []
    r = f"@{largura}px"
    with sessao.pagina("marina", largura) as page:
        _exigir_botao(page)
        for estado in ("fechado", "aberto"):
            if estado == "aberto":
                _abrir(page)
            d = page.evaluate(_JS_MEDIR)
            fora = "; ".join(d["fora"]) or "nenhum elemento identificado"
            if d["scrollWidth"] > largura:
                v.append(f"{r} com o painel {estado}: scrollWidth {d['scrollWidth']}px (> {largura}). Passam da borda: {fora}")
            elif d["clipaRaiz"] and d["fora"]:
                v.append(f"{r} com o painel {estado}: estouro escondido por overflow-x hidden. Passam da borda: {fora}")
    _exigir(v, f"rolagem horizontal a {largura}px")


def test_a5_foco_visivel_no_fechar_no_campo_e_no_enviar(sessao):
    v = []
    with sessao.pagina("marina", 1280) as page:
        _abrir(page)
        page.locator('[data-testid="chat-input"]').fill("texto para habilitar o Enviar")
        for sel, nome in ((FECHAR, "botão de fechar"), ('[data-testid="chat-input"]', "campo"), ('[data-testid="chat-send"]', "Enviar")):
            if not page.locator(sel).count():
                v.append(f"{nome}: ausente")
                continue
            repouso, foco = _medir_foco(page, sel)
            problema = _foco_visivel(foco, repouso)
            if problema:
                v.append(f"{nome}: {problema}")
    _exigir(v, "foco visível")


def test_a6_sem_emoji_novo_e_sem_animacao_com_mensagens(sessao):
    v = []
    with _pagina_com_conversa(sessao, "sofia", 1280) as page:
        emoji = page.evaluate(r"""() => {
            const p = document.querySelector('[data-testid="chat-panel"]').cloneNode(true);
            p.querySelectorAll('[data-testid^="chat-feedback-"]').forEach(e => e.remove());
            const dentro = (p.innerText || '').match(/\p{Emoji_Presentation}/gu) || [];
            const botao = (document.querySelector('[data-testid="assistente-botao"]').innerText || '').match(/\p{Emoji_Presentation}/gu) || [];
            const feedback = Array.from(document.querySelectorAll('[data-testid^="chat-feedback-"]')).map(e => e.innerText.trim());
            return { dentro, botao, feedback };
        }""")
        if emoji["dentro"] or emoji["botao"]:
            v.append(f"emoji novo no painel ou no botão: {emoji['dentro'] + emoji['botao']} (só os 👍 e 👎 do feedback já existem)")
        if sorted(set(emoji["feedback"])) != ["👍", "👎"]:
            v.append(f"botões de feedback com {emoji['feedback']} (esperado 👍 e 👎, como hoje)")
    with sessao.pagina("marina", 1280, reduzido=False) as page:
        _abrir(page, espera_ms=1500)
        v += [f"animação em repouso com o painel aberto: {a}" for a in page.evaluate(_JS_ANIMACOES)]
    _exigir(v, "emoji novo e animação em repouso")


# ------------------------------------------------------------------------------------------------- C cobertura
@pytest.mark.parametrize("largura", LARGURAS_COBERTURA)
def test_c1_botao_nao_cobre_conteudo_no_fim_da_pagina(sessao, largura):
    v = []
    telas = (("Meus cursos (Carla)", "carla", None), ("Financeiro (Marina)", "marina", "financeiro"), ("conta vazia (Bruno)", "bruno", None))
    for nome, conta, aba in telas:
        with sessao.pagina(conta, largura) as page:
            _exigir_botao(page)
            if aba:
                _ir_para_aba(page, aba)
            _no_fim_da_pagina(page)
            m = page.evaluate(_JS_COBERTURA)
            r = f"{nome} @{largura}px"
            if page.locator(PAINEL).count():
                v.append(f"{r}: o painel deveria estar fechado nesta medida")
            if m["textosVerificados"] < 10:
                v.append(f"{r}: só {m['textosVerificados']} retângulos de texto verificados (medida sem sentido)")
            if not m["rodape"]["existe"] or m["rodape"]["textos"] < 1:
                v.append(f"{r}: o rodapé da aplicação (app-footer) não foi medido (existe={m['rodape']['existe']}, textos={m['rodape']['textos']})")
            if m["cobertos"]:
                v.append(f"{r}: o botão {m['botao']} cobre {len(m['cobertos'])} item(ns): {'; '.join(m['cobertos'][:4])}")
    _exigir(v, f"conteúdo coberto pelo botão no fim da página a {largura}px")


# ------------------------------------------------------------------------------------------------- K1 (último)
def test_k1_sem_erro_de_console_nem_dialogo_nativo(sessao):
    sessao.exigir_seed()
    v = list(sessao.erros)
    v += [f"diálogo nativo (confirm/alert) aberto: {d}" for d in sessao.dialogos]
    _exigir(v, "erro de console (4xx/5xx de /api, exceção de página) ou diálogo nativo em todo o arquivo")
