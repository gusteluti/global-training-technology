from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
import hmac
import os
import re
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

# Textos fixos de erro (E9, D48): nunca repassam corpo do gateway nem texto de exceção.
DETAIL_ASSINATURA = "Assinatura inválida."
DETAIL_WEBHOOK_NAO_CONFIGURADO = "Webhook não configurado."
DETAIL_ID_INVALIDO = "Identificador de pagamento inválido."
DETAIL_CONSULTA_GATEWAY = "Erro ao consultar pagamento no Mercado Pago."
DETAIL_CHECKOUT_FALHA = "Não foi possível iniciar o pagamento. Tente novamente."
DETAIL_CHECKOUT_INDISPONIVEL = "Pagamento indisponível no momento."
DETAIL_REEMBOLSO_NAO_APROVADO = "Só é possível reembolsar pagamentos aprovados."

# Só dígitos ASCII (D49.3): `\d` aceitaria dígitos de outros alfabetos.
PAYMENT_ID_RE = re.compile(r"[0-9]{1,20}")
TS_RE = re.compile(r"[0-9]+")
V1_RE = re.compile(r"[0-9a-fA-F]{64}")

CENTAVOS = Decimal("0.01")

MOTIVO_IGNORADO = {
    "unknown_reference": "unknown reference",
    "unsupported_status": "unsupported status",
    "terminal": "terminal",
    "duplicate": "duplicate",
    "stale": "stale",
    "duplicate_transaction": "duplicate transaction",
}

# Transições por webhook que entram na trilha de auditoria (D48).
STATUS_AUDITADOS = ("approved", "refunded", "charged_back")


class PayerInput(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class CheckoutInput(BaseModel):
    course_id: str
    payer: PayerInput


def _access_token_gateway() -> str:
    """Token do Mercado Pago ('' quando não configurado ou em branco)."""
    return (os.getenv("MERCADO_PAGO_ACCESS_TOKEN") or "").strip()


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
    # O preço vem sempre do catálogo do servidor; price/amount enviados pelo cliente são ignorados.
    amount = money_to_float(course.get("price"))
    access_token = _access_token_gateway()
    if not access_token:
        raise HTTPException(status_code=503, detail=DETAIL_CHECKOUT_INDISPONIVEL)

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

    # Erros do gateway: o cliente recebe só o texto fixo; o log traz só o status (nunca o corpo).
    try:
        response = requests.post(
            MERCADO_PAGO_PREFERENCES_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=preference_data,
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[ERRO] Falha de comunicação com o Mercado Pago no checkout: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail=DETAIL_CHECKOUT_FALHA)

    if response.status_code >= 400:
        print(f"[ERRO] Mercado Pago recusou a criação do checkout: HTTP {response.status_code}")
        raise HTTPException(status_code=502, detail=DETAIL_CHECKOUT_FALHA)

    try:
        preference = response.json()
    except ValueError:
        print("[ERRO] Mercado Pago devolveu resposta ilegível na criação do checkout")
        raise HTTPException(status_code=502, detail=DETAIL_CHECKOUT_FALHA)
    if not isinstance(preference, dict):
        print("[ERRO] Mercado Pago devolveu resposta inesperada na criação do checkout")
        raise HTTPException(status_code=502, detail=DETAIL_CHECKOUT_FALHA)

    checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
    if not checkout_url:
        print("[ERRO] Mercado Pago não retornou URL de checkout")
        raise HTTPException(status_code=502, detail=DETAIL_CHECKOUT_FALHA)

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


# ---------------------------------------------------------------------------------------------
# Webhook do Mercado Pago (E9, D48/D49)
# ---------------------------------------------------------------------------------------------

async def _corpo_json(request: Request) -> dict:
    """Corpo JSON do webhook; ilegível ou que não seja objeto vira {} (a assinatura decide o resto)."""
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001 - qualquer corpo ilegível é tratado como vazio
        return {}
    return corpo if isinstance(corpo, dict) else {}


def _como_texto_de_id(valor) -> Optional[str]:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (str, int)):
        texto = str(valor)
        return texto or None
    return None


def _data_id(request: Request, corpo: dict) -> Optional[str]:
    """`data.id` da query (preferido) ou do corpo."""
    da_query = request.query_params.get("data.id")
    if da_query:
        return da_query
    dados = corpo.get("data")
    if isinstance(dados, dict):
        return _como_texto_de_id(dados.get("id"))
    return None


