"""E2E da entrega F2 — horário de São Paulo (America/Sao_Paulo) e formato pt-BR nas telas.

Plano: docs/tdd/PLANO_FEEDBACK_PROF.md (F2). Modo autônomo: D69. Contrato (decisões de forma do orquestrador):
o banco continua gravando UTC ('AAAA-MM-DD HH:MM:SS', sem fuso) e a API não muda; o navegador formata no fuso
'America/Sao_Paulo' (Intl), no padrão dd/MM/aaaa HH:mm, sem depender do fuso nem do idioma da máquina.
Backend correspondente: backend/tests/test_f2_fuso_horario.py.

Para provar que a tela não depende da máquina, os navegadores rodam em fusos e idiomas diferentes de São Paulo:
o funcionário em 'Asia/Tokyo' (UTC+9) e o aluno em 'Europe/Lisbon' (UTC+1 em outubro), os dois com locale 'en-US'.

Seed (harness D58, SQLite temporário; horários UTC conhecidos gravados direto no banco):
  - curso criado pela API (Gestão);
  - aluno com matrícula ATIVA (enrolled_at '2026-10-08 01:30:00'), pagamento APROVADO (created_at e updated_at
    '2026-10-08 01:30:00') e uma mensagem de chat às '2026-10-08 02:10:00';
  - evento de auditoria inserido com created_at '2026-10-08 01:30:00' (a tabela é só de inserção).
Em São Paulo: 01:30 UTC = 07/10/2026 22:30; 02:10 UTC = 07/10/2026 23:10.

Cenários:
  T0 guarda: os navegadores estão mesmo em Asia/Tokyo e Europe/Lisbon (emulação de fuso ativa)
  S1 caracterização: a turma criada pela tela com início 2026-11-01 fica com starts_on '2026-11-01' (data só de
     dia não é deslocada)
  A1 auditoria: a coluna Data do evento semeado mostra exatamente '07/10/2026 22:30' (sem o texto UTC cru)
  A2 caracterização: o evento class.create da turma continua mostrando '2026-11-01' (não '31/10/2026')
  F1 financeiro: a coluna Data do pagamento do aluno mostra exatamente '07/10/2026 22:30'
  D1 dashboard de alunos: "Última matrícula" '07/10/2026 22:30' e "Última conversa" (aluno-last-chat)
     '07/10/2026 23:10', sem o texto UTC cru
  E1 área do aluno: curso-data mostra '07/10/2026' (dia de São Paulo), não '08/10/2026'
  E2 área do aluno: a data do pagamento no histórico é '07/10/2026'
  E3 área do aluno: o recibo na tela mostra "Emitido em" com '07/10/2026'
  K1 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_f2_fuso_horario_angular.py -s
"""

import json
import os
import re
import sqlite3
import sys
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
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-f2-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")

FUSO_FUNCIONARIO = "Asia/Tokyo"
FUSO_ALUNO = "Europe/Lisbon"
IDIOMA = "en-US"

UTC_NOITE = "2026-10-08 01:30:00"
SP_NOITE = "07/10/2026 22:30"
UTC_CHAT = "2026-10-08 02:10:00"
SP_CHAT = "07/10/2026 23:10"
DIA_SP = "07/10/2026"
CRUS = ("2026-10-08", "08/10/2026", "01:30:00", "10/8/2026", "Oct")
INICIO_TURMA = "2026-11-01"

SEL_ABA = "ul.nav-tabs button.nav-link"


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


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
    course_id = f"f2-fuso-{uuid.uuid4().hex[:8]}"
    nome = f"Curso F2 Fuso {uuid.uuid4().hex[:6]}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso F2 do e2e", "price": 250.0,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt", "materials": [],
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome}


