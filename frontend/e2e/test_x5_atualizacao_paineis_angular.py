"""E2E da entrega X5 - atualizacao automatica dos paineis da area do funcionario (D87, processo enxuto D84).

Teste VERMELHO escrito antes da implementacao: hoje cada aba de /admin busca os dados uma vez, ao abrir; nao ha
`atualizacao-botao`, `atualizacao-hora` nem timer.

Contrato de tela (D87):
  - As cinco abas de painel (Financeiro, Alunos, Cursos, Observabilidade de IA, Auditoria) mostram
    `atualizacao-botao` ("Atualizar") e `atualizacao-hora` ("Atualizado às HH:MM", horario de Sao Paulo, D71).
  - A cada 30 s a aba aberta busca de novo os proprios dados, sempre ligado, mantendo busca, filtro e pagina.
  - O botao busca na hora. Trocar de aba encerra o timer da aba anterior.
  - Nao atualiza enquanto: a aba do navegador esta escondida; ha um campo de texto/selecao em foco dentro do
    painel; ha formulario aberto ou acao em andamento (no Cursos: turma em edicao, matricula manual).
  - Abas de formulario (Cadastro de cursos) nao ganham o componente.

Escolhas de forma do teste (nenhuma define politica):
  - O tempo e controlado pelo relogio falso do Playwright (`page.clock`), instalado antes do login num instante fixo
    (18:00:05 UTC = 15:00 em Sao Paulo) com o navegador em UTC; `run_for(31000)` cruza um ciclo de 30 s.
  - O ciclo e conferido pela contagem de requisicoes GET ao endpoint da aba; o conteudo novo, no Financeiro.

Seed (harness D58, SQLite temporario): curso A e B pela API de Gestao, turma no curso A, alunos Rui e Lia com um
pagamento aprovado cada. Pagamentos novos sao gravados direto no banco temporario durante o teste.

Cenarios:
  S0 pre-condicao: Gestao abre o Financeiro e ve o pagamento do seed (o red e por falta da X5, nao do harness)
  H1 Financeiro mostra atualizacao-botao "Atualizar" e atualizacao-hora "Atualizado às 15:00"
  A1 com a busca "Rui" aplicada, um ciclo de 30 s traz o pagamento novo do Rui, nao o da Lia, e a busca continua
  A2 o botao Atualizar traz na hora mais um pagamento do Rui
  A3 Alunos, Cursos, IA e Auditoria tem o componente e o ciclo busca o endpoint da aba; o da aba anterior para
  P1 Cursos com turma em edicao: o ciclo nao busca e o texto digitado fica; ao cancelar, volta a buscar
  P2 aba do navegador escondida: o ciclo nao busca; visivel de novo, volta a buscar
  P3 campo de busca da Auditoria em foco: o ciclo nao busca
  R1 Cadastro de cursos nao tem o componente
  Z1 sem erros de console de /api nem excecoes de pagina

Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_x5_atualizacao_paineis_angular.py -s
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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-x5-2026"
TIMEOUT = 5000
CICLO_MS = 31_000
ERRO_HTTP = re.compile(r"status of (\d{3})")
INSTANTE = datetime(2026, 1, 15, 18, 0, 5, tzinfo=timezone.utc)  # 15:00 em Sao Paulo
HORA_SP = "15:00"

EP_FIN = "/api/dashboard/financeiro"
EP_ALUNOS = "/api/dashboard/alunos"
EP_CURSOS = "/api/dashboard/cursos"
EP_IA = "/api/dashboard/observabilidade-ia"
EP_AUDIT = "/api/admin/audit-logs"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_BOTAO = '[data-testid="atualizacao-botao"]'
SEL_HORA = '[data-testid="atualizacao-hora"]'
SEL_BUSCA_FIN = '[data-testid="financeiro-busca"]'
SEL_BUSCA_AUDIT = "#auditoria-busca"
SEL_ROW = '[data-testid="turma-row"]'
SEL_NAME = '[data-testid="turma-name"]'
SEL_EDITAR = '[data-testid="turma-editar"]'
SEL_EDIT_NOME = '[data-testid="turma-edit-nome"]'
SEL_EDIT_CANCELAR = '[data-testid="turma-edit-cancelar"]'
TURMA = "Turma X5"


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


def _executar(comando, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    try:
        conn.execute(comando, params)
        conn.commit()
    finally:
        conn.close()


def _dia_sp(delta):
    return ((datetime.now(timezone.utc) - timedelta(hours=3)).date() + timedelta(days=delta)).isoformat()


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, rotulo, preco):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"x5-{rotulo.lower()}-{sufixo}"
    corpo = {
        "id": course_id, "name": f"Curso X5 {rotulo} {sufixo}", "description": "Curso X5 do e2e", "price": preco,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": [],
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "preco": preco}


def criar_aluno(Database, rotulo):
    from core.security import get_password_hash  # noqa: PLC0415  (backend no sys.path depois de abrir_banco)

    email = f"e2e.x5.{rotulo.lower()}.{uuid.uuid4().hex[:10]}@teste.com"
    nome = f"{rotulo} X5 {uuid.uuid4().hex[:4]}"
    uid = Database.add_user(email, nome, get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: nao foi possivel criar {email}")
    return {"uid": uid, "email": email, "nome": nome}


def pagamento_aprovado(Database, aluno, curso):
    eid = Database.create_enrollment(aluno["uid"], curso["id"], f"{curso['id']}:x5:{uuid.uuid4().hex}")
    pid = Database.record_payment(eid, curso["preco"], "mercado_pago")
    _executar("UPDATE payments SET status = 'approved', transaction_id = ? WHERE id = ?",
              (f"mp-x5-e2e-{uuid.uuid4().hex[:10]}", pid))
    _executar("UPDATE enrollments SET status = 'active' WHERE id = ?", (eid,))
    return pid


def semear():
    token = token_gestao()
    curso_a = criar_curso(token, "A", 240.0)
    curso_b = criar_curso(token, "B", 120.0)
    status, corpo = _api("POST", "/api/admin/classes", {"course_id": curso_a["id"], "name": TURMA,
                                                        "starts_on": _dia_sp(20), "capacity": 20}, token=token)
    if status != 200:
        raise RuntimeError(f"seed: POST /api/admin/classes respondeu HTTP {status}: {corpo}")
    Database = abrir_banco(ALVO["db_path"])
    rui = criar_aluno(Database, "Rui")
    lia = criar_aluno(Database, "Lia")
    pagamento_aprovado(Database, rui, curso_a)
    pagamento_aprovado(Database, lia, curso_a)
    return {"db": Database, "a": curso_a, "b": curso_b, "rui": rui, "lia": lia}


# ---------------------------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------------------------

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


def emails_na_tabela(page):
    # Tabela de transacoes do Financeiro (a de cancelamentos nao tem table-hover).
    return [_normalizar(t) for t in page.locator("table.table-hover tbody tr small").all_inner_texts()]


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("x5") as ambiente:
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

def test_x5_atualizacao_paineis_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    pedidos = Counter()

    seed = {"ok": False, "erro": ""}
    s = {}
    try:
        s.update(semear())
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, timezone_id="UTC", locale="en-US")
    page = ctx.new_page()
    page.clock.install(time=INSTANTE)

    def ao_console(msg):
        url = msg.location.get("url") or ""
        if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
            erros_console.append(f"{msg.text[:120]} ({url})")

    def ao_pedido(req):
        if req.method == "GET":
            pedidos[urllib.parse.urlparse(req.url).path] += 1

    page.on("console", ao_console)
    page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
    page.on("request", ao_pedido)
    page.on("dialog", lambda dialogo: dialogo.accept())

    logado = {"ok": False}

    def admin():
        if not logado["ok"]:
            entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
            logado["ok"] = True
        return page

    def ciclo():
        page.clock.run_for(CICLO_MS)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)

    def busca_no_ciclo(endpoint, codigo, deve_buscar, descricao):
        antes = pedidos[endpoint]
        ciclo()
        depois = pedidos[endpoint]
        if deve_buscar and depois <= antes:
            raise Falha(f"{codigo}: {descricao}: nenhum GET {endpoint} em 31 s")
        if not deve_buscar and depois != antes:
            raise Falha(f"{codigo}: {descricao}: {depois - antes} GET {endpoint} em 31 s, esperado nenhum")

    def componente(codigo, aba):
        botao = esperar(page.locator(SEL_BOTAO), codigo, f"atualizacao-botao na aba {aba}")
        if _normalizar(botao.inner_text()) != "Atualizar":
            raise Falha(f"{codigo}: atualizacao-botao mostra {botao.inner_text()!r}, esperado 'Atualizar'")
        hora = _normalizar(esperar(page.locator(SEL_HORA), codigo, f"atualizacao-hora na aba {aba}").inner_text())
        if not re.fullmatch(r"Atualizado às \d{2}:\d{2}", hora):
            raise Falha(f"{codigo}: atualizacao-hora mostra {hora!r}, esperado 'Atualizado às HH:MM'")
        return hora

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
        admin()
        clicar_aba(page, "Financeiro")
        esperar_condicao(lambda: None if s["rui"]["email"] in emails_na_tabela(page)
                         else f"o pagamento do Rui nao aparece (vistos: {emails_na_tabela(page)})", "S0")

    def h1():
        admin()
        clicar_aba(page, "Financeiro")
        hora = componente("H1", "Financeiro")
        if hora != f"Atualizado às {HORA_SP}":
            raise Falha(f"H1: atualizacao-hora mostra {hora!r}, esperado 'Atualizado às {HORA_SP}' (Sao Paulo)")

    def a1():
        admin()
        clicar_aba(page, "Financeiro")
        busca = esperar(page.locator(SEL_BUSCA_FIN), "A1", "o campo financeiro-busca")
        busca.fill(s["rui"]["nome"], timeout=TIMEOUT)
        busca.press("Enter")
        page.wait_for_load_state("networkidle")
        busca.blur()
        esperar_condicao(lambda: None if emails_na_tabela(page) == [s["rui"]["email"]]
                         else f"a busca nao deixou so o Rui: {emails_na_tabela(page)}", "A1")
        pagamento_aprovado(s["db"], s["rui"], s["b"])
        pagamento_aprovado(s["db"], s["lia"], s["b"])
        if len(emails_na_tabela(page)) != 1:
            raise Falha("A1: a tabela mudou antes do ciclo de 30 s")
        ciclo()
        esperar_condicao(lambda: None if emails_na_tabela(page) == [s["rui"]["email"]] * 2
                         else f"depois de 31 s a tabela mostra {emails_na_tabela(page)}, esperado 2 linhas do Rui",
                         "A1")
        valor = page.locator(SEL_BUSCA_FIN).first.input_value()
        if valor != s["rui"]["nome"]:
            raise Falha(f"A1: a busca virou {valor!r} depois da atualizacao")

    def a2():
        admin()
        pagamento_aprovado(s["db"], s["rui"], s["a"])
        esperar(page.locator(SEL_BOTAO), "A2", "atualizacao-botao").click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        esperar_condicao(lambda: None if emails_na_tabela(page) == [s["rui"]["email"]] * 3
                         else f"depois do botao a tabela mostra {emails_na_tabela(page)}, esperado 3 linhas do Rui",
                         "A2")

    def a3():
        admin()
        clicar_aba(page, "Financeiro")
        for aba, endpoint in (("Alunos", EP_ALUNOS), ("Cursos", EP_CURSOS),
                              ("Observabilidade de IA", EP_IA), ("Auditoria", EP_AUDIT)):
            anterior = pedidos[EP_FIN]
            clicar_aba(page, aba)
            componente("A3", aba)
            busca_no_ciclo(endpoint, "A3", True, f"aba {aba}")
            if aba == "Alunos" and pedidos[EP_FIN] != anterior:
                raise Falha("A3: o Financeiro continuou buscando depois de trocar de aba")

    def p1():
        admin()
        clicar_aba(page, "Cursos")
        nomes = [_normalizar(t) for t in page.locator(f"{SEL_ROW} {SEL_NAME}").all_inner_texts()]
        if TURMA not in nomes:
            raise Falha(f"P1: a turma {TURMA!r} nao aparece (vistas: {nomes})")
        linha = page.locator(SEL_ROW).filter(has=page.locator(SEL_NAME, has_text=TURMA)).first
        linha.locator(SEL_EDITAR).first.click(timeout=TIMEOUT)
        campo = esperar(page.locator(SEL_EDIT_NOME), "P1", "turma-edit-nome")
        campo.fill("Nome em edicao X5", timeout=TIMEOUT)
        campo.blur()
        busca_no_ciclo(EP_CURSOS, "P1", False, "turma em edicao")
        valor = page.locator(SEL_EDIT_NOME).first.input_value()
        if valor != "Nome em edicao X5":
            raise Falha(f"P1: o texto digitado virou {valor!r}")
        page.locator(SEL_EDIT_CANCELAR).first.click(timeout=TIMEOUT)
        busca_no_ciclo(EP_CURSOS, "P1", True, "depois de cancelar a edicao")

    def p2():
        admin()
        clicar_aba(page, "Observabilidade de IA")
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
            Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        busca_no_ciclo(EP_IA, "P2", False, "aba do navegador escondida")
        page.evaluate("""() => {
            delete document.hidden;
            delete document.visibilityState;
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        busca_no_ciclo(EP_IA, "P2", True, "aba do navegador visivel de novo")

    def p3():
        admin()
        clicar_aba(page, "Auditoria")
        campo = esperar(page.locator(SEL_BUSCA_AUDIT), "P3", "o campo de busca da Auditoria")
        campo.click(timeout=TIMEOUT)
        campo.type("reemb", delay=20)
        busca_no_ciclo(EP_AUDIT, "P3", False, "campo de busca em foco")

    def r1():
        admin()
        clicar_aba(page, "Cadastro de cursos")
        page.wait_for_timeout(300)
        if page.locator(SEL_BOTAO).count() or page.locator(SEL_HORA).count():
            raise Falha("R1: Cadastro de cursos mostra o componente de atualizacao")

    def z1():
        if erros_console:
            raise Falha(f"Z1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("S0", "pre-condicao: Gestao ve o pagamento do seed no Financeiro", s0)
    cenario("H1", "Financeiro mostra Atualizar e 'Atualizado às 15:00' (Sao Paulo)", h1)
    cenario("A1", "ciclo de 30 s traz o pagamento novo e mantem a busca", a1)
    cenario("A2", "botao Atualizar busca na hora", a2)
    cenario("A3", "as outras quatro abas atualizam no ciclo; a anterior para", a3)
    cenario("P1", "Cursos com turma em edicao nao atualiza; ao cancelar, volta", p1)
    cenario("P2", "aba do navegador escondida nao atualiza; visivel, volta", p2)
    cenario("P3", "campo de busca em foco nao atualiza", p3)
    cenario("R1", "Cadastro de cursos nao tem o componente", r1)
    cenario("Z1", "sem erros de console de /api nem excecoes de pagina", z1)

    try:
        ctx.close()
    except Exception:
        pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
