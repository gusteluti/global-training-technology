"""E8 - Auditoria com identificacao do usuario responsavel (PDF secao 2, D45).

Escritos ANTES da implementacao. Devem falhar agora: `audit_logs` nao tem actor_email, actor_name,
entity_type, entity_id nem changes; os eventos gravam so o perfil (`role`) e nunca a pessoa; o preco
mascara os demais campos alterados; reembolso repetido duplica o evento; login nao e auditado; a
tabela aceita UPDATE/DELETE; o endpoint nao filtra, nao limita e nao devolve os campos novos.

Grupos
  A  Responsavel pela pessoa (nucleo)
  A1  dois gestores com JWT alteram precos de cursos: cada evento traz user_id, actor_email, actor_name e role de QUEM agiu.
  A2  user_id/actor_email/actor_name/role enviados no corpo ou na query (create, update, refund) sao IGNORADOS.
  A3  token administrativo legado (Gestao): user_id e actor_email nulos, actor_name "Login administrativo (Gestão)".
  A4  Financeiro com JWT no reembolso: ator correto, role financial.
  A5  Financeiro/Gestao com token administrativo legado no reembolso: rotulo do perfil, sem pessoa.
  A6  evento do sistema (manager_reload): role 'system', sem usuario.
  Grupo B  Alteracao efetuada (`changes`)
  B1  course.create: entity_type/entity_id, changes com name e price, before nulo.
  B2  course.price_change so com preco: um item, price antes/depois exatos.
  B3  preco + outros campos: UM evento price_change com TODOS os campos alterados e so eles.
  B4  todos os 12 campos alterados de uma vez: um evento com os 12.
  B5  edicao sem preco: course.update com so os campos alterados (incl. materials e lista).
  B6  PUT identico (e preco 100 -> 100.0): course.update com changes vazio.
  B7  valores longos (antes e depois) truncados em 2000 caracteres.
  B8  course.delete: name e price antes, after nulo.
  B9  payment.refund: entity_type/entity_id, payment.status e enrollment.status antes e 'refunded'.
  B10 reembolso repetido do mesmo pagamento NAO grava evento novo.
  B11 operacao que falha (curso/pagamento inexistente, perfil sem permissao) NAO grava evento de alteracao.
  B12 detail continua preenchido nos eventos de curso (compatibilidade com o texto antigo).
  Grupo C  Login
  C1  staff.login via /api/token (JWT de funcionario, 3 perfis).
  C2  staff.login via /api/admin/login (legado, 3 senhas).
  C3  staff.login_failed: senha errada de conta de funcionario existente; senha nunca gravada.
  C4  staff.login_failed: senha administrativa invalida; senha nunca gravada.
  C5  e-mail inexistente e senha digitada nunca aparecem em nenhuma coluna.
  C6  login de aluno (certo ou errado) NAO gera evento.
  Grupo D  Estampa de tempo
  D1  created_at preenchido e dentro de uma janela de segundos (eventos de curso e de login).
  Grupo E  Endpoint GET /api/admin/audit-logs
  E1  campos novos presentes; changes e LISTA (vazia quando nao ha).
  E2  filtros action, user_id e a combinacao.
  E3  limit padrao 100; limit explicito; maximo 500.
  E4  ordem decrescente por id.
  E5  RBAC: Financeiro, Suporte e aluno 403 (JWT e legado); sem token e token forjado 401.
  E6  PUT, PATCH, DELETE e POST em /api/admin/audit-logs -> 405 (e nenhum 2xx em /audit-logs/{id}).
  Grupo F  Append-only
  F1  UPDATE direto levanta erro e nao altera a linha (colunas antigas e novas).
  F2  DELETE direto levanta erro e nao apaga.
  F3  INSERT continua funcionando (SQL direto e Database.add_audit_log).
  Grupo G  Compatibilidade
  G1  esquema novo: colunas e triggers em banco recem-criado.
  G2  banco antigo (audit_logs sem as colunas novas): init_db ganha colunas e triggers sem perder linhas.
  G3  eventos antigos listados com actor_*/entity_* nulos e changes vazio.
  G4  Database.add_audit_log com a assinatura antiga continua valida.
  G5  init_db idempotente.

Checklist: IDOR NAO SE APLICA (a trilha e dado de funcionario, sem recurso de aluno; nenhum endpoint
novo recebe id de usuario como identidade: o `user_id` da query do GET e FILTRO de consulta, so da
Gestao, e A2 prova que a identidade gravada vem so do token). Recurso pago so com matricula ativa:
nao se aplica (nenhuma URL de material). O 403/401 do endpoint esta em E5.

Convencoes (padrao de test_e3/test_e7): banco temporario via conftest, rotas HTTP reais, JWT de conta
montado com create_access_token (igual ao que /api/token emite; os testes de login usam /api/token de
verdade), cursos em diretorio temporario. As rotas de curso usam Path(__file__).parent.parent / "courses"
(fixo) e `admin.routes.COURSES_DIR`; a fixture `cursos` redireciona os dois (monkeypatch de
`admin.routes.__file__` e de COURSES_DIR) e, ao final, exige que backend/courses nao tenha mudado.
Nenhum teste toca backend/db.sqlite nem o Groq.

Escolhas conservadoras (ver relatorio): valores de `before`/`after` sao comparados de forma tolerante
(valor cru, ou o mesmo valor serializado em JSON); `staff.login_failed` de conta existente aceita
user_id/actor_email nulos OU os da conta; nao se exige ator no evento de sistema alem de user_id/e-mail
nulos; `changes` pode ser texto JSON no banco (o endpoint e que devolve lista).
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database


SENHA = "senha-e8-2026-correta"
ROTA = "/api/admin/audit-logs"
REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
ROTULO = {"admin": "Gestão", "financial": "Financeiro", "support": "Suporte"}
SENHA_LEGADA = {"admin": "admin123", "financial": "fin123", "support": "sup123"}
CAMPOS_CURSO = [
    "price", "name", "description", "duration_hours", "level", "target_audience",
    "objectives", "topics", "benefits", "faq", "system_prompt", "materials",
]
CAMPOS_NOVOS = {"actor_email", "actor_name", "entity_type", "entity_id", "changes"}
CAMPOS_ENDPOINT = {
    "id", "created_at", "user_id", "role", "actor_email", "actor_name",
    "entity_type", "entity_id", "action", "detail", "changes",
}


# --- Fixtures ---------------------------------------------------------------------------

def _foto_repo():
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Diretorio temporario para as rotas de curso; backend/courses nao pode mudar."""
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses (deveria usar o diretorio temporario)"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def contas(client):
    """Contas sem senha (token montado direto, sem passar pelo login, para nao gerar evento de login)."""
    return SimpleNamespace(
        ana=_conta("ana.gestora@e8.test", "Ana Gestora", "admin"),
        bruno=_conta("bruno.gestor@e8.test", "Bruno Gestor", "admin"),
        fin=_conta("fernanda.fin@e8.test", "Fernanda Financeira", "financial"),
        sup=_conta("sergio.sup@e8.test", "Sergio Suporte", "support"),
        aluno=_conta("aluno.e8@e8.test", "Aluno E8", "student"),
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


def _eventos(action=None):
    if action is None:
        return _sql("SELECT * FROM audit_logs ORDER BY id")
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _do_curso(action, course_id):
    """Eventos de `action` do curso, pelo entity_id (a coluna e parte da entrega)."""
    achados = []
    for ev in _eventos(action):
        assert "entity_id" in ev, "coluna entity_id ausente em audit_logs"
        if str(ev["entity_id"]) == course_id:
            achados.append(ev)
    return achados


def _unico(eventos, descricao):
    assert len(eventos) == 1, f"esperado exatamente 1 evento {descricao}, achei {len(eventos)}: {eventos}"
    return eventos[0]


def _dump_tabela():
    """Todas as colunas de todas as linhas, em um texto so (para provar o que NUNCA aparece)."""
    return json.dumps(_sql("SELECT * FROM audit_logs"), ensure_ascii=False, default=str)


def _col(evento, nome):
    assert nome in evento, f"coluna {nome!r} ausente em audit_logs: colunas = {sorted(evento)}"
    return evento[nome]


def _checar_ator(evento, user_id, email, nome, role):
    assert _col(evento, "user_id") == user_id, evento
    assert _col(evento, "actor_email") == email, evento
    assert _col(evento, "actor_name") == nome, evento
    assert _col(evento, "role") == role, evento


def _checar_ator_legado(evento, role):
    assert _col(evento, "user_id") is None, evento
    assert _col(evento, "actor_email") is None, evento
    assert _col(evento, "actor_name") == f"Login administrativo ({ROTULO[role]})", evento
    assert _col(evento, "role") == role, evento


def _lista_changes(valor):
    """`changes` como lista de {"field","before","after"}; no banco pode ser texto JSON, na API e lista."""
    if valor is None or valor == "":
        return []
    lista = json.loads(valor) if isinstance(valor, str) else valor
    assert isinstance(lista, list), f"changes deve ser lista, veio {lista!r}"
    for item in lista:
        assert isinstance(item, dict) and set(item) == {"field", "before", "after"}, item
    return lista


def _mudancas(evento):
    """{campo: item} de um evento (do banco ou da API); campo repetido reprova."""
    itens = _lista_changes(_col(evento, "changes"))
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
    """Valor cru ou o mesmo valor serializado em JSON (D45: 'cada valor serializado')."""
    if valor == esperado or _norm(valor) == esperado:
        return True
    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        try:
            return float(valor) == float(esperado)
        except (TypeError, ValueError):
            return False
    return False


def _nulo(valor):
    return valor is None or valor == "null"


def _checar_mudanca(mud, campo, antes, depois):
    assert campo in mud, f"campo {campo!r} ausente em changes: {sorted(mud)}"
    item = mud[campo]
    assert _igual(item["before"], antes), f"{campo}.before = {item['before']!r}, esperado {antes!r}"
    assert _igual(item["after"], depois), f"{campo}.after = {item['after']!r}, esperado {depois!r}"


def _tamanho(valor):
    return len(valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False))


