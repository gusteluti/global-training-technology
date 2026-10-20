"""E2E da F7 - criar curso a partir de anexo (JSON e PDF), Chromium via Playwright. Contrato na D78.

Teste VERMELHO: a tela "Cadastro de cursos" (L2, D56) ainda não tem o controle `curso-anexo-input` e o backend não
tem POST /api/admin/course-draft.

Contrato de tela (D78), aba "Cadastro de cursos" de /admin (só Gestão), data-testid:
  curso-anexo-input   controle de arquivo (<input type=file>); escolher o arquivo envia para /api/admin/course-draft
  curso-anexo-avisos  avisos do rascunho (`warnings`), texto exato de cada aviso
  curso-anexo-erro    erro do envio (`detail` da API, texto exato)
  O rascunho abre o formulário de NOVO curso (L2: curso-id editável) preenchido; salvar usa a criação existente
  (POST /api/admin/create-course), com "Curso salvo." em curso-success.

Escolhas conservadoras (ver relatório do agente-testes): o envio acontece ao escolher o arquivo (a D78 só nomeia o
controle de arquivo; nenhum botão extra é exigido); o formulário é lido pelos testids da L2 (texto "Título | URL | tipo"
nos materiais, um item por linha nas listas, "Pergunta | Resposta" no FAQ); com rascunho sem avisos, curso-anexo-avisos
pode não existir, estar oculto ou vazio; o teste não exige que o erro some num envio seguinte nem que o formulário
seja limpo por um erro.

Checks:
  S1 pré-condição (anterior à F7): gestor loga, /admin, aba "Cadastro de cursos" com curso-form e o curso do seed
  I1 o gestor vê o controle curso-anexo-input (input de arquivo) na aba
  J1 JSON completo: o formulário de novo curso fica igual ao arquivo (curso-id editável); nada é criado ainda
     (sem POST create-course, lista e diretório de cursos iguais); sem curso-anexo-erro e sem avisos
  J2 salvar o rascunho do JSON: "Curso salvo.", curso-row novo e a API com exatamente os campos do arquivo
  W1 JSON com campos faltando: curso-anexo-avisos mostra 'Campo "<campo>" não encontrado no arquivo.' de cada
     obrigatório ausente; os campos presentes vêm preenchidos
  X1 arquivo inválido (texto puro com extensão .pdf): curso-anexo-erro mostra o texto exato do 415; nada é criado
  P1 PDF: formulário preenchido com o rascunho do LLM falso (nome, id sugerido, preço, duração), instruções do
     assistente vazias, sem materiais, aviso "Escreva as instruções do assistente do curso." em curso-anexo-avisos;
     o system_prompt e a URL que o LLM devolveu não aparecem na tela; nada é criado ainda
  P2 completar as instruções e salvar o rascunho do PDF cria o curso (não arquivado, sem os materiais do LLM)
  R1 Suporte e Financeiro: sem curso-anexo-input em nenhuma aba; a API responde 403 ao envio deles
  K1 sem erros de console/exceção/diálogo; o único erro HTTP provocado é o 415 de X1
  Z1 isolamento: backend/courses intacto; os cursos criados só no diretório temporário

Harness (D58): sobe `servidor_e2e_f7.py` (backend do E8 com LLM falso que devolve o JSON do curso para o PDF) e
`ng serve` em portas livres; nada fica rodando. Exige a dependência `pypdf` instalada no Python do backend (F7).
Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f7_curso_anexo_angular.py -s
"""

import json
import os
import shutil
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
TESTES_BACKEND = E2E_DIR.parent.parent / "backend" / "tests"
if str(TESTES_BACKEND) not in sys.path:
    sys.path.insert(0, str(TESTES_BACKEND))

