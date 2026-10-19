"""E2E da entrega O0 — checkout do aluno logado pela tela /catalogo (PLANO_FEEDBACK_PROF.md, item H2; D68/D69).

A tela `/catalogo` e o `POST /api/student/checkout` vieram do commit `15104c7`, fora do ciclo TDD. Este e2e é de
CARACTERIZAÇÃO: fixa o comportamento que já existe e pode passar inteiro antes da implementação da O0. A trava do
pagamento simulado (H3) é coberta no backend (`backend/tests/test_o0_checkout_aluno.py`); aqui o mock fica
desligado (PAYMENTS_MOCK e APP_ENV são removidos do ambiente herdado pelo backend de teste) e o checkout passa
pelo Mercado Pago falso do harness (D58), que devolve `https://mp.invalid/checkout`.

Seed: dois cursos criados pela API da Gestão no diretório de cursos temporário (um com material), dois alunos com
senha (A compra; B nunca compra) pela camada Database no SQLite temporário.

Cenários:
  C1 sem login, /catalogo leva ao login (rota "/" com o formulário) e nenhum cartão do catálogo aparece
  C2 aluno A logado abre /catalogo e vê os dois cursos do seed, cada um com o preço em BRL ("R$" e "1.234,50")
  C3 "Comprar e matricular" no curso com material: aparece a mensagem [data-testid=catalogo-mensagem], nenhum
     [data-testid=catalogo-erro], e a tela abre o checkout do gateway (mp.invalid) em nova aba: vale a aba nova
     vista pelo Playwright OU a chamada a window.open registrada por um script de página (o Chromium headless pode
     não materializar a aba de um window.open com noopener feito depois da resposta assíncrona)
  C4 efeito no banco: uma matrícula `pending` de A no curso, com um pagamento `pending`, `mercado_pago`, no valor
     do catálogo; B continua sem matrícula; nenhuma conta nova
  C5 /student mostra o cartão do curso com o badge "Pendente" e a URL do material NÃO aparece na página
     (recurso pago só com matrícula ativa)
  C6 funcionário (Gestão, Financeiro, Suporte) logado não fica em /catalogo e não vê o catálogo
  C7 sem erros de console de /api (4xx/5xx) nem exceções de página nas telas do aluno

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_o0_catalogo_angular.py -s
"""

import json
import os
import re
import sqlite3
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
from servidor_e2e_h1 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-o0-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
GATEWAY_FALSO = "mp.invalid"


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


