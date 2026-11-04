"""E2E da sala do curso (D103). Harness D58.

G1 Gestão cadastra vídeo, extra e arquivo pela tela; link que não é de vídeo é recusado.
A1 aluno entra pelo botão do cartão, vê módulos, extras e o player.
A2 baixa o arquivo; marcar as aulas libera o certificado, sem precisar do extra.
A3 aluno sem matrícula ativa não abre a sala.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from playwright import sync_api

from apoio_harness_h1 import abrir_banco, ambiente_isolado

TIMEOUT = 15000
SENHA = "senha-e2e-sala-2026"
GESTAO = "gestao.sala@teste.com"
ALUNO = "aluno.sala@teste.com"
CANCELADO = "cancelado.sala@teste.com"
PDF = b"%PDF-1.4 apostila do e2e"


def _entrar(page, base, email, destino):
    page.goto(base + "/login", wait_until="networkidle")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", SENHA)
    page.click("button[type=submit]")
    page.wait_for_url(f"**/{destino}", timeout=TIMEOUT)


def _preencher(page, modulo, titulo, tipo):
    page.fill('[data-testid="conteudo-modulo"]', modulo)
    page.fill('[data-testid="conteudo-titulo"]', titulo)
    page.select_option('[data-testid="conteudo-tipo"]', tipo)


def _salvar(page, total):
    page.click('[data-testid="conteudo-salvar"]')
    page.locator('[data-testid="conteudo-linha"]').nth(total - 1).wait_for(timeout=TIMEOUT)


def test_sala_do_curso():
    with ambiente_isolado("sala") as alvo, sync_api.sync_playwright() as p:
        (alvo["cursos_tmp"] / "curso_sala.json").write_text(json.dumps({
            "id": "curso_sala", "name": "Curso Sala", "price": 50.0, "duration_hours": 12,
            "description": "d", "level": "b", "target_audience": "t", "objectives": [], "topics": [], "benefits": [],
            "faq": [], "system_prompt": "p",
        }), encoding="utf-8")
        Database = abrir_banco(alvo["db_path"])
        from core.security import get_password_hash  # noqa: PLC0415

        senha = get_password_hash(SENHA)
        Database.add_user(GESTAO, "Gestão Sala", senha, role="admin")
        aluno_id = Database.add_user(ALUNO, "Aluno Sala", senha, role="student")
        cancelado_id = Database.add_user(CANCELADO, "Aluno Cancelado", senha, role="student")
        conn = sqlite3.connect(alvo["db_path"])
        conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_sala', 'active')",
                     (aluno_id,))
        matricula_cancelada = conn.execute(
            "INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_sala', 'cancelled')",
            (cancelado_id,)).lastrowid
        conn.commit()
        conn.close()

        arquivo = Path(tempfile.mkdtemp()) / "apostila.pdf"
        arquivo.write_bytes(PDF)

        navegador = p.chromium.launch()
        try:
            gestao = navegador.new_context().new_page()
            _entrar(gestao, alvo["base"], GESTAO, "admin")
            gestao.get_by_role("button", name="Cadastro de cursos").click()
            gestao.locator('[data-testid="curso-conteudos"]').first.click()
            gestao.locator('[data-testid="conteudos-painel"]').wait_for(timeout=TIMEOUT)

            _preencher(gestao, "Módulo 1", "Vídeo errado", "video")
            gestao.fill('[data-testid="conteudo-url"]', "https://site.example/video")
            gestao.click('[data-testid="conteudo-salvar"]')
            erro = gestao.locator('[data-testid="conteudo-erro"]')
            erro.wait_for(timeout=TIMEOUT)
            assert "YouTube" in erro.inner_text()

            _preencher(gestao, "Módulo 1", "Aula em vídeo", "video")
            gestao.fill('[data-testid="conteudo-url"]', "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            _salvar(gestao, 1)

            _preencher(gestao, "Módulo 1", "Apostila", "file")
            gestao.set_input_files('[data-testid="conteudo-arquivo"]', str(arquivo))
            _salvar(gestao, 2)

            gestao.check('[data-testid="conteudo-extra"]')
            gestao.fill('[data-testid="conteudo-titulo"]', "Leitura extra")
            gestao.select_option('[data-testid="conteudo-tipo"]', "link")
            gestao.fill('[data-testid="conteudo-url"]', "https://materiais.test/extra")
            _salvar(gestao, 3)

            aluno = navegador.new_context(accept_downloads=True).new_page()
            _entrar(aluno, alvo["base"], ALUNO, "student")
            aluno.click('[data-testid="curso-entrar"]')
            aluno.wait_for_url("**/student/curso/*", timeout=TIMEOUT)
            player = aluno.locator('[data-testid="sala-player"]')
            player.locator("iframe").wait_for(state="attached", timeout=TIMEOUT)
            assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in player.locator("iframe").get_attribute("src")
            assert aluno.locator('[data-testid="sala-item"]').count() == 2
            assert aluno.locator('[data-testid="sala-extra"]').count() == 1
            assert aluno.locator('[data-testid="sala-progresso"]').inner_text().strip() == "0 de 2 concluídos"

            assert aluno.locator('[data-testid="sala-concluido"]').count() == 0, "vídeo não se conclui à mão"
            conn = sqlite3.connect(alvo["db_path"])
            matricula = conn.execute("SELECT id FROM enrollments WHERE user_id = ?", (aluno_id,)).fetchone()[0]
            conteudo = conn.execute("SELECT id FROM course_contents WHERE kind = 'video'").fetchone()[0]
            conn.execute("INSERT INTO material_progress (enrollment_id, url, completed_at) VALUES (?, ?, datetime('now'))",
                         (matricula, f"conteudo:{conteudo}"))
            conn.commit()
            conn.close()
            aluno.reload(wait_until="networkidle")
            aluno.locator('[data-testid="sala-progresso"]', has_text="1 de 2").wait_for(timeout=TIMEOUT)
            aluno.locator('[data-testid="sala-item"]').first.click()

            aluno.click('[data-testid="sala-proxima"]')
            aluno.locator('[data-testid="sala-titulo"]', has_text="Apostila").wait_for(timeout=TIMEOUT)
            with aluno.expect_download(timeout=TIMEOUT) as baixado:
                aluno.click('[data-testid="sala-baixar"]')
            assert open(baixado.value.path(), "rb").read() == PDF

            aluno.check('[data-testid="sala-concluido"]')
            with aluno.expect_download(timeout=TIMEOUT) as certificado:
                aluno.click('[data-testid="sala-certificado"]')
            assert open(certificado.value.path(), "rb").read().startswith(b"%PDF-")

            conn = sqlite3.connect(alvo["db_path"])
            conn.execute("UPDATE enrollments SET status = 'refunded' WHERE user_id = ?", (aluno_id,))
            conn.commit()
            conn.close()
            aluno.locator('[data-testid="sala-item"]').first.click()
            encerrado = aluno.locator('[data-testid="sala-erro"]')
            encerrado.wait_for(timeout=TIMEOUT)
            assert "encerrado" in encerrado.inner_text()

            sem_acesso = navegador.new_context().new_page()
            _entrar(sem_acesso, alvo["base"], CANCELADO, "student")
            assert sem_acesso.locator('[data-testid="curso-entrar"]').count() == 0
            sem_acesso.goto(f"{alvo['base']}/student/curso/{matricula_cancelada}", wait_until="networkidle")
            sem_acesso.locator('[data-testid="sala-erro"]').wait_for(timeout=TIMEOUT)
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
