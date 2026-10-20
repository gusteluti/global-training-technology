"""S4/S5/U3/U9 - Conta do aluno: revogacao de token, desativar/reativar e perfil (D80, modo autonomo D69).

Escritos ANTES da implementacao. Devem falhar agora: o JWT nao tem a claim `tv`, `users` nao tem `is_active` nem
`token_version`, nao existem as rotas de desativar/reativar nem `/api/student/me` e `/api/student/me/password`, e um
token antigo continua valendo depois de trocar a senha.

Contrato (D80, textos exatos):
  Banco: users.is_active (padrao 1) e users.token_version (padrao 0), migracao idempotente.
  JWT de conta: claim `tv`; token sem `tv` vale como 0. Toda rota autenticada por JWT de conta confere no banco conta
    existente, ativa e `tv` igual; senao 401 ERRO_SESSAO. Token legado de funcionario (HMAC) nao muda.
  S5: definir senha (E2), redefinir senha (B1) e trocar senha logado incrementam token_version.
  S4: POST /api/admin/students/{user_id}/deactivate e /reactivate (so Gestao; id que nao e aluno -> 404 ERRO_ALUNO),
    idempotentes; desativar incrementa token_version; eventos student.deactivate / student.reactivate. Login de aluno
    desativado com a senha certa -> 403 ERRO_DESATIVADA; senha errada -> resposta generica de sempre. Detalhe F3 e
    lista de alunos trazem is_active.
  U3: GET /api/student/me -> {id, name, email, phone}; PUT /api/student/me {name, phone} (e-mail nao muda; nome 1-120
    aparado; telefone opcional, 10 a 15 digitos depois de limpar; invalido -> 422 com mensagem em portugues);
    POST /api/student/me/password {current_password, new_password}: atual errada -> 400 ERRO_SENHA_ATUAL; politica
    D14/D52; sucesso -> {status, token} novo; evento student.password_change. Nada aceita id de usuario do cliente.

Grupos
  T  Claim `tv`: login emite tv igual ao banco; compatibilidade de token sem tv; tv diferente -> 401
  R  Revogacao (S5/S4): token antigo cai em varias rotas depois de definir, redefinir, trocar senha e desativar
  C  Conta apagada, inexistente ou inativa com JWT valido -> 401; funcionario: JWT e legado
  D  Desativar/reativar: RBAC, 404, idempotencia, eventos, token_version, isolamento
  L  Login de aluno desativado (403 so com a senha certa; senha errada generica), reativar devolve o acesso
  F  is_active no detalhe F3 e na lista de alunos
  M  /api/student/me GET/PUT: campos, validacoes, e-mail imutavel, IDOR, RBAC
  P  /api/student/me/password: senha atual, politica, sucesso, evento sem senha, IDOR, RBAC
  G  Migracao idempotente das colunas em banco antigo

Escolhas conservadoras do teste (ver relatorio do agente-testes; nenhuma define politica):
  - GET /api/student/me: os campos id, name, email, phone ficam no NIVEL DE CIMA do corpo (leitura literal da D80);
    chaves extras (ex.: status) sao aceitas.
  - is_active e booleano JSON (true/false). No detalhe F3 fica em `student.is_active`; na lista, em cada item de
    `students`.
  - Corpo de sucesso de desativar/reativar e de PUT /me nao e fixado (so o status 200 e o efeito).
  - Evento de desativar/reativar: action exata, entity_id = id do aluno (texto) e user_id = conta da Gestao do token
    (padrao E8). Evento de troca de senha: action exata e user_id = o proprio aluno. Repetir uma chamada idempotente
    pode ou nao gravar outro evento (nao fixado).
  - Telefone: guardado em qualquer formato cujos digitos sejam os informados. Exemplos invalidos escolhidos para serem
    invalidos em qualquer leitura de "limpar" (9 digitos, 16 digitos, letras com 6 digitos).
  - 422 "em portugues": o corpo menciona "nome" (erros de nome) ou "telefone" (erros de telefone), palavras que nao
    aparecem nas mensagens padrao em ingles do Pydantic (que citam `name`/`phone`).
  - Nova senha fora da politica na troca logada: 400 ou 422 (D80 nao fixa o status), e nada muda.
  - Id nao numerico em desativar: 404 ou 422 (D80 so fixa 404 para ids numericos que nao sao de aluno).
  - Limite da D79 (5 falhas por e-mail): nenhum teste faz mais de 2 logins errados no mesmo e-mail; a senha e
    conferida no banco (verify_password) em vez de por login sempre que possivel.
Banco temporario (conftest), cursos em diretorio temporario, catalogo do bot temporario (D70), LLM e Mercado Pago
falsos. Nada toca backend/db.sqlite, backend/courses, o Groq ou a rede.
"""

import json
import os
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from agents.groq_client import GroqChatClient
from core.password_setup import emitir_token_com_limite, emitir_token_definicao
from core.security import Role, create_access_token, create_admin_token, get_password_hash, verify_password
from db import Database


REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"

ERRO_SESSAO = "Sessão expirada. Entre novamente."
ERRO_DESATIVADA = "Sua conta está desativada. Fale com o suporte."
ERRO_ALUNO = "Aluno não encontrado"
ERRO_SENHA_ATUAL = "Senha atual incorreta."
ERRO_LOGIN = "Usuário ou senha inválidos"

ROTA_ME = "/api/student/me"
ROTA_SENHA = "/api/student/me/password"
ROTA_DETALHE = "/api/dashboard/alunos/{}"
ROTA_LISTA = "/api/dashboard/alunos"

