"""U5 - Pedido de cancelamento em 7 dias, CDC art. 49 (D82, modo autonomo D69).

Escritos ANTES da implementacao. Contrato (D82):
  - POST /api/student/enrollments/{id}/cancel-request (so aluno; dono pelo JWT; alheia ou inexistente -> o mesmo 404
    da E3) {reason?} (ate 500 caracteres, opcional). Condicoes, NESTA ORDEM:
      1. matricula nao `active` -> 409 `Só é possível pedir o cancelamento de uma matrícula ativa.`
      2. ja existe pedido `open` -> 409 `Já existe uma solicitação de cancelamento em análise para esta matrícula.`
      3. ultimo pagamento aprovado com valor 0 ou forma `manual` -> 409
         `Esta matrícula não tem pagamento a reembolsar. Fale com o suporte.`
      4. aprovado ha mais de 7 dias (payments.updated_at, ou created_at sem ele) -> 409
         `O prazo de 7 dias para cancelamento terminou. Fale com o suporte.`
    Senao cria pedido `open` (tabela `cancellation_requests`) e grava `enrollment.cancel_request`.
    Pedido recusado antes nao impede um novo dentro do prazo.
  - Itens de /api/student/enrollments: `cancellation` (null ou {status, requested_at, decided_at, decision_reason}) e
    `can_request_cancellation` (bool, mesmas regras).
  - Financeiro e Gestao: GET /api/admin/cancellation-requests?status= (padrao `open`) com {id, enrollment_id,
    payment_id, student_name, student_email, course_id, course_name, amount, requested_at, reason, status};
    Suporte e aluno 403. POST .../{id}/approve executa o reembolso da E9 (mesma regra e trilha) e marca `approved`;
    POST .../{id}/reject {reason} (5 a 300) marca `rejected`. Nao `open` -> 409 `Esta solicitação já foi decidida.`;
    inexistente -> 404 `Solicitação não encontrada.` Reembolso direto pela rota da E9 marca como `approved` o pedido
    `open` da matricula. Eventos `cancellation.approve` / `cancellation.reject`.

Escolhas conservadoras do agente-testes (o contrato nao fixa; registradas no relatorio):
  - Sucesso do pedido: 200 ou 201; aprovar/recusar: 200. Corpo de sucesso nao fixado (o teste confere pelas rotas de
    leitura e pelo banco).
  - Envelope da lista do admin nao fixado: aceita lista pura ou objeto com UMA lista (padrao {"status", "<itens>"}).
  - `cancellation` mostra o pedido MAIS RECENTE da matricula (depois de um recusado e um novo, aparece o novo `open`).
  - Motivo da recusa e aparado antes de medir (precedente da D81): so espacos -> 422. Ausente -> 422.
  - Validacao (motivo do aluno > 500, motivo da recusa fora de 5..300): 422 sem fixar texto, e nada muda.
  - Datas no banco no formato de CURRENT_TIMESTAMP (UTC, 'YYYY-MM-DD HH:MM:SS'), relativas a agora (D81).
  - O evento `enrollment.cancel_request` tem user_id do aluno; `cancellation.approve/reject` tem user_id de quem decidiu.
  - Concorrencia: alem de "aprovar duas vezes seguidas", aprovacoes simultaneas (threads, como a E9 R8) geram um 200,
    os demais 409 com o texto, um reembolso e um evento de cada.

Grupos
  I  IDOR: alheia = inexistente (404 igual); user_id no corpo/query ignorado                        [red]
  O  ordem e textos exatos dos 409                                                                   [red]
  P  prazo de 7 dias a partir da aprovacao (6d23h pode; 7d1h nao; updated_at x created_at)             [red]
  C  criacao: open, evento, duplicado 409, recusado permite novo, motivo do aluno (<= 500)            [red]
  L  itens do aluno: cancellation e can_request_cancellation em todos os status                     [red]
  A  RBAC: lista Financeiro/Gestao (JWT e legado), filtro status; Suporte/aluno 403; 401             [red]
  D  decisoes: aprovar reembolsa (E9) e esconde materiais; recusar com motivo; 409; 404              [red]
  R  reembolso direto pela rota da E9 resolve o pedido open                                          [red]
  X  concorrencia: duas aprovacoes seguidas e simultaneas = um reembolso                             [red]
  K  compatibilidade: dado antigo (sem pedido, updated_at NULL), init_db idempotente                 [red]
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
CURSO = "curso_u5"
OUTRO_CURSO = "curso_u5_outro"
NOME_CURSO = "Curso U5"
PRECO = 249.9
URL_MATERIAL = "https://materiais.test/u5/apostila.pdf"
SENHA = "senha-u5-forte-2026"
MOTIVO_ALUNO = "Comprei por engano, quero desistir"
MOTIVO_RECUSA = "Aluno ja concluiu o curso inteiro"

ROTA_LISTA = "/api/admin/cancellation-requests"
ERR_MATRICULA = "Matrícula não encontrada."
ERR_NAO_ATIVA = "Só é possível pedir o cancelamento de uma matrícula ativa."
ERR_JA_ABERTO = "Já existe uma solicitação de cancelamento em análise para esta matrícula."
ERR_SEM_PAGAMENTO = "Esta matrícula não tem pagamento a reembolsar. Fale com o suporte."
ERR_PRAZO = "O prazo de 7 dias para cancelamento terminou. Fale com o suporte."
ERR_DECIDIDA = "Esta solicitação já foi decidida."
ERR_SOLICITACAO = "Solicitação não encontrada."
EV_PEDIDO = "enrollment.cancel_request"
EV_APROVA = "cancellation.approve"
EV_RECUSA = "cancellation.reject"
EV_REEMBOLSO = "payment.refund"
CAMPOS_CANCELLATION = {"status", "requested_at", "decided_at", "decision_reason"}
CAMPOS_LISTA = {"id", "enrollment_id", "payment_id", "student_name", "student_email", "course_id", "course_name",
                "amount", "requested_at", "reason", "status"}


# =========================================================================================
# Ambiente, cursos e cliente
# =========================================================================================

@pytest.fixture(autouse=True)
def ambiente_u5(monkeypatch, tmp_path):
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


def _gravar_curso(diretorio, course_id, nome, preco, materiais=None):
    dados = {"id": course_id, "name": nome, "description": f"{nome} da U5", "price": preco,
             "materials": materiais or []}
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _gravar_curso(diretorio, CURSO, NOME_CURSO, PRECO, [{"title": "Apostila U5", "url": URL_MATERIAL, "type": "pdf"}])
    _gravar_curso(diretorio, OUTRO_CURSO, "Outro Curso U5", 99.0)
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    return TestClient(fastapi_app, raise_server_exceptions=False)


# =========================================================================================
# Helpers
# =========================================================================================

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


def _auth(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _conta(email, nome, perfil="student"):
    user_id = Database.add_user(email, nome, get_password_hash(SENHA), role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        gestao=_conta("gestao.u5@teste.com", "Gestora U5", "admin"),
        fin=_conta("fin.u5@teste.com", "Financeira U5", "financial"),
        sup=_conta("sup.u5@teste.com", "Suporte U5", "support"),
        ana=_conta("ana.u5@teste.com", "Ana Aluna U5"),
        bia=_conta("bia.u5@teste.com", "Bia Aluna U5"),
    )


def _forjado(role="student", user_id=1):
    return jose_jwt.encode({"user_id": user_id, "email": "x@u5.test", "role": role},
                           "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")


def _ts(delta):
    """Instante (agora - delta) no formato de CURRENT_TIMESTAMP (UTC)."""
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%d %H:%M:%S")


def _compra(aluno, curso=CURSO, valor=PRECO, metodo="mercado_pago", aprovado_ha=timedelta(days=1),
            criado_ha=None, sem_updated_at=False, matricula="active", pagamento="approved"):
    """Matricula + pagamento no estado pedido, com datas relativas a agora (D81)."""
    criado_ha = criado_ha if criado_ha is not None else aprovado_ha
    eid = Database.create_enrollment(aluno.id, curso, f"{curso}:u5:{uuid.uuid4().hex}")
    pid = Database.record_payment(eid, valor, metodo)
    _executar(
        "UPDATE payments SET status = ?, transaction_id = ?, created_at = ?, updated_at = ? WHERE id = ?",
        (pagamento, f"mp-u5-{uuid.uuid4().hex[:12]}", _ts(criado_ha),
         None if sem_updated_at else _ts(aprovado_ha), pid),
    )
    _executar("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?", (matricula, _ts(criado_ha), eid))
    return SimpleNamespace(eid=eid, pid=pid, aluno=aluno, valor=valor)


def _pedir(client, aluno_token, eid, corpo=None, **kw):
    return client.post(f"/api/student/enrollments/{eid}/cancel-request",
                       json={} if corpo is None else corpo, headers=_auth(aluno_token), **kw)


def _pedir_ok(client, c, motivo=MOTIVO_ALUNO):
    r = _pedir(client, c.aluno.token, c.eid, {"reason": motivo})
    assert r.status_code in (200, 201), r.text
    return r


def _itens(client, token):
    r = client.get("/api/student/enrollments", headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["enrollments"]


def _item(client, token, eid):
    achados = [i for i in _itens(client, token) if i["id"] == eid]
    assert len(achados) == 1, f"matricula {eid} nao esta na lista do aluno"
    return achados[0]


def _lista(r):
    assert r.status_code == 200, r.text
    corpo = r.json()
    if isinstance(corpo, list):
        return corpo
    listas = [v for v in corpo.values() if isinstance(v, list)]
    assert len(listas) == 1, f"esperada uma lista na resposta: {corpo}"
    return listas[0]


def _listar(client, token, status=None):
    params = {"status": status} if status is not None else None
    return client.get(ROTA_LISTA, params=params, headers=_auth(token))


def _pedido_de(client, token, eid, status="open"):
    achados = [p for p in _lista(_listar(client, token, status)) if p["enrollment_id"] == eid]
    assert len(achados) == 1, f"esperado 1 pedido {status} da matricula {eid}, veio {achados}"
    return achados[0]


def _aprovar(client, token, pedido_id):
    return client.post(f"{ROTA_LISTA}/{pedido_id}/approve", headers=_auth(token))


def _recusar(client, token, pedido_id, motivo=MOTIVO_RECUSA, corpo=None):
    return client.post(f"{ROTA_LISTA}/{pedido_id}/reject",
                       json={"reason": motivo} if corpo is None else corpo, headers=_auth(token))


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _pag(c):
    return _sql("SELECT * FROM payments WHERE id = ?", (c.pid,))[0]


def _mat(c):
    return _sql("SELECT status FROM enrollments WHERE id = ?", (c.eid,))[0]["status"]


def _pedidos_no_banco():
    return _sql("SELECT * FROM cancellation_requests ORDER BY id")


def _detalhe(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text


def _sem_aspas(valor):
    """Valor de `changes` como a E9 aceita: cru ou serializado em JSON."""
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return valor
    return valor


def _conflito(r, texto):
    assert r.status_code == 409, f"esperado 409, veio {r.status_code} {r.text}"
    assert r.json() == {"detail": texto}, r.text


# =========================================================================================
# Grupo I - IDOR
# =========================================================================================

def test_i1_matricula_alheia_responde_o_mesmo_404_de_inexistente(client, contas):
    da_bia = _compra(contas.bia)
    alheia = _pedir(client, contas.ana.token, da_bia.eid, {"reason": MOTIVO_ALUNO})
    inexistente = _pedir(client, contas.ana.token, 987654, {"reason": MOTIVO_ALUNO})
    assert alheia.status_code == inexistente.status_code == 404, (alheia.text, inexistente.text)
    assert alheia.json() == inexistente.json() == {"detail": ERR_MATRICULA}
    assert _eventos(EV_PEDIDO) == []
    assert _item(client, contas.bia.token, da_bia.eid)["cancellation"] is None


def test_i2_user_id_no_corpo_e_na_query_e_ignorado(client, contas):
    da_ana = _compra(contas.ana)
    da_bia = _compra(contas.bia)
    # Ana tenta agir em nome da Bia na matricula da Bia: continua 404.
    r = _pedir(client, contas.ana.token, da_bia.eid, {"reason": MOTIVO_ALUNO, "user_id": contas.bia.id},
               params={"user_id": contas.bia.id})
    assert r.status_code == 404 and r.json() == {"detail": ERR_MATRICULA}, r.text
    # Ana, na propria matricula, com user_id da Bia no corpo: o pedido e da Ana.
    r = _pedir(client, contas.ana.token, da_ana.eid, {"reason": MOTIVO_ALUNO, "user_id": contas.bia.id},
               params={"user_id": contas.bia.id})
    assert r.status_code in (200, 201), r.text
    assert _item(client, contas.ana.token, da_ana.eid)["cancellation"]["status"] == "open"
    assert _item(client, contas.bia.token, da_bia.eid)["cancellation"] is None
    pedido = _pedido_de(client, contas.fin.token, da_ana.eid)
    assert pedido["student_email"] == contas.ana.email
    eventos = _eventos(EV_PEDIDO)
    assert len(eventos) == 1 and eventos[0]["user_id"] == contas.ana.id, eventos


def test_i3_aluno_nao_le_pedido_de_outro_na_propria_lista(client, contas):
    da_ana = _compra(contas.ana)
    _pedir_ok(client, da_ana)
    assert all(i["cancellation"] is None for i in _itens(client, contas.bia.token))


# =========================================================================================
# Grupo O - ordem e textos exatos dos 409
# =========================================================================================

@pytest.mark.parametrize("matricula,pagamento", [
    ("pending", "pending"), ("cancelled", "cancelled"), ("refunded", "refunded"),
])
def test_o1_matricula_nao_ativa_responde_409(client, contas, matricula, pagamento):
    c = _compra(contas.ana, matricula=matricula, pagamento=pagamento, aprovado_ha=timedelta(hours=2))
    _conflito(_pedir(client, contas.ana.token, c.eid, {"reason": MOTIVO_ALUNO}), ERR_NAO_ATIVA)
    assert _eventos(EV_PEDIDO) == []


def test_o2_nao_ativa_vem_antes_de_pedido_aberto(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    _executar("UPDATE enrollments SET status = 'cancelled' WHERE id = ?", (c.eid,))
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_NAO_ATIVA)


def test_o3_pedido_aberto_vem_antes_de_pagamento_manual_ou_zero(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    _executar("UPDATE payments SET payment_method = 'manual', amount = 0 WHERE id = ?", (c.pid,))
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_JA_ABERTO)


def test_o4_pedido_aberto_vem_antes_do_prazo(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    _executar("UPDATE payments SET updated_at = ?, created_at = ? WHERE id = ?",
              (_ts(timedelta(days=20)), _ts(timedelta(days=20)), c.pid))
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_JA_ABERTO)


@pytest.mark.parametrize("metodo,valor", [("manual", 150.0), ("manual", 0), ("mercado_pago", 0)])
def test_o5_pagamento_manual_ou_zero_responde_409(client, contas, metodo, valor):
    c = _compra(contas.ana, metodo=metodo, valor=valor, aprovado_ha=timedelta(hours=1))
    _conflito(_pedir(client, contas.ana.token, c.eid, {"reason": MOTIVO_ALUNO}), ERR_SEM_PAGAMENTO)
    assert _eventos(EV_PEDIDO) == []


def test_o6_pagamento_manual_vem_antes_do_prazo(client, contas):
    c = _compra(contas.ana, metodo="manual", valor=150.0, aprovado_ha=timedelta(days=30))
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_SEM_PAGAMENTO)


def test_o7_prazo_vencido_responde_409(client, contas):
    c = _compra(contas.ana, aprovado_ha=timedelta(days=10))
    _conflito(_pedir(client, contas.ana.token, c.eid, {"reason": MOTIVO_ALUNO}), ERR_PRAZO)
    assert _eventos(EV_PEDIDO) == []
    assert _sql("SELECT COUNT(*) AS n FROM cancellation_requests")[0]["n"] == 0


# =========================================================================================
# Grupo P - prazo de 7 dias contado da aprovacao
# =========================================================================================

def test_p1_seis_dias_e_23_horas_depois_da_aprovacao_pode(client, contas):
    c = _compra(contas.ana, aprovado_ha=timedelta(days=6, hours=23))
    assert _item(client, contas.ana.token, c.eid)["can_request_cancellation"] is True
    _pedir_ok(client, c)


def test_p2_sete_dias_e_1_hora_depois_da_aprovacao_nao_pode(client, contas):
    c = _compra(contas.ana, aprovado_ha=timedelta(days=7, hours=1))
    assert _item(client, contas.ana.token, c.eid)["can_request_cancellation"] is False
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_PRAZO)


def test_p3_prazo_conta_da_aprovacao_e_nao_da_criacao(client, contas):
    # Criado ha 30 dias (pagamento ficou pendente), aprovado ha 1 dia: dentro do prazo.
    c = _compra(contas.ana, criado_ha=timedelta(days=30), aprovado_ha=timedelta(days=1))
    assert _item(client, contas.ana.token, c.eid)["can_request_cancellation"] is True
    _pedir_ok(client, c)


def test_p4_sem_updated_at_usa_created_at_dentro_do_prazo(client, contas):
    c = _compra(contas.ana, criado_ha=timedelta(days=2), sem_updated_at=True)
    assert _pag(c)["updated_at"] is None
    assert _item(client, contas.ana.token, c.eid)["can_request_cancellation"] is True
    _pedir_ok(client, c)


def test_p5_sem_updated_at_usa_created_at_fora_do_prazo(client, contas):
    c = _compra(contas.ana, criado_ha=timedelta(days=8), sem_updated_at=True)
    assert _item(client, contas.ana.token, c.eid)["can_request_cancellation"] is False
    _conflito(_pedir(client, contas.ana.token, c.eid), ERR_PRAZO)


# =========================================================================================
# Grupo C - criacao do pedido
# =========================================================================================

def test_c1_pedido_criado_open_com_evento_e_tabela(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    linhas = _pedidos_no_banco()
    assert len(linhas) == 1 and linhas[0]["status"] == "open", linhas
    item = _item(client, contas.ana.token, c.eid)
    canc = item["cancellation"]
    assert CAMPOS_CANCELLATION <= set(canc), canc
    assert canc["status"] == "open" and canc["requested_at"]
    assert canc["decided_at"] is None and canc["decision_reason"] is None
    assert item["can_request_cancellation"] is False
    eventos = _eventos(EV_PEDIDO)
    assert len(eventos) == 1, eventos
    assert eventos[0]["user_id"] == contas.ana.id
    # Pedir nao reembolsa nada: matricula e pagamento seguem iguais, materiais continuam.
    assert _pag(c)["status"] == "approved" and _mat(c) == "active"
    assert [m["url"] for m in item["materials"]] == [URL_MATERIAL]


def test_c2_pedido_duplicado_responde_409_sem_segundo_registro(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    _conflito(_pedir(client, contas.ana.token, c.eid, {"reason": "de novo"}), ERR_JA_ABERTO)
    assert len(_pedidos_no_banco()) == 1
    assert len(_eventos(EV_PEDIDO)) == 1


def test_c3_recusado_antes_permite_novo_pedido_no_prazo(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido = _pedido_de(client, contas.fin.token, c.eid)
    assert _recusar(client, contas.fin.token, pedido["id"]).status_code == 200
    item = _item(client, contas.ana.token, c.eid)
    assert item["cancellation"]["status"] == "rejected"
    assert item["can_request_cancellation"] is True
    _pedir_ok(client, c, "Pensei melhor e quero mesmo cancelar")
    item = _item(client, contas.ana.token, c.eid)
    assert item["cancellation"]["status"] == "open" and item["can_request_cancellation"] is False
    assert len(_eventos(EV_PEDIDO)) == 2


def test_c4_motivo_opcional_e_gravado(client, contas):
    sem = _compra(contas.ana)
    com = _compra(contas.ana, curso=OUTRO_CURSO, valor=99.0)
    r = _pedir(client, contas.ana.token, sem.eid)
    assert r.status_code in (200, 201), r.text
    _pedir_ok(client, com, MOTIVO_ALUNO)
    assert _pedido_de(client, contas.fin.token, com.eid)["reason"] == MOTIVO_ALUNO


def test_c5_motivo_do_aluno_ate_500_caracteres(client, contas):
    c = _compra(contas.ana)
    r = _pedir(client, contas.ana.token, c.eid, {"reason": "x" * 501})
    assert r.status_code == 422, r.text
    assert _pedidos_no_banco() == [] and _eventos(EV_PEDIDO) == []
    r = _pedir(client, contas.ana.token, c.eid, {"reason": "y" * 500})
    assert r.status_code in (200, 201), r.text


def test_c6_rbac_do_pedido_do_aluno(client, contas):
    c = _compra(contas.ana)
    url = f"/api/student/enrollments/{c.eid}/cancel-request"
    assert client.post(url, json={}).status_code == 401
    assert client.post(url, json={}, headers=_auth(_forjado(user_id=contas.ana.id))).status_code == 401
    assert client.post(url, json={}, headers=_auth("lixo")).status_code == 401
    for token in (contas.gestao.token, contas.fin.token, contas.sup.token,
                  create_admin_token(Role("admin"))):
        r = client.post(url, json={}, headers=_auth(token))
        assert r.status_code == 403, r.text
    assert _pedidos_no_banco() == [] and _eventos(EV_PEDIDO) == []


# =========================================================================================
# Grupo L - itens do aluno
# =========================================================================================

def test_l1_itens_trazem_cancellation_e_can_request_em_todos_os_status(client, contas):
    ok = _compra(contas.ana, aprovado_ha=timedelta(hours=3))
    pendente = _compra(contas.ana, curso=OUTRO_CURSO, valor=99.0, matricula="pending", pagamento="pending",
                       aprovado_ha=timedelta(hours=1))
    cancelada = _compra(contas.ana, matricula="cancelled", pagamento="cancelled", aprovado_ha=timedelta(hours=1))
    reembolsada = _compra(contas.ana, matricula="refunded", pagamento="refunded", aprovado_ha=timedelta(hours=1))
    manual = _compra(contas.ana, metodo="manual", valor=0, aprovado_ha=timedelta(hours=1))
    antiga = _compra(contas.ana, aprovado_ha=timedelta(days=15))
    esperado = {ok.eid: True, pendente.eid: False, cancelada.eid: False, reembolsada.eid: False,
                manual.eid: False, antiga.eid: False}
    itens = {i["id"]: i for i in _itens(client, contas.ana.token)}
    for eid, pode in esperado.items():
        assert "cancellation" in itens[eid] and itens[eid]["cancellation"] is None, itens[eid]
        assert itens[eid]["can_request_cancellation"] is pode, (eid, itens[eid])


# =========================================================================================
# Grupo A - lista e RBAC do admin
# =========================================================================================

def test_a1_financeiro_e_gestao_listam_os_pedidos_abertos_com_os_campos(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    for token in (contas.fin.token, contas.gestao.token, create_admin_token(Role("financial")),
                  create_admin_token(Role("admin"))):
        itens = _lista(_listar(client, token))
        assert len(itens) == 1, itens
        p = itens[0]
        assert CAMPOS_LISTA <= set(p), p
        assert p["enrollment_id"] == c.eid and p["payment_id"] == c.pid
        assert p["student_name"] == contas.ana.name and p["student_email"] == contas.ana.email
        assert p["course_id"] == CURSO and p["course_name"] == NOME_CURSO
        assert abs(float(p["amount"]) - PRECO) < 0.005
        assert p["requested_at"] and p["reason"] == MOTIVO_ALUNO and p["status"] == "open"


def test_a2_filtro_status_padrao_open(client, contas):
    aberto = _compra(contas.ana)
    recusado = _compra(contas.bia)
    aprovado = _compra(contas.ana, curso=OUTRO_CURSO, valor=99.0)
    for c in (aberto, recusado, aprovado):
        _pedir_ok(client, c)
    assert _recusar(client, contas.fin.token, _pedido_de(client, contas.fin.token, recusado.eid)["id"]).status_code == 200
    assert _aprovar(client, contas.fin.token, _pedido_de(client, contas.fin.token, aprovado.eid)["id"]).status_code == 200

    def por_status(status):
        return sorted((p["enrollment_id"], p["status"]) for p in _lista(_listar(client, contas.gestao.token, status)))

    assert por_status(None) == [(aberto.eid, "open")]
    assert por_status("open") == [(aberto.eid, "open")]
    assert por_status("rejected") == [(recusado.eid, "rejected")]
    assert por_status("approved") == [(aprovado.eid, "approved")]


def test_a3_suporte_e_aluno_recebem_403_e_sem_token_401(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    proibidos = {
        "suporte_jwt": contas.sup.token,
        "suporte_legado": create_admin_token(Role("support")),
        "aluno_dono": contas.ana.token,
    }
    for rotulo, token in proibidos.items():
        assert _listar(client, token).status_code == 403, rotulo
        assert _aprovar(client, token, pedido_id).status_code == 403, rotulo
        assert _recusar(client, token, pedido_id).status_code == 403, rotulo
    for token in (None, _forjado("admin"), "lixo"):
        assert _listar(client, token).status_code == 401
        assert _aprovar(client, token, pedido_id).status_code == 401
        assert _recusar(client, token, pedido_id).status_code == 401
    assert _pedido_de(client, contas.fin.token, c.eid)["status"] == "open"
    assert _pag(c)["status"] == "approved" and _mat(c) == "active"
    assert _eventos(EV_REEMBOLSO) == [] and _eventos(EV_APROVA) == [] and _eventos(EV_RECUSA) == []


# =========================================================================================
# Grupo D - decisoes
# =========================================================================================

@pytest.mark.parametrize("quem", ["fin", "gestao"])
def test_d1_aprovar_executa_o_reembolso_da_e9_e_marca_approved(client, contas, quem):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    assert URL_MATERIAL in client.get("/api/student/enrollments", headers=_auth(contas.ana.token)).text
    decisor = getattr(contas, quem)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    r = _aprovar(client, decisor.token, pedido_id)
    assert r.status_code == 200, r.text
    assert _pag(c)["status"] == "refunded" and _mat(c) == "refunded"
    # Trilha da E9: um payment.refund do pagamento, com as mudancas de status, feito por quem decidiu.
    reembolsos = _eventos(EV_REEMBOLSO)
    assert len(reembolsos) == 1, reembolsos
    ev = reembolsos[0]
    assert ev["entity_type"] == "payment" and str(ev["entity_id"]) == str(c.pid)
    assert ev["user_id"] == decisor.id
    mudancas = {m["field"]: m for m in json.loads(ev["changes"] or "[]")}
    for campo, antes, depois in (("payment.status", "approved", "refunded"),
                                 ("enrollment.status", "active", "refunded")):
        assert campo in mudancas, mudancas
        assert _sem_aspas(mudancas[campo]["before"]) == antes and _sem_aspas(mudancas[campo]["after"]) == depois, \
            mudancas[campo]
    aprovacoes = _eventos(EV_APROVA)
    assert len(aprovacoes) == 1 and aprovacoes[0]["user_id"] == decisor.id, aprovacoes
    # Pedido marcado approved; aluno ve a decisao e perde os materiais.
    item = _item(client, contas.ana.token, c.eid)
    assert item["status"] == "refunded"
    assert item["cancellation"]["status"] == "approved" and item["cancellation"]["decided_at"]
    assert item["can_request_cancellation"] is False
    assert "materials" not in item or not item["materials"]
    for rota in ("/api/student/enrollments", f"/api/student/enrollments/{c.eid}"):
        assert URL_MATERIAL not in client.get(rota, headers=_auth(contas.ana.token)).text, rota
    assert _pedido_de(client, contas.fin.token, c.eid, "approved")["status"] == "approved"


def test_d2_recusar_com_motivo_marca_rejected_sem_reembolsar(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    r = _recusar(client, contas.fin.token, pedido_id, MOTIVO_RECUSA)
    assert r.status_code == 200, r.text
    assert _pag(c)["status"] == "approved" and _mat(c) == "active"
    assert _eventos(EV_REEMBOLSO) == [] and _eventos(EV_APROVA) == []
    recusas = _eventos(EV_RECUSA)
    assert len(recusas) == 1 and recusas[0]["user_id"] == contas.fin.id, recusas
    canc = _item(client, contas.ana.token, c.eid)["cancellation"]
    assert canc["status"] == "rejected" and canc["decision_reason"] == MOTIVO_RECUSA and canc["decided_at"]
    assert _pedido_de(client, contas.gestao.token, c.eid, "rejected")["status"] == "rejected"
    assert URL_MATERIAL in client.get("/api/student/enrollments", headers=_auth(contas.ana.token)).text


@pytest.mark.parametrize("corpo", [
    {"reason": "abcd"}, {"reason": "z" * 301}, {"reason": "        "}, {"reason": "  ab  "}, {}, {"reason": None},
], ids=["4", "301", "so_espacos", "2_aparado", "ausente", "nulo"])
def test_d3_motivo_da_recusa_fora_de_5_a_300_responde_422(client, contas, corpo):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    r = _recusar(client, contas.fin.token, pedido_id, corpo=corpo)
    assert r.status_code == 422, r.text
    assert _pedido_de(client, contas.fin.token, c.eid)["status"] == "open"
    assert _eventos(EV_RECUSA) == []


@pytest.mark.parametrize("motivo", ["abcde", "w" * 300], ids=["5", "300"])
def test_d4_motivo_da_recusa_nos_limites_e_aceito(client, contas, motivo):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    assert _recusar(client, contas.fin.token, pedido_id, motivo).status_code == 200
    assert _item(client, contas.ana.token, c.eid)["cancellation"]["decision_reason"] == motivo


@pytest.mark.parametrize("primeira,segunda", [
    ("approve", "approve"), ("approve", "reject"), ("reject", "approve"), ("reject", "reject"),
])
def test_d5_decidir_duas_vezes_responde_409(client, contas, primeira, segunda):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    acao = {"approve": lambda: _aprovar(client, contas.fin.token, pedido_id),
            "reject": lambda: _recusar(client, contas.fin.token, pedido_id)}
    assert acao[primeira]().status_code == 200
    antes = (_pag(c)["status"], _mat(c), len(_eventos(EV_REEMBOLSO)), len(_eventos(EV_APROVA)),
             len(_eventos(EV_RECUSA)))
    _conflito(acao[segunda](), ERR_DECIDIDA)
    depois = (_pag(c)["status"], _mat(c), len(_eventos(EV_REEMBOLSO)), len(_eventos(EV_APROVA)),
              len(_eventos(EV_RECUSA)))
    assert antes == depois


def test_d6_solicitacao_inexistente_responde_404(client, contas):
    for r in (_aprovar(client, contas.fin.token, 987654), _recusar(client, contas.fin.token, 987654)):
        assert r.status_code == 404, r.text
        assert r.json() == {"detail": ERR_SOLICITACAO}
    assert _eventos(EV_APROVA) == [] and _eventos(EV_RECUSA) == []


# =========================================================================================
# Grupo R - reembolso direto pela rota da E9
# =========================================================================================

def test_r1_reembolso_direto_marca_o_pedido_open_como_approved(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    r = client.post(f"/api/payments/refund/{c.pid}", headers=_auth(contas.fin.token))
    assert r.status_code == 200, r.text
    assert _pag(c)["status"] == "refunded" and _mat(c) == "refunded"
    assert _lista(_listar(client, contas.fin.token)) == []
    assert _pedido_de(client, contas.fin.token, c.eid, "approved")["id"] == pedido_id
    assert _item(client, contas.ana.token, c.eid)["cancellation"]["status"] == "approved"
    assert len(_eventos(EV_REEMBOLSO)) == 1
    _conflito(_aprovar(client, contas.fin.token, pedido_id), ERR_DECIDIDA)
    assert len(_eventos(EV_REEMBOLSO)) == 1


def test_r2_reembolso_direto_nao_mexe_em_pedido_recusado(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    assert _recusar(client, contas.fin.token, pedido_id).status_code == 200
    assert client.post(f"/api/payments/refund/{c.pid}", headers=_auth(contas.fin.token)).status_code == 200
    assert _pedido_de(client, contas.fin.token, c.eid, "rejected")["id"] == pedido_id
    assert _lista(_listar(client, contas.fin.token, "approved")) == []


# =========================================================================================
# Grupo X - concorrencia
# =========================================================================================

def test_x1_aprovar_duas_vezes_seguidas_gera_um_reembolso_e_um_evento(client, contas):
    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    r1 = _aprovar(client, contas.fin.token, pedido_id)
    r2 = _aprovar(client, contas.gestao.token, pedido_id)
    assert r1.status_code == 200, r1.text
    _conflito(r2, ERR_DECIDIDA)
    assert len(_eventos(EV_REEMBOLSO)) == 1
    assert len(_eventos(EV_APROVA)) == 1
    assert _pag(c)["status"] == "refunded" and _mat(c) == "refunded"


def test_x2_aprovacoes_simultaneas_geram_um_reembolso_e_um_evento(client, contas):
    from app import app as fastapi_app

    c = _compra(contas.ana)
    _pedir_ok(client, c)
    pedido_id = _pedido_de(client, contas.fin.token, c.eid)["id"]
    n = 5
    barreira = threading.Barrier(n)
    respostas = [None] * n
    erros = []

    def alvo(i):
        try:
            cliente = TestClient(fastapi_app, raise_server_exceptions=False)
            barreira.wait(timeout=60)
            respostas[i] = _aprovar(cliente, contas.fin.token, pedido_id)
        except Exception as exc:  # noqa: BLE001
            erros.append(repr(exc))

    threads = [threading.Thread(target=alvo, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not erros, erros
    codigos = sorted(r.status_code for r in respostas)
    assert codigos == [200] + [409] * (n - 1), [(r.status_code, _detalhe(r)) for r in respostas]
    for r in respostas:
        if r.status_code == 409:
            assert r.json() == {"detail": ERR_DECIDIDA}
    assert len(_eventos(EV_REEMBOLSO)) == 1
    assert len(_eventos(EV_APROVA)) == 1
    assert _pag(c)["status"] == "refunded" and _mat(c) == "refunded"


# =========================================================================================
# Grupo K - compatibilidade
# =========================================================================================

def test_k1_init_db_repetido_e_dado_antigo_sem_pedido(client, contas):
    c = _compra(contas.ana, sem_updated_at=True, criado_ha=timedelta(days=1))
    Database.init_db()
    Database.init_db()
    tabelas = _sql("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'cancellation_requests'")
    assert len(tabelas) == 1
    item = _item(client, contas.ana.token, c.eid)
    assert item["cancellation"] is None and item["can_request_cancellation"] is True
    assert _lista(_listar(client, contas.fin.token)) == []
