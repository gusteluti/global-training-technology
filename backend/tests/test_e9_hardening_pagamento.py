"""E9 - Hardening de pagamento (D48). Escritos ANTES da implementacao.

Devem falhar agora (o red e o esperado): o webhook nao verifica assinatura, nao valida o id, nao confere valor
nem moeda, nao tem maquina de estados nem idempotencia (emite outro token a cada `approved`, reativa matricula
reembolsada, rebaixa matricula ativa); o CORS e `*` com credenciais; o checkout repassa o corpo de erro do
gateway; o reembolso aceita qualquer status e tem corrida.

O Mercado Pago e simulado como nos testes antigos (`patch("payments.routes.requests.get"/"post")`), por um falso
que CONTA as chamadas e devolve o pagamento pedido (status, valor, moeda, referencia). A entrega do link de
senha e verificada pela saida de desenvolvimento (PASSWORD_LINK_OUTBOX, um arquivo JSON por linha) e pela tabela
`password_setup_tokens`, sem mock de `send_password_setup_link`.

Grupos
  S   Assinatura valida passa e processa (S1-S6: ts antigo/ms, data.id na query ou no corpo, query preferida)
  A   Assinatura invalida: ausente, malformada, segredo errado, data.id/request-id/ts adulterados -> 401, ZERO
      chamadas ao gateway, nada alterado; segredo nao configurado -> 503 (A1-A10)
  T   Topico e id: topico diferente de payment ignorado; id nao numerico (../x, 1/../../y...) -> 400 sem gateway
  V   Conferencia de valor e moeda: divergencia -> rejected + payment.amount_mismatch; valor igual ativa
  U   Referencia desconhecida / sem pagamento local: ignorada, sem token nem e-mail
  M   Maquina de estados (refunded e charged_back terminais; approved nao rebaixa; livre entre os demais; no-op)
  E   Efeitos colaterais uma vez so (sequencia e 8 threads); transaction_id duplicado; indice unico parcial
  D   Auditoria payment.status_change (approved, refunded, charged_back) e nenhuma em webhook ignorado
  R   Reembolso: so approved; idempotente; 409; 404; 401; 403; concorrencia (um evento so)
  C   CORS: origem permitida recebe o ACAO exato (nunca `*`), estranha nao, sem credenciais, variavel de ambiente
  K   Checkout: erro do gateway -> 502 fixo sem corpo; token ausente -> 503; preco/amount do corpo ignorados
  I   Isolamento: pagamento de outro aluno nao e afetado por webhook com referencia de outro

Checklist: IDOR direto NAO SE APLICA (o webhook e do gateway e nao recebe id de usuario; o reembolso e de
funcionario; nenhum endpoint aceita id de usuario do cliente). O analogo coberto e o grupo I (webhook de uma
referencia nao altera pagamento/matricula/token de outro aluno) e R6 (o aluno dono do pagamento tambem recebe
403 no reembolso). Recurso pago so com matricula ativa: NAO SE APLICA (nenhuma URL de material); as garantias
de que so `approved` ativa a matricula estao em V (divergencia nao ativa) e M (refunded/terminal nao reativa).

Escolhas conservadoras (ver relatorio): `pending -> refunded` e `pending -> charged_back` por webhook NAO sao
testados (a D48 nao diz); a matricula apos `charged_back` NAO e conferida (o mapa fechado atual nao tem
charged_back); topico ausente NAO e testado; ids com digitos nao ASCII NAO sao testados; o corpo de sucesso do
webhook processado NAO e conferido (so status 200, o banco e, onde cabe, `status` diferente de ignored/rejected).
"""

import importlib.util
import json
import re
import sqlite3
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from apoio_mercado_pago import (
    SEGREDO_WEBHOOK, assinar, corpo_pagamento_mp, id_de_pagamento, post_webhook,
)
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROTA_WEBHOOK = "/api/payments/webhook"
DETAIL_ASSINATURA = "Assinatura inválida."
DETAIL_NAO_CONFIGURADO = "Webhook não configurado."
DETAIL_ID = "Identificador de pagamento inválido."
DETAIL_409 = "Só é possível reembolsar pagamentos aprovados."
DETAIL_CHECKOUT_502 = "Não foi possível iniciar o pagamento. Tente novamente."
DETAIL_CHECKOUT_503 = "Pagamento indisponível no momento."
CURSO = "curso_e9"
PRECO = 100.0
AUSENTE = object()  # campo omitido do pagamento devolvido pelo gateway


# =========================================================================================
# Gateway (Mercado Pago) falso, com contagem de chamadas
# =========================================================================================

class GatewayFalso:
    def __init__(self):
        self.pagamentos = {}
        self.get_chamadas = []   # (url, kwargs)
        self.post_chamadas = []  # (url, kwargs)
        self.post_resposta = None
        self.atraso_get = 0.0
        self._trava = threading.Lock()

    def definir(self, mp_id, status, referencia, valor, moeda="BRL"):
        corpo = corpo_pagamento_mp(status, referencia, valor, mp_id, moeda)
        if valor is AUSENTE:
            del corpo["transaction_amount"]
        if moeda is AUSENTE:
            del corpo["currency_id"]
        self.pagamentos[str(mp_id)] = corpo

    def get(self, url, *args, **kwargs):
        with self._trava:
            self.get_chamadas.append((url, kwargs))
        if self.atraso_get:
            time.sleep(self.atraso_get)
        corpo = self.pagamentos.get(str(url).rsplit("/", 1)[-1])
        resposta = MagicMock()
        if corpo is None:
            resposta.status_code = 404
            resposta.json.return_value = {"message": "not found"}
            resposta.text = '{"message": "not found"}'
        else:
            resposta.status_code = 200
            resposta.json.return_value = corpo
            resposta.text = json.dumps(corpo)
        return resposta

    def post(self, url, *args, **kwargs):
        with self._trava:
            self.post_chamadas.append((url, kwargs))
        if self.post_resposta is not None:
            return self.post_resposta
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": "pref-e9", "init_point": "https://mp.test/checkout"}
        resposta.text = '{"id": "pref-e9"}'
        return resposta

    def ids_consultados(self):
        return [url.rsplit("/", 1)[-1] for url, _ in self.get_chamadas]


# =========================================================================================
# Fixtures
# =========================================================================================

@pytest.fixture(autouse=True)
def ambiente_e9(monkeypatch, tmp_path):
    """Segredo do webhook, token do gateway e saida de desenvolvimento (outbox) isolados por teste."""
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", SEGREDO_WEBHOOK)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake")
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    return tmp_path / "outbox.jsonl"


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": "Curso E9", "description": "Curso para o hardening de pagamento", "price": PRECO,
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return diretorio


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    # Sem `with`: nao dispara o startup (agente de chat); as rotas de pagamento nao dependem dele.
    return TestClient(fastapi_app, raise_server_exceptions=False)


@pytest.fixture
def gw():
    falso = GatewayFalso()
    with patch("payments.routes.requests.get", side_effect=falso.get), \
         patch("payments.routes.requests.post", side_effect=falso.post):
        yield falso


# =========================================================================================
# Helpers de banco
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


def _pagamento(valor=PRECO, email=None, com_pagamento=True, com_senha=False, curso=CURSO):
    """Aluno + matricula pending + pagamento pending (estado em que o checkout deixa)."""
    email = email or f"aluno.{uuid.uuid4().hex[:8]}@e9.test"
    user_id = Database.get_or_create_user(email, "Aluno E9")
    if com_senha:
        _executar("UPDATE users SET password_hash = ? WHERE id = ?", (get_password_hash("senha-e9-correta"), user_id))
    ref = f"{curso}:e9:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, curso, ref)
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago") if com_pagamento else None
    return SimpleNamespace(
        email=email, user_id=user_id, ref=ref, enrollment_id=enrollment_id, payment_id=payment_id,
        valor=valor, mp_id=id_de_pagamento(ref),
    )


