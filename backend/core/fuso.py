"""Horário de São Paulo (F2, D71): deslocamento fixo de -3 h em relação ao UTC.

O Brasil não tem horário de verão desde 2019; por isso o deslocamento é fixo e não depende de zoneinfo/tzdata.
O banco e a API JSON continuam em UTC; este módulo só é usado onde o backend gera texto ou agrupa por dia.
"""

from datetime import date, datetime, timedelta
from typing import Optional

DESLOCAMENTO_SP = timedelta(hours=-3)
# Modificador equivalente para funções de data do SQLite (ex.: date(created_at, '-3 hours')).
MODIFICADOR_SQLITE_SP = "-3 hours"


def para_sao_paulo(instante_utc: datetime) -> datetime:
    """Converte um instante UTC (com ou sem tzinfo) para o horário de São Paulo, sem tzinfo."""
    return instante_utc.replace(tzinfo=None) + DESLOCAMENTO_SP


def dia_sao_paulo(instante_utc: datetime) -> date:
    """Dia do calendário de São Paulo correspondente a um instante UTC."""
    return para_sao_paulo(instante_utc).date()


def formatar_utc_em_sao_paulo(texto_utc: Optional[str]) -> str:
    """'AAAA-MM-DD HH:MM:SS' (UTC, como grava o banco) -> 'dd/mm/aaaa HH:MM' em São Paulo.

    Texto vazio vira ''; texto em formato inesperado é devolvido sem conversão.
    """
    if not texto_utc:
        return ""
    texto = str(texto_utc).strip()
    try:
        instante = datetime.fromisoformat(texto.replace("T", " ").replace("Z", ""))
    except ValueError:
        return texto
    return para_sao_paulo(instante).strftime("%d/%m/%Y %H:%M")
