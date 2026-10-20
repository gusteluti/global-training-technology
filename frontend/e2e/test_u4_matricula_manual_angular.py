"""E2E da entrega U4 - matricula manual pela Gestao (D81, modo autonomo D69).

Backend correspondente: backend/tests/test_u4_matricula_manual.py.
Teste VERMELHO escrito antes da implementacao: hoje a lista de alunos do curso (F4) nao tem o botao
`matricula-manual-abrir` nem o formulario, e o recibo do aluno nao traduz a forma `manual`.

Contrato de tela (D81):
  - Dashboard de cursos -> lista de alunos do curso (curso-alunos, F4): botao `matricula-manual-abrir` (so Gestao)
    com o formulario `matricula-manual-email`, `matricula-manual-nome`, `matricula-manual-turma`,
    `matricula-manual-valor`, `matricula-manual-motivo`, `matricula-manual-salvar` e as mensagens
    `matricula-manual-ok` / `matricula-manual-erro` (data-testid).
  - Recibo do aluno: forma de pagamento "Matrícula manual".

Escolhas de forma do teste (nenhuma define politica):
  - `matricula-manual-turma` e um <select>; a turma e escolhida pelo value (id) OU pelo texto (nome da turma).
  - O valor e digitado como "150" (serve para input numerico e de texto). Os textos de ok/erro nao sao fixados.
  - O erro de motivo curto pode vir da validacao da tela ou do 422 da API: basta `matricula-manual-erro` visivel e
    nada gravado.
  - Depois de salvar, a linha do aluno (curso-aluno-row) aparece com "Ativa" sem recarregar a pagina a mao.

Seed (harness D58, SQLite temporario): curso A com a turma "Alfa U4" e curso B criados pela API de Gestao (L1);
Caio (conta com senha) com matricula pendente no curso A; Lia (conta com senha) sem matricula.

Cenarios:
  M1 Gestao abre os alunos do curso A, usa matricula-manual-abrir, preenche e-mail novo, nome, turma Alfa, valor 150 e
     motivo, salva: matricula-manual-ok e a linha do aluno novo como Ativa na turma; banco com active + approved/manual
  M2 motivo curto ("abc"): matricula-manual-erro visivel e nada gravado para o e-mail
  M3 Caio (pendente no curso): matricula manual sem turma reaproveita a pendente; uma linha so, Ativa
  F1 Financeiro abre a lista de alunos do curso A e nao ve matricula-manual-abrir
  S1 Suporte abre a lista de alunos do curso A e nao ve matricula-manual-abrir
  R1 Lia, matriculada manualmente pela API no curso B, abre "Ver recibo": "Forma de pagamento: Matrícula manual"
  K1 sem erros de console de /api (4xx/5xx) nem excecoes de pagina, exceto 4xx de /api/admin/enrollments em M2

Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_u4_matricula_manual_angular.py -s
"""

import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
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
SENHA = "senha-aluno-u4-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
FUSO = "America/Sao_Paulo"
IDIOMA = "en-US"
TURMA_ALFA = "Alfa U4"
MOTIVO = "Bolsa integral concedida pela diretoria"
ROTULO_MANUAL = "Matrícula manual"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_CURSO_LINK = '[data-testid="curso-alunos-link"]'
SEL_CURSO_ALUNOS = '[data-testid="curso-alunos"]'
SEL_CURSO_ROW = '[data-testid="curso-aluno-row"]'
SEL_ABRIR = '[data-testid="matricula-manual-abrir"]'
SEL_EMAIL = '[data-testid="matricula-manual-email"]'
SEL_NOME = '[data-testid="matricula-manual-nome"]'
SEL_TURMA = '[data-testid="matricula-manual-turma"]'
SEL_VALOR = '[data-testid="matricula-manual-valor"]'
SEL_MOTIVO = '[data-testid="matricula-manual-motivo"]'
SEL_SALVAR = '[data-testid="matricula-manual-salvar"]'
SEL_OK = '[data-testid="matricula-manual-ok"]'
SEL_ERRO = '[data-testid="matricula-manual-erro"]'


class Falha(Exception):
    """Falha de um passo de cenario; a mensagem diz o que faltou na tela."""


# ---------------------------------------------------------------------------------------------
# API e banco (seed)
# ---------------------------------------------------------------------------------------------

