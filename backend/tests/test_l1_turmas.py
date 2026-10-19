"""L1 - Turmas (lacuna do dashboard de cursos, PDF 1.2 "inscritos por turma", D53).

Escritos ANTES da implementacao. Devem falhar agora: nao existem a tabela `classes`, a coluna
`enrollments.class_id`, as rotas /api/admin/classes, /api/admin/enrollments e
/api/admin/enrollments/{id}/class, nem os campos `classes` e `unassigned` no dashboard de cursos.

Grupos
  A  Schema e compatibilidade (tabela, coluna, unico (course_id, name), banco antigo migrado e idempotente)
  B  POST /classes (criacao e validacao)
  C  PUT /classes/{id} (atualizacao parcial, null limpa, capacidade abaixo do total)
  D  DELETE /classes/{id}
  E  GET /classes (filtro por curso, contagens enrolled/pending/total)
  F  GET /enrollments?course_id= (campos exatos, sem dados de pagamento)
  G  PUT /enrollments/{id}/class (atribuicao, regras, idempotencia, isolamento entre cursos)
  H  Dashboard /api/dashboard/cursos (chaves antigas + classes + unassigned)
  I  RBAC (Gestao escreve; Suporte le classes/enrollments; Financeiro le classes e dashboard; aluno 403;
     401 sem token e com token forjado; token administrativo legado)
  J  Auditoria da E8 (class.create/update/delete, enrollment.class_change)
  K  Recurso pago so com matricula ativa (a turma nao libera material)

Checklist: IDOR e tratado em B/C/G/J (o corpo e a query nao definem o responsavel nem a identidade; nenhum
endpoint novo recebe id de usuario do cliente; a turma de um curso nao altera matricula de outro). Recurso pago:
grupo K. Compatibilidade: grupo A. 401/403: grupo I.

Convencoes (padrao de test_e8/test_e3): banco temporario via conftest, rotas HTTP reais, JWT de conta montado
com create_access_token, cursos em diretorio temporario (fixture `cursos`, igual a de test_e8; ao final exige
que backend/courses nao tenha mudado). As matriculas sao criadas por Database.create_enrollment e seu status e
levado por SQL (como o webhook deixaria) apenas para montar estado; a atribuicao de turma e sempre feita pela
rota. Nenhum teste toca backend/db.sqlite nem o Groq.

Escolhas conservadoras (ver relatorio): nome invalido (vazio/so espacos/81 caracteres) aceita 400 ou 422 (D53 nao
fixa o codigo); no PUT de turma, nome repetido no curso e tratado como o POST (409 com o mesmo texto); remover
turma com matricula cancelada/reembolsada ainda atribuida e 409 (a matricula mantem class_id); ordem de turmas
sem `starts_on` no dashboard nao e testada (D53 so fixa starts_on e depois name); remover a turma de uma matricula
cancelada/reembolsada e atribuicao `null` sobre matricula sem turma nao sao testados (D53 e omisso); em `changes`,
campo nao alterado pode estar ausente ou ter before == after, mas nunca before != after.
"""

import json
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token
from db import Database


REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
CURSO_A = "curso_l1_a"
CURSO_B = "curso_l1_b"
URL_A1 = "https://materiais.test/l1/apostila-a.pdf"
URL_A2 = "https://materiais.test/l1/video-a.mp4"

ERR_DUP = "Já existe uma turma com esse nome neste curso."
ERR_CAP = "A capacidade não pode ser menor que o número de matrículas da turma."
ERR_DEL = "A turma tem matrículas e não pode ser removida."
ERR_OUTRO = "A turma pertence a outro curso."
ERR_STATUS = "Só matrículas pendentes ou ativas podem ser atribuídas a uma turma."
ERR_CHEIA = "A turma está cheia."

CAMPOS_TURMA = {"id", "course_id", "name", "starts_on", "capacity", "enrolled", "pending", "total"}
CAMPOS_MATRICULA = {"id", "student_name", "student_email", "status", "class_id", "enrolled_at"}
CAMPOS_DASH_ANTIGOS = {
    "id", "name", "price", "level", "total_enrollments", "approved_enrollments",
    "pending_enrollments", "conversion_rate",
}
ACOES_TURMA = ("class.create", "class.update", "class.delete", "enrollment.class_change")
ROTULO = {"admin": "Gestão", "financial": "Financeiro", "support": "Suporte"}


# --- Fixtures ---------------------------------------------------------------------------

