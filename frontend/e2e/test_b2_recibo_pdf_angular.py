"""E2E do botão "Baixar PDF" do recibo no histórico financeiro do aluno (B2, D63 seção "Tela"; Chromium via Playwright).

O backend da entrega já existe (commit 553b9d7): GET /api/student/payments/{id}/receipt.pdf (só approved/refunded;
409 nos demais) e `receipt_pdf_url` em cada item de GET /api/student/payments. Este arquivo cobre só a TELA.

Contrato da tela (D63): na tabela do histórico financeiro de /student, um botão `recibo-pdf` ("Baixar PDF") por
pagamento, SOMENTE para approved e refunded; ao clicar baixa `recibo-<id>.pdf` por requisição autenticada (token no
cabeçalho Authorization, nunca na URL); falha mostra "Não foi possível baixar o recibo." no alerta do histórico
financeiro (erroFinanceiro) e o botão continua disponível. "Ver recibo" (E4) segue funcionando.

Seletor adotado para o botão (o contrato só dá o nome `recibo-pdf`; segue o padrão data-testid do chat da tela):
  [data-testid="recibo-pdf"], dentro da linha (<tr>) do pagamento. Cada pagamento do seed tem um curso próprio, de
  nome único, que identifica a linha. O alerta de erro do histórico é o `.alert-danger` irmão do <h3> "Histórico
  financeiro" (hoje `<div *ngIf="erroFinanceiro" class="alert alert-danger">`).

Checks (cada um aparece como [OK]/[FAIL] no -s, e todos os que falharam entram na asserção final):
  B0 pré-condição (guarda, passa antes da implementação): login do aluno chega a /student e o histórico financeiro
     lista os 7 pagamentos semeados, cada um com "Ver recibo"
  B1 `recibo-pdf` aparece só em approved e refunded; nenhum em pending, rejected, cancelled, in_process,
     charged_back; o botão diz "Baixar PDF"
  B2 clicar no do aprovado baixa recibo-<id>.pdf: começa com %PDF-1., termina com %%EOF, tem (texto não
     comprimido) "RECIBO DE PAGAMENTO", o nome do curso e "R$ 1234,50"; o do reembolsado tem "Pagamento reembolsado."
  B3 a requisição do download é GET autenticada (Authorization: Bearer <JWT do aluno>) e o token não está na URL
  B4 outro aluno (contexto novo) não baixa o recibo do primeiro: a API com o token dele devolve 404 (mesmo corpo
     de um id inexistente); a tela dele não lista os pagamentos do primeiro e só mostra o próprio `recibo-pdf`
  B5 falha (requisição do PDF interceptada com 500): a mensagem exata aparece no alerta do histórico, `recibo-pdf`
     segue visível e habilitado, e com a rede restabelecida um novo clique baixa o PDF
  B6 "Ver recibo" (E4) continua mostrando o recibo na tela (guarda, passa antes da implementação)
  B7 sem erros de console (HTTP 400, 404 em /api, 5xx) nem exceções de página, exceto o 500 provocado de propósito
     em B5 (só o da rota receipt.pdf, só durante B5)

Seed (camada Database no MESMO SQLite temporário do backend de teste, como o e2e da E3): aluno A com 7 pagamentos,
um por status (approved R$ 1234,50 com transação; pending; refunded R$ 80,00; rejected; cancelled; in_process;
charged_back), cada um em um curso próprio criado pela API de admin; aluno B com 1 pagamento aprovado em curso
próprio. O reembolso usa Database.mark_payment_refunded (o mesmo caminho do reembolso do backend). O webhook do
Mercado Pago não é usado: o status vai direto pela camada Database, como na E3 (sem chamada externa).

Harness isolado (D58, H1): este teste sobe e derruba os próprios servidores (backend em processo próprio com banco e
diretório de cursos temporários; `ng serve` em porta livre com proxy temporário). backend/db.sqlite e backend/courses
não são abertos nem alterados. Qualquer `ng serve` que já esteja em outra porta (ex.: 4200) não é usado.

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_b2_recibo_pdf_angular.py -s
Opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT, E2E_NG_TIMEOUT (s, padrão 300), E2E_SCREENSHOTS (pasta de capturas e
dos PDFs baixados; padrão: pasta temporária do sistema).
"""

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import _api, abrir_banco, ambiente_isolado  # noqa: E402
from servidor_e2e_h1 import GESTAO_SENHA  # noqa: E402

