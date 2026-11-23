"""E2E da X4 — cartão "Saúde do sistema" na aba Observabilidade de IA (D90). Harness D58.

SG1 (D109, P2; ajuste mecânico 4.3, D109 -> D111): o detalhe de saúde só sai de `GET /api/dashboard/saude`, que é da
Gestão (Suporte e Financeiro recebem 403). O cartão com os serviços passa a ser conferido na conta da Gestão; antes o
teste entrava como Suporte. Fica vermelho até o frontend ler a rota nova (o `/api/health` público só traz o status).
"""

import pytest
from playwright import sync_api

from apoio_harness_h1 import ambiente_isolado
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA

TIMEOUT = 15000


def test_x4_saude():
    with ambiente_isolado("x4") as alvo, sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            page = navegador.new_page()
            page.goto(alvo["base"] + "/login", wait_until="networkidle")
            page.fill("input[name=email]", GESTAO_EMAIL)
            page.fill("input[name=password]", GESTAO_SENHA)
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
