"""E5 - Chatbot autenticado com historico persistido (secao 4 do escopo, D35).

Escritos ANTES da implementacao. Devem falhar agora: as rotas /api/student/chat e
/api/student/chat/history ainda nao existem (404), a tabela chat_messages nao existe e o
dashboard de alunos ainda nao traz chat_messages / last_chat_at.

Contrato (D35.5):
  POST /api/student/chat          corpo {"message": str} -> {"status": "success", "message": <bot>}
  GET  /api/student/chat/history  -> {"status": "success", "messages": [{role, content, created_at}]}
  Cada troca grava 2 linhas em chat_messages (user e assistant), persistidas em banco.
  Contexto enviado ao LLM: nome do aluno + nomes dos cursos com matricula 'active' + ultimas 10
  mensagens persistidas do proprio aluno. Nunca: pagamento, curso pending/cancelled/refunded, URL.
  Identidade so pelo JWT. GET /api/dashboard/alunos: cada aluno ganha chat_messages e last_chat_at.

Testes:
  T1  POST feliz: 200, corpo {status, message} com a resposta do bot.
  T2  cada troca grava 2 linhas (user, assistant) em chat_messages, com user_id do dono do token.
  T3  mensagem vazia / so espacos / ausente: 422, nada gravado, LLM nao chamado.
  T4  GET history: ordem cronologica crescente, campos role/content/created_at, so o dono.
  T5  aluno sem conversa: lista vazia.
  T6  persistencia nao e memoria (a): limpar manager_agent.sessions e o contexto ainda traz o historico.
  T7  persistencia nao e memoria (b): novo app/ManagerAgent (novo ciclo de vida) mantem GET e contexto.
  T8  contexto leva so as ultimas 10 mensagens persistidas.
  T9  contexto traz nome do aluno e cursos 'active'.
  T10 pending/cancelled/refunded: nome do curso nao entra no contexto (parametrizado).
  T11 pagamento (valor, id externo, transaction_id) e URLs de material nunca vao ao LLM nem a resposta.
  T12 aluno sem matriculas conversa normalmente (contexto sem cursos).
  T13 IDOR no POST: user_id/student_id/session_id no corpo sao ignorados; A nao grava como B.
  T14 IDOR no GET: user_id/student_id/session_id na query sao ignorados; A nao le B.
  T15 isolamento A x B: historicos separados e nada de B no contexto de A (mesmo session_id).
  T16 /api/chat anonimo nao enxerga o historico persistido de um aluno.
  T17 sem token e token forjado: 401 nos dois endpoints, nada gravado, LLM nao chamado.
  T18 admin, financeiro e suporte (JWT e token administrativo): 403 nos dois endpoints.
  T19 dashboard: chat_messages e last_chat_at por aluno; 0/null para quem nunca conversou.
  T20 dashboard nao expoe o conteudo das mensagens; total_chat_sessions segue a regra de hoje.
  T21 RBAC do dashboard: admin, financeiro e suporte continuam com 200.
  T22 regressao: /api/chat anonimo segue respondendo sem token e sem gravar em chat_messages.

Seam: GroqChatClient.create_chat_completion e trocado por um duble que captura as mensagens e devolve
um texto unico por chamada. Nenhum teste chama a API real do Groq.

Convencoes (padrao de test_e3/test_e4): banco temporario via conftest, rotas HTTP reais, token real por
POST /api/token, matricula por Database (create_enrollment + record_payment + status por referencia).
Os cursos vivem em um diretorio temporario (admin.routes.COURSES_DIR), como na E3.
"""

import copy
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from agents.groq_client import GroqChatClient
from core.security import get_password_hash
from db import Database


SENHA = "senha-aluno-e5-2026"
ROTA_CHAT = "/api/student/chat"
ROTA_HISTORICO = "/api/student/chat/history"
ROTA_DASHBOARD = "/api/dashboard/alunos"
ROTA_CHAT_ANONIMO = "/api/chat"
PERFIS_FUNCIONARIO = ["admin", "financial", "support"]
SENHAS_ADMINISTRATIVAS = [("admin123", "admin"), ("fin123", "financial"), ("sup123", "support")]

