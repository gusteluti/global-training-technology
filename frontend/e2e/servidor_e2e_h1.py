"""Backend de teste dos e2e antigos migrados (D58, entrega H1). Não é código de produção.

Reaproveita os harnesses anteriores (`servidor_e2e_e5.py` -> `servidor_e2e_e7.py` -> `servidor_e2e_e8.py`):
banco SQLite temporário isolado, diretório de cursos temporário, Groq falso e Mercado Pago falso (create-checkout
e webhook aprovam sem rede), segredo de webhook de teste (`apoio_webhook_mp.SEGREDO_WEBHOOK`).

Diferenças deste servidor:
  1. Contas de funcionário com os e-mails e as senhas que os e2e antigos usam, fabricadas AQUI e passadas por
     variável de ambiente ao app (o app semeia uma conta por perfil a partir de <PERFIL>_EMAIL/<PERFIL>_PASSWORD).
     Nada vem de um `.env` real: o python-dotenv não sobrescreve variável já definida, e todas as variáveis que
     importam são definidas (inclusive com valor vazio) antes do import do app.
       admin@gt.com / admin123      (perfil Gestão; ADMIN_PASSWORD também é a senha do login administrativo legado)
       financeiro@gt.com / fin123   (perfil Financeiro)
       suporte@gt.com / sup123      (perfil Suporte)
  2. CORS de teste: `CORS_ALLOWED_ORIGINS` recebe a origem do `ng serve` do teste (passada em --cors-origin).

O backend/db.sqlite e o backend/courses de desenvolvimento não são abertos nem alterados.

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_h1.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl \
      --courses-dir <tmp>/courses --cors-origin http://localhost:4300
"""

import argparse
import os
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402
import servidor_e2e_e7 as e7  # noqa: E402
import servidor_e2e_e8 as e8  # noqa: E402

GESTAO_EMAIL = "admin@gt.com"
GESTAO_SENHA = "admin123"
FINANCEIRO_EMAIL = "financeiro@gt.com"
FINANCEIRO_SENHA = "fin123"
SUPORTE_EMAIL = "suporte@gt.com"
SUPORTE_SENHA = "sup123"


def _ambiente_h1(cors_origin: str) -> None:
    os.environ.update({
        "ADMIN_EMAIL": GESTAO_EMAIL,
        "ADMIN_PASSWORD": GESTAO_SENHA,
        "FINANCIAL_EMAIL": FINANCEIRO_EMAIL,
        "FINANCIAL_PASSWORD": FINANCEIRO_SENHA,
        "SUPPORT_EMAIL": SUPORTE_EMAIL,
        "SUPPORT_PASSWORD": SUPORTE_SENHA,
        "GROQ_MODEL": e7.MODELO,
        "GROQ_PRICE_INPUT_PER_1M_USD": str(e7.PRECO_ENTRADA),
        "GROQ_PRICE_OUTPUT_PER_1M_USD": str(e7.PRECO_SAIDA),
        "CORS_ALLOWED_ORIGINS": cors_origin,
        "FRONTEND_BASE_URL": cors_origin,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--courses-dir", required=True)
    parser.add_argument("--cors-origin", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    _ambiente_h1(args.cors_origin)
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    e8._isolar_cursos(Path(args.courses_dir))
    e7._instalar_groq_falso()
    e7._instalar_mercado_pago_falso()

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
