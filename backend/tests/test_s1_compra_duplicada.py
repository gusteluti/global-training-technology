"""S1 - Trava de compra duplicada e retomada de pagamento pendente (D72, modo autonomo D69).

Contrato (D72):
  - Checkout do aluno logado (POST /api/student/checkout): matricula `active` do mesmo curso -> 409
    `Você já está matriculado neste curso.`, sem criar nada e sem chamar o gateway (vale tambem com o mock efetivo,
    PAYMENTS_MOCK=1 + APP_ENV=development).
  - Matricula `pending` do mesmo curso (aluno logado, ou mesmo e-mail na landing) -> RETOMAR: nenhuma matricula nem
    pagamento novos; nova preferencia no gateway com a MESMA external_reference da matricula pendente; a resposta traz
    o novo link. O webhook aprovado com essa referencia ativa a matricula unica. Preco do catalogo mudou -> o valor
    do pagamento pendente e atualizado.
  - Landing (POST /api/payments/create-checkout) com e-mail que ja tem matricula `active` no curso -> 409
    `Este e-mail já tem acesso a este curso. Entre na sua conta para acessá-lo.`
  - `cancelled`/`refunded` nao bloqueiam: nova compra cria matricula nova, como hoje.

Grupos
  A  aluno com `active` -> 409 texto exato, nada criado, gateway nao chamado (fluxo real e mock efetivo)    [red]
  P  aluno com `pending` -> retomada (contagens iguais, mesma referencia, novo link, webhook ativa a unica
     matricula, preco atualizado, material continua oculto)                                                [red]
  L  landing: mesmo e-mail com `pending` retoma; com `active` -> 409 texto exato; sem matricula -> fluxo
     normal                                                                                    [red, exceto L5/L6]
  C  `cancelled`/`refunded` nao bloqueiam                                                     [caracterizacao]
  I  isolamento (outro aluno/curso nao interfere) e IDOR (id/e-mail do corpo ignorados)     [caracterizacao/red]

Checklist: IDOR (grupo I: matricula alheia nunca bloqueia nem e retomada; id/e-mail do corpo nao mudam o dono).
Recurso pago so com `active`: P6 (retomada mantem pending e nao expoe URL de material). 401/403 ja cobertos em
test_o0_checkout_aluno.py (grupo A), rota inalterada. Compatibilidade: C (status antigos seguem criando matricula).

Convencoes (padrao de test_o0/test_e9): banco temporario do conftest, cursos em diretorio temporario, Mercado Pago
falso por patch de `payments.routes.requests.post/get` (nenhuma rede real), webhook assinado com o segredo de teste,
PAYMENTS_MOCK e APP_ENV removidos do ambiente antes de cada teste.
"""

import json
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from apoio_mercado_pago import SEGREDO_WEBHOOK, corpo_pagamento_mp, id_de_pagamento, post_webhook
from core.security import create_access_token, get_password_hash
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
ROTA_ALUNO = "/api/student/checkout"
ROTA_LANDING = "/api/payments/create-checkout"
CURSO = "curso_s1"
OUTRO_CURSO = "curso_s1_outro"
PRECO = 149.9
PRECO_OUTRO = 89.9
NOVO_PRECO = 199.9
URL_MATERIAL = "https://materiais.test/s1/apostila.pdf"
URL_GATEWAY = "https://mp.test/s1/checkout"
ERRO_ALUNO = "Você já está matriculado neste curso."
ERRO_LANDING = "Este e-mail já tem acesso a este curso. Entre na sua conta para acessá-lo."
ACAO_MOCK = "payment.mock_approved"
STATUS_PAGAMENTO = {"pending": "pending", "active": "approved", "cancelled": "cancelled", "refunded": "refunded"}


# =========================================================================================
# Mercado Pago falso: cada preferencia devolve um link diferente (para provar o "novo link")
# =========================================================================================

