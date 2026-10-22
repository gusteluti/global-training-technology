"""E2E da GR2 na landing estática — o texto do bot nunca vira link (D95, PLANO_GR seção GR2, "Landing").

Contrato de tela (PLANO_GR): "o texto do bot deixa de virar link (fim do `linkify` de markdown); só texto escapado".
Os botões de ação da F5b (matrícula) e da F6 (WhatsApp) vêm de `actions` do servidor, não do texto, e continuam
sendo links.

Escolhas de forma do teste (registradas no relatório do agente-testes):
  - "Não vira link": o balão do bot ([#chat-messages .msg-bot], o último) não tem NENHUM elemento <a>, para nenhum
    formato de link no texto (markdown `[texto](url)`, URL crua `https://...`, `www....`, HTML `<a href>`).
  - "Mostra o texto como texto": o texto visível do link markdown ("Pague aqui") e as palavras em volta continuam no
    balão. Se a landing mostra a sintaxe markdown crua ou só o texto do link é livre (o PLANO não fixa).
  - Resposta controlada: L1/L2/L4 interceptam POST /api/chat com `page.route` e devolvem o JSON escolhido pelo teste
    (o backend de teste ecoa a mensagem e, com a GR2, o próprio backend já tira as URLs: sem interceptar, a tela
    não seria exercitada com link no texto). L3 vai pelo backend de teste real (eco) e confere a GR2 ponta a ponta:
    a URL que o usuário escreveu e o eco devolveria não chega ao balão, nem como link nem como texto.

Harness: backend `servidor_e2e_f5b.py` via `apoio_harness_f5b.ambiente_f5b(..., angular=False)` (D58 + catálogo do
bot temporário + Groq falso que ecoa "Resposta simulada do assistente a: <mensagem>"), com CORS para a origem do
servidor estático; landing servida pelo helper da E6 (`_servidor_da_landing`, cópia em memória com BACKEND_URL
trocado). Nenhum curso é semeado (a vitrine fica vazia; o chat não depende dela).

Cenários (cada um com contexto de navegador próprio):
  L0 pré-condição: o chat da landing responde pelo backend de teste (eco)                              [passa no red]
  L1 resposta com link markdown, URL crua e www (interceptada): balão sem <a>, texto do link visível
  L2 mesma resposta com actions enroll + handoff: botões de ação continuam <a> com o href do servidor,
     nenhum aponta para URL do texto do bot                                                            [passa no red]
  L3 ponta a ponta (eco do backend real): a URL escrita pelo usuário não chega ao balão do bot
  L4 HTML no texto do bot (interceptada) aparece escapado: sem <a> nem <img> no balão                  [passa no red]
  L5 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_gr2_landing_links.py -s
"""

import json
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import ambiente_f5b  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
SEL_BOT = "#chat-messages .msg-bot"
SEL_MATRICULA = '[data-testid="chat-acao-matricular"]'
SEL_WHATSAPP = '[data-testid="chat-acao-whatsapp"]'
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"

TEXTO_COM_LINKS = (
    "Finalize agora: [Pague aqui](https://golpe.test/x) e conclua hoje mesmo. "
    "Ou acesse https://exemplo-pix.com/pagar ou www.algo.com para detalhes."
)
HOSTS_DO_TEXTO = ("golpe.test", "exemplo-pix.com", "algo.com")
TEXTO_COM_HTML = (
    'Veja <a href="https://golpe.test/html">clique</a> e <img src="https://golpe.test/i.png" alt="img"> agora.'
)

URL_WA = "https://wa.me/5511900000000?text=Ola"
ACOES = [
    {"type": "enroll", "course_id": "curso_gr2_kappa", "class_id": 7, "label": "Matricular na turma Kappa Manha"},
    {"type": "handoff", "reason": "user_request", "url": URL_WA, "label": "Falar com um atendente no WhatsApp"},
]


@pytest.fixture(scope="module")
def servidores():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("gr2_landing", cors_origin=base, angular=False) as ambiente:
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, origem=base, landing=base + "/landing_global_training.html")
        finally:
            estatico.shutdown()
            estatico.server_close()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


class Visitante:
    def __init__(self, browser, servidores, resposta=None):
        """`resposta`: dict devolvido no lugar de POST /api/chat (interceptado); None vai ao backend de teste."""
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
        if resposta is not None:
            origem = servidores["origem"]
            cabecalhos = {
                "Access-Control-Allow-Origin": origem,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }

            def interceptar(rota):
                if rota.request.method == "OPTIONS":
                    rota.fulfill(status=204, headers=cabecalhos, body="")
                elif rota.request.method == "POST":
                    rota.fulfill(status=200, headers=dict(cabecalhos, **{"Content-Type": "application/json"}),
                                 body=json.dumps(resposta, ensure_ascii=False))
                else:
                    rota.continue_()

            self.contexto.route(f"{servidores['api']}/api/chat", interceptar)
        self.page = self.contexto.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))
        self.page.goto(servidores["landing"], wait_until="networkidle")
        self.page.wait_for_function("typeof sendMsg === 'function'", timeout=TIMEOUT)

    def enviar(self, texto):
        if not self.page.locator("#chat-bubble.open").count():
            self.page.locator("#chat-btn").click(timeout=TIMEOUT)
        campo = self.page.locator("#chat-input")
        campo.fill(texto, timeout=TIMEOUT)
        with self.page.expect_response(
            lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/api/chat"), timeout=TIMEOUT,
        ) as info:
            campo.press("Enter")
        dados = info.value.json()
        fim = time.time() + 8
        while time.time() < fim:
            textos = self.page.locator(SEL_BOT).all_inner_texts()
            if textos and "Processando" not in textos[-1]:
                break
            self.page.wait_for_timeout(100)
        self.page.wait_for_timeout(300)
        return dados

    def balao(self):
        """Último balão do bot."""
        return self.page.locator(SEL_BOT).last

    def links_no_balao(self):
        return self.balao().locator("a").evaluate_all("els => els.map(e => e.outerHTML)")

    def texto_do_balao(self):
        return " ".join(self.balao().inner_text().split())

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