from apoio_pdf import pdf_com_texto  # noqa: E402
from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402
from servidor_e2e_e8 import FINANCEIRO_EMAIL, FINANCEIRO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA  # noqa: E402
from servidor_e2e_f7 import ID_PDF, MARCA_PDF, NOME_PDF, PROMPT_DO_LLM, RESPOSTA_LLM, URL_DO_LLM  # noqa: E402
from test_e5_chat_aluno_angular import (  # noqa: E402
    ERRO_HTTP, Falha, FRONTEND, REPO, TIMEOUT, _api, _encerrar, _esperar_http, _iniciar, _porta_livre,
    login_na_tela,
)
from test_e8_auditoria_angular import abas_visiveis, imprimir, norm, snapshot_de_cursos, token_de_funcionario  # noqa: E402
from test_l1_turmas_angular import aguardar_visivel, clicar_aba, esperar  # noqa: E402
from test_l2_cadastro_cursos_angular import (  # noqa: E402
    ABA_CADASTRO, MSG_SALVO, SEL, SEL_ERRO, SEL_FORM, SEL_ROW, SEL_SALVAR, SEL_SUCESSO, comparar_form_com_api,
    esperar_texto, linhas, preencher, sem_datas, texto_visivel, valor_do_campo,
)

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_f7_curso_anexo"))

SEL_ANEXO = '[data-testid="curso-anexo-input"]'
SEL_AVISOS = '[data-testid="curso-anexo-avisos"]'
SEL_ANEXO_ERRO = '[data-testid="curso-anexo-erro"]'

MSG_415 = "Formato não suportado. Envie um arquivo JSON ou PDF."
AVISO_PROMPT = "Escreva as instruções do assistente do curso."
ROTA_RASCUNHO = "/api/admin/course-draft"


def aviso_ausente(campo):
    return f'Campo "{campo}" não encontrado no arquivo.'


SEED = {
    "id": "curso_f7_seed", "name": "Curso F7 Seed", "description": "Curso que já existia", "price": 100,
    "duration_hours": 10, "level": "Iniciante", "target_audience": "Todos", "objectives": ["Objetivo"],
    "topics": ["Tópico"], "benefits": ["Benefício"], "faq": [{"question": "Pergunta?", "answer": "Resposta."}],
    "system_prompt": "Você é o assistente do Curso F7 Seed.", "materials": [],
}

ANEXO_JSON = {
    "id": "excel_f7_anexo", "name": "Excel F7 Anexo", "description": "Planilhas do básico ao avançado",
    "price": 349.9, "duration_hours": 24, "level": "Avançado", "target_audience": "Analistas",
    "objectives": ["Dominar tabelas dinâmicas", "Automatizar relatórios"], "topics": ["PROCX", "Power Query"],
    "benefits": ["Certificado"], "faq": [{"question": "Tem certificado?", "answer": "Sim."}],
    "system_prompt": "Você é o assistente do curso Excel F7 Anexo.",
    "materials": [{"title": "Apostila", "url": "https://materiais.test/f7/apostila.pdf", "type": "pdf"}],
}
ANEXO_INCOMPLETO = {"name": "Curso F7 Incompleto", "description": "Só nome e descrição", "campo_estranho": 1}
FALTANTES = ["id", "price", "duration_hours", "level", "target_audience", "objectives", "topics", "benefits", "faq",
             "system_prompt"]

LINHAS_PDF = [f"{NOME_PDF} - ementa", "Carga horária: 40 horas.", f"Código {MARCA_PDF}"]
PROMPT_DIGITADO = "Você é o assistente do curso de Gestão Ágil."


# ---------------------------------------------------------------------------------------------
# Servidores e navegador
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_f7_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_FRONT_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://localhost:{porta_web}"
    log_web = tmp / "ng_serve.log"
    log_api = tmp / "backend.log"
    proxy = tmp / "proxy.e2e.json"
    proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}), encoding="utf-8")
    cursos_tmp = tmp / "courses"
    llm_log = tmp / "llm.jsonl"
    cursos_antes = snapshot_de_cursos()
    processos, arquivos = [], []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_f7.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--courses-dir", str(cursos_tmp), "--log-llm", str(llm_log)],
            arq_api, REPO / "backend",
        )
        processos.append(backend)
        _esperar_http(api + "/health", 90, backend, "backend de teste", log_api)

        arq_web = open(log_web, "wb")
        arquivos.append(arq_web)
        env_web = dict(os.environ, NG_CLI_ANALYTICS="false", NO_COLOR="1")
        comando_ng = f'npx ng serve --port {porta_web} --proxy-config "{proxy}"'
        front = _iniciar(comando_ng, arq_web, FRONTEND, env=env_web, shell=True)
        processos.append(front)
        _esperar_http(base + "/", int(os.environ.get("E2E_NG_TIMEOUT", "300")), front, "ng serve", log_web)

        yield {"base": base, "api": api, "cursos_tmp": cursos_tmp, "cursos_antes": cursos_antes, "llm_log": llm_log}
    finally:
        for processo in reversed(processos):
            _encerrar(processo)
        for arquivo in arquivos:
            try:
                arquivo.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