class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []
        self.get_chamadas = []
        self.pagamentos = {}

    def post(self, url, *args, **kwargs):
        self.post_chamadas.append((url, kwargs))
        n = len(self.post_chamadas)
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": f"pref-s1-{n}", "init_point": f"{URL_GATEWAY}/{n}"}
        resposta.text = json.dumps({"id": f"pref-s1-{n}"})
        return resposta

    def get(self, url, *args, **kwargs):
        self.get_chamadas.append((url, kwargs))
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

    def definir(self, mp_id, status, referencia, valor):
        self.pagamentos[str(mp_id)] = corpo_pagamento_mp(status, referencia, valor, mp_id)

    def preferencia(self, i=-1):
        return self.post_chamadas[i][1]["json"]

    def link(self, i=-1):
        return f"{URL_GATEWAY}/{len(self.post_chamadas) if i == -1 else i + 1}"


@pytest.fixture(autouse=True)
def ambiente_s1(monkeypatch, tmp_path):
    """Mock desligado por padrao; token do gateway e segredo do webhook de teste; nada vem do backend/.env local."""
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-s1")
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", SEGREDO_WEBHOOK)
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


def _gravar_curso(diretorio, course_id, nome, preco, materiais=None):
    (diretorio / f"{course_id}.json").write_text(json.dumps({
        "id": course_id, "name": nome, "description": f"{nome} da S1", "price": preco,
        "materials": materiais or [],
    }), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _gravar_curso(diretorio, CURSO, "Curso S1", PRECO,
                  [{"title": "Apostila S1", "url": URL_MATERIAL, "type": "pdf"}])
    _gravar_curso(diretorio, OUTRO_CURSO, "Outro Curso S1", PRECO_OUTRO)
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    # Sem `with`: nao dispara o startup (agente de chat); checkout e webhook nao dependem dele.
    return TestClient(fastapi_app, raise_server_exceptions=False)


@pytest.fixture
def gw():
    falso = GatewayFalso()
    with patch("payments.routes.requests.post", side_effect=falso.post), \
         patch("payments.routes.requests.get", side_effect=falso.get):
        yield falso


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
    return {"Authorization": f"Bearer {token}"}


def _conta(email, nome, senha="senha-s1-123"):
    user_id = Database.add_user(email, nome, get_password_hash(senha), role="student")
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": "student"})
    return SimpleNamespace(id=user_id, email=email, name=nome, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        ana=_conta("ana.aluna@s1.test", "Ana Aluna"),
        bia=_conta("bia.aluna@s1.test", "Bia Aluna"),
    )


def _semear_matricula(user_id, status, course_id=CURSO, valor=PRECO):
    """Matricula com o status pedido e o pagamento coerente (gravados pela camada Database + SQL de seed)."""
    referencia = f"{course_id}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(user_id, course_id, referencia)
    payment_id = Database.record_payment(enrollment_id, valor, "mercado_pago")
    _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))
    _executar("UPDATE payments SET status = ? WHERE id = ?", (STATUS_PAGAMENTO[status], payment_id))
    return SimpleNamespace(id=enrollment_id, payment_id=payment_id, ref=referencia)


def _comprar(client, token, **corpo):
    payload = {"course_id": CURSO}
    payload.update(corpo)
    return client.post(ROTA_ALUNO, json=payload, headers=_auth(token))


def _comprar_landing(client, email, course_id=CURSO, nome="Comprador Landing"):
    return client.post(ROTA_LANDING, json={"course_id": course_id, "payer": {"name": nome, "email": email}})


def _contagens():
    return {
        "users": len(_sql("SELECT id FROM users")),
        "enrollments": len(_sql("SELECT id FROM enrollments")),
        "payments": len(_sql("SELECT id FROM payments")),
    }


def _foto():
    """Estado completo de matriculas e pagamentos (para provar 'nada mudou')."""
    return (
        _sql("SELECT id, user_id, course_id, status, external_reference FROM enrollments ORDER BY id"),
        _sql("SELECT id, enrollment_id, amount, status, payment_method, transaction_id FROM payments ORDER BY id"),
    )


def _matriculas(user_id, course_id=CURSO):
    return _sql("SELECT * FROM enrollments WHERE user_id = ? AND course_id = ? ORDER BY id", (user_id, course_id))


def _pagamento(payment_id):
    return _sql("SELECT * FROM payments WHERE id = ?", (payment_id,))[0]


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _ligar_mock_efetivo(monkeypatch):
    monkeypatch.setenv("PAYMENTS_MOCK", "1")
    monkeypatch.setenv("APP_ENV", "development")