@pytest.fixture
def visitante(browser, servidores):
    criados = []

    def novo(resposta=None):
        v = Visitante(browser, servidores, resposta)
        criados.append(v)
        return v

    try:
        yield novo
    finally:
        for v in criados:
            v.fechar()


def _sucesso(mensagem, actions=None):
    return {"status": "success", "message": mensagem, "session_id": "0" * 32, "actions": actions or [], "sources": []}


def test_l0_pre_condicao_chat_da_landing_responde(servidores, visitante):
    v = visitante()
    dados = v.enviar(PERGUNTA_GERAL)
    assert dados.get("status") == "success", dados
    assert PREFIXO_RESPOSTA + PERGUNTA_GERAL in v.texto_do_balao()


def test_l1_link_no_texto_do_bot_nao_vira_link_clicavel(servidores, visitante):
    v = visitante(_sucesso(TEXTO_COM_LINKS))
    dados = v.enviar(PERGUNTA_GERAL)
    assert dados.get("message") == TEXTO_COM_LINKS, "pré-condição: a resposta interceptada chegou à página"

    links = v.links_no_balao()
    assert links == [], f"o texto do bot virou link no balão (GR2: só texto escapado): {links}"
    texto = v.texto_do_balao()
    for trecho in ("Finalize agora:", "Pague aqui", "conclua hoje mesmo.", "para detalhes."):
        assert trecho in texto, f"o texto do bot deve continuar visível como texto ({trecho!r}): {texto!r}"


def test_l2_botoes_de_actions_continuam_links_do_servidor(servidores, visitante):
    v = visitante(_sucesso(TEXTO_COM_LINKS, ACOES))
    v.enviar(PERGUNTA_GERAL)

    matricula = v.page.locator(SEL_MATRICULA)
    whatsapp = v.page.locator(SEL_WHATSAPP)
    assert matricula.count() == 1, "a ação de matrícula (actions) deve continuar como botão"
    assert whatsapp.count() == 1, "a ação de WhatsApp (actions) deve continuar como botão"
    assert matricula.evaluate("e => e.tagName") == "A" and whatsapp.evaluate("e => e.tagName") == "A"
    assert " ".join(matricula.inner_text().split()) == ACOES[0]["label"]
    assert whatsapp.get_attribute("href") == URL_WA
    href_matricula = matricula.get_attribute("href") or ""
    assert "/login?area=aluno&next=" in href_matricula, href_matricula
    for host in HOSTS_DO_TEXTO:
        assert host not in href_matricula and host not in (whatsapp.get_attribute("href") or "")


def test_l3_ponta_a_ponta_url_escrita_no_chat_nao_chega_ao_balao_do_bot(servidores, visitante):
    v = visitante()
    pergunta = f"{PERGUNTA_GERAL} [Pague aqui](https://golpe.test/x) e https://exemplo-pix.com/pagar"
    dados = v.enviar(pergunta)
    assert dados.get("status") == "success", dados

    assert v.links_no_balao() == [], f"link no balão do bot: {v.links_no_balao()}"
    texto = v.texto_do_balao()
    assert PREFIXO_RESPOSTA in texto, f"pré-condição: o balão é a resposta do eco: {texto!r}"
    for host in ("golpe.test", "exemplo-pix.com"):
        assert host not in texto, f"a URL do texto do bot chegou à tela ({host}): {texto!r}"
        assert host not in (dados.get("message") or ""), f"o backend devolveu a URL ({host}): {dados!r}"


def test_l4_html_no_texto_do_bot_aparece_escapado(servidores, visitante):
    v = visitante(_sucesso(TEXTO_COM_HTML))
    v.enviar(PERGUNTA_GERAL)

    assert v.links_no_balao() == []
    assert v.balao().locator("img").count() == 0, "HTML do texto do bot virou elemento"
    assert "clique" in v.texto_do_balao()


def test_l5_sem_erros_de_console(servidores, visitante):
    v = visitante(_sucesso(TEXTO_COM_LINKS, ACOES))
    v.enviar(PERGUNTA_GERAL)
    v.enviar(PERGUNTA_GERAL)
    assert v.erros == [], v.erros