CURSO = "curso_s4"
PRECO = 180.0

SENHA = "senha-aluno-s4-2026"
SENHA_NOVA = "senha-nova-s4-2026"
SENHA_STAFF = "senha-staff-s4-2026"


def _rota(acao, user_id):
    return f"/api/admin/students/{user_id}/{acao}"


# =====================================================================================
# Fixtures
# =====================================================================================

@pytest.fixture(autouse=True)
def ambiente_s4(monkeypatch, tmp_path):
    """Saida de links/avisos em tmp_path; mock de pagamento desligado (fluxo real com gateway falso)."""
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-s4")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": "Curso S4", "description": "Curso do teste S4", "price": PRECO,
        "materials": [{"title": "Apostila S4", "url": "https://materiais.test/s4/apostila.pdf", "type": "pdf"}],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def llm(monkeypatch):
    chamadas = []

    def falso(self, messages, max_tokens=1024, temperature=0.7):
        chamadas.append(messages)
        return "Resposta do duble S4."

    monkeypatch.setattr(GroqChatClient, "create_chat_completion", falso)
    return chamadas


@pytest.fixture
def gateway():
    def post(url, *args, **kwargs):
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": f"pref-s4-{uuid.uuid4().hex[:6]}", "init_point": "https://mp.test/s4"}
        resposta.text = '{"id": "pref-s4"}'
        return resposta

    with patch("payments.routes.requests.post", side_effect=post) as falso:
        yield falso


@pytest.fixture
def client(banco, cursos, catalogo_bot, llm, gateway):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


def _conta(email, nome, perfil, senha=SENHA):
    user_id = Database.add_user(email, nome, get_password_hash(senha) if senha else None, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, senha=senha,
                           token=create_access_token({"user_id": user_id, "email": email, "role": perfil}))


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        gestao=_conta("gestao.s4@teste.com", "Gestora S4", "admin", SENHA_STAFF),
        fin=_conta("fin.s4@teste.com", "Financeira S4", "financial", SENHA_STAFF),
        sup=_conta("sup.s4@teste.com", "Suporte S4", "support", SENHA_STAFF),
        maria=_conta("maria.s4@teste.com", "Maria Aluna", "student"),
        joao=_conta("joao.s4@teste.com", "Joao Aluno", "student"),
    )


# =====================================================================================
# Helpers
# =====================================================================================

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


def _usuario(user_id):
    linhas = _sql("SELECT * FROM users WHERE id = ?", (user_id,))
    return linhas[0] if linhas else None


def _colunas(tabela="users"):
    return {c["name"]: c for c in _sql(f"PRAGMA table_info({tabela})")}


def _exigir_colunas():
    colunas = _colunas()
    faltam = [c for c in ("is_active", "token_version") if c not in colunas]
    assert not faltam, f"falta(m) a(s) coluna(s) users.{faltam} (D80)"


def _token_version(user_id):
    _exigir_colunas()
    return _usuario(user_id)["token_version"]


def _is_active(user_id):
    _exigir_colunas()
    return _usuario(user_id)["is_active"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _claims(token):
    return jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])


def _jwt(conta, **extra):
    return create_access_token({"user_id": conta.id, "email": conta.email, "role": conta.role, **extra})


def _forjado(role="admin"):
    return jose_jwt.encode({"user_id": 1, "email": "x@s4.test", "role": role, "tv": 0},
                           "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")


def _login(client, email, senha):
    return client.post("/api/token", data={"username": email, "password": senha})


def _token_login(client, email, senha):
    r = _login(client, email, senha)
    assert r.status_code == 200, f"login de {email}: HTTP {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _sessao_expirada(r, onde):
    assert r.status_code == 401, f"{onde}: HTTP {r.status_code} (esperado 401) {r.text[:200]}"
    assert r.json().get("detail") == ERRO_SESSAO, f"{onde}: corpo {r.text[:200]} (esperado detail {ERRO_SESSAO!r})"


def _eventos(acao):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (acao,))


def _desativar(client, token, user_id):
    return client.post(_rota("deactivate", user_id), headers=_auth(token))


def _reativar(client, token, user_id):
    return client.post(_rota("reactivate", user_id), headers=_auth(token))


# Rotas autenticadas por JWT de aluno usadas na prova de revogacao (D80: "toda rota").
ROTAS_ALUNO = [
    ("GET", "/api/student/enrollments", None),
    ("GET", "/api/student/payments", None),
    ("GET", "/api/student/chat/history", None),
    ("POST", "/api/student/chat", {"message": "Quais cursos voces tem?"}),
    ("POST", "/api/student/checkout", {"course_id": CURSO}),
    ("GET", ROTA_ME, None),
    ("PUT", ROTA_ME, {"name": "Nome Trocado Por Token Velho"}),
    ("POST", ROTA_SENHA, {"current_password": SENHA, "new_password": "senha-do-token-velho-1"}),
]


def _chamar(client, metodo, caminho, corpo, token):
    return client.request(metodo, caminho, headers=_auth(token), json=corpo)


def _todas_as_rotas_recusam(client, token, onde):
    """Toda rota de aluno responde 401 ERRO_SESSAO ao token; junta todas as divergencias numa mensagem."""
    falhas = []
    for metodo, caminho, corpo in ROTAS_ALUNO:
        r = _chamar(client, metodo, caminho, corpo, token)
        if r.status_code != 401 or (r.json() or {}).get("detail") != ERRO_SESSAO:
            falhas.append(f"{metodo} {caminho} -> HTTP {r.status_code} {r.text[:120]}")
    assert not falhas, f"{onde}: o token antigo ainda vale ou o 401 nao tem o texto exato:\n" + "\n".join(falhas)


