"""Conteúdos da sala do curso na Gestão (C2/C4, D96). Só o perfil Gestão edita; toda alteração vai para a auditoria."""

from typing import Literal, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

import admin.routes as admin_routes
from admin.course_draft import sanitizar_nome_arquivo
from core import conteudos
from core.audit import record_audit
from core.security import AuthContext, Role, require_roles

router = APIRouter()

ERR_CURSO = "Curso não encontrado."
ERR_CONTEUDO = "Conteúdo não encontrado."
ERR_VIDEO = "Use um link do YouTube ou do Vimeo."
ERR_VIDEO_ESPECIFICO = "Este link não aponta para um vídeo. Abra o vídeo, não a playlist ou o canal, e copie o link dele."
ERR_NAO_E_ARQUIVO = "Este conteúdo não é um arquivo."
ERR_LINK = "O link deve começar com http:// ou https://."
ERR_TAMANHO = "Arquivo maior que 20 MB."
ERR_TIPO = "Formato não suportado. Envie PDF, Word, Excel, PowerPoint ou ZIP."
ERR_TITULO = "Informe o título e o módulo."

_so_gestao = require_roles(Role.ADMIN)


class ConteudoBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    module: str = Field(default="", max_length=120)
    title: str = Field(min_length=1, max_length=200)
    url: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=6000)
    is_extra: bool = False
    published: bool = True

    @field_validator("module", "title", mode="before")
    @classmethod
    def _aparar(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class ConteudoInput(ConteudoBase):
    kind: Literal["video", "link"]


class MoverInput(BaseModel):
    direction: Literal["up", "down"]


def _exigir_curso(course_id: str) -> None:
    if not admin_routes._arquivo_do_curso(admin_routes.COURSES_DIR, course_id):
        raise HTTPException(status_code=404, detail=ERR_CURSO)


def _exigir_conteudo(conteudo_id: int) -> dict:
    conteudo = conteudos.obter(conteudo_id)
    if conteudo is None:
        raise HTTPException(status_code=404, detail=ERR_CONTEUDO)
    return conteudo


def _validar_endereco(kind: str, url: Optional[str]) -> str:
    url = (url or "").strip()
    if kind == "video" and not conteudos.embed_do_video(url):
        raise HTTPException(status_code=422,
                            detail=ERR_VIDEO_ESPECIFICO if conteudos.e_servico_de_video(url) else ERR_VIDEO)
    if kind == "link" and not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail=ERR_LINK)
    return url


def _modulo(module: str, is_extra: bool) -> str:
    """Extra não pertence a um módulo; aula precisa de um."""
    if is_extra:
        return module or conteudos.MODULO_EXTRAS
    if not module:
        raise HTTPException(status_code=422, detail=ERR_TITULO)
    return module


def _ler_arquivo(file: UploadFile) -> Tuple[str, bytes]:
    dados = file.file.read(conteudos.MAX_BYTES_ARQUIVO + 1)
    if len(dados) > conteudos.MAX_BYTES_ARQUIVO:
        raise HTTPException(status_code=413, detail=ERR_TAMANHO)
    extensao = conteudos.extensao_aceita(file.filename, dados)
    if extensao is None:
        raise HTTPException(status_code=415, detail=ERR_TIPO)
    return extensao, dados


def _publico(conteudo: dict) -> dict:
    """Sem o nome interno do arquivo."""
    return {campo: valor for campo, valor in conteudo.items() if campo != "stored_name"}


def _auditar(acao: str, detalhe: str, conteudo: dict, current_user: AuthContext) -> None:
    record_audit(acao, f"{detalhe}: '{conteudo['title']}' ({conteudo['course_id']})", user=current_user,
                 entity_type="course", entity_id=conteudo["course_id"])


@router.get("/courses/{course_id}/contents")
async def listar_conteudos(course_id: str, current_user: AuthContext = Depends(_so_gestao)):
    _exigir_curso(course_id)
    return {"status": "success", "contents": [_publico(c) for c in conteudos.listar(course_id)]}


