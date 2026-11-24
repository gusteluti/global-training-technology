"""Apoio dos e2e da área do aluno depois da R3-4 (D126): o assistente virtual deixou de ser uma seção sempre visível abaixo do
painel e virou um botão flutuante (`[data-testid=assistente-botao]`, `#assistente-btn`) que abre o painel de chat
(`[data-testid=chat-panel]`, `#assistente-painel`). Não é código de produção.

- `abrir_assistente(page)`: deixa o painel do chat aberto e visível. Exige que o botão exista (um só) e é idempotente: só clica
  nele quando o painel NÃO existe no DOM (o painel é `*ngIf`: existe só enquanto aberto). Todo teste do ALUNO que usa `chat-input`, `chat-send`,
  `chat-message`, `chat-acao-*`, `chat-fonte`, `chat-aviso-*` ou `chat-feedback-*` chama esta função antes (e de novo depois de um
  `goto`/`reload`, porque o componente nasce com o painel fechado). Se o botão não existe, falha com uma mensagem que diz isso
  (em vez de um timeout de clique).
- `fechar_assistente(page)`: o inverso (clica no botão só se o painel existe).
- `PAINEL`, `BOTAO`: seletores.

Não vale para o chat da landing (`#chat-btn`, `#chat-bubble`), que não mudou, nem para o chat da sala do curso (`chat-sala`).
Ajuste mecânico de teste antigo (autoridade 4.3): D125 -> D126 (pedido do PM de 23/11/2026).
"""

PAINEL = '[data-testid="chat-panel"]'
BOTAO = '[data-testid="assistente-botao"]'
TIMEOUT_PADRAO = 8000


class AssistenteIndisponivel(AssertionError):
    """O botão flutuante do assistente não existe (ou o painel não abriu) na tela."""


def abrir_assistente(page, timeout=TIMEOUT_PADRAO):
    # O botão tem de existir SEMPRE (inclusive com o painel já aberto): é o contrato da R3-4. Sem isso, estes testes passariam
    # também com o chat antigo, sempre visível abaixo do painel das abas, e não provariam que o chat se alcança pelo botão.
    try:
        page.locator(BOTAO).first.wait_for(state="attached", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass
    if page.locator(BOTAO).count() != 1:
        raise AssistenteIndisponivel(
            f"[data-testid=assistente-botao] aparece {page.locator(BOTAO).count()} vez(es) em {page.url} (esperado 1): o "
            "botão flutuante do assistente não existe, então o painel do chat não abre")
    if page.locator(PAINEL).count():
        page.locator(PAINEL).first.wait_for(state="visible", timeout=timeout)
        return
    page.locator(BOTAO).click(timeout=timeout)
    try:
        page.locator(PAINEL).first.wait_for(state="visible", timeout=timeout)
    except Exception as erro:  # noqa: BLE001
        raise AssistenteIndisponivel(
            f"o clique em [data-testid=assistente-botao] não abriu [data-testid=chat-panel] em {page.url}: "
            f"{str(erro).splitlines()[0]}") from erro


def fechar_assistente(page, timeout=TIMEOUT_PADRAO):
    if not page.locator(PAINEL).count():
        return
    if page.locator(BOTAO).count() != 1:
        raise AssistenteIndisponivel(f"[data-testid=assistente-botao] aparece {page.locator(BOTAO).count()} vez(es) em {page.url}")
    page.locator(BOTAO).click(timeout=timeout)
    page.locator(PAINEL).wait_for(state="detached", timeout=timeout)
