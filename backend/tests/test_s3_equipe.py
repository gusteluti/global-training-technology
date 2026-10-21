"""S3 — gestão da equipe (D85, processo enxuto D84).

Cobre o caminho principal (listar, convidar com link de senha, trocar perfil, desativar e reativar) e as travas
(própria conta, última Gestão ativa, e-mail em uso, 404 para quem não é funcionário), além de RBAC e auditoria.
"""

import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.security import create_admin_token, get_password_hash, Role
from db import Database

SENHA = "senha-equipe-s3-2026"
ROTA = "/api/admin/staff"


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    caminho = tmp_path / "outbox.jsonl"
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(caminho))
    return caminho


@pytest.fixture
def client(banco, outbox):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(email, nome, perfil):
    user_id = Database.add_user(email, nome, get_password_hash(SENHA), role=perfil)
    assert user_id
    return SimpleNamespace(id=user_id, email=email)


def _login(client, email, senha=SENHA):
    return client.post("/api/token", data={"username": email, "password": senha})


def _token(client, email):
    r = _login(client, email)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def equipe(client):
    contas = SimpleNamespace(
        gestao=_conta("gestao.s3@teste.com", "Gestora S3", "admin"),
        fin=_conta("fin.s3@teste.com", "Financeira S3", "financial"),
        sup=_conta("sup.s3@teste.com", "Suporte S3", "support"),
        aluno=_conta("aluno.s3@teste.com", "Aluno S3", "student"),
    )
    contas.tk_gestao = _token(client, contas.gestao.email)
    return contas


def _eventos(acao):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        return conn.execute("SELECT entity_id FROM audit_logs WHERE action = ?", (acao,)).fetchall()
    finally:
        conn.close()