def _assert_409(r, texto):
    assert r.status_code == 409, r.text
    assert r.json() == {"detail": texto}, r.text


def _assert_retomada(r, gw, pendente, contagens_antes, chamadas_esperadas=1):
    """Retomada: 200, nada novo no banco, mesma referencia na preferencia e na resposta, link novo."""
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert _contagens() == contagens_antes, "retomada nao pode criar matricula, pagamento nem conta"
    assert len(gw.post_chamadas) == chamadas_esperadas, "a retomada gera uma nova preferencia no gateway"
    assert gw.preferencia()["external_reference"] == pendente.ref, (
        "a nova preferencia tem de usar a external_reference da matricula pendente")
    assert corpo.get("external_reference") == pendente.ref, corpo
    assert corpo.get("checkout_url") == gw.link(), f"a resposta tem de trazer o novo link: {corpo}"
    assert not corpo.get("mocked"), corpo
    matricula = _sql("SELECT * FROM enrollments WHERE id = ?", (pendente.id,))[0]
    assert matricula["status"] == "pending", matricula
    assert matricula["external_reference"] == pendente.ref, matricula
    assert _pagamento(pendente.payment_id)["status"] == "pending"
    return corpo


def _aprovar_pelo_webhook(client, gw, referencia, valor):
    mp_id = id_de_pagamento(referencia)
    gw.definir(mp_id, "approved", referencia, valor)
    r = post_webhook(client, mp_id)
    assert r.status_code == 200, r.text
    return r


# =========================================================================================
# Grupo A - aluno com matricula `active` no mesmo curso: 409
# =========================================================================================

def test_a1_aluno_com_matricula_ativa_recebe_409_com_texto_exato(client, gw, contas):
    _semear_matricula(contas.ana.id, "active")
    antes = _foto()
    r = _comprar(client, contas.ana.token)
    _assert_409(r, ERRO_ALUNO)
    assert gw.post_chamadas == [], "com matricula ativa o gateway nao pode ser chamado"
    assert _foto() == antes, "com matricula ativa nada pode ser criado nem alterado"


def test_a2_aluno_com_matricula_ativa_recebe_409_tambem_com_mock_efetivo(client, gw, contas, monkeypatch):
    _semear_matricula(contas.ana.id, "active")
    _ligar_mock_efetivo(monkeypatch)
    antes = _foto()
    usuarios = _contagens()["users"]
    r = _comprar(client, contas.ana.token)
    _assert_409(r, ERRO_ALUNO)
    assert gw.post_chamadas == []
    assert _foto() == antes, "o mock efetivo nao pode criar uma segunda matricula"
    assert _contagens()["users"] == usuarios
    assert _eventos(ACAO_MOCK) == [], "nenhum pagamento simulado pode ser registrado"


def test_a3_ativa_prevalece_sobre_pendente_do_mesmo_curso(client, gw, contas):
    """Dado antigo com ativa e pendente no mesmo curso: a ativa bloqueia (nao cobrar duas vezes)."""
    _semear_matricula(contas.ana.id, "active")
    _semear_matricula(contas.ana.id, "pending")
    antes = _foto()
    r = _comprar(client, contas.ana.token)
    _assert_409(r, ERRO_ALUNO)
    assert gw.post_chamadas == []
    assert _foto() == antes


def test_a4_campos_do_corpo_nao_contornam_a_trava(client, gw, contas):
    """IDOR: id/e-mail de outro aluno no corpo nao trocam o dono da compra nem liberam a segunda compra."""
    _semear_matricula(contas.ana.id, "active")
    antes = _foto()
    r = _comprar(client, contas.ana.token, user_id=contas.bia.id, email=contas.bia.email,
                 payer={"email": contas.bia.email, "name": "Bia"})
    _assert_409(r, ERRO_ALUNO)
    assert gw.post_chamadas == []
    assert _foto() == antes
    assert _matriculas(contas.bia.id) == []


# =========================================================================================
# Grupo P - aluno com matricula `pending` no mesmo curso: retomada
# =========================================================================================