def _foto_repo():
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Diretorio temporario para os cursos; backend/courses nao pode mudar."""
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses (deveria usar o diretorio temporario)"


def _escrever_curso(diretorio, course_id, nome, preco=100.0, materiais=None):
    dados = {
        "id": course_id, "name": nome, "description": "Curso de teste L1", "price": preco,
        "level": "Iniciante", "duration_hours": 10,
    }
    if materiais is not None:
        dados["materials"] = materiais
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def catalogo(cursos):
    """Dois cursos: A (com materiais) e B (sem o campo materials)."""
    _escrever_curso(cursos, CURSO_A, "Curso L1 A", 100.0, [
        {"title": "Apostila A", "url": URL_A1, "type": "pdf"},
        {"title": "Video A", "url": URL_A2, "type": "video"},
    ])
    _escrever_curso(cursos, CURSO_B, "Curso L1 B", 200.0)
    return SimpleNamespace(a=CURSO_A, b=CURSO_B)


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(email, nome, perfil):
    user_id = Database.add_user(email, nome, None, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        ana=_conta("ana.gestora@l1.test", "Ana Gestora", "admin"),
        bruno=_conta("bruno.gestor@l1.test", "Bruno Gestor", "admin"),
        sup=_conta("sergio.sup@l1.test", "Sergio Suporte", "support"),
        fin=_conta("fernanda.fin@l1.test", "Fernanda Financeira", "financial"),
        aluno=_conta("aluno.l1@l1.test", "Aluno L1", "student"),
    )


@pytest.fixture
def adm(contas):
    """Token JWT de Gestao (padrao para montar estado)."""
    return contas.ana.token


@pytest.fixture
def ident(contas):
    """Identidades da matriz de RBAC: nome -> token (None = sem cabecalho)."""
    return {
        "gestao_jwt": contas.ana.token,
        "suporte_jwt": contas.sup.token,
        "financeiro_jwt": contas.fin.token,
        "aluno_jwt": contas.aluno.token,
        "gestao_legado": create_admin_token(Role.ADMIN),
        "suporte_legado": create_admin_token(Role.SUPPORT),
        "financeiro_legado": create_admin_token(Role.FINANCIAL),
        "sem_token": None,
        "token_forjado": _forjado(),
    }


def _forjado(role="admin"):
    return jose_jwt.encode(
        {"user_id": 1, "email": "x@l1.test", "role": role},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


# --- Helpers de banco -------------------------------------------------------------------

def _sql(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _matricula(course_id, status="pending", nome=None, email=None):
    """Matricula real (create_enrollment); o status e levado por SQL so para montar o estado."""
    sufixo = uuid.uuid4().hex[:8]
    email = email or f"aluno.{sufixo}@l1.test"
    nome = nome or f"Aluno {sufixo}"
    user_id = Database.get_or_create_user(email, nome)
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:l1:{uuid.uuid4().hex}")
    if status != "pending":
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))
    return enrollment_id


def _mudar_status(enrollment_id, status):
    _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))


def _class_id_no_banco(enrollment_id):
    return _sql("SELECT class_id FROM enrollments WHERE id = ?", (enrollment_id,))[0]["class_id"]


def _status_no_banco(enrollment_id):
    return _sql("SELECT status FROM enrollments WHERE id = ?", (enrollment_id,))[0]["status"]


def _n_turmas():
    return _sql("SELECT COUNT(*) AS n FROM classes")[0]["n"]


def _eventos(action=None):
    if action is None:
        return _sql("SELECT * FROM audit_logs ORDER BY id")
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _n_eventos_turma():
    marcas = ",".join("?" for _ in ACOES_TURMA)
    return _sql(f"SELECT COUNT(*) AS n FROM audit_logs WHERE action IN ({marcas})", ACOES_TURMA)[0]["n"]


# --- Helpers de HTTP --------------------------------------------------------------------

def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _criar_turma(client, token, course_id, name, **extra):
    corpo = {"course_id": course_id, "name": name, **extra}
    return client.post("/api/admin/classes", json=corpo, headers=_auth(token))


def _turma(client, token, course_id, name, **extra):
    """Cria a turma e devolve o objeto `class` da resposta."""
    r = _criar_turma(client, token, course_id, name, **extra)
    assert r.status_code == 200, f"POST /classes: HTTP {r.status_code} {r.text[:300]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert isinstance(corpo.get("class"), dict), corpo
    return corpo["class"]


def _put_turma(client, token, class_id, corpo):
    return client.put(f"/api/admin/classes/{class_id}", json=corpo, headers=_auth(token))


def _del_turma(client, token, class_id):
    return client.delete(f"/api/admin/classes/{class_id}", headers=_auth(token))


def _turmas(client, token, course_id=None):
    params = {"course_id": course_id} if course_id else {}
    r = client.get("/api/admin/classes", params=params, headers=_auth(token))
    assert r.status_code == 200, f"GET /classes: HTTP {r.status_code} {r.text[:300]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert isinstance(corpo.get("classes"), list), corpo
    return corpo["classes"]


def _turma_na_lista(client, token, class_id, course_id=None):
    achadas = [t for t in _turmas(client, token, course_id) if t["id"] == class_id]
    assert len(achadas) == 1, f"turma {class_id} deveria estar na lista exatamente uma vez: {achadas}"
    return achadas[0]


def _contagem(turma):
    return (turma["enrolled"], turma["pending"], turma["total"])


def _atribuir(client, token, enrollment_id, class_id):
    return client.put(
        f"/api/admin/enrollments/{enrollment_id}/class",
        json={"class_id": class_id}, headers=_auth(token),
    )


def _atribuir_ok(client, token, enrollment_id, class_id):
    r = _atribuir(client, token, enrollment_id, class_id)
    assert r.status_code == 200, f"PUT /enrollments/{enrollment_id}/class: HTTP {r.status_code} {r.text[:300]}"
    assert _class_id_no_banco(enrollment_id) == class_id
    return r


def _matriculas(client, token, course_id):
    r = client.get("/api/admin/enrollments", params={"course_id": course_id}, headers=_auth(token))
    assert r.status_code == 200, f"GET /enrollments: HTTP {r.status_code} {r.text[:300]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert isinstance(corpo.get("enrollments"), list), corpo
    return corpo["enrollments"]


def _dashboard(client, token):
    r = client.get("/api/dashboard/cursos", headers=_auth(token))
    assert r.status_code == 200, f"GET /dashboard/cursos: HTTP {r.status_code} {r.text[:300]}"
    return r.json()


def _curso_no_dashboard(client, token, course_id):
    achados = [c for c in _dashboard(client, token)["courses"] if c["id"] == course_id]
    assert len(achados) == 1, f"curso {course_id} deveria estar no dashboard: {achados}"
    return achados[0]


def _detalhe(resposta):
    return resposta.json().get("detail")


# --- Helpers de auditoria ---------------------------------------------------------------

def _lista_changes(valor):
    if valor is None or valor == "":
        return []
    lista = json.loads(valor) if isinstance(valor, str) else valor
    assert isinstance(lista, list), f"changes deve ser lista, veio {lista!r}"
    for item in lista:
        assert isinstance(item, dict) and set(item) == {"field", "before", "after"}, item
    return lista


def _mudancas(evento):
    itens = _lista_changes(evento["changes"])
    campos = [i["field"] for i in itens]
    assert len(campos) == len(set(campos)), f"campo repetido em changes: {campos}"
    return {i["field"]: i for i in itens}


def _norm(valor):
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return valor
    return valor


def _igual(valor, esperado):
    return valor == esperado or _norm(valor) == esperado


def _checar_changes_turma(evento, esperado):
    """`esperado`: {campo: (antes, depois)} para name/starts_on/capacity.

    Campo esperado: valores exatos. Campo de turma nao esperado: ausente, ou com before == after.
    Nenhum campo fora de name/starts_on/capacity.
    """
    mud = _mudancas(evento)
    assert set(mud) <= {"name", "starts_on", "capacity"}, f"campos inesperados em changes: {sorted(mud)}"
    for campo, (antes, depois) in esperado.items():
        assert campo in mud, f"campo {campo!r} ausente em changes: {sorted(mud)}"
        assert _igual(mud[campo]["before"], antes), f"{campo}.before = {mud[campo]['before']!r}, esperado {antes!r}"
        assert _igual(mud[campo]["after"], depois), f"{campo}.after = {mud[campo]['after']!r}, esperado {depois!r}"
    for campo, item in mud.items():
        if campo not in esperado:
            assert _norm(item["before"]) == _norm(item["after"]), f"{campo} nao mudou mas changes diz {item}"


def _checar_ator(evento, pessoa):
    assert evento["user_id"] == pessoa.id, evento
    assert evento["actor_email"] == pessoa.email, evento
    assert evento["actor_name"] == pessoa.name, evento
    assert evento["role"] == pessoa.role, evento


def _checar_ator_legado(evento, perfil):
    assert evento["user_id"] is None, evento
    assert evento["actor_email"] is None, evento
    assert evento["actor_name"] == f"Login administrativo ({ROTULO[perfil]})", evento
    assert evento["role"] == perfil, evento


def _unico(eventos, descricao):
    assert len(eventos) == 1, f"esperado exatamente 1 evento {descricao}, achei {len(eventos)}: {eventos}"
    return eventos[0]


# =========================================================================================
# Grupo S - setup (deve estar verde ja no red: prova que o isolamento dos cursos funciona)
# =========================================================================================

def test_s1_setup_cursos_vao_para_diretorio_temporario(client, catalogo, cursos):
    assert (cursos / f"{CURSO_A}.json").exists()
    assert not (REPO_COURSES / f"{CURSO_A}.json").exists()
    ids = {c["id"] for c in _dashboard(client, create_admin_token(Role.ADMIN))["courses"]}
    assert ids == {CURSO_A, CURSO_B}


# =========================================================================================
# Grupo A - Schema e compatibilidade
# =========================================================================================

def _colunas(tabela):
    return {r["name"] for r in _sql(f"PRAGMA table_info({tabela})")}


def test_a1_schema_novo_tem_tabela_classes_e_coluna_class_id(banco):
    tabelas = {r["name"] for r in _sql("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "classes" in tabelas, "tabela classes ausente"
    assert {"id", "course_id", "name", "starts_on", "capacity", "created_at"} <= _colunas("classes")
    assert "class_id" in _colunas("enrollments"), "coluna enrollments.class_id ausente"


def test_a2_par_curso_nome_e_unico_no_banco(banco):
    tabelas = {r["name"] for r in _sql("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "classes" in tabelas, "tabela classes ausente"
    _executar("INSERT INTO classes (course_id, name) VALUES ('c1', 'Turma 1')")
    _executar("INSERT INTO classes (course_id, name) VALUES ('c2', 'Turma 1')")  # outro curso: ok
    with pytest.raises(sqlite3.IntegrityError):
        _executar("INSERT INTO classes (course_id, name) VALUES ('c1', 'Turma 1')")
    assert _n_turmas() == 2


_DDL_ANTIGO = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT,
        role TEXT DEFAULT 'student',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'active', 'cancelled', 'refunded')),
        external_reference TEXT,
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrollment_id INTEGER NOT NULL,
        amount FLOAT NOT NULL,
        status TEXT DEFAULT 'pending',
        payment_method TEXT,
        transaction_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (enrollment_id) REFERENCES enrollments(id)
    );
"""
_LINHAS_ANTIGAS = [
    # id, user_id, course_id, status, external_reference, enrolled_at
    (1, 1, "curso_l1_antigo", "active", "ref-antiga-1", "2026-01-10 10:00:00"),
    (2, 2, "curso_l1_antigo", "pending", "ref-antiga-2", "2026-01-11 11:00:00"),
    (3, 1, "curso_l1_antigo", "cancelled", "ref-antiga-3", "2026-01-12 12:00:00"),
]


def _criar_banco_antigo(caminho):
    """Banco no formato anterior a D53: sem tabela classes e sem enrollments.class_id."""
    conn = sqlite3.connect(caminho)
    try:
        conn.executescript(_DDL_ANTIGO)
        conn.execute("INSERT INTO users (id, email, name, role) VALUES (1, 'a@antigo.test', 'Antiga A', 'student')")
        conn.execute("INSERT INTO users (id, email, name, role) VALUES (2, 'b@antigo.test', 'Antiga B', 'student')")
        conn.executemany(
            "INSERT INTO enrollments (id, user_id, course_id, status, external_reference, enrolled_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", _LINHAS_ANTIGAS)
        conn.execute("INSERT INTO payments (enrollment_id, amount, status) VALUES (1, 100.0, 'approved')")
        conn.commit()
    finally:
        conn.close()


def _foto_dados():
    return {
        "enrollments": _sql("SELECT id, user_id, course_id, status, external_reference, enrolled_at "
                            "FROM enrollments ORDER BY id"),
        "users": _sql("SELECT id, email, name, role FROM users ORDER BY id"),
        "payments": _sql("SELECT id, enrollment_id, amount, status FROM payments ORDER BY id"),
    }


def test_a3_banco_antigo_e_migrado_sem_perder_dados_e_de_forma_idempotente(db_path):
    _criar_banco_antigo(db_path)
    assert "class_id" not in _colunas("enrollments"), "pre-condicao: banco antigo sem class_id"
    antes = _foto_dados()
    assert len(antes["enrollments"]) == 3

    Database.init_db()

    assert "class_id" in _colunas("enrollments")
    assert {"id", "course_id", "name", "starts_on", "capacity", "created_at"} <= _colunas("classes")
    assert _foto_dados() == antes, "init_db nao pode perder nem alterar dados antigos"
    assert [r["class_id"] for r in _sql("SELECT class_id FROM enrollments ORDER BY id")] == [None, None, None]

    colunas_enr, colunas_cls = _colunas("enrollments"), _colunas("classes")
    Database.init_db()
    assert _colunas("enrollments") == colunas_enr and _colunas("classes") == colunas_cls
    assert _foto_dados() == antes


