"""C1-C4 - Sala do curso (D96): processo enxuto da D84, caminho principal e segurança essencial."""

import json
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from core import conteudos
from core.security import create_access_token, get_password_hash
from db import Database

CURSO = "curso_sala"
VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
PDF = b"%PDF-1.4 apostila"
MATERIAL = "https://materiais.test/sala/apostila.pdf"


@pytest.fixture
def client(banco, catalogo_bot, tmp_path, monkeypatch):
    pasta = tmp_path / "courses"
    pasta.mkdir()
    (pasta / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": "Curso Sala", "price": 10.0,
        "materials": [{"title": "Apostila antiga", "url": MATERIAL, "type": "pdf"}],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", pasta)
    monkeypatch.setenv("CONTENTS_DIR", str(tmp_path / "conteudos"))
    from app import app as fastapi_app

    with TestClient(fastapi_app) as cliente:
        yield cliente


def _conta(perfil="student"):
    email = f"{perfil}.{uuid.uuid4().hex[:8]}@sala.test"
    user_id = Database.add_user(email, "Pessoa Sala", get_password_hash("senha-sala-123456"), role=perfil)
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return user_id, {"Authorization": f"Bearer {token}"}


def _matricula(user_id, status="active", curso=CURSO):
    conn = sqlite3.connect(Database.DB_PATH)
    cursor = conn.execute("INSERT INTO enrollments (user_id, course_id, status) VALUES (?, ?, ?)",
                          (user_id, curso, status))
    conn.commit()
    conn.close()
    return cursor.lastrowid


@pytest.fixture
def gestao(client):
    return _conta("admin")[1]


def _video(client, gestao, **extra):
    corpo = {"module": "Módulo 1", "title": "Aula 1", "kind": "video", "url": VIDEO, **extra}
    resposta = client.post(f"/api/admin/courses/{CURSO}/contents", json=corpo, headers=gestao)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["content"]


def _arquivo(client, gestao, nome="apostila.pdf", dados=PDF, curso=CURSO, **extra):
    return client.post(f"/api/admin/courses/{curso}/contents/file", headers=gestao, files={"file": (nome, dados)},
                       data={"module": "Módulo 1", "title": "Apostila", **extra})


def _aluno_ativo():
    user_id, headers = _conta()
    return _matricula(user_id), headers


def _sala(client, enrollment_id, headers):
    return client.get(f"/api/student/enrollments/{enrollment_id}/room", headers=headers)


@pytest.mark.parametrize("url, esperado", [
    (VIDEO, "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=10", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://vimeo.com/123456789/abcdef1234", "https://player.vimeo.com/video/123456789?h=abcdef1234"),
    ("https://youtube.com.golpe.example/watch?v=dQw4w9WgXcQ", None),
    ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", None),
    ("https://vimeo.com/abc", None),
])
def test_so_youtube_e_vimeo_viram_player(url, esperado):
    assert conteudos.embed_do_video(url) == esperado


def test_sala_mostra_materiais_antigos_modulos_e_extras(client, gestao):
    _video(client, gestao)
    _video(client, gestao, title="Bônus", is_extra=True)
    _video(client, gestao, title="Rascunho", published=False)
    enrollment_id, headers = _aluno_ativo()
    corpo = _sala(client, enrollment_id, headers).json()
    assert [m["title"] for m in corpo["modules"]] == ["Materiais", "Módulo 1"]
    assert corpo["modules"][0]["items"][0]["url"] == MATERIAL
    assert corpo["modules"][1]["items"][0]["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")
    assert [e["title"] for e in corpo["extras"]] == ["Bônus"]
    assert "Rascunho" not in json.dumps(corpo)
    assert corpo["next_key"] == MATERIAL


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_sem_matricula_ativa_nao_ve_nem_baixa(client, gestao, status):
    conteudo = _arquivo(client, gestao).json()["content"]
    user_id, headers = _conta()
    enrollment_id = _matricula(user_id, status)
    assert _sala(client, enrollment_id, headers).status_code == 409
    rota = f"/api/student/enrollments/{enrollment_id}/contents/{conteudo['id']}/file"
    assert client.get(rota, headers=headers).status_code == 409


def test_idor_na_sala_e_no_arquivo_devolve_o_mesmo_404(client, gestao):
    conteudo = _arquivo(client, gestao).json()["content"]
    enrollment_id, _ = _aluno_ativo()
    _, outro = _conta()
    alheia = _sala(client, enrollment_id, outro)
    inexistente = _sala(client, 999999, outro)
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()
    rota = f"/api/student/enrollments/{enrollment_id}/contents/{conteudo['id']}/file"
    assert client.get(rota, headers=outro).status_code == 404


def test_arquivo_exige_token_e_baixa_com_matricula_ativa(client, gestao):
    conteudo = _arquivo(client, gestao).json()["content"]
    assert "stored_name" not in conteudo
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/contents/{conteudo['id']}/file"
    assert client.get(rota).status_code == 401
    resposta = client.get(rota, headers=headers)
    assert resposta.status_code == 200 and resposta.content == PDF
    assert "attachment" in resposta.headers["content-disposition"]
    assert "stored_name" not in json.dumps(_sala(client, enrollment_id, headers).json())


def test_arquivo_de_outro_curso_e_oculto_devolvem_404(client, gestao):
    outro_curso = admin_routes.COURSES_DIR / "outro.json"
    outro_curso.write_text(json.dumps({"id": "outro", "name": "Outro", "price": 1}), encoding="utf-8")
    alheio = _arquivo(client, gestao, curso="outro").json()["content"]
    oculto = _arquivo(client, gestao, published="false").json()["content"]
    enrollment_id, headers = _aluno_ativo()
    for conteudo in (alheio, oculto):
        rota = f"/api/student/enrollments/{enrollment_id}/contents/{conteudo['id']}/file"
        assert client.get(rota, headers=headers).status_code == 404


def test_extras_nao_contam_para_o_certificado(client, gestao):
    aula = _video(client, gestao)
    extra = _video(client, gestao, title="Bônus", is_extra=True)
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/progress"
    certificado = f"/api/student/enrollments/{enrollment_id}/certificate.pdf"
    assert client.post(rota, json={"url": conteudos.chave(extra)}, headers=headers).json()["progress"]["done"] == 0
    assert client.get(certificado, headers=headers).status_code == 409
    client.post(rota, json={"url": MATERIAL}, headers=headers)
    progresso = client.post(rota, json={"url": conteudos.chave(aula)}, headers=headers).json()["progress"]
    assert progresso["certificate_available"] is True
    assert client.get(certificado, headers=headers).status_code == 200
    assert _sala(client, enrollment_id, headers).json()["next_key"] is None


def test_progresso_antigo_continua_valendo_na_sala(client, gestao):
    enrollment_id, headers = _aluno_ativo()
    client.post(f"/api/student/enrollments/{enrollment_id}/progress", json={"url": MATERIAL}, headers=headers)
    corpo = _sala(client, enrollment_id, headers).json()
    assert corpo["modules"][0]["items"][0]["done"] is True


def test_progresso_recusa_conteudo_oculto(client, gestao):
    oculto = _video(client, gestao, published=False)
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/progress"
    assert client.post(rota, json={"url": conteudos.chave(oculto)}, headers=headers).status_code == 422


@pytest.mark.parametrize("corpo, status", [
    ({"kind": "video", "url": "https://site.example/video"}, 422),
    ({"kind": "link", "url": "javascript:alert(1)"}, 422),
])
def test_gestao_nao_grava_endereco_invalido(client, gestao, corpo, status):
    dados = {"module": "M", "title": "T", **corpo}
    assert client.post(f"/api/admin/courses/{CURSO}/contents", json=dados, headers=gestao).status_code == status


@pytest.mark.parametrize("nome, dados, status", [
    ("virus.exe", b"MZ", 415),
    ("falso.pdf", b"MZ", 415),
    ("../../../evil.pdf", PDF, 201),
])
def test_upload_valida_tipo_e_nao_usa_o_nome_do_cliente(client, gestao, nome, dados, status):
    resposta = _arquivo(client, gestao, nome=nome, dados=dados)
    assert resposta.status_code == status
    if status == 201:
        conteudo = conteudos.obter(resposta.json()["content"]["id"])
        assert conteudo["file_name"] == "evil.pdf"
        assert conteudos.caminho_do_arquivo(conteudo).parent == conteudos.pasta_de_arquivos()


def test_upload_acima_do_limite(client, gestao, monkeypatch):
    monkeypatch.setattr(conteudos, "MAX_BYTES_ARQUIVO", 10)
    assert _arquivo(client, gestao).status_code == 413


@pytest.mark.parametrize("perfil", ["financial", "support", "student"])
def test_so_gestao_edita(client, perfil):
    _, headers = _conta(perfil)
    rota = f"/api/admin/courses/{CURSO}/contents"
    corpo = {"module": "M", "title": "T", "kind": "video", "url": VIDEO}
    assert client.get(rota, headers=headers).status_code == 403
    assert client.post(rota, json=corpo, headers=headers).status_code == 403


def test_sem_token_nao_edita(client):
    assert client.get(f"/api/admin/courses/{CURSO}/contents").status_code == 401


def test_curso_inexistente_e_id_invalido(client, gestao):
    assert client.get("/api/admin/courses/nao_existe/contents", headers=gestao).status_code == 404
    assert client.get("/api/admin/courses/..%2Fsegredo/contents", headers=gestao).status_code == 404


def test_reordenar_editar_excluir_e_auditar(client, gestao):
    primeiro = _video(client, gestao)
    segundo = _video(client, gestao, title="Aula 2")
    resposta = client.post(f"/api/admin/contents/{segundo['id']}/move", json={"direction": "up"}, headers=gestao)
    assert [c["title"] for c in resposta.json()["contents"]] == ["Aula 2", "Aula 1"]

    editado = client.put(f"/api/admin/contents/{primeiro['id']}", headers=gestao,
                         json={"module": "M2", "title": "Novo", "url": VIDEO, "published": False})
    assert editado.status_code == 200 and editado.json()["content"]["published"] is False

    arquivo = _arquivo(client, gestao).json()["content"]
    caminho = conteudos.caminho_do_arquivo(conteudos.obter(arquivo["id"]))
    assert client.delete(f"/api/admin/contents/{arquivo['id']}", headers=gestao).status_code == 200
    assert not caminho.exists()
    assert client.delete(f"/api/admin/contents/{arquivo['id']}", headers=gestao).status_code == 404

    acoes = {log["action"] for log in Database.list_audit_logs()}
    assert {"course_content.create", "course_content.update", "course_content.move",
            "course_content.delete"} <= acoes


def test_matricula_ativa_recebe_progresso_com_as_aulas(client, gestao):
    _video(client, gestao)
    user_id, headers = _conta()
    _matricula(user_id)
    item = client.get("/api/student/enrollments", headers=headers).json()["enrollments"][0]
    assert item["progress"]["total"] == 2
