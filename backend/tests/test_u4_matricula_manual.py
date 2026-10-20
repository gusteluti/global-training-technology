"""U4/S6 - Matricula manual pela Gestao e expiracao de pendente (D81, modo autonomo D69).

Escritos ANTES da implementacao. Contrato (D81):
  U4: POST /api/admin/enrollments (so Gestao) {email, name?, course_id, class_id?, reason, amount?}.
    - `reason` obrigatorio, 5 a 300 caracteres aparados; `amount` >= 0, padrao 0 (cortesia).
    - Curso inexistente/arquivado -> 404 `Course not found`; turma pelas regras da D75 (404 `Turma não encontrada`,
      409 `Esta turma está lotada. Escolha outra turma.`); aluno ja `active` no curso -> 409
      `O aluno já está matriculado neste curso.`; e-mail de funcionario -> 409 `Este e-mail pertence a um funcionário.`
    - Conta inexistente e criada (aluno sem senha) e recebe o link de definicao de senha da E2 (mesmo mecanismo).
    - Cria matricula `active` e pagamento `approved` com `payment_method` `manual` e o valor informado, numa transacao;
      `pending` existente do mesmo curso e reaproveitada (vira `active`) em vez de criar outra.
    - Evento `enrollment.manual` com motivo, valor, curso e turma. Recibo do aluno: "Matrícula manual".
  S6: pagamento `pending` (e a matricula `pending` dele) criado ha mais de 7 dias -> `cancelled` (os dois), liberando a
    vaga. `Database.expirar_pendentes()` no startup e antes das leituras de dashboard, listas do aluno e checkout;
    idempotente; cada expiracao grava `payment.expired`. Webhook `approved` depois da expiracao reativa a matricula
    (regra da S8 para a turma) e grava `payment.approved_after_expiry`. Retomada (D72) so vale para `pending`.

Escolhas conservadoras do agente-testes (o contrato nao fixa; registradas no relatorio):
  - Sucesso da matricula manual: 200 ou 201; o corpo nao e fixado (o teste confere o banco e as rotas de leitura).
  - Validacao (`reason`, `amount`, e-mail, campos obrigatorios): 422, sem fixar texto, e nada e gravado.
  - Recibo: JSON traz o valor bruto `payment_method` = `manual` (padrao da E4: o JSON e bruto e a tela traduz);
    o PDF traz o rotulo "Matrícula manual" (D81: o recibo do aluno mostra a forma em portugues).
  - Pendente reaproveitada: nenhuma matricula nova e nenhum pagamento da matricula fica `pending` (senao a S6
    expiraria depois e cancelaria uma matricula ativa); ha um pagamento `approved`/`manual` com o valor.
  - Conta existente: nao ganha conta nova, nao perde a senha, nao recebe link de definicao e o nome nao e trocado.
  - Atomicidade: um gatilho SQLite de teste aborta a gravacao do pagamento `manual`; a resposta nao e 2xx e nao fica
    matricula nem pagamento novo, nem link enviado, nem evento; a pendente reaproveitada continua `pending`.
    (A conta criada antes da falha nao e conferida: a D81 so poe matricula e pagamento na transacao.)
  - Expiracao via leitura: cada rota de leitura listada (dashboard e listas do aluno) expira por si so.
  - "Mais de 7 dias" conta a partir de `payments.created_at` (UTC, formato de CURRENT_TIMESTAMP); o teste envelhece
    tambem `enrollments.enrolled_at` e `reserved_until` para nao depender de qual coluna o dev le.

Grupos
  A  RBAC: so Gestao (JWT e login legado); Financeiro/Suporte/aluno 403; sem token/forjado 401        [red]
  V  validacoes: reason, amount, e-mail, campos obrigatorios -> 422 sem gravar nada                    [red]
  C  curso inexistente/arquivado/id invalido 404; turma 404/409; ja ativo 409; funcionario 409         [red]
  N  conta nova sem senha + link de definicao da E2 (outbox) que funciona; conta existente reaproveitada [red]
  P  pagamento approved/manual com valor; cortesia 0; pendente reaproveitada; turma ocupa vaga          [red]
  L  leitura: aluno ve active com materiais; financeiro conta o valor; recibo JSON/PDF; evento          [red]
  T  atomicidade (gatilho de teste)                                                                     [red]
  I  IDOR: user_id no corpo ignorado                                                                    [red]
  E  S6: expirar_pendentes (7 dias), limite, idempotencia, vaga, evento, startup, leituras, checkout    [red]
  W  S6: webhook approved depois da expiracao (reativa, evento, regra S8)                               [red]
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from apoio_mercado_pago import SEGREDO_WEBHOOK, corpo_pagamento_mp, id_de_pagamento, post_webhook
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"
ROTA_MANUAL = "/api/admin/enrollments"
ROTA_ALUNO = "/api/student/checkout"
ROTA_LANDING = "/api/payments/create-checkout"
CURSO = "curso_u4"
OUTRO_CURSO = "curso_u4_outro"
ARQUIVADO = "curso_u4_arquivado"
PRECO = 199.9
PRECO_OUTRO = 79.9
URL_MATERIAL = "https://materiais.test/u4/apostila.pdf"
URL_GATEWAY = "https://mp.test/u4/checkout"
SENHA = "senha-u4-forte-2026"
MOTIVO = "Bolsa integral concedida pela diretoria"
ERR_CURSO = "Course not found"
ERR_TURMA = "Turma não encontrada"
ERR_LOTADA = "Esta turma está lotada. Escolha outra turma."
ERR_JA_ATIVO = "O aluno já está matriculado neste curso."
ERR_FUNCIONARIO = "Este e-mail pertence a um funcionário."
EVENTO_MANUAL = "enrollment.manual"
EVENTO_EXPIRADO = "payment.expired"
EVENTO_APOS_EXPIRAR = "payment.approved_after_expiry"
EVENTO_OVERFLOW = "enrollment.class_overflow"
ROTULO_MANUAL = "Matrícula manual"
STATUS_PAGAMENTO = {"pending": "pending", "active": "approved", "cancelled": "cancelled", "refunded": "refunded"}


# =========================================================================================
# Ambiente, cursos, cliente e gateway falso
# =========================================================================================

@pytest.fixture(autouse=True)
def ambiente_u4(monkeypatch, tmp_path):
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-u4")
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", SEGREDO_WEBHOOK)
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:8000")


def _gravar_curso(diretorio, course_id, nome, preco, materiais=None, arquivado=False):
    dados = {"id": course_id, "name": nome, "description": f"{nome} da U4", "price": preco,
             "materials": materiais or []}
    if arquivado:
        dados["archived"] = True
    (diretorio / f"{course_id}.json").write_text(json.dumps(dados), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    antes = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _gravar_curso(diretorio, CURSO, "Curso U4", PRECO, [{"title": "Apostila U4", "url": URL_MATERIAL, "type": "pdf"}])
    _gravar_curso(diretorio, OUTRO_CURSO, "Outro Curso U4", PRECO_OUTRO)
    _gravar_curso(diretorio, ARQUIVADO, "Curso Arquivado U4", PRECO, arquivado=True)
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    yield diretorio
    depois = sorted(p.name for p in REPO_COURSES.glob("*.json")) if REPO_COURSES.exists() else []
    assert depois == antes, "o teste nao pode alterar backend/courses"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    # Sem `with`: nao dispara o startup (o startup e conferido a parte, no grupo E).
    return TestClient(fastapi_app, raise_server_exceptions=False)


class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []
        self.pagamentos = {}

    def post(self, url, *args, **kwargs):
        self.post_chamadas.append((url, kwargs))
        n = len(self.post_chamadas)
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": f"pref-u4-{n}", "init_point": f"{URL_GATEWAY}/{n}"}
        resposta.text = json.dumps({"id": f"pref-u4-{n}"})
        return resposta

    def get(self, url, *args, **kwargs):
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
    return {"Authorization": f"Bearer {token}"} if token else {}


def _conta(email, nome, perfil="student", senha=SENHA):
    user_id = Database.add_user(email, nome, get_password_hash(senha) if senha else None, role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, name=nome, token=token)


@pytest.fixture
def contas(client):
    return SimpleNamespace(
        gestao=_conta("gestao.u4@teste.com", "Gestora U4", "admin"),
        fin=_conta("fin.u4@teste.com", "Financeira U4", "financial"),
        sup=_conta("sup.u4@teste.com", "Suporte U4", "support"),
        ana=_conta("ana.u4@teste.com", "Ana Aluna U4"),
        bia=_conta("bia.u4@teste.com", "Bia Aluna U4"),
    )


def _token_de(user_id, email):
    return create_access_token({"user_id": user_id, "email": email, "role": "student"})


def _forjado(role="admin"):
    return jose_jwt.encode({"user_id": 1, "email": "x@u4.test", "role": role},
                           "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")


def _manual(client, token, **corpo):
    payload = {"email": "novo.u4@teste.com", "name": "Novo Aluno U4", "course_id": CURSO, "reason": MOTIVO}
    payload.update(corpo)
    payload = {k: v for k, v in payload.items() if v is not _AUSENTE}
    return client.post(ROTA_MANUAL, json=payload, headers=_auth(token))


_AUSENTE = object()


def _manual_ok(client, token, **corpo):
    r = _manual(client, token, **corpo)
    assert r.status_code in (200, 201), r.text
    return r


def _usuario(email):
    linhas = _sql("SELECT * FROM users WHERE email = ?", (email,))
    return linhas[0] if linhas else None


def _matriculas(user_id, course_id=CURSO):
    return _sql("SELECT * FROM enrollments WHERE user_id = ? AND course_id = ? ORDER BY id", (user_id, course_id))


def _matricula(enrollment_id):
    return _sql("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,))[0]


def _pagamentos_da_matricula(enrollment_id):
    return _sql("SELECT * FROM payments WHERE enrollment_id = ? ORDER BY id", (enrollment_id,))


def _pagamento(payment_id):
    return _sql("SELECT * FROM payments WHERE id = ?", (payment_id,))[0]


def _unica_matricula_ativa(user_id, course_id=CURSO):
    ativas = [m for m in _matriculas(user_id, course_id) if m["status"] == "active"]
    assert len(ativas) == 1, f"esperada 1 matricula active do usuario {user_id} em {course_id}: {ativas}"
    return ativas[0]


def _pagamento_manual(enrollment_id):
    manuais = [p for p in _pagamentos_da_matricula(enrollment_id) if p["payment_method"] == "manual"]
    assert len(manuais) == 1, f"esperado 1 pagamento manual na matricula {enrollment_id}: " \
                              f"{_pagamentos_da_matricula(enrollment_id)}"
    return manuais[0]


def _foto():
    return (
        _sql("SELECT * FROM enrollments ORDER BY id"),
        _sql("SELECT * FROM payments ORDER BY id"),
        _sql("SELECT id, email, name, password_hash, role FROM users ORDER BY id"),
    )


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _texto(linha):
    return json.dumps(linha, ensure_ascii=False, default=str)


def _assert_erro(r, status, texto):
    assert r.status_code == status, r.text
    assert r.json() == {"detail": texto}, r.text


def _outbox(tmp_path):
    caminho = tmp_path / "outbox.jsonl"
    if not caminho.exists():
        return []
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _links_de_definicao(tmp_path, email):
    return [m for m in _outbox(tmp_path)
            if m.get("email") == email and "/definir-senha?token=" in str(m.get("link", ""))]


def _turma(nome, course_id=CURSO, capacity=None, dias=10):
    inicio = ((datetime.now(timezone.utc) - timedelta(hours=3)).date() + timedelta(days=dias)).isoformat()
    class_id = Database.create_class(course_id, nome, inicio, capacity)
    assert class_id is not None, f"seed: turma {nome} ja existe"
    return class_id


def _semear(user_id, status, course_id=CURSO, class_id=None, valor=PRECO, metodo="mercado_pago"):
    """Matricula com status e pagamento coerentes, sem reserved_until (como a Gestao ou antes da F5a)."""
    referencia = f"{course_id}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(user_id, course_id, referencia)
    payment_id = Database.record_payment(enrollment_id, valor, metodo)
    _executar("UPDATE enrollments SET status = ?, class_id = ? WHERE id = ?", (status, class_id, enrollment_id))
    _executar("UPDATE payments SET status = ? WHERE id = ?", (STATUS_PAGAMENTO[status], payment_id))
    return SimpleNamespace(id=enrollment_id, payment_id=payment_id, ref=referencia)


def _aluno_avulso(status, class_id=None, course_id=CURSO):
    sufixo = uuid.uuid4().hex[:8]
    user_id = Database.get_or_create_user(f"avulso.{sufixo}@u4.test", f"Avulso {sufixo}")
    return _semear(user_id, status, course_id=course_id, class_id=class_id)


def _texto_utc(instante):
    return instante.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _envelhecer(semente, idade):
    """Leva created_at do pagamento (e enrolled_at/reserved_until da matricula) para agora - idade, em UTC."""
    instante = _texto_utc(datetime.now(timezone.utc) - idade)
    _executar("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?",
              (instante, instante, semente.payment_id))
    _executar("UPDATE enrollments SET enrolled_at = ? WHERE id = ?", (instante, semente.id))
    _executar("UPDATE enrollments SET reserved_until = ? WHERE id = ? AND reserved_until IS NOT NULL",
              (_texto_utc(datetime.now(timezone.utc) - idade + timedelta(minutes=30)), semente.id))


VELHA = timedelta(days=7, hours=1)
QUASE = timedelta(days=6, hours=23)


def _status(semente):
    return _matricula(semente.id)["status"], _pagamento(semente.payment_id)["status"]


def _expirar():
    assert hasattr(Database, "expirar_pendentes"), "D81: falta Database.expirar_pendentes()"
    return Database.expirar_pendentes()


def _seats_left(client, class_id, course_id=CURSO):
    r = client.get(f"/api/courses/{course_id}/turmas")
    assert r.status_code == 200, r.text
    achadas = [t for t in r.json() if t["id"] == class_id]
    assert len(achadas) == 1, r.json()
    return achadas[0]["seats_left"]


def _aprovar_pelo_webhook(client, gw, referencia, valor=PRECO):
    mp_id = id_de_pagamento(referencia)
    gw.definir(mp_id, "approved", referencia, valor)
    r = post_webhook(client, mp_id)
    assert r.status_code == 200, r.text
    return r


_RE_PDF_OBJ = re.compile(rb"(?m)^(\d+) 0 obj\b(.*?)endobj", re.DOTALL)


def _texto_do_pdf(corpo: bytes) -> str:
    """Strings literais de todos os streams (cp1252), como em test_b2_recibo_pdf (copia minima)."""
    saida = []
    for m in _RE_PDF_OBJ.finditer(corpo):
        obj = m.group(2)
        ms = re.search(rb"(?<!end)stream\r?\n", obj)
        if not ms:
            continue
        dados = obj[ms.end():]
        dados = dados[:dados.rfind(b"endstream")]
        i, n = 0, len(dados)
        while i < n:
            if dados[i] != 0x28:
                i += 1
                continue
            prof, buf = 1, bytearray()
            i += 1
            while i < n:
                c = dados[i]
                if c == 0x5C:
                    i += 1
                    if i >= n:
                        break
                    p = dados[i]
                    if 0x30 <= p <= 0x37:
                        octal = bytes([p])
                        while len(octal) < 3 and i + 1 < n and 0x30 <= dados[i + 1] <= 0x37:
                            i += 1
                            octal += bytes([dados[i]])
                        buf.append(int(octal, 8) & 0xFF)
                    elif p not in (10, 13):
                        buf.append({ord("n"): 10, ord("r"): 13, ord("t"): 9}.get(p, p))
                elif c == 0x28:
                    prof += 1
                    buf.append(c)
                elif c == 0x29:
                    prof -= 1
                    if prof == 0:
                        break
                    buf.append(c)
                else:
                    buf.append(c)
                i += 1
            saida.append(bytes(buf).decode("cp1252", errors="replace"))
            i += 1
    return "\n".join(saida)


# =========================================================================================
# Grupo A - RBAC
# =========================================================================================

def test_a1_gestao_por_jwt_matricula(client, contas):
    r = _manual(client, contas.gestao.token, email=contas.ana.email)
    assert r.status_code in (200, 201), r.text
    _unica_matricula_ativa(contas.ana.id)


def test_a2_gestao_pelo_login_legado_matricula(client, contas):
    r = _manual(client, create_admin_token(Role.ADMIN), email=contas.ana.email)
    assert r.status_code in (200, 201), r.text
    _unica_matricula_ativa(contas.ana.id)


@pytest.mark.parametrize("perfil", ["fin", "sup", "ana", "fin_legado", "sup_legado"])
def test_a3_financeiro_suporte_e_aluno_403_sem_gravar(client, contas, perfil):
    token = {
        "fin": contas.fin.token, "sup": contas.sup.token, "ana": contas.ana.token,
        "fin_legado": create_admin_token(Role.FINANCIAL), "sup_legado": create_admin_token(Role.SUPPORT),
    }[perfil]
    antes = _foto()
    r = _manual(client, token, email=contas.bia.email)
    assert r.status_code == 403, r.text
    assert _foto() == antes
    assert _eventos(EVENTO_MANUAL) == []


@pytest.mark.parametrize("token", [None, "forjado", "lixo"])
def test_a4_sem_token_forjado_ou_invalido_401_sem_gravar(client, contas, token):
    valor = {None: None, "forjado": _forjado(), "lixo": "nao-e-um-token"}[token]
    antes = _foto()
    r = _manual(client, valor, email=contas.bia.email)
    assert r.status_code == 401, r.text
    assert _foto() == antes


# =========================================================================================
# Grupo V - validacoes (422 sem gravar nada)
# =========================================================================================

@pytest.mark.parametrize("motivo", [_AUSENTE, "", "    ", "abcd", "  abcd  ", "x" * 301, "  " + "x" * 301])
def test_v1_motivo_obrigatorio_de_5_a_300_aparados_422(client, contas, motivo):
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, reason=motivo)
    assert r.status_code == 422, r.text
    assert _foto() == antes
    assert _eventos(EVENTO_MANUAL) == []


@pytest.mark.parametrize("motivo", ["abcde", "  abcde  ", "x" * 300, "  " + "x" * 300 + "  "])
def test_v2_motivo_nos_limites_e_aceito(client, contas, motivo):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, reason=motivo)
    _unica_matricula_ativa(contas.ana.id)


@pytest.mark.parametrize("valor", [-0.01, -1, "abc"])
def test_v3_valor_negativo_ou_invalido_422(client, contas, valor):
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, amount=valor)
    assert r.status_code == 422, r.text
    assert _foto() == antes


@pytest.mark.parametrize("email", [_AUSENTE, "", "nao-e-um-email", "sem-dominio@", "@sem-usuario.com"])
def test_v4_email_ausente_ou_invalido_422(client, contas, email):
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=email)
    assert r.status_code == 422, r.text
    assert _foto() == antes


def test_v5_curso_ausente_422(client, contas):
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, course_id=_AUSENTE)
    assert r.status_code == 422, r.text
    assert _foto() == antes


# =========================================================================================
# Grupo C - curso, turma, ja ativo, funcionario
# =========================================================================================

@pytest.mark.parametrize("course_id", ["curso_que_nao_existe", ARQUIVADO, "../etc/passwd", "Curso Invalido!"])
def test_c1_curso_inexistente_arquivado_ou_id_invalido_404(client, contas, course_id):
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, course_id=course_id)
    _assert_erro(r, 404, ERR_CURSO)
    assert _foto() == antes


@pytest.mark.parametrize("caso", ["outro_curso", "inexistente", "ja_iniciada", "id_enorme"])
def test_c2_turma_invalida_404(client, contas, caso):
    if caso == "outro_curso":
        class_id = _turma("C2 alheia", course_id=OUTRO_CURSO, capacity=5)
    elif caso == "inexistente":
        class_id = _turma("C2 existe", capacity=5) + 999
    elif caso == "ja_iniciada":
        class_id = _turma("C2 iniciada", capacity=5, dias=-1)
    else:
        class_id = 2 ** 63
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, class_id=class_id)
    _assert_erro(r, 404, ERR_TURMA)
    assert _foto() == antes


def test_c3_turma_lotada_409(client, contas):
    t = _turma("C3 lotada", capacity=1)
    _aluno_avulso("active", t)
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email, class_id=t)
    _assert_erro(r, 409, ERR_LOTADA)
    assert _foto() == antes


def test_c4_aluno_ja_ativo_no_curso_409(client, contas):
    _semear(contas.ana.id, "active")
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=contas.ana.email)
    _assert_erro(r, 409, ERR_JA_ATIVO)
    assert _foto() == antes
    assert _eventos(EVENTO_MANUAL) == []


@pytest.mark.parametrize("perfil", ["gestao", "fin", "sup"])
def test_c5_email_de_funcionario_409(client, contas, perfil, tmp_path):
    conta = getattr(contas, perfil)
    antes = _foto()
    r = _manual(client, contas.gestao.token, email=conta.email)
    _assert_erro(r, 409, ERR_FUNCIONARIO)
    assert _foto() == antes
    assert _outbox(tmp_path) == []


@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_c6_cancelada_ou_reembolsada_nao_bloqueia_cria_matricula_nova(client, contas, status):
    antiga = _semear(contas.ana.id, status)
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    ativa = _unica_matricula_ativa(contas.ana.id)
    assert ativa["id"] != antiga.id
    assert _matricula(antiga.id)["status"] == status


def test_c7_matricula_ativa_em_outro_curso_nao_bloqueia(client, contas):
    _semear(contas.ana.id, "active", course_id=OUTRO_CURSO)
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    _unica_matricula_ativa(contas.ana.id)


# =========================================================================================
# Grupo N - conta nova e conta existente
# =========================================================================================

def test_n1_conta_nova_criada_como_aluno_sem_senha(client, contas):
    _manual_ok(client, contas.gestao.token, email="nova.n1@teste.com", name="Nova Conta N1")
    usuario = _usuario("nova.n1@teste.com")
    assert usuario is not None, "a conta inexistente deve ser criada"
    assert usuario["role"] == "student"
    assert usuario["password_hash"] is None, "a conta criada pela Gestao nasce sem senha"
    assert usuario["name"] == "Nova Conta N1"
    _unica_matricula_ativa(usuario["id"])


def test_n2_conta_nova_recebe_link_de_definicao_da_e2_que_funciona(client, contas, tmp_path):
    _manual_ok(client, contas.gestao.token, email="nova.n2@teste.com", name="Nova Conta N2")
    usuario = _usuario("nova.n2@teste.com")
    links = _links_de_definicao(tmp_path, "nova.n2@teste.com")
    assert len(links) == 1, f"esperado 1 link de definicao de senha no outbox: {_outbox(tmp_path)}"
    tokens = _sql("SELECT * FROM password_setup_tokens WHERE user_id = ?", (usuario["id"],))
    assert len(tokens) == 1 and tokens[0]["purpose"] == "setup", tokens
    token = re.search(r"token=([A-Za-z0-9_\-]+)", links[0]["link"]).group(1)
    assert token not in json.dumps(tokens), "o token em claro nao pode ficar no banco"

    r = client.post("/api/auth/password-setup", json={"token": token, "password": SENHA})
    assert r.status_code == 200, r.text
    login = client.post("/api/token", data={"username": "nova.n2@teste.com", "password": SENHA})
    assert login.status_code == 200, login.text
    r = client.get("/api/student/enrollments", headers=_auth(login.json()["access_token"]))
    assert r.status_code == 200, r.text
    assert [m["status"] for m in r.json()["enrollments"]] == ["active"]


def test_n3_conta_existente_e_reaproveitada_sem_link_e_sem_trocar_nome_ou_senha(client, contas, tmp_path):
    antes = _usuario(contas.ana.email)
    n_usuarios = len(_sql("SELECT id FROM users"))
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, name="Outro Nome Qualquer")
    depois = _usuario(contas.ana.email)
    assert len(_sql("SELECT id FROM users")) == n_usuarios, "conta existente nao gera conta nova"
    assert depois["id"] == antes["id"]
    assert depois["password_hash"] == antes["password_hash"], "a senha da conta existente nao muda"
    assert depois["name"] == antes["name"], "a matricula manual nao renomeia a conta existente"
    assert _links_de_definicao(tmp_path, contas.ana.email) == []
    _unica_matricula_ativa(contas.ana.id)


def test_n4_conta_existente_sem_nome_no_corpo(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, name=_AUSENTE)
    _unica_matricula_ativa(contas.ana.id)


# =========================================================================================
# Grupo P - pagamento, pendente reaproveitada, turma
# =========================================================================================

def test_p1_cria_matricula_active_e_pagamento_approved_manual_com_o_valor(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=321.5)
    m = _unica_matricula_ativa(contas.ana.id)
    assert m["class_id"] is None
    pagamentos = _pagamentos_da_matricula(m["id"])
    assert len(pagamentos) == 1, pagamentos
    p = pagamentos[0]
    assert (p["status"], p["payment_method"]) == ("approved", "manual"), p
    assert abs(p["amount"] - 321.5) < 1e-9, p


def test_p2_sem_valor_e_cortesia_zero(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=_AUSENTE)
    p = _pagamento_manual(_unica_matricula_ativa(contas.ana.id)["id"])
    assert p["status"] == "approved" and p["amount"] == 0, p


def test_p3_valor_zero_explicito_aceito(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=0)
    assert _pagamento_manual(_unica_matricula_ativa(contas.ana.id)["id"])["amount"] == 0


def test_p4_pendente_do_mesmo_curso_e_reaproveitada_sem_linha_nova(client, contas):
    pendente = _semear(contas.ana.id, "pending")
    n_matriculas = len(_sql("SELECT id FROM enrollments"))
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=150)
    assert len(_sql("SELECT id FROM enrollments")) == n_matriculas, "a pendente e reaproveitada, sem matricula nova"
    m = _matricula(pendente.id)
    assert m["status"] == "active", m
    assert m["external_reference"] == pendente.ref
    pagamentos = _pagamentos_da_matricula(pendente.id)
    assert [p for p in pagamentos if p["status"] == "pending"] == [], \
        f"nenhum pagamento da matricula pode ficar pending (a S6 o expiraria): {pagamentos}"
    p = _pagamento_manual(pendente.id)
    assert p["status"] == "approved" and abs(p["amount"] - 150) < 1e-9, p


def test_p5_pendente_de_outro_curso_nao_e_tocada(client, contas):
    outra = _semear(contas.ana.id, "pending", course_id=OUTRO_CURSO)
    foto = (_matricula(outra.id), _pagamento(outra.payment_id))
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    assert (_matricula(outra.id), _pagamento(outra.payment_id)) == foto


def test_p6_com_turma_a_matricula_nasce_na_turma_e_ocupa_a_vaga(client, contas):
    t = _turma("P6", capacity=2)
    assert _seats_left(client, t) == 2
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, class_id=t)
    assert _unica_matricula_ativa(contas.ana.id)["class_id"] == t
    assert _seats_left(client, t) == 1
    _manual_ok(client, contas.gestao.token, email=contas.bia.email, class_id=t)
    assert _seats_left(client, t) == 0
    r = _manual(client, contas.gestao.token, email="terceiro.p6@teste.com", class_id=t)
    _assert_erro(r, 409, ERR_LOTADA)


def test_p7_pendente_reaproveitada_na_ultima_vaga_da_propria_turma(client, contas):
    """A propria pendente ocupa a vaga; reaproveita-la na mesma turma nao pode dar 409 de lotada."""
    t = _turma("P7", capacity=1)
    pendente = _semear(contas.ana.id, "pending", class_id=t)
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, class_id=t)
    m = _matricula(pendente.id)
    assert m["status"] == "active" and m["class_id"] == t, m


def test_p8_null_em_class_id_e_amount_ausente_compativeis(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, class_id=None, amount=_AUSENTE)
    m = _unica_matricula_ativa(contas.ana.id)
    assert m["class_id"] is None


# =========================================================================================
# Grupo L - leituras: aluno, financeiro, recibo, evento
# =========================================================================================

def test_l1_aluno_ve_a_matricula_active_com_materiais(client, contas):
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert URL_MATERIAL not in r.text
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    itens = [m for m in r.json()["enrollments"] if m["course_id"] == CURSO]
    assert len(itens) == 1 and itens[0]["status"] == "active", itens
    assert URL_MATERIAL in json.dumps(itens[0]), "matricula manual active libera os materiais"


def test_l2_conta_nova_ve_o_curso_com_materiais(client, contas):
    _manual_ok(client, contas.gestao.token, email="nova.l2@teste.com", name="Nova L2")
    usuario = _usuario("nova.l2@teste.com")
    r = client.get("/api/student/enrollments", headers=_auth(_token_de(usuario["id"], usuario["email"])))
    assert r.status_code == 200, r.text
    assert URL_MATERIAL in r.text


def test_l3_financeiro_conta_o_valor_aprovado(client, contas):
    token = contas.fin.token
    antes = client.get("/api/dashboard/financeiro", headers=_auth(token)).json()["totals"]
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=321.5)
    r = client.get("/api/dashboard/financeiro", headers=_auth(token))
    assert r.status_code == 200, r.text
    depois = r.json()["totals"]
    assert abs(depois["revenue_approved"] - antes["revenue_approved"] - 321.5) < 0.01, (antes, depois)
    assert depois["approved_count"] == antes["approved_count"] + 1
    linhas = [p for p in r.json()["payments"] if p.get("student_email") == contas.ana.email]
    assert len(linhas) == 1 and linhas[0]["status"] == "approved" and abs(linhas[0]["amount"] - 321.5) < 1e-9, linhas


def test_l4_lista_de_alunos_do_curso_mostra_ativo_com_valor(client, contas):
    t = _turma("L4", capacity=5)
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, class_id=t, amount=99)
    r = client.get(f"/api/dashboard/cursos/{CURSO}/alunos", headers=_auth(contas.gestao.token))
    assert r.status_code == 200, r.text
    linhas = [s for s in r.json()["students"] if s["email"] == contas.ana.email]
    assert len(linhas) == 1, r.json()
    assert linhas[0]["status"] == "active" and linhas[0]["class_id"] == t
    assert linhas[0]["payment_status"] == "approved" and abs(linhas[0]["amount"] - 99) < 1e-9, linhas


def test_l5_recibo_json_com_forma_manual(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=45.5)
    r = client.get("/api/student/payments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    pagamentos = r.json()["payments"]
    assert len(pagamentos) == 1 and pagamentos[0]["payment_method"] == "manual", pagamentos
    r = client.get(pagamentos[0]["receipt_url"], headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    recibo = r.json()["receipt"]
    assert recibo["payment_method"] == "manual"
    assert recibo["status"] == "approved" and abs(recibo["amount"] - 45.5) < 1e-9, recibo


@pytest.mark.parametrize("valor, texto_valor", [(45.5, "R$ 45,50"), (0, "R$ 0,00")])
def test_l6_recibo_pdf_mostra_matricula_manual(client, contas, valor, texto_valor):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=valor)
    pagamento = client.get("/api/student/payments", headers=_auth(contas.ana.token)).json()["payments"][0]
    r = client.get(pagamento["receipt_pdf_url"], headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text[:200]
    texto = _texto_do_pdf(r.content)
    assert ROTULO_MANUAL in texto, texto
    assert texto_valor in texto, texto


def test_l7_evento_enrollment_manual_com_motivo_valor_curso_turma_e_responsavel(client, contas):
    t = _turma("Turma L7 Noturna", capacity=5)
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, class_id=t, amount=321.5,
               reason="  Permuta com parceiro institucional  ")
    eventos = _eventos(EVENTO_MANUAL)
    assert len(eventos) == 1, eventos
    evento = eventos[0]
    texto = _texto(evento)
    assert evento["user_id"] == contas.gestao.id, "o responsavel vem do token da Gestao"
    assert "Permuta com parceiro institucional" in texto, texto
    assert CURSO in texto, texto
    assert re.search(r"321[.,]5", texto), texto
    assert "Turma L7 Noturna" in texto or re.search(rf"\b{t}\b", texto), texto


def test_l8_falha_de_regra_nao_grava_evento(client, contas):
    _semear(contas.ana.id, "active")
    _manual(client, contas.gestao.token, email=contas.ana.email)
    _manual(client, contas.gestao.token, email=contas.bia.email, course_id="nao_existe")
    assert _eventos(EVENTO_MANUAL) == []
    _manual_ok(client, contas.gestao.token, email=contas.bia.email)
    assert len(_eventos(EVENTO_MANUAL)) == 1, "controle positivo: a matricula que passa grava o evento"


# =========================================================================================
# Grupo T - atomicidade
# =========================================================================================

def _consertar_pagamento_manual():
    _executar("DROP TRIGGER IF EXISTS u4_falha_insert")
    _executar("DROP TRIGGER IF EXISTS u4_falha_update")


def _quebrar_pagamento_manual():
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute("""CREATE TRIGGER u4_falha_insert BEFORE INSERT ON payments
                        WHEN NEW.payment_method = 'manual'
                        BEGIN SELECT RAISE(ABORT, 'falha simulada do teste U4'); END""")
        conn.execute("""CREATE TRIGGER u4_falha_update BEFORE UPDATE ON payments
                        WHEN NEW.payment_method = 'manual'
                        BEGIN SELECT RAISE(ABORT, 'falha simulada do teste U4'); END""")
        conn.commit()
    finally:
        conn.close()


def test_t1_falha_ao_gravar_o_pagamento_nao_deixa_matricula_orfa(client, contas, tmp_path):
    _quebrar_pagamento_manual()
    matriculas, pagamentos, _ = _foto()
    r = _manual(client, contas.gestao.token, email="nova.t1@teste.com", name="Nova T1")
    assert not (200 <= r.status_code < 300), r.text
    assert _sql("SELECT * FROM enrollments ORDER BY id") == matriculas, "matricula orfa depois da falha"
    assert _sql("SELECT * FROM payments ORDER BY id") == pagamentos
    assert _links_de_definicao(tmp_path, "nova.t1@teste.com") == [], "nao envia link de matricula que falhou"
    assert _eventos(EVENTO_MANUAL) == []
    # Controle positivo: sem o gatilho, a mesma chamada funciona (a falha veio mesmo do pagamento manual).
    _consertar_pagamento_manual()
    _manual_ok(client, contas.gestao.token, email="nova.t1@teste.com", name="Nova T1")
    usuario = _usuario("nova.t1@teste.com")
    _pagamento_manual(_unica_matricula_ativa(usuario["id"])["id"])


def test_t2_falha_com_pendente_reaproveitada_mantem_a_pendente(client, contas):
    pendente = _semear(contas.ana.id, "pending")
    foto = (_matricula(pendente.id), _pagamentos_da_matricula(pendente.id))
    _quebrar_pagamento_manual()
    r = _manual(client, contas.gestao.token, email=contas.ana.email)
    assert not (200 <= r.status_code < 300), r.text
    assert (_matricula(pendente.id), _pagamentos_da_matricula(pendente.id)) == foto, \
        "a pendente nao pode virar active sem o pagamento"
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert URL_MATERIAL not in r.text
    _consertar_pagamento_manual()
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    assert _matricula(pendente.id)["status"] == "active", "controle positivo: sem o gatilho, reaproveita"


# =========================================================================================
# Grupo I - IDOR
# =========================================================================================

def test_i1_user_id_no_corpo_e_ignorado(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, user_id=contas.bia.id)
    _unica_matricula_ativa(contas.ana.id)
    assert _matriculas(contas.bia.id) == []


# =========================================================================================
# Grupo E - S6: expiracao de pendente
# =========================================================================================

def test_e1_pendente_com_mais_de_7_dias_expira_pagamento_e_matricula(client, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    _expirar()
    assert _status(velha) == ("cancelled", "cancelled")


def test_e2_pendente_com_6_dias_e_23_horas_nao_expira(client, contas):
    quase = _semear(contas.ana.id, "pending")
    _envelhecer(quase, QUASE)
    nova = _semear(contas.bia.id, "pending")
    _expirar()
    assert _status(quase) == ("pending", "pending")
    assert _status(nova) == ("pending", "pending")
    assert _eventos(EVENTO_EXPIRADO) == []


@pytest.mark.parametrize("status", ["active", "refunded", "cancelled"])
def test_e3_aprovado_reembolsado_e_cancelado_nunca_expiram(client, contas, status):
    antiga = _semear(contas.ana.id, status)
    _envelhecer(antiga, timedelta(days=60))
    foto = (_matricula(antiga.id), _pagamento(antiga.payment_id))
    _expirar()
    assert (_matricula(antiga.id), _pagamento(antiga.payment_id)) == foto
    assert _eventos(EVENTO_EXPIRADO) == []


def test_e4_pagamento_manual_aprovado_antigo_nao_expira(client, contas):
    _manual_ok(client, contas.gestao.token, email=contas.ana.email, amount=10)
    m = _unica_matricula_ativa(contas.ana.id)
    p = _pagamento_manual(m["id"])
    _envelhecer(SimpleNamespace(id=m["id"], payment_id=p["id"]), timedelta(days=30))
    _expirar()
    assert _matricula(m["id"])["status"] == "active"
    assert _pagamento(p["id"])["status"] == "approved"


def test_e5_idempotente_e_um_evento_por_pagamento(client, contas):
    a = _semear(contas.ana.id, "pending")
    b = _semear(contas.bia.id, "pending", course_id=OUTRO_CURSO)
    _envelhecer(a, VELHA)
    _envelhecer(b, timedelta(days=20))
    _expirar()
    foto = _foto()
    _expirar()
    _expirar()
    assert _foto() == foto
    eventos = _eventos(EVENTO_EXPIRADO)
    assert len(eventos) == 2, eventos
    assert _status(a) == ("cancelled", "cancelled") and _status(b) == ("cancelled", "cancelled")


def test_e6_expiracao_libera_a_vaga_da_turma(client, gw, contas):
    t = _turma("E6", capacity=1)
    velha = _semear(contas.ana.id, "pending", class_id=t)
    assert _seats_left(client, t) == 0, "pre-condicao: a pendente ocupa a vaga"
    _envelhecer(velha, VELHA)
    _expirar()
    assert _seats_left(client, t) == 1
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO, "class_id": t}, headers=_auth(contas.bia.token))
    assert r.status_code == 200, r.text


def test_e7_expirada_nao_libera_material(client, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    _expirar()
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert URL_MATERIAL not in r.text
    assert [m["status"] for m in r.json()["enrollments"]] == ["cancelled"]


def test_e8_startup_expira(banco, cursos, catalogo_bot, contas_sem_client):
    from app import app as fastapi_app

    velha = _semear(contas_sem_client.ana.id, "pending")
    _envelhecer(velha, VELHA)
    with TestClient(fastapi_app):
        pass
    assert _status(velha) == ("cancelled", "cancelled")
    assert len(_eventos(EVENTO_EXPIRADO)) == 1


@pytest.fixture
def contas_sem_client(banco):
    return SimpleNamespace(ana=_conta("ana.startup.u4@teste.com", "Ana Startup"))


LEITURAS = [
    ("dashboard_financeiro", "gestao", "GET", "/api/dashboard/financeiro"),
    ("dashboard_alunos", "gestao", "GET", "/api/dashboard/alunos"),
    ("dashboard_cursos", "gestao", "GET", "/api/dashboard/cursos"),
    ("dashboard_curso_alunos", "gestao", "GET", f"/api/dashboard/cursos/{CURSO}/alunos"),
    ("dashboard_aluno_detalhe", "gestao", "GET", "/api/dashboard/alunos/{ana}"),
    ("aluno_matriculas", "ana", "GET", "/api/student/enrollments"),
    ("aluno_pagamentos", "ana", "GET", "/api/student/payments"),
]


@pytest.mark.parametrize("nome, quem, metodo, rota", LEITURAS, ids=[l[0] for l in LEITURAS])
def test_e9_leituras_expiram_antes_de_responder(client, contas, nome, quem, metodo, rota):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    r = client.request(metodo, rota.format(ana=contas.ana.id), headers=_auth(getattr(contas, quem).token))
    assert r.status_code == 200, r.text
    assert _status(velha) == ("cancelled", "cancelled"), f"{nome}: a leitura deve expirar a pendente velha"
    assert len(_eventos(EVENTO_EXPIRADO)) == 1


def test_e10_checkout_do_aluno_nao_retoma_a_expirada_e_cria_compra_nova(client, gw, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO}, headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] != velha.ref, "a expirada nao e retomada (D81)"
    assert _status(velha) == ("cancelled", "cancelled")
    pendentes = [m for m in _matriculas(contas.ana.id) if m["status"] == "pending"]
    assert len(pendentes) == 1 and pendentes[0]["id"] != velha.id, pendentes
    assert len(gw.post_chamadas) == 1
    assert len(_eventos(EVENTO_EXPIRADO)) == 1


def test_e11_checkout_da_landing_nao_retoma_a_expirada(client, gw, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    r = client.post(ROTA_LANDING, json={"course_id": CURSO, "payer": {"name": "Ana", "email": contas.ana.email}})
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] != velha.ref
    assert _status(velha) == ("cancelled", "cancelled")


def test_e12_checkout_retoma_a_pendente_ainda_valida(client, gw, contas):
    """[caracterizacao D72] com 6 dias e 23 h a pendente continua sendo retomada."""
    quase = _semear(contas.ana.id, "pending")
    _envelhecer(quase, QUASE)
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO}, headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    assert r.json()["external_reference"] == quase.ref
    assert hasattr(Database, "expirar_pendentes"), "D81: falta Database.expirar_pendentes()"


def test_e13_matricula_manual_depois_da_expiracao_cria_nova(client, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    _expirar()
    _manual_ok(client, contas.gestao.token, email=contas.ana.email)
    ativa = _unica_matricula_ativa(contas.ana.id)
    assert ativa["id"] != velha.id
    assert _status(velha) == ("cancelled", "cancelled")


# =========================================================================================
# Grupo W - S6: webhook approved depois da expiracao
# =========================================================================================

def test_w1_webhook_aprovado_depois_de_expirar_reativa_e_grava_evento(client, gw, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    _expirar()
    assert _status(velha) == ("cancelled", "cancelled")
    _aprovar_pelo_webhook(client, gw, velha.ref)
    assert _status(velha) == ("active", "approved")
    eventos = _eventos(EVENTO_APOS_EXPIRAR)
    assert len(eventos) == 1, eventos
    r = client.get("/api/student/enrollments", headers=_auth(contas.ana.token))
    assert URL_MATERIAL in r.text, "o dinheiro entrou: a matricula reativada libera o material"


def test_w2_webhook_repetido_nao_duplica_o_evento(client, gw, contas):
    velha = _semear(contas.ana.id, "pending")
    _envelhecer(velha, VELHA)
    _expirar()
    _aprovar_pelo_webhook(client, gw, velha.ref)
    _aprovar_pelo_webhook(client, gw, velha.ref)
    assert len(_eventos(EVENTO_APOS_EXPIRAR)) == 1
    assert len(_eventos(EVENTO_EXPIRADO)) == 1


def test_w3_aprovado_sem_expiracao_nao_grava_o_evento(client, gw, contas):
    pendente = _semear(contas.ana.id, "pending")
    _envelhecer(pendente, QUASE)
    _aprovar_pelo_webhook(client, gw, pendente.ref)
    assert _status(pendente) == ("active", "approved")
    assert _eventos(EVENTO_APOS_EXPIRAR) == []
    assert hasattr(Database, "expirar_pendentes"), "D81: falta Database.expirar_pendentes()"


def test_w4_reativada_com_turma_lotada_por_outro_fica_sem_turma_regra_s8(client, gw, contas):
    t = _turma("W4", capacity=1)
    r = client.post(ROTA_ALUNO, json={"course_id": CURSO, "class_id": t}, headers=_auth(contas.ana.token))
    assert r.status_code == 200, r.text
    ref = r.json()["external_reference"]
    m = _sql("SELECT * FROM enrollments WHERE external_reference = ?", (ref,))[0]
    p = _pagamentos_da_matricula(m["id"])[-1]
    da_ana = SimpleNamespace(id=m["id"], payment_id=p["id"], ref=ref)
    _envelhecer(da_ana, VELHA)
    _expirar()
    assert _status(da_ana) == ("cancelled", "cancelled")
    _semear(contas.bia.id, "active", class_id=t)  # a vaga liberada foi ocupada por outra aluna
    _aprovar_pelo_webhook(client, gw, ref)
    reativada = _matricula(da_ana.id)
    assert reativada["status"] == "active"
    assert reativada["class_id"] is None, "sem vaga: fica sem turma (S8)"
    assert len(_eventos(EVENTO_OVERFLOW)) == 1
    assert len(_eventos(EVENTO_APOS_EXPIRAR)) == 1


def test_w5_reativada_com_vaga_mantem_a_turma(client, gw, contas):
    t = _turma("W5", capacity=2)
    velha = _semear(contas.ana.id, "pending", class_id=t)
    _envelhecer(velha, VELHA)
    _expirar()
    _aprovar_pelo_webhook(client, gw, velha.ref)
    m = _matricula(velha.id)
    assert m["status"] == "active" and m["class_id"] == t, m
    assert _eventos(EVENTO_OVERFLOW) == []
