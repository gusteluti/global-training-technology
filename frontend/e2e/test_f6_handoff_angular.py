"""E2E da F6 no Angular — handoff para o WhatsApp no chat do aluno e cartão na observabilidade (D77).

Contrato de tela (D77):
  - no chat do aluno (/student), a ação `handoff` da resposta vira o link [data-testid=chat-acao-whatsapp] com o label
    `Falar com um atendente no WhatsApp`, `href` = url do servidor (`https://wa.me/<número>?text=<texto>`),
    `target=_blank` e `rel` com `noopener` e `noreferrer`; convive com os botões de matrícula da D76;
  - a ação não é persistida (D76): depois de recarregar /student, o histórico volta sem o link;
  - na aba "Observabilidade de IA" de /admin, o cartão "Encaminhamentos ao WhatsApp" mostra o total de
    `handoff.total` da API em [data-testid=ia-handoff-total]; visível para todos os perfis (não é custo).

Harness (apoio_harness_f6): backend da F5b (D58 + catálogo do bot isolado + Groq falso que ecoa) com
`WHATSAPP_HANDOFF_NUMBER` FABRICADO (5511900000000) no processo do backend; `ng serve` em porta livre com proxy.
Seed: cursos da F5b (Omega Analytics com turmas, Sigma Design sem turmas) pela API da Gestão.

Cenários:
  S0 pré-condição: aluno entra, pergunta geral tem resposta e nenhum link de WhatsApp                  [passa no red]
  W1 "Quero falar com um atendente": 1 link chat-acao-whatsapp com label, href wa.me, texto "os cursos", target/rel
  W2 pedido de atendente sobre Omega: link com "o curso Omega Analytics" e os 3 botões de matrícula continuam
  W3 recarregar /student: o histórico volta sem link de WhatsApp (ação não persistida; exige W1)
  O1 Gestão: cartão "Encaminhamentos ao WhatsApp" com ia-handoff-total igual a handoff.total da API (>= 2)
  O2 Suporte: o mesmo cartão com o mesmo total
  K1 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f6_handoff_angular.py -s
"""

import re
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f6 import (  # noqa: E402
    GESTAO_EMAIL, GESTAO_SENHA, LABEL_WHATSAPP, PEDIDO_HUMANO, PEDIDO_HUMANO_CURSO, SENHA_ALUNO, SUPORTE_EMAIL,
    SUPORTE_SENHA, _api, ambiente_f6, conferir_atributos, conferir_link_whatsapp, semear_aluno, semear_cursos_f5b,
)

TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_MATRICULA = '[data-testid="chat-acao-matricular"]'
SEL_WHATSAPP = '[data-testid="chat-acao-whatsapp"]'
SEL_TOTAL = '[data-testid="ia-handoff-total"]'
TITULO_CARTAO = "Encaminhamentos ao WhatsApp"
ABA = "Observabilidade de IA"
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"
CAMINHO_DASHBOARD = "/api/dashboard/observabilidade-ia"


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


@pytest.fixture(scope="module")
def servidores():
    with ambiente_f6("f6_angular") as ambiente:
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _total_da_api(api, email, senha):
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": email, "password": senha})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise Falha(f"login por API de {email} respondeu HTTP {status}")
    status, corpo = _api(api, "GET", CAMINHO_DASHBOARD, token=corpo["access_token"])
    if status != 200:
        raise Falha(f"GET {CAMINHO_DASHBOARD} respondeu HTTP {status}")
    metricas = corpo.get("metrics") or {}
    if "handoff" not in metricas:
        raise Falha("a API ainda não devolve `handoff` no dashboard de observabilidade")
    return metricas["handoff"]["total"]


