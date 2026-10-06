"""E2E do cadastro de cursos no Angular e da higiene do interceptor (L2, Chromium via Playwright).
Decisão D56 (docs/tdd/decisoes_tdd.md). O backend de cursos já está pronto e inalterado; este arquivo é o teste
VERMELHO do frontend: a aba "Cadastro de cursos" (só Gestão) com o componente `course-admin`, e a regra do
interceptor (Authorization: Bearer só em /api/admin/, /api/dashboard/, /api/student/ e /api/payments/refund/).

Contrato de tela (D56), aba "Cadastro de cursos" de /admin, data-testid:
  lista:       curso-row (atributo data-course-id; mostra nome, preço e duração), curso-edit, curso-delete,
               curso-delete-confirm (confirmação na própria tela, sem window.confirm), curso-cancel-delete
  formulário:  curso-form, curso-id (somente leitura na edição), curso-name, curso-description, curso-price,
               curso-hours, curso-level, curso-audience, curso-objectives, curso-topics, curso-benefits (um item por
               linha), curso-faq (uma linha por item: "Pergunta | Resposta"), curso-prompt, curso-materials (uma linha
               por item: "Título | URL | tipo", tipo opcional, padrão link), curso-save, curso-cancel-edit,
               curso-error, curso-success
  textos:      "Curso salvo." / "Curso removido." / "Cada linha do FAQ deve ter o formato: Pergunta | Resposta." /
               "A URL do material deve começar com http:// ou https://." / erro da API = `detail` exato.

Escolhas de forma aceitas pelo teste (nenhuma define política): os campos de linha única podem ser <input>
ou <select> (o teste trata os dois); texto, preço e duração da curso-row podem ter palavras ao redor (o teste só
exige o nome, os dígitos do preço e os da duração); espaços em volta do "|" são aparados; o teste NÃO exige que
o formulário seja limpo depois de salvar nem que curso-cancel-edit exista no modo de criação.

Cenários (checks numerados):
  S1 pré-condição (anterior aos testids): login do gestor chega a /admin e a aba "Cursos" mostra os cursos do seed.
     Garante que o red é por falta da L2 na tela, não por servidor, login ou seed
  T1 o gestor vê a aba "Cadastro de cursos" (além das abas atuais)
  L1 a aba lista os cursos do diretório temporário em curso-row (data-course-id, nome, preço, duração)
  C1 cria o curso preenchendo todos os campos (listas por linha, FAQ e materiais com "|"): curso-row novo,
     curso-success "Curso salvo.", API com exatamente os campos esperados (faq [{question,answer}], materials
     [{title,url,type}], tipo link quando omitido) e uma única escrita (POST create-course)
  V1 campos vazios, preço 0 ou negativo e duração não inteira ou <= 0 mantêm curso-save desabilitado
  V2 FAQ sem "|" e URL de material javascript:/ftp:// mostram o texto exato em curso-error; nada é enviado
  D1 id duplicado mostra em curso-error o detail da API (texto exato) e não duplica nem altera o curso
  E1 curso-edit carrega o formulário (campos, FAQ e materiais em linhas, curso-id somente leitura)
  E2 alterar só o preço PRESERVA os materiais (corpo do PUT leva materials; API) e a trilha mostra
     course.price_change com changes só de price e o e-mail do gestor logado (aba Auditoria)
  E3 alterar os materiais substitui (tipo omitido vira link); a trilha tem course.update só de materials
  A1 aluno com matrícula ativa vê os materiais novos em /student; aluno pendente não vê nenhum (API e tela)
  E4 limpar o campo de materiais salva [] (propositalmente) e o aluno ativo passa a não ter material
  E5 curso-cancel-edit volta ao modo de criação (campos vazios, curso-id editável), sem escrita
  X1 curso-delete não remove; curso-cancel-delete mantém; só curso-delete-confirm remove ("Curso removido.",
     course.delete na trilha com o gestor logado, sem window.confirm)
  R1 suporte: sem a aba nem curso-form/curso-row em nenhuma aba; escritas de curso 403
  R2 financeiro: idem
  R3 sem token e com token forjado: 401 nas escritas de curso
  N1 interceptor, gestor logado (com token velho no navegador antes do login): /api/token sem Authorization;
     /api/admin/* e /api/dashboard/* com Bearer
  N2 interceptor, aluno logado: /api/student/* com Bearer
  N3 /cadastro com token no navegador: /api/auth/register sem Authorization
  N4 /definir-senha?token=x com token no navegador: /api/auth/password-setup sem Authorization (400 esperado)
  N5 regra geral: nenhuma chamada a /api/ fora dos quatro prefixos (inclui /api/courses, se alguma tela chamar)
     levou Authorization; as dos quatro prefixos levaram Bearer
  K1 sem erros de console (400, 404 em /api, 5xx) nem exceções de página, sem window.confirm; os ÚNICOS 400
     permitidos são os dois provocados (D1: POST /api/admin/create-course; N4: POST /api/auth/password-setup)
  Z1 isolamento: os cursos só foram gravados no diretório temporário; backend/courses não mudou

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e8.py (Groq e Mercado Pago falsos, banco SQLite temporário, diretório de
    cursos temporário, dois gestores, suporte e financeiro). backend/db.sqlite e backend/courses não são abertos.
  - Frontend: `npx ng serve` numa porta livre própria, com proxy temporário /api -> backend de teste.
  - Seed só pela API: dois cursos (o A com 2 materiais), um aluno com matrícula ativa e um com matrícula pendente
    no curso A (checkout falso + webhook assinado).

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas: E2E_BACKEND_PORT / E2E_FRONT_PORT para fixar.
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_l2_cadastro_cursos_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
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

from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402
from apoio_webhook_mp import enviar_webhook  # noqa: E402
from servidor_e2e_e8 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)
# Utilitários de harness e de seed já usados pelos e2e anteriores (somente leitura, não alterados).
from test_e5_chat_aluno_angular import (  # noqa: E402
    ERRO_HTTP, Falha, FRONTEND, REPO, SENHA, TIMEOUT, _api, _encerrar, _esperar_http, _iniciar,
    _porta_livre, semear_aluno,
)
from test_e8_auditoria_angular import (  # noqa: E402
    abas_visiveis, checar_alteracoes_da_linha, checar_responsavel, imprimir, linhas_da_tela, norm,
    snapshot_de_cursos, texto_do_responsavel, token_de_funcionario,
)
from test_l1_turmas_angular import aguardar_visivel, clicar_aba, esperar  # noqa: E402

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_cadastro_cursos"))

CURSO_A = "curso-l2-a"
CURSO_B = "curso-l2-b"
NOME_A = "Curso L2 A"
NOME_B = "Curso L2 B"
ID_NOVO = "curso-l2-novo"
NOME_NOVO = "Curso L2 Novo"

ABA_CURSOS = re.compile(r"^\s*Cursos\s*$")
ABA_CADASTRO = re.compile(r"^\s*Cadastro de cursos\s*$")
ABA_AUDITORIA = re.compile(r"^\s*Auditoria\s*$")
ABA_ALUNOS = re.compile(r"^\s*Alunos\s*$")
TEXTO_ABA = "Cadastro de cursos"

MSG_SALVO = "Curso salvo."
MSG_REMOVIDO = "Curso removido."
MSG_FAQ = "Cada linha do FAQ deve ter o formato: Pergunta | Resposta."
MSG_URL = "A URL do material deve começar com http:// ou https://."

CAMPOS = ["id", "name", "description", "price", "hours", "level", "audience", "objectives", "topics", "benefits",
          "faq", "prompt", "materials"]
OBRIGATORIOS = [c for c in CAMPOS if c != "materials"]
SEL = {c: f'[data-testid="curso-{c}"]' for c in CAMPOS}
SEL_ROW = '[data-testid="curso-row"]'
SEL_EDIT = '[data-testid="curso-edit"]'
SEL_DELETE = '[data-testid="curso-delete"]'
SEL_CONFIRMAR = '[data-testid="curso-delete-confirm"]'
SEL_CANCELAR_EXCLUSAO = '[data-testid="curso-cancel-delete"]'
SEL_FORM = '[data-testid="curso-form"]'
SEL_SALVAR = '[data-testid="curso-save"]'
SEL_CANCELAR_EDICAO = '[data-testid="curso-cancel-edit"]'
SEL_ERRO = '[data-testid="curso-error"]'
SEL_SUCESSO = '[data-testid="curso-success"]'
SEL_AUDIT_ROW = '[data-testid="audit-row"]'

PREFIXOS_COM_TOKEN = ("/api/admin/", "/api/dashboard/", "/api/student/", "/api/payments/refund/")
TOKEN_VELHO = "token-velho.de-outra-sessao.xyz"

# Curso do seed A (com dois materiais). Nenhum texto tem "|" nem espaços sobrando.
SEED_A = {
    "id": CURSO_A, "name": NOME_A, "description": "Descrição do curso L2 A", "price": 100,
    "duration_hours": 10, "level": "Iniciante", "target_audience": "Quem está começando",
    "objectives": ["Aprender o básico", "Praticar com exercícios"], "topics": ["Introdução", "Módulo prático"],
    "benefits": ["Certificado", "Acesso vitalício"],
    "faq": [{"question": "Tem certificado?", "answer": "Sim."}, {"question": "Quanto dura?", "answer": "Doze horas."}],
    "system_prompt": "Você é o assistente do Curso L2 A.",
    "materials": [{"title": "Apostila A", "url": "https://exemplo.com/apostila-a.pdf", "type": "pdf"},
                  {"title": "Vídeo A", "url": "https://exemplo.com/video-a", "type": "video"}],
}
SEED_B = {
    "id": CURSO_B, "name": NOME_B, "description": "Descrição do curso L2 B", "price": 200,
    "duration_hours": 20, "level": "Avançado", "target_audience": "Quem já domina o básico",
    "objectives": ["Objetivo B"], "topics": ["Tópico B"], "benefits": ["Benefício B"],
    "faq": [{"question": "Pergunta B?", "answer": "Resposta B."}], "system_prompt": "Você é o assistente do Curso L2 B.",
    "materials": [],
}

# Curso novo digitado pela tela (textos de formulário) e o que a API deve guardar.
NOVO = {
    "id": ID_NOVO, "name": NOME_NOVO, "description": "Descrição do curso novo", "price": "149.9", "hours": "12",
    "level": "Intermediário", "audience": "Analistas de dados", "objectives": "Objetivo um\nObjetivo dois",
    "topics": "Tópico A\nTópico B\nTópico C", "benefits": "Benefício X",
    "faq": "Como pago? | Pelo checkout.\nTem certificado? | Sim, ao final.",
    "prompt": "Você é o assistente do Curso L2 Novo.",
    "materials": "Apostila | https://exemplo.com/apostila.pdf | pdf\nSite oficial | https://exemplo.com/site",
}
ESPERADO_NOVO = {
    "id": ID_NOVO, "name": NOME_NOVO, "description": "Descrição do curso novo", "price": 149.9, "duration_hours": 12,
    "level": "Intermediário", "target_audience": "Analistas de dados",
    "objectives": ["Objetivo um", "Objetivo dois"], "topics": ["Tópico A", "Tópico B", "Tópico C"],
    "benefits": ["Benefício X"],
    "faq": [{"question": "Como pago?", "answer": "Pelo checkout."},
            {"question": "Tem certificado?", "answer": "Sim, ao final."}],
    "system_prompt": "Você é o assistente do Curso L2 Novo.",
    "materials": [{"title": "Apostila", "url": "https://exemplo.com/apostila.pdf", "type": "pdf"},
                  {"title": "Site oficial", "url": "https://exemplo.com/site", "type": "link"}],
}
MATERIAIS_NOVOS_TELA = "Material Novo | https://exemplo.com/novo.pdf | pdf\nOutro Material | https://exemplo.com/outro"
MATERIAIS_NOVOS_API = [{"title": "Material Novo", "url": "https://exemplo.com/novo.pdf", "type": "pdf"},
                       {"title": "Outro Material", "url": "https://exemplo.com/outro", "type": "link"}]


# ---------------------------------------------------------------------------------------------
# Servidores e navegador
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    """Sobe o backend de teste (cursos isolados, gestores) e o Angular; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_l2_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_FRONT_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://localhost:{porta_web}"
    log_web = tmp / "ng_serve.log"
    log_api = tmp / "backend.log"
    proxy = tmp / "proxy.e2e.json"
    proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}), encoding="utf-8")
    cursos_tmp = tmp / "courses"
    cursos_antes = snapshot_de_cursos()

    processos = []
    arquivos = []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_e8.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--courses-dir", str(cursos_tmp)],
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

        yield {"base": base, "api": api, "cursos_tmp": cursos_tmp, "cursos_antes": cursos_antes}
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
# Auxiliares de API
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


