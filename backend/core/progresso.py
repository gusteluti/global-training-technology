"""Progresso nos materiais e certificado de conclusão (X1, D91).

O material é identificado pela URL (a ordem da lista do curso pode mudar). O certificado sai quando todos os materiais
do curso estão marcados como concluídos numa matrícula ativa. O código de validação é derivado de dados do servidor
(HMAC com a chave do JWT), sem dado pessoal.
"""

import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.fuso import formatar_utc_em_sao_paulo
from core.receipt_pdf import gerar_pdf_de_linhas
from db import Database


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(Database.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS material_progress (
               enrollment_id INTEGER NOT NULL,
               url TEXT NOT NULL,
               completed_at TEXT NOT NULL,
               PRIMARY KEY (enrollment_id, url)
           )"""
    )
    return conn


def concluidos(enrollment_id: int) -> Dict[str, str]:
    conn = _conectar()
    try:
        linhas = conn.execute("SELECT url, completed_at FROM material_progress WHERE enrollment_id = ?",
                              (enrollment_id,)).fetchall()
        return {linha["url"]: linha["completed_at"] for linha in linhas}
    finally:
        conn.close()


def marcar(enrollment_id: int, url: str, feito: bool) -> None:
    conn = _conectar()
    try:
        if feito:
            conn.execute("INSERT OR IGNORE INTO material_progress (enrollment_id, url, completed_at) VALUES (?, ?, ?)",
                         (enrollment_id, url, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
        else:
            conn.execute("DELETE FROM material_progress WHERE enrollment_id = ? AND url = ?", (enrollment_id, url))
        conn.commit()
    finally:
        conn.close()


def resumo(enrollment_id: int, urls_do_curso: List[str]) -> Dict:
    feitos = concluidos(enrollment_id)
    urls = [u for u in urls_do_curso if u]
    completos = [u for u in urls if u in feitos]
    total = len(urls)
    return {
        "done": len(completos),
        "total": total,
        "percent": round(100 * len(completos) / total) if total else 0,
        "completed": completos,
        "certificate_available": total > 0 and len(completos) == total,
        "completed_at": max((feitos[u] for u in completos), default=None) if total and len(completos) == total else None,
    }


def codigo_validacao(enrollment_id: int, user_id: int) -> str:
    chave = (os.getenv("JWT_SECRET_KEY") or "gt").encode()
    return hmac.new(chave, f"certificado:{enrollment_id}:{user_id}".encode(), hashlib.sha256).hexdigest()[:12].upper()


def gerar_certificado_pdf(nome_aluno: str, nome_curso: str, horas: Optional[int], concluido_em: Optional[str],
                          codigo: str) -> bytes:
    data = (formatar_utc_em_sao_paulo(concluido_em) or "")[:10] if concluido_em else ""
    linhas = [
        ("F2", "CERTIFICADO DE CONCLUSÃO"),
        ("F1", "Global Training Technology"),
        ("F1", ""),
        ("F1", "Certificamos que"),
        ("F2", nome_aluno or "Aluno"),
        ("F1", "concluiu o curso"),
        ("F2", nome_curso),
    ]
    if horas:
        linhas.append(("F1", f"com carga horária de {horas} horas."))
    linhas += [
        ("F1", ""),
        ("F1", f"Data de conclusão: {data}"),
        ("F1", f"Código de validação: {codigo}"),
    ]
    return gerar_pdf_de_linhas(linhas)
