"""E2E das telas de conta do aluno (E2, Chromium via Playwright): cadastro, definição de senha e login.

Cenários (cada um é um check numerado, C1-C8):
  C1 cadastro em /cadastro -> mensagem de sucesso -> login em / leva ao /student
  C2 cadastro com senha curta (<8) -> erro visível, sem recarregar e sem criar conta
  C3 cadastro com e-mail existente (admin@gt.com) -> erro GENÉRICO; e-mail e "já cadastrado" ausentes
     da tela; senha da conta existente continua a mesma
  C4 /definir-senha?token=<válido> -> sucesso; login por API com e-mail + nova senha funciona
  C5 mesmo token reaberto e enviado -> erro genérico (uso único)
  C6 /definir-senha?token=xyz -> erro genérico visível; sucesso nunca aparece
  C7 login existente em / : conta sem senha é recusada; conta com senha entra e chega a /student
  C8 nenhum erro de console (nem exceção de página) nas telas acima

Filtro estreito do C8 (ignora SOMENTE os 400 esperados por rota de validação, D15/D16):
  1) POST /api/auth/register com 400, na tela /cadastro (validação: senha curta, e-mail existente)
  2) POST /api/auth/password-setup com 400, na tela /definir-senha (token inválido, usado ou
     expirado, e senha curta)
A associação é feita pela resposta HTTP real (page.on("response")): cada erro de console
"status of 400" consome uma resposta 400 pendente, e só é ignorado se método, caminho da API e
tela atual baterem exatamente com a lista acima. Qualquer outro 400 (ex.: POST /api/token),
qualquer 500 ou 4xx/5xx de outra origem, e qualquer exceção de página reprovam o C8.

Pré-requisitos (ambos de pé antes de rodar):
  - backend FastAPI em http://127.0.0.1:8000  (cd backend && uvicorn app:app --port 8000)
  - Angular em http://localhost:4200 com proxy /api -> 8000 (cd frontend && npx ng serve)
  - conta admin@gt.com / admin123 cadastrada (gestor de teste, usada no C3)
  - Chromium do Playwright instalado: py -3 -m playwright install chromium

Seed: as contas de teste (e-mails com uuid) e os tokens de definição são criados no banco que o
backend usa (backend/db.sqlite, via Database e core.password_setup.emitir_token_definicao).
Limitação D7: o harness usa o banco de dev e o acúmulo de contas de teste se repete a cada execução.
Correção futura: subir o backend com DB_PATH isolado.

Porta diferente do 4200: defina E2E_BASE_URL (ex.: http://localhost:4300).
API direta (login por API no C4/C7/C3): E2E_API_URL, padrão http://127.0.0.1:8000.
Execução: py -3 -m pytest frontend/e2e/test_e2_conta_aluno_angular.py -s
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

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:4200").rstrip("/")
API = os.environ.get("E2E_API_URL", "http://127.0.0.1:8000").rstrip("/")
BACKEND = Path(__file__).resolve().parents[2] / "backend"
OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_conta_aluno"))

ADMIN_EMAIL = "admin@gt.com"
ADMIN_PASSWORD = "admin123"
SENHA_NOVA = "senha-forte-2026"
SENHA_CURTA = "curta1"  # 6 caracteres (mínimo é 8, D14)
TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
# Únicos 400 de console tolerados: (método, caminho da API, tela onde ocorre). Lista exata.
ROTAS_400_ESPERADO = {
    ("POST", "/api/auth/register", "/cadastro"),
    ("POST", "/api/auth/password-setup", "/definir-senha"),
}


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


def _seed_backend():
    """Importa a camada de banco e o módulo de produção de token. Só leitura de código de produção."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from db import Database
    from core.password_setup import emitir_token_definicao

    Database.init_db()
    return Database, emitir_token_definicao


def novo_email(tag):
    return f"e2e.{tag}.{uuid.uuid4().hex[:10]}@teste.com"


