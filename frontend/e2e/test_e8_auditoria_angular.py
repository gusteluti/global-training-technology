"""E2E da tela de auditoria da área do funcionário (E8, Chromium via Playwright).
Decisões D45 e D46 (seção "Tela `audit-logs`"): a trilha mostra quem fez cada ação (responsável) e o que mudou
(antes e depois), a partir de GET /api/admin/audit-logs (só Gestão).

Contrato de tela (D45), aba "Auditoria" de /admin:
  colunas (nesta ordem): Data, Responsável, Ação, Alteração, Detalhe
  data-testid="audit-row"    -> uma linha por evento (na ordem da API: do mais novo para o mais antigo)
  data-testid="audit-actor"  -> célula do responsável: e-mail (ou nome) do ator MAIS o perfil; "sistema" quando
                                for evento do sistema (role "system", sem usuário); o login administrativo legado
                                aparece pelo nome "Login administrativo (Gestão)"
  data-testid="audit-change" -> um por item de `changes`, texto `campo: antes → depois`; valores de lista ou
                                objeto aparecem como JSON; evento sem `changes` não tem nenhum audit-change
Escolhas de forma aceitas pelo teste (nenhuma define política): o perfil pode aparecer como o valor ("admin") ou
o rótulo ("Gestão"); string pode vir com ou sem aspas; número pode vir como 100, 100.0 ou 100,00; valor nulo pode
vir como "null", "—", "-" ou vazio; JSON compacto ou com espaços.

Cenários (checks numerados):
  S1 pré-condição (anterior aos testids): login do gestor chega a /admin, a aba "Auditoria" abre, o título
     "Trilha de auditoria" e linhas de tabela aparecem. Garante que o red é por falta da E8 na tela, não por
     servidor, login ou seed
  I1 isolamento: os cursos do seed foram gravados só no diretório temporário; backend/courses não mudou
  A1 uma audit-row por evento da API; ação e detalhe de cada evento aparecem na linha dele
  A2 cabeçalho da tabela: Data, Responsável, Ação, Alteração, Detalhe (a coluna "Alteração" existe)
  B1 todo audit-actor segue a regra do contrato (e-mail/nome + perfil; "sistema" para o sistema)
  B2 os dois gestores são distinguíveis: cada evento de curso mostra o e-mail do gestor certo e não o do outro
  B3 o login administrativo legado aparece como "Login administrativo (Gestão)" (sem e-mail) e o evento do
     sistema (recarga de cursos) aparece como "sistema"
  C1 evento de preço do 1º gestor: audit-change único `price: 100 → 150`
  C2 evento do 2º gestor: audit-change só dos campos alterados (price, name, duration_hours, topics), com os
     valores da API e listas em JSON; campo igual não aparece (description)
  C3 evento sem mudança de preço: audit-change só do campo alterado (description)
  C4 reembolso: um evento, com payment.status e enrollment.status (approved/active -> refunded)
  C5 evento sem changes não tem audit-change e o total de audit-change da tela é o total de changes da API
  P1 nenhum texto de senha nem o e-mail inexistente digitado numa falha de login na página, no HTML ou na API
  R1 suporte: sem aba de auditoria nem audit-row; API dele devolve 403
  R2 financeiro: idem (sem aba, sem audit-row, API 403)
  R3 sem token e com token forjado: 401 na API de auditoria
  K1 sem erros de console (400, 404 em /api, 5xx) nem exceções de página. Sem lista de tolerância

Harness (o teste sobe e derruba os próprios servidores; nada fica rodando ao terminar):
  - Backend: frontend/e2e/servidor_e2e_e8.py (reaproveita o do E7: Groq e Mercado Pago falsos, banco SQLite
    temporário isolado) com o diretório de cursos redirecionado para uma pasta temporária e um segundo gestor
    semeado no banco temporário. O backend/db.sqlite e o backend/courses de desenvolvimento não são abertos nem
    alterados.
  - Frontend: `npx ng serve` numa porta livre própria, com proxy temporário /api -> backend de teste.
  - Seed só pela API pública/administrativa: dois gestores com JWT (POST /api/token) e e-mails distintos; o 1º cria
    um curso (preço 100) e altera o preço (150); o 2º altera preço e outros campos e depois só a descrição; um
    aluno se cadastra, paga (create-checkout + webhook, aprovado) e o 1º gestor reembolsa (duas vezes: o segundo
    pedido não gera evento); login legado em /api/admin/login; uma falha de login legado e uma de conta inexistente.

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas: E2E_BACKEND_PORT / E2E_FRONT_PORT para fixar.
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_e8_auditoria_angular.py -s
Screenshots de falha vão para E2E_SCREENSHOTS, ou para a pasta temporária do sistema.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from servidor_e2e_e5 import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402
from apoio_webhook_mp import enviar_webhook  # noqa: E402  (E9, D48: webhook assinado, id numérico)
from servidor_e2e_e8 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTOR2_EMAIL, GESTOR2_SENHA, SENHA_LEGADA_GESTAO,
    SUPORTE_EMAIL, SUPORTE_SENHA,
)
# Utilitários de harness e de seed já usados pelo e2e do chat (somente leitura, o arquivo não é alterado).
from test_e5_chat_aluno_angular import (  # noqa: E402
    ERRO_HTTP, Falha, FRONTEND, REPO, TIMEOUT, _api, _encerrar, _esperar_http, _iniciar,
    _porta_livre, login_na_tela, semear_aluno,
)

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_auditoria"))

CAMINHO_AUDITORIA = "/api/admin/audit-logs"
ABA = "Auditoria"
TITULO_TELA = "Trilha de auditoria"
COLUNAS = ["Data", "Responsável", "Ação", "Alteração", "Detalhe"]
SEL_ROW = '[data-testid="audit-row"]'
SEL_ACTOR = '[data-testid="audit-actor"]'
SEL_CHANGE = '[data-testid="audit-change"]'

CURSO_ID = "curso-e8-a"
SENHA_ERRADA_LEGADO = "senha-errada-legado-e8"
EMAIL_INEXISTENTE = "fantasma.e8@teste.com"
SENHA_ERRADA_TOKEN = "senha-errada-token-e8"
NULOS = {"null", "", "—", "-", "–", "∅", "vazio", "(vazio)", "nulo", "none"}
PERFIS_ADMIN = ("admin", "gestão", "gestao")
SENHAS_QUE_NAO_PODEM_APARECER = [
    ADMIN_PASSWORD, GESTOR2_SENHA, FINANCEIRO_SENHA, SUPORTE_SENHA, SENHA_LEGADA_GESTAO,
    SENHA_ERRADA_LEGADO, SENHA_ERRADA_TOKEN,
]


def imprimir(mensagem):
    """print que não quebra em console cp1252 (a seta '→' do contrato não existe nessa codificação)."""
    codificacao = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(mensagem.encode(codificacao, "replace").decode(codificacao))


def snapshot_de_cursos():
    """Impressão digital de backend/courses (nomes, tamanhos, mtime e conteúdo) para provar que não mudou."""
    pasta = REPO / "backend" / "courses"
    itens = []
    if pasta.exists():
        for arquivo in sorted(pasta.rglob("*")):
            if arquivo.is_file():
                dados = arquivo.read_bytes()
                itens.append((arquivo.relative_to(pasta).as_posix(), len(dados), arquivo.stat().st_mtime_ns,
                              hashlib.sha256(dados).hexdigest()))
    return itens


@pytest.fixture(scope="module")
def servidores():
    """Sobe o backend de teste (cursos isolados, dois gestores) e o Angular; derruba tudo ao final."""
    tmp = Path(tempfile.mkdtemp(prefix="gt_e2e_e8_"))
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
# Auxiliares
# ---------------------------------------------------------------------------------------------

def token_de_funcionario(api, email, senha):
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": email, "password": senha})
    if status != 200 or not (corpo or {}).get("access_token"):
        raise RuntimeError(f"seed: login por API de {email} respondeu HTTP {status}")
    return corpo["access_token"]


def eventos_da_api(api, token):
    status, corpo = _api(api, "GET", CAMINHO_AUDITORIA, token=token)
    if status != 200:
        raise RuntimeError(f"GET {CAMINHO_AUDITORIA} respondeu HTTP {status}")
    return corpo["logs"]


def corpo_do_curso(nome, preco, **alterados):
    curso = {
        "id": CURSO_ID, "name": nome, "description": "Descrição do curso E8", "price": preco,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Público do curso E8",
        "objectives": ["Objetivo 1"], "topics": ["Tópico 1"], "benefits": ["Benefício 1"],
        "faq": [{"question": "Pergunta?", "answer": "Resposta."}], "system_prompt": "Prompt do curso E8",
        "materials": [],
    }
    curso.update(alterados)
    return curso


def norm(texto):
    return " ".join((texto or "").split())


def valor_confere(texto, esperado):
    """O texto exibido (depois ou antes da seta) representa o valor da API?"""
    texto = norm(texto)
    if esperado is None:
        return texto.lower() in NULOS
    if isinstance(esperado, bool):
        return texto.lower() in ({"true", "sim"} if esperado else {"false", "não", "nao"})
    if isinstance(esperado, (int, float)):
        try:
            return abs(float(texto.replace(",", ".")) - float(esperado)) < 1e-9
        except ValueError:
            return False
    if isinstance(esperado, str):
        if texto == esperado:
            return True
        try:
            return json.loads(texto) == esperado
        except ValueError:
            return False
    try:  # lista ou objeto: JSON
        return json.loads(texto) == esperado
    except ValueError:
        return False


def separar_alteracao(texto):
    """'campo: antes → depois' -> (campo, antes, depois); None se não seguir o formato."""
    m = re.match(r"^([\w.]+):\s(.*?)\s→\s(.*)$", norm(texto))
    if m is None:
        return None
    return m.group(1), m.group(2), m.group(3)


def checar_alteracoes_da_linha(linha, evento, rotulo):
    """Os audit-change da linha são exatamente os `changes` do evento (campo e valores, qualquer ordem)."""
    textos = linha.locator(SEL_CHANGE).all_inner_texts()
    esperados = evento["changes"]
    if len(textos) != len(esperados):
        raise Falha(f"{rotulo}: {len(textos)} audit-change na linha, a API tem {len(esperados)} "
                    f"({[c['field'] for c in esperados]}); exibidos: {textos}")
    restantes = list(esperados)
    for texto in textos:
        partes = separar_alteracao(texto)
        if partes is None:
            raise Falha(f"{rotulo}: audit-change {texto!r} não segue o formato 'campo: antes → depois'")
        campo, antes, depois = partes
        achado = next((c for c in restantes if c["field"] == campo), None)
        if achado is None:
            raise Falha(f"{rotulo}: campo {campo!r} exibido não está em changes da API "
                        f"({[c['field'] for c in restantes]})")
        if not valor_confere(antes, achado["before"]):
            raise Falha(f"{rotulo}: {campo}: 'antes' exibido {antes!r}, a API tem {achado['before']!r}")
        if not valor_confere(depois, achado["after"]):
            raise Falha(f"{rotulo}: {campo}: 'depois' exibido {depois!r}, a API tem {achado['after']!r}")
        restantes.remove(achado)


def abrir_aba_auditoria(page, base, email, senha, rotulo):
    """Login de funcionário em /, abre a aba "Auditoria" e espera o título e as linhas da tabela."""
    login_na_tela(page, base, email, senha, rotulo)
    try:
        page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: URL final {page.url} (esperado /admin)")
    page.wait_for_load_state("networkidle")
    aba = page.locator("ul.nav-tabs button", has_text=ABA)
    try:
        aba.first.click(timeout=TIMEOUT)
        page.get_by_text(TITULO_TELA, exact=True).first.wait_for(state="visible", timeout=TIMEOUT)
        page.locator("table tbody tr").first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: a aba '{ABA}' não abriu ou não mostrou o título '{TITULO_TELA}' com linhas")
    page.wait_for_load_state("networkidle")


def abas_visiveis(page):
    return [t.strip() for t in page.locator("ul.nav-tabs button").all_inner_texts()]


def linhas_da_tela(page, esperadas, rotulo):
    linhas = page.locator(SEL_ROW)
    try:
        linhas.first.wait_for(state="visible", timeout=TIMEOUT)
    except sync_api.TimeoutError:
        raise Falha(f"{rotulo}: não existe nenhum elemento visível {SEL_ROW} (a API tem {esperadas} eventos)")
    if linhas.count() != esperadas:
        raise Falha(f"{rotulo}: {linhas.count()} elementos {SEL_ROW}, a API tem {esperadas} eventos")
    return linhas


def texto_do_responsavel(linha, indice, rotulo):
    alvo = linha.locator(SEL_ACTOR)
    if alvo.count() != 1:
        raise Falha(f"{rotulo}: linha {indice} tem {alvo.count()} elementos {SEL_ACTOR} (esperado 1)")
    return norm(alvo.first.inner_text())


def checar_responsavel(texto, evento, rotulo):
    """Regra do contrato para o texto de audit-actor de um evento da API."""
    baixo = texto.lower()
    if evento.get("actor_email"):
        if evento["actor_email"].lower() not in baixo:
            raise Falha(f"{rotulo}: responsável {texto!r} não mostra o e-mail {evento['actor_email']}")
        resto = baixo.replace(evento["actor_email"].lower(), "")
        perfis = PERFIS_ADMIN if evento["role"] == "admin" else (evento["role"].lower(),)
        if not any(p in resto for p in perfis):
            raise Falha(f"{rotulo}: responsável {texto!r} não mostra o perfil ({evento['role']}) além do e-mail")
    elif evento.get("actor_name"):
        if evento["actor_name"].lower() not in baixo:
            raise Falha(f"{rotulo}: responsável {texto!r} não mostra o nome {evento['actor_name']!r}")
    elif evento.get("role") == "system" or evento.get("user_id") is None:
        if "sistema" not in baixo:
            raise Falha(f"{rotulo}: evento do sistema ({evento['action']}) mostra {texto!r} em vez de 'sistema'")
    else:
        raise Falha(f"{rotulo}: evento {evento['action']} sem e-mail, nome nem perfil de sistema na API: {evento}")


def achar_eventos(eventos, acao, **filtros):
    return [e for e in eventos if e["action"] == acao and all(e.get(k) == v for k, v in filtros.items())]


def test_e8_auditoria_angular_e2e(servidores, browser):
    base = servidores["base"]
    api = servidores["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    resultados = []
    erros_console = []
    contextos = []
    estado = {"page": None}
    paginas = {}

    # --- seed pela API pública/administrativa do backend de teste ------------------------
    seed = {"ok": False, "erro": ""}
    dados = {}
    try:
        token_g1 = token_de_funcionario(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        token_g2 = token_de_funcionario(api, GESTOR2_EMAIL, GESTOR2_SENHA)

        # gestor 1: cria o curso (preço 100) e altera só o preço (150)
        status, _ = _api(api, "POST", "/api/admin/create-course", corpo_do_curso("Curso E8 A", 100), token=token_g1)
        if status != 200:
            raise RuntimeError(f"seed: create-course respondeu HTTP {status}")
        status, _ = _api(api, "PUT", f"/api/admin/course/{CURSO_ID}", corpo_do_curso("Curso E8 A", 150),
                         token=token_g1)
        if status != 200:
            raise RuntimeError(f"seed: PUT do preço (gestor 1) respondeu HTTP {status}")

        # gestor 2: altera preço (180) e outros campos; depois só a descrição
        mudancas_g2 = dict(duration_hours=12, topics=["Tópico 1", "Tópico 2"])
        status, _ = _api(api, "PUT", f"/api/admin/course/{CURSO_ID}",
                         corpo_do_curso("Curso E8 A Renomeado", 180, **mudancas_g2), token=token_g2)
        if status != 200:
            raise RuntimeError(f"seed: PUT de vários campos (gestor 2) respondeu HTTP {status}")
        status, _ = _api(api, "PUT", f"/api/admin/course/{CURSO_ID}",
                         corpo_do_curso("Curso E8 A Renomeado", 180, description="Descrição revisada E8",
                                        **mudancas_g2), token=token_g2)
        if status != 200:
            raise RuntimeError(f"seed: PUT da descrição (gestor 2) respondeu HTTP {status}")

        # aluno paga (aprovado) e o gestor 1 reembolsa; o segundo pedido de reembolso não gera evento
        email_aluno, _token_aluno = semear_aluno(api, "e8")
        status, corpo = _api(api, "POST", "/api/payments/create-checkout",
                             {"course_id": CURSO_ID, "payer": {"name": "Aluno E8", "email": email_aluno}})
        if status != 200 or not (corpo or {}).get("external_reference"):
            raise RuntimeError(f"seed: create-checkout respondeu HTTP {status}")
        status, _ = enviar_webhook(api, corpo["external_reference"])
        if status != 200:
            raise RuntimeError(f"seed: webhook respondeu HTTP {status}")
        status, painel = _api(api, "GET", "/api/dashboard/financeiro", token=token_g1)
        if status != 200:
            raise RuntimeError(f"seed: dashboard financeiro respondeu HTTP {status}")
        pagamento = next((p for p in painel["payments"] if p["student_email"] == email_aluno), None)
        if pagamento is None or pagamento["status"] != "approved":
            raise RuntimeError(f"seed: pagamento aprovado do aluno não encontrado: {pagamento}")
        for _ in range(2):
            status, _ = _api(api, "POST", f"/api/payments/refund/{pagamento['id']}", {}, token=token_g1)
            if status != 200:
                raise RuntimeError(f"seed: reembolso respondeu HTTP {status}")

        # login administrativo legado (ok) e falhas de login (legado e conta inexistente)
        status, _ = _api(api, "POST", "/api/admin/login", {"password": SENHA_LEGADA_GESTAO})
        if status != 200:
            raise RuntimeError(f"seed: login legado respondeu HTTP {status}")
        status, _ = _api(api, "POST", "/api/admin/login", {"password": SENHA_ERRADA_LEGADO})
        if status != 401:
            raise RuntimeError(f"seed: login legado com senha errada respondeu HTTP {status} (esperado 401)")
        status, _ = _api(api, "POST", "/api/token",
                         formulario={"username": EMAIL_INEXISTENTE, "password": SENHA_ERRADA_TOKEN})
        if status == 200:
            raise RuntimeError("seed: login de conta inexistente não deveria dar 200")

        # sanidade do seed (o backend da E8 já está verde; isto só garante que o cenário é o planejado)
        eventos = eventos_da_api(api, token_g1)
        if not 0 < len(eventos) < 100:
            raise RuntimeError(f"seed: {len(eventos)} eventos (esperado de 1 a 99, abaixo do limite padrão)")
        criar = achar_eventos(eventos, "course.create", entity_id=CURSO_ID)
        preco = achar_eventos(eventos, "course.price_change", entity_id=CURSO_ID)
        atualiza = achar_eventos(eventos, "course.update", entity_id=CURSO_ID)
        reembolso = achar_eventos(eventos, "payment.refund")
        if len(criar) != 1 or len(preco) != 2 or len(atualiza) != 1 or len(reembolso) != 1:
            raise RuntimeError("seed: eventos de curso/reembolso inesperados na API: "
                               f"criar={len(criar)} preco={len(preco)} update={len(atualiza)} "
                               f"reembolso={len(reembolso)}")
        dados.update(
            token_g1=token_g1,
            ev_criar=criar[0],
            ev_preco_g1=next(e for e in preco if e["actor_email"] == ADMIN_EMAIL),
            ev_preco_g2=next(e for e in preco if e["actor_email"] == GESTOR2_EMAIL),
            ev_update=atualiza[0],
            ev_reembolso=reembolso[0],
        )
        if dados["ev_preco_g1"]["changes"] != [{"field": "price", "before": 100.0, "after": 150.0}]:
            raise RuntimeError(f"seed: changes do preço do gestor 1 inesperado: {dados['ev_preco_g1']['changes']}")
        campos_g2 = {c["field"] for c in dados["ev_preco_g2"]["changes"]}
        if campos_g2 != {"price", "name", "duration_hours", "topics"}:
            raise RuntimeError(f"seed: campos do gestor 2 inesperados: {campos_g2}")
        if [c["field"] for c in dados["ev_update"]["changes"]] != ["description"]:
            raise RuntimeError(f"seed: changes do update inesperado: {dados['ev_update']['changes']}")
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
        if page is None or "eventos_tela" not in dados:
            raise Falha("pré-requisito: a tela do gestor não ficou pronta (S1 falhou)")
        estado["page"] = page
        return page

    def linha_do_evento(evento, rotulo):
        """Linha da tela que corresponde ao evento (mesma posição da API, que vem do mais novo para o mais antigo)."""
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        linhas = linhas_da_tela(page, len(eventos), rotulo)
        indice = next(i for i, e in enumerate(eventos) if e["id"] == evento["id"])
        return linhas.nth(indice), indice

    # --- S1 ---------------------------------------------------------------------------
    def s1():
        page = nova_pagina("S-gestor")
        paginas["gestor"] = page
        abrir_aba_auditoria(page, base, ADMIN_EMAIL, ADMIN_PASSWORD, "pré-condição gestor")
        # a API é lida DEPOIS do login (o próprio login gera evento) e antes de qualquer outro login
        dados["eventos_tela"] = eventos_da_api(api, dados["token_g1"])
        total_linhas = page.locator("table tbody tr").count()
        if total_linhas < 1:
            raise Falha("S1: a tabela da auditoria não tem nenhuma linha")

    cenario("S1", "pré-condição: gestor abre a aba Auditoria e vê o título e linhas de tabela", s1)

    # --- I1 ---------------------------------------------------------------------------
    def i1():
        cursos_tmp = servidores["cursos_tmp"]
        if not (cursos_tmp / f"{CURSO_ID}.json").exists():
            raise Falha(f"I1: o curso do seed não foi gravado em {cursos_tmp} (isolamento do helper falhou)")
        if snapshot_de_cursos() != servidores["cursos_antes"]:
            raise Falha("I1: backend/courses mudou durante o teste (o teste não pode alterar esse diretório)")
        if (REPO / "backend" / "courses" / f"{CURSO_ID}.json").exists():
            raise Falha("I1: o curso do seed apareceu em backend/courses")

    cenario("I1", "isolamento: cursos do seed só no diretório temporário; backend/courses intacto", i1)

    # --- A1 / A2 ----------------------------------------------------------------------
    def a1():
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        linhas = linhas_da_tela(page, len(eventos), "A1")
        for i, evento in enumerate(eventos):
            texto = norm(linhas.nth(i).inner_text())
            if evento["action"] not in texto:
                raise Falha(f"A1: linha {i} ({texto!r}) não mostra a ação {evento['action']!r}")
            if norm(evento["detail"]) not in texto:
                raise Falha(f"A1: linha {i} ({texto!r}) não mostra o detalhe {evento['detail']!r}")

    def a2():
        page = tela_gestor()
        cabecalho = [norm(t) for t in page.locator("table thead th").all_inner_texts()]
        if cabecalho != COLUNAS:
            raise Falha(f"A2: colunas {cabecalho}, esperado {COLUNAS}")

    cenario("A1", "uma audit-row por evento da API; ação e detalhe de cada evento na linha dele", a1)
    cenario("A2", "colunas Data, Responsável, Ação, Alteração, Detalhe", a2)

    # --- B1 / B2 / B3 -----------------------------------------------------------------
    def b1():
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        linhas = linhas_da_tela(page, len(eventos), "B1")
        for i, evento in enumerate(eventos):
            texto = texto_do_responsavel(linhas.nth(i), i, "B1")
            checar_responsavel(texto, evento, f"B1 linha {i} ({evento['action']})")

    def b2():
        eventos_por_gestor = (
            (dados["ev_criar"], ADMIN_EMAIL, GESTOR2_EMAIL),
            (dados["ev_preco_g1"], ADMIN_EMAIL, GESTOR2_EMAIL),
            (dados["ev_preco_g2"], GESTOR2_EMAIL, ADMIN_EMAIL),
            (dados["ev_update"], GESTOR2_EMAIL, ADMIN_EMAIL),
            (dados["ev_reembolso"], ADMIN_EMAIL, GESTOR2_EMAIL),
        )
        for evento, certo, outro in eventos_por_gestor:
            linha, i = linha_do_evento(evento, "B2")
            texto = texto_do_responsavel(linha, i, "B2").lower()
            if certo.lower() not in texto:
                raise Falha(f"B2: {evento['action']} do gestor {certo}: audit-actor mostra {texto!r}")
            if outro.lower() in texto:
                raise Falha(f"B2: {evento['action']} do gestor {certo}: audit-actor mostra também {outro}")

    def b3():
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        linhas = linhas_da_tela(page, len(eventos), "B3")
        legados = [(i, e) for i, e in enumerate(eventos) if e["action"] == "staff.login" and not e.get("actor_email")]
        if len(legados) != 1:
            raise Falha(f"B3: esperava 1 staff.login legado (sem e-mail) na API, há {len(legados)}")
        i, evento = legados[0]
        texto = texto_do_responsavel(linhas.nth(i), i, "B3")
        if "Login administrativo (Gestão)" not in texto:
            raise Falha(f"B3: o login legado mostra {texto!r}, esperado 'Login administrativo (Gestão)'")
        if "@" in texto:
            raise Falha(f"B3: o login legado não tem e-mail, mas o responsável mostra {texto!r}")
        sistema = [(i, e) for i, e in enumerate(eventos)
                   if e["action"] == "manager_reload" and e["role"] == "system"]
        if not sistema:
            raise Falha("B3: a API não tem evento manager_reload do sistema (seed)")
        for i, evento in sistema:
            texto = texto_do_responsavel(linhas.nth(i), i, "B3")
            if texto.lower() != "sistema" and "sistema" not in texto.lower():
                raise Falha(f"B3: evento do sistema na linha {i} mostra {texto!r}, esperado 'sistema'")
            if "@" in texto or "admin" in texto.lower():
                raise Falha(f"B3: evento do sistema não tem pessoa, mas o responsável mostra {texto!r}")

    cenario("B1", "todo audit-actor segue o contrato (e-mail/nome + perfil; 'sistema' para o sistema)", b1)
    cenario("B2", "dois gestores distinguíveis: cada evento mostra o e-mail do gestor certo e não o do outro", b2)
    cenario("B3", "login legado = 'Login administrativo (Gestão)' sem e-mail; evento do sistema = 'sistema'", b3)

    # --- C1..C5 -----------------------------------------------------------------------
    def c1():
        linha, i = linha_do_evento(dados["ev_preco_g1"], "C1")
        itens = linha.locator(SEL_CHANGE)
        if itens.count() != 1:
            raise Falha(f"C1: o evento de preço do gestor 1 tem {itens.count()} audit-change, esperado 1 (price)")
        texto = norm(itens.first.inner_text())
        partes = separar_alteracao(texto)
        if partes is None or partes[0] != "price":
            raise Falha(f"C1: audit-change {texto!r} não é 'price: antes → depois'")
        if not valor_confere(partes[1], 100) or not valor_confere(partes[2], 150):
            raise Falha(f"C1: audit-change {texto!r}, esperado 'price: 100 → 150'")

    def c2():
        evento = dados["ev_preco_g2"]
        linha, i = linha_do_evento(evento, "C2")
        checar_alteracoes_da_linha(linha, evento, "C2")
        campos = {separar_alteracao(t)[0] for t in linha.locator(SEL_CHANGE).all_inner_texts()}
        if campos != {"price", "name", "duration_hours", "topics"}:
            raise Falha(f"C2: campos exibidos {sorted(campos)}, esperado price, name, duration_hours, topics")
        if "description" in campos:
            raise Falha("C2: description não mudou neste evento e não pode aparecer")
        topicos = next(t for t in linha.locator(SEL_CHANGE).all_inner_texts() if norm(t).startswith("topics:"))
        _, antes, depois = separar_alteracao(topicos)
        if json.loads(antes) != ["Tópico 1"] or json.loads(depois) != ["Tópico 1", "Tópico 2"]:
            raise Falha(f"C2: topics exibido como {topicos!r}, esperado listas em JSON")
        preco = next(t for t in linha.locator(SEL_CHANGE).all_inner_texts() if norm(t).startswith("price:"))
        _, antes, depois = separar_alteracao(preco)
        if not valor_confere(antes, 150) or not valor_confere(depois, 180):
            raise Falha(f"C2: audit-change do preço {preco!r}, esperado 'price: 150 → 180'")

    def c3():
        evento = dados["ev_update"]
        linha, i = linha_do_evento(evento, "C3")
        checar_alteracoes_da_linha(linha, evento, "C3")
        textos = linha.locator(SEL_CHANGE).all_inner_texts()
        if len(textos) != 1 or not norm(textos[0]).startswith("description:"):
            raise Falha(f"C3: esperado um único audit-change de description, há {textos}")

    def c4():
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        reembolsos = [e for e in eventos if e["action"] == "payment.refund"]
        if len(reembolsos) != 1:
            raise Falha(f"C4: a API tem {len(reembolsos)} eventos payment.refund (esperado 1)")
        evento = reembolsos[0]
        linha, i = linha_do_evento(evento, "C4")
        checar_alteracoes_da_linha(linha, evento, "C4")
        campos = sorted(separar_alteracao(t)[0] for t in linha.locator(SEL_CHANGE).all_inner_texts())
        if campos != ["enrollment.status", "payment.status"]:
            raise Falha(f"C4: o reembolso mostra os campos {campos}, esperado payment.status e enrollment.status")
        if not any("refunded" in norm(t) for t in linha.locator(SEL_CHANGE).all_inner_texts()):
            raise Falha("C4: o 'depois' do reembolso deveria ser refunded")

    def c5():
        page = tela_gestor()
        eventos = dados["eventos_tela"]
        linhas = linhas_da_tela(page, len(eventos), "C5")
        sem_changes = 0
        for i, evento in enumerate(eventos):
            linha = linhas.nth(i)
            if not evento["changes"]:
                sem_changes += 1
                if linha.locator(SEL_CHANGE).count() != 0:
                    raise Falha(f"C5: o evento {evento['action']} (linha {i}) não tem changes mas a linha tem "
                                f"audit-change: {linha.locator(SEL_CHANGE).all_inner_texts()}")
            else:
                checar_alteracoes_da_linha(linha, evento, f"C5 linha {i} ({evento['action']})")
        if sem_changes == 0:
            raise Falha("C5: o seed deveria ter eventos sem changes (login, recarga de cursos)")
        total_api = sum(len(e["changes"]) for e in eventos)
        total_tela = page.locator(SEL_CHANGE).count()
        if total_tela != total_api:
            raise Falha(f"C5: {total_tela} audit-change na tela, {total_api} itens de changes na API")

    cenario("C1", "evento de preço do gestor 1: um audit-change 'price: 100 → 150'", c1)
    cenario("C2", "evento do gestor 2: audit-change só dos campos alterados, valores e listas em JSON", c2)
    cenario("C3", "update sem preço: audit-change só de description", c3)
    cenario("C4", "reembolso: um evento com payment.status e enrollment.status", c4)
    cenario("C5", "evento sem changes não tem audit-change; total da tela = total da API", c5)

    # --- P1 ---------------------------------------------------------------------------
    def p1():
        page = tela_gestor()
        visivel = page.inner_text("body")
        html = page.content()
        bruto_api = json.dumps(dados["eventos_tela"], ensure_ascii=False)
        proibidos = SENHAS_QUE_NAO_PODEM_APARECER + [EMAIL_INEXISTENTE]
        for texto in proibidos:
            if texto in visivel or texto in html:
                raise Falha(f"P1: texto que não pode aparecer está na página: {texto!r}")
            if texto in bruto_api:
                raise Falha(f"P1: texto que não pode aparecer está na API de auditoria: {texto!r}")

    cenario("P1", "nenhuma senha nem e-mail inexistente na página, no HTML ou na API", p1)

    # --- R1 / R2 / R3 -----------------------------------------------------------------
    def sem_acesso(perfil, email, senha, codigo):
        def fn():
            page = nova_pagina(f"{codigo}-{perfil}")
            paginas[perfil] = page
            login_na_tela(page, base, email, senha, f"{codigo} {perfil}")
            try:
                page.wait_for_url("**/admin", timeout=TIMEOUT * 2)
            except sync_api.TimeoutError:
                raise Falha(f"{codigo}: URL final {page.url} (esperado /admin)")
            page.wait_for_load_state("networkidle")
            try:
                page.locator("ul.nav-tabs button").first.wait_for(state="visible", timeout=TIMEOUT)
            except sync_api.TimeoutError:
                raise Falha(f"{codigo}: o painel de {perfil} não mostrou nenhuma aba")
            abas = abas_visiveis(page)
            if any(ABA.lower() in a.lower() for a in abas):
                raise Falha(f"{codigo}: {perfil} vê a aba de auditoria ({abas})")
            if page.locator(SEL_ROW).count() != 0 or TITULO_TELA in page.inner_text("body"):
                raise Falha(f"{codigo}: a tela de auditoria aparece para {perfil}")
            token = token_de_funcionario(api, email, senha)
            status, _ = _api(api, "GET", CAMINHO_AUDITORIA, token=token)
            if status != 403:
                raise Falha(f"{codigo}: GET {CAMINHO_AUDITORIA} do {perfil} respondeu HTTP {status} (esperado 403)")
        return fn

    cenario("R1", "suporte: sem aba de auditoria nem audit-row; API 403",
            sem_acesso("suporte", SUPORTE_EMAIL, SUPORTE_SENHA, "R1"))
    cenario("R2", "financeiro: sem aba de auditoria nem audit-row; API 403",
            sem_acesso("financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA, "R2"))

    def r3():
        status, _ = _api(api, "GET", CAMINHO_AUDITORIA)
        if status != 401:
            raise Falha(f"R3: sem token a API respondeu HTTP {status} (esperado 401)")
        for forjado in ("abc.def.ghi", "Zm9yamFkby1zZW0tcG9udG9z"):
            status, _ = _api(api, "GET", CAMINHO_AUDITORIA, token=forjado)
            if status != 401:
                raise Falha(f"R3: token forjado {forjado!r} respondeu HTTP {status} (esperado 401)")

    cenario("R3", "sem token e com token forjado: 401 na API de auditoria", r3)

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
    imprimir(f"\nRESULTADO: {passou}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(falhas)