def sem_datas(curso):
    return {k: v for k, v in curso.items() if k not in ("created_at", "updated_at")}


def eventos_da_api(api, token):
    status, corpo = _api(api, "GET", "/api/admin/audit-logs", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/audit-logs respondeu HTTP {status}")
    return corpo["logs"]


def eventos_de_curso(api, token, acao, curso_id):
    return sorted((e for e in eventos_da_api(api, token)
                   if e["action"] == acao and str(e.get("entity_id")) == curso_id), key=lambda e: e["id"])


def detalhe_do_erro_da_api(api, token, metodo, caminho, corpo):
    """Status e `detail` (texto) de uma chamada que deve falhar; usado só para comparar com o texto da tela."""
    dados = json.dumps(corpo).encode()
    req = urllib.request.Request(api + caminho, data=dados, method=metodo, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resposta:
            return resposta.status, None
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read()).get("detail")
        except Exception:
            return erro.code, None


def corpo_da_api(c):
    """Corpo de escrita (CourseInput) de um curso lido da API."""
    return {k: c[k] for k in ("id", "name", "description", "price", "duration_hours", "level", "target_audience",
                              "objectives", "topics", "benefits", "faq", "system_prompt", "materials")}


# ---------------------------------------------------------------------------------------------
# Auxiliares de tela
# ---------------------------------------------------------------------------------------------

def clicar(page, seletor, rotulo, descricao=None):
    try:
        page.locator(seletor).first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: {descricao or seletor} não encontrado ou não clicável")


def preencher(page, campo, valor, rotulo):
    """Preenche curso-<campo> (input, textarea ou select)."""
    alvo = page.locator(SEL[campo]).first
    try:
        if alvo.evaluate("e => e.tagName", timeout=TIMEOUT) == "SELECT":
            alvo.select_option(label=valor, timeout=TIMEOUT)
        else:
            alvo.fill(valor, timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campo {SEL[campo]} não encontrado")


def preencher_tudo(page, dados, rotulo, sem=()):
    for campo in CAMPOS:
        if campo in dados and campo not in sem:
            preencher(page, campo, dados[campo], rotulo)


def valor_do_campo(page, campo, rotulo):
    try:
        return page.locator(SEL[campo]).first.input_value(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campo {SEL[campo]} não encontrado")


def n_visiveis(page, seletor):
    alvo = page.locator(seletor)
    return sum(1 for i in range(alvo.count()) if alvo.nth(i).is_visible())


def texto_visivel(page, seletor):
    alvo = page.locator(seletor)
    for i in range(alvo.count()):
        if alvo.nth(i).is_visible():
            return norm(alvo.nth(i).inner_text())
    return None


def esperar_texto(page, seletor, esperado, rotulo, limite=6.0):
    def leitura():
        atual = texto_visivel(page, seletor)
        if atual is None:
            return f"nenhum elemento visível {seletor} (esperado {esperado!r})"
        if atual != esperado:
            return f"{seletor} mostra {atual!r}, esperado exatamente {esperado!r}"
        return None
    esperar(leitura, rotulo, limite)


def salvar_desabilitado(page, rotulo):
    try:
        return page.locator(SEL_SALVAR).first.is_disabled(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: botão {SEL_SALVAR} não encontrado")


def linha_do_curso(page, curso_id):
    return page.locator(f'{SEL_ROW}[data-course-id="{curso_id}"]')


def esperar_lista(page, api, token, rotulo):
    """curso-row na tela == cursos da API (mesmos ids)."""
    def leitura():
        esperados = ids_da_api(api, token)
        na_tela = sorted(page.eval_on_selector_all(SEL_ROW, "els => els.map(e => e.getAttribute('data-course-id'))"))
        return None if na_tela == esperados else f"curso-row na tela {na_tela}, a API tem {esperados}"
    esperar(leitura, rotulo)


def linhas(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def partes(linha):
    return tuple(p.strip() for p in linha.split("|"))


def comparar_form_com_api(page, curso, rotulo):
    """None se o formulário mostra exatamente o curso da API; senão, o motivo."""
    lido = {c: valor_do_campo(page, c, rotulo) for c in CAMPOS}
    for campo, chave in (("id", "id"), ("name", "name"), ("description", "description"), ("level", "level"),
                         ("audience", "target_audience"), ("prompt", "system_prompt")):
        if lido[campo].strip() != curso[chave]:
            return f"curso-{campo} mostra {lido[campo]!r}, a API tem {curso[chave]!r}"
    try:
        if float(lido["price"]) != float(curso["price"]):
            return f"curso-price mostra {lido['price']!r}, a API tem {curso['price']!r}"
        if int(float(lido["hours"])) != curso["duration_hours"]:
            return f"curso-hours mostra {lido['hours']!r}, a API tem {curso['duration_hours']!r}"
    except ValueError:
        return f"preço/duração não numéricos no formulário: {lido['price']!r} / {lido['hours']!r}"
    for campo in ("objectives", "topics", "benefits"):
        if linhas(lido[campo]) != curso[campo]:
            return f"curso-{campo} mostra {linhas(lido[campo])}, a API tem {curso[campo]}"
    faq = [partes(l) for l in linhas(lido["faq"])]
    if faq != [(f["question"], f["answer"]) for f in curso["faq"]]:
        return f"curso-faq mostra {faq}, a API tem {curso['faq']}"
    materiais = [partes(l) for l in linhas(lido["materials"])]
    if materiais != [(m["title"], m["url"], m["type"]) for m in curso["materials"]]:
        return f"curso-materials mostra {materiais}, a API tem {curso['materials']} (formato 'Título | URL | tipo')"
    return None


def checar_curso_na_api(curso, esperado, rotulo):
    chaves = set(sem_datas(curso))
    if chaves != set(esperado):
        raise Falha(f"{rotulo}: campos do curso na API {sorted(chaves)}, esperado {sorted(esperado)}")
    for chave, valor in esperado.items():
        if curso[chave] != valor:
            raise Falha(f"{rotulo}: {chave} na API é {curso[chave]!r}, esperado {valor!r}")


def abrir_pagina_com_token_velho(page, base, caminho):
    """Abre `caminho` e deixa um token velho em localStorage (como se houvesse uma sessão anterior)."""
    page.goto(base + caminho, wait_until="networkidle")
    page.evaluate("t => localStorage.setItem('gtt_token', t)", TOKEN_VELHO)


def login_na_tela_com_token_velho(page, base, email, senha, rotulo):
    try:
        abrir_pagina_com_token_velho(page, base, "/")
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campos de login não encontrados na tela /")


def esperar_url(page, padrao, rotulo):
    try:
        page.wait_for_url(padrao, timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado {padrao})")
    page.wait_for_load_state("networkidle")


def test_l2_cadastro_cursos_angular_e2e(servidores, browser):
    base = servidores["base"]
    api = servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_inesperados = []
    provocados = []
    dialogos = []
    chamadas = []   # toda requisição a /api/ feita pelas páginas: {rotulo, metodo, caminho, auth}
    escritas = []   # POST/PUT/DELETE em /api/admin/: {metodo, caminho, corpo}
    contextos = []
    estado = {"page": None}
    paginas = {}
    PERMITIDOS = {("POST", "/api/admin/create-course", 400), ("POST", "/api/auth/password-setup", 400)}
    CAMINHOS_PERMITIDOS = {"/api/admin/create-course", "/api/auth/password-setup"}

    # --- seed pela API pública/administrativa do backend de teste ------------------------
    seed = {"ok": False, "erro": ""}
    dados = {"alunos": {}}
    try:
        dados["token_g"] = token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        dados["token_sup"] = token_de_funcionario(api, SUPORTE_EMAIL, SUPORTE_SENHA)
        dados["token_fin"] = token_de_funcionario(api, FINANCEIRO_EMAIL, FINANCEIRO_SENHA)
        for curso in (SEED_A, SEED_B):
            status, _ = _api(api, "POST", "/api/admin/create-course", curso, token=dados["token_g"])
            if status != 200:
                raise RuntimeError(f"seed: create-course {curso['id']} respondeu HTTP {status}")
        # dois alunos no curso A: "ativo" paga (webhook assinado -> active); "pendente" só abre o checkout
        for tag, paga in (("l2ativo", True), ("l2pend", False)):
            email, token_aluno = semear_aluno(api, tag)
            status, corpo = _api(api, "POST", "/api/payments/create-checkout",
                                 {"course_id": CURSO_A, "payer": {"name": f"Aluno L2 {tag}", "email": email}})
            if status != 200 or not (corpo or {}).get("external_reference"):
                raise RuntimeError(f"seed: create-checkout de {tag} respondeu HTTP {status}")
            if paga:
                status, _ = enviar_webhook(api, corpo["external_reference"])
                if status != 200:
                    raise RuntimeError(f"seed: webhook de {tag} respondeu HTTP {status}")
            status, corpo = _api(api, "GET", "/api/student/enrollments", token=token_aluno)
            item = next((m for m in (corpo or {}).get("enrollments", []) if m["course_id"] == CURSO_A), None)
            esperado = "active" if paga else "pending"
            if status != 200 or item is None or item["status"] != esperado:
                raise RuntimeError(f"seed: matrícula de {tag} inesperada (HTTP {status}, {item}, esperado {esperado})")
            dados["alunos"][tag] = {"email": email, "token": token_aluno}
        if ids_da_api(api, dados["token_g"]) != sorted([CURSO_A, CURSO_B]):
            raise RuntimeError(f"seed: cursos da API {ids_da_api(api, dados['token_g'])}")
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
            codigo = int(m.group(1))
            url = msg.location.get("url") or ""
            caminho = urllib.parse.urlparse(url).path
            if caminho in CAMINHOS_PERMITIDOS:
                return  # a ocorrência é conferida em K1 pela resposta (provocados)
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_inesperados.append(f"{rotulo}: console: {msg.text} [{url}]")

        def ao_response(resposta):
            url = resposta.url
            if "/api/" not in url:
                return
            codigo = resposta.status
            metodo = resposta.request.method
            caminho = urllib.parse.urlparse(url).path
            if (metodo, caminho, codigo) in PERMITIDOS:
                provocados.append((rotulo, metodo, caminho, codigo))
            elif codigo == 400 or codigo >= 500 or codigo == 404:
                erros_inesperados.append(f"{rotulo}: {metodo} {caminho} respondeu HTTP {codigo}")
            elif codigo in (401, 403) and caminho.startswith("/api/admin/course"):
                erros_inesperados.append(f"{rotulo}: {metodo} {caminho} respondeu HTTP {codigo}")

        def ao_request(requisicao):
            caminho = urllib.parse.urlparse(requisicao.url).path
            if not caminho.startswith("/api/"):
                return
            chamadas.append({"rotulo": rotulo, "metodo": requisicao.method, "caminho": caminho,
                             "auth": requisicao.headers.get("authorization")})
            if requisicao.method in ("POST", "PUT", "DELETE", "PATCH") and caminho.startswith("/api/admin/"):
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
            detalhe = f"{type(erro).__name__}: {linha}"
            resultados.append((codigo, nome, False, detalhe))
            imprimir(f"[FAIL] {codigo} {nome} -> {detalhe}")

    def tela_gestor():
        page = paginas.get("gestor")
        if page is None:
            raise Falha("pré-requisito: a tela do gestor não ficou pronta (S1 falhou)")
        estado["page"] = page
        return page

    def abrir_cadastro(rotulo, recarregar=False):
        """Gestor na aba "Cadastro de cursos", formulário visível, lista igual à da API."""
        page = tela_gestor()
        if recarregar:
            page.reload(wait_until="networkidle")
        clicar_aba(page, ABA_CADASTRO, rotulo)
        aguardar_visivel(page.locator(SEL_FORM), rotulo, f"formulário {SEL_FORM}")
        esperar_lista(page, api, dados["token_g"], rotulo)
        return page

    def salvar_com_sucesso(page, rotulo):
        clicar(page, SEL_SALVAR, rotulo)
        esperar_texto(page, SEL_SUCESSO, MSG_SALVO, rotulo)
        if texto_visivel(page, SEL_ERRO) is not None:
            raise Falha(f"{rotulo}: curso-error visível depois de salvar com sucesso: {texto_visivel(page, SEL_ERRO)!r}")
        page.wait_for_load_state("networkidle")

    def editar(page, curso_id, rotulo):
        linha = linha_do_curso(page, curso_id)
        aguardar_visivel(linha, rotulo, f"curso-row do curso {curso_id}")
        try:
            linha.first.locator(SEL_EDIT).first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: curso-edit não encontrado na linha do curso {curso_id}")
        esperar(lambda: None if valor_do_campo(page, "id", rotulo).strip() == curso_id
                else f"curso-id mostra {valor_do_campo(page, 'id', rotulo)!r} (esperado {curso_id!r})", rotulo)

    def checar_evento_na_tela(page, evento_id, rotulo):
        """Aba Auditoria: a linha do evento mostra o gestor logado, a ação e exatamente as alterações da API."""
        clicar_aba(page, ABA_AUDITORIA, rotulo)
        eventos = eventos_da_api(api, dados["token_g"])
        if len(eventos) >= 100:
            raise Falha(f"{rotulo}: {len(eventos)} eventos na API (acima do limite padrão de 100; o teste não cobre)")
        telas = linhas_da_tela(page, len(eventos), rotulo)
        indice = next(i for i, e in enumerate(eventos) if e["id"] == evento_id)
        evento = eventos[indice]
        linha = telas.nth(indice)
        if evento["actor_email"] != ADMIN_EMAIL:
            raise Falha(f"{rotulo}: responsável do evento na API é {evento['actor_email']}, esperado {ADMIN_EMAIL}")
        if evento["action"] not in norm(linha.inner_text()):
            raise Falha(f"{rotulo}: a linha {indice} não mostra a ação {evento['action']!r}")
        checar_responsavel(texto_do_responsavel(linha, indice, rotulo), evento, f"{rotulo} linha {indice}")
        checar_alteracoes_da_linha(linha, evento, f"{rotulo} linha {indice} ({evento['action']})")

    def novo_evento(antes_ids, acao, curso_id, rotulo):
        achados = [e for e in eventos_de_curso(api, dados["token_g"], acao, curso_id) if e["id"] not in antes_ids]
        if len(achados) != 1:
            raise Falha(f"{rotulo}: {len(achados)} eventos novos {acao} do curso {curso_id} na API (esperado 1)")
        return achados[0]

    def ids_de_eventos():
        return {e["id"] for e in eventos_da_api(api, dados["token_g"])}

    def escritas_desde(marca):
        return escritas[marca:]

    # --- S1 ---------------------------------------------------------------------------
    def s1():
        page = nova_pagina("gestor")
        paginas["gestor"] = page
        login_na_tela_com_token_velho(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "S1")
        esperar_url(page, "**/admin", "S1")
        clicar_aba(page, ABA_CURSOS, "S1")
        for nome in (NOME_A, NOME_B):
            aguardar_visivel(page.locator("table tbody tr", has_text=nome), "S1", f"linha do curso {nome!r} em Cursos")
        for curso_id in (CURSO_A, CURSO_B):
            if not (servidores["cursos_tmp"] / f"{curso_id}.json").exists():
                raise Falha(f"S1: o curso {curso_id} do seed não foi gravado em {servidores['cursos_tmp']}")

    cenario("S1", "pré-condição: gestor loga, abre /admin e a aba Cursos mostra os cursos do seed", s1)

    # --- T1 ---------------------------------------------------------------------------
    def t1():
        page = tela_gestor()
        abas = abas_visiveis(page)
        if TEXTO_ABA not in abas:
            raise Falha(f"T1: o gestor não vê a aba {TEXTO_ABA!r}; abas visíveis: {abas}")
        for atual in ("Financeiro", "Alunos", "Cursos", "Observabilidade de IA", "Auditoria"):
            if atual not in abas:
                raise Falha(f"T1: a aba atual {atual!r} sumiu; abas visíveis: {abas}")

    cenario("T1", "o gestor vê a aba 'Cadastro de cursos' além das abas atuais", t1)

    # --- L1 ---------------------------------------------------------------------------
    def l1():
        page = abrir_cadastro("L1")
        if page.locator(SEL_ROW).count() != 2:
            raise Falha(f"L1: {page.locator(SEL_ROW).count()} curso-row, esperado 2 (A e B do seed)")
        for curso in (SEED_A, SEED_B):
            linha = linha_do_curso(page, curso["id"])
            if linha.count() != 1:
                raise Falha(f"L1: {linha.count()} curso-row com data-course-id={curso['id']} (esperado 1)")
            texto = norm(linha.first.inner_text())
            if curso["name"] not in texto:
                raise Falha(f"L1: a linha do curso {curso['id']} não mostra o nome {curso['name']!r}: {texto!r}")
            numeros = re.findall(r"\d+", texto)
            if str(curso["price"]) not in numeros:
                raise Falha(f"L1: a linha do curso {curso['id']} não mostra o preço {curso['price']}: {texto!r}")
            if str(curso["duration_hours"]) not in numeros:
                raise Falha(f"L1: a linha do curso {curso['id']} não mostra a duração {curso['duration_hours']}: {texto!r}")
            for testid in ("curso-edit", "curso-delete"):
                if linha.first.locator(f'[data-testid="{testid}"]').count() != 1:
                    raise Falha(f"L1: a linha do curso {curso['id']} não tem exatamente um {testid}")
        if n_visiveis(page, SEL_CONFIRMAR) != 0:
            raise Falha("L1: curso-delete-confirm visível antes de clicar em curso-delete")

    cenario("L1", "a aba lista os cursos do diretório temporário em curso-row (id, nome, preço, duração)", l1)

    # --- C1 ---------------------------------------------------------------------------
    def c1():
        page = abrir_cadastro("C1", recarregar=True)
        if not salvar_desabilitado(page, "C1"):
            raise Falha("C1: curso-save está habilitado com o formulário vazio")
        marca = len(escritas)
        preencher_tudo(page, NOVO, "C1")
        if salvar_desabilitado(page, "C1"):
            raise Falha("C1: curso-save continua desabilitado com o formulário válido")
        clicar(page, SEL_SALVAR, "C1")
        esperar_texto(page, SEL_SUCESSO, MSG_SALVO, "C1")
        if texto_visivel(page, SEL_ERRO) is not None:
            raise Falha(f"C1: curso-error visível depois de salvar: {texto_visivel(page, SEL_ERRO)!r}")
        aguardar_visivel(linha_do_curso(page, ID_NOVO), "C1", f"curso-row com data-course-id={ID_NOVO}")
        esperar_lista(page, api, dados["token_g"], "C1")
        if ID_NOVO not in norm(linha_do_curso(page, ID_NOVO).first.get_attribute("data-course-id") or ""):
            raise Falha("C1: data-course-id da linha nova inesperado")
        if NOME_NOVO not in norm(linha_do_curso(page, ID_NOVO).first.inner_text()):
            raise Falha(f"C1: a linha nova não mostra o nome {NOME_NOVO!r}")
        curso = curso_da_api(api, dados["token_g"], ID_NOVO)
        if curso is None:
            raise Falha(f"C1: a API não tem o curso {ID_NOVO} depois de salvar")
        checar_curso_na_api(curso, ESPERADO_NOVO, "C1")
        feitas = [(e["metodo"], e["caminho"]) for e in escritas_desde(marca)]
        if feitas != [("POST", "/api/admin/create-course")]:
            raise Falha(f"C1: escritas da tela {feitas}, esperado só POST /api/admin/create-course")
        if not (servidores["cursos_tmp"] / f"{ID_NOVO}.json").exists():
            raise Falha(f"C1: o curso novo não foi gravado em {servidores['cursos_tmp']}")

    cenario("C1", "cria o curso com todos os campos; curso-row, 'Curso salvo.' e a API com os campos exatos", c1)

    # --- V1 ---------------------------------------------------------------------------
    def v1():
        page = abrir_cadastro("V1", recarregar=True)
        antes_ids = ids_da_api(api, dados["token_g"])
        marca = len(escritas)
        valido = dict(NOVO, id="curso-l2-validacao")
        preencher_tudo(page, valido, "V1")
        if salvar_desabilitado(page, "V1"):
            raise Falha("V1: curso-save desabilitado com o formulário válido")
        casos = [(campo, "") for campo in OBRIGATORIOS]
        casos += [("price", "0"), ("price", "-5"), ("hours", "2.5"), ("hours", "0"), ("hours", "-3")]
        for campo, invalido in casos:
            preencher(page, campo, invalido, "V1")
            esperar(lambda: None if salvar_desabilitado(page, "V1")
                    else f"curso-save habilitado com curso-{campo} = {invalido!r}", f"V1 ({campo}={invalido!r})")
            preencher(page, campo, valido[campo], "V1")
            esperar(lambda: None if not salvar_desabilitado(page, "V1")
                    else f"curso-save continua desabilitado depois de restaurar curso-{campo}", f"V1 (restaurar {campo})")
        # o campo de materiais é opcional: vazio não desabilita
        preencher(page, "materials", "", "V1")
        esperar(lambda: None if not salvar_desabilitado(page, "V1")
                else "curso-save desabilitado com curso-materials vazio (o campo é opcional)", "V1 (materials vazio)")
        if len(escritas) != marca or ids_da_api(api, dados["token_g"]) != antes_ids:
            raise Falha("V1: houve escrita ou curso novo durante a validação do formulário")

    cenario("V1", "campos vazios, preço 0/negativo e duração inválida mantêm curso-save desabilitado", v1)

    # --- V2 ---------------------------------------------------------------------------
    def v2():
        page = abrir_cadastro("V2", recarregar=True)
        antes_ids = ids_da_api(api, dados["token_g"])
        marca = len(escritas)
        valido = dict(NOVO, id="curso-l2-validacao")
        preencher_tudo(page, valido, "V2")

        def tentar_e_esperar_erro(esperado, rotulo):
            clicar(page, SEL_SALVAR, rotulo)
            esperar_texto(page, SEL_ERRO, esperado, rotulo)
            page.wait_for_timeout(600)
            page.wait_for_load_state("networkidle")
            if texto_visivel(page, SEL_SUCESSO) is not None:
                raise Falha(f"{rotulo}: curso-success visível junto do erro de validação")
            if len(escritas) != marca:
                raise Falha(f"{rotulo}: a tela enviou {escritas[marca:]} apesar do erro de validação")
            if ids_da_api(api, dados["token_g"]) != antes_ids:
                raise Falha(f"{rotulo}: a API ganhou um curso apesar do erro de validação")

        preencher(page, "faq", "Pergunta com resposta | Resposta\nLinha sem barra", "V2")
        tentar_e_esperar_erro(MSG_FAQ, "V2 faq sem '|'")
        preencher(page, "faq", valido["faq"], "V2")
        preencher(page, "materials", "Malicioso | javascript:alert(1) | link", "V2")
        tentar_e_esperar_erro(MSG_URL, "V2 javascript:")
        preencher(page, "materials", "Servidor | ftp://exemplo.com/arquivo | link", "V2")
        tentar_e_esperar_erro(MSG_URL, "V2 ftp://")
        # o erro de URL com outra linha boa antes: continua recusando o conjunto
        preencher(page, "materials", "Bom | https://exemplo.com/ok | pdf\nRuim | javascript:void(0) | link", "V2")
        tentar_e_esperar_erro(MSG_URL, "V2 uma linha ruim entre duas")

    cenario("V2", "FAQ sem '|' e URL javascript:/ftp:// mostram o texto exato e nada é enviado", v2)

    # --- D1 ---------------------------------------------------------------------------
    def d1():
        page = abrir_cadastro("D1", recarregar=True)
        antes_ids = ids_da_api(api, dados["token_g"])
        antes_curso = curso_da_api(api, dados["token_g"], CURSO_A)
        duplicado = dict(NOVO, id=CURSO_A, name="Nome que não pode entrar")
        corpo = {"id": CURSO_A, "name": "x", "description": "x", "price": 1, "duration_hours": 1, "level": "x",
                 "target_audience": "x", "objectives": ["x"], "topics": ["x"], "benefits": ["x"],
                 "faq": [{"question": "x", "answer": "x"}], "system_prompt": "x", "materials": []}
        status, detalhe = detalhe_do_erro_da_api(api, dados["token_g"], "POST", "/api/admin/create-course", corpo)
        if status != 400 or not isinstance(detalhe, str):
            raise Falha(f"D1: a API devolveu HTTP {status} / detail {detalhe!r} para o id duplicado (esperado 400 com texto)")
        preencher_tudo(page, duplicado, "D1")
        try:
            with page.expect_response(lambda r: r.request.method == "POST"
                                      and urllib.parse.urlparse(r.url).path == "/api/admin/create-course",
                                      timeout=TIMEOUT * 2):
                clicar(page, SEL_SALVAR, "D1")
        except sync_api.TimeoutError:
            raise Falha("D1: a tela não enviou POST /api/admin/create-course")
        esperar_texto(page, SEL_ERRO, detalhe, "D1")
        if texto_visivel(page, SEL_SUCESSO) is not None:
            raise Falha("D1: curso-success visível junto do erro de id duplicado")
        if ids_da_api(api, dados["token_g"]) != antes_ids:
            raise Falha("D1: o id duplicado mudou a lista de cursos da API")
        if curso_da_api(api, dados["token_g"], CURSO_A) != antes_curso:
            raise Falha("D1: o curso existente foi alterado pelo cadastro duplicado")
        esperar_lista(page, api, dados["token_g"], "D1")

    cenario("D1", "id duplicado: curso-error mostra o detail da API (texto exato) e nada muda", d1)

    # --- E1 ---------------------------------------------------------------------------
    def e1():
        page = abrir_cadastro("E1", recarregar=True)
        editar(page, CURSO_A, "E1")
        curso = curso_da_api(api, dados["token_g"], CURSO_A)
        esperar(lambda: comparar_form_com_api(page, curso, "E1"), "E1 formulário carregado")
        if page.locator(SEL["id"]).first.is_editable():
            raise Falha("E1: curso-id é editável na edição (deveria ser somente leitura)")

    cenario("E1", "curso-edit carrega o formulário (listas, FAQ e materiais em linhas; curso-id somente leitura)", e1)

    # --- E2 ---------------------------------------------------------------------------
    def e2():
        page = abrir_cadastro("E2", recarregar=True)
        antes = curso_da_api(api, dados["token_g"], CURSO_A)
        antes_ids = ids_de_eventos()
        editar(page, CURSO_A, "E2")
        marca = len(escritas)
        preencher(page, "price", "250", "E2")
        salvar_com_sucesso(page, "E2")
        feitas = escritas_desde(marca)
        if [(e["metodo"], e["caminho"]) for e in feitas] != [("PUT", f"/api/admin/course/{CURSO_A}")]:
            raise Falha(f"E2: escritas da tela {[(e['metodo'], e['caminho']) for e in feitas]}, esperado só PUT do curso")
        corpo = feitas[0]["corpo"] or {}
        if corpo.get("materials") != SEED_A["materials"]:
            raise Falha(f"E2: o PUT não enviou os materiais carregados (materials={corpo.get('materials')!r})")
        depois = curso_da_api(api, dados["token_g"], CURSO_A)
        if depois["price"] != 250:
            raise Falha(f"E2: preço na API {depois['price']!r}, esperado 250")
        if depois["materials"] != SEED_A["materials"]:
            raise Falha(f"E2: os materiais foram perdidos ao alterar só o preço: {depois['materials']}")
        esperado = dict(sem_datas(antes), price=250)
        if sem_datas(depois) != esperado:
            raise Falha(f"E2: outros campos mudaram além do preço: {sem_datas(depois)} (esperado {esperado})")
        if "250" not in re.findall(r"\d+", norm(linha_do_curso(page, CURSO_A).first.inner_text())):
            raise Falha("E2: a linha do curso não mostra o preço novo (250) depois de salvar")
        evento = novo_evento(antes_ids, "course.price_change", CURSO_A, "E2")
        if evento["actor_email"] != ADMIN_EMAIL:
            raise Falha(f"E2: responsável do evento é {evento['actor_email']}, esperado {ADMIN_EMAIL}")
        if [c["field"] for c in evento["changes"]] != ["price"]:
            raise Falha(f"E2: changes do evento {[c['field'] for c in evento['changes']]}, esperado só ['price']")
        if [c for c in eventos_de_curso(api, dados["token_g"], "course.update", CURSO_A) if c["id"] not in antes_ids]:
            raise Falha("E2: a edição gerou também um course.update (esperado um evento só)")
        checar_evento_na_tela(page, evento["id"], "E2")

    cenario("E2", "alterar só o preço preserva os materiais; course.price_change só de price com o gestor logado", e2)

    # --- E3 ---------------------------------------------------------------------------
    def e3():
        page = abrir_cadastro("E3", recarregar=True)
        antes = curso_da_api(api, dados["token_g"], CURSO_A)
        antes_ids = ids_de_eventos()
        editar(page, CURSO_A, "E3")
        marca = len(escritas)
        preencher(page, "materials", MATERIAIS_NOVOS_TELA, "E3")
        salvar_com_sucesso(page, "E3")
        feitas = [(e["metodo"], e["caminho"]) for e in escritas_desde(marca)]
        if feitas != [("PUT", f"/api/admin/course/{CURSO_A}")]:
            raise Falha(f"E3: escritas da tela {feitas}, esperado só PUT do curso")
        depois = curso_da_api(api, dados["token_g"], CURSO_A)
        if depois["materials"] != MATERIAIS_NOVOS_API:
            raise Falha(f"E3: materiais na API {depois['materials']}, esperado {MATERIAIS_NOVOS_API} "
                        f"(tipo omitido vira 'link')")
        if sem_datas(depois) != dict(sem_datas(antes), materials=MATERIAIS_NOVOS_API):
            raise Falha("E3: outros campos mudaram além dos materiais")
        evento = novo_evento(antes_ids, "course.update", CURSO_A, "E3")
        if [c["field"] for c in evento["changes"]] != ["materials"] or evento["actor_email"] != ADMIN_EMAIL:
            raise Falha(f"E3: evento course.update inesperado: responsável {evento['actor_email']}, "
                        f"changes {[c['field'] for c in evento['changes']]}")

    cenario("E3", "alterar os materiais substitui (tipo omitido vira link); course.update só de materials", e3)

    # --- A1 ---------------------------------------------------------------------------
    def a1():
        ativo, pendente = dados["alunos"]["l2ativo"], dados["alunos"]["l2pend"]
        # API: ativo recebe os materiais novos; pendente não recebe campo nenhum de material
        status, corpo = _api(api, "GET", "/api/student/enrollments", token=ativo["token"])
        item = next(m for m in corpo["enrollments"] if m["course_id"] == CURSO_A)
        if status != 200 or item.get("materials") != MATERIAIS_NOVOS_API:
            raise Falha(f"A1: materiais do aluno ativo na API {item.get('materials')!r}, esperado {MATERIAIS_NOVOS_API}")
        status, corpo = _api(api, "GET", "/api/student/enrollments", token=pendente["token"])
        item_p = next(m for m in corpo["enrollments"] if m["course_id"] == CURSO_A)
        if "materials" in item_p or "http" in json.dumps(item_p):
            raise Falha(f"A1: a matrícula pendente tem material ou URL na resposta: {item_p}")
        # tela do aluno ativo (com token velho antes do login)
        page = nova_pagina("aluno-ativo")
        paginas["aluno"] = page
        login_na_tela_com_token_velho(page, base, ativo["email"], SENHA, "A1")
        esperar_url(page, "**/student", "A1")
        links = lambda: page.eval_on_selector_all(
            "a.list-group-item", "els => els.map(e => [e.innerText.trim(), e.getAttribute('href')])")
        esperado = [[m["title"], m["url"]] for m in MATERIAIS_NOVOS_API]
        esperar(lambda: None if links() == esperado else f"links de material em /student {links()}, esperado {esperado}", "A1")
        # tela do aluno pendente: nenhum link de material
        page_p = nova_pagina("aluno-pendente")
        login_na_tela_com_token_velho(page_p, base, pendente["email"], SENHA, "A1 pendente")
        esperar_url(page_p, "**/student", "A1 pendente")
        if page_p.locator("a.list-group-item").count() != 0 or "exemplo.com" in page_p.content():
            raise Falha("A1: o aluno com matrícula pendente vê link de material em /student")
        estado["page"] = page

    cenario("A1", "aluno ativo vê os materiais novos em /student; o pendente não vê nenhum (API e tela)", a1)

    # --- E4 ---------------------------------------------------------------------------
    def e4():
        page = abrir_cadastro("E4", recarregar=True)
        antes = curso_da_api(api, dados["token_g"], CURSO_A)
        editar(page, CURSO_A, "E4")
        marca = len(escritas)
        preencher(page, "materials", "", "E4")
        salvar_com_sucesso(page, "E4")
        feitas = escritas_desde(marca)
        if [(e["metodo"], e["caminho"]) for e in feitas] != [("PUT", f"/api/admin/course/{CURSO_A}")]:
            raise Falha(f"E4: escritas da tela {[(e['metodo'], e['caminho']) for e in feitas]}")
        if (feitas[0]["corpo"] or {}).get("materials", "ausente") != []:
            raise Falha(f"E4: o PUT deveria enviar materials=[] (enviou {(feitas[0]['corpo'] or {}).get('materials', 'ausente')!r})")
        depois = curso_da_api(api, dados["token_g"], CURSO_A)
        if depois["materials"] != [] or sem_datas(depois) != dict(sem_datas(antes), materials=[]):
            raise Falha(f"E4: curso na API depois de limpar os materiais: materials={depois['materials']!r}")
        status, corpo = _api(api, "GET", "/api/student/enrollments", token=dados["alunos"]["l2ativo"]["token"])
        item = next(m for m in corpo["enrollments"] if m["course_id"] == CURSO_A)
        if item.get("materials") != []:
            raise Falha(f"E4: o aluno ativo ainda recebe materiais: {item.get('materials')!r}")

    cenario("E4", "limpar o campo de materiais salva [] (propositalmente); o aluno deixa de receber material", e4)

    # --- E5 ---------------------------------------------------------------------------
    def e5():
        page = abrir_cadastro("E5", recarregar=True)
        marca = len(escritas)
        editar(page, CURSO_B, "E5")
        if page.locator(SEL["id"]).first.is_editable():
            raise Falha("E5: curso-id é editável na edição")
        clicar(page, SEL_CANCELAR_EDICAO, "E5", "curso-cancel-edit (visível durante a edição)")
        def criacao():
            for campo in CAMPOS:
                if valor_do_campo(page, campo, "E5").strip() != "":
                    return f"curso-{campo} ainda tem {valor_do_campo(page, campo, 'E5')!r} depois de cancelar a edição"
            if not page.locator(SEL["id"]).first.is_editable():
                return "curso-id continua somente leitura depois de cancelar a edição"
            return None
        esperar(criacao, "E5")
        if not salvar_desabilitado(page, "E5"):
            raise Falha("E5: curso-save habilitado no modo de criação com o formulário vazio")
        if len(escritas) != marca:
            raise Falha(f"E5: houve escrita ao cancelar a edição: {escritas[marca:]}")
        if curso_da_api(api, dados["token_g"], CURSO_B) is None:
            raise Falha("E5: o curso B sumiu")

    cenario("E5", "curso-cancel-edit volta ao modo de criação (campos vazios, curso-id editável), sem escrita", e5)

    # --- X1 ---------------------------------------------------------------------------
    def x1():
        page = abrir_cadastro("X1", recarregar=True)
        antes_ids = ids_da_api(api, dados["token_g"])
        if ID_NOVO not in antes_ids:
            raise Falha(f"X1: o curso {ID_NOVO} (criado em C1) não está na API; C1 precisa passar antes")
        antes_ids_evento = ids_de_eventos()
        marca = len(escritas)
        linha = linha_do_curso(page, ID_NOVO)
        aguardar_visivel(linha, "X1", f"curso-row do curso {ID_NOVO}")
        # curso-delete só pede a confirmação
        try:
            linha.first.locator(SEL_DELETE).first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha(f"X1: curso-delete não encontrado na linha do curso {ID_NOVO}")
        aguardar_visivel(page.locator(SEL_CONFIRMAR), "X1", "curso-delete-confirm")
        page.wait_for_load_state("networkidle")
        if any(e["metodo"] == "DELETE" for e in escritas_desde(marca)) or curso_da_api(api, dados["token_g"], ID_NOVO) is None:
            raise Falha("X1: curso-delete removeu o curso sem confirmação")
        if n_visiveis(page, SEL_CONFIRMAR) != 1:
            raise Falha(f"X1: {n_visiveis(page, SEL_CONFIRMAR)} curso-delete-confirm visíveis (esperado 1)")
        # cancelar mantém
        clicar(page, SEL_CANCELAR_EXCLUSAO, "X1", "curso-cancel-delete")
        esperar(lambda: None if n_visiveis(page, SEL_CONFIRMAR) == 0
                else "curso-delete-confirm continua visível depois de curso-cancel-delete", "X1")
        page.wait_for_load_state("networkidle")
        if any(e["metodo"] == "DELETE" for e in escritas_desde(marca)) or curso_da_api(api, dados["token_g"], ID_NOVO) is None:
            raise Falha("X1: cancelar a exclusão removeu o curso")
        if linha_do_curso(page, ID_NOVO).count() != 1:
            raise Falha("X1: a linha do curso sumiu depois de cancelar a exclusão")
        # confirmar remove
        linha.first.locator(SEL_DELETE).first.click(timeout=TIMEOUT)
        aguardar_visivel(page.locator(SEL_CONFIRMAR), "X1", "curso-delete-confirm (segunda vez)")
        clicar(page, SEL_CONFIRMAR, "X1")
        esperar_texto(page, SEL_SUCESSO, MSG_REMOVIDO, "X1")
        esperar(lambda: None if linha_do_curso(page, ID_NOVO).count() == 0
                else "a curso-row do curso removido continua na tela", "X1")
        removidas = [(e["metodo"], e["caminho"]) for e in escritas_desde(marca)]
        if removidas != [("DELETE", f"/api/admin/course/{ID_NOVO}")]:
            raise Falha(f"X1: escritas da tela {removidas}, esperado só um DELETE do curso")
        if curso_da_api(api, dados["token_g"], ID_NOVO) is not None or (servidores["cursos_tmp"] / f"{ID_NOVO}.json").exists():
            raise Falha("X1: o curso continua na API ou no diretório temporário depois da confirmação")
        if ids_da_api(api, dados["token_g"]) != sorted(set(antes_ids) - {ID_NOVO}):
            raise Falha("X1: a lista de cursos da API mudou além da remoção")
        esperar_lista(page, api, dados["token_g"], "X1")
        if dialogos:
            raise Falha(f"X1: a tela abriu window.confirm/alert: {dialogos}")
        evento = novo_evento(antes_ids_evento, "course.delete", ID_NOVO, "X1")
        checar_evento_na_tela(page, evento["id"], "X1")

    cenario("X1", "curso-delete só pede confirmação; cancelar mantém; confirmar remove e grava course.delete", x1)

    # --- R1 / R2 ----------------------------------------------------------------------
    def sem_cadastro(perfil, email, senha, token, codigo):
        def fn():
            page = nova_pagina(f"{codigo}-{perfil}")
            paginas[perfil] = page
            login_na_tela_com_token_velho(page, base, email, senha, codigo)
            esperar_url(page, "**/admin", codigo)
            abas = abas_visiveis(page)
            if not abas or TEXTO_ABA in abas:
                raise Falha(f"{codigo}: abas do {perfil} {abas} (a aba {TEXTO_ABA!r} não pode aparecer)")
            for i in range(len(abas)):
                page.locator("ul.nav-tabs button").nth(i).click(timeout=TIMEOUT)
                page.wait_for_load_state("networkidle")
                for seletor in (SEL_FORM, SEL_ROW, SEL["id"], SEL_SALVAR):
                    if page.locator(seletor).count() != 0:
                        raise Falha(f"{codigo}: o {perfil} vê {seletor} na aba {abas[i]!r}")
            antes_ids = ids_da_api(api, dados["token_g"])
            antes_a = curso_da_api(api, dados["token_g"], CURSO_A)
            tentativas = (
                ("POST", "/api/admin/create-course", dict(corpo_da_api(SEED_B), id=f"curso-l2-{perfil}")),
                ("PUT", f"/api/admin/course/{CURSO_A}", dict(corpo_da_api(antes_a), price=1)),
                ("DELETE", f"/api/admin/course/{CURSO_B}", None),
            )
            for metodo, caminho, corpo in tentativas:
                status, _ = _api(api, metodo, caminho, corpo, token=token)
                if status != 403:
                    raise Falha(f"{codigo}: {metodo} {caminho} como {perfil} respondeu HTTP {status} (esperado 403)")
            if ids_da_api(api, dados["token_g"]) != antes_ids or curso_da_api(api, dados["token_g"], CURSO_A) != antes_a:
                raise Falha(f"{codigo}: os cursos mudaram depois das escritas recusadas do {perfil}")
        return fn

    cenario("R1", "suporte: sem a aba nem curso-form/curso-row; escritas de curso 403",
            sem_cadastro("suporte", SUPORTE_EMAIL, SUPORTE_SENHA, dados.get("token_sup"), "R1"))
    cenario("R2", "financeiro: sem a aba nem curso-form/curso-row; escritas de curso 403",
            sem_cadastro("financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA, dados.get("token_fin"), "R2"))

    # --- R3 ---------------------------------------------------------------------------
    def r3():
        rotas = (
            ("POST", "/api/admin/create-course", dict(corpo_da_api(SEED_B), id="curso-l2-sem-token")),
            ("PUT", f"/api/admin/course/{CURSO_A}", corpo_da_api(SEED_A)),
            ("DELETE", f"/api/admin/course/{CURSO_B}", None),
        )
        for token in (None, "abc.def.ghi", "Zm9yamFkby1zZW0tcG9udG9z"):
            for metodo, caminho, corpo in rotas:
                status, _ = _api(api, metodo, caminho, corpo, token=token)
                if status != 401:
                    raise Falha(f"R3: {metodo} {caminho} com token {token!r} respondeu HTTP {status} (esperado 401)")
        if curso_da_api(api, dados["token_g"], CURSO_B) is None or "curso-l2-sem-token" in ids_da_api(api, dados["token_g"]):
            raise Falha("R3: uma escrita sem credencial válida alterou os cursos")

    cenario("R3", "sem token e com token forjado: 401 nas escritas de curso", r3)

    # --- N1 ---------------------------------------------------------------------------
    def desde(rotulo, prefixo=None, caminho=None):
        return [c for c in chamadas if c["rotulo"] == rotulo
                and (prefixo is None or c["caminho"].startswith(prefixo))
                and (caminho is None or c["caminho"] == caminho)]

    def n1():
        page = nova_pagina("N1-gestor")
        login_na_tela_com_token_velho(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "N1")
        esperar_url(page, "**/admin", "N1")
        for aba in (ABA_ALUNOS, ABA_CURSOS, ABA_AUDITORIA):
            clicar_aba(page, aba, "N1")
        logins = desde("N1-gestor", caminho="/api/token")
        if len(logins) != 1:
            raise Falha(f"N1: {len(logins)} chamadas a /api/token (esperado 1)")
        if logins[0]["auth"] is not None:
            raise Falha(f"N1: /api/token levou Authorization ({logins[0]['auth'][:25]}...) com um token velho no navegador")
        for prefixo in ("/api/dashboard/", "/api/admin/"):
            achadas = desde("N1-gestor", prefixo=prefixo)
            if not achadas:
                raise Falha(f"N1: nenhuma chamada a {prefixo}* depois do login")
            sem = [c for c in achadas if not (c["auth"] or "").startswith("Bearer ") or c["auth"] == "Bearer " + TOKEN_VELHO]
            if sem:
                raise Falha(f"N1: {len(sem)} chamadas a {prefixo}* sem o Bearer do login: {[(c['metodo'], c['caminho']) for c in sem][:3]}")

    cenario("N1", "gestor: /api/token sem Authorization (token velho no navegador); /api/admin e /api/dashboard com Bearer", n1)

    # --- N2 ---------------------------------------------------------------------------
    def n2():
        ativo = dados["alunos"]["l2ativo"]
        page = nova_pagina("N2-aluno")
        login_na_tela_com_token_velho(page, base, ativo["email"], SENHA, "N2")
        esperar_url(page, "**/student", "N2")
        logins = desde("N2-aluno", caminho="/api/token")
        if len(logins) != 1 or logins[0]["auth"] is not None:
            raise Falha(f"N2: login do aluno: {len(logins)} chamadas a /api/token, auth={[c['auth'] for c in logins]} "
                        f"(esperado 1 sem Authorization)")
        achadas = desde("N2-aluno", prefixo="/api/student/")
        if not achadas:
            raise Falha("N2: nenhuma chamada a /api/student/* na tela do aluno")
        sem = [c for c in achadas if not (c["auth"] or "").startswith("Bearer ") or c["auth"] == "Bearer " + TOKEN_VELHO]
        if sem:
            raise Falha(f"N2: {len(sem)} chamadas a /api/student/* sem o Bearer do login: {[(c['metodo'], c['caminho']) for c in sem][:3]}")

    cenario("N2", "aluno logado: /api/student/* com Bearer; o login do aluno sem Authorization", n2)

    # --- N3 ---------------------------------------------------------------------------
    def n3():
        page = nova_pagina("N3-cadastro")
        try:
            abrir_pagina_com_token_velho(page, base, "/cadastro")
            page.locator("input[name=name]").first.fill("Aluno Interceptor L2", timeout=TIMEOUT)
            page.locator("input[name=email]").first.fill(f"e2e.l2.{uuid.uuid4().hex[:10]}@teste.com", timeout=TIMEOUT)
            page.locator("input[name=password]").first.fill(SENHA, timeout=TIMEOUT)
            with page.expect_response(lambda r: urllib.parse.urlparse(r.url).path == "/api/auth/register",
                                      timeout=TIMEOUT * 2):
                page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("N3: formulário de /cadastro não encontrado ou a tela não chamou /api/auth/register")
        esperar(lambda: None if desde("N3-cadastro", caminho="/api/auth/register")
                else "a tela não chamou /api/auth/register", "N3")
        page.wait_for_load_state("networkidle")
        chamada = desde("N3-cadastro", caminho="/api/auth/register")[0]
        if chamada["auth"] is not None:
            raise Falha(f"N3: /api/auth/register levou Authorization ({chamada['auth'][:25]}...) com token no navegador")
        aguardar_visivel(page.get_by_text("Conta criada", exact=False), "N3", "mensagem de conta criada")

    cenario("N3", "/cadastro com token no navegador: /api/auth/register sem Authorization", n3)

    # --- N4 ---------------------------------------------------------------------------
    def n4():
        page = nova_pagina("N4-definir-senha")
        try:
            abrir_pagina_com_token_velho(page, base, "/definir-senha?token=x")
            page.locator("input[name=password]").first.fill("senha-qualquer-123", timeout=TIMEOUT)
            with page.expect_response(lambda r: urllib.parse.urlparse(r.url).path == "/api/auth/password-setup",
                                      timeout=TIMEOUT * 2):
                page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("N4: formulário de /definir-senha não encontrado ou a tela não chamou /api/auth/password-setup")
        esperar(lambda: None if desde("N4-definir-senha", caminho="/api/auth/password-setup")
                else "a tela não chamou /api/auth/password-setup", "N4")
        page.wait_for_load_state("networkidle")
        chamada = desde("N4-definir-senha", caminho="/api/auth/password-setup")[0]
        if chamada["auth"] is not None:
            raise Falha(f"N4: /api/auth/password-setup levou Authorization ({chamada['auth'][:25]}...) com token no navegador")

    cenario("N4", "/definir-senha?token=x com token no navegador: password-setup sem Authorization (400 esperado)", n4)

    # --- N5 ---------------------------------------------------------------------------
    def n5():
        if not chamadas:
            raise Falha("N5: nenhuma chamada a /api/ registrada")
        for c in chamadas:
            com_token = c["caminho"].startswith(PREFIXOS_COM_TOKEN)
            if com_token and not (c["auth"] or "").startswith("Bearer "):
                raise Falha(f"N5 [{c['rotulo']}]: {c['metodo']} {c['caminho']} sem Authorization: Bearer")
            if not com_token and c["auth"] is not None:
                raise Falha(f"N5 [{c['rotulo']}]: {c['metodo']} {c['caminho']} levou Authorization, mas só "
                            f"{', '.join(PREFIXOS_COM_TOKEN)} podem levar")

    cenario("N5", "regra geral: Authorization só nos quatro prefixos; Bearer em todos eles", n5)

    # --- K1 ---------------------------------------------------------------------------
    def k1():
        if erros_inesperados:
            raise Falha(f"K1: {len(erros_inesperados)} erro(s) inesperado(s): " + " | ".join(erros_inesperados[:5]))
        if dialogos:
            raise Falha(f"K1: a tela abriu diálogos do navegador (window.confirm/alert): {dialogos}")
        obtidos = sorted((m, c, k) for _, m, c, k in provocados)
        if obtidos != sorted(PERMITIDOS):
            raise Falha(f"K1: respostas 400 provocadas {obtidos}; esperado exatamente {sorted(PERMITIDOS)}")

    cenario("K1", "sem erros de console/exceção/diálogo; só os dois 400 provocados (D1 e N4)", k1)

    # --- Z1 ---------------------------------------------------------------------------
    def z1():
        cursos_tmp = servidores["cursos_tmp"]
        for curso_id in (CURSO_A, CURSO_B):
            if not (cursos_tmp / f"{curso_id}.json").exists():
                raise Falha(f"Z1: o curso {curso_id} do seed não está em {cursos_tmp} (isolamento falhou)")
        for curso_id in (CURSO_A, CURSO_B, ID_NOVO, "curso-l2-validacao"):
            if (REPO / "backend" / "courses" / f"{curso_id}.json").exists():
                raise Falha(f"Z1: o curso {curso_id} apareceu em backend/courses")
        if snapshot_de_cursos() != servidores["cursos_antes"]:
            raise Falha("Z1: backend/courses mudou durante o teste (o teste não pode alterar esse diretório)")

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
