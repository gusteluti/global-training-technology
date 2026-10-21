"""E2E da F6 na landing estática — o chat mostra o link de WhatsApp da ação `handoff` do servidor (D77).

Contrato de tela (D77): na landing, a ação `handoff` da resposta de POST /api/chat vira o link
[data-testid=chat-acao-whatsapp] com o label `Falar com um atendente no WhatsApp`, `href` = url do servidor
(`https://wa.me/<número>?text=<texto>`), `target=_blank` e `rel` com `noopener` e `noreferrer`. Convive com os botões
de matrícula da D76. Texto do LLM com link de WhatsApp nunca vira link de handoff (os links vêm só de `actions`).

Harness (apoio_harness_f6): backend da F5b com `WHATSAPP_HANDOFF_NUMBER` FABRICADO (5511900000000) e CORS para a
origem do servidor estático; landing servida pelo helper da E6 (`_servidor_da_landing`, BACKEND_URL trocado).
Seed: cursos da F5b (Omega Analytics com turmas, Sigma Design sem turmas).

Cenários (cada um com contexto de navegador próprio):
  L0 pré-condição: o chat da landing responde (eco do dublê) e a pergunta geral não tem link de WhatsApp [passa no red]
  L1 "Quero falar com um atendente": 1 link com label, href wa.me com o texto "os cursos", target e rel
  L2 pedido de atendente sobre Omega: texto "o curso Omega Analytics" e os 3 botões de matrícula continuam
  L3 texto do bot com link wa.me em pergunta sem gatilho: nenhum link de handoff                        [caract.]
  L4 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f6_landing_handoff.py -s
"""

import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f6 import (  # noqa: E402
    LABEL_WHATSAPP, PEDIDO_HUMANO, PEDIDO_HUMANO_CURSO, ambiente_f6, conferir_atributos, conferir_link_whatsapp,
    semear_cursos_f5b,
)
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
SEL_BOT = "#chat-messages .msg-bot"
SEL_MATRICULA = '[data-testid="chat-acao-matricular"]'
SEL_WHATSAPP = '[data-testid="chat-acao-whatsapp"]'
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"
LINK_FALSO = "Fale no https://wa.me/5599999999999?text=oi"


@pytest.fixture(scope="module")
def servidores():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f6("f6_landing", cors_origin=base, angular=False) as ambiente:
        dados = semear_cursos_f5b(ambiente["api"], ambiente["db_path"])
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, landing=base + "/landing_global_training.html", dados=dados)
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
    def __init__(self, browser, servidores):
        self.contexto = browser.new_context()
        self.contexto.route("https://fonts.googleapis.com/**",
                            lambda rota: rota.fulfill(status=200, content_type="text/css", body=""))
        self.contexto.route("https://fonts.gstatic.com/**", lambda rota: rota.abort())
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

    def links(self):
        alvo = self.page.locator(SEL_WHATSAPP)
        return [{"texto": " ".join(alvo.nth(i).inner_text().split()), "href": alvo.nth(i).get_attribute("href"),
                 "target": alvo.nth(i).get_attribute("target"), "rel": alvo.nth(i).get_attribute("rel")}
                for i in range(alvo.count())]

    def matriculas(self):
        return [" ".join(t.split()) for t in self.page.locator(SEL_MATRICULA).all_inner_texts()]

    def fechar(self):
        try:
            self.contexto.close()
        except Exception:
            pass


@pytest.fixture
def visitante(browser, servidores):
    criados = []

    def novo():
        v = Visitante(browser, servidores)
        criados.append(v)
        return v

    try:
        yield novo
    finally:
        for v in criados:
            v.fechar()


def _exigir_link(link, alvo):
    assert link["texto"] == LABEL_WHATSAPP, link
    problema = conferir_link_whatsapp(link["href"], alvo)
    assert not problema, problema
    problema = conferir_atributos(link["target"], link["rel"])
    assert not problema, problema


def test_l0_pre_condicao_chat_responde_sem_link_na_pergunta_geral(servidores, visitante):
    v = visitante()
    dados = v.enviar(PERGUNTA_GERAL)
    assert dados.get("status") == "success", dados
    assert any(PREFIXO_RESPOSTA + PERGUNTA_GERAL in t for t in v.page.locator(SEL_BOT).all_inner_texts())
    assert v.links() == []


def test_l1_pedido_de_atendente_mostra_o_link_do_whatsapp(servidores, visitante):
    v = visitante()
    v.enviar(PEDIDO_HUMANO)
    links = v.links()
    assert len(links) == 1, f"esperava 1 [data-testid=chat-acao-whatsapp], há {len(links)}: {links}"
    _exigir_link(links[0], "os cursos")


def test_l2_pedido_sobre_o_curso_tem_o_curso_no_texto_e_mantem_a_matricula(servidores, visitante):
    v = visitante()
    v.enviar(PEDIDO_HUMANO_CURSO)
    links = v.links()
    assert len(links) == 1, f"esperava 1 link de WhatsApp, há {len(links)}: {links}"
    _exigir_link(links[0], "o curso Omega Analytics")
    assert v.matriculas() == [a["label"] for a in servidores["dados"]["acoes_omega"]], v.matriculas()


def test_l3_link_wa_me_no_texto_do_bot_nao_vira_link_de_handoff(servidores, visitante):
    v = visitante()
    v.enviar(f"{PERGUNTA_GERAL}. {LINK_FALSO}")
    assert any("wa.me/5599999999999" in t for t in v.page.locator(SEL_BOT).all_inner_texts()), \
        "pré-condição: o texto do bot (eco) traz o link"
    assert v.links() == [], "link do texto do bot virou link de handoff"


def test_l4_sem_erros_de_console(servidores, visitante):
    v = visitante()
    v.enviar(PEDIDO_HUMANO)
    v.enviar(PEDIDO_HUMANO_CURSO)
    v.enviar(PERGUNTA_GERAL)
    assert v.erros == [], v.erros
