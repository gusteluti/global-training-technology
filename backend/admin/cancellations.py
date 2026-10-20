"""Pedidos de cancelamento em 7 dias (U5, D82): lista e decisão pelo Financeiro e pela Gestão.

Montado em /api/admin (app.py). Router próprio porque a aprovação reaproveita o reembolso da E9 e a trilha
`payment.refund` de payments.routes, que já importa admin.routes.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

import admin.routes as admin_routes
from core.audit import change, record_audit
from core.security import AuthContext, Role, require_roles
from db import Database
from payments.routes import DETAIL_REEMBOLSO_NAO_APROVADO, registrar_trilha_reembolso

router = APIRouter()

ERR_SOLICITACAO_NAO_ENCONTRADA = "Solicitação não encontrada."
ERR_SOLICITACAO_DECIDIDA = "Esta solicitação já foi decidida."
MOTIVO_RECUSA_MIN, MOTIVO_RECUSA_MAX = 5, 300

_decisores = require_roles(Role.ADMIN, Role.FINANCIAL)


class RecusaInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reason: str

    @field_validator("reason")
    @classmethod
    def _motivo_valido(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not MOTIVO_RECUSA_MIN <= len(valor) <= MOTIVO_RECUSA_MAX:
            raise ValueError(f"O motivo deve ter de {MOTIVO_RECUSA_MIN} a {MOTIVO_RECUSA_MAX} caracteres.")
        return valor


def _nome_do_curso(course_id: str) -> str:
    try:
        return admin_routes.load_course_data(course_id).get("name") or course_id
    except HTTPException:
        return course_id


def _erro_de_decisao(outcome: str) -> None:
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail=ERR_SOLICITACAO_NAO_ENCONTRADA)
    if outcome == "already_decided":
        raise HTTPException(status_code=409, detail=ERR_SOLICITACAO_DECIDIDA)
    if outcome == "not_approved":
        raise HTTPException(status_code=409, detail=DETAIL_REEMBOLSO_NAO_APROVADO)


@router.get("/cancellation-requests")
async def listar_pedidos_de_cancelamento(
    status: Literal["open", "approved", "rejected"] = "open",
    current_user: AuthContext = Depends(_decisores),
):
    """Pedidos de um status (padrão `open`), do mais antigo para o mais novo."""
    pedidos = []
    for pedido in Database.listar_pedidos_cancelamento(status):
        pedido["course_name"] = _nome_do_curso(pedido["course_id"])
        pedidos.append(pedido)
    return {"status": "success", "requests": pedidos}


@router.post("/cancellation-requests/{request_id}/approve")
async def aprovar_pedido_de_cancelamento(request_id: int, current_user: AuthContext = Depends(_decisores)):
    """Aprova: reembolso da E9 (mesma regra e trilha `payment.refund`) e pedido `approved`, numa transação."""
    resultado = Database.aprovar_pedido_cancelamento(request_id)
    _erro_de_decisao(resultado["outcome"])
    registrar_trilha_reembolso(resultado["refund"], current_user)
    record_audit(
        "cancellation.approve",
        f"Pedido de cancelamento #{request_id} (matrícula #{resultado['enrollment_id']}) aprovado",
        user=current_user,
        entity_type="cancellation_request",
        entity_id=request_id,
        changes=[change("cancellation.status", "open", "approved")],
    )
    return {"status": "success", "request_id": request_id, "cancellation_status": "approved"}


@router.post("/cancellation-requests/{request_id}/reject")
async def recusar_pedido_de_cancelamento(
    request_id: int,
    corpo: RecusaInput,
    current_user: AuthContext = Depends(_decisores),
):
    """Recusa com motivo (5 a 300 caracteres, aparado). Nada é reembolsado."""
    resultado = Database.recusar_pedido_cancelamento(request_id, corpo.reason)
    _erro_de_decisao(resultado["outcome"])
    record_audit(
        "cancellation.reject",
        f"Pedido de cancelamento #{request_id} (matrícula #{resultado['enrollment_id']}) recusado",
        user=current_user,
        entity_type="cancellation_request",
        entity_id=request_id,
        changes=[change("cancellation.status", "open", "rejected"), change("decision_reason", None, corpo.reason)],
    )
    return {"status": "success", "request_id": request_id, "cancellation_status": "rejected"}