def test_p1_pendente_retoma_sem_criar_matricula_nem_pagamento(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    antes = _contagens()
    r = _comprar(client, contas.ana.token)
    _assert_retomada(r, gw, pendente, antes)
    assert len(_matriculas(contas.ana.id)) == 1


def test_p2_preferencia_da_retomada_usa_dados_do_dono_e_preco_do_catalogo(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, _contagens())
    preferencia = gw.preferencia()
    assert preferencia["items"][0]["unit_price"] == PRECO, preferencia["items"]
    assert preferencia["items"][0]["id"] == CURSO, preferencia["items"]
    assert preferencia["payer"]["email"] == contas.ana.email, preferencia["payer"]
    assert _pagamento(pendente.payment_id)["amount"] == PRECO


def test_p3_retomar_duas_vezes_continua_com_uma_matricula_e_link_novo_a_cada_vez(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    antes = _contagens()
    primeira = _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, antes, chamadas_esperadas=1)
    segunda = _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, antes, chamadas_esperadas=2)
    assert primeira["checkout_url"] != segunda["checkout_url"], "cada retomada devolve o link novo do gateway"
    assert all(c[1]["json"]["external_reference"] == pendente.ref for c in gw.post_chamadas)


def test_p4_compra_nova_seguida_de_retomada_reaproveita_a_matricula_criada(client, gw, contas):
    """Fluxo completo pela API: a primeira compra cria a pendente; a segunda a retoma."""
    r1 = _comprar(client, contas.ana.token)
    assert r1.status_code == 200, r1.text
    ref = r1.json()["external_reference"]
    matriculas = _matriculas(contas.ana.id)
    assert len(matriculas) == 1 and matriculas[0]["status"] == "pending", matriculas
    antes = _contagens()
    r2 = _comprar(client, contas.ana.token)
    assert r2.status_code == 200, r2.text
    assert _contagens() == antes, "a segunda compra do mesmo curso pendente nao pode criar nada"
    assert r2.json()["external_reference"] == ref
    assert gw.preferencia()["external_reference"] == ref
    assert r2.json()["checkout_url"] == gw.link()


def test_p5_webhook_aprovado_com_a_referencia_retomada_ativa_a_matricula_unica(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, _contagens())
    _aprovar_pelo_webhook(client, gw, pendente.ref, PRECO)
    matriculas = _matriculas(contas.ana.id)
    assert len(matriculas) == 1, matriculas
    assert matriculas[0]["id"] == pendente.id and matriculas[0]["status"] == "active", matriculas
    pagamentos = _sql("SELECT * FROM payments WHERE enrollment_id = ?", (pendente.id,))
    assert len(pagamentos) == 1 and pagamentos[0]["status"] == "approved", pagamentos
    # Depois de ativa, nova tentativa de compra e bloqueada.
    _assert_409(_comprar(client, contas.ana.token), ERRO_ALUNO)


def test_p6_retomada_nao_libera_material(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, _contagens())
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert URL_MATERIAL not in r.text, "matricula pendente retomada nao pode expor material"


def test_p7_preco_mudado_no_catalogo_atualiza_o_valor_do_pagamento_pendente(client, gw, contas, cursos):
    pendente = _semear_matricula(contas.ana.id, "pending", valor=PRECO)
    _gravar_curso(cursos, CURSO, "Curso S1", NOVO_PRECO,
                  [{"title": "Apostila S1", "url": URL_MATERIAL, "type": "pdf"}])
    _assert_retomada(_comprar(client, contas.ana.token), gw, pendente, _contagens())
    assert gw.preferencia()["items"][0]["unit_price"] == NOVO_PRECO, gw.preferencia()["items"]
    assert _pagamento(pendente.payment_id)["amount"] == NOVO_PRECO, "o pagamento pendente segue o preco atual"
    _aprovar_pelo_webhook(client, gw, pendente.ref, NOVO_PRECO)
    assert _matriculas(contas.ana.id)[0]["status"] == "active"


# =========================================================================================
# Grupo L - landing (anonima), pelo e-mail
# =========================================================================================