def _token_vale(client, token, onde):
    r = client.get("/api/student/enrollments", headers=_auth(token))
    assert r.status_code == 200, f"{onde}: HTTP {r.status_code} {r.text[:200]}"


# =====================================================================================
# Grupo T - claim `tv`
# =====================================================================================

def test_t1_login_de_aluno_emite_tv_igual_ao_banco(client, contas):
    token = _token_login(client, contas.maria.email, SENHA)
    claims = _claims(token)
    assert "tv" in claims, f"o JWT de conta precisa da claim `tv` (D80): {claims}"
    assert claims["tv"] == _token_version(contas.maria.id) == 0


def test_t2_login_de_funcionario_tambem_emite_tv(client, contas):
    token = _token_login(client, contas.gestao.email, SENHA_STAFF)
    claims = _claims(token)
    assert claims.get("tv") == _token_version(contas.gestao.id) == 0, claims


def test_t3_token_sem_tv_vale_como_versao_zero(client, contas):
    """Compatibilidade: tokens emitidos antes da D80 (sem `tv`) continuam valendo enquanto a versao for 0."""
    assert "tv" not in _claims(contas.maria.token)
    _token_vale(client, contas.maria.token, "token sem tv")
    _exigir_colunas()
    assert _token_version(contas.maria.id) == 0


def test_t4_token_sem_tv_cai_quando_a_versao_do_banco_passa_de_zero(client, contas):
    _exigir_colunas()
    _executar("UPDATE users SET token_version = 1 WHERE id = ?", (contas.maria.id,))
    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(contas.maria.token)), "token sem tv, banco 1")


@pytest.mark.parametrize("tv_token,tv_banco", [(0, 1), (2, 1), (1, 0), (5, 3)])
def test_t5_tv_diferente_do_banco_e_401_com_o_texto_exato(client, contas, tv_token, tv_banco):
    _exigir_colunas()
    _executar("UPDATE users SET token_version = ? WHERE id = ?", (tv_banco, contas.maria.id))
    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(_jwt(contas.maria, tv=tv_token))),
                     f"tv {tv_token} x banco {tv_banco}")


def test_t6_tv_igual_ao_banco_vale(client, contas):
    _exigir_colunas()
    _executar("UPDATE users SET token_version = 3 WHERE id = ?", (contas.maria.id,))
    _token_vale(client, _jwt(contas.maria, tv=3), "tv 3 x banco 3")


# =====================================================================================
# Grupo R - revogacao do token antigo (S5 e S4)
# =====================================================================================

def test_r1_definir_senha_pelo_link_derruba_o_token_antigo(client, contas):
    sem_senha = _conta("sem.senha.s4@teste.com", "Aluno Sem Senha", "student", senha=None)
    _token_vale(client, sem_senha.token, "pre-condicao (token antigo valia)")
    antes = _token_version(sem_senha.id)

    r = client.post("/api/auth/password-setup", json={"token": emitir_token_definicao(sem_senha.id), "password": SENHA})
    assert r.status_code == 200, r.text

    assert _token_version(sem_senha.id) == antes + 1
    _todas_as_rotas_recusam(client, sem_senha.token, "depois de definir a senha (E2)")
    novo = _token_login(client, sem_senha.email, SENHA)
    assert _claims(novo).get("tv") == antes + 1
    _token_vale(client, novo, "token emitido depois de definir a senha")


def test_r2_redefinir_senha_pelo_link_derruba_o_token_antigo(client, contas):
    antigo = _token_login(client, contas.maria.email, SENHA)
    _token_vale(client, antigo, "pre-condicao")
    antes = _token_version(contas.maria.id)
    token_reset = emitir_token_com_limite(contas.maria.id, "reset")
    assert token_reset

    r = client.post("/api/auth/password-reset", json={"token": token_reset, "password": SENHA_NOVA})
    assert r.status_code == 200, r.text

    assert _token_version(contas.maria.id) == antes + 1
    _todas_as_rotas_recusam(client, antigo, "depois de redefinir a senha (B1)")
    _todas_as_rotas_recusam(client, contas.maria.token, "token sem tv depois de redefinir a senha (B1)")
    _token_vale(client, _token_login(client, contas.maria.email, SENHA_NOVA), "token novo depois da redefinicao")


def test_r3_trocar_a_senha_logado_derruba_as_outras_sessoes_e_o_token_usado(client, contas):
    sessao_a = _token_login(client, contas.maria.email, SENHA)
    sessao_b = _token_login(client, contas.maria.email, SENHA)
    _token_vale(client, sessao_b, "pre-condicao")
    antes = _token_version(contas.maria.id)

    r = client.post(ROTA_SENHA, headers=_auth(sessao_a), json={"current_password": SENHA, "new_password": SENHA_NOVA})
    assert r.status_code == 200, r.text
    novo = r.json()["token"]

    assert _token_version(contas.maria.id) == antes + 1
    _todas_as_rotas_recusam(client, sessao_b, "outra sessao depois de trocar a senha")
    _todas_as_rotas_recusam(client, sessao_a, "o token usado na troca (substituido pelo novo)")
    _token_vale(client, novo, "token devolvido pela troca")
    assert client.get(ROTA_ME, headers=_auth(novo)).status_code == 200


