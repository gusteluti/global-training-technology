"""Gerador mínimo de recibo em PDF, em Python puro (D63/D64), sem biblioteca de terceiros.

Formato: PDF 1.4, Helvetica com WinAnsiEncoding (cp1252; o que não cabe vira '?'), sem compressão,
/Length direto, tabela xref com entradas de exatamente 20 bytes e offsets exatos.
"""

from typing import Dict, List, Optional, Tuple

MAX_LINHA = 90  # limite de caracteres por linha para não estourar a largura da página


def formatar_valor(valor) -> str:
    """R$ 1234,50: vírgula decimal, duas casas, sem separador de milhar."""
    return "R$ " + f"{float(valor or 0):.2f}".replace(".", ",")


def _para_bytes(texto) -> bytes:
    """Texto em cp1252 com (, ) e \\ escapados; caracteres de controle viram espaço; fora do cp1252 viram '?'."""
    limpo = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in str(texto))[:MAX_LINHA]
    bruto = limpo.encode("cp1252", errors="replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _linhas_do_recibo(recibo: Dict, nome_aluno: str) -> List[Tuple[str, str]]:
    """Lista de (fonte, texto). Cada texto vira exatamente um Tj."""
    linhas: List[Tuple[str, str]] = [
        ("F2", "RECIBO DE PAGAMENTO"),
        ("F1", "Global Training Technology"),
        ("F1", ""),
        ("F1", f"Recibo n. {recibo['payment_id']}"),
        ("F1", f"Aluno: {nome_aluno}"),
        ("F1", f"Curso: {recibo['course_name']}"),
        ("F1", f"Valor: {formatar_valor(recibo['amount'])}"),
        ("F1", f"Status: {recibo['status']}"),
        ("F1", f"Forma de pagamento: {recibo['payment_method']}"),
    ]
    if recibo.get("transaction_id"):
        linhas.append(("F1", f"Transação: {recibo['transaction_id']}"))
    linhas.append(("F1", f"Data de emissão: {recibo['issued_at']}"))
    if recibo["status"] == "refunded":
        linhas.append(("F1", ""))
        linhas.append(("F1", "Pagamento reembolsado."))
    return linhas


def _conteudo(linhas: List[Tuple[str, str]]) -> bytes:
    partes: List[bytes] = []
    y = 780
    for fonte, texto in linhas:
        tamanho = 18 if fonte == "F2" else 12
        if texto:
            partes.append(
                b"BT /" + fonte.encode() + b" " + str(tamanho).encode() + b" Tf 56 "
                + str(y).encode() + b" Td (" + _para_bytes(texto) + b") Tj ET"
            )
        y -= 32 if fonte == "F2" else 22
    return b"\n".join(partes) + b"\n"


def gerar_recibo_pdf(recibo: Dict, nome_aluno: Optional[str]) -> bytes:
    """Monta o PDF do recibo (dict no formato do recibo JSON) e devolve os bytes."""
    conteudo = _conteudo(_linhas_do_recibo(recibo, nome_aluno or ""))
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]

    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for numero, corpo in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += str(numero).encode() + b" 0 obj\n" + corpo + b"\nendobj\n"

    inicio_xref = len(saida)
    total = len(objetos) + 1
    saida += b"xref\n0 " + str(total).encode() + b"\n"
    saida += b"0000000000 65535 f \n"
    for offset in offsets:
        saida += f"{offset:010d} 00000 n \n".encode()
    saida += (
        b"trailer\n<< /Size " + str(total).encode() + b" /Root 1 0 R >>\nstartxref\n"
        + str(inicio_xref).encode() + b"\n%%EOF\n"
    )
    return bytes(saida)
