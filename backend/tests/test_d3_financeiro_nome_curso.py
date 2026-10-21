"""D3 (D93) - o financeiro mostra o NOME do curso nas transacoes, nao o id.

Escritos ANTES da implementacao. Devem falhar agora: os itens de `payments` em GET /api/dashboard/financeiro so
trazem `course_id`; a tela mostra "ing", "py" etc.

Contrato (D93):
  - Cada item de `payments` ganha `course_name` (nome do catalogo, inclusive de curso arquivado).
  - Curso que nao existe mais no catalogo: `course_name` = `course_id` (o mesmo padrao do detalhe do aluno, F3).
  - `course_id` continua na resposta (compatibilidade). Com paginacao, o campo vem nos itens da pagina.
  - RBAC inalterado: Gestao e Financeiro 200, Suporte 403, sem token 401.
"""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from core.security import create_access_token
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
CURSO_A, NOME_A = "curso_d3_dados", "Ciencia de Dados D3"
CURSO_B, NOME_B = "curso_d3_ingles", "Ingles Tecnico D3"
CURSO_SUMIDO = "curso_d3_removido"


def _foto_repo():
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


def _escrever(diretorio, course_id, nome, extra=None):
    dados = {"id": course_id, "name": nome, "description": "Curso D3", "price": 100.0, "level": "Iniciante",
             "duration_hours": 10}
    dados.update(extra or {})
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    _escrever(diretorio, CURSO_A, NOME_A)
    _escrever(diretorio, CURSO_B, NOME_B, {"archived": True})
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(email, nome, perfil):
    user_id = Database.add_user(email, nome, None, role=perfil)
    return SimpleNamespace(id=user_id, token=create_access_token({"user_id": user_id, "email": email, "role": perfil}))


def _pagamento(user_id, course_id, valor):
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:d3:{uuid.uuid4().hex}")
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    Database.update_payment_status(payment_id, "approved", f"mp-d3-{uuid.uuid4().hex[:8]}")
    return payment_id


@pytest.fixture
def cenario(client):
    contas = SimpleNamespace(
        gestao=_conta("gestao@d3.test", "Gestao D3", "admin"),
        fin=_conta("fin@d3.test", "Financeiro D3", "financial"),
        sup=_conta("sup@d3.test", "Suporte D3", "support"),
        aluna=_conta("aluna@d3.test", "Aluna D3", "student"),
    )
    pagamentos = {
        CURSO_A: _pagamento(contas.aluna.id, CURSO_A, 120.0),
        CURSO_B: _pagamento(contas.aluna.id, CURSO_B, 80.0),
        CURSO_SUMIDO: _pagamento(contas.aluna.id, CURSO_SUMIDO, 50.0),
    }
    return SimpleNamespace(contas=contas, pagamentos=pagamentos)


def _financeiro(client, token, **params):
    return client.get("/api/dashboard/financeiro", params=params, headers={"Authorization": f"Bearer {token}"})


def _por_curso(resposta):
    assert resposta.status_code == 200, resposta.text
    return {p["course_id"]: p for p in resposta.json()["payments"]}


def test_gestao_recebe_nome_do_curso(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.gestao.token))
    assert itens[CURSO_A]["course_name"] == NOME_A


def test_financeiro_recebe_nome_do_curso(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.fin.token))
    assert itens[CURSO_A]["course_name"] == NOME_A


def test_curso_arquivado_mantem_o_nome(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.gestao.token))
    assert itens[CURSO_B]["course_name"] == NOME_B


def test_curso_fora_do_catalogo_cai_no_id(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.gestao.token))
    assert itens[CURSO_SUMIDO]["course_name"] == CURSO_SUMIDO


def test_course_id_continua_na_resposta(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.gestao.token))
    assert set(itens) == {CURSO_A, CURSO_B, CURSO_SUMIDO}
    assert all("course_id" in item and "amount" in item for item in itens.values())


def test_nome_vem_tambem_na_pagina(client, cenario):
    resposta = _financeiro(client, cenario.contas.gestao.token, page=1, page_size=2)
    assert resposta.status_code == 200, resposta.text
    pagina = resposta.json()["payments"]
    assert len(pagina) == 2
    assert all(item.get("course_name") for item in pagina)


def test_busca_pelo_nome_continua_funcionando(client, cenario):
    itens = _por_curso(_financeiro(client, cenario.contas.gestao.token, q="ciencia de dados"))
    assert list(itens) == [CURSO_A]
    assert itens[CURSO_A]["course_name"] == NOME_A


def test_suporte_continua_sem_acesso(client, cenario):
    assert _financeiro(client, cenario.contas.sup.token).status_code == 403


def test_sem_token_401(client, cenario):
    assert client.get("/api/dashboard/financeiro").status_code == 401
