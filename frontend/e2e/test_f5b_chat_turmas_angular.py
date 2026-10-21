"""E2E da F5b no Angular — chat do aluno com turmas e botão de matrícula; login com `next` (D76, parte do U9).

Contrato de tela (D76):
  - no chat do aluno (/student), cada ação `enroll` da resposta vira o botão [data-testid=chat-acao-matricular] com o
    label do servidor (`Matricular na turma <nome>` / `Matricular no curso`) e leva a
    `/catalogo?curso=<id>&turma=<id>` (sem `turma` quando `class_id` é nulo); o catálogo chega com a turma
    pré-selecionada (D75);
  - as ações não são persistidas: depois de recarregar /student, o histórico volta sem botões;
  - AuthGuard: quem não está logado e pede uma rota protegida vai para `/login?next=<rota pedida>`;
  - login de ALUNO segue o `next` só se for caminho interno (começa com `/`, não com `//`, sem esquema); senão vai
    para /student. Funcionário continua indo para /admin.

Harness (apoio_harness_f5b): backend do D58 com catálogo do bot no diretório temporário de cursos e Groq falso que
ecoa ("Resposta simulada do assistente a: <mensagem>"), `ng serve` em porta livre com proxy temporário. Seed: cursos
"Omega Analytics" (turmas Lotada Express +3d cap 1 ocupada, Alfa Noturna +5d, Beta Sabado +8d sem capacidade, Gama
Integral +8d, Delta Livre sem data, Iniciada Antiga -2d) e "Sigma Design" (sem turmas), pela API da Gestão; turmas
por Database.create_class. Ações esperadas para Omega: Alfa, Beta, Gama (ordem D75, até 3, com vaga).

Cenários:
  S0 pré-condição: aluno A entra, vê o chat e recebe resposta a uma pergunta geral, sem botão de matrícula  [passa no red]
  G1 pergunta sobre Omega: 3 botões chat-acao-matricular com os labels exatos, na ordem
  G2 clicar no primeiro leva a /catalogo?curso=<omega>&turma=<alfa> com a turma Alfa pré-selecionada
  G3 recarregar /student: o histórico volta e nenhum botão de matrícula aparece (ações não persistidas; exige G1)
  G4 aluno B pergunta sobre Sigma (sem turmas): um botão "Matricular no curso" que leva a /catalogo?curso=<sigma>
  G5 texto do bot com link markdown de matrícula não vira botão: pergunta geral com o link -> nenhum botão
  G6 não logado em /catalogo?curso=<omega>&turma=<gama> vai para /login?next=<a rota pedida>
  G7 login do aluno C nessa tela volta a /catalogo?curso=<omega>&turma=<gama> com a Gama pré-selecionada
  G8 `next` externo (//evil.example, https://evil.example, javascript:...) é ignorado: aluno vai para /student [caract.]
  G9 funcionário (Gestão) com `next` interno vai para /admin                                           [caract.]
  G10 sem erros de console de /api (4xx/5xx) nem exceções de página

Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_f5b_chat_turmas_angular.py -s
"""

import re
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import (  # noqa: E402
    GESTAO_EMAIL, GESTAO_SENHA, LABEL_CURSO, SENHA_ALUNO, ambiente_f5b, semear_aluno, semear_cursos_f5b,
)

TIMEOUT = 5000
ERRO_HTTP = re.compile(r"status of (\d{3})")
SEL_PAINEL = '[data-testid="chat-panel"]'
SEL_CAMPO = '[data-testid="chat-input"]'
SEL_ENVIAR = '[data-testid="chat-send"]'
SEL_MENSAGEM = '[data-testid="chat-message"]'
SEL_ACAO = '[data-testid="chat-acao-matricular"]'
PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "
PERGUNTA_OMEGA = "Quais sao as turmas e as datas de Omega Analytics?"
PERGUNTA_SIGMA = "Me conte sobre Sigma Design"
PERGUNTA_GERAL = "Gostaria de uma recomendacao geral da plataforma"
LINK_FALSO = "[Matricular na turma Alfa Noturna](https://evil.example/pagar)"
NEXTS_EXTERNOS = ["//evil.example", "https://evil.example", "javascript:alert(1)"]