def test_l1_landing_mesmo_email_com_pendente_retoma(client, gw, contas):
    pendente = _semear_matricula(contas.ana.id, "pending")
    antes = _contagens()
    r = _comprar_landing(client, contas.ana.email)
    _assert_retomada(r, gw, pendente, antes)
    assert gw.preferencia()["items"][0]["unit_price"] == PRECO
    assert len(_matriculas(contas.ana.id)) == 1


def test_l2_landing_retomada_e_ativada_pelo_webhook(client, gw, contas, cursos):
    pendente = _semear_matricula(contas.ana.id, "pending")
    _gravar_curso(cursos, CURSO, "Curso S1", NOVO_PRECO)
    _assert_retomada(_comprar_landing(client, contas.ana.email), gw, pendente, _contagens())
    assert _pagamento(pendente.payment_id)["amount"] == NOVO_PRECO
    _aprovar_pelo_webhook(client, gw, pendente.ref, NOVO_PRECO)
    matriculas = _matriculas(contas.ana.id)
    assert len(matriculas) == 1 and matriculas[0]["status"] == "active", matriculas


def test_l3_landing_compra_anonima_repetida_retoma_a_primeira(client, gw):
    """Sem conta previa: a primeira compra cria conta e pendente; a segunda com o mesmo e-mail retoma."""
    email = "anonimo.repetido@s1.test"
    r1 = _comprar_landing(client, email)
    assert r1.status_code == 200, r1.text
    ref = r1.json()["external_reference"]
    antes = _contagens()
    r2 = _comprar_landing(client, email)
    assert r2.status_code == 200, r2.text
    assert _contagens() == antes, "a segunda compra do mesmo e-mail pendente nao pode criar nada"
    assert r2.json()["external_reference"] == ref
    assert gw.preferencia()["external_reference"] == ref
    assert r2.json()["checkout_url"] == gw.link()


def test_l4_landing_email_com_matricula_ativa_recebe_409_com_texto_exato(client, gw, contas):
    _semear_matricula(contas.ana.id, "active")
    antes = _foto()
    usuarios = _contagens()["users"]
    r = _comprar_landing(client, contas.ana.email)
    _assert_409(r, ERRO_LANDING)
    assert gw.post_chamadas == []
    assert _foto() == antes
    assert _contagens()["users"] == usuarios


def test_l4b_landing_email_com_matricula_ativa_recebe_409_tambem_com_mock_efetivo(client, gw, contas, monkeypatch):
    _semear_matricula(contas.ana.id, "active")
    _ligar_mock_efetivo(monkeypatch)
    antes = _foto()
    r = _comprar_landing(client, contas.ana.email)
    _assert_409(r, ERRO_LANDING)
    assert gw.post_chamadas == []
    assert _foto() == antes
    assert _eventos(ACAO_MOCK) == []


def test_l5_landing_email_sem_matricula_segue_fluxo_normal(client, gw, contas):
    """[caracterizacao] e-mail sem matricula no curso: cria matricula e pagamento pending, como hoje."""
    antes = _contagens()
    r = _comprar_landing(client, "novo.comprador@s1.test")
    assert r.status_code == 200, r.text
    depois = _contagens()
    assert depois["enrollments"] == antes["enrollments"] + 1
    assert depois["payments"] == antes["payments"] + 1
    ref = r.json()["external_reference"]
    m = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))
    assert len(m) == 1 and m[0]["status"] == "pending", m
    assert gw.preferencia()["external_reference"] == ref


def test_l6_landing_email_com_matricula_em_outro_curso_segue_fluxo_normal(client, gw, contas):
    """[caracterizacao] matricula ativa em OUTRO curso nao bloqueia nem e retomada."""
    outra = _semear_matricula(contas.ana.id, "active", course_id=OUTRO_CURSO, valor=PRECO_OUTRO)
    antes = _contagens()
    r = _comprar_landing(client, contas.ana.email)
    assert r.status_code == 200, r.text
    assert _contagens()["enrollments"] == antes["enrollments"] + 1
    assert r.json()["external_reference"] != outra.ref


# =========================================================================================
# Grupo C - `cancelled` e `refunded` nao bloqueiam [caracterizacao]
# =========================================================================================

