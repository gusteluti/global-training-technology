"""E2E da entrega U8 - edicao de turma, termino e horario (D83, modo autonomo D69).

Backend correspondente: backend/tests/test_u8_turmas.py.
Teste VERMELHO escrito antes da implementacao: hoje a tela de turmas (aba "Cursos" de /admin) nao tem
`turma-editar`, `turma-excluir`, `turma-erro`, `turma-new-end` nem `turma-new-schedule`; o catalogo e o cartao do
aluno nao mostram horario nem termino.

Contrato de tela (D83):
  - Dashboard de cursos (so Gestao): cada turma ganha `turma-editar` (formulario na linha: `turma-edit-nome`,
    `turma-edit-inicio`, `turma-edit-fim`, `turma-edit-horario`, `turma-edit-capacidade`, `turma-edit-salvar`,
    `turma-edit-cancelar`) e `turma-excluir` (window.confirm com o nome; o 409 da L1 aparece em `turma-erro`).
    A criacao ganha `turma-new-end` e `turma-new-schedule`.
  - Catalogo: o rotulo da turma inclui o horario quando houver.
  - Area do aluno: `curso-turma` acrescenta ` · <horario>` e ` · término em dd/mm/aaaa` quando houver.

Escolhas de forma do teste (nenhuma define politica):
  - Os campos `turma-edit-*` sao procurados na pagina depois do clique em `turma-editar` (o teste abre um formulario
    por vez); o formulario pode substituir a linha ou aparecer abaixo dela.
  - O novo nome e conferido na tela (`turma-name` da linha) sem recarregar; o novo horario e conferido na API
    (D83 nao fixa onde o horario aparece na linha da turma).
  - A mensagem de termino antes do inicio pode vir do backend (422) ou de validacao no formulario; o teste so exige o
    texto exato em `turma-erro` e que nada mude na API.
  - `turma-erro` e o testid novo da D83; o `turma-error` da L1 nao e usado por este teste.
  - Todo dialogo (confirm) e aceito; a exclusao exige um confirm cujo texto contenha o nome da turma.
  - Datas do formulario preenchidas em AAAA-MM-DD (input date do Chromium).

Seed (harness D58, SQLite temporario; datas relativas a hoje, D81): curso A (com material) e curso B criados pela API
de Gestao; turma "Turma Aluno U8" no curso A (inicio +20, termino +80, horario, capacidade 20) com Rui ativo nela;
turma "Turma Catalogo U8" no curso B (inicio +12, horario proprio, capacidade 10); Lia (aluna sem matricula).

Cenarios:
  S0 pre-condicao: Gestao abre a aba Cursos e ve a turma-row do seed (o red e por falta da U8, nao do harness)
  C1 Gestao cria turma com termino e horario (turma-new-end, turma-new-schedule); a API grava os dois
  E1 Gestao edita nome e horario pela linha (turma-editar ... turma-edit-salvar); o novo nome aparece; API confere
  E2 termino antes do inicio na edicao: turma-erro com o texto exato; nada muda na API
  X1 Gestao exclui a turma vazia (confirm com o nome): a linha some e a API nao a tem mais
  X2 excluir a turma com aluno: turma-erro com o texto do 409 da L1; a linha e a turma continuam
  R1 Suporte ve as turmas mas nao ve turma-editar nem turma-excluir
  K1 catalogo (Lia): o rotulo da turma do curso B inclui o horario
  A1 area do aluno (Rui): curso-turma mostra " · <horario>" e " · término em dd/mm/aaaa"
  Z1 sem erros de console de /api fora dos provocados (409 da exclusao, 422 do termino) nem excecoes de pagina

Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_u8_turmas_angular.py -s
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-u8-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
FUSO = "America/Sao_Paulo"
IDIOMA = "en-US"
URL_MATERIAL = "https://materiais.test/u8/apostila-e2e.pdf"

ERR_FIM = "A data de término não pode ser anterior ao início."
ERR_DEL = "A turma tem matrículas e não pode ser removida."

HORARIO_ALUNO = "Seg e Qua, 19h às 22h"
HORARIO_CATALOGO = "Ter e Qui, 18h às 21h"
HORARIO_NOVA = "Sábados, 8h às 12h"
HORARIO_EDITADO = "Sextas, 14h às 18h"
TURMA_ALUNO = "Turma Aluno U8"
TURMA_CATALOGO = "Turma Catalogo U8"
TURMA_NOVA = "Turma Nova U8"
TURMA_EDITADA = "Turma Editada U8"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_ROW = '[data-testid="turma-row"]'
SEL_NAME = '[data-testid="turma-name"]'
SEL_NEW_COURSE = '[data-testid="turma-new-course"]'
SEL_NEW_NAME = '[data-testid="turma-new-name"]'
SEL_NEW_START = '[data-testid="turma-new-start"]'
SEL_NEW_END = '[data-testid="turma-new-end"]'
SEL_NEW_SCHEDULE = '[data-testid="turma-new-schedule"]'
SEL_NEW_CAPACITY = '[data-testid="turma-new-capacity"]'
SEL_CREATE = '[data-testid="turma-create"]'
SEL_EDITAR = '[data-testid="turma-editar"]'
SEL_EDIT_NOME = '[data-testid="turma-edit-nome"]'
SEL_EDIT_INICIO = '[data-testid="turma-edit-inicio"]'
SEL_EDIT_FIM = '[data-testid="turma-edit-fim"]'
SEL_EDIT_HORARIO = '[data-testid="turma-edit-horario"]'
SEL_EDIT_SALVAR = '[data-testid="turma-edit-salvar"]'
SEL_EDIT_CANCELAR = '[data-testid="turma-edit-cancelar"]'
SEL_EXCLUIR = '[data-testid="turma-excluir"]'
SEL_ERRO = '[data-testid="turma-erro"]'
SEL_CURSO_CARD = '[data-testid="curso-card"]'
SEL_CURSO_TURMA = '[data-testid="curso-turma"]'
SEL_CATALOGO_CARD = '[data-testid="catalogo-card"]'
SEL_CATALOGO_TURMA = '[data-testid="catalogo-turma"]'


class Falha(Exception):
    """Falha de um passo de cenario; a mensagem diz o que faltou na tela."""


# ---------------------------------------------------------------------------------------------
# Datas (dia de Sao Paulo, D71; relativas, D81)
# ---------------------------------------------------------------------------------------------

def _dia_sp(delta):
    return ((datetime.now(timezone.utc) - timedelta(hours=3)).date() + timedelta(days=delta)).isoformat()


def _br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


INICIO_ALUNO = _dia_sp(20)
FIM_ALUNO = _dia_sp(80)
INICIO_NOVA = _dia_sp(30)
FIM_NOVA = _dia_sp(90)


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


def _executar(comando, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    try:
        conn.execute(comando, params)
        conn.commit()
    finally:
        conn.close()


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, rotulo, preco, materiais):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"u8-{rotulo.lower()}-{sufixo}"
    nome = f"Curso U8 {rotulo} {sufixo}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso U8 do e2e", "price": preco,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": materiais,
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome, "preco": preco}


def criar_turma(token, curso, nome, **campos):
    status, corpo = _api("POST", "/api/admin/classes", {"course_id": curso["id"], "name": nome, **campos}, token=token)
    if status != 200:
        raise RuntimeError(f"seed: POST /api/admin/classes {nome} respondeu HTTP {status}: {corpo}")
    return corpo["class"]


def criar_aluno(Database, rotulo):
    from core.security import get_password_hash  # noqa: PLC0415  (backend no sys.path depois de abrir_banco)

    email = f"e2e.u8.{rotulo.lower()}.{uuid.uuid4().hex[:10]}@teste.com"
    nome = f"{rotulo} U8 {uuid.uuid4().hex[:4]}"
    uid = Database.add_user(email, nome, get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: nao foi possivel criar {email}")
    return {"uid": uid, "email": email, "nome": nome}


def matricula_ativa(Database, aluno, curso, class_id):
    eid = Database.create_enrollment(aluno["uid"], curso["id"], f"{curso['id']}:u8:{uuid.uuid4().hex}")
    pid = Database.record_payment(eid, curso["preco"], "mercado_pago")
    _executar("UPDATE payments SET status = 'approved', transaction_id = ? WHERE id = ?",
              (f"mp-u8-e2e-{uuid.uuid4().hex[:10]}", pid))
    _executar("UPDATE enrollments SET status = 'active', class_id = ? WHERE id = ?", (class_id, eid))
    return eid


def semear():
    token = token_gestao()
    curso_a = criar_curso(token, "A", 240.0, [{"title": "Apostila U8", "url": URL_MATERIAL, "type": "pdf"}])
    curso_b = criar_curso(token, "B", 120.0, [])
    turma_aluno = criar_turma(token, curso_a, TURMA_ALUNO, starts_on=INICIO_ALUNO, ends_on=FIM_ALUNO,
                              schedule=HORARIO_ALUNO, capacity=20)
    turma_catalogo = criar_turma(token, curso_b, TURMA_CATALOGO, starts_on=_dia_sp(12), schedule=HORARIO_CATALOGO,
                                 capacity=10)
    Database = abrir_banco(ALVO["db_path"])
    rui = criar_aluno(Database, "Rui")
    lia = criar_aluno(Database, "Lia")
    matricula_ativa(Database, rui, curso_a, turma_aluno["id"])
    return {"token": token, "a": curso_a, "b": curso_b, "turma_aluno": turma_aluno, "turma_catalogo": turma_catalogo,
            "rui": rui, "lia": lia}


def turmas_api(token, course_id=None):
    caminho = "/api/admin/classes" + (f"?course_id={urllib.parse.quote(course_id)}" if course_id else "")
    status, corpo = _api("GET", caminho, token=token)
    if status != 200:
        raise Falha(f"GET /api/admin/classes respondeu HTTP {status}")
    return corpo["classes"]


def turma_api(token, nome):
    achadas = [t for t in turmas_api(token) if t["name"] == nome]
    return achadas[0] if len(achadas) == 1 else None


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


def visivel(locator):
    return locator.count() > 0 and locator.first.is_visible()


def abrir_cursos(page):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
    clicar_aba(page, "Cursos")


def linha_da_turma(page, nome, codigo):
    def leitura():
        nomes = [_normalizar(t) for t in page.locator(f"{SEL_ROW} {SEL_NAME}").all_inner_texts()]
        return None if nome in nomes else f"nenhuma turma-row com turma-name {nome!r} (vistas: {nomes})"
    esperar_condicao(leitura, codigo, TIMEOUT * 3)
    return page.locator(SEL_ROW).filter(has=page.locator(SEL_NAME, has_text=re.compile(rf"^\s*{re.escape(nome)}\s*$")))


def linha_some(page, nome, codigo):
    def leitura():
        nomes = [_normalizar(t) for t in page.locator(f"{SEL_ROW} {SEL_NAME}").all_inner_texts()]
        return None if nome not in nomes else f"a turma-row de {nome!r} continua na tela"
    esperar_condicao(leitura, codigo, TIMEOUT * 3)


def botao_da_linha(linha, seletor, codigo, descricao):
    botao = linha.locator(seletor)
    if not visivel(botao):
        raise Falha(f"{codigo}: a turma-row nao tem {descricao}")
    return botao.first


def erro_na_tela(page, esperado, codigo):
    def leitura():
        alvo = page.locator(SEL_ERRO)
        if not alvo.count() or not alvo.first.is_visible():
            return f"turma-erro nao aparece (esperado {esperado!r})"
        texto = _normalizar(alvo.first.inner_text())
        return None if esperado in texto else f"turma-erro mostra {texto!r}, esperado {esperado!r}"
    esperar_condicao(leitura, codigo, TIMEOUT * 3)


def abrir_edicao(page, nome, codigo):
    linha = linha_da_turma(page, nome, codigo)
    botao_da_linha(linha.first, SEL_EDITAR, codigo, "turma-editar").click(timeout=TIMEOUT)
    page.wait_for_timeout(300)
    return esperar(page.locator(SEL_EDIT_NOME), codigo, "o campo turma-edit-nome depois de turma-editar")


def preencher(page, seletor, valor, codigo, descricao):
    campo = esperar(page.locator(seletor), codigo, descricao)
    campo.fill(valor, timeout=TIMEOUT)


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("u8") as ambiente:
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

def test_u8_turmas_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    provocados = []
    contextos = []
    paginas = {}
    dialogos = []

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
            achado = ERRO_HTTP.search(msg.text)
            if msg.type != "error" or not achado or "/api/" not in (url + msg.text):
                return
            if achado.group(1) in ("409", "422") and "/classes" in (url + msg.text):
                provocados.append(achado.group(1))
                return
            erros_console.append(f"{msg.text[:120]} ({url})")

        def ao_dialogo(dialogo):
            dialogos.append(dialogo.message)
            dialogo.accept()

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        page.on("dialog", ao_dialogo)
        return page

    def pagina(perfil):
        if perfil not in paginas:
            page = nova_pagina()
            email, senha, destino = {
                "gestao": (GESTAO_EMAIL, GESTAO_SENHA, "admin"),
                "sup": (SUPORTE_EMAIL, SUPORTE_SENHA, "admin"),
                "rui": (s["rui"]["email"], SENHA, "student"),
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

    def s0():
        page = pagina("gestao")
        abrir_cursos(page)
        linha_da_turma(page, TURMA_ALUNO, "S0")

    def c1():
        page = pagina("gestao")
        abrir_cursos(page)
        curso = esperar(page.locator(SEL_NEW_COURSE), "C1", "o select turma-new-course")
        curso.select_option(value=s["a"]["id"], timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        preencher(page, SEL_NEW_NAME, TURMA_NOVA, "C1", "o campo turma-new-name")
        preencher(page, SEL_NEW_START, INICIO_NOVA, "C1", "o campo turma-new-start")
        preencher(page, SEL_NEW_END, FIM_NOVA, "C1", "o campo turma-new-end")
        preencher(page, SEL_NEW_SCHEDULE, HORARIO_NOVA, "C1", "o campo turma-new-schedule")
        preencher(page, SEL_NEW_CAPACITY, "15", "C1", "o campo turma-new-capacity")
        esperar(page.locator(SEL_CREATE), "C1", "o botao turma-create").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        linha_da_turma(page, TURMA_NOVA, "C1")

        def banco():
            t = turma_api(s["token"], TURMA_NOVA)
            if t is None:
                return "a turma criada pela tela nao esta em GET /api/admin/classes"
            obtido = (t.get("starts_on"), t.get("ends_on"), t.get("schedule"), t.get("capacity"))
            esperado = (INICIO_NOVA, FIM_NOVA, HORARIO_NOVA, 15)
            return None if obtido == esperado else f"API: (inicio, termino, horario, capacidade) = {obtido}, " \
                                                   f"esperado {esperado}"
        esperar_condicao(banco, "C1")

    def e1():
        page = pagina("gestao")
        abrir_cursos(page)
        nome = abrir_edicao(page, TURMA_NOVA, "E1")
        nome.fill(TURMA_EDITADA, timeout=TIMEOUT)
        preencher(page, SEL_EDIT_HORARIO, HORARIO_EDITADO, "E1", "o campo turma-edit-horario")
        esperar(page.locator(SEL_EDIT_SALVAR), "E1", "o botao turma-edit-salvar").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        linha_da_turma(page, TURMA_EDITADA, "E1")
        linha_some(page, TURMA_NOVA, "E1")

        def banco():
            t = turma_api(s["token"], TURMA_EDITADA)
            if t is None:
                return "a turma editada nao esta em GET /api/admin/classes com o novo nome"
            obtido = (t.get("starts_on"), t.get("ends_on"), t.get("schedule"), t.get("capacity"))
            esperado = (INICIO_NOVA, FIM_NOVA, HORARIO_EDITADO, 15)
            return None if obtido == esperado else f"API depois da edicao: {obtido}, esperado {esperado}"
        esperar_condicao(banco, "E1")

    def e2():
        page = pagina("gestao")
        abrir_cursos(page)
        abrir_edicao(page, TURMA_EDITADA, "E2")
        preencher(page, SEL_EDIT_INICIO, INICIO_NOVA, "E2", "o campo turma-edit-inicio")
        preencher(page, SEL_EDIT_FIM, _dia_sp(29), "E2", "o campo turma-edit-fim")
        esperar(page.locator(SEL_EDIT_SALVAR), "E2", "o botao turma-edit-salvar").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        erro_na_tela(page, ERR_FIM, "E2")
        t = turma_api(s["token"], TURMA_EDITADA)
        if t is None or (t.get("starts_on"), t.get("ends_on")) != (INICIO_NOVA, FIM_NOVA):
            raise Falha(f"E2: a recusa nao pode mudar a turma na API: {t}")
        if visivel(page.locator(SEL_EDIT_CANCELAR)):
            page.locator(SEL_EDIT_CANCELAR).first.click(timeout=TIMEOUT)

    def x1():
        page = pagina("gestao")
        abrir_cursos(page)
        linha = linha_da_turma(page, TURMA_EDITADA, "X1")
        antes = len(dialogos)
        botao_da_linha(linha.first, SEL_EXCLUIR, "X1", "turma-excluir").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        esperar_condicao(lambda: None if len(dialogos) > antes else "nenhum window.confirm ao excluir", "X1")
        if not any(TURMA_EDITADA in d for d in dialogos[antes:]):
            raise Falha(f"X1: o confirm da exclusao nao cita o nome da turma: {dialogos[antes:]}")
        linha_some(page, TURMA_EDITADA, "X1")
        esperar_condicao(lambda: None if turma_api(s["token"], TURMA_EDITADA) is None
                         else "a turma excluida continua em GET /api/admin/classes", "X1")

    def x2():
        page = pagina("gestao")
        abrir_cursos(page)
        linha = linha_da_turma(page, TURMA_ALUNO, "X2")
        antes = len(dialogos)
        botao_da_linha(linha.first, SEL_EXCLUIR, "X2", "turma-excluir").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        esperar_condicao(lambda: None if len(dialogos) > antes else "nenhum window.confirm ao excluir", "X2")
        erro_na_tela(page, ERR_DEL, "X2")
        linha_da_turma(page, TURMA_ALUNO, "X2")
        if turma_api(s["token"], TURMA_ALUNO) is None:
            raise Falha("X2: a turma com aluno sumiu da API")

    def r1():
        page = pagina("sup")
        abrir_cursos(page)
        linha_da_turma(page, TURMA_ALUNO, "R1")
        page.wait_for_timeout(500)
        for seletor, nome in ((SEL_EDITAR, "turma-editar"), (SEL_EXCLUIR, "turma-excluir"),
                              (SEL_NEW_END, "turma-new-end"), (SEL_NEW_SCHEDULE, "turma-new-schedule")):
            if page.locator(seletor).count():
                raise Falha(f"R1: o Suporte ve {nome}")

    def k1():
        page = pagina("lia")
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        card = esperar(page.locator(SEL_CATALOGO_CARD).filter(has_text=s["b"]["nome"]), "K1",
                       f"o catalogo-card de {s['b']['nome']!r}")
        sel = esperar(card.locator(SEL_CATALOGO_TURMA), "K1", "a selecao catalogo-turma do curso B")

        def leitura():
            textos = [_normalizar(t) for t in sel.locator("option").all_text_contents()]
            alvo = [t for t in textos if TURMA_CATALOGO in t]
            if len(alvo) != 1:
                return f"a turma {TURMA_CATALOGO!r} aparece {len(alvo)} vez(es) nas opcoes: {textos}"
            return None if HORARIO_CATALOGO in alvo[0] else \
                f"o rotulo da turma nao inclui o horario {HORARIO_CATALOGO!r}: {alvo[0]!r}"
        esperar_condicao(leitura, "K1")

    def a1():
        page = pagina("rui")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        card = esperar(page.locator(SEL_CURSO_CARD).filter(has_text=s["a"]["nome"]), "A1",
                       f"o curso-card de {s['a']['nome']!r}")
        turma = esperar(card.locator(SEL_CURSO_TURMA), "A1", "curso-turma no cartao do curso A")

        def leitura():
            texto = _normalizar(turma.inner_text())
            faltas = [trecho for trecho in (f"Turma: {TURMA_ALUNO}", f"· {HORARIO_ALUNO}",
                                            f"· término em {_br(FIM_ALUNO)}") if trecho not in texto]
            return None if not faltas else f"curso-turma mostra {texto!r}; faltam {faltas}"
        esperar_condicao(leitura, "A1")

    def z1():
        if erros_console:
            raise Falha(f"Z1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("S0", "pre-condicao: Gestao ve a turma do seed na aba Cursos", s0)
    cenario("C1", "Gestao cria turma com termino e horario", c1)
    cenario("E1", "Gestao edita nome e horario pela linha e ve o novo nome", e1)
    cenario("E2", "termino antes do inicio aparece em turma-erro e nada muda", e2)
    cenario("X1", "Gestao exclui a turma vazia com confirm e ela some", x1)
    cenario("X2", "excluir turma com aluno mostra o 409 em turma-erro", x2)
    cenario("R1", "Suporte nao ve edicao nem exclusao de turma", r1)
    cenario("K1", "catalogo mostra o horario no rotulo da turma", k1)
    cenario("A1", "cartao do aluno mostra horario e termino da turma", a1)
    cenario("Z1", "sem erros de console de /api fora dos provocados nem excecoes de pagina", z1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