class Falha(Exception):
    """Falha de um passo de cenário; a mensagem diz o que faltou na tela."""


@pytest.fixture(scope="module")
def servidores():
    with ambiente_f5b("f5b_angular") as ambiente:
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _url(page):
    partes = urllib.parse.urlparse(page.url)
    return partes, urllib.parse.parse_qs(partes.query)


def test_f5b_chat_turmas_angular_e2e(servidores, browser):
    base = servidores["base"]
    resultados, erros_console, contextos = [], [], []
    estado = {}

    seed = {"ok": False, "erro": ""}
    try:
        dados = semear_cursos_f5b(servidores["api"], servidores["db_path"])
        email_a, _ = semear_aluno(servidores["db_path"], "a")
        email_b, _ = semear_aluno(servidores["db_path"], "b")
        email_c, _ = semear_aluno(servidores["db_path"], "c")
        emails_externos = [semear_aluno(servidores["db_path"], f"ext{i}")[0] for i in range(len(NEXTS_EXTERNOS))]
        seed["ok"] = True
    except Exception as erro:
        seed["erro"] = f"{type(erro).__name__}: {erro}"

    def nova_pagina():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contextos.append(ctx)
        page = ctx.new_page()

        def ao_console(msg):
            url = msg.location.get("url") or ""
            if msg.type == "error" and ERRO_HTTP.search(msg.text) and "/api/" in url:
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
            linha = str(erro).splitlines()[0] if str(erro) else type(erro).__name__
            resultados.append((codigo, nome, False, linha))
            print(f"[FAIL] {codigo} {nome} -> {linha}")

    def preencher_login(page, email, senha):
        page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
        page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
        page.locator("button[type=submit]").first.click(timeout=TIMEOUT)

    def entrar_no_student(email):
        page = nova_pagina()
        page.goto(base + "/", wait_until="networkidle")
        preencher_login(page, email, SENHA_ALUNO)
        try:
            page.wait_for_url("**/student", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"login de {email} não levou a /student (URL {page.url})")
        page.wait_for_load_state("networkidle")
        try:
            page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        except sync_api.TimeoutError:
            raise Falha("[data-testid=chat-panel] não está visível em /student")
        return page

    def enviar(page, texto, rotulo):
        antes = page.locator(SEL_MENSAGEM).count()
        page.locator(SEL_CAMPO).first.fill(texto, timeout=TIMEOUT)
        page.locator(SEL_ENVIAR).first.click(timeout=TIMEOUT)
        fim = time.time() + 15
        while time.time() < fim:
            msgs = page.eval_on_selector_all(
                SEL_MENSAGEM, "els => els.map(e => ({role: e.getAttribute('data-role'), text: e.innerText}))")
            if len(msgs) >= antes + 2 and msgs[-1]["role"] == "assistant" and PREFIXO_RESPOSTA in msgs[-1]["text"]:
                page.wait_for_timeout(300)
                return msgs[-1]["text"]
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: a resposta do bot não apareceu na tela")

    def botoes(page):
        return [_normalizar(t) for t in page.locator(SEL_ACAO).all_inner_texts()]

    def esperar_botoes(page, quantidade, rotulo):
        fim = time.time() + 8
        while time.time() < fim:
            if page.locator(SEL_ACAO).count() == quantidade:
                return botoes(page)
            page.wait_for_timeout(150)
        raise Falha(f"{rotulo}: esperava {quantidade} [data-testid=chat-acao-matricular], há "
                    f"{page.locator(SEL_ACAO).count()} ({botoes(page)})")

    def selecao_do_catalogo(page, curso, rotulo):
        try:
            page.locator('[data-testid="catalogo-card"]').first.wait_for(state="visible", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: o catálogo não carregou em {page.url}")
        page.wait_for_load_state("networkidle")
        sel = page.locator('[data-testid="catalogo-card"]').filter(has_text=curso["nome"]) \
            .locator('[data-testid="catalogo-turma"]')
        if sel.count() != 1:
            raise Falha(f"{rotulo}: o cartão de {curso['nome']} não tem [data-testid=catalogo-turma]")
        return sel.first

    def exigir_catalogo(page, curso_id, turma_id, rotulo):
        try:
            page.wait_for_url("**/catalogo**", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"{rotulo}: não chegou a /catalogo (URL {page.url})")
        partes, qs = _url(page)
        if partes.path.rstrip("/") != "/catalogo":
            raise Falha(f"{rotulo}: caminho {partes.path} (esperado /catalogo)")
        if qs.get("curso") != [curso_id]:
            raise Falha(f"{rotulo}: curso={qs.get('curso')} (esperado {curso_id})")
        esperado_turma = None if turma_id is None else [str(turma_id)]
        if qs.get("turma") != esperado_turma:
            raise Falha(f"{rotulo}: turma={qs.get('turma')} (esperado {esperado_turma})")

    # ---------------------------------------------------------------------------------------

    def s0():
        page = entrar_no_student(email_a)
        estado["a"] = page
        texto = enviar(page, PERGUNTA_GERAL, "S0")
        if PERGUNTA_GERAL not in texto:
            raise Falha(f"S0: resposta inesperada {texto!r}")
        if page.locator(SEL_ACAO).count() != 0:
            raise Falha("S0: pergunta geral mostrou botão de matrícula")

    def g1():
        page = estado.get("a")
        if page is None:
            raise Falha("pré-requisito: S0 falhou")
        enviar(page, PERGUNTA_OMEGA, "G1")
        esperados = [a["label"] for a in dados["acoes_omega"]]
        achados = esperar_botoes(page, 3, "G1")
        if achados != esperados:
            raise Falha(f"G1: labels {achados} (esperado {esperados})")
        estado["g1"] = True

    def g2():
        page = estado["a"]
        if page.locator(SEL_ACAO).count() != 3:
            raise Falha("pré-requisito: G1 falhou")
        page.locator(SEL_ACAO).first.click(timeout=TIMEOUT)
        exigir_catalogo(page, dados["omega"]["id"], dados["turmas"]["alfa"]["id"], "G2")
        sel = selecao_do_catalogo(page, dados["omega"], "G2")
        if sel.input_value() != str(dados["turmas"]["alfa"]["id"]):
            raise Falha(f"G2: a turma Alfa não veio pré-selecionada (valor {sel.input_value()!r})")

    def g3():
        if not estado.get("g1"):
            raise Falha("pré-requisito: G1 falhou (sem botões antes do reload, o check não prova nada)")
        page = estado["a"]
        page.goto(base + "/student", wait_until="networkidle")
        page.locator(SEL_PAINEL).first.wait_for(state="visible", timeout=TIMEOUT)
        fim = time.time() + 8
        while time.time() < fim and page.locator(SEL_MENSAGEM).count() < 4:
            page.wait_for_timeout(150)
        if page.locator(SEL_MENSAGEM).count() < 4:
            raise Falha("G3: o histórico não voltou depois de recarregar")
        page.wait_for_timeout(500)
        if page.locator(SEL_ACAO).count() != 0:
            raise Falha(f"G3: {page.locator(SEL_ACAO).count()} botões de matrícula no histórico recarregado")

    def g4():
        page = entrar_no_student(email_b)
        enviar(page, PERGUNTA_SIGMA, "G4")
        achados = esperar_botoes(page, 1, "G4")
        if achados != [LABEL_CURSO]:
            raise Falha(f"G4: labels {achados} (esperado {[LABEL_CURSO]})")
        page.locator(SEL_ACAO).first.click(timeout=TIMEOUT)
        exigir_catalogo(page, dados["sigma"]["id"], None, "G4")
        estado["b"] = page

    def g5():
        page = entrar_no_student(email_c)
        enviar(page, f"{PERGUNTA_GERAL} {LINK_FALSO}", "G5")
        page.wait_for_timeout(500)
        if page.locator(SEL_ACAO).count() != 0:
            raise Falha("G5: link markdown do texto do bot virou botão de matrícula")
        enviar(page, f"{PERGUNTA_OMEGA} {LINK_FALSO}", "G5")
        achados = esperar_botoes(page, 3, "G5")
        hrefs = [page.locator(SEL_ACAO).nth(i).get_attribute("href") or "" for i in range(3)]
        if any("evil.example" in h for h in hrefs):
            raise Falha(f"G5: botão de matrícula aponta para o link do texto do bot: {hrefs}")
        if achados != [a["label"] for a in dados["acoes_omega"]]:
            raise Falha(f"G5: labels {achados}")
        estado["c_page"] = page

    def g6():
        page = nova_pagina()
        destino = f"/catalogo?curso={dados['omega']['id']}&turma={dados['turmas']['gama']['id']}"
        page.goto(base + destino, wait_until="networkidle")
        try:
            page.wait_for_url("**/login?**", timeout=TIMEOUT * 2)
        except sync_api.TimeoutError:
            raise Falha(f"G6: o AuthGuard não levou a /login?next=... (URL {page.url})")
        partes, qs = _url(page)
        if partes.path.rstrip("/") != "/login" or qs.get("next") != [destino]:
            raise Falha(f"G6: URL {page.url} (esperado /login?next={destino} codificado)")
        estado["g6"] = page

    def g7():
        page = estado.get("g6")
        if page is None:
            raise Falha("pré-requisito: G6 falhou")
        _email, _uid = semear_aluno(servidores["db_path"], "g7")
        preencher_login(page, _email, SENHA_ALUNO)
        exigir_catalogo(page, dados["omega"]["id"], dados["turmas"]["gama"]["id"], "G7")
        sel = selecao_do_catalogo(page, dados["omega"], "G7")
        if sel.input_value() != str(dados["turmas"]["gama"]["id"]):
            raise Falha(f"G7: a turma Gama não veio pré-selecionada (valor {sel.input_value()!r})")

    def g8():
        for externo, email in zip(NEXTS_EXTERNOS, emails_externos):
            page = nova_pagina()
            page.goto(base + "/login?next=" + urllib.parse.quote(externo, safe=""), wait_until="networkidle")
            preencher_login(page, email, SENHA_ALUNO)
            try:
                page.wait_for_url("**/student", timeout=TIMEOUT * 3)
            except sync_api.TimeoutError:
                raise Falha(f"G8: next={externo!r} não levou a /student (URL {page.url})")
            partes, _ = _url(page)
            if f"{partes.scheme}://{partes.netloc}" != base:
                raise Falha(f"G8: next={externo!r} saiu da aplicação: {page.url}")

    def g9():
        page = nova_pagina()
        destino = f"/catalogo?curso={dados['omega']['id']}&turma={dados['turmas']['alfa']['id']}"
        page.goto(base + "/login?next=" + urllib.parse.quote(destino, safe=""), wait_until="networkidle")
        preencher_login(page, GESTAO_EMAIL, GESTAO_SENHA)
        try:
            page.wait_for_url("**/admin", timeout=TIMEOUT * 3)
        except sync_api.TimeoutError:
            raise Falha(f"G9: funcionário com next não foi para /admin (URL {page.url})")

    def g10():
        if erros_console:
            raise Falha(f"G10: {len(erros_console)} erro(s): {erros_console[:3]}")

    try:
        cenario("S0", "pré-condição: chat do aluno responde sem botão na pergunta geral", s0)
        cenario("G1", "pergunta sobre o curso mostra 3 botões com os labels, na ordem", g1)
        cenario("G2", "botão leva ao catálogo com a turma pré-selecionada", g2)
        cenario("G3", "histórico recarregado sem botões (ações não persistidas)", g3)
        cenario("G4", "curso sem turmas: 'Matricular no curso' leva a /catalogo?curso=", g4)
        cenario("G5", "link markdown do texto do bot não vira botão de matrícula", g5)
        cenario("G6", "não logado em /catalogo vai para /login?next=", g6)
        cenario("G7", "login do aluno volta ao catálogo com a turma pré-selecionada", g7)
        cenario("G8", "next externo é ignorado: aluno vai para /student", g8)
        cenario("G9", "funcionário com next vai para /admin", g9)
        cenario("G10", "sem erros de console de /api nem exceções de página", g10)
    finally:
        for ctx in contextos:
            try:
                ctx.close()
            except Exception:
                pass

    falhas = [r for r in resultados if not r[2]]
    print(f"\nF5b Angular: {len(resultados) - len(falhas)}/{len(resultados)} checks passaram")
    assert not falhas, "\n".join(f"{c} {n}: {m}" for c, n, _, m in falhas)