def criar_curso(prefixo, preco, com_material):
    token = _api("POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    course_id = f"{prefixo}_{uuid.uuid4().hex[:8]}"
    nome = f"Curso O0 {uuid.uuid4().hex[:6]}"
    materiais = []
    if com_material:
        materiais = [{"title": f"Apostila {course_id}", "url": f"https://materiais.test/{course_id}/apostila.pdf",
                      "type": "pdf"}]
    corpo = {
        "id": course_id, "name": nome, "description": "Curso O0 do e2e", "price": preco,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
        "materials": materiais,
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome, "preco": preco, "material": materiais[0] if materiais else None}


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.o0.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, f"Aluno O0 {tag}", get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return email, uid


def _sql(sql, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def caminho(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("#")[0].split("?")[0] if "://" in url else url


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ").replace(" ", " ")).strip()


def entrar(page, email, senha, destino):
    try:
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        page.wait_for_url(f"**/{destino}", timeout=TIMEOUT * 3)
        page.wait_for_load_state("networkidle")
    except sync_api.TimeoutError:
        raise Falha(f"login de {email} não levou a /{destino} (URL atual {page.url})")


@pytest.fixture(scope="module")
def servidores():
    # O backend de teste herda o ambiente deste processo: o mock nunca pode estar ligado neste e2e.
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("o0") as ambiente:
            ALVO.update(base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"])
            yield ambiente
    finally:
        os.environ.update(salvos)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_o0_catalogo_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {"abas": []}

    seed = {"ok": False, "erro": ""}
    try:
        email_a, uid_a = semear_aluno("a")
        email_b, uid_b = semear_aluno("b")
        curso_x = criar_curso("o0_x", 1234.5, com_material=True)
        curso_y = criar_curso("o0_y", 89.9, com_material=False)
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(monitorar_console=True):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        # Registra as chamadas a window.open (e ainda abre a aba): o Chromium headless pode não emitir a aba nova
        # de um window.open com noopener disparado fora do gesto do clique (resposta assíncrona da API).
        ctx.add_init_script(
            "(() => { const original = window.open; window.__o0Abertas = [];"
            " window.open = function(url, ...resto) { window.__o0Abertas.push(String(url));"
            " return original.call(window, url, ...resto); }; })();"
        )
        page = ctx.new_page()
        ctx.on("page", lambda nova: estado["abas"].append(nova))

        if monitorar_console:
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

    def c1():
        page = nova_pagina()
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        page.wait_for_timeout(500)
        if caminho(page.url) not in ("/", "/login"):
            raise Falha(f"C1: sem login, /catalogo ficou em {page.url} (esperado o login)")
        if page.locator("input[name=email]").count() == 0 or page.locator("input[name=password]").count() == 0:
            raise Falha("C1: o formulário de login não aparece")
        if page.locator('[data-testid="catalogo-card"]').count() != 0:
            raise Falha("C1: o catálogo aparece sem login")

    def pagina_a():
        page = estado.get("page")
        if page is None:
            raise Falha("pré-requisito: o aluno A não abriu o catálogo (C2 falhou)")
        return page

    def c2():
        page = nova_pagina()
        estado["page"] = page
        entrar(page, email_a, SENHA, "student")
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        if caminho(page.url) != "/catalogo":
            raise Falha(f"C2: o aluno logado não ficou em /catalogo ({page.url})")
        cards = page.locator('[data-testid="catalogo-card"]')
        try:
            cards.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("C2: nenhum [data-testid=catalogo-card] visível")
        for curso, preco_br in ((curso_x, "1.234,50"), (curso_y, "89,90")):
            card = cards.filter(has_text=curso["nome"])
            if card.count() != 1:
                raise Falha(f"C2: o cartão de '{curso['nome']}' não aparece uma única vez")
            preco = card.first.locator('[data-testid="catalogo-preco"]')
            if preco.count() != 1:
                raise Falha(f"C2: o cartão de '{curso['nome']}' não tem [data-testid=catalogo-preco]")
            texto = _normalizar(preco.first.inner_text())
            if "R$" not in texto or preco_br not in texto:
                raise Falha(f"C2: preço de '{curso['nome']}' = {texto!r} (esperado R$ {preco_br})")

    def c3():
        page = pagina_a()
        usuarios = _sql("SELECT COUNT(*) AS n FROM users")[0]["n"]
        estado["usuarios_antes"] = usuarios
        card = page.locator('[data-testid="catalogo-card"]').filter(has_text=curso_x["nome"]).first
        botao = card.locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha("C3: o cartão não tem o botão [data-testid=catalogo-comprar]")
        botao.first.click(timeout=TIMEOUT)
        mensagem = page.locator('[data-testid="catalogo-mensagem"]')
        try:
            mensagem.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            erro = page.locator('[data-testid="catalogo-erro"]')
            detalhe = erro.first.inner_text() if erro.count() else "sem mensagem"
            raise Falha(f"C3: a compra não mostrou [data-testid=catalogo-mensagem] ({detalhe})")
        if page.locator('[data-testid="catalogo-erro"]').count() != 0:
            raise Falha("C3: a compra mostrou [data-testid=catalogo-erro]")
        page.wait_for_timeout(1000)
        urls = []
        for aba in estado["abas"]:
            try:
                urls.append(aba.url)
            except Exception:
                pass
        pedidas = page.evaluate("() => window.__o0Abertas || []")
        if not any(GATEWAY_FALSO in (u or "") for u in urls + pedidas):
            raise Falha(f"C3: a tela não abriu o checkout do gateway em nova aba (abas: {urls}; window.open: {pedidas})")

    def c4():
        matriculas = _sql("SELECT * FROM enrollments WHERE user_id = ?", (uid_a,))
        if len(matriculas) != 1:
            raise Falha(f"C4: {len(matriculas)} matrícula(s) de A (esperado 1)")
        m = matriculas[0]
        if m["course_id"] != curso_x["id"] or m["status"] != "pending":
            raise Falha(f"C4: matrícula de A = {m['course_id']}/{m['status']} (esperado {curso_x['id']}/pending)")
        pagamentos = _sql("SELECT * FROM payments WHERE enrollment_id = ?", (m["id"],))
        if len(pagamentos) != 1:
            raise Falha(f"C4: {len(pagamentos)} pagamento(s) da matrícula (esperado 1)")
        p = pagamentos[0]
        if p["status"] != "pending" or p["payment_method"] != "mercado_pago" or abs(p["amount"] - curso_x["preco"]) > 0.001:
            raise Falha(f"C4: pagamento = {p['status']}/{p['payment_method']}/{p['amount']} "
                        f"(esperado pending/mercado_pago/{curso_x['preco']})")
        if _sql("SELECT id FROM enrollments WHERE user_id = ?", (uid_b,)):
            raise Falha("C4: o aluno B ganhou matrícula")
        if "usuarios_antes" in estado and _sql("SELECT COUNT(*) AS n FROM users")[0]["n"] != estado["usuarios_antes"]:
            raise Falha("C4: a compra do aluno logado criou conta nova")

    def c5():
        page = pagina_a()
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        cards = page.locator('[data-testid="curso-card"]')
        try:
            cards.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("C5: /student não mostra nenhum cartão de curso")
        card = cards.filter(has_text=curso_x["nome"])
        if card.count() != 1:
            raise Falha(f"C5: o cartão de '{curso_x['nome']}' não aparece uma única vez em /student")
        badge = card.first.locator(".badge").first.inner_text().strip()
        if badge != "Pendente":
            raise Falha(f"C5: badge do curso comprado = {badge!r} (esperado 'Pendente')")
        if curso_x["material"]["url"] in page.content():
            raise Falha("C5: a URL do material do curso pendente aparece em /student")

    def c6():
        for email, senha in ((GESTAO_EMAIL, GESTAO_SENHA), (FINANCEIRO_EMAIL, FINANCEIRO_SENHA),
                             (SUPORTE_EMAIL, SUPORTE_SENHA)):
            page = nova_pagina(monitorar_console=False)
            entrar(page, email, senha, "admin")
            page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
            page.wait_for_timeout(500)
            if caminho(page.url) == "/catalogo":
                raise Falha(f"C6: {email} ficou em /catalogo")
            if page.locator('[data-testid="catalogo-card"]').count() != 0:
                raise Falha(f"C6: {email} vê o catálogo do aluno")

    def c7():
        if erros_console:
            raise Falha(f"C7: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("C1", "sem login, /catalogo leva ao login", c1)
    cenario("C2", "aluno vê os cursos do catálogo com preço em BRL", c2)
    cenario("C3", "comprar mostra a mensagem e abre o checkout do gateway em nova aba", c3)
    cenario("C4", "matrícula e pagamento pending do aluno, valor do catálogo, sem conta nova", c4)
    cenario("C5", "/student mostra o curso como Pendente, sem material", c5)
    cenario("C6", "funcionário não acessa /catalogo", c6)
    cenario("C7", "sem erros de console de /api", c7)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