# --- Helpers de contas e HTTP -----------------------------------------------------------

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _conta(email, nome, perfil, senha=None):
    hash_ = get_password_hash(senha) if senha else None
    user_id = Database.add_user(email, nome, hash_, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


def _legado(perfil):
    """Token administrativo legado direto (sem passar por /api/admin/login, para nao gerar evento de login)."""
    return create_admin_token(Role(perfil))


def _forjado(role="admin"):
    return jose_jwt.encode(
        {"user_id": 1, "email": "x@e8.test", "role": role},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


def _curso(course_id="curso_e8_a", **mud):
    base = {
        "id": course_id, "name": "Curso E8", "description": "Descricao original", "price": 100.0,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Todos",
        "objectives": ["obj1"], "topics": ["top1"], "benefits": ["ben1"],
        "faq": [{"question": "q1", "answer": "a1"}], "system_prompt": "prompt original",
    }
    base.update(mud)
    return base


def _criar(client, token, curso=None, **kw):
    return client.post("/api/admin/create-course", json=curso or _curso(), headers=_auth(token), **kw)


def _criar_ok(client, token, curso=None):
    r = _criar(client, token, curso)
    assert r.status_code == 200, r.text
    return r


def _put(client, token, course_id, payload, **kw):
    return client.put(f"/api/admin/course/{course_id}", json=payload, headers=_auth(token), **kw)


def _put_ok(client, token, course_id, payload):
    r = _put(client, token, course_id, payload)
    assert r.status_code == 200, r.text
    return r


def _pagamento(curso_id="curso_e8_pag", valor=100.0):
    """Pagamento aprovado e matricula ativa (estado real via Database, como o webhook deixa)."""
    user_id = Database.get_or_create_user(f"pagante.{uuid.uuid4().hex[:8]}@e8.test", "Aluno Pagante")
    ref = f"{curso_id}:e8:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, curso_id, ref)
    pagamento_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    Database.update_payment_status_by_reference(ref, "approved", "tx-e8")
    assert _sql("SELECT status FROM payments WHERE id = ?", (pagamento_id,))[0]["status"] == "approved"
    assert _sql("SELECT status FROM enrollments WHERE id = ?", (enrollment_id,))[0]["status"] == "active"
    return pagamento_id, enrollment_id


def _reembolsar(client, token, pagamento_id, **kw):
    return client.post(f"/api/payments/refund/{pagamento_id}", headers=_auth(token), **kw)


def _listar(client, token, **params):
    r = client.get(ROTA, headers=_auth(token), params=params)
    assert r.status_code == 200, r.text
    return r.json()["logs"]


def _semear(n, prefixo="seed"):
    """n eventos pelo caminho publico do banco (assinatura antiga)."""
    for i in range(n):
        Database.add_audit_log("seed.e8", f"{prefixo}-{i}", role="system")


def _ts(texto):
    t = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None)
    return t


def _perto_de_agora(texto, janela=30):
    t = _ts(texto)
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    local = datetime.now()
    return min(abs((t - utc).total_seconds()), abs((t - local).total_seconds())) <= janela


# =========================================================================================
# Grupo S - setup (prova que o isolamento dos cursos funciona; deve estar verde ja no red)
# =========================================================================================

def test_s1_setup_cursos_vao_para_diretorio_temporario(client, contas, cursos):
    _criar_ok(client, contas.ana.token, _curso("curso_e8_setup"))
    assert (cursos / "curso_e8_setup.json").exists()
    assert not (REPO_COURSES / "curso_e8_setup.json").exists()


# =========================================================================================
# Grupo A - Responsavel pela pessoa (nucleo)
# =========================================================================================

def test_a1_dois_gestores_com_jwt_cada_evento_traz_quem_agiu(client, contas):
    ana, bruno = contas.ana, contas.bruno
    _criar_ok(client, ana.token, _curso("curso_a1_x", price=100.0))
    _criar_ok(client, ana.token, _curso("curso_a1_y", price=200.0))

    _put_ok(client, bruno.token, "curso_a1_x", _curso("curso_a1_x", price=150.0))   # Bruno altera X
    _put_ok(client, ana.token, "curso_a1_y", _curso("curso_a1_y", price=250.0))     # Ana altera Y
    _put_ok(client, bruno.token, "curso_a1_y", _curso("curso_a1_y", price=275.0))   # Bruno altera Y

    ev_x = _unico(_do_curso("course.price_change", "curso_a1_x"), "price_change do curso X")
    _checar_ator(ev_x, bruno.id, bruno.email, bruno.name, "admin")

    eventos_y = _do_curso("course.price_change", "curso_a1_y")
    assert len(eventos_y) == 2, eventos_y
    _checar_ator(eventos_y[0], ana.id, ana.email, ana.name, "admin")
    _checar_ator(eventos_y[1], bruno.id, bruno.email, bruno.name, "admin")

    # as criacoes foram da Ana
    for cid in ("curso_a1_x", "curso_a1_y"):
        _checar_ator(_unico(_do_curso("course.create", cid), f"create de {cid}"),
                     ana.id, ana.email, ana.name, "admin")

    # os dois gestores sao pessoas distintas na trilha (a trilha antiga so mostraria 'admin')
    quem = {(ev["user_id"], ev["actor_email"]) for ev in _eventos() if ev["action"].startswith("course.")}
    assert quem == {(ana.id, ana.email), (bruno.id, bruno.email)}


@pytest.mark.parametrize("forma", ["corpo", "query", "ambos"])
def test_a2_identidade_enviada_pelo_cliente_e_ignorada(client, contas, forma):
    ana, bruno, fin = contas.ana, contas.bruno, contas.fin
    falsa = {"user_id": bruno.id, "actor_email": bruno.email, "actor_name": "Quem Nao Agiu", "role": "financial"}
    query = {"user_id": bruno.id, "actor_email": bruno.email, "actor_name": "Quem Nao Agiu", "role": "financial"}

    def corpo(d):
        return {**d, **falsa} if forma in ("corpo", "ambos") else d

    def kw():
        return {"params": query} if forma in ("query", "ambos") else {}

    r = client.post("/api/admin/create-course", json=corpo(_curso("curso_a2")),
                    headers=_auth(ana.token), **kw())
    assert r.status_code == 200, r.text
    r = client.put("/api/admin/course/curso_a2", json=corpo(_curso("curso_a2", price=130.0)),
                   headers=_auth(ana.token), **kw())
    assert r.status_code == 200, r.text
    pagamento_id, _ = _pagamento()
    r = client.post(f"/api/payments/refund/{pagamento_id}", json=falsa if forma != "query" else None,
                    headers=_auth(fin.token), **kw())
    assert r.status_code == 200, r.text

    _checar_ator(_unico(_do_curso("course.create", "curso_a2"), "create"), ana.id, ana.email, ana.name, "admin")
    _checar_ator(_unico(_do_curso("course.price_change", "curso_a2"), "price_change"),
                 ana.id, ana.email, ana.name, "admin")
    ev = _unico(_eventos("payment.refund"), "refund")
    _checar_ator(ev, fin.id, fin.email, fin.name, "financial")

    texto = _dump_tabela()
    assert "Quem Nao Agiu" not in texto, "nome enviado pelo cliente foi gravado"
    assert bruno.email not in texto, "e-mail enviado pelo cliente foi gravado"


def test_a3_token_administrativo_legado_gestao_nao_identifica_pessoa(client):
    token = client.post("/api/admin/login", json={"password": SENHA_LEGADA["admin"]}).json()["token"]
    _criar_ok(client, token, _curso("curso_a3"))
    _put_ok(client, token, "curso_a3", _curso("curso_a3", price=120.0))
    _put_ok(client, token, "curso_a3", _curso("curso_a3", price=120.0, level="Avancado"))

    _checar_ator_legado(_unico(_do_curso("course.create", "curso_a3"), "create"), "admin")
    _checar_ator_legado(_unico(_do_curso("course.price_change", "curso_a3"), "price_change"), "admin")
    _checar_ator_legado(_unico(_do_curso("course.update", "curso_a3"), "update"), "admin")


def test_a4_financeiro_com_jwt_no_reembolso_tem_ator_correto(client, contas):
    fin = contas.fin
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, fin.token, pagamento_id).status_code == 200
    ev = _unico(_eventos("payment.refund"), "refund")
    _checar_ator(ev, fin.id, fin.email, fin.name, "financial")