def _api(metodo, caminho, corpo=None, token=None, formulario=None):
    cabecalhos = {}
    dados = None
    if formulario is not None:
        dados = urllib.parse.urlencode(formulario).encode()
        cabecalhos["Content-Type"] = "application/x-www-form-urlencoded"
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        cabecalhos["Content-Type"] = "application/json"
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(ALVO["api"] + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read() or b"null")
        except Exception:
            return erro.code, None


def _consulta(comando, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(comando, params).fetchall()]
    finally:
        conn.close()


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, rotulo, preco):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"u4-{rotulo.lower()}-{sufixo}"
    nome = f"Curso U4 {rotulo} {sufixo}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso U4 do e2e", "price": preco,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": [],
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome}


def criar_turma(token, course_id, nome, inicio):
    status, corpo = _api("POST", "/api/admin/classes",
                         {"course_id": course_id, "name": nome, "starts_on": inicio}, token=token)
    if status != 200:
        raise RuntimeError(f"seed: POST /api/admin/classes {nome} respondeu HTTP {status}")
    return corpo["class"]["id"]


def criar_aluno(Database, nome):
    from core.security import get_password_hash

    email = f"e2e.u4.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, nome, get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: nao foi possivel criar {email}")
    return {"uid": uid, "email": email, "nome": nome}


def semear():
    token = token_gestao()
    curso_a = criar_curso(token, "A", 321.45)
    curso_b = criar_curso(token, "B", 80.0)
    inicio = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 30 * 86400))
    alfa = criar_turma(token, curso_a["id"], TURMA_ALFA, inicio)

    Database = abrir_banco(ALVO["db_path"])
    caio = criar_aluno(Database, f"Caio U4 {uuid.uuid4().hex[:4]}")
    lia = criar_aluno(Database, f"Lia U4 {uuid.uuid4().hex[:4]}")
    enrollment_id = Database.create_enrollment(caio["uid"], curso_a["id"], f"{curso_a['id']}:u4:{uuid.uuid4().hex}")
    Database.record_payment(enrollment_id, 321.45, "mercado_pago")
    caio["pendente"] = enrollment_id
    return {"token": token, "a": curso_a, "b": curso_b, "alfa": alfa, "caio": caio, "lia": lia}


# ---------------------------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------------------------

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
        raise Falha(f"login de {email} nao levou a /{destino} (URL atual {page.url})")


def clicar_aba(page, nome):
    aba = page.locator(SEL_ABA, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$"))
    try:
        aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"a aba '{nome}' nao aparece")
    aba.first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def esperar(locator, codigo, descricao, limite=TIMEOUT * 2):
    try:
        locator.first.wait_for(state="visible", timeout=limite)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: {descricao} nao aparece na tela")
    return locator.first


