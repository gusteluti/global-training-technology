"""Apoio compartilhado dos testes que falam com o webhook do Mercado Pago (E9, D48).

Módulo de apoio (não é teste). Fica ao lado do conftest, que coloca este diretório no sys.path.

- SEGREDO_WEBHOOK: o segredo de teste que o conftest publica em MERCADO_PAGO_WEBHOOK_SECRET.
- assinar(): cabeçalhos x-signature e x-request-id no formato da D48
  (manifesto `id:<data_id>;request-id:<x-request-id>;ts:<ts>;`, HMAC-SHA256 hex).
- post_webhook(): POST assinado em /api/payments/webhook (data.id na query E no corpo, tópico payment).
- id_de_pagamento(): id numérico de pagamento, determinístico por referência (o webhook só aceita ids numéricos
  e o transaction_id não pode se repetir entre pagamentos distintos).
- corpo_pagamento_mp(): o JSON que o Mercado Pago devolveria em GET /v1/payments/{id}, com valor e moeda.

Tudo isto funciona tanto contra o código atual (que ignora cabeçalhos e consulta) quanto contra a E9.
"""

import hashlib
import hmac

SEGREDO_WEBHOOK = "segredo-webhook-de-teste-e9"
TS_PADRAO = "1700000000000"
REQUEST_ID_PADRAO = "req-e9-0001"
URL_WEBHOOK = "/api/payments/webhook"


def id_de_pagamento(referencia) -> str:
    """Id numérico (12 dígitos hexadecimais lidos como inteiro, no máximo 15 dígitos decimais) por referência."""
    return str(int(hashlib.sha256(str(referencia).encode("utf-8")).hexdigest()[:12], 16))


def assinar(data_id, request_id=REQUEST_ID_PADRAO, ts=TS_PADRAO, segredo=SEGREDO_WEBHOOK) -> dict:
    """Cabeçalhos assinados como o Mercado Pago assina. `data_id` em minúsculas se alfanumérico (D48)."""
    id_manifesto = str(data_id)
    if id_manifesto.isalnum():
        id_manifesto = id_manifesto.lower()
    manifesto = f"id:{id_manifesto};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(str(segredo).encode("utf-8"), manifesto.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


def corpo_pagamento_mp(status, referencia, valor, pagamento_id, moeda="BRL") -> dict:
    """Resposta de GET /v1/payments/{id} do Mercado Pago (campos que a rota usa)."""
    return {
        "id": pagamento_id,
        "status": status,
        "external_reference": referencia,
        "transaction_amount": valor,
        "currency_id": moeda,
    }


def post_webhook(client, data_id, *, tipo="payment", assinatura=True, na_query=True, no_corpo=True,
                 headers=None, **kw_assinatura):
    """POST em /api/payments/webhook, assinado. `kw_assinatura` vai para assinar() (segredo, ts, request_id).

    Com assinatura=False não envia cabeçalho de assinatura (para testar a recusa).
    """
    cabecalhos = {}
    if assinatura:
        cabecalhos.update(assinar(data_id, **kw_assinatura))
    cabecalhos.update(headers or {})
    params = {}
    if na_query:
        params["data.id"] = str(data_id)
        if tipo is not None:
            params["type"] = tipo
    corpo = {}
    if tipo is not None:
        corpo["type"] = tipo
    if no_corpo:
        corpo["data"] = {"id": str(data_id)}
    return client.post(URL_WEBHOOK, params=params, json=corpo, headers=cabecalhos)