def _seed(p, status_pagamento, status_matricula=None):
    """Estado direto no banco (SQL), sem depender de nenhuma funcao da implementacao."""
    _executar("UPDATE payments SET status = ?, transaction_id = ? WHERE id = ?",
              (status_pagamento, p.mp_id, p.payment_id))
    if status_matricula:
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status_matricula, p.enrollment_id))


def _pag(p):
    return _sql("SELECT * FROM payments WHERE id = ?", (p.payment_id,))[0]


def _mat(p):
    return _sql("SELECT status FROM enrollments WHERE id = ?", (p.enrollment_id,))[0]["status"]


def _tokens(p=None):
    if p is None:
        return _sql("SELECT * FROM password_setup_tokens ORDER BY id")
    return _sql("SELECT * FROM password_setup_tokens WHERE user_id = ? ORDER BY id", (p.user_id,))


def _outbox(caminho):
    if not Path(caminho).exists():
        return []
    return [json.loads(l) for l in Path(caminho).read_text(encoding="utf-8").splitlines() if l.strip()]


def _eventos(action=None):
    if action is None:
        return _sql("SELECT * FROM audit_logs ORDER BY id")
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _foto(ambiente_outbox):
    """Tudo o que um webhook recusado/ignorado NAO pode alterar."""
    return {
        "payments": _sql("SELECT * FROM payments ORDER BY id"),
        "enrollments": _sql("SELECT * FROM enrollments ORDER BY id"),
        "tokens": _sql("SELECT * FROM password_setup_tokens ORDER BY id"),
        "audit": _sql("SELECT * FROM audit_logs ORDER BY id"),
        "outbox": _outbox(ambiente_outbox),
    }


def _changes(evento):
    bruto = evento.get("changes")
    if bruto is None or bruto == "":
        return []
    return json.loads(bruto) if isinstance(bruto, str) else bruto


def _valor_igual(valor, esperado):
    if valor == esperado:
        return True
    if isinstance(valor, str):
        try:
            return json.loads(valor) == esperado
        except ValueError:
            return False
    return False


def _checar_mudanca(evento, campo, antes, depois):
    itens = {i["field"]: i for i in _changes(evento)}
    assert campo in itens, f"campo {campo!r} ausente em changes: {sorted(itens)} ({evento})"
    assert _valor_igual(itens[campo]["before"], antes), f"{campo}.before = {itens[campo]['before']!r}, esperado {antes!r}"
    assert _valor_igual(itens[campo]["after"], depois), f"{campo}.after = {itens[campo]['after']!r}, esperado {depois!r}"


def _numeros(texto):
    return {Decimal(m) for m in re.findall(r"-?\d+(?:\.\d+)?", texto)}


# =========================================================================================
# Helpers de HTTP
# =========================================================================================

def _hook(client, gw, p, status, *, valor=None, moeda="BRL", mp_id=None, **kw):
    """Define o pagamento no gateway falso e envia o webhook assinado."""
    mp_id = mp_id or p.mp_id
    gw.definir(mp_id, status, p.ref, p.valor if valor is None else valor, moeda)
    return post_webhook(client, mp_id, **kw)


def _ignorado(r, motivo=None):
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo.get("status") == "ignored", corpo
    if motivo is not None:
        assert corpo.get("reason") == motivo, corpo


def _processado(r):
    assert r.status_code == 200, r.text
    assert r.json().get("status") not in ("ignored", "rejected"), r.json()


def _levar_a(client, gw, p, estado):
    """Leva o pagamento ao estado pedido por webhooks assinados, so por transicoes que a D48 permite."""
    if estado == "pending":
        return
    if estado in ("approved", "in_process", "rejected", "cancelled"):
        _processado(_hook(client, gw, p, estado))
    elif estado in ("refunded", "charged_back"):
        _processado(_hook(client, gw, p, "approved"))
        _processado(_hook(client, gw, p, estado))
    else:
        raise AssertionError(estado)
    assert _pag(p)["status"] == estado, f"seed: pagamento nao chegou a {estado}: {_pag(p)}"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _conta(email, nome, perfil):
    user_id = Database.add_user(email, nome, None, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, role=perfil, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        ana=_conta("ana.gestora@e9.test", "Ana Gestora", "admin"),
        fin=_conta("fernanda.fin@e9.test", "Fernanda Financeira", "financial"),
        sup=_conta("sergio.sup@e9.test", "Sergio Suporte", "support"),
    )


def _reembolsar(client, token, payment_id):
    return client.post(f"/api/payments/refund/{payment_id}", headers=_auth(token))


def _paralelo(n, funcao):
    """Executa funcao(client, i) em n threads ao mesmo tempo (barreira). Cada thread tem o seu TestClient."""
    from app import app as fastapi_app

    barreira = threading.Barrier(n)
    resultados = [None] * n
    erros = []

    def alvo(i):
        try:
            c = TestClient(fastapi_app, raise_server_exceptions=False)
            barreira.wait(timeout=60)
            resultados[i] = funcao(c, i)
        except Exception as exc:  # noqa: BLE001
            erros.append(repr(exc))

    threads = [threading.Thread(target=alvo, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not erros, f"erro nas threads: {erros}"
    assert all(r is not None for r in resultados), "alguma thread nao terminou"
    return resultados


# =========================================================================================
# Grupo S - assinatura valida passa e processa
# =========================================================================================

def test_s1_assinatura_valida_processa_e_consulta_o_gateway_uma_vez(client, gw):
    p = _pagamento()
    r = _hook(client, gw, p, "approved")
    _processado(r)
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert gw.ids_consultados() == [p.mp_id], "uma consulta ao gateway, com o id assinado"
    url, kwargs = gw.get_chamadas[0]
    assert url == f"https://api.mercadopago.com/v1/payments/{p.mp_id}", url
    assert kwargs.get("headers", {}).get("Authorization") == "Bearer TEST-fake"


@pytest.mark.parametrize("ts", ["1600000000", "1700000000000", "1"])
def test_s2_sem_janela_de_tempo_ts_antigo_ou_em_ms_vale(client, gw, ts):
    p = _pagamento()
    _processado(_hook(client, gw, p, "approved", ts=ts, request_id=f"req-{ts}"))
    assert _mat(p) == "active"


def test_s3_data_id_so_na_query_processa(client, gw):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    r = client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id, "type": "payment"}, json={},
                    headers=assinar(p.mp_id))
    _processado(r)
    assert _mat(p) == "active" and gw.ids_consultados() == [p.mp_id]


def test_s4_data_id_so_no_corpo_processa(client, gw):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    r = client.post(ROTA_WEBHOOK, json={"type": "payment", "data": {"id": p.mp_id}}, headers=assinar(p.mp_id))
    _processado(r)
    assert _mat(p) == "active" and gw.ids_consultados() == [p.mp_id]


def test_s5_data_id_da_query_e_preferido_ao_do_corpo(client, gw):
    a, b = _pagamento(), _pagamento()
    gw.definir(a.mp_id, "approved", a.ref, a.valor)
    gw.definir(b.mp_id, "approved", b.ref, b.valor)
    r = client.post(ROTA_WEBHOOK, params={"data.id": a.mp_id, "type": "payment"},
                    json={"type": "payment", "data": {"id": b.mp_id}}, headers=assinar(a.mp_id))
    _processado(r)
    assert gw.ids_consultados() == [a.mp_id], "o id da query (assinado) prevalece sobre o do corpo"
    assert _mat(a) == "active"
    assert _mat(b) == "pending" and _pag(b)["status"] == "pending"


def test_s6_assinatura_do_id_do_corpo_com_outro_id_na_query_e_recusada(client, gw, ambiente_e9):
    a, b = _pagamento(), _pagamento()
    gw.definir(a.mp_id, "approved", a.ref, a.valor)
    gw.definir(b.mp_id, "approved", b.ref, b.valor)
    antes = _foto(ambiente_e9)
    r = client.post(ROTA_WEBHOOK, params={"data.id": a.mp_id, "type": "payment"},
                    json={"type": "payment", "data": {"id": b.mp_id}}, headers=assinar(b.mp_id))
    assert r.status_code == 401, r.text
    assert gw.get_chamadas == []
    assert _foto(ambiente_e9) == antes


