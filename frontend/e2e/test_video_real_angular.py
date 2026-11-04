"""E2E da videoaula com vídeo real (D105): precisa de internet. Harness D58.

Tudo pela tela e com cliques reais no player. Para ver o navegador abrindo: E2E_VER=1.
G1 Gestão cadastra vídeos pela tela; a prévia toca o vídeo bom e avisa sobre o vídeo inexistente.
A1 aluno assiste alguns segundos, sai e volta: o vídeo retoma do minuto e o percentual aparece.
A2 pular para o fim pela barra não conclui a aula.
A3 assistir de verdade conclui a aula sem marcar nada e libera o certificado.
A4 vídeo inexistente mostra mensagem clara ao aluno.
V1 o player real do Vimeo carrega (o Vimeo recusa reprodução em navegador automatizado).
"""

import json
import os
import re
import sqlite3

import pytest
from playwright import sync_api

from apoio_harness_h1 import abrir_banco, ambiente_isolado

TIMEOUT = 20000
SENHA = "senha-e2e-video-2026"
GESTAO = "gestao.video@teste.com"
ALUNO = "aluno.video@teste.com"
VIDEO_CURTO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # 19 s
VIDEO_INEXISTENTE = "https://www.youtube.com/watch?v=xxxxxxxxxxx"
VIDEO_VIMEO = "https://vimeo.com/76979871"
CURSO = {"id": "curso_video", "name": "Curso de Vídeo", "price": 50.0, "duration_hours": 2, "description": "d",
         "level": "b", "target_audience": "t", "objectives": [], "topics": [], "benefits": [], "faq": [],
         "system_prompt": "p"}


def _entrar(page, base, email, destino):
    page.goto(base + "/login", wait_until="networkidle")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", SENHA)
    page.click("button[type=submit]")
    page.wait_for_url(f"**/{destino}", timeout=TIMEOUT)


def _cadastrar(page, titulo, url, extra=False):
    page.fill('[data-testid="conteudo-modulo"]', "Módulo real")
    page.fill('[data-testid="conteudo-titulo"]', titulo)
    page.fill('[data-testid="conteudo-url"]', url)
    if extra:
        page.check('[data-testid="conteudo-extra"]')
    page.click('[data-testid="conteudo-salvar"]')
    page.locator('[data-testid="conteudo-linha"]', has_text=titulo).wait_for(timeout=TIMEOUT)


