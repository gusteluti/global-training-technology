"""X1 — progresso nos materiais e certificado de conclusão (D91, processo enxuto D84)."""

import io
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

import admin.routes as admin_routes
from core import progresso
from core.fuso import dia_sao_paulo
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
    assert r.content.startswith(b"%PDF-") and "Joana Certificada" in _texto_do_pdf(r.content)


# --- Layout do Canva (backend/assets/certificado): fundo, nome em script, frases com curso e datas ----------------

def _texto_do_pdf(conteudo: bytes) -> str:
    """Texto extraído do PDF, com os espaços normalizados (o extrator pode quebrar a linha em pedaços)."""
    paginas = PdfReader(io.BytesIO(conteudo)).pages
    return " ".join(" ".join(p.extract_text() or "" for p in paginas).split())


def _concluir(client, auth, matricula):
    for m in (M1, M2):
        client.post(f"/api/student/enrollments/{matricula}/progress", json={"url": m}, headers=auth)
    r = client.get(f"/api/student/enrollments/{matricula}/certificate.pdf", headers=auth)
    assert r.status_code == 200
    return r.content


def test_certificado_segue_o_layout(client):
    matricula, auth = _aluno(client, "f.x1@teste.com")
    # 01:00 UTC de 02/03 ainda é 01/03 em São Paulo: a data de início sai no horário de SP (F2).
    conn = sqlite3.connect(Database.DB_PATH)
    conn.execute("UPDATE enrollments SET enrolled_at = '2026-03-02 01:00:00' WHERE id = ?", (matricula,))
    conn.commit()
    conn.close()
    conteudo = _concluir(client, auth, matricula)
    hoje = dia_sao_paulo(datetime.now(timezone.utc)).strftime("%d/%m/%Y")
    texto = _texto_do_pdf(conteudo)
    assert "Joana Certificada" in texto
    # Carga horária (duration_hours do curso) entra na frase, a pedido do PM depois do layout.
    assert (f"CONCLUIU COM ÊXITO O CURSO CURSO DE GESTÃO X1, COM CARGA HORÁRIA DE 20 HORAS, "
            f"ENTRE 01/03/2026 E {hoje}.") in texto
    assert f"EMITIDO EM {hoje} PELA GLOBAL TRAINING TECHNOLOGY." in texto
    assert f"Código de validação: {progresso.codigo_validacao(matricula, _id_do_aluno(matricula))}" in texto
    assert "{" not in texto  # nenhum marcador do modelo sobra no PDF

    pagina = PdfReader(io.BytesIO(conteudo)).pages[0]
    largura, altura = float(pagina.mediabox.width), float(pagina.mediabox.height)
    assert (round(largura), round(altura)) == (842, 595)  # A4 deitado, como o modelo
    assert len(pagina.images) == 1  # a arte do Canva vai de fundo


def test_curso_de_nome_longo_quebra_em_linhas_sem_perder_texto():
    nome_curso = "Formação Completa em Gestão de Projetos Ágeis, Liderança de Equipes e Indicadores de Desempenho"
    conteudo = progresso.gerar_certificado_pdf(
        "Maria Aparecida dos Santos de Oliveira Albuquerque", nome_curso,
        "2026-01-10 12:00:00", "2026-02-20 12:00:00", "ABC123DEF456",
    )
    leitor = PdfReader(io.BytesIO(conteudo))
    assert len(leitor.pages) == 1
    texto = _texto_do_pdf(conteudo)
    assert "Maria Aparecida dos Santos de Oliveira Albuquerque" in texto
    # Curso sem carga horária cadastrada: a frase sai sem o trecho, em vez de "0 HORAS" ou "NONE HORAS".
    assert f"CONCLUIU COM ÊXITO O CURSO {nome_curso.upper()} ENTRE 10/01/2026 E 20/02/2026." in texto


@pytest.mark.parametrize("horas, trecho", [(1, ", COM CARGA HORÁRIA DE 1 HORA,"), (40, ", COM CARGA HORÁRIA DE 40 HORAS,")])
def test_carga_horaria_no_singular_e_no_plural(horas, trecho):
    conteudo = progresso.gerar_certificado_pdf("Ana", "Excel", "2026-01-10 12:00:00", "2026-02-20 12:00:00",
                                               "ABC123DEF456", horas=horas)
    assert f"O CURSO EXCEL{trecho} ENTRE" in _texto_do_pdf(conteudo)


def _id_do_aluno(matricula):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        return conn.execute("SELECT user_id FROM enrollments WHERE id = ?", (matricula,)).fetchone()[0]
    finally:
        conn.close()


def test_sem_token_401(client):
    assert client.post("/api/student/enrollments/1/progress", json={"url": M1}).status_code == 401
