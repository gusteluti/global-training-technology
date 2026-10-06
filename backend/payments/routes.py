from datetime import datetime
import os
import uuid
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

from admin.routes import load_course_data
from core.audit import change, record_audit
from core.notifications import send_password_setup_link
from core.password_setup import emitir_token_definicao
from core.security import AuthContext, Role, require_roles
from db import Database

load_dotenv()

router = APIRouter()

MERCADO_PAGO_PREFERENCES_URL = "https://api.mercadopago.com/checkout/preferences"
MERCADO_PAGO_PAYMENTS_URL = "https://api.mercadopago.com/v1/payments"


class PayerInput(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class CheckoutInput(BaseModel):
    course_id: str
    payer: PayerInput


def get_access_token() -> str:
    access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
    if not access_token:
        raise HTTPException(
            status_code=500,
            detail="MERCADO_PAGO_ACCESS_TOKEN não configurado no backend.",
        )
    return access_token


def money_to_float(value) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Preço do curso inválido.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Preço do curso precisa ser maior que zero.")
    return round(amount, 2)


def validate_payer(payer: PayerInput):
    if len(payer.name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Informe o nome completo.")
    if "@" not in payer.email or "." not in payer.email:
        raise HTTPException(status_code=400, detail="Informe um e-mail válido.")


@router.post("/create-checkout")
async def create_checkout(payload: CheckoutInput, request: Request):
    validate_payer(payload.payer)
    course = load_course_data(payload.course_id)
    amount = money_to_float(course.get("price"))
    access_token = get_access_token()

    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    api_base_url = os.getenv("API_BASE_URL", str(request.base_url).rstrip("/")).rstrip("/")
    # Sufixo aleatório: duas compras do mesmo curso no mesmo segundo não podem compartilhar referência
    # (o webhook localiza a matrícula pela referência).
    external_reference = f"{payload.course_id}:{int(datetime.utcnow().timestamp())}:{uuid.uuid4().hex[:8]}"

    preference_data = {
        "items": [
            {
                "id": payload.course_id,
                "title": course.get("name", "Curso Global Training"),
                "description": course.get("description", "Matrícula em curso Global Training Technology"),
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": amount,
            }
        ],
        "payer": {
            "name": payload.payer.name,
            "email": payload.payer.email,
            "phone": {"number": payload.payer.phone or ""},
        },
        "external_reference": external_reference,
        "back_urls": {
            "success": f"{frontend_base_url}/frontend/landing_global_training.html?payment=success",
            "failure": f"{frontend_base_url}/frontend/landing_global_training.html?payment=failure",
            "pending": f"{frontend_base_url}/frontend/landing_global_training.html?payment=pending",
        },
        "notification_url": f"{api_base_url}/api/payments/webhook",
        "statement_descriptor": "GLOBAL TRAINING",
        "metadata": {
            "course_id": payload.course_id,
            "course_name": course.get("name"),
            "student_name": payload.payer.name,
            "student_email": payload.payer.email,
        },
    }

    response = requests.post(
        MERCADO_PAGO_PREFERENCES_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=preference_data,
        timeout=15,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao criar checkout no Mercado Pago: {response.text}",
        )

    preference = response.json()
    checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
    if not checkout_url:
        raise HTTPException(status_code=502, detail="Mercado Pago não retornou URL de checkout.")

    # Persiste aluno/matrícula/pagamento para alimentar os dashboards
    # administrativos da Fase 2 (Dashboard de Alunos/Cursos/Financeiro).
    # Conta do aluno (role 'student', sem senha) e matrícula 'pending'; a matrícula é
    # ativada pelo webhook quando o pagamento for aprovado.
    user_id = Database.get_or_create_user(payload.payer.email, payload.payer.name)
    enrollment_id = Database.create_enrollment(user_id, payload.course_id, external_reference)
    Database.record_payment(enrollment_id, amount, "mercado_pago")

    return {
        "status": "success",
        "preference_id": preference.get("id"),
        "checkout_url": checkout_url,
        "sandbox_checkout_url": preference.get("sandbox_init_point"),
        "external_reference": external_reference,
    }


def _entregar_definicao_de_senha(external_reference: str):
    """Pagamento aprovado e conta sem senha: emite o token de definição e envia o link (E2, D12/D13)."""
    conta = Database.get_user_by_external_reference(external_reference)
    if not conta or conta["password_hash"] is not None:
        return
    token = emitir_token_definicao(conta["id"])
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    send_password_setup_link(conta["email"], f"{frontend_base_url}/definir-senha?token={token}")


@router.post("/webhook")
async def mercado_pago_webhook(request: Request):
    data = await request.json()
    payment_id = data.get("data", {}).get("id") or data.get("id")

    if not payment_id:
        return {"status": "ignored", "reason": "missing payment id"}

    access_token = get_access_token()
    response = requests.get(
        f"{MERCADO_PAGO_PAYMENTS_URL}/{payment_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Erro ao consultar pagamento no Mercado Pago.")

    payment = response.json()
    status = payment.get("status")
    external_reference = payment.get("external_reference")

    if external_reference:
        Database.update_payment_status_by_reference(external_reference, status, str(payment_id))
        if status == "approved":
            _entregar_definicao_de_senha(external_reference)
    print(f"[PAGAMENTO] Payment update: {payment_id} | {status} | {external_reference}")

    return {
        "status": "received",
        "payment_id": payment_id,
        "payment_status": status,
        "external_reference": external_reference,
    }


@router.post("/refund/{payment_id}")
async def refund_payment(
    payment_id: int,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN, Role.FINANCIAL)),
):
    """
    Marca um pagamento como reembolsado localmente e registra a trilha de
    auditoria (Fase 2 - Governança: reembolsos são eventos críticos).
    A chamada ao gateway de pagamento em produção deve ser feita aqui também;
    neste MVP apenas o status local é atualizado.
    """
    payment = Database.get_payment_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado.")

    # Estado ANTES do reembolso, para a trilha (E8, D45).
    payment_status_before = payment.get("status")
    enrollment = Database.get_enrollment_by_id(payment.get("enrollment_id"))
    enrollment_status_before = enrollment.get("status") if enrollment else None

    # Marca o pagamento e a matrícula como refunded.
    Database.mark_payment_refunded(payment_id)

    # Reembolsar de novo um pagamento já refunded não muda nada: sem evento novo.
    # A trilha é gravada depois da alteração; se falhar, a rota termina em 500 genérico.
    if payment_status_before != "refunded":
        record_audit(
            "payment.refund",
            f"Pagamento #{payment_id} (R$ {float(payment.get('amount', 0)):.2f}) marcado como reembolsado",
            user=current_user,
            entity_type="payment",
            entity_id=payment_id,
            changes=[
                change("payment.status", payment_status_before, "refunded"),
                change("enrollment.status", enrollment_status_before, "refunded"),
            ],
        )

    return {
        "status": "success",
        "message": f"Pagamento #{payment_id} reembolsado.",
    }