def test_r4_desativar_derruba_o_token_do_aluno_em_todas_as_rotas(client, contas):
    sessao = _token_login(client, contas.maria.email, SENHA)
    _token_vale(client, sessao, "pre-condicao")
    antes = _token_version(contas.maria.id)

    r = _desativar(client, contas.gestao.token, contas.maria.id)
    assert r.status_code == 200, r.text

    assert _token_version(contas.maria.id) > antes, "desativar incrementa token_version (D80)"
    _todas_as_rotas_recusam(client, sessao, "depois de desativar")
    _todas_as_rotas_recusam(client, contas.maria.token, "token sem tv depois de desativar")


def test_r5_revogacao_de_um_aluno_nao_afeta_outro(client, contas):
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    r = client.post(ROTA_SENHA, headers=_auth(contas.joao.token),
                    json={"current_password": SENHA, "new_password": SENHA_NOVA})
    assert r.status_code == 200, r.text
    # o joao trocou a senha e a maria foi desativada: os tokens da Gestao e o novo do joao seguem valendo
    _token_vale(client, r.json()["token"], "novo token do joao")
    assert client.get(ROTA_LISTA, headers=_auth(contas.gestao.token)).status_code == 200


def test_r6_o_401_de_sessao_nao_cria_nada_nem_chama_o_llm_nem_o_gateway(client, contas, llm, gateway):
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    _sessao_expirada(client.post("/api/student/chat", headers=_auth(contas.maria.token), json={"message": "Oi"}),
                     "chat")
    _sessao_expirada(client.post("/api/student/checkout", headers=_auth(contas.maria.token),
                                 json={"course_id": CURSO}), "checkout")
    assert llm == [], "o LLM nao pode ser chamado com token revogado"
    assert gateway.call_count == 0, "o gateway nao pode ser chamado com token revogado"
    assert _sql("SELECT * FROM enrollments") == []
    assert _sql("SELECT * FROM chat_messages") == []


# =====================================================================================
# Grupo C - conta apagada, inexistente, inativa; funcionario
# =====================================================================================

def test_c1_conta_apagada_com_jwt_valido_e_401_com_o_texto_exato(client, contas):
    _token_vale(client, contas.joao.token, "pre-condicao")
    _executar("DELETE FROM users WHERE id = ?", (contas.joao.id,))
    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(contas.joao.token)), "conta apagada")


def test_c2_conta_que_nunca_existiu_com_jwt_valido_e_401_com_o_texto_exato(client, contas):
    fantasma = create_access_token({"user_id": 987654, "email": "fantasma.s4@teste.com", "role": "student", "tv": 0})
    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(fantasma)), "conta inexistente")


def test_c3_conta_inativa_com_tv_igual_tambem_e_401(client, contas):
    """is_active e conferido por si: mesmo sem mexer em token_version, conta inativa nao autentica."""
    _exigir_colunas()
    _executar("UPDATE users SET is_active = 0 WHERE id = ?", (contas.maria.id,))
    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(contas.maria.token)), "conta inativa")
    _sessao_expirada(client.get(ROTA_ME, headers=_auth(contas.maria.token)), "conta inativa (me)")


@pytest.mark.parametrize("perfil", [Role.ADMIN, Role.FINANCIAL, Role.SUPPORT])
def test_c4_token_legado_de_funcionario_nao_e_afetado(client, contas, perfil):
    r = client.get(ROTA_LISTA, headers=_auth(create_admin_token(perfil)))
    assert r.status_code == 200, r.text


def test_c5_jwt_de_funcionario_sem_tv_continua_valendo(client, contas):
    for conta in (contas.gestao, contas.fin, contas.sup):
        assert "tv" not in _claims(conta.token)
        r = client.get(ROTA_LISTA, headers=_auth(conta.token))
        assert r.status_code == 200, f"{conta.role}: {r.text[:200]}"


def test_c6_jwt_de_funcionario_com_tv_diferente_e_401(client, contas):
    _exigir_colunas()
    r = client.get(ROTA_LISTA, headers=_auth(_jwt(contas.gestao, tv=3)))
    _sessao_expirada(r, "JWT de funcionario com tv 3 x banco 0")


def test_c7_token_forjado_continua_401(client, contas):
    assert client.get("/api/student/enrollments", headers=_auth(_forjado("student"))).status_code == 401
    assert client.get(ROTA_ME, headers=_auth(_forjado("student"))).status_code == 401


# =====================================================================================
# Grupo D - desativar / reativar
# =====================================================================================

@pytest.mark.parametrize("acao", ["deactivate", "reactivate"])
def test_d1_rbac_so_gestao(client, contas, acao):
    _exigir_colunas()
    if acao == "reactivate":
        _executar("UPDATE users SET is_active = 0 WHERE id = ?", (contas.maria.id,))
    estado = _is_active(contas.maria.id)
    tv = _token_version(contas.maria.id)
    casos = {
        "financeiro (JWT)": (contas.fin.token, 403),
        "suporte (JWT)": (contas.sup.token, 403),
        "financeiro (legado)": (create_admin_token(Role.FINANCIAL), 403),
        "suporte (legado)": (create_admin_token(Role.SUPPORT), 403),
        "aluno": (contas.joao.token, 403),
        "forjado": (_forjado("admin"), 401),
    }
    for nome, (token, esperado) in casos.items():
        r = client.post(_rota(acao, contas.maria.id), headers=_auth(token))
        assert r.status_code == esperado, f"{acao} por {nome}: HTTP {r.status_code} (esperado {esperado})"
    r = client.post(_rota(acao, contas.maria.id))
    assert r.status_code == 401, f"{acao} sem token: HTTP {r.status_code}"
    assert _is_active(contas.maria.id) == estado and _token_version(contas.maria.id) == tv, "nada pode mudar"
    assert _eventos(f"student.{acao}") == []

    r = client.post(_rota(acao, contas.maria.id), headers=_auth(contas.gestao.token))
    assert r.status_code == 200, f"{acao} pela Gestao: HTTP {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("acao", ["deactivate", "reactivate"])
