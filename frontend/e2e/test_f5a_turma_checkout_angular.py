"""E2E da entrega F5a — turma no checkout da tela /catalogo (D75).

Contrato de tela (D75):
  - curso com turmas abertas: o cartão mostra a seleção obrigatória [data-testid=catalogo-turma] com nome, início
    (dd/mm/aaaa) e vagas de cada turma aberta; turma lotada aparece desabilitada com "(lotada)"; turma já iniciada
    não aparece;
  - a compra envia `class_id`; sem turma escolhida a compra não acontece (bloqueada na tela);
  - `/catalogo?curso=<id>&turma=<id>` pré-seleciona a turma no cartão do curso;
  - curso sem turmas: sem [data-testid=catalogo-turma], compra como hoje.

Escolha de forma do teste (D75 não fixa o elemento): [data-testid=catalogo-turma] é um <select> cujas <option> são as
turmas (uma opção-guia sem valor é permitida). As opções são lidas pelo texto, não pelo `value`.

Harness D58 (apoio_harness_h1): backend próprio com banco SQLite temporário, cursos temporários, Mercado Pago falso
(preferência devolve https://mp.invalid/checkout) e `ng serve` em porta livre. PAYMENTS_MOCK e APP_ENV removidos.

Seed: três cursos pela API da Gestão — "turmas" (aberta com capacidade 7 e uma pendente antiga = 6 vagas; lotada
com capacidade 1 ocupada por B; iniciada ontem), "qs" (duas turmas abertas) e "sem" (sem turmas). Turmas por
Database.create_class no banco temporário.

Cenários:
  F1 aluno A em /catalogo vê os três cursos
  F2 curso com turmas: [data-testid=catalogo-turma] com a turma aberta (nome, início dd/mm/aaaa, "6" vagas) e sem a
     turma iniciada; curso sem turmas não tem a seleção
  F3 turma lotada: opção desabilitada com "(lotada)"
  F4 sem turma escolhida, a compra não acontece (nenhuma matrícula nova, gateway não aberto)
  F5 escolher a turma aberta e comprar: mensagem, gateway aberto, matrícula `pending` de A com o `class_id` da turma
  F6 curso sem turmas: compra sem seleção cria matrícula `pending` sem turma
  F7 aluno C em /catalogo?curso=<qs>&turma=<segunda turma>: a segunda turma vem selecionada
  F8 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f5a_turma_checkout_angular.py -s
"""

import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-f5a-2026"
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


def _dia_sp(delta):
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date() + timedelta(days=delta)


def _br(dia: date):
    return dia.strftime("%d/%m/%Y")


def criar_curso(prefixo, preco):
    token = _api("POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    course_id = f"{prefixo}_{uuid.uuid4().hex[:8]}"
    nome = f"Curso F5a {prefixo} {uuid.uuid4().hex[:6]}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso F5a do e2e", "price": preco,
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


def criar_turma(curso, nome, inicio, capacidade):
    Database = abrir_banco(ALVO["db_path"])
    class_id = Database.create_class(curso["id"], nome, inicio.isoformat() if inicio else None, capacidade)
    if class_id is None:
        raise RuntimeError(f"seed: turma {nome} não foi criada")
    return {"id": class_id, "nome": nome, "inicio": inicio}


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.f5a.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, f"Aluno F5a {tag}", get_password_hash(SENHA), role="student")
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


def semear_matricula_na_turma(user_id, curso, status, class_id):
    """Matrícula sem reserved_until (como a Gestão a deixaria) na turma; ocupa vaga se `active` ou `pending`."""
    Database = abrir_banco(ALVO["db_path"])
    referencia = f"{curso['id']}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(user_id, curso["id"], referencia)
    payment_id = Database.record_payment(enrollment_id, curso["preco"], "mercado_pago")
    _executar("UPDATE enrollments SET status = ?, class_id = ? WHERE id = ?", (status, class_id, enrollment_id))
    _executar("UPDATE payments SET status = ? WHERE id = ?",
              ("approved" if status == "active" else "pending", payment_id))
    return enrollment_id


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
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("f5a") as ambiente:
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


