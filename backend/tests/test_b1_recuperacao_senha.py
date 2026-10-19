"""B1 - Recuperação de senha do aluno (D60). Testes escritos ANTES da implementação (vermelho).

Contrato (D60):
  POST /api/auth/password-reset/request  {"email": str}
    - SEMPRE 200 com o corpo exato RESPOSTA_PEDIDO, para qualquer texto de e-mail (existente, inexistente,
      de funcionário, malformado) e com campos extras ignorados; 422 só se o campo `email` faltar.
    - Só conta de aluno (role 'student') recebe link. Funcionário e e-mail inexistente: nada (sem token, sem
      outbox, sem evento).
    - Aluno COM senha: token purpose='reset' (1 h) + send_password_reset_link (outbox: email, assunto
      "Redefinição de senha", mensagem, link `{FRONTEND_BASE_URL}/redefinir-senha?token=...`).
      Aluno SEM senha: token purpose='setup' (48 h) + send_password_setup_link (link `/definir-senha?token=`).
    - Limite: no máximo 3 tokens por conta em 1 hora (janela móvel, qualquer finalidade); acima disso nada é
      emitido nem enviado e a resposta continua idêntica. Token novo invalida (used_at) os anteriores abertos da
      mesma conta e finalidade.
  POST /api/auth/password-reset  {"token": str, "password": str}
    - 200 RESPOSTA_REDEFINIR; qualquer falha 400 {"detail": ERRO_DEFINICAO_SENHA}. O alvo é sempre o dono do token.
      Uso único e atômico; senha nova substitui a antiga; outros tokens abertos da conta são invalidados; o dono
      recebe send_password_changed_notice (outbox: assunto "Sua senha foi alterada", mensagem com a URL de login,
      sem senha e sem token). Token 'setup' não vale aqui e token 'reset' não vale em /password-setup.
  password_setup_tokens ganha `purpose TEXT NOT NULL DEFAULT 'setup'` por _ensure_column (tokens antigos: 'setup').

Checklist: IDOR (o alvo vem só do token; nenhum id de usuário do cliente é usado) coberto nos grupos A3, F9 e F14.
Recurso pago só com matrícula ativa: NÃO SE APLICA (não há conteúdo pago nesta entrega). 401/403: NÃO SE APLICAM
(os dois endpoints são públicos por desenho; o grupo A4 prova que um bearer forjado não muda nada).

Convenções: banco temporário (conftest), rotas HTTP reais, saída de desenvolvimento em PASSWORD_LINK_OUTBOX (um JSON
por linha) em tmp_path. Nenhum teste toca backend/db.sqlite nem o Groq. O token em claro só é lido do outbox.
"""

import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from apoio_mercado_pago import corpo_pagamento_mp, id_de_pagamento, post_webhook
from core.password_setup import emitir_token_definicao, hash_token
from core.security import get_password_hash, verify_password
from db import Database


# Mesmo valor do conftest: mudar FRONTEND_BASE_URL antes do primeiro import de `app` alteraria a lista de
# origens do CORS (calculada no import) e quebraria test_e9 na suíte completa.
BASE_FRONT = "http://localhost:8000"
URL_PEDIDO = "/api/auth/password-reset/request"
URL_REDEFINIR = "/api/auth/password-reset"
URL_DEFINIR = "/api/auth/password-setup"

RESPOSTA_PEDIDO = {
    "status": "success",
    "message": "Se o e-mail estiver cadastrado, enviaremos um link para redefinir a senha.",
}
RESPOSTA_REDEFINIR = {"status": "success", "message": "Senha redefinida. Faça login para entrar."}
ERRO_DEFINICAO_SENHA = "Não foi possível definir a senha. Verifique o link e a senha informada."

ASSUNTO_RESET = "Redefinição de senha"
ASSUNTO_AVISO = "Sua senha foi alterada"

SENHA_ANTIGA = "senha-antiga-b1-ok"
SENHA_NOVA = "senha-nova-b1-ok"
SENHA_OUTRA = "outra-senha-b1-ok"
SENHA_72_ACENTOS = "ñ" * 30 + "A" * 12            # 72 bytes, 42 caracteres
EMAIL_INEXISTENTE = "ninguem.b1@teste.com"
N_CONCORRENTES = 8


# --- Fixtures ----------------------------------------------------------------------

@pytest.fixture
def outbox(tmp_path, monkeypatch):
    caminho = tmp_path / "outbox.jsonl"
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(caminho))
    monkeypatch.setenv("FRONTEND_BASE_URL", BASE_FRONT)
    return caminho