def test_d2_id_que_nao_e_aluno_e_404_com_o_texto_exato(client, contas, acao):
    _exigir_colunas()
    for alvo in (contas.gestao.id, contas.fin.id, contas.sup.id, 999999, 0, -1, 2 ** 63):
        r = client.post(_rota(acao, alvo), headers=_auth(contas.gestao.token))
        assert r.status_code == 404, f"{acao} {alvo}: HTTP {r.status_code} {r.text[:200]}"
        assert r.json() == {"detail": ERRO_ALUNO}, f"{acao} {alvo}: {r.text[:200]}"
    r = client.post(_rota(acao, "abc"), headers=_auth(contas.gestao.token))
    assert r.status_code in (404, 422), f"{acao} id nao numerico: HTTP {r.status_code}"
    for conta in (contas.gestao, contas.fin, contas.sup):
        assert _usuario(conta.id)["is_active"] == 1 and _usuario(conta.id)["token_version"] == 0, conta.role
    # funcionario continua entrando com o mesmo token
    assert client.get(ROTA_LISTA, headers=_auth(contas.fin.token)).status_code == 200


def test_d3_desativar_e_idempotente(client, contas):
    for vez in (1, 2):
        r = _desativar(client, contas.gestao.token, contas.maria.id)
        assert r.status_code == 200, f"desativar ({vez}a vez): HTTP {r.status_code} {r.text[:200]}"
        assert _is_active(contas.maria.id) == 0
    assert _token_version(contas.maria.id) >= 1


def test_d4_reativar_e_idempotente_e_conta_ativa_pode_ser_reativada(client, contas):
    r = _reativar(client, contas.gestao.token, contas.maria.id)
    assert r.status_code == 200, f"reativar conta ja ativa: HTTP {r.status_code} {r.text[:200]}"
    assert _is_active(contas.maria.id) == 1
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    for vez in (1, 2):
        r = _reativar(client, contas.gestao.token, contas.maria.id)
        assert r.status_code == 200, f"reativar ({vez}a vez): HTTP {r.status_code}"
        assert _is_active(contas.maria.id) == 1


def test_d5_eventos_de_desativar_e_reativar_com_o_responsavel_do_token(client, contas):
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    eventos = _eventos("student.deactivate")
    assert eventos, "desativar grava student.deactivate"
    assert eventos[0]["entity_id"] == str(contas.maria.id), eventos[0]
    assert eventos[0]["user_id"] == contas.gestao.id, eventos[0]

    assert _reativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    eventos = _eventos("student.reactivate")
    assert eventos, "reativar grava student.reactivate"
    assert eventos[-1]["entity_id"] == str(contas.maria.id), eventos[-1]
    assert eventos[-1]["user_id"] == contas.gestao.id, eventos[-1]
    texto = json.dumps(_sql("SELECT * FROM audit_logs"), ensure_ascii=False, default=str)
    assert SENHA not in texto


def test_d6_desativar_nao_mexe_na_senha_nem_nas_matriculas(client, contas):
    Database.create_enrollment(contas.maria.id, CURSO, f"{CURSO}:s4:{uuid.uuid4().hex}")
    hash_antes = _usuario(contas.maria.id)["password_hash"]
    matriculas = _sql("SELECT * FROM enrollments WHERE user_id = ?", (contas.maria.id,))
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    assert _usuario(contas.maria.id)["password_hash"] == hash_antes
    assert _sql("SELECT * FROM enrollments WHERE user_id = ?", (contas.maria.id,)) == matriculas


# =====================================================================================
# Grupo L - login de aluno desativado
# =====================================================================================

def test_l1_desativado_com_a_senha_certa_recebe_403_com_o_texto_exato_e_sem_token(client, contas):
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    r = _login(client, contas.maria.email, SENHA)
    assert r.status_code == 403, f"HTTP {r.status_code} {r.text[:200]}"
    assert r.json() == {"detail": ERRO_DESATIVADA}, r.text
    assert "access_token" not in r.text


def test_l2_desativado_com_a_senha_errada_recebe_a_resposta_generica_de_sempre(client, contas):
    ativo = _login(client, contas.joao.email, "senha-errada-s4")
    inexistente = _login(client, "ninguem.s4@teste.com", "senha-errada-s4")
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    desativado = _login(client, contas.maria.email, "senha-errada-s4")
    for r in (ativo, inexistente, desativado):
        assert r.status_code == 400, r.text
    assert desativado.json() == ativo.json() == inexistente.json() == {"detail": ERRO_LOGIN}
    assert ERRO_DESATIVADA not in desativado.text


def test_l3_reativar_devolve_o_acesso_com_login_novo_e_o_token_antigo_continua_morto(client, contas):
    antigo = _token_login(client, contas.maria.email, SENHA)
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    assert _reativar(client, contas.gestao.token, contas.maria.id).status_code == 200

    _sessao_expirada(client.get("/api/student/enrollments", headers=_auth(antigo)), "token anterior a desativacao")
    novo = _token_login(client, contas.maria.email, SENHA)
    assert _claims(novo).get("tv") == _token_version(contas.maria.id)
    _token_vale(client, novo, "login depois de reativar")


