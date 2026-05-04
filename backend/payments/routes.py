from datetime import datetime
import os
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

from admin.routes import load_course_data

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
    external_reference = f"{payload.course_id}:{int(datetime.utcnow().timestamp())}"

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

    return {
        "status": "success",
        "preference_id": preference.get("id"),
        "checkout_url": checkout_url,
        "sandbox_checkout_url": preference.get("sandbox_init_point"),
        "external_reference": external_reference,
    }


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

    # MVP: do not grant access here yet. In production, persist this event and
    # release enrollment only when status == "approved".
    print(f"💳 Payment update: {payment_id} | {status} | {external_reference}")

    return {
        "status": "received",
        "payment_id": payment_id,
        "payment_status": status,
        "external_reference": external_reference,
    }
