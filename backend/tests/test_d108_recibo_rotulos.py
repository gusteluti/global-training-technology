"""D108 (pedido do PM, J-ALU-01 passo 5) — recibo em PDF com os rótulos da tela.

Escritos ANTES da implementação. Hoje o PDF imprime o status e a forma de pagamento como gravados no banco
(`approved`, `mercado_pago`); a Área do aluno (D67) mostra "Aprovado" e "Mercado Pago". O PM pediu o mesmo
rótulo da tela no PDF.

Contrato:
  - GET /api/student/payments/{id}/receipt.pdf: a linha "Status: <rótulo>" usa o rótulo de pagamento da Área do
    aluno (frontend/src/app/components/student-dashboard: ROTULOS_PAGAMENTO, D67) e a linha
    "Forma de pagamento: <rótulo>" usa FORMAS_PAGAMENTO (mercado_pago -> "Mercado Pago"; manual -> "Matrícula
    manual", D81). Só `approved` e `refunded` geram PDF (B2), então os status testados são esses dois.
  - Nenhum código cru (`approved`, `refunded`, `mercado_pago`) no texto do PDF.
  - O recibo JSON continua com os valores brutos (o JSON é bruto e a tela traduz, padrão da E4/B2): guarda.

Leitura do PDF: o mesmo extrator sem biblioteca dos testes da B2 (`_texto_do_pdf`, `_validar_estrutura`).
Fixtures e helpers: os da B2 (banco temporário, cursos em diretório temporário, login real por /api/token).

Testes:
  R1  approved + mercado_pago: "Status: Aprovado" e "Forma de pagamento: Mercado Pago", sem código cru
  R2  refunded: "Status: Reembolsado" (a linha "Pagamento reembolsado." continua), sem `refunded`
  R3  manual continua "Matrícula manual" (D81) e o status sai em português também nesse caso
  R4  guarda: o recibo JSON segue com `status` e `payment_method` brutos; o PDF continua estruturalmente válido
"""

import re

import pytest

from test_b2_recibo_pdf import (  # noqa: F401  (fixtures da B2 reaproveitadas)
    CURSO_ACENTO,
    _aluno_logado,
    _executar,
    _pagamento,
    _pdf_ok,
    _recibo_json,
    _texto_do_pdf,
    _validar_estrutura,
    client,
    cursos,
)

# Rótulos da Área do aluno (student-dashboard.component.ts, D67/D81).
ROTULO_STATUS = {"approved": "Aprovado", "refunded": "Reembolsado"}
ROTULO_FORMA = {"mercado_pago": "Mercado Pago", "manual": "Matrícula manual"}


def _linha(texto, prefixo):
    """Linha do PDF que começa com `prefixo` (uma string por Tj)."""
    achadas = [linha for linha in texto.splitlines() if linha.startswith(prefixo)]
    assert len(achadas) == 1, f"esperava uma linha {prefixo!r} no PDF; texto:\n{texto}"
    return achadas[0]


def _texto(client, token, pid):
    corpo = _pdf_ok(client, token, pid).content
    _validar_estrutura(corpo)
    return _texto_do_pdf(corpo)


def test_r1_aprovado_mercado_pago_com_os_rotulos_da_tela(client):
    uid, token = _aluno_logado(client, "r1@d108.test", "Aluna Recibo")
    pid = _pagamento(uid, CURSO_ACENTO, 349.90, "approved", "mp-d108-r1")
    texto = _texto(client, token, pid)
    assert _linha(texto, "Status:") == "Status: Aprovado", texto
    assert _linha(texto, "Forma de pagamento:") == "Forma de pagamento: Mercado Pago", texto
    for cru in ("approved", "mercado_pago"):
        assert cru not in texto, f"código cru {cru!r} no PDF:\n{texto}"


def test_r2_reembolsado_com_o_rotulo_da_tela(client):
    uid, token = _aluno_logado(client, "r2@d108.test", "Aluno Reembolso")
    pid = _pagamento(uid, CURSO_ACENTO, 120.00, "refunded", "mp-d108-r2")
    texto = _texto(client, token, pid)
    assert _linha(texto, "Status:") == "Status: Reembolsado", texto
    assert _linha(texto, "Forma de pagamento:") == "Forma de pagamento: Mercado Pago", texto
    assert "Pagamento reembolsado." in texto
    for cru in ("refunded", "mercado_pago"):
        assert cru not in texto, f"código cru {cru!r} no PDF:\n{texto}"


def test_r3_matricula_manual_continua_com_rotulo_e_status_em_portugues(client):
    uid, token = _aluno_logado(client, "r3@d108.test", "Aluno Bolsista")
    pid = _pagamento(uid, CURSO_ACENTO, 0.0, "approved", None)
    _executar("UPDATE payments SET payment_method = 'manual' WHERE id = ?", (pid,))
    texto = _texto(client, token, pid)
    assert _linha(texto, "Forma de pagamento:") == "Forma de pagamento: Matrícula manual", texto
    assert _linha(texto, "Status:") == "Status: Aprovado", texto
    assert not re.search(r"\b(approved|manual)\b", texto.replace("Matrícula manual", "")), texto


@pytest.mark.parametrize("status", ["approved", "refunded"])
def test_r4_guarda_recibo_json_continua_bruto(client, status):
    uid, token = _aluno_logado(client, f"r4-{status}@d108.test", "Aluno Json")
    pid = _pagamento(uid, CURSO_ACENTO, 80.00, status, f"mp-d108-r4-{status}")
    recibo = _recibo_json(client, token, pid)
    assert recibo["status"] == status
    assert recibo["payment_method"] == "mercado_pago"
    assert ROTULO_STATUS[status] in _texto(client, token, pid)