def test_l4_login_de_funcionario_continua_funcionando(client, contas):
    token = _token_login(client, contas.gestao.email, SENHA_STAFF)
    assert client.get(ROTA_LISTA, headers=_auth(token)).status_code == 200


# =====================================================================================
# Grupo F - is_active no detalhe F3 e na lista de alunos
# =====================================================================================

def _item_da_lista(client, token, user_id):
    r = client.get(ROTA_LISTA, headers=_auth(token), params={"page_size": 200})
    assert r.status_code == 200, r.text
    itens = [s for s in r.json()["students"] if s.get("id") == user_id]
    assert len(itens) == 1, f"o aluno {user_id} precisa aparecer na lista (desativado tambem)"
    return itens[0]


def test_f1_detalhe_e_lista_trazem_is_active_true_para_aluno_ativo(client, contas):
    r = client.get(ROTA_DETALHE.format(contas.maria.id), headers=_auth(contas.gestao.token))
    assert r.status_code == 200, r.text
    assert r.json()["student"].get("is_active") is True, r.json()["student"]
    assert _item_da_lista(client, contas.gestao.token, contas.maria.id).get("is_active") is True


def test_f2_detalhe_e_lista_trazem_is_active_false_depois_de_desativar_e_true_depois_de_reativar(client, contas):
    assert _desativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    for token in (contas.gestao.token, contas.fin.token, contas.sup.token):
        r = client.get(ROTA_DETALHE.format(contas.maria.id), headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["student"].get("is_active") is False, r.json()["student"]
        assert _item_da_lista(client, token, contas.maria.id).get("is_active") is False
    assert _item_da_lista(client, contas.gestao.token, contas.joao.id).get("is_active") is True

    assert _reativar(client, contas.gestao.token, contas.maria.id).status_code == 200
    r = client.get(ROTA_DETALHE.format(contas.maria.id), headers=_auth(contas.gestao.token))
    assert r.json()["student"].get("is_active") is True


# =====================================================================================
# Grupo M - /api/student/me
# =====================================================================================

def test_m1_get_me_devolve_os_dados_do_dono_do_token(client, contas):
    r = client.get(ROTA_ME, headers=_auth(contas.maria.token))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert {k: corpo.get(k) for k in ("id", "name", "email", "phone")} == {
        "id": contas.maria.id, "name": "Maria Aluna", "email": contas.maria.email, "phone": None,
    }, corpo
    assert "password_hash" not in r.text and "token_version" not in r.text


def test_m2_get_me_ignora_user_id_da_query(client, contas):
    r = client.get(ROTA_ME, headers=_auth(contas.maria.token), params={"user_id": contas.joao.id, "id": contas.joao.id})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == contas.maria.id and contas.joao.email not in r.text


def test_m3_put_me_apara_o_nome_e_guarda_o_telefone(client, contas):
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token),
                   json={"name": "  Mariana Souza  ", "phone": "(11) 98765-4321"})
    assert r.status_code == 200, r.text
    corpo = client.get(ROTA_ME, headers=_auth(contas.maria.token)).json()
    assert corpo["name"] == "Mariana Souza"
    assert "".join(ch for ch in str(corpo["phone"]) if ch.isdigit()) == "11987654321", corpo
    assert _usuario(contas.maria.id)["name"] == "Mariana Souza"


@pytest.mark.parametrize("telefone,digitos", [
    ("1198765432", "1198765432"),                 # 10 digitos
    ("123456789012345", "123456789012345"),       # 15 digitos
    ("+55 (11) 98765-4321", "5511987654321"),
])
def test_m4_telefone_nos_limites_e_aceito(client, contas, telefone, digitos):
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": "Maria Aluna", "phone": telefone})
    assert r.status_code == 200, r.text
    fone = client.get(ROTA_ME, headers=_auth(contas.maria.token)).json()["phone"]
    assert "".join(ch for ch in str(fone) if ch.isdigit()) == digitos


def test_m5_telefone_e_opcional(client, contas):
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": "Maria Sem Fone"})
    assert r.status_code == 200, r.text
    assert client.put(ROTA_ME, headers=_auth(contas.maria.token),
                      json={"name": "Maria Aluna", "phone": "11987654321"}).status_code == 200
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": "Maria Aluna", "phone": None})
    assert r.status_code == 200, r.text
    assert client.get(ROTA_ME, headers=_auth(contas.maria.token)).json()["phone"] in (None, "")


def test_m6_nome_com_120_caracteres_e_aceito(client, contas):
    nome = "M" + "a" * 119
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": nome})
    assert r.status_code == 200, r.text
    assert client.get(ROTA_ME, headers=_auth(contas.maria.token)).json()["name"] == nome


@pytest.mark.parametrize("nome", ["", "   ", "M" * 121, None])
def test_m7_nome_invalido_e_422_em_portugues_e_nada_muda(client, contas, nome):
    antes = _usuario(contas.maria.id)
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": nome, "phone": "11987654321"})
    assert r.status_code == 422, f"HTTP {r.status_code} {r.text[:200]}"
    assert "nome" in r.text.lower(), f"a mensagem de erro precisa estar em portugues e citar o nome: {r.text[:300]}"
    assert _usuario(contas.maria.id) == antes


