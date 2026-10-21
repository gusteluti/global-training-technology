"""U6 — envio de e-mail real por SMTP (D88, processo enxuto D84).

Servidor SMTP falso (monkeypatch de smtplib): nada sai da máquina. Cobre envio com SMTP configurado, conteúdo
(assunto, link, texto e HTML), STARTTLS/login, SSL na 465, falha que não derruba o fluxo, desligado sem SMTP_HOST e
o fluxo real de "esqueci minha senha" disparando o e-mail.
"""

import smtplib

import pytest
from fastapi.testclient import TestClient

from core import notifications
from core.security import get_password_hash
from db import Database


class SMTPFalso:
    instancias = []
    falhar = False

    def __init__(self, host, porta, timeout=None, context=None):
        self.host, self.porta, self.timeout = host, porta, timeout
        self.ssl = isinstance(self, SMTPSSLFalso)
        self.starttls_feito = False
        self.login_feito = None
        self.mensagens = []
        SMTPFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        pass

    def has_extn(self, nome):
        return nome == "starttls"

    def starttls(self, context=None):
        self.starttls_feito = True

    def login(self, usuario, senha):
        self.login_feito = (usuario, senha)

    def send_message(self, msg):
        if SMTPFalso.falhar:
            raise smtplib.SMTPServerDisconnected("caiu")
        self.mensagens.append(msg)


class SMTPSSLFalso(SMTPFalso):
    pass


@pytest.fixture
def smtp(monkeypatch):
    SMTPFalso.instancias = []
    SMTPFalso.falhar = False
    monkeypatch.setattr(notifications.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", SMTPSSLFalso)
    monkeypatch.setenv("SMTP_HOST", "smtp.teste.local")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "remetente@teste.com")
    monkeypatch.setenv("SMTP_PASSWORD", "senha-app-falsa")
    monkeypatch.setenv("SMTP_FROM", "Global Training <remetente@teste.com>")
    return SMTPFalso


def _mensagens(smtp):
    return [m for inst in smtp.instancias for m in inst.mensagens]


def test_envia_link_de_definicao_com_assunto_link_e_html(smtp, tmp_path, monkeypatch):
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    link = "http://localhost:4200/definir-senha?token=abc123"
    notifications.send_password_setup_link("aluno@teste.com", link)
    [msg] = _mensagens(smtp)
    assert msg["To"] == "aluno@teste.com"
    assert msg["Subject"] == "Defina sua senha na Global Training"
    assert "remetente@teste.com" in msg["From"]
    texto = msg.get_body(preferencelist=("plain",)).get_content()
    corpo_html = msg.get_body(preferencelist=("html",)).get_content()
    assert link in texto and link in corpo_html
    # O outbox de desenvolvimento continua sendo gravado.
    assert link in (tmp_path / "outbox.jsonl").read_text(encoding="utf-8")


def test_starttls_e_login_na_587(smtp):
    notifications.send_password_changed_notice("aluno@teste.com", "http://localhost:4200/login")
    [inst] = smtp.instancias
    assert inst.porta == 587 and inst.starttls_feito and not inst.ssl
    assert inst.login_feito == ("remetente@teste.com", "senha-app-falsa")


def test_ssl_na_465(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    notifications.send_account_created_notice("aluno@teste.com", "http://localhost:4200/login")
    [inst] = smtp.instancias
    assert inst.ssl and inst.porta == 465 and len(inst.mensagens) == 1


def test_sem_smtp_host_nao_envia(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    notifications.send_password_setup_link("aluno@teste.com", "http://x/definir-senha?token=t")
    assert smtp.instancias == []


def test_falha_de_envio_nao_levanta_e_nao_vaza_senha(smtp, caplog):
    smtp.falhar = True
    notifications.send_password_setup_link("aluno@teste.com", "http://x/definir-senha?token=segredo-do-token")
    assert "senha-app-falsa" not in caplog.text and "segredo-do-token" not in caplog.text
    assert "SMTPServerDisconnected" in caplog.text


def test_fluxo_esqueci_senha_envia_email(smtp, banco, tmp_path, monkeypatch):
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    Database.add_user("aluna.u6@teste.com", "Aluna U6", get_password_hash("senha-u6-2026"), role="student")
    from app import app as fastapi_app

    with TestClient(fastapi_app) as client:
        r = client.post("/api/auth/password-reset/request", json={"email": "aluna.u6@teste.com"})
    assert r.status_code == 200
    [msg] = _mensagens(smtp)
    assert msg["To"] == "aluna.u6@teste.com" and msg["Subject"] == "Redefinição de senha"
    assert "/redefinir-senha?token=" in msg.get_body(preferencelist=("plain",)).get_content()


def test_fluxo_falha_smtp_nao_muda_resposta(smtp, banco):
    smtp.falhar = True
    Database.add_user("aluno2.u6@teste.com", "Aluno U6", get_password_hash("senha-u6-2026"), role="student")
    from app import app as fastapi_app

    with TestClient(fastapi_app) as client:
        r = client.post("/api/auth/password-reset/request", json={"email": "aluno2.u6@teste.com"})
    assert r.status_code == 200