# =========================================================================================
# Grupo A - assinatura invalida (fail closed)
# =========================================================================================

def _recusado(r, gw, antes, ambiente_outbox):
    assert r.status_code == 401, f"esperado 401, veio {r.status_code}: {r.text}"
    assert r.json() == {"detail": DETAIL_ASSINATURA}, r.text
    assert gw.get_chamadas == [], f"o gateway foi consultado ({gw.get_chamadas}) antes de validar a assinatura"
    assert _foto(ambiente_outbox) == antes, "um webhook com assinatura invalida alterou estado"


def test_a1_sem_x_signature(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    r = post_webhook(client, p.mp_id, assinatura=False, headers={"x-request-id": "req-e9-0001"})
    _recusado(r, gw, antes, ambiente_e9)
    assert _mat(p) == "pending"


def test_a2_sem_cabecalho_nenhum(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    r = post_webhook(client, p.mp_id, assinatura=False)
    _recusado(r, gw, antes, ambiente_e9)
    assert _mat(p) == "pending" and _tokens() == []


def test_a3_sem_x_request_id(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    cab = assinar(p.mp_id)
    del cab["x-request-id"]
    r = post_webhook(client, p.mp_id, assinatura=False, headers=cab)
    _recusado(r, gw, antes, ambiente_e9)


def _assinaturas_malformadas(id_):
    valido = assinar(id_)["x-signature"]
    ts, v1 = valido.split(",")
    hex_ = v1.split("=", 1)[1]
    return {
        "vazia": "",
        "lixo": "isto-nao-e-uma-assinatura",
        "so_ts": ts,
        "so_v1": v1,
        "ts_vazio": f"ts=,v1={hex_}",
        "ts_nao_numerico_com_hmac_valido": assinar(id_, ts="abc")["x-signature"],
        "v1_vazio": f"{ts},v1=",
        "v1_curto": f"{ts},v1={hex_[:16]}",
        "v1_nao_hex": f"{ts},v1={'z' * 64}",
        "separador_errado": f"{ts};{v1}",
        "ordem_trocada_sem_ts": f"v1={hex_}",
    }


@pytest.mark.parametrize("variante", list(_assinaturas_malformadas("111").keys()))
def test_a4_x_signature_malformado(client, gw, ambiente_e9, variante):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    valor = _assinaturas_malformadas(p.mp_id)[variante]
    r = post_webhook(client, p.mp_id, assinatura=False,
                     headers={"x-signature": valor, "x-request-id": "req-e9-0001"})
    _recusado(r, gw, antes, ambiente_e9)
    assert _mat(p) == "pending"


def test_a5_segredo_errado(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    r = post_webhook(client, p.mp_id, segredo="outro-segredo-qualquer")
    _recusado(r, gw, antes, ambiente_e9)
    assert _mat(p) == "pending"


def test_a6_data_id_adulterado_depois_de_assinar(client, gw, ambiente_e9):
    alvo = _pagamento()
    gw.definir(alvo.mp_id, "approved", alvo.ref, alvo.valor)
    antes = _foto(ambiente_e9)
    cab = assinar("111111")  # assinatura de OUTRO id
    r = post_webhook(client, alvo.mp_id, assinatura=False, headers=cab)
    _recusado(r, gw, antes, ambiente_e9)
    assert _mat(alvo) == "pending"


def test_a7_x_request_id_adulterado(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    cab = assinar(p.mp_id, request_id="req-original")
    cab["x-request-id"] = "req-adulterado"
    r = post_webhook(client, p.mp_id, assinatura=False, headers=cab)
    _recusado(r, gw, antes, ambiente_e9)


def test_a8_ts_adulterado(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    cab = assinar(p.mp_id, ts="1700000000000")
    cab["x-signature"] = cab["x-signature"].replace("ts=1700000000000", "ts=1700000000001")
    assert "ts=1700000000001" in cab["x-signature"]
    r = post_webhook(client, p.mp_id, assinatura=False, headers=cab)
    _recusado(r, gw, antes, ambiente_e9)


def test_a9_assinatura_e_verificada_antes_do_id_e_do_topico(client, gw, ambiente_e9):
    """Com assinatura invalida a resposta e 401, mesmo com id invalido (o 400 vem DEPOIS da assinatura)."""
    antes = _foto(ambiente_e9)
    r = post_webhook(client, "../x", segredo="outro-segredo-qualquer")
    _recusado(r, gw, antes, ambiente_e9)


@pytest.mark.parametrize("configuracao", ["ausente", "vazio"])
def test_a10_segredo_nao_configurado_responde_503_e_nao_processa(client, gw, monkeypatch, ambiente_e9, configuracao):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    if configuracao == "ausente":
        monkeypatch.delenv("MERCADO_PAGO_WEBHOOK_SECRET", raising=False)
    else:
        monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", "")
    antes = _foto(ambiente_e9)
    r = post_webhook(client, p.mp_id)  # assinado com o segredo de teste: nao pode valer sem segredo configurado
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": DETAIL_NAO_CONFIGURADO}, r.text
    assert gw.get_chamadas == []
    assert _foto(ambiente_e9) == antes
    assert _mat(p) == "pending"


# =========================================================================================
# Grupo T - topico e id
# =========================================================================================

@pytest.mark.parametrize("onde", ["query", "corpo", "topic_na_query"])
def test_t1_topico_diferente_de_payment_e_ignorado(client, gw, ambiente_e9, onde):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    antes = _foto(ambiente_e9)
    if onde == "query":
        r = client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id, "type": "merchant_order"}, json={},
                        headers=assinar(p.mp_id))
    elif onde == "corpo":
        r = client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id},
                        json={"type": "merchant_order", "data": {"id": p.mp_id}}, headers=assinar(p.mp_id))
    else:
        r = client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id, "topic": "merchant_order"}, json={},
                        headers=assinar(p.mp_id))
    _ignorado(r, "unsupported topic")
    assert gw.get_chamadas == [], "topico nao suportado nao pode consultar o gateway"
    assert _foto(ambiente_e9) == antes


@pytest.mark.parametrize("campo", ["type", "topic"])
def test_t2_type_ou_topic_payment_na_query_processam(client, gw, campo):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    r = client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id, campo: "payment"}, json={}, headers=assinar(p.mp_id))
    _processado(r)
    assert _mat(p) == "active"


INVALIDOS = ["abc", "12a", "../x", "1/../../y", "123456789012345678901", "-1", "1.5", "1 2", "%2e%2e", "1;2", "0x1f"]


@pytest.mark.parametrize("data_id", INVALIDOS)
def test_t3_data_id_nao_numerico_ou_longo_demais_responde_400_sem_consultar_o_gateway(client, gw, ambiente_e9, data_id):
    antes = _foto(ambiente_e9)
    r = post_webhook(client, data_id)  # assinatura VALIDA para esse id
    assert r.status_code == 400, f"id {data_id!r}: esperado 400, veio {r.status_code} {r.text}"
    assert r.json() == {"detail": DETAIL_ID}, r.text
    assert gw.get_chamadas == [], f"id {data_id!r} chegou ao gateway: {gw.get_chamadas}"
    assert _foto(ambiente_e9) == antes


def test_t4_data_id_invalido_so_no_corpo_tambem_e_400(client, gw):
    r = client.post(ROTA_WEBHOOK, json={"type": "payment", "data": {"id": "../x"}}, headers=assinar("../x"))
    assert r.status_code == 400, r.text
    assert gw.get_chamadas == []


