"""E2E da tela de turmas da área do funcionário (L1, Chromium via Playwright).
Decisões D53 (seção "Tela (Angular, `courses-dashboard`), `data-testid`") e D54. O backend da L1 já está pronto
(commit 21218b8); este arquivo é o teste VERMELHO da parte de frontend: a aba "Cursos" de /admin precisa mostrar
as turmas de cada curso e, só para Gestão, a seção "Gerenciar turmas".

Contrato de tela (D53), aba "Cursos":
  data-testid="turma-row"         -> uma linha por turma, dentro do curso
  data-testid="turma-name"        -> nome da turma (dentro da turma-row)
  data-testid="turma-enrolled"    -> matrículas ativas (número)
  data-testid="turma-pending"     -> matrículas pendentes (número)
  data-testid="turma-capacity"    -> capacidade (número) ou "—" quando a turma não tem capacidade
  data-testid="turma-unassigned"  -> um por curso (na ordem de GET /api/dashboard/cursos): "ativos/pendentes sem
                                     turma", dois números separados por "/" (os dois dígitos são os conferidos)
  Só Gestão, seção "Gerenciar turmas":
  data-testid="turma-new-course" (select), "turma-new-name", "turma-new-start", "turma-new-capacity",
  "turma-create" (botão), "enrollment-row" (uma por matrícula do curso escolhido no turma-new-course),
  "enrollment-class-select" (um por enrollment-row; opção "Sem turma" mais as turmas do curso),
  "turma-error" (mensagem de erro da API, texto exato do `detail`).
  Suporte e Financeiro veem os turma-* (números), nunca a seção de gestão.
Os cartões/gráfico/tabela atuais do dashboard de cursos continuam ("Inscritos por curso", canvas, "Performance
do catálogo" com uma linha por curso).

Escolhas de forma aceitas pelo teste (nenhuma define política): o texto de turma-enrolled/pending/capacity pode
ter palavras ao redor desde que haja exatamente um número; turma-unassigned pode ter palavras ao redor desde que
haja exatamente dois números; a opção do select de curso pode ter qualquer rótulo que contenha o nome (ou o id)
do curso; a opção do select de turma pode ter qualquer rótulo que contenha o nome da turma (ex.: "Turma Alfa (0/1)").
O teste NÃO exige que o select de curso comece vazio nem que o formulário seja limpo depois de criar.

Cenários (checks numerados):
  S1 pré-condição (anterior aos testids): login do gestor chega a /admin; a aba "Cursos" abre e mostra o gráfico,
     a tabela "Performance do catálogo" e os dois cursos do seed. Garante que o red é por falta da L1 na tela,
     não por servidor, login ou seed
  I1 isolamento: os cursos do seed foram gravados só no diretório temporário; backend/courses não mudou
  A1 os números por turma (turma-row/name/enrolled/pending/capacity) e os turma-unassigned de cada curso batem
     com GET /api/dashboard/cursos e com o seed (Alfa 0/0 cap 1; Beta 0/0 sem cap; curso A sem turma 2/1; curso B 0/0)
  B1 Gestão cria a turma "Turma Gama" (início, capacidade 5) pela tela; ela aparece com 0/0 e capacidade 5 e a API
     (GET /api/admin/classes) a tem com os mesmos valores
  B2 nome repetido no mesmo curso: turma-error com o texto exato "Já existe uma turma com esse nome neste curso.",
     sem turma nova na tela nem na API
  C1 Gestão escolhe o curso A: uma enrollment-row por matrícula (API), cada uma com enrollment-class-select
     ("Sem turma" selecionado + as turmas do curso); atribui a matrícula ativa 1 à "Turma Alfa" sem recarregar:
     turma-enrolled da Alfa e turma-unassigned do curso mudam; API confirma class_id
  C2 atribuir a matrícula ativa 2 à "Turma Alfa" (capacidade 1, cheia): turma-error "A turma está cheia.", a
     matrícula continua sem turma (API e select) e os números não mudam
  C3 voltar a matrícula 1 para "Sem turma": Alfa volta a 0/0, turma-unassigned volta a 2/1, API class_id nulo
  C4 matrícula pendente 3 -> "Turma Beta" (pending 1, sem capacidade) e matrícula ativa 2 -> "Turma Alfa" (agora
     cabe): números e turma-unassigned conferem com a API depois de cada passo, sem recarregar
  P1 as enrollment-row não mostram texto de pagamento (R$, valor, referência externa, id do pagamento, status do
     pagamento) e GET /api/admin/enrollments não tem campo de pagamento
  D1 persistência: recarregar a página mantém os números (Alfa 1/0 cap 1; Beta 0/1 sem cap; sem turma 1/0) e os
     selects das matrículas voltam a mostrar a turma salva
  E1 trilha de auditoria (aba "Auditoria", audit-row): 3 class.create (Alfa e Beta pelo gestor 2, Gama pelo gestor 1)
     e exatamente 4 enrollment.class_change do gestor 1 (a tentativa recusada por turma cheia não gera evento), com
     o gestor certo em audit-actor e as mudanças de class_id em audit-change
  R1 suporte: vê os turma-* (números conferem com a API) mas nenhuma seção de gestão; API de escrita 403;
     GET /api/admin/enrollments 200 (Suporte pode ler)
  R2 financeiro: idem; GET /api/admin/enrollments 403
  R3 sem token e com token forjado: 401 nas rotas de escrita de turma
  K1 sem erros de console (400, 404 em /api, 5xx) nem exceções de página, e nenhuma resposta de 401/403 nas rotas
     de turma/matrícula; os ÚNICOS 409/422 permitidos são os dois provocados de propósito (B2: POST /classes 409;
     C2: PUT /enrollments/{id}/class 409), e o teste confere que ocorreram

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e8.py (Groq e Mercado Pago falsos, banco SQLite temporário, diretório de
    cursos temporário, dois gestores, suporte e financeiro). O backend/db.sqlite e o backend/courses de
    desenvolvimento não são abertos nem alterados.
  - Frontend: `npx ng serve` numa porta livre própria, com proxy temporário /api -> backend de teste.
  - Seed só pela API: dois cursos (POST /api/admin/create-course), 3 alunos com checkout falso (webhook assinado
    ativa 2 e deixa 1 pendente), turmas "Turma Alfa" (capacidade 1) e "Turma Beta" (sem capacidade) criadas pelo
    gestor 2 pela API. As ações da tela são do gestor 1 (admin.e5@teste.com).

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas: E2E_BACKEND_PORT / E2E_FRONT_PORT para fixar.
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_l1_turmas_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402
from apoio_webhook_mp import enviar_webhook, id_de_pagamento  # noqa: E402
from servidor_e2e_e8 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTOR2_EMAIL, GESTOR2_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)
# Utilitários de harness e de seed já usados pelos e2e do chat e da auditoria (somente leitura, não alterados).
from test_e5_chat_aluno_angular import (  # noqa: E402
    ERRO_HTTP, Falha, FRONTEND, REPO, TIMEOUT, _api, _encerrar, _esperar_http, _iniciar,
    _porta_livre, login_na_tela, semear_aluno,
)
from test_e8_auditoria_angular import (  # noqa: E402
    abas_visiveis, checar_alteracoes_da_linha, checar_responsavel, imprimir, linhas_da_tela, norm,
    snapshot_de_cursos, texto_do_responsavel, token_de_funcionario,
)

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_turmas"))

CURSO_A = "curso-l1-a"
CURSO_B = "curso-l1-b"
NOME_A = "Curso L1 A"
NOME_B = "Curso L1 B"
PRECO_A = 100
PRECO_B = 200
ALFA = "Turma Alfa"
BETA = "Turma Beta"
GAMA = "Turma Gama"
INICIO_GAMA = "2027-01-15"
CAPACIDADE_GAMA = 5
SEM_TURMA = "Sem turma"
ERRO_DUPLICADA = "Já existe uma turma com esse nome neste curso."
ERRO_CHEIA = "A turma está cheia."
TRACO = "—"

ABA_CURSOS = re.compile(r"^\s*Cursos\s*$")
ABA_AUDITORIA = re.compile(r"^\s*Auditoria\s*$")
TITULO_TABELA = "Performance do catálogo"
TITULO_GRAFICO = "Inscritos por curso"
TITULO_GESTAO = "Gerenciar turmas"

SEL_ROW = '[data-testid="turma-row"]'
SEL_UNASSIGNED = '[data-testid="turma-unassigned"]'
SEL_CURSO = '[data-testid="turma-new-course"]'
SEL_NOME = '[data-testid="turma-new-name"]'
SEL_INICIO = '[data-testid="turma-new-start"]'
SEL_CAPACIDADE = '[data-testid="turma-new-capacity"]'
SEL_CRIAR = '[data-testid="turma-create"]'
SEL_MATRICULA = '[data-testid="enrollment-row"]'
SEL_SELECT = '[data-testid="enrollment-class-select"]'
SEL_ERRO = '[data-testid="turma-error"]'
SEL_AUDIT_ROW = '[data-testid="audit-row"]'
SELETORES_DE_GESTAO = [SEL_CURSO, SEL_NOME, SEL_INICIO, SEL_CAPACIDADE, SEL_CRIAR, SEL_MATRICULA, SEL_SELECT,
                       SEL_ERRO]

LER_LINHAS = """els => els.map(e => {
  const g = id => Array.from(e.querySelectorAll('[data-testid="' + id + '"]')).map(x => x.innerText);
  return {nome: g('turma-name'), ativos: g('turma-enrolled'), pend: g('turma-pending'), cap: g('turma-capacity')};
})"""


# ---------------------------------------------------------------------------------------------
# Servidores e navegador
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servidores():
    """Sobe o backend de teste (cursos isolados, gestores) e o Angular; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_l1_"))
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
# Auxiliares de API (seed e conferências no servidor)
# ---------------------------------------------------------------------------------------------

