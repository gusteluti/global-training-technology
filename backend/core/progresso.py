"""Progresso nos materiais e certificado de conclusão (X1, D91).

O material é identificado pela URL (a ordem da lista do curso pode mudar). O certificado sai quando todos os materiais
do curso estão marcados como concluídos numa matrícula ativa. O código de validação é derivado de dados do servidor
(HMAC com a chave do JWT), sem dado pessoal.
"""

import hashlib
import hmac
import os
import sqlite3
import time
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
    # D96: último conteúdo aberto na sala, para retomar de onde o aluno parou.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS room_last_seen (
               enrollment_id INTEGER PRIMARY KEY,
               content_key TEXT NOT NULL
           )"""
    )
    # D98: tempo assistido por vídeo. last_beat (epoch) limita o crédito ao tempo que passou de verdade.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_progress (
               enrollment_id INTEGER NOT NULL,
               content_key TEXT NOT NULL,
               position REAL NOT NULL DEFAULT 0,
               watched REAL NOT NULL DEFAULT 0,
               duration REAL NOT NULL DEFAULT 0,
               last_beat REAL NOT NULL,
               PRIMARY KEY (enrollment_id, content_key)
           )"""
    )
    return conn


FRACAO_PARA_CONCLUIR = 0.9
VELOCIDADE_MAXIMA = 2.0  # a maior velocidade comum dos players
INTERVALO_MAXIMO_CREDITADO = 60.0  # uma pausa longa não vira crédito


def videos(enrollment_id: int) -> Dict[str, Dict]:
    conn = _conectar()
    try:
        linhas = conn.execute("SELECT content_key, position, watched, duration FROM video_progress "
                              "WHERE enrollment_id = ?", (enrollment_id,)).fetchall()
        return {linha["content_key"]: _estado_do_video(linha) for linha in linhas}
    finally:
        conn.close()


def _estado_do_video(linha) -> Dict:
    duracao = linha["duration"]
    fracao = min(linha["watched"] / duracao, 1) if duracao else 0
    return {
        "position": round(linha["position"], 1), "duration": round(duracao, 1), "watched": round(linha["watched"], 1),
        "percent": round(100 * fracao), "complete": bool(duracao) and fracao >= FRACAO_PARA_CONCLUIR,
    }


def registrar_video(enrollment_id: int, chave: str, posicao: float, assistido: float, duracao: float) -> Dict:
    """Soma o tempo assistido, limitado ao tempo real desde o último envio. Conclui a aula ao chegar a 90%."""
    agora = time.time()
    conn = _conectar()
    try:
        anterior = conn.execute("SELECT watched, duration, last_beat FROM video_progress "
                                "WHERE enrollment_id = ? AND content_key = ?", (enrollment_id, chave)).fetchone()
        decorrido = min(agora - anterior["last_beat"], INTERVALO_MAXIMO_CREDITADO) if anterior else 0.0
        credito = min(assistido, max(decorrido, 0.0) * VELOCIDADE_MAXIMA)
        duracao = max(duracao, anterior["duration"] if anterior else 0.0)
        total = min((anterior["watched"] if anterior else 0.0) + credito, duracao)
        posicao = min(posicao, duracao)
        conn.execute(
            """INSERT INTO video_progress (enrollment_id, content_key, position, watched, duration, last_beat)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(enrollment_id, content_key) DO UPDATE SET position = excluded.position,
                   watched = excluded.watched, duration = excluded.duration, last_beat = excluded.last_beat""",
            (enrollment_id, chave, posicao, total, duracao, agora),
        )
        conn.commit()
        estado = _estado_do_video(conn.execute(
            "SELECT position, watched, duration FROM video_progress WHERE enrollment_id = ? AND content_key = ?",
            (enrollment_id, chave)).fetchone())
    finally:
        conn.close()
    if estado["complete"]:
        marcar(enrollment_id, chave, True)
    return estado


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


def marcar_visto(enrollment_id: int, chave: str) -> None:
    conn = _conectar()
    try:
        conn.execute(
            """INSERT INTO room_last_seen (enrollment_id, content_key) VALUES (?, ?)
               ON CONFLICT(enrollment_id) DO UPDATE SET content_key = excluded.content_key""",
            (enrollment_id, chave),
        )
        conn.commit()
    finally:
        conn.close()


def ultimo_visto(enrollment_id: int) -> Optional[str]:
    conn = _conectar()
    try:
        linha = conn.execute("SELECT content_key FROM room_last_seen WHERE enrollment_id = ?",
                             (enrollment_id,)).fetchone()
        return linha["content_key"] if linha else None
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