def test_t5_id_de_20_digitos_e_aceito(client, gw):
    p = _pagamento()
    mp_id = "9" * 20
    r = _hook(client, gw, p, "approved", mp_id=mp_id)
    _processado(r)
    assert gw.ids_consultados() == [mp_id] and _mat(p) == "active"


# =========================================================================================
# Grupo V - conferencia de valor e moeda
# =========================================================================================

def _nada_mudou_no_pagamento(p, antes_pag):
    assert _pag(p) == antes_pag, "divergencia nao pode alterar o pagamento local"
    assert _mat(p) == "pending", "divergencia nao pode ativar a matricula"
    assert _tokens(p) == []


@pytest.mark.parametrize("preco, recebido", [
    (100.0, 100.0), (100.0, 100), (99.9, 99.9), (19.99, 19.99), (0.1, 0.1), (1234.56, 1234.56),
])
def test_v1_valor_e_moeda_iguais_ativam_a_matricula(client, gw, preco, recebido):
    p = _pagamento(valor=preco)
    _processado(_hook(client, gw, p, "approved", valor=recebido))
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert _eventos("payment.amount_mismatch") == []


@pytest.mark.parametrize("recebido", [100.01, 99.99, 150.0, 10.0, 0.01, 10000.0, 1.0, 0, -100.0, AUSENTE])
def test_v2_valor_divergente_nao_ativa_e_grava_evento_amount_mismatch(client, gw, ambiente_e9, recebido):
    p = _pagamento(valor=100.0)
    antes_pag = _pag(p)
    r = _hook(client, gw, p, "approved", valor=recebido)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "rejected", "reason": "amount_mismatch"}, r.json()
    _nada_mudou_no_pagamento(p, antes_pag)
    assert _outbox(ambiente_e9) == [], "divergencia nao pode enviar link de senha"

    eventos = _eventos("payment.amount_mismatch")
    assert len(eventos) == 1, eventos
    ev = eventos[0]
    assert ev["role"] == "system", ev
    assert ev["entity_type"] == "payment" and str(ev["entity_id"]) == str(p.payment_id), ev
    alteracoes = _changes(ev)
    assert alteracoes, "changes deve trazer o valor esperado e o recebido"
    numeros = _numeros(json.dumps(alteracoes))
    assert Decimal("100") in numeros, f"valor esperado (100) ausente em changes: {alteracoes}"
    if recebido is not AUSENTE:
        assert Decimal(str(recebido)) in numeros, f"valor recebido ({recebido}) ausente em changes: {alteracoes}"
    assert _eventos("payment.status_change") == [], "divergencia nao e transicao de status"


@pytest.mark.parametrize("moeda", ["USD", "ARS", "EUR", "", AUSENTE])
def test_v3_moeda_diferente_de_brl_nao_ativa(client, gw, ambiente_e9, moeda):
    p = _pagamento(valor=100.0)
    antes_pag = _pag(p)
    r = _hook(client, gw, p, "approved", valor=100.0, moeda=moeda)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "rejected", "reason": "amount_mismatch"}, r.json()
    _nada_mudou_no_pagamento(p, antes_pag)
    assert _outbox(ambiente_e9) == []
    eventos = _eventos("payment.amount_mismatch")
    assert len(eventos) == 1, eventos
    assert eventos[0]["role"] == "system" and eventos[0]["entity_type"] == "payment"
    assert str(eventos[0]["entity_id"]) == str(p.payment_id)


def test_v4_divergencia_nao_envenena_o_pagamento_e_o_valor_correto_depois_ativa(client, gw, ambiente_e9):
    p = _pagamento(valor=100.0)
    r1 = _hook(client, gw, p, "approved", valor=10.0)
    assert r1.json().get("status") == "rejected"
    assert _mat(p) == "pending"
    r2 = _hook(client, gw, p, "approved", valor=100.0, request_id="req-e9-0002")
    _processado(r2)
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert len(_tokens(p)) == 1 and len(_outbox(ambiente_e9)) == 1


# =========================================================================================
# Grupo U - referencia desconhecida / sem pagamento local
# =========================================================================================

def test_u1_referencia_desconhecida_e_ignorada_sem_token_nem_email(client, gw, ambiente_e9):
    p = _pagamento()
    mp_id = id_de_pagamento("ref-que-nao-existe")
    gw.definir(mp_id, "approved", "ref-que-nao-existe", 100.0)
    antes = _foto(ambiente_e9)
    r = post_webhook(client, mp_id)
    _ignorado(r, "unknown reference")
    assert _foto(ambiente_e9) == antes
    assert _mat(p) == "pending" and _tokens() == [] and _outbox(ambiente_e9) == []


def test_u2_referencia_ausente_no_pagamento_do_gateway_nao_altera_nada(client, gw, ambiente_e9):
    p = _pagamento()
    mp_id = id_de_pagamento("sem-referencia")
    gw.definir(mp_id, "approved", None, 100.0)
    antes = _foto(ambiente_e9)
    r = post_webhook(client, mp_id)
    assert r.status_code == 200, r.text
    assert _foto(ambiente_e9) == antes
    assert _mat(p) == "pending" and _tokens() == [] and _outbox(ambiente_e9) == []


def test_u3_matricula_sem_pagamento_local_e_ignorada(client, gw, ambiente_e9):
    p = _pagamento(com_pagamento=False)
    antes = _foto(ambiente_e9)
    gw.definir(p.mp_id, "approved", p.ref, 100.0)
    r = post_webhook(client, p.mp_id)
    _ignorado(r, "unknown reference")
    assert _foto(ambiente_e9) == antes
    assert _mat(p) == "pending" and _tokens() == [] and _outbox(ambiente_e9) == []


# =========================================================================================
# Grupo M - maquina de estados do pagamento
# =========================================================================================

ENTRADAS = ["approved", "pending", "in_process", "rejected", "cancelled", "refunded", "charged_back"]


@pytest.mark.parametrize("terminal", ["refunded", "charged_back"])
@pytest.mark.parametrize("chega", ENTRADAS)
def test_m1_refunded_e_charged_back_sao_terminais(client, gw, ambiente_e9, terminal, chega):
    p = _pagamento()
    _levar_a(client, gw, p, terminal)
    antes = _foto(ambiente_e9)
    pagamento_antes, matricula_antes = _pag(p), _mat(p)
    r = _hook(client, gw, p, chega, request_id="req-e9-0099")
    if chega == terminal:
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ignored", r.json()
        assert r.json().get("reason") in ("terminal", "duplicate"), r.json()
    else:
        _ignorado(r, "terminal")
    assert _pag(p) == pagamento_antes, "um estado terminal nao pode ser alterado por notificacao"
    assert _mat(p) == matricula_antes
    assert _foto(ambiente_e9) == antes, "nem token, nem e-mail, nem evento novo"


def test_m1b_approved_repetido_depois_de_reembolso_nao_reativa_a_matricula(client, gw, ambiente_e9):
    p = _pagamento()
    _levar_a(client, gw, p, "refunded")
    assert _mat(p) == "refunded"
    tokens_antes, outbox_antes = len(_tokens(p)), len(_outbox(ambiente_e9))
    for n in range(3):
        _ignorado(_hook(client, gw, p, "approved", request_id=f"req-e9-{n}"), "terminal")
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"
    assert len(_tokens(p)) == tokens_antes and len(_outbox(ambiente_e9)) == outbox_antes


@pytest.mark.parametrize("chega", ["pending", "in_process", "rejected", "cancelled"])
def test_m2_approved_nao_e_rebaixado(client, gw, ambiente_e9, chega):
    p = _pagamento()
    _levar_a(client, gw, p, "approved")
    antes = _foto(ambiente_e9)
    r = _hook(client, gw, p, chega, request_id="req-e9-0099")
    _ignorado(r, "stale")
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert _foto(ambiente_e9) == antes


def test_m3_approved_vai_para_refunded_e_a_matricula_acompanha(client, gw):
    p = _pagamento()
    _levar_a(client, gw, p, "approved")
    _processado(_hook(client, gw, p, "refunded", request_id="req-e9-0002"))
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"


