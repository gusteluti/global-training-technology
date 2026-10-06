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
ERRO_PAGAMENTO_NAO_ENCONTRADO = "Pagamento não encontrado."


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


def _montar_pagamento(pagamento: Dict) -> Dict:
    """Representação pública do pagamento do próprio aluno (E4)."""
    curso = _carregar_curso(pagamento["course_id"])
    return {
        "id": pagamento["id"],
        "enrollment_id": pagamento["enrollment_id"],
        "course_id": pagamento["course_id"],
        "course_name": (curso or {}).get("name") or pagamento["course_id"],
        "amount": pagamento["amount"],
        "status": pagamento["status"],
        "payment_method": pagamento["payment_method"],
        "transaction_id": pagamento["transaction_id"],
        "created_at": pagamento["created_at"],
        "updated_at": pagamento["updated_at"],
        "receipt_url": f"/api/student/payments/{pagamento['id']}/receipt",
    }


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


@router.get("/payments")
async def listar_meus_pagamentos(current_user: AuthContext = Depends(require_roles(Role.STUDENT))):
    """Histórico de pagamentos ligados às matrículas do dono do JWT (E4)."""
    pagamentos = [_montar_pagamento(p) for p in Database.list_payments_for_user(current_user.id)]
    return {"status": "success", "total": len(pagamentos), "payments": pagamentos}


@router.get("/payments/{payment_id}/receipt")
async def obter_meu_recibo(payment_id: int, current_user: AuthContext = Depends(require_roles(Role.STUDENT))):
    """Recibo JSON de um pagamento próprio; alheio e inexistente são o mesmo 404."""
    pagamento = Database.get_payment_for_user(payment_id, current_user.id)
    if pagamento is None:
        raise HTTPException(status_code=404, detail=ERRO_PAGAMENTO_NAO_ENCONTRADO)
    item = _montar_pagamento(pagamento)
    recibo = {
        "payment_id": item["id"],
        "enrollment_id": item["enrollment_id"],
        "course_id": item["course_id"],
        "course_name": item["course_name"],
        "amount": item["amount"],
        "status": item["status"],
        "payment_method": item["payment_method"],
        "transaction_id": item["transaction_id"],
        "issued_at": item["updated_at"] or item["created_at"],
    }
    return {"status": "success", "receipt": recibo}
