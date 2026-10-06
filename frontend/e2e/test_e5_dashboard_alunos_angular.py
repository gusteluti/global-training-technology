"""E2E do dashboard de alunos da área do funcionário (E5, Chromium via Playwright).
Decisão D35.4 P5 do PM: o dashboard mostra, por aluno, a contagem de mensagens do chat e a data da
última conversa, e NUNCA o conteúdo das conversas.

Contrato de tela (decidido pelo orquestrador): na tabela "Alunos matriculados" (aba "Alunos" de /admin)
entram duas colunas novas, com cabeçalhos exatos "Mensagens no chat" e "Última conversa". Em cada linha:
  data-testid="aluno-chat-count"  -> o número (0 se nunca conversou)
  data-testid="aluno-last-chat"   -> o valor de last_chat_at como veio da API, ou "—" quando for null
O colspan da linha "Nenhum aluno matriculado ainda." acompanha as 7 colunas (não coberto aqui: o
cenário sempre tem alunos; fica para revisão de código).

Cenários (checks numerados):
  S1 pré-condição (anterior às colunas novas): login de admin chega a /admin, a aba "Alunos" abre e a
     tabela "Alunos matriculados" mostra as linhas dos três alunos semeados
  S2 pré-condição: o mesmo para o perfil Suporte (conta própria do servidor deste teste)
  D1/D3 (admin / suporte) a tabela tem os cabeçalhos "Mensagens no chat" e "Última conversa"
  D2/D4 (admin / suporte) aluno A mostra 2 e B mostra 1 (data exibida e igual a last_chat_at da API),
        C mostra 0 e "—"
  P1 privacidade: o texto das mensagens do aluno e as respostas do bot não aparecem em lugar nenhum da
     página (texto visível e HTML), em nenhum dos dois perfis, nem na resposta da API do dashboard
  M1 a coluna "Matrículas"/"Ativas", as demais colunas e as métricas do topo continuam aparecendo
  K1 sem erros de console nem exceções de página. Erro reprova quando: HTTP 400, HTTP 404 em /api/,
     HTTP 5xx, ou exceção de página. Sem lista de tolerância

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e5_dashboard.py (reusa servidor_e2e_e5.py: Groq substituído por
    dublê, banco SQLite temporário isolado, ambiente fabricado) + conta de Suporte. O backend/db.sqlite
    de desenvolvimento não é aberto (D7) e nenhuma chamada ao Groq real é feita.
  - Frontend: `npx ng serve` numa porta livre própria, com proxy temporário /api -> backend de teste.
    O ng serve que já esteja na porta 4200 não é usado nem tocado.
  - Seed só pela API pública: cadastro (POST /api/auth/register) e chat (POST /api/student/chat).

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas: E2E_BACKEND_PORT / E2E_FRONT_PORT para fixar.
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_e5_dashboard_alunos_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD, PREFIXO_RESPOSTA  # noqa: E402
from servidor_e2e_e5_dashboard import SUPPORT_EMAIL, SUPPORT_PASSWORD  # noqa: E402
# Utilitários de harness e de seed já usados pelo e2e do chat (somente leitura, o arquivo não é alterado).
from test_e5_chat_aluno_angular import (  # noqa: E402
    ERRO_HTTP, Falha, FRONTEND, REPO, TIMEOUT, _api, _encerrar, _esperar_http, _iniciar,
    _porta_livre, login_na_tela, semear_aluno,
)

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_dashboard_alunos"))

CAMINHO_CHAT = "/api/student/chat"
CAMINHO_DASHBOARD = "/api/dashboard/alunos"
SEL_CONTAGEM = '[data-testid="aluno-chat-count"]'
SEL_ULTIMA = '[data-testid="aluno-last-chat"]'
COL_MENSAGENS = "Mensagens no chat"
COL_ULTIMA = "Última conversa"
COLUNAS_ANTIGAS = ["Aluno", "E-mail", "Matrículas", "Ativas", "Última matrícula"]
METRICAS = {"Alunos cadastrados": "total_students", "Com matrícula ativa": "active_students",
            "Sessões de chat com a IA": "total_chat_sessions"}
SEM_CONVERSA = "—"


@pytest.fixture(scope="module")
def servidores():
    """Sobe o backend de teste (com Suporte) e o Angular; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_e5_dash_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_FRONT_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://localhost:{porta_web}"
    log_api = tmp / "backend.log"
    log_web = tmp / "ng_serve.log"
    proxy = tmp / "proxy.e2e.json"
    proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}), encoding="utf-8")

    processos = []
    arquivos = []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_e5_dashboard.py"), "--port", str(porta_api),
             "--db-path", str(tmp / "db.sqlite"), "--outbox", str(tmp / "outbox.jsonl"),
             "--log-llm", str(tmp / "llm.jsonl")],
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

        yield {"base": base, "api": api}
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