# Preenchido pela fixture `servidores` (URLs e banco do ambiente isolado deste módulo).
ALVO = {"base": "", "api": "", "db_path": None}
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_b2_recibo_pdf"))

SENHA = "senha-aluno-b2-2026"
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
MSG_FALHA = "Não foi possível baixar o recibo."

# (rótulo do status no banco, preço do curso, tem recibo em PDF)
STATUS_SEMEADOS = [
    ("approved", 1234.50, True),
    ("pending", 99.00, False),
    ("refunded", 80.00, True),
    ("rejected", 70.00, False),
    ("cancelled", 60.00, False),
    ("in_process", 50.00, False),
    ("charged_back", 40.00, False),
]
BOTAO_PDF = '[data-testid="recibo-pdf"]'


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _seed_backend():
    return abrir_banco(ALVO["db_path"])


def _hash_senha(senha):
    _seed_backend()
    from core.security import get_password_hash

    return get_password_hash(senha)


def novo_email(tag):
    return f"e2e.b2.{tag}.{uuid.uuid4().hex[:10]}@teste.com"


def criar_curso(prefixo, preco):
    """Cria um curso pela API de admin. Devolve (course_id, nome). O nome é ASCII e único (aparece no PDF)."""
    token = _api(ALVO["api"], "POST", "/api/admin/login", {"password": GESTAO_SENHA})[1]["token"]
    course_id = f"{prefixo}_{uuid.uuid4().hex[:8]}"
    nome = f"Curso B2 {uuid.uuid4().hex[:8]}"
    corpo = {
        "id": course_id, "name": nome, "description": "Curso B2 do e2e", "price": preco,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt",
    }
    status, _ = _api(ALVO["api"], "POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")
    return course_id, nome


def semear_aluno(tag):
    Database = _seed_backend()
    email = novo_email(tag)
    nome = f"Aluno B2 {tag}"
    user_id = Database.add_user(email, nome, _hash_senha(SENHA), role="student")
    if user_id is None:
        raise RuntimeError(f"seed: não foi possível criar a conta {email}")
    return email, user_id, nome


def semear_pagamento(user_id, course_id, status, valor):
    """Matrícula + pagamento no status pedido. Devolve payment_id."""
    Database = _seed_backend()
    ref = f"{course_id}:b2e2e:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    if status == "refunded":
        Database.update_payment_status(payment_id, "approved", uuid.uuid4().hex[:12])
        Database.mark_payment_refunded(payment_id)
    elif status == "pending":
        pass
    elif status == "approved":
        Database.update_payment_status_by_reference(ref, "approved", uuid.uuid4().hex[:12])
    else:
        Database.update_payment_status(payment_id, status)
    return payment_id


def token_do_aluno(email):
    status, corpo = _api(ALVO["api"], "POST", "/api/token", formulario={"username": email, "password": SENHA})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise RuntimeError(f"seed: login por API de {email} respondeu HTTP {status}")
    return corpo["access_token"]