@pytest.mark.parametrize("telefone", ["123456789", "1234567890123456", "11 9876-ABCD", "abc"])
def test_m8_telefone_invalido_e_422_em_portugues_e_nada_muda(client, contas, telefone):
    antes = _usuario(contas.maria.id)
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token), json={"name": "Outro Nome", "phone": telefone})
    assert r.status_code == 422, f"{telefone!r}: HTTP {r.status_code} {r.text[:200]}"
    assert "telefone" in r.text.lower(), f"a mensagem precisa estar em portugues e citar o telefone: {r.text[:300]}"
    assert _usuario(contas.maria.id) == antes


def test_m9_email_enviado_no_corpo_e_ignorado(client, contas):
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token),
                   json={"name": "Maria Nova", "email": "trocado.s4@teste.com"})
    assert r.status_code == 200, r.text
    assert _usuario(contas.maria.id)["email"] == contas.maria.email
    assert Database.get_user_by_email("trocado.s4@teste.com") is None
    assert client.get(ROTA_ME, headers=_auth(contas.maria.token)).json()["email"] == contas.maria.email


def test_m10_user_id_e_id_do_corpo_sao_ignorados_idor(client, contas):
    joao_antes = _usuario(contas.joao.id)
    r = client.put(ROTA_ME, headers=_auth(contas.maria.token),
                   json={"name": "Nome Da Maria", "phone": "11912345678", "user_id": contas.joao.id,
                         "id": contas.joao.id, "role": "admin", "is_active": 0, "token_version": 9})
    assert r.status_code == 200, r.text
    assert _usuario(contas.joao.id) == joao_antes, "a conta de outro aluno nao pode mudar"
    maria = _usuario(contas.maria.id)
    assert maria["name"] == "Nome Da Maria"
    assert maria["role"] == "student" and maria["is_active"] == 1 and maria["token_version"] == 0


def test_m11_rbac_de_me(client, contas):
    for conta in (contas.gestao, contas.fin, contas.sup):
        assert client.get(ROTA_ME, headers=_auth(conta.token)).status_code == 403, conta.role
        r = client.put(ROTA_ME, headers=_auth(conta.token), json={"name": "Funcionario Tentando"})
        assert r.status_code == 403, conta.role
        assert _usuario(conta.id)["name"] == conta.name
    assert client.get(ROTA_ME, headers=_auth(create_admin_token(Role.ADMIN))).status_code == 403
    assert client.get(ROTA_ME).status_code == 401
    assert client.put(ROTA_ME, json={"name": "Sem Token"}).status_code == 401
    assert client.get(ROTA_ME, headers=_auth(_forjado("student"))).status_code == 401


# =====================================================================================
# Grupo P - troca de senha logado
# =====================================================================================

def _trocar(client, token, atual, nova, **extra):
    return client.post(ROTA_SENHA, headers=_auth(token), json={"current_password": atual, "new_password": nova, **extra})


def test_p1_senha_atual_errada_e_400_com_o_texto_exato_e_nada_muda(client, contas):
    hash_antes = _usuario(contas.maria.id)["password_hash"]
    tv = _token_version(contas.maria.id)
    r = _trocar(client, contas.maria.token, "senha-que-nao-e-a-atual", SENHA_NOVA)
    assert r.status_code == 400, f"HTTP {r.status_code} {r.text[:200]}"
    assert r.json() == {"detail": ERRO_SENHA_ATUAL}, r.text
    assert _usuario(contas.maria.id)["password_hash"] == hash_antes
    assert _token_version(contas.maria.id) == tv
    _token_vale(client, contas.maria.token, "o token continua valendo depois da troca recusada")
    assert _eventos("student.password_change") == []


@pytest.mark.parametrize("nova", ["curta7c", "", "ñ" * 30 + "A" * 13])  # 7 caracteres; vazia; 73 bytes
def test_p2_nova_senha_fora_da_politica_e_recusada_e_nada_muda(client, contas, nova):
    hash_antes = _usuario(contas.maria.id)["password_hash"]
    tv = _token_version(contas.maria.id)
    r = _trocar(client, contas.maria.token, SENHA, nova)
    assert r.status_code in (400, 422), f"HTTP {r.status_code} {r.text[:200]}"
    assert "token" not in r.json()
    assert _usuario(contas.maria.id)["password_hash"] == hash_antes
    assert _token_version(contas.maria.id) == tv
    assert _eventos("student.password_change") == []


def test_p3_nova_senha_com_8_caracteres_e_aceita(client, contas):
    r = _trocar(client, contas.maria.token, SENHA, "abcd1234")
    assert r.status_code == 200, r.text
    assert verify_password("abcd1234", _usuario(contas.maria.id)["password_hash"])


def test_p4_sucesso_devolve_token_novo_que_funciona_e_o_antigo_cai(client, contas):
    antes = _token_version(contas.maria.id)
    r = _trocar(client, contas.maria.token, SENHA, SENHA_NOVA)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    novo = corpo.get("token")
    assert isinstance(novo, str) and novo, corpo
    assert SENHA not in r.text and SENHA_NOVA not in r.text

    claims = _claims(novo)
    assert claims["user_id"] == contas.maria.id and claims["email"] == contas.maria.email
    assert claims["role"] == "student"
    assert claims.get("tv") == antes + 1 == _token_version(contas.maria.id)
    assert client.get(ROTA_ME, headers=_auth(novo)).json()["id"] == contas.maria.id
    _sessao_expirada(client.get(ROTA_ME, headers=_auth(contas.maria.token)), "token antigo depois da troca")

    hash_novo = _usuario(contas.maria.id)["password_hash"]
    assert verify_password(SENHA_NOVA, hash_novo) and not verify_password(SENHA, hash_novo)
    assert _login(client, contas.maria.email, SENHA).status_code == 400
    _token_vale(client, _token_login(client, contas.maria.email, SENHA_NOVA), "login com a senha nova")