def token_de_funcionario(api, email, senha):
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": email, "password": senha})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise RuntimeError(f"seed: login por API de {email} respondeu HTTP {status}")
    return corpo["access_token"]


def dashboard_da_api(api, token):
    status, corpo = _api(api, "GET", CAMINHO_DASHBOARD, token=token)
    if status != 200:
        raise RuntimeError(f"GET {CAMINHO_DASHBOARD} respondeu HTTP {status}")
    return corpo


def abrir_aba_alunos(page, base, email, senha, rotulo, emails_esperados):
    """Login de funcionário em /, abre a aba "Alunos" e espera as linhas dos alunos semeados."""
    login_na_tela(page, base, email, senha, rotulo)
    try:
        page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /admin)")
    page.wait_for_load_state("networkidle")
    aba = page.locator("ul.nav-tabs button", has_text="Alunos")
    try:
        aba.first.click(timeout=TIMEOUT)
        page.get_by_text("Alunos matriculados", exact=True).first.wait_for(state="visible", timeout=TIMEOUT)
        for alvo in emails_esperados:
            page.locator("tbody tr", has_text=alvo).first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: a aba Alunos não mostrou a tabela 'Alunos matriculados' com os alunos semeados")
    page.wait_for_load_state("networkidle")


def cabecalhos(page):
    return [t.strip() for t in page.locator("table thead th").all_inner_texts()]


def linha_do_aluno(page, email):
    return page.locator("tbody tr", has_text=email).first


def celula(linha, seletor, rotulo):
    alvo = linha.locator(seletor)
    if alvo.count() != 1:
        raise Falha(f"{rotulo}: esperava 1 célula {seletor}, há {alvo.count()}")
    return alvo.first.inner_text().strip()


def validar_cabecalhos(page, rotulo):
    heads = cabecalhos(page)
    for coluna in (COL_MENSAGENS, COL_ULTIMA):
        if coluna not in heads:
            raise Falha(f"{rotulo}: falta o cabeçalho '{coluna}' na tabela (cabeçalhos={heads})")
    if heads.index(COL_MENSAGENS) > heads.index(COL_ULTIMA):
        raise Falha(f"{rotulo}: 'Mensagens no chat' deve vir antes de 'Última conversa' ({heads})")


