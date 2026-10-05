"""E1 - Identidade unificada (Fase 2, itens 1.1 e 2; RF21 e RF22).

Testes de comportamento: nenhum depende de função interna nova. Usam
Database.init_db(), consultas SQLite diretas e as rotas HTTP.

Requisitos cobertos (numeração do charter do agente-testes):
  1. migração idempotente do schema antigo (students/enrollments com student_id)
  2. status de matrícula normalizado {pending, active, cancelled, refunded}
  3. checkout cria usuário 'student' sem senha + matrícula 'pending', sem linha em students
  4. webhook: approved->active, refunded->refunded, rejected/cancelled->cancelled, pending/in_process->pending
  5. reembolso (financial ou admin) marca pagamento e matrícula como refunded
  6. dashboard de alunos (admin) conta a partir de users
  7. segurança: aluno sem senha não loga; aluno não acessa área de funcionário
  8. preservação de login/dashboards de funcionário: coberto por test_regressao_fase2.py
"""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.security import get_password_hash
from db import Database

import admin.routes as admin_routes


# --- Fixtures específicas da E1 -------------------------------------------------

@pytest.fixture
def curso_teste(tmp_path, monkeypatch):
    """Um curso com preço, em diretório temporário (checkout lê preço de courses/)."""
    import json

    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / "curso_teste.json").write_text(json.dumps({
        "id": "curso_teste",
        "name": "Curso Teste",
        "description": "Curso para teste de identidade",
        "price": 100.0,
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return "curso_teste"


@pytest.fixture
def client(banco, curso_teste):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers ----------------------------------------------------------------------

SCHEMA_ANTIGO = """
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    external_reference TEXT,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id)
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT,
    role TEXT DEFAULT 'student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

ALUNOS_ANTIGOS = ["aluno1@x.com", "gestor@x.com", "aluno2@x.com"]


def _criar_schema_antigo(caminho):
    """Schema anterior à E1 com dados: 3 students (um deles também é admin em users), 6 matrículas."""
    conn = sqlite3.connect(caminho)
    conn.executescript(SCHEMA_ANTIGO)
    conn.executemany(
        "INSERT INTO students (id, email, name) VALUES (?, ?, ?)",
        [
            (1, "aluno1@x.com", "Aluno Um"),
            (2, "gestor@x.com", "Gestor que tambem fez curso"),
            (3, "aluno2@x.com", "Aluno Dois"),
        ],
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, role) VALUES (1, 'gestor@x.com', 'Gestor', 'hash-admin', 'admin')"
    )
    conn.executemany(
        "INSERT INTO enrollments (student_id, course_id, status, external_reference) VALUES (?, ?, ?, ?)",
        [
            (1, "curso_a", "approved", "ref-1"),
            (1, "curso_b", "in_process", "ref-2"),
            (2, "curso_a", "rejected", "ref-3"),
            (3, "curso_c", "completed", "ref-4"),
            (3, "curso_b", "cancelled", "ref-5"),
            (2, "curso_c", "pending", "ref-6"),
        ],
    )
    conn.commit()
    conn.close()


def _sql(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _contar(tabela):
    """Linhas de uma tabela; tabela inexistente conta como zero."""
    try:
        return _sql(f"SELECT COUNT(*) AS n FROM {tabela}")[0]["n"]
    except sqlite3.OperationalError:
        return 0


def _usuario(email):
    linhas = _sql("SELECT * FROM users WHERE email = ?", (email,))
    return linhas[0] if linhas else None


def _matricula_por_ref(ref):
    linhas = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))
    return linhas[0] if linhas else None


def _token_staff(client, senha):
    r = client.post("/api/admin/login", json={"password": senha})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _checkout(client, email, name="Aluno Teste"):
    resposta = MagicMock(status_code=201)
    resposta.json.return_value = {"id": "pref-1", "init_point": "https://mp.test/checkout"}
    with patch("payments.routes.requests.post", return_value=resposta):
        return client.post("/api/payments/create-checkout", json={
            "course_id": "curso_teste",
            "payer": {"name": name, "email": email},
        })


def _webhook(client, status, ref, pagamento_id="555"):
    resposta = MagicMock(status_code=200)
    resposta.json.return_value = {"id": pagamento_id, "status": status, "external_reference": ref}
    with patch("payments.routes.requests.get", return_value=resposta):
        return client.post("/api/payments/webhook", json={"data": {"id": pagamento_id}})


def _snapshot_migrado():
    usuarios = _sql("SELECT id, email, role, password_hash FROM users ORDER BY id")
    matriculas = _sql("SELECT id, course_id, status, user_id FROM enrollments ORDER BY id")
    return usuarios, matriculas


# --- Requisito 1: migração idempotente do schema antigo ----------------------------

def test_1a_migracao_cria_usuario_student_sem_senha_para_cada_aluno(db_path):
    _criar_schema_antigo(db_path)
    Database.init_db()

    aluno1 = _usuario("aluno1@x.com")
    aluno2 = _usuario("aluno2@x.com")
    assert aluno1 is not None and aluno1["role"] == "student" and aluno1["password_hash"] is None
    assert aluno2 is not None and aluno2["role"] == "student" and aluno2["password_hash"] is None


def test_1b_migracao_nao_rebaixa_papel_de_email_ja_existente(db_path):
    _criar_schema_antigo(db_path)
    Database.init_db()

    # A migração precisa ter rodado (sem isso o teste passaria por ausência de mudança).
    assert _usuario("aluno1@x.com") is not None
    gestor = _usuario("gestor@x.com")
    assert gestor is not None
    assert gestor["role"] == "admin", "o papel admin não pode ser rebaixado para student"
    assert gestor["password_hash"] == "hash-admin", "a senha existente não pode ser apagada"


def test_1c_enrollments_ganham_user_id_sem_perder_linhas(db_path):
    _criar_schema_antigo(db_path)
    matriculas_antes = _contar("enrollments")
    alunos_antes = _contar("students")
    assert (matriculas_antes, alunos_antes) == (6, 3)

    Database.init_db()

    assert _contar("enrollments") == matriculas_antes, "nenhuma matrícula pode se perder"
    sem_usuario = _sql("SELECT COUNT(*) AS n FROM enrollments WHERE user_id IS NULL")[0]["n"]
    assert sem_usuario == 0

    pares = {
        (r["course_id"], r["email"])
        for r in _sql("SELECT e.course_id, u.email FROM enrollments e JOIN users u ON u.id = e.user_id")
    }
    assert pares == {
        ("curso_a", "aluno1@x.com"),
        ("curso_b", "aluno1@x.com"),
        ("curso_a", "gestor@x.com"),
        ("curso_c", "aluno2@x.com"),
        ("curso_b", "aluno2@x.com"),
        ("curso_c", "gestor@x.com"),
    }

    marcados = _sql(
        f"SELECT COUNT(*) AS n FROM users WHERE email IN ({','.join('?' * len(ALUNOS_ANTIGOS))})",
        ALUNOS_ANTIGOS,
    )[0]["n"]
    assert marcados == alunos_antes, "cada linha de students precisa de linha correspondente em users"


def test_1d_rodar_migracao_duas_vezes_nao_quebra_nem_duplica(db_path):
    _criar_schema_antigo(db_path)
    Database.init_db()
    primeiro = _snapshot_migrado()

    Database.init_db()
    segundo = _snapshot_migrado()

    assert segundo == primeiro
    assert _contar("users") == 3
    assert _contar("enrollments") == 6


# --- Requisito 2: status de matrícula normalizado -----------------------------------

def test_2a_migracao_normaliza_status_antigos(db_path):
    _criar_schema_antigo(db_path)
    Database.init_db()

    esperado = {
        ("curso_a", "aluno1@x.com"): "active",       # approved
        ("curso_b", "aluno1@x.com"): "pending",      # in_process
        ("curso_a", "gestor@x.com"): "cancelled",    # rejected
        ("curso_c", "aluno2@x.com"): "active",       # completed
        ("curso_b", "aluno2@x.com"): "cancelled",    # cancelled
        ("curso_c", "gestor@x.com"): "pending",      # pending
    }
    obtido = {
        (r["course_id"], r["email"]): r["status"]
        for r in _sql("SELECT e.course_id, u.email, e.status FROM enrollments e JOIN users u ON u.id = e.user_id")
    }
    assert obtido == esperado


def test_2b_banco_recusa_status_fora_do_conjunto(banco):
    uid = Database.add_user("chk@x.com", "Chk")
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_a', 'bogus')",
                (uid,),
            )
    finally:
        conn.close()


def test_2c_banco_aceita_os_quatro_status_do_conjunto(banco):
    uid = Database.add_user("ok@x.com", "Ok")
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        for status in ("pending", "active", "cancelled", "refunded"):
            conn.execute(
                "INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_a', ?)",
                (uid, status),
            )
        conn.commit()
    finally:
        conn.close()
    assert _contar("enrollments") == 4


def test_2d_check_de_status_existe_tambem_apos_migracao(db_path):
    _criar_schema_antigo(db_path)
    Database.init_db()
    uid = _usuario("aluno1@x.com")["id"]

    conn = sqlite3.connect(Database.DB_PATH)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO enrollments (user_id, course_id, status) VALUES (?, 'curso_a', 'bogus')",
                (uid,),
            )
    finally:
        conn.close()


# --- Requisito 3: checkout cria usuário student + matrícula pending -----------------

def test_3a_checkout_cria_usuario_student_sem_senha_e_matricula_pending(client):
    r = _checkout(client, "maria@teste.com", "Maria Silva")
    assert r.status_code == 200, r.text
    ref = r.json()["external_reference"]

    usuario = _usuario("maria@teste.com")
    assert usuario is not None, "checkout precisa criar a conta do aluno em users"
    assert usuario["role"] == "student"
    assert usuario["password_hash"] is None

    matricula = _matricula_por_ref(ref)
    assert matricula is not None
    assert matricula["user_id"] == usuario["id"]
    assert matricula["status"] == "pending"
    assert matricula["course_id"] == "curso_teste"


def test_3b_checkout_nao_cria_linha_em_students(client):
    antes = _contar("students")
    r = _checkout(client, "joao@teste.com", "Joao Souza")
    assert r.status_code == 200, r.text
    assert _contar("students") == antes


# --- Requisito 4: webhook mapeia status de pagamento para matrícula ----------------

@pytest.mark.parametrize(
    "status_pagamento, status_matricula",
    [
        ("approved", "active"),
        ("refunded", "refunded"),
        ("rejected", "cancelled"),
        ("cancelled", "cancelled"),
        ("pending", "pending"),
        ("in_process", "pending"),
    ],
)
def test_4_webhook_mapeia_status_para_matricula(client, status_pagamento, status_matricula):
    r = _checkout(client, "aluno.webhook@teste.com")
    assert r.status_code == 200, r.text
    ref = r.json()["external_reference"]

    r_hook = _webhook(client, status_pagamento, ref)
    assert r_hook.status_code == 200, r_hook.text

    matricula = _matricula_por_ref(ref)
    assert matricula["status"] == status_matricula
    assert matricula["user_id"] is not None, "a matrícula precisa estar vinculada à conta do aluno"


# --- Requisito 5: reembolso marca pagamento e matrícula ----------------------------

def _pagamento_da_matricula(ref):
    linhas = _sql(
        """SELECT p.id, p.status AS pagamento_status FROM payments p
           JOIN enrollments e ON e.id = p.enrollment_id
           WHERE e.external_reference = ?""",
        (ref,),
    )
    return linhas[0]


@pytest.mark.parametrize("perfil, senha", [("financial", "fin123"), ("admin", "admin123")])
def test_5a_reembolso_marca_pagamento_e_matricula_como_refunded(client, perfil, senha):
    ref = _checkout(client, f"reembolso.{perfil}@teste.com").json()["external_reference"]
    _webhook(client, "approved", ref)
    pagamento = _pagamento_da_matricula(ref)

    r = client.post(
        f"/api/payments/refund/{pagamento['id']}",
        headers={"Authorization": f"Bearer {_token_staff(client, senha)}"},
    )
    assert r.status_code == 200, r.text

    assert _pagamento_da_matricula(ref)["pagamento_status"] == "refunded"
    assert _matricula_por_ref(ref)["status"] == "refunded"


def test_5b_reembolso_recusado_para_suporte(client):
    ref = _checkout(client, "reembolso.suporte@teste.com").json()["external_reference"]
    _webhook(client, "approved", ref)
    pagamento = _pagamento_da_matricula(ref)

    r = client.post(
        f"/api/payments/refund/{pagamento['id']}",
        headers={"Authorization": f"Bearer {_token_staff(client, 'sup123')}"},
    )
    assert r.status_code == 403
    assert _matricula_por_ref(ref)["status"] == "active"


# --- Requisito 6: dashboard de alunos conta a partir de users ----------------------

def test_6_dashboard_alunos_conta_users_e_matriculas_ativas(client):
    admin_token = _token_staff(client, "admin123")

    ref_ativo = _checkout(client, "aluno.ativo@teste.com", "Ativo").json()["external_reference"]
    _webhook(client, "approved", ref_ativo)
    _checkout(client, "aluno.pendente@teste.com", "Pendente")
    Database.add_user("aluno.sem.matricula@teste.com", "Sem Matricula", None, role="student")
    Database.add_user("staff.financeiro@teste.com", "Staff", get_password_hash("x"), role="financial")

    r = client.get("/api/dashboard/alunos", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    corpo = r.json()

    assert corpo["metrics"]["total_students"] == 3, "conta usuários com role 'student' (não funcionários)"
    assert corpo["metrics"]["active_students"] == 1, "conta só quem tem matrícula active"

    emails_na_lista = {aluno["email"] for aluno in corpo["students"]}
    assert emails_na_lista == {
        "aluno.ativo@teste.com",
        "aluno.pendente@teste.com",
        "aluno.sem.matricula@teste.com",
    }


# --- Requisito 7: segurança ---------------------------------------------------------

def test_7a_aluno_criado_pela_compra_sem_senha_nao_loga(client):
    assert _checkout(client, "sem.senha@teste.com").status_code == 200
    assert _usuario("sem.senha@teste.com")["password_hash"] is None

    r = client.post("/api/token", data={"username": "sem.senha@teste.com", "password": "qualquer"})
    assert r.status_code == 400
    assert "access_token" not in r.json()


def test_7b_aluno_com_jwt_valido_nao_acessa_area_de_funcionario(client):
    Database.add_user("aluno.jwt@teste.com", "Aluno JWT", get_password_hash("senha-aluno-123"), role="student")
    r_login = client.post("/api/token", data={"username": "aluno.jwt@teste.com", "password": "senha-aluno-123"})
    assert r_login.status_code == 200, r_login.text
    cabecalho = {"Authorization": f"Bearer {r_login.json()['access_token']}"}

    assert client.get("/api/dashboard/alunos", headers=cabecalho).status_code == 403
    assert client.get("/api/admin/audit-logs", headers=cabecalho).status_code == 403
