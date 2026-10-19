"""Backend de teste do e2e do dashboard de alunos (E5). Não é código de produção.

Reaproveita o servidor_e2e_e5.py (Groq substituído por dublê, banco SQLite temporário isolado,
variáveis de ambiente fabricadas) e acrescenta só uma conta de funcionário de suporte, porque o
servidor_e2e_e5.py deixa SUPPORT_EMAIL vazio (não semeia o perfil Suporte).

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_e5_dashboard.py --port 8123 --db-path <tmp>/db.sqlite \
      --outbox <tmp>/outbox.jsonl --log-llm <tmp>/llm.jsonl
"""

import argparse
import os
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402

SUPPORT_EMAIL = "suporte.e5@teste.com"
SUPPORT_PASSWORD = "senha-sup-e5-teste"  # mesmo valor que o servidor_e2e_e5.py usa em SUPPORT_PASSWORD


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--log-llm", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    os.environ["SUPPORT_EMAIL"] = SUPPORT_EMAIL
    os.environ["SUPPORT_PASSWORD"] = SUPPORT_PASSWORD
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    base._instalar_duble(Path(args.log_llm))

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