# ---------------------------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------------------------

def ids_da_api(api, token):
    status, corpo = _api(api, "GET", "/api/admin/courses", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/courses respondeu HTTP {status}")
    return sorted(c["id"] for c in corpo["courses"])


def curso_da_api(api, token, curso_id):
    status, corpo = _api(api, "GET", f"/api/admin/course/{curso_id}", token=token)
    if status == 404:
        return None
    if status != 200:
        raise RuntimeError(f"GET /api/admin/course/{curso_id} respondeu HTTP {status}")
    return corpo["course"]


def enviar_multipart(api, token, nome, conteudo):
    """POST multipart (campo `file`) direto na API; devolve o status HTTP."""
    fronteira = uuid.uuid4().hex
    corpo = (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n").encode() + conteudo + f"\r\n--{fronteira}--\r\n".encode()
    req = urllib.request.Request(api + ROTA_RASCUNHO, data=corpo, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={fronteira}", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code


def arquivos_de_curso(pasta):
    return sorted(p.name for p in pasta.glob("*.json")) if pasta.exists() else []


def test_f7_curso_anexo_angular_e2e(servidores, browser):
    base, api = servidores["base"], servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados, erros_inesperados, provocados, dialogos, contextos = [], [], [], [], []
    escritas = []   # POST/PUT/DELETE em /api/admin/ (exceto o rascunho)
    estado = {"page": None}
    paginas = {}
    PERMITIDOS = {("POST", ROTA_RASCUNHO, 415)}

    seed = {"ok": False, "erro": ""}
    dados = {}
    try:
        dados["token_g"] = token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        dados["token_sup"] = token_de_funcionario(api, SUPORTE_EMAIL, SUPORTE_SENHA)
        dados["token_fin"] = token_de_funcionario(api, FINANCEIRO_EMAIL, FINANCEIRO_SENHA)
        status, _ = _api(api, "POST", "/api/admin/create-course", SEED, token=dados["token_g"])
        if status != 200:
            raise RuntimeError(f"seed: create-course respondeu HTTP {status}")
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina(rotulo):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()
        estado["page"] = page

        def ao_console(msg):
            if msg.type != "error":
                return
            m = ERRO_HTTP.search(msg.text)
            if m is None:
                return
            url = msg.location.get("url") or ""
            if urllib.parse.urlparse(url).path == ROTA_RASCUNHO:
                return  # conferido em K1 pela resposta
            codigo = int(m.group(1))
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_inesperados.append(f"{rotulo}: console: {msg.text} [{url}]")

        def ao_response(resposta):
            if "/api/" not in resposta.url:
                return
            codigo, metodo = resposta.status, resposta.request.method
            caminho = urllib.parse.urlparse(resposta.url).path
            if (metodo, caminho, codigo) in PERMITIDOS:
                provocados.append((rotulo, metodo, caminho, codigo))
            elif codigo in (400, 404, 413, 415, 422) or codigo >= 500 or \
                    (codigo in (401, 403) and caminho.startswith("/api/admin/course")):
                erros_inesperados.append(f"{rotulo}: {metodo} {caminho} respondeu HTTP {codigo}")

        def ao_request(requisicao):
            caminho = urllib.parse.urlparse(requisicao.url).path
            if requisicao.method in ("POST", "PUT", "DELETE", "PATCH") and caminho.startswith("/api/admin/") \
                    and caminho != ROTA_RASCUNHO:
                try:
                    corpo = json.loads(requisicao.post_data) if requisicao.post_data else None
                except ValueError:
                    corpo = None
                escritas.append({"metodo": requisicao.method, "caminho": caminho, "corpo": corpo})

        def ao_dialogo(dialogo):
            dialogos.append(dialogo.message)
            dialogo.dismiss()

        page.on("console", ao_console)
        page.on("response", ao_response)
        page.on("request", ao_request)
        page.on("dialog", ao_dialogo)
        page.on("pageerror", lambda e: erros_inesperados.append(f"{rotulo}: exceção de página: {e}"))
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
            imprimir(f"[FAIL] {codigo} {nome} -> seed falhou: {seed['erro']}")
            return
        try:
            fn()
            resultados.append((codigo, nome, True, ""))
            imprimir(f"[OK]   {codigo} {nome}")
        except Falha as erro:
            captura_de_falha(codigo)
            resultados.append((codigo, nome, False, str(erro)))
            imprimir(f"[FAIL] {codigo} {nome} -> {erro}")
        except Exception as erro:
            captura_de_falha(codigo)
            linha = str(erro).splitlines()[0] if str(erro) else ""
            resultados.append((codigo, nome, False, f"{type(erro).__name__}: {linha}"))
            imprimir(f"[FAIL] {codigo} {nome} -> {type(erro).__name__}: {linha}")

    def tela_gestor():
        page = paginas.get("gestor")
        if page is None:
            raise Falha("pré-requisito: a tela do gestor não ficou pronta (S1 falhou)")
        estado["page"] = page
        return page

    def abrir_cadastro(rotulo):
        """Recarrega /admin, abre a aba "Cadastro de cursos" e espera o formulário e a lista."""
        page = tela_gestor()
        page.reload(wait_until="networkidle")
        clicar_aba(page, ABA_CADASTRO, rotulo)
        aguardar_visivel(page.locator(SEL_FORM), rotulo, f"formulário {SEL_FORM}")
        aguardar_visivel(page.locator(f'{SEL_ROW}[data-course-id="{SEED["id"]}"]'), rotulo, "curso-row do seed")
        return page

    def anexar(page, nome, tipo, conteudo, rotulo):
        """Escolhe o arquivo no curso-anexo-input e espera a resposta do POST /api/admin/course-draft."""
        controle = page.locator(SEL_ANEXO)
        if controle.count() == 0:
            raise Falha(f"{rotulo}: controle {SEL_ANEXO} não existe na aba Cadastro de cursos")
        try:
            with page.expect_response(lambda r: urllib.parse.urlparse(r.url).path == ROTA_RASCUNHO
                                      and r.request.method == "POST", timeout=TIMEOUT * 3) as info:
                controle.first.set_input_files(files=[{"name": nome, "mimeType": tipo, "buffer": conteudo}],
                                               timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: escolher o arquivo em {SEL_ANEXO} não chamou POST {ROTA_RASCUNHO}")
        page.wait_for_load_state("networkidle")
        return info.value

    def texto_dos_avisos(page):
        return texto_visivel(page, SEL_AVISOS) or ""

    def exigir_avisos(page, esperados, rotulo):
        def leitura():
            texto = texto_dos_avisos(page)
            faltando = [a for a in esperados if a not in texto]
            return None if not faltando else f"{SEL_AVISOS} mostra {texto!r}; faltam {faltando}"
        esperar(leitura, rotulo)

    def exigir_nada_criado(antes_ids, antes_arquivos, marca_escritas, rotulo):
        novas = [e for e in escritas[marca_escritas:] if e["caminho"] == "/api/admin/create-course"]
        if novas:
            raise Falha(f"{rotulo}: o anexo disparou POST /api/admin/create-course antes de salvar")
        if ids_da_api(api, dados["token_g"]) != antes_ids:
            raise Falha(f"{rotulo}: a lista de cursos da API mudou só com o anexo: {ids_da_api(api, dados['token_g'])}")
        if arquivos_de_curso(servidores["cursos_tmp"]) != antes_arquivos:
            raise Falha(f"{rotulo}: o diretório de cursos mudou só com o anexo")

    def exigir_id_editavel(page, rotulo):
        campo = page.locator(SEL["id"]).first
        if campo.get_attribute("readonly") is not None or campo.is_disabled():
            raise Falha(f"{rotulo}: curso-id está somente leitura (esperado formulário de NOVO curso)")

    # --- S1 ---------------------------------------------------------------------------
    def s1():
        page = nova_pagina("gestor")
        paginas["gestor"] = page
        login_na_tela(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "S1")
        try:
            page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"S1: URL final {page.url} (esperado /admin)")
        page.wait_for_load_state("networkidle")
        abrir_cadastro("S1")

    cenario("S1", "pré-condição: gestor na aba Cadastro de cursos com o formulário e o curso do seed", s1)

    # --- I1 ---------------------------------------------------------------------------
    def i1():
        page = abrir_cadastro("I1")
        controle = page.locator(SEL_ANEXO)
        if controle.count() != 1:
            raise Falha(f"I1: {controle.count()} elementos {SEL_ANEXO} na aba (esperado 1)")
        tag = controle.first.evaluate("e => e.tagName + ':' + (e.getAttribute('type') || '')")
        if tag.upper() != "INPUT:FILE":
            raise Falha(f"I1: {SEL_ANEXO} é {tag!r} (esperado <input type=file>)")

    cenario("I1", "o gestor vê o controle curso-anexo-input (input de arquivo)", i1)

    # --- J1 ---------------------------------------------------------------------------
    def j1():
        page = abrir_cadastro("J1")
        antes_ids, antes_arq, marca = ids_da_api(api, dados["token_g"]), arquivos_de_curso(servidores["cursos_tmp"]), len(escritas)
        resposta = anexar(page, "excel.json", "application/json",
                          json.dumps(ANEXO_JSON, ensure_ascii=False).encode("utf-8"), "J1")
        if resposta.status != 200:
            raise Falha(f"J1: POST {ROTA_RASCUNHO} respondeu HTTP {resposta.status}")
        esperar(lambda: comparar_form_com_api(page, ANEXO_JSON, "J1"), "J1")
        exigir_id_editavel(page, "J1")
        if texto_visivel(page, SEL_ANEXO_ERRO):
            raise Falha(f"J1: {SEL_ANEXO_ERRO} visível: {texto_visivel(page, SEL_ANEXO_ERRO)!r}")
        if texto_dos_avisos(page).strip():
            raise Falha(f"J1: arquivo completo mostrou avisos: {texto_dos_avisos(page)!r}")
        exigir_nada_criado(antes_ids, antes_arq, marca, "J1")

    cenario("J1", "JSON completo preenche o formulário de novo curso, sem criar nada", j1)

    # --- J2 ---------------------------------------------------------------------------
    def j2():
        page = tela_gestor()
        if valor_do_campo(page, "id", "J2").strip() != ANEXO_JSON["id"]:
            raise Falha("J2: o formulário não está com o rascunho do J1")
        page.locator(SEL_SALVAR).first.click(timeout=TIMEOUT)
        esperar_texto(page, SEL_SUCESSO, MSG_SALVO, "J2")
        aguardar_visivel(page.locator(f'{SEL_ROW}[data-course-id="{ANEXO_JSON["id"]}"]'), "J2", "curso-row do curso novo")
        curso = curso_da_api(api, dados["token_g"], ANEXO_JSON["id"])
        if curso is None:
            raise Falha("J2: o curso não existe na API depois de salvar")
        obtido = {k: v for k, v in sem_datas(curso).items() if k != "archived"}
        if obtido != ANEXO_JSON:
            raise Falha(f"J2: curso na API {obtido} difere do arquivo {ANEXO_JSON}")
        if curso.get("archived", False) is not False:
            raise Falha("J2: o curso criado a partir do anexo ficou arquivado")

    cenario("J2", "salvar o rascunho do JSON cria o curso pela criação existente", j2)

    # --- W1 ---------------------------------------------------------------------------
    def w1():
        page = abrir_cadastro("W1")
        resposta = anexar(page, "incompleto.json", "application/json",
                          json.dumps(ANEXO_INCOMPLETO, ensure_ascii=False).encode("utf-8"), "W1")
        if resposta.status != 200:
            raise Falha(f"W1: POST {ROTA_RASCUNHO} respondeu HTTP {resposta.status}")
        exigir_avisos(page, [aviso_ausente(c) for c in FALTANTES], "W1")
        esperar(lambda: None if valor_do_campo(page, "name", "W1").strip() == ANEXO_INCOMPLETO["name"]
                else f"curso-name mostra {valor_do_campo(page, 'name', 'W1')!r}", "W1")
        if valor_do_campo(page, "description", "W1").strip() != ANEXO_INCOMPLETO["description"]:
            raise Falha(f"W1: curso-description mostra {valor_do_campo(page, 'description', 'W1')!r}")
        if "campo_estranho" in norm(page.locator("body").inner_text()):
            raise Falha("W1: o campo desconhecido do arquivo apareceu na tela")

    cenario("W1", "JSON com campos faltando mostra os avisos exatos em curso-anexo-avisos", w1)

    # --- X1 ---------------------------------------------------------------------------
    def x1():
        page = abrir_cadastro("X1")
        antes_ids, antes_arq, marca = ids_da_api(api, dados["token_g"]), arquivos_de_curso(servidores["cursos_tmp"]), len(escritas)
        resposta = anexar(page, "notas.pdf", "application/pdf", "Isto é só texto, não é PDF.".encode("utf-8"), "X1")
        if resposta.status != 415:
            raise Falha(f"X1: POST {ROTA_RASCUNHO} respondeu HTTP {resposta.status} (esperado 415)")
        esperar_texto(page, SEL_ANEXO_ERRO, MSG_415, "X1")
        exigir_nada_criado(antes_ids, antes_arq, marca, "X1")

    cenario("X1", "arquivo inválido mostra o texto exato do 415 em curso-anexo-erro", x1)

    # --- P1 ---------------------------------------------------------------------------
    def p1():
        page = abrir_cadastro("P1")
        antes_ids, antes_arq, marca = ids_da_api(api, dados["token_g"]), arquivos_de_curso(servidores["cursos_tmp"]), len(escritas)
        resposta = anexar(page, "ementa.pdf", "application/pdf", pdf_com_texto(LINHAS_PDF), "P1")
        if resposta.status != 200:
            raise Falha(f"P1: POST {ROTA_RASCUNHO} respondeu HTTP {resposta.status}")
        esperar(lambda: None if valor_do_campo(page, "name", "P1").strip() == NOME_PDF
                else f"curso-name mostra {valor_do_campo(page, 'name', 'P1')!r}", "P1")
        if valor_do_campo(page, "id", "P1").strip() != ID_PDF:
            raise Falha(f"P1: curso-id mostra {valor_do_campo(page, 'id', 'P1')!r} (esperado {ID_PDF!r})")
        exigir_id_editavel(page, "P1")
        for campo, chave in (("description", "description"), ("level", "level"), ("audience", "target_audience")):
            if valor_do_campo(page, campo, "P1").strip() != RESPOSTA_LLM[chave]:
                raise Falha(f"P1: curso-{campo} mostra {valor_do_campo(page, campo, 'P1')!r}")
        try:
            if float(valor_do_campo(page, "price", "P1")) != float(RESPOSTA_LLM["price"]):
                raise Falha(f"P1: curso-price mostra {valor_do_campo(page, 'price', 'P1')!r}")
            if int(float(valor_do_campo(page, "hours", "P1"))) != RESPOSTA_LLM["duration_hours"]:
                raise Falha(f"P1: curso-hours mostra {valor_do_campo(page, 'hours', 'P1')!r}")
        except ValueError:
            raise Falha("P1: preço/duração não numéricos no formulário")
        if linhas(valor_do_campo(page, "topics", "P1")) != RESPOSTA_LLM["topics"]:
            raise Falha(f"P1: curso-topics mostra {valor_do_campo(page, 'topics', 'P1')!r}")
        if valor_do_campo(page, "prompt", "P1").strip() != "":
            raise Falha(f"P1: curso-prompt veio preenchido do PDF: {valor_do_campo(page, 'prompt', 'P1')!r}")
        if valor_do_campo(page, "materials", "P1").strip() != "":
            raise Falha(f"P1: curso-materials veio preenchido do PDF: {valor_do_campo(page, 'materials', 'P1')!r}")
        exigir_avisos(page, [AVISO_PROMPT], "P1")
        corpo = page.content()
        for proibido in (PROMPT_DO_LLM, URL_DO_LLM):
            if proibido in corpo:
                raise Falha(f"P1: {proibido!r} (vindo do LLM) apareceu na página")
        exigir_nada_criado(antes_ids, antes_arq, marca, "P1")

    cenario("P1", "PDF gera rascunho preenchido, sem instruções nem materiais, com o aviso do system_prompt", p1)

    # --- P2 ---------------------------------------------------------------------------
    def p2():
        page = tela_gestor()
        if valor_do_campo(page, "id", "P2").strip() != ID_PDF:
            raise Falha("P2: o formulário não está com o rascunho do P1")
        preencher(page, "prompt", PROMPT_DIGITADO, "P2")
        page.locator(SEL_SALVAR).first.click(timeout=TIMEOUT)
        esperar_texto(page, SEL_SUCESSO, MSG_SALVO, "P2")
        aguardar_visivel(page.locator(f'{SEL_ROW}[data-course-id="{ID_PDF}"]'), "P2", "curso-row do curso do PDF")
        curso = curso_da_api(api, dados["token_g"], ID_PDF)
        if curso is None:
            raise Falha("P2: o curso do PDF não existe na API depois de salvar")
        if curso["name"] != NOME_PDF or curso["system_prompt"] != PROMPT_DIGITADO:
            raise Falha(f"P2: curso na API {curso['name']!r} / {curso['system_prompt']!r}")
        if curso.get("materials") not in ([], None) or curso.get("archived", False) is not False:
            raise Falha(f"P2: materiais {curso.get('materials')} / archived {curso.get('archived')} vindos do LLM")

    cenario("P2", "completar as instruções e salvar o rascunho do PDF cria o curso", p2)

    # --- R1 ---------------------------------------------------------------------------
    def r1():
        for rotulo, email, senha, token in (("R1-suporte", SUPORTE_EMAIL, SUPORTE_SENHA, dados["token_sup"]),
                                            ("R1-financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA, dados["token_fin"])):
            page = nova_pagina(rotulo)
            login_na_tela(page, base, email, senha, rotulo)
            try:
                page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
            except sync_api.TimeoutError:
                raise Falha(f"{rotulo}: URL final {page.url} (esperado /admin)")
            page.wait_for_load_state("networkidle")
            for aba in abas_visiveis(page):
                page.locator("ul.nav-tabs button", has_text=aba).first.click(timeout=TIMEOUT)
                page.wait_for_load_state("networkidle")
                if page.locator(SEL_ANEXO).count():
                    raise Falha(f"{rotulo}: {SEL_ANEXO} presente na aba {aba!r}")
            status = enviar_multipart(api, token, "curso.json", json.dumps(ANEXO_JSON).encode("utf-8"))
            if status != 403:
                raise Falha(f"{rotulo}: POST {ROTA_RASCUNHO} respondeu HTTP {status} (esperado 403)")

    cenario("R1", "Suporte e Financeiro sem curso-anexo-input e com 403 na API", r1)

    # --- K1 ---------------------------------------------------------------------------
    def k1():
        if erros_inesperados:
            raise Falha(f"K1: {len(erros_inesperados)} erro(s) inesperado(s): " + " | ".join(erros_inesperados[:5]))
        if dialogos:
            raise Falha(f"K1: a tela abriu diálogos do navegador: {dialogos}")
        obtidos = sorted((m, c, k) for _, m, c, k in provocados)
        if obtidos != sorted(PERMITIDOS):
            raise Falha(f"K1: respostas de erro provocadas {obtidos}; esperado exatamente {sorted(PERMITIDOS)}")

    cenario("K1", "sem erros de console/exceção/diálogo; só o 415 provocado em X1", k1)

    # --- Z1 ---------------------------------------------------------------------------
    def z1():
        cursos_tmp = servidores["cursos_tmp"]
        for curso_id in (SEED["id"], ANEXO_JSON["id"], ID_PDF):
            if not (cursos_tmp / f"{curso_id}.json").exists():
                raise Falha(f"Z1: o curso {curso_id} não está em {cursos_tmp}")
            if (REPO / "backend" / "courses" / f"{curso_id}.json").exists():
                raise Falha(f"Z1: o curso {curso_id} apareceu em backend/courses")
        if snapshot_de_cursos() != servidores["cursos_antes"]:
            raise Falha("Z1: backend/courses mudou durante o teste")

    cenario("Z1", "isolamento: cursos só no diretório temporário; backend/courses intacto", z1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    imprimir(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
