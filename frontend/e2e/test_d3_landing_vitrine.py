"""E2E da D3 (D93), item 9 — a landing (vitrine) leva o curso escolhido ao login e não fixa o endereço da SPA.

Contrato (D93):
  - `APP_URL` vem de <meta name="gtt-app-url">; vazia, vale http://localhost:4200 quando a landing roda localmente
    (localhost, 127.0.0.1 ou file://) e a própria origem da página em qualquer outro host.
  - "Matricular agora" de um curso leva a `<APP_URL>/login?area=aluno&next=/catalogo?curso=<id>` (next codificado).
  - "Área do aluno" e "Área do funcionário" continuam levando ao login, sem `next`.

Harness: backend da F5b sem Angular (CORS para o servidor estático) e a landing servida pelo helper da E6.
Execução (da raiz do repo): py -3 -m pytest frontend/e2e/test_d3_landing_vitrine.py -s
"""

import sys
import urllib.parse
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import ambiente_f5b, semear_cursos_f5b  # noqa: E402
from test_e6_landing_chat import LANDING, _porta_livre, _servidor_da_landing  # noqa: E402

TIMEOUT = 8000


@pytest.fixture(scope="module")
def servidores():
    porta_web = _porta_livre("E2E_LANDING_PORT")
    base = f"http://127.0.0.1:{porta_web}"
    with ambiente_f5b("d3_landing", cors_origin=base, angular=False) as ambiente:
        dados = semear_cursos_f5b(ambiente["api"], ambiente["db_path"])
        estatico = _servidor_da_landing(porta_web, ambiente["api"])
        try:
            yield dict(ambiente, landing=base + "/landing_global_training.html", dados=dados)
        finally:
            estatico.shutdown()
            estatico.server_close()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador
        finally:
            navegador.close()


def _pagina(browser, url):
    ctx = browser.new_context()
    ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    # A SPA não está de pé: a navegação para o login é interceptada e só a URL de destino é conferida.
    ctx.route("http://localhost:4200/**", lambda r: r.fulfill(status=200, content_type="text/html", body="spa"))
    page = ctx.new_page()
    page.goto(url, wait_until="networkidle")
    return ctx, page


def test_meta_vazia_em_host_local_usa_a_porta_do_ng_serve(browser, servidores):
    ctx, page = _pagina(browser, servidores["landing"])
    try:
        assert page.evaluate("APP_URL") == "http://localhost:4200"
        meta = page.locator('meta[name="gtt-app-url"]')
        assert meta.count() == 1, "a landing não declara <meta name=gtt-app-url>"
    finally:
        ctx.close()


def test_app_url_nao_e_mais_constante_fixa():
    html = LANDING.read_text(encoding="utf-8")
    assert "const APP_URL = 'http://localhost:4200';" not in html


def test_matricular_agora_leva_o_curso_ao_login(browser, servidores):
    ctx, page = _pagina(browser, servidores["landing"])
    try:
        nome = servidores["dados"]["omega"]["nome"] if "omega" in servidores["dados"] else "Omega Analytics"
        card = page.locator(".course-card", has_text=nome).first
        card.wait_for(timeout=TIMEOUT)
        with page.expect_navigation(timeout=TIMEOUT):
            card.locator(".btn-enroll").click()
        destino = urllib.parse.urlparse(page.url)
        assert destino.netloc == "localhost:4200" and destino.path == "/login", page.url
        query = urllib.parse.parse_qs(destino.query)
        assert query.get("area") == ["aluno"]
        assert query.get("next") == ["/catalogo?curso=curso_f5b_omega"], query
    finally:
        ctx.close()


@pytest.mark.parametrize("texto,area", [("Área do aluno", "aluno"), ("Área do funcionário", "funcionario")])
def test_botoes_da_barra_continuam_no_login(browser, servidores, texto, area):
    ctx, page = _pagina(browser, servidores["landing"])
    try:
        with page.expect_navigation(timeout=TIMEOUT):
            page.locator("nav a", has_text=texto).first.click()
        destino = urllib.parse.urlparse(page.url)
        assert destino.path == "/login" and urllib.parse.parse_qs(destino.query) == {"area": [area]}, page.url
    finally:
        ctx.close()
