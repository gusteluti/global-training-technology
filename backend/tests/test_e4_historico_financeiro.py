"""E4 — Histórico financeiro e recibos JSON (RF22, item 1.1).

Contrato:
  - GET /api/student/payments lista somente pagamentos das matrículas do aluno
    autenticado, incluindo curso, valor, status Mercado Pago e datas.
  - GET /api/student/payments/{id}/receipt devolve o recibo JSON do pagamento
    do próprio aluno. Um pagamento de terceiro é indistinguível de inexistente.
  - A área do aluno aceita apenas JWT de student; funcionário recebe 403 e
    ausência/forja de token recebe 401.
"""

import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from core.security import get_password_hash
from db import Database


SENHA = "senha-aluno-e4-2026"
ROTA_PAGAMENTOS = "/api/student/payments"


@pytest.fixture
def client(banco):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _conta(email, role="student"):
    user_id = Database.add_user(email, f"Usuário {role}", get_password_hash(SENHA), role=role)
    assert user_id is not None
    return user_id


def _pagamento(user_id, course_id, amount, status, transaction_id=None):
    ref = f"{course_id}:e4:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    payment_id = Database.record_payment(enrollment_id, amount, "mercado_pago")
    Database.update_payment_status(payment_id, status, transaction_id)
    return payment_id, enrollment_id


def _login(client, email):
    resposta = client.post("/api/token", data={"username": email, "password": SENHA})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _lista(client, token):
    resposta = client.get(ROTA_PAGAMENTOS, headers=_auth(token))
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert isinstance(corpo.get("payments"), list), corpo
    return resposta, corpo["payments"]


def test_t1_historico_lista_apenas_pagamentos_do_proprio_aluno_com_status_e_recibo(client):
    alice = _conta("alice.e4@teste.com")
    bob = _conta("bob.e4@teste.com")
    aprovado, matricula_aprovada = _pagamento(alice, "curso-python", 199.90, "approved", "mp-approved-1")
    pendente, matricula_pendente = _pagamento(alice, "curso-angular", 99.50, "pending")
    _pagamento(bob, "curso-secreto", 777.00, "approved", "mp-bob-secret")

    resposta, pagamentos = _lista(client, _login(client, "alice.e4@teste.com"))

    assert {p["id"] for p in pagamentos} == {aprovado, pendente}
    assert "curso-secreto" not in resposta.text
    assert "mp-bob-secret" not in resposta.text
    por_id = {p["id"]: p for p in pagamentos}
    for payment_id, enrollment_id, course_id, amount, status in (
        (aprovado, matricula_aprovada, "curso-python", 199.90, "approved"),
        (pendente, matricula_pendente, "curso-angular", 99.50, "pending"),
    ):
        item = por_id[payment_id]
        assert item["enrollment_id"] == enrollment_id
        assert item["course_id"] == course_id
        assert item["amount"] == amount
        assert item["status"] == status
        assert item["payment_method"] == "mercado_pago"
        assert item["created_at"]
        assert item["updated_at"]
        assert item["receipt_url"] == f"{ROTA_PAGAMENTOS}/{payment_id}/receipt"


def test_t2_recibo_json_do_proprio_pagamento_contem_dados_da_compra(client):
    alice = _conta("recibo.e4@teste.com")
    payment_id, enrollment_id = _pagamento(alice, "curso-recibo", 250.00, "approved", "mp-recibo-123")
    token = _login(client, "recibo.e4@teste.com")

    resposta = client.get(f"{ROTA_PAGAMENTOS}/{payment_id}/receipt", headers=_auth(token))

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    recibo = corpo.get("receipt", corpo)
    assert recibo["payment_id"] == payment_id
    assert recibo["enrollment_id"] == enrollment_id
    assert recibo["course_id"] == "curso-recibo"
    assert recibo["amount"] == 250.00
    assert recibo["status"] == "approved"
    assert recibo["payment_method"] == "mercado_pago"
    assert recibo["transaction_id"] == "mp-recibo-123"
    assert recibo["issued_at"]


def test_t3_idor_recibo_alheio_e_inexistente_devolvem_o_mesmo_404_sem_vazamento(client):
    alice = _conta("idor.a.e4@teste.com")
    bob = _conta("idor.b.e4@teste.com")
    alheio, _ = _pagamento(bob, "curso-privado", 321.00, "approved", "mp-privado")
    token = _login(client, "idor.a.e4@teste.com")

    de_terceiro = client.get(f"{ROTA_PAGAMENTOS}/{alheio}/receipt", headers=_auth(token))
    inexistente = client.get(f"{ROTA_PAGAMENTOS}/999999/receipt", headers=_auth(token))

    assert de_terceiro.status_code == 404
    assert de_terceiro.status_code == inexistente.status_code
    assert de_terceiro.json() == inexistente.json()
    assert "curso-privado" not in de_terceiro.text
    assert "mp-privado" not in de_terceiro.text


@pytest.mark.parametrize("role", ["admin", "financial", "support"])
def test_t4_funcionario_nao_acessa_historico_financeiro_do_aluno(client, role):
    _conta(f"{role}.e4@teste.com", role=role)
    token = _login(client, f"{role}.e4@teste.com")

    resposta = client.get(ROTA_PAGAMENTOS, headers=_auth(token))

    assert resposta.status_code == 403


def test_t5_sem_token_ou_token_forjado_recebe_401(client):
    sem_token = client.get(ROTA_PAGAMENTOS)
    token_forjado = jose_jwt.encode(
        {"user_id": 999, "email": "forjado@teste.com"}, "segredo-errado", algorithm="HS256"
    )
    forjado = client.get(ROTA_PAGAMENTOS, headers=_auth(token_forjado))

    assert sem_token.status_code == 401
    assert forjado.status_code == 401
