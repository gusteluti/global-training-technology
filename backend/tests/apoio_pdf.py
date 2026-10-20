"""Apoio de teste da F7 (D78): PDFs mínimos fabricados em Python puro. Não é código de produção.

Os testes NÃO importam pypdf (dependência que a implementação acrescenta); estes geradores só escrevem bytes de PDF
1.4 válidos, no mesmo estilo do `core/receipt_pdf.py` (Helvetica com WinAnsiEncoding, sem compressão, xref exata).

- `pdf_com_texto(linhas, por_pagina=40)`: uma linha de texto por operador Tj, em quantas páginas forem precisas.
- `pdf_sem_texto()`: uma página sem nenhum operador de texto (conteúdo vazio).
- `pdf_so_imagem()`: uma página que só desenha uma imagem 2x2 em tons de cinza (nenhum texto).
"""

from typing import List, Sequence


def _escapar(texto: str) -> bytes:
    limpo = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in str(texto))
    bruto = limpo.encode("cp1252", errors="replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _montar(objetos: List[bytes]) -> bytes:
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


def _stream(conteudo: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length " + str(len(conteudo)).encode() + extra + b" >>\nstream\n" + conteudo + b"\nendstream"


def _pdf_de_paginas(conteudos: Sequence[bytes], recursos: bytes, objetos_extras: Sequence[bytes] = ()) -> bytes:
    """Objetos: 1 catálogo, 2 páginas, 3 fonte, 4.. extras, depois (página, conteúdo) por página."""
    n_extras = len(objetos_extras)
    primeiro = 4 + n_extras
    kids = []
    corpo_paginas: List[bytes] = []
    for i, conteudo in enumerate(conteudos):
        num_pagina = primeiro + 2 * i
        num_conteudo = num_pagina + 1
        kids.append(f"{num_pagina} 0 R".encode())
        corpo_paginas.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents "
            + f"{num_conteudo} 0 R".encode() + b" /Resources " + recursos + b" >>"
        )
        corpo_paginas.append(_stream(conteudo))
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count " + str(len(conteudos)).encode() + b" >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        *objetos_extras,
        *corpo_paginas,
    ]
    return _montar(objetos)


def pdf_com_texto(linhas: Sequence[str], por_pagina: int = 40) -> bytes:
    linhas = list(linhas) or [""]
    conteudos = []
    for inicio in range(0, len(linhas), por_pagina):
        partes = []
        y = 800
        for linha in linhas[inicio:inicio + por_pagina]:
            partes.append(b"BT /F1 9 Tf 30 " + str(y).encode() + b" Td (" + _escapar(linha) + b") Tj ET")
            y -= 19
        conteudos.append(b"\n".join(partes))
    return _pdf_de_paginas(conteudos, b"<< /Font << /F1 3 0 R >> >>")


def pdf_sem_texto() -> bytes:
    return _pdf_de_paginas([b""], b"<< >>")


def pdf_so_imagem() -> bytes:
    pixels = bytes([0, 128, 255, 64])
    imagem = _stream(
        pixels,
        b" /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8",
    )
    conteudo = b"q 200 0 0 200 100 500 cm /Im1 Do Q"
    return _pdf_de_paginas([conteudo], b"<< /XObject << /Im1 4 0 R >> >>", [imagem])
