"""E2E da área administrativa Angular (Chromium via Playwright): 33 checks, sem pulos.

Contagem (D58): os 29 checks históricos (27 quando os 2 de reembolso eram pulados) viraram 33 porque a aba
"Observabilidade de IA" passou de 1 para 2 gráficos (E7, +1 por perfil) e a Gestão ganhou a aba "Cadastro de
cursos" (L2, +1). Os dois checks de reembolso pela tela rodam sempre (D4).

Login por perfil, abas visíveis por papel (a Gestão ganhou a aba "Cadastro de cursos" na L2/D56; a lista
esperada e o clique por texto exato foram atualizados, sem mudar a intenção), carregamento e gráficos das abas,
reembolso pela tela, erros de console e guard de rota sem login.

Harness isolado (D58, H1): o teste sobe e derruba os próprios servidores; nada precisa estar de pé antes.
  - Backend: frontend/e2e/servidor_e2e_h1.py em processo próprio, porta livre, SQLite temporário (DB_PATH
    isolado), diretório de cursos temporário, segredo de webhook e CORS de teste, Groq e Mercado Pago falsos.
    As contas admin@gt.com / financeiro@gt.com / suporte@gt.com são semeadas pelo próprio helper a partir de
    variáveis de ambiente fabricadas lá (nunca de um .env real).
  - Frontend: `npx ng serve` em porta livre, com proxy temporário /api -> backend de teste.
  - Seed só pela API pública (D4): um curso criado pelo gestor e dois pagamentos APROVADOS (create-checkout
    falso + webhook assinado, E9), um para o reembolso de cada perfil que reembolsa. Reembolso só vale para
    `approved`, então com o banco isolado os dois checks de reembolso pela tela rodam, sem pulos.
  - backend/db.sqlite e backend/courses de desenvolvimento não são abertos nem alterados.
  - E2E_BASE_URL / E2E_API_URL não são mais usados (apontar para servidores de fora quebraria o isolamento).

Pré-requisitos: dependências do backend, node_modules do frontend e o Chromium do Playwright
(py -3 -m playwright install chromium). Portas fixas opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT;
E2E_NG_TIMEOUT (s, padrão 300). Execução (da raiz do repo):
  py -3 -m pytest frontend/e2e/test_admin_angular.py -s
Screenshots vão para a pasta temporária do sistema (ou para E2E_SCREENSHOTS, se definida).
"""

import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import _api, ambiente_isolado  # noqa: E402
from apoio_webhook_mp import enviar_webhook  # noqa: E402  (E9, D48: webhook assinado, id numérico)
from servidor_e2e_h1 import (  # noqa: E402
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)

EXPECTED = {
    GESTAO_EMAIL: (GESTAO_SENHA, ["Financeiro", "Alunos", "Cursos", "Cadastro de cursos", "Observabilidade de IA", "Auditoria"]),
    FINANCEIRO_EMAIL: (FINANCEIRO_SENHA, ["Financeiro", "Alunos", "Cursos", "Observabilidade de IA"]),
    SUPORTE_EMAIL: (SUPORTE_SENHA, ["Alunos", "Cursos", "Observabilidade de IA"]),
}

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_screens"))
CURSO_ID = "curso-e2e"


@pytest.fixture(scope="module")
def servidores():
    """Backend de teste (banco e cursos temporários) e Angular; derruba tudo ao final."""
    with ambiente_isolado("admin") as ambiente:
        yield ambiente


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