def corpo_do_curso(curso_id, nome, preco):
    return {
        "id": curso_id, "name": nome, "description": "Descrição do curso L1", "price": preco,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Público do curso L1",
        "objectives": ["Objetivo 1"], "topics": ["Tópico 1"], "benefits": ["Benefício 1"],
        "faq": [{"question": "Pergunta?", "answer": "Resposta."}], "system_prompt": "Prompt do curso L1",
        "materials": [],
    }


def dashboard_da_api(api, token):
    status, corpo = _api(api, "GET", "/api/dashboard/cursos", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/dashboard/cursos respondeu HTTP {status}")
    return corpo


def turmas_da_api(api, token, curso_id):
    status, corpo = _api(api, "GET", f"/api/admin/classes?course_id={curso_id}", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/classes respondeu HTTP {status}")
    return corpo["classes"]


def matriculas_da_api(api, token, curso_id):
    status, corpo = _api(api, "GET", f"/api/admin/enrollments?course_id={curso_id}", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/enrollments respondeu HTTP {status}")
    return corpo["enrollments"]


def eventos_da_api(api, token):
    status, corpo = _api(api, "GET", "/api/admin/audit-logs", token=token)
    if status != 200:
        raise RuntimeError(f"GET /api/admin/audit-logs respondeu HTTP {status}")
    return corpo["logs"]


def id_da_turma(api, token, nome):
    achadas = [t for t in turmas_da_api(api, token, CURSO_A) if t["name"] == nome]
    if len(achadas) != 1:
        raise Falha(f"a API tem {len(achadas)} turmas chamadas {nome!r} no curso A (esperado 1)")
    return achadas[0]["id"]


def class_id_da_matricula(api, token, matricula_id):
    achadas = [m for m in matriculas_da_api(api, token, CURSO_A) if m["id"] == matricula_id]
    if len(achadas) != 1:
        raise Falha(f"matrícula {matricula_id} não está (ou está repetida) em GET /enrollments")
    return achadas[0]["class_id"]


# ---------------------------------------------------------------------------------------------
# Auxiliares de tela
# ---------------------------------------------------------------------------------------------

def esperar(fn, rotulo, limite=6.0):
    """Repete fn() até devolver None (ok); uma string é o motivo da divergência. Estoura em Falha."""
    fim = time.time() + limite
    ultimo = "sem leitura"
    while True:
        try:
            ultimo = fn()
        except sync_api.Error as erro:
            ultimo = f"erro do navegador: {str(erro).splitlines()[0] if str(erro) else type(erro).__name__}"
        if ultimo is None:
            return
        if time.time() > fim:
            raise Falha(f"{rotulo}: {ultimo}")
        time.sleep(0.25)


def aguardar_visivel(locator, rotulo, descricao):
    try:
        locator.first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: {descricao} não apareceu na tela")


def abrir_aba(page, base, email, senha, aba, rotulo):
    """Login de funcionário em /, vai a /admin e abre a aba pedida."""
    login_na_tela(page, base, email, senha, rotulo)
    try:
        page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /admin)")
    page.wait_for_load_state("networkidle")
    clicar_aba(page, aba, rotulo)


def clicar_aba(page, aba, rotulo):
    try:
        page.locator("ul.nav-tabs button", has_text=aba).first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: a aba {aba.pattern!r} não existe em /admin")
    page.wait_for_load_state("networkidle")


def abrir_cursos(page, base, email, senha, rotulo):
    abrir_aba(page, base, email, senha, ABA_CURSOS, rotulo)
    esperar_aba_cursos(page, rotulo)


def esperar_aba_cursos(page, rotulo):
    """A aba Cursos carregou: gráfico, tabela do catálogo e os dois cursos do seed."""
    aguardar_visivel(page.get_by_text(TITULO_TABELA, exact=True), rotulo, f"título {TITULO_TABELA!r}")
    aguardar_visivel(page.get_by_text(TITULO_GRAFICO, exact=True), rotulo, f"título {TITULO_GRAFICO!r}")
    aguardar_visivel(page.locator("canvas"), rotulo, "gráfico (canvas)")
    for nome in (NOME_A, NOME_B):
        aguardar_visivel(page.locator("table tbody tr", has_text=nome), rotulo,
                         f"linha do curso {nome!r} na tabela do catálogo")
    page.wait_for_load_state("networkidle")


def um_inteiro(texto):
    numeros = re.findall(r"\d+", texto or "")
    return int(numeros[0]) if len(numeros) == 1 else None


def comparar_numeros(page, dash):
    """None se a tela confere com `dash` (GET /api/dashboard/cursos); senão, o motivo da divergência."""
    esperadas = [(c, t) for c in dash["courses"] for t in c["classes"]]
    linhas = page.eval_on_selector_all(SEL_ROW, LER_LINHAS)
    if len(linhas) != len(esperadas):
        return (f"{len(linhas)} elementos {SEL_ROW} na tela, a API tem {len(esperadas)} turmas "
                f"({[t['name'] for _, t in esperadas]})")
    por_nome = {}
    for linha in linhas:
        for chave in ("nome", "ativos", "pend", "cap"):
            if len(linha[chave]) != 1:
                return f"turma-row com {len(linha[chave])} elementos de '{chave}' (esperado 1): {linha}"
        nome = norm(linha["nome"][0])
        if nome in por_nome:
            return f"turma {nome!r} aparece mais de uma vez na tela"
        por_nome[nome] = linha
    for curso, turma in esperadas:
        linha = por_nome.get(turma["name"])
        if linha is None:
            return f"turma {turma['name']!r} (curso {curso['id']}) não está na tela; há {sorted(por_nome)}"
        ativos, pend = um_inteiro(linha["ativos"][0]), um_inteiro(linha["pend"][0])
        if ativos != turma["enrolled"]:
            return (f"{turma['name']}: turma-enrolled {linha['ativos'][0]!r}, a API tem {turma['enrolled']} "
                    f"matrículas ativas")
        if pend != turma["pending"]:
            return f"{turma['name']}: turma-pending {linha['pend'][0]!r}, a API tem {turma['pending']}"
        capacidade = norm(linha["cap"][0])
        if turma["capacity"] is None:
            if capacidade != TRACO:
                return f"{turma['name']}: sem capacidade na API, turma-capacity mostra {capacidade!r} (esperado '—')"
        elif um_inteiro(capacidade) != turma["capacity"]:
            return f"{turma['name']}: turma-capacity {capacidade!r}, a API tem {turma['capacity']}"
    sem_turma = page.eval_on_selector_all(SEL_UNASSIGNED, "els => els.map(e => e.innerText)")
    if len(sem_turma) != len(dash["courses"]):
        return f"{len(sem_turma)} elementos turma-unassigned, a API tem {len(dash['courses'])} cursos"
    for curso, texto in zip(dash["courses"], sem_turma):
        numeros = re.findall(r"\d+", texto)
        if len(numeros) != 2 or "/" not in texto:
            return f"turma-unassigned do curso {curso['id']} mostra {norm(texto)!r} (esperado 'ativos/pendentes ...')"
        esperado = (curso["unassigned"]["active"], curso["unassigned"]["pending"])
        if (int(numeros[0]), int(numeros[1])) != esperado:
            return (f"turma-unassigned do curso {curso['id']} mostra {norm(texto)!r}, a API tem "
                    f"{esperado[0]}/{esperado[1]} (ativos/pendentes)")
    return None


def conferir_numeros(page, api, token, rotulo, limite=6.0):
    def leitura():
        return comparar_numeros(page, dashboard_da_api(api, token))
    esperar(leitura, rotulo, limite)


def sem_turma_do_curso_a(api, token):
    dash = dashboard_da_api(api, token)
    curso = next(c for c in dash["courses"] if c["id"] == CURSO_A)
    return curso["unassigned"]["active"], curso["unassigned"]["pending"]


def opcoes_do_select(select):
    return select.evaluate("e => Array.from(e.options).map(o => o.text)")


def opcao_selecionada(select):
    return norm(select.evaluate("e => e.options[e.selectedIndex] ? e.options[e.selectedIndex].text : ''"))


def escolher_curso_na_gestao(page, curso_id, curso_nome, rotulo):
    """Escolhe o curso no turma-new-course (o mesmo select define o curso da nova turma e a lista de matrículas)."""
    select = page.locator(SEL_CURSO)
    aguardar_visivel(select, rotulo, f"seção '{TITULO_GESTAO}' (select {SEL_CURSO})")
    pares = select.first.evaluate("e => Array.from(e.options).map(o => [o.value, o.text])")
    indice = next((i for i, (valor, texto) in enumerate(pares) if curso_nome in texto or curso_id in valor), None)
    if indice is None:
        raise Falha(f"{rotulo}: o select de curso não tem a opção do curso {curso_nome!r}: {pares}")
    select.first.select_option(index=indice)
    page.wait_for_load_state("networkidle")


def preencher_nova_turma(page, nome, inicio, capacidade, rotulo):
    try:
        page.locator(SEL_NOME).first.fill(nome, timeout=TIMEOUT)
        page.locator(SEL_INICIO).first.fill(inicio, timeout=TIMEOUT)
        page.locator(SEL_CAPACIDADE).first.fill(str(capacidade), timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: campos {SEL_NOME}, {SEL_INICIO} e {SEL_CAPACIDADE} não encontrados")


def clicar_criar(page, rotulo):
    try:
        page.locator(SEL_CRIAR).first.click(timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: botão {SEL_CRIAR} não encontrado ou não clicável")


def texto_do_erro(page):
    alvo = page.locator(SEL_ERRO)
    return norm(alvo.first.inner_text()) if alvo.count() and alvo.first.is_visible() else None


def esperar_erro(page, esperado, rotulo):
    def leitura():
        atual = texto_do_erro(page)
        if atual is None:
            return f"nenhum elemento visível {SEL_ERRO} (esperado {esperado!r})"
        if atual != esperado:
            return f"{SEL_ERRO} mostra {atual!r}, esperado exatamente {esperado!r}"
        return None
    esperar(leitura, rotulo)


def linhas_de_matricula(page, rotulo):
    linhas = page.locator(SEL_MATRICULA)
    aguardar_visivel(linhas, rotulo, f"nenhuma {SEL_MATRICULA}")
    return linhas


def linha_do_aluno(page, aluno, rotulo):
    linhas = linhas_de_matricula(page, rotulo)
    achadas = [i for i in range(linhas.count())
               if aluno["email"] in linhas.nth(i).inner_text() or aluno["nome"] in linhas.nth(i).inner_text()]
    if len(achadas) != 1:
        raise Falha(f"{rotulo}: {len(achadas)} enrollment-row mostram o aluno {aluno['nome']} / {aluno['email']} "
                    f"(esperado 1); linhas: {[norm(linhas.nth(i).inner_text()) for i in range(linhas.count())]}")
    return linhas.nth(achadas[0])


def select_da_linha(linha, rotulo):
    select = linha.locator(SEL_SELECT)
    if select.count() != 1:
        raise Falha(f"{rotulo}: a enrollment-row tem {select.count()} {SEL_SELECT} (esperado 1)")
    return select.first


def atribuir_pela_tela(page, aluno, destino, rotulo):
    """Escolhe no select da matrícula do aluno a opção `destino` (nome da turma ou 'Sem turma')."""
    select = select_da_linha(linha_do_aluno(page, aluno, rotulo), rotulo)
    opcoes = opcoes_do_select(select)
    indice = next((i for i, texto in enumerate(opcoes) if destino in texto), None)
    if indice is None:
        raise Falha(f"{rotulo}: o select da matrícula de {aluno['nome']} não tem a opção {destino!r}: {opcoes}")
    select.select_option(index=indice)


def esperar_api_class_id(api, token, aluno, esperado, rotulo):
    def leitura():
        atual = class_id_da_matricula(api, token, aluno["matricula"])
        return None if atual == esperado else f"API: class_id da matrícula de {aluno['nome']} é {atual}, esperado {esperado}"
    esperar(leitura, rotulo)


def exigir_marca(page, rotulo):
    if page.evaluate("() => window.__l1_marca") != 42:
        raise Falha(f"{rotulo}: a página foi recarregada (a atribuição deveria atualizar a tela sem recarregar)")


def test_l1_turmas_angular_e2e(servidores, browser):
    base = servidores["base"]
    api = servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_inesperados = []
    provocados = []
    contextos = []
    estado = {"page": None}
    paginas = {}

    # --- seed pela API pública/administrativa do backend de teste ------------------------
    seed = {"ok": False, "erro": ""}
    dados = {"alunos": {}, "refs": [], "mp_ids": []}
    try:
        token_g1 = token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        token_g2 = token_de_funcionario(api, GESTOR2_EMAIL, GESTOR2_SENHA)
        token_sup = token_de_funcionario(api, SUPORTE_EMAIL, SUPORTE_SENHA)
        token_fin = token_de_funcionario(api, FINANCEIRO_EMAIL, FINANCEIRO_SENHA)
        dados.update(token_g1=token_g1, token_g2=token_g2, token_sup=token_sup, token_fin=token_fin)

        for curso_id, nome, preco in ((CURSO_A, NOME_A, PRECO_A), (CURSO_B, NOME_B, PRECO_B)):
            status, _ = _api(api, "POST", "/api/admin/create-course", corpo_do_curso(curso_id, nome, preco),
                             token=token_g1)
            if status != 200:
                raise RuntimeError(f"seed: create-course {curso_id} respondeu HTTP {status}")

        # 3 alunos no curso A: os dois primeiros pagam (webhook assinado -> active), o terceiro fica pending
        for tag, paga in (("l1a", True), ("l1b", True), ("l1c", False)):
            email, _token_aluno = semear_aluno(api, tag)
            status, corpo = _api(api, "POST", "/api/payments/create-checkout",
                                 {"course_id": CURSO_A, "payer": {"name": f"Aluno L1 {tag}", "email": email}})
            if status != 200 or not (corpo or {}).get("external_reference"):
                raise RuntimeError(f"seed: create-checkout de {tag} respondeu HTTP {status}")
            referencia = corpo["external_reference"]
            dados["refs"].append(referencia)
            dados["mp_ids"].append(id_de_pagamento(referencia))
            if paga:
                status, _ = enviar_webhook(api, referencia)
                if status != 200:
                    raise RuntimeError(f"seed: webhook de {tag} respondeu HTTP {status}")
            dados["alunos"][tag] = {"email": email, "esperado": "active" if paga else "pending"}

        matriculas = matriculas_da_api(api, token_g1, CURSO_A)
        for tag, aluno in dados["alunos"].items():
            achadas = [m for m in matriculas if m["student_email"] == aluno["email"]]
            if len(achadas) != 1 or achadas[0]["status"] != aluno["esperado"]:
                raise RuntimeError(f"seed: matrícula de {tag} inesperada: {achadas} (esperado {aluno['esperado']})")
            aluno.update(matricula=achadas[0]["id"], nome=achadas[0]["student_name"])
        if len(matriculas) != 3:
            raise RuntimeError(f"seed: {len(matriculas)} matrículas no curso A (esperado 3)")

        # turmas do seed, criadas pelo gestor 2 pela API (as ações da tela serão do gestor 1)
        for nome, extra in ((ALFA, {"starts_on": "2026-11-01", "capacity": 1}), (BETA, {"starts_on": "2026-12-01"})):
            status, _ = _api(api, "POST", "/api/admin/classes", {"course_id": CURSO_A, "name": nome, **extra},
                             token=token_g2)
            if status != 200:
                raise RuntimeError(f"seed: POST /classes {nome} respondeu HTTP {status}")

        dash = dashboard_da_api(api, token_g1)
        ids = [c["id"] for c in dash["courses"]]
        if sorted(ids) != sorted([CURSO_A, CURSO_B]):
            raise RuntimeError(f"seed: o dashboard de cursos lista {ids}, esperado só os dois cursos do seed")
        curso_a = next(c for c in dash["courses"] if c["id"] == CURSO_A)
        curso_b = next(c for c in dash["courses"] if c["id"] == CURSO_B)
        resumo = {t["name"]: (t["enrolled"], t["pending"], t["capacity"]) for t in curso_a["classes"]}
        if resumo != {ALFA: (0, 0, 1), BETA: (0, 0, None)}:
            raise RuntimeError(f"seed: turmas do curso A inesperadas no dashboard: {resumo}")
        if (curso_a["unassigned"]["active"], curso_a["unassigned"]["pending"]) != (2, 1):
            raise RuntimeError(f"seed: sem turma do curso A inesperado: {curso_a['unassigned']}")
        if curso_b["classes"] != [] or (curso_b["unassigned"]["active"], curso_b["unassigned"]["pending"]) != (0, 0):
            raise RuntimeError(f"seed: curso B deveria estar sem turma e sem matrícula: {curso_b}")
        dados["id_alfa"] = id_da_turma(api, token_g1, ALFA)
        dados["id_beta"] = id_da_turma(api, token_g1, BETA)
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
            if codigo == 400 or codigo >= 500 or (codigo == 404 and "/api/" in url):
                erros_inesperados.append(f"{rotulo}: console: {msg.text} [{url}]")

        def ao_response(resposta):
            url = resposta.url
            if "/api/" not in url:
                return
            codigo = resposta.status
            metodo = resposta.request.method
            caminho = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
            if codigo in (409, 422):
                provocados.append((rotulo, metodo, caminho, codigo))
            elif codigo == 400 or codigo >= 500 or codigo == 404:
                erros_inesperados.append(f"{rotulo}: {metodo} {caminho} respondeu HTTP {codigo}")
            elif codigo in (401, 403) and ("/classes" in caminho or "/enrollments" in caminho):
                erros_inesperados.append(f"{rotulo}: {metodo} {caminho} respondeu HTTP {codigo}")

        page.on("console", ao_console)
        page.on("response", ao_response)
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

    def gestor_na_aba_cursos(rotulo):
        """Página do gestor, garantidamente na aba Cursos (clicar na aba já ativa não recarrega a página)."""
        page = tela_gestor()
        clicar_aba(page, ABA_CURSOS, rotulo)
        esperar_aba_cursos(page, rotulo)
        return page

    def aluno(tag):
        return dados["alunos"][tag]

    a1_, a2_, a3_ = "l1a", "l1b", "l1c"  # a1_ e a2_ ativos, a3_ pendente

    # --- S1 ---------------------------------------------------------------------------
    def s1():
        page = nova_pagina("S-gestor")
        paginas["gestor"] = page
        abrir_cursos(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "pré-condição gestor")

    cenario("S1", "pré-condição: gestor abre a aba Cursos e vê gráfico, tabela do catálogo e os cursos do seed", s1)

    # --- I1 ---------------------------------------------------------------------------
    def i1():
        cursos_tmp = servidores["cursos_tmp"]
        for curso_id in (CURSO_A, CURSO_B):
            if not (cursos_tmp / f"{curso_id}.json").exists():
                raise Falha(f"I1: o curso {curso_id} do seed não foi gravado em {cursos_tmp} (isolamento falhou)")
            if (REPO / "backend" / "courses" / f"{curso_id}.json").exists():
                raise Falha(f"I1: o curso {curso_id} do seed apareceu em backend/courses")
        if snapshot_de_cursos() != servidores["cursos_antes"]:
            raise Falha("I1: backend/courses mudou durante o teste (o teste não pode alterar esse diretório)")

    cenario("I1", "isolamento: cursos do seed só no diretório temporário; backend/courses intacto", i1)

    # --- A1 ---------------------------------------------------------------------------
    def a1():
        page = gestor_na_aba_cursos("A1")
        conferir_numeros(page, api, dados["token_g1"], "A1")
        # o seed conhecido (não só "igual à API"): Alfa 0/0 cap 1, Beta 0/0 sem cap; curso A sem turma 2/1; curso B 0/0
        linhas = page.eval_on_selector_all(SEL_ROW, LER_LINHAS)
        nomes = sorted(norm(l["nome"][0]) for l in linhas if l["nome"])
        if nomes != sorted([ALFA, BETA]):
            raise Falha(f"A1: turmas na tela {nomes}, esperado {sorted([ALFA, BETA])}")
        ordem = [c["id"] for c in dashboard_da_api(api, dados["token_g1"])["courses"]]
        textos = page.eval_on_selector_all(SEL_UNASSIGNED, "els => els.map(e => e.innerText)")
        por_curso = {curso: tuple(int(n) for n in re.findall(r"\d+", texto)) for curso, texto in zip(ordem, textos)}
        if por_curso.get(CURSO_A) != (2, 1) or por_curso.get(CURSO_B) != (0, 0):
            raise Falha(f"A1: turma-unassigned por curso {por_curso}, esperado {CURSO_A}=(2, 1) e {CURSO_B}=(0, 0)")

    cenario("A1", "números por turma e turma-unassigned de cada curso batem com GET /api/dashboard/cursos e o seed", a1)

    # --- B1 / B2 ----------------------------------------------------------------------
    def b1():
        page = gestor_na_aba_cursos("B1")
        escolher_curso_na_gestao(page, CURSO_A, NOME_A, "B1")
        preencher_nova_turma(page, GAMA, INICIO_GAMA, CAPACIDADE_GAMA, "B1")
        clicar_criar(page, "B1")
        linha = page.locator(SEL_ROW, has=page.locator('[data-testid="turma-name"]', has_text=GAMA))
        aguardar_visivel(linha, "B1", f"a turma {GAMA!r} (turma-row) depois de criar")
        gama = next((t for t in turmas_da_api(api, dados["token_g1"], CURSO_A) if t["name"] == GAMA), None)
        if gama is None:
            raise Falha(f"B1: a API não tem a turma {GAMA!r} depois do clique em {SEL_CRIAR}")
        if (gama["capacity"], gama["starts_on"], gama["enrolled"], gama["pending"]) != (
                CAPACIDADE_GAMA, INICIO_GAMA, 0, 0):
            raise Falha(f"B1: a turma criada na API tem {gama}")
        dados["id_gama"] = gama["id"]
        conferir_numeros(page, api, dados["token_g1"], "B1")
        texto = norm(linha.first.inner_text())
        if linha.first.locator('[data-testid="turma-enrolled"]').inner_text().strip() != "0" or \
                linha.first.locator('[data-testid="turma-pending"]').inner_text().strip() != "0":
            raise Falha(f"B1: a turma nova não aparece com 0 ativos e 0 pendentes: {texto!r}")
        if um_inteiro(linha.first.locator('[data-testid="turma-capacity"]').inner_text()) != CAPACIDADE_GAMA:
            raise Falha(f"B1: capacidade da turma nova na tela não é {CAPACIDADE_GAMA}: {texto!r}")

    def b2():
        page = gestor_na_aba_cursos("B2")
        antes_tela = page.locator(SEL_ROW).count()
        antes_api = len(turmas_da_api(api, dados["token_g1"], CURSO_A))
        escolher_curso_na_gestao(page, CURSO_A, NOME_A, "B2")
        preencher_nova_turma(page, GAMA, INICIO_GAMA, CAPACIDADE_GAMA, "B2")
        clicar_criar(page, "B2")
        esperar_erro(page, ERRO_DUPLICADA, "B2")
        if len(turmas_da_api(api, dados["token_g1"], CURSO_A)) != antes_api:
            raise Falha("B2: o nome repetido criou uma turma na API")
        if page.locator(SEL_ROW).count() != antes_tela:
            raise Falha(f"B2: o nome repetido mudou a quantidade de turma-row ({antes_tela} -> "
                        f"{page.locator(SEL_ROW).count()})")
        conferir_numeros(page, api, dados["token_g1"], "B2")

    cenario("B1", "Gestão cria 'Turma Gama' (início, capacidade 5) pela tela; aparece 0/0 e a API a tem", b1)
    cenario("B2", "nome repetido no curso: turma-error com o texto exato; nada criado", b2)

    # --- C1..C4 -----------------------------------------------------------------------
    def preparar_matriculas(rotulo):
        page = gestor_na_aba_cursos(rotulo)
        escolher_curso_na_gestao(page, CURSO_A, NOME_A, rotulo)
        linhas = linhas_de_matricula(page, rotulo)
        esperadas = len(matriculas_da_api(api, dados["token_g1"], CURSO_A))
        esperar(lambda: None if linhas.count() == esperadas
                else f"{linhas.count()} {SEL_MATRICULA} na tela, a API tem {esperadas} matrículas do curso A",
                rotulo)
        page.evaluate("() => { window.__l1_marca = 42; }")
        return page

    def c1():
        page = preparar_matriculas("C1")
        # uma enrollment-row por matrícula, com o select ("Sem turma" selecionado + turmas do curso)
        nomes_turmas = [t["name"] for t in turmas_da_api(api, dados["token_g1"], CURSO_A)]
        for tag in (a1_, a2_, a3_):
            select = select_da_linha(linha_do_aluno(page, aluno(tag), "C1"), "C1")
            opcoes = opcoes_do_select(select)
            if not any(SEM_TURMA in o for o in opcoes):
                raise Falha(f"C1: o select da matrícula de {tag} não tem a opção {SEM_TURMA!r}: {opcoes}")
            for nome in nomes_turmas:
                if not any(nome in o for o in opcoes):
                    raise Falha(f"C1: o select da matrícula de {tag} não lista a turma {nome!r}: {opcoes}")
            if SEM_TURMA not in opcao_selecionada(select):
                raise Falha(f"C1: matrícula de {tag} sem turma mostra {opcao_selecionada(select)!r} selecionado")
        atribuir_pela_tela(page, aluno(a1_), ALFA, "C1")
        esperar_api_class_id(api, dados["token_g1"], aluno(a1_), dados["id_alfa"], "C1")
        conferir_numeros(page, api, dados["token_g1"], "C1")
        linha_alfa = page.locator(SEL_ROW, has=page.locator('[data-testid="turma-name"]', has_text=ALFA)).first
        if um_inteiro(linha_alfa.locator('[data-testid="turma-enrolled"]').inner_text()) != 1:
            raise Falha("C1: depois de atribuir a matrícula ativa, turma-enrolled da Alfa não é 1")
        if sem_turma_do_curso_a(api, dados["token_g1"]) != (1, 1):
            raise Falha(f"C1: a API deveria ter 1/1 sem turma no curso A: {sem_turma_do_curso_a(api, dados['token_g1'])}")
        if SEM_TURMA in opcao_selecionada(select_da_linha(linha_do_aluno(page, aluno(a1_), "C1"), "C1")):
            raise Falha("C1: o select da matrícula atribuída ainda mostra 'Sem turma'")
        exigir_marca(page, "C1")

    def c2():
        page = preparar_matriculas("C2")
        numeros_antes = sem_turma_do_curso_a(api, dados["token_g1"])
        atribuir_pela_tela(page, aluno(a2_), ALFA, "C2")
        esperar_erro(page, ERRO_CHEIA, "C2")
        if class_id_da_matricula(api, dados["token_g1"], aluno(a2_)["matricula"]) is not None:
            raise Falha("C2: a matrícula 2 recebeu turma na API mesmo com a turma cheia")
        conferir_numeros(page, api, dados["token_g1"], "C2")
        if sem_turma_do_curso_a(api, dados["token_g1"]) != numeros_antes:
            raise Falha("C2: os números sem turma do curso A mudaram com a atribuição recusada")
        select = select_da_linha(linha_do_aluno(page, aluno(a2_), "C2"), "C2")
        esperar(lambda: None if SEM_TURMA in opcao_selecionada(select)
                else f"depois da recusa o select da matrícula 2 mostra {opcao_selecionada(select)!r} (esperado "
                     f"{SEM_TURMA!r})", "C2")
        exigir_marca(page, "C2")

    def c3():
        page = preparar_matriculas("C3")
        atribuir_pela_tela(page, aluno(a1_), SEM_TURMA, "C3")
        esperar_api_class_id(api, dados["token_g1"], aluno(a1_), None, "C3")
        conferir_numeros(page, api, dados["token_g1"], "C3")
        if sem_turma_do_curso_a(api, dados["token_g1"]) != (2, 1):
            raise Falha("C3: a API deveria voltar a 2/1 sem turma no curso A")
        linha_alfa = page.locator(SEL_ROW, has=page.locator('[data-testid="turma-name"]', has_text=ALFA)).first
        if um_inteiro(linha_alfa.locator('[data-testid="turma-enrolled"]').inner_text()) != 0:
            raise Falha("C3: depois de voltar para 'Sem turma', turma-enrolled da Alfa não voltou a 0")
        exigir_marca(page, "C3")

    def c4():
        page = preparar_matriculas("C4")
        atribuir_pela_tela(page, aluno(a3_), BETA, "C4")
        esperar_api_class_id(api, dados["token_g1"], aluno(a3_), dados["id_beta"], "C4")
        conferir_numeros(page, api, dados["token_g1"], "C4 (pendente na Beta)")
        linha_beta = page.locator(SEL_ROW, has=page.locator('[data-testid="turma-name"]', has_text=BETA)).first
        if um_inteiro(linha_beta.locator('[data-testid="turma-pending"]').inner_text()) != 1 or \
                um_inteiro(linha_beta.locator('[data-testid="turma-enrolled"]').inner_text()) != 0:
            raise Falha("C4: a matrícula pendente atribuída à Beta deveria dar turma-pending 1 e turma-enrolled 0")
        if sem_turma_do_curso_a(api, dados["token_g1"]) != (2, 0):
            raise Falha("C4: a API deveria ter 2/0 sem turma no curso A depois da pendente ir para a Beta")
        atribuir_pela_tela(page, aluno(a2_), ALFA, "C4")
        esperar_api_class_id(api, dados["token_g1"], aluno(a2_), dados["id_alfa"], "C4")
        conferir_numeros(page, api, dados["token_g1"], "C4 (ativa na Alfa)")
        if sem_turma_do_curso_a(api, dados["token_g1"]) != (1, 0):
            raise Falha("C4: a API deveria ter 1/0 sem turma no curso A no fim")
        exigir_marca(page, "C4")

    cenario("C1", "atribui matrícula ativa 1 à Alfa pelo select, sem recarregar; números e turma-unassigned mudam", c1)
    cenario("C2", "atribuir a 2ª à Alfa (capacidade 1): 'A turma está cheia.'; nada muda na API nem no select", c2)
    cenario("C3", "voltar a matrícula 1 para 'Sem turma': Alfa 0/0, sem turma 2/1", c3)
    cenario("C4", "pendente 3 -> Beta (pending 1) e ativa 2 -> Alfa (agora cabe); números conferem a cada passo", c4)

    # --- P1 ---------------------------------------------------------------------------
    def p1():
        page = preparar_matriculas("P1")
        linhas = linhas_de_matricula(page, "P1")
        textos = [norm(linhas.nth(i).inner_text()) for i in range(linhas.count())]
        if len(textos) != 3:
            raise Falha(f"P1: {len(textos)} enrollment-row, esperado 3")
        proibidos = ["R$", "$", "external_reference", "approved", "aprovado", "payment", "valor", "100,00", "100.00"]
        proibidos += dados["refs"] + dados["mp_ids"]
        for texto in textos:
            for item in proibidos:
                if item.lower() in texto.lower():
                    raise Falha(f"P1: a enrollment-row mostra texto de pagamento {item!r}: {texto!r}")
        status, corpo = _api(api, "GET", f"/api/admin/enrollments?course_id={CURSO_A}", token=dados["token_g1"])
        chaves = {k for m in corpo["enrollments"] for k in m}
        suspeitas = [k for k in chaves if any(p in k.lower() for p in ("pay", "amount", "price", "refer", "valor"))]
        if suspeitas:
            raise Falha(f"P1: GET /api/admin/enrollments tem campos de pagamento: {suspeitas}")

    cenario("P1", "enrollment-row sem texto de pagamento (valor, referência); API de matrículas sem campo de pagamento", p1)

    # --- D1 ---------------------------------------------------------------------------
    def d1():
        page = tela_gestor()
        page.reload(wait_until="networkidle")
        clicar_aba(page, ABA_CURSOS, "D1")
        esperar_aba_cursos(page, "D1")
        conferir_numeros(page, api, dados["token_g1"], "D1")
        linhas = {norm(l["nome"][0]): l for l in page.eval_on_selector_all(SEL_ROW, LER_LINHAS)}
        esperado = {ALFA: (1, 0, "1"), BETA: (0, 1, TRACO), GAMA: (0, 0, str(CAPACIDADE_GAMA))}
        for nome, (ativos, pend, cap) in esperado.items():
            linha = linhas.get(nome)
            if linha is None:
                raise Falha(f"D1: depois de recarregar a turma {nome!r} sumiu da tela; há {sorted(linhas)}")
            lido = (um_inteiro(linha["ativos"][0]), um_inteiro(linha["pend"][0]), norm(linha["cap"][0]))
            if lido[0] != ativos or lido[1] != pend or (lido[2] != cap if cap == TRACO else um_inteiro(lido[2]) != int(cap)):
                raise Falha(f"D1: {nome} depois de recarregar mostra {lido}, esperado {(ativos, pend, cap)}")
        ordem = [c["id"] for c in dashboard_da_api(api, dados["token_g1"])["courses"]]
        textos = page.eval_on_selector_all(SEL_UNASSIGNED, "els => els.map(e => e.innerText)")
        por_curso = {curso: tuple(int(n) for n in re.findall(r"\d+", texto)) for curso, texto in zip(ordem, textos)}
        if por_curso.get(CURSO_A) != (1, 0):
            raise Falha(f"D1: turma-unassigned do curso A depois de recarregar: {por_curso.get(CURSO_A)}, esperado (1, 0)")
        # os selects voltam a refletir a turma salva
        escolher_curso_na_gestao(page, CURSO_A, NOME_A, "D1")
        linhas_de_matricula(page, "D1")
        destinos = {a1_: SEM_TURMA, a2_: ALFA, a3_: BETA}
        for tag, destino in destinos.items():
            select = select_da_linha(linha_do_aluno(page, aluno(tag), "D1"), "D1")
            esperar(lambda select=select, destino=destino, tag=tag: None if destino in opcao_selecionada(select)
                    else f"matrícula de {tag}: o select mostra {opcao_selecionada(select)!r}, esperado {destino!r}",
                    "D1")

    cenario("D1", "persistência: recarregar mantém os números e os selects voltam a mostrar a turma salva", d1)

    # --- E1 ---------------------------------------------------------------------------
    def e1():
        page = tela_gestor()
        clicar_aba(page, ABA_AUDITORIA, "E1")
        aguardar_visivel(page.locator(SEL_AUDIT_ROW), "E1", f"nenhum {SEL_AUDIT_ROW} na aba Auditoria")
        eventos = eventos_da_api(api, dados["token_g1"])
        if len(eventos) >= 100:
            raise Falha(f"E1: {len(eventos)} eventos na API (acima do limite padrão de 100; o teste não cobre)")
        criacoes = [e for e in eventos if e["action"] == "class.create"]
        trocas = sorted((e for e in eventos if e["action"] == "enrollment.class_change"), key=lambda e: e["id"])
        if len(criacoes) != 3:
            raise Falha(f"E1: {len(criacoes)} eventos class.create na API (esperado 3: Alfa, Beta e Gama)")
        if len(trocas) != 4:
            raise Falha(f"E1: {len(trocas)} eventos enrollment.class_change na API (esperado 4; a atribuição "
                        f"recusada por turma cheia não pode gerar evento)")
        linhas = linhas_da_tela(page, len(eventos), "E1")

        def indice_do(evento):
            return next(i for i, e in enumerate(eventos) if e["id"] == evento["id"])

        for turma, gestor in ((ALFA, GESTOR2_EMAIL), (BETA, GESTOR2_EMAIL), (GAMA, ADMIN_EMAIL)):
            achados = [e for e in criacoes if f"'{turma}'" in e["detail"]]
            if len(achados) != 1:
                raise Falha(f"E1: {len(achados)} eventos class.create citam {turma!r} no detalhe: "
                            f"{[e['detail'] for e in criacoes]}")
            if achados[0]["actor_email"] != gestor:
                raise Falha(f"E1: class.create da {turma} tem responsável {achados[0]['actor_email']} na API, "
                            f"esperado {gestor}")
        esperados = [
            (aluno(a1_), None, dados["id_alfa"]),
            (aluno(a1_), dados["id_alfa"], None),
            (aluno(a3_), None, dados["id_beta"]),
            (aluno(a2_), None, dados["id_alfa"]),
        ]
        for evento, (quem, antes, depois) in zip(trocas, esperados):
            if evento["actor_email"] != ADMIN_EMAIL or str(evento["entity_id"]) != str(quem["matricula"]):
                raise Falha(f"E1: enrollment.class_change inesperado (responsável {evento['actor_email']}, matrícula "
                            f"{evento['entity_id']}), esperado {ADMIN_EMAIL} na matrícula {quem['matricula']}")
            if [(c["field"], c["before"], c["after"]) for c in evento["changes"]] != [("class_id", antes, depois)]:
                raise Falha(f"E1: changes de enrollment.class_change {evento['changes']}, esperado class_id "
                            f"{antes} -> {depois}")
        # a tela: ação, responsável e alterações de cada um desses eventos
        for evento in criacoes + trocas:
            i = indice_do(evento)
            linha = linhas.nth(i)
            if evento["action"] not in norm(linha.inner_text()):
                raise Falha(f"E1: a linha {i} não mostra a ação {evento['action']!r}")
            checar_responsavel(texto_do_responsavel(linha, i, "E1"), evento, f"E1 linha {i} ({evento['action']})")
            checar_alteracoes_da_linha(linha, evento, f"E1 linha {i} ({evento['action']})")

    cenario("E1", "auditoria mostra class.create (3) e enrollment.class_change (4) com o gestor certo; recusada sem evento", e1)

    # --- R1 / R2 ----------------------------------------------------------------------
    def sem_gestao(perfil, email, senha, token, codigo, pode_ler_matriculas):
        def fn():
            page = nova_pagina(f"{codigo}-{perfil}")
            paginas[perfil] = page
            abrir_cursos(page, base, email, senha, f"{codigo} {perfil}")
            aguardar_visivel(page.locator(SEL_ROW), codigo, f"os turma-row que o {perfil} deve ver")
            conferir_numeros(page, api, token, f"{codigo} {perfil}")
            # nenhuma seção de gestão, nenhum controle de escrita
            if TITULO_GESTAO in page.inner_text("body"):
                raise Falha(f"{codigo}: o {perfil} vê a seção {TITULO_GESTAO!r}")
            for seletor in SELETORES_DE_GESTAO:
                if page.locator(seletor).count() != 0:
                    raise Falha(f"{codigo}: o {perfil} vê {seletor} ({page.locator(seletor).count()} elementos)")
            # a API de escrita recusa (403) e nada muda
            antes = dashboard_da_api(api, dados["token_g1"])
            id_matricula = aluno(a3_)["matricula"]
            tentativas = (
                ("POST", "/api/admin/classes", {"course_id": CURSO_B, "name": f"Turma {perfil}"}),
                ("PUT", f"/api/admin/classes/{dados['id_alfa']}", {"name": f"Renomeada {perfil}"}),
                ("DELETE", f"/api/admin/classes/{dados.get('id_gama', 0)}", None),
                ("PUT", f"/api/admin/enrollments/{id_matricula}/class", {"class_id": None}),
            )
            for metodo, caminho, corpo in tentativas:
                status, _ = _api(api, metodo, caminho, corpo, token=token)
                if status != 403:
                    raise Falha(f"{codigo}: {metodo} {caminho} como {perfil} respondeu HTTP {status} (esperado 403)")
            if dashboard_da_api(api, dados["token_g1"]) != antes:
                raise Falha(f"{codigo}: o dashboard de cursos mudou depois das escritas recusadas do {perfil}")
            status, _ = _api(api, "GET", f"/api/admin/enrollments?course_id={CURSO_A}", token=token)
            esperado = 200 if pode_ler_matriculas else 403
            if status != esperado:
                raise Falha(f"{codigo}: GET /api/admin/enrollments como {perfil} respondeu HTTP {status} "
                            f"(esperado {esperado})")
        return fn

    cenario("R1", "suporte: vê os turma-*, sem seção de gestão; escrita 403; leitura de matrículas 200",
            sem_gestao("suporte", SUPORTE_EMAIL, SUPORTE_SENHA, dados.get("token_sup"), "R1", True))
    cenario("R2", "financeiro: vê os turma-*, sem seção de gestão; escrita 403; leitura de matrículas 403",
            sem_gestao("financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA, dados.get("token_fin"), "R2", False))

    # --- R3 ---------------------------------------------------------------------------
    def r3():
        id_matricula = aluno(a3_)["matricula"]
        rotas = (
            ("POST", "/api/admin/classes", {"course_id": CURSO_B, "name": "Sem token"}),
            ("PUT", f"/api/admin/classes/{dados['id_alfa']}", {"name": "Sem token"}),
            ("PUT", f"/api/admin/enrollments/{id_matricula}/class", {"class_id": None}),
        )
        for token in (None, "abc.def.ghi", "Zm9yamFkby1zZW0tcG9udG9z"):
            for metodo, caminho, corpo in rotas:
                status, _ = _api(api, metodo, caminho, corpo, token=token)
                if status != 401:
                    raise Falha(f"R3: {metodo} {caminho} com token {token!r} respondeu HTTP {status} (esperado 401)")

    cenario("R3", "sem token e com token forjado: 401 nas rotas de escrita de turma", r3)

    # --- K1 ---------------------------------------------------------------------------
    def k1():
        if erros_inesperados:
            raise Falha(f"K1: {len(erros_inesperados)} erro(s) inesperado(s): " + " | ".join(erros_inesperados[:5]))
        esperados = [("POST", re.compile(r"^/api/admin/classes$"), 409),
                     ("PUT", re.compile(r"^/api/admin/enrollments/\d+/class$"), 409)]
        obtidos = [(m, c, k) for _, m, c, k in provocados]
        if len(obtidos) != len(esperados) or any(
                m != em or not padrao.match(c) or k != ek for (m, c, k), (em, padrao, ek) in zip(obtidos, esperados)):
            raise Falha(f"K1: respostas 409/422 da tela {obtidos}; esperado exatamente os dois provocados "
                        f"(POST /api/admin/classes 409 e PUT /api/admin/enrollments/<id>/class 409)")

    cenario("K1", "sem erros de console/exceção; só os dois 409 provocados (B2 e C2) ocorreram", k1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    imprimir(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