def test_a4_matriculas_antigas_aparecem_como_sem_turma_na_api_e_no_dashboard(db_path, cursos):
    _criar_banco_antigo(db_path)
    Database.init_db()
    _escrever_curso(cursos, "curso_l1_antigo", "Curso Antigo")
    from app import app as fastapi_app

    token = create_admin_token(Role.ADMIN)
    with TestClient(fastapi_app) as c:
        itens = {m["id"]: m for m in _matriculas(c, token, "curso_l1_antigo")}
        assert set(itens) == {1, 2, 3}
        assert all(m["class_id"] is None for m in itens.values())
        assert {m["id"]: m["status"] for m in itens.values()} == {1: "active", 2: "pending", 3: "cancelled"}
        assert _turmas(c, token) == []
        curso = _curso_no_dashboard(c, token, "curso_l1_antigo")
        assert curso["classes"] == []
        assert curso["unassigned"] == {"total": 2, "active": 1, "pending": 1}
        assert curso["total_enrollments"] == 3
        # e o fluxo novo funciona sobre o banco migrado
        turma = _turma(c, token, "curso_l1_antigo", "Turma pos-migracao")
        _atribuir_ok(c, token, 2, turma["id"])
        assert _contagem(_turma_na_lista(c, token, turma["id"])) == (0, 1, 1)


# =========================================================================================
# Grupo B - POST /classes
# =========================================================================================

def test_b1_cria_turma_completa(client, catalogo, adm):
    r = _criar_turma(client, adm, CURSO_A, "Turma Manha", starts_on="2026-11-05", capacity=30)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "success"
    turma = corpo["class"]
    assert CAMPOS_TURMA <= set(turma), f"faltam campos: {CAMPOS_TURMA - set(turma)}"
    assert isinstance(turma["id"], int)
    assert turma["course_id"] == CURSO_A
    assert turma["name"] == "Turma Manha"
    assert turma["starts_on"] == "2026-11-05"
    assert turma["capacity"] == 30
    assert _contagem(turma) == (0, 0, 0)
    na_lista = _turma_na_lista(client, adm, turma["id"])
    assert na_lista["name"] == "Turma Manha" and na_lista["starts_on"] == "2026-11-05" and na_lista["capacity"] == 30


def test_b2_data_e_capacidade_sao_opcionais(client, catalogo, adm):
    turma = _turma(client, adm, CURSO_A, "Turma sem limites")
    assert turma["starts_on"] is None
    assert turma["capacity"] is None
    assert _contagem(turma) == (0, 0, 0)
    linha = _turma_na_lista(client, adm, turma["id"])
    assert linha["starts_on"] is None and linha["capacity"] is None


def test_b3_nome_recebe_strip(client, catalogo, adm):
    turma = _turma(client, adm, CURSO_A, "   Turma Tarde  ")
    assert turma["name"] == "Turma Tarde"
    assert _turma_na_lista(client, adm, turma["id"])["name"] == "Turma Tarde"


def test_b4_curso_inexistente_404_sem_criar(client, catalogo, adm):
    _turma(client, adm, CURSO_A, "Controle")  # a rota existe
    antes = _n_turmas()
    r = _criar_turma(client, adm, "curso_que_nao_existe", "Turma X")
    assert r.status_code == 404, r.text
    assert _detalhe(r) == "Course not found"
    assert _n_turmas() == antes


@pytest.mark.parametrize("nome", ["", "   ", "x" * 81], ids=["vazio", "so_espacos", "81_caracteres"])
def test_b5_nome_invalido_e_recusado_sem_criar(client, catalogo, adm, nome):
    _turma(client, adm, CURSO_A, "Controle")
    antes = _n_turmas()
    r = _criar_turma(client, adm, CURSO_A, nome)
    assert r.status_code in (400, 422), f"HTTP {r.status_code} {r.text[:200]}"
    assert _n_turmas() == antes


def test_b6_nome_com_80_caracteres_e_aceito(client, catalogo, adm):
    nome = "n" * 80
    turma = _turma(client, adm, CURSO_A, nome)
    assert turma["name"] == nome


def test_b7_nome_ausente_ou_curso_ausente_422(client, catalogo, adm):
    _turma(client, adm, CURSO_A, "Controle")
    antes = _n_turmas()
    r1 = client.post("/api/admin/classes", json={"course_id": CURSO_A}, headers=_auth(adm))
    r2 = client.post("/api/admin/classes", json={"name": "Sem curso"}, headers=_auth(adm))
    assert r1.status_code == 422, r1.text
    assert r2.status_code == 422, r2.text
    assert _n_turmas() == antes


def test_b8_nome_repetido_no_mesmo_curso_409(client, catalogo, adm):
    primeira = _turma(client, adm, CURSO_A, "Turma Unica")
    r = _criar_turma(client, adm, CURSO_A, "Turma Unica")
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_DUP
    # a comparacao e feita depois do strip
    r2 = _criar_turma(client, adm, CURSO_A, "  Turma Unica ")
    assert r2.status_code == 409, r2.text
    assert _detalhe(r2) == ERR_DUP
    assert [t["id"] for t in _turmas(client, adm, CURSO_A)] == [primeira["id"]]


def test_b9_mesmo_nome_em_cursos_diferentes_e_permitido(client, catalogo, adm):
    a = _turma(client, adm, CURSO_A, "Turma 1")
    b = _turma(client, adm, CURSO_B, "Turma 1")
    assert a["id"] != b["id"]
    assert a["course_id"] == CURSO_A and b["course_id"] == CURSO_B


@pytest.mark.parametrize("capacidade", [0, -1, -30, "abc"], ids=["zero", "menos_1", "menos_30", "texto"])
def test_b10_capacidade_invalida_422(client, catalogo, adm, capacidade):
    _turma(client, adm, CURSO_A, "Controle")
    antes = _n_turmas()
    r = _criar_turma(client, adm, CURSO_A, "Turma Cap", capacity=capacidade)
    assert r.status_code == 422, f"HTTP {r.status_code} {r.text[:200]}"
    assert _n_turmas() == antes


def test_b11_capacidade_um_e_valida(client, catalogo, adm):
    assert _turma(client, adm, CURSO_A, "Turma Minima", capacity=1)["capacity"] == 1


@pytest.mark.parametrize("data", ["2026-13-45", "2026-02-30", "amanha", "31/12/2026", "2026-1-1x"],
                         ids=["mes13", "fev30", "texto", "br", "lixo"])
def test_b12_data_invalida_422(client, catalogo, adm, data):
    _turma(client, adm, CURSO_A, "Controle")
    antes = _n_turmas()
    r = _criar_turma(client, adm, CURSO_A, "Turma Data", starts_on=data)
    assert r.status_code == 422, f"HTTP {r.status_code} {r.text[:200]}"
    assert _n_turmas() == antes


# =========================================================================================
# Grupo C - PUT /classes/{id}
# =========================================================================================

def _turma_base(client, adm, **extra):
    return _turma(client, adm, CURSO_A, "Turma Base", starts_on="2026-10-01", capacity=10, **extra)


def test_c1_so_o_nome_muda(client, catalogo, adm):
    t = _turma_base(client, adm)
    r = _put_turma(client, adm, t["id"], {"name": "Turma Renomeada"})
    assert r.status_code == 200, r.text
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Renomeada", "2026-10-01", 10)


def test_c2_so_a_capacidade_muda(client, catalogo, adm):
    t = _turma_base(client, adm)
    assert _put_turma(client, adm, t["id"], {"capacity": 25}).status_code == 200
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Base", "2026-10-01", 25)


def test_c3_so_a_data_muda(client, catalogo, adm):
    t = _turma_base(client, adm)
    assert _put_turma(client, adm, t["id"], {"starts_on": "2026-12-15"}).status_code == 200
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Base", "2026-12-15", 10)


def test_c4_null_limpa_data_e_capacidade(client, catalogo, adm):
    t = _turma_base(client, adm)
    assert _put_turma(client, adm, t["id"], {"starts_on": None}).status_code == 200
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Base", None, 10)
    assert _put_turma(client, adm, t["id"], {"capacity": None}).status_code == 200
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Base", None, None)


def test_c5_varios_campos_de_uma_vez(client, catalogo, adm):
    t = _turma_base(client, adm)
    r = _put_turma(client, adm, t["id"], {"name": "Nova", "starts_on": None, "capacity": 5})
    assert r.status_code == 200, r.text
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Nova", None, 5)


def test_c6_turma_inexistente_404(client, catalogo, adm):
    t = _turma_base(client, adm)
    assert _put_turma(client, adm, t["id"], {"name": "Controle"}).status_code == 200
    r = _put_turma(client, adm, 999999, {"name": "Fantasma"})
    assert r.status_code == 404, r.text


