"""E2 - Comunicação fora do HTTP no cadastro (D22).

A resposta HTTP do cadastro é uniforme para e-mail novo e existente (D21). Por isso a
informação ao usuário legítimo vai por e-mail. Aqui o e-mail é simulado pelo outbox de
desenvolvimento: PASSWORD_LINK_OUTBOX aponta para um arquivo em tmp_path, com uma linha JSON
por mensagem (ver core/notifications.py). Nenhum teste toca backend/db.sqlite.

  B1 cadastro de e-mail NOVO: mensagem de CONFIRMAÇÃO DE CONTA CRIADA, sem link de definição de
     senha e sem token (D23). O link de definição fica exclusivo do fluxo de compra.
     A diferença de conteúdo entre os e-mails é permitida; a resposta HTTP não pode diferir
     entre e-mail novo e existente (coberta por test_enum_1/2 e test_3/13a).
  B2 cadastro de e-mail EXISTENTE: mensagem avisando que houve tentativa de cadastro e que a
     conta já existe, com caminho para ENTRAR (link para a tela de login). D26: o aviso aponta só
     para o login; recuperação de senha é item de backlog. A mensagem NÃO contém
     link de definição de senha, NÃO contém senha, e NÃO altera a conta.
  B3 as duas mensagens são distintas entre si. Cada teste lê a mensagem do próprio e-mail.
  B4 resposta HTTP idêntica nos dois casos: já coberta por D21 em test_e2_conta_aluno.py
     (test_3 e test_13a) e em test_e2_enumeracao.py. Não é duplicada aqui.

Leitura do outbox: cada mensagem é identificada pelo campo "email" do registro JSON. O conteúdo
é analisado a partir do registro inteiro serializado, sem depender do nome dos campos de texto.
"""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from core.security import get_password_hash
from db import Database


SENHA_NOVA = "senha-forte-2026"
SENHA_ANTIGA = "senha-existente-b2"


# --- Fixtures ----------------------------------------------------------------------

@pytest.fixture
def outbox(tmp_path, monkeypatch):
    caminho = tmp_path / "outbox.jsonl"
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(caminho))
    return caminho


@pytest.fixture
def client(banco, outbox):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers -----------------------------------------------------------------------

def _registrar(client, email, password=SENHA_NOVA):
    return client.post("/api/auth/register", json={
        "name": "Pessoa Teste", "email": email, "password": password,
    })


def _usuario(email):
    import sqlite3

    conn = sqlite3.connect(Database.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        linha = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(linha) if linha else None
    finally:
        conn.close()


def _mensagens(caminho, email):
    if not caminho.exists():
        return []
    registros = [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]
    return [r for r in registros if r.get("email") == email]


def _mensagem_unica(caminho, email):
    mensagens = _mensagens(caminho, email)
    assert len(mensagens) == 1, (
        f"esperada 1 mensagem no outbox para {email}, encontradas {len(mensagens)}"
    )
    return mensagens[0]


def _texto(registro):
    return json.dumps(registro, ensure_ascii=False)


def _links(texto):
    return re.findall(r"https?://[^\s\"']+", texto)


def _token_em_query(texto):
    """Token do link de definição (query string ?token=...), ou None."""
    for link in _links(texto):
        valores = parse_qs(urlparse(link).query).get("token")
        if valores and valores[0]:
            return valores[0]
    return None


# --- B1: e-mail novo recebe confirmação de conta criada, sem link de definição (D22/D23) --

def test_b1_cadastro_de_email_novo_gera_confirmacao_sem_link_de_definicao_nem_token(client, outbox):
    email = "b1.novo@teste.com"

    r = _registrar(client, email)
    assert r.status_code == 200, r.text

    texto = _texto(_mensagem_unica(outbox, email))
    assert email in texto, "a mensagem deve identificar o destinatário (campo email do registro)"
    assert re.search(r"criad[ao]|confirma", texto, re.IGNORECASE), (
        "a mensagem deve confirmar que a conta foi criada"
    )
    assert _links(texto) and re.search(r"entrar|login", texto, re.IGNORECASE), (
        "a mensagem deve indicar o caminho para entrar (link para a tela de login)"
    )
    assert _token_em_query(texto) is None and "token=" not in texto, (
        "a confirmação de conta criada não pode conter token nem link de definição de senha (D23)"
    )
    assert "definir-senha" not in texto, "a confirmação não pode apontar para a tela de definição de senha (D23)"
    assert SENHA_NOVA not in texto, "a mensagem não pode conter a senha"


# --- B2: e-mail existente recebe aviso, sem link, sem senha, sem alterar a conta (D22) --

def test_b2_cadastro_de_email_existente_gera_aviso_sem_link_nem_senha_e_sem_alterar_conta(client, outbox):
    """D26: aviso aponta só para o login; recuperação de senha é item de backlog.

    Sem token, sem link de definição de senha, sem senha, conta inalterada.
    """
    email = "b2.existente@teste.com"
    Database.add_user(email, "Existente B2", get_password_hash(SENHA_ANTIGA), role="student")
    antes = _usuario(email)

    r = _registrar(client, email)
    assert r.status_code == 200, r.text

    texto = _texto(_mensagem_unica(outbox, email))

    assert _token_em_query(texto) is None and "token=" not in texto, (
        "a mensagem de e-mail existente não pode conter link de definição de senha"
    )
    assert "definir-senha" not in texto, "a mensagem de e-mail existente não pode apontar para definição de senha"
    assert SENHA_NOVA not in texto and SENHA_ANTIGA not in texto, "a mensagem não pode conter senha"

    assert re.search(r"tentativa|tentou", texto, re.IGNORECASE), "a mensagem deve avisar que houve tentativa de cadastro"
    assert re.search(r"j[aá]\s+(existe|est[aá]\s+cadastrad|possui)|existe\s+(uma\s+)?conta", texto, re.IGNORECASE), (
        "a mensagem deve avisar que a conta já existe"
    )
    assert any("login" in link.lower() for link in _links(texto)), "a mensagem deve trazer link para a tela de login"
    assert re.search(r"entrar|login", texto, re.IGNORECASE), "a mensagem deve indicar o caminho para entrar"
    assert not re.search(r"recuper|esqueci", texto, re.IGNORECASE), (
        "a mensagem não pode prometer recuperação de senha (D26: recuperação é backlog)"
    )

    depois = _usuario(email)
    assert depois["password_hash"] == antes["password_hash"], "o cadastro não pode alterar a senha da conta existente"
    assert depois["role"] == antes["role"], "o cadastro não pode alterar o papel da conta existente"
    assert depois["name"] == antes["name"], "o cadastro não pode alterar o nome da conta existente"


# --- B3: as duas mensagens são distintas (D22) ----------------------------------------

def test_b3_mensagens_dos_dois_caminhos_sao_distintas(client, outbox):
    novo = "b3.novo@teste.com"
    existente = "b3.existente@teste.com"
    Database.add_user(existente, "Existente B3", get_password_hash(SENHA_ANTIGA), role="student")

    _registrar(client, novo)
    _registrar(client, existente)

    texto_novo = _texto(_mensagem_unica(outbox, novo))
    texto_existente = _texto(_mensagem_unica(outbox, existente))

    assert texto_novo != texto_existente, "as mensagens dos dois caminhos devem ser distintas"

    for texto, rotulo in ((texto_novo, "novo"), (texto_existente, "existente")):
        assert _token_em_query(texto) is None and "token=" not in texto, (
            f"a mensagem de e-mail {rotulo} não pode conter token (D23)"
        )
