"""Certificado de conclusão em PDF sobre o layout feito no Canva (backend/assets/certificado).

O fundo (fundo.jpg) é o modelo do Canva sem as linhas variáveis; aqui elas são escritas por cima, como texto de
verdade (selecionável e legível pelo extrator de PDF), com as fontes mais próximas das do modelo, todas OFL, em
backend/assets/fonts:
- Alex Brush no nome do aluno;
- Martel nas frases; os algarismos vêm da Alike, porque os da Martel descem da linha e destoam da caixa alta.

As posições estão em pixels do modelo (2000 x 1414, A4 deitado) e são convertidas para pontos do PDF.
"""

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from core.fuso import dia_sao_paulo, formatar_utc_em_sao_paulo

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FUNDO = ASSETS / "certificado" / "fundo.jpg"
FONTE_NOME, FONTE_TEXTO, FONTE_DIGITOS = "GTAlexBrush", "GTMartel", "GTAlike"
ARQUIVOS_DAS_FONTES = {
    FONTE_NOME: "AlexBrush-Regular.ttf",
    FONTE_TEXTO: "Martel-Regular.ttf",
    FONTE_DIGITOS: "Alike-Regular.ttf",
}

LARGURA_MODELO = 2000  # px
PAGINA_L, PAGINA_A = landscape(A4)
ESCALA = PAGINA_L / LARGURA_MODELO  # pt por px do modelo

AZUL = Color(0, 45 / 255, 105 / 255)        # #002D69, a cor do texto no modelo
AZUL_SUAVE = Color(0.29, 0.40, 0.56)        # código de validação, discreto

CENTRO_X = 1000
# Nome do aluno: linha de base e tamanho do modelo; encolhe até caber na largura.
NOME_BASE_Y, NOME_TAMANHO, NOME_LARGURA_MAX = 610, 112, 1300
# Frases: mesma fonte, tamanho e espaçamento do modelo; quebram em linhas equilibradas dentro da largura.
FRASE_BASE_Y, FRASE_TAMANHO, FRASE_ENTRELINHA, FRASE_LARGURA_MAX = 723, 35.5, 66, 1400
# Abaixo disto começa a assinatura; se as frases passarem daqui, a fonte diminui.
FRASE_LIMITE_Y = 1010
CODIGO_X, CODIGO_BASE_Y, CODIGO_TAMANHO = 110, 1305, 20

Trecho = Tuple[str, str]  # (fonte, texto)

_fontes_registradas = False


def _registrar_fontes() -> None:
    global _fontes_registradas
    if not _fontes_registradas:
        for nome, arquivo in ARQUIVOS_DAS_FONTES.items():
            pdfmetrics.registerFont(TTFont(nome, str(ASSETS / "fonts" / arquivo)))
        _fontes_registradas = True


def _pt(px: float) -> float:
    return px * ESCALA


def _y(px: float) -> float:
    """Y do modelo (de cima para baixo) para Y do PDF (de baixo para cima)."""
    return PAGINA_A - _pt(px)


def _data(texto_utc: Optional[str]) -> str:
    """'AAAA-MM-DD HH:MM:SS' em UTC -> 'dd/mm/aaaa' em São Paulo."""
    return (formatar_utc_em_sao_paulo(texto_utc) or "")[:10]


# --- Texto com duas fontes (letras na Martel, algarismos na Alike) -------------------------------------------------

def _trechos(texto: str) -> List[Trecho]:
    return [(FONTE_DIGITOS if parte[0].isdigit() else FONTE_TEXTO, parte)
            for parte in re.findall(r"\d+|\D+", texto)]


def _largura(texto: str, tamanho: float) -> float:
    return sum(pdfmetrics.stringWidth(parte, fonte, tamanho) for fonte, parte in _trechos(texto))


def _quebrar(texto: str, tamanho: float, largura_max: float) -> List[str]:
    """Quebra gulosa por palavras."""
    linhas: List[str] = []
    for palavra in texto.split():
        if linhas and _largura(f"{linhas[-1]} {palavra}", tamanho) <= largura_max:
            linhas[-1] += f" {palavra}"
        else:
            linhas.append(palavra)
    return linhas


