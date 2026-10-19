"""F1 - Trava de exclusao de curso e arquivar curso (PLANO_FEEDBACK_PROF.md, F1; politica na D68; modo autonomo D69).

Escritos ANTES da implementacao. Devem falhar agora: DELETE /api/admin/course/{id} apaga o curso mesmo com
matriculas, nao existem as rotas /archive e /unarchive, o campo `archived` nao e lido em lugar nenhum (catalogo
publico, chatbot, checkouts) e /api/admin/courses e /api/dashboard/cursos nao trazem `archived`/`enrollments_count`.

Contrato (decisoes de forma do orquestrador; politica na D68):
  1. DELETE com QUALQUER matricula do curso (pending, active, cancelled, refunded) -> 409 com DETAIL_BLOQUEIO; o
     JSON continua igual, nada muda, e grava `course.delete_blocked` (entity_type course, entity_id = id). Sem
     matricula -> 200 como hoje, as turmas do curso saem junto e grava `course.delete`.
  2. POST /api/admin/course/{id}/archive e /unarchive: so Gestao (Financeiro/Suporte/aluno 403; sem token ou forjado
     401; inexistente 404 "Course not found"). Gravam "archived": true/false no JSON; idempotentes (sem evento novo);
     eventos `course.archive` / `course.unarchive` com change `archived` false->true / true->false.
  3. Curso arquivado: some de GET /api/courses e do chatbot; os dois checkouts devolvem 409 DETAIL_INDISPONIVEL sem
     criar nada; o aluno `active` continua vendo o curso e os materiais em /api/student/enrollments; materiais so
     com `active`.
  4. GET /api/admin/courses: `archived` (bool, padrao false) e `enrollments_count` (int, todas as matriculas) em cada
     item. GET /api/dashboard/cursos: `archived` em cada curso.
  5. Compatibilidade: curso sem a chave `archived` vale como nao arquivado; create/update do admin aceitam `archived`
     opcional; editar sem mandar `archived` preserva o valor.

Grupos
  A  Trava de exclusao (os quatro status, auditoria, nada muda, isolamento entre cursos)
  B  Exclusao permitida sem matricula (turmas removidas, course.delete)
  C  Arquivar / desarquivar (JSON, eventos, idempotencia, 404)
  D  RBAC e IDOR (403/401 nas rotas novas e no DELETE; corpo nao define o responsavel)
  E  Catalogo publico e listagens da Gestao (archived, enrollments_count, dashboard)
  F  Checkouts (landing e aluno, inclusive com o pagamento simulado efetivo)
  G  Aluno com matricula ativa no curso arquivado; recurso pago so com `active`
  H  Chatbot nao oferece curso arquivado (catalogo do bot em diretorio temporario, D70)
  I  Compatibilidade e schema de escrita do admin

Convencoes: banco temporario do conftest; cursos em diretorio temporario (padrao de test_l1_turmas: COURSES_DIR e
__file__ de admin.routes); o ManagerAgent le o MESMO diretorio temporario (seam de teste igual ao `catalogo_bot` do
conftest, D70); LLM falso por patch de GroqChatClient.create_chat_completion; Mercado Pago falso por patch de
payments.routes.requests.post; PAYMENTS_MOCK/APP_ENV removidos do ambiente. Nenhum teste toca backend/db.sqlite,
backend/courses, o Groq ou a rede.

Escolhas conservadoras (ver relatorio): o corpo de sucesso de archive/unarchive nao e fixado (so o HTTP 200); no
arquivar, campos originais do JSON nao podem mudar, mas chaves novas (ex.: updated_at) sao toleradas; na operacao
idempotente nao se exige reescrita do arquivo; o responsavel dos eventos novos e o dono do token (padrao E8); o
chatbot e verificado pelo que chega ao LLM (nenhuma mensagem de sistema cita o curso arquivado e o Course Agent dele
nunca e usado, nem quando o roteamento do LLM devolve o id arquivado).
"""

import json
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"

DETAIL_BLOQUEIO = ("Não é possível excluir: o curso tem alunos matriculados. "
                   "Arquive o curso para tirá-lo do catálogo.")
DETAIL_INDISPONIVEL = "Este curso não está disponível para novas matrículas."
DETAIL_404 = "Course not found"

CURSO_A = "curso_f1_alfa"      # fica disponivel
CURSO_Z = "curso_f1_zeta"      # e arquivado nos testes
NOME_A = "Curso Alfa Disponivel"
NOME_Z = "Curso Zeta Legado"
MARCA_Z = "MARCA-PROMPT-ZETA-F1"
URL_Z = "https://materiais.test/f1/zeta-apostila.pdf"
URL_A = "https://materiais.test/f1/alfa-apostila.pdf"
PRECO_Z = 321.5
STATUS = ("pending", "active", "cancelled", "refunded")
URL_GATEWAY = "https://mp.test/f1/checkout"


