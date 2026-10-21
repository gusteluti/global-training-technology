"""E2E da X2 — avaliação do curso (D92). Harness D58.

A1 aluno com matrícula ativa dá nota 4 com comentário: aparece "sua nota: 4 ★".
A2 Gestão vê a média "4,0 ★ (1)" na coluna Avaliação do dashboard de cursos.
"""

import json
import sqlite3

import pytest
from playwright import sync_api

from apoio_harness_h1 import abrir_banco, ambiente_isolado
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA

TIMEOUT = 15000
SENHA = "senha-e2e-x2-2026"
EMAIL = "aluno.x2@teste.com"


def _entrar(page, base, email, senha, destino):
    page.goto(base + "/login", wait_until="networkidle")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", senha)
    page.click("button[type=submit]")
    page.wait_for_url(f"**/{destino}", timeout=TIMEOUT)


def test_x2_avaliacao():
    with ambiente_isolado("x2") as alvo, sync_api.sync_playwright() as p:
        (alvo["cursos_tmp"] / "curso_x2.json").write_text(json.dumps({
            "id": "curso_x2", "name": "Curso Avaliado X2", "price": 30.0,
            "materials": [{"title": "Aula", "url": "https://materiais.test/x2/a.pdf", "type": "pdf"}],
        }), encoding="utf-8")
        Database = abrir_banco(alvo["db_path"])
        from core.security import get_password_hash  # noqa: PLC0415

        user_id = Database.add_user(EMAIL, "Aluno X2", get_password_hash(SENHA), role="student")
        conn = sqlite3.connect(alvo["db_path"])
        conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_x2', 'active')", (user_id,))
        conn.commit()
        conn.close()

        navegador = p.chromium.launch()
        try:
            page = navegador.new_page()
            _entrar(page, alvo["base"], EMAIL, SENHA, "student")
            page.locator('[data-testid="curso-avaliacao-nota"]').first.select_option(label="4 ★")
            page.fill('[data-testid="curso-avaliacao-comentario"]', "Gostei bastante")
            page.click('[data-testid="curso-avaliacao-enviar"]')
            page.locator('[data-testid="curso-avaliacao-atual"]', has_text="4 ★").wait_for(timeout=TIMEOUT)

            gestao = navegador.new_page()
            _entrar(gestao, alvo["base"], GESTAO_EMAIL, GESTAO_SENHA, "admin")
            gestao.locator("button.nav-link", has_text="Cursos").first.click(timeout=TIMEOUT)
            linha = gestao.locator("tr", has_text="Curso Avaliado X2")
            linha.first.wait_for(timeout=TIMEOUT)
            media = linha.first.locator('[data-testid="curso-avaliacao-media"]').inner_text()
            assert "4,0" in media and "(1)" in media, media
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
