"""E2E da entrega D2 — nova Área do Aluno no design da landing (escopo Fase 2, seção 1.1; RF21 e RF22).

Fonte: pedido do PM (07/10/2026) "após aplicar o design construa a área do aluno" e o escopo
(`Escopo_Fase2_Global_Training_Technology.pdf`, 1.1: painel de inscrições com cursos, status e materiais; histórico
financeiro com recibos e status de pagamentos concluídos ou pendentes). Contrato da tela em decisoes_tdd.md, D67.
O que já existia (E3, E4, E5, B2) é preservado: os e2e dessas entregas continuam valendo como regressão.

Seed (camada Database no SQLite temporário do backend de teste, como na E3/B2):
  aluno A: curso Ativo (pagamento approved R$ 250,00, com material), curso Pendente (pending R$ 99,00, com material),
           curso Reembolsado (approved e depois refunded, R$ 80,00)
  aluno B: curso próprio ativo (approved R$ 33,00, com material) — nunca pode aparecer para A

Cenários:
  A1 login de A leva a /student; cabeçalho com o rótulo "Área do aluno" e o e-mail de A em [data-testid=aluno-email]
  A2 resumo: [data-testid=resumo-cursos-ativos] = "1", [data-testid=resumo-pagamentos-pendentes] = "1" e
     [data-testid=resumo-total-investido] com "250,00" (só pagamento aprovado e não reembolsado conta)
  A3 "Meus cursos": exatamente 3 [data-testid=curso-card], um por matrícula de A, cada um com o nome do curso, o
     badge de status em português (Ativa / Pendente / Reembolsada) e a data da matrícula em [data-testid=curso-data]
     no formato dd/mm/aaaa
  A4 só o cartão ativo tem link de material (título e href); a URL do material do curso pendente não está na página
  A5 histórico financeiro com o status em português em [data-testid=pagamento-status]: Aprovado, Pendente e
     Reembolsado; nenhum valor bruto (approved, pending, refunded) visível na tabela
  A6 "Ver recibo" do aprovado mostra o cartão do recibo (div.card.border-primary) com "Recibo #<id>", o curso e o
     status "Aprovado"
  A7 atalhos: [data-testid=atalho-financeiro] leva a seção [data-testid=secao-financeiro] para a área visível e a
     URL continua /student (sem navegar para outra rota); idem [data-testid=atalho-assistente] -> chat-panel
  A8 isolamento (IDOR na tela): curso, e-mail e URL de material do aluno B não aparecem para A
  A9 celular (390 x 844): sem rolagem horizontal na página, cartões de curso e resumo visíveis
  A10 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_d2_area_aluno_angular.py -s
"""

