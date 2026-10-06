"""Configuração compartilhada das suítes de backend (pytest).

- Variáveis de ambiente mínimas para importar e subir a aplicação.
- `db_path`: aponta Database.DB_PATH para um arquivo temporário (tmp_path).
- `banco`: `db_path` + Database.init_db() (schema atual).

Observação: importar `db` executa Database.init_db() uma vez, no caminho padrão
(backend/db.sqlite, ignorado pelo git). Os testes não usam esse arquivo: todo
teste reaponta DB_PATH para tmp_path antes de qualquer operação.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# E9 (D48): segredo de teste do webhook do Mercado Pago; os testes assinam com apoio_mercado_pago.assinar().
from apoio_mercado_pago import SEGREDO_WEBHOOK  # noqa: E402

os.environ.update({
    "MERCADO_PAGO_WEBHOOK_SECRET": SEGREDO_WEBHOOK,
    "GROQ_API_KEY": "dummy",
    "ADMIN_PASSWORD": "admin123",
    "ADMIN_TOKEN_SECRET": "staff-secret-123",
    "JWT_SECRET_KEY": "jwt-secret-456-long-enough",
    "FINANCIAL_PASSWORD": "fin123",
    "SUPPORT_PASSWORD": "sup123",
    "MERCADO_PAGO_ACCESS_TOKEN": "TEST-fake",
    "FRONTEND_BASE_URL": "http://localhost:8000",
    "API_BASE_URL": "http://localhost:8000",
})


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Aponta o banco para um arquivo temporário. Não inicializa o schema."""
    from db import Database

    caminho = tmp_path / "db.sqlite"
    monkeypatch.setattr(Database, "DB_PATH", caminho)
    return caminho


@pytest.fixture
def banco(db_path):
    """Banco temporário com o schema atual (Database.init_db())."""
    from db import Database

    Database.init_db()
    return db_path