def test_f5a_turma_checkout_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {"abas": []}

    seed = {"ok": False, "erro": ""}
    try:
        email_a, uid_a = semear_aluno("a")
        _email_b, uid_b = semear_aluno("b")
        email_c, _uid_c = semear_aluno("c")
        _email_d, uid_d = semear_aluno("d")
        curso_turmas = criar_curso("f5a_turmas", 120.0)
        curso_qs = criar_curso("f5a_qs", 99.9)
        curso_sem = criar_curso("f5a_sem", 59.9)
        aberta = criar_turma(curso_turmas, f"Turma Aberta {uuid.uuid4().hex[:4]}", _dia_sp(12), 7)
        lotada = criar_turma(curso_turmas, f"Turma Lotada {uuid.uuid4().hex[:4]}", _dia_sp(15), 1)
        iniciada = criar_turma(curso_turmas, f"Turma Iniciada {uuid.uuid4().hex[:4]}", _dia_sp(-1), 7)
        semear_matricula_na_turma(uid_d, curso_turmas, "pending", aberta["id"])  # 7 - 1 = 6 vagas
        semear_matricula_na_turma(uid_b, curso_turmas, "active", lotada["id"])
        qs1 = criar_turma(curso_qs, f"Turma QS Um {uuid.uuid4().hex[:4]}", _dia_sp(5), 3)
        qs2 = criar_turma(curso_qs, f"Turma QS Dois {uuid.uuid4().hex[:4]}", _dia_sp(8), 3)
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        ctx.add_init_script(
            "(() => { const original = window.open; window.__f5aAbertas = [];"
            " window.open = function(url, ...resto) { window.__f5aAbertas.push(String(url));"
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
            raise Falha("pré-requisito: o aluno A não abriu o catálogo (F1 falhou)")
        return page

    def cartao(curso, page=None):
        card = (page or pagina()).locator('[data-testid="catalogo-card"]').filter(has_text=curso["nome"])
        if card.count() != 1:
            raise Falha(f"o cartão de '{curso['nome']}' não aparece uma única vez (vezes: {card.count()})")
        return card.first

    def selecao(curso, codigo, page=None):
        sel = cartao(curso, page).locator('[data-testid="catalogo-turma"]')
        try:
            sel.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{codigo}: o cartão de '{curso['nome']}' não mostra [data-testid=catalogo-turma]")
        if sel.count() != 1:
            raise Falha(f"{codigo}: {sel.count()} elementos [data-testid=catalogo-turma] no cartão")
        return sel.first

    def opcoes(sel):
        return sel.locator("option").evaluate_all(
            "els => els.map((o, i) => ({i, text: o.textContent, disabled: o.disabled,"
            " selected: o.selected, value: o.value}))"
        )

    def opcao_de(sel, turma, codigo):
        achadas = [o for o in opcoes(sel) if turma["nome"] in _normalizar(o["text"])]
        if len(achadas) != 1:
            raise Falha(f"{codigo}: a turma '{turma['nome']}' aparece {len(achadas)} vez(es) na seleção "
                        f"(opções: {[_normalizar(o['text']) for o in opcoes(sel)]})")
        return achadas[0]

    def contagens():
        return {
            "enrollments": _sql("SELECT COUNT(*) AS n FROM enrollments")[0]["n"],
            "payments": _sql("SELECT COUNT(*) AS n FROM payments")[0]["n"],
        }

    def gateway_aberto(page):
        urls = []
        for aba in estado["abas"]:
            try:
                urls.append(aba.url)
            except Exception:
                pass
        pedidas = page.evaluate("() => window.__f5aAbertas || []")
        return any(GATEWAY_FALSO in (u or "") for u in urls + pedidas), urls + pedidas

    def esperar_mensagem(page, codigo):
        mensagem = page.locator('[data-testid="catalogo-mensagem"]')
        try:
            mensagem.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            erro = page.locator('[data-testid="catalogo-erro"]')
            detalhe = erro.first.inner_text() if erro.count() else "sem mensagem"
            raise Falha(f"{codigo}: a compra não mostrou [data-testid=catalogo-mensagem] ({detalhe})")
        page.wait_for_timeout(1000)

    def f1():
        page = nova_pagina()
        estado["page"] = page
        entrar(page, email_a, SENHA, "student")
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        if caminho(page.url) != "/catalogo":
            raise Falha(f"F1: o aluno logado não ficou em /catalogo ({page.url})")
        try:
            page.locator('[data-testid="catalogo-card"]').first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("F1: nenhum [data-testid=catalogo-card] visível")
        page.wait_for_timeout(800)
        for curso in (curso_turmas, curso_qs, curso_sem):
            cartao(curso)

    def f2():
        sel = selecao(curso_turmas, "F2")
        o = opcao_de(sel, aberta, "F2")
        texto = _normalizar(o["text"])
        if _br(aberta["inicio"]) not in texto:
            raise Falha(f"F2: opção {texto!r} sem o início {_br(aberta['inicio'])}")
        if not re.search(r"(?<![\d/])6(?![\d/])", texto) or "vaga" not in texto.lower():
            raise Falha(f"F2: opção {texto!r} sem as vagas restantes (6 vagas)")
        if o["disabled"]:
            raise Falha("F2: a turma aberta está desabilitada")
        if any(iniciada["nome"] in _normalizar(x["text"]) for x in opcoes(sel)):
            raise Falha("F2: a turma já iniciada aparece na seleção")
        if cartao(curso_sem).locator('[data-testid="catalogo-turma"]').count() != 0:
            raise Falha("F2: o curso sem turmas mostra [data-testid=catalogo-turma]")

    def f3():
        sel = selecao(curso_turmas, "F3")
        o = opcao_de(sel, lotada, "F3")
        if not o["disabled"]:
            raise Falha(f"F3: a turma lotada não está desabilitada ({_normalizar(o['text'])!r})")
        if "(lotada)" not in _normalizar(o["text"]):
            raise Falha(f"F3: a turma lotada não mostra '(lotada)' ({_normalizar(o['text'])!r})")

    def f4():
        page = pagina()
        sel = selecao(curso_turmas, "F4")
        escolhidas = [o for o in opcoes(sel) if o["selected"] and o["value"] not in ("", None)
                      and any(t["nome"] in _normalizar(o["text"]) for t in (aberta, lotada))]
        if escolhidas:
            raise Falha(f"F4: sem query a seleção já vem com turma ({_normalizar(escolhidas[0]['text'])!r})")
        antes = contagens()
        botao = cartao(curso_turmas).locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha("F4: o curso com turmas não tem o botão [data-testid=catalogo-comprar]")
        if botao.first.is_enabled():
            botao.first.click(timeout=TIMEOUT)
            page.wait_for_timeout(1500)
        aberto, urls = gateway_aberto(page)
        if aberto:
            raise Falha(f"F4: sem turma o gateway foi aberto ({urls})")
        if contagens() != antes:
            raise Falha(f"F4: sem turma a compra criou registros ({antes} -> {contagens()})")

    def f5():
        page = pagina()
        sel = selecao(curso_turmas, "F5")
        o = opcao_de(sel, aberta, "F5")
        sel.select_option(index=o["i"], timeout=TIMEOUT)
        antes = contagens()
        cartao(curso_turmas).locator('[data-testid="catalogo-comprar"]').first.click(timeout=TIMEOUT)
        esperar_mensagem(page, "F5")
        aberto, urls = gateway_aberto(page)
        if not aberto:
            raise Falha(f"F5: a compra não abriu o checkout do gateway ({urls})")
        if contagens()["enrollments"] != antes["enrollments"] + 1:
            raise Falha(f"F5: esperada uma matrícula nova ({antes} -> {contagens()})")
        m = _sql("SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?", (uid_a, curso_turmas["id"]))
        if len(m) != 1 or m[0]["status"] != "pending" or m[0]["class_id"] != aberta["id"]:
            raise Falha(f"F5: matrícula de A = {[(x['status'], x['class_id']) for x in m]} "
                        f"(esperado pending na turma {aberta['id']})")

    def f6():
        page = pagina()
        estado["abas"].clear()
        page.evaluate("() => { window.__f5aAbertas = []; }")
        botao = cartao(curso_sem).locator('[data-testid="catalogo-comprar"]')
        if botao.count() != 1:
            raise Falha("F6: o curso sem turmas não tem o botão de compra")
        botao.first.click(timeout=TIMEOUT)
        esperar_mensagem(page, "F6")
        aberto, urls = gateway_aberto(page)
        if not aberto:
            raise Falha(f"F6: a compra sem turma não abriu o gateway ({urls})")
        m = _sql("SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?", (uid_a, curso_sem["id"]))
        if len(m) != 1 or m[0]["status"] != "pending" or m[0]["class_id"] is not None:
            raise Falha(f"F6: matrícula de A no curso sem turmas = {[(x['status'], x['class_id']) for x in m]}")

    def f7():
        page = nova_pagina()
        entrar(page, email_c, SENHA, "student")
        page.goto(f"{ALVO['base']}/catalogo?curso={curso_qs['id']}&turma={qs2['id']}", wait_until="networkidle")
        page.wait_for_timeout(800)
        sel = selecao(curso_qs, "F7", page)
        try:
            page.wait_for_function(
                "([el, nome]) => { const o = el.options[el.selectedIndex]; return !!o && o.textContent.includes(nome); }",
                arg=[sel.element_handle(), qs2["nome"]], timeout=TIMEOUT)
        except sync_api.TimeoutError:
            marcadas = [_normalizar(o["text"]) for o in opcoes(sel) if o["selected"]]
            raise Falha(f"F7: a turma '{qs2['nome']}' não veio selecionada (selecionada: {marcadas})")
        if any(qs1["nome"] in _normalizar(o["text"]) and o["selected"] for o in opcoes(sel)):
            raise Falha("F7: a primeira turma ficou selecionada no lugar da pedida")

    def f8():
        if erros_console:
            raise Falha(f"F8: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("F1", "aluno vê os cursos do seed em /catalogo", f1)
    cenario("F2", "seleção de turma com nome, início e vagas; sem turma iniciada; curso sem turma sem seleção", f2)
    cenario("F3", "turma lotada desabilitada com '(lotada)'", f3)
    cenario("F4", "sem turma escolhida a compra não acontece", f4)
    cenario("F5", "compra com turma cria matrícula pendente com o class_id", f5)
    cenario("F6", "curso sem turmas compra sem seleção (matrícula sem turma)", f6)
    cenario("F7", "?curso=&turma= pré-seleciona a turma", f7)
    cenario("F8", "sem erros de console de /api", f8)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