def test_m3b_approved_vai_para_charged_back(client, gw):
    p = _pagamento()
    _levar_a(client, gw, p, "approved")
    _processado(_hook(client, gw, p, "charged_back", request_id="req-e9-0002"))
    assert _pag(p)["status"] == "charged_back"


def test_m4_estados_nao_aprovados_movem_se_livremente_e_a_matricula_segue_o_mapa(client, gw):
    p = _pagamento()
    esperado = [
        ("in_process", "pending"), ("rejected", "cancelled"), ("cancelled", "cancelled"),
        ("pending", "pending"), ("rejected", "cancelled"), ("in_process", "pending"), ("approved", "active"),
    ]
    for n, (status, matricula) in enumerate(esperado):
        _processado(_hook(client, gw, p, status, request_id=f"req-e9-{n}"))
        assert _pag(p)["status"] == status, f"passo {n}: pagamento deveria ir a {status}"
        assert _mat(p) == matricula, f"passo {n}: matricula deveria ser {matricula}"


def test_m4b_rejected_para_approved_e_permitido_e_emite_um_token(client, gw, ambiente_e9):
    p = _pagamento()
    _levar_a(client, gw, p, "rejected")
    assert _mat(p) == "cancelled" and _tokens(p) == []
    _processado(_hook(client, gw, p, "approved", request_id="req-e9-0002"))
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert len(_tokens(p)) == 1 and len(_outbox(ambiente_e9)) == 1


@pytest.mark.parametrize("estado", ["pending", "in_process", "rejected", "cancelled", "approved"])
def test_m5_mesmo_status_de_novo_e_no_op(client, gw, ambiente_e9, estado):
    p = _pagamento()
    if estado != "pending":
        _levar_a(client, gw, p, estado)
    antes = _foto(ambiente_e9)
    r = _hook(client, gw, p, estado, request_id="req-e9-0099")
    _ignorado(r, "duplicate")
    assert _foto(ambiente_e9) == antes, "mesmo status nao tem efeito colateral nem grava nada"


# =========================================================================================
# Grupo E - efeitos colaterais uma vez so
# =========================================================================================

def test_e1_dois_approved_identicos_em_sequencia_geram_um_token_e_uma_entrega(client, gw, ambiente_e9):
    p = _pagamento()
    r1 = _hook(client, gw, p, "approved")
    r2 = _hook(client, gw, p, "approved")
    _processado(r1)
    _ignorado(r2, "duplicate")
    assert len(_tokens(p)) == 1, f"esperado 1 token, achei {len(_tokens(p))}"
    entregas = _outbox(ambiente_e9)
    assert len(entregas) == 1 and entregas[0]["email"] == p.email, entregas
    assert "definir-senha?token=" in entregas[0]["link"]
    assert len(_eventos("payment.status_change")) == 1


def test_e2_oito_approved_simultaneos_geram_exatamente_um_token_e_uma_entrega(client, gw, ambiente_e9):
    p = _pagamento()
    gw.definir(p.mp_id, "approved", p.ref, p.valor)
    gw.atraso_get = 0.05  # todas leem o estado `pending` antes de qualquer gravacao (alarga a corrida)

    respostas = _paralelo(8, lambda c, i: post_webhook(c, p.mp_id))

    assert [r.status_code for r in respostas] == [200] * 8, [(r.status_code, r.text) for r in respostas]
    processadas = [r for r in respostas if r.json().get("status") not in ("ignored", "rejected")]
    ignoradas = [r for r in respostas if r.json().get("status") == "ignored"]
    assert len(processadas) == 1 and len(ignoradas) == 7, [r.json() for r in respostas]
    assert len(_tokens(p)) == 1, f"esperado 1 token, achei {len(_tokens(p))}"
    assert len(_outbox(ambiente_e9)) == 1, f"esperada 1 entrega, achei {len(_outbox(ambiente_e9))}"
    assert len(_eventos("payment.status_change")) == 1
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"


def test_e3_conta_com_senha_nao_recebe_link(client, gw, ambiente_e9):
    p = _pagamento(com_senha=True)
    _processado(_hook(client, gw, p, "approved"))
    assert _mat(p) == "active"
    assert _tokens(p) == [] and _outbox(ambiente_e9) == []


def test_e4_transaction_id_duplicado_em_dois_pagamentos_e_ignorado(client, gw, ambiente_e9):
    a, b = _pagamento(), _pagamento()
    # o id do gateway aponta, primeiro, para o pagamento A...
    _processado(_hook(client, gw, a, "approved"))
    assert _pag(a)["transaction_id"] == a.mp_id
    # ...e depois (id reaproveitado/forjado no gateway) para a referencia de B: mesmo transaction_id em dois pagamentos
    antes = _foto(ambiente_e9)
    gw.definir(a.mp_id, "approved", b.ref, b.valor)
    r = post_webhook(client, a.mp_id, request_id="req-e9-0002")
    _ignorado(r, "duplicate transaction")
    assert _pag(b)["status"] == "pending" and _mat(b) == "pending" and _tokens(b) == []
    assert _foto(ambiente_e9) == antes
    assert len([x for x in _sql("SELECT id FROM payments WHERE transaction_id = ?", (a.mp_id,))]) == 1


def test_e5_indice_unico_parcial_em_transaction_id(client):
    a, b, c = _pagamento(), _pagamento(), _pagamento()
    # varios NULL continuam permitidos (indice parcial: so valores nao nulos)
    assert all(_pag(x)["transaction_id"] is None for x in (a, b, c))
    _executar("UPDATE payments SET transaction_id = 'tx-unico-e9' WHERE id = ?", (a.payment_id,))
    with pytest.raises(sqlite3.IntegrityError):
        _executar("UPDATE payments SET transaction_id = 'tx-unico-e9' WHERE id = ?", (b.payment_id,))
    assert _pag(b)["transaction_id"] is None
    _executar("UPDATE payments SET transaction_id = 'tx-outro-e9' WHERE id = ?", (b.payment_id,))


def test_e6_init_db_repetido_nao_quebra_com_o_indice(banco):
    Database.init_db()
    Database.init_db()


# =========================================================================================
# Grupo D - auditoria payment.status_change
# =========================================================================================

def _checar_status_change(evento, p, antes, depois):
    assert evento["role"] == "system", evento
    assert evento["entity_type"] == "payment", evento
    assert str(evento["entity_id"]) == str(p.payment_id), evento
    _checar_mudanca(evento, "payment.status", antes, depois)


@pytest.mark.parametrize("origem", ["pending", "rejected"])
def test_d1_transicao_para_approved_grava_evento(client, gw, origem):
    p = _pagamento()
    if origem != "pending":
        _levar_a(client, gw, p, origem)
    _processado(_hook(client, gw, p, "approved", request_id="req-e9-0002"))
    eventos = _eventos("payment.status_change")
    assert len(eventos) == 1, eventos
    _checar_status_change(eventos[0], p, origem, "approved")


def test_d2_transicao_para_refunded_e_para_charged_back_gravam_evento(client, gw):
    r_, c_ = _pagamento(), _pagamento()
    _levar_a(client, gw, r_, "refunded")
    _levar_a(client, gw, c_, "charged_back")
    eventos = _eventos("payment.status_change")
    assert len(eventos) == 4, f"esperados 4 eventos (2 por pagamento), achei {len(eventos)}: {eventos}"
    por_pagamento = {}
    for ev in eventos:
        por_pagamento.setdefault(str(ev["entity_id"]), []).append(ev)
    assert len(por_pagamento[str(r_.payment_id)]) == 2, por_pagamento
    assert len(por_pagamento[str(c_.payment_id)]) == 2, por_pagamento
    _checar_status_change(por_pagamento[str(r_.payment_id)][0], r_, "pending", "approved")
    _checar_status_change(por_pagamento[str(r_.payment_id)][1], r_, "approved", "refunded")
    _checar_status_change(por_pagamento[str(c_.payment_id)][1], c_, "approved", "charged_back")


