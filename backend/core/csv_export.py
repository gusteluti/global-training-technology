"""Exportação CSV no formato do Excel pt-BR (U1/U2, D74).

UTF-8 com BOM, separador `;`, decimal com vírgula, datas `dd/mm/aaaa HH:MM` em São Paulo e status em português.
Célula de texto que começa com `=`, `+`, `-`, `@`, tab ou CR recebe `'` na frente (injeção de fórmula).
"""

import csv
import io
import re
from typing import Any, Iterable, List, Optional

from fastapi import Response

from core.fuso import formatar_utc_em_sao_paulo

BOM = "﻿"
INICIOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")

# Mesmos rótulos usados nas telas (E3/D67).
ROTULOS_MATRICULA = {
    "pending": "Pendente",
    "active": "Ativa",
    "cancelled": "Cancelada",
    "refunded": "Reembolsada",
}

ROTULOS_PAGAMENTO = {
    "approved": "Aprovado",
    "pending": "Pendente",
    "in_process": "Em análise",
    "rejected": "Recusado",
    "cancelled": "Cancelado",
    "refunded": "Reembolsado",
    "charged_back": "Contestado",
}


def neutralizar(valor: Any) -> str:
    """Texto da célula com `'` na frente quando poderia ser lido como fórmula."""
    if valor is None:
        return ""
    texto = str(valor)
    if texto.startswith(INICIOS_PERIGOSOS):
        return "'" + texto
    return texto


def decimal_br(valor: Optional[float]) -> str:
    if valor is None:
        return ""
    return f"{float(valor):.2f}".replace(".", ",")


def data_sp(valor: Optional[str]) -> str:
    return formatar_utc_em_sao_paulo(valor)


def rotulo_matricula(status: Optional[str]) -> str:
    return ROTULOS_MATRICULA.get(status or "", status or "")


def rotulo_pagamento(status: Optional[str]) -> str:
    return ROTULOS_PAGAMENTO.get(status or "", status or "")


def nome_arquivo_seguro(nome: str) -> str:
    """Só letras, números, `_` e `-` no nome do arquivo do Content-Disposition."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", nome) or "relatorio"


def resposta_csv(nome_arquivo: str, cabecalho: List[str], linhas: Iterable[List[Any]]) -> Response:
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    escritor.writerow([neutralizar(c) for c in cabecalho])
    for linha in linhas:
        escritor.writerow([neutralizar(c) for c in linha])
    conteudo = (BOM + buffer.getvalue()).encode("utf-8")
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo_seguro(nome_arquivo)}.csv"'},
    )
