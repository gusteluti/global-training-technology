"""E2 - Autenticação e criação de conta do aluno (itens 1.1 e RF21).

Testes de comportamento: usam as rotas HTTP, o banco SQLite temporário (tmp_path)
e consultas diretas à tabela. Nenhum teste depende de função interna nova, exceto
o ponto de entrega do link de definição de senha (send_password_setup_link), que
é substituído por um mock para capturar o token em claro (ver _token_do_envio).

Decisões de referência (registro do orquestrador, D12-D18):
  D12 token de definição: gerado pelo webhook aprovado para conta sem senha; guardado
      só como SHA-256; expira em 48 h; uso único.
  D13 entrega do link via send_password_setup_link (ponto único).
  D14 senha mínima de 8 caracteres.
  D15 cadastro direto: papel sempre 'student'; e-mail existente -> 400 genérico e sem troca de senha.
  D16 definição de senha só para conta SEM senha.
  D17 nenhum endpoint aceita user_id do cliente.
  D18 senha em bcrypt.
"""

import hashlib
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from core.security import get_password_hash
from db import Database

import admin.routes as admin_routes


SENHA_NOVA = "senha-forte-2026"
SENHA_OUTRA = "outra-senha-forte-1"


# --- Fixtures ----------------------------------------------------------------------