def semear_aluno_sem_senha(tag):
    Database, _ = _seed_backend()
    email = novo_email(tag)
    user_id = Database.get_or_create_user(email, "Aluno E2E Conta")
    return email, user_id


def semear_token_definicao(tag):
    """Conta de aluno SEM senha e um token de definição válido (valor em claro, uma vez)."""
    Database, emitir_token_definicao = _seed_backend()
    email, user_id = semear_aluno_sem_senha(tag)
    token = emitir_token_definicao(user_id)
    return email, token


def semear_aluno_com_senha(tag, senha):
    Database, _ = _seed_backend()
    from core.security import get_password_hash

    email = novo_email(tag)
    Database.add_user(email, "Aluno E2E Senha", get_password_hash(senha), role="student")
    return email


def conta_no_banco(email):
    Database, _ = _seed_backend()
    return Database.get_user_by_email(email)


def login_api(email, senha):
    """POST /api/token direto. Devolve (status_http, corpo_json_ou_None)."""
    dados = urllib.parse.urlencode({"username": email, "password": senha}).encode()
    req = urllib.request.Request(
        API + "/api/token", data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


def caminho_da_url(url):
    return urllib.parse.urlparse(url).path.rstrip("/")


def exigir_rota(page, caminho_com_query, rotulo):
    """Abre a rota e exige que a URL final continue nela (o curinga '**' redireciona para '/')."""
    page.goto(BASE + caminho_com_query, wait_until="networkidle")
    esperado = urllib.parse.urlparse(caminho_com_query).path.rstrip("/")
    if caminho_da_url(page.url) != esperado:
        raise Falha(f"{rotulo}: rota {esperado} não existe (URL final {page.url}; o curinga redirecionou)")


def preencher(page, seletor, valor, rotulo):
    try:
        page.locator(seletor).first.fill(valor, timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campo {seletor} não encontrado na tela")


def enviar(page, rotulo):
    try:
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: botão button[type=submit] não encontrado")


def esperar_alerta(page, classe, rotulo):
    try:
        page.locator(f".alert-{classe}").first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: mensagem .alert-{classe} não ficou visível")
    return page.locator(f".alert-{classe}").first.inner_text().strip()


def alerta_visivel(page, classe):
    loc = page.locator(f".alert-{classe}")
    return loc.count() > 0 and any(loc.nth(i).is_visible() for i in range(loc.count()))


def erro_400_esperado(respostas_pendentes, codigo):
    """Consome a primeira resposta HTTP pendente com o código do erro de console.

    Devolve True só se essa resposta for um 400 da lista ROTAS_400_ESPERADO na tela certa.
    """
    for i, (status, metodo, caminho, tela) in enumerate(respostas_pendentes):
        if status == codigo:
            del respostas_pendentes[i]
            return (metodo, caminho, tela) in ROTAS_400_ESPERADO
    return False


def login_na_tela(page, email, senha, rotulo):
    exigir_rota(page, "/", rotulo)
    preencher(page, "input[name=email]", email, rotulo)
    preencher(page, "input[name=password]", senha, rotulo)
    enviar(page, rotulo)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def test_e2_conta_aluno_angular_e2e(browser):
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    atual = {"rotulo": "", "page": None}

    def nova_pagina(rotulo):
        atual["rotulo"] = rotulo
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()
        atual["page"] = page
        # respostas HTTP >= 400 ainda não associadas a um erro de console: (status, método, caminho, tela)
        respostas_erro = []

        def ao_resposta(resposta):
            if resposta.status >= 400:
                respostas_erro.append((
                    resposta.status, resposta.request.method,
                    caminho_da_url(resposta.url), caminho_da_url(page.url),
                ))

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is not None and m.group(1) == "400" and erro_400_esperado(respostas_erro, 400):
                return
            erros_console.append(f"{rotulo}: {msg.text}")

        page.on("response", ao_resposta)
        page.on("console", ao_console)
        page.on("pageerror", lambda e: erros_console.append(f"{rotulo}: {e}"))
        return page

    def captura_de_falha(codigo):
        page = atual["page"]
        if page is None:
            return
        try:
            page.screenshot(path=str(OUT / f"{codigo}_falha.png"), full_page=True)
        except Exception:
            pass

    def cenario(codigo, nome, fn):
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
        finally:
            atual["page"] = None

    # --- C1 -------------------------------------------------------------------------
    def c1():
        email = novo_email("cadastro")
        page = nova_pagina("C1")
        exigir_rota(page, "/cadastro", "C1 cadastro")
        preencher(page, "input[name=name]", "Aluno E2E Cadastro", "C1 cadastro")
        preencher(page, "input[name=email]", email, "C1 cadastro")
        preencher(page, "input[name=password]", SENHA_NOVA, "C1 cadastro")
        enviar(page, "C1 cadastro")
        esperar_alerta(page, "success", "C1 cadastro")
        conta = conta_no_banco(email)
        if conta is None or conta.get("role") != "student":
            raise Falha("C1 cadastro: conta de aluno não foi criada no banco")
        login_na_tela(page, email, SENHA_NOVA, "C1 login")
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"C1 login: após entrar com as credenciais, a URL é {page.url} (esperado /student)")

    cenario("C1", "cadastro com sucesso e login em / com as mesmas credenciais", c1)

    # --- C2 -------------------------------------------------------------------------
    def c2():
        email = novo_email("curta")
        page = nova_pagina("C2")
        exigir_rota(page, "/cadastro", "C2 senha curta")
        page.evaluate("window.__marcador_e2e = 1")
        preencher(page, "input[name=name]", "Aluno E2E Curta", "C2 senha curta")
        preencher(page, "input[name=email]", email, "C2 senha curta")
        preencher(page, "input[name=password]", SENHA_CURTA, "C2 senha curta")
        enviar(page, "C2 senha curta")
        esperar_alerta(page, "danger", "C2 senha curta")
        if page.evaluate("window.__marcador_e2e") != 1:
            raise Falha("C2 senha curta: a página recarregou após o envio")
        if conta_no_banco(email) is not None:
            raise Falha("C2 senha curta: conta foi criada mesmo com senha de 6 caracteres")

    cenario("C2", "cadastro com senha curta mostra erro, sem recarregar e sem criar conta", c2)

    # --- C3 -------------------------------------------------------------------------
    def c3():
        if conta_no_banco(ADMIN_EMAIL) is None:
            raise Falha("C3 e-mail existente: pré-requisito ausente, conta admin@gt.com não existe no banco")
        page = nova_pagina("C3")
        exigir_rota(page, "/cadastro", "C3 e-mail existente")
        preencher(page, "input[name=name]", "Outra Pessoa", "C3 e-mail existente")
        preencher(page, "input[name=email]", ADMIN_EMAIL, "C3 e-mail existente")
        preencher(page, "input[name=password]", SENHA_NOVA, "C3 e-mail existente")
        enviar(page, "C3 e-mail existente")
        esperar_alerta(page, "danger", "C3 e-mail existente")
        corpo = page.inner_text("body").lower()
        if ADMIN_EMAIL in corpo:
            raise Falha("C3 e-mail existente: o e-mail cadastrado aparece na tela (revela a conta)")
        if "já cadastrado" in corpo or "ja cadastrado" in corpo:
            raise Falha("C3 e-mail existente: a tela diz 'já cadastrado' (revela a conta)")
        status_antiga, _ = login_api(ADMIN_EMAIL, ADMIN_PASSWORD)
        status_nova, _ = login_api(ADMIN_EMAIL, SENHA_NOVA)
        if status_antiga != 200 or status_nova == 200:
            raise Falha("C3 e-mail existente: a senha da conta existente foi alterada pelo cadastro")

    cenario("C3", "cadastro com e-mail existente mostra erro genérico, sem revelar a conta", c3)

    # --- C4 -------------------------------------------------------------------------
    def c4():
        email, token = semear_token_definicao("definir")
        page = nova_pagina("C4")
        exigir_rota(page, f"/definir-senha?token={token}", "C4 definir senha")
        preencher(page, "input[name=password]", SENHA_NOVA, "C4 definir senha")
        enviar(page, "C4 definir senha")
        esperar_alerta(page, "success", "C4 definir senha")
        status, corpo = login_api(email, SENHA_NOVA)
        if status != 200 or not (corpo or {}).get("access_token"):
            raise Falha(f"C4 definir senha: login com e-mail e nova senha falhou (HTTP {status})")

    cenario("C4", "definir senha pelo token válido e login com a nova senha", c4)

    # --- C5 -------------------------------------------------------------------------
    def c5():
        _, token = semear_token_definicao("reuso")
        primeiro = nova_pagina("C5")
        exigir_rota(primeiro, f"/definir-senha?token={token}", "C5 token usado")
        preencher(primeiro, "input[name=password]", SENHA_NOVA, "C5 token usado")
        enviar(primeiro, "C5 token usado")
        esperar_alerta(primeiro, "success", "C5 token usado (primeiro uso)")
        atual["page"] = None
        segundo = nova_pagina("C5")
        exigir_rota(segundo, f"/definir-senha?token={token}", "C5 token usado")
        preencher(segundo, "input[name=password]", "outra-senha-forte-1", "C5 token usado")
        enviar(segundo, "C5 token usado")
        esperar_alerta(segundo, "danger", "C5 token usado (reuso)")
        if alerta_visivel(segundo, "success"):
            raise Falha("C5 token usado: token já usado aceitou nova senha")

    cenario("C5", "token de uso único: reabrir e enviar mostra erro genérico", c5)

    # --- C6 -------------------------------------------------------------------------
    def c6():
        page = nova_pagina("C6")
        exigir_rota(page, "/definir-senha?token=xyz", "C6 token inválido")
        preencher(page, "input[name=password]", SENHA_NOVA, "C6 token inválido")
        enviar(page, "C6 token inválido")
        esperar_alerta(page, "danger", "C6 token inválido")
        if alerta_visivel(page, "success"):
            raise Falha("C6 token inválido: a tela mostrou sucesso para token inválido")

    cenario("C6", "token inválido mostra erro genérico e não aceita a senha", c6)

    # --- C7 -------------------------------------------------------------------------
    def c7():
        sem_senha, _ = semear_aluno_sem_senha("sem-senha")
        page = nova_pagina("C7")
        login_na_tela(page, sem_senha, SENHA_NOVA, "C7 conta sem senha")
        esperar_alerta(page, "danger", "C7 conta sem senha")
        if caminho_da_url(page.url) != "":
            raise Falha(f"C7 conta sem senha: login sem senha levou a {page.url}")
        atual["page"] = None

        com_senha = semear_aluno_com_senha("com-senha", SENHA_NOVA)
        page = nova_pagina("C7")
        login_na_tela(page, com_senha, SENHA_NOVA, "C7 conta com senha")
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"C7 conta com senha: URL final {page.url} (esperado /student)")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(OUT / "C7_student.png"), full_page=True)

    cenario("C7", "login existente: conta sem senha é recusada; conta com senha chega a /student", c7)

    # --- C8 -------------------------------------------------------------------------
    try:
        if erros_console:
            resultados.append(("C8", "sem erros de console nas telas acima", False,
                               " | ".join(erros_console[:5])))
            print(f"[FAIL] C8 sem erros de console nas telas acima -> {len(erros_console)} erro(s)")
        else:
            resultados.append(("C8", "sem erros de console nas telas acima", True, ""))
            print("[OK]   C8 sem erros de console nas telas acima")
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