VALOR_SECRETO = 4321.09
TRANSACAO_SECRETA = "mp-tx-e5-segredo-9981"

NOMES = {
    "ativo": "Curso Ativo Alfa",
    "ativo2": "Curso Ativo Beta",
    "pending": "Curso Pendente Gama",
    "cancelled": "Curso Cancelado Delta",
    "refunded": "Curso Reembolsado Epsilon",
}
IDS = {chave: f"curso_e5_{chave}" for chave in NOMES}
URL_MATERIAL = {chave: f"https://materiais.test/e5/{chave}/apostila.pdf" for chave in NOMES}
STATUS_DE_PAGAMENTO = {
    "active": "approved",
    "pending": "pending",
    "cancelled": "cancelled",
    "refunded": "refunded",
}


# --- Duble do LLM -----------------------------------------------------------------------

class LLMDuble:
    """Captura toda chamada ao modelo e responde com um texto unico por chamada."""

    def __init__(self):
        self.chamadas = []

    def responder(self, messages):
        self.chamadas.append(copy.deepcopy(messages))
        return f"RESPOSTA-DUBLE-{uuid.uuid4().hex[:10]}"

    def limpar(self):
        self.chamadas.clear()

    @staticmethod
    def texto(chamada):
        return "\n".join(str(m.get("content", "")) for m in chamada)

    def contexto_final(self):
        """Texto da ultima chamada ao modelo (a que produz a resposta ao aluno)."""
        assert self.chamadas, "o LLM nao foi chamado"
        return self.texto(self.chamadas[-1])

    def contexto_total(self):
        """Texto de todas as chamadas feitas ao modelo desde o ultimo limpar()."""
        return "\n".join(self.texto(c) for c in self.chamadas)


# --- Fixtures ---------------------------------------------------------------------------