import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-d2-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
DATA_BR = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _api(metodo, caminho, corpo=None, token=None):
    cabecalhos = {"Content-Type": "application/json"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(ALVO["api"] + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


def criar_curso(prefixo, preco):
    token = _api("POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    course_id = f"{prefixo}_{uuid.uuid4().hex[:8]}"
    nome = f"Curso D2 {uuid.uuid4().hex[:6]}"
    materiais = [{"title": f"Apostila {course_id}", "url": f"https://materiais.test/{course_id}/apostila.pdf", "type": "pdf"}]
    corpo = {
        "id": course_id, "name": nome, "description": "Curso D2 do e2e", "price": preco,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
        "materials": materiais,
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return course_id, nome, materiais[0]


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.d2.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, f"Aluno D2 {tag}", get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return email, uid


def semear_pagamento(user_id, course_id, status, valor):
    Database = abrir_banco(ALVO["db_path"])
    ref = f"{course_id}:d2e2e:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    if status in ("approved", "refunded"):
        Database.update_payment_status_by_reference(ref, "approved", uuid.uuid4().hex[:12])
    if status == "refunded":
        Database.mark_payment_refunded(payment_id)
    return payment_id


def entrar(page, email):
    try:
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(SENHA, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        page.wait_for_load_state("networkidle")
    except sync_api.TimeoutError:
        raise Falha(f"login não levou a /student (URL atual {page.url})")


def caminho(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("#")[0].split("?")[0] if "://" in url else url


def texto_de(page, testid):
    loc = page.locator(f'[data-testid="{testid}"]').first
    try:
        loc.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"[data-testid={testid}] não está visível")
    return loc.inner_text().strip()


def no_viewport(page, seletor):
    return page.locator(seletor).first.evaluate(
        "e => { const r = e.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0; }")


@pytest.fixture(scope="module")
def servidores():
    with ambiente_isolado("d2") as ambiente:
        ALVO.update(base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"])
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_d2_area_aluno_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {}

    seed = {"ok": False, "erro": ""}
    cursos = {}
    try:
        email_a, uid_a = semear_aluno("a")
        for status, valor in (("approved", 250.00), ("pending", 99.00), ("refunded", 80.00)):
            cid, nome, mat = criar_curso(f"d2_{status}", valor)
            pid = semear_pagamento(uid_a, cid, status, valor)
            cursos[status] = {"nome": nome, "material": mat, "payment_id": pid}
        email_b, uid_b = semear_aluno("b")
        cid_b, nome_b, mat_b = criar_curso("d2_outro", 33.00)
        semear_pagamento(uid_b, cid_b, "approved", 33.00)
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(largura=1366, altura=900):
        ctx = browser.new_context(viewport={"width": largura, "height": altura})
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

    def pagina_a():
        page = estado.get("page")
        if page is None or caminho(page.url) != "/student":
            raise Falha("pré-requisito: o aluno A não está em /student (A1 falhou)")
        return page

    def a1():
        page = nova_pagina()
        estado["page"] = page
        entrar(page, email_a)
        if "Área do aluno" not in page.inner_text("body"):
            raise Falha("A1: a tela não mostra o rótulo 'Área do aluno'")
        if email_a not in texto_de(page, "aluno-email"):
            raise Falha("A1: [data-testid=aluno-email] não mostra o e-mail do aluno logado")

    def a2():
        page = pagina_a()
        ativos = texto_de(page, "resumo-cursos-ativos")
        pendentes = texto_de(page, "resumo-pagamentos-pendentes")
        total = texto_de(page, "resumo-total-investido")
        if ativos != "1":
            raise Falha(f"A2: cursos ativos = {ativos!r} (esperado '1')")
        if pendentes != "1":
            raise Falha(f"A2: pagamentos pendentes = {pendentes!r} (esperado '1')")
        if "250,00" not in total:
            raise Falha(f"A2: total investido = {total!r} (esperado R$ 250,00, sem o reembolsado nem o pendente)")

    def a3():
        page = pagina_a()
        cards = page.locator('[data-testid="curso-card"]')
        if cards.count() != 3:
            raise Falha(f"A3: {cards.count()} cartões de curso (esperado 3)")
        esperado = {"approved": "Ativa", "pending": "Pendente", "refunded": "Reembolsada"}
        for status, rotulo in esperado.items():
            card = cards.filter(has_text=cursos[status]["nome"])
            if card.count() != 1:
                raise Falha(f"A3: o cartão de '{cursos[status]['nome']}' não aparece uma única vez")
            badge = card.first.locator(".badge").first.inner_text().strip()
            if badge != rotulo:
                raise Falha(f"A3: badge do curso {status} = {badge!r} (esperado {rotulo!r})")
            data = card.first.locator('[data-testid="curso-data"]')
            if data.count() != 1 or not DATA_BR.search(data.first.inner_text()):
                raise Falha(f"A3: o cartão do curso {status} não mostra a data da matrícula em dd/mm/aaaa")

    def a4():
        page = pagina_a()
        cards = page.locator('[data-testid="curso-card"]')
        ativo = cards.filter(has_text=cursos["approved"]["nome"]).first
        mat = cursos["approved"]["material"]
        link = ativo.locator(f'a[href="{mat["url"]}"]')
        if link.count() != 1 or mat["title"] not in link.first.inner_text():
            raise Falha("A4: o cartão ativo não mostra o link do material com o título")
        conteudo = page.content()
        for status in ("pending", "refunded"):
            if cursos[status]["material"]["url"] in conteudo:
                raise Falha(f"A4: a URL do material do curso {status} aparece na página")

    def a5():
        page = pagina_a()
        page.locator("tbody tr").first.wait_for(timeout=TIMEOUT)
        esperado = {"approved": "Aprovado", "pending": "Pendente", "refunded": "Reembolsado"}
        for status, rotulo in esperado.items():
            linha = page.locator("tbody tr").filter(has_text=cursos[status]["nome"])
            if linha.count() != 1:
                raise Falha(f"A5: a linha do pagamento de '{cursos[status]['nome']}' não aparece uma única vez")
            st = linha.first.locator('[data-testid="pagamento-status"]')
            if st.count() != 1 or st.first.inner_text().strip() != rotulo:
                raise Falha(f"A5: status do pagamento {status} na tela = "
                            f"{st.first.inner_text().strip() if st.count() else None!r} (esperado {rotulo!r})")
        tabela = page.locator("table").first.inner_text()
        for bruto in ("approved", "pending", "refunded"):
            if re.search(rf"\b{bruto}\b", tabela):
                raise Falha(f"A5: o valor bruto '{bruto}' aparece na tabela do histórico")

    def a6():
        page = pagina_a()
        aprovado = cursos["approved"]
        linha = page.locator("tbody tr").filter(has_text=aprovado["nome"])
        linha.get_by_role("button", name="Ver recibo").click(timeout=TIMEOUT)
        cartao = page.locator("div.card.border-primary")
        try:
            cartao.first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("A6: 'Ver recibo' não mostrou o cartão do recibo")
        texto = cartao.first.inner_text()
        for trecho in (f"Recibo #{aprovado['payment_id']}", aprovado["nome"], "Aprovado"):
            if trecho not in texto:
                raise Falha(f"A6: o cartão do recibo não mostra {trecho!r} (texto: {texto[:120]!r})")

    def a7():
        page = pagina_a()
        page.evaluate("window.scrollTo(0, 0)")
        for atalho, secao in (("atalho-financeiro", '[data-testid="secao-financeiro"]'),
                              ("atalho-assistente", '[data-testid="chat-panel"]')):
            botao = page.locator(f'[data-testid="{atalho}"]')
            if botao.count() != 1:
                raise Falha(f"A7: [data-testid={atalho}] não existe")
            botao.first.click(timeout=TIMEOUT)
            page.wait_for_timeout(900)
            if caminho(page.url) != "/student":
                raise Falha(f"A7: o atalho {atalho} mudou a rota para {page.url}")
            if page.locator(secao).count() == 0 or not no_viewport(page, secao):
                raise Falha(f"A7: depois de {atalho}, {secao} não está na área visível")
            page.evaluate("window.scrollTo(0, 0)")

    def a8():
        page = pagina_a()
        texto = page.inner_text("body")
        if nome_b in texto or email_b in texto:
            raise Falha("A8: a tela de A mostra curso ou e-mail do aluno B")
        if mat_b["url"] in page.content():
            raise Falha("A8: a tela de A mostra a URL do material do aluno B")

    def a9():
        page = nova_pagina(390, 844)
        entrar(page, email_a)
        page.locator('[data-testid="curso-card"]').first.wait_for(state="visible", timeout=TIMEOUT)
        larguras = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if larguras[0] > larguras[1] + 1:
            raise Falha(f"A9: rolagem horizontal no celular (scrollWidth {larguras[0]} > clientWidth {larguras[1]})")
        if not page.locator('[data-testid="resumo-cursos-ativos"]').first.is_visible():
            raise Falha("A9: o resumo não está visível no celular")

    def a10():
        if erros_console:
            raise Falha(f"A10: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("A1", "login leva a /student com 'Área do aluno' e o e-mail do aluno", a1)
    cenario("A2", "resumo: 1 curso ativo, 1 pagamento pendente, R$ 250,00 investidos", a2)
    cenario("A3", "3 cartões de curso com badge em português e data dd/mm/aaaa", a3)
    cenario("A4", "material só no cartão ativo; nenhuma URL de pendente/reembolsado", a4)
    cenario("A5", "histórico financeiro com status de pagamento em português", a5)
    cenario("A6", "recibo mostra número, curso e status 'Aprovado'", a6)
    cenario("A7", "atalhos rolam até as seções sem trocar de rota", a7)
    cenario("A8", "nada do aluno B aparece para A", a8)
    cenario("A9", "celular sem rolagem horizontal", a9)
    cenario("A10", "sem erros de console de /api", a10)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
