"""E2E da entrega F1 — trava de exclusão de curso, arquivar curso e confirmação de reembolso (S7).

Plano: docs/tdd/PLANO_FEEDBACK_PROF.md (F1 e S7). Política: D68 (todos os status bloqueiam a exclusão; "arquivar"
tira o curso do catálogo e do chat, e o aluno ativo mantém o acesso). Modo autônomo: D69. Contrato de tela decidido
pelo orquestrador no pedido da F1 (decisões de forma). Backend correspondente: backend/tests/test_f1_trava_exclusao.py.

Contrato de tela (aba "Cadastro de cursos" de /admin, só Gestão), data-testid por linha `curso-row`:
  curso-delete            desabilitado (atributo disabled) quando o curso tem aluno matriculado (enrollments_count > 0)
  curso-delete-motivo     ao lado do botão, texto exato "Tem alunos matriculados — arquive em vez de excluir."
  curso-archive           "Arquivar" (curso não arquivado); confirmação nativa window.confirm com o nome do curso
  curso-unarchive         "Desarquivar" (curso arquivado); confirmação nativa window.confirm com o nome do curso
  curso-arquivado         badge "Arquivado" na linha do curso arquivado
  Curso sem aluno: exclui como hoje (curso-delete -> curso-delete-confirm, confirmação na própria tela).
S7 (aba Financeiro): clicar em "Reembolsar" abre window.confirm com a identificação do pagamento (#<id>); recusado,
nenhuma chamada a /api/payments/refund/ é feita e o pagamento continua `approved`; aceito, segue o fluxo atual.

Seed (só pela API e pela camada Database no SQLite temporário do harness D58):
  - curso COM: um aluno A com conta e senha, matrícula ATIVA (checkout falso + webhook assinado), com material;
  - curso SEM: sem nenhuma matrícula (é o que se exclui);
  - curso LIVRE: sem matrícula do A; um comprador avulso tem pagamento APROVADO nele (é o que se reembolsa no S7);
  - aluno B com conta e senha, sem matrícula (vê o catálogo /catalogo).

Cenários:
  S1 pré-condição: o gestor abre a aba "Cadastro de cursos" e vê as linhas dos três cursos do seed
  X1 curso COM: curso-delete desabilitado e curso-delete-motivo com o texto exato; clicar (forçado) não envia DELETE
     e o curso continua existindo (API)
  X2 curso SEM: curso-delete habilitado, sem curso-delete-motivo; exclui como hoje (linha some; API 404)
  A0 arquivar com o diálogo RECUSADO: o diálogo cita o nome do curso; nada é enviado; sem badge; API archived false
  A1 arquivar com o diálogo ACEITO: badge curso-arquivado "Arquivado", curso-unarchive aparece e curso-archive some
     na linha; API (lista da Gestão) archived true
  A2 o curso arquivado some de /api/courses (o que a landing consome) e do /catalogo do aluno B; o LIVRE continua
  A3 o aluno A (matrícula ativa) continua vendo o curso arquivado em /student, com o material
  A4 desarquivar (diálogo aceito, cita o nome): o badge some e o curso volta ao /catalogo do aluno B
  R1 S7 reembolso com o diálogo RECUSADO: o diálogo cita #<id>; nenhuma chamada de reembolso; continua approved
  R2 S7 reembolso com o diálogo ACEITO: o pagamento vira refunded (API)
  K1 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo, um por vez): py -3 -m pytest frontend/e2e/test_f1_trava_exclusao_angular.py -s
"""

import json
import os
import re
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
from apoio_webhook_mp import enviar_webhook  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402

ALVO = {"base": "", "api": "", "db_path": None}
SENHA = "senha-aluno-f1-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
MOTIVO = "Tem alunos matriculados — arquive em vez de excluir."