@pytest.fixture
def llm(monkeypatch):
    duble = LLMDuble()

    def falso(self, messages, max_tokens=1024, temperature=0.7):
        return duble.responder(messages)

    monkeypatch.setattr(GroqChatClient, "create_chat_completion", falso)
    return duble


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Cinco cursos em diretorio temporario, todos com materials (URL unica por curso)."""
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    for chave, nome in NOMES.items():
        (diretorio / f"{IDS[chave]}.json").write_text(json.dumps({
            "id": IDS[chave],
            "name": nome,
            "description": f"Descricao de {nome}",
            "price": 100.0,
            "materials": [{"title": f"Apostila {chave}", "url": URL_MATERIAL[chave], "type": "pdf"}],
        }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return IDS


@pytest.fixture
def client(banco, cursos, llm):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco -------------------------------------------------------------------

def _consultar(sql, params=()):
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


def _tabela_chat_existe():
    return bool(_consultar("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chat_messages'"))


def _linhas_chat(user_id=None):
    """Linhas de chat_messages por id crescente; [] se a tabela ainda nao existe."""
    if not _tabela_chat_existe():
        return []
    if user_id is None:
        return _consultar("SELECT * FROM chat_messages ORDER BY id")
    return _consultar("SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id", (user_id,))


def _conta_aluno(email, nome="Aluno E5"):
    user_id = Database.get_or_create_user(email, nome)
    _executar("UPDATE users SET password_hash = ? WHERE id = ?", (get_password_hash(SENHA), user_id))
    return user_id


def _conta_funcionario(email, perfil):
    user_id = Database.add_user(email, f"Funcionario {perfil}", get_password_hash(SENHA), role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    return user_id


def _matricula(user_id, chave_curso, status):
    """Matricula real no status pedido, com pagamento de valor e transacao secretos."""
    referencia = f"{IDS[chave_curso]}:e5:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, IDS[chave_curso], referencia)
    Database.record_payment(enrollment_id, VALOR_SECRETO, "mercado_pago")
    Database.update_payment_status_by_reference(referencia, STATUS_DE_PAGAMENTO[status], TRANSACAO_SECRETA)
    atual = _consultar("SELECT status FROM enrollments WHERE id = ?", (enrollment_id,))[0]["status"]
    assert atual == status, f"seed: matricula ficou {atual}, esperado {status}"
    return enrollment_id, referencia


# --- Helpers de HTTP --------------------------------------------------------------------

def _login(client, email):
    r = client.post("/api/token", data={"username": email, "password": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _marcador():
    return f"mk-{uuid.uuid4().hex[:8]}"


def _texto_usuario():
    # Sem palavras que casem com palavras-chave de cursos reais (python, excel, lua, c, sql, ia...).
    return f"Mensagem de teste {_marcador()}"


def _enviar(client, token, texto, **extra):
    return client.post(ROTA_CHAT, json={"message": texto, **extra}, headers=_auth(token))


def _enviar_ok(client, token, texto=None, **extra):
    texto = texto or _texto_usuario()
    r = _enviar(client, token, texto, **extra)
    assert r.status_code == 200, f"POST {ROTA_CHAT}: HTTP {r.status_code} {r.text[:200]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert isinstance(corpo.get("message"), str) and corpo["message"], corpo
    return texto, corpo["message"], r


def _historico(client, token, query=""):
    r = client.get(ROTA_HISTORICO + query, headers=_auth(token))
    assert r.status_code == 200, f"GET {ROTA_HISTORICO}: HTTP {r.status_code} {r.text[:200]}"
    corpo = r.json()
    assert corpo.get("status") == "success", corpo
    assert isinstance(corpo.get("messages"), list), corpo
    return corpo["messages"], r


def _forjado(user_id, email):
    return jose_jwt.encode(
        {"user_id": user_id, "email": email, "role": "student", "exp": datetime.utcnow() + timedelta(hours=1)},
        "segredo-do-atacante-que-nao-e-o-real",
        algorithm="HS256",
    )


def _aluno_logado(client, email, nome="Aluno E5"):
    user_id = _conta_aluno(email, nome)
    return user_id, _login(client, email)


# --- T1 - T5 : contrato basico ---------------------------------------------------------

def test_t1_post_devolve_status_success_e_a_resposta_do_bot(client, llm):
    _, token = _aluno_logado(client, "t1@e5.test")

    texto, resposta, r = _enviar_ok(client, token)

    assert resposta.startswith("RESPOSTA-DUBLE-"), "a resposta do bot deve ser o texto devolvido pelo LLM"
    assert llm.chamadas, "o LLM (duble) deveria ter sido chamado"
    assert any(texto in LLMDuble.texto(c) for c in llm.chamadas), "a mensagem do aluno deve chegar ao LLM"


def test_t2_cada_troca_grava_duas_linhas_user_e_assistant_do_dono_do_token(client):
    user_id, token = _aluno_logado(client, "t2@e5.test")

    texto, resposta, _ = _enviar_ok(client, token)

    assert _tabela_chat_existe(), "a tabela chat_messages deveria existir"
    linhas = _linhas_chat()
    assert len(linhas) == 2, f"uma troca deve gravar 2 linhas, vieram {len(linhas)}"
    assert [l["role"] for l in linhas] == ["user", "assistant"]
    assert [l["content"] for l in linhas] == [texto, resposta]
    assert all(l["user_id"] == user_id for l in linhas)
    assert all(l["created_at"] for l in linhas)


@pytest.mark.parametrize("corpo", [
    {"message": ""},
    {"message": "   "},
    {"message": "\n\t  \n"},
    {},
], ids=["vazia", "so_espacos", "so_quebras", "sem_campo"])
def test_t3_mensagem_vazia_ou_ausente_devolve_422_e_nao_grava(client, llm, corpo):
    _, token = _aluno_logado(client, "t3@e5.test")
    llm.limpar()

    r = client.post(ROTA_CHAT, json=corpo, headers=_auth(token))

    assert r.status_code == 422, f"esperado 422, veio {r.status_code}: {r.text[:200]}"
    assert _linhas_chat() == [], "mensagem invalida nao pode gravar nada"
    assert llm.chamadas == [], "mensagem invalida nao pode chegar ao LLM"


def test_t4_historico_em_ordem_cronologica_crescente_com_os_tres_campos(client):
    _, token = _aluno_logado(client, "t4@e5.test")
    esperado = []
    for _ in range(3):
        texto, resposta, _r = _enviar_ok(client, token)
        esperado += [("user", texto), ("assistant", resposta)]

    mensagens, _ = _historico(client, token)

    assert [(m["role"], m["content"]) for m in mensagens] == esperado
    for m in mensagens:
        assert m["created_at"], m
        assert "user_id" not in m, "o historico nao deve expor identificadores"
    datas = [m["created_at"] for m in mensagens]
    assert datas == sorted(datas), "created_at deve ser nao decrescente"


def test_t5_aluno_sem_conversa_recebe_lista_vazia(client):
    _, token = _aluno_logado(client, "t5@e5.test")

    mensagens, r = _historico(client, token)

    assert mensagens == []
    assert r.json() == {"status": "success", "messages": []}


# --- T6 - T8 : persistencia real e contexto --------------------------------------------

def test_t6_limpar_a_memoria_do_manager_nao_apaga_o_historico_nem_o_contexto(client, llm):
    _, token = _aluno_logado(client, "t6@e5.test")
    texto1, resposta1, _ = _enviar_ok(client, token)

    client.app.state.manager_agent.sessions.clear()
    llm.limpar()
    texto2, _, _ = _enviar_ok(client, token)

    contexto = llm.contexto_final()
    assert texto1 in contexto and resposta1 in contexto, "o historico persistido deve voltar ao contexto do LLM"
    assert texto2 in contexto
    mensagens, _ = _historico(client, token)
    assert texto1 in [m["content"] for m in mensagens]
    assert len(mensagens) == 4


def test_t7_historico_sobrevive_a_um_novo_app_e_novo_manager_agent(banco, cursos, llm):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as primeiro:
        _, token = _aluno_logado(primeiro, "t7@e5.test")
        texto1, resposta1, _ = _enviar_ok(primeiro, token)
        manager_antigo = fastapi_app.state.manager_agent

    with TestClient(fastapi_app) as segundo:
        assert fastapi_app.state.manager_agent is not manager_antigo, "esperado um ManagerAgent novo"
        assert not any(texto1 in str(v) for v in fastapi_app.state.manager_agent.sessions.values())
        mensagens, _ = _historico(segundo, token)
        assert [(m["role"], m["content"]) for m in mensagens] == [("user", texto1), ("assistant", resposta1)]

        llm.limpar()
        texto2, _, _ = _enviar_ok(segundo, token)
        contexto = llm.contexto_final()
        assert texto1 in contexto and resposta1 in contexto, "o historico persistido deve chegar ao novo manager"
        assert texto2 in contexto


def test_t8_contexto_leva_so_as_ultimas_10_mensagens_persistidas(client, llm):
    _, token = _aluno_logado(client, "t8@e5.test")
    for _ in range(6):
        _enviar_ok(client, token)
    antigas, _ = _historico(client, token)
    assert len(antigas) == 12
    conteudos = [m["content"] for m in antigas]

    llm.limpar()
    texto_novo, _, _ = _enviar_ok(client, token)

    contexto = llm.contexto_final()
    assert texto_novo in contexto
    # Fora da janela: as duas mais antigas. Dentro: as nove mais recentes (a 10a vaga e da mensagem atual).
    for antiga in conteudos[:2]:
        assert antiga not in contexto, f"mensagem fora das ultimas 10 vazou para o contexto: {antiga}"
    for recente in conteudos[3:]:
        assert recente in contexto, f"mensagem recente ausente do contexto: {recente}"
    assert len(_linhas_chat()) == 14, "o historico em banco nao e truncado: so a janela do contexto e"


# --- T9 - T12 : o que entra e o que nao entra no contexto ------------------------------

def test_t9_contexto_traz_nome_do_aluno_e_nomes_dos_cursos_active(client, llm):
    user_id, token = _aluno_logado(client, "t9@e5.test", nome="Marina Quintanilha")
    _matricula(user_id, "ativo", "active")
    _matricula(user_id, "ativo2", "active")
    llm.limpar()

    _enviar_ok(client, token)

    contexto = llm.contexto_final()
    assert "Marina Quintanilha" in contexto
    assert NOMES["ativo"] in contexto
    assert NOMES["ativo2"] in contexto


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_t10_matricula_nao_active_nao_entra_no_contexto(client, llm, status):
    user_id, token = _aluno_logado(client, f"t10.{status}@e5.test", nome="Aluno Dez")
    _matricula(user_id, "ativo", "active")
    _matricula(user_id, status, status)
    llm.limpar()

    _, _, r = _enviar_ok(client, token)

    assert NOMES["ativo"] in llm.contexto_final()
    contexto = llm.contexto_total()
    assert NOMES[status] not in contexto, f"curso com matricula {status} vazou para o LLM"
    assert IDS[status] not in contexto, f"id de curso com matricula {status} vazou para o LLM"
    assert NOMES[status] not in r.text


def test_t11_pagamento_e_urls_de_material_nunca_vao_ao_llm_nem_a_resposta(client, llm):
    user_id, token = _aluno_logado(client, "t11@e5.test", nome="Aluno Onze")
    referencias = []
    for chave, status in (("ativo", "active"), ("pending", "pending"),
                          ("cancelled", "cancelled"), ("refunded", "refunded")):
        _, ref = _matricula(user_id, chave, status)
        referencias.append(ref)
    llm.limpar()

    _, _, r_post = _enviar_ok(client, token)
    _, r_hist = _historico(client, token)

    contexto = llm.contexto_total()
    assert NOMES["ativo"] in llm.contexto_final()
    proibidos = [
        f"{VALOR_SECRETO}", "4321,09", TRANSACAO_SECRETA, "mercado_pago",
        *referencias, *(r.split(":")[-1] for r in referencias),
        *URL_MATERIAL.values(), "materiais.test",
    ]
    for proibido in proibidos:
        assert proibido not in contexto, f"dado proibido no que vai ao LLM: {proibido}"
        assert proibido not in r_post.text, f"dado proibido na resposta do POST: {proibido}"
        assert proibido not in r_hist.text, f"dado proibido na resposta do historico: {proibido}"


def test_t12_aluno_sem_matriculas_conversa_normalmente_com_contexto_sem_cursos(client, llm):
    _, token = _aluno_logado(client, "t12@e5.test", nome="Aluno Sem Cursos")
    llm.limpar()

    texto, resposta, _ = _enviar_ok(client, token)

    contexto = llm.contexto_final()
    assert "Aluno Sem Cursos" in contexto
    assert texto in contexto
    assert not any(nome in llm.contexto_total() for nome in NOMES.values()), "nao ha cursos ativos para citar"
    mensagens, _ = _historico(client, token)
    assert [(m["role"], m["content"]) for m in mensagens] == [("user", texto), ("assistant", resposta)]


# --- T13 - T16 : IDOR e isolamento -----------------------------------------------------

def test_t13_identidade_so_pelo_jwt_no_post_ids_do_corpo_sao_ignorados(client):
    a, token_a = _aluno_logado(client, "t13.a@e5.test", nome="Aluno A")
    b, token_b = _aluno_logado(client, "t13.b@e5.test", nome="Aluno B")
    texto_b, resposta_b, _ = _enviar_ok(client, token_b)

    texto_a, _, _ = _enviar_ok(
        client, token_a, user_id=b, student_id=b, session_id=str(b), userId=b, id=b,
    )

    assert {l["user_id"] for l in _linhas_chat() if l["content"] == texto_a} == {a}
    assert [l["content"] for l in _linhas_chat(b)] == [texto_b, resposta_b], "A nao pode gravar no historico de B"
    mensagens_b, _ = _historico(client, token_b)
    assert texto_a not in [m["content"] for m in mensagens_b]
    mensagens_a, _ = _historico(client, token_a)
    assert texto_a in [m["content"] for m in mensagens_a]
    assert texto_b not in [m["content"] for m in mensagens_a]


def test_t14_identidade_so_pelo_jwt_no_get_ids_da_query_sao_ignorados(client):
    a, token_a = _aluno_logado(client, "t14.a@e5.test", nome="Aluno A")
    b, token_b = _aluno_logado(client, "t14.b@e5.test", nome="Aluno B")
    texto_a, _, _ = _enviar_ok(client, token_a)
    texto_b, _, _ = _enviar_ok(client, token_b)

    mensagens, r = _historico(
        client, token_a, f"?user_id={b}&student_id={b}&session_id={b}&userId={b}")

    conteudos = [m["content"] for m in mensagens]
    assert texto_a in conteudos
    assert texto_b not in conteudos, "A leu o historico de B mandando o id de B na query"
    assert texto_b not in r.text


def test_t15_historicos_separados_e_nada_de_b_no_contexto_de_a_mesmo_com_session_id_igual(client, llm):
    a, token_a = _aluno_logado(client, "t15.a@e5.test", nome="Alice Arruda")
    b, token_b = _aluno_logado(client, "t15.b@e5.test", nome="Bruno Bittencourt")
    _matricula(a, "ativo", "active")
    _matricula(b, "ativo2", "active")
    sessao = "web-chat-session"
    texto_b, resposta_b, _ = _enviar_ok(client, token_b, session_id=sessao)
    texto_a1, resposta_a1, _ = _enviar_ok(client, token_a, session_id=sessao)
    llm.limpar()

    texto_a2, _, _ = _enviar_ok(client, token_a, session_id=sessao)

    contexto_total = llm.contexto_total()
    assert texto_a1 in llm.contexto_final() and resposta_a1 in llm.contexto_final()
    for alheio in (texto_b, resposta_b, "Bruno Bittencourt", NOMES["ativo2"]):
        assert alheio not in contexto_total, f"dado do aluno B no contexto do aluno A: {alheio}"
    assert "Alice Arruda" in llm.contexto_final()
    assert NOMES["ativo"] in llm.contexto_final()

    llm.limpar()
    texto_b2, _, _ = _enviar_ok(client, token_b, session_id=sessao)
    for alheio in (texto_a1, resposta_a1, texto_a2, "Alice Arruda", NOMES["ativo"]):
        assert alheio not in llm.contexto_total(), f"dado do aluno A no contexto do aluno B: {alheio}"

    mensagens_a, _ = _historico(client, token_a)
    mensagens_b, _ = _historico(client, token_b)
    conteudos_a = [m["content"] for m in mensagens_a]
    conteudos_b = [m["content"] for m in mensagens_b]
    assert texto_a1 in conteudos_a and texto_a2 in conteudos_a and len(conteudos_a) == 4
    assert texto_b in conteudos_b and texto_b2 in conteudos_b and len(conteudos_b) == 4
    assert not set(conteudos_a) & set(conteudos_b)


def test_t16_chat_anonimo_nao_enxerga_o_historico_persistido_de_um_aluno(client, llm):
    a, token_a = _aluno_logado(client, "t16@e5.test", nome="Aluno Dezesseis")
    _matricula(a, "ativo", "active")
    texto_a, resposta_a, _ = _enviar_ok(client, token_a)
    llm.limpar()

    r = client.post(ROTA_CHAT_ANONIMO, json={"message": _texto_usuario(), "session_id": str(a)})

    assert r.status_code == 200, r.text
    contexto = llm.contexto_total()
    for privado in (texto_a, resposta_a, "Aluno Dezesseis", NOMES["ativo"]):
        assert privado not in contexto, f"dado do aluno no chat anonimo: {privado}"


# --- T17 - T18 : controle de acesso ----------------------------------------------------

def _chamar(client, rota, headers=None):
    if rota == ROTA_CHAT:
        return client.post(rota, json={"message": _texto_usuario()}, headers=headers or {})
    return client.get(rota, headers=headers or {})


@pytest.mark.parametrize("rota", [ROTA_CHAT, ROTA_HISTORICO])
def test_t17_sem_token_e_token_forjado_recebem_401_e_nada_e_gravado(client, llm, rota):
    user_id, token = _aluno_logado(client, "t17@e5.test")
    llm.limpar()

    sem_token = _chamar(client, rota)
    forjado = _chamar(client, rota, _auth(_forjado(user_id, "t17@e5.test")))

    assert sem_token.status_code == 401, f"sem token em {rota}: {sem_token.status_code}"
    assert forjado.status_code == 401, f"token forjado em {rota}: {forjado.status_code}"
    assert _linhas_chat() == []
    assert llm.chamadas == []


@pytest.mark.parametrize("rota", [ROTA_CHAT, ROTA_HISTORICO])
@pytest.mark.parametrize("perfil", PERFIS_FUNCIONARIO)
def test_t18_funcionario_com_jwt_recebe_403_e_nada_e_gravado(client, llm, perfil, rota):
    email = f"{perfil}.t18@gt.test"
    _conta_funcionario(email, perfil)
    token = _login(client, email)
    llm.limpar()

    r = _chamar(client, rota, _auth(token))

    assert r.status_code == 403, f"{perfil} em {rota}: esperado 403, veio {r.status_code}"
    assert _linhas_chat() == []
    assert llm.chamadas == []


@pytest.mark.parametrize("rota", [ROTA_CHAT, ROTA_HISTORICO])
@pytest.mark.parametrize("senha, perfil", SENHAS_ADMINISTRATIVAS)
def test_t18b_funcionario_com_token_administrativo_recebe_403(client, llm, senha, perfil, rota):
    login = client.post("/api/admin/login", json={"password": senha})
    assert login.status_code == 200, login.text
    llm.limpar()

    r = _chamar(client, rota, _auth(login.json()["token"]))

    assert r.status_code == 403, f"{perfil} com token administrativo em {rota}: veio {r.status_code}"
    assert _linhas_chat() == []
    assert llm.chamadas == []


# --- T19 - T21 : dashboard de alunos ---------------------------------------------------

def _staff_token(client, perfil="support"):
    email = f"{perfil}.dash@gt.test"
    if not Database.get_user_by_email(email):
        _conta_funcionario(email, perfil)
    return _login(client, email)


def _dashboard(client, token):
    r = client.get(ROTA_DASHBOARD, headers=_auth(token))
    assert r.status_code == 200, f"GET {ROTA_DASHBOARD}: HTTP {r.status_code} {r.text[:200]}"
    return r.json(), r


def _item_do_aluno(corpo, user_id):
    itens = [s for s in corpo["students"] if s["id"] == user_id]
    assert len(itens) == 1, f"aluno {user_id} deveria aparecer uma vez no dashboard"
    return itens[0]


def test_t19_dashboard_traz_contagem_e_data_da_ultima_conversa_por_aluno(client):
    a, token_a = _aluno_logado(client, "t19.a@e5.test", nome="Aluno A")
    b, token_b = _aluno_logado(client, "t19.b@e5.test", nome="Aluno B")
    c = _conta_aluno("t19.c@e5.test", "Aluno C sem conversa")
    _enviar_ok(client, token_a)
    _enviar_ok(client, token_a)
    _enviar_ok(client, token_b)

    corpo, _ = _dashboard(client, _staff_token(client))

    item_a, item_b, item_c = (_item_do_aluno(corpo, u) for u in (a, b, c))
    for item in (item_a, item_b, item_c):
        assert "chat_messages" in item, f"campo chat_messages ausente no item {item}"
        assert "last_chat_at" in item, f"campo last_chat_at ausente no item {item}"
        assert isinstance(item["chat_messages"], int) and not isinstance(item["chat_messages"], bool)
    # "Contagem de mensagens": 1 por mensagem do aluno ou 1 por linha gravada (2 por troca).
    # O contrato (D35.5) nao fixa qual; o teste aceita as duas e exige consistencia entre os alunos.
    assert item_a["chat_messages"] in (2, 4)
    assert item_b["chat_messages"] in (1, 2)
    assert item_a["chat_messages"] == 2 * item_b["chat_messages"]
    for item in (item_a, item_b):
        assert isinstance(item["last_chat_at"], str) and item["last_chat_at"]
    ultima = _consultar("SELECT MAX(created_at) AS ultima FROM chat_messages WHERE user_id = ?", (a,))[0]["ultima"]
    assert item_a["last_chat_at"][:10] == str(ultima)[:10]
    # Compatibilidade: quem nunca conversou.
    assert item_c["chat_messages"] == 0
    assert item_c["last_chat_at"] is None
    # Campos que ja existiam continuam.
    for campo in ("id", "email", "name", "total_enrollments", "active_enrollments"):
        assert campo in item_a, f"campo existente '{campo}' sumiu do item"


def test_t19b_dashboard_aluno_que_nunca_conversou_tem_zero_e_null(client):
    c = _conta_aluno("t19b@e5.test", "Aluno sem conversa")

    corpo, _ = _dashboard(client, _staff_token(client))

    item = _item_do_aluno(corpo, c)
    assert "chat_messages" in item, f"campo chat_messages ausente no item {item}"
    assert "last_chat_at" in item, f"campo last_chat_at ausente no item {item}"
    assert item["chat_messages"] == 0
    assert item["last_chat_at"] is None


def test_t20_dashboard_nao_expoe_o_conteudo_das_conversas(client, llm):
    a, token_a = _aluno_logado(client, "t20@e5.test", nome="Aluno Vinte")
    texto, resposta, _ = _enviar_ok(client, token_a)
    token_staff = _staff_token(client, "admin")

    corpo, r = _dashboard(client, token_staff)

    assert texto not in r.text, "o conteudo da mensagem do aluno apareceu no dashboard"
    assert resposta not in r.text, "a resposta do bot apareceu no dashboard"
    item = _item_do_aluno(corpo, a)
    assert "messages" not in item and "content" not in item and "history" not in item
    metricas = corpo["metrics"]
    for chave in ("total_students", "active_students", "total_chat_sessions"):
        assert chave in metricas, f"metrics.{chave} sumiu"
    assert isinstance(metricas["total_chat_sessions"], int)
    assert metricas["total_chat_sessions"] == len(client.app.state.manager_agent.sessions), \
        "metrics.total_chat_sessions deve seguir contando as sessoes do ManagerAgent, como hoje"


@pytest.mark.parametrize("perfil", PERFIS_FUNCIONARIO)
def test_t21_rbac_do_dashboard_continua_liberando_os_tres_perfis(client, perfil):
    a, token_a = _aluno_logado(client, f"t21.{perfil}@e5.test", nome="Aluno Vinte e Um")
    _enviar_ok(client, token_a)

    corpo, _ = _dashboard(client, _staff_token(client, perfil))

    assert corpo["status"] == "success"
    assert _item_do_aluno(corpo, a)["chat_messages"] >= 1


def test_t21b_sem_token_o_dashboard_continua_401(client):
    assert client.get(ROTA_DASHBOARD).status_code == 401


# --- T22 : regressao do chat anonimo ---------------------------------------------------

def test_t22_chat_anonimo_segue_funcionando_sem_token_e_sem_gravar_em_chat_messages(client, llm):
    r = client.post(ROTA_CHAT_ANONIMO, json={"message": _texto_usuario(), "session_id": "visitante-e5"})

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "success"
    assert corpo["session_id"] == "visitante-e5"
    assert isinstance(corpo["message"], str) and corpo["message"].startswith("RESPOSTA-DUBLE-")
    assert llm.chamadas, "o duble deveria ter respondido ao chat anonimo"
    assert _linhas_chat() == [], "o chat anonimo nao grava em chat_messages"