def test_p5_evento_de_troca_sem_a_senha(client, contas):
    assert _trocar(client, contas.maria.token, SENHA, SENHA_NOVA).status_code == 200
    eventos = _eventos("student.password_change")
    assert len(eventos) == 1, eventos
    assert eventos[0]["user_id"] == contas.maria.id, eventos[0]
    texto = json.dumps(_sql("SELECT * FROM audit_logs"), ensure_ascii=False, default=str)
    for segredo in (SENHA, SENHA_NOVA):
        assert segredo not in texto, "a trilha nao pode conter a senha"
    for linha in _sql("SELECT * FROM audit_logs"):
        assert "$2b$" not in str(linha.get("changes") or "") and "$2b$" not in str(linha.get("detail") or "")


def test_p6_user_id_do_corpo_e_ignorado_idor(client, contas):
    hash_joao = _usuario(contas.joao.id)["password_hash"]
    r = _trocar(client, contas.maria.token, SENHA, SENHA_NOVA, user_id=contas.joao.id, id=contas.joao.id,
                email=contas.joao.email)
    assert r.status_code == 200, r.text
    assert _usuario(contas.joao.id)["password_hash"] == hash_joao
    assert _usuario(contas.joao.id)["token_version"] == 0
    _token_vale(client, contas.joao.token, "o token do outro aluno continua valendo")
    assert verify_password(SENHA_NOVA, _usuario(contas.maria.id)["password_hash"])
    assert _claims(r.json()["token"])["user_id"] == contas.maria.id


def test_p7_rbac_da_troca_de_senha(client, contas):
    for conta in (contas.gestao, contas.fin, contas.sup):
        r = _trocar(client, conta.token, SENHA_STAFF, SENHA_NOVA)
        assert r.status_code == 403, f"{conta.role}: HTTP {r.status_code}"
        assert verify_password(SENHA_STAFF, _usuario(conta.id)["password_hash"])
    assert _trocar(client, create_admin_token(Role.ADMIN), "x", SENHA_NOVA).status_code == 403
    r = client.post(ROTA_SENHA, json={"current_password": SENHA, "new_password": SENHA_NOVA})
    assert r.status_code == 401
    assert _trocar(client, _forjado("student"), SENHA, SENHA_NOVA).status_code == 401
    assert verify_password(SENHA, _usuario(contas.maria.id)["password_hash"])


# =====================================================================================
# Grupo G - migracao
# =====================================================================================

def _criar_banco_antigo(db_path):
    """Banco anterior a D80: users SEM is_active e SEM token_version, com um aluno e um funcionario."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            password_hash TEXT, role TEXT DEFAULT 'student', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, 'student')",
                 ("antigo.s4@teste.com", "Aluno Antigo", get_password_hash(SENHA)))
    conn.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, 'admin')",
                 ("gestor.antigo.s4@teste.com", "Gestor Antigo", get_password_hash(SENHA_STAFF)))
    conn.commit()
    conn.close()


def test_g1_banco_novo_tem_as_colunas_com_os_padroes(banco):
    colunas = _colunas()
    assert "is_active" in colunas and "token_version" in colunas, f"colunas de users: {sorted(colunas)}"
    assert str(colunas["is_active"]["dflt_value"]).strip("'\"") == "1"
    assert str(colunas["token_version"]["dflt_value"]).strip("'\"") == "0"
    user_id = Database.add_user("novo.s4@teste.com", "Aluno Novo", None, role="student")
    assert _usuario(user_id)["is_active"] == 1 and _usuario(user_id)["token_version"] == 0


def test_g2_migracao_de_banco_antigo_preserva_os_dados_e_e_idempotente(db_path):
    _criar_banco_antigo(db_path)
    antes = _sql("SELECT * FROM users ORDER BY id")

    Database.init_db()
    primeira = _sql("SELECT * FROM users ORDER BY id")
    for linha in primeira:
        assert linha.get("is_active") == 1 and linha.get("token_version") == 0, linha
    assert [{k: v for k, v in l.items() if k not in ("is_active", "token_version")} for l in primeira] == antes

    Database.init_db()
    Database.init_db()
    assert _sql("SELECT * FROM users ORDER BY id") == primeira
    nomes = [c["name"] for c in _sql("PRAGMA table_info(users)")]
    assert nomes.count("is_active") == 1 and nomes.count("token_version") == 1


def test_g3_token_sem_tv_de_conta_migrada_continua_valendo(db_path, cursos, catalogo_bot, llm, gateway):
    from app import app as fastapi_app

    _criar_banco_antigo(db_path)
    Database.init_db()
    aluno = _sql("SELECT id, email FROM users WHERE role = 'student'")[0]
    gestor = _sql("SELECT id, email FROM users WHERE role = 'admin'")[0]
    with TestClient(fastapi_app) as c:
        token = create_access_token({"user_id": aluno["id"], "email": aluno["email"], "role": "student"})
        assert c.get("/api/student/enrollments", headers=_auth(token)).status_code == 200
        assert c.get(ROTA_ME, headers=_auth(token)).json()["email"] == aluno["email"]
        token_gestor = create_access_token({"user_id": gestor["id"], "email": gestor["email"], "role": "admin"})
        assert c.get(ROTA_LISTA, headers=_auth(token_gestor)).status_code == 200
