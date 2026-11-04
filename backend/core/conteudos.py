"""Conteúdos da sala do curso (C1-C4, D103): aulas e extras por curso, em módulos.

Vídeo é sempre incorporado do YouTube ou do Vimeo; o player nasce de um id validado aqui, nunca da URL colada.
Arquivo fica em pasta privada, com nome gerado pelo servidor, e só sai pelo endpoint que confere a matrícula.
Os `materials` do JSON do curso continuam como estão e aparecem na sala como o módulo "Materiais".
"""

import html
import io
import os
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pypdf import PdfReader

from db import Database

MODULO_MATERIAIS = "Materiais"
MODULO_EXTRAS = "Extras"
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
    r"https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})"
    r"(?:[?&#/].*)?"
)
_VIMEO = re.compile(r"https://(?:www\.)?vimeo\.com/(\d{6,12})(?:/([0-9a-f]{6,20}))?(?:[?#].*)?")
_VIMEO_PLAYER = re.compile(r"https://player\.vimeo\.com/video/(\d{6,12})(?:\?h=([0-9a-f]{6,20}))?(?:[&#].*)?")
_SERVICO_DE_VIDEO = re.compile(r"https://(?:[\w-]+\.)?(?:youtube\.com|youtu\.be|vimeo\.com)(?:[/?#]|$)")


def _com_https(url: Optional[str]) -> str:
    """Aceita o link colado sem esquema ou com http; o resto da validação vale para https."""
    url = (url or "").strip()
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url if "://" in url else f"https://{url}"


def e_servico_de_video(url: Optional[str]) -> bool:
    return _SERVICO_DE_VIDEO.match(_com_https(url)) is not None


def embed_do_video(url: Optional[str]) -> Optional[str]:
    """Endereço do player para uma URL do YouTube ou do Vimeo; None para qualquer outra."""
    url = _com_https(url)
    youtube = _YOUTUBE.fullmatch(url)
    if youtube:
        return f"https://www.youtube-nocookie.com/embed/{youtube.group(1)}"
    vimeo = _VIMEO.fullmatch(url) or _VIMEO_PLAYER.fullmatch(url)
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
    # D107: texto do arquivo para o assistente. NULL = ainda não lido; vazio = arquivo sem texto (PDF escaneado, ZIP).
    colunas = {linha["name"] for linha in conn.execute("PRAGMA table_info(course_contents)")}
    if "extracted_text" not in colunas:
        conn.execute("ALTER TABLE course_contents ADD COLUMN extracted_text TEXT")
    return conn


def _para_dict(linha: sqlite3.Row) -> Dict:
    item = dict(linha)
    texto = item.pop("extracted_text", None)
    item["text_status"] = None if item["kind"] != "file" else "pending" if texto is None else "ok" if texto else "empty"
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


def trocar_arquivo(conteudo: Dict, file_name: str, stored_name: str) -> Dict:
    """Troca o arquivo mantendo o id: o progresso de quem já concluiu continua valendo."""
    conn = _conectar()
    try:
        conn.execute("UPDATE course_contents SET file_name = ?, stored_name = ?, extracted_text = NULL WHERE id = ?",
                     (file_name, stored_name, conteudo["id"]))
        conn.commit()
    finally:
        conn.close()
    _apagar_arquivo(conteudo.get("stored_name"))
    return obter(conteudo["id"])


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


# --- Texto dos arquivos para o assistente (D107) -----------------------------------------------------------------------

SEPARADOR_DE_PAGINA = "\f"
MAX_CARACTERES = 400_000
MAX_BYTES_XML = 50 * 1024 * 1024  # teto por parte do Office, contra arquivo compactado malicioso


def _paginas_do_pdf(dados: bytes) -> List[str]:
    return [pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(dados)).pages]


def _xml_para_texto(xml: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"</(?:w:p|a:p|si)>", "\n", xml)))


def _partes_do_office(dados: bytes, extensao: str) -> List[str]:
    padrao = {".docx": r"word/document\.xml", ".pptx": r"ppt/slides/slide(\d+)\.xml",
              ".xlsx": r"xl/sharedStrings\.xml"}[extensao]
    with zipfile.ZipFile(io.BytesIO(dados)) as arquivo:
        partes = [i for i in arquivo.infolist() if re.fullmatch(padrao, i.filename) and i.file_size <= MAX_BYTES_XML]
        partes.sort(key=lambda i: [int(n) for n in re.findall(r"\d+", i.filename)])
        return [_xml_para_texto(arquivo.read(i).decode("utf-8", "replace")) for i in partes]


def _extrair(caminho: Path) -> str:
    """Texto do arquivo, com as páginas separadas. Arquivo ilegível ou sem texto devolve vazio."""
    extensao = caminho.suffix.lower()
    try:
        dados = caminho.read_bytes()
        paginas = _paginas_do_pdf(dados) if extensao == ".pdf" else _partes_do_office(dados, extensao) \
            if extensao in (".docx", ".pptx", ".xlsx") else []
    except Exception as erro:  # arquivo corrompido não pode impedir o cadastro nem derrubar o chat
        print(f"[AVISO] Conteúdo sem texto legível: {type(erro).__name__}")
        return ""
    texto = SEPARADOR_DE_PAGINA.join(" ".join(p.split(" ")).strip() for p in paginas)
    return texto[:MAX_CARACTERES] if texto.replace(SEPARADOR_DE_PAGINA, "").strip() else ""


def preparar_texto(conteudo: Dict) -> Dict:
    """Lê o texto do arquivo e guarda para o assistente. Chamado no envio e, para arquivos antigos, ao montar o índice."""
    caminho = caminho_do_arquivo(conteudo)
    conn = _conectar()
    try:
        conn.execute("UPDATE course_contents SET extracted_text = ? WHERE id = ?",
                     (_extrair(caminho) if caminho else "", conteudo["id"]))
        conn.commit()
    finally:
        conn.close()
    return obter(conteudo["id"])


def assinatura_para_o_assistente() -> Tuple:
    """Muda quando um arquivo publicado entra, sai, é trocado ou é renomeado: o índice do RAG se reconstrói."""
    conn = _conectar()
    try:
        return tuple(tuple(linha) for linha in conn.execute(
            """SELECT id, course_id, title, stored_name FROM course_contents
               WHERE kind = 'file' AND published = 1 ORDER BY id"""))
    finally:
        conn.close()


def documentos_para_o_assistente() -> List[Dict]:
    """Arquivos publicados com texto: {id, course_id, title, pages}. Quem pode ler cada um é decidido no RAG."""
    conn = _conectar()
    try:
        linhas = [dict(l) for l in conn.execute(
            """SELECT id, course_id, title, stored_name, extracted_text FROM course_contents
               WHERE kind = 'file' AND published = 1 ORDER BY id""")]
    finally:
        conn.close()
    documentos = []
    for linha in linhas:
        texto = linha["extracted_text"]
        if texto is None:  # arquivo enviado antes desta leitura existir
            caminho = caminho_do_arquivo(linha)
            texto = _extrair(caminho) if caminho else ""
            preparar_texto(linha)
        if texto:
            documentos.append({"id": linha["id"], "course_id": linha["course_id"], "title": linha["title"],
                               "pages": texto.split(SEPARADOR_DE_PAGINA)})
    return documentos


def _apagar_arquivo(nome: Optional[str]) -> None:
    if nome:
        (pasta_de_arquivos() / nome).unlink(missing_ok=True)
