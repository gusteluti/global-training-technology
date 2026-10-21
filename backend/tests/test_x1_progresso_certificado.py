"""X1 — progresso nos materiais e certificado de conclusão (D91, processo enxuto D84)."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from core.security import get_password_hash
from db import Database

SENHA = "senha-x1-2026-aluno"
M1, M2 = "https://materiais.test/x1/aula1.pdf", "https://materiais.test/x1/aula2.mp4"


@pytest.fixture
def client(banco, tmp_path, monkeypatch):
    pasta = tmp_path / "courses"
    pasta.mkdir()
    (pasta / "curso_x1.json").write_text(json.dumps({
        "id": "curso_x1", "name": "Curso de Gestão X1", "price": 100.0, "duration_hours": 20,
        "materials": [{"title": "Aula 1", "url": M1, "type": "pdf"}, {"title": "Aula 2", "url": M2, "type": "video"}],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", pasta)
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _aluno(client, email, status="active"):
    user_id = Database.add_user(email, "Joana Certificada", get_password_hash(SENHA), role="student")
    conn = sqlite3.connect(Database.DB_PATH)
    matricula = conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_x1', ?)",
                             (user_id, status)).lastrowid
    conn.commit()
    conn.close()
    token = client.post("/api/token", data={"username": email, "password": SENHA}).json()["access_token"]
    return matricula, {"Authorization": f"Bearer {token}"}


def _item(client, auth, matricula):
    itens = client.get("/api/student/enrollments", headers=auth).json()["enrollments"]
    return [i for i in itens if i["id"] == matricula][0]


def test_progresso_comeca_zerado(client):
    matricula, auth = _aluno(client, "a.x1@teste.com")
    p = _item(client, auth, matricula)["progress"]
    assert (p["done"], p["total"], p["percent"], p["certificate_available"]) == (0, 2, 0, False)


def test_marcar_e_desmarcar(client):
    matricula, auth = _aluno(client, "b.x1@teste.com")
    r = client.post(f"/api/student/enrollments/{matricula}/progress", json={"url": M1}, headers=auth)
    assert r.status_code == 200 and r.json()["progress"]["percent"] == 50
    client.post(f"/api/student/enrollments/{matricula}/progress", json={"url": M1, "done": False}, headers=auth)
    assert _item(client, auth, matricula)["progress"]["done"] == 0


def test_material_de_fora_do_curso_422(client):
    matricula, auth = _aluno(client, "c.x1@teste.com")
    r = client.post(f"/api/student/enrollments/{matricula}/progress", json={"url": "https://outro/x"}, headers=auth)
    assert r.status_code == 422


def test_matricula_alheia_404_e_pendente_409(client):
    alheia, _ = _aluno(client, "dono.x1@teste.com")
    pendente, auth = _aluno(client, "d.x1@teste.com", status="pending")
    r = client.post(f"/api/student/enrollments/{alheia}/progress", json={"url": M1}, headers=auth)
    assert r.status_code == 404 and r.json() == {"detail": "Matrícula não encontrada."}
    assert client.get(f"/api/student/enrollments/{alheia}/certificate.pdf", headers=auth).status_code == 404
    r = client.post(f"/api/student/enrollments/{pendente}/progress", json={"url": M1}, headers=auth)
    assert r.status_code == 409
    assert "progress" not in _item(client, auth, pendente) and "materials" not in _item(client, auth, pendente)


def test_certificado_so_com_tudo_concluido(client):
    matricula, auth = _aluno(client, "e.x1@teste.com")
    url = f"/api/student/enrollments/{matricula}/certificate.pdf"
    r = client.get(url, headers=auth)
    assert r.status_code == 409 and r.json() == {"detail": "Conclua todos os materiais para emitir o certificado."}
    for m in (M1, M2):
        client.post(f"/api/student/enrollments/{matricula}/progress", json={"url": m}, headers=auth)
    assert _item(client, auth, matricula)["progress"]["certificate_available"] is True
    r = client.get(url, headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and b"Joana Certificada" in r.content and b"20 horas" in r.content


def test_sem_token_401(client):
    assert client.post("/api/student/enrollments/1/progress", json={"url": M1}).status_code == 401