ABA_CADASTRO = re.compile(r"^\s*Cadastro de cursos\s*$")
ABA_FINANCEIRO = re.compile(r"^\s*Financeiro\s*$")
SEL_ABA = "ul.nav-tabs button.nav-link"
SEL_ROW = '[data-testid="curso-row"]'


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _api(metodo, caminho, corpo=None, token=None, formulario=None, base=None):
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
    req = urllib.request.Request((base or ALVO["api"]) + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


def token_gestao():
    status, corpo = _api("POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    return corpo["access_token"]


def criar_curso(token, prefixo, nome_base, com_material):
    course_id = f"{prefixo}-{uuid.uuid4().hex[:8]}"
    nome = f"{nome_base} {uuid.uuid4().hex[:6]}"
    materiais = []
    if com_material:
        materiais = [{"title": f"Apostila {nome}", "url": f"https://materiais.test/{course_id}/apostila.pdf",
                      "type": "pdf"}]
    corpo = {
        "id": course_id, "name": nome, "description": "Curso F1 do e2e", "price": 120.0,
        "duration_hours": 6, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
        "materials": materiais,
    }
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return {"id": course_id, "nome": nome, "material": materiais[0] if materiais else None}


def semear_aluno(tag):
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    email = f"e2e.f1.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, f"Aluno F1 {tag}", get_password_hash(SENHA), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return email, uid


def compra_aprovada(course_id, email, nome):
    status, checkout = _api("POST", "/api/payments/create-checkout",
                            {"course_id": course_id, "payer": {"name": nome, "email": email}})
    if status != 200 or not (checkout or {}).get("external_reference"):
        raise RuntimeError(f"seed: create-checkout ({course_id}) respondeu HTTP {status}")
    status, _ = enviar_webhook(ALVO["api"], checkout["external_reference"])
    if status != 200:
        raise RuntimeError(f"seed: webhook respondeu HTTP {status}")


def pagamento_de(token, email):
    status, painel = _api("GET", "/api/dashboard/financeiro", token=token)
    if status != 200:
        raise Falha(f"painel financeiro respondeu HTTP {status}")
    achados = [p for p in painel["payments"] if p.get("student_email") == email]
    if len(achados) != 1:
        raise Falha(f"esperado 1 pagamento de {email}, encontrados {len(achados)}")
    return achados[0]


def item_admin(token, course_id):
    status, corpo = _api("GET", "/api/admin/courses", token=token)
    if status != 200:
        raise Falha(f"/api/admin/courses respondeu HTTP {status}")
    itens = [c for c in corpo["courses"] if c.get("id") == course_id]
    if len(itens) != 1:
        raise Falha(f"{course_id} não aparece uma única vez em /api/admin/courses")
    return itens[0]


def caminho(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("#")[0].split("?")[0] if "://" in url else url


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


def clicar_aba(page, padrao, nome):
    aba = page.locator(SEL_ABA, has_text=padrao)
    try:
        aba.first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"a aba '{nome}' não aparece")
    aba.first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def linha(page, course_id):
    return page.locator(f'{SEL_ROW}[data-course-id="{course_id}"]')


def esperar_linha(page, course_id, codigo):
    try:
        linha(page, course_id).first.wait_for(state="visible", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{codigo}: a linha do curso {course_id} não aparece na aba Cadastro de cursos")
    return linha(page, course_id).first


@pytest.fixture(scope="module")
def servidores():
    # O backend de teste herda o ambiente: o pagamento simulado nunca pode estar ligado neste e2e.
    salvos = {nome: os.environ.pop(nome) for nome in ("PAYMENTS_MOCK", "APP_ENV") if nome in os.environ}
    try:
        with ambiente_isolado("f1") as ambiente:
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


def test_f1_trava_exclusao_angular_e2e(servidores, browser):
    resultados = []
    erros_console = []
    contextos = []
    estado = {"dialogo": "dismiss", "dialogos": [], "requisicoes": []}

    seed = {"ok": False, "erro": ""}
    try:
        token = token_gestao()
        email_a, _uid_a = semear_aluno("a")
        email_b, _uid_b = semear_aluno("b")
        curso_com = criar_curso(token, "f1-com", "Curso F1 Com Aluno", com_material=True)
        curso_sem = criar_curso(token, "f1-sem", "Curso F1 Sem Aluno", com_material=False)
        curso_livre = criar_curso(token, "f1-livre", "Curso F1 Livre", com_material=False)
        compra_aprovada(curso_com["id"], email_a, "Aluno F1 a")
        email_reembolso = f"e2e.f1.reembolso.{uuid.uuid4().hex[:8]}@teste.com"
        compra_aprovada(curso_livre["id"], email_reembolso, "Comprador F1 Reembolso")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in (url + msg.text):
                erros_console.append(f"{msg.text[:120]} ({url})")

        def ao_dialogo(dialogo):
            estado["dialogos"].append((dialogo.type, dialogo.message))
            if estado["dialogo"] == "accept":
                dialogo.accept()
            else:
                dialogo.dismiss()

        page.on("console", ao_console)
        page.on("pageerror", lambda erro: erros_console.append(f"pageerror: {erro}"[:160]))
        page.on("dialog", ao_dialogo)
        page.on("request", lambda req: estado["requisicoes"].append((req.method, req.url)))
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
            raise Falha("pré-requisito: o gestor não abriu a aba Cadastro de cursos (S1 falhou)")
        return page

    def reabrir_cadastro(page):
        page.reload(wait_until="networkidle")
        clicar_aba(page, ABA_CADASTRO, "Cadastro de cursos")

    def chamadas(metodo, trecho):
        return [u for m, u in estado["requisicoes"] if m == metodo and trecho in u]

    def s1():
        page = nova_pagina()
        estado["gestor"] = page
        entrar(page, GESTAO_EMAIL, GESTAO_SENHA, "admin")
        clicar_aba(page, ABA_CADASTRO, "Cadastro de cursos")
        for curso in (curso_com, curso_sem, curso_livre):
            esperar_linha(page, curso["id"], "S1")

    def x1():
        page = pagina_gestor()
        row = esperar_linha(page, curso_com["id"], "X1")
        botao = row.locator('[data-testid="curso-delete"]')
        if botao.count() != 1:
            raise Falha("X1: a linha do curso com aluno não tem um único [data-testid=curso-delete]")
        if not botao.first.is_disabled():
            raise Falha("X1: o botão Excluir do curso com aluno está habilitado")
        motivo = row.locator('[data-testid="curso-delete-motivo"]')
        if motivo.count() != 1:
            raise Falha("X1: falta [data-testid=curso-delete-motivo] na linha do curso com aluno")
        texto = _normalizar(motivo.first.inner_text())
        if texto != MOTIVO:
            raise Falha(f"X1: motivo = {texto!r} (esperado {MOTIVO!r})")
        antes = len(chamadas("DELETE", "/api/admin/course/"))
        botao.first.click(force=True, timeout=TIMEOUT)
        page.wait_for_timeout(800)
        if page.locator('[data-testid="curso-delete-confirm"]').count() != 0:
            raise Falha("X1: o botão desabilitado abriu a confirmação de exclusão")
        if len(chamadas("DELETE", "/api/admin/course/")) != antes:
            raise Falha("X1: o clique no botão desabilitado enviou DELETE")
        status, _ = _api("GET", f"/api/admin/course/{curso_com['id']}", token=token)
        if status != 200:
            raise Falha(f"X1: o curso com aluno não existe mais (GET HTTP {status})")

    def x2():
        page = pagina_gestor()
        row = esperar_linha(page, curso_sem["id"], "X2")
        botao = row.locator('[data-testid="curso-delete"]')
        if botao.count() != 1 or botao.first.is_disabled():
            raise Falha("X2: o botão Excluir do curso sem aluno não está habilitado")
        if row.locator('[data-testid="curso-delete-motivo"]').count() != 0:
            raise Falha("X2: o curso sem aluno mostra o motivo de bloqueio")
        botao.first.click(timeout=TIMEOUT)
        confirmar = row.locator('[data-testid="curso-delete-confirm"]')
        try:
            confirmar.first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("X2: curso-delete não abriu a confirmação na tela (curso-delete-confirm)")
        confirmar.first.click(timeout=TIMEOUT)
        try:
            linha(page, curso_sem["id"]).first.wait_for(state="detached", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("X2: a linha do curso excluído continua na tela")
        status, _ = _api("GET", f"/api/admin/course/{curso_sem['id']}", token=token)
        if status != 404:
            raise Falha(f"X2: o curso sem aluno não foi excluído (GET HTTP {status})")

    def a0():
        page = pagina_gestor()
        row = esperar_linha(page, curso_com["id"], "A0")
        botao = row.locator('[data-testid="curso-archive"]')
        if botao.count() != 1:
            raise Falha("A0: a linha do curso não tem um único [data-testid=curso-archive]")
        if _normalizar(botao.first.inner_text()) != "Arquivar":
            raise Falha(f"A0: texto do botão = {botao.first.inner_text()!r} (esperado 'Arquivar')")
        estado["dialogo"] = "dismiss"
        dialogos_antes = len(estado["dialogos"])
        posts_antes = len(chamadas("POST", "/archive"))
        botao.first.click(timeout=TIMEOUT)
        page.wait_for_timeout(1000)
        novos = estado["dialogos"][dialogos_antes:]
        if not novos or novos[0][0] != "confirm":
            raise Falha(f"A0: arquivar não abriu window.confirm (diálogos: {novos})")
        if curso_com["nome"] not in novos[0][1]:
            raise Falha(f"A0: a confirmação não cita o nome do curso ({novos[0][1]!r})")
        if len(chamadas("POST", "/archive")) != posts_antes:
            raise Falha("A0: com o diálogo recusado, a tela chamou o arquivamento")
        if row.locator('[data-testid="curso-arquivado"]').count() != 0:
            raise Falha("A0: o badge Arquivado apareceu com o diálogo recusado")
        if item_admin(token, curso_com["id"]).get("archived") is not False:
            raise Falha("A0: o curso ficou arquivado com o diálogo recusado")

    def a1():
        page = pagina_gestor()
        row = esperar_linha(page, curso_com["id"], "A1")
        estado["dialogo"] = "accept"
        dialogos_antes = len(estado["dialogos"])
        arquivar = row.locator('[data-testid="curso-archive"]')
        if arquivar.count() != 1:
            raise Falha("A1: a linha do curso não tem um único [data-testid=curso-archive]")
        arquivar.first.click(timeout=TIMEOUT)
        badge = linha(page, curso_com["id"]).first.locator('[data-testid="curso-arquivado"]')
        try:
            badge.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("A1: o badge [data-testid=curso-arquivado] não apareceu depois de arquivar")
        if _normalizar(badge.first.inner_text()) != "Arquivado":
            raise Falha(f"A1: texto do badge = {badge.first.inner_text()!r} (esperado 'Arquivado')")
        novos = estado["dialogos"][dialogos_antes:]
        if not novos or novos[0][0] != "confirm" or curso_com["nome"] not in novos[0][1]:
            raise Falha(f"A1: arquivar não pediu confirmação com o nome do curso ({novos})")
        row = linha(page, curso_com["id"]).first
        desarquivar = row.locator('[data-testid="curso-unarchive"]')
        if desarquivar.count() != 1 or _normalizar(desarquivar.first.inner_text()) != "Desarquivar":
            raise Falha("A1: a linha arquivada não mostra [data-testid=curso-unarchive] 'Desarquivar'")
        if row.locator('[data-testid="curso-archive"]').count() != 0:
            raise Falha("A1: a linha arquivada ainda mostra curso-archive")
        if item_admin(token, curso_com["id"]).get("archived") is not True:
            raise Falha("A1: a API não mostra o curso como arquivado")
        reabrir_cadastro(page)
        if esperar_linha(page, curso_com["id"], "A1").locator('[data-testid="curso-arquivado"]').count() != 1:
            raise Falha("A1: depois de recarregar, o badge Arquivado sumiu")

    def a2():
        status, publico = _api("GET", "/api/courses", base=ALVO["base"])
        if status != 200:
            raise Falha(f"A2: /api/courses (proxy do front) respondeu HTTP {status}")
        ids = [c.get("id") for c in publico["courses"]]
        if curso_com["id"] in ids:
            raise Falha("A2: o curso arquivado continua em /api/courses (landing)")
        if curso_livre["id"] not in ids:
            raise Falha("A2: o curso livre sumiu de /api/courses")
        page = nova_pagina()
        estado["aluno_b"] = page
        entrar(page, email_b, SENHA, "student")
        page.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        cards = page.locator('[data-testid="catalogo-card"]')
        try:
            cards.filter(has_text=curso_livre["nome"]).first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("A2: o curso livre não aparece no /catalogo")
        if cards.filter(has_text=curso_com["nome"]).count() != 0:
            raise Falha("A2: o curso arquivado aparece no /catalogo do aluno")

    def a3():
        page = nova_pagina()
        entrar(page, email_a, SENHA, "student")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        cards = page.locator('[data-testid="curso-card"]')
        try:
            cards.filter(has_text=curso_com["nome"]).first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("A3: o aluno ativo não vê mais o curso arquivado em /student")
        if curso_com["material"]["url"] not in page.content():
            raise Falha("A3: o material do curso arquivado sumiu para o aluno ativo")

    def a4():
        page = pagina_gestor()
        row = esperar_linha(page, curso_com["id"], "A4")
        botao = row.locator('[data-testid="curso-unarchive"]')
        if botao.count() != 1:
            raise Falha("A4: falta [data-testid=curso-unarchive] na linha do curso arquivado")
        estado["dialogo"] = "accept"
        dialogos_antes = len(estado["dialogos"])
        botao.first.click(timeout=TIMEOUT)
        try:
            linha(page, curso_com["id"]).first.locator('[data-testid="curso-arquivado"]').first.wait_for(
                state="detached", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("A4: o badge Arquivado continua depois de desarquivar")
        novos = estado["dialogos"][dialogos_antes:]
        if not novos or novos[0][0] != "confirm" or curso_com["nome"] not in novos[0][1]:
            raise Falha(f"A4: desarquivar não pediu confirmação com o nome do curso ({novos})")
        if item_admin(token, curso_com["id"]).get("archived") is not False:
            raise Falha("A4: a API ainda mostra o curso como arquivado")
        aluno = estado.get("aluno_b") or nova_pagina()
        if "aluno_b" not in estado:
            entrar(aluno, email_b, SENHA, "student")
        aluno.goto(ALVO["base"] + "/catalogo", wait_until="networkidle")
        try:
            aluno.locator('[data-testid="catalogo-card"]').filter(has_text=curso_com["nome"]).first.wait_for(
                state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("A4: o curso desarquivado não voltou ao /catalogo")

    def botao_reembolso(page):
        clicar_aba(page, ABA_FINANCEIRO, "Financeiro")
        row = page.locator("tr", has_text=email_reembolso)
        try:
            row.first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha("a linha do pagamento do seed não aparece na aba Financeiro")
        botao = row.first.locator("button", has_text="Reembolsar")
        if botao.count() != 1:
            raise Falha("a linha do pagamento aprovado não tem o botão Reembolsar")
        return botao.first

    def r1():
        page = pagina_gestor()
        pagamento = pagamento_de(token, email_reembolso)
        if pagamento["status"] != "approved":
            raise Falha(f"R1: pré-condição: pagamento do seed está {pagamento['status']}")
        botao = botao_reembolso(page)
        estado["dialogo"] = "dismiss"
        dialogos_antes = len(estado["dialogos"])
        reembolsos_antes = len(chamadas("POST", "/api/payments/refund/"))
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(1500)
        novos = estado["dialogos"][dialogos_antes:]
        if not novos or novos[0][0] != "confirm":
            raise Falha(f"R1: Reembolsar não abriu window.confirm (diálogos: {novos})")
        if f"#{pagamento['id']}" not in novos[0][1]:
            raise Falha(f"R1: a confirmação não identifica o pagamento #{pagamento['id']} ({novos[0][1]!r})")
        if len(chamadas("POST", "/api/payments/refund/")) != reembolsos_antes:
            raise Falha("R1: com o diálogo recusado, a tela chamou o reembolso")
        if pagamento_de(token, email_reembolso)["status"] != "approved":
            raise Falha("R1: o pagamento deixou de estar aprovado com o diálogo recusado")

    def r2():
        page = pagina_gestor()
        pagamento = pagamento_de(token, email_reembolso)
        botao = botao_reembolso(page)
        estado["dialogo"] = "accept"
        dialogos_antes = len(estado["dialogos"])
        botao.click(timeout=TIMEOUT)
        page.wait_for_timeout(2000)
        novos = estado["dialogos"][dialogos_antes:]
        if not novos or f"#{pagamento['id']}" not in novos[0][1]:
            raise Falha(f"R2: a confirmação não identifica o pagamento ({novos})")
        if pagamento_de(token, email_reembolso)["status"] != "refunded":
            raise Falha("R2: com o diálogo aceito, o pagamento não foi reembolsado")

    def k1():
        if erros_console:
            raise Falha(f"K1: {len(erros_console)} erro(s) de console: " + " | ".join(erros_console[:5]))

    cenario("S1", "gestor vê os cursos do seed na aba Cadastro de cursos", s1)
    cenario("X1", "curso com aluno: Excluir desabilitado com o motivo", x1)
    cenario("X2", "curso sem aluno: exclui como hoje", x2)
    cenario("A0", "arquivar com o diálogo recusado não arquiva", a0)
    cenario("A1", "arquivar com o diálogo aceito mostra o badge Arquivado", a1)
    cenario("A2", "arquivado some de /api/courses e do /catalogo", a2)
    cenario("A3", "aluno ativo continua vendo o curso arquivado e o material", a3)
    cenario("A4", "desarquivar devolve o curso ao catálogo", a4)
    cenario("R1", "S7: reembolso recusado no diálogo não chama a API", r1)
    cenario("R2", "S7: reembolso aceito no diálogo reembolsa", r2)
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
