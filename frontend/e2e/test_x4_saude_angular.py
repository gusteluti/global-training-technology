"""E2E da X4 — cartão "Saúde do sistema" na aba Observabilidade de IA (D90). Harness D58."""

import pytest
from playwright import sync_api

from apoio_harness_h1 import ambiente_isolado
from servidor_e2e_h1 import SUPORTE_EMAIL, SUPORTE_SENHA

TIMEOUT = 15000


def test_x4_saude():
    with ambiente_isolado("x4") as alvo, sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            page = navegador.new_page()
            page.goto(alvo["base"] + "/login", wait_until="networkidle")
            page.fill("input[name=email]", SUPORTE_EMAIL)
            page.fill("input[name=password]", SUPORTE_SENHA)
            page.click("button[type=submit]")
            page.wait_for_url("**/admin", timeout=TIMEOUT)
            page.locator("button.nav-link", has_text="Observabilidade de IA").click(timeout=TIMEOUT)
            cartao = page.locator('[data-testid="saude-sistema"]')
            cartao.wait_for(timeout=TIMEOUT)
            texto = cartao.inner_text()
            assert "No ar" in texto and "Banco de dados" in texto
            assert "TEST-" not in page.inner_text("body")
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
