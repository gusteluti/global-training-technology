"""Dados de demonstração (D107): criam o cenário, não duplicam e nunca rodam em produção."""

import sqlite3

import pytest

import seed_demo
from core import conteudos
from db import Database


@pytest.fixture
def ambiente(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTS_DIR", str(tmp_path / "conteudos"))


def _contagem(tabela):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        conn.close()


def test_cria_contas_turmas_matriculas_e_conteudos(ambiente):
    seed_demo.semear()
    assert Database.get_user_by_email("rafael@demo.test")["role"] == "student"
    assert Database.get_user_by_email("gestao@demo.test")["role"] == "admin"
    assert {t["name"] for t in Database.list_classes()} == {"Turma Noite", "Turma Sábado"}
    assert _contagem("enrollments") == 6
    itens = conteudos.listar(seed_demo.EXCEL, so_publicados=True)
    assert len(itens) == 5 and {i["kind"] for i in itens} == {"video", "file", "link"}
    assert all(i["text_status"] == "ok" for i in itens if i["kind"] == "file")


def test_rodar_de_novo_nao_duplica(ambiente):
    seed_demo.semear()
    antes = [_contagem(t) for t in ("users", "enrollments", "payments", "classes", "course_contents")]
    seed_demo.semear()
    assert [_contagem(t) for t in ("users", "enrollments", "payments", "classes", "course_contents")] == antes


def test_recusa_producao(ambiente, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(SystemExit):
        seed_demo.main()
    assert Database.get_user_by_email("rafael@demo.test") is None