def validar_contagens(page, rotulo, alunos, esperado_api):
    """alunos: {tag: email}. esperado_api: {email: item da API}. Contagens fixas: A=2, B=1, C=0."""
    esperado = {"a": 2, "b": 1, "c": 0}
    for tag, contagem in esperado.items():
        email = alunos[tag]
        linha = linha_do_aluno(page, email)
        mostrado = celula(linha, SEL_CONTAGEM, f"{rotulo} aluno {tag.upper()} contagem")
        if mostrado != str(contagem):
            raise Falha(f"{rotulo}: aluno {tag.upper()} mostra '{mostrado}' mensagens (esperado {contagem})")
        data = celula(linha, SEL_ULTIMA, f"{rotulo} aluno {tag.upper()} última conversa")
        item = esperado_api[email]
        if contagem == 0:
            if data != SEM_CONVERSA:
                raise Falha(f"{rotulo}: aluno {tag.upper()} sem conversa deveria mostrar '{SEM_CONVERSA}', mostra '{data}'")
        else:
            last = item.get("last_chat_at")
            if not last:
                raise Falha(f"{rotulo}: a API não devolveu last_chat_at do aluno {tag.upper()}")
            if data == SEM_CONVERSA or not data:
                raise Falha(f"{rotulo}: aluno {tag.upper()} conversou, mas a data não é exibida ('{data}')")
            if data != last:
                raise Falha(f"{rotulo}: aluno {tag.upper()} mostra '{data}', last_chat_at da API é '{last}'")


