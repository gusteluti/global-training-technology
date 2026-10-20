"""Backend de teste do e2e da F7 (curso a partir de anexo, D78). Não é código de produção.

É o backend do `servidor_e2e_e8.py` (harness D58: banco SQLite temporário, diretório de cursos temporário, contas de
Gestão, Suporte e Financeiro fabricadas, Mercado Pago falso), com um Groq falso próprio:
  - roteamento de intenção ("identifica intenções") -> "GENERAL";
  - pedido que traz o texto do PDF de teste (contém `MARCA_PDF`) -> `RESPOSTA_LLM` em JSON (inclui `system_prompt`,
    `materials` e `archived`, que a D78 manda descartar);
  - qualquer outro pedido -> um texto fixo.
Cada chamada é registrada (mensagens) em --log-llm.

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_f7.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl \
      --courses-dir <tmp>/courses --log-llm <tmp>/llm.jsonl
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
import servidor_e2e_e7 as e7  # noqa: E402
import servidor_e2e_e8 as e8  # noqa: E402

MARCA_PDF = "MARCA-PDF-E2E-F7-c41"
NOME_PDF = "Gestão Ágil de Projetos"
ID_PDF = "gestao_agil_de_projetos"
PROMPT_DO_LLM = "PROMPT-VINDO-DO-PDF-NAO-PODE-APARECER"
URL_DO_LLM = "https://atacante.test/f7/e2e.exe"
RESPOSTA_LLM = {
    "name": NOME_PDF, "description": "Scrum e Kanban na prática.", "price": 1500, "duration_hours": 40,
    "level": "Intermediário", "target_audience": "Gerentes e líderes", "objectives": ["Planejar sprints"],
    "topics": ["Scrum", "Kanban"], "benefits": ["Certificado"],
    "faq": [{"question": "Precisa de experiência?", "answer": "Não."}],
    "system_prompt": PROMPT_DO_LLM, "archived": True,
    "materials": [{"title": "Baixe aqui", "url": URL_DO_LLM, "type": "link"}],
}


def _instalar_llm_falso(log_llm: Path) -> None:
    from agents import groq_client  # noqa: PLC0415

    def create_chat_completion(self, messages, *args, **kwargs):
        with open(log_llm, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
        sistema = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        if "identifica intenções" in sistema:
            return "GENERAL"
        if any(MARCA_PDF in str(m.get("content") or "") for m in messages):
            return json.dumps(RESPOSTA_LLM, ensure_ascii=False)
        return "Resposta simulada do assistente."

    groq_client.GroqChatClient.create_chat_completion = create_chat_completion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--courses-dir", required=True)
    parser.add_argument("--log-llm", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    os.environ["SUPPORT_EMAIL"] = e8.SUPORTE_EMAIL
    os.environ["SUPPORT_PASSWORD"] = e8.SUPORTE_SENHA
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    e8._isolar_cursos(Path(args.courses_dir))
    _instalar_llm_falso(Path(args.log_llm))
    e7._instalar_mercado_pago_falso()
    e8._semear_contas()

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
