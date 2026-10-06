"""Regressão da Fase 2 (portada de smoke_merge.py): 44 checks.

Mesmos checks, mesma ordem e mesmo significado do smoke original, agrupados
em funções. Os blocos compartilham estado (tokens, pagamentos) e precisam
rodar na ordem do arquivo, como no smoke.

Cobre: login por conta (JWT) e por perfil de funcionário, RBAC de dashboards,
cadastro de curso com auditoria, checkout/webhook/reembolso e bloqueio de aluno.
Banco: arquivo temporário em tmp_path. Cursos de teste são criados em
backend/courses e removidos ao final.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from apoio_mercado_pago import SEGREDO_WEBHOOK, corpo_pagamento_mp, post_webhook
from core.security import get_password_hash
from db import Database

BACKEND = Path(__file__).resolve().parent.parent
COURSE_FILE = BACKEND / "courses" / "curso_smoke.json"

AMBIENTE = {
    "GROQ_API_KEY": "dummy",
    "ADMIN_PASSWORD": "admin123",
    "FINANCIAL_PASSWORD": "fin123",
    "SUPPORT_PASSWORD": "sup123",
    "ADMIN_TOKEN_SECRET": "staff-secret-123",
    "JWT_SECRET_KEY": "jwt-secret-456-long-enough",
    "ADMIN_EMAIL": "gestor@teste.com",
    "FINANCIAL_EMAIL": "fin@teste.com",
    "SUPPORT_EMAIL": "sup@teste.com",
    "MERCADO_PAGO_ACCESS_TOKEN": "TEST-fake",
    "MERCADO_PAGO_WEBHOOK_SECRET": SEGREDO_WEBHOOK,
    "FRONTEND_BASE_URL": "http://localhost:8000",
    "API_BASE_URL": "http://localhost:8000",
}

TODOS = []


class Checks:
    """Coleta os checks de um bloco; o bloco falha ao final se algum check falhou."""

    def __init__(self):
        self.itens = []

    def __call__(self, name, cond, extra=""):
        resultado = (name, bool(cond), extra)
        self.itens.append(resultado)
        TODOS.append(resultado)

    def assert_all(self):
        falhas = [f"{nome} -> {extra}" for nome, ok, extra in self.itens if not ok]
        assert not falhas, "\n".join(falhas)


@pytest.fixture
def checks():
    return Checks()


@pytest.fixture(scope="module")
def sistema(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.chdir(BACKEND)
    for chave, valor in AMBIENTE.items():
        mp.setenv(chave, valor)
    mp.setattr(Database, "DB_PATH", tmp_path_factory.mktemp("regressao") / "db.sqlite")
    Database.init_db()

    import app as appmod

    cliente = TestClient(appmod.app)
    cliente.__enter__()  # dispara o startup (contas de funcionário, agente)
    estado = {}
    try:
        yield SimpleNamespace(client=cliente, app=appmod.app, estado=estado)
    finally:
        cliente.__exit__(None, None, None)
        COURSE_FILE.unlink(missing_ok=True)
        (BACKEND / "courses" / "curso_smoke2.json").unlink(missing_ok=True)
        mp.undo()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- Bloco 1: rotas, bootstrap e login -------------------------------------------

def test_bloco1_rotas_bootstrap_e_login(sistema, checks):
    c = sistema.client
    e = sistema.estado

    paths = set(sistema.app.openapi()["paths"].keys())
    checks("rota /api/token registrada", "/api/token" in paths)
    checks("rota /api/dashboard/financeiro registrada", "/api/dashboard/financeiro" in paths)
    checks("rota /api/v1/dashboard/* removida (duplicada)", not any(p.startswith("/api/v1/dashboard") for p in paths))

    # bootstrap da conta admin JWT (startup do Gustavo)
    u = Database.get_user_by_email("gestor@teste.com")
    checks("startup criou a conta admin JWT do ADMIN_EMAIL", u is not None and u["role"] == "admin")

    # login por senha de perfil (admin.html)
    r = c.post("/api/admin/login", json={"password": "admin123"})
    checks("login staff: Gestão", r.status_code == 200 and r.json()["role"] == "admin", r.text)
    e["staff_admin"] = r.json()["token"]
    e["staff_fin"] = c.post("/api/admin/login", json={"password": "fin123"}).json()["token"]
    e["staff_sup"] = c.post("/api/admin/login", json={"password": "sup123"}).json()["token"]
    checks("login staff: senha errada -> 401", c.post("/api/admin/login", json={"password": "x"}).status_code == 401)

    # login por conta JWT (Angular)
    r = c.post("/api/token", data={"username": "gestor@teste.com", "password": "admin123"})
    checks("JWT: /api/token com credenciais válidas", r.status_code == 200 and "access_token" in r.json(), r.text)
    e["jwt_admin"] = r.json().get("access_token", "")
    r = c.post("/api/token", data={"username": "gestor@teste.com", "password": "errada"})
    checks("JWT: senha errada -> 400 (comportamento do Gustavo)", r.status_code == 400)

    # contas de Financeiro e Suporte (semeadas no startup a partir do .env)
    e["jwt_fin"] = c.post("/api/token", data={"username": "fin@teste.com", "password": "fin123"}).json().get("access_token", "")
    e["jwt_sup"] = c.post("/api/token", data={"username": "sup@teste.com", "password": "sup123"}).json().get("access_token", "")
    checks("JWT: conta Financeiro criada no startup e logando", bool(e["jwt_fin"]))
    checks("JWT: conta Suporte criada no startup e logando", bool(e["jwt_sup"]))

    checks.assert_all()


# --- Bloco 2: RBAC (JWT, staff, aluno) --------------------------------------------

def test_bloco2_rbac(sistema, checks):
    c = sistema.client
    e = sistema.estado

    r = c.get("/api/dashboard/financeiro", headers=_auth(e["jwt_fin"]))
    checks("RBAC JWT: Financeiro acessa financeiro -> 200", r.status_code == 200, r.text)
    r = c.get("/api/dashboard/financeiro", headers=_auth(e["jwt_sup"]))
    checks("RBAC JWT: Suporte NÃO acessa financeiro -> 403", r.status_code == 403, f"status {r.status_code}")
    r = c.get("/api/dashboard/alunos", headers=_auth(e["jwt_sup"]))
    checks("RBAC JWT: Suporte acessa alunos -> 200", r.status_code == 200, r.text)
    r = c.get("/api/admin/audit-logs", headers=_auth(e["jwt_fin"]))
    checks("RBAC JWT: Financeiro NÃO acessa auditoria -> 403", r.status_code == 403)

    # aluno com conta JWT
    Database.add_user("aluno@teste.com", "Aluno Teste", get_password_hash("aluno123"), role="student")
    e["jwt_student"] = c.post("/api/token", data={"username": "aluno@teste.com", "password": "aluno123"}).json()["access_token"]
    jwt_student = e["jwt_student"]

    # RBAC da Angular (JWT)
    r = c.get("/api/dashboard/financeiro", headers=_auth(e["jwt_admin"]))
    checks("Angular financeiro: admin JWT -> 200", r.status_code == 200, r.text)
    r = c.get("/api/dashboard/financeiro", headers=_auth(jwt_student))
    checks("Angular financeiro: aluno JWT -> 403", r.status_code == 403, r.text)
    r = c.get("/api/admin/audit-logs", headers=_auth(e["jwt_admin"]))
    checks("Angular audit: admin JWT -> 200", r.status_code == 200, r.text)
    r = c.get("/api/admin/audit-logs", headers=_auth(jwt_student))
    checks("Angular audit: aluno JWT -> 403", r.status_code == 403, r.text)

    # RBAC do admin.html (staff)
    r = c.get("/api/dashboard/financeiro", headers=_auth(e["staff_sup"]))
    checks("admin.html financeiro: suporte -> 403", r.status_code == 403)
    r = c.get("/api/dashboard/financeiro", headers=_auth(e["staff_fin"]))
    checks("admin.html financeiro: financeiro -> 200", r.status_code == 200)
    r = c.get("/api/dashboard/alunos", headers=_auth(e["staff_sup"]))
    checks("admin.html alunos: suporte -> 200", r.status_code == 200)
    r = c.get("/api/admin/audit-logs", headers=_auth(e["staff_fin"]))
    checks("admin.html auditoria: financeiro -> 403", r.status_code == 403)

    # token staff aceito pelo dashboard; JWT forjado com segredo padrão antigo é recusado
    r = c.get("/api/dashboard/alunos", headers=_auth(e["staff_admin"]))
    checks("staff token aceito pelo dashboard (admin)", r.status_code == 200, r.text)
    forjado = jose_jwt.encode(
        {"user_id": 1, "email": "gestor@teste.com", "role": "admin"},
        "change-me-for-production",
        algorithm="HS256",
    )
    r = c.get("/api/dashboard/financeiro", headers=_auth(forjado))
    checks("JWT forjado com segredo padrão antigo é RECUSADO", r.status_code == 401, f"status {r.status_code}")

    checks.assert_all()


# --- Bloco 3: cadastro de curso e auditoria ---------------------------------------

def test_bloco3_cursos_e_auditoria(sistema, checks):
    c = sistema.client
    e = sistema.estado

    course = {
        "id": "curso_smoke", "name": "Curso Smoke", "description": "d", "price": 100.0,
        "duration_hours": 5, "level": "Iniciante", "target_audience": "t",
        "objectives": ["o"], "topics": ["t"], "benefits": ["b"],
        "faq": [{"question": "q", "answer": "a"}], "system_prompt": "p",
    }
    r = c.post("/api/admin/create-course", json=course, headers=_auth(e["staff_admin"]))
    checks("criar curso (Gestão) -> 200", r.status_code == 200, r.text)
    r = c.post("/api/admin/create-course", json={**course, "id": "curso_smoke2"}, headers=_auth(e["staff_sup"]))
    checks("criar curso (Suporte) -> 403", r.status_code == 403)
    c.put("/api/admin/course/curso_smoke", json={**course, "price": 150.0}, headers=_auth(e["staff_admin"]))

    logs = c.get("/api/admin/audit-logs", headers=_auth(e["staff_admin"])).json()["logs"]
    actions = {l["action"]: l for l in logs}
    checks("auditoria: course.create com role=admin", actions.get("course.create", {}).get("role") == "admin")
    checks("auditoria: course.price_change registrado", "course.price_change" in actions)
    checks("auditoria: manager_reload registrado com role=system", actions.get("manager_reload", {}).get("role") == "system")

    # Log do Gustavo via JWT (user_id) aparece na listagem da Angular
    Database.add_audit_log("login.test", "evento via conta", user_id=1)
    alog = c.get("/api/admin/audit-logs", headers=_auth(e["jwt_admin"])).json()["logs"]
    checks("auditoria Angular lista eventos com user_id", any(l["action"] == "login.test" and l["user_id"] == 1 for l in alog))

    checks.assert_all()


# --- Bloco 4: pagamentos (checkout, webhook, reembolso) ---------------------------

def test_bloco4_pagamentos(sistema, checks):
    c = sistema.client
    e = sistema.estado

    fake_pref = MagicMock(status_code=201)
    fake_pref.json.return_value = {"id": "pref-1", "init_point": "https://mp/checkout"}
    with patch("payments.routes.requests.post", return_value=fake_pref):
        r = c.post("/api/payments/create-checkout", json={
            "course_id": "curso_smoke",
            "payer": {"name": "Maria Silva", "email": "maria@teste.com"},
        })
    checks("checkout cria preferência e retorna URL", r.status_code == 200 and r.json().get("checkout_url"), r.text)
    ref = r.json().get("external_reference")

    # E9 (D48): webhook assinado, com valor e moeda do curso (preço 150.0 BRL, alterado pelo PUT do bloco 3).
    fake_pay = MagicMock(status_code=200)
    fake_pay.json.return_value = corpo_pagamento_mp("approved", ref, 150.0, "999")
    with patch("payments.routes.requests.get", return_value=fake_pay):
        r1 = post_webhook(c, "999")
        r2 = post_webhook(c, "999")  # duplicado
    checks("webhook aprovado atualiza pagamento", r1.json().get("payment_status") == "approved")
    checks("webhook duplicado não quebra", r2.status_code == 200)

    totals = c.get("/api/dashboard/financeiro", headers=_auth(e["jwt_admin"])).json()["totals"]
    checks("financeiro conta receita 'approved'", totals.get("revenue_approved", 0) == 150.0, totals)
    checks("get_revenue_totals (legado do Gustavo) conta 'approved'", Database.get_revenue_totals()["total_revenue"] == 150.0)

    pay_id = Database.get_payments_overview()[0]["id"]
    r = c.post(f"/api/payments/refund/{pay_id}", headers=_auth(e["staff_sup"]))
    checks("reembolso: suporte -> 403", r.status_code == 403)
    r = c.post(f"/api/payments/refund/{pay_id}", headers=_auth(e["staff_fin"]))
    checks("reembolso: financeiro -> 200", r.status_code == 200, r.text)
    logs = c.get("/api/admin/audit-logs", headers=_auth(e["staff_admin"])).json()["logs"]
    checks("reembolso auditado com role=financial", any(l["action"] == "payment.refund" and l["role"] == "financial" for l in logs))

    checks.assert_all()


# --- Bloco 5: aluno autenticado não lê dados de funcionário ------------------------

def test_bloco5_aluno_bloqueado(sistema, checks):
    c = sistema.client
    e = sistema.estado
    jwt_student = e["jwt_student"]

    r = c.get("/api/dashboard/alunos", headers=_auth(jwt_student))
    checks("aluno JWT -> /api/dashboard/alunos = 403", r.status_code == 403, f"status {r.status_code}")
    r = c.get("/api/dashboard/cursos", headers=_auth(jwt_student))
    checks("aluno JWT -> /api/dashboard/cursos = 403", r.status_code == 403, f"status {r.status_code}")
    r = c.get("/api/dashboard/observabilidade-ia", headers=_auth(jwt_student))
    checks("aluno JWT -> observabilidade IA = 403", r.status_code == 403, f"status {r.status_code}")
    r = c.get("/api/admin/courses", headers=_auth(jwt_student))
    checks("aluno JWT -> /api/admin/courses (inclui system_prompt) = 403", r.status_code == 403, f"status {r.status_code}")
    r = c.get("/api/admin/courses", headers=_auth(e["staff_sup"]))
    checks("suporte (staff) -> /api/admin/courses = 200", r.status_code == 200, r.text)
    r = c.get("/api/admin/audit-logs", headers=_auth(jwt_student))
    checks("aluno JWT -> audit logs = 403", r.status_code == 403, f"status {r.status_code}")

    checks.assert_all()


def test_total_de_checks_da_regressao():
    """Fecha a conta: 44 checks no total, todos passando (só vale rodando o módulo inteiro)."""
    assert len(TODOS) == 44, f"esperado 44 checks, executados {len(TODOS)}"
    falhas = [nome for nome, ok, _ in TODOS if not ok]
    assert not falhas, falhas