def test_d3_webhook_ignorado_nao_grava_evento(client, gw):
    p = _pagamento()
    _levar_a(client, gw, p, "approved")
    base = len(_eventos("payment.status_change"))
    assert base == 1
    # duplicado, obsoleto, topico nao suportado, referencia desconhecida, id invalido, assinatura invalida
    _ignorado(_hook(client, gw, p, "approved", request_id="r1"), "duplicate")
    _ignorado(_hook(client, gw, p, "pending", request_id="r2"), "stale")
    client.post(ROTA_WEBHOOK, params={"data.id": p.mp_id, "type": "merchant_order"}, json={}, headers=assinar(p.mp_id))
    mp_x = id_de_pagamento("ref-x")
    gw.definir(mp_x, "approved", "ref-x", 100.0)
    post_webhook(client, mp_x)
    post_webhook(client, "../x")
    post_webhook(client, p.mp_id, segredo="errado")
    assert len(_eventos("payment.status_change")) == base


# =========================================================================================
# Grupo R - reembolso
# =========================================================================================

def _aprovado_direto(valor=PRECO):
    p = _pagamento(valor=valor)
    _seed(p, "approved", "active")
    return p


def test_r1_approved_vira_refunded_no_pagamento_e_na_matricula_com_evento(client, contas):
    p = _aprovado_direto()
    r = _reembolsar(client, contas.fin.token, p.payment_id)
    assert r.status_code == 200, r.text
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"
    eventos = _eventos("payment.refund")
    assert len(eventos) == 1, eventos
    ev = eventos[0]
    assert ev["user_id"] == contas.fin.id and ev["actor_email"] == contas.fin.email and ev["role"] == "financial"
    assert ev["entity_type"] == "payment" and str(ev["entity_id"]) == str(p.payment_id)
    _checar_mudanca(ev, "payment.status", "approved", "refunded")
    _checar_mudanca(ev, "enrollment.status", "active", "refunded")


def test_r2_reembolso_repetido_e_idempotente_sem_evento_novo(client, contas):
    p = _aprovado_direto()
    r1 = _reembolsar(client, contas.fin.token, p.payment_id)
    r2 = _reembolsar(client, contas.ana.token, p.payment_id)
    r3 = _reembolsar(client, contas.fin.token, p.payment_id)
    assert r1.status_code == r2.status_code == r3.status_code == 200, (r1.text, r2.text, r3.text)
    assert r1.json() == r2.json() == r3.json(), "mesmo corpo na repeticao"
    assert len(_eventos("payment.refund")) == 1
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"


@pytest.mark.parametrize("quem", ["fin", "ana"])
@pytest.mark.parametrize("status", ["pending", "rejected", "cancelled", "in_process", "charged_back"])
def test_r3_so_pagamento_aprovado_pode_ser_reembolsado(client, contas, status, quem):
    p = _pagamento()
    matricula = {"pending": "pending", "rejected": "cancelled", "cancelled": "cancelled",
                 "in_process": "pending", "charged_back": "active"}[status]
    if status != "pending":
        _seed(p, status, matricula)
    antes_pag, antes_mat = _pag(p), _mat(p)
    antes_audit = _eventos()
    token = getattr(contas, quem).token
    r = _reembolsar(client, token, p.payment_id)
    assert r.status_code == 409, f"{status}: esperado 409, veio {r.status_code} {r.text}"
    assert r.json() == {"detail": DETAIL_409}, r.text
    assert _pag(p) == antes_pag and _mat(p) == antes_mat, "reembolso recusado nao pode alterar nada"
    assert _eventos("payment.refund") == []
    assert _eventos() == antes_audit


def test_r4_pagamento_inexistente_e_404(client, contas):
    r = _reembolsar(client, contas.fin.token, 987654)
    assert r.status_code == 404, r.text
    assert r.json() == {"detail": "Pagamento não encontrado."}
    assert _eventos("payment.refund") == []


def test_r5_sem_token_ou_token_forjado_e_401(client, contas):
    p = _aprovado_direto()
    forjado = jose_jwt.encode({"user_id": 1, "email": "x@e9.test", "role": "admin"},
                              "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")
    assert client.post(f"/api/payments/refund/{p.payment_id}").status_code == 401
    assert client.post(f"/api/payments/refund/{p.payment_id}", headers=_auth(forjado)).status_code == 401
    assert client.post(f"/api/payments/refund/{p.payment_id}", headers=_auth("lixo")).status_code == 401
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert _eventos("payment.refund") == []


def test_r6_suporte_e_aluno_recebem_403_e_nada_muda(client, contas):
    p = _aprovado_direto()
    aluno = SimpleNamespace(token=create_access_token({"user_id": p.user_id, "email": p.email, "role": "student"}))
    tokens = {
        "suporte_jwt": contas.sup.token,
        "suporte_legado": create_admin_token(Role("support")),
        "aluno_dono_do_pagamento": aluno.token,
    }
    for rotulo, token in tokens.items():
        r = _reembolsar(client, token, p.payment_id)
        assert r.status_code == 403, f"{rotulo}: esperado 403, veio {r.status_code} {r.text}"
    assert _pag(p)["status"] == "approved" and _mat(p) == "active"
    assert _eventos("payment.refund") == []


def test_r7_pagamento_ja_reembolsado_pelo_webhook_responde_200_sem_evento_de_reembolso(client, gw, contas):
    p = _pagamento()
    _levar_a(client, gw, p, "refunded")
    r = _reembolsar(client, contas.fin.token, p.payment_id)
    assert r.status_code == 200, r.text
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"
    assert _eventos("payment.refund") == []


def test_r8_dois_ou_mais_reembolsos_simultaneos_geram_um_evento_so(client, contas):
    p = _aprovado_direto()
    token = contas.fin.token
    respostas = _paralelo(6, lambda c, i: _reembolsar(c, token, p.payment_id))
    assert [r.status_code for r in respostas] == [200] * 6, [(r.status_code, r.text) for r in respostas]
    assert len({json.dumps(r.json(), sort_keys=True) for r in respostas}) == 1, "todos com o mesmo corpo"
    assert len(_eventos("payment.refund")) == 1, _eventos("payment.refund")
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"


def test_r9_approved_que_chega_depois_do_reembolso_nao_reativa_a_matricula(client, gw, contas, ambiente_e9):
    p = _pagamento()
    _levar_a(client, gw, p, "approved")
    assert _reembolsar(client, contas.fin.token, p.payment_id).status_code == 200
    tokens_antes, outbox_antes = len(_tokens(p)), len(_outbox(ambiente_e9))
    _ignorado(_hook(client, gw, p, "approved", request_id="req-e9-0002"), "terminal")
    assert _pag(p)["status"] == "refunded" and _mat(p) == "refunded"
    assert len(_tokens(p)) == tokens_antes and len(_outbox(ambiente_e9)) == outbox_antes


# =========================================================================================
# Grupo C - CORS
# =========================================================================================

ORIGENS_ESTRANHAS = [
    "https://evil.example", "http://localhost:4200.evil.example", "http://localhost:42000",
    "https://localhost:4200", "null", "http://127.0.0.1:9999", "http://evil.example:4200",
]


