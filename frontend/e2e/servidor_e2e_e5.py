"""Backend de teste do e2e da E5 (chat do aluno). Não é código de produção.

Sobe a API FastAPI real num processo próprio, mas com duas diferenças em relação ao uvicorn normal:
  1. NENHUMA chamada ao Groq: `agents.groq_client.GroqChatClient.create_chat_completion` é
     substituído por um dublê determinístico ANTES de o app iniciar.
  2. Banco isolado: todo acesso do SQLite é redirecionado para o arquivo passado em --db-path
     (o backend/db.sqlite de desenvolvimento não é aberto nem gravado, dívida D7). O redirecionamento
     cobre também o `Database.init_db()` que o módulo `db` executa ao ser importado.

Variáveis de ambiente: todas fabricadas aqui (valores de teste, nada real, nada gravado em arquivo).
Elas são definidas à força e têm precedência sobre um eventual backend/.env, porque o python-dotenv
não sobrescreve variável já definida.

Dublê do modelo:
  - chamada de roteamento de intenção (prompt "identifica intenções") -> "GENERAL";
  - qualquer outra chamada -> "Resposta simulada do assistente a: <última mensagem do aluno>".
  Cada chamada é registrada (uma linha JSON) em --log-llm, para inspeção opcional.

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_e5.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_webhook_mp import SEGREDO_WEBHOOK  # noqa: E402  (E9, D48: segredo de teste do webhook)

# Credenciais fabricadas para o e2e (as mesmas que o teste importa).
ADMIN_EMAIL = "admin.e5@teste.com"
ADMIN_PASSWORD = "senha-admin-e5-teste"

PREFIXO_RESPOSTA = "Resposta simulada do assistente a: "


def _ambiente(outbox: str) -> None:
    os.environ.update({
        "GROQ_API_KEY": "chave-falsa-de-teste-e5",
        "GROQ_MODEL": "modelo-falso",
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "ADMIN_TOKEN_SECRET": "segredo-staff-e5-teste",
        "JWT_SECRET_KEY": "segredo-jwt-e5-teste-bem-longo-0123456789",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
        "FINANCIAL_PASSWORD": "senha-fin-e5-teste",
        "SUPPORT_PASSWORD": "senha-sup-e5-teste",
        # vazios: impedem que um backend/.env semeie outras contas de funcionário no banco de teste
        "FINANCIAL_EMAIL": "",
        "SUPPORT_EMAIL": "",
        "MERCADO_PAGO_ACCESS_TOKEN": "TEST-fake-e5",
        "MERCADO_PAGO_WEBHOOK_SECRET": SEGREDO_WEBHOOK,
        "FRONTEND_BASE_URL": "http://localhost:4200",
        "API_BASE_URL": "http://localhost:8000",
        "PASSWORD_LINK_OUTBOX": outbox,
    })


def _importar_app_com_banco_isolado(db_path: Path):
    """Importa o app com o SQLite redirecionado para db_path (inclui o init_db do import de `db`)."""
    original = sqlite3.connect

    def conectar(_database, *args, **kwargs):
        return original(str(db_path), *args, **kwargs)

    sqlite3.connect = conectar
    try:
        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        os.chdir(BACKEND)  # courses/ é lido por caminho relativo ao pacote; cwd só por segurança
        import db  # noqa: PLC0415  (executa Database.init_db() no banco isolado)
        import app as modulo_app  # noqa: PLC0415
    finally:
        sqlite3.connect = original
    db.Database.DB_PATH = db_path
    return modulo_app.app


def _instalar_duble(log_llm: Path) -> None:
    from agents import groq_client  # noqa: PLC0415

    def create_chat_completion(self, messages, max_tokens=1024, temperature=0.7):
        sistema = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")
        with open(log_llm, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
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
    args = parser.parse_args()

    _ambiente(args.outbox)
    app = _importar_app_com_banco_isolado(Path(args.db_path))
    _instalar_duble(Path(args.log_llm))

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
