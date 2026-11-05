"""Gera fundo.jpg (fundo do certificado) a partir de modelo_canva.png, o layout feito no Canva.

O modelo traz o nome do aluno e as duas frases com marcadores ({NOMEALUNO}, {CURSO}, ...). Este script apaga só
essas linhas, refazendo o fundo cinza claro por baixo; título, moldura, assinatura e "Clayton Malta / Diretor de
ensino" ficam como no Canva. O texto variável é escrito por cima, no PDF, por core/certificado_pdf.py.

Só precisa rodar de novo se o modelo mudar (depende do Pillow, que não é dependência do servidor):
    cd backend && venv/Scripts/python.exe assets/certificado/preparar_fundo.py
"""

from pathlib import Path

from PIL import Image, ImageFilter

PASTA = Path(__file__).parent
# Faixas (x0, y0, x1, y1), em pixels do modelo de 2000x1414, com o texto a apagar.
FAIXAS_DO_TEXTO = [
    (395, 505, 1605, 650),   # {NOMEALUNO}
    (315, 680, 1685, 805),   # CONCLUIU COM ÊXITO ... / EMITIDO EM ...
]


def _apagar_texto(img: Image.Image, faixa) -> None:
    margem = 30
    x0, y0, x1, y1 = faixa
    area = img.crop((x0 - margem, y0 - margem, x1 + margem, y1 + margem))
    # Fundo estimado: o filtro de máximo some com os traços escuros do texto; o desfoque tira o "degrau".
    fundo = area.filter(ImageFilter.MaxFilter(25)).filter(ImageFilter.GaussianBlur(10))
    # Máscara: pixels mais escuros que o fundo (o texto), um pouco alargada para levar o antisserrilhado junto.
    cinza = area.convert("L")
    mascara = cinza.point(lambda v: 255 if v < 225 else 0).filter(ImageFilter.MaxFilter(9))
    mascara = mascara.filter(ImageFilter.GaussianBlur(2))
    area.paste(fundo, (0, 0), mascara)
    # Só a faixa volta para a imagem; a margem serviu de contexto para o filtro.
    img.paste(area.crop((margem, margem, margem + x1 - x0, margem + y1 - y0)), (x0, y0))


def main() -> None:
    img = Image.open(PASTA / "modelo_canva.png").convert("RGB")
    for faixa in FAIXAS_DO_TEXTO:
        _apagar_texto(img, faixa)
    img.save(PASTA / "fundo.jpg", quality=90, optimize=True)


if __name__ == "__main__":
    main()