def _assinatura_valida(request: Request, data_id: Optional[str], segredo: str) -> bool:
    """Confere x-signature (`ts=<número>,v1=<hex>`) contra o manifesto do Mercado Pago. Qualquer falha = False."""
    cabecalho = request.headers.get("x-signature")
    request_id = request.headers.get("x-request-id")
    if not cabecalho or not request_id or not data_id:
        return False

    partes = {}
    for pedaco in cabecalho.split(","):
        chave, separador, valor = pedaco.strip().partition("=")
        if not separador or chave in partes:
            return False
        partes[chave] = valor
    ts, v1 = partes.get("ts", ""), partes.get("v1", "")
    if not TS_RE.fullmatch(ts) or not V1_RE.fullmatch(v1):
        return False

    id_manifesto = data_id.lower() if data_id.isalnum() else data_id
    manifesto = f"id:{id_manifesto};request-id:{request_id};ts:{ts};"
    esperado = hmac.new(segredo.encode("utf-8"), manifesto.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado.encode("ascii"), v1.lower().encode("ascii"))


def _topico_e_payment(request: Request, corpo: dict) -> bool:
    """Todos os `type`/`topic` informados (query e corpo) devem ser 'payment', e ao menos um deve existir."""
    informados = [
        request.query_params.get("type"),
        request.query_params.get("topic"),
        corpo.get("type"),
        corpo.get("topic"),
    ]
    informados = [valor for valor in informados if valor not in (None, "")]
    return bool(informados) and all(valor == "payment" for valor in informados)


