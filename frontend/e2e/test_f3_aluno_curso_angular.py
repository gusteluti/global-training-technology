"""E2E da entrega F3/F4 — aluno -> cursos e turma; curso -> alunos; turma visível ao aluno (D73, política D68).

Backend correspondente: backend/tests/test_f3_aluno_curso.py. Modo autônomo: D69.

Contrato de tela (D73 + pedido do orquestrador):
  - Dashboard de alunos (aba "Alunos" de /admin): o nome do aluno abre o detalhe.
      data-testid="aluno-detalhe"            -> container do detalhe do aluno
      data-testid="aluno-detalhe-matricula"  -> uma por matrícula: curso, turma, status em português (rótulos da E3:
                                                Pendente, Ativa, Cancelada, Reembolsada) e data dd/mm/aaaa
      pagamentos do aluno dentro do aluno-detalhe, com o valor em R$ para Gestão e Financeiro; para Suporte, nenhum
      valor em R$ (D68: Suporte vê status, nunca valores).
  - Dashboard de cursos (aba "Cursos"): o curso abre a lista de alunos.
      data-testid="curso-alunos-link"          -> um por curso, contém o nome do curso
      data-testid="curso-alunos"               -> container da lista de alunos do curso
      data-testid="curso-aluno-row"            -> uma por matrícula: nome, e-mail, turma, status (português)
      data-testid="curso-alunos-filtro-status" -> <select> de status
      data-testid="curso-alunos-filtro-turma"  -> <select> de turma (inclui a opção "Sem turma")
  - Área do aluno (/student): no cartão do curso (curso-card), data-testid="curso-turma" com "Turma: <nome>" e a data
    de início em dd/mm/aaaa, sem deslocar o dia (é data só de dia). Sem turma, curso-turma não aparece.

Escolhas de forma aceitas pelo teste (nenhuma define política): o nome do aluno pode ser link ou botão (o teste clica
no texto do nome dentro da linha do aluno); as opções dos filtros são escolhidas pelo `value` ("active", "pending",
id da turma, "none") OU pelo texto (Ativa/Pendente, nome da turma, "Sem turma"), para não fixar o binding do select;
a data da matrícula no detalhe pode ter a hora ao lado; o texto "sem turma" da linha não é fixado. O detalhe pode ser
rota própria ou painel na aba. Cada cenário reabre /admin para começar sem filtro aplicado.

Seed (harness D58, SQLite temporário):
  - Curso A (preço 321,45) com turmas "Alfa F3" (início 2026-11-01) e "Beta F3" (início 2026-12-05); curso B (150,00).
  - Joana: A ativa na Alfa (pagamento aprovado 321,45, matrícula 2026-09-15 15:00 UTC); B pendente sem turma
    (pagamento pendente 150,00, 2026-09-20 15:00 UTC). Login com senha (área do aluno).
  - Pedro: A pendente na Beta (pagamento pendente 321,45). Rita: A cancelada, sem turma.
  As turmas são criadas e atribuídas pela API de Gestão (L1); status e datas são montados na camada de banco.

Cenários:
  D1 Gestão clica no nome da Joana no dashboard de alunos: aluno-detalhe com 2 aluno-detalhe-matricula
     (curso, turma, status em português e data dd/mm/aaaa)
  D2 Gestão vê os pagamentos da Joana com valor em R$ (321,45 e 150,00)
  D3 Financeiro também vê os valores em R$
  D4 Suporte vê o detalhe (matrículas e status) SEM nenhum valor em R$
  C1 Gestão clica no curso A (curso-alunos-link): curso-alunos com 3 curso-aluno-row (nome, e-mail, turma, status)
  C2 filtro de status: Ativa -> só Joana; Pendente -> só Pedro
  C3 filtro de turma: Alfa F3 -> só Joana; Sem turma -> só Rita
  C4 Suporte abre a lista de alunos do curso sem nenhum valor em R$
  A1 área do aluno: o cartão do curso A mostra curso-turma "Turma: Alfa F3" e 01/11/2026 (não 31/10/2026)
  A2 área do aluno: o cartão do curso B (sem turma) não tem curso-turma
  K1 sem erros de console de /api (4xx/5xx) nem exceções de página

Os navegadores rodam em 'America/Sao_Paulo' com locale 'en-US': uma data só de dia lida como UTC apareceria no dia
anterior, e a tela não pode depender do idioma da máquina.

Execução (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_f3_aluno_curso_angular.py -s
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
SENHA = "senha-aluno-f3-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
FUSO = "America/Sao_Paulo"
IDIOMA = "en-US"

PRECO_A = 321.45
PRECO_B = 150.0
VALORES_TELA = ("321,45", "150,00")
TURMA_ALFA = "Alfa F3"
TURMA_BETA = "Beta F3"
INICIO_ALFA = "2026-11-01"
INICIO_ALFA_TELA = "01/11/2026"
INICIO_ALFA_DESLOCADO = "31/10/2026"
INICIO_BETA = "2026-12-05"
DATA_JOANA_A = "2026-09-15 15:00:00"
DATA_JOANA_B = "2026-09-20 15:00:00"
DATA_JOANA_A_TELA = "15/09/2026"
DATA_JOANA_B_TELA = "20/09/2026"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_DETALHE = '[data-testid="aluno-detalhe"]'
SEL_DETALHE_MATRICULA = '[data-testid="aluno-detalhe-matricula"]'
SEL_CURSO_LINK = '[data-testid="curso-alunos-link"]'
SEL_CURSO_ALUNOS = '[data-testid="curso-alunos"]'
SEL_CURSO_ROW = '[data-testid="curso-aluno-row"]'
SEL_FILTRO_STATUS = '[data-testid="curso-alunos-filtro-status"]'
SEL_FILTRO_TURMA = '[data-testid="curso-alunos-filtro-turma"]'
SEL_CURSO_CARD = '[data-testid="curso-card"]'
SEL_CURSO_TURMA = '[data-testid="curso-turma"]'
REAIS = re.compile(r"R\$")


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


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
        return erro.code, None


def _sql(comando, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    try:
        cur = conn.execute(comando, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, rotulo, preco):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"f3-{rotulo.lower()}-{sufixo}"
    nome = f"Curso F3 {rotulo} {sufixo}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso F3 do e2e", "price": preco,
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


def atribuir_turma(token, enrollment_id, class_id):
    status, _ = _api("PUT", f"/api/admin/enrollments/{enrollment_id}/class", {"class_id": class_id}, token=token)
    if status != 200:
        raise RuntimeError(f"seed: PUT /api/admin/enrollments/{enrollment_id}/class respondeu HTTP {status}")


def criar_aluno(Database, nome, com_senha=False):
    from core.security import get_password_hash

    email = f"e2e.f3.{uuid.uuid4().hex[:10]}@teste.com"
    senha = get_password_hash(SENHA) if com_senha else None
    uid = Database.add_user(email, nome, senha, role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return {"uid": uid, "email": email, "nome": nome}


def matricular(Database, aluno, course_id, status, data, valor=None, status_pagamento=None):
    enrollment_id = Database.create_enrollment(aluno["uid"], course_id, f"{course_id}:f3:{uuid.uuid4().hex}")
    _sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, data, enrollment_id))
    if valor is not None:
        pid = Database.record_payment(enrollment_id, valor, "mercado_pago")
        if status_pagamento != "pending":
            Database.update_payment_status(pid, status_pagamento, f"mp-f3-{uuid.uuid4().hex[:6]}")
        _sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (data, data, pid))
    return enrollment_id


def semear():
    token = token_gestao()
    curso_a = criar_curso(token, "A", PRECO_A)
    curso_b = criar_curso(token, "B", PRECO_B)
    alfa = criar_turma(token, curso_a["id"], TURMA_ALFA, INICIO_ALFA)
    beta = criar_turma(token, curso_a["id"], TURMA_BETA, INICIO_BETA)

    Database = abrir_banco(ALVO["db_path"])
    joana = criar_aluno(Database, f"Joana F3 {uuid.uuid4().hex[:4]}", com_senha=True)
    pedro = criar_aluno(Database, f"Pedro F3 {uuid.uuid4().hex[:4]}")
    rita = criar_aluno(Database, f"Rita F3 {uuid.uuid4().hex[:4]}")

    joana_a = matricular(Database, joana, curso_a["id"], "active", DATA_JOANA_A, PRECO_A, "approved")
    matricular(Database, joana, curso_b["id"], "pending", DATA_JOANA_B, PRECO_B, "pending")
    pedro_a = matricular(Database, pedro, curso_a["id"], "pending", "2026-09-16 15:00:00", PRECO_A, "pending")
    matricular(Database, rita, curso_a["id"], "cancelled", "2026-09-17 15:00:00")
    atribuir_turma(token, joana_a, alfa)
    atribuir_turma(token, pedro_a, beta)
    return {"token": token, "a": curso_a, "b": curso_b, "alfa": alfa, "beta": beta,
            "joana": joana, "pedro": pedro, "rita": rita}


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
        raise Falha(f"login de {email} não levou a /{destino} (URL atual {page.url})")


def clicar_aba(page, nome):
    aba = page.locator(SEL_ABA, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$"))
    try:
        aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"a aba '{nome}' não aparece")
    aba.first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def esperar(locator, codigo, descricao):
    try:
        locator.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: {descricao} não aparece na tela")
    return locator.first


def esperar_condicao(fn, codigo, limite_ms=TIMEOUT * 2):
    """Repete fn() até devolver None; uma string é o motivo da divergência."""
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


def ir_para_admin(page):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")


def abrir_detalhe(page, aluno, codigo):
    ir_para_admin(page)
    clicar_aba(page, "Alunos")
    linha = esperar(page.locator("tr", has_text=aluno["email"]), codigo, f"a linha do aluno {aluno['email']}")
    try:
        linha.get_by_text(aluno["nome"], exact=True).first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: o nome {aluno['nome']!r} não está clicável na linha do aluno")
    page.wait_for_load_state("networkidle")
    detalhe = esperar(page.locator(SEL_DETALHE), codigo, "o detalhe do aluno (aluno-detalhe) depois do clique no nome")
    try:
        detalhe.locator(f"text={aluno['email']}").first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: o aluno-detalhe não mostra o e-mail do aluno clicado ({aluno['email']})")
    return detalhe


def abrir_curso_alunos(page, curso, codigo):
    ir_para_admin(page)
    clicar_aba(page, "Cursos")
    link = esperar(page.locator(SEL_CURSO_LINK, has_text=curso["nome"]), codigo,
                   f"o curso-alunos-link do curso {curso['nome']!r}")
    link.click(timeout=TIMEOUT)
    page.wait_for_load_state("networkidle")
    return esperar(page.locator(SEL_CURSO_ALUNOS), codigo, "a lista de alunos do curso (curso-alunos)")


def linhas_do_curso(page):
    return [_normalizar(t) for t in page.eval_on_selector_all(SEL_CURSO_ROW, "els => els.map(e => e.innerText)")]


def conferir_linhas(page, esperados, ausentes, codigo):
    """Espera a lista curso-aluno-row ter exatamente os alunos `esperados` (nenhum dos `ausentes`)."""
    def leitura():
        linhas = linhas_do_curso(page)
        if len(linhas) != len(esperados):
            return f"{len(linhas)} curso-aluno-row na tela (esperado {len(esperados)}): {linhas}"
        for aluno in esperados:
            if not any(aluno["email"] in linha for linha in linhas):
                return f"o aluno {aluno['email']} não está nas linhas: {linhas}"
        for aluno in ausentes:
            if any(aluno["email"] in linha for linha in linhas):
                return f"o aluno {aluno['email']} não deveria aparecer com o filtro: {linhas}"
        return None
    esperar_condicao(leitura, codigo)


def escolher(page, seletor, valores, texto, codigo):
    """Seleciona a opção pelo value (um de `valores`) ou pelo texto (regex `texto`)."""
    select = esperar(page.locator(seletor), codigo, f"o filtro {seletor}")
    opcoes = select.evaluate("e => Array.from(e.options).map(o => ({value: o.value, text: o.text}))")
    for indice, opcao in enumerate(opcoes):
        if opcao["value"] in valores or re.search(texto, _normalizar(opcao["text"]), re.IGNORECASE):
            select.select_option(index=indice)
            page.wait_for_load_state("networkidle")
            return
    raise Falha(f"{codigo}: o filtro {seletor} não tem a opção {texto!r}; opções: {opcoes}")


def sem_reais(texto, codigo, onde):
    texto = _normalizar(texto)
    if REAIS.search(texto):
        raise Falha(f"{codigo}: {onde} mostra valor em R$ para o Suporte: {texto[:200]!r}")
    for valor in VALORES_TELA + ("321.45", "150.00"):
        if valor in texto:
            raise Falha(f"{codigo}: {onde} mostra o valor {valor} para o Suporte")


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("f3") as ambiente:
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

def test_f3_aluno_curso_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    paginas = {}

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
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
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
                "aluno": (s["joana"]["email"], SENHA, "student"),
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

    def matriculas_do_detalhe(page, codigo):
        def leitura():
            n = page.locator(SEL_DETALHE_MATRICULA).count()
            return None if n == 2 else f"{n} aluno-detalhe-matricula na tela (esperado 2)"
        esperar_condicao(leitura, codigo)
        return [_normalizar(t) for t in
                page.eval_on_selector_all(SEL_DETALHE_MATRICULA, "els => els.map(e => e.innerText)")]

    def d1():
        page = pagina("gestao")
        abrir_detalhe(page, s["joana"], "D1")
        linhas = matriculas_do_detalhe(page, "D1")
        linha_a = next((l for l in linhas if s["a"]["nome"] in l), None)
        linha_b = next((l for l in linhas if s["b"]["nome"] in l), None)
        if linha_a is None or linha_b is None:
            raise Falha(f"D1: as matrículas não mostram os dois cursos: {linhas}")
        for texto in (TURMA_ALFA, "Ativa", DATA_JOANA_A_TELA):
            if texto not in linha_a:
                raise Falha(f"D1: a matrícula do curso A não mostra {texto!r}: {linha_a!r}")
        for texto in ("Pendente", DATA_JOANA_B_TELA):
            if texto not in linha_b:
                raise Falha(f"D1: a matrícula do curso B não mostra {texto!r}: {linha_b!r}")
        if TURMA_ALFA in linha_b or TURMA_BETA in linha_b:
            raise Falha(f"D1: a matrícula sem turma mostra uma turma: {linha_b!r}")
        for cru in ("2026-09-15", "active", "pending"):
            if cru in linha_a + linha_b:
                raise Falha(f"D1: o detalhe mostra o valor cru {cru!r}")

    def com_valores(perfil, codigo):
        page = pagina(perfil)
        detalhe = abrir_detalhe(page, s["joana"], codigo)
        def leitura():
            texto = _normalizar(detalhe.inner_text())
            for valor in VALORES_TELA:
                if not re.search(rf"R\$\s*{re.escape(valor)}", texto):
                    return f"o detalhe não mostra o pagamento 'R$ {valor}': {texto[:300]!r}"
            return None
        esperar_condicao(leitura, codigo)

    def d2():
        com_valores("gestao", "D2")

    def d3():
        com_valores("fin", "D3")

    def d4():
        page = pagina("sup")
        detalhe = abrir_detalhe(page, s["joana"], "D4")
        linhas = matriculas_do_detalhe(page, "D4")
        if not any("Ativa" in l for l in linhas) or not any("Pendente" in l for l in linhas):
            raise Falha(f"D4: o Suporte deve ver o status das matrículas: {linhas}")
        page.wait_for_timeout(500)
        sem_reais(detalhe.inner_text(), "D4", "o detalhe do aluno")

    def c1():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "C1")
        conferir_linhas(page, [s["joana"], s["pedro"], s["rita"]], [], "C1")
        linhas = linhas_do_curso(page)
        esperado = {
            s["joana"]["email"]: (s["joana"]["nome"], TURMA_ALFA, "Ativa"),
            s["pedro"]["email"]: (s["pedro"]["nome"], TURMA_BETA, "Pendente"),
            s["rita"]["email"]: (s["rita"]["nome"], None, "Cancelada"),
        }
        for email, (nome, turma, status) in esperado.items():
            linha = next(l for l in linhas if email in l)
            for texto in (nome, status) + ((turma,) if turma else ()):
                if texto not in linha:
                    raise Falha(f"C1: a linha de {email} não mostra {texto!r}: {linha!r}")
            if turma is None and (TURMA_ALFA in linha or TURMA_BETA in linha):
                raise Falha(f"C1: a linha sem turma mostra uma turma: {linha!r}")

    def c2():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "C2")
        conferir_linhas(page, [s["joana"], s["pedro"], s["rita"]], [], "C2")
        escolher(page, SEL_FILTRO_STATUS, ("active",), r"^Ativ", "C2")
        conferir_linhas(page, [s["joana"]], [s["pedro"], s["rita"]], "C2 (Ativa)")
        escolher(page, SEL_FILTRO_STATUS, ("pending",), r"^Pendente", "C2")
        conferir_linhas(page, [s["pedro"]], [s["joana"], s["rita"]], "C2 (Pendente)")

    def c3():
        page = pagina("gestao")
        abrir_curso_alunos(page, s["a"], "C3")
        conferir_linhas(page, [s["joana"], s["pedro"], s["rita"]], [], "C3")
        escolher(page, SEL_FILTRO_TURMA, (str(s["alfa"]),), re.escape(TURMA_ALFA), "C3")
        conferir_linhas(page, [s["joana"]], [s["pedro"], s["rita"]], "C3 (Alfa)")
        escolher(page, SEL_FILTRO_TURMA, ("none",), r"Sem turma", "C3")
        conferir_linhas(page, [s["rita"]], [s["joana"], s["pedro"]], "C3 (Sem turma)")

    def c4():
        page = pagina("sup")
        lista = abrir_curso_alunos(page, s["a"], "C4")
        conferir_linhas(page, [s["joana"], s["pedro"], s["rita"]], [], "C4")
        sem_reais(lista.inner_text(), "C4", "a lista de alunos do curso")

    def cartao(page, curso, codigo):
        return esperar(page.locator(SEL_CURSO_CARD, has_text=curso["nome"]), codigo,
                       f"o cartão do curso {curso['nome']!r}")

    def a1():
        page = pagina("aluno")
        card = cartao(page, s["a"], "A1")
        turma = card.locator(SEL_CURSO_TURMA)
        try:
            turma.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("A1: o cartão do curso com turma não mostra curso-turma")
        texto = _normalizar(turma.first.inner_text())
        if f"Turma: {TURMA_ALFA}" not in texto:
            raise Falha(f"A1: curso-turma mostra {texto!r} (esperado 'Turma: {TURMA_ALFA}')")
        if INICIO_ALFA_DESLOCADO in texto:
            raise Falha(f"A1: a data de início foi deslocada para {INICIO_ALFA_DESLOCADO}: {texto!r}")
        if INICIO_ALFA_TELA not in texto:
            raise Falha(f"A1: curso-turma não mostra o início {INICIO_ALFA_TELA}: {texto!r}")

    def a2():
        page = pagina("aluno")
        card = cartao(page, s["b"], "A2")
        cartao(page, s["a"], "A2")
        n = card.locator(SEL_CURSO_TURMA).count()
        if n:
            raise Falha(f"A2: o cartão do curso sem turma tem {n} curso-turma (esperado nenhum)")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("D1", "Gestão abre o detalhe do aluno pelo nome: matrículas com curso, turma, status e data", d1)
    cenario("D2", "Gestão vê os pagamentos do aluno com valor em R$", d2)
    cenario("D3", "Financeiro vê os pagamentos do aluno com valor em R$", d3)
    cenario("D4", "Suporte vê o detalhe do aluno sem nenhum valor em R$", d4)
    cenario("C1", "Gestão abre os alunos do curso: nome, e-mail, turma e status", c1)
    cenario("C2", "filtro de status na lista de alunos do curso", c2)
    cenario("C3", "filtro de turma (inclui 'Sem turma') na lista de alunos do curso", c3)
    cenario("C4", "Suporte vê a lista de alunos do curso sem valor em R$", c4)
    cenario("A1", "área do aluno: 'Turma: <nome>' e início 01/11/2026 sem deslocar o dia", a1)
    cenario("A2", "área do aluno: curso sem turma não mostra curso-turma", a2)
    cenario("K1", "sem erros de console de /api nem exceções de página", k1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