@router.post("/courses/{course_id}/contents", status_code=201)
async def criar_conteudo(course_id: str, corpo: ConteudoInput, current_user: AuthContext = Depends(_so_gestao)):
    _exigir_curso(course_id)
    dados = corpo.model_dump()
    dados["module"] = _modulo(corpo.module, corpo.is_extra)
    dados["url"] = _validar_endereco(corpo.kind, corpo.url)
    conteudo = conteudos.criar(course_id, dados)
    _auditar("course_content.create", "Conteúdo criado", conteudo, current_user)
    return {"status": "success", "content": _publico(conteudo)}


@router.post("/courses/{course_id}/contents/file", status_code=201)
def enviar_arquivo(
    course_id: str,
    file: UploadFile = File(...),
    module: str = Form(""),
    title: str = Form(...),
    is_extra: bool = Form(False),
    published: bool = Form(True),
    current_user: AuthContext = Depends(_so_gestao),
):
    _exigir_curso(course_id)
    module, title = _modulo(module.strip()[:120], is_extra), title.strip()[:200]
    if not title:
        raise HTTPException(status_code=422, detail=ERR_TITULO)
    extensao, dados = _ler_arquivo(file)
    conteudo = conteudos.criar(course_id, {
        "module": module, "title": title, "kind": "file", "is_extra": is_extra, "published": published,
        "file_name": sanitizar_nome_arquivo(file.filename), "stored_name": conteudos.salvar_arquivo(extensao, dados),
    })
    _auditar("course_content.create", "Arquivo enviado", conteudo, current_user)
    return {"status": "success", "content": _publico(conteudo)}


@router.put("/contents/{conteudo_id}")
async def editar_conteudo(conteudo_id: int, corpo: ConteudoBase, current_user: AuthContext = Depends(_so_gestao)):
    conteudo = _exigir_conteudo(conteudo_id)
    dados = corpo.model_dump()
    dados["module"] = _modulo(corpo.module, corpo.is_extra)
    dados["url"] = None if conteudo["kind"] == "file" else _validar_endereco(conteudo["kind"], corpo.url)
    atualizado = conteudos.atualizar(conteudo_id, dados)
    _auditar("course_content.update", "Conteúdo alterado", atualizado, current_user)
    return {"status": "success", "content": _publico(atualizado)}


@router.put("/contents/{conteudo_id}/file")
def trocar_arquivo(conteudo_id: int, file: UploadFile = File(...), current_user: AuthContext = Depends(_so_gestao)):
    """Troca o arquivo sem perder o progresso de quem já concluiu."""
    conteudo = _exigir_conteudo(conteudo_id)
    if conteudo["kind"] != "file":
        raise HTTPException(status_code=422, detail=ERR_NAO_E_ARQUIVO)
    extensao, dados = _ler_arquivo(file)
    atualizado = conteudos.trocar_arquivo(conteudo, sanitizar_nome_arquivo(file.filename),
                                          conteudos.salvar_arquivo(extensao, dados))
    _auditar("course_content.update", "Arquivo trocado", atualizado, current_user)
    return {"status": "success", "content": _publico(atualizado)}


@router.post("/contents/{conteudo_id}/move")
async def mover_conteudo(conteudo_id: int, corpo: MoverInput, current_user: AuthContext = Depends(_so_gestao)):
    conteudo = _exigir_conteudo(conteudo_id)
    conteudos.mover(conteudo, corpo.direction)
    _auditar("course_content.move", "Conteúdo reordenado", conteudo, current_user)
    return {"status": "success", "contents": [_publico(c) for c in conteudos.listar(conteudo["course_id"])]}


@router.delete("/contents/{conteudo_id}")
async def excluir_conteudo(conteudo_id: int, current_user: AuthContext = Depends(_so_gestao)):
    conteudo = _exigir_conteudo(conteudo_id)
    conteudos.remover(conteudo)
    _auditar("course_content.delete", "Conteúdo excluído", conteudo, current_user)
    return {"status": "success"}
