"""Apoio dos e2e para a janela de confirmação do próprio app (DS1, D115). Não é código de produção.

A DS1 troca o `confirm()` do navegador por uma janela do app (contrato no pedido da DS1):
  [data-testid="confirmacao"]            a janela (role="alertdialog", aria-modal="true"), um único componente na casca
  [data-testid="confirmacao-voltar"]     "Voltar": fecha sem fazer nada (o `confirm()` devolvia false)
  [data-testid="confirmacao-confirmar"]  rótulo da ação: executa exatamente o que o `confirm()` aceito executava

Ajuste mecânico dos e2e antigos (4.3, D115 -> DS1): onde o teste aceitava o diálogo nativo
(`page.on("dialog", lambda d: d.accept())`), ele passa a clicar no botão da janela com `confirmar_no_app`; onde recusava
(`d.dismiss()`), usa `voltar_no_app`. As duas funções devolvem o texto da janela, para os testes que conferiam o texto
da pergunta (`dialogo.message`) continuarem conferindo.

Funções:
- `esperar_confirmacao(page, timeout=8000)`: espera a janela ficar visível e devolve o Locator; sem janela, levanta
  `JanelaAusente` (subclasse de AssertionError) com o motivo.
- `texto_da_confirmacao(page)`: texto visível da janela, com espaços normalizados (título, pergunta e botões).
- `confirmar_no_app(page, contem=None, timeout=8000, obrigatoria=True)`: espera a janela, confere que o texto contém
  `contem` (quando dado), clica em confirmar, espera a janela fechar e devolve o texto. Com `obrigatoria=False`, devolve
  None em vez de levantar quando a janela não aparece (para os testes de checklist que registram o resultado).
- `voltar_no_app(page, contem=None, timeout=8000, obrigatoria=True)`: o mesmo, clicando em "Voltar".
"""

import re

SEL_JANELA = '[data-testid="confirmacao"]'
SEL_VOLTAR = '[data-testid="confirmacao-voltar"]'
SEL_CONFIRMAR = '[data-testid="confirmacao-confirmar"]'


class JanelaAusente(AssertionError):
    """A janela de confirmação do app não apareceu (ou não fechou, ou não tem o texto esperado)."""


def _normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def esperar_confirmacao(page, timeout=8000):
    janela = page.locator(SEL_JANELA)
    try:
        janela.first.wait_for(state="visible", timeout=timeout)
    except Exception:
        raise JanelaAusente(f"a janela de confirmação do app ({SEL_JANELA}) não apareceu em {timeout} ms") from None
    return janela.first


def texto_da_confirmacao(page):
    return _normalizar(page.locator(SEL_JANELA).first.inner_text())


def _responder(page, seletor_botao, contem, timeout, obrigatoria):
    try:
        janela = esperar_confirmacao(page, timeout)
    except JanelaAusente:
        if obrigatoria:
            raise
        return None
    texto = texto_da_confirmacao(page)
    if contem is not None and _normalizar(contem) not in texto:
        raise JanelaAusente(f"a janela de confirmação não contém {contem!r} (texto: {texto!r})")
    botao = janela.locator(seletor_botao)
    if botao.count() != 1:
        raise JanelaAusente(f"a janela de confirmação tem {botao.count()} {seletor_botao} (esperado 1)")
    botao.first.click(timeout=timeout)
    try:
        page.locator(SEL_JANELA).first.wait_for(state="hidden", timeout=timeout)
    except Exception:
        raise JanelaAusente(f"a janela de confirmação continuou aberta depois de clicar em {seletor_botao}") from None
    return texto


def confirmar_no_app(page, contem=None, timeout=8000, obrigatoria=True):
    """Clica no botão de confirmar da janela do app (equivale a aceitar o `confirm()` antigo)."""
    return _responder(page, SEL_CONFIRMAR, contem, timeout, obrigatoria)


def voltar_no_app(page, contem=None, timeout=8000, obrigatoria=True):
    """Clica em "Voltar" na janela do app (equivale a recusar o `confirm()` antigo)."""
    return _responder(page, SEL_VOLTAR, contem, timeout, obrigatoria)