def _app_novo(monkeypatch, **ambiente):
    """Executa app.py de novo sob outro nome de modulo, com a variavel de ambiente pedida.

    Nao toca em sys.modules['app'] (os demais testes seguem com o app padrao). Valor None remove a variavel.
    """
    for nome, valor in ambiente.items():
        if valor is None:
            monkeypatch.delenv(nome, raising=False)
        else:
            monkeypatch.setenv(nome, valor)
    spec = importlib.util.spec_from_file_location(f"app_cors_e9_{uuid.uuid4().hex}", BACKEND_DIR / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return TestClient(modulo.app, raise_server_exceptions=False)


def _acao(resposta):
    return resposta.headers.get("access-control-allow-origin")


def _simples(c, origem):
    return c.get("/health", headers={"Origin": origem})


def _preflight(c, origem, metodo="POST", cabecalhos="content-type, authorization", rota="/api/payments/create-checkout"):
    return c.options(rota, headers={
        "Origin": origem,
        "Access-Control-Request-Method": metodo,
        "Access-Control-Request-Headers": cabecalhos,
    })


ORIGENS_PADRAO = ["http://localhost:4200", "http://127.0.0.1:4200", "http://127.0.0.1:8000", "http://localhost:8000"]


@pytest.mark.parametrize("origem", ORIGENS_PADRAO)
def test_c1_origem_permitida_recebe_o_acao_exato_e_nunca_asterisco(client, origem):
    r = _simples(client, origem)
    assert _acao(r) == origem, f"{origem}: access-control-allow-origin = {_acao(r)!r}"
    assert "access-control-allow-credentials" not in r.headers, "a autenticacao e por cabecalho: sem credenciais"


@pytest.mark.parametrize("origem", ORIGENS_ESTRANHAS)
def test_c2_origem_estranha_nao_recebe_acao(client, origem):
    r = _simples(client, origem)
    assert _acao(r) is None, f"{origem}: recebeu access-control-allow-origin = {_acao(r)!r}"
    assert "access-control-allow-credentials" not in r.headers


@pytest.mark.parametrize("origem", ORIGENS_ESTRANHAS)
def test_c3_preflight_de_origem_estranha_nao_recebe_acao(client, origem):
    r = _preflight(client, origem)
    assert _acao(r) is None, f"{origem}: preflight recebeu access-control-allow-origin = {_acao(r)!r}"
    assert "access-control-allow-credentials" not in r.headers


def test_c4_preflight_de_origem_permitida_libera_metodos_e_cabecalhos_da_lista(client):
    r = _preflight(client, "http://localhost:4200")
    assert r.status_code == 200, r.text
    assert _acao(r) == "http://localhost:4200"
    assert "access-control-allow-credentials" not in r.headers
    metodos = {m.strip().upper() for m in r.headers.get("access-control-allow-methods", "").split(",")}
    assert {"GET", "POST", "PUT", "DELETE", "OPTIONS"} <= metodos, metodos
    cabecalhos = {h.strip().lower() for h in r.headers.get("access-control-allow-headers", "").split(",")}
    assert {"authorization", "content-type"} <= cabecalhos, cabecalhos


def test_c5_metodo_fora_da_lista_nao_e_liberado_no_preflight(client):
    r = _preflight(client, "http://localhost:4200", metodo="PATCH")
    metodos = {m.strip().upper() for m in r.headers.get("access-control-allow-methods", "").split(",")}
    assert "PATCH" not in metodos and "*" not in metodos, metodos


def test_c6_o_padrao_inclui_frontend_base_url_e_exclui_o_resto(monkeypatch):
    c = _app_novo(monkeypatch, CORS_ALLOWED_ORIGINS=None, FRONTEND_BASE_URL="https://app.exemplo.test")
    for origem in ["https://app.exemplo.test"] + ORIGENS_PADRAO[:3]:
        assert _acao(_simples(c, origem)) == origem, origem
    assert _acao(_simples(c, "https://evil.example")) is None
    assert _acao(_preflight(c, "https://evil.example")) is None


def test_c7_frontend_base_url_ausente_usa_localhost_8000(monkeypatch):
    c = _app_novo(monkeypatch, CORS_ALLOWED_ORIGINS=None, FRONTEND_BASE_URL=None)
    assert _acao(_simples(c, "http://localhost:8000")) == "http://localhost:8000"
    assert _acao(_simples(c, "https://evil.example")) is None


def test_c8_cors_allowed_origins_define_a_lista(monkeypatch):
    c = _app_novo(monkeypatch, CORS_ALLOWED_ORIGINS="https://a.exemplo.test,https://b.exemplo.test")
    assert _acao(_simples(c, "https://a.exemplo.test")) == "https://a.exemplo.test"
    assert _acao(_simples(c, "https://b.exemplo.test")) == "https://b.exemplo.test"
    assert _acao(_preflight(c, "https://b.exemplo.test")) == "https://b.exemplo.test"
    assert _acao(_simples(c, "https://evil.example")) is None
    assert _acao(_preflight(c, "https://evil.example")) is None
    # a variavel SUBSTITUI o padrao (a D48 so aplica o padrao "quando ausente")
    assert _acao(_simples(c, "http://localhost:4200")) is None, "com a variavel definida, o padrao nao vale"
    assert "access-control-allow-credentials" not in _simples(c, "https://a.exemplo.test").headers


@pytest.mark.parametrize("valor", ["*", "https://a.exemplo.test,*"])
def test_c9_asterisco_na_variavel_nunca_vira_acao_para_origem_estranha(monkeypatch, valor):
    c = _app_novo(monkeypatch, CORS_ALLOWED_ORIGINS=valor)
    for origem in ("https://evil.example", "null"):
        assert _acao(_simples(c, origem)) is None, f"{origem}: recebeu {_acao(_simples(c, origem))!r}"
        assert _acao(_preflight(c, origem)) is None
    assert "access-control-allow-credentials" not in _simples(c, "https://evil.example").headers


# =========================================================================================
# Grupo K - checkout
# =========================================================================================

def _checkout(client, email="comprador.e9@e9.test", **extra):
    return client.post("/api/payments/create-checkout", json={
        "course_id": CURSO, "payer": {"name": "Comprador E9", "email": email}, **extra,
    })


def _contagens():
    return {
        "payments": len(_sql("SELECT id FROM payments")),
        "enrollments": len(_sql("SELECT id FROM enrollments")),
        "users": len(_sql("SELECT id FROM users")),
    }


@pytest.mark.parametrize("status_gateway", [400, 401, 422, 500, 503])
def test_k1_erro_do_gateway_devolve_502_fixo_sem_o_corpo(client, gw, capsys, status_gateway):
    marcador = "SEGREDO-DO-GATEWAY-e9-cause-12345"
    resposta = MagicMock(status_code=status_gateway)
    resposta.text = f'{{"message":"{marcador}","cause":[{{"code":"{marcador}"}}]}}'
    resposta.json.return_value = {"message": marcador, "cause": [{"code": marcador}]}
    gw.post_resposta = resposta
    antes = _contagens()
    r = _checkout(client)
    assert r.status_code == 502, r.text
    assert r.json() == {"detail": DETAIL_CHECKOUT_502}, r.text
    assert marcador not in r.text and "cause" not in r.text
    saida = capsys.readouterr()
    assert marcador not in saida.out and marcador not in saida.err, "o log nao pode trazer o corpo do gateway"
    assert _contagens() == antes, "checkout que falhou nao pode criar conta, matricula nem pagamento"


@pytest.mark.parametrize("configuracao", ["ausente", "vazio"])
def test_k2_token_do_gateway_ausente_responde_503(client, gw, monkeypatch, configuracao):
    if configuracao == "ausente":
        monkeypatch.delenv("MERCADO_PAGO_ACCESS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "")
    antes = _contagens()
    r = _checkout(client)
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": DETAIL_CHECKOUT_503}, r.text
    assert gw.post_chamadas == []
    assert _contagens() == antes


@pytest.mark.parametrize("extra", [
    {"price": 1}, {"amount": 0.01}, {"unit_price": 1}, {"price": 0, "amount": 0, "unit_price": 0},
    {"price": -50, "amount": -50}, {"payer_price": 1},
])
def test_k3_preco_do_corpo_e_ignorado_vale_o_do_catalogo(client, gw, extra):
    r = _checkout(client, **extra)
    assert r.status_code == 200, r.text
    assert len(gw.post_chamadas) == 1
    preferencia = gw.post_chamadas[0][1]["json"]
    assert preferencia["items"][0]["unit_price"] == PRECO, preferencia["items"]
    pagamentos = _sql("SELECT amount FROM payments")
    assert len(pagamentos) == 1 and pagamentos[0]["amount"] == PRECO, pagamentos


def test_k4_checkout_feliz_continua_funcionando(client, gw):
    r = _checkout(client)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["checkout_url"] == "https://mp.test/checkout" and corpo["external_reference"]
    matricula = _sql("SELECT status, external_reference FROM enrollments")[0]
    assert matricula == {"status": "pending", "external_reference": corpo["external_reference"]}
    assert _sql("SELECT status FROM payments")[0]["status"] == "pending"


def test_k5_checkout_e_webhook_ponta_a_ponta_com_o_valor_do_catalogo(client, gw):
    corpo = _checkout(client, email="ponta.a.ponta@e9.test").json()
    ref = corpo["external_reference"]
    mp_id = id_de_pagamento(ref)
    gw.definir(mp_id, "approved", ref, PRECO)
    _processado(post_webhook(client, mp_id))
    assert _sql("SELECT status FROM enrollments")[0]["status"] == "active"
    assert _sql("SELECT status FROM payments")[0]["status"] == "approved"


# =========================================================================================
# Grupo I - isolamento entre alunos
# =========================================================================================

def test_i1_webhook_de_uma_referencia_nao_altera_pagamento_nem_token_de_outro_aluno(client, gw, ambiente_e9):
    a, b = _pagamento(), _pagamento()
    b_antes = (_pag(b), _mat(b))
    _processado(_hook(client, gw, a, "approved"))
    assert (_pag(b), _mat(b)) == b_antes
    assert _tokens(b) == []
    assert [e["email"] for e in _outbox(ambiente_e9)] == [a.email]
    # e o inverso: reembolsar/charged_back de B por webhook nao toca em A
    _processado(_hook(client, gw, b, "approved", request_id="req-b1"))
    a_antes = (_pag(a), _mat(a))
    _processado(_hook(client, gw, b, "refunded", request_id="req-b2"))
    assert (_pag(a), _mat(a)) == a_antes
    assert _pag(a)["status"] == "approved" and _mat(a) == "active"


# =========================================================================================
# Grupo G - charged_back revoga o acesso (D49.1) e refunded/charged_back so a partir de approved (D49.2)
# =========================================================================================

CURSO_MAT = "curso_e9_materiais"
SENHA_ALUNO = "senha-e9-correta"
MATERIAIS = [
    {"title": "Apostila E9", "url": "https://materiais.test/e9/apostila.pdf", "type": "pdf"},
    {"title": "Video E9", "url": "https://materiais.test/e9/video.mp4", "type": "video"},
]


@pytest.fixture
def curso_materiais(cursos):
    (cursos / f"{CURSO_MAT}.json").write_text(json.dumps({
        "id": CURSO_MAT, "name": "Curso E9 com Materiais", "description": "Curso com materiais pagos",
        "price": PRECO, "materials": MATERIAIS,
    }), encoding="utf-8")
    return CURSO_MAT


def _painel(client, p):
    """Painel do aluno: devolve (texto_da_lista, item_da_lista, texto_do_detalhe) da matricula `p`."""
    login = client.post("/api/token", data={"username": p.email, "password": SENHA_ALUNO})
    assert login.status_code == 200, login.text
    cab = _auth(login.json()["access_token"])
    lista = client.get("/api/student/enrollments", headers=cab)
    assert lista.status_code == 200, lista.text
    corpo = lista.json()
    itens = corpo["enrollments"] if isinstance(corpo, dict) and "enrollments" in corpo else corpo
    item = next(i for i in itens if i["id"] == p.enrollment_id)
    detalhe = client.get(f"/api/student/enrollments/{p.enrollment_id}", headers=cab)
    assert detalhe.status_code == 200, detalhe.text
    return lista.text, item, detalhe.text


def test_g1_charged_back_revoga_o_acesso_e_nenhuma_url_de_material_aparece(client, gw, curso_materiais, ambiente_e9):
    p = _pagamento(com_senha=True, curso=curso_materiais)
    _levar_a(client, gw, p, "approved")
    texto_lista, item, texto_detalhe = _painel(client, p)
    assert item["status"] == "active" and MATERIAIS[0]["url"] in texto_lista, "pre-condicao: matricula ativa ve o material"

    _processado(_hook(client, gw, p, "charged_back", request_id="req-e9-cb"))

    assert _pag(p)["status"] == "charged_back"
    assert _mat(p) == "refunded", "charged_back devolve o dinheiro ao comprador: a matricula vai para refunded"
    texto_lista, item, texto_detalhe = _painel(client, p)
    assert item["status"] == "refunded"
    assert not item.get("materials")
    for texto in (texto_lista, texto_detalhe):
        for material in MATERIAIS:
            assert material["url"] not in texto, f"URL de material vazou depois do chargeback: {material['url']}"

    eventos = [e for e in _eventos("payment.status_change") if str(e["entity_id"]) == str(p.payment_id)]
    assert len(eventos) == 2, eventos
    _checar_status_change(eventos[-1], p, "approved", "charged_back")

    # approved repetido depois do chargeback e ignorado (terminal) e nao reativa nada
    antes = _foto(ambiente_e9)
    _ignorado(_hook(client, gw, p, "approved", request_id="req-e9-cb2"), "terminal")
    assert _foto(ambiente_e9) == antes
    assert _pag(p)["status"] == "charged_back" and _mat(p) == "refunded"
    texto_lista, item, texto_detalhe = _painel(client, p)
    assert item["status"] == "refunded"
    assert all(m["url"] not in texto_lista + texto_detalhe for m in MATERIAIS)


@pytest.mark.parametrize("chega", ["refunded", "charged_back"])
@pytest.mark.parametrize("origem", ["pending", "in_process", "rejected", "cancelled"])
def test_g2_refunded_e_charged_back_so_a_partir_de_approved(client, gw, ambiente_e9, origem, chega):
    p = _pagamento()
    if origem != "pending":
        _levar_a(client, gw, p, origem)
    antes = _foto(ambiente_e9)
    pagamento_antes, matricula_antes = _pag(p), _mat(p)
    r = _hook(client, gw, p, chega, request_id="req-e9-stale")
    _ignorado(r, "stale")
    assert _pag(p) == pagamento_antes and _mat(p) == matricula_antes
    assert _foto(ambiente_e9) == antes, "nem token, nem e-mail, nem evento"


# =========================================================================================
# Grupo H - data.id so aceita digitos ASCII (D49.3) e corpo de sucesso do webhook (D49.4)
# =========================================================================================

IDS_NAO_ASCII = ["١٢٣", "１２３", "12٣", "१२३"]


@pytest.mark.parametrize("data_id", IDS_NAO_ASCII, ids=["arabe_indico", "fullwidth", "misto", "devanagari"])
def test_h1_data_id_com_digitos_de_outros_alfabetos_e_400_sem_gateway(client, gw, ambiente_e9, data_id):
    antes = _foto(ambiente_e9)
    r = post_webhook(client, data_id)  # assinatura valida para o id exato enviado
    assert r.status_code == 400, f"id {data_id!r}: esperado 400, veio {r.status_code} {r.text}"
    assert r.json() == {"detail": DETAIL_ID}, r.text
    assert gw.get_chamadas == [], f"id {data_id!r} chegou ao gateway: {gw.get_chamadas}"
    assert _foto(ambiente_e9) == antes


@pytest.mark.parametrize("status", ["approved", "in_process", "rejected"])
def test_h2_corpo_de_sucesso_do_webhook_processado(client, gw, status):
    p = _pagamento()
    r = _hook(client, gw, p, status)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo.get("status") == "received", corpo
    assert str(corpo.get("payment_id")) == p.mp_id, corpo
    assert corpo.get("payment_status") == status, corpo
    assert corpo.get("external_reference") == p.ref, corpo
