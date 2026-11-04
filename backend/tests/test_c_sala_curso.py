"""C1-C4 - Sala do curso (D103): processo enxuto da D84, caminho principal e segurança essencial."""

import io
import json
import sqlite3
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from agents import rag
from core import conteudos
from core.receipt_pdf import gerar_pdf_de_linhas
from core import progresso as progresso_core
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
    ("www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://player.vimeo.com/video/123456789", "https://player.vimeo.com/video/123456789"),
    ("https://www.youtube.com/playlist?list=PLabc", None),
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
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/progress"
    certificado = f"/api/student/enrollments/{enrollment_id}/certificate.pdf"
    extra_link = client.post(f"/api/admin/courses/{CURSO}/contents", headers=gestao, json={
        "module": "M", "title": "Link", "kind": "link", "url": "https://materiais.test/l", "is_extra": True}).json()["content"]
    assert client.post(rota, json={"url": conteudos.chave(extra_link)}, headers=headers).json()["progress"]["done"] == 0
    assert client.get(certificado, headers=headers).status_code == 409
    client.post(rota, json={"url": MATERIAL}, headers=headers)
    progresso_core.marcar(enrollment_id, conteudos.chave(aula), True)
    progresso = client.get("/api/student/enrollments", headers=headers).json()["enrollments"][0]["progress"]
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


def test_playlist_recebe_mensagem_propria(client, gestao):
    corpo = {"module": "M", "title": "T", "kind": "video", "url": "https://www.youtube.com/playlist?list=PLabc"}
    resposta = client.post(f"/api/admin/courses/{CURSO}/contents", json=corpo, headers=gestao)
    assert resposta.status_code == 422 and "playlist" in resposta.json()["detail"]


def test_extra_nao_precisa_de_modulo_e_aula_precisa(client, gestao):
    rota = f"/api/admin/courses/{CURSO}/contents"
    extra = {"title": "Bônus", "kind": "link", "url": "https://materiais.test/b", "is_extra": True}
    assert client.post(rota, json=extra, headers=gestao).json()["content"]["module"] == "Extras"
    aula = {"title": "Aula", "kind": "video", "url": VIDEO}
    assert client.post(rota, json=aula, headers=gestao).status_code == 422


def test_trocar_arquivo_mantem_progresso_e_apaga_o_antigo(client, gestao):
    conteudo = _arquivo(client, gestao).json()["content"]
    antigo = conteudos.caminho_do_arquivo(conteudos.obter(conteudo["id"]))
    enrollment_id, headers = _aluno_ativo()
    chave = conteudos.chave(conteudo)
    client.post(f"/api/student/enrollments/{enrollment_id}/progress", json={"url": chave}, headers=headers)

    rota = f"/api/admin/contents/{conteudo['id']}/file"
    novo = b"%PDF-1.4 nova"
    assert client.put(rota, files={"file": ("nova.pdf", novo)}, headers=gestao).status_code == 200
    assert not antigo.exists()
    baixado = client.get(f"/api/student/enrollments/{enrollment_id}/contents/{conteudo['id']}/file", headers=headers)
    assert baixado.content == novo
    assert chave in _sala(client, enrollment_id, headers).json()["progress"]["completed"]
    assert client.put(rota, files={"file": ("x.exe", b"MZ")}, headers=gestao).status_code == 415
    _, suporte = _conta("support")
    assert client.put(rota, files={"file": ("nova.pdf", novo)}, headers=suporte).status_code == 403


def test_trocar_arquivo_recusa_conteudo_que_nao_e_arquivo(client, gestao):
    video = _video(client, gestao)
    resposta = client.put(f"/api/admin/contents/{video['id']}/file", files={"file": ("a.pdf", PDF)}, headers=gestao)
    assert resposta.status_code == 422


