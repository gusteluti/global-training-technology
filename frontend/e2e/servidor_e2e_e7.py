"""Backend de teste do e2e da E7 (observabilidade de IA). Não é código de produção.

Diferença para o servidor_e2e_e5_dashboard.py: aqui o dublê fica UM NÍVEL ABAIXO. Em vez de substituir
`GroqChatClient.create_chat_completion` (que não grava `ai_usage`), substitui a classe `Groq` do SDK
(`agents.groq_client.Groq`) por um falso cujo `client.chat.completions.create(**kw)` devolve texto fixo e
`usage` fixo. Assim o código real da E7 (`create_chat_completion` -> `ai_observability`) roda inteiro e grava
`ai_usage` e `ai_interactions` no banco temporário.

  - Chamada de roteamento (max_completion_tokens <= 300): texto "GENERAL", usage (400, 100, 500).
  - Demais chamadas (resposta): texto fixo, usage (1500, 250, 1750).
  - Preços fixos por ambiente: GROQ_PRICE_INPUT_PER_1M_USD=2 e GROQ_PRICE_OUTPUT_PER_1M_USD=8.

Também substitui, SÓ neste processo de teste, o `requests` do módulo de pagamentos por um Mercado Pago falso
(POST de preferência e GET de pagamento), para que a matrícula do aluno possa ser criada e aprovada pela API
pública (create-checkout + webhook) sem rede. E9 (D48): o POST falso registra, por id numérico de pagamento
(`apoio_webhook_mp.id_de_pagamento(external_reference)`), a referência e o valor da preferência; o GET falso
devolve esse pagamento "approved", com `transaction_amount` e `currency_id` BRL, para o id pedido (o webhook
assinado do teste usa o mesmo id). Nenhuma chamada ao Groq nem ao Mercado Pago reais; o backend/db.sqlite de
desenvolvimento não é aberto (banco isolado do servidor_e2e_e5.py).

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_e7.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl
"""

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402
from apoio_webhook_mp import id_de_pagamento  # noqa: E402

SUPPORT_EMAIL = "suporte.e5@teste.com"
SUPPORT_PASSWORD = "senha-sup-e5-teste"

MODELO = "modelo-e7-e2e"
PRECO_ENTRADA = 2.0
PRECO_SAIDA = 8.0
USAGE_ROTA = (400, 100, 500)
USAGE_RESPOSTA = (1500, 250, 1750)
TEXTO_RESPOSTA = "Resposta fixa do dublê e7."


class _RespostaFalsa:
    def __init__(self, status_code, corpo):
        self.status_code = status_code
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        return self._corpo


def _instalar_groq_falso() -> None:
    from agents import groq_client  # noqa: PLC0415

    class GroqSDKFalso:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        @staticmethod
        def _create(**kw):
            limite = kw.get("max_completion_tokens", kw.get("max_tokens"))
            rota = limite is not None and limite <= 300
            conteudo = "GENERAL" if rota else TEXTO_RESPOSTA
            p, c, t = USAGE_ROTA if rota else USAGE_RESPOSTA
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=conteudo))],
                usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=t),
            )

    groq_client.Groq = GroqSDKFalso


def _instalar_mercado_pago_falso() -> None:
    from payments import routes as rotas_pagamento  # noqa: PLC0415

    preferencias = {}  # id numérico do pagamento -> (referência externa, valor da preferência)

    def post(url, headers=None, json=None, timeout=None):
        referencia = (json or {}).get("external_reference")
        itens = (json or {}).get("items") or [{}]
        if referencia:
            preferencias[id_de_pagamento(referencia)] = (referencia, itens[0].get("unit_price"))
        return _RespostaFalsa(200, {"id": "pref-e2e", "init_point": "https://mp.invalid/checkout"})

    def get(url, headers=None, timeout=None):
        mp_id = url.rsplit("/", 1)[-1]
        if mp_id not in preferencias:
            return _RespostaFalsa(404, {"message": "payment not found"})
        referencia, valor = preferencias[mp_id]
        return _RespostaFalsa(200, {
            "id": mp_id, "status": "approved", "external_reference": referencia,
            "transaction_amount": valor, "currency_id": "BRL",
        })

    rotas_pagamento.requests = SimpleNamespace(post=post, get=get)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    os.environ["SUPPORT_EMAIL"] = SUPPORT_EMAIL
    os.environ["SUPPORT_PASSWORD"] = SUPPORT_PASSWORD
    os.environ["GROQ_MODEL"] = MODELO
    os.environ["GROQ_PRICE_INPUT_PER_1M_USD"] = str(PRECO_ENTRADA)
    os.environ["GROQ_PRICE_OUTPUT_PER_1M_USD"] = str(PRECO_SAIDA)
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    _instalar_groq_falso()
    _instalar_mercado_pago_falso()

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
