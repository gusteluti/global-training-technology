"""E2E da entrega U1/U2 — busca, paginação e exportação CSV (D74). Modo autônomo: D69.

Backend correspondente: backend/tests/test_u1_busca_csv.py.

Contrato de tela (D74 + pedido do orquestrador):
  - Dashboard de alunos (aba "Alunos" de /admin):
      data-testid="alunos-busca"        -> campo de busca (nome ou e-mail, sem caixa)
      data-testid="paginacao-anterior"  -> botão da página anterior
      data-testid="paginacao-proxima"   -> botão da próxima página
      data-testid="paginacao-info"      -> indicador da página atual
      25 alunos por página na tela.
  - Dashboard financeiro (aba "Financeiro"):
      data-testid="financeiro-busca"         -> busca (e-mail, nome ou curso)
      data-testid="financeiro-filtro-status" -> <select> de status do pagamento
  - Auditoria (aba "Auditoria", só Gestão):
      data-testid="auditoria-busca", "auditoria-data-inicio", "auditoria-data-fim" (dias de São Paulo)
  - data-testid="exportar-csv": visível para Gestão e Financeiro (Alunos; Financeiro), AUSENTE para Suporte.
    O clique baixa um arquivo .csv (UTF-8 com BOM, separador ';').

Escolhas de forma aceitas pelo teste (nenhuma define política):
  - a busca pode filtrar ao digitar ou ao Enter (o teste digita e pressiona Enter);
  - o filtro de status é escolhido pelo `value` ("approved", "pending") OU pelo texto (Aprovado, Pendente);
  - os campos de data podem ser <input type="date"> (o teste preenche AAAA-MM-DD) ou texto (o teste preenche
    dd/mm/aaaa); o filtro vale ao alterar o campo ou ao Enter;
  - o texto do indicador de página não é fixado: só precisa mostrar o número da página atual (1, depois 2) e mudar;
  - o download pode vir de link direto ou de Blob (o teste usa o evento de download do Playwright).

Seed (harness D58, SQLite temporário):
  - 30 alunos "Aluno Pag NN" (sem matrícula) + Zuleica (matrícula ativa, pagamento aprovado 777,77 em
    2026-10-08 01:30 UTC) + Otávio (matrícula pendente, pagamento pendente 333,33,
    há 2 dias): 32 alunos -> 2 páginas (25 + 7).
  - Curso U1 criado pela API de Gestão.
  - Auditoria (INSERT direto; a trilha só recusa UPDATE/DELETE):
      "U1E2E alfa" em 2026-10-08 01:30 UTC (dia 07/10 em São Paulo)
      "U1E2E beta" em 2026-10-09 15:00 UTC
      "U1E2E gama" em 2026-10-05 12:00 UTC

Cenários:
  B1 Gestão busca "zULEICA" em alunos-busca: só a linha da Zuleica
  P1 Alunos página 1: 25 linhas e paginacao-info com a página 1
  P2 paginacao-proxima: 7 linhas, nenhuma da página 1, paginacao-info muda para a página 2
  P3 paginacao-anterior: volta às 25 linhas da página 1
  F1 Financeiro busca o e-mail do Otávio: só o pagamento do Otávio
  F2 Financeiro filtra status Aprovado: Zuleica sim, Otávio não
  A1 Auditoria: busca "U1E2E alfa" mostra só esse evento
  A2 Auditoria: busca "U1E2E" + início e fim 2026-10-07 mostram só "alfa" (01:30 UTC do dia 08 é dia 07 em SP)
  X1 Gestão: exportar-csv nos Alunos baixa .csv com BOM e ';'
  X2 Financeiro: exportar-csv na aba Financeiro baixa .csv com BOM e ';'
  X3 Financeiro: exportar-csv visível na aba Alunos
  X4 Suporte: nenhum exportar-csv na aba Alunos nem na lista de alunos do curso
  K1 sem erros de console de /api (4xx/5xx) nem exceções de página

Ajuste mecânico D74 (U1) -> D81 (S6, autoridade 4.3): o pagamento pendente do Otávio tinha data fixa (2026-09-20),
que a S6 (pendente com mais de 7 dias vira `cancelled` nas leituras do dashboard) expira, e o filtro "Pendente" (F2)
deixaria de achá-lo. A data passa a ser relativa a hoje (UTC, há 2 dias). Zuleica e os eventos de auditoria continuam
em instantes fixos (aprovado / trilha de auditoria, sem expiração; base dos testes de fuso). Intenção preservada.

Execução (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_u1_busca_csv_angular.py -s
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
from servidor_e2e_h1 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)

ALVO = {"base": "", "api": "", "db_path": None}
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
FUSO = "America/Sao_Paulo"
IDIOMA = "en-US"

POR_PAGINA = 25
N_PAGINACAO = 30
TOTAL_ALUNOS = N_PAGINACAO + 2
BOM = b"\xef\xbb\xbf"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_ALUNOS_BUSCA = '[data-testid="alunos-busca"]'
SEL_PAG_ANTERIOR = '[data-testid="paginacao-anterior"]'
SEL_PAG_PROXIMA = '[data-testid="paginacao-proxima"]'
SEL_PAG_INFO = '[data-testid="paginacao-info"]'
SEL_FIN_BUSCA = '[data-testid="financeiro-busca"]'
SEL_FIN_STATUS = '[data-testid="financeiro-filtro-status"]'
SEL_AUD_BUSCA = '[data-testid="auditoria-busca"]'
SEL_AUD_INICIO = '[data-testid="auditoria-data-inicio"]'
SEL_AUD_FIM = '[data-testid="auditoria-data-fim"]'
SEL_AUD_ROW = '[data-testid="audit-row"]'
SEL_EXPORTAR = '[data-testid="exportar-csv"]'
SEL_CURSO_LINK = '[data-testid="curso-alunos-link"]'
SEL_CURSO_ALUNOS = '[data-testid="curso-alunos"]'
SEL_LINHAS_ALUNOS = "app-students-dashboard tbody tr"
SEL_LINHAS_FIN = "app-financial-dashboard tbody tr"
MARCA_EMAIL = "e2e.u1."


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


def criar_curso(token):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"u1-{sufixo}"
    nome = f"Curso U1 {sufixo}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso U1 do e2e", "price": 777.77,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": [],
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome}


def criar_aluno(Database, nome, rotulo):
    email = f"{MARCA_EMAIL}{rotulo}.{uuid.uuid4().hex[:6]}@teste.com"
    uid = Database.add_user(email, nome, None, role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return {"uid": uid, "email": email, "nome": nome}


def matricular(Database, aluno, course_id, status, data, valor, status_pagamento):
    enrollment_id = Database.create_enrollment(aluno["uid"], course_id, f"{course_id}:u1:{uuid.uuid4().hex}")
    _sql("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (status, data, enrollment_id))
    pid = Database.record_payment(enrollment_id, valor, "mercado_pago")
    if status_pagamento != "pending":
        Database.update_payment_status(pid, status_pagamento, f"mp-u1-{uuid.uuid4().hex[:6]}")
    _sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (data, data, pid))


def evento_auditoria(detalhe, criado_em):
    _sql("""INSERT INTO audit_logs (user_id, role, action, detail, actor_email, actor_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
         (None, "admin", "u1.e2e", detalhe, "ops.u1@teste.com", "Pessoa U1", criado_em))