def test_lista_so_funcionarios(client, equipe):
    r = client.get(ROTA, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 200
    emails = {f["email"] for f in r.json()["staff"]}
    # O startup pode criar contas de funcionário pelo ambiente; o que importa é ter a equipe e nenhum aluno.
    assert {"gestao.s3@teste.com", "fin.s3@teste.com", "sup.s3@teste.com"} <= emails
    assert equipe.aluno.email not in emails
    item = r.json()["staff"][0]
    assert set(item) == {"id", "name", "email", "role", "is_active", "created_at"}
    assert "password_hash" not in r.text


@pytest.mark.parametrize("perfil", ["fin", "sup", "aluno"])
def test_rbac_so_gestao(client, equipe, perfil):
    token = _token(client, getattr(equipe, perfil).email)
    assert client.get(ROTA, headers=_auth(token)).status_code == 403
    r = client.post(ROTA, json={"email": "x@teste.com", "name": "X", "role": "support"}, headers=_auth(token))
    assert r.status_code == 403
    assert client.post(f"{ROTA}/{equipe.sup.id}/deactivate", headers=_auth(token)).status_code == 403


def test_sem_token_401(client, equipe):
    assert client.get(ROTA).status_code == 401
    assert client.get(ROTA, headers=_auth("forjado")).status_code == 401


def test_convite_cria_conta_sem_senha_e_envia_link(client, equipe, outbox):
    r = client.post(ROTA, json={"email": "novo.s3@teste.com", "name": "Novo Suporte", "role": "support",
                               "user_id": 1}, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 200, r.text
    conta = Database.get_user_by_email("novo.s3@teste.com")
    assert conta["role"] == "support" and not conta.get("password_hash")
    linhas = [json.loads(linha) for linha in outbox.read_text(encoding="utf-8").splitlines()]
    link = [linha for linha in linhas if linha["email"] == "novo.s3@teste.com"][-1]["link"]
    token = link.split("token=")[1]
    assert client.post("/api/auth/password-setup", json={"token": token, "password": SENHA}).status_code == 200
    assert _login(client, "novo.s3@teste.com").status_code == 200
    assert len(_eventos("staff.create")) == 1


def test_convite_email_em_uso_409(client, equipe):
    r = client.post(ROTA, json={"email": equipe.aluno.email, "name": "X", "role": "support"},
                    headers=_auth(equipe.tk_gestao))
    assert r.status_code == 409 and r.json() == {"detail": "Já existe uma conta com este e-mail."}


def test_convite_perfil_invalido_422(client, equipe):
    r = client.post(ROTA, json={"email": "a@teste.com", "name": "X", "role": "student"}, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 422


def test_trocar_perfil_derruba_token_antigo(client, equipe):
    tk_sup = _token(client, equipe.sup.email)
    r = client.put(f"{ROTA}/{equipe.sup.id}", json={"role": "financial"}, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 200 and r.json()["staff"]["role"] == "financial"
    assert client.get("/api/dashboard/alunos", headers=_auth(tk_sup)).status_code == 401
    tk_novo = _token(client, equipe.sup.email)
    assert client.get("/api/dashboard/financeiro", headers=_auth(tk_novo)).status_code == 200
    assert len(_eventos("staff.update")) == 1


def test_desativar_e_reativar(client, equipe):
    tk_fin = _token(client, equipe.fin.email)
    assert client.post(f"{ROTA}/{equipe.fin.id}/deactivate", headers=_auth(equipe.tk_gestao)).status_code == 200
    assert client.get("/api/dashboard/financeiro", headers=_auth(tk_fin)).status_code == 401
    r = _login(client, equipe.fin.email)
    assert r.status_code == 403 and r.json() == {"detail": "Sua conta está desativada. Fale com o suporte."}
    assert client.post(f"{ROTA}/{equipe.fin.id}/reactivate", headers=_auth(equipe.tk_gestao)).status_code == 200
    assert _login(client, equipe.fin.email).status_code == 200
    assert len(_eventos("staff.deactivate")) == 1 and len(_eventos("staff.reactivate")) == 1


def test_propria_conta_409(client, equipe):
    msg = {"detail": "Você não pode desativar ou trocar o perfil da sua própria conta."}
    r = client.post(f"{ROTA}/{equipe.gestao.id}/deactivate", headers=_auth(equipe.tk_gestao))
    assert r.status_code == 409 and r.json() == msg
    r = client.put(f"{ROTA}/{equipe.gestao.id}", json={"role": "support"}, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 409 and r.json() == msg
    # trocar o próprio nome pode
    r = client.put(f"{ROTA}/{equipe.gestao.id}", json={"name": "Gestora Renomeada"}, headers=_auth(equipe.tk_gestao))
    assert r.status_code == 200


def test_ultima_gestao_ativa_409(client, equipe):
    # Pelo token legado (sem conta), a única Gestão ativa não pode sair. Outras Gestões criadas pelo startup
    # são desativadas antes, para o cenário ter exatamente uma.
    conn = sqlite3.connect(Database.DB_PATH)
    conn.execute("UPDATE users SET is_active = 0 WHERE role = 'admin' AND id != ?", (equipe.gestao.id,))
    conn.commit()
    conn.close()
    legado = create_admin_token(Role.ADMIN)
    r = client.post(f"{ROTA}/{equipe.gestao.id}/deactivate", headers=_auth(legado))
    assert r.status_code == 409 and r.json() == {"detail": "É preciso manter pelo menos uma conta de Gestão ativa."}
    # Com outra Gestão ativa, pode.
    outra = _conta("gestao2.s3@teste.com", "Gestor 2", "admin")
    assert client.put(f"{ROTA}/{equipe.gestao.id}", json={"role": "support"}, headers=_auth(legado)).status_code == 200
    assert outra.id


@pytest.mark.parametrize("alvo", ["aluno", "inexistente", "enorme"])
def test_404_quem_nao_e_funcionario(client, equipe, alvo):
    user_id = {"aluno": equipe.aluno.id, "inexistente": 99999, "enorme": 2 ** 63}[alvo]
    r = client.post(f"{ROTA}/{user_id}/deactivate", headers=_auth(equipe.tk_gestao))
    assert r.status_code == 404 and r.json() == {"detail": "Funcionário não encontrado."}
    assert Database.get_user_by_email(equipe.aluno.email)["is_active"]