def test_c7_capacidade_abaixo_do_total_409_e_nada_muda(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Lotada", capacity=5)
    _atribuir_ok(client, adm, _matricula(CURSO_A, "pending"), t["id"])
    _atribuir_ok(client, adm, _matricula(CURSO_A, "active"), t["id"])
    r = _put_turma(client, adm, t["id"], {"capacity": 1, "name": "Nao deve mudar"})
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_CAP
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["capacity"]) == ("Lotada", 5), "recusa nao pode aplicar parte do PUT"
    # igual ao total e permitido
    assert _put_turma(client, adm, t["id"], {"capacity": 2}).status_code == 200
    assert _turma_na_lista(client, adm, t["id"])["capacity"] == 2


def test_c8_cancelada_e_reembolsada_nao_entram_no_total_da_capacidade(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Com baixas", capacity=5)
    ativa = _matricula(CURSO_A, "active")
    cancelada = _matricula(CURSO_A, "pending")
    reembolsada = _matricula(CURSO_A, "active")
    for m in (ativa, cancelada, reembolsada):
        _atribuir_ok(client, adm, m, t["id"])
    _mudar_status(cancelada, "cancelled")
    _mudar_status(reembolsada, "refunded")
    r = _put_turma(client, adm, t["id"], {"capacity": 1})
    assert r.status_code == 200, f"so 1 matricula conta (ativa): {r.text}"
    assert _turma_na_lista(client, adm, t["id"])["capacity"] == 1


@pytest.mark.parametrize("corpo", [{"capacity": 0}, {"capacity": -2}, {"starts_on": "2026-02-31"}, {"starts_on": "hoje"}],
                         ids=["cap_zero", "cap_negativa", "data_inexistente", "data_texto"])
def test_c9_valores_invalidos_422_e_nada_muda(client, catalogo, adm, corpo):
    t = _turma_base(client, adm)
    r = _put_turma(client, adm, t["id"], corpo)
    assert r.status_code == 422, f"HTTP {r.status_code} {r.text[:200]}"
    linha = _turma_na_lista(client, adm, t["id"])
    assert (linha["name"], linha["starts_on"], linha["capacity"]) == ("Turma Base", "2026-10-01", 10)


@pytest.mark.parametrize("nome", ["", "   ", "x" * 81], ids=["vazio", "so_espacos", "81_caracteres"])
def test_c10_nome_invalido_e_recusado(client, catalogo, adm, nome):
    t = _turma_base(client, adm)
    r = _put_turma(client, adm, t["id"], {"name": nome})
    assert r.status_code in (400, 422), f"HTTP {r.status_code} {r.text[:200]}"
    assert _turma_na_lista(client, adm, t["id"])["name"] == "Turma Base"


def test_c11_renomear_para_nome_de_outra_turma_do_mesmo_curso_409(client, catalogo, adm):
    t1 = _turma(client, adm, CURSO_A, "Turma 1")
    t2 = _turma(client, adm, CURSO_A, "Turma 2")
    r = _put_turma(client, adm, t2["id"], {"name": "Turma 1"})
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_DUP
    assert _turma_na_lista(client, adm, t2["id"])["name"] == "Turma 2"
    # o proprio nome nao conflita consigo mesmo; nome de turma de outro curso tambem e livre
    assert _put_turma(client, adm, t1["id"], {"name": "Turma 1"}).status_code == 200
    _turma(client, adm, CURSO_B, "Nome do B")
    assert _put_turma(client, adm, t1["id"], {"name": "Nome do B"}).status_code == 200


def test_c12_course_id_no_corpo_nao_move_a_turma(client, catalogo, adm):
    t = _turma_base(client, adm)
    r = _put_turma(client, adm, t["id"], {"name": "Mesma", "course_id": CURSO_B})
    assert r.status_code in (200, 422), r.text
    assert _turma_na_lista(client, adm, t["id"])["course_id"] == CURSO_A
    assert _sql("SELECT course_id FROM classes WHERE id = ?", (t["id"],))[0]["course_id"] == CURSO_A


# =========================================================================================
# Grupo D - DELETE /classes/{id}
# =========================================================================================

def test_d1_remove_turma_sem_matriculas(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Descartavel")
    r = _del_turma(client, adm, t["id"])
    assert r.status_code == 200, r.text
    assert t["id"] not in [x["id"] for x in _turmas(client, adm)]
    assert _n_turmas() == 0


def test_d2_turma_inexistente_404(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Controle")
    assert _del_turma(client, adm, t["id"]).status_code == 200
    r = _del_turma(client, adm, t["id"])  # ja removida
    assert r.status_code == 404, r.text
    assert _del_turma(client, adm, 999999).status_code == 404


def test_d3_turma_com_matriculas_409_e_continua_existindo(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Com alunos")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])
    r = _del_turma(client, adm, t["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_DEL
    assert _turma_na_lista(client, adm, t["id"])["total"] == 1
    assert _class_id_no_banco(m) == t["id"]


def test_d4_matricula_cancelada_ainda_atribuida_tambem_bloqueia(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Com baixa")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t["id"])
    _mudar_status(m, "cancelled")  # mantem class_id
    r = _del_turma(client, adm, t["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_DEL
    assert _n_turmas() == 1
    assert _class_id_no_banco(m) == t["id"]


def test_d5_depois_de_remover_as_matriculas_da_turma_ela_pode_ser_removida(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Esvaziada")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])
    assert _del_turma(client, adm, t["id"]).status_code == 409
    _atribuir_ok(client, adm, m, None)
    assert _del_turma(client, adm, t["id"]).status_code == 200
    assert _status_no_banco(m) == "pending", "remover a turma nao mexe na matricula"


def test_d6_remover_uma_turma_nao_toca_nas_outras(client, catalogo, adm):
    t1 = _turma(client, adm, CURSO_A, "Fica")
    t2 = _turma(client, adm, CURSO_A, "Sai")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t1["id"])
    assert _del_turma(client, adm, t2["id"]).status_code == 200
    assert _contagem(_turma_na_lista(client, adm, t1["id"])) == (1, 0, 1)
    assert _class_id_no_banco(m) == t1["id"]


# =========================================================================================
# Grupo E - GET /classes
# =========================================================================================

def test_e1_lista_com_e_sem_filtro_de_curso_e_campos_exatos(client, catalogo, adm):
    a1 = _turma(client, adm, CURSO_A, "A1", starts_on="2026-09-01", capacity=3)
    a2 = _turma(client, adm, CURSO_A, "A2")
    b1 = _turma(client, adm, CURSO_B, "B1")
    todas = _turmas(client, adm)
    assert {t["id"] for t in todas} == {a1["id"], a2["id"], b1["id"]}
    for t in todas:
        assert set(t) == CAMPOS_TURMA, f"campos exatos esperados, veio {sorted(t)}"
    assert {t["id"] for t in _turmas(client, adm, CURSO_A)} == {a1["id"], a2["id"]}
    assert {t["id"] for t in _turmas(client, adm, CURSO_B)} == {b1["id"]}
    por_id = {t["id"]: t for t in todas}
    assert por_id[a1["id"]]["course_id"] == CURSO_A and por_id[b1["id"]]["course_id"] == CURSO_B
    assert por_id[a1["id"]]["starts_on"] == "2026-09-01" and por_id[a1["id"]]["capacity"] == 3


def test_e2_sem_turmas_devolve_lista_vazia(client, catalogo, adm):
    assert _turmas(client, adm) == []
    _turma(client, adm, CURSO_A, "So no A")
    assert _turmas(client, adm, CURSO_B) == []


def test_e3_contagens_enrolled_pending_total(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Contagem")
    outra = _turma(client, adm, CURSO_A, "Outra")
    for status in ("active", "active", "pending"):
        _atribuir_ok(client, adm, _matricula(CURSO_A, status), t["id"])
    _atribuir_ok(client, adm, _matricula(CURSO_A, "active"), outra["id"])
    _matricula(CURSO_A, "active")  # sem turma: nao conta em nenhuma
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (2, 1, 3)
    assert _contagem(_turma_na_lista(client, adm, outra["id"])) == (1, 0, 1)


def test_e4_cancelada_e_reembolsada_atribuidas_antes_nao_contam(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Com baixas")
    ativa = _matricula(CURSO_A, "active")
    pendente = _matricula(CURSO_A, "pending")
    a_cancelar = _matricula(CURSO_A, "pending")
    a_reembolsar = _matricula(CURSO_A, "active")
    for m in (ativa, pendente, a_cancelar, a_reembolsar):
        _atribuir_ok(client, adm, m, t["id"])
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (2, 2, 4)
    _mudar_status(a_cancelar, "cancelled")
    _mudar_status(a_reembolsar, "refunded")
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 1, 2)
    # e as matriculas baixadas continuam apontando para a turma (class_id e mantido)
    assert _class_id_no_banco(a_cancelar) == t["id"] and _class_id_no_banco(a_reembolsar) == t["id"]
    # pending -> active move a contagem de pending para enrolled
    _mudar_status(pendente, "active")
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (2, 0, 2)


def test_e5_matricula_ja_baixada_nao_pode_entrar_e_nao_conta(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Sem baixas")
    _atribuir_ok(client, adm, _matricula(CURSO_A, "active"), t["id"])
    morta = _matricula(CURSO_A, "cancelled")
    assert _atribuir(client, adm, morta, t["id"]).status_code == 409
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 0, 1)


# =========================================================================================
# Grupo F - GET /enrollments?course_id=
# =========================================================================================

def test_f1_campos_exatos_filtro_por_curso_e_todos_os_status(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "T")
    ativa = _matricula(CURSO_A, "active", nome="Maria Ativa", email="maria.ativa@l1.test")
    pendente = _matricula(CURSO_A, "pending", nome="Joao Pendente", email="joao.pendente@l1.test")
    cancelada = _matricula(CURSO_A, "cancelled", nome="Carla Cancelada", email="carla.cancelada@l1.test")
    reembolsada = _matricula(CURSO_A, "refunded", nome="Rui Reembolsado", email="rui.reembolsado@l1.test")
    do_b = _matricula(CURSO_B, "active", nome="Beto do B", email="beto.b@l1.test")
    _atribuir_ok(client, adm, ativa, t["id"])

    itens = _matriculas(client, adm, CURSO_A)
    por_id = {m["id"]: m for m in itens}
    assert set(por_id) == {ativa, pendente, cancelada, reembolsada}, "so as matriculas do curso pedido"
    for m in itens:
        assert set(m) == CAMPOS_MATRICULA, f"campos exatos esperados, veio {sorted(m)}"
        assert m["enrolled_at"], m
    assert por_id[ativa]["student_name"] == "Maria Ativa"
    assert por_id[ativa]["student_email"] == "maria.ativa@l1.test"
    assert por_id[ativa]["status"] == "active" and por_id[ativa]["class_id"] == t["id"]
    assert por_id[pendente]["status"] == "pending" and por_id[pendente]["class_id"] is None
    assert por_id[cancelada]["status"] == "cancelled"
    assert por_id[reembolsada]["status"] == "refunded"
    assert {m["id"] for m in _matriculas(client, adm, CURSO_B)} == {do_b}


def test_f2_sem_dados_de_pagamento_nem_de_conta(client, catalogo, adm):
    user_id = Database.get_or_create_user("pagante.f2@l1.test", "Pagante F2")
    ref = f"ref-segredo-f2-{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, CURSO_A, ref)
    Database.record_payment(enrollment_id, 4321.99, "mercado_pago")
    Database.update_payment_status_by_reference(ref, "approved", "tx-segredo-f2")
    r = client.get("/api/admin/enrollments", params={"course_id": CURSO_A}, headers=_auth(adm))
    assert r.status_code == 200, r.text
    itens = r.json()["enrollments"]
    assert [m["id"] for m in itens] == [enrollment_id]
    texto = r.text
    for segredo in ("4321.99", ref, "tx-segredo-f2", "mercado_pago"):
        assert segredo not in texto, f"dado de pagamento vazou: {segredo}"
    proibidos = {"amount", "payment", "payments", "payment_method", "transaction_id", "external_reference",
                 "price", "password", "password_hash", "user_id"}
    assert not (proibidos & set(itens[0])), f"campo proibido na matricula: {proibidos & set(itens[0])}"
    assert "password" not in texto.lower()


def test_f3_identificador_de_usuario_na_query_e_ignorado(client, catalogo, adm):
    a = _matricula(CURSO_A, "active", email="f3.a@l1.test")
    b = _matricula(CURSO_A, "pending", email="f3.b@l1.test")
    uid = _sql("SELECT user_id FROM enrollments WHERE id = ?", (a,))[0]["user_id"]
    base = {m["id"] for m in _matriculas(client, adm, CURSO_A)}
    assert base == {a, b}
    for extra in ({"user_id": uid}, {"student_id": uid}, {"email": "f3.a@l1.test"}):
        r = client.get("/api/admin/enrollments", params={"course_id": CURSO_A, **extra}, headers=_auth(adm))
        assert r.status_code == 200, r.text
        assert {m["id"] for m in r.json()["enrollments"]} == base, f"{extra} nao pode filtrar nem identificar"


# =========================================================================================
# Grupo G - PUT /enrollments/{id}/class
# =========================================================================================

@pytest.mark.parametrize("status", ["pending", "active"])
def test_g1_atribui_matricula_pendente_ou_ativa(client, catalogo, adm, status):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, status)
    r = _atribuir(client, adm, m, t["id"])
    assert r.status_code == 200, r.text
    assert _class_id_no_banco(m) == t["id"]
    assert _status_no_banco(m) == status, "atribuir turma nao muda o status da matricula"
    item = [x for x in _matriculas(client, adm, CURSO_A) if x["id"] == m][0]
    assert item["class_id"] == t["id"]
    esperado = (1, 0, 1) if status == "active" else (0, 1, 1)
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == esperado


def test_g2_null_remove_a_matricula_da_turma(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Origem")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t["id"])
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 0, 1)
    r = _atribuir(client, adm, m, None)
    assert r.status_code == 200, r.text
    assert _class_id_no_banco(m) is None
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (0, 0, 0)
    assert _status_no_banco(m) == "active"


def test_g3_matricula_inexistente_404(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])  # a rota existe
    r = _atribuir(client, adm, 999999, t["id"])
    assert r.status_code == 404, r.text


def test_g4_turma_inexistente_404_e_nada_muda(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])
    r = _atribuir(client, adm, m, 999999)
    assert r.status_code == 404, r.text
    assert _class_id_no_banco(m) == t["id"], "turma inexistente nao pode soltar a matricula da turma atual"


def test_g5_class_id_com_tipo_invalido_422(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])
    r = client.put(f"/api/admin/enrollments/{m}/class", json={"class_id": "abc"}, headers=_auth(adm))
    assert r.status_code == 422, r.text
    assert _class_id_no_banco(m) == t["id"]


def test_g6_turma_de_outro_curso_409(client, catalogo, adm):
    tb = _turma(client, adm, CURSO_B, "Turma do B")
    m = _matricula(CURSO_A, "active")
    r = _atribuir(client, adm, m, tb["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_OUTRO
    assert _class_id_no_banco(m) is None
    assert _contagem(_turma_na_lista(client, adm, tb["id"])) == (0, 0, 0)


@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_g7_matricula_cancelada_ou_reembolsada_409(client, catalogo, adm, status):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, status)
    r = _atribuir(client, adm, m, t["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_STATUS
    assert _class_id_no_banco(m) is None
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (0, 0, 0)


def test_g8_turma_cheia_409(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Cheia", capacity=2)
    _atribuir_ok(client, adm, _matricula(CURSO_A, "pending"), t["id"])
    _atribuir_ok(client, adm, _matricula(CURSO_A, "active"), t["id"])
    extra = _matricula(CURSO_A, "active")
    r = _atribuir(client, adm, extra, t["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_CHEIA
    assert _class_id_no_banco(extra) is None
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 1, 2)


def test_g9_reatribuir_a_propria_matricula_a_turma_cheia_e_idempotente(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Cheia", capacity=1)
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t["id"])
    antes = _n_eventos_turma()
    r = _atribuir(client, adm, m, t["id"])
    assert r.status_code == 200, f"a propria matricula nao conta contra a capacidade: {r.text}"
    assert _class_id_no_banco(m) == t["id"]
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 0, 1)
    assert _n_eventos_turma() == antes, "atribuicao idempotente nao grava evento"


def test_g10_vaga_de_matricula_baixada_e_liberada(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Uma vaga", capacity=1)
    primeira = _matricula(CURSO_A, "active")
    segunda = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, primeira, t["id"])
    assert _atribuir(client, adm, segunda, t["id"]).status_code == 409
    _mudar_status(primeira, "refunded")
    r = _atribuir(client, adm, segunda, t["id"])
    assert r.status_code == 200, f"matricula reembolsada nao ocupa vaga: {r.text}"
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (1, 0, 1)


def test_g11_mudar_de_turma_atualiza_as_duas_contagens(client, catalogo, adm):
    t1 = _turma(client, adm, CURSO_A, "T1")
    t2 = _turma(client, adm, CURSO_A, "T2")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t1["id"])
    assert _contagem(_turma_na_lista(client, adm, t1["id"])) == (1, 0, 1)
    assert _contagem(_turma_na_lista(client, adm, t2["id"])) == (0, 0, 0)
    _atribuir_ok(client, adm, m, t2["id"])
    assert _contagem(_turma_na_lista(client, adm, t1["id"])) == (0, 0, 0)
    assert _contagem(_turma_na_lista(client, adm, t2["id"])) == (1, 0, 1)


def test_g12_mudar_para_turma_cheia_409_e_continua_na_turma_de_origem(client, catalogo, adm):
    t1 = _turma(client, adm, CURSO_A, "Origem")
    t2 = _turma(client, adm, CURSO_A, "Cheia", capacity=1)
    ocupante = _matricula(CURSO_A, "pending")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, ocupante, t2["id"])
    _atribuir_ok(client, adm, m, t1["id"])
    r = _atribuir(client, adm, m, t2["id"])
    assert r.status_code == 409, r.text
    assert _detalhe(r) == ERR_CHEIA
    assert _class_id_no_banco(m) == t1["id"]
    assert _contagem(_turma_na_lista(client, adm, t1["id"])) == (1, 0, 1)
    assert _contagem(_turma_na_lista(client, adm, t2["id"])) == (0, 1, 1)


def test_g13_turma_sem_capacidade_nao_tem_limite(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Sem teto")
    for _ in range(6):
        _atribuir_ok(client, adm, _matricula(CURSO_A, "pending"), t["id"])
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (0, 6, 6)


def test_g14_mudar_a_turma_nao_toca_matricula_de_outro_curso(client, catalogo, adm):
    ta = _turma(client, adm, CURSO_A, "TA")
    ta2 = _turma(client, adm, CURSO_A, "TA2")
    tb = _turma(client, adm, CURSO_B, "TB")
    user_id = Database.get_or_create_user("mesmo.aluno@l1.test", "Mesmo Aluno")
    ma = Database.create_enrollment(user_id, CURSO_A, f"a:{uuid.uuid4().hex}")
    mb = Database.create_enrollment(user_id, CURSO_B, f"b:{uuid.uuid4().hex}")
    _mudar_status(ma, "active")
    _mudar_status(mb, "active")
    _atribuir_ok(client, adm, mb, tb["id"])
    _atribuir_ok(client, adm, ma, ta["id"])
    _atribuir_ok(client, adm, ma, ta2["id"])
    _atribuir_ok(client, adm, ma, None)
    assert _class_id_no_banco(mb) == tb["id"], "a matricula do outro curso nao pode ser tocada"
    assert _status_no_banco(mb) == "active"
    assert _contagem(_turma_na_lista(client, adm, tb["id"])) == (1, 0, 1)
    # tentar levar a matricula do A para turma do B e recusado e nao mexe em nada
    assert _atribuir(client, adm, ma, tb["id"]).status_code == 409
    assert _class_id_no_banco(mb) == tb["id"] and _class_id_no_banco(ma) is None


def test_g15_corpo_com_identificadores_extras_nao_muda_o_alvo(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "Destino")
    alvo = _matricula(CURSO_A, "pending")
    outra = _matricula(CURSO_A, "pending")
    r = client.put(
        f"/api/admin/enrollments/{alvo}/class",
        json={"class_id": t["id"], "enrollment_id": outra, "user_id": 1, "course_id": CURSO_B},
        headers=_auth(adm),
    )
    assert r.status_code == 200, r.text
    assert _class_id_no_banco(alvo) == t["id"]
    assert _class_id_no_banco(outra) is None


# =========================================================================================
# Grupo H - Dashboard de cursos
# =========================================================================================

def test_h1_mantem_chaves_atuais_e_acrescenta_classes_e_unassigned(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "T1", starts_on="2026-10-10", capacity=8)
    e1 = _matricula(CURSO_A, "active")
    e2 = _matricula(CURSO_A, "pending")
    e6 = _matricula(CURSO_A, "active")
    for m in (e1, e2, e6):
        _atribuir_ok(client, adm, m, t["id"])
    _mudar_status(e6, "refunded")
    _matricula(CURSO_A, "active")      # e3, sem turma
    _matricula(CURSO_A, "pending")     # e4, sem turma
    _matricula(CURSO_A, "cancelled")   # e5, sem turma, nao conta em unassigned

    corpo = _dashboard(client, adm)
    assert corpo["status"] == "success"
    assert corpo["total_courses"] == 2
    curso = [c for c in corpo["courses"] if c["id"] == CURSO_A][0]
    assert CAMPOS_DASH_ANTIGOS <= set(curso), f"chaves atuais perdidas: {CAMPOS_DASH_ANTIGOS - set(curso)}"
    assert {"classes", "unassigned"} <= set(curso)
    assert curso["name"] == "Curso L1 A" and curso["price"] == 100.0 and curso["level"] == "Iniciante"
    assert curso["total_enrollments"] == 6
    assert curso["approved_enrollments"] == 2
    assert curso["pending_enrollments"] == 2
    assert curso["conversion_rate"] == round(2 / 6 * 100, 1)
    assert curso["unassigned"] == {"total": 2, "active": 1, "pending": 1}
    assert len(curso["classes"]) == 1
    turma = curso["classes"][0]
    assert set(turma) == CAMPOS_TURMA
    assert turma["id"] == t["id"] and turma["course_id"] == CURSO_A and turma["name"] == "T1"
    assert turma["starts_on"] == "2026-10-10" and turma["capacity"] == 8
    assert _contagem(turma) == (1, 1, 2), "a reembolsada atribuida nao conta"
    assert turma == _turma_na_lista(client, adm, t["id"]), "mesmo formato de GET /classes"


def test_h2_curso_sem_turma_devolve_classes_vazio_e_unassigned_zerado(client, catalogo, adm):
    curso = _curso_no_dashboard(client, adm, CURSO_B)
    assert curso["classes"] == []
    assert curso["unassigned"] == {"total": 0, "active": 0, "pending": 0}
    assert CAMPOS_DASH_ANTIGOS <= set(curso)
    # com matriculas e sem nenhuma turma, tudo e "sem turma"
    _matricula(CURSO_B, "active")
    _matricula(CURSO_B, "pending")
    _matricula(CURSO_B, "pending")
    curso = _curso_no_dashboard(client, adm, CURSO_B)
    assert curso["classes"] == []
    assert curso["unassigned"] == {"total": 3, "active": 1, "pending": 2}


def test_h3_turmas_em_ordem_de_data_e_depois_de_nome(client, catalogo, adm):
    # criadas fora de ordem de proposito
    for nome, data in [("Zeta", "2026-01-10"), ("Beta", "2026-03-01"), ("Gama", "2026-02-01"), ("Alfa", "2026-03-01")]:
        _turma(client, adm, CURSO_A, nome, starts_on=data)
    curso = _curso_no_dashboard(client, adm, CURSO_A)
    assert [t["name"] for t in curso["classes"]] == ["Zeta", "Gama", "Alfa", "Beta"]


def test_h4_atribuir_move_o_numero_de_sem_turma_para_a_turma(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "T")
    m = _matricula(CURSO_A, "active")
    p = _matricula(CURSO_A, "pending")
    assert _curso_no_dashboard(client, adm, CURSO_A)["unassigned"] == {"total": 2, "active": 1, "pending": 1}
    _atribuir_ok(client, adm, m, t["id"])
    curso = _curso_no_dashboard(client, adm, CURSO_A)
    assert curso["unassigned"] == {"total": 1, "active": 0, "pending": 1}
    assert _contagem(curso["classes"][0]) == (1, 0, 1)
    _atribuir_ok(client, adm, m, None)
    _atribuir_ok(client, adm, p, t["id"])
    curso = _curso_no_dashboard(client, adm, CURSO_A)
    assert curso["unassigned"] == {"total": 1, "active": 1, "pending": 0}
    assert _contagem(curso["classes"][0]) == (0, 1, 1)


def test_h5_baixada_atribuida_nao_conta_nem_em_turma_nem_em_sem_turma(client, catalogo, adm):
    t = _turma(client, adm, CURSO_A, "T")
    m = _matricula(CURSO_A, "active")
    _atribuir_ok(client, adm, m, t["id"])
    _mudar_status(m, "cancelled")
    curso = _curso_no_dashboard(client, adm, CURSO_A)
    assert _contagem(curso["classes"][0]) == (0, 0, 0)
    assert curso["unassigned"] == {"total": 0, "active": 0, "pending": 0}
    assert curso["total_enrollments"] == 1 and curso["approved_enrollments"] == 0


def test_h6_turmas_de_um_curso_nao_aparecem_no_outro(client, catalogo, adm):
    ta = _turma(client, adm, CURSO_A, "So no A")
    tb = _turma(client, adm, CURSO_B, "So no B")
    assert [t["id"] for t in _curso_no_dashboard(client, adm, CURSO_A)["classes"]] == [ta["id"]]
    assert [t["id"] for t in _curso_no_dashboard(client, adm, CURSO_B)["classes"]] == [tb["id"]]


def test_h7_ordem_dos_cursos_do_dashboard_continua_por_inscricoes(client, catalogo, adm):
    _matricula(CURSO_B, "active")
    _matricula(CURSO_B, "pending")
    _matricula(CURSO_A, "active")
    ids = [c["id"] for c in _dashboard(client, adm)["courses"]]
    assert ids == [CURSO_B, CURSO_A]
    _turma(client, adm, CURSO_A, "T")  # a existencia de turmas nao muda a ordem
    assert [c["id"] for c in _dashboard(client, adm)["courses"]] == [CURSO_B, CURSO_A]


# =========================================================================================
# Grupo I - RBAC
# =========================================================================================

LEITURA_LIVRE = {  # classes e dashboard: qualquer funcionario
    "gestao_jwt": 200, "suporte_jwt": 200, "financeiro_jwt": 200, "aluno_jwt": 403,
    "gestao_legado": 200, "suporte_legado": 200, "financeiro_legado": 200,
    "sem_token": 401, "token_forjado": 401,
}
LEITURA_SEM_FINANCEIRO = {**LEITURA_LIVRE, "financeiro_jwt": 403, "financeiro_legado": 403}
SO_GESTAO = {
    "gestao_jwt": 200, "suporte_jwt": 403, "financeiro_jwt": 403, "aluno_jwt": 403,
    "gestao_legado": 200, "suporte_legado": 403, "financeiro_legado": 403,
    "sem_token": 401, "token_forjado": 401,
}


def _matriz(tabela):
    return [pytest.param(nome, codigo, id=f"{nome}-{codigo}") for nome, codigo in tabela.items()]


@pytest.mark.parametrize("quem,esperado", _matriz(LEITURA_LIVRE))
def test_i1_get_classes(client, catalogo, ident, adm, quem, esperado):
    _turma(client, adm, CURSO_A, "T")
    r = client.get("/api/admin/classes", headers=_auth(ident[quem]))
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    if esperado == 200:
        assert len(r.json()["classes"]) == 1


@pytest.mark.parametrize("quem,esperado", _matriz(LEITURA_SEM_FINANCEIRO))
def test_i2_get_enrollments(client, catalogo, ident, adm, quem, esperado):
    _matricula(CURSO_A, "pending")
    r = client.get("/api/admin/enrollments", params={"course_id": CURSO_A}, headers=_auth(ident[quem]))
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    if esperado == 200:
        assert len(r.json()["enrollments"]) == 1


@pytest.mark.parametrize("quem,esperado", _matriz(LEITURA_LIVRE))
def test_i3_dashboard_cursos_com_turmas(client, catalogo, ident, adm, quem, esperado):
    t = _turma(client, adm, CURSO_A, "T")
    r = client.get("/api/dashboard/cursos", headers=_auth(ident[quem]))
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    if esperado == 200:
        curso = [c for c in r.json()["courses"] if c["id"] == CURSO_A][0]
        assert [x["id"] for x in curso["classes"]] == [t["id"]]


@pytest.mark.parametrize("quem,esperado", _matriz(SO_GESTAO))
def test_i4_post_classes(client, catalogo, ident, quem, esperado):
    antes = _n_eventos_turma()
    r = _criar_turma(client, ident[quem], CURSO_A, f"Turma {quem}")
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    assert _n_turmas() == (1 if esperado == 200 else 0)
    assert _n_eventos_turma() == antes + (1 if esperado == 200 else 0)


@pytest.mark.parametrize("quem,esperado", _matriz(SO_GESTAO))
def test_i5_put_classes(client, catalogo, ident, adm, quem, esperado):
    t = _turma(client, adm, CURSO_A, "Original", capacity=4)
    antes = _n_eventos_turma()
    r = _put_turma(client, ident[quem], t["id"], {"name": "Alterada", "capacity": 9})
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    linha = _turma_na_lista(client, adm, t["id"])
    if esperado == 200:
        assert (linha["name"], linha["capacity"]) == ("Alterada", 9)
        assert _n_eventos_turma() == antes + 1
    else:
        assert (linha["name"], linha["capacity"]) == ("Original", 4)
        assert _n_eventos_turma() == antes


@pytest.mark.parametrize("quem,esperado", _matriz(SO_GESTAO))
def test_i6_delete_classes(client, catalogo, ident, adm, quem, esperado):
    t = _turma(client, adm, CURSO_A, "Removivel")
    antes = _n_eventos_turma()
    r = _del_turma(client, ident[quem], t["id"])
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    assert _n_turmas() == (0 if esperado == 200 else 1)
    assert _n_eventos_turma() == antes + (1 if esperado == 200 else 0)


@pytest.mark.parametrize("quem,esperado", _matriz(SO_GESTAO))
def test_i7_put_enrollment_class(client, catalogo, ident, adm, quem, esperado):
    t = _turma(client, adm, CURSO_A, "Destino")
    m = _matricula(CURSO_A, "pending")
    antes = _n_eventos_turma()
    r = _atribuir(client, ident[quem], m, t["id"])
    assert r.status_code == esperado, f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    assert _class_id_no_banco(m) == (t["id"] if esperado == 200 else None)
    assert _n_eventos_turma() == antes + (1 if esperado == 200 else 0)


# =========================================================================================
# Grupo J - Auditoria (E8)
# =========================================================================================

def test_j1_class_create(client, catalogo, contas):
    t = _turma(client, contas.ana.token, CURSO_A, "Turma Auditada", starts_on="2026-11-05", capacity=12)
    ev = _unico(_eventos("class.create"), "class.create")
    _checar_ator(ev, contas.ana)
    assert ev["entity_type"] == "class"
    assert str(ev["entity_id"]) == str(t["id"])
    assert ev["detail"], "detail deve vir preenchido"
    _checar_changes_turma(ev, {
        "name": (None, "Turma Auditada"), "starts_on": (None, "2026-11-05"), "capacity": (None, 12),
    })


def test_j2_class_create_sem_data_e_capacidade(client, catalogo, contas):
    _turma(client, contas.ana.token, CURSO_A, "Turma Simples")
    ev = _unico(_eventos("class.create"), "class.create")
    _checar_changes_turma(ev, {"name": (None, "Turma Simples")})


def test_j3_class_update_so_os_campos_alterados(client, catalogo, contas):
    t = _turma(client, contas.ana.token, CURSO_A, "Antes", starts_on="2026-10-01", capacity=10)
    r = _put_turma(client, contas.bruno.token, t["id"], {"name": "Depois", "capacity": 20})
    assert r.status_code == 200, r.text
    ev = _unico(_eventos("class.update"), "class.update")
    _checar_ator(ev, contas.bruno)
    assert ev["entity_type"] == "class" and str(ev["entity_id"]) == str(t["id"])
    _checar_changes_turma(ev, {"name": ("Antes", "Depois"), "capacity": (10, 20)})
    # null que limpa tambem e registrado
    assert _put_turma(client, contas.bruno.token, t["id"], {"starts_on": None, "capacity": None}).status_code == 200
    ev2 = _eventos("class.update")[-1]
    assert len(_eventos("class.update")) == 2
    _checar_changes_turma(ev2, {"starts_on": ("2026-10-01", None), "capacity": (20, None)})


def test_j4_class_delete(client, catalogo, contas):
    t = _turma(client, contas.ana.token, CURSO_A, "Vai Sair", starts_on="2026-10-01", capacity=7)
    assert _del_turma(client, contas.bruno.token, t["id"]).status_code == 200
    ev = _unico(_eventos("class.delete"), "class.delete")
    _checar_ator(ev, contas.bruno)
    assert ev["entity_type"] == "class" and str(ev["entity_id"]) == str(t["id"])
    _checar_changes_turma(ev, {
        "name": ("Vai Sair", None), "starts_on": ("2026-10-01", None), "capacity": (7, None),
    })


def test_j5_enrollment_class_change_atribuir_mover_e_remover(client, catalogo, contas):
    adm = contas.ana.token
    t1 = _turma(client, adm, CURSO_A, "T1")
    t2 = _turma(client, adm, CURSO_A, "T2")
    m = _matricula(CURSO_A, "active")
    n_antes = _n_eventos_turma()
    _atribuir_ok(client, contas.bruno.token, m, t1["id"])
    _atribuir_ok(client, adm, m, t2["id"])
    _atribuir_ok(client, contas.bruno.token, m, None)
    eventos = _eventos("enrollment.class_change")
    assert len(eventos) == 3, eventos
    assert _n_eventos_turma() == n_antes + 3
    esperado = [(None, t1["id"], contas.bruno), (t1["id"], t2["id"], contas.ana), (t2["id"], None, contas.bruno)]
    for ev, (antes, depois, pessoa) in zip(eventos, esperado):
        _checar_ator(ev, pessoa)
        assert ev["entity_type"] == "enrollment" and str(ev["entity_id"]) == str(m)
        assert ev["detail"]
        mud = _mudancas(ev)
        assert set(mud) == {"class_id"}, f"so class_id em changes: {sorted(mud)}"
        assert _igual(mud["class_id"]["before"], antes), mud
        assert _igual(mud["class_id"]["after"], depois), mud


def test_j6_login_administrativo_legado_de_gestao_e_registrado_como_tal(client, catalogo, ident):
    token = ident["gestao_legado"]
    t = _turma(client, token, CURSO_A, "Legada", capacity=3)
    m = _matricula(CURSO_A, "pending")
    assert _put_turma(client, token, t["id"], {"capacity": 4}).status_code == 200
    _atribuir_ok(client, token, m, t["id"])
    _atribuir_ok(client, token, m, None)
    assert _del_turma(client, token, t["id"]).status_code == 200
    for acao, n in (("class.create", 1), ("class.update", 1), ("class.delete", 1), ("enrollment.class_change", 2)):
        eventos = _eventos(acao)
        assert len(eventos) == n, (acao, eventos)
        for ev in eventos:
            _checar_ator_legado(ev, "admin")


def test_j7_responsavel_enviado_no_corpo_e_ignorado(client, catalogo, contas):
    falso = {"user_id": contas.bruno.id, "actor_email": "falso@l1.test", "actor_name": "Falso",
             "role": "support", "created_by": contas.bruno.id}
    ana = contas.ana.token
    r = client.post("/api/admin/classes", json={"course_id": CURSO_A, "name": "Com ator falso", **falso},
                    headers=_auth(ana))
    assert r.status_code == 200, r.text
    tid = r.json()["class"]["id"]
    r = client.put(f"/api/admin/classes/{tid}", json={"capacity": 5, **falso}, headers=_auth(ana))
    assert r.status_code == 200, r.text
    m = _matricula(CURSO_A, "pending")
    r = client.put(f"/api/admin/enrollments/{m}/class", json={"class_id": tid, **falso}, headers=_auth(ana))
    assert r.status_code == 200, r.text
    for acao in ("class.create", "class.update", "enrollment.class_change"):
        _checar_ator(_unico(_eventos(acao), acao), contas.ana)
    assert "falso@l1.test" not in json.dumps(_eventos(), default=str)


def test_j8_atribuicao_idempotente_nao_grava_evento(client, catalogo, contas):
    adm = contas.ana.token
    t = _turma(client, adm, CURSO_A, "T")
    m = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, m, t["id"])
    assert len(_eventos("enrollment.class_change")) == 1
    for _ in range(3):
        assert _atribuir(client, adm, m, t["id"]).status_code == 200
    assert len(_eventos("enrollment.class_change")) == 1


def test_j9_operacao_recusada_nao_grava_evento(client, catalogo, contas, ident):
    adm = contas.ana.token
    t1 = _turma(client, adm, CURSO_A, "T1", capacity=1)
    tb = _turma(client, adm, CURSO_B, "TB")
    ocupante = _matricula(CURSO_A, "pending")
    _atribuir_ok(client, adm, ocupante, t1["id"])
    baixada = _matricula(CURSO_A, "cancelled")
    reembolsada = _matricula(CURSO_A, "refunded")
    candidato = _matricula(CURSO_A, "active")
    do_b = _matricula(CURSO_B, "active")
    base = _n_eventos_turma()
    assert base == 3  # criacao de T1, criacao de TB e a atribuicao do ocupante

    def req(metodo, url, corpo=None, quem="gestao_jwt"):
        return client.request(metodo, url, json=corpo, headers=_auth(ident[quem]))

    recusadas = [
        ("curso inexistente", "POST", "/api/admin/classes", {"course_id": "nao_existe", "name": "X"}, 404),
        ("nome repetido", "POST", "/api/admin/classes", {"course_id": CURSO_A, "name": "T1"}, 409),
        ("capacidade zero", "POST", "/api/admin/classes", {"course_id": CURSO_A, "name": "Z", "capacity": 0}, 422),
        ("data invalida", "POST", "/api/admin/classes", {"course_id": CURSO_A, "name": "D", "starts_on": "x"}, 422),
        ("put inexistente", "PUT", "/api/admin/classes/999999", {"name": "Y"}, 404),
        ("put capacidade zero", "PUT", f"/api/admin/classes/{t1['id']}", {"capacity": 0}, 422),
        ("delete inexistente", "DELETE", "/api/admin/classes/999999", None, 404),
        ("delete com matriculas", "DELETE", f"/api/admin/classes/{t1['id']}", None, 409),
        ("matricula inexistente", "PUT", "/api/admin/enrollments/999999/class", {"class_id": t1["id"]}, 404),
        ("turma inexistente", "PUT", f"/api/admin/enrollments/{candidato}/class", {"class_id": 999999}, 404),
        ("outro curso", "PUT", f"/api/admin/enrollments/{candidato}/class", {"class_id": tb["id"]}, 409),
        ("matricula cancelada", "PUT", f"/api/admin/enrollments/{baixada}/class", {"class_id": t1["id"]}, 409),
        ("matricula reembolsada", "PUT", f"/api/admin/enrollments/{reembolsada}/class", {"class_id": t1["id"]}, 409),
        ("turma cheia", "PUT", f"/api/admin/enrollments/{candidato}/class", {"class_id": t1["id"]}, 409),
        ("matricula do B na turma do A", "PUT", f"/api/admin/enrollments/{do_b}/class", {"class_id": t1["id"]}, 409),
        ("suporte cria", "POST", "/api/admin/classes", {"course_id": CURSO_A, "name": "S"}, 403, "suporte_jwt"),
        ("financeiro atribui", "PUT", f"/api/admin/enrollments/{candidato}/class", {"class_id": tb["id"]}, 403,
         "financeiro_jwt"),
        ("sem token apaga", "DELETE", f"/api/admin/classes/{tb['id']}", None, 401, "sem_token"),
        ("token forjado edita", "PUT", f"/api/admin/classes/{tb['id']}", {"name": "H"}, 401, "token_forjado"),
    ]
    for item in recusadas:
        descricao, metodo, url, corpo, esperado = item[:5]
        quem = item[5] if len(item) > 5 else "gestao_jwt"
        r = req(metodo, url, corpo, quem)
        assert r.status_code == esperado, f"{descricao}: HTTP {r.status_code} {r.text[:200]}"
    assert _n_eventos_turma() == base, "nenhuma operacao recusada pode gravar evento de turma"
    assert _class_id_no_banco(candidato) is None and _class_id_no_banco(do_b) is None
    assert _n_turmas() == 2


# =========================================================================================
# Grupo K - Recurso pago so com matricula ativa
# =========================================================================================

def _token_aluno(user_id, email):
    return create_access_token({"user_id": user_id, "email": email, "role": "student"})


def _minhas(client, token):
    r = client.get("/api/student/enrollments", headers=_auth(token))
    assert r.status_code == 200, f"GET /api/student/enrollments: HTTP {r.status_code} {r.text[:200]}"
    return r


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_k1_turma_nao_libera_material_sem_matricula_ativa(client, catalogo, adm, status):
    email = f"aluno.k1.{status}@l1.test"
    user_id = Database.get_or_create_user(email, "Aluno K1")
    t = _turma(client, adm, CURSO_A, "T")
    m = Database.create_enrollment(user_id, CURSO_A, f"{CURSO_A}:k1:{uuid.uuid4().hex}")
    # pending e atribuida pela rota; cancelled/refunded foram atribuidas como pending e baixadas depois
    _atribuir_ok(client, adm, m, t["id"])
    if status != "pending":
        _mudar_status(m, status)
    assert _status_no_banco(m) == status

    r = _minhas(client, _token_aluno(user_id, email))
    itens = [i for i in r.json()["enrollments"] if i["id"] == m]
    assert len(itens) == 1 and itens[0]["status"] == status
    assert not itens[0].get("materials"), f"matricula {status} nao pode trazer materiais"
    assert URL_A1 not in r.text and URL_A2 not in r.text, f"URL de material vazou na matricula {status}"


def test_k2_atribuir_turma_nao_ativa_a_matricula_pendente(client, catalogo, adm):
    email = "aluno.k2@l1.test"
    user_id = Database.get_or_create_user(email, "Aluno K2")
    t = _turma(client, adm, CURSO_A, "T")
    m = Database.create_enrollment(user_id, CURSO_A, f"{CURSO_A}:k2:{uuid.uuid4().hex}")
    _atribuir_ok(client, adm, m, t["id"])
    assert _status_no_banco(m) == "pending"
    r = _minhas(client, _token_aluno(user_id, email))
    assert URL_A1 not in r.text and URL_A2 not in r.text
    assert _contagem(_turma_na_lista(client, adm, t["id"])) == (0, 1, 1)


def test_k3_matricula_ativa_com_turma_continua_recebendo_os_materiais(client, catalogo, adm):
    email = "aluno.k3@l1.test"
    user_id = Database.get_or_create_user(email, "Aluno K3")
    t = _turma(client, adm, CURSO_A, "T")
    m = Database.create_enrollment(user_id, CURSO_A, f"{CURSO_A}:k3:{uuid.uuid4().hex}")
    _mudar_status(m, "active")
    _atribuir_ok(client, adm, m, t["id"])
    r = _minhas(client, _token_aluno(user_id, email))
    item = [i for i in r.json()["enrollments"] if i["id"] == m][0]
    assert {x["url"] for x in item["materials"]} == {URL_A1, URL_A2}


def test_k4_o_aluno_nao_usa_as_rotas_de_turma(client, catalogo, adm):
    email = "aluno.k4@l1.test"
    user_id = Database.get_or_create_user(email, "Aluno K4")
    token = _token_aluno(user_id, email)
    t = _turma(client, adm, CURSO_A, "T")
    m = Database.create_enrollment(user_id, CURSO_A, f"{CURSO_A}:k4:{uuid.uuid4().hex}")
    assert _atribuir(client, token, m, t["id"]).status_code == 403
    assert client.get("/api/admin/classes", headers=_auth(token)).status_code == 403
    assert client.get("/api/admin/enrollments", params={"course_id": CURSO_A}, headers=_auth(token)).status_code == 403
    assert _class_id_no_banco(m) is None
