"""E2E da entrega U5 - pedido de cancelamento em 7 dias, CDC art. 49 (D82, modo autonomo D69).

Backend correspondente: backend/tests/test_u5_cancelamento.py.
Teste VERMELHO escrito antes da implementacao: hoje o cartao do curso do aluno nao tem `curso-cancelar` e o
dashboard financeiro nao tem a secao "Solicitacoes de cancelamento".

Contrato de tela (D82):
  - Cartao do curso do aluno (curso-card): `curso-cancelar` so quando `can_request_cancellation`; abre
    `curso-cancelar-motivo` + `curso-cancelar-enviar` (com window.confirm); status em `curso-cancelamento-status`
    (`Cancelamento em análise`, `Cancelamento aprovado`, `Cancelamento recusado: <motivo>`).
  - Dashboard financeiro (aba Financeiro): secao "Solicitações de cancelamento" com `cancelamento-row`,
    `cancelamento-aprovar` (confirm), `cancelamento-motivo` + `cancelamento-recusar`.

Escolhas de forma do teste (nenhuma define politica):
  - Todo dialogo (confirm) e aceito; o teste confere que houve ao menos um confirm ao enviar e ao aprovar.
  - `cancelamento-motivo`/`cancelamento-recusar` sao procurados dentro da linha; se o campo so aparece depois do
    primeiro clique em recusar, o teste clica, preenche e clica de novo. Fora da linha, aceita o campo da secao.
  - Depois de enviar o pedido, o status aparece no cartao sem recarregar a pagina; mudancas feitas por OUTRO perfil
    (decisao do financeiro) sao conferidas depois de recarregar.
  - Depois de decidir, a linha some da lista (filtro padrao `open`) sem recarregar a pagina a mao.

Seed (harness D58, SQLite temporario): curso A (com material) e curso B criados pela API de Gestao; Rui (conta com
senha) com compra aprovada ha 1 dia no curso A e compra aprovada ha 10 dias no curso B.

Cenarios:
  C1 Rui ve curso-cancelar no curso A, envia com motivo (confirm) e ve "Cancelamento em análise"; banco com pedido open
  C2 Rui nao ve curso-cancelar no curso B (aprovado ha mais de 7 dias)
  F1 Financeiro ve a secao e a linha do Rui (cancelamento-row), recusa com motivo; a linha some; banco rejected
  C3 Rui recarrega e ve "Cancelamento recusado: <motivo>"; curso-cancelar volta; novo pedido -> "Cancelamento em análise"
  F2 Financeiro aprova o novo pedido (confirm): a linha some; pagamento e matricula refunded no banco
  C4 Rui recarrega e ve "Cancelamento aprovado" e nao ve mais o material do curso A
  S1 Suporte nao ve a secao nem cancelamento-row em nenhuma aba
  K1 sem erros de console de /api (4xx/5xx) nem excecoes de pagina

Execucao (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_u5_cancelamento_angular.py -s
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
SENHA = "senha-aluno-u5-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
FUSO = "America/Sao_Paulo"
IDIOMA = "en-US"
URL_MATERIAL = "https://materiais.test/u5/apostila-e2e.pdf"
TITULO_MATERIAL = "Apostila U5 e2e"
MOTIVO_ALUNO = "Comprei por engano, quero desistir"
MOTIVO_RECUSA = "Aluno ja assistiu ao curso inteiro"
TXT_ANALISE = "Cancelamento em análise"
TXT_APROVADO = "Cancelamento aprovado"
TXT_RECUSADO = "Cancelamento recusado:"
TXT_SECAO = "Solicitações de cancelamento"

SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_CARD = '[data-testid="curso-card"]'
SEL_CANCELAR = '[data-testid="curso-cancelar"]'
SEL_CANCELAR_MOTIVO = '[data-testid="curso-cancelar-motivo"]'
SEL_CANCELAR_ENVIAR = '[data-testid="curso-cancelar-enviar"]'
SEL_STATUS = '[data-testid="curso-cancelamento-status"]'
SEL_ROW = '[data-testid="cancelamento-row"]'
SEL_APROVAR = '[data-testid="cancelamento-aprovar"]'
SEL_MOTIVO = '[data-testid="cancelamento-motivo"]'
SEL_RECUSAR = '[data-testid="cancelamento-recusar"]'


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


def _executar(comando, params=()):
    conn = sqlite3.connect(str(ALVO["db_path"]))
    try:
        conn.execute(comando, params)
        conn.commit()
    finally:
        conn.close()


def _ts(delta):
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%d %H:%M:%S")


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, rotulo, preco, materiais):
    sufixo = uuid.uuid4().hex[:6]
    course_id = f"u5-{rotulo.lower()}-{sufixo}"
    nome = f"Curso U5 {rotulo} {sufixo}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso U5 do e2e", "price": preco,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": materiais,
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome, "preco": preco}


def compra_aprovada(Database, aluno, curso, aprovado_ha):
    eid = Database.create_enrollment(aluno["uid"], curso["id"], f"{curso['id']}:u5:{uuid.uuid4().hex}")
    pid = Database.record_payment(eid, curso["preco"], "mercado_pago")
    quando = _ts(aprovado_ha)
    _executar("UPDATE payments SET status = 'approved', transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
              (f"mp-u5-e2e-{uuid.uuid4().hex[:10]}", quando, quando, pid))
    _executar("UPDATE enrollments SET status = 'active', enrolled_at = ? WHERE id = ?", (quando, eid))
    return {"eid": eid, "pid": pid}


def semear():
    token = token_gestao()
    curso_a = criar_curso(token, "A", 230.0, [{"title": TITULO_MATERIAL, "url": URL_MATERIAL, "type": "pdf"}])
    curso_b = criar_curso(token, "B", 90.0, [])
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash  # noqa: PLC0415  (backend no sys.path depois de abrir_banco)

    email = f"e2e.u5.{uuid.uuid4().hex[:10]}@teste.com"
    nome = f"Rui U5 {uuid.uuid4().hex[:4]}"
    uid = Database.add_user(email, nome, get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: nao foi possivel criar {email}")
    rui = {"uid": uid, "email": email, "nome": nome}
    rui["a"] = compra_aprovada(Database, rui, curso_a, timedelta(days=1))
    rui["b"] = compra_aprovada(Database, rui, curso_b, timedelta(days=10))
    return {"a": curso_a, "b": curso_b, "rui": rui}


def pedidos(eid):
    return _consulta("SELECT * FROM cancellation_requests WHERE enrollment_id = ? ORDER BY id", (eid,))


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


def abrir_area_aluno(page):
    page.goto(ALVO["base"] + "/student", wait_until="networkidle")
    page.wait_for_timeout(300)


def cartao(page, curso, codigo):
    return esperar(page.locator(SEL_CARD, has_text=curso["nome"]), codigo, f"o curso-card de {curso['nome']!r}")


def visivel(locator):
    return locator.count() > 0 and locator.first.is_visible()


def status_do_cartao(page, curso, esperado, codigo):
    def leitura():
        card = page.locator(SEL_CARD, has_text=curso["nome"]).first
        alvo = card.locator(SEL_STATUS)
        if not alvo.count():
            return f"o cartao de {curso['nome']!r} nao tem curso-cancelamento-status (esperado {esperado!r})"
        texto = _normalizar(alvo.first.inner_text())
        if esperado not in texto:
            return f"curso-cancelamento-status mostra {texto!r}, esperado {esperado!r}"
        return None
    esperar_condicao(leitura, codigo, TIMEOUT * 3)


def pedir_cancelamento(page, curso, dialogos, codigo, motivo):
    card = cartao(page, curso, codigo)
    botao = card.locator(SEL_CANCELAR)
    if not visivel(botao):
        raise Falha(f"{codigo}: o cartao de {curso['nome']!r} nao mostra curso-cancelar")
    botao.first.click(timeout=TIMEOUT)
    campo = esperar(page.locator(SEL_CANCELAR_MOTIVO), codigo, "o campo curso-cancelar-motivo")
    campo.fill(motivo, timeout=TIMEOUT)
    antes = len(dialogos)
    esperar(page.locator(SEL_CANCELAR_ENVIAR), codigo, "o botao curso-cancelar-enviar").click(timeout=TIMEOUT)
    page.wait_for_load_state("networkidle")
    esperar_condicao(lambda: None if len(dialogos) > antes else "nenhum window.confirm ao enviar o pedido", codigo)


def abrir_financeiro(page, codigo):
    page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
    clicar_aba(page, "Financeiro")
    esperar_condicao(
        lambda: None if TXT_SECAO in _normalizar(page.locator("body").inner_text())
        else f"a secao '{TXT_SECAO}' nao aparece na aba Financeiro", codigo)


def linha_do_aluno(page, aluno, curso, codigo):
    def leitura():
        linhas = page.locator(SEL_ROW, has_text=aluno["email"])
        if not linhas.count():
            return f"nenhuma cancelamento-row com {aluno['email']}"
        texto = _normalizar(linhas.first.inner_text())
        if curso["nome"] not in texto:
            return f"a cancelamento-row de {aluno['email']} nao mostra o curso {curso['nome']!r}: {texto!r}"
        return None
    esperar_condicao(leitura, codigo, TIMEOUT * 3)
    return page.locator(SEL_ROW, has_text=aluno["email"]).first


def linha_some(page, aluno, codigo):
    esperar_condicao(
        lambda: None if page.locator(SEL_ROW, has_text=aluno["email"]).count() == 0
        else "a cancelamento-row continua na lista depois da decisao", codigo, TIMEOUT * 3)


def recusar(page, linha, motivo, codigo):
    campo = linha.locator(SEL_MOTIVO)
    if not visivel(campo):
        botao = linha.locator(SEL_RECUSAR)
        if not visivel(botao):
            raise Falha(f"{codigo}: a cancelamento-row nao tem cancelamento-motivo nem cancelamento-recusar")
        botao.first.click(timeout=TIMEOUT)
        page.wait_for_timeout(300)
        campo = linha.locator(SEL_MOTIVO) if visivel(linha.locator(SEL_MOTIVO)) else page.locator(SEL_MOTIVO)
    esperar(campo, codigo, "o campo cancelamento-motivo").fill(motivo, timeout=TIMEOUT)
    botao = linha.locator(SEL_RECUSAR) if visivel(linha.locator(SEL_RECUSAR)) else page.locator(SEL_RECUSAR)
    esperar(botao, codigo, "o botao cancelamento-recusar").click(timeout=TIMEOUT)
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("u5") as ambiente:
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

def test_u5_cancelamento_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
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
            if msg.type != "error" or not ERRO_HTTP.search(msg.text) or "/api/" not in (url + msg.text):
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
                "fin": (FINANCEIRO_EMAIL, FINANCEIRO_SENHA, "admin"),
                "sup": (SUPORTE_EMAIL, SUPORTE_SENHA, "admin"),
                "rui": (s["rui"]["email"], SENHA, "student"),
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

    def c1():
        page = pagina("rui")
        abrir_area_aluno(page)
        card = cartao(page, s["a"], "C1")
        if not visivel(card.locator(f'a[href="{URL_MATERIAL}"]')):
            raise Falha("C1: antes do pedido, o material do curso A deveria aparecer no cartao")
        pedir_cancelamento(page, s["a"], dialogos, "C1", MOTIVO_ALUNO)
        status_do_cartao(page, s["a"], TXT_ANALISE, "C1")
        if visivel(cartao(page, s["a"], "C1").locator(SEL_CANCELAR)):
            raise Falha("C1: curso-cancelar continua visivel com o pedido em analise")
        linhas = pedidos(s["rui"]["a"]["eid"])
        if [l["status"] for l in linhas] != ["open"]:
            raise Falha(f"C1: no banco, esperado um pedido open: {linhas}")

    def c2():
        page = pagina("rui")
        abrir_area_aluno(page)
        card = cartao(page, s["b"], "C2")
        page.wait_for_timeout(500)
        if card.locator(SEL_CANCELAR).count():
            raise Falha("C2: curso-cancelar aparece numa compra aprovada ha mais de 7 dias")

    def f1():
        page = pagina("fin")
        abrir_financeiro(page, "F1")
        linha = linha_do_aluno(page, s["rui"], s["a"], "F1")
        recusar(page, linha, MOTIVO_RECUSA, "F1")
        linha_some(page, s["rui"], "F1")
        linhas = pedidos(s["rui"]["a"]["eid"])
        if [l["status"] for l in linhas] != ["rejected"]:
            raise Falha(f"F1: no banco, esperado o pedido rejected: {linhas}")

    def c3():
        page = pagina("rui")
        abrir_area_aluno(page)
        status_do_cartao(page, s["a"], f"{TXT_RECUSADO} {MOTIVO_RECUSA}", "C3")
        pedir_cancelamento(page, s["a"], dialogos, "C3", "Quero cancelar mesmo assim")
        status_do_cartao(page, s["a"], TXT_ANALISE, "C3")

    def f2():
        page = pagina("fin")
        abrir_financeiro(page, "F2")
        linha = linha_do_aluno(page, s["rui"], s["a"], "F2")
        antes = len(dialogos)
        botao = linha.locator(SEL_APROVAR)
        if not visivel(botao):
            raise Falha("F2: a cancelamento-row nao tem cancelamento-aprovar")
        botao.first.click(timeout=TIMEOUT)
        page.wait_for_load_state("networkidle")
        esperar_condicao(lambda: None if len(dialogos) > antes else "nenhum window.confirm ao aprovar", "F2")
        linha_some(page, s["rui"], "F2")
        pid, eid = s["rui"]["a"]["pid"], s["rui"]["a"]["eid"]

        def banco():
            pag = _consulta("SELECT status FROM payments WHERE id = ?", (pid,))[0]["status"]
            mat = _consulta("SELECT status FROM enrollments WHERE id = ?", (eid,))[0]["status"]
            if (pag, mat) != ("refunded", "refunded"):
                return f"pagamento/matricula deveriam estar refunded: {pag}/{mat}"
            return None
        esperar_condicao(banco, "F2")
        if [l["status"] for l in pedidos(eid)] != ["rejected", "approved"]:
            raise Falha(f"F2: no banco, esperado rejected e approved: {pedidos(eid)}")

    def c4():
        page = pagina("rui")
        abrir_area_aluno(page)
        status_do_cartao(page, s["a"], TXT_APROVADO, "C4")
        if page.locator(f'a[href="{URL_MATERIAL}"]').count():
            raise Falha("C4: o material do curso A continua na tela depois do reembolso")
        if URL_MATERIAL in page.content():
            raise Falha("C4: a URL do material continua no HTML depois do reembolso")
        if visivel(cartao(page, s["a"], "C4").locator(SEL_CANCELAR)):
            raise Falha("C4: curso-cancelar aparece numa matricula reembolsada")

    def s1():
        page = pagina("sup")
        page.goto(ALVO["base"] + "/admin", wait_until="networkidle")
        abas = [_normalizar(t) for t in page.eval_on_selector_all(SEL_ABA, "els => els.map(e => e.innerText)")]
        for aba in abas:
            clicar_aba(page, aba)
            if page.locator(SEL_ROW).count() or TXT_SECAO in _normalizar(page.locator("body").inner_text()):
                raise Falha(f"S1: o Suporte ve as solicitacoes de cancelamento na aba {aba!r}")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("C1", "aluno pede o cancelamento com motivo e ve 'Cancelamento em análise'", c1)
    cenario("C2", "compra aprovada ha mais de 7 dias nao mostra curso-cancelar", c2)
    cenario("F1", "Financeiro ve a solicitacao e recusa com motivo", f1)
    cenario("C3", "aluno ve 'Cancelamento recusado: <motivo>' e pede de novo", c3)
    cenario("F2", "Financeiro aprova (confirm): pagamento e matricula reembolsados", f2)
    cenario("C4", "aluno ve 'Cancelamento aprovado' e perde o material", c4)
    cenario("S1", "Suporte nao ve as solicitacoes de cancelamento", s1)
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
