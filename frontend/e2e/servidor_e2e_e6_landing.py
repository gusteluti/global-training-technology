"""Backend de teste do e2e da landing page (E6). Não é código de produção.

Reaproveita o harness da E5 (`servidor_e2e_e5.py`, sem alterá-lo): API FastAPI real, banco SQLite
temporário isolado, variáveis de ambiente fabricadas e Groq SUBSTITUÍDO por dublê (nenhuma chamada real).

Diferença em relação ao dublê da E5: este também sabe FALHAR. Se alguma mensagem da chamada contiver o
marcador `FALHAR-LLM`, o dublê levanta uma exceção (simula o Groq fora do ar), o que o backend traduz em
`{"status":"error","message":LLM_UNAVAILABLE}` no chat anônimo. Sem o marcador, o comportamento é o da E5:
  - roteamento de intenção ("identifica intenções") -> "GENERAL";
  - qualquer outra chamada -> "Resposta simulada do assistente a: <última mensagem do usuário>".
Cada chamada (inclusive as que falham) é registrada em --log-llm, uma linha JSON com todas as mensagens
enviadas ao modelo, para o teste inspecionar o contexto que chegou ao LLM.

E9 (D48): o CORS do backend só libera as origens da lista. A landing de teste é servida por um servidor estático
em outra porta, então o teste passa essa origem em --cors-origin e o harness a publica em CORS_ALLOWED_ORIGINS.

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_e6_landing.py --port 8124 --db-path <tmp>/db.sqlite --outbox <tmp>/o.jsonl --log-llm <tmp>/llm.jsonl --cors-origin http://127.0.0.1:8125
"""

import argparse
import json
import os
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402

MARCADOR_FALHA = "FALHAR-LLM"
PREFIXO_RESPOSTA = base.PREFIXO_RESPOSTA


def _instalar_duble(log_llm: Path) -> None:
    from agents import groq_client  # noqa: PLC0415

    def create_chat_completion(self, messages, max_tokens=1024, temperature=0.7):
        with open(log_llm, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
        if any(MARCADOR_FALHA in (m.get("content") or "") for m in messages):
            raise RuntimeError("falha simulada do provedor de LLM (e2e)")
        sistema = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")
        if "identifica intenções" in sistema:
            return "GENERAL"
        ultima = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return PREFIXO_RESPOSTA + ultima

    groq_client.GroqChatClient.create_chat_completion = create_chat_completion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--log-llm", required=True)
    parser.add_argument("--cors-origin", default="", help="origem do servidor estático da landing (CORS_ALLOWED_ORIGINS)")
    args = parser.parse_args()

    base._ambiente(args.outbox)
    if args.cors_origin:
        os.environ["CORS_ALLOWED_ORIGINS"] = args.cors_origin
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    _instalar_duble(Path(args.log_llm))

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