def test_f6_handoff_angular_e2e(servidores, browser):
    base, api = servidores["base"], servidores["api"]
    resultados, erros_console, contextos = [], [], []
    estado = {}

    seed = {"ok": False, "erro": ""}
    try:
        dados = semear_cursos_f5b(api, servidores["db_path"])
        email_a, _ = semear_aluno(servidores["db_path"], "f6a")
        email_b, _ = semear_aluno(servidores["db_path"], "f6b")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
                erros_console.append(f"{msg.text[:120]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        return page

    def cenario(codigo, nome, funcao):
        try:
            if not seed["ok"]:
                raise Falha(f"seed falhou: {seed['erro']}")
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")

    def login(page, email, senha):
        page.goto(base + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)

    def entrar_no_student(email):
        page = nova_pagina()
        login(page, email, SENHA_ALUNO)
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

    def enviar(page, texto, rotulo):
        antes = page.locator(SEL_MENSAGEM).count()
        page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
        page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and PREFIXO_RESPOSTA in msgs[-1]["text"]:
                page.wait_for_timeout(300)
                return msgs[-1]["text"]
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def esperar_link(page, rotulo):
        fim = time.time() + 8
        while time.time() < fim:
            if page.locator(SEL_WHATSAPP).count() >= 1:
                break
            page.wait_for_timeout(150)
        links = page.locator(SEL_WHATSAPP)
        if links.count() < 1:
            raise Falha(f"{rotulo}: nenhum [data-testid=chat-acao-whatsapp] na tela")
        return links.last

    def conferir(link, alvo, rotulo):
        texto = _normalizar(link.inner_text())
        if texto != LABEL_WHATSAPP:
            raise Falha(f"{rotulo}: label {texto!r} (esperado {LABEL_WHATSAPP!r})")
        problema = conferir_link_whatsapp(link.get_attribute("href"), alvo)
        if problema:
            raise Falha(f"{rotulo}: {problema}")
        problema = conferir_atributos(link.get_attribute("target"), link.get_attribute("rel"))
        if problema:
            raise Falha(f"{rotulo}: {problema}")

    def abrir_aba_ia(email, senha, rotulo):
        page = nova_pagina()
        login(page, email, senha)
        try:
            page.wait_for_url("**/admin", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: login de funcionário não levou a /admin (URL {page.url})")
        page.wait_for_load_state("networkidle")
        try:
            page.locator("ul.nav-tabs button", has_text=ABA).first.click(timeout=TIMEOUT)
            page.get_by_text("Sessões de chat", exact=True).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: a aba '{ABA}' não abriu")
        page.wait_for_load_state("networkidle")
        return page

    def conferir_cartao(email, senha, rotulo):
        page = abrir_aba_ia(email, senha, rotulo)
        try:
            page.get_by_text(TITULO_CARTAO, exact=True).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: o cartão '{TITULO_CARTAO}' não aparece")
        alvo = page.locator(SEL_TOTAL)
        try:
            alvo.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: não existe {SEL_TOTAL} visível")
        if alvo.count() != 1:
            raise Falha(f"{rotulo}: esperava 1 {SEL_TOTAL}, há {alvo.count()}")
        total = _total_da_api(api, email, senha)
        if total < 2:
            raise Falha(f"{rotulo}: pré-condição: a API deveria ter ao menos 2 encaminhamentos (W1, W2), tem {total}")
        mostrado = re.sub(r"\D", "", alvo.first.inner_text())
        if mostrado != str(total):
            raise Falha(f"{rotulo}: {SEL_TOTAL} mostra {alvo.first.inner_text()!r}, a API tem {total}")

    # ---------------------------------------------------------------------------------------

    def s0():
        page = entrar_no_student(email_a)
        estado["a"] = page
        enviar(page, PERGUNTA_GERAL, "S0")
        if page.locator(SEL_WHATSAPP).count() != 0:
            raise Falha("S0: pergunta geral mostrou link de WhatsApp")

    def w1():
        page = estado.get("a")
        if page is None:
            raise Falha("pré-requisito: S0 falhou")
        enviar(page, PEDIDO_HUMANO, "W1")
        link = esperar_link(page, "W1")
        if page.locator(SEL_WHATSAPP).count() != 1:
            raise Falha(f"W1: esperava 1 link de WhatsApp, há {page.locator(SEL_WHATSAPP).count()}")
        conferir(link, "os cursos", "W1")
        estado["w1"] = True

    def w2():
        page = entrar_no_student(email_b)
        enviar(page, PEDIDO_HUMANO_CURSO, "W2")
        link = esperar_link(page, "W2")
        conferir(link, "o curso Omega Analytics", "W2")
        labels = [_normalizar(t) for t in page.locator(SEL_MATRICULA).all_inner_texts()]
        esperados = [a["label"] for a in dados["acoes_omega"]]
        if labels != esperados:
            raise Falha(f"W2: botões de matrícula {labels} (esperado {esperados}): o handoff não convive com a D76")

    def w3():
        if not estado.get("w1"):
            raise Falha("pré-requisito: W1 falhou (sem link antes do reload, o check não prova nada)")
        page = estado["a"]
        page.goto(base + "/student", wait_until="networkidle")
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        fim = time.time() + 8
        while time.time() < fim and page.locator(SEL_MENSAGEM).count() < 4:
            page.wait_for_timeout(150)
        if page.locator(SEL_MENSAGEM).count() < 4:
            raise Falha("W3: o histórico não voltou depois de recarregar")
        page.wait_for_timeout(500)
        if page.locator(SEL_WHATSAPP).count() != 0:
            raise Falha("W3: link de WhatsApp no histórico recarregado (a ação foi persistida)")

    def o1():
        conferir_cartao(GESTAO_EMAIL, GESTAO_SENHA, "O1 Gestão")

    def o2():
        conferir_cartao(SUPORTE_EMAIL, SUPORTE_SENHA, "O2 Suporte")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s): {erros_console[:3]}")

    try:
        cenario("S0", "pré-condição: chat do aluno responde sem link de WhatsApp na pergunta geral", s0)
        cenario("W1", "pedido de atendente mostra o link do WhatsApp (label, href, target, rel)", w1)
        cenario("W2", "pedido sobre o curso: texto com o curso e botões de matrícula mantidos", w2)
        cenario("W3", "histórico recarregado sem link de WhatsApp", w3)
        cenario("O1", "Gestão vê o cartão 'Encaminhamentos ao WhatsApp' com o total da API", o1)
        cenario("O2", "Suporte vê o mesmo cartão com o total da API", o2)
        cenario("K1", "sem erros de console de /api nem exceções de página", k1)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nF6 Angular: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