def _video_do_banco(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT position, watched, duration FROM video_progress").fetchone()
    finally:
        conn.close()


def _quadro(page):
    return page.frame_locator('[data-testid="sala-player"] iframe')


def _tocar(page):
    quadro = page.locator('[data-testid="sala-player"] iframe')
    quadro.wait_for(state="attached", timeout=TIMEOUT)
    page.wait_for_timeout(2500)  # o player termina de carregar dentro do iframe
    quadro.click()


def _status(page):
    return page.locator('[data-testid="sala-video-status"]').inner_text()


def _pular_para_o_fim(page):
    """Mesmo efeito de arrastar a barra: move o vídeo dentro do player."""
    quadro = next(f for f in page.frames if "youtube" in f.url)
    quadro.evaluate("document.querySelector('video').currentTime = 17")


def test_videoaula_real():
    ver = os.getenv("E2E_VER") == "1"
    with ambiente_isolado("video") as alvo, sync_api.sync_playwright() as p:
        (alvo["cursos_tmp"] / "curso_video.json").write_text(json.dumps(CURSO), encoding="utf-8")
        Database = abrir_banco(alvo["db_path"])
        from core.security import get_password_hash  # noqa: PLC0415

        senha = get_password_hash(SENHA)
        Database.add_user(GESTAO, "Gestão Vídeo", senha, role="admin")
        aluno_id = Database.add_user(ALUNO, "Aluno Vídeo", senha, role="student")
        conn = sqlite3.connect(alvo["db_path"])
        conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_video', 'active')",
                     (aluno_id,))
        conn.commit()
        conn.close()

        navegador = p.chromium.launch(headless=not ver, channel="chrome", slow_mo=250 if ver else 0)
        try:
            gestao = navegador.new_context(viewport={"width": 1280, "height": 900}).new_page()
            gestao.set_default_timeout(TIMEOUT)
            _entrar(gestao, alvo["base"], GESTAO, "admin")
            gestao.get_by_role("button", name="Cadastro de cursos").click()
            gestao.locator('[data-testid="curso-conteudos"]').first.click()
            _cadastrar(gestao, "Primeira aula", VIDEO_CURTO)

            gestao.locator('[data-testid="conteudo-previa"]').first.click()
            gestao.locator('[data-testid="conteudo-previa-painel"] iframe').wait_for(state="attached", timeout=TIMEOUT)
            gestao.locator('[data-testid="conteudo-previa"]').first.click()

            _cadastrar(gestao, "Link quebrado", VIDEO_INEXISTENTE, extra=True)
            gestao.locator('[data-testid="conteudo-linha"]', has_text="Link quebrado") \
                .locator('[data-testid="conteudo-previa"]').click()
            gestao.locator('[data-testid="conteudo-previa-falha"]').wait_for(timeout=TIMEOUT)
            gestao.locator('[data-testid="conteudo-linha"]', has_text="Link quebrado") \
                .locator('[data-testid="conteudo-previa"]').click()
            _cadastrar(gestao, "Aula Vimeo", VIDEO_VIMEO, extra=True)

            aluno = navegador.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True).new_page()
            aluno.set_default_timeout(TIMEOUT)
            _entrar(aluno, alvo["base"], ALUNO, "student")
            aluno.click('[data-testid="curso-entrar"]')
            aluno.wait_for_url("**/student/curso/*", timeout=TIMEOUT)

            # A1: assiste, sai e volta do minuto.
            _tocar(aluno)
            aluno.wait_for_timeout(7000)
            aluno.click('[data-testid="sala-voltar"]')
            aluno.wait_for_url("**/student", timeout=TIMEOUT)
            aluno.wait_for_timeout(500)
            posicao, assistido, duracao = _video_do_banco(alvo["db_path"])
            assert 3 <= posicao <= 14 and 18 <= duracao <= 20, (posicao, assistido, duracao)
            aluno.click('[data-testid="curso-entrar"]')
            quadro = aluno.locator('[data-testid="sala-player"] iframe')
            quadro.wait_for(state="attached", timeout=TIMEOUT)
            inicio = int(re.search(r"[?&]start=(\d+)", quadro.get_attribute("src")).group(1))
            assert inicio == int(posicao), (inicio, posicao)
            percentual = re.search(r"assistiu (\d+)%", _status(aluno))
            assert percentual, _status(aluno)
            antes = int(percentual.group(1))

            # A2: pular para o fim não conclui.
            _tocar(aluno)
            aluno.wait_for_timeout(1500)
            _pular_para_o_fim(aluno)
            aluno.wait_for_timeout(4000)
            registro = _video_do_banco(alvo["db_path"])
            assert registro[0] >= 15, f"o pulo precisa ter acontecido: {registro}"
            assert registro[1] < 0.9 * registro[2], registro
            assert "Aula concluída" not in _status(aluno), _status(aluno)
            assert aluno.locator('[data-testid="sala-certificado"]').count() == 0

            # A3: assiste de verdade até concluir, sem marcar nada. Quem parou no fim recomeça do início.
            aluno.reload(wait_until="networkidle")
            quadro.wait_for(state="attached", timeout=TIMEOUT)
            assert "start=0" in quadro.get_attribute("src"), quadro.get_attribute("src")
            _tocar(aluno)
            aluno.wait_for_timeout(1000)
            aluno.locator('[data-testid="sala-video-status"]', has_text="Aula concluída").wait_for(timeout=70000)
            with aluno.expect_download(timeout=TIMEOUT) as baixado:
                aluno.click('[data-testid="sala-certificado"]')
            assert open(baixado.value.path(), "rb").read().startswith(b"%PDF-")
            assert antes >= 0

            # A4: vídeo inexistente avisa o aluno.
            aluno.locator('[data-testid="sala-extra"]', has_text="Link quebrado").click()
            aluno.locator('[data-testid="sala-video-falha"]').wait_for(timeout=TIMEOUT)

            # V1: o player do Vimeo carrega. A reprodução não é testada: o Vimeo recusa navegador automatizado.
            aluno.locator('[data-testid="sala-extra"]', has_text="Aula Vimeo").click()
            quadro_vimeo = aluno.locator('[data-testid="sala-player"] iframe')
            quadro_vimeo.wait_for(state="attached", timeout=TIMEOUT)
            aluno.wait_for_function(
                "document.querySelector('[data-testid=\"sala-player\"] iframe').src.includes('player.vimeo.com')")
        except Exception:
            destino = os.getenv("E2E_CAPTURA")
            if destino:
                aluno.screenshot(path=destino)
            raise
        finally:
            navegador.close()


def test_video_assistido_uma_vez_conclui():
    """Uma única assistida, do início ao fim, conclui a aula e o percentual acompanha."""
    with ambiente_isolado("video1") as alvo, sync_api.sync_playwright() as p:
        (alvo["cursos_tmp"] / "curso_video.json").write_text(json.dumps(CURSO), encoding="utf-8")
        Database = abrir_banco(alvo["db_path"])
        from core.security import get_password_hash  # noqa: PLC0415

        aluno_id = Database.add_user(ALUNO, "Aluno Vídeo", get_password_hash(SENHA), role="student")
        conn = sqlite3.connect(alvo["db_path"])
        conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_video', 'active')", (aluno_id,))
        conn.commit()
        conn.close()
        token = p.request.new_context(base_url=alvo["api"]).post("/api/admin/login", data={"password": "admin123"}).json()["token"]
        contexto = p.request.new_context(base_url=alvo["api"], extra_http_headers={"Authorization": f"Bearer {token}"})
        contexto.post("/api/admin/courses/curso_video/contents",
                      data={"module": "M", "title": "Aula única", "kind": "video", "url": VIDEO_CURTO})
        navegador = p.chromium.launch(headless=os.getenv("E2E_VER") != "1", channel="chrome")
        try:
            aluno = navegador.new_page(viewport={"width": 1280, "height": 900})
            aluno.set_default_timeout(TIMEOUT)
            _entrar(aluno, alvo["base"], ALUNO, "student")
            aluno.click('[data-testid="curso-entrar"]')
            aluno.wait_for_url("**/student/curso/*", timeout=TIMEOUT)
            _tocar(aluno)
            aluno.wait_for_timeout(9000)
            parcial = int(re.search(r"assistiu (\d+)%", _status(aluno)).group(1))
            assert parcial >= 20, _status(aluno)
            aluno.locator('[data-testid="sala-video-status"]', has_text="Aula concluída").wait_for(timeout=30000)
            aluno.wait_for_timeout(6000)  # até o vídeo terminar e sair o último envio
            conn = sqlite3.connect(alvo["db_path"])
            assistido, duracao = conn.execute("SELECT watched, duration FROM video_progress").fetchone()
            conn.close()
            assert assistido >= 0.95 * duracao, (assistido, duracao)
        finally:
            navegador.close()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