def _decimal_ou_none(valor) -> Optional[Decimal]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def _valor_esperado(amount) -> Decimal:
    return Decimal(str(amount)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _valor_e_moeda_conferem(pagamento_local: dict, pagamento_mp: dict) -> bool:
    """Valor igual ao gravado (2 casas, Decimal; mais casas que isso não confere) e moeda BRL."""
    recebido = _decimal_ou_none(pagamento_mp.get("transaction_amount"))
    if recebido is None or recebido != _valor_esperado(pagamento_local["amount"]):
        return False
    return pagamento_mp.get("currency_id") == "BRL"


def _texto_curto(valor, limite: int = 50) -> Optional[str]:
    return None if valor is None else str(valor)[:limite]


def _consultar_pagamento_no_gateway(data_id: str) -> dict:
    access_token = _access_token_gateway()
    if not access_token:
        raise HTTPException(status_code=503, detail=DETAIL_WEBHOOK_NAO_CONFIGURADO)
    try:
        response = requests.get(
            f"{MERCADO_PAGO_PAYMENTS_URL}/{data_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[ERRO] Falha de comunicação com o Mercado Pago no webhook: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail=DETAIL_CONSULTA_GATEWAY)

    if response.status_code >= 400:
        print(f"[ERRO] Mercado Pago recusou a consulta do pagamento: HTTP {response.status_code}")
        raise HTTPException(status_code=502, detail=DETAIL_CONSULTA_GATEWAY)
    try:
        pagamento = response.json()
    except ValueError:
        pagamento = None
    if not isinstance(pagamento, dict):
        print("[ERRO] Mercado Pago devolveu resposta inesperada na consulta do pagamento")
        raise HTTPException(status_code=502, detail=DETAIL_CONSULTA_GATEWAY)
    return pagamento


@router.post("/webhook")
async def mercado_pago_webhook(request: Request):
    # 1. Assinatura (fail closed), antes de qualquer outra coisa.
    segredo = os.getenv("MERCADO_PAGO_WEBHOOK_SECRET") or ""
    if not segredo.strip():
        raise HTTPException(status_code=503, detail=DETAIL_WEBHOOK_NAO_CONFIGURADO)
    corpo = await _corpo_json(request)
    data_id = _data_id(request, corpo)
    if not _assinatura_valida(request, data_id, segredo):
        raise HTTPException(status_code=401, detail=DETAIL_ASSINATURA)

    # 2. Tópico e identificador.
    if not _topico_e_payment(request, corpo):
        return {"status": "ignored", "reason": "unsupported topic"}
    if not PAYMENT_ID_RE.fullmatch(data_id):
        raise HTTPException(status_code=400, detail=DETAIL_ID_INVALIDO)

    # 3. O estado do pagamento é sempre reconsultado no Mercado Pago.
    pagamento_mp = _consultar_pagamento_no_gateway(data_id)
    status = pagamento_mp.get("status")
    external_reference = pagamento_mp.get("external_reference")
    if not isinstance(external_reference, str) or not external_reference:
        return {"status": "ignored", "reason": "unknown reference"}
    if not isinstance(status, str):
        return {"status": "ignored", "reason": "unsupported status"}

    # 4. Transição atômica (máquina de estados, valor e moeda, transaction_id único).
    resultado = Database.aplicar_transicao_pagamento_webhook(
        external_reference,
        status,
        data_id,
        valor_confere=lambda local: _valor_e_moeda_conferem(local, pagamento_mp),
    )
    outcome = resultado["outcome"]
    print(f"[PAGAMENTO] Payment update: {data_id} | {status} | {outcome}")

    if outcome == "amount_mismatch":
        recebido = _decimal_ou_none(pagamento_mp.get("transaction_amount"))
        record_audit(
            "payment.amount_mismatch",
            f"Pagamento #{resultado['payment_id']}: valor ou moeda do Mercado Pago diverge do valor gravado",
            actor={"role": "system"},
            entity_type="payment",
            entity_id=resultado["payment_id"],
            changes=[
                change(
                    "payment.amount",
                    format(_valor_esperado(resultado["amount"]), "f"),
                    format(recebido, "f") if recebido is not None
                    else _texto_curto(pagamento_mp.get("transaction_amount")),
                ),
                change("payment.currency", "BRL", _texto_curto(pagamento_mp.get("currency_id"), 20)),
            ],
        )
        return {"status": "rejected", "reason": "amount_mismatch"}

    if outcome != "applied":
        return {"status": "ignored", "reason": MOTIVO_IGNORADO[outcome]}

    # 5. Efeitos colaterais, uma vez só: só a transição aplicada chega aqui. A entrega do link de
    #    senha não espera pela trilha; se a trilha falhar, o erro sobe depois da entrega (D45).
    erro_de_trilha = None
    if status in STATUS_AUDITADOS:
        try:
            record_audit(
                "payment.status_change",
                f"Pagamento #{resultado['payment_id']}: {resultado['status_before']} -> {status} (webhook Mercado Pago)",
                actor={"role": "system"},
                entity_type="payment",
                entity_id=resultado["payment_id"],
                changes=[change("payment.status", resultado["status_before"], status)],
            )
        except HTTPException as exc:
            erro_de_trilha = exc
    if status == "approved":
        _entregar_definicao_de_senha(external_reference)
    if erro_de_trilha is not None:
        raise erro_de_trilha

    return {
        "status": "received",
        "payment_id": data_id,
        "payment_status": status,
        "external_reference": external_reference,
    }


@router.post("/refund/{payment_id}")
async def refund_payment(
    payment_id: int,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN, Role.FINANCIAL)),
):
    """
    Marca um pagamento aprovado como reembolsado localmente e registra a trilha de
    auditoria (Fase 2 - Governança: reembolsos são eventos críticos).
    Só `approved` pode ser reembolsado (E9, D48); a condição e a gravação são atômicas, então
    reembolsos simultâneos geram um único evento. Já reembolsado: 200 idempotente, sem evento novo.
    A chamada ao gateway de pagamento em produção deve ser feita aqui também;
    neste MVP apenas o status local é atualizado.
    """
    resultado = Database.reembolsar_pagamento_se_aprovado(payment_id)
    outcome = resultado["outcome"]
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Pagamento não encontrado.")
    if outcome == "not_approved":
        raise HTTPException(status_code=409, detail=DETAIL_REEMBOLSO_NAO_APROVADO)

    # A trilha é gravada depois da alteração; se falhar, a rota termina em 500 genérico.
    if outcome == "refunded":
        record_audit(
            "payment.refund",
            f"Pagamento #{payment_id} (R$ {float(resultado.get('amount') or 0):.2f}) marcado como reembolsado",
            user=current_user,
            entity_type="payment",
            entity_id=payment_id,
            changes=[
                change("payment.status", resultado["payment_status_before"], "refunded"),
                change("enrollment.status", resultado["enrollment_status_before"], "refunded"),
            ],
        )

    return {
        "status": "success",
        "message": f"Pagamento #{payment_id} reembolsado.",
    }
