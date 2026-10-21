"""E2E da X1 — progresso nos materiais e certificado (D91). Harness D58.

P1 aluno com matrícula ativa vê "0 de 2 concluídos" e nenhum botão de certificado.
P2 marca os dois materiais: "2 de 2 concluídos" e aparece "Baixar certificado".
P3 o certificado baixa como PDF.
"""

import json
import sqlite3

import pytest
from playwright import sync_api

from apoio_harness_h1 import abrir_banco, ambiente_isolado

TIMEOUT = 15000
SENHA = "senha-e2e-x1-2026"
EMAIL = "aluno.x1@teste.com"


def test_x1_progresso():
    with ambiente_isolado("x1") as alvo, sync_api.sync_playwright() as p:
        (alvo["cursos_tmp"] / "curso_x1.json").write_text(json.dumps({
            "id": "curso_x1", "name": "Curso X1", "price": 50.0, "duration_hours": 12,
            "materials": [{"title": "Aula 1", "url": "https://materiais.test/x1/a1.pdf", "type": "pdf"},
                          {"title": "Aula 2", "url": "https://materiais.test/x1/a2.pdf", "type": "pdf"}],
        }), encoding="utf-8")
        Database = abrir_banco(alvo["db_path"])
        from core.security import get_password_hash  # noqa: PLC0415

        user_id = Database.add_user(EMAIL, "Aluno X1", get_password_hash(SENHA), role="student")
        conn = sqlite3.connect(alvo["db_path"])
        conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_x1', 'active')", (user_id,))
        conn.commit()
        conn.close()

        navegador = p.chromium.launch()
        try:
            page = navegador.new_context(accept_downloads=True).new_page()
            page.goto(alvo["base"] + "/login", wait_until="networkidle")
            page.fill("input[name=email]", EMAIL)
            page.fill("input[name=password]", SENHA)
            page.click("button[type=submit]")
            page.wait_for_url("**/student", timeout=TIMEOUT)

            progresso = page.locator('[data-testid="curso-progresso"]')
            progresso.wait_for(timeout=TIMEOUT)
            assert progresso.inner_text().strip() == "0 de 2 concluídos"
            assert page.locator('[data-testid="curso-certificado"]').count() == 0

            caixas = page.locator('[data-testid="material-concluido"]')
            caixas.nth(0).check()
            page.locator('[data-testid="curso-progresso"]', has_text="1 de 2").wait_for(timeout=TIMEOUT)
            caixas.nth(1).check()
            page.locator('[data-testid="curso-progresso"]', has_text="2 de 2").wait_for(timeout=TIMEOUT)

            with page.expect_download(timeout=TIMEOUT) as baixado:
                page.click('[data-testid="curso-certificado"]')
            assert open(baixado.value.path(), "rb").read().startswith(b"%PDF-")
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