# =========================================================================================
# Fixtures
# =========================================================================================

def _foto_repo():
    if not REPO_COURSES.exists():
        return []
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


@pytest.fixture(autouse=True)
def ambiente_f1(monkeypatch, tmp_path):
    """Pagamento simulado desligado; token de gateway de teste; nada vem do backend/.env local."""
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-f1")
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


def _dados_curso(course_id, nome, preco, url, marca, **extra):
    return {
        "id": course_id, "name": nome, "description": f"Descricao de {nome}", "price": preco,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Todos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta?", "answer": "Resposta."}],
        "system_prompt": f"Voce e o assistente do {nome}. {marca}",
        "materials": [{"title": f"Apostila {nome}", "url": url, "type": "pdf"}],
        **extra,
    }


def _escrever(diretorio, dados):
    (diretorio / f"{dados['id']}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Dois cursos em diretorio temporario, ambos SEM a chave `archived` (dado antigo)."""
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _escrever(diretorio, _dados_curso(CURSO_A, NOME_A, 100.0, URL_A, "MARCA-PROMPT-ALFA-F1"))
    _escrever(diretorio, _dados_curso(CURSO_Z, NOME_Z, PRECO_Z, URL_Z, MARCA_Z))
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses (deveria usar o diretorio temporario)"


@pytest.fixture
def bot_no_diretorio_temporario(cursos, monkeypatch):
    """Seam de teste (mesmo padrao do `catalogo_bot`, D70): o ManagerAgent le o diretorio temporario dos cursos."""
    from agents.manager_agent import ManagerAgent

    construtor_original = ManagerAgent.__init__

    def construtor(self, *args, **kwargs):
        construtor_original(self, *args, **kwargs)
        self.courses_dir = cursos

    monkeypatch.setattr(ManagerAgent, "__init__", construtor)
    return cursos


@pytest.fixture
def client(banco, cursos, bot_no_diretorio_temporario):
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
        ana=_conta("ana.gestora@f1.test", "Ana Gestora", "admin"),
        bruno=_conta("bruno.gestor@f1.test", "Bruno Gestor", "admin"),
        sup=_conta("sergio.sup@f1.test", "Sergio Suporte", "support"),
        fin=_conta("fernanda.fin@f1.test", "Fernanda Financeira", "financial"),
        aluno=_conta("aluno.f1@f1.test", "Aluno F1", "student"),
        aluna=_conta("aluna.f1@f1.test", "Aluna F1", "student"),
    )


def _forjado(role="admin"):
    return jose_jwt.encode(
        {"user_id": 1, "email": "x@f1.test", "role": role},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []

    def post(self, url, *args, **kwargs):
        self.post_chamadas.append((url, kwargs))
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": "pref-f1", "init_point": URL_GATEWAY}
        resposta.text = '{"id": "pref-f1"}'
        return resposta


@pytest.fixture
def gw():
    falso = GatewayFalso()
    with patch("payments.routes.requests.post", side_effect=falso.post):
        yield falso


class LLMFalso:
    """Substitui GroqChatClient.create_chat_completion (manager e course agents). Guarda tudo o que chega ao LLM."""

    def __init__(self, rota="GENERAL"):
        self.rota = rota
        self.chamadas = []

    def responder(self, messages):
        self.chamadas.append([dict(m) for m in messages])
        if messages and "identifica intenções" in (messages[0].get("content") or ""):
            return self.rota
        return "Temos otimos cursos para voce."

    def mensagens_de_sistema(self):
        return [m.get("content") or "" for chamada in self.chamadas for m in chamada if m.get("role") == "system"]

    def todo_o_texto(self):
        return "\n".join(m.get("content") or "" for chamada in self.chamadas for m in chamada)


@pytest.fixture
def llm(monkeypatch):
    from agents.groq_client import GroqChatClient

    falso = LLMFalso()

    def create_chat_completion(self, messages, max_tokens=1024, temperature=0.7):
        return falso.responder(messages)

    monkeypatch.setattr(GroqChatClient, "create_chat_completion", create_chat_completion)
    return falso


# =========================================================================================
# Helpers
# =========================================================================================

def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


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


def _matricula(course_id, status="pending", user_id=None):
    """Matricula real (create_enrollment); o status e levado por SQL so para montar o estado."""
    if user_id is None:
        sufixo = uuid.uuid4().hex[:8]
        user_id = Database.get_or_create_user(f"aluno.{sufixo}@f1.test", f"Aluno {sufixo}")
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:f1:{uuid.uuid4().hex}")
    if status != "pending":
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))
    return enrollment_id


