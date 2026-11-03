"""Conteúdos da sala do curso (C1-C4, D96): aulas e extras por curso, em módulos.

Vídeo é sempre incorporado do YouTube ou do Vimeo; o player nasce de um id validado aqui, nunca da URL colada.
Arquivo fica em pasta privada, com nome gerado pelo servidor, e só sai pelo endpoint que confere a matrícula.
Os `materials` do JSON do curso continuam como estão e aparecem na sala como o módulo "Materiais".
"""

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from db import Database

MODULO_MATERIAIS = "Materiais"
MAX_BYTES_ARQUIVO = 20 * 1024 * 1024
PASTA_PADRAO = Path(__file__).parent.parent / "uploads" / "conteudos"

# Extensão -> (media type, início obrigatório do arquivo).
TIPOS_DE_ARQUIVO = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", b"PK"),
    ".zip": ("application/zip", b"PK"),
}

_YOUTUBE = re.compile(
    r"https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})(?:[?&#/].*)?"
)
_VIMEO = re.compile(r"https://(?:www\.)?vimeo\.com/(\d{6,12})(?:/([0-9a-f]{6,20}))?(?:[?#].*)?")


def embed_do_video(url: Optional[str]) -> Optional[str]:
    """Endereço do player para uma URL do YouTube ou do Vimeo; None para qualquer outra."""
    url = (url or "").strip()
    youtube = _YOUTUBE.fullmatch(url)
    if youtube:
        return f"https://www.youtube-nocookie.com/embed/{youtube.group(1)}"
    vimeo = _VIMEO.fullmatch(url)
    if vimeo:
        sufixo = f"?h={vimeo.group(2)}" if vimeo.group(2) else ""
        return f"https://player.vimeo.com/video/{vimeo.group(1)}{sufixo}"
    return None


def chave(conteudo: Dict) -> str:
    """Identificador no progresso (material_progress.url). Material do JSON continua identificado pela URL."""
    return f"conteudo:{conteudo['id']}"


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(Database.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS course_contents (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               course_id TEXT NOT NULL,
               module TEXT NOT NULL,
               title TEXT NOT NULL,
               kind TEXT NOT NULL CHECK (kind IN ('video', 'file', 'link')),
               url TEXT,
               file_name TEXT,
               stored_name TEXT,
               duration_minutes INTEGER,
               is_extra INTEGER NOT NULL DEFAULT 0,
               published INTEGER NOT NULL DEFAULT 1,
               position INTEGER NOT NULL,
               created_at TEXT NOT NULL
           )"""
    )
    return conn


def _para_dict(linha: sqlite3.Row) -> Dict:
    item = dict(linha)
    item["is_extra"] = bool(item["is_extra"])
    item["published"] = bool(item["published"])
    return item


def listar(course_id: str, so_publicados: bool = False) -> List[Dict]:
    filtro = " AND published = 1" if so_publicados else ""
    conn = _conectar()
    try:
        linhas = conn.execute(
            f"SELECT * FROM course_contents WHERE course_id = ?{filtro} ORDER BY position, id", (course_id,)
        ).fetchall()
        return [_para_dict(linha) for linha in linhas]
    finally:
        conn.close()


def obter(conteudo_id: int) -> Optional[Dict]:
    conn = _conectar()
    try:
        linha = conn.execute("SELECT * FROM course_contents WHERE id = ?", (conteudo_id,)).fetchone()
        return _para_dict(linha) if linha else None
    finally:
        conn.close()


def criar(course_id: str, dados: Dict) -> Dict:
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = _conectar()
    try:
        posicao = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM course_contents WHERE course_id = ?", (course_id,)
        ).fetchone()[0]
        cursor = conn.execute(
            """INSERT INTO course_contents (course_id, module, title, kind, url, file_name, stored_name,
                                            duration_minutes, is_extra, published, position, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (course_id, dados["module"], dados["title"], dados["kind"], dados.get("url"), dados.get("file_name"),
             dados.get("stored_name"), dados.get("duration_minutes"), int(bool(dados.get("is_extra"))),
             int(bool(dados.get("published", True))), posicao, agora),
        )
        conn.commit()
        conteudo_id = cursor.lastrowid
    finally:
        conn.close()
    return obter(conteudo_id)


def atualizar(conteudo_id: int, dados: Dict) -> Dict:
    conn = _conectar()
    try:
        conn.execute(
            """UPDATE course_contents SET module = ?, title = ?, url = ?, duration_minutes = ?, is_extra = ?,
                                          published = ? WHERE id = ?""",
            (dados["module"], dados["title"], dados.get("url"), dados.get("duration_minutes"),
             int(bool(dados.get("is_extra"))), int(bool(dados.get("published", True))), conteudo_id),
        )
        conn.commit()
    finally:
        conn.close()
    return obter(conteudo_id)


def mover(conteudo: Dict, direcao: str) -> None:
    """Troca a posição com o conteúdo vizinho do curso. Na ponta da lista, nada muda."""
    operador, ordem = ("<", "DESC") if direcao == "up" else (">", "ASC")
    conn = _conectar()
    try:
        vizinho = conn.execute(
            f"""SELECT id, position FROM course_contents WHERE course_id = ? AND position {operador} ?
                ORDER BY position {ordem} LIMIT 1""",
            (conteudo["course_id"], conteudo["position"]),
        ).fetchone()
        if vizinho:
            conn.execute("UPDATE course_contents SET position = ? WHERE id = ?", (vizinho["position"], conteudo["id"]))
            conn.execute("UPDATE course_contents SET position = ? WHERE id = ?", (conteudo["position"], vizinho["id"]))
            conn.commit()
    finally:
        conn.close()


def remover(conteudo: Dict) -> None:
    conn = _conectar()
    try:
        conn.execute("DELETE FROM course_contents WHERE id = ?", (conteudo["id"],))
        conn.commit()
    finally:
        conn.close()
    _apagar_arquivo(conteudo.get("stored_name"))


def remover_do_curso(course_id: str) -> None:
    for conteudo in listar(course_id):
        remover(conteudo)


# --- Arquivos ---------------------------------------------------------------------------------------------------------


def pasta_de_arquivos() -> Path:
    return Path(os.getenv("CONTENTS_DIR") or PASTA_PADRAO)


def extensao_aceita(nome: Optional[str], conteudo: bytes) -> Optional[str]:
    """Extensão do arquivo se ela for permitida e o início do arquivo corresponder a ela; senão None."""
    extensao = Path(nome or "").suffix.lower()
    tipo = TIPOS_DE_ARQUIVO.get(extensao)
    return extensao if tipo and conteudo.startswith(tipo[1]) else None


def salvar_arquivo(extensao: str, conteudo: bytes) -> str:
    pasta = pasta_de_arquivos()
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"{uuid.uuid4().hex}{extensao}"
    (pasta / nome).write_bytes(conteudo)
    return nome


def caminho_do_arquivo(conteudo: Dict) -> Optional[Path]:
    caminho = pasta_de_arquivos() / (conteudo.get("stored_name") or "")
    return caminho if conteudo.get("stored_name") and caminho.is_file() else None


def media_type(conteudo: Dict) -> str:
    return TIPOS_DE_ARQUIVO[Path(conteudo["stored_name"]).suffix.lower()][0]


def _apagar_arquivo(nome: Optional[str]) -> None:
    if nome:
        (pasta_de_arquivos() / nome).unlink(missing_ok=True)