def test_sala_retoma_o_ultimo_conteudo_aberto(client, gestao):
    aula = _video(client, gestao)
    _video(client, gestao, title="Aula 2")
    enrollment_id, headers = _aluno_ativo()
    chave = conteudos.chave(aula)
    assert _sala(client, enrollment_id, headers).json()["resume_key"] == MATERIAL
    rota = f"/api/student/enrollments/{enrollment_id}/room/last-seen"
    assert client.post(rota, json={"key": chave}, headers=headers).status_code == 200
    assert _sala(client, enrollment_id, headers).json()["resume_key"] == chave
    progresso_core.marcar(enrollment_id, chave, True)
    assert _sala(client, enrollment_id, headers).json()["resume_key"] == MATERIAL


def test_marcar_visto_valida_acesso_e_conteudo(client, gestao):
    aula = _video(client, gestao)
    chave = conteudos.chave(aula)
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/room/last-seen"
    assert client.post(rota, json={"key": "conteudo:999"}, headers=headers).status_code == 422
    _, outro = _conta()
    assert client.post(rota, json={"key": chave}, headers=outro).status_code == 404
    user_id, cancelado = _conta()
    cancelada = _matricula(user_id, "cancelled")
    rota_cancelada = f"/api/student/enrollments/{cancelada}/room/last-seen"
    assert client.post(rota_cancelada, json={"key": chave}, headers=cancelado).status_code == 409


def test_material_antigo_informa_o_tipo(client):
    enrollment_id, headers = _aluno_ativo()
    item = _sala(client, enrollment_id, headers).json()["modules"][0]["items"][0]
    assert item["material_type"] == "pdf"


def _avanco(client, enrollment_id, headers, chave, **campos):
    corpo = {"key": chave, "position": 10, "watched_delta": 10, "duration": 100, **campos}
    return client.post(f"/api/student/enrollments/{enrollment_id}/room/video", json=corpo, headers=headers)


def _recuar_relogio(segundos, monkeypatch):
    agora = time.time()
    monkeypatch.setattr(progresso_core.time, "time", lambda: agora + segundos)


def test_primeiro_envio_nao_credita_tempo_nenhum(client, gestao):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    corpo = _avanco(client, enrollment_id, headers, chave, watched_delta=100, position=100).json()
    assert corpo["video"]["watched"] == 0 and corpo["video"]["complete"] is False


def test_tempo_assistido_e_limitado_ao_tempo_real(client, gestao, monkeypatch):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    _avanco(client, enrollment_id, headers, chave, watched_delta=0)
    _recuar_relogio(10, monkeypatch)
    corpo = _avanco(client, enrollment_id, headers, chave, watched_delta=95).json()
    assert corpo["video"]["watched"] <= 20.5, "em 10 s reais, no máximo 20 s em velocidade 2x"
    assert corpo["video"]["complete"] is False


def test_pausa_longa_nao_vira_credito(client, gestao, monkeypatch):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    _avanco(client, enrollment_id, headers, chave, watched_delta=0, duration=1000)
    _recuar_relogio(3600, monkeypatch)
    assert _avanco(client, enrollment_id, headers, chave, watched_delta=900, duration=1000).json()["video"]["watched"] <= 120


def test_noventa_por_cento_conclui_e_libera_certificado(client, gestao, monkeypatch):
    aula = _video(client, gestao)
    chave = conteudos.chave(aula)
    enrollment_id, headers = _aluno_ativo()
    client.post(f"/api/student/enrollments/{enrollment_id}/progress", json={"url": MATERIAL}, headers=headers)
    _avanco(client, enrollment_id, headers, chave, watched_delta=0)
    _recuar_relogio(44, monkeypatch)
    corpo = _avanco(client, enrollment_id, headers, chave, watched_delta=88).json()
    assert corpo["video"]["complete"] is False and corpo["video"]["percent"] == 88
    _recuar_relogio(46, monkeypatch)
    corpo = _avanco(client, enrollment_id, headers, chave, watched_delta=2, position=90).json()
    assert corpo["video"]["complete"] is True and corpo["progress"]["certificate_available"] is True
    sala = _sala(client, enrollment_id, headers).json()
    assert sala["modules"][1]["items"][0]["position"] == 90


