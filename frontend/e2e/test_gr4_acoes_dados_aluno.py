"""E2E da GR4 — ações devolvidas pelo servidor para os dados do próprio aluno (D95, PLANO_GR seção GR4).

Contrato de tela (PLANO_GR, GR4, e pedido do orquestrador):
  - Área do aluno (Angular): uma resposta de POST /api/student/chat com `{type: "open", target, label}` mostra um botão
    [data-testid=chat-acao-abrir] com o `label`; o clique leva à seção como os atalhos da D2: `financeiro` ->
    [data-testid=secao-financeiro] (id secao-financeiro), `cursos` -> [data-testid=secao-cursos] (id secao-cursos), sem
    trocar de rota; `perfil` -> /student/perfil (o atalho "Meu perfil" da D2 é um link de rota).
  - Landing: uma resposta de POST /api/chat com `{type: "login", label}` mostra [data-testid=chat-acao-login] que leva
    ao login da Área do aluno em `<APP_URL>/login?area=aluno` (APP_URL da D93, como em addEnrollActions).
  - Ação `open`/`login` com campos estranhos (target fora de financeiro|cursos|perfil, `url`) é ignorada inteira:
    nenhum botão/link para ela e nenhum href externo.

Escolhas de forma do teste (registradas no relatório do agente-testes):
  - "Mesmos atalhos da D2": depois do clique a seção fica na área visível, a URL continua /student e (a) a seção foi o
    alvo de um scrollIntoView (espião instalado com add_init_script) OU (b) a posição de rolagem final é a mesma
    (±4 px) que o atalho da D2 produz para a mesma seção.
  - Área do aluno ignora a ação `login` (o aluno já está logado) e a landing ignora `open` (não tem as seções).
  - O texto do botão é o `label` do servidor (o teste não fixa o rótulo; o backend propõe).
  - Cenários "interceptados" usam page.route (padrão GR1/GR3); os "ponta a ponta" vão ao backend de teste (D58, Groq
    falso que ecoa) e conferem a GR4 inteira: "Meu pagamento foi aprovado?" devolve open/financeiro no aluno e
    LOGIN_NECESSARIO + login no anônimo.

  - Pré-condição da rolagem: com a página no fim (chat), a posição precisa ser diferente da do atalho; por isso o
    aluno é semeado com 8 matrículas pendentes (com pagamento pendente), que deixam Cursos e Financeiro altos.

Harness: `apoio_harness_f5b.ambiente_f5b(..., knowledge={})` (backend D58, catálogo temporário, KNOWLEDGE_DIR vazia).
Angular: `ng serve` com proxy. Landing: servidor estático do helper da E6.

Cenários — Área do aluno (test_gr4_acoes_area_do_aluno):
  A0 pré-condição: pergunta comum sem chat-acao-abrir                                              [passa no red]
  A1 open/financeiro (interceptado): botão com o label; clique rola até secao-financeiro como o atalho da D2
  A2 open/cursos (interceptado): botão; clique rola até secao-cursos como o atalho da D2
  A3 ações estranhas (target fora da lista, url, login no aluno) ignoradas                        [passa no red]
  A4 ponta a ponta: "Meu pagamento foi aprovado?" -> backend devolve open/financeiro -> botão na tela
  A5 open/perfil (interceptado): clique leva a /student/perfil
  A6 sem erros de console de /api nem exceções de página
Cenários — landing (test_gr4_acao_login_landing):
  L0 pré-condição: pergunta comum sem chat-acao-login                                              [passa no red]
  L1 login (interceptado): link chat-acao-login com "Entrar na Área do aluno" e href <APP_URL>/login?area=aluno
  L2 ações estranhas (login com url, open na landing) ignoradas                                     [passa no red]
  L3 ponta a ponta: "Meu pagamento foi aprovado?" -> LOGIN_NECESSARIO no balão e o link de login
  L4 clique no link leva a <APP_URL>/login?area=aluno
  L5 sem erros de console nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_gr4_acoes_dados_aluno.py -s
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import SENHA_ALUNO, ambiente_f5b, semear_aluno  # noqa: E402
from apoio_harness_h1 import abrir_banco  # noqa: E402
from test_e6_landing_chat import _porta_livre, _servidor_da_landing  # noqa: E402
from test_gr3_aviso_pii_chat import Falha, Interceptador, Visitante, _normalizar, _rodar  # noqa: E402

TIMEOUT = 8000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_ABRIR = '[data-testid="chat-acao-abrir"]'
SEL_LOGIN = '[data-testid="chat-acao-login"]'
SEL_LANDING_BOT = "#chat-messages .msg-bot"
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "

LOGIN_NECESSARIO = "Para consultar seus dados (pagamentos, turmas e progresso), entre na Área do aluno."
LABEL_LOGIN = "Entrar na Área do aluno"
PERGUNTA_NEUTRA = "Recomenda leituras introdutorias?"
PERGUNTA_PAGAMENTO = "Meu pagamento foi aprovado?"
MARCA_ESTRANHA = "GR4X"
HOST_ESTRANHO = "evil.gr4.test"

ACOES_ESTRANHAS_ALUNO = [
    {"type": "open", "target": "admin", "label": f"Abrir painel {MARCA_ESTRANHA}"},
    {"type": "open", "target": "financeiro", "label": f"Abrir com url {MARCA_ESTRANHA}",
     "url": f"https://{HOST_ESTRANHO}/x"},
    {"type": "open", "target": f"https://{HOST_ESTRANHO}", "label": f"Abrir externo {MARCA_ESTRANHA}"},
    {"type": "open", "label": f"Sem alvo {MARCA_ESTRANHA}"},
    {"type": "login", "label": f"Entrar {MARCA_ESTRANHA}"},
]
ACOES_ESTRANHAS_LANDING = [
    {"type": "login", "label": f"Entrar {MARCA_ESTRANHA}", "url": f"https://{HOST_ESTRANHO}/login"},
    {"type": "open", "target": "financeiro", "label": f"Abrir financeiro {MARCA_ESTRANHA}"},
]

# Espião: registra o alvo de cada scrollIntoView (id ou data-testid) em window.__gr4Rolagens.
_ESPIAO_ROLAGEM = """
(() => {
  window.__gr4Rolagens = [];
  const original = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (...args) {
    try { window.__gr4Rolagens.push(this.id || this.getAttribute('data-testid') || ''); } catch (e) {}
    return original.apply(this, args);
  };
})();
"""
_VISIVEL_JS = "e => { const r = e.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0; }"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _semear_conteudo(db_path, user_id, quantidade=8):
    """Matrículas pendentes com pagamento pendente: deixa Cursos e Financeiro altos o bastante para que, com a página
    no fim (chat), a seção esteja fora do lugar em que o atalho da D2 a deixa (senão a rolagem não prova nada)."""
    Database = abrir_banco(db_path)
    for i in range(quantidade):
        course_id = f"curso_gr4_e2e_{i}"
        enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:e2e:{i}")
        Database.record_payment(enrollment_id, 100.0 + i, "mercado_pago")


def _resposta(mensagem, acoes):
    return {"status": "success", "message": mensagem, "actions": acoes, "sources": [], "pii_masked": False}


# =========================================================================================
# Área do aluno (Angular)
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_angular():
    with ambiente_f5b("gr4_angular", knowledge={}) as ambiente:
        yield ambiente


def _rota_do_chat_do_aluno(url):
    return urlsplit(url).path.rstrip("/") == "/api/student/chat"


def test_gr4_acoes_area_do_aluno(servidores_angular, browser):
    base = servidores_angular["base"]
    resultados, erros_console, contextos = [], [], []
    estado = {}
    interceptar = Interceptador()

    seed = {"ok": False, "erro": ""}
    try:
        email, uid = semear_aluno(servidores_angular["db_path"], "gr4")
        _semear_conteudo(servidores_angular["db_path"], uid)
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def exigir_seed():
        if not seed["ok"]:
            raise Falha(f"seed falhou: {seed['erro']}")

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 700})
        contextos.append(ctx)
        ctx.add_init_script(_ESPIAO_ROLAGEM)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros_console.append(f"{msg.text[:120]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        page.route(_rota_do_chat_do_aluno, interceptar)
        return page

    def entrar_no_student():
        page = nova_pagina()
        page.goto(base + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA_ALUNO, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /student (URL {page.url})")
        page.wait_for_load_state("networkidle")
        try:
            page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("[data-testid=chat-panel] não está visível em /student")
        return page

    def pagina():
        if "page" not in estado:
            estado["page"] = entrar_no_student()
        return estado["page"]

    def enviar(texto, rotulo, resposta=None, esperado_no_bot=None):
        page = pagina()
        interceptar.resposta = resposta
        try:
            antes = page.locator(SEL_MENSAGEM).count()
            with page.expect_response(
                lambda r: r.request.method == "POST" and _rota_do_chat_do_aluno(r.url), timeout=TIMEOUT * 2,
            ) as info:
                page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
                page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
            dados = info.value.json()
        finally:
            interceptar.resposta = None
        esperado = esperado_no_bot if esperado_no_bot is not None else (resposta or {}).get("message", "")
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and esperado in msgs[-1]["text"]:
                page.wait_for_timeout(400)
                return dados
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def botao_com(label, rotulo):
        page = pagina()
        botoes = page.locator(SEL_ABRIR).filter(has_text=label)
        fim = time.time() + 5
        while time.time() < fim and botoes.count() == 0:
            page.wait_for_timeout(150)
        if botoes.count() == 0:
            raise Falha(f"{rotulo}: nenhum [data-testid=chat-acao-abrir] com o label {label!r}")
        botao = botoes.last
        if not botao.is_visible():
            raise Falha(f"{rotulo}: o botão {label!r} não está visível")
        if _normalizar(botao.inner_text()) != _normalizar(label):
            raise Falha(f"{rotulo}: o botão mostra {botao.inner_text()!r}, esperado o label {label!r}")
        return botao

    def rolagem_do_atalho(atalho):
        """Posição de rolagem em que o atalho da D2 deixa a seção (referência), saindo do topo da página."""
        page = pagina()
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.locator(f'[data-testid="{atalho}"]').first.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        return page.evaluate("window.scrollY")

    def conferir_rolagem(botao, secao_testid, secao_id, atalho, rotulo):
        page = pagina()
        referencia = rolagem_do_atalho(atalho)
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight); window.__gr4Rolagens = [];")
        page.wait_for_timeout(300)
        no_fim = page.evaluate("window.scrollY")
        if abs(no_fim - referencia) <= 4:
            raise Falha(f"{rotulo}: pré-condição: a página é curta demais (fim {no_fim}px = atalho {referencia}px)")
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1300)
        if urlsplit(page.url).path.rstrip("/") != "/student":
            raise Falha(f"{rotulo}: o botão trocou a rota para {page.url} (deveria só rolar, como a D2)")
        secao = page.locator(f'[data-testid="{secao_testid}"]').first
        if not secao.count() or not secao.evaluate(_VISIVEL_JS):
            raise Falha(f"{rotulo}: depois do clique, [data-testid={secao_testid}] não está na área visível")
        alvos = page.evaluate("window.__gr4Rolagens || []")
        rolagem = page.evaluate("window.scrollY")
        if abs(rolagem - referencia) > 4 and secao_id not in alvos and secao_testid not in alvos:
            raise Falha(f"{rotulo}: a rolagem ({rolagem}px, era {no_fim}px) não é a do atalho {atalho} da D2 "
                        f"({referencia}px) e a seção não foi alvo de scrollIntoView (alvos: {alvos})")

    def a0():
        dados = enviar(PERGUNTA_NEUTRA, "A0", esperado_no_bot=PREFIXO_RESPOSTA)
        if [a for a in dados.get("actions", []) if isinstance(a, dict) and a.get("type") == "open"]:
            raise Falha(f"A0: pré-condição: pergunta comum sem ação open ({dados.get('actions')})")
        if pagina().locator(SEL_ABRIR).count():
            raise Falha("A0: resposta sem ação open mostrou [data-testid=chat-acao-abrir]")

    def a1():
        label = "Abrir Financeiro GR4"
        enviar("Meu pagamento foi aprovado? (A1)", "A1",
               _resposta("Resposta interceptada GR4 A1", [{"type": "open", "target": "financeiro", "label": label}]))
        conferir_rolagem(botao_com(label, "A1"), "secao-financeiro", "secao-financeiro", "atalho-financeiro", "A1")
        estado["a1"] = True

    def a2():
        label = "Abrir Cursos GR4"
        enviar("Quando começa minha turma? (A2)", "A2",
               _resposta("Resposta interceptada GR4 A2", [{"type": "open", "target": "cursos", "label": label}]))
        conferir_rolagem(botao_com(label, "A2"), "secao-cursos", "secao-cursos", "atalho-cursos", "A2")

    def a3():
        enviar("Ações estranhas (A3)", "A3", _resposta("Resposta interceptada GR4 A3", ACOES_ESTRANHAS_ALUNO))
        page = pagina()
        page.wait_for_timeout(500)
        estranhos = page.locator(f"{SEL_ABRIR}, {SEL_LOGIN}").filter(has_text=MARCA_ESTRANHA).count()
        if estranhos:
            raise Falha(f"A3: {estranhos} botão(ões) para ação com campos estranhos (deveriam ser ignoradas)")
        if page.locator(f'a[href*="{HOST_ESTRANHO}"]').count():
            raise Falha("A3: a tela criou um link para o host da ação estranha")
        if page.get_by_text(MARCA_ESTRANHA).locator("xpath=ancestor-or-self::button | ancestor-or-self::a").count():
            raise Falha("A3: a tela mostrou um botão/link com o label de uma ação estranha")

    def a4():
        dados = enviar(PERGUNTA_PAGAMENTO, "A4", esperado_no_bot="")
        abertas = [a for a in dados.get("actions", []) if isinstance(a, dict) and a.get("type") == "open"]
        if [a.get("target") for a in abertas] != ["financeiro"]:
            raise Falha(f"A4: o backend devia devolver uma ação open/financeiro, veio {dados.get('actions')}")
        botao_com(abertas[0]["label"], "A4")

    def a5():
        page = pagina()
        if urlsplit(page.url).path.rstrip("/") != "/student":
            page.goto(base + "/student", wait_until="networkidle")
            page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        label = "Abrir Meu perfil GR4"
        enviar("Quero ver meu perfil (A5)", "A5",
               _resposta("Resposta interceptada GR4 A5", [{"type": "open", "target": "perfil", "label": label}]))
        botao_com(label, "A5").click(timeout=TIMEOUT)
        try:
            page.wait_for_url("**/student/perfil", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"A5: open/perfil não levou a /student/perfil (URL {page.url})")

    def a6():
        if erros_console:
            raise Falha(f"A6: erros de console: {erros_console[:3]}")

    try:
        _rodar(resultados, "A0", "pré-condição: pergunta comum sem chat-acao-abrir", a0, exigir_seed)
        _rodar(resultados, "A1", "open/financeiro: botão rola até secao-financeiro (D2)", a1, exigir_seed)
        _rodar(resultados, "A2", "open/cursos: botão rola até secao-cursos (D2)", a2, exigir_seed)
        _rodar(resultados, "A3", "ações com campos estranhos e login no aluno são ignorados", a3, exigir_seed)
        _rodar(resultados, "A4", "ponta a ponta: pagamento -> open/financeiro do backend -> botão", a4, exigir_seed)
        _rodar(resultados, "A5", "open/perfil leva a /student/perfil", a5, exigir_seed)
        _rodar(resultados, "A6", "sem erros de console de /api nem exceções de página", a6)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR4 Área do aluno: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)


# =========================================================================================
# Landing estática
# =========================================================================================

@pytest.fixture(scope="module")
def servidores_landing():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    origem = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("gr4_landing", cors_origin=origem, angular=False, knowledge={}) as ambiente:
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, origem=origem, landing=origem + "/landing_global_training.html")
        finally:
            estatico.shutdown()
            estatico.server_close()


def _sucesso_anonimo(mensagem, acoes):
    return {"status": "success", "message": mensagem, "session_id": "0" * 32, "actions": acoes, "sources": [],
            "pii_masked": False}


def _conferir_href_login(page, link, rotulo):
    app_url = page.evaluate("APP_URL")
    href = link.get_attribute("href") or ""
    partes, base = urlsplit(href), urlsplit(app_url)
    if (partes.scheme, partes.netloc) != (base.scheme, base.netloc) or partes.path != base.path.rstrip("/") + "/login":
        raise Falha(f"{rotulo}: o link de login aponta para {href!r}, esperado {app_url}/login?area=aluno")
    consulta = parse_qs(partes.query)
    if consulta.get("area") != ["aluno"]:
        raise Falha(f"{rotulo}: o link de login não leva à Área do aluno (area={consulta.get('area')})")
    for destino in consulta.get("next", []):
        if not destino.startswith("/") or destino.startswith("//"):
            raise Falha(f"{rotulo}: `next` do link de login não é um caminho interno ({destino!r})")


def test_gr4_acao_login_landing(servidores_landing, browser):
    v = Visitante(browser, servidores_landing)
    v.contexto.route("http://localhost:4200/**",
                     lambda rota: rota.fulfill(status=200, content_type="text/html", body="spa"))
    resultados, estado = [], {}

    def link_login(rotulo):
        links = v.page.locator(SEL_LOGIN).filter(has_text=LABEL_LOGIN)
        fim = time.time() + 5
        while time.time() < fim and links.count() == 0:
            v.page.wait_for_timeout(150)
        if links.count() == 0:
            raise Falha(f"{rotulo}: nenhum [data-testid=chat-acao-login] com {LABEL_LOGIN!r}")
        link = links.last
        if not link.is_visible():
            raise Falha(f"{rotulo}: o link de login não está visível")
        if _normalizar(link.inner_text()) != LABEL_LOGIN:
            raise Falha(f"{rotulo}: o link mostra {link.inner_text()!r}, esperado {LABEL_LOGIN!r}")
        return link

    def l0():
        dados, _ = v.enviar(PERGUNTA_NEUTRA, PREFIXO_RESPOSTA + PERGUNTA_NEUTRA)
        if [a for a in dados.get("actions", []) if isinstance(a, dict) and a.get("type") == "login"]:
            raise Falha(f"L0: pré-condição: pergunta comum sem ação login ({dados.get('actions')})")
        if v.page.locator(SEL_LOGIN).count():
            raise Falha("L0: resposta sem ação login mostrou [data-testid=chat-acao-login]")

    def l1():
        v.enviar("Meu pagamento foi aprovado? (L1)", LOGIN_NECESSARIO,
                 _sucesso_anonimo(LOGIN_NECESSARIO, [{"type": "login", "label": LABEL_LOGIN}]))
        _conferir_href_login(v.page, link_login("L1"), "L1")

    def l2():
        resposta = "Resposta interceptada GR4 L2"
        v.enviar("Ações estranhas (L2)", resposta, _sucesso_anonimo(resposta, ACOES_ESTRANHAS_LANDING))
        v.page.wait_for_timeout(500)
        estranhos = v.page.locator(f"{SEL_LOGIN}, {SEL_ABRIR}").filter(has_text=MARCA_ESTRANHA).count()
        if estranhos:
            raise Falha(f"L2: {estranhos} link(s) para ação com campos estranhos (deveriam ser ignoradas)")
        if v.page.locator(f'a[href*="{HOST_ESTRANHO}"]').count():
            raise Falha("L2: a landing criou um link para o host da ação estranha")
        if v.page.locator(SEL_ABRIR).count():
            raise Falha("L2: a landing mostrou [data-testid=chat-acao-abrir] (não tem as seções da Área do aluno)")

    def l3():
        dados, texto_bot = v.enviar(PERGUNTA_PAGAMENTO, "")
        fim = time.time() + 5
        while time.time() < fim and "Processando" in texto_bot:
            v.page.wait_for_timeout(150)
            texto_bot = (v.page.locator(SEL_LANDING_BOT).all_inner_texts() or [""])[-1]
        if dados.get("message") != LOGIN_NECESSARIO:
            raise Falha(f"L3: o backend devia responder LOGIN_NECESSARIO, veio {dados.get('message')!r}")
        if dados.get("actions") != [{"type": "login", "label": LABEL_LOGIN}]:
            raise Falha(f"L3: o backend devia devolver a ação login, veio {dados.get('actions')}")
        if _normalizar(texto_bot) != LOGIN_NECESSARIO:
            raise Falha(f"L3: o balão do bot mostra {texto_bot!r}")
        _conferir_href_login(v.page, link_login("L3"), "L3")
        estado["l3"] = True

    def l4():
        if v.page.locator(SEL_LOGIN).count() == 0:
            raise Falha("L4 depende de um [data-testid=chat-acao-login] na tela (L1/L3)")
        app_url = v.page.evaluate("APP_URL")
        v.page.locator(SEL_LOGIN).last.click(timeout=TIMEOUT)
        try:
            v.page.wait_for_url(re.compile(re.escape(app_url) + r"/login\?"), timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"L4: o clique não levou a {app_url}/login (URL {v.page.url})")
        if parse_qs(urlsplit(v.page.url).query).get("area") != ["aluno"]:
            raise Falha(f"L4: o login aberto não é o da Área do aluno ({v.page.url})")

    def l5():
        if v.erros:
            raise Falha(f"L5: erros de console: {v.erros[:3]}")

    try:
        _rodar(resultados, "L0", "pré-condição: pergunta comum sem chat-acao-login", l0)
        _rodar(resultados, "L1", "login (interceptado): link para <APP_URL>/login?area=aluno", l1)
        _rodar(resultados, "L2", "login com url e open na landing são ignorados", l2)
        _rodar(resultados, "L3", "ponta a ponta: pedido de dado pessoal -> LOGIN_NECESSARIO + login", l3)
        _rodar(resultados, "L5", "sem erros de console nem exceções de página", l5)
        _rodar(resultados, "L4", "clique no link leva ao login da Área do aluno", l4)
    finally:
        v.fechar()

    falhas = [r for r in resultados if not r[2]]
    print(f"\nGR4 landing: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
