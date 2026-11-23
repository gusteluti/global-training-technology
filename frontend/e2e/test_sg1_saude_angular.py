"""E2E da SG1 (D109, P2) - cartao "Saude do sistema" da aba Observabilidade de IA so para a Gestao. Harness D58.

Contrato de tela (decidido pelo PM, P2): o detalhe de saude vem de `GET /api/dashboard/saude` (so Gestao; Suporte e
Financeiro recebem 403). O `/api/health` publico so devolve `{"status": ...}`.

  1  Gestao abre a aba e ve o cartao `saude-sistema` com "No ar" e os servicos (Banco de dados...); a tela le
     `GET /api/dashboard/saude` (200) e nao depende de `/api/health`.
  2  Suporte e Financeiro, na mesma aba, NAO veem o cartao `saude-sistema`; a tela nao faz nenhuma chamada a
     `/api/dashboard/saude` nem a `/api/health`, e nao ha erro 403 no console nem resposta 403.
  3  [guarda] o resto da aba continua para esses perfis: cartao Guardrails e KPIs; custo para o Financeiro e nunca
     para o Suporte (D42).

Um unico ambiente isolado para os tres perfis (cada perfil em um contexto de navegador novo). Nada toca db.sqlite.
"""

import pytest
from playwright import sync_api

from apoio_harness_h1 import ambiente_isolado
from servidor_e2e_h1 import (
    FINANCEIRO_EMAIL, FINANCEIRO_SENHA, GESTAO_EMAIL, GESTAO_SENHA, SUPORTE_EMAIL, SUPORTE_SENHA,
)

TIMEOUT = 15000
ABA = "Observabilidade de IA"
ROTA_SAUDE = "/api/dashboard/saude"
ROTA_HEALTH = "/api/health"


@pytest.fixture(scope="module")
def alvo():
    with ambiente_isolado("sg1saude") as a:
        yield a


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        br = p.chromium.launch()
        yield br
        br.close()


def _abrir_aba(navegador, alvo, email, senha):
    """Login, abre a aba e espera o cartao Guardrails. Devolve (pagina, requisicoes, respostas, erros_de_console).

    As requisicoes sao observadas desde o login, entao qualquer chamada da tela a saude/health e capturada."""
    pagina = navegador.new_context(viewport={"width": 1280, "height": 900}).new_page()
    pagina.set_default_timeout(TIMEOUT)
    requisicoes, respostas, erros = [], [], []
    pagina.on("request", lambda r: requisicoes.append(r.url))
    pagina.on("response", lambda r: respostas.append((r.status, r.url)))
    pagina.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.goto(alvo["base"] + "/login", wait_until="networkidle")
    pagina.fill("input[name=email]", email)
    pagina.fill("input[name=password]", senha)
    pagina.click("button[type=submit]")
    pagina.wait_for_url("**/admin", timeout=TIMEOUT)
    pagina.locator("button.nav-link", has_text=ABA).click(timeout=TIMEOUT)
    pagina.locator('[data-testid="obs-guard-total"]').wait_for(timeout=TIMEOUT)
    pagina.wait_for_load_state("networkidle")
    return pagina, requisicoes, respostas, erros


def _chamou(requisicoes, rota):
    return [u for u in requisicoes if rota in u]


def test_sg1_1_gestao_ve_o_cartao_de_saude_lido_de_dashboard_saude(navegador, alvo):
    pagina, requisicoes, respostas, erros = _abrir_aba(navegador, alvo, GESTAO_EMAIL, GESTAO_SENHA)
    cartao = pagina.locator('[data-testid="saude-sistema"]')
    cartao.wait_for(timeout=TIMEOUT)
    texto = cartao.inner_text()
    assert "No ar" in texto, texto
    assert "Banco de dados" in texto, f"o cartao deve listar os servicos: {texto!r}"
    assert "IA (Groq)" in texto and "Pagamentos" in texto, texto
    assert "TEST-" not in pagina.inner_text("body"), "nenhum segredo na tela"
    assert _chamou(requisicoes, ROTA_SAUDE), f"a tela da Gestao deve ler {ROTA_SAUDE}; requisicoes: {requisicoes}"
    assert any(s == 200 and ROTA_SAUDE in u for s, u in respostas), respostas
    assert not _chamou(requisicoes, ROTA_HEALTH), "o cartao nao pode depender do /api/health publico (so tem status)"
    assert not [e for e in erros if "403" in e or "401" in e], erros


@pytest.mark.parametrize("rotulo,email,senha", [
    ("suporte", SUPORTE_EMAIL, SUPORTE_SENHA),
    ("financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA),
])
def test_sg1_2_suporte_e_financeiro_nao_veem_o_cartao_nem_chamam_saude(navegador, alvo, rotulo, email, senha):
    pagina, requisicoes, respostas, erros = _abrir_aba(navegador, alvo, email, senha)
    assert pagina.locator('[data-testid="saude-sistema"]').count() == 0, \
        f"{rotulo}: o cartao de saude e so da Gestao"
    assert "Saúde do sistema" not in pagina.inner_text("body")
    assert not _chamou(requisicoes, ROTA_SAUDE), f"{rotulo}: a tela nao pode chamar {ROTA_SAUDE}: {requisicoes}"
    assert not _chamou(requisicoes, ROTA_HEALTH), f"{rotulo}: a tela nao pode chamar {ROTA_HEALTH}: {requisicoes}"
    assert not [(s, u) for s, u in respostas if s == 403], f"{rotulo}: resposta 403 na tela: {respostas}"
    assert not [e for e in erros if "403" in e], f"{rotulo}: erro 403 no console: {erros}"


@pytest.mark.parametrize("rotulo,email,senha,ve_custo", [
    ("suporte", SUPORTE_EMAIL, SUPORTE_SENHA, False),
    ("financeiro", FINANCEIRO_EMAIL, FINANCEIRO_SENHA, True),
])
def test_sg1_3_guarda_o_resto_da_aba_continua_para_suporte_e_financeiro(navegador, alvo, rotulo, email, senha, ve_custo):
    pagina, _, _, _ = _abrir_aba(navegador, alvo, email, senha)
    for testid in ("obs-guardrails", "obs-guard-total", "obs-requests", "obs-tokens", "obs-resolution-rate"):
        assert pagina.locator(f'[data-testid="{testid}"]').count() == 1, f"{rotulo}: falta {testid}"
    assert pagina.locator('[data-testid="obs-cost"]').count() == (1 if ve_custo else 0), \
        f"{rotulo}: custo {'deve' if ve_custo else 'nunca pode'} aparecer (D42)"


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
