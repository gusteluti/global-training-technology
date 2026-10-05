"""E2E da área administrativa Angular (Chromium via Playwright): 29 checks.

Login por perfil, abas visíveis por papel, carregamento e gráficos das abas,
reembolso pela tela, erros de console e guard de rota sem login.

Pré-requisitos (ambos precisam estar de pé antes de rodar):
  - backend FastAPI em http://localhost:8000  (cd backend && uvicorn app:app --port 8000)
  - Angular em http://localhost:4200          (cd frontend && npx ng serve)
  - contas admin@gt.com, financeiro@gt.com e suporte@gt.com cadastradas no backend
    (semeadas a partir do .env: ADMIN_EMAIL/FINANCIAL_EMAIL/SUPPORT_EMAIL e as senhas de perfil)
  - Chromium do Playwright instalado: py -3 -m playwright install chromium

Porta diferente do 4200: defina E2E_BASE_URL (ex.: http://localhost:4300).
Execução: py -3 -m pytest frontend/e2e -s
Screenshots vão para a pasta temporária do sistema (ou para E2E_SCREENSHOTS, se definida).
"""

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:4200")

EXPECTED = {
    "admin@gt.com": ("admin123", ["Financeiro", "Alunos", "Cursos", "Observabilidade de IA", "Auditoria"]),
    "financeiro@gt.com": ("fin123", ["Financeiro", "Alunos", "Cursos", "Observabilidade de IA"]),
    "suporte@gt.com": ("sup123", ["Alunos", "Cursos", "Observabilidade de IA"]),
}

OUT = Path(os.environ.get("E2E_SCREENSHOTS", Path(tempfile.gettempdir()) / "gt_e2e_screens"))


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
def pagamentos_pendentes_para_reembolso():
    """Semeia dois pagamentos pendentes (um para o reembolso de cada perfil que reembolsa).

    A aba Financeiro so mostra o botao 'Reembolsar' para pagamentos nao reembolsados; com banco
    vazio os dois checks de reembolso pela tela seriam pulados. O seed usa a camada Database do
    backend (mesmo db.sqlite do servidor), sem tocar em codigo de producao.
    """
    backend = Path(__file__).resolve().parents[2] / "backend"
    sys.path.insert(0, str(backend))
    from db import Database

    Database.init_db()
    user_id = Database.get_or_create_user("e2e.reembolso@teste.com", "Aluno E2E Reembolso")
    ids = []
    for _ in range(2):
        enrollment_id = Database.create_enrollment(user_id, "curso-e2e", f"e2e-{uuid.uuid4().hex[:12]}")
        ids.append(Database.record_payment(enrollment_id, 99.90, "e2e-seed"))
    yield ids


def test_admin_angular_e2e(browser, pagamentos_pendentes_para_reembolso):
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
            page.locator("ul.nav-tabs button.nav-link", has_text=tab).click()
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
            refund_btns = page.locator("button", has_text="Reembolsar")
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
