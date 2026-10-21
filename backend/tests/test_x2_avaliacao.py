"""X2 — avaliação do curso pelo aluno e média no dashboard de cursos (D92, processo enxuto D84)."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from core.security import get_password_hash
from db import Database

SENHA = "senha-x2-2026-aluno"


@pytest.fixture
def client(banco, tmp_path, monkeypatch):
    pasta = tmp_path / "courses"
    pasta.mkdir()
    (pasta / "curso_x2.json").write_text(json.dumps({"id": "curso_x2", "name": "Curso X2", "price": 10.0}),
                                         encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", pasta)
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(client, email, perfil="student", status="active"):
    user_id = Database.add_user(email, "Pessoa X2", get_password_hash(SENHA), role=perfil)
    matricula = None
    if perfil == "student":
        conn = sqlite3.connect(Database.DB_PATH)
        matricula = conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_x2', ?)",
                                 (user_id, status)).lastrowid
        conn.commit()
        conn.close()
    token = client.post("/api/token", data={"username": email, "password": SENHA}).json()["access_token"]
    return matricula, {"Authorization": f"Bearer {token}"}


def test_avaliar_e_atualizar(client):
    matricula, auth = _conta(client, "a.x2@teste.com")
    r = client.post(f"/api/student/enrollments/{matricula}/review", json={"rating": 4, "comment": " Muito bom "},
                    headers=auth)
    assert r.status_code == 200 and r.json()["review"]["comment"] == "Muito bom"
    client.post(f"/api/student/enrollments/{matricula}/review", json={"rating": 5}, headers=auth)
    item = client.get("/api/student/enrollments", headers=auth).json()["enrollments"][0]
    assert item["review"]["rating"] == 5


@pytest.mark.parametrize("nota", [0, 6, -1, True])
def test_nota_fora_do_intervalo_422(client, nota):
    matricula, auth = _conta(client, f"b{str(nota)}.x2@teste.com")
    r = client.post(f"/api/student/enrollments/{matricula}/review", json={"rating": nota}, headers=auth)
    assert r.status_code == 422


def test_alheia_404_e_pendente_409(client):
    alheia, _ = _conta(client, "dono.x2@teste.com")
    pendente, auth = _conta(client, "c.x2@teste.com", status="pending")
    r = client.post(f"/api/student/enrollments/{alheia}/review", json={"rating": 5}, headers=auth)
    assert r.status_code == 404 and r.json() == {"detail": "Matrícula não encontrada."}
    r = client.post(f"/api/student/enrollments/{pendente}/review", json={"rating": 5}, headers=auth)
    assert r.status_code == 409


def test_media_no_dashboard(client):
    for i, nota in enumerate((5, 4)):
        matricula, auth = _conta(client, f"d{i}.x2@teste.com")
        client.post(f"/api/student/enrollments/{matricula}/review", json={"rating": nota}, headers=auth)
    _, staff = _conta(client, "suporte.x2@teste.com", perfil="support")
    curso = [c for c in client.get("/api/dashboard/cursos", headers=staff).json()["courses"] if c["id"] == "curso_x2"][0]
    assert curso["rating"] == {"average": 4.5, "count": 2}