def test_e5_dashboard_alunos_angular_e2e(servidores, browser):
    base = servidores["base"]
    api = servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    estado = {"page": None}
    paginas = {}

    # --- seed pela API pública do backend de teste -------------------------------------
    seed = {"ok": False, "erro": ""}
    alunos = {}
    textos = []   # tudo que o aluno escreveu e o bot respondeu: nunca pode aparecer no dashboard
    esperado_api = {}
    try:
        for tag in ("a", "b", "c"):
            email, token = semear_aluno(api, tag)
            alunos[tag] = email
            if tag == "c":
                continue
            for n in range(2 if tag == "a" else 1):
                texto = f"Mensagem sigilosa do aluno {tag.upper()} numero {n} {uuid.uuid4().hex[:8]}"
                status, _ = _api(api, "POST", CAMINHO_CHAT, {"message": texto}, token=token)
                if status != 200:
                    raise RuntimeError(f"seed: POST {CAMINHO_CHAT} do aluno {tag.upper()} respondeu HTTP {status}")
                textos.append(texto)
                textos.append(PREFIXO_RESPOSTA + texto)
        token_admin = token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        dash = dashboard_da_api(api, token_admin)
        esperado_api = {item["email"]: item for item in dash["students"]}
        for tag, email in alunos.items():
            if email not in esperado_api:
                raise RuntimeError(f"seed: aluno {tag.upper()} não aparece em GET {CAMINHO_DASHBOARD}")
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
                erros_console.append(f"{rotulo}: {msg.text} [{url}]")

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

    def pagina(perfil):
        page = paginas.get(perfil)
        if page is None:
            raise Falha(f"pré-requisito: a tela do perfil {perfil} não ficou pronta (S1/S2 falharam)")
        estado["page"] = page
        return page

    emails = list(alunos.values())

    # --- S1 / S2 ----------------------------------------------------------------------
    def pre(perfil, email, senha):
        def fn():
            page = nova_pagina(f"S-{perfil}")
            paginas[perfil] = page
            abrir_aba_alunos(page, base, email, senha, f"pré-condição {perfil}", emails)
        return fn

    cenario("S1", "pré-condição: admin abre a aba Alunos e vê a tabela com os 3 alunos semeados",
            pre("admin", ADMIN_EMAIL, ADMIN_PASSWORD))
    cenario("S2", "pré-condição: suporte abre a aba Alunos e vê a tabela com os 3 alunos semeados",
            pre("suporte", SUPPORT_EMAIL, SUPPORT_PASSWORD))

    # --- D1..D4 -----------------------------------------------------------------------
    cenario("D1", "admin: cabeçalhos 'Mensagens no chat' e 'Última conversa' na tabela",
            lambda: validar_cabecalhos(pagina("admin"), "D1 admin"))
    cenario("D2", "admin: A=2, B=1 (datas iguais a last_chat_at da API), C=0 e '—'",
            lambda: validar_contagens(pagina("admin"), "D2 admin", alunos, esperado_api))
    cenario("D3", "suporte: cabeçalhos 'Mensagens no chat' e 'Última conversa' na tabela",
            lambda: validar_cabecalhos(pagina("suporte"), "D3 suporte"))
    cenario("D4", "suporte: A=2, B=1 (datas iguais a last_chat_at da API), C=0 e '—'",
            lambda: validar_contagens(pagina("suporte"), "D4 suporte", alunos, esperado_api))

    # --- P1 ---------------------------------------------------------------------------
    def p1():
        for perfil in ("admin", "suporte"):
            page = pagina(perfil)
            visivel = page.inner_text("body")
            html = page.content()
            for texto in textos:
                trecho = texto.split(PREFIXO_RESPOSTA)[-1]  # o miolo "Mensagem sigilosa ..." vale para os dois
                if texto in visivel or texto in html or trecho in visivel or trecho in html:
                    raise Falha(f"P1: conteúdo de conversa apareceu na página do perfil {perfil}: {trecho!r}")
            if "Resposta simulada" in visivel or "Resposta simulada" in html:
                raise Falha(f"P1: resposta do bot apareceu na página do perfil {perfil}")
        # a própria API do dashboard também não pode vazar o conteúdo
        token_sup = token_de_funcionario(api, SUPPORT_EMAIL, SUPPORT_PASSWORD)
        bruto = json.dumps(dashboard_da_api(api, token_sup), ensure_ascii=False)
        for texto in textos:
            if texto in bruto or texto.split(PREFIXO_RESPOSTA)[-1] in bruto:
                raise Falha("P1: a resposta de GET /api/dashboard/alunos contém texto de conversa")

    cenario("P1", "privacidade: mensagens do aluno e respostas do bot não aparecem na página nem na API", p1)

    # --- M1 ---------------------------------------------------------------------------
    def m1():
        dash = dashboard_da_api(api, token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD))
        for perfil in ("admin", "suporte"):
            page = pagina(perfil)
            heads = cabecalhos(page)
            for coluna in COLUNAS_ANTIGAS:
                if coluna not in heads:
                    raise Falha(f"M1 {perfil}: o cabeçalho '{coluna}' sumiu (cabeçalhos={heads})")
            linha = linha_do_aluno(page, alunos["a"])
            tds = [t.strip() for t in linha.locator("td").all_inner_texts()]
            pos_total, pos_ativas = heads.index("Matrículas"), heads.index("Ativas")
            if len(tds) <= max(pos_total, pos_ativas) or tds[pos_total] != "0" or tds[pos_ativas] != "0":
                raise Falha(f"M1 {perfil}: colunas Matrículas/Ativas do aluno A erradas (células={tds})")
            for rotulo, chave in METRICAS.items():
                cartao = page.locator(".card", has_text=rotulo)
                if cartao.count() == 0:
                    raise Falha(f"M1 {perfil}: a métrica '{rotulo}' não aparece no topo")
                valor = dash["metrics"][chave]
                if not re.search(rf"(?<!\d){valor}(?!\d)", cartao.first.inner_text()):
                    raise Falha(f"M1 {perfil}: a métrica '{rotulo}' não mostra o valor {valor}")

    cenario("M1", "colunas Matrículas/Ativas, demais colunas e métricas do topo continuam aparecendo", m1)

    # --- K1 ---------------------------------------------------------------------------
    def k1():
        if erros_console:
            raise Falha(f"K1 console: {len(erros_console)} erro(s): " + " | ".join(erros_console[:5]))

    cenario("K1", "sem erros de console (400, 404 em /api, 5xx) nem exceções nas telas acima", k1)

    for ctx in contextos:
        try:
            ctx.close()
        except Exception:
            pass

    passou = sum(1 for _, _, ok, _ in resultados if ok)
    falhas = [f"{codigo} {nome} -> {detalhe}" for codigo, nome, ok, detalhe in resultados if not ok]
    print(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
