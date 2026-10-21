"""E2E da S3 — aba "Equipe" (D85, processo enxuto D84). Harness D58 (servidores e banco isolados).

G1 Gestão abre a aba Equipe e vê as contas de funcionário do harness.
G2 Gestão convida uma pessoa (Suporte): aparece `equipe-ok` e a nova linha.
G3 Gestão troca o perfil da pessoa convidada para Financeiro (a API confirma).
G4 Gestão desativa a pessoa (confirm aceito): aparece o badge `equipe-desativada`.
G5 Suporte não vê a aba Equipe.
"""

import json
import urllib.request

import pytest
from playwright import sync_api

from apoio_harness_h1 import ambiente_isolado
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA

TIMEOUT = 15000
NOVO_EMAIL = "convidado.s3@teste.com"


def _entrar(page, base, email, senha):
    page.goto(base + "/login", wait_until="networkidle")
    page.locator("input[name=email]").first.fill(email, timeout=TIMEOUT)
    page.locator("input[name=password]").first.fill(senha, timeout=TIMEOUT)
    page.locator("button[type=submit]").first.click(timeout=TIMEOUT)
    page.wait_for_url("**/admin", timeout=TIMEOUT)


def _abrir_aba(page, nome):
    page.locator("button.nav-link", has_text=nome).first.click(timeout=TIMEOUT)


def _staff_via_api(api, email, senha):
    dados = f"username={email}&password={senha}".encode()
    req = urllib.request.Request(api + "/api/token", data=dados,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = json.loads(urllib.request.urlopen(req).read())["access_token"]
    req = urllib.request.Request(api + "/api/admin/staff", headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())["staff"]


def test_s3_equipe():
    with ambiente_isolado("s3") as alvo, sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            page = navegador.new_context(viewport={"width": 1366, "height": 900}).new_page()
            page.on("dialog", lambda d: d.accept())
            _entrar(page, alvo["base"], GESTAO_EMAIL, GESTAO_SENHA)

            # G1
            _abrir_aba(page, "Equipe")
            linhas = page.locator('[data-testid="equipe-row"]')
            linhas.first.wait_for(timeout=TIMEOUT)
            assert GESTAO_EMAIL in page.inner_text("body")

            # G2
            page.fill('[data-testid="equipe-email"]', NOVO_EMAIL)
            page.fill('[data-testid="equipe-nome"]', "Pessoa Convidada")
            page.select_option('[data-testid="equipe-perfil"]', "support")
            page.click('[data-testid="equipe-convidar"]')
            page.locator('[data-testid="equipe-ok"]').wait_for(timeout=TIMEOUT)
            linha = linhas.filter(has_text=NOVO_EMAIL)
            linha.first.wait_for(timeout=TIMEOUT)

            # G3
            linha.first.locator('[data-testid="equipe-perfil-select"]').select_option("financial")
            page.locator('[data-testid="equipe-ok"]', has_text="Financeiro").wait_for(timeout=TIMEOUT)
            pessoa = [s for s in _staff_via_api(alvo["api"], GESTAO_EMAIL, GESTAO_SENHA) if s["email"] == NOVO_EMAIL][0]
            assert pessoa["role"] == "financial"

            # G4
            linha.first.locator('[data-testid="equipe-desativar"]').click(timeout=TIMEOUT)
            linhas.filter(has_text=NOVO_EMAIL).locator('[data-testid="equipe-desativada"]').wait_for(timeout=TIMEOUT)

            # G5
            page2 = navegador.new_context().new_page()
            _entrar(page2, alvo["base"], SUPORTE_EMAIL, SUPORTE_SENHA)
            page2.locator("button.nav-link").first.wait_for(timeout=TIMEOUT)
            assert page2.locator("button.nav-link", has_text="Equipe").count() == 0
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
