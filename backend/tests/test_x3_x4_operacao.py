"""X3/X4 — backup do banco e /health com estado das dependências (D90, processo enxuto D84)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core import operacao
from db import Database


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
        corpo = c.get("/health").json()
    assert list((tmp_path / "auto").glob("db-*.sqlite"))
    assert corpo["services"]["backup"].startswith("db-")


def test_health_traz_servicos_e_mantem_chaves_antigas(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.teste.local")
    corpo = client.get("/health").json()
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
