"""E2E da F5b na landing estática — o chat mostra o botão de matrícula das ações do servidor (D76).

Contrato de tela (D76): na landing, cada ação `enroll` da resposta de POST /api/chat vira o botão
[data-testid=chat-acao-matricular] com o label do servidor, e o botão leva a
`<APP_URL>/login?area=aluno&next=<caminho>`, com `<caminho>` = `/catalogo?curso=<id>&turma=<id>` (sem `turma` quando
`class_id` é nulo) CODIFICADO no parâmetro `next`. Texto do LLM (inclusive link markdown de "matrícula") nunca vira
botão de matrícula: os botões vêm só de `actions`.

Escolha de forma do teste: o botão é um link (<a>) com `href` (o teste lê o atributo, não clica: a aplicação Angular
não está de pé neste e2e). `APP_URL` é a constante da própria landing (lida da página). O `next` é conferido
decodificando a query do `href`; a forma exata da codificação é livre, mas `&turma=` não pode aparecer cru (senão o
`turma` deixaria de fazer parte do `next`).

Harness: backend `servidor_e2e_f5b.py` (D58 + catálogo do bot no diretório temporário + Groq falso que ecoa a última
mensagem) com CORS para a origem do servidor estático; landing servida pelo helper da E6 (`_servidor_da_landing`,
cópia em memória com BACKEND_URL trocado). Seed como no e2e Angular da F5b (Omega com turmas; Sigma sem turmas).

Cenários (cada um com contexto de navegador próprio):
  L0 pré-condição: o chat da landing responde (eco do dublê) e a pergunta geral não tem botão           [passa no red]
  L1 pergunta sobre Omega: 3 botões com os labels exatos, na ordem, e href <APP_URL>/login?area=aluno&next=...
  L2 pergunta sobre Sigma (sem turmas): 1 botão "Matricular no curso" com next=/catalogo?curso=<sigma>
  L3 texto do bot com link markdown de matrícula, em pergunta geral: nenhum botão de matrícula
  L4 texto do bot com link markdown em pergunta sobre Omega: só os 3 botões do servidor, nenhum aponta para o link
  L5 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f5b_landing_chat_turmas.py -s
"""

import sys
import time
import urllib.parse
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import LABEL_CURSO, ambiente_f5b, semear_cursos_f5b  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000
SEL_BOT = "#chat-messages .msg-bot"
SEL_ACAO = '[data-testid="chat-acao-matricular"]'
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
PERGUNTA_OMEGA = "Quais sao as turmas e as datas de Omega Analytics?"
PERGUNTA_SIGMA = "Me conte sobre Sigma Design"
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"
LINK_FALSO = "[Matricular na turma Alfa Noturna](https://evil.example/pagar)"


@pytest.fixture(scope="module")
def servidores():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("f5b_landing", cors_origin=base, angular=False) as ambiente:
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

    def acoes(self):
        botoes = self.page.locator(SEL_ACAO)
        return [(" ".join(botoes.nth(i).inner_text().split()), botoes.nth(i).get_attribute("href"))
                for i in range(botoes.count())]

    def app_url(self):
        return self.page.evaluate("APP_URL")

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


def _exigir_course_agent(servidores, nome_curso, pergunta):
    """Pré-condição: a pergunta chegou ao Course Agent do curso (base de conhecimento dele no prompt do dublê)."""
    import json  # noqa: PLC0415

    linhas = servidores["llm_log"].read_text(encoding="utf-8").splitlines() if servidores["llm_log"].exists() else []
    for linha in linhas:
        mensagens = json.loads(linha)["messages"]
        textos = [m.get("content") or "" for m in mensagens]
        usuarios = [m.get("content") or "" for m in mensagens if m.get("role") == "user"]
        if usuarios and pergunta in usuarios[-1] and any(f"{nome_curso} do e2e F5b" in t for t in textos):
            return
    raise AssertionError(f"pré-condição: a pergunta não foi roteada ao Course Agent de {nome_curso}")


def _caminho(curso_id, class_id):
    return f"/catalogo?curso={curso_id}" + (f"&turma={class_id}" if class_id is not None else "")


def _exigir_href(href, app_url, caminho_esperado):
    assert href, "o botão de matrícula deve ser um link com href"
    partes = urllib.parse.urlsplit(href)
    assert f"{partes.scheme}://{partes.netloc}{partes.path}" == f"{app_url}/login", href
    qs = urllib.parse.parse_qs(partes.query)
    assert qs.get("area") == ["aluno"], f"href sem area=aluno: {href}"
    assert qs.get("next") == [caminho_esperado], f"next={qs.get('next')} (esperado {caminho_esperado!r}): {href}"
    assert set(qs) == {"area", "next"}, f"parâmetros a mais no href (o caminho do next não foi codificado?): {href}"


def test_l0_pre_condicao_chat_da_landing_responde_sem_botao_na_pergunta_geral(servidores, visitante):
    v = visitante()
    dados = v.enviar(PERGUNTA_GERAL)
    assert dados.get("status") == "success", dados
    assert any(PREFIXO_RESPOSTA + PERGUNTA_GERAL in t for t in v.page.locator(SEL_BOT).all_inner_texts())
    assert v.acoes() == []


def test_l1_curso_com_turmas_mostra_botoes_com_label_e_href_de_login(servidores, visitante):
    v = visitante()
    v.enviar(PERGUNTA_OMEGA)
    _exigir_course_agent(servidores, "Omega Analytics", PERGUNTA_OMEGA)
    esperadas = servidores["dados"]["acoes_omega"]
    achadas = v.acoes()
    assert [label for label, _ in achadas] == [a["label"] for a in esperadas], achadas
    app_url = v.app_url()
    for (_, href), acao in zip(achadas, esperadas):
        _exigir_href(href, app_url, _caminho(acao["course_id"], acao["class_id"]))


def test_l2_curso_sem_turmas_mostra_matricular_no_curso(servidores, visitante):
    v = visitante()
    v.enviar(PERGUNTA_SIGMA)
    _exigir_course_agent(servidores, "Sigma Design", PERGUNTA_SIGMA)
    achadas = v.acoes()
    assert [label for label, _ in achadas] == [LABEL_CURSO], achadas
    _exigir_href(achadas[0][1], v.app_url(), _caminho(servidores["dados"]["sigma"]["id"], None))


def test_l3_link_markdown_do_bot_na_pergunta_geral_nao_vira_botao(servidores, visitante):
    v = visitante()
    v.enviar(f"{PERGUNTA_GERAL} {LINK_FALSO}")
    assert any("Matricular na turma Alfa Noturna" in t for t in v.page.locator(SEL_BOT).all_inner_texts()), \
        "pré-condição: o texto do bot (eco) traz o link markdown"
    assert v.acoes() == [], "link do texto do bot virou botão de matrícula"


def test_l4_link_markdown_do_bot_no_curso_nao_vira_botao_nem_muda_os_do_servidor(servidores, visitante):
    v = visitante()
    v.enviar(f"{PERGUNTA_OMEGA} {LINK_FALSO}")
    achadas = v.acoes()
    assert [label for label, _ in achadas] == [a["label"] for a in servidores["dados"]["acoes_omega"]], achadas
    assert all("evil.example" not in (href or "") for _, href in achadas), achadas


def test_l5_sem_erros_de_console(servidores, visitante):
    v = visitante()
    v.enviar(PERGUNTA_OMEGA)
    v.enviar(PERGUNTA_SIGMA)
    v.enviar(PERGUNTA_GERAL)
    assert v.erros == [], v.erros