def semear():
    token = token_gestao()
    curso = criar_curso(token)
    Database = abrir_banco(ALVO["db_path"])
    pag = [criar_aluno(Database, f"Aluno Pag {i:02d}", f"pag{i:02d}") for i in range(N_PAGINACAO)]
    zuleica = criar_aluno(Database, "Zuleica Buscavel", "zuleica")
    otavio = criar_aluno(Database, "Otavio Pendente", "otavio")
    matricular(Database, zuleica, curso["id"], "active", "2026-10-08 01:30:00", 777.77, "approved")
    matricular(Database, otavio, curso["id"], "pending",
               (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d 12:00:00"), 333.33, "pending")
    evento_auditoria("U1E2E alfa", "2026-10-08 01:30:00")
    evento_auditoria("U1E2E beta", "2026-10-09 15:00:00")
    evento_auditoria("U1E2E gama", "2026-10-05 12:00:00")
    return {"curso": curso, "pag": pag, "zuleica": zuleica, "otavio": otavio}


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


def abrir_aba(page, nome):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
    clicar_aba(page, nome)


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


def textos(page, seletor):
    return [_normalizar(t) for t in page.eval_on_selector_all(seletor, "els => els.map(e => e.innerText)")]


def linhas_marcadas(page, seletor):
    """Linhas da tabela que têm um e-mail semeado pelo teste."""
    return [t for t in textos(page, seletor) if MARCA_EMAIL in t]


def emails_das_linhas(linhas):
    return {m for linha in linhas for m in re.findall(rf"{re.escape(MARCA_EMAIL)}[\w.]+@teste\.com", linha)}


def digitar(page, seletor, texto, codigo, descricao):
    campo = esperar(page.locator(seletor), codigo, descricao)
    campo.fill(texto)
    campo.press("Enter")
    page.wait_for_load_state("networkidle")


def preencher_data(page, seletor, iso, codigo, descricao):
    campo = esperar(page.locator(seletor), codigo, descricao)
    tipo = (campo.get_attribute("type") or "").lower()
    if tipo == "date":
        campo.fill(iso)
    else:
        ano, mes, dia = iso.split("-")
        campo.fill(f"{dia}/{mes}/{ano}")
    campo.dispatch_event("change")
    campo.press("Enter")
    page.wait_for_load_state("networkidle")


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


def baixar_csv(page, codigo):
    botao = esperar(page.locator(SEL_EXPORTAR), codigo, "o botão exportar-csv")
    try:
        with page.expect_download(timeout=TIMEOUT * 2) as info:
            botao.click(timeout=TIMEOUT)
        download = info.value
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: clicar em exportar-csv não iniciou nenhum download")
    nome = download.suggested_filename or ""
    if not nome.lower().endswith(".csv"):
        raise Falha(f"{codigo}: o arquivo baixado não é .csv: {nome!r}")
    caminho = download.path()
    if not caminho:
        raise Falha(f"{codigo}: o download falhou: {download.failure()}")
    conteudo = Path(caminho).read_bytes()
    if not conteudo.startswith(BOM):
        raise Falha(f"{codigo}: o CSV não começa com BOM UTF-8: {conteudo[:20]!r}")
    primeira = conteudo[len(BOM):].split(b"\n", 1)[0]
    if b";" not in primeira:
        raise Falha(f"{codigo}: o cabeçalho do CSV não usa ';': {primeira[:120]!r}")
    return conteudo


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("u1") as ambiente:
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

def test_u1_busca_csv_angular_e2e(servidores, browser):
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
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, timezone_id=FUSO, locale=IDIOMA,
                                  accept_downloads=True)
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
            email, senha = {
                "gestao": (GESTAO_EMAIL, GESTAO_SENHA),
                "fin": (FINANCEIRO_EMAIL, FINANCEIRO_SENHA),
                "sup": (SUPORTE_EMAIL, SUPORTE_SENHA),
            }[perfil]
            entrar(page, email, senha, "admin")
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

    def esperar_alunos(page, n, codigo):
        def leitura():
            linhas = linhas_marcadas(page, SEL_LINHAS_ALUNOS)
            return None if len(linhas) == n else f"{len(linhas)} linhas de aluno na tela (esperado {n})"
        esperar_condicao(leitura, codigo)
        return emails_das_linhas(linhas_marcadas(page, SEL_LINHAS_ALUNOS))

    def info_pagina(page, numero, codigo):
        def leitura():
            loc = page.locator(SEL_PAG_INFO)
            if loc.count() == 0:
                return "o indicador paginacao-info não aparece"
            texto = _normalizar(loc.first.inner_text())
            return None if re.search(rf"\b{numero}\b", texto) else f"paginacao-info não mostra a página {numero}: {texto!r}"
        esperar_condicao(leitura, codigo)
        return _normalizar(page.locator(SEL_PAG_INFO).first.inner_text())

    estado = {}

    def b1():
        page = pagina("gestao")
        abrir_aba(page, "Alunos")
        digitar(page, SEL_ALUNOS_BUSCA, "zULEICA", "B1", "o campo alunos-busca")
        emails = esperar_alunos(page, 1, "B1")
        if emails != {s["zuleica"]["email"]}:
            raise Falha(f"B1: a busca mostra {emails} (esperado só a Zuleica)")

    def p1():
        page = pagina("gestao")
        abrir_aba(page, "Alunos")
        emails = esperar_alunos(page, POR_PAGINA, "P1")
        estado["pagina1"] = emails
        estado["info1"] = info_pagina(page, 1, "P1")

    def p2():
        page = pagina("gestao")
        if "pagina1" not in estado:
            raise Falha("P2: depende de P1")
        esperar(page.locator(SEL_PAG_PROXIMA), "P2", "o botão paginacao-proxima").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        emails = esperar_alunos(page, TOTAL_ALUNOS - POR_PAGINA, "P2")
        if emails & estado["pagina1"]:
            raise Falha(f"P2: a página 2 repete alunos da página 1: {sorted(emails & estado['pagina1'])[:3]}")
        if len(emails | estado["pagina1"]) != TOTAL_ALUNOS:
            raise Falha(f"P2: as duas páginas somam {len(emails | estado['pagina1'])} alunos (esperado {TOTAL_ALUNOS})")
        info2 = info_pagina(page, 2, "P2")
        if info2 == estado["info1"]:
            raise Falha(f"P2: paginacao-info não mudou: {info2!r}")

    def p3():
        page = pagina("gestao")
        if "pagina1" not in estado:
            raise Falha("P3: depende de P1")
        esperar(page.locator(SEL_PAG_ANTERIOR), "P3", "o botão paginacao-anterior").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        emails = esperar_alunos(page, POR_PAGINA, "P3")
        if emails != estado["pagina1"]:
            raise Falha("P3: paginacao-anterior não voltou aos alunos da página 1")
        info_pagina(page, 1, "P3")

    def esperar_fin(page, presentes, ausentes, codigo):
        def leitura():
            emails = emails_das_linhas(linhas_marcadas(page, SEL_LINHAS_FIN))
            faltam = [a["email"] for a in presentes if a["email"] not in emails]
            sobram = [a["email"] for a in ausentes if a["email"] in emails]
            if faltam:
                return f"faltam na tabela de transações: {faltam}"
            if sobram:
                return f"não deveriam aparecer com o filtro: {sobram}"
            return None
        esperar_condicao(leitura, codigo)

    def f1():
        page = pagina("fin")
        abrir_aba(page, "Financeiro")
        esperar_fin(page, [s["zuleica"], s["otavio"]], [], "F1 (sem filtro)")
        digitar(page, SEL_FIN_BUSCA, s["otavio"]["email"], "F1", "o campo financeiro-busca")
        esperar_fin(page, [s["otavio"]], [s["zuleica"]], "F1")

    def f2():
        page = pagina("fin")
        abrir_aba(page, "Financeiro")
        esperar_fin(page, [s["zuleica"], s["otavio"]], [], "F2 (sem filtro)")
        escolher(page, SEL_FIN_STATUS, ("approved",), r"^Aprovad", "F2")
        esperar_fin(page, [s["zuleica"]], [s["otavio"]], "F2 (Aprovado)")
        escolher(page, SEL_FIN_STATUS, ("pending",), r"^Pendente", "F2")
        esperar_fin(page, [s["otavio"]], [s["zuleica"]], "F2 (Pendente)")

    def esperar_auditoria(page, esperados, codigo):
        def leitura():
            linhas = [l for l in textos(page, SEL_AUD_ROW) if "U1E2E" in l]
            achados = sorted(re.findall(r"U1E2E (\w+)", " ".join(linhas)))
            return None if achados == sorted(esperados) else f"eventos U1E2E na tela {achados} (esperado {sorted(esperados)})"
        esperar_condicao(leitura, codigo)

    def a1():
        page = pagina("gestao")
        abrir_aba(page, "Auditoria")
        esperar_auditoria(page, ["alfa", "beta", "gama"], "A1 (sem filtro)")
        digitar(page, SEL_AUD_BUSCA, "U1E2E alfa", "A1", "o campo auditoria-busca")
        esperar_auditoria(page, ["alfa"], "A1")

    def a2():
        page = pagina("gestao")
        abrir_aba(page, "Auditoria")
        esperar_auditoria(page, ["alfa", "beta", "gama"], "A2 (sem filtro)")
        digitar(page, SEL_AUD_BUSCA, "U1E2E", "A2", "o campo auditoria-busca")
        preencher_data(page, SEL_AUD_INICIO, "2026-10-07", "A2", "o campo auditoria-data-inicio")
        preencher_data(page, SEL_AUD_FIM, "2026-10-07", "A2", "o campo auditoria-data-fim")
        esperar_auditoria(page, ["alfa"], "A2")

    def x1():
        page = pagina("gestao")
        abrir_aba(page, "Alunos")
        esperar_alunos(page, POR_PAGINA, "X1")
        conteudo = baixar_csv(page, "X1")
        if s["zuleica"]["email"].encode() not in conteudo:
            raise Falha("X1: o CSV de alunos não tem o e-mail da Zuleica")

    def x2():
        page = pagina("fin")
        abrir_aba(page, "Financeiro")
        esperar_fin(page, [s["zuleica"], s["otavio"]], [], "X2")
        conteudo = baixar_csv(page, "X2")
        if b"777,77" not in conteudo:
            raise Falha("X2: o CSV financeiro não tem o valor 777,77 (decimal com vírgula)")

    def x3():
        page = pagina("fin")
        abrir_aba(page, "Alunos")
        esperar_alunos(page, POR_PAGINA, "X3")
        esperar(page.locator(SEL_EXPORTAR), "X3", "o botão exportar-csv na aba Alunos (Financeiro)")

    def x4():
        page = pagina("sup")
        abrir_aba(page, "Alunos")
        esperar_condicao(lambda: None if linhas_marcadas(page, SEL_LINHAS_ALUNOS) else "a lista de alunos não carregou",
                         "X4")
        page.wait_for_timeout(500)
        n = page.locator(SEL_EXPORTAR).count()
        if n:
            raise Falha(f"X4: o Suporte vê {n} botão(ões) exportar-csv na aba Alunos")
        abrir_aba(page, "Cursos")
        link = esperar(page.locator(SEL_CURSO_LINK, has_text=s["curso"]["nome"]), "X4", "o curso-alunos-link do curso U1")
        link.click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        esperar(page.locator(SEL_CURSO_ALUNOS), "X4", "a lista de alunos do curso")
        page.wait_for_timeout(500)
        n = page.locator(SEL_EXPORTAR).count()
        if n:
            raise Falha(f"X4: o Suporte vê {n} botão(ões) exportar-csv na lista de alunos do curso")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("B1", "busca de alunos sem caixa filtra as linhas", b1)
    cenario("P1", "alunos: página 1 com 25 linhas e indicador da página 1", p1)
    cenario("P2", "alunos: próxima página com o restante e indicador da página 2", p2)
    cenario("P3", "alunos: página anterior volta à página 1", p3)
    cenario("F1", "financeiro: busca por e-mail filtra as transações", f1)
    cenario("F2", "financeiro: filtro de status", f2)
    cenario("A1", "auditoria: busca pela descrição", a1)
    cenario("A2", "auditoria: datas de início e fim em dias de São Paulo", a2)
    cenario("X1", "Gestão baixa o CSV de alunos (BOM e ';')", x1)
    cenario("X2", "Financeiro baixa o CSV financeiro (BOM, ';' e vírgula decimal)", x2)
    cenario("X3", "Financeiro vê exportar-csv na aba Alunos", x3)
    cenario("X4", "Suporte não vê exportar-csv", x4)
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