@pytest.fixture
def curso_teste(tmp_path, monkeypatch):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / "curso_teste.json").write_text(json.dumps({
        "id": "curso_teste", "name": "Curso Teste", "description": "Curso para o teste B1", "price": 100.0,
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return "curso_teste"


@pytest.fixture
def client(banco, outbox, curso_teste):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco --------------------------------------------------------------

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


def _tokens(user_id=None):
    if user_id is None:
        return _sql("SELECT * FROM password_setup_tokens ORDER BY id")
    return _sql("SELECT * FROM password_setup_tokens WHERE user_id = ? ORDER BY id", (user_id,))


def _exigir_coluna_purpose():
    colunas = {c["name"] for c in _sql("PRAGMA table_info(password_setup_tokens)")}
    assert "purpose" in colunas, "falta a coluna password_setup_tokens.purpose (D60)"


def _auditoria():
    return _sql("SELECT * FROM audit_logs ORDER BY id")


def _agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _expira_em_datetime(valor):
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor, tz=timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(str(valor)).replace(tzinfo=None)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _inserir_token(user_id, purpose, *, horas=1, usado=False, token=None):
    """Insere um token (só o hash) diretamente no banco, contornando as rotas. Devolve o token em claro."""
    _exigir_coluna_purpose()
    token = token or ("forjado-" + hash_token(f"{user_id}-{purpose}-{_agora().isoformat()}-{id(object())}")[:40])
    _executar(
        "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, used_at, purpose) VALUES (?, ?, ?, ?, ?)",
        (user_id, hash_token(token), _fmt(_agora() + timedelta(hours=horas)), _fmt(_agora()) if usado else None, purpose),
    )
    return token


def _recuar_valor(valor, minutos):
    if isinstance(valor, (int, float)):
        return valor - minutos * 60
    texto = str(valor)
    separador = "T" if "T" in texto else " "
    return (datetime.fromisoformat(texto) - timedelta(minutes=minutos)).isoformat(sep=separador, timespec="seconds")


def _recuar_tokens(user_id, minutos, ids=None):
    """Move created_at dos tokens da conta `minutos` para o passado, no mesmo formato já gravado."""
    for linha in _tokens(user_id):
        if ids is not None and linha["id"] not in ids:
            continue
        _executar("UPDATE password_setup_tokens SET created_at = ? WHERE id = ?",
                  (_recuar_valor(linha["created_at"], minutos), linha["id"]))


def _nenhum_token_em_claro(*tokens):
    for linha in _tokens():
        for valor in linha.values():
            for token in tokens:
                assert token not in str(valor), "o token em claro não pode ser gravado no banco"
    bruto = Database.DB_PATH.read_bytes()
    for token in tokens:
        assert token.encode("utf-8") not in bruto, "o token em claro apareceu nos bytes do arquivo do banco"


# --- Helpers de contas -------------------------------------------------------------

def _aluno(email, senha=SENHA_ANTIGA):
    user_id = Database.add_user(email, "Aluno B1", get_password_hash(senha), role="student")
    assert user_id is not None, f"seed: {email} já existe"
    return user_id


def _aluno_sem_senha(email):
    user_id = Database.get_or_create_user(email, "Aluno Sem Senha B1")
    assert _usuario(email)["password_hash"] is None
    return user_id


def _funcionario(email, perfil, senha=SENHA_ANTIGA):
    user_id = Database.add_user(email, f"Func {perfil}", get_password_hash(senha) if senha else None, role=perfil)
    assert user_id is not None, f"seed: {email} já existe"
    return user_id


# --- Helpers de outbox -------------------------------------------------------------

def _outbox_registros(caminho, email=None):
    if not caminho.exists():
        return []
    registros = [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in registros if email is None or r.get("email") == email]


def _token_do_link(link):
    valores = parse_qs(urlparse(link).query).get("token")
    assert valores and valores[0], f"link sem token: {link!r}"
    return valores[0]


def _ultimo_token(caminho, email, caminho_do_link):
    """Token em claro do último registro do outbox para o e-mail cujo link contém `caminho_do_link`."""
    registros = [r for r in _outbox_registros(caminho, email) if caminho_do_link in str(r.get("link", ""))]
    assert registros, f"nenhum registro no outbox para {email} com link {caminho_do_link!r}"
    return _token_do_link(registros[-1]["link"])


def _avisos(caminho, email):
    return [r for r in _outbox_registros(caminho, email) if r.get("assunto") == ASSUNTO_AVISO]


# --- Helpers de HTTP ---------------------------------------------------------------

def _pedir(client, email, **extra):
    return client.post(URL_PEDIDO, json={"email": email, **extra})


def _redefinir(client, token, senha, **extra):
    return client.post(URL_REDEFINIR, json={"token": token, "password": senha, **extra})


def _definir(client, token, senha):
    return client.post(URL_DEFINIR, json={"token": token, "password": senha})


def _login(client, email, senha):
    return client.post("/api/token", data={"username": email, "password": senha})


def _novo_reset(client, outbox, email):
    """Pede a redefinição e devolve o token em claro lido do outbox."""
    r = _pedir(client, email)
    assert r.status_code == 200, r.text
    return _ultimo_token(outbox, email, "/redefinir-senha")


def _erro_padrao(r):
    assert r.status_code == 400, f"HTTP {r.status_code}: {r.text[:200]}"
    assert r.json() == {"detail": ERRO_DEFINICAO_SENHA}, r.text


def _disparar_simultaneos(tarefa, quantidade):
    barreira = threading.Barrier(quantidade)
    resultados = [None] * quantidade
    erros = []

    def trabalhador(i):
        try:
            barreira.wait(timeout=30)
            resultados[i] = tarefa(i)
        except Exception as exc:  # noqa: BLE001
            erros.append((i, repr(exc)))

    threads = [threading.Thread(target=trabalhador, args=(i,)) for i in range(quantidade)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not erros, f"threads com erro: {erros}"
    assert all(r is not None for r in resultados), "alguma thread não terminou"
    return resultados


# =====================================================================================
# Grupo A - resposta uniforme do pedido (anti-enumeração, D15/D21)
# =====================================================================================

EMAILS_MALFORMADOS = [
    "nao-e-um-email", "", "   ", "@", "a@b", "A" * 5000 + "@x.com", "' OR '1'='1", "ñandú@exemplo.com.br",
    "<script>alert(1)</script>", "../../etc/passwd", "x@y.com, aluno.com.senha@teste.com",
]


@pytest.fixture
def contas(client):
    return {
        "aluno_com_senha": _aluno("aluno.com.senha@teste.com"),
        "aluno_sem_senha": _aluno_sem_senha("aluno.sem.senha@teste.com"),
        "admin": _funcionario("admin.b1@teste.com", "admin"),
        "financial": _funcionario("financeiro.b1@teste.com", "financial"),
        "support": _funcionario("suporte.b1@teste.com", "support"),
        "financial_sem_senha": _funcionario("fin.sem.senha.b1@teste.com", "financial", senha=None),
    }


@pytest.mark.parametrize("email", [
    "aluno.com.senha@teste.com", "aluno.sem.senha@teste.com", EMAIL_INEXISTENTE,
    "admin.b1@teste.com", "financeiro.b1@teste.com", "suporte.b1@teste.com", "fin.sem.senha.b1@teste.com",
] + EMAILS_MALFORMADOS, ids=lambda e: (e[:25] + "...") if len(e) > 25 else (e or "vazio"))
def test_a1_resposta_e_identica_em_corpo_e_status_para_qualquer_email(client, contas, email):
    base = _pedir(client, "referencia.inexistente.b1@teste.com")
    assert base.status_code == 200, base.text
    assert base.json() == RESPOSTA_PEDIDO

    r = _pedir(client, email)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    assert r.json() == RESPOSTA_PEDIDO
    assert r.content == base.content, "o corpo precisa ser idêntico byte a byte ao de e-mail inexistente"
    assert r.headers["content-type"] == base.headers["content-type"]


def test_a2_422_so_quando_o_campo_email_falta(client):
    for corpo in ({}, {"mail": "aluno@teste.com"}, {"password": "x", "token": "y"}):
        r = client.post(URL_PEDIDO, json=corpo)
        assert r.status_code == 422, f"corpo {corpo}: HTTP {r.status_code} {r.text[:200]}"
    assert client.post(URL_PEDIDO).status_code == 422
    assert _tokens() == []


def test_a3_campos_extras_sao_ignorados_e_nao_mudam_o_alvo(client, contas, outbox):
    """IDOR: user_id/role/token/password no corpo do pedido não direcionam nada. O alvo vem só do e-mail."""
    id_aluno = contas["aluno_com_senha"]
    extras = {"user_id": id_aluno, "role": "admin", "token": "x", "password": "senha-qualquer-ok", "purpose": "setup"}

    r = _pedir(client, EMAIL_INEXISTENTE, **extras)
    assert r.status_code == 200 and r.json() == RESPOSTA_PEDIDO
    assert _tokens() == [], "user_id no corpo não pode emitir token para outra conta"
    assert _outbox_registros(outbox) == []

    r = _pedir(client, "aluno.com.senha@teste.com", **extras)
    assert r.status_code == 200 and r.json() == RESPOSTA_PEDIDO
    linhas = _tokens(id_aluno)
    assert len(linhas) == 1 and linhas[0]["purpose"] == "reset", "campo extra `purpose` não pode escolher a finalidade"
    assert _usuario("aluno.com.senha@teste.com")["role"] == "student"


def test_a4_endpoint_e_publico_e_ignora_bearer_forjado(client, contas):
    base = _pedir(client, EMAIL_INEXISTENTE)
    r = client.post(URL_PEDIDO, json={"email": EMAIL_INEXISTENTE}, headers={"Authorization": "Bearer token.forjado.xyz"})
    assert r.status_code == 200 and r.content == base.content


# =====================================================================================
# Grupo B - nada é emitido nem enviado (funcionário, inexistente, malformado)
# =====================================================================================

@pytest.mark.parametrize("email", [
    "admin.b1@teste.com", "financeiro.b1@teste.com", "suporte.b1@teste.com", "fin.sem.senha.b1@teste.com",
], ids=["admin", "financeiro", "suporte", "financeiro_sem_senha"])
def test_b1_conta_de_funcionario_nao_recebe_token_nem_mensagem_nem_evento(client, contas, outbox, email):
    antes = _auditoria()
    usuario_antes = _usuario(email)
    for _ in range(5):                                   # repetir não pode vazar nem emitir
        assert _pedir(client, email).json() == RESPOSTA_PEDIDO
    assert _tokens() == [], "funcionário não pode ter linha em password_setup_tokens"
    assert _outbox_registros(outbox) == [], "funcionário não pode receber mensagem"
    assert not outbox.exists() or outbox.read_text(encoding="utf-8").strip() == ""
    assert _auditoria() == antes, "pedido de redefinição de funcionário não gera evento"
    assert _usuario(email) == usuario_antes, "a conta de funcionário não pode ser alterada"


def test_b2_email_inexistente_nao_emite_nem_envia_nem_cria_conta(client, contas, outbox):
    antes = _auditoria()
    usuarios_antes = _sql("SELECT id, email FROM users ORDER BY id")
    assert _pedir(client, EMAIL_INEXISTENTE).json() == RESPOSTA_PEDIDO
    assert _tokens() == []
    assert _outbox_registros(outbox) == []
    assert _auditoria() == antes
    assert _sql("SELECT id, email FROM users ORDER BY id") == usuarios_antes, "não pode criar conta"


@pytest.mark.parametrize("email", EMAILS_MALFORMADOS, ids=lambda e: (e[:25] + "...") if len(e) > 25 else (e or "vazio"))
def test_b3_email_malformado_nao_emite_nem_envia(client, contas, outbox, email):
    assert _pedir(client, email).status_code == 200
    assert _tokens() == [], f"e-mail {email[:30]!r} não pode gerar token"
    assert _outbox_registros(outbox) == [], f"e-mail {email[:30]!r} não pode gerar mensagem"


# =====================================================================================
# Grupo C - emissão para aluno (com senha: 'reset' 1 h; sem senha: 'setup' 48 h)
# =====================================================================================

def test_c1_aluno_com_senha_recebe_token_reset_de_1_hora_so_com_hash(client, outbox):
    user_id = _aluno("c1@teste.com")
    token = _novo_reset(client, outbox, "c1@teste.com")

    linhas = _tokens(user_id)
    assert len(linhas) == 1, "um pedido gera exatamente um token"
    linha = linhas[0]
    assert linha["purpose"] == "reset"
    assert linha["used_at"] is None
    assert linha["token_hash"] == hash_token(token), "o banco guarda o SHA-256 do token do link"
    assert re.fullmatch(r"[0-9a-f]{64}", linha["token_hash"])

    diferenca = abs((_expira_em_datetime(linha["expires_at"]) - _agora()) - timedelta(hours=1))
    assert diferenca <= timedelta(minutes=5), f"validade deve ser ~1 h em UTC (desvio {diferenca})"
    _nenhum_token_em_claro(token)


def test_c2_registro_do_outbox_do_aluno_com_senha(client, outbox):
    _aluno("c2@teste.com")
    token = _novo_reset(client, outbox, "c2@teste.com")

    registros = _outbox_registros(outbox, "c2@teste.com")
    assert len(registros) == 1, f"esperado UM registro no outbox, veio {len(registros)}"
    registro = registros[0]
    assert registro["email"] == "c2@teste.com"
    assert registro["assunto"] == ASSUNTO_RESET
    assert isinstance(registro.get("mensagem"), str) and registro["mensagem"].strip()
    assert registro["link"] == f"{BASE_FRONT}/redefinir-senha?token={token}"
    assert re.fullmatch(r"[A-Za-z0-9_\-]{32,}", token), "token URL-safe com entropia suficiente"
    assert SENHA_ANTIGA not in json.dumps(registro, ensure_ascii=False), "a mensagem não pode conter senha"


def test_c3_dois_alunos_recebem_tokens_distintos_cada_um_no_proprio_email(client, outbox):
    id_a, id_b = _aluno("c3.a@teste.com"), _aluno("c3.b@teste.com")
    ta = _novo_reset(client, outbox, "c3.a@teste.com")
    tb = _novo_reset(client, outbox, "c3.b@teste.com")
    assert ta != tb
    assert [l["token_hash"] for l in _tokens(id_a)] == [hash_token(ta)]
    assert [l["token_hash"] for l in _tokens(id_b)] == [hash_token(tb)]
    assert len(_outbox_registros(outbox, "c3.a@teste.com")) == 1 and len(_outbox_registros(outbox, "c3.b@teste.com")) == 1


def test_c4_aluno_sem_senha_recebe_token_setup_de_48_horas_pelo_envio_de_definicao(client, outbox):
    user_id = _aluno_sem_senha("c4@teste.com")
    assert _pedir(client, "c4@teste.com").json() == RESPOSTA_PEDIDO

    linhas = _tokens(user_id)
    assert len(linhas) == 1 and linhas[0]["purpose"] == "setup"
    diferenca = abs((_expira_em_datetime(linhas[0]["expires_at"]) - _agora()) - timedelta(hours=48))
    assert diferenca <= timedelta(minutes=5), f"validade deve ser ~48 h em UTC (desvio {diferenca})"

    registros = _outbox_registros(outbox, "c4@teste.com")
    assert len(registros) == 1, f"esperado UM registro, veio {len(registros)}"
    link = registros[0]["link"]
    assert link.startswith(f"{BASE_FRONT}/definir-senha?token="), link
    assert "redefinir-senha" not in link
    token = _token_do_link(link)
    assert linhas[0]["token_hash"] == hash_token(token)
    _nenhum_token_em_claro(token)

    # o link serve de verdade para definir a senha, e a conta passa a logar
    assert _definir(client, token, SENHA_NOVA).status_code == 200
    assert _login(client, "c4@teste.com", SENHA_NOVA).status_code == 200


def test_c5_aluno_sem_senha_pedir_de_novo_invalida_o_token_de_definicao_anterior(client, outbox):
    user_id = _aluno_sem_senha("c5@teste.com")
    _pedir(client, "c5@teste.com")
    primeiro = _ultimo_token(outbox, "c5@teste.com", "/definir-senha")
    _pedir(client, "c5@teste.com")
    segundo = _ultimo_token(outbox, "c5@teste.com", "/definir-senha")
    assert primeiro != segundo

    _erro_padrao(_definir(client, primeiro, SENHA_NOVA))
    assert _usuario("c5@teste.com")["password_hash"] is None
    assert _definir(client, segundo, SENHA_NOVA).status_code == 200
    assert len(_tokens(user_id)) == 2


def test_c6_pedido_do_aluno_nao_grava_auditoria_e_nao_altera_a_conta(client, outbox):
    _aluno("c6@teste.com")
    antes = _auditoria()
    conta = _usuario("c6@teste.com")
    for _ in range(3):
        assert _pedir(client, "c6@teste.com").status_code == 200
    assert len(_tokens(_usuario("c6@teste.com")["id"])) == 3, "o pedido precisa de fato emitir (sem isto o teste seria vazio)"
    assert _auditoria() == antes
    assert _usuario("c6@teste.com") == conta, "pedir o link não muda senha, papel nem nome"
    assert _login(client, "c6@teste.com", SENHA_ANTIGA).status_code == 200, "a senha antiga segue valendo até a redefinição"


# =====================================================================================
# Grupo D - limite de 3 tokens por conta por hora (janela móvel)
# =====================================================================================

def test_d1_quarto_pedido_nao_emite_nem_envia_e_responde_igual_outra_conta_nao_e_afetada(client, outbox):
    id_a, id_b = _aluno("d1.a@teste.com"), _aluno("d1.b@teste.com")
    respostas = [_pedir(client, "d1.a@teste.com") for _ in range(3)]
    assert len(_tokens(id_a)) == 3 and len(_outbox_registros(outbox, "d1.a@teste.com")) == 3

    quarto = _pedir(client, "d1.a@teste.com")
    assert quarto.status_code == 200 and quarto.content == respostas[0].content, "resposta idêntica no bloqueio"
    assert len(_tokens(id_a)) == 3, "o 4º pedido não pode emitir token"
    assert len(_outbox_registros(outbox, "d1.a@teste.com")) == 3, "o 4º pedido não pode enviar mensagem"
    assert len(_tokens(id_a)) == 3 and _pedir(client, "d1.a@teste.com").content == respostas[0].content
    assert len(_tokens(id_a)) == 3 and len(_outbox_registros(outbox, "d1.a@teste.com")) == 3

    # outra conta não é afetada
    assert _pedir(client, "d1.b@teste.com").status_code == 200
    assert len(_tokens(id_b)) == 1 and len(_outbox_registros(outbox, "d1.b@teste.com")) == 1


def test_d2_janela_de_uma_hora_tokens_de_59_min_ainda_contam_de_61_min_nao_contam(client, outbox):
    user_id = _aluno("d2@teste.com")
    for _ in range(3):
        _pedir(client, "d2@teste.com")
    assert len(_tokens(user_id)) == 3

    _recuar_tokens(user_id, 59)
    _pedir(client, "d2@teste.com")
    assert len(_tokens(user_id)) == 3, "tokens de 59 minutos ainda estão na janela de 1 hora"
    assert len(_outbox_registros(outbox, "d2@teste.com")) == 3

    _recuar_tokens(user_id, 3)                        # agora todos têm ~62 min: fora da janela
    r = _pedir(client, "d2@teste.com")
    assert r.status_code == 200 and r.json() == RESPOSTA_PEDIDO
    assert len(_tokens(user_id)) == 4, "com os tokens fora da janela o pedido volta a emitir"
    assert len(_outbox_registros(outbox, "d2@teste.com")) == 4


def test_d3_janela_e_movel_so_o_token_mais_antigo_sai_da_contagem(client, outbox):
    user_id = _aluno("d3@teste.com")
    for _ in range(3):
        _pedir(client, "d3@teste.com")
    ids = [l["id"] for l in _tokens(user_id)]
    _recuar_tokens(user_id, 61, ids=[ids[0]])         # só o mais antigo sai da janela

    _pedir(client, "d3@teste.com")
    assert len(_tokens(user_id)) == 4, "restavam 2 na janela: o pedido emite"
    _pedir(client, "d3@teste.com")
    assert len(_tokens(user_id)) == 4, "agora há 3 na janela: o pedido seguinte é bloqueado"
    assert len(_outbox_registros(outbox, "d3@teste.com")) == 4


def test_d4_o_limite_conta_qualquer_finalidade(client, outbox):
    user_id = _aluno("d4@teste.com")
    emitir_token_definicao(user_id)                   # 'setup' emitido por outro caminho (compra)
    emitir_token_definicao(user_id)
    assert len(_tokens(user_id)) == 2

    _pedir(client, "d4@teste.com")
    assert len(_tokens(user_id)) == 3, "havia 2 na janela: o pedido emite o 3º"
    assert _tokens(user_id)[-1]["purpose"] == "reset"
    _pedir(client, "d4@teste.com")
    assert len(_tokens(user_id)) == 3, "3 tokens de finalidades mistas na janela bloqueiam o próximo"
    assert len(_outbox_registros(outbox, "d4@teste.com")) == 1


def test_d5_tres_tokens_de_definicao_ja_emitidos_bloqueiam_o_pedido(client, outbox):
    user_id = _aluno("d5@teste.com")
    for _ in range(3):
        emitir_token_definicao(user_id)
    assert _pedir(client, "d5@teste.com").json() == RESPOSTA_PEDIDO
    assert len(_tokens(user_id)) == 3
    assert _outbox_registros(outbox, "d5@teste.com") == []


def test_d6_aluno_sem_senha_tambem_respeita_o_limite(client, outbox):
    user_id = _aluno_sem_senha("d6@teste.com")
    for _ in range(4):
        assert _pedir(client, "d6@teste.com").json() == RESPOSTA_PEDIDO
    assert len(_tokens(user_id)) == 3 and len(_outbox_registros(outbox, "d6@teste.com")) == 3


def test_d7_pedidos_simultaneos_nunca_passam_de_3_tokens_por_conta(client, outbox):
    """Propriedade derivada do limite: 8 pedidos ao mesmo tempo emitem no máximo 3 tokens e 3 mensagens."""
    from app import app as fastapi_app

    user_id = _aluno("d7@teste.com")
    resultados = _disparar_simultaneos(
        lambda i: (i, TestClient(fastapi_app).post(URL_PEDIDO, json={"email": "d7@teste.com"})), N_CONCORRENTES
    )
    assert all(r.status_code == 200 and r.json() == RESPOSTA_PEDIDO for _, r in resultados)
    emitidos = len(_tokens(user_id))
    assert 1 <= emitidos <= 3, f"limite de 3 por hora violado: {emitidos} tokens"
    assert len(_outbox_registros(outbox, "d7@teste.com")) == emitidos, "uma mensagem por token emitido"


# =====================================================================================
# Grupo E - token novo invalida os anteriores abertos da mesma conta e finalidade
# =====================================================================================

def test_e1_token_anterior_passa_a_ser_recusado(client, outbox):
    user_id = _aluno("e1@teste.com")
    primeiro = _novo_reset(client, outbox, "e1@teste.com")
    segundo = _novo_reset(client, outbox, "e1@teste.com")
    assert primeiro != segundo

    linhas = _tokens(user_id)
    assert len(linhas) == 2
    assert linhas[0]["used_at"] is not None, "o token anterior fica marcado como usado"
    assert linhas[1]["used_at"] is None

    _erro_padrao(_redefinir(client, primeiro, SENHA_NOVA))
    assert _login(client, "e1@teste.com", SENHA_ANTIGA).status_code == 200, "token invalidado não troca a senha"
    assert _redefinir(client, segundo, SENHA_NOVA).status_code == 200


def test_e2_invalida_so_a_mesma_conta_e_a_mesma_finalidade(client, outbox):
    id_a, id_b = _aluno("e2.a@teste.com"), _aluno("e2.b@teste.com")
    setup_a = emitir_token_definicao(id_a)            # outra finalidade, mesma conta
    token_b = _novo_reset(client, outbox, "e2.b@teste.com")   # outra conta
    _novo_reset(client, outbox, "e2.a@teste.com")

    abertos_a = {l["purpose"]: l["used_at"] for l in _tokens(id_a)}
    assert abertos_a["setup"] is None, "o token 'setup' não é invalidado por um pedido de 'reset'"
    assert _tokens(id_b)[0]["used_at"] is None, "pedido de uma conta não invalida token de outra"
    assert _redefinir(client, token_b, SENHA_NOVA).status_code == 200
    assert hash_token(setup_a) == [l for l in _tokens(id_a) if l["purpose"] == "setup"][0]["token_hash"]


# =====================================================================================
# Grupo F - POST /api/auth/password-reset
# =====================================================================================

def test_f1_sucesso_texto_exato_senha_antiga_deixa_de_logar_e_a_nova_loga(client, outbox):
    _aluno("f1@teste.com")
    token = _novo_reset(client, outbox, "f1@teste.com")

    r = _redefinir(client, token, SENHA_NOVA)
    assert r.status_code == 200, r.text
    assert r.json() == RESPOSTA_REDEFINIR

    assert _login(client, "f1@teste.com", SENHA_ANTIGA).status_code == 400, "a senha antiga não pode mais logar"
    login = _login(client, "f1@teste.com", SENHA_NOVA)
    assert login.status_code == 200 and login.json().get("access_token")
    hash_novo = _usuario("f1@teste.com")["password_hash"]
    assert hash_novo.startswith("$2b$") and verify_password(SENHA_NOVA, hash_novo)
    assert _usuario("f1@teste.com")["role"] == "student"


def test_f2_token_de_uso_unico_o_segundo_uso_e_400_e_nao_troca_a_senha(client, outbox):
    user_id = _aluno("f2@teste.com")
    token = _novo_reset(client, outbox, "f2@teste.com")
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200
    assert _tokens(user_id)[0]["used_at"] is not None

    _erro_padrao(_redefinir(client, token, SENHA_OUTRA))
    assert _login(client, "f2@teste.com", SENHA_NOVA).status_code == 200
    assert _login(client, "f2@teste.com", SENHA_OUTRA).status_code == 400


def test_f3_token_expirado_e_recusado(client, outbox):
    user_id = _aluno("f3@teste.com")
    token = _novo_reset(client, outbox, "f3@teste.com")
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?", ("2000-01-01 00:00:00", user_id))

    _erro_padrao(_redefinir(client, token, SENHA_NOVA))
    assert _login(client, "f3@teste.com", SENHA_ANTIGA).status_code == 200
    assert _login(client, "f3@teste.com", SENHA_NOVA).status_code == 400
    assert _tokens(user_id)[0]["used_at"] is None


def test_f3b_token_perto_do_fim_da_hora_ainda_vale_e_apos_a_hora_nao(client, outbox):
    user_id = _aluno("f3b@teste.com")
    token = _inserir_token(user_id, "reset", horas=1)
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?",
              (_fmt(_agora() + timedelta(minutes=2)), user_id))
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200

    outro = _aluno("f3b.2@teste.com")
    token2 = _inserir_token(outro, "reset")
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?",
              (_fmt(_agora() - timedelta(minutes=2)), outro))
    _erro_padrao(_redefinir(client, token2, SENHA_NOVA))


@pytest.mark.parametrize("token", ["token-que-nunca-foi-emitido-" + "x" * 32, "", "A" * 1000, " "],
                         ids=["inexistente", "vazio", "longo", "espaco"])
def test_f4_token_inexistente_ou_forjado_e_400(client, token):
    _aluno("f4@teste.com")
    _erro_padrao(_redefinir(client, token, SENHA_NOVA))
    assert _login(client, "f4@teste.com", SENHA_ANTIGA).status_code == 200


def test_f5_token_ja_usado_no_banco_e_recusado(client):
    user_id = _aluno("f5@teste.com")
    token = _inserir_token(user_id, "reset", usado=True)
    _erro_padrao(_redefinir(client, token, SENHA_NOVA))
    assert _login(client, "f5@teste.com", SENHA_ANTIGA).status_code == 200


def test_f6_token_setup_e_recusado_no_password_reset(client):
    # conta COM senha (token de compra antigo, ainda aberto)
    com_senha = _aluno("f6.com@teste.com")
    token_com = emitir_token_definicao(com_senha)
    _erro_padrao(_redefinir(client, token_com, SENHA_NOVA))
    assert _login(client, "f6.com@teste.com", SENHA_ANTIGA).status_code == 200
    assert _tokens(com_senha)[0]["used_at"] is None, "token recusado não é consumido"

    # conta SEM senha: o token de definição só vale em /password-setup
    sem_senha = _aluno_sem_senha("f6.sem@teste.com")
    token_sem = emitir_token_definicao(sem_senha)
    _erro_padrao(_redefinir(client, token_sem, SENHA_NOVA))
    assert _usuario("f6.sem@teste.com")["password_hash"] is None
    assert _tokens(sem_senha)[0]["used_at"] is None
    assert _definir(client, token_sem, SENHA_NOVA).status_code == 200, "o mesmo token ainda vale em /password-setup"


def test_f7_token_reset_e_recusado_no_password_setup(client, outbox):
    # conta sem senha com token 'reset' forjado: /password-setup não pode aceitá-lo
    sem_senha = _aluno_sem_senha("f7.sem@teste.com")
    token = _inserir_token(sem_senha, "reset")
    _erro_padrao(_definir(client, token, SENHA_NOVA))
    assert _usuario("f7.sem@teste.com")["password_hash"] is None
    assert _tokens(sem_senha)[0]["used_at"] is None

    # conta com senha: token legítimo de redefinição também é recusado em /password-setup
    _aluno("f7.com@teste.com")
    token_reset = _novo_reset(client, outbox, "f7.com@teste.com")
    _erro_padrao(_definir(client, token_reset, SENHA_OUTRA))
    assert _login(client, "f7.com@teste.com", SENHA_ANTIGA).status_code == 200
    assert _redefinir(client, token_reset, SENHA_NOVA).status_code == 200, "o token ainda vale em /password-reset"


@pytest.mark.parametrize("senha", ["", "1234567", "abc", "ñññññññ"[:3]], ids=["vazia", "7_caracteres", "3", "3_acentos"])
def test_f8a_senha_com_menos_de_8_caracteres_e_400_sem_consumir_o_token(client, outbox, senha):
    user_id = _aluno("f8a@teste.com")
    token = _novo_reset(client, outbox, "f8a@teste.com")
    _erro_padrao(_redefinir(client, token, senha))
    assert _tokens(user_id)[0]["used_at"] is None, "senha recusada não consome o token"
    assert _login(client, "f8a@teste.com", SENHA_ANTIGA).status_code == 200
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200, "o mesmo token ainda serve com senha válida"


@pytest.mark.parametrize("longa", ["A" * 73, "é" * 37, "A" * 1000], ids=["73_ascii", "74_bytes", "1000_ascii"])
def test_f8b_senha_com_mais_de_72_bytes_e_400_sem_consumir_o_token(client, outbox, longa):
    user_id = _aluno("f8b@teste.com")
    token = _novo_reset(client, outbox, "f8b@teste.com")
    r = _redefinir(client, token, longa)
    _erro_padrao(r)
    assert longa not in r.text
    assert _tokens(user_id)[0]["used_at"] is None
    assert _login(client, "f8b@teste.com", SENHA_ANTIGA).status_code == 200
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200


@pytest.mark.parametrize("senha", ["A" * 72, SENHA_72_ACENTOS, "é" * 36], ids=["72_ascii", "72_acentos_mistos", "72_so_acentos"])
def test_f8c_senha_de_exatamente_72_bytes_e_aceita_e_loga(client, outbox, senha):
    _aluno("f8c@teste.com")
    token = _novo_reset(client, outbox, "f8c@teste.com")
    assert _redefinir(client, token, senha).status_code == 200
    assert _login(client, "f8c@teste.com", senha).status_code == 200
    assert _login(client, "f8c@teste.com", senha + "x").status_code == 400


def test_f8d_senha_com_exatamente_8_caracteres_e_aceita(client, outbox):
    _aluno("f8d@teste.com")
    token = _novo_reset(client, outbox, "f8d@teste.com")
    assert _redefinir(client, token, "12345678").status_code == 200
    assert _login(client, "f8d@teste.com", "12345678").status_code == 200


def test_f9_user_id_email_e_role_extras_sao_ignorados_o_alvo_e_o_dono_do_token(client, outbox):
    id_a, id_b = _aluno("f9.a@teste.com", "senha-da-conta-a-ok"), _aluno("f9.b@teste.com", "senha-da-conta-b-ok")
    token_a = _novo_reset(client, outbox, "f9.a@teste.com")
    hash_b = _usuario("f9.b@teste.com")["password_hash"]

    r = _redefinir(client, token_a, SENHA_NOVA, user_id=id_b, email="f9.b@teste.com", role="admin", id=id_b)
    assert r.status_code == 200, r.text
    assert r.json() == RESPOSTA_REDEFINIR

    assert _login(client, "f9.a@teste.com", SENHA_NOVA).status_code == 200, "o dono do token teve a senha trocada"
    assert _login(client, "f9.a@teste.com", "senha-da-conta-a-ok").status_code == 400
    assert _usuario("f9.b@teste.com")["password_hash"] == hash_b, "a conta apontada pelo cliente não pode mudar"
    assert _login(client, "f9.b@teste.com", "senha-da-conta-b-ok").status_code == 200
    assert _login(client, "f9.b@teste.com", SENHA_NOVA).status_code == 400
    assert _usuario("f9.a@teste.com")["role"] == "student", "role do corpo é ignorado"
    assert _usuario("f9.b@teste.com")["role"] == "student"
    assert _avisos(outbox, "f9.b@teste.com") == [], "a conta alheia não recebe aviso de alteração"
    assert len(_avisos(outbox, "f9.a@teste.com")) == 1


def test_f9b_token_de_uma_conta_nao_serve_com_email_de_outra_no_corpo_e_nada_muda(client, outbox):
    _aluno("f9b.a@teste.com")
    _aluno("f9b.b@teste.com")
    _erro_padrao(_redefinir(client, "token-inexistente-" + "z" * 30, SENHA_NOVA, email="f9b.b@teste.com", user_id=2))
    assert _login(client, "f9b.a@teste.com", SENHA_ANTIGA).status_code == 200
    assert _login(client, "f9b.b@teste.com", SENHA_ANTIGA).status_code == 200


def test_f10_a_redefinicao_invalida_os_outros_tokens_abertos_da_conta(client, outbox):
    id_a, id_b = _aluno("f10.a@teste.com"), _aluno("f10.b@teste.com")
    token_a = _novo_reset(client, outbox, "f10.a@teste.com")
    setup_aberto = emitir_token_definicao(id_a)                   # outro token aberto, outra finalidade
    reset_extra = _inserir_token(id_a, "reset")                   # segundo 'reset' aberto (contorna o pedido)
    token_b = _novo_reset(client, outbox, "f10.b@teste.com")      # outra conta

    assert _redefinir(client, token_a, SENHA_NOVA).status_code == 200

    assert all(l["used_at"] is not None for l in _tokens(id_a)), "todos os tokens da conta ficam invalidados"
    _erro_padrao(_redefinir(client, reset_extra, SENHA_OUTRA))
    _erro_padrao(_redefinir(client, setup_aberto, SENHA_OUTRA))
    assert _login(client, "f10.a@teste.com", SENHA_NOVA).status_code == 200
    assert _tokens(id_b)[0]["used_at"] is None, "o token de outra conta não é invalidado"
    assert _redefinir(client, token_b, SENHA_NOVA).status_code == 200


@pytest.mark.parametrize("rodada", [1, 2, 3])
def test_f11_requisicoes_simultaneas_com_o_mesmo_token_so_uma_vence(client, outbox, rodada):
    from app import app as fastapi_app

    email = f"f11.{rodada}@teste.com"
    user_id = _aluno(email)
    token = _novo_reset(client, outbox, email)
    senhas = [f"senha-concorrente-{rodada}-{i}-ok" for i in range(N_CONCORRENTES)]

    def tarefa(i):
        r = TestClient(fastapi_app).post(URL_REDEFINIR, json={"token": token, "password": senhas[i]})
        return (i, r.status_code, r.text)

    resultados = _disparar_simultaneos(tarefa, N_CONCORRENTES)
    codigos = sorted(c for _, c, _ in resultados)
    assert codigos == [200] + [400] * (N_CONCORRENTES - 1), f"respostas = {[(i, c) for i, c, _ in resultados]}"
    vencedor = [i for i, c, _ in resultados if c == 200][0]

    assert _login(client, email, senhas[vencedor]).status_code == 200, "a conta fica com a senha do vencedor"
    for i, senha in enumerate(senhas):
        if i != vencedor:
            assert _login(client, email, senha).status_code == 400, f"a senha do perdedor {i} não pode logar"
    assert _login(client, email, SENHA_ANTIGA).status_code == 400
    assert all(l["used_at"] is not None for l in _tokens(user_id))
    for _, c, texto in resultados:
        if c == 400:
            assert token not in texto and all(s not in texto for s in senhas)
    assert len(_avisos(outbox, email)) == 1, "exatamente um aviso de senha alterada (só o vencedor)"


def test_f12_aviso_de_senha_alterada_vai_ao_dono_sem_senha_e_sem_token(client, outbox):
    _aluno("f12@teste.com")
    token = _novo_reset(client, outbox, "f12@teste.com")
    assert _avisos(outbox, "f12@teste.com") == [], "nenhum aviso antes da redefinição"

    assert _redefinir(client, token, SENHA_NOVA).status_code == 200

    avisos = _avisos(outbox, "f12@teste.com")
    assert len(avisos) == 1, f"esperado UM aviso, veio {len(avisos)}"
    aviso = avisos[0]
    assert aviso["email"] == "f12@teste.com"
    assert aviso["assunto"] == ASSUNTO_AVISO
    assert f"{BASE_FRONT}/login" in aviso["mensagem"], "a mensagem traz a URL de login"
    texto = json.dumps(aviso, ensure_ascii=False)
    assert SENHA_NOVA not in texto and SENHA_ANTIGA not in texto, "o aviso não pode conter senha"
    assert token not in texto and "token=" not in texto and "redefinir-senha" not in texto, "o aviso não pode conter token nem link de redefinição"
    assert "link" not in aviso or "token" not in str(aviso["link"])
    assert len(_outbox_registros(outbox, "f12@teste.com")) == 2, "link de redefinição + aviso, nada além"


def test_f12b_falhas_nao_enviam_aviso_e_nao_alteram_a_conta(client, outbox):
    user_id = _aluno("f12b@teste.com")
    token = _novo_reset(client, outbox, "f12b@teste.com")
    hash_antes = _usuario("f12b@teste.com")["password_hash"]
    _redefinir(client, "token-inexistente-" + "q" * 30, SENHA_NOVA)
    _redefinir(client, token, "curta")
    _redefinir(client, token, "A" * 80)
    assert _avisos(outbox, "f12b@teste.com") == []
    assert _usuario("f12b@teste.com")["password_hash"] == hash_antes
    assert _tokens(user_id)[0]["used_at"] is None


def test_f13_todas_as_falhas_tem_o_mesmo_status_e_o_texto_de_erro_padrao(client, outbox):
    corpos = []
    # token inexistente
    corpos.append(_redefinir(client, "inexistente-" + "k" * 30, SENHA_NOVA))
    # token usado
    _aluno("f13.usado@teste.com")
    t = _novo_reset(client, outbox, "f13.usado@teste.com")
    assert _redefinir(client, t, SENHA_NOVA).status_code == 200
    corpos.append(_redefinir(client, t, SENHA_OUTRA))
    # token expirado
    exp = _aluno("f13.exp@teste.com")
    t = _inserir_token(exp, "reset")
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?", ("2000-01-01 00:00:00", exp))
    corpos.append(_redefinir(client, t, SENHA_NOVA))
    # outra finalidade
    setup = _aluno("f13.setup@teste.com")
    corpos.append(_redefinir(client, emitir_token_definicao(setup), SENHA_NOVA))
    # senha fora da política
    _aluno("f13.fraca@teste.com")
    t = _novo_reset(client, outbox, "f13.fraca@teste.com")
    corpos.append(_redefinir(client, t, "curta"))
    corpos.append(_redefinir(client, t, "A" * 73))
    # campo extra com user_id e token inexistente
    corpos.append(_redefinir(client, "inexistente2-" + "k" * 30, SENHA_NOVA, user_id=1))

    for r in corpos:
        _erro_padrao(r)
    assert len({r.content for r in corpos}) == 1, "o corpo de erro é o mesmo em todas as falhas"


def test_f14_conta_de_funcionario_nunca_e_afetada_nem_por_token_forjado_no_banco(client, outbox):
    ids = {
        "admin": _funcionario("f14.admin@teste.com", "admin"),
        "financial": _funcionario("f14.fin@teste.com", "financial"),
        "support": _funcionario("f14.sup@teste.com", "support"),
    }
    emails = {"admin": "f14.admin@teste.com", "financial": "f14.fin@teste.com", "support": "f14.sup@teste.com"}
    for perfil, user_id in ids.items():
        antes = _usuario(emails[perfil])
        token = _inserir_token(user_id, "reset")
        _erro_padrao(_redefinir(client, token, SENHA_NOVA))
        assert _usuario(emails[perfil]) == antes, f"a conta {perfil} não pode ser alterada"
        assert _login(client, emails[perfil], SENHA_ANTIGA).status_code == 200
        assert _login(client, emails[perfil], SENHA_NOVA).status_code == 400
        assert _avisos(outbox, emails[perfil]) == []


def test_f14b_funcionario_sem_senha_com_token_forjado_continua_sem_senha(client):
    user_id = _funcionario("f14b@teste.com", "financial", senha=None)
    token = _inserir_token(user_id, "reset")
    _erro_padrao(_redefinir(client, token, SENHA_NOVA))
    assert _usuario("f14b@teste.com")["password_hash"] is None
    assert _login(client, "f14b@teste.com", SENHA_NOVA).status_code == 400


def test_f15_respostas_nao_ecoam_email_token_nem_senha_e_nao_gravam_auditoria(client, outbox):
    _aluno("f15@teste.com")
    antes = _auditoria()
    textos = []

    r = _pedir(client, "f15@teste.com")
    textos.append(r.text)
    token = _ultimo_token(outbox, "f15@teste.com", "/redefinir-senha")

    falha = _redefinir(client, token, "curta")
    textos.append(falha.text)
    falha2 = _redefinir(client, "forjado-" + "w" * 30, SENHA_OUTRA, email="f15@teste.com")
    textos.append(falha2.text)
    ok = _redefinir(client, token, SENHA_NOVA)
    assert ok.status_code == 200
    textos.append(ok.text)
    textos.append(_redefinir(client, token, SENHA_OUTRA).text)

    for texto in textos:
        assert "f15@teste.com" not in texto and "@" not in texto
        assert token not in texto
        for senha in (SENHA_NOVA, SENHA_OUTRA, SENHA_ANTIGA, "curta"):
            assert senha not in texto
    assert _auditoria() == antes, "fluxo do aluno não grava trilha de auditoria (login de aluno também não grava)"


def test_f16_token_so_vale_com_o_hash_gravado_o_hash_em_si_nao_e_um_token_valido(client, outbox):
    user_id = _aluno("f16@teste.com")
    token = _novo_reset(client, outbox, "f16@teste.com")
    hash_gravado = _tokens(user_id)[0]["token_hash"]
    _erro_padrao(_redefinir(client, hash_gravado, SENHA_NOVA))
    assert _tokens(user_id)[0]["used_at"] is None
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200


# =====================================================================================
# Grupo G - compatibilidade (migração da coluna `purpose`, fluxo de compra da E2)
# =====================================================================================

DDL_TOKENS_ANTIGO = """
    CREATE TABLE password_setup_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
"""


def _criar_banco_antigo(db_path):
    """Banco anterior à D60: users + password_setup_tokens SEM a coluna `purpose`, com 3 tokens."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            password_hash TEXT, role TEXT DEFAULT 'student', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(DDL_TOKENS_ANTIGO)
    conn.execute("INSERT INTO users (email, name, password_hash, role) VALUES ('antigo@teste.com', 'Antigo', NULL, 'student')")
    futuro, passado = _fmt(_agora() + timedelta(hours=10)), "2000-01-01 00:00:00"
    token_aberto = "token-antigo-aberto-" + "a" * 30
    conn.execute("INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, used_at) VALUES (1, ?, ?, NULL)",
                 (hash_token(token_aberto), futuro))
    conn.execute("INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, used_at) VALUES (1, ?, ?, ?)",
                 (hash_token("token-antigo-usado-" + "b" * 30), futuro, _fmt(_agora())))
    conn.execute("INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, used_at) VALUES (1, ?, ?, NULL)",
                 (hash_token("token-antigo-expirado-" + "c" * 30), passado))
    conn.commit()
    conn.close()
    return token_aberto


def test_g1_init_db_cria_a_coluna_purpose_com_padrao_setup_em_banco_novo(banco):
    colunas = {c["name"]: c for c in _sql("PRAGMA table_info(password_setup_tokens)")}
    assert "purpose" in colunas, "falta a coluna password_setup_tokens.purpose (D60)"
    assert colunas["purpose"]["type"].upper() == "TEXT"
    assert colunas["purpose"]["notnull"] == 1
    assert str(colunas["purpose"]["dflt_value"]).strip("'\"") == "setup"
    # inserção sem informar a finalidade (caminho legado) vira 'setup'
    user_id = Database.get_or_create_user("g1@teste.com", "G1")
    Database.insert_password_setup_token(user_id, hash_token("qualquer-g1"), _fmt(_agora() + timedelta(hours=1)))
    assert _tokens(user_id)[0]["purpose"] == "setup"


def test_g2_init_db_migra_banco_antigo_tokens_antigos_viram_setup_sem_perder_nada(db_path):
    _criar_banco_antigo(db_path)
    antes = _sql("SELECT id, user_id, token_hash, expires_at, used_at FROM password_setup_tokens ORDER BY id")
    assert len(antes) == 3

    Database.init_db()

    colunas = {c["name"] for c in _sql("PRAGMA table_info(password_setup_tokens)")}
    assert "purpose" in colunas, "init_db precisa adicionar a coluna purpose a bancos antigos"
    depois = _sql("SELECT id, user_id, token_hash, expires_at, used_at, purpose FROM password_setup_tokens ORDER BY id")
    assert [l["purpose"] for l in depois] == ["setup", "setup", "setup"], "tokens antigos viram 'setup'"
    assert [{k: v for k, v in l.items() if k != "purpose"} for l in depois] == antes, "nenhum dado antigo pode mudar"
    assert _usuario("antigo@teste.com")["role"] == "student"


def test_g3_init_db_e_idempotente_com_a_coluna_purpose(db_path):
    _criar_banco_antigo(db_path)
    Database.init_db()
    _inserir_token(1, "reset")
    primeira = _sql("SELECT * FROM password_setup_tokens ORDER BY id")

    Database.init_db()
    Database.init_db()

    assert _sql("SELECT * FROM password_setup_tokens ORDER BY id") == primeira, "rodar init_db de novo não altera nada"
    assert [l["purpose"] for l in primeira] == ["setup", "setup", "setup", "reset"]
    assert [c["name"] for c in _sql("PRAGMA table_info(password_setup_tokens)")].count("purpose") == 1


def test_g4_token_antigo_aberto_continua_valendo_em_password_setup_apos_a_migracao(db_path, outbox, curso_teste):
    from app import app as fastapi_app

    token = _criar_banco_antigo(db_path)
    Database.init_db()
    with TestClient(fastapi_app) as c:
        r = _redefinir(c, token, SENHA_NOVA)                       # é 'setup': não vale em /password-reset
        _erro_padrao(r)
        assert _usuario("antigo@teste.com")["password_hash"] is None
        assert _definir(c, token, SENHA_NOVA).status_code == 200
        assert _login(c, "antigo@teste.com", SENHA_NOVA).status_code == 200


def test_g5_fluxo_de_compra_continua_emitindo_token_setup_e_enviando_o_link(client, outbox):
    resposta_mp = MagicMock(status_code=201)
    resposta_mp.json.return_value = {"id": "pref-b1", "init_point": "https://mp.test/checkout"}
    with patch("payments.routes.requests.post", return_value=resposta_mp):
        r = client.post("/api/payments/create-checkout", json={
            "course_id": "curso_teste", "payer": {"name": "Comprador B1", "email": "comprador.b1@teste.com"},
        })
    assert r.status_code == 200, r.text
    ref = r.json()["external_reference"]

    pagamento_id = id_de_pagamento(ref)
    consulta = MagicMock(status_code=200)
    consulta.json.return_value = corpo_pagamento_mp("approved", ref, 100.0, pagamento_id)
    with patch("payments.routes.requests.get", return_value=consulta):
        assert post_webhook(client, pagamento_id).status_code == 200

    _exigir_coluna_purpose()
    conta = _usuario("comprador.b1@teste.com")
    linhas = _tokens(conta["id"])
    assert len(linhas) == 1 and linhas[0]["purpose"] == "setup"
    registros = _outbox_registros(outbox, "comprador.b1@teste.com")
    assert len(registros) == 1
    assert registros[0]["link"].startswith(f"{BASE_FRONT}/definir-senha?token=")
    token = _token_do_link(registros[0]["link"])
    assert linhas[0]["token_hash"] == hash_token(token)
    assert _definir(client, token, SENHA_NOVA).status_code == 200
    assert _login(client, "comprador.b1@teste.com", SENHA_NOVA).status_code == 200


def test_g6_recuperacao_apos_expirar_o_link_da_compra_leva_o_aluno_a_definir_a_senha(client, outbox):
    """Cenário que motivou a D60: o link de compra expirou; o aluno sem senha pede de novo e consegue definir."""
    user_id = _aluno_sem_senha("g6@teste.com")
    token_antigo = _inserir_token(user_id, "setup", horas=48)
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE id = ?", ("2000-01-01 00:00:00", _tokens(user_id)[0]["id"]))
    _erro_padrao(_definir(client, token_antigo, SENHA_NOVA))

    assert _pedir(client, "g6@teste.com").json() == RESPOSTA_PEDIDO
    novo = _ultimo_token(outbox, "g6@teste.com", "/definir-senha")
    assert _definir(client, novo, SENHA_NOVA).status_code == 200
    assert _login(client, "g6@teste.com", SENHA_NOVA).status_code == 200