def esperar_condicao(fn, codigo, limite_ms=TIMEOUT * 2):
    passos = max(1, limite_ms // 250)
    motivo = "sem leitura"
    for _ in range(passos):
        try:
            motivo = fn()
        except sync_api.Error as erro:
            motivo = f"erro do navegador: {str(erro).splitlines()[0] if str(erro) else type(erro).__name__}"
        if motivo is None:
            return
        time.sleep(0.25)
    raise Falha(f"{codigo}: {motivo}")


def abrir_curso_alunos(page, curso, codigo):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
    clicar_aba(page, "Cursos")
    link = esperar(page.locator(SEL_CURSO_LINK, has_text=curso["nome"]), codigo,
                   f"o curso-alunos-link do curso {curso['nome']!r}")
    link.click(timeout=TIMEOUT)
    page.wait_for_load_state("networkidle")
    return esperar(page.locator(SEL_CURSO_ALUNOS), codigo, "a lista de alunos do curso (curso-alunos)")


def linhas_do_curso(page):
    return [_normalizar(t) for t in page.eval_on_selector_all(SEL_CURSO_ROW, "els => els.map(e => e.innerText)")]


def abrir_formulario(page, codigo):
    botao = esperar(page.locator(SEL_ABRIR), codigo, "o botao matricula-manual-abrir na lista de alunos do curso")
    botao.click(timeout=TIMEOUT)
    esperar(page.locator(SEL_EMAIL), codigo, "o campo matricula-manual-email depois de abrir o formulario")


def preencher(page, seletor, valor, codigo):
    campo = esperar(page.locator(seletor), codigo, f"o campo {seletor}")
    campo.fill(str(valor), timeout=TIMEOUT)


def escolher_turma(page, class_id, nome, codigo):
    select = esperar(page.locator(SEL_TURMA), codigo, "o campo matricula-manual-turma")
    opcoes = select.evaluate("e => Array.from(e.options || []).map(o => ({value: o.value, text: o.text}))")
    for indice, opcao in enumerate(opcoes):
        if opcao["value"] == str(class_id) or opcao["value"].endswith(f": {class_id}") \
                or nome in _normalizar(opcao["text"]):
            select.select_option(index=indice)
            return
    raise Falha(f"{codigo}: matricula-manual-turma nao tem a turma {nome!r}; opcoes: {opcoes}")


def salvar(page, codigo):
    esperar(page.locator(SEL_SALVAR), codigo, "o botao matricula-manual-salvar").click(timeout=TIMEOUT)
    page.wait_for_load_state("networkidle")


def matriculas_por_email(email, course_id):
    return _consulta(
        """SELECT e.id, e.status, e.class_id FROM enrollments e JOIN users u ON u.id = e.user_id
           WHERE u.email = ? AND e.course_id = ? ORDER BY e.id""",
        (email, course_id),
    )


def pagamentos(enrollment_id):
    return _consulta("SELECT * FROM payments WHERE enrollment_id = ? ORDER BY id", (enrollment_id,))


def conferir_linha_ativa(page, email, codigo, turma=None):
    def leitura():
        linhas = [l for l in linhas_do_curso(page) if email in l]
        if len(linhas) != 1:
            return f"{len(linhas)} curso-aluno-row com {email} (esperado 1): {linhas_do_curso(page)}"
        if "Ativa" not in linhas[0]:
            return f"a linha de {email} nao mostra 'Ativa': {linhas[0]!r}"
        if turma and turma not in linhas[0]:
            return f"a linha de {email} nao mostra a turma {turma!r}: {linhas[0]!r}"
        return None
    esperar_condicao(leitura, codigo, TIMEOUT * 3)


def sem_botao(page, perfil, codigo):
    page.wait_for_timeout(800)
    n = page.locator(SEL_ABRIR).count()
    if n:
        raise Falha(f"{codigo}: o perfil {perfil} ve {n} botao(oes) matricula-manual-abrir (so Gestao)")


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("u4") as ambiente:
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


# ---------------------------------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------------------------------

def test_u4_matricula_manual_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    paginas = {}
    permitir_4xx_manual = {"ativo": False}

    seed = {"ok": False, "erro": ""}
    s = {}
    try:
        s.update(semear())
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, timezone_id=FUSO, locale=IDIOMA)
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            m = ERRO_HTTP.search(msg.text)
            if msg.type != "error" or not m or "/api/" not in (url + msg.text):
                return
            codigo = int(m.group(1))
            if permitir_4xx_manual["ativo"] and 400 <= codigo < 500 and "/api/admin/enrollments" in url + msg.text:
                return
            erros_console.append(f"{msg.text[:120]} ({url})")

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        return page

    def pagina(perfil):
        if perfil not in paginas:
            page = nova_pagina()
            email, senha, destino = {
                "gestao": (GESTAO_EMAIL, GESTAO_SENHA, "admin"),
                "fin": (FINANCEIRO_EMAIL, FINANCEIRO_SENHA, "admin"),
                "sup": (SUPORTE_EMAIL, SUPORTE_SENHA, "admin"),
                "lia": (s["lia"]["email"], SENHA, "student"),
            }[perfil]
            entrar(page, email, senha, destino)
            paginas[perfil] = page
        return paginas[perfil]

    def cenario(codigo, nome, funcao):
        try:
            if not seed["ok"]:
                raise Falha(f"seed falhou: {seed['erro']}")
            funcao()
            resultados.append((codigo, nome, True, ""))
            print(f"[PASS] {codigo} {nome}")
        except Exception as erro:
            texto = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, texto))
            print(f"[FAIL] {codigo} {nome} -> {texto}")

    def m1():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "M1")
        abrir_formulario(page, "M1")
        email = f"novo.m1.{uuid.uuid4().hex[:6]}@teste.com"
        preencher(page, SEL_EMAIL, email, "M1")
        preencher(page, SEL_NOME, "Novo Aluno M1", "M1")
        escolher_turma(page, s["alfa"], TURMA_ALFA, "M1")
        preencher(page, SEL_VALOR, "150", "M1")
        preencher(page, SEL_MOTIVO, MOTIVO, "M1")
        salvar(page, "M1")
        esperar(page.locator(SEL_OK), "M1", "a mensagem matricula-manual-ok depois de salvar")
        conferir_linha_ativa(page, email, "M1", TURMA_ALFA)
        linhas = matriculas_por_email(email, s["a"]["id"])
        if [(l["status"], l["class_id"]) for l in linhas] != [("active", s["alfa"])]:
            raise Falha(f"M1: no banco, a matricula de {email} deveria ser active na turma Alfa: {linhas}")
        p = pagamentos(linhas[0]["id"])
        if [(x["status"], x["payment_method"], round(x["amount"], 2)) for x in p] != [("approved", "manual", 150.0)]:
            raise Falha(f"M1: o pagamento deveria ser approved/manual de 150: {p}")

    def m2():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "M2")
        abrir_formulario(page, "M2")
        email = f"erro.m2.{uuid.uuid4().hex[:6]}@teste.com"
        preencher(page, SEL_EMAIL, email, "M2")
        preencher(page, SEL_NOME, "Erro M2", "M2")
        preencher(page, SEL_VALOR, "0", "M2")
        preencher(page, SEL_MOTIVO, "abc", "M2")
        permitir_4xx_manual["ativo"] = True
        try:
            salvar(page, "M2")
            esperar(page.locator(SEL_ERRO), "M2", "a mensagem matricula-manual-erro com motivo curto")
            page.wait_for_timeout(300)
        finally:
            permitir_4xx_manual["ativo"] = False
        if page.locator(SEL_OK).count() and page.locator(SEL_OK).first.is_visible():
            raise Falha("M2: matricula-manual-ok apareceu junto com o erro")
        if matriculas_por_email(email, s["a"]["id"]):
            raise Falha("M2: o motivo curto nao pode gravar matricula")

    def m3():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "M3")
        abrir_formulario(page, "M3")
        preencher(page, SEL_EMAIL, s["caio"]["email"], "M3")
        preencher(page, SEL_VALOR, "0", "M3")
        preencher(page, SEL_MOTIVO, "Cortesia para aluno com pagamento travado", "M3")
        salvar(page, "M3")
        esperar(page.locator(SEL_OK), "M3", "a mensagem matricula-manual-ok depois de salvar")
        conferir_linha_ativa(page, s["caio"]["email"], "M3")
        linhas = matriculas_por_email(s["caio"]["email"], s["a"]["id"])
        if [(l["id"], l["status"]) for l in linhas] != [(s["caio"]["pendente"], "active")]:
            raise Falha(f"M3: a pendente do Caio deveria ser reaproveitada como active: {linhas}")

    def f1():
        page = pagina("fin")
        abrir_curso_alunos(page, s["a"], "F1")
        sem_botao(page, "Financeiro", "F1")

    def s1():
        page = pagina("sup")
        abrir_curso_alunos(page, s["a"], "S1")
        sem_botao(page, "Suporte", "S1")

    def r1():
        status, corpo = _api("POST", "/api/admin/enrollments", {
            "email": s["lia"]["email"], "course_id": s["b"]["id"], "amount": 80,
            "reason": "Matricula por convenio com a empresa",
        }, token=s["token"])
        if status not in (200, 201):
            raise Falha(f"R1: POST /api/admin/enrollments respondeu HTTP {status}: {corpo}")
        page = pagina("lia")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        linha = esperar(page.locator("tr", has_text=s["b"]["nome"]), "R1",
                        f"a linha do pagamento do curso {s['b']['nome']!r} no historico financeiro")
        linha.get_by_role("button", name="Ver recibo").first.click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")

        def leitura():
            texto = _normalizar(page.locator("body").inner_text())
            if f"Forma de pagamento: {ROTULO_MANUAL}" not in texto:
                achado = re.search(r"Forma de pagamento:[^\n]{0,40}", texto)
                return f"o recibo nao mostra 'Forma de pagamento: {ROTULO_MANUAL}' ({achado.group(0) if achado else 'sem forma'})"
            return None
        esperar_condicao(leitura, "R1")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("M1", "Gestao matricula aluno novo pelo formulario: ok e linha Ativa na turma", m1)
    cenario("M2", "motivo curto: matricula-manual-erro e nada gravado", m2)
    cenario("M3", "aluno com pendente: matricula manual reaproveita a pendente", m3)
    cenario("F1", "Financeiro nao ve matricula-manual-abrir", f1)
    cenario("S1", "Suporte nao ve matricula-manual-abrir", s1)
    cenario("R1", "recibo do aluno mostra 'Matrícula manual'", r1)
    cenario("K1", "sem erros de console de /api nem excecoes de pagina", k1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