def _arquivo(cursos, course_id):
    return cursos / f"{course_id}.json"


def _ler(cursos, course_id):
    return json.loads(_arquivo(cursos, course_id).read_text(encoding="utf-8"))


def _eventos(action=None, entity_id=None):
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    if action is not None:
        sql += " AND action = ?"
        params.append(action)
    if entity_id is not None:
        sql += " AND entity_id = ?"
        params.append(str(entity_id))
    return _sql(sql + " ORDER BY id", tuple(params))


def _eventos_de_curso():
    return _sql("SELECT * FROM audit_logs WHERE action LIKE 'course.%' ORDER BY id")


def _changes(evento):
    bruto = evento.get("changes")
    return json.loads(bruto) if isinstance(bruto, str) else (bruto or [])


def _arquivar(client, token, course_id, **kwargs):
    return client.post(f"/api/admin/course/{course_id}/archive", headers=_auth(token), **kwargs)


def _desarquivar(client, token, course_id, **kwargs):
    return client.post(f"/api/admin/course/{course_id}/unarchive", headers=_auth(token), **kwargs)


def _excluir(client, token, course_id):
    return client.delete(f"/api/admin/course/{course_id}", headers=_auth(token))


def _arquivado_ok(client, token, course_id):
    r = _arquivar(client, token, course_id)
    assert r.status_code == 200, f"archive: HTTP {r.status_code} {r.text[:300]}"
    return r


def _ids_publicos(client):
    r = client.get("/api/courses")
    assert r.status_code == 200, r.text
    return [c.get("id") for c in r.json()["courses"]]


def _item_admin(client, token, course_id):
    r = client.get("/api/admin/courses", headers=_auth(token))
    assert r.status_code == 200, r.text
    itens = [c for c in r.json()["courses"] if c.get("id") == course_id]
    assert len(itens) == 1, f"{course_id} deveria aparecer uma vez na lista da Gestao: {r.json()}"
    return itens[0]


def _curso_dashboard(client, token, course_id):
    r = client.get("/api/dashboard/cursos", headers=_auth(token))
    assert r.status_code == 200, r.text
    itens = [c for c in r.json()["courses"] if c.get("id") == course_id]
    assert len(itens) == 1, f"{course_id} deveria aparecer uma vez no dashboard de cursos: {r.json()}"
    return itens[0]


def _checkout_landing(client, course_id, email=None):
    email = email or f"comprador.{uuid.uuid4().hex[:8]}@f1.test"
    return client.post("/api/payments/create-checkout",
                       json={"course_id": course_id, "payer": {"name": "Comprador F1", "email": email}})


def _checkout_aluno(client, token, course_id):
    return client.post("/api/student/checkout", json={"course_id": course_id}, headers=_auth(token))


def _contagens():
    return {
        "users": _sql("SELECT COUNT(*) AS n FROM users")[0]["n"],
        "enrollments": _sql("SELECT COUNT(*) AS n FROM enrollments")[0]["n"],
        "payments": _sql("SELECT COUNT(*) AS n FROM payments")[0]["n"],
    }


# =========================================================================================
# A - Trava de exclusao
# =========================================================================================

