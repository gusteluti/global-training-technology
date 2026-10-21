"""U7 — LGPD (D89, processo enxuto D84): aceite dos termos, exportação e exclusão dos dados pelo aluno."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from core.security import get_password_hash
from db import Database

SENHA = "senha-lgpd-u7-2026"


@pytest.fixture
def client(banco):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _sql(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _exec(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _aluno(client, email="aluna.u7@teste.com"):
    user_id = Database.add_user(email, "Aluna U7", get_password_hash(SENHA), role="student")
    token = client.post("/api/token", data={"username": email, "password": SENHA}).json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def _com_dados(user_id):
    _exec("INSERT INTO user_profiles (user_id, phone) VALUES (?, '11987654321')", (user_id,))
    matricula = _exec("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_u7', 'active')", (user_id,))
    _exec("INSERT INTO payments (enrollment_id, amount, payment_method, status) VALUES (?, 99.9, 'mock', 'approved')",
          (matricula,))
    _exec("INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', 'meu cpf e 123')", (user_id,))
    return matricula


def test_cadastro_com_aceite_grava_data_e_versao(client):
    r = client.post("/api/auth/register", json={"name": "Nova", "email": "nova.u7@teste.com", "password": SENHA,
                                                "accept_terms": True})
    assert r.status_code == 200
    [linha] = _sql("SELECT terms_accepted_at, terms_version FROM users WHERE email = 'nova.u7@teste.com'")
    assert linha["terms_accepted_at"] and linha["terms_version"] == "2026-10"


def test_cadastro_sem_campo_continua_aceito(client):
    r = client.post("/api/auth/register", json={"name": "Antiga", "email": "antiga.u7@teste.com", "password": SENHA})
    assert r.status_code == 200
    [linha] = _sql("SELECT terms_accepted_at FROM users WHERE email = 'antiga.u7@teste.com'")
    assert linha["terms_accepted_at"] is None


def test_exportar_traz_todos_os_dados_do_dono(client):
    user_id, auth = _aluno(client)
    _com_dados(user_id)
    outro_id, _ = _aluno(client, "outro.u7@teste.com")
    _exec("INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', 'segredo do outro')", (outro_id,))
    r = client.get("/api/student/me/export", headers=auth)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    dados = r.json()
    assert dados["conta"]["email"] == "aluna.u7@teste.com" and dados["conta"]["phone"] == "11987654321"
    assert len(dados["matriculas"]) == 1 and len(dados["pagamentos"]) == 1
    assert dados["conversas_do_chat"][0]["content"] == "meu cpf e 123"
    assert "segredo do outro" not in r.text and "password" not in r.text
    assert _sql("SELECT 1 FROM audit_logs WHERE action = 'student.data_export'")


def test_exportar_ignora_user_id_do_cliente(client):
    _, auth = _aluno(client)
    outro_id, _ = _aluno(client, "outro2.u7@teste.com")
    r = client.get(f"/api/student/me/export?user_id={outro_id}", headers=auth)
    assert r.json()["conta"]["email"] == "aluna.u7@teste.com"


def test_excluir_com_senha_errada_nao_muda_nada(client):
    user_id, auth = _aluno(client)
    r = client.post("/api/student/me/delete", json={"password": "errada-123456"}, headers=auth)
    assert r.status_code == 400 and r.json() == {"detail": "Senha incorreta."}
    assert _sql("SELECT email FROM users WHERE id = ?", (user_id,))[0]["email"] == "aluna.u7@teste.com"


def test_excluir_anonimiza_e_mantem_registro_financeiro(client):
    user_id, auth = _aluno(client)
    matricula = _com_dados(user_id)
    r = client.post("/api/student/me/delete", json={"password": SENHA}, headers=auth)
    assert r.status_code == 200
    [conta] = _sql("SELECT name, email, password_hash, is_active FROM users WHERE id = ?", (user_id,))
    assert conta["name"] == "Conta excluída" and conta["email"].endswith("@anonimo.invalid")
    assert conta["password_hash"] is None and conta["is_active"] == 0
    assert _sql("SELECT 1 FROM user_profiles WHERE user_id = ?", (user_id,)) == []
    assert _sql("SELECT 1 FROM chat_messages WHERE user_id = ?", (user_id,)) == []
    assert _sql("SELECT status FROM enrollments WHERE id = ?", (matricula,))[0]["status"] == "active"
    assert len(_sql("SELECT 1 FROM payments WHERE enrollment_id = ?", (matricula,))) == 1
    eventos = _sql("SELECT detail, actor_email FROM audit_logs WHERE action = 'student.data_delete'")
    assert len(eventos) == 1 and "aluna.u7" not in json.dumps(eventos)


def test_depois_de_excluir_token_e_login_nao_valem(client):
    _, auth = _aluno(client)
    client.post("/api/student/me/delete", json={"password": SENHA}, headers=auth)
    assert client.get("/api/student/me", headers=auth).status_code == 401
    r = client.post("/api/token", data={"username": "aluna.u7@teste.com", "password": SENHA})
    assert r.status_code == 400
    # O e-mail fica livre para um cadastro novo.
    r = client.post("/api/auth/register", json={"name": "Volta", "email": "aluna.u7@teste.com", "password": SENHA})
    assert r.status_code == 200 and len(_sql("SELECT 1 FROM users WHERE email = 'aluna.u7@teste.com'")) == 1


@pytest.mark.parametrize("rota,metodo", [("/api/student/me/export", "get"), ("/api/student/me/delete", "post")])
def test_rbac(client, rota, metodo):
    assert getattr(client, metodo)(rota).status_code == 401
    Database.add_user("staff.u7@teste.com", "Staff", get_password_hash(SENHA), role="admin")
    token = client.post("/api/token", data={"username": "staff.u7@teste.com", "password": SENHA}).json()["access_token"]
    kwargs = {"json": {"password": SENHA}} if metodo == "post" else {}
    r = getattr(client, metodo)(rota, headers={"Authorization": f"Bearer {token}"}, **kwargs)
    assert r.status_code == 403
