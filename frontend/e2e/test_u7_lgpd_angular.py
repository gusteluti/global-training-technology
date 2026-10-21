"""E2E da U7 — LGPD (D89, processo enxuto D84). Harness D58.

L1 cadastro: "Criar conta" só habilita depois de marcar o aceite; os links levam aos Termos e à Privacidade.
L2 área do aluno: aviso de gravação no chat.
L3 Meu perfil → "Baixar meus dados" baixa um JSON com o e-mail do aluno.
L4 Meu perfil → excluir com a senha certa (confirm aceito) → login com "Sua conta foi excluída." e o login antigo falha.
"""

import json
import uuid

import pytest
from playwright import sync_api

from apoio_harness_h1 import ambiente_isolado

TIMEOUT = 15000
SENHA = "senha-e2e-u7-2026"


def test_u7_lgpd():
    email = f"aluna.u7.{uuid.uuid4().hex[:8]}@teste.com"
    with ambiente_isolado("u7") as alvo, sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            base = alvo["base"]

            # L1
            page.goto(base + "/cadastro", wait_until="networkidle")
            page.fill("input[name=name]", "Aluna U7")
            page.fill("input[name=email]", email)
            page.fill("input[name=password]", SENHA)
            botao = page.locator("button[type=submit]")
            assert botao.is_disabled(), "Criar conta deveria estar desabilitado sem o aceite"
            page.check('[data-testid="cadastro-aceite"]')
            assert botao.is_enabled()
            botao.click()
            page.locator(".alert-success").wait_for(timeout=TIMEOUT)
            pag_termos = ctx.new_page()
            pag_termos.goto(base + "/privacidade", wait_until="networkidle")
            assert "Política de Privacidade" in pag_termos.inner_text('[data-testid="termos-texto"]')
            pag_termos.close()

            # L2
            page.goto(base + "/login", wait_until="networkidle")
            page.fill("input[name=email]", email)
            page.fill("input[name=password]", SENHA)
            page.click("button[type=submit]")
            page.wait_for_url("**/student", timeout=TIMEOUT)
            aviso = page.locator('[data-testid="chat-aviso-gravacao"]')
            aviso.wait_for(timeout=TIMEOUT)
            assert "gravadas" in aviso.inner_text()

            # L3
            page.goto(base + "/student/perfil", wait_until="networkidle")
            with page.expect_download(timeout=TIMEOUT) as baixado:
                page.click('[data-testid="perfil-exportar"]')
            caminho = baixado.value.path()
            dados = json.loads(open(caminho, encoding="utf-8").read())
            assert dados["conta"]["email"] == email

            # L4
            page.fill('[data-testid="perfil-excluir-senha"]', SENHA)
            page.click('[data-testid="perfil-excluir"]')
            page.wait_for_url("**/login?conta=excluida", timeout=TIMEOUT)
            assert "Sua conta foi excluída." in page.inner_text("body")
            page.fill("input[name=email]", email)
            page.fill("input[name=password]", SENHA)
            page.click("button[type=submit]")
            page.locator(".alert-danger").wait_for(timeout=TIMEOUT)
            assert "/student" not in page.url
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