def semear_aluno(course_id):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.f2.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, "Aluno F2 Fuso", get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    enrollment_id = Database.create_enrollment(uid, course_id, f"{course_id}:f2:{uuid.uuid4().hex}")
    pid = Database.record_payment(enrollment_id, 250.0, "mercado_pago")
    Database.update_payment_status(pid, "approved", f"mp-f2-{uuid.uuid4().hex[:6]}")
    _sql("UPDATE enrollments SET status = 'active', enrolled_at = ? WHERE id = ?", (UTC_NOITE, enrollment_id))
    _sql("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (UTC_NOITE, UTC_NOITE, pid))
    _sql("INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
         (uid, "Pergunta do aluno F2", UTC_CHAT))
    return {"email": email, "uid": uid, "payment_id": pid}


def semear_auditoria():
    detalhe = f"Evento F2 fuso {uuid.uuid4().hex[:8]}"
    _sql("INSERT INTO audit_logs (role, action, detail, created_at) VALUES ('admin', 'course.update', ?, ?)",
         (detalhe, UTC_NOITE))
    return detalhe


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


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
    page.wait_for_timeout(500)


def esperar(locator, codigo, descricao):
    try:
        locator.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: {descricao} não aparece na tela")
    return locator.first


def sem_utc_cru(texto, codigo, onde):
    for cru in CRUS:
        if cru in texto:
            raise Falha(f"{codigo}: {onde} mostra {cru!r} (texto UTC ou fora do fuso de São Paulo): {texto[:160]!r}")


@pytest.fixture(scope="module")
def servidores():
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("f2") as ambiente:
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


def test_f2_fuso_horario_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {}

    seed = {"ok": False, "erro": ""}
    try:
        token = token_gestao()
        curso = criar_curso(token)
        aluno = semear_aluno(curso["id"])
        detalhe_auditoria = semear_auditoria()
        nome_turma = f"Turma F2 {uuid.uuid4().hex[:6]}"
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(fuso):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, timezone_id=fuso, locale=IDIOMA)
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
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
            texto = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, texto))
            print(f"[FAIL] {codigo} {nome} -> {texto}")

    def pagina_gestor():
        page = estado.get("gestor")
        if page is None:
            page = nova_pagina(FUSO_FUNCIONARIO)
            entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
            estado["gestor"] = page
        return page

    def pagina_aluno():
        page = estado.get("aluno")
        if page is None:
            page = nova_pagina(FUSO_ALUNO)
            entrar(page, aluno["email"], SENHA, "student")
            page.goto(ALVO["base"] + "/student", wait_until="networkidle")
            estado["aluno"] = page
        return page

    def t0():
        for fuso in (FUSO_FUNCIONARIO, FUSO_ALUNO):
            page = nova_pagina(fuso)
            page.goto(ALVO["base"] + "/", wait_until="domcontentloaded")
            visto = page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
            if visto != fuso:
                raise Falha(f"T0: o navegador deveria estar em {fuso}, está em {visto}")
            deslocamento = page.evaluate("new Date('2026-10-08T01:30:00Z').getTimezoneOffset()")
            if deslocamento == 180:
                raise Falha("T0: a emulação de fuso não saiu de UTC-3; o teste não provaria nada")

    def s1():
        page = pagina_gestor()
        clicar_aba(page, "Cursos")
        try:
            page.locator('[data-testid="turma-new-course"]').first.select_option(curso["id"], timeout=TIMEOUT)
            page.locator('[data-testid="turma-new-name"]').first.fill(nome_turma, timeout=TIMEOUT)
            page.locator('[data-testid="turma-new-start"]').first.fill(INICIO_TURMA, timeout=TIMEOUT)
            page.locator('[data-testid="turma-new-capacity"]').first.fill("10", timeout=TIMEOUT)
            page.locator('[data-testid="turma-create"]').first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("S1: o formulário de nova turma (turma-new-*) não está disponível")
        esperar(page.locator('[data-testid="turma-name"]', has_text=nome_turma), "S1", f"a turma {nome_turma}")
        status, corpo = _api("GET", f"/api/admin/classes?course_id={curso['id']}", token=token)
        if status != 200:
            raise Falha(f"S1: /api/admin/classes respondeu HTTP {status}")
        turmas = [t for t in corpo["classes"] if t.get("name") == nome_turma]
        if len(turmas) != 1 or turmas[0].get("starts_on") != INICIO_TURMA:
            raise Falha(f"S1: starts_on gravado = {[t.get('starts_on') for t in turmas]} (esperado {INICIO_TURMA})")

    def abrir_auditoria():
        page = pagina_gestor()
        clicar_aba(page, "Auditoria")
        return page

    def a1():
        page = abrir_auditoria()
        linha = esperar(page.locator('[data-testid="audit-row"]', has_text=detalhe_auditoria), "A1",
                        "a linha do evento de auditoria semeado")
        data = _normalizar(linha.locator("td").first.inner_text())
        if data != SP_NOITE:
            raise Falha(f"A1: a coluna Data mostra {data!r} (esperado {SP_NOITE!r}, horário de São Paulo)")
        sem_utc_cru(_normalizar(linha.inner_text()), "A1", "a linha do evento")

    def a2():
        page = abrir_auditoria()
        linha = esperar(page.locator('[data-testid="audit-row"]', has_text=nome_turma), "A2",
                        "a linha do evento class.create da turma")
        texto = _normalizar(linha.inner_text())
        if INICIO_TURMA not in texto:
            raise Falha(f"A2: o evento da turma não mostra mais {INICIO_TURMA!r}: {texto[:160]!r}")
        if "31/10/2026" in texto:
            raise Falha("A2: a data só de dia da turma foi deslocada para 31/10/2026")

    def f1():
        page = pagina_gestor()
        clicar_aba(page, "Financeiro")
        linha = esperar(page.locator("tr", has_text=aluno["email"]), "F1", "a linha do pagamento do aluno")
        celulas = linha.locator("td")
        if celulas.count() < 5:
            raise Falha(f"F1: a linha do pagamento tem {celulas.count()} colunas (esperado ao menos 5)")
        data = _normalizar(celulas.nth(4).inner_text())
        if data != SP_NOITE:
            raise Falha(f"F1: a coluna Data mostra {data!r} (esperado {SP_NOITE!r}, horário de São Paulo)")
        sem_utc_cru(_normalizar(linha.inner_text()), "F1", "a linha do pagamento")

    def d1():
        page = pagina_gestor()
        clicar_aba(page, "Alunos")
        linha = esperar(page.locator("tr", has_text=aluno["email"]), "D1", "a linha do aluno")
        ultima_conversa = _normalizar(linha.locator('[data-testid="aluno-last-chat"]').first.inner_text())
        if ultima_conversa != SP_CHAT:
            raise Falha(f"D1: 'Última conversa' mostra {ultima_conversa!r} (esperado {SP_CHAT!r})")
        celulas = linha.locator("td")
        ultima_matricula = _normalizar(celulas.nth(4).inner_text()) if celulas.count() >= 5 else ""
        if ultima_matricula != SP_NOITE:
            raise Falha(f"D1: 'Última matrícula' mostra {ultima_matricula!r} (esperado {SP_NOITE!r})")
        sem_utc_cru(_normalizar(linha.inner_text()), "D1", "a linha do aluno")

    def e1():
        page = pagina_aluno()
        card = esperar(page.locator('[data-testid="curso-card"]', has_text=curso["nome"]), "E1",
                       "o cartão do curso do aluno")
        data = _normalizar(card.locator('[data-testid="curso-data"]').first.inner_text())
        if DIA_SP not in data:
            raise Falha(f"E1: curso-data mostra {data!r} (esperado o dia de São Paulo {DIA_SP})")
        sem_utc_cru(data, "E1", "curso-data")

    def e2():
        page = pagina_aluno()
        linha = esperar(page.locator("tbody tr", has_text=curso["nome"]), "E2", "a linha do pagamento no histórico")
        data = _normalizar(linha.locator("td.pg-data").first.inner_text())
        if DIA_SP not in data:
            raise Falha(f"E2: a data do pagamento mostra {data!r} (esperado o dia de São Paulo {DIA_SP})")
        sem_utc_cru(data, "E2", "a data do pagamento")

    def e3():
        page = pagina_aluno()
        linha = esperar(page.locator("tbody tr", has_text=curso["nome"]), "E3", "a linha do pagamento no histórico")
        linha.get_by_role("button", name="Ver recibo").click(timeout=TIMEOUT)
        cartao = esperar(page.locator("div.card.border-primary"), "E3", "o cartão do recibo")
        emitido = [l for l in cartao.inner_text().splitlines() if "Emitido em" in l]
        if not emitido:
            raise Falha("E3: o recibo na tela não mostra 'Emitido em'")
        texto = _normalizar(emitido[0])
        if DIA_SP not in texto:
            raise Falha(f"E3: 'Emitido em' mostra {texto!r} (esperado o dia de São Paulo {DIA_SP})")
        sem_utc_cru(texto, "E3", "'Emitido em'")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("T0", "navegadores em Asia/Tokyo e Europe/Lisbon (fora de São Paulo)", t0)
    cenario("S1", "turma criada pela tela mantém starts_on 2026-11-01", s1)
    cenario("A1", "auditoria mostra a data/hora de São Paulo", a1)
    cenario("A2", "auditoria: data só de dia da turma não é deslocada", a2)
    cenario("F1", "financeiro mostra a data/hora de São Paulo", f1)
    cenario("D1", "dashboard de alunos: última matrícula e última conversa em São Paulo", d1)
    cenario("E1", "área do aluno: data da matrícula no dia de São Paulo", e1)
    cenario("E2", "área do aluno: data do pagamento no dia de São Paulo", e2)
    cenario("E3", "área do aluno: recibo 'Emitido em' no dia de São Paulo", e3)
    cenario("K1", "sem erros de console de /api", k1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{c} {n} -> {d}" for c, n, ok, d in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
