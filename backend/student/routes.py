"""Área do aluno (E3, D28): painel de inscrições e materiais didáticos.

Regras:
- Só perfil 'student'. Funcionário recebe 403; sem token ou token inválido, 401.
- O alvo é sempre o dono do token. user_id vindo do cliente (query ou corpo) é ignorado.
- Matrícula de outro aluno responde 404 com o mesmo corpo de uma matrícula inexistente (IDOR).
- Materiais só entram na resposta quando a matrícula está 'active'.
"""

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

import admin.routes as admin_routes
from core.security import AuthContext, Role, require_roles
from db import Database

router = APIRouter()

STATUS_COM_MATERIAIS = "active"
ERRO_MATRICULA_NAO_ENCONTRADA = "Matrícula não encontrada."


def _carregar_curso(course_id: str) -> Optional[Dict]:
    """Dados do curso (JSON em COURSES_DIR), ou None se o arquivo não existir."""
    diretorio = admin_routes.COURSES_DIR
    if not diretorio.exists():
        return None

    arquivo = diretorio / f"{course_id}.json"
    if arquivo.exists():
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)

    for candidato in diretorio.glob("*.json"):
        try:
            with open(candidato, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            continue
        if dados.get("id") == course_id:
            return dados
    return None


def _materiais(curso: Optional[Dict]) -> List[Dict[str, str]]:
    if not curso:
        return []
    return [
        {"title": m.get("title"), "url": m.get("url"), "type": m.get("type")}
        for m in (curso.get("materials") or [])
    ]


def _montar_item(matricula: Dict) -> Dict:
    curso = _carregar_curso(matricula["course_id"])
    item = {
        "id": matricula["id"],
        "course_id": matricula["course_id"],
        "course_name": (curso or {}).get("name") or matricula["course_id"],
        "status": matricula["status"],
        "enrolled_at": matricula["enrolled_at"],
    }
    # Só a matrícula ativa recebe materiais. Nos demais status o campo nem existe na resposta.
    if matricula["status"] == STATUS_COM_MATERIAIS:
        item["materials"] = _materiais(curso)
    return item


@router.get("/enrollments")
async def listar_minhas_matriculas(current_user: AuthContext = Depends(require_roles(Role.STUDENT))):
    """Matrículas do próprio aluno (o user_id do token define o filtro)."""
    matriculas = Database.list_enrollments_for_user(current_user.id)
    itens = [_montar_item(m) for m in matriculas]
    return {"status": "success", "total": len(itens), "enrollments": itens}


@router.get("/enrollments/{enrollment_id}")
async def obter_minha_matricula(enrollment_id: int, current_user: AuthContext = Depends(require_roles(Role.STUDENT))):
    """Uma matrícula do próprio aluno. Alheia ou inexistente: mesmo 404."""
    matricula = Database.get_enrollment_for_user(enrollment_id, current_user.id)
    if matricula is None:
        raise HTTPException(status_code=404, detail=ERRO_MATRICULA_NAO_ENCONTRADA)
    return {"status": "success", "enrollment": _montar_item(matricula)}
