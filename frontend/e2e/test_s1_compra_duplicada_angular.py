"""E2E da entrega S1 — trava de compra duplicada e retomada de pagamento pendente na tela /catalogo (D72).

Contrato de tela (D72):
  - curso com matrícula `active` do aluno: o cartão mostra [data-testid=catalogo-ja-matriculado] com o texto
    "Você já está matriculado" e NÃO tem botão de compra;
  - curso com matrícula `pending`: o botão de compra ([data-testid=catalogo-comprar], o mesmo botão de hoje) mostra
    "Retomar pagamento"; clicar retoma o pagamento sem criar matrícula nem pagamento novos (conferido no banco);
  - curso sem matrícula (ou com matrícula `cancelled`/`refunded`): o botão de compra atual, "Comprar e matricular".

Harness D58 (apoio_harness_h1): backend próprio com banco SQLite temporário, cursos temporários, Mercado Pago falso
(preferência devolve https://mp.invalid/checkout) e `ng serve` em porta livre. PAYMENTS_MOCK e APP_ENV são removidos
do ambiente herdado pelo backend de teste (o mock nunca vale aqui).

Seed: quatro cursos pela API da Gestão (ativo, pendente, livre, cancelado); aluno A com matrícula `active` no curso
ativo, `pending` (com pagamento `pending` no valor do catálogo) no pendente e `cancelled` no cancelado; aluno B com
matrícula `active` no curso livre (isolamento: a matrícula de B não muda a tela de A).

Cenários:
  S1 aluno A em /catalogo vê os quatro cursos do seed
  S2 curso ativo: [data-testid=catalogo-ja-matriculado] "Você já está matriculado" e nenhum botão de compra
  S3 curso pendente: botão [data-testid=catalogo-comprar] com o texto "Retomar pagamento"
  S4 clicar "Retomar pagamento": mensagem [data-testid=catalogo-mensagem], nenhum [data-testid=catalogo-erro], abre o
     checkout do gateway (mp.invalid), e no banco: nenhuma matrícula nem pagamento novos, a matrícula pendente
     continua a mesma (id, referência, status `pending`)
  S5 curso livre (B tem matrícula ativa nele): botão "Comprar e matricular", sem "já matriculado"
  S6 curso com matrícula `cancelled`: botão "Comprar e matricular", sem "já matriculado"
  S7 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_s1_compra_duplicada_angular.py -s
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
from servidor_e2e_h1 import GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-s1-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
GATEWAY_FALSO = "mp.invalid"
TEXTO_JA_MATRICULADO = "Você já está matriculado"
TEXTO_RETOMAR = "Retomar pagamento"
TEXTO_COMPRAR = "Comprar e matricular"
STATUS_PAGAMENTO = {"pending": "pending", "active": "approved", "cancelled": "cancelled", "refunded": "refunded"}


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
    nome = f"Curso S1 {prefixo} {uuid.uuid4().hex[:6]}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso S1 do e2e", "price": preco,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
        "materials": [{"title": f"Apostila {course_id}", "url": f"https://materiais.test/{course_id}/apostila.pdf",
                       "type": "pdf"}],
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome, "preco": preco}


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.s1.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, f"Aluno S1 {tag}", get_password_hash(SENHA), role="student")
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


def _executar(sql, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def semear_matricula(user_id, curso, status):
    Database = abrir_banco(ALVO["db_path"])
    referencia = f"{curso['id']}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(user_id, curso["id"], referencia)
    payment_id = Database.record_payment(enrollment_id, curso["preco"], "mercado_pago")
    _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))
    _executar("UPDATE payments SET status = ? WHERE id = ?", (STATUS_PAGAMENTO[status], payment_id))
    return {"id": enrollment_id, "payment_id": payment_id, "ref": referencia}


def caminho(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("#")[0].split("?")[0] if "://" in url else url


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ").replace(" ", " ")).strip()


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
        with ambiente_isolado("s1") as ambiente:
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


def test_s1_compra_duplicada_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {"abas": []}

    seed = {"ok": False, "erro": ""}
    try:
        email_a, uid_a = semear_aluno("a")
        _email_b, uid_b = semear_aluno("b")
        curso_ativo = criar_curso("s1_ativo", 120.0)
        curso_pendente = criar_curso("s1_pend", 249.9)
        curso_livre = criar_curso("s1_livre", 89.9)
        curso_cancelado = criar_curso("s1_canc", 59.9)
        semear_matricula(uid_a, curso_ativo, "active")
        pendente = semear_matricula(uid_a, curso_pendente, "pending")
        semear_matricula(uid_a, curso_cancelado, "cancelled")
        semear_matricula(uid_b, curso_livre, "active")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        # Registra as chamadas a window.open (o Chromium headless pode não materializar a aba de um window.open
        # disparado depois da resposta assíncrona da API).
        ctx.add_init_script(
            "(() => { const original = window.open; window.__s1Abertas = [];"
            " window.open = function(url, ...resto) { window.__s1Abertas.push(String(url));"
            " return original.call(window, url, ...resto); }; })();"
        )
        page = ctx.new_page()
        ctx.on("page", lambda nova: estado["abas"].append(nova))

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

    def pagina():
        page = estado.get("page")
        if page is None:
            raise Falha("pré-requisito: o aluno A não abriu o catálogo (S1 falhou)")
        return page

    def cartao(curso):
        card = pagina().locator('[data-testid="catalogo-card"]').filter(has_text=curso["nome"])
        if card.count() != 1:
            raise Falha(f"o cartão de '{curso['nome']}' não aparece uma única vez (vezes: {card.count()})")
        return card.first

    def assert_botao_de_compra(curso, codigo):
        card = cartao(curso)
        if card.locator('[data-testid="catalogo-ja-matriculado"]').count() != 0:
            raise Falha(f"{codigo}: o cartão de '{curso['nome']}' mostra 'já matriculado'")
        botao = card.locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha(f"{codigo}: o cartão de '{curso['nome']}' não tem o botão [data-testid=catalogo-comprar]")
        texto = _normalizar(botao.first.inner_text())
        if texto != TEXTO_COMPRAR:
            raise Falha(f"{codigo}: texto do botão = {texto!r} (esperado {TEXTO_COMPRAR!r})")

    def s1():
        page = nova_pagina()
        estado["page"] = page
        entrar(page, email_a, SENHA, "student")
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        if caminho(page.url) != "/catalogo":
            raise Falha(f"S1: o aluno logado não ficou em /catalogo ({page.url})")
        cards = page.locator('[data-testid="catalogo-card"]')
        try:
            cards.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("S1: nenhum [data-testid=catalogo-card] visível")
        page.wait_for_timeout(500)
        for curso in (curso_ativo, curso_pendente, curso_livre, curso_cancelado):
            cartao(curso)

    def s2():
        card = cartao(curso_ativo)
        aviso = card.locator('[data-testid="catalogo-ja-matriculado"]')
        try:
            aviso.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("S2: o curso com matrícula ativa não mostra [data-testid=catalogo-ja-matriculado]")
        texto = _normalizar(aviso.first.inner_text())
        if TEXTO_JA_MATRICULADO not in texto:
            raise Falha(f"S2: aviso = {texto!r} (esperado conter {TEXTO_JA_MATRICULADO!r})")
        if card.locator('[data-testid="catalogo-comprar"]').count() != 0:
            raise Falha("S2: o curso com matrícula ativa ainda tem o botão de compra")
        if card.locator("button", has_text=re.compile("Comprar|Retomar")).count() != 0:
            raise Falha("S2: o curso com matrícula ativa tem botão de compra/retomada")

    def s3():
        card = cartao(curso_pendente)
        botao = card.locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha("S3: o curso pendente não tem o botão [data-testid=catalogo-comprar]")
        texto = _normalizar(botao.first.inner_text())
        if texto != TEXTO_RETOMAR:
            raise Falha(f"S3: texto do botão do curso pendente = {texto!r} (esperado {TEXTO_RETOMAR!r})")
        if card.locator('[data-testid="catalogo-ja-matriculado"]').count() != 0:
            raise Falha("S3: o curso pendente mostra 'já matriculado'")

    def s4():
        page = pagina()
        antes = {
            "enrollments": _sql("SELECT COUNT(*) AS n FROM enrollments")[0]["n"],
            "payments": _sql("SELECT COUNT(*) AS n FROM payments")[0]["n"],
            "users": _sql("SELECT COUNT(*) AS n FROM users")[0]["n"],
        }
        botao = cartao(curso_pendente).locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha("S4: o curso pendente não tem o botão [data-testid=catalogo-comprar]")
        botao.first.click(timeout=TIMEOUT)
        mensagem = page.locator('[data-testid="catalogo-mensagem"]')
        try:
            mensagem.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            erro = page.locator('[data-testid="catalogo-erro"]')
            detalhe = erro.first.inner_text() if erro.count() else "sem mensagem"
            raise Falha(f"S4: a retomada não mostrou [data-testid=catalogo-mensagem] ({detalhe})")
        if page.locator('[data-testid="catalogo-erro"]').count() != 0:
            raise Falha("S4: a retomada mostrou [data-testid=catalogo-erro]")
        page.wait_for_timeout(1000)
        urls = []
        for aba in estado["abas"]:
            try:
                urls.append(aba.url)
            except Exception:
                pass
        pedidas = page.evaluate("() => window.__s1Abertas || []")
        if not any(GATEWAY_FALSO in (u or "") for u in urls + pedidas):
            raise Falha(f"S4: a retomada não abriu o checkout do gateway (abas: {urls}; window.open: {pedidas})")
        depois = {
            "enrollments": _sql("SELECT COUNT(*) AS n FROM enrollments")[0]["n"],
            "payments": _sql("SELECT COUNT(*) AS n FROM payments")[0]["n"],
            "users": _sql("SELECT COUNT(*) AS n FROM users")[0]["n"],
        }
        if depois != antes:
            raise Falha(f"S4: a retomada mudou as contagens do banco ({antes} -> {depois})")
        matriculas = _sql("SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?",
                          (uid_a, curso_pendente["id"]))
        if len(matriculas) != 1:
            raise Falha(f"S4: {len(matriculas)} matrícula(s) de A no curso pendente (esperado 1)")
        m = matriculas[0]
        if m["id"] != pendente["id"] or m["external_reference"] != pendente["ref"] or m["status"] != "pending":
            raise Falha(f"S4: matrícula pendente mudou: {m['id']}/{m['external_reference']}/{m['status']}")
        pagamentos = _sql("SELECT * FROM payments WHERE enrollment_id = ?", (pendente["id"],))
        if len(pagamentos) != 1 or pagamentos[0]["status"] != "pending":
            raise Falha(f"S4: pagamentos da matrícula pendente = {[(p['id'], p['status']) for p in pagamentos]}")

    def s5():
        assert_botao_de_compra(curso_livre, "S5")

    def s6():
        assert_botao_de_compra(curso_cancelado, "S6")

    def s7():
        if erros_console:
            raise Falha(f"S7: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("S1", "aluno vê os cursos do seed em /catalogo", s1)
    cenario("S2", "curso com matrícula ativa: 'Você já está matriculado' sem botão de compra", s2)
    cenario("S3", "curso com matrícula pendente: botão 'Retomar pagamento'", s3)
    cenario("S5", "curso sem matrícula do aluno (outro aluno ativo): botão de compra atual", s5)
    cenario("S6", "curso com matrícula cancelada: botão de compra atual", s6)
    cenario("S4", "retomar abre o gateway sem criar matrícula nem pagamento", s4)
    cenario("S7", "sem erros de console de /api", s7)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
