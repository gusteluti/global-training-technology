"""Avaliação do curso pelo aluno (X2, D92): nota de 1 a 5 e comentário opcional, uma por matrícula ativa."""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from db import Database

COMENTARIO_MAX = 500


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(Database.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS course_reviews (
               enrollment_id INTEGER PRIMARY KEY,
               course_id TEXT NOT NULL,
               rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
               comment TEXT,
               updated_at TEXT NOT NULL
           )"""
    )
    return conn


def salvar(enrollment_id: int, course_id: str, nota: int, comentario: Optional[str]) -> Dict:
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = _conectar()
    try:
        conn.execute(
            """INSERT INTO course_reviews (enrollment_id, course_id, rating, comment, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(enrollment_id) DO UPDATE SET rating = excluded.rating, comment = excluded.comment,
                                                         updated_at = excluded.updated_at""",
            (enrollment_id, course_id, nota, comentario, agora),
        )
        conn.commit()
        return {"rating": nota, "comment": comentario, "updated_at": agora}
    finally:
        conn.close()


def da_matricula(enrollment_id: int) -> Optional[Dict]:
    conn = _conectar()
    try:
        linha = conn.execute("SELECT rating, comment, updated_at FROM course_reviews WHERE enrollment_id = ?",
                             (enrollment_id,)).fetchone()
        return dict(linha) if linha else None
    finally:
        conn.close()


def medias_por_curso() -> Dict[str, Dict]:
    conn = _conectar()
    try:
        linhas = conn.execute(
            "SELECT course_id, AVG(rating) AS media, COUNT(*) AS total FROM course_reviews GROUP BY course_id"
        ).fetchall()
        return {l["course_id"]: {"average": round(l["media"], 1), "count": l["total"]} for l in linhas}
    finally:
        conn.close()
