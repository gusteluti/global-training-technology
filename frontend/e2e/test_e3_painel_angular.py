"""E2E do painel de inscrições e materiais do aluno (E3, Chromium via Playwright). Item 1.1 e RF22.

Cenários (checks numerados):
  P1 login do aluno em / chega a /student
  P2 /student mostra "Meus cursos" com as DUAS matrículas, cada uma com badge de status visível
     (badge = classe Bootstrap .badge, padrão do projeto; a matrícula ativa mostra o status ativo e a
     pendente mostra o status pendente, em português ou no valor cru do status)
  P3 matrícula ativa mostra o link do material: âncora com o título e href com a URL do material
  P4 matrícula pending NÃO mostra nenhuma URL do material (busca no HTML inteiro da tela, page.content())
  P5 o aluno NÃO vê matrícula de outro aluno: nome, e-mail, curso e URL do material do outro aluno
     estão ausentes da tela
  P6 sem erros de console nem exceções de página nas telas acima. Erro reprova quando: HTTP 400,
     HTTP 404 em /api/ ou HTTP 5xx, ou exceção de página. Sem lista de tolerância: E3 não tem 400 esperado
  P7 usuário não logado em /student é redirecionado para / (AuthGuard). Este check é guarda de
     preservação: o guard já existe no frontend, então pode passar antes da implementação (ver relatório)

Seed: um aluno com senha, matrícula ativa no curso com materiais, matrícula pending em outro curso com
materiais, e um segundo aluno com matrícula ativa em um curso com materiais próprios (P5).
Os cursos são criados pela API de admin (POST /api/admin/create-course, com o campo materials).
As matrículas são criadas por Database.create_enrollment + record_payment, e o status é levado ao
valor pedido por Database.update_payment_status_by_reference (o mesmo caminho que o webhook usa depois
de consultar o Mercado Pago, sem chamada externa).

Harness isolado (D58, H1): o teste sobe e derruba os próprios servidores; nada precisa estar de pé antes.
  - Backend: frontend/e2e/servidor_e2e_h1.py em processo próprio, porta livre, SQLite temporário (DB_PATH
    isolado), diretório de cursos temporário (create-course grava lá, nunca em backend/courses), segredo de
    webhook e CORS de teste, Groq e Mercado Pago falsos. A credencial administrativa (login legado
    /api/admin/login, usada para criar os cursos) é a fabricada pelo helper; o ADMIN_PASSWORD do ambiente do
    desenvolvedor não é lido.
  - Frontend: `npx ng serve` em porta livre, com proxy temporário /api -> backend de teste.
  - backend/db.sqlite e backend/courses de desenvolvimento não são abertos nem alterados (limitação D7 resolvida).
  - E2E_BASE_URL / E2E_API_URL não são mais usados (apontar para servidores de fora quebraria o isolamento).

O seed das matrículas usa a camada Database dentro do processo do teste, apontando para o MESMO arquivo SQLite
temporário do backend de teste (apoio_harness_h1.abrir_banco redireciona o import de `db`).

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas fixas opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT;
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_e3_painel_angular.py -s
Screenshots vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
import sys
import tempfile
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
from servidor_e2e_h1 import GESTAO_SENHA  # noqa: E402

# Preenchido pela fixture `servidores` (URLs e banco do ambiente isolado deste módulo).
ALVO = {"base": "", "api": "", "db_path": None}
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_painel_aluno"))

ADMIN_PASSWORD = GESTAO_SENHA
SENHA = "senha-aluno-e3-2026"
TIMEOUT = 5000
PAGAMENTO_DE_STATUS = {"active": "approved", "pending": "pending"}
ATIVO = re.compile(r"\b(ativo|ativa|active)\b", re.IGNORECASE)
PENDENTE = re.compile(r"\b(pendente|pending)\b", re.IGNORECASE)
ERRO_HTTP = re.compile(r"status of (\d{3})")


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _seed_backend():
    Database = abrir_banco(ALVO["db_path"])
    from core.security import get_password_hash

    return Database, get_password_hash


def novo_email(tag):
    return f"e2e.e3.{tag}.{uuid.uuid4().hex[:10]}@teste.com"


def _api(metodo, caminho, corpo=None, token=None):
    """Chamada HTTP direta à API. Devolve (status, corpo_json_ou_None)."""
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


def criar_curso(prefixo, com_materiais):
    """Cria um curso pela API de admin. Devolve (course_id, nome, materiais_ou_None)."""
    token = _api("POST", "/api/admin/login", {"password": ADMIN_PASSWORD})[1]["token"]
    course_id = f"{prefixo}_{uuid.uuid4().hex[:8]}"
    nome = f"Curso E3 {uuid.uuid4().hex[:6]}"
    materiais = None
    if com_materiais:
        materiais = [
            {"title": f"Apostila {course_id}", "url": f"https://materiais.test/{course_id}/apostila.pdf", "type": "pdf"},
        ]
    corpo = {
        "id": course_id, "name": nome, "description": "Curso E3 do e2e", "price": 150.0,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
    }
    if materiais is not None:
        corpo["materials"] = materiais
    status, _ = _api("POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return course_id, nome, materiais


def semear_aluno(tag):
    Database, get_password_hash = _seed_backend()
    email = novo_email(tag)
    user_id = Database.add_user(email, f"Aluno E3 {tag}", get_password_hash(SENHA), role="student")
    if user_id is None:
        raise RuntimeError(f"seed: não foi possível criar a conta {email}")
    return email, user_id, f"Aluno E3 {tag}"


def semear_matricula(user_id, course_id, status):
    Database, _ = _seed_backend()
    ref = f"{course_id}:e3e2e:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    Database.record_payment(enrollment_id, 150.0, "mercado_pago")
    if status != "pending":
        Database.update_payment_status_by_reference(ref, PAGAMENTO_DE_STATUS[status], uuid.uuid4().hex[:12])
    return enrollment_id


def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/")


def login_na_tela(page, email, senha, rotulo):
    try:
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campos de login não encontrados na tela /")


@pytest.fixture(scope="module")
def servidores():
    """Backend de teste (banco e cursos temporários) e Angular; derruba tudo (e apaga os cursos) ao final."""
    with ambiente_isolado("e3") as ambiente:
        ALVO.update(base=ambiente["base"], api=ambiente["api"], db_path=ambiente["db_path"])
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_e3_painel_angular_e2e(servidores, browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    cursos_criados = []
    estado = {"rotulo": "", "page": None}

    # --- seed: aluno A (matrícula ativa com material + pending com material) e aluno B (ativa, sigilosa)
    seed_ok = {"ok": False, "erro": ""}
    try:
        curso_ativo, nome_ativo, mats_ativo = criar_curso("e3_ativo", com_materiais=True)
        cursos_criados.append(curso_ativo)
        curso_pend, nome_pend, mats_pend = criar_curso("e3_pend", com_materiais=True)
        cursos_criados.append(curso_pend)
        curso_b, nome_b, mats_b = criar_curso("e3_sigilo", com_materiais=True)
        cursos_criados.append(curso_b)

        email_a, uid_a, nome_a = semear_aluno("a")
        semear_matricula(uid_a, curso_ativo, "active")
        semear_matricula(uid_a, curso_pend, "pending")

        email_b, uid_b, nome_b_aluno = semear_aluno("b")
        semear_matricula(uid_b, curso_b, "active")
        seed_ok["ok"] = True
    except Exception as erro:  # o seed falhando deixa o cenário vermelho, com a causa
        seed_ok["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(rotulo):
        estado["rotulo"] = rotulo
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()
        estado["page"] = page
        respostas_erro = []

        def ao_resposta(resposta):
            if resposta.status >= 400:
                respostas_erro.append((resposta.status, resposta.url))

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is None:
                return
            codigo = int(m.group(1))
            url = msg.location.get("url") or ""
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_console.append(f"{rotulo}: {msg.text} [{url}]")

        page.on("response", ao_resposta)
        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: exceção de página: {e}"))
        return page

    def captura_de_falha(codigo):
        page = estado["page"]
        if page is None:
            return
        try:
            page.screenshot(path=str(OUT / f"{codigo}_falha.png"), full_page=True)
        except Exception:
            pass

    def cenario(codigo, nome, fn):
        if not seed_ok["ok"]:
            resultados.append((codigo, nome, False, f"seed falhou: {seed_ok['erro']}"))
            print(f"[FAIL] {codigo} {nome} -> seed falhou: {seed_ok['erro']}")
            return
        try:
            fn()
            resultados.append((codigo, nome, True, ""))
            print(f"[OK]   {codigo} {nome}")
        except Falha as erro:
            captura_de_falha(codigo)
            resultados.append((codigo, nome, False, str(erro)))
            print(f"[FAIL] {codigo} {nome} -> {erro}")
        except Exception as erro:
            captura_de_falha(codigo)
            linha = str(erro).splitlines()[0] if str(erro) else ""
            detalhe = f"{type(erro).__name__}: {linha}"
            resultados.append((codigo, nome, False, detalhe))
            print(f"[FAIL] {codigo} {nome} -> {detalhe}")

    # --- P1 -------------------------------------------------------------------------
    def p1():
        page = nova_pagina("P1")
        login_na_tela(page, email_a, SENHA, "P1 login do aluno")
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"P1 login do aluno: URL final {page.url} (esperado /student)")
        page.wait_for_load_state("networkidle")

    cenario("P1", "login do aluno em / chega a /student", p1)

    # --- P2 -------------------------------------------------------------------------
    def p2():
        page = estado["page"]
        if page is None or caminho_da_url(page.url) != "/student":
            raise Falha("P2 pré-requisito: P1 não deixou o aluno em /student")
        texto = page.inner_text("body")
        if "Meus cursos" not in texto:
            raise Falha("P2 meus cursos: a tela /student não mostra 'Meus cursos'")
        for nome in (nome_ativo, nome_pend):
            if nome not in texto:
                raise Falha(f"P2 meus cursos: matrícula '{nome}' não aparece na tela")
        badges = [page.locator(".badge").nth(i).inner_text().strip() for i in range(page.locator(".badge").count())
                  if page.locator(".badge").nth(i).is_visible()]
        if not any(ATIVO.search(b) for b in badges):
            raise Falha(f"P2 badge: nenhum badge de matrícula ativa visível (badges={badges})")
        if not any(PENDENTE.search(b) for b in badges):
            raise Falha(f"P2 badge: nenhum badge de matrícula pendente visível (badges={badges})")

    cenario("P2", "/student mostra 'Meus cursos' com as duas matrículas e badge de status", p2)

    # --- P3 -------------------------------------------------------------------------
    def p3():
        page = estado["page"]
        if page is None or caminho_da_url(page.url) != "/student":
            raise Falha("P3 pré-requisito: aluno não está em /student")
        url = mats_ativo[0]["url"]
        titulo = mats_ativo[0]["title"]
        link = page.locator(f'a[href="{url}"]')
        if link.count() == 0:
            raise Falha(f"P3 material ativo: nenhum link para {url} na tela")
        if titulo not in link.first.inner_text():
            raise Falha(f"P3 material ativo: o link não mostra o título '{titulo}'")

    cenario("P3", "matrícula ativa mostra o link do material (título e href)", p3)

    # --- P4 -------------------------------------------------------------------------
    def p4():
        page = estado["page"]
        if page is None or caminho_da_url(page.url) != "/student":
            raise Falha("P4 pré-requisito: aluno não está em /student")
        url_pend = mats_pend[0]["url"]
        if url_pend in page.content():
            raise Falha(f"P4 pending: a URL do material da matrícula pendente aparece na tela ({url_pend})")

    cenario("P4", "matrícula pending não mostra nenhuma URL de material", p4)

    # --- P5 -------------------------------------------------------------------------
    def p5():
        page = estado["page"]
        if page is None or caminho_da_url(page.url) != "/student":
            raise Falha("P5 pré-requisito: aluno não está em /student")
        texto = page.inner_text("body")
        conteudo = page.content()
        for nome_alheio, rotulo_alheio in ((nome_b, "curso do outro aluno"), (nome_b_aluno, "nome do outro aluno"),
                                           (email_b, "e-mail do outro aluno")):
            if nome_alheio in texto:
                raise Falha(f"P5 isolamento: a tela mostra o {rotulo_alheio} ({nome_alheio})")
        url_b = mats_b[0]["url"]
        if url_b in conteudo:
            raise Falha("P5 isolamento: a tela mostra a URL do material de matrícula de outro aluno")

    cenario("P5", "aluno não vê matrícula, nome, e-mail nem material de outro aluno", p5)

    # --- P6 -------------------------------------------------------------------------
    def p6():
        if erros_console:
            raise Falha(f"P6 console: {len(erros_console)} erro(s): " + " | ".join(erros_console[:5]))

    cenario("P6", "sem erros de console (400, 404 em /api, 5xx) nem exceções nas telas acima", p6)

    # --- P7 -------------------------------------------------------------------------
    def p7():
        page = nova_pagina("P7")
        page.goto(ALVO["base"] + "/student", wait_until="networkidle")
        if caminho_da_url(page.url) != "":
            raise Falha(f"P7 guarda: usuário sem login em /student foi levado a {page.url} (esperado /)")

    cenario("P7", "usuário não logado em /student é redirecionado para /", p7)

    # --- limpeza ----------------------------------------------------------------------
    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