@pytest.mark.parametrize("status", STATUS)
def test_a1_excluir_curso_com_matricula_em_qualquer_status_devolve_409(client, contas, cursos, status):
    matricula = _matricula(CURSO_Z, status)
    conteudo_antes = _arquivo(cursos, CURSO_Z).read_bytes()
    matriculas_antes = _sql("SELECT * FROM enrollments ORDER BY id")

    r = _excluir(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 409, f"status {status}: HTTP {r.status_code} {r.text[:300]}"
    assert r.json() == {"detail": DETAIL_BLOQUEIO}
    assert _arquivo(cursos, CURSO_Z).exists(), "o arquivo do curso foi apagado apesar da matricula"
    assert _arquivo(cursos, CURSO_Z).read_bytes() == conteudo_antes, "o JSON do curso mudou"
    assert _sql("SELECT * FROM enrollments ORDER BY id") == matriculas_antes, "as matriculas mudaram"
    assert _sql("SELECT status FROM enrollments WHERE id = ?", (matricula,))[0]["status"] == status
    assert _eventos("course.delete") == [], "a exclusao bloqueada nao pode gravar course.delete"


@pytest.mark.parametrize("status", STATUS)
def test_a2_exclusao_bloqueada_grava_course_delete_blocked(client, contas, status):
    _matricula(CURSO_Z, status)

    r = _excluir(client, contas.ana.token, CURSO_Z)
    assert r.status_code == 409, r.text

    eventos = _eventos("course.delete_blocked")
    assert len(eventos) == 1, eventos
    ev = eventos[0]
    assert ev["entity_type"] == "course"
    assert ev["entity_id"] == CURSO_Z
    # Responsavel vem do token (padrao E8).
    assert ev["user_id"] == contas.ana.id
    assert ev["actor_email"] == contas.ana.email
    assert ev["role"] == "admin"


def test_a3_curso_com_matricula_continua_no_catalogo_depois_do_bloqueio(client, contas):
    _matricula(CURSO_Z, "active")
    assert _excluir(client, contas.ana.token, CURSO_Z).status_code == 409
    assert CURSO_Z in _ids_publicos(client)
    r = client.get(f"/api/admin/course/{CURSO_Z}", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text


def test_a4_exclusao_bloqueada_nao_remove_turmas_do_curso(client, contas):
    r = client.post("/api/admin/classes", json={"course_id": CURSO_Z, "name": "Turma Z"},
                    headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    _matricula(CURSO_Z, "cancelled")

    assert _excluir(client, contas.ana.token, CURSO_Z).status_code == 409
    assert len(_sql("SELECT * FROM classes WHERE course_id = ?", (CURSO_Z,))) == 1


def test_a5_matricula_de_outro_curso_nao_bloqueia(client, contas, cursos):
    _matricula(CURSO_A, "active")  # so o curso A tem aluno

    r = _excluir(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 200, r.text
    assert not _arquivo(cursos, CURSO_Z).exists()
    assert _arquivo(cursos, CURSO_A).exists()


def test_a6_curso_arquivado_com_matricula_tambem_nao_pode_ser_excluido(client, contas, cursos):
    _matricula(CURSO_Z, "refunded")
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = _excluir(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 409, r.text
    assert r.json() == {"detail": DETAIL_BLOQUEIO}
    assert _arquivo(cursos, CURSO_Z).exists()


# =========================================================================================
# B - Exclusao permitida (sem matricula)
# =========================================================================================

def test_b1_curso_sem_matricula_e_excluido_como_hoje(client, contas, cursos):
    r = _excluir(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 200, r.text
    assert r.json().get("status") == "success"
    assert not _arquivo(cursos, CURSO_Z).exists()
    assert CURSO_Z not in _ids_publicos(client)
    eventos = _eventos("course.delete", CURSO_Z)
    assert len(eventos) == 1, eventos
    assert eventos[0]["entity_type"] == "course"
    assert eventos[0]["user_id"] == contas.ana.id
    assert _eventos("course.delete_blocked") == []


def test_b2_excluir_curso_sem_aluno_remove_as_turmas_dele(client, contas):
    for curso, nome in ((CURSO_Z, "Turma Z1"), (CURSO_Z, "Turma Z2"), (CURSO_A, "Turma A1")):
        r = client.post("/api/admin/classes", json={"course_id": curso, "name": nome},
                        headers=_auth(contas.ana.token))
        assert r.status_code == 200, r.text

    r = _excluir(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 200, r.text
    assert _sql("SELECT * FROM classes WHERE course_id = ?", (CURSO_Z,)) == [], \
        "as turmas (sem alunos) do curso excluido deveriam sair junto"
    restantes = _sql("SELECT name FROM classes WHERE course_id = ?", (CURSO_A,))
    assert [t["name"] for t in restantes] == ["Turma A1"], "turmas de outro curso nao podem ser removidas"


def test_b3_excluir_curso_inexistente_continua_404(client, contas):
    r = _excluir(client, contas.ana.token, "curso_que_nao_existe_f1")
    assert r.status_code == 404
    assert r.json() == {"detail": DETAIL_404}


# =========================================================================================
# C - Arquivar / desarquivar
# =========================================================================================

def test_c1_arquivar_grava_archived_true_e_preserva_o_resto(client, contas, cursos):
    antes = _ler(cursos, CURSO_Z)

    r = _arquivar(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    depois = _ler(cursos, CURSO_Z)
    assert depois.get("archived") is True
    for chave, valor in antes.items():
        assert depois.get(chave) == valor, f"arquivar alterou o campo {chave!r}"


def test_c2_arquivar_grava_evento_course_archive(client, contas):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    eventos = _eventos("course.archive")
    assert len(eventos) == 1, eventos
    ev = eventos[0]
    assert ev["entity_type"] == "course"
    assert ev["entity_id"] == CURSO_Z
    assert ev["user_id"] == contas.ana.id
    assert ev["actor_email"] == contas.ana.email
    assert {"field": "archived", "before": False, "after": True} in _changes(ev)


def test_c3_arquivar_de_novo_e_idempotente_sem_evento_novo(client, contas, cursos):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = _arquivar(client, contas.ana.token, CURSO_Z)

    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_Z).get("archived") is True
    assert len(_eventos("course.archive")) == 1


def test_c4_desarquivar_grava_false_e_evento_course_unarchive(client, contas, cursos):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = _desarquivar(client, contas.bruno.token, CURSO_Z)

    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    assert _ler(cursos, CURSO_Z).get("archived") is False
    eventos = _eventos("course.unarchive")
    assert len(eventos) == 1, eventos
    ev = eventos[0]
    assert ev["entity_type"] == "course"
    assert ev["entity_id"] == CURSO_Z
    assert ev["user_id"] == contas.bruno.id
    assert {"field": "archived", "before": True, "after": False} in _changes(ev)


def test_c5_desarquivar_curso_nao_arquivado_e_idempotente(client, contas, cursos):
    r = _desarquivar(client, contas.ana.token, CURSO_A)

    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    assert _ler(cursos, CURSO_A).get("archived", False) is False
    assert _eventos("course.unarchive") == []

    _arquivado_ok(client, contas.ana.token, CURSO_A)
    assert _desarquivar(client, contas.ana.token, CURSO_A).status_code == 200
    assert _desarquivar(client, contas.ana.token, CURSO_A).status_code == 200
    assert len(_eventos("course.unarchive")) == 1


@pytest.mark.parametrize("rota", ("archive", "unarchive"))
def test_c6_curso_inexistente_devolve_404(client, contas, rota):
    r = client.post(f"/api/admin/course/curso_inexistente_f1/{rota}", headers=_auth(contas.ana.token))
    assert r.status_code == 404, r.text
    assert r.json() == {"detail": DETAIL_404}
    assert _eventos_de_curso() == []


def test_c7_ciclo_arquivar_desarquivar_volta_ao_catalogo(client, contas):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    assert CURSO_Z not in _ids_publicos(client)
    assert _desarquivar(client, contas.ana.token, CURSO_Z).status_code == 200
    assert CURSO_Z in _ids_publicos(client)


def test_c8_token_legado_de_gestao_arquiva(client, contas, cursos):
    r = _arquivar(client, create_admin_token(Role.ADMIN), CURSO_Z)
    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_Z).get("archived") is True


# =========================================================================================
# D - RBAC e IDOR
# =========================================================================================

def _identidades_sem_permissao(contas):
    return {
        "suporte_jwt": (contas.sup.token, 403),
        "financeiro_jwt": (contas.fin.token, 403),
        "aluno_jwt": (contas.aluno.token, 403),
        "suporte_legado": (create_admin_token(Role.SUPPORT), 403),
        "financeiro_legado": (create_admin_token(Role.FINANCIAL), 403),
        "sem_token": (None, 401),
        "token_forjado": (_forjado(), 401),
    }


@pytest.mark.parametrize("rota", ("archive", "unarchive"))
def test_d1_arquivar_e_desarquivar_so_gestao(client, contas, cursos, rota):
    if rota == "unarchive":
        _arquivado_ok(client, contas.ana.token, CURSO_Z)
    conteudo = _arquivo(cursos, CURSO_Z).read_bytes()
    eventos_antes = len(_eventos_de_curso())

    for nome, (token, esperado) in _identidades_sem_permissao(contas).items():
        r = client.post(f"/api/admin/course/{CURSO_Z}/{rota}", headers=_auth(token))
        assert r.status_code == esperado, f"{rota} com {nome}: HTTP {r.status_code} (esperado {esperado})"

    assert _arquivo(cursos, CURSO_Z).read_bytes() == conteudo, "o JSON mudou sem permissao"
    assert len(_eventos_de_curso()) == eventos_antes


def test_d2_rotas_novas_existem_para_gestao(client, contas):
    """Garante que o 403/401 do D1 nao e o 404/405 de rota inexistente."""
    assert _arquivar(client, contas.ana.token, CURSO_Z).status_code == 200
    assert _desarquivar(client, contas.ana.token, CURSO_Z).status_code == 200


def test_d3_excluir_continua_so_gestao_mesmo_sem_matricula(client, contas, cursos):
    for nome, (token, esperado) in _identidades_sem_permissao(contas).items():
        r = _excluir(client, token, CURSO_Z)
        assert r.status_code == esperado, f"DELETE com {nome}: HTTP {r.status_code} (esperado {esperado})"
    assert _arquivo(cursos, CURSO_Z).exists()
    assert _eventos("course.delete") == [] and _eventos("course.delete_blocked") == []


def test_d4_corpo_nao_define_responsavel_nem_valor_do_arquivamento(client, contas, cursos):
    corpo = {"user_id": contas.bruno.id, "actor_email": contas.bruno.email, "role": "financial",
             "archived": False, "course_id": CURSO_A}
    r = _arquivar(client, contas.ana.token, CURSO_Z, json=corpo)

    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_Z).get("archived") is True
    assert _ler(cursos, CURSO_A).get("archived", False) is False, "o corpo nao pode escolher outro curso"
    ev = _eventos("course.archive")
    assert len(ev) == 1 and ev[0]["entity_id"] == CURSO_Z
    assert ev[0]["user_id"] == contas.ana.id and ev[0]["actor_email"] == contas.ana.email


# =========================================================================================
# E - Catalogo publico e listagens da Gestao
# =========================================================================================

def test_e1_curso_arquivado_some_do_catalogo_publico(client, contas):
    assert set(_ids_publicos(client)) >= {CURSO_A, CURSO_Z}
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = client.get("/api/courses")
    ids = [c.get("id") for c in r.json()["courses"]]
    assert CURSO_Z not in ids
    assert CURSO_A in ids
    assert r.json()["total"] == len(r.json()["courses"])
    assert NOME_Z not in r.text


def test_e2_lista_da_gestao_traz_archived_e_enrollments_count(client, contas):
    for status in STATUS:
        _matricula(CURSO_Z, status)
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    z = _item_admin(client, contas.ana.token, CURSO_Z)
    a = _item_admin(client, contas.ana.token, CURSO_A)

    assert z.get("archived") is True, z
    assert z.get("enrollments_count") == 4, z
    assert a.get("archived") is False, a
    assert a.get("enrollments_count") == 0, a
    assert isinstance(a.get("enrollments_count"), int) and not isinstance(a.get("enrollments_count"), bool)


def test_e3_lista_da_gestao_campos_tambem_para_financeiro_e_suporte(client, contas):
    _matricula(CURSO_A, "active")
    for token in (contas.fin.token, contas.sup.token):
        a = _item_admin(client, token, CURSO_A)
        assert a.get("archived") is False and a.get("enrollments_count") == 1, a


def test_e4_dashboard_de_cursos_traz_archived(client, contas):
    _matricula(CURSO_Z, "active")
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    z = _curso_dashboard(client, contas.ana.token, CURSO_Z)
    a = _curso_dashboard(client, contas.ana.token, CURSO_A)
    assert z.get("archived") is True, z
    assert z.get("total_enrollments") == 1, "o arquivado continua com o historico no dashboard"
    assert a.get("archived") is False, a


# =========================================================================================
# F - Checkouts
# =========================================================================================

def test_f1_checkout_da_landing_de_curso_arquivado_devolve_409_sem_criar_nada(client, contas, gw):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    antes = _contagens()

    r = _checkout_landing(client, CURSO_Z)

    assert r.status_code == 409, f"HTTP {r.status_code} {r.text[:300]}"
    assert r.json() == {"detail": DETAIL_INDISPONIVEL}
    assert _contagens() == antes, "o checkout bloqueado criou conta, matricula ou pagamento"
    assert gw.post_chamadas == [], "o gateway nao pode ser chamado para curso arquivado"


def test_f2_checkout_do_aluno_de_curso_arquivado_devolve_409_sem_criar_nada(client, contas, gw):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    antes = _contagens()

    r = _checkout_aluno(client, contas.aluno.token, CURSO_Z)

    assert r.status_code == 409, f"HTTP {r.status_code} {r.text[:300]}"
    assert r.json() == {"detail": DETAIL_INDISPONIVEL}
    assert _contagens() == antes
    assert gw.post_chamadas == []


def test_f3_pagamento_simulado_efetivo_tambem_respeita_o_arquivamento(client, contas, monkeypatch):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    monkeypatch.setenv("PAYMENTS_MOCK", "1")
    monkeypatch.setenv("APP_ENV", "development")
    antes = _contagens()

    r1 = _checkout_aluno(client, contas.aluno.token, CURSO_Z)
    r2 = _checkout_landing(client, CURSO_Z)

    assert (r1.status_code, r2.status_code) == (409, 409), f"{r1.text[:200]} | {r2.text[:200]}"
    assert r1.json() == r2.json() == {"detail": DETAIL_INDISPONIVEL}
    assert _contagens() == antes
    assert _eventos("payment.mock_approved") == []


def test_f4_curso_nao_arquivado_continua_vendendo(client, contas, gw):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r1 = _checkout_landing(client, CURSO_A)
    r2 = _checkout_aluno(client, contas.aluno.token, CURSO_A)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert len(_sql("SELECT * FROM enrollments WHERE course_id = ? AND status = 'pending'", (CURSO_A,))) == 2


def test_f5_desarquivado_volta_a_vender(client, contas, gw):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    assert _desarquivar(client, contas.ana.token, CURSO_Z).status_code == 200

    r = _checkout_aluno(client, contas.aluno.token, CURSO_Z)
    assert r.status_code == 200, r.text


# =========================================================================================
# G - Aluno ativo no curso arquivado; recurso pago so com `active`
# =========================================================================================

def test_g1_aluno_ativo_continua_vendo_curso_e_materiais(client, contas):
    matricula = _matricula(CURSO_Z, "active", user_id=contas.aluno.id)
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = client.get("/api/student/enrollments", headers=_auth(contas.aluno.token))
    assert r.status_code == 200, r.text
    itens = [e for e in r.json()["enrollments"] if e["id"] == matricula]
    assert len(itens) == 1, r.json()
    item = itens[0]
    assert item["course_id"] == CURSO_Z
    assert item["course_name"] == NOME_Z
    assert item["status"] == "active"
    assert [m["url"] for m in item.get("materials", [])] == [URL_Z]

    detalhe = client.get(f"/api/student/enrollments/{matricula}", headers=_auth(contas.aluno.token))
    assert detalhe.status_code == 200, detalhe.text
    assert [m["url"] for m in detalhe.json()["enrollment"].get("materials", [])] == [URL_Z]


@pytest.mark.parametrize("status", ("pending", "cancelled", "refunded"))
def test_g2_arquivado_nao_libera_material_sem_matricula_ativa(client, contas, status):
    matricula = _matricula(CURSO_Z, status, user_id=contas.aluna.id)
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = client.get("/api/student/enrollments", headers=_auth(contas.aluna.token))
    assert r.status_code == 200, r.text
    assert URL_Z not in r.text, f"material liberado com matricula {status}"
    item = [e for e in r.json()["enrollments"] if e["id"] == matricula][0]
    assert not item.get("materials")

    detalhe = client.get(f"/api/student/enrollments/{matricula}", headers=_auth(contas.aluna.token))
    assert URL_Z not in detalhe.text


def test_g3_matricula_alheia_no_curso_arquivado_continua_404(client, contas):
    """IDOR: arquivar nao muda o isolamento da area do aluno."""
    alheia = _matricula(CURSO_Z, "active", user_id=contas.aluno.id)
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r_alheia = client.get(f"/api/student/enrollments/{alheia}", headers=_auth(contas.aluna.token))
    r_inexistente = client.get("/api/student/enrollments/999999", headers=_auth(contas.aluna.token))

    assert r_alheia.status_code == r_inexistente.status_code == 404
    assert r_alheia.json() == r_inexistente.json()
    assert URL_Z not in r_alheia.text


# =========================================================================================
# H - Chatbot nao oferece curso arquivado
# =========================================================================================

def _chat(client, mensagem):
    r = client.post("/api/chat", json={"message": mensagem})
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "success", r.json()
    return r


def test_h0_sanidade_bot_oferece_os_dois_cursos_antes_de_arquivar(client, llm):
    _chat(client, "Quais cursos voces tem?")
    sistema = "\n".join(llm.mensagens_de_sistema())
    assert NOME_A in sistema and NOME_Z in sistema, "pre-condicao: o bot le o diretorio temporario"


def test_h1_resposta_geral_nao_lista_curso_arquivado(client, contas, llm):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    _chat(client, "Quais cursos voces tem?")

    sistema = "\n".join(llm.mensagens_de_sistema())
    assert NOME_A in sistema, "o curso disponivel continua no catalogo do bot"
    assert NOME_Z not in sistema, "o curso arquivado ainda e oferecido pelo bot"
    assert MARCA_Z not in llm.todo_o_texto()


def test_h2_pergunta_pelo_nome_do_arquivado_nao_aciona_o_agente_do_curso(client, contas, llm):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    _chat(client, f"Quero me matricular no {NOME_Z}")

    assert MARCA_Z not in llm.todo_o_texto(), "o Course Agent do curso arquivado foi usado"
    assert all(NOME_Z not in texto for texto in llm.mensagens_de_sistema())


def test_h3_roteamento_do_llm_para_id_arquivado_e_ignorado(client, contas, llm):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    llm.rota = CURSO_Z  # o LLM de roteamento "alucina" o id do curso arquivado

    _chat(client, "Me fala de algum curso bom")

    assert MARCA_Z not in llm.todo_o_texto(), "o Course Agent do curso arquivado foi usado"
    assert all(NOME_Z not in texto for texto in llm.mensagens_de_sistema())


def test_h4_arquivado_direto_no_json_nao_e_carregado_no_startup(banco, cursos, bot_no_diretorio_temporario, llm):
    dados = _ler(cursos, CURSO_Z)
    dados["archived"] = True
    _escrever(cursos, dados)
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        _chat(c, "Quais cursos voces tem?")
        assert CURSO_Z not in [x.get("id") for x in c.get("/api/courses").json()["courses"]]

    sistema = "\n".join(llm.mensagens_de_sistema())
    assert NOME_A in sistema and NOME_Z not in sistema


def test_h5_desarquivar_devolve_o_curso_ao_bot(client, contas, llm):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    assert _desarquivar(client, contas.ana.token, CURSO_Z).status_code == 200

    _chat(client, "Quais cursos voces tem?")

    assert NOME_Z in "\n".join(llm.mensagens_de_sistema())


# =========================================================================================
# I - Compatibilidade e schema de escrita do admin
# =========================================================================================

def _corpo_admin(course_id, nome, **extra):
    corpo = _dados_curso(course_id, nome, 150.0, f"https://materiais.test/f1/{course_id}.pdf", "MARCA-I")
    corpo.update(extra)
    return corpo


def test_i1_curso_sem_a_chave_archived_vale_como_nao_arquivado(client, contas, cursos, gw):
    assert "archived" not in _ler(cursos, CURSO_A)
    assert CURSO_A in _ids_publicos(client)
    assert _item_admin(client, contas.ana.token, CURSO_A).get("archived") is False
    assert _curso_dashboard(client, contas.ana.token, CURSO_A).get("archived") is False
    assert _checkout_aluno(client, contas.aluno.token, CURSO_A).status_code == 200


def test_i2_archived_false_explicito_vale_como_nao_arquivado(client, contas, cursos):
    dados = _ler(cursos, CURSO_A)
    dados["archived"] = False
    _escrever(cursos, dados)
    assert CURSO_A in _ids_publicos(client)
    assert _item_admin(client, contas.ana.token, CURSO_A).get("archived") is False


def test_i3_create_course_aceita_archived_opcional(client, contas, cursos):
    r1 = client.post("/api/admin/create-course", json=_corpo_admin("curso_f1_novo_arq", "Novo Arquivado F1",
                                                                     archived=True),
                     headers=_auth(contas.ana.token))
    r2 = client.post("/api/admin/create-course", json=_corpo_admin("curso_f1_novo", "Novo Normal F1"),
                     headers=_auth(contas.ana.token))

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert _ler(cursos, "curso_f1_novo_arq").get("archived") is True
    assert _ler(cursos, "curso_f1_novo").get("archived", False) is False
    ids = _ids_publicos(client)
    assert "curso_f1_novo_arq" not in ids
    assert "curso_f1_novo" in ids


def test_i4_editar_sem_mandar_archived_preserva_o_arquivamento(client, contas, cursos):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)
    corpo = _corpo_admin(CURSO_Z, NOME_Z, price=PRECO_Z + 10)
    corpo.pop("archived", None)

    r = client.put(f"/api/admin/course/{CURSO_Z}", json=corpo, headers=_auth(contas.ana.token))

    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_Z).get("archived") is True, "editar sem `archived` desarquivou o curso"
    assert CURSO_Z not in _ids_publicos(client)


def test_i5_editar_sem_mandar_archived_nao_arquiva_curso_ativo(client, contas, cursos):
    r = client.put(f"/api/admin/course/{CURSO_A}", json=_corpo_admin(CURSO_A, NOME_A, price=111.0),
                   headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_A).get("archived", False) is False
    assert CURSO_A in _ids_publicos(client)


def test_i6_update_aceita_archived_quando_enviado(client, contas, cursos):
    _arquivado_ok(client, contas.ana.token, CURSO_Z)

    r = client.put(f"/api/admin/course/{CURSO_Z}", json=_corpo_admin(CURSO_Z, NOME_Z, price=PRECO_Z, archived=False),
                   headers=_auth(contas.ana.token))

    assert r.status_code == 200, r.text
    assert _ler(cursos, CURSO_Z).get("archived") is False
    assert CURSO_Z in _ids_publicos(client)