@pytest.fixture(scope="module", autouse=True)
def pagamentos_aprovados_para_reembolso(servidores):
    """Semeia dois pagamentos APROVADOS (um para o reembolso de cada perfil que reembolsa).

    A aba Financeiro só mostra o botão 'Reembolsar' em pagamento aprovado (E9: os demais respondem 409);
    sem isso os dois checks de reembolso pela tela seriam pulados (D4). O seed usa só a API do backend de
    teste: o gestor cria o curso, o aluno faz o checkout (Mercado Pago falso) e o webhook assinado aprova.
    """
    api = servidores["api"]
    status, corpo = _api(api, "POST", "/api/token", formulario={"username": GESTAO_EMAIL, "password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login do gestor respondeu HTTP {status}")
    token = corpo["access_token"]
    curso = {
        "id": CURSO_ID, "name": "Curso E2E Reembolso", "description": "Curso do e2e administrativo", "price": 99.9,
        "duration_hours": 4, "level": "Basico", "target_audience": "Alunos", "objectives": ["Objetivo"],
        "topics": ["Topico"], "benefits": ["Beneficio"], "faq": [{"question": "Pergunta", "answer": "Resposta"}],
        "system_prompt": "Prompt", "materials": [],
    }
    status, _ = _api(api, "POST", "/api/admin/create-course", curso, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course respondeu HTTP {status}")
    emails = []
    for i in range(2):
        email = f"e2e.reembolso{i}.{uuid.uuid4().hex[:8]}@teste.com"
        status, checkout = _api(api, "POST", "/api/payments/create-checkout",
                                {"course_id": CURSO_ID, "payer": {"name": f"Aluno E2E Reembolso {i}", "email": email}})
        if status != 200 or not (checkout or {}).get("external_reference"):
            raise RuntimeError(f"seed: create-checkout respondeu HTTP {status}")
        status, _ = enviar_webhook(api, checkout["external_reference"])
        if status != 200:
            raise RuntimeError(f"seed: webhook respondeu HTTP {status}")
        emails.append(email)
    status, painel = _api(api, "GET", "/api/dashboard/financeiro", token=token)
    if status != 200:
        raise RuntimeError(f"seed: painel financeiro respondeu HTTP {status}")
    aprovados = [p for p in painel["payments"] if p["student_email"] in emails and p["status"] == "approved"]
    if len(aprovados) != 2:
        raise RuntimeError(f"seed: esperados 2 pagamentos aprovados, encontrados {len(aprovados)}")
    yield [p["id"] for p in aprovados]


def test_admin_angular_e2e(servidores, browser, pagamentos_aprovados_para_reembolso):
    BASE = servidores["base"]
    OUT.mkdir(parents=True, exist_ok=True)
    results = []

    def check(name, cond, extra=""):
        results.append((name, bool(cond), extra))
        print(("[OK]  " if cond else "[FAIL]") + f" {name}" + (f" -> {extra}" if extra and not cond else ""))

    for email, (password, expected_tabs) in EXPECTED.items():
        role = email.split("@")[0]
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

        page.goto(BASE + "/", wait_until="networkidle")
        page.fill("input[name=email]", email)
        page.fill("input[name=password]", password)
        page.click("button[type=submit]")
        page.wait_for_url("**/admin", timeout=15000)
        page.wait_for_selector("ul.nav-tabs button.nav-link", timeout=15000)
        time.sleep(1.0)

        tabs = [t.strip() for t in page.locator("ul.nav-tabs button.nav-link").all_inner_texts()]
        check(f"{role}: abas visíveis = {expected_tabs}", tabs == expected_tabs, f"obtido {tabs}")

        for tab in tabs:
            # texto exato: "Cursos" também é substring de "Cadastro de cursos" (aba só da Gestão, L2/D56)
            page.locator("ul.nav-tabs button.nav-link", has_text=re.compile(rf"^\s*{re.escape(tab)}\s*$")).click()
            time.sleep(1.8)
            slug = tab.lower().replace(" ", "_")
            page.screenshot(path=str(OUT / f"{role}_{slug}.png"), full_page=True)
            body = page.inner_text("body")
            check(f"{role}: aba '{tab}' carrega sem erro visível", "Não foi possível" not in body)
            canvases = page.locator("canvas")
            for i in range(canvases.count()):
                box = canvases.nth(i).bounding_box()
                check(f"{role}: gráfico '{tab}' renderizado (altura {box and round(box['height'])}px)",
                      box is not None and box["height"] > 100)

        if role == "financeiro" or role == "admin":
            page.locator("ul.nav-tabs button.nav-link", has_text="Financeiro").click()
            time.sleep(1.5)
            # E9 (D48): só pagamento aprovado pode ser reembolsado (os demais respondem 409); clica numa linha 'approved'.
            refund_btns = page.locator("tr", has=page.locator("span.badge", has_text="approved")) \
                              .locator("button", has_text="Reembolsar")
            n_before = refund_btns.count()
            if n_before:
                refunded_antes = page.locator("span.badge", has_text="refunded").count()
                refund_btns.first.click()
                time.sleep(2.0)
                refunded_badges = page.locator("span.badge", has_text="refunded").count()
                check(f"{role}: reembolso pela tela muda status para refunded",
                      refunded_badges > refunded_antes and dialogs,
                      f"badges refunded antes={refunded_antes}, depois={refunded_badges}, dialogs={dialogs}")
                page.screenshot(path=str(OUT / f"{role}_financeiro_apos_reembolso.png"), full_page=True)
            else:
                # D4: com o banco isolado sempre há pagamento aprovado; sem botão, o check de reembolso não pode sumir.
                check(f"{role}: reembolso pela tela muda status para refunded", False,
                      "nenhum pagamento 'approved' com botão Reembolsar na aba Financeiro (o seed deveria tê-lo criado)")

        check(f"{role}: sem erros de console", not console_errors, "; ".join(console_errors[:3]))
        ctx.close()

    # Sem login, /admin volta para a tela de login.
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(BASE + "/admin", wait_until="networkidle")
    time.sleep(1.0)
    check("sem login: /admin volta para a tela de login", page.url.rstrip("/") == BASE.rstrip("/") or page.url.endswith("/"),
          page.url)
    ctx.close()

    passed = sum(1 for _, ok, _ in results if ok)
    falhas = [f"{nome} -> {extra}" for nome, ok, extra in results if not ok]
    print(f"\nRESULTADO: {passed}/{len(results)} checks passaram")
    assert not falhas, "\n".join(falhas)