def test_parar_no_fim_recomeca_do_inicio(client, gestao):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    _avanco(client, enrollment_id, headers, chave, position=97, watched_delta=0)
    assert _sala(client, enrollment_id, headers).json()["modules"][1]["items"][0]["position"] == 0


def test_video_nao_pode_ser_concluido_a_mao(client, gestao):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    rota = f"/api/student/enrollments/{enrollment_id}/progress"
    assert client.post(rota, json={"url": chave}, headers=headers).status_code == 409


def test_material_antigo_em_video_tambem_conta_por_tempo(client):
    arquivo = admin_routes.COURSES_DIR / f"{CURSO}.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    dados["materials"] = [{"title": "Vídeo antigo", "url": VIDEO, "type": "video"}]
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    enrollment_id, headers = _aluno_ativo()
    assert _avanco(client, enrollment_id, headers, VIDEO).status_code == 200
    rota = f"/api/student/enrollments/{enrollment_id}/progress"
    assert client.post(rota, json={"url": VIDEO}, headers=headers).status_code == 409


@pytest.mark.parametrize("campos, codigo", [
    ({"key": "conteudo:999"}, 422), ({"position": -1}, 422), ({"watched_delta": -1}, 422), ({"duration": 0}, 422),
    ({"duration": 86401}, 422), ({"watched_delta": 3601}, 422),
], ids=lambda v: str(v)[:24])
def test_avanco_recusa_valores_invalidos(client, gestao, campos, codigo):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, headers = _aluno_ativo()
    assert _avanco(client, enrollment_id, headers, campos.pop("key", chave), **campos).status_code == codigo


def test_avanco_de_link_e_recusado(client, gestao):
    link = client.post(f"/api/admin/courses/{CURSO}/contents", headers=gestao, json={
        "module": "M", "title": "L", "kind": "link", "url": "https://materiais.test/l"}).json()["content"]
    enrollment_id, headers = _aluno_ativo()
    assert _avanco(client, enrollment_id, headers, conteudos.chave(link)).status_code == 422


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_avanco_exige_matricula_ativa(client, gestao, status):
    chave = conteudos.chave(_video(client, gestao))
    user_id, headers = _conta()
    assert _avanco(client, _matricula(user_id, status), headers, chave).status_code == 409


def test_avanco_em_matricula_alheia_devolve_404(client, gestao):
    chave = conteudos.chave(_video(client, gestao))
    enrollment_id, _ = _aluno_ativo()
    _, outro = _conta()
    assert _avanco(client, enrollment_id, outro, chave).status_code == 404


def test_gestao_recebe_o_player_da_previa(client, gestao):
    assert _video(client, gestao)["embed_url"].startswith("https://www.youtube-nocookie.com/embed/")


# --- D107: o assistente lê os arquivos do curso ------------------------------------------------------------------

TERMO = "fotossintese"


def _pdf_com_texto(*linhas):
    return gerar_pdf_de_linhas([("F1", linha) for linha in linhas])


def _base():
    return rag.BaseInstitucional()


def _enviar(client, gestao, dados=None, nome="apostila.pdf", curso=CURSO, **extra):
    resposta = _arquivo(client, gestao, nome=nome, dados=dados or _pdf_com_texto(f"Capitulo sobre {TERMO} aplicada"),
                        curso=curso, **extra)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["content"]


def test_arquivo_lido_informa_a_gestao(client, gestao):
    assert _enviar(client, gestao)["text_status"] == "ok"
    assert "extracted_text" not in json.dumps(client.get(f"/api/admin/courses/{CURSO}/contents", headers=gestao).json())


def test_arquivo_sem_texto_informa_a_gestao(client, gestao):
    assert _arquivo(client, gestao, dados=PDF).json()["content"]["text_status"] == "empty"


