"""E1 - Referência externa única por compra (decisão D10 do registro do orquestrador).

Duas compras do mesmo curso, pelo mesmo e-mail, no mesmo instante (relógio congelado)
devem gerar external_reference distintas. Cada matrícula tem a sua, e um webhook só
atualiza a matrícula cuja referência ele carrega.

Comportamento implementado antes deste teste (commit 50a1164), sem red prévio: o
teste foi escrito depois e passa com a implementação atual.
"""

import json
import sqlite3
from datetime import datetime as RealDatetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apoio_mercado_pago import corpo_pagamento_mp, id_de_pagamento, post_webhook
from db import Database

import admin.routes as admin_routes


INSTANTE_CONGELADO = RealDatetime(2026, 10, 5, 12, 0, 0)


@pytest.fixture
def curso_teste(tmp_path, monkeypatch):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / "curso_teste.json").write_text(json.dumps({
        "id": "curso_teste",
        "name": "Curso Teste",
        "description": "Curso para teste de referência única",
        "price": 100.0,
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return "curso_teste"


@pytest.fixture
def client(banco, curso_teste):
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


def _checkout(client, email, name="Aluno Teste"):
    resposta = MagicMock(status_code=201)
    resposta.json.return_value = {"id": "pref-1", "init_point": "https://mp.test/checkout"}
    with patch("payments.routes.requests.post", return_value=resposta), \
         patch("payments.routes.datetime") as relogio:
        relogio.utcnow.return_value = INSTANTE_CONGELADO
        return client.post("/api/payments/create-checkout", json={
            "course_id": "curso_teste",
            "payer": {"name": name, "email": email},
        })


def _webhook(client, status, ref, pagamento_id=None):
    # E9 (D48): webhook assinado, id numérico por referência e valor/moeda do curso (100.0 BRL).
    pagamento_id = pagamento_id or id_de_pagamento(ref)
    resposta = MagicMock(status_code=200)
    resposta.json.return_value = corpo_pagamento_mp(status, ref, 100.0, pagamento_id)
    with patch("payments.routes.requests.get", return_value=resposta):
        return post_webhook(client, pagamento_id)


def _matriculas_do_email(email):
    return _sql(
        """SELECT e.id, e.external_reference, e.status, e.course_id
           FROM enrollments e JOIN users u ON u.id = e.user_id
           WHERE u.email = ? ORDER BY e.id""",
        (email,),
    )


def _status_pagamentos(enrollment_id):
    return [r["status"] for r in _sql(
        "SELECT status FROM payments WHERE enrollment_id = ? ORDER BY id", (enrollment_id,)
    )]


def test_d10_duas_compras_mesmo_curso_mesmo_email_mesmo_instante_geram_referencias_distintas(client):
    email = "compra.dupla@teste.com"
    r1 = _checkout(client, email)
    r2 = _checkout(client, email)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    ref1 = r1.json()["external_reference"]
    ref2 = r2.json()["external_reference"]
    assert ref1 != ref2


def test_d10_cada_matricula_tem_a_propria_referencia(client):
    email = "compra.matriculas@teste.com"
    ref1 = _checkout(client, email).json()["external_reference"]
    ref2 = _checkout(client, email).json()["external_reference"]

    matriculas = _matriculas_do_email(email)
    assert len(matriculas) == 2
    assert {m["external_reference"] for m in matriculas} == {ref1, ref2}
    assert all(m["course_id"] == "curso_teste" for m in matriculas)


def test_d10_webhook_atualiza_somente_a_matricula_da_referencia(client):
    email = "compra.webhook@teste.com"
    ref1 = _checkout(client, email).json()["external_reference"]
    ref2 = _checkout(client, email).json()["external_reference"]
    m1, m2 = _matriculas_do_email(email)
    assert m1["external_reference"] == ref1 and m2["external_reference"] == ref2

    pagamentos_m2_antes = _status_pagamentos(m2["id"])

    r_hook = _webhook(client, "approved", ref1)
    assert r_hook.status_code == 200, r_hook.text

    m1_depois, m2_depois = _matriculas_do_email(email)
    assert m1_depois["status"] == "active"
    assert m2_depois["status"] == "pending"
    assert _status_pagamentos(m2["id"]) == pagamentos_m2_antes
    assert "approved" in _status_pagamentos(m1["id"])
    assert "approved" not in _status_pagamentos(m2["id"])