@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_c1_aluno_com_matricula_cancelada_ou_reembolsada_compra_de_novo(client, gw, contas, status):
    antiga = _semear_matricula(contas.ana.id, status)
    antes = _contagens()
    r = _comprar(client, contas.ana.token)
    assert r.status_code == 200, r.text
    assert _contagens()["enrollments"] == antes["enrollments"] + 1
    assert _contagens()["payments"] == antes["payments"] + 1
    ref = r.json()["external_reference"]
    assert ref != antiga.ref, "a matricula antiga nao pode ser reaproveitada"
    assert gw.preferencia()["external_reference"] == ref
    assert _sql("SELECT status FROM enrollments WHERE id = ?", (antiga.id,))[0]["status"] == status


@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_c2_landing_email_com_matricula_cancelada_ou_reembolsada_compra_de_novo(client, gw, contas, status):
    antiga = _semear_matricula(contas.ana.id, status)
    antes = _contagens()
    r = _comprar_landing(client, contas.ana.email)
    assert r.status_code == 200, r.text
    assert _contagens()["enrollments"] == antes["enrollments"] + 1
    assert r.json()["external_reference"] != antiga.ref


# =========================================================================================
# Grupo I - isolamento e IDOR
# =========================================================================================

@pytest.mark.parametrize("status", ["active", "pending"])
def test_i1_matricula_de_outro_aluno_no_mesmo_curso_nao_interfere(client, gw, contas, status):
    """[caracterizacao] a matricula da Bia nao bloqueia nem e retomada pela compra da Ana."""
    da_bia = _semear_matricula(contas.bia.id, status)
    foto_bia = _sql("SELECT * FROM enrollments WHERE id = ?", (da_bia.id,)), _pagamento(da_bia.payment_id)
    r = _comprar(client, contas.ana.token)
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] != da_bia.ref
    assert len(_matriculas(contas.ana.id)) == 1
    assert (_sql("SELECT * FROM enrollments WHERE id = ?", (da_bia.id,)), _pagamento(da_bia.payment_id)) == foto_bia


@pytest.mark.parametrize("status", ["active", "pending"])
def test_i2_matricula_do_aluno_em_outro_curso_nao_interfere(client, gw, contas, status):
    """[caracterizacao]"""
    outra = _semear_matricula(contas.ana.id, status, course_id=OUTRO_CURSO, valor=PRECO_OUTRO)
    r = _comprar(client, contas.ana.token)
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] != outra.ref
    assert len(_matriculas(contas.ana.id)) == 1
    assert _pagamento(outra.payment_id)["amount"] == PRECO_OUTRO


@pytest.mark.parametrize("status", ["active", "pending"])
def test_i3_idor_id_e_email_de_outro_aluno_no_corpo_sao_ignorados(client, gw, contas, status):
    """A Bia tem matricula no curso; a Ana (sem matricula) manda o id/e-mail da Bia no corpo: compra normal da Ana,
    sem 409 e sem retomar a pendente da Bia. [caracterizacao]"""
    da_bia = _semear_matricula(contas.bia.id, status)
    pagamento_bia = _pagamento(da_bia.payment_id)
    r = _comprar(client, contas.ana.token, user_id=contas.bia.id, email=contas.bia.email,
                 payer={"email": contas.bia.email, "name": "Bia"})
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] != da_bia.ref
    assert gw.preferencia()["external_reference"] != da_bia.ref
    assert gw.preferencia()["payer"]["email"] == contas.ana.email
    assert len(_matriculas(contas.ana.id)) == 1
    assert len(_matriculas(contas.bia.id)) == 1
    assert _pagamento(da_bia.payment_id) == pagamento_bia


def test_i4_idor_retomada_usa_so_a_pendente_do_dono_do_jwt(client, gw, contas):
    """Ana e Bia com pendente no curso; Ana manda o id da Bia no corpo: retoma a da Ana, nunca a da Bia."""
    da_ana = _semear_matricula(contas.ana.id, "pending")
    da_bia = _semear_matricula(contas.bia.id, "pending")
    pagamento_bia = _pagamento(da_bia.payment_id)
    antes = _contagens()
    r = _comprar(client, contas.ana.token, user_id=contas.bia.id, email=contas.bia.email)
    _assert_retomada(r, gw, da_ana, antes)
    assert _pagamento(da_bia.payment_id) == pagamento_bia