@pytest.mark.parametrize("perfil", ["financial", "admin"])
def test_a5_reembolso_com_token_administrativo_legado(client, perfil):
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, _legado(perfil), pagamento_id).status_code == 200
    ev = _unico(_eventos("payment.refund"), "refund")
    _checar_ator_legado(ev, perfil)


def test_a5b_gestor_com_jwt_tambem_pode_reembolsar_e_aparece(client, contas):
    ana = contas.ana
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, ana.token, pagamento_id).status_code == 200
    _checar_ator(_unico(_eventos("payment.refund"), "refund"), ana.id, ana.email, ana.name, "admin")


def test_a6_evento_do_sistema_manager_reload_sem_usuario(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_a6"))
    recargas = _eventos("manager_reload")
    assert recargas, "a criacao de curso deveria gravar manager_reload"
    for ev in recargas:
        assert _col(ev, "role") == "system", ev
        assert ev["user_id"] is None, ev
        assert _col(ev, "actor_email") is None, ev
        assert _col(ev, "actor_name") != contas.ana.name, ev


# =========================================================================================
# Grupo B - Alteracao efetuada (changes)
# =========================================================================================

def test_b1_course_create_changes_name_e_price(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b1", name="Curso B1", price=321.5))
    ev = _unico(_do_curso("course.create", "curso_b1"), "create")
    assert _col(ev, "entity_type") == "course"
    assert str(_col(ev, "entity_id")) == "curso_b1"
    mud = _mudancas(ev)
    _checar_mudanca(mud, "name", None, "Curso B1")
    _checar_mudanca(mud, "price", None, 321.5)
    assert _nulo(mud["name"]["before"]) and _nulo(mud["price"]["before"])


def test_b2_price_change_so_preco_antes_e_depois_exatos(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b2", price=100.0))
    _put_ok(client, contas.ana.token, "curso_b2", _curso("curso_b2", price=149.9))
    ev = _unico(_do_curso("course.price_change", "curso_b2"), "price_change")
    assert _col(ev, "entity_type") == "course"
    mud = _mudancas(ev)
    assert set(mud) == {"price"}, f"so o preco mudou, changes = {sorted(mud)}"
    _checar_mudanca(mud, "price", 100.0, 149.9)
    assert not _do_curso("course.update", "curso_b2"), "preco mudou: nao pode virar course.update"


def test_b3_preco_e_outros_campos_um_evento_com_todos_e_so_eles(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b3"))
    novo = _curso("curso_b3", price=180.0, name="Nome Novo", level="Avancado", topics=["top1", "top2"])
    _put_ok(client, contas.ana.token, "curso_b3", novo)

    assert not _do_curso("course.update", "curso_b3"), "preco mudou: nao pode haver course.update"
    ev = _unico(_do_curso("course.price_change", "curso_b3"), "price_change")  # um evento so
    mud = _mudancas(ev)
    assert set(mud) == {"price", "name", "level", "topics"}, f"changes = {sorted(mud)}"
    _checar_mudanca(mud, "price", 100.0, 180.0)
    _checar_mudanca(mud, "name", "Curso E8", "Nome Novo")
    _checar_mudanca(mud, "level", "Iniciante", "Avancado")
    _checar_mudanca(mud, "topics", ["top1"], ["top1", "top2"])


def test_b4_todos_os_12_campos_alterados(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b4"))
    material = {"title": "Apostila", "url": "https://materiais.test/e8/a.pdf", "type": "pdf"}
    novo = _curso(
        "curso_b4", price=210.0, name="Outro Nome", description="Outra descricao", duration_hours=40,
        level="Avancado", target_audience="Gestores", objectives=["o1", "o2"], topics=["t9"],
        benefits=["b9"], faq=[{"question": "q9", "answer": "a9"}], system_prompt="outro prompt",
        materials=[material],
    )
    _put_ok(client, contas.ana.token, "curso_b4", novo)
    ev = _unico(_do_curso("course.price_change", "curso_b4"), "price_change")
    mud = _mudancas(ev)
    assert set(mud) == set(CAMPOS_CURSO), f"faltam/sobram: {set(CAMPOS_CURSO) ^ set(mud)}"
    _checar_mudanca(mud, "price", 100.0, 210.0)
    _checar_mudanca(mud, "description", "Descricao original", "Outra descricao")
    _checar_mudanca(mud, "duration_hours", 10, 40)
    _checar_mudanca(mud, "target_audience", "Todos", "Gestores")
    _checar_mudanca(mud, "objectives", ["obj1"], ["o1", "o2"])
    _checar_mudanca(mud, "benefits", ["ben1"], ["b9"])
    _checar_mudanca(mud, "faq", [{"question": "q1", "answer": "a1"}], [{"question": "q9", "answer": "a9"}])
    _checar_mudanca(mud, "system_prompt", "prompt original", "outro prompt")
    _checar_mudanca(mud, "materials", [], [material])


def test_b5_edicao_sem_preco_gera_course_update_com_so_o_que_mudou(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b5"))
    material = {"title": "Video", "url": "https://materiais.test/e8/v.mp4", "type": "video"}
    novo = _curso("curso_b5", duration_hours=12, materials=[material], benefits=["ben1", "ben2"])
    _put_ok(client, contas.ana.token, "curso_b5", novo)

    assert not _do_curso("course.price_change", "curso_b5"), "preco nao mudou"
    ev = _unico(_do_curso("course.update", "curso_b5"), "update")
    assert _col(ev, "entity_type") == "course"
    mud = _mudancas(ev)
    assert set(mud) == {"duration_hours", "materials", "benefits"}, f"changes = {sorted(mud)}"
    _checar_mudanca(mud, "duration_hours", 10, 12)
    _checar_mudanca(mud, "materials", [], [material])
    _checar_mudanca(mud, "benefits", ["ben1"], ["ben1", "ben2"])


def test_b6_put_identico_gera_update_com_changes_vazio(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b6", price=100.0))
    _put_ok(client, contas.ana.token, "curso_b6", _curso("curso_b6", price=100.0))
    _put_ok(client, contas.ana.token, "curso_b6", _curso("curso_b6", price=100))   # 100 == 100.0: nao e alteracao
    eventos = _do_curso("course.update", "curso_b6")
    assert len(eventos) == 2, eventos
    for ev in eventos:
        assert _col(ev, "entity_type") == "course"
        assert _lista_changes(_col(ev, "changes")) == [], ev
    assert not _do_curso("course.price_change", "curso_b6")


def test_b7_valores_longos_truncados_em_2000_caracteres(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b7"))
    longo1 = "y" * 3000
    _put_ok(client, contas.ana.token, "curso_b7", _curso("curso_b7", description=longo1))
    longo2 = "z" * 3000
    _put_ok(client, contas.ana.token, "curso_b7", _curso("curso_b7", description=longo2))

    primeiro, segundo = _do_curso("course.update", "curso_b7")
    m1 = _mudancas(primeiro)["description"]
    assert _igual(m1["before"], "Descricao original")
    assert 1000 <= _tamanho(m1["after"]) <= 2000, _tamanho(m1["after"])
    assert "y" * 500 in str(m1["after"])

    m2 = _mudancas(segundo)["description"]          # o 'antes' agora e o valor longo
    assert 1000 <= _tamanho(m2["before"]) <= 2000, _tamanho(m2["before"])
    assert 1000 <= _tamanho(m2["after"]) <= 2000, _tamanho(m2["after"])
    assert "y" * 500 in str(m2["before"]) and "z" * 500 in str(m2["after"])

    # lista longa tambem: serializada e cortada em 2000
    muitos = [f"topico-{i:04d}" for i in range(600)]
    _put_ok(client, contas.ana.token, "curso_b7", _curso("curso_b7", description=longo2, topics=muitos))
    ev = _do_curso("course.update", "curso_b7")[-1]
    assert _tamanho(_mudancas(ev)["topics"]["after"]) <= 2000


def test_b8_course_delete_name_e_price_antes_after_nulo(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b8", name="Curso B8", price=77.0))
    r = client.delete("/api/admin/course/curso_b8", headers=_auth(contas.bruno.token))
    assert r.status_code == 200, r.text
    ev = _unico(_do_curso("course.delete", "curso_b8"), "delete")
    assert _col(ev, "entity_type") == "course"
    _checar_ator(ev, contas.bruno.id, contas.bruno.email, contas.bruno.name, "admin")
    mud = _mudancas(ev)
    _checar_mudanca(mud, "name", "Curso B8", None)
    _checar_mudanca(mud, "price", 77.0, None)
    assert _nulo(mud["name"]["after"]) and _nulo(mud["price"]["after"])


def test_b9_payment_refund_entidade_e_changes(client, contas):
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, contas.fin.token, pagamento_id).status_code == 200
    ev = _unico(_eventos("payment.refund"), "refund")
    assert _col(ev, "entity_type") == "payment"
    assert str(_col(ev, "entity_id")) == str(pagamento_id)
    mud = _mudancas(ev)
    _checar_mudanca(mud, "payment.status", "approved", "refunded")
    _checar_mudanca(mud, "enrollment.status", "active", "refunded")


def test_b10_reembolso_repetido_nao_grava_evento_novo(client, contas):
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, contas.fin.token, pagamento_id).status_code == 200
    antes = _eventos()
    r = _reembolsar(client, contas.ana.token, pagamento_id)     # outro ator, mesmo pagamento
    assert r.status_code < 500, r.text
    r = _reembolsar(client, contas.fin.token, pagamento_id)
    assert r.status_code < 500, r.text
    assert len(_eventos("payment.refund")) == 1, "reembolso repetido nao pode duplicar o evento"
    assert _eventos() == antes, "reembolso repetido nao pode gravar nenhum evento"


def test_b11_operacao_que_falha_nao_grava_evento_de_alteracao(client, contas):
    # pagamento inexistente
    r = _reembolsar(client, contas.fin.token, 987654)
    assert r.status_code == 404, r.text
    # curso inexistente
    assert _put(client, contas.ana.token, "curso_nao_existe", _curso("curso_nao_existe")).status_code == 404
    assert client.delete("/api/admin/course/curso_nao_existe", headers=_auth(contas.ana.token)).status_code == 404
    # perfil sem permissao
    pagamento_id, _ = _pagamento()
    assert _reembolsar(client, contas.sup.token, pagamento_id).status_code == 403
    assert _criar(client, contas.sup.token, _curso("curso_b11")).status_code == 403
    assert _criar(client, contas.fin.token, _curso("curso_b11")).status_code == 403
    # id duplicado (400)
    _criar_ok(client, contas.ana.token, _curso("curso_b11_dup"))
    assert _criar(client, contas.bruno.token, _curso("curso_b11_dup")).status_code == 400

    assert _eventos("payment.refund") == []
    assert _eventos("course.update") == [] and _eventos("course.delete") == []
    assert len(_eventos("course.create")) == 1, "so a criacao bem-sucedida de curso_b11_dup"
    assert not [e for e in _eventos() if "curso_b11)" in (e["detail"] or "") and "dup" not in (e["detail"] or "")]


def test_b12_detail_continua_preenchido_nos_eventos(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_b12", price=100.0))
    _put_ok(client, contas.ana.token, "curso_b12", _curso("curso_b12", price=140.0))
    pagamento_id, _ = _pagamento()
    _reembolsar(client, contas.fin.token, pagamento_id)
    for acao in ("course.create", "course.price_change", "payment.refund"):
        ev = _eventos(acao)[-1]
        assert (ev["detail"] or "").strip(), f"detail vazio em {acao}"


# =========================================================================================
# Grupo C - Login
# =========================================================================================

@pytest.mark.parametrize("perfil", ["admin", "financial", "support"])
def test_c1_staff_login_jwt_grava_quem_entrou(client, perfil):
    conta = _conta(f"{perfil}.c1@e8.test", f"Func {perfil} C1", perfil, senha=SENHA)
    r = client.post("/api/token", data={"username": conta.email, "password": SENHA})
    assert r.status_code == 200, r.text
    ev = _unico(_eventos("staff.login"), "staff.login")
    _checar_ator(ev, conta.id, conta.email, conta.name, perfil)
    assert not _eventos("staff.login_failed")
    assert SENHA not in _dump_tabela()


@pytest.mark.parametrize("perfil", ["admin", "financial", "support"])
def test_c2_staff_login_legado_grava_so_o_perfil(client, perfil):
    r = client.post("/api/admin/login", json={"password": SENHA_LEGADA[perfil]})
    assert r.status_code == 200, r.text
    ev = _unico(_eventos("staff.login"), "staff.login")
    _checar_ator_legado(ev, perfil)
    assert not _eventos("staff.login_failed")
    assert SENHA_LEGADA[perfil] not in _dump_tabela()


def test_c3_falha_de_conta_de_funcionario_existente(client):
    conta = _conta("gestor.c3@e8.test", "Gestor C3", "admin", senha=SENHA)
    errada = "senha-errada-c3-MARCADOR"
    r = client.post("/api/token", data={"username": conta.email, "password": errada})
    assert r.status_code == 400, r.text
    ev = _unico(_eventos("staff.login_failed"), "staff.login_failed")
    assert _col(ev, "user_id") in (None, conta.id), ev          # conta alvo ou nada (D45 nao fixa)
    assert _col(ev, "actor_email") in (None, conta.email), ev
    assert not _eventos("staff.login"), "falha nao pode virar login bem-sucedido"
    assert errada not in _dump_tabela(), "a senha digitada nunca e gravada"


def test_c4_senha_administrativa_invalida(client):
    errada = "senha-admin-errada-c4-MARCADOR"
    r = client.post("/api/admin/login", json={"password": errada})
    assert r.status_code == 401, r.text
    ev = _unico(_eventos("staff.login_failed"), "staff.login_failed")
    assert _col(ev, "user_id") is None, ev
    assert _col(ev, "actor_email") is None, ev
    assert not _eventos("staff.login")
    assert errada not in _dump_tabela(), "a senha digitada nunca e gravada"


def test_c5_email_inexistente_e_senha_digitada_nunca_aparecem(client):
    _conta("gestor.c5@e8.test", "Gestor C5", "admin", senha=SENHA)
    email_fantasma = "fantasma.c5.MARCADOR@e8.test"
    senha_digitada = "senha-digitada-c5-MARCADOR"
    r = client.post("/api/token", data={"username": email_fantasma, "password": senha_digitada})
    assert r.status_code == 400, r.text
    # tambem falha em conta existente: a senha digitada nao aparece, nem o e-mail digitado errado
    r = client.post("/api/token", data={"username": "gestor.c5@e8.test", "password": senha_digitada})
    assert r.status_code == 400, r.text
    r = client.post("/api/admin/login", json={"password": senha_digitada})
    assert r.status_code == 401, r.text
    texto = _dump_tabela()
    assert email_fantasma not in texto and "fantasma.c5" not in texto
    assert senha_digitada not in texto and "MARCADOR" not in texto
    assert _eventos("staff.login_failed"), "as falhas de conta existente/senha administrativa sao auditadas"


def test_c6_login_de_aluno_nao_gera_evento(client):
    aluno = _conta("aluno.c6@e8.test", "Aluno C6", "student", senha=SENHA)
    ok = client.post("/api/token", data={"username": aluno.email, "password": SENHA})
    assert ok.status_code == 200, ok.text
    ruim = client.post("/api/token", data={"username": aluno.email, "password": "senha-errada-aluno-c6"})
    assert ruim.status_code == 400, ruim.text
    assert _eventos() == [], f"login de aluno (certo ou errado) nao e auditado: {_eventos()}"


# =========================================================================================
# Grupo D - Estampa de tempo
# =========================================================================================

def test_d1_created_at_preenchido_e_recente(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_d1"))
    _put_ok(client, contas.ana.token, "curso_d1", _curso("curso_d1", price=111.0))
    conta = _conta("gestor.d1@e8.test", "Gestor D1", "admin", senha=SENHA)
    assert client.post("/api/token", data={"username": conta.email, "password": SENHA}).status_code == 200

    novos = [ev for ev in _eventos() if ev["action"] in ("course.create", "course.price_change", "staff.login")]
    assert {ev["action"] for ev in novos} == {"course.create", "course.price_change", "staff.login"}
    for ev in novos:
        assert ev["created_at"], f"created_at vazio em {ev['action']}"
        assert _perto_de_agora(ev["created_at"]), f"created_at fora da janela: {ev['created_at']}"


# =========================================================================================
# Grupo E - Endpoint
# =========================================================================================

def test_e1_campos_novos_presentes_e_changes_e_lista(client, contas):
    ana = contas.ana
    _criar_ok(client, ana.token, _curso("curso_e1", price=100.0))
    _put_ok(client, ana.token, "curso_e1", _curso("curso_e1", price=120.0))

    logs = _listar(client, ana.token)
    for item in logs:
        assert CAMPOS_ENDPOINT <= set(item), f"campos ausentes: {CAMPOS_ENDPOINT - set(item)}"
        assert isinstance(item["changes"], list), f"changes deve ser lista, veio {type(item['changes']).__name__}"

    criacao = next(i for i in logs if i["action"] == "course.create")
    assert (criacao["user_id"], criacao["actor_email"], criacao["actor_name"], criacao["role"]) == \
        (ana.id, ana.email, ana.name, "admin")
    assert criacao["entity_type"] == "course" and str(criacao["entity_id"]) == "curso_e1"
    assert {c["field"] for c in criacao["changes"]} >= {"name", "price"}
    assert criacao["created_at"] and criacao["detail"]

    preco = next(i for i in logs if i["action"] == "course.price_change")
    _checar_mudanca(_mudancas(preco), "price", 100.0, 120.0)

    # evento sem alteracao: lista vazia (nunca null nem texto)
    recarga = next(i for i in logs if i["action"] == "manager_reload")
    assert recarga["changes"] == [] and recarga["role"] == "system"
    assert recarga["user_id"] is None and recarga["actor_email"] is None


def test_e1b_evento_gravado_por_add_audit_log_antigo_vem_com_changes_vazio(client, contas):
    Database.add_audit_log("legado.x", "evento simples", role="admin")
    item = next(i for i in _listar(client, contas.ana.token) if i["action"] == "legado.x")
    assert CAMPOS_ENDPOINT <= set(item)
    assert item["changes"] == []
    assert item["actor_email"] is None and item["actor_name"] is None
    assert item["entity_type"] is None and item["entity_id"] is None


def test_e2_filtros_action_e_user_id(client, contas):
    ana, bruno = contas.ana, contas.bruno
    _criar_ok(client, ana.token, _curso("curso_e2_x", price=100.0))
    _criar_ok(client, bruno.token, _curso("curso_e2_y", price=100.0))
    _put_ok(client, ana.token, "curso_e2_x", _curso("curso_e2_x", price=110.0))
    _put_ok(client, bruno.token, "curso_e2_y", _curso("curso_e2_y", price=120.0))
    _put_ok(client, bruno.token, "curso_e2_y", _curso("curso_e2_y", price=120.0, level="Avancado"))

    so_preco = _listar(client, ana.token, action="course.price_change")
    assert len(so_preco) == 2 and {i["action"] for i in so_preco} == {"course.price_change"}
    assert {i["user_id"] for i in so_preco} == {ana.id, bruno.id}

    do_bruno = _listar(client, ana.token, user_id=bruno.id)
    assert do_bruno, "o filtro por user_id nao pode devolver vazio"
    assert {i["user_id"] for i in do_bruno} == {bruno.id}
    assert {i["action"] for i in do_bruno} == {"course.create", "course.price_change", "course.update"}

    combinado = _listar(client, ana.token, action="course.price_change", user_id=ana.id)
    assert len(combinado) == 1
    assert combinado[0]["user_id"] == ana.id and str(combinado[0]["entity_id"]) == "curso_e2_x"

    assert _listar(client, ana.token, action="acao.inexistente") == []
    assert _listar(client, ana.token, user_id=987654) == []


def test_e3a_limit_padrao_e_100(client, contas):
    _semear(120)
    logs = _listar(client, contas.ana.token)
    assert len(logs) == 100
    assert logs[0]["detail"] == "seed-119", "os 100 mais recentes, do mais novo para o mais antigo"
    assert logs[-1]["detail"] == "seed-20"


def test_e3b_limit_explicito_e_maximo_500(client, contas):
    _semear(520)
    assert len(_listar(client, contas.ana.token, limit=7)) == 7
    assert len(_listar(client, contas.ana.token, limit=500)) == 500
    acima = _listar(client, contas.ana.token, limit=9999)
    assert len(acima) == 500, f"limit acima do maximo vale 500, vieram {len(acima)}"
    assert acima[0]["detail"] == "seed-519"


def test_e4_ordem_decrescente_por_id(client, contas):
    _criar_ok(client, contas.ana.token, _curso("curso_e4"))
    _put_ok(client, contas.bruno.token, "curso_e4", _curso("curso_e4", price=101.0))
    _semear(5)
    ids = [i["id"] for i in _listar(client, contas.ana.token)]
    assert len(ids) >= 8
    assert ids == sorted(ids, reverse=True)
    assert len(set(ids)) == len(ids)


def _tokens_sem_permissao(contas):
    return {
        "jwt_financeiro": contas.fin.token,
        "jwt_suporte": contas.sup.token,
        "jwt_aluno": contas.aluno.token,
        "legado_financeiro": _legado("financial"),
        "legado_suporte": _legado("support"),
    }


@pytest.mark.parametrize("quem", ["jwt_financeiro", "jwt_suporte", "jwt_aluno", "legado_financeiro", "legado_suporte"])
def test_e5a_perfil_sem_permissao_recebe_403(client, contas, quem):
    token = _tokens_sem_permissao(contas)[quem]
    assert client.get(ROTA, headers=_auth(token)).status_code == 403
    assert client.get(ROTA, headers=_auth(token), params={"user_id": contas.ana.id, "limit": 5}).status_code == 403


def test_e5b_sem_token_e_token_forjado_recebem_401(client, contas):
    assert client.get(ROTA).status_code == 401
    assert client.get(ROTA, headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get(ROTA, headers=_auth(_forjado("admin"))).status_code == 401
    assert client.get(ROTA, headers=_auth("lixo-sem-formato")).status_code == 401
    legado_adulterado = _legado("support")[:-4] + "AAAA"     # assinatura quebrada
    assert client.get(ROTA, headers=_auth(legado_adulterado)).status_code == 401


def test_e5c_gestao_acessa_com_jwt_e_com_token_legado(client, contas):
    assert client.get(ROTA, headers=_auth(contas.ana.token)).status_code == 200
    assert client.get(ROTA, headers=_auth(_legado("admin"))).status_code == 200


@pytest.mark.parametrize("metodo", ["put", "patch", "delete", "post"])
def test_e6a_metodos_de_escrita_na_colecao_devolvem_405(client, contas, metodo):
    _semear(1)
    antes = _eventos()
    r = client.request(metodo.upper(), ROTA, headers=_auth(contas.ana.token), json={"action": "x"})
    assert r.status_code == 405, f"{metodo.upper()} {ROTA} -> {r.status_code}"
    assert _eventos() == antes


@pytest.mark.parametrize("metodo", ["put", "patch", "delete", "post"])
def test_e6b_nenhuma_rota_de_item_altera_ou_apaga_evento(client, contas, metodo):
    ev_id = Database.add_audit_log("legado.y", "x", role="admin")
    antes = _eventos()
    r = client.request(metodo.upper(), f"{ROTA}/{ev_id}", headers=_auth(contas.ana.token), json={"action": "x"})
    assert r.status_code in (404, 405), f"{metodo.upper()} {ROTA}/{ev_id} -> {r.status_code}"
    assert _eventos() == antes


# =========================================================================================
# Grupo F - Append-only
# =========================================================================================

def _semente_com_evento_completo(client, contas):
    """Um evento com os campos novos preenchidos (se a coluna nao existir, o teste reprova nela)."""
    _criar_ok(client, contas.ana.token, _curso("curso_f"))
    ev = _unico(_do_curso("course.create", "curso_f"), "create")
    _col(ev, "actor_email")
    return ev


def test_f1_update_direto_levanta_erro_e_nao_altera(client, contas):
    ev = _semente_com_evento_completo(client, contas)
    antes = _eventos()
    for sql, params in [
        ("UPDATE audit_logs SET detail = 'adulterado' WHERE id = ?", (ev["id"],)),
        ("UPDATE audit_logs SET actor_email = 'outro@e8.test' WHERE id = ?", (ev["id"],)),
        ("UPDATE audit_logs SET changes = '[]' WHERE id = ?", (ev["id"],)),
        ("UPDATE audit_logs SET role = 'admin'", ()),
    ]:
        with pytest.raises(sqlite3.DatabaseError) as exc:
            _executar(sql, params)
        assert "no such column" not in str(exc.value).lower(), f"erro por coluna ausente, nao pelo trigger: {exc.value}"
    assert _eventos() == antes, "nenhuma linha pode ter mudado"


def test_f2_delete_direto_levanta_erro_e_nao_apaga(client, contas):
    ev = _semente_com_evento_completo(client, contas)
    antes = _eventos()
    with pytest.raises(sqlite3.DatabaseError):
        _executar("DELETE FROM audit_logs WHERE id = ?", (ev["id"],))
    with pytest.raises(sqlite3.DatabaseError):
        _executar("DELETE FROM audit_logs")
    assert _eventos() == antes


def test_f3_insert_continua_funcionando(client, contas):
    _semente_com_evento_completo(client, contas)
    antes = len(_eventos())
    _executar("INSERT INTO audit_logs (user_id, role, action, detail) VALUES (NULL, 'system', 'direto.sql', 'ok')")
    assert len(_eventos()) == antes + 1
    novo_id = Database.add_audit_log("direto.api", "ok", role="system")
    assert isinstance(novo_id, int)
    assert len(_eventos()) == antes + 2
    # e os eventos de verdade continuam sendo gravados pelas rotas depois de existirem os triggers
    _put_ok(client, contas.ana.token, "curso_f", _curso("curso_f", price=190.0))
    assert len(_do_curso("course.price_change", "curso_f")) == 1


# =========================================================================================
# Grupo G - Compatibilidade
# =========================================================================================

def _colunas(tabela="audit_logs"):
    return {r["name"] for r in _sql(f"PRAGMA table_info({tabela})")}


def _triggers():
    return {r["name"]: r["sql"] for r in _sql(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit_logs'")}


def _criar_banco_antigo(caminho, linhas):
    conn = sqlite3.connect(caminho)
    conn.execute("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.executemany(
        "INSERT INTO audit_logs (user_id, role, action, detail, created_at) VALUES (?, ?, ?, ?, ?)", linhas)
    conn.commit()
    conn.close()


LINHAS_ANTIGAS = [
    (None, "admin", "course.create", "Curso 'Velho' (velho) criado com preço R$ 10.00", "2026-01-10 08:00:00"),
    (None, "admin", "course.price_change", "Curso 'Velho' (velho): preço alterado de R$ 10.00 para R$ 20.00", "2026-01-11 09:30:00"),
    (3, None, "login.test", "evento via conta", "2026-01-12 10:45:00"),
]


def test_g1_esquema_novo_colunas_e_triggers(banco):
    assert CAMPOS_NOVOS <= _colunas(), f"faltam colunas: {CAMPOS_NOVOS - _colunas()}"
    assert {"id", "user_id", "role", "action", "detail", "created_at"} <= _colunas()
    gatilhos = _triggers()
    assert len(gatilhos) >= 2, f"esperados triggers de UPDATE e DELETE em audit_logs, achei {sorted(gatilhos)}"
    sqls = " ".join((s or "").upper() for s in gatilhos.values())
    assert re.search(r"(BEFORE|AFTER)\s+UPDATE", sqls), sqls
    assert re.search(r"(BEFORE|AFTER)\s+DELETE", sqls), sqls


def test_g2_banco_antigo_ganha_colunas_e_triggers_sem_perder_linhas(db_path):
    _criar_banco_antigo(db_path, LINHAS_ANTIGAS)
    assert not (CAMPOS_NOVOS & _colunas()), "pre-condicao: o banco antigo nao tem as colunas novas"
    antes = _sql("SELECT id, user_id, role, action, detail, created_at FROM audit_logs ORDER BY id")
    assert len(antes) == 3

    Database.init_db()

    assert CAMPOS_NOVOS <= _colunas(), f"faltam colunas: {CAMPOS_NOVOS - _colunas()}"
    depois = _sql("SELECT id, user_id, role, action, detail, created_at FROM audit_logs ORDER BY id")
    assert depois == antes, "init_db nao pode perder nem alterar linhas antigas"
    assert len(_triggers()) >= 2, "banco migrado precisa dos triggers append-only"
    with pytest.raises(sqlite3.DatabaseError):
        _executar("UPDATE audit_logs SET detail = 'adulterado' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError):
        _executar("DELETE FROM audit_logs WHERE id = 1")
    assert _sql("SELECT detail FROM audit_logs WHERE id = 1")[0]["detail"] == LINHAS_ANTIGAS[0][3]


def test_g3_eventos_antigos_listados_com_campos_novos_nulos_e_changes_vazio(db_path, cursos):
    _criar_banco_antigo(db_path, LINHAS_ANTIGAS)
    Database.init_db()
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        logs = _listar(c, _legado("admin"))
    por_acao = {i["action"]: i for i in logs}
    assert {"course.create", "course.price_change", "login.test"} <= set(por_acao)
    for item in logs:
        assert CAMPOS_ENDPOINT <= set(item)
        assert item["actor_email"] is None and item["actor_name"] is None
        assert item["entity_type"] is None and item["entity_id"] is None
        assert item["changes"] == []
    assert por_acao["login.test"]["user_id"] == 3 and por_acao["login.test"]["role"] is None
    assert por_acao["course.create"]["role"] == "admin"
    assert por_acao["course.price_change"]["detail"] == LINHAS_ANTIGAS[1][3]
    assert por_acao["course.create"]["created_at"] == LINHAS_ANTIGAS[0][4]
    ids = [i["id"] for i in logs]
    assert ids == sorted(ids, reverse=True)


def test_g4_assinatura_antiga_de_add_audit_log_continua_valida(banco):
    log_id = Database.add_audit_log("x", "y", role="admin")
    assert isinstance(log_id, int)
    log_id2 = Database.add_audit_log("x2", "y2")
    log_id3 = Database.add_audit_log("x3", "y3", user_id=7)
    linhas = {r["id"]: r for r in _eventos()}
    assert linhas[log_id]["role"] == "admin" and linhas[log_id]["action"] == "x" and linhas[log_id]["detail"] == "y"
    assert linhas[log_id2]["role"] == "system", "sem role nem user_id o evento e do sistema"
    assert linhas[log_id3]["user_id"] == 7
    for r in linhas.values():
        assert r["actor_email"] is None and r["actor_name"] is None
        assert r["entity_type"] is None and r["entity_id"] is None
        assert _lista_changes(r["changes"]) == []


def test_g5_init_db_idempotente(db_path):
    _criar_banco_antigo(db_path, LINHAS_ANTIGAS)
    Database.init_db()
    colunas1, gatilhos1 = _colunas(), _triggers()
    linhas1 = _sql("SELECT * FROM audit_logs ORDER BY id")
    Database.init_db()
    Database.init_db()
    assert _colunas() == colunas1
    assert _triggers() == gatilhos1
    assert _sql("SELECT * FROM audit_logs ORDER BY id") == linhas1
    assert CAMPOS_NOVOS <= colunas1
    with pytest.raises(sqlite3.DatabaseError):
        _executar("UPDATE audit_logs SET detail = 'x'")
    new_id = Database.add_audit_log("depois.init", "ok", role="admin")
    assert new_id > len(LINHAS_ANTIGAS)
