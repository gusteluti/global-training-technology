"""X3/X4 — backup do banco e estado das dependências (D90, processo enxuto D84).

SG1 (D109, P2; ajuste mecânico 4.3, D109 -> D111): o detalhe do estado das dependências saiu do `/health` público
(agora só `{"status": ...}`) e vive em `GET /api/dashboard/saude`, só para a Gestão. Os testes que liam `services`,
`courses_loaded`, `llm` e `payments_mock` do `/health` passam a ler da rota nova com o token da Gestão; a intenção
(o estado dos serviços aparece, sem segredo, e o backup do startup é reportado) é a mesma.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core import operacao
from core.security import create_access_token
from db import Database

ROTA_SAUDE = "/api/dashboard/saude"


def _gestao():
    """Cabeçalho de autorização de uma conta da Gestão (perfil admin), só para ler o detalhe de saúde (SG1)."""
    email = "gestao.x4@teste.com"
    user_id = Database.add_user(email, "Gestao X4", None, role="admin")
    token = create_access_token({"user_id": user_id, "email": email, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(banco):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def test_backup_copia_consistente(banco, tmp_path):
    Database.add_user("backup.x3@teste.com", "Backup", None)
    destino = operacao.fazer_backup(str(tmp_path / "bk"))
    conn = sqlite3.connect(destino)
    try:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE email = 'backup.x3@teste.com'").fetchone()[0] == 1
    finally:
        conn.close()


def test_backup_mantem_os_mais_recentes(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_KEEP", "3")
    pasta = tmp_path / "bk"
    inicio = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for dia in range(5):
        operacao.fazer_backup(str(pasta), agora=inicio + timedelta(days=dia))
    nomes = sorted(p.name for p in pasta.glob("db-*.sqlite"))
    assert nomes == ["db-20261003.sqlite", "db-20261004.sqlite", "db-20261005.sqlite"]


def test_sem_diretorio_nao_faz_backup(banco):
    assert operacao.fazer_backup() is None


def test_startup_faz_backup_quando_configurado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "auto"))
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        corpo = c.get(ROTA_SAUDE, headers=_gestao()).json()
    assert list((tmp_path / "auto").glob("db-*.sqlite"))
    assert corpo["services"]["backup"].startswith("db-")


def test_saude_traz_servicos_e_mantem_chaves_antigas(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.teste.local")
    corpo = client.get(ROTA_SAUDE, headers=_gestao()).json()
    assert corpo["status"] == "ok"
    for chave in ("courses_loaded", "llm", "payments_mock"):
        assert chave in corpo
    servicos = corpo["services"]
    assert servicos["database"] == "ok"
    assert servicos["email"] == "configurado" and servicos["payment_gateway"] == "configurado"
    assert servicos["backup"] == "desligado"
    texto = str(corpo)
    assert "TEST-fake" not in texto and "smtp.teste.local" not in texto


def test_health_degradado_quando_banco_cai(client, monkeypatch, tmp_path):
    monkeypatch.setattr(Database, "DB_PATH", tmp_path / "nao" / "existe" / "db.sqlite")
    assert client.get("/health").json()["status"] == "degraded"