def get_bruto(caminho, token=None):
    """GET direto na API. Devolve (status, corpo_bytes, cabecalhos_em_minusculas)."""
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(ALVO["api"] + caminho, headers=cabecalhos, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, resposta.read(), {k.lower(): v for k, v in resposta.headers.items()}
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read(), {k.lower(): v for k, v in erro.headers.items()}


def login_na_tela(page, email, senha, rotulo):
    try:
        page.goto(ALVO["base"] + "/", wait_until="networkidle")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        page.wait_for_load_state("networkidle")
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: login não levou a /student (URL atual {page.url})")


def linha_do_curso(page, nome_curso):
    return page.locator("tbody tr").filter(has_text=nome_curso)


def alerta_financeiro(page):
    """erroFinanceiro: o .alert-danger irmão do <h3> 'Histórico financeiro'."""
    return page.locator("h3:has-text('Histórico financeiro') ~ .alert-danger")


def texto_pdf(caminho):
    """Conteúdo do PDF baixado como texto latin-1 (o PDF da D63 não é comprimido)."""
    dados = Path(caminho).read_bytes()
    return dados, dados.decode("latin-1")


@pytest.fixture(scope="module")
def servidores():
    """Backend de teste (banco e cursos temporários) e Angular; derruba tudo (e apaga os cursos) ao final."""
    with ambiente_isolado("b2") as ambiente:
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


def test_b2_recibo_pdf_angular_e2e(servidores, browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    estado = {"rotulo": "", "page": None, "tolerar_500_recibo": False}
    requisicoes_pdf = []  # (metodo, url, request) de tudo que casa com receipt.pdf no contexto do aluno A

    # --- seed: aluno A com 7 pagamentos (um por status), aluno B com 1 aprovado
    seed = {"ok": False, "erro": ""}
    pagamentos = {}  # status -> {"id", "nome", "valor"}
    try:
        email_a, uid_a, nome_a = semear_aluno("a")
        for status, valor, _ in STATUS_SEMEADOS:
            course_id, nome_curso = criar_curso(f"b2_{status}", valor)
            pid = semear_pagamento(uid_a, course_id, status, valor)
            pagamentos[status] = {"id": pid, "nome": nome_curso, "valor": valor}
        email_b, uid_b, nome_b = semear_aluno("b")
        curso_b_id, nome_curso_b = criar_curso("b2_outro", 33.00)
        pid_b = semear_pagamento(uid_b, curso_b_id, "approved", 33.00)
        token_a = token_do_aluno(email_a)
        token_b = token_do_aluno(email_b)
        seed["ok"] = True
    except Exception as erro:  # o seed falhando deixa o cenário vermelho, com a causa
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(rotulo, capturar_pdf=False):
        estado["rotulo"] = rotulo
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        contextos.append(ctx)
        page = ctx.new_page()
        estado["page"] = page

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is None:
                return
            codigo = int(m.group(1))
            url = msg.location.get("url") or ""
            if estado["tolerar_500_recibo"] and codigo == 500 and "receipt.pdf" in url:
                return  # 500 provocado de propósito em B5
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_console.append(f"{rotulo}: {msg.text} [{url}]")

        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: exceção de página: {e}"))
        if capturar_pdf:
            page.on("request", lambda req: requisicoes_pdf.append(req) if "receipt.pdf" in req.url else None)
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
        if not seed["ok"]:
            resultados.append((codigo, nome, False, f"seed falhou: {seed['erro']}"))
            print(f"[FAIL] {codigo} {nome} -> seed falhou: {seed['erro']}")
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

    def exigir_pagina_do_aluno_a():
        page = estado["pagina_a"] if "pagina_a" in estado else None
        if page is None or not page.url.rstrip("/").endswith("/student"):
            raise Falha("pré-requisito: o aluno A não está em /student (B0 falhou)")
        estado["page"] = page
        return page

    def baixar(page, status, rotulo):
        """Clica no recibo-pdf da linha do pagamento e devolve (download, caminho_salvo)."""
        linha = linha_do_curso(page, pagamentos[status]["nome"])
        botao = linha.locator(BOTAO_PDF)
        if botao.count() == 0:
            raise Falha(f"{rotulo}: a linha do pagamento {status} não tem botão recibo-pdf")
        try:
            with page.expect_download(timeout=TIMEOUT * 2) as info:
                botao.first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: clicar em recibo-pdf ({status}) não disparou download")
        download = info.value
        destino = OUT / f"b2_{status}_{uuid.uuid4().hex[:6]}.pdf"
        download.save_as(str(destino))
        return download, destino

    # --- B0 -------------------------------------------------------------------------
    def b0():
        page = nova_pagina("B0", capturar_pdf=True)
        login_na_tela(page, email_a, SENHA, "B0 login do aluno A")
        estado["pagina_a"] = page
        try:
            page.locator("tbody tr").first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("B0: o histórico financeiro não carregou nenhuma linha em /student")
        linhas = page.locator("tbody tr").count()
        if linhas != len(STATUS_SEMEADOS):
            raise Falha(f"B0: o histórico mostra {linhas} linhas (esperado {len(STATUS_SEMEADOS)})")
        for status, dados in pagamentos.items():
            linha = linha_do_curso(page, dados["nome"])
            if linha.count() != 1:
                raise Falha(f"B0: o pagamento {status} ({dados['nome']}) aparece {linha.count()}x no histórico")
            if linha.get_by_role("button", name="Ver recibo").count() != 1:
                raise Falha(f"B0: a linha do pagamento {status} não tem o botão 'Ver recibo'")
        # a API (já pronta) entrega o receipt_pdf_url de cada item
        status_http, corpo, _ = get_bruto("/api/student/payments", token_a)
        itens = json.loads(corpo)["payments"] if status_http == 200 else []
        faltando = [i["id"] for i in itens if i.get("receipt_pdf_url") != f"/api/student/payments/{i['id']}/receipt.pdf"]
        if status_http != 200 or len(itens) != len(STATUS_SEMEADOS) or faltando:
            raise Falha(f"B0: GET /api/student/payments HTTP {status_http}, {len(itens)} itens, sem receipt_pdf_url em {faltando}")

    cenario("B0", "pré-condição: login, seed e histórico financeiro carregam (7 pagamentos, 'Ver recibo' em todos)", b0)

    # --- B1 -------------------------------------------------------------------------
    def b1():
        page = exigir_pagina_do_aluno_a()
        erros = []
        for status, _valor, deve_ter in STATUS_SEMEADOS:
            linha = linha_do_curso(page, pagamentos[status]["nome"])
            qtd = linha.locator(BOTAO_PDF).count()
            if deve_ter and qtd != 1:
                erros.append(f"{status}: esperado 1 recibo-pdf, achou {qtd}")
            if not deve_ter and qtd != 0:
                erros.append(f"{status}: esperado nenhum recibo-pdf, achou {qtd}")
            if deve_ter and qtd == 1:
                rotulo = linha.locator(BOTAO_PDF).first.inner_text().strip()
                if "Baixar PDF" not in rotulo:
                    erros.append(f"{status}: o botão diz '{rotulo}' (esperado 'Baixar PDF')")
        total = page.locator(BOTAO_PDF).count()
        if total != 2:
            erros.append(f"total de recibo-pdf na tela: {total} (esperado 2)")
        if erros:
            raise Falha("B1: " + "; ".join(erros))

    cenario("B1", "recibo-pdf só em approved e refunded (nenhum em pending, rejected, cancelled, in_process, charged_back)", b1)

    # --- B2 -------------------------------------------------------------------------
    def b2():
        page = exigir_pagina_do_aluno_a()
        # aprovado
        aprovado = pagamentos["approved"]
        download, destino = baixar(page, "approved", "B2 aprovado")
        esperado = f"recibo-{aprovado['id']}.pdf"
        if download.suggested_filename != esperado:
            raise Falha(f"B2 aprovado: nome sugerido '{download.suggested_filename}' (esperado '{esperado}')")
        dados, texto = texto_pdf(destino)
        if not texto.startswith("%PDF-1."):
            raise Falha(f"B2 aprovado: o arquivo não começa com %PDF-1. (começa com {dados[:12]!r})")
        if not texto.rstrip().endswith("%%EOF"):
            raise Falha(f"B2 aprovado: o arquivo não termina com %%EOF (termina com {dados[-12:]!r})")
        for trecho in ("RECIBO DE PAGAMENTO", aprovado["nome"], "R$ 1234,50"):
            if trecho not in texto:
                raise Falha(f"B2 aprovado: o PDF baixado não contém '{trecho}'")
        if "Pagamento reembolsado." in texto:
            raise Falha("B2 aprovado: o PDF do aprovado traz 'Pagamento reembolsado.'")
        # reembolsado
        reemb = pagamentos["refunded"]
        download, destino = baixar(page, "refunded", "B2 reembolsado")
        esperado = f"recibo-{reemb['id']}.pdf"
        if download.suggested_filename != esperado:
            raise Falha(f"B2 reembolsado: nome sugerido '{download.suggested_filename}' (esperado '{esperado}')")
        dados, texto = texto_pdf(destino)
        if not texto.startswith("%PDF-1.") or not texto.rstrip().endswith("%%EOF"):
            raise Falha("B2 reembolsado: o arquivo não é um PDF íntegro (%PDF-1. ... %%EOF)")
        for trecho in ("RECIBO DE PAGAMENTO", reemb["nome"], "R$ 80,00", "Pagamento reembolsado."):
            if trecho not in texto:
                raise Falha(f"B2 reembolsado: o PDF baixado não contém '{trecho}'")

    cenario("B2", "clicar em recibo-pdf baixa recibo-<id>.pdf íntegro, com título, curso e valor (aprovado e reembolsado)", b2)

    # --- B3 -------------------------------------------------------------------------
    def b3():
        exigir_pagina_do_aluno_a()
        alvo = f"/api/student/payments/{pagamentos['approved']['id']}/receipt.pdf"
        casam = [r for r in requisicoes_pdf if r.url.split("?")[0].endswith(alvo)]
        if not casam:
            raise Falha(f"B3: nenhuma requisição a {alvo} saiu do navegador (vistas: {[r.url for r in requisicoes_pdf]})")
        req = casam[0]
        cabecalhos = {k.lower(): v for k, v in req.all_headers().items()}
        auth = cabecalhos.get("authorization", "")
        if req.method != "GET":
            raise Falha(f"B3: a requisição do PDF usou {req.method} (esperado GET)")
        if not auth.startswith("Bearer ") or len(auth) <= len("Bearer "):
            raise Falha(f"B3: a requisição do PDF saiu sem 'Authorization: Bearer <token>' (cabeçalho: '{auth[:20]}')")
        if not re.fullmatch(r"Bearer [\w-]+\.[\w-]+\.[\w-]+", auth):
            raise Falha("B3: o Authorization da requisição não é 'Bearer <JWT>'")
        jwt_navegador = auth.split(" ", 1)[1]
        for r in requisicoes_pdf:
            consulta = r.url.partition("?")[2].lower()
            if jwt_navegador in r.url or token_a in r.url or any(p in consulta for p in ("token", "jwt", "authorization", "access_token")):
                raise Falha(f"B3: o token aparece na URL do download ({r.url})")

    cenario("B3", "o download é GET com Authorization: Bearer e sem token na URL", b3)

    # --- B4 -------------------------------------------------------------------------
    def b4():
        id_a = pagamentos["approved"]["id"]
        caminho_a = f"/api/student/payments/{id_a}/receipt.pdf"
        # sanidade: o dono baixa pela API
        status_dono, corpo_dono, cab = get_bruto(caminho_a, token_a)
        if status_dono != 200 or not corpo_dono.startswith(b"%PDF-1."):
            raise Falha(f"B4: o dono não baixou o próprio PDF pela API (HTTP {status_dono})")
        # o outro aluno recebe o MESMO 404 de um id inexistente
        status_b, corpo_b, _ = get_bruto(caminho_a, token_b)
        status_x, corpo_x, _ = get_bruto("/api/student/payments/987654321/receipt.pdf", token_b)
        if status_b != 404:
            raise Falha(f"B4: o outro aluno recebeu HTTP {status_b} no recibo alheio (esperado 404)")
        if (status_b, corpo_b) != (status_x, corpo_x):
            raise Falha(f"B4: 404 do recibo alheio difere do de id inexistente ({corpo_b!r} vs {corpo_x!r})")
        if corpo_dono[:8] in corpo_b:
            raise Falha("B4: o 404 do outro aluno carrega conteúdo de PDF")
        # a tela do outro aluno
        page = nova_pagina("B4")
        login_na_tela(page, email_b, SENHA, "B4 login do aluno B")
        try:
            page.locator("tbody tr").first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("B4: o histórico financeiro do aluno B não carregou")
        conteudo = page.content()
        for status, dados in pagamentos.items():
            if dados["nome"] in conteudo:
                raise Falha(f"B4: a tela do aluno B mostra o curso do aluno A ({status}: {dados['nome']})")
        if nome_a in conteudo or email_a in conteudo:
            raise Falha("B4: a tela do aluno B mostra nome ou e-mail do aluno A")
        if linha_do_curso(page, nome_curso_b).count() != 1:
            raise Falha("B4: a tela do aluno B não mostra o próprio pagamento")
        qtd = page.locator(BOTAO_PDF).count()
        if qtd != 1 or linha_do_curso(page, nome_curso_b).locator(BOTAO_PDF).count() != 1:
            raise Falha(f"B4: o aluno B deveria ter exatamente 1 recibo-pdf (o do próprio pagamento), achou {qtd}")
        # o clique do aluno B baixa o PDF DELE (não o de A)
        with page.expect_download(timeout=TIMEOUT * 2) as info:
            page.locator(BOTAO_PDF).first.click(timeout=TIMEOUT)
        download = info.value
        if download.suggested_filename != f"recibo-{pid_b}.pdf":
            raise Falha(f"B4: o aluno B baixou '{download.suggested_filename}' (esperado recibo-{pid_b}.pdf)")
        destino = OUT / f"b2_aluno_b_{uuid.uuid4().hex[:6]}.pdf"
        download.save_as(str(destino))
        _, texto = texto_pdf(destino)
        if pagamentos["approved"]["nome"] in texto or nome_a in texto:
            raise Falha("B4: o PDF do aluno B contém dados do aluno A")
        estado["page"] = estado["pagina_a"]

    cenario("B4", "outro aluno: 404 igual ao de inexistente na API, tela sem pagamentos alheios, só o próprio recibo-pdf", b4)

    # --- B5 -------------------------------------------------------------------------
    def b5():
        page = exigir_pagina_do_aluno_a()
        linha = linha_do_curso(page, pagamentos["approved"]["nome"])
        botao = linha.locator(BOTAO_PDF)
        if botao.count() == 0:
            raise Falha("B5: a linha do pagamento aprovado não tem recibo-pdf")
        estado["tolerar_500_recibo"] = True
        page.route(re.compile(r"receipt\.pdf"), lambda rota: rota.fulfill(
            status=500, content_type="application/json", body='{"detail":"erro provocado pelo teste"}'))
        try:
            botao.first.click(timeout=TIMEOUT)
            alerta = alerta_financeiro(page)
            try:
                alerta.first.wait_for(timeout=TIMEOUT)
            except sync_api.TimeoutError:
                raise Falha("B5: após o 500 do PDF nenhum alerta apareceu no histórico financeiro")
            texto = alerta.first.inner_text().strip()
            if texto != MSG_FALHA:
                raise Falha(f"B5: mensagem do alerta '{texto}' (esperado '{MSG_FALHA}')")
            if "erro provocado" in page.inner_text("body"):
                raise Falha("B5: a tela expõe o corpo do erro do servidor")
            botao_depois = linha_do_curso(page, pagamentos["approved"]["nome"]).locator(BOTAO_PDF)
            if botao_depois.count() != 1 or not botao_depois.first.is_visible() or not botao_depois.first.is_enabled():
                raise Falha("B5: após a falha o recibo-pdf não continua visível e habilitado")
        finally:
            page.unroute(re.compile(r"receipt\.pdf"))
        # com a rede restabelecida, novo clique baixa o PDF
        download, destino = baixar(page, "approved", "B5 nova tentativa")
        if download.suggested_filename != f"recibo-{pagamentos['approved']['id']}.pdf":
            raise Falha(f"B5: nova tentativa baixou '{download.suggested_filename}'")
        estado["tolerar_500_recibo"] = False

    cenario("B5", "falha 500 no PDF: mensagem exata em erroFinanceiro, recibo-pdf segue disponível, nova tentativa baixa", b5)
    estado["tolerar_500_recibo"] = False

    # --- B6 -------------------------------------------------------------------------
    def b6():
        page = exigir_pagina_do_aluno_a()
        aprovado = pagamentos["approved"]
        linha = linha_do_curso(page, aprovado["nome"])
        linha.get_by_role("button", name="Ver recibo").click(timeout=TIMEOUT)
        cartao = page.locator("div.card.border-primary")
        try:
            cartao.first.wait_for(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("B6: 'Ver recibo' não mostrou o cartão do recibo na tela")
        texto = cartao.first.inner_text()
        if f"Recibo #{aprovado['id']}" not in texto or aprovado["nome"] not in texto:
            raise Falha(f"B6: o cartão do recibo não mostra o número e o curso do pagamento (texto: {texto!r})")

    cenario("B6", "'Ver recibo' (E4) continua mostrando o recibo na tela", b6)

    # --- B7 -------------------------------------------------------------------------
    def b7():
        if erros_console:
            raise Falha(f"B7 console: {len(erros_console)} erro(s): " + " | ".join(erros_console[:5]))

    cenario("B7", "sem erros de console (400, 404 em /api, 5xx) nem exceções de página, exceto o 500 provocado em B5", b7)

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
