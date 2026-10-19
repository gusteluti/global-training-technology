"""Apoio dos e2e que chamam o webhook do Mercado Pago (E9, D48). Não é código de produção.

- SEGREDO_WEBHOOK: o segredo de teste que os harnesses (servidor_e2e_e5.py e derivados) publicam em
  MERCADO_PAGO_WEBHOOK_SECRET no backend de teste.
- id_de_pagamento(): id numérico do pagamento, determinístico por referência externa (o webhook só aceita
  ids numéricos; o harness do Mercado Pago falso devolve o pagamento registrado para esse id).
- enviar_webhook(): POST assinado (x-signature/x-request-id no formato da D48) em /api/payments/webhook, com
  data.id na query e no corpo. Devolve (status_http, corpo_json_ou_None).

Funciona contra o código anterior à E9 (que ignora a assinatura) e contra o da E9.
"""

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request

SEGREDO_WEBHOOK = "segredo-webhook-e2e-teste"
TS_PADRAO = "1700000000000"
REQUEST_ID_PADRAO = "req-e2e-0001"


def id_de_pagamento(referencia: str) -> str:
    return str(int(hashlib.sha256(str(referencia).encode("utf-8")).hexdigest()[:12], 16))


def assinar(data_id, request_id=REQUEST_ID_PADRAO, ts=TS_PADRAO, segredo=SEGREDO_WEBHOOK) -> dict:
    manifesto = f"id:{str(data_id).lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(segredo.encode("utf-8"), manifesto.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


def enviar_webhook(api: str, referencia: str, timeout: int = 15):
    """Webhook assinado para o pagamento da `referencia` (id numérico derivado dela)."""
    mp_id = id_de_pagamento(referencia)
    consulta = urllib.parse.urlencode({"data.id": mp_id, "type": "payment"})
    corpo = json.dumps({"type": "payment", "data": {"id": mp_id}}).encode("utf-8")
    cabecalhos = {"Content-Type": "application/json", **assinar(mp_id)}
    requisicao = urllib.request.Request(f"{api}/api/payments/webhook?{consulta}", data=corpo,
                                        headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None