@pytest.mark.parametrize("aluno, ativos, encontra", [
    (True, [CURSO], True), (True, ["outro"], False), (True, [], False), (False, [CURSO], False),
], ids=["matriculado", "outro-curso", "sem-matricula", "visitante"])
def test_so_o_aluno_ativo_do_curso_recebe_o_trecho(client, gestao, aluno, ativos, encontra):
    _enviar(client, gestao)
    achados = _base().buscar(TERMO, aluno=aluno, cursos_ativos=ativos)
    assert bool(achados) is encontra
    if encontra:
        assert achados[0].titulo == "Apostila" and achados[0].secao == "Página 1"


def test_oculto_excluido_e_trocado_acompanham_o_indice(client, gestao):
    item = _enviar(client, gestao)
    base = _base()
    assert base.buscar(TERMO, aluno=True, cursos_ativos=[CURSO])
    client.put(f"/api/admin/contents/{item['id']}", json={**item, "published": False}, headers=gestao)
    assert base.buscar(TERMO, aluno=True, cursos_ativos=[CURSO]) == []
    client.put(f"/api/admin/contents/{item['id']}", json={**item, "published": True}, headers=gestao)
    novo = _pdf_com_texto("Capitulo sobre mitocondria celular")
    client.put(f"/api/admin/contents/{item['id']}/file", files={"file": ("n.pdf", novo)}, headers=gestao)
    assert base.buscar(TERMO, aluno=True, cursos_ativos=[CURSO]) == []
    assert base.buscar("mitocondria", aluno=True, cursos_ativos=[CURSO])
    client.delete(f"/api/admin/contents/{item['id']}", headers=gestao)
    assert base.buscar("mitocondria", aluno=True, cursos_ativos=[CURSO]) == []


def test_arquivo_antigo_e_lido_ao_montar_o_indice(client, gestao):
    item = _enviar(client, gestao)
    conn = sqlite3.connect(Database.DB_PATH)
    conn.execute("UPDATE course_contents SET extracted_text = NULL WHERE id = ?", (item["id"],))
    conn.commit()
    conn.close()
    assert _base().buscar(TERMO, aluno=True, cursos_ativos=[CURSO])
    assert conteudos.obter(item["id"])["text_status"] == "ok"


@pytest.mark.parametrize("nome, parte, xml", [
    ("a.docx", "word/document.xml", "<w:p><w:t>Texto sobre fotossintese</w:t></w:p>"),
    ("a.pptx", "ppt/slides/slide1.xml", "<a:p><a:t>Slide sobre fotossintese</a:t></a:p>"),
    ("a.xlsx", "xl/sharedStrings.xml", "<si><t>Planilha sobre fotossintese</t></si>"),
], ids=["word", "powerpoint", "excel"])
def test_arquivos_do_office_sao_lidos(client, gestao, nome, parte, xml):
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as arquivo:
        arquivo.writestr(parte, xml)
    _enviar(client, gestao, dados=pacote.getvalue(), nome=nome)
    assert _base().buscar(TERMO, aluno=True, cursos_ativos=[CURSO])


def test_dado_pessoal_do_arquivo_nao_entra_no_indice(client, gestao):
    _enviar(client, gestao, dados=_pdf_com_texto("Presenca: Carla, CPF 529.982.247-25, fone (11) 91234-5678"))
    trecho = _base().buscar("Carla presenca", aluno=True, cursos_ativos=[CURSO])[0]
    assert "529.982.247-25" not in trecho.texto and "91234" not in trecho.texto and "[cpf]" in trecho.texto


def test_arquivo_corrompido_nao_impede_o_envio(client, gestao):
    assert _arquivo(client, gestao, dados=b"%PDF-1.4 sem estrutura").json()["content"]["text_status"] == "empty"
    assert _arquivo(client, gestao, nome="a.docx", dados=b"PK quebrado").json()["content"]["text_status"] == "empty"