def _quebrar_equilibrado(texto: str, tamanho: float, largura_max: float) -> List[str]:
    """Mesmo número de linhas da quebra gulosa, mas com a menor largura possível: as linhas ficam parecidas e
    nenhuma sobra com uma palavra só."""
    linhas = _quebrar(texto, tamanho, largura_max)
    if len(linhas) < 2:
        return linhas
    menor, maior = max(_largura(p, tamanho) for p in texto.split()), largura_max
    while maior - menor > 1:
        meio = (menor + maior) / 2
        if len(_quebrar(texto, tamanho, meio)) <= len(linhas):
            maior = meio
        else:
            menor = meio
    return _quebrar(texto, tamanho, maior)


def _escrever_centralizado(c: canvas.Canvas, texto: str, tamanho: float, y: float) -> None:
    _escrever(c, texto, tamanho, _pt(CENTRO_X) - _largura(texto, tamanho) / 2, y)


def _escrever(c: canvas.Canvas, texto: str, tamanho: float, x: float, y: float) -> None:
    t = c.beginText(x, y)
    for fonte, parte in _trechos(texto):
        t.setFont(fonte, tamanho)
        t.textOut(parte)
    c.drawText(t)


def _linhas_das_frases(frases: List[str], tamanho: float) -> List[str]:
    linhas: List[str] = []
    for frase in frases:
        linhas += _quebrar_equilibrado(frase, tamanho, _pt(FRASE_LARGURA_MAX))
    return linhas


# --- Certificado -------------------------------------------------------------------------------------------------

def _carga_horaria(horas) -> str:
    """', COM CARGA HORÁRIA DE 20 HORAS,' (1 HORA no singular); vazio se o curso não tiver carga horária."""
    try:
        horas = int(horas or 0)
    except (TypeError, ValueError):
        return ""
    if horas <= 0:
        return ""
    return f", COM CARGA HORÁRIA DE {horas} {'HORA' if horas == 1 else 'HORAS'},"


def gerar(nome_aluno: str, nome_curso: str, iniciado_em: Optional[str], concluido_em: Optional[str],
          codigo: str, horas: Optional[int] = None, emitido_em: Optional[datetime] = None) -> bytes:
    _registrar_fontes()
    emissao = dia_sao_paulo(emitido_em or datetime.now(timezone.utc)).strftime("%d/%m/%Y")
    curso = " ".join((nome_curso or "").split()).upper()
    frases = [
        f"CONCLUIU COM ÊXITO O CURSO {curso}{_carga_horaria(horas)} "
        f"ENTRE {_data(iniciado_em)} E {_data(concluido_em)}.",
        f"EMITIDO EM {emissao} PELA GLOBAL TRAINING TECHNOLOGY.",
    ]

    saida = io.BytesIO()
    c = canvas.Canvas(saida, pagesize=(PAGINA_L, PAGINA_A))
    c.setTitle(f"Certificado - {nome_curso}")
    c.setAuthor("Global Training Technology")
    c.drawImage(ImageReader(str(FUNDO)), 0, 0, width=PAGINA_L, height=PAGINA_A)
    c.setFillColor(AZUL)

    # Nome do aluno, centralizado, encolhendo até caber.
    nome = " ".join((nome_aluno or "").split()) or "Aluno"
    tamanho = _pt(NOME_TAMANHO)
    largura = pdfmetrics.stringWidth(nome, FONTE_NOME, tamanho)
    if largura > _pt(NOME_LARGURA_MAX):
        tamanho *= _pt(NOME_LARGURA_MAX) / largura
    c.setFont(FONTE_NOME, tamanho)
    c.drawCentredString(_pt(CENTRO_X), _y(NOME_BASE_Y), nome)

    # Frases: se não couberem antes da assinatura, a fonte diminui um pouco por vez.
    tamanho, entrelinha = _pt(FRASE_TAMANHO), _pt(FRASE_ENTRELINHA)
    linhas = _linhas_das_frases(frases, tamanho)
    while _pt(FRASE_BASE_Y) + entrelinha * (len(linhas) - 1) > _pt(FRASE_LIMITE_Y) and tamanho > _pt(22):
        tamanho, entrelinha = tamanho * 0.92, entrelinha * 0.92
        linhas = _linhas_das_frases(frases, tamanho)
    for i, linha in enumerate(linhas):
        _escrever_centralizado(c, linha, tamanho, _y(FRASE_BASE_Y) - i * entrelinha)

    c.setFillColor(AZUL_SUAVE)
    _escrever(c, f"Código de validação: {codigo}", _pt(CODIGO_TAMANHO), _pt(CODIGO_X), _y(CODIGO_BASE_Y))

    c.showPage()
    c.save()
    return saida.getvalue()