@pytest.fixture
def curso_teste(tmp_path, monkeypatch):
    """Um curso com preço, em diretório temporário (checkout lê preço de courses/)."""
    import json

    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / "curso_teste.json").write_text(json.dumps({
        "id": "curso_teste",
        "name": "Curso Teste",
        "description": "Curso para teste de conta do aluno",
        "price": 100.0,
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return "curso_teste"


@pytest.fixture
def client(banco, curso_teste):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco ----------------------------------------------------------------

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


def _usuario(email):
    linhas = _sql("SELECT * FROM users WHERE email = ?", (email,))
    return linhas[0] if linhas else None


def _tokens_do_usuario(user_id):
    return _sql("SELECT * FROM password_setup_tokens WHERE user_id = ?", (user_id,))


# --- Helpers de HTTP -----------------------------------------------------------------

def _registrar(client, email, password, name="Aluno Teste", **extra):
    corpo = {"name": name, "email": email, "password": password, **extra}
    return client.post("/api/auth/register", json=corpo)


def _login(client, email, senha):
    return client.post("/api/token", data={"username": email, "password": senha})


def _checkout(client, email, name="Aluno Teste"):
    resposta = MagicMock(status_code=201)
    resposta.json.return_value = {"id": "pref-1", "init_point": "https://mp.test/checkout"}
    with patch("payments.routes.requests.post", return_value=resposta):
        return client.post("/api/payments/create-checkout", json={
            "course_id": "curso_teste",
            "payer": {"name": name, "email": email},
        })


def _webhook_aprovado(client, ref, pagamento_id="555"):
    resposta = MagicMock(status_code=200)
    resposta.json.return_value = {"id": pagamento_id, "status": "approved", "external_reference": ref}
    with patch("payments.routes.requests.get", return_value=resposta):
        return client.post("/api/payments/webhook", json={"data": {"id": pagamento_id}})


def _compra_aprovada(client, email, name="Aluno Compra"):
    """Checkout + webhook aprovado. Devolve o mock de send_password_setup_link (captura do link).

    Se o webhook não chamar send_password_setup_link, o mock fica sem chamadas e
    _token_do_envio falha com mensagem explicando o motivo.
    """
    ref = _checkout(client, email, name).json()["external_reference"]
    with patch("payments.routes.send_password_setup_link", create=True) as envio:
        r = _webhook_aprovado(client, ref)
        assert r.status_code == 200, r.text
    return envio


def _token_do_envio(envio):
    """Extrai o token em claro do envio capturado pelo mock.

    Aceita o link em URL (contendo 'token=...') ou o token passado diretamente como argumento.
    """
    assert envio.call_count >= 1, (
        "o webhook precisa entregar o link de definição de senha via send_password_setup_link "
        "(conta sem senha após pagamento aprovado)"
    )
    chamada = envio.call_args
    textos = [v for v in list(chamada.args) + list(chamada.kwargs.values()) if isinstance(v, str)]
    for texto in textos:
        m = re.search(r"token=([A-Za-z0-9_\-]+)", texto)
        if m:
            return m.group(1)
    candidatos = [t for t in textos if "@" not in t and " " not in t and len(t) >= 32]
    assert candidatos, "o token de definição não foi entregue em claro ao envio"
    return candidatos[0]


def _definir_senha(client, token, senha, **extra):
    return client.post("/api/auth/password-setup", json={"token": token, "password": senha, **extra})


def _token_de_definicao_para(client, email):
    """Cria conta sem senha por compra aprovada e devolve (token_em_claro, user_id)."""
    envio = _compra_aprovada(client, email)
    token = _token_do_envio(envio)
    return token, _usuario(email)["id"]


def _verifica_bcrypt(senha, hash_armazenado):
    return CryptContext(schemes=["bcrypt"]).verify(senha, hash_armazenado)


def _expira_em_datetime(valor):
    """expires_at pode ser gravado como texto ISO ou como timestamp Unix. Devolve datetime naive em UTC."""
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor, tz=timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(str(valor)).replace(tzinfo=None)


def _forcar_expiracao_passada(user_id):
    """Ajusta expires_at do token do usuário para o passado, no mesmo formato já gravado."""
    linha = _tokens_do_usuario(user_id)[0]
    if isinstance(linha["expires_at"], (int, float)):
        passado = int(time.time()) - 3600
    else:
        passado = "2000-01-01 00:00:00"
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?", (passado, user_id))


# --- Requisito T1: cadastro direto ---------------------------------------------------

def test_1_cadastro_direto_cria_aluno_e_login_devolve_access_token(client):
    r = _registrar(client, "cadastro.direto@teste.com", SENHA_NOVA, name="Cadastro Direto")
    assert r.status_code in (200, 201), r.text

    usuario = _usuario("cadastro.direto@teste.com")
    assert usuario is not None, "o cadastro precisa criar a conta em users"
    assert usuario["role"] == "student"

    login = _login(client, "cadastro.direto@teste.com", SENHA_NOVA)
    assert login.status_code == 200, login.text
    assert login.json().get("access_token")


# --- Requisito T2: papel enviado pelo cliente é ignorado (D15) ----------------------

def test_2_cadastro_com_role_admin_cria_conta_student(client):
    r = _registrar(client, "tentativa.admin@teste.com", SENHA_NOVA, role="admin")
    assert r.status_code in (200, 201), r.text

    usuario = _usuario("tentativa.admin@teste.com")
    assert usuario is not None
    assert usuario["role"] == "student", "o campo role enviado pelo cliente deve ser ignorado"


# --- Requisito T3: e-mail já existente (D15) ----------------------------------------

def test_3_cadastro_com_email_de_gestor_existente_falha_e_nao_troca_senha(client):
    senha_antiga = "senha-do-gestor-1"
    Database.add_user("gestor@teste.com", "Gestor", get_password_hash(senha_antiga), role="admin")

    r = _registrar(client, "gestor@teste.com", SENHA_NOVA, name="Invasor")
    assert r.status_code == 400, r.text

    assert _login(client, "gestor@teste.com", senha_antiga).status_code == 200, (
        "a senha da conta existente não pode mudar com um cadastro de mesmo e-mail"
    )
    assert _login(client, "gestor@teste.com", SENHA_NOVA).status_code == 400
    assert _usuario("gestor@teste.com")["role"] == "admin", "o papel da conta existente não pode mudar"


# --- Requisito T4: senha fraca (D14) ------------------------------------------------

def test_4_cadastro_com_senha_de_menos_de_8_caracteres_falha(client):
    r = _registrar(client, "senha.fraca@teste.com", "1234567")
    assert r.status_code == 400, r.text
    assert _usuario("senha.fraca@teste.com") is None, "conta não pode ser criada com senha fraca"


# --- Requisito T5: token de definição após compra (D12, D13) ------------------------

def test_5_compra_aprovada_gera_token_e_banco_guarda_so_o_hash(client):
    envio = _compra_aprovada(client, "comprador.sem.senha@teste.com")
    token = _token_do_envio(envio)

    usuario = _usuario("comprador.sem.senha@teste.com")
    assert usuario is not None and usuario["password_hash"] is None

    linhas = _tokens_do_usuario(usuario["id"])
    assert len(linhas) == 1, "uma compra aprovada de conta sem senha gera um token de definição"

    for linha in _sql("SELECT * FROM password_setup_tokens"):
        for valor in linha.values():
            assert token not in str(valor), "o token em texto puro não pode ser gravado no banco"

    hash_esperado = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert hash_esperado in [str(v) for v in linhas[0].values()], (
        "o banco deve guardar o SHA-256 do token"
    )


# --- Requisito T6: definição de senha válida (D12, D16) -----------------------------

def test_6_definicao_de_senha_valida_permite_login_com_a_nova_senha(client):
    token, _ = _token_de_definicao_para(client, "defina.senha@teste.com")

    r = _definir_senha(client, token, SENHA_NOVA)
    assert r.status_code == 200, r.text

    login = _login(client, "defina.senha@teste.com", SENHA_NOVA)
    assert login.status_code == 200, login.text
    assert login.json().get("access_token")


# --- Requisito T7: uso único (D12) --------------------------------------------------

def test_7_token_de_definicao_so_vale_uma_vez(client):
    token, _ = _token_de_definicao_para(client, "uso.unico@teste.com")

    assert _definir_senha(client, token, SENHA_NOVA).status_code == 200

    r = _definir_senha(client, token, SENHA_OUTRA)
    assert r.status_code == 400, r.text
    assert _login(client, "uso.unico@teste.com", SENHA_NOVA).status_code == 200, (
        "a segunda tentativa com o mesmo token não pode trocar a senha"
    )


# --- Requisito T8: expiração (D12) --------------------------------------------------

def test_8a_token_expirado_e_recusado(client):
    token, user_id = _token_de_definicao_para(client, "expirado@teste.com")
    _forcar_expiracao_passada(user_id)

    r = _definir_senha(client, token, SENHA_NOVA)
    assert r.status_code == 400, r.text
    assert _usuario("expirado@teste.com")["password_hash"] is None


def test_8b_token_recem_criado_expira_em_cerca_de_48_horas(client):
    _, user_id = _token_de_definicao_para(client, "validade.48h@teste.com")
    expira = _expira_em_datetime(_tokens_do_usuario(user_id)[0]["expires_at"])

    alvo = timedelta(hours=48)
    tolerancia = timedelta(minutes=5)
    diferenca_utc = abs((expira - datetime.utcnow()) - alvo)
    diferenca_local = abs((expira - datetime.now()) - alvo)
    assert min(diferenca_utc, diferenca_local) <= tolerancia, (
        f"expira_em={expira}, esperado ~48 h a partir de agora"
    )


# --- Requisito T9: token inválido ---------------------------------------------------

def test_9_token_aleatorio_e_recusado_com_400(client):
    r = _definir_senha(client, "token-aleatorio-" + secrets.token_urlsafe(32), SENHA_NOVA)
    assert r.status_code == 400, r.text


# --- Requisito T10: conta que já tem senha não aceita definição (D16) ---------------

def test_10_conta_com_senha_nao_aceita_definicao_de_senha(client):
    token, user_id = _token_de_definicao_para(client, "ja.tem.senha@teste.com")
    senha_atual = get_password_hash("senha-ja-existente-1")
    _executar("UPDATE users SET password_hash = ? WHERE id = ?", (senha_atual, user_id))

    r = _definir_senha(client, token, SENHA_NOVA)
    assert r.status_code == 400, r.text
    assert _usuario("ja.tem.senha@teste.com")["password_hash"] == senha_atual, (
        "a senha de conta que já existe não pode ser substituída"
    )


# --- Requisito T11: sem user_id do cliente (D17) ------------------------------------

def test_11_user_id_enviado_pelo_cliente_nao_altera_outra_conta(client):
    token, dona_id = _token_de_definicao_para(client, "dona.do.token@teste.com")
    _compra_aprovada(client, "outra.conta@teste.com")
    outra = _usuario("outra.conta@teste.com")
    assert outra["id"] != dona_id

    r = _definir_senha(client, token, SENHA_NOVA, user_id=outra["id"])
    assert r.status_code == 200, r.text

    assert _usuario("outra.conta@teste.com")["password_hash"] is None, (
        "user_id do cliente não pode apontar para outra conta"
    )
    assert _login(client, "dona.do.token@teste.com", SENHA_NOVA).status_code == 200


# --- Requisito T12: senha em bcrypt (D18) -------------------------------------------

def test_12a_senha_de_cadastro_direto_e_bcrypt(client):
    r = _registrar(client, "bcrypt.cadastro@teste.com", SENHA_NOVA)
    assert r.status_code in (200, 201), r.text
    usuario = _usuario("bcrypt.cadastro@teste.com")
    assert usuario is not None, "o cadastro precisa criar a conta em users"
    hash_armazenado = usuario["password_hash"]

    assert hash_armazenado and hash_armazenado != SENHA_NOVA
    assert hash_armazenado.startswith("$2b$"), "a senha deve ser guardada com bcrypt"
    assert _verifica_bcrypt(SENHA_NOVA, hash_armazenado)


def test_12b_senha_definida_por_link_e_bcrypt(client):
    token, _ = _token_de_definicao_para(client, "bcrypt.definicao@teste.com")
    assert _definir_senha(client, token, SENHA_NOVA).status_code == 200

    hash_armazenado = _usuario("bcrypt.definicao@teste.com")["password_hash"]
    assert hash_armazenado and hash_armazenado != SENHA_NOVA
    assert hash_armazenado.startswith("$2b$")
    assert _verifica_bcrypt(SENHA_NOVA, hash_armazenado)


# --- Requisito T13: respostas genéricas (D15, D16) ----------------------------------

def test_13a_cadastro_com_email_existente_nao_revela_conta_nem_ecoa_dados(client):
    Database.add_user("existe.13a@teste.com", "Existente", get_password_hash("senha-existente-1"))

    r = _registrar(client, "existe.13a@teste.com", SENHA_NOVA)
    assert r.status_code == 400, r.text
    assert set(r.json().keys()) == {"detail"}, "a resposta de erro deve ter só a mensagem genérica"
    assert "existe.13a@teste.com" not in r.text


def test_13b_cadastro_com_senha_fraca_tem_mesma_forma_de_erro(client):
    Database.add_user("forma.existente@teste.com", "Existente", get_password_hash("senha-existente-2"))
    r_existente = _registrar(client, "forma.existente@teste.com", SENHA_NOVA)
    r_fraca = _registrar(client, "forma.fraca@teste.com", "123")

    assert r_existente.status_code == r_fraca.status_code == 400
    assert set(r_existente.json().keys()) == set(r_fraca.json().keys()) == {"detail"}
    assert "forma.fraca@teste.com" not in r_fraca.text


def test_13c_definicao_com_token_invalido_nao_ecoa_o_token(client):
    token_falso = "token-falso-" + secrets.token_urlsafe(24)

    r = _definir_senha(client, token_falso, SENHA_NOVA)
    assert r.status_code == 400, r.text
    assert token_falso not in r.text


# --- Requisito T14: aluno criado por cadastro continua fora da área de funcionário --

def test_14_aluno_criado_por_cadastro_nao_acessa_dashboard_de_alunos(client):
    _registrar(client, "aluno.sem.acesso@teste.com", SENHA_NOVA)
    login = _login(client, "aluno.sem.acesso@teste.com", SENHA_NOVA)
    assert login.status_code == 200, login.text
    cabecalho = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/dashboard/alunos", headers=cabecalho).status_code == 403
