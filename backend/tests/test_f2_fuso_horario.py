"""F2 — Horário de São Paulo (GMT-3) no recibo PDF e na série diária da observabilidade.

Plano: docs/tdd/PLANO_FEEDBACK_PROF.md (F2). Modo autônomo: D69. Contrato (decisões de forma do orquestrador):
  - O banco continua gravando UTC (CURRENT_TIMESTAMP, texto 'AAAA-MM-DD HH:MM:SS' sem fuso) e a API JSON NÃO muda:
    mesmos campos e os mesmos valores UTC do banco (caracterização, grupo C).
  - Backend: deslocamento FIXO de -3 h (o Brasil não tem horário de verão desde 2019), sem depender de zoneinfo/tzdata.
  - Recibo PDF: a data/hora impressa é a de São Paulo, no formato 'dd/mm/aaaa HH:MM' (sem segundos), e o texto UTC
    cru não aparece. Ex.: created_at UTC '2026-10-08 01:30:00' -> '07/10/2026 22:30'. O recibo JSON continua igual.
  - Observabilidade (E7): per_day agrupa pelo DIA DE SÃO PAULO e o "hoje" da janela de 14 dias também é o dia de
    São Paulo. Mesmas chaves (date, requests, cost_usd).

Seam do "hoje" (grupo P2): o instante atual é congelado trocando a classe `datetime` nos módulos do backend que a
importam (`from datetime import datetime`), como faz hoje `db.get_ai_usage_per_day`. Se a implementação passar a
obter o "agora" de outra fonte (ex.: date('now') do SQLite), P2 deixa de enxergar o relógio congelado: o dev deve
reportar, não contornar.

Testes:
  R1  PDF: '2026-10-08 01:30:00' UTC sai como '07/10/2026 22:30' na linha "Data de emissão"; nada do UTC cru
  R2  PDF: virada de dia, de mês, de ano, ano bissexto e a fronteira das 03:00 UTC (parametrizado)
  R3  PDF: issued_at = updated_at quando existe (a data convertida é a do updated_at, não a do created_at)
  R4  recibo JSON e lista de pagamentos do aluno continuam com o texto UTC do banco (caracterização)
  P1  per_day agrupa pelo dia de São Paulo (usos às 02:59:59 / 03:00 / 01:30 / 03:30 UTC)
  P2  "hoje" da janela = dia de São Paulo (agora congelado em 2026-10-08 01:30 UTC -> último dia 2026-10-07)
  P3  o endpoint /api/dashboard/observabilidade-ia devolve a mesma série, com as mesmas chaves (Gestão e Suporte)
  C1  auditoria: created_at continua o texto UTC do banco
  C2  matrículas do aluno: enrolled_at continua o texto UTC do banco
  C3  dashboard financeiro: payments[].created_at continua o texto UTC do banco
  C4  dashboard de alunos: last_enrollment_at e last_chat_at continuam o texto UTC do banco
  C5  turma: starts_on (data só de dia) não é deslocado

Fixtures: banco temporário (conftest), cursos em diretório temporário, catálogo do bot isolado (D70), SDK do Groq
falso (nenhuma chamada real). Nenhum teste toca backend/db.sqlite.
"""

import json
import sqlite3
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
import agents.groq_client as groq_client_mod
from core.security import get_password_hash
from db import Database
from test_b2_recibo_pdf import _texto_do_pdf, _validar_estrutura


SENHA = "senha-aluno-f2-2026"
CURSO = "curso-f2-fuso"
NOME_CURSO = "Curso F2 Fuso Horario"
SENHAS_ADMINISTRATIVAS = {"admin": "admin123", "financial": "fin123", "support": "sup123"}
BACKEND_DIR = Path(__file__).resolve().parent.parent

UTC_NOITE = "2026-10-08 01:30:00"     # 07/10/2026 22:30 em São Paulo
SP_NOITE = "07/10/2026 22:30"


# --- Fixtures ----------------------------------------------------------------------------

@pytest.fixture
def cursos(tmp_path, monkeypatch, catalogo_bot):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    (diretorio / f"{CURSO}.json").write_text(json.dumps({
        "id": CURSO, "name": NOME_CURSO, "description": "Curso de teste F2", "price": 100.0, "materials": [],
    }), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return diretorio


@pytest.fixture
def groq_falso(monkeypatch):
    """O app cria o ManagerAgent no startup; o SDK do Groq é falso para não haver chamada real."""

    def create(**kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], usage=None)

    class GroqSDKFalso:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(groq_client_mod, "Groq", GroqSDKFalso)


@pytest.fixture
def client(banco, cursos, groq_falso):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers -----------------------------------------------------------------------------

def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _conta(email, nome="Aluno F2", role="student"):
    user_id = Database.add_user(email, nome, get_password_hash(SENHA), role=role)
    assert user_id is not None, f"seed: conta {email} já existe"
    return user_id


def _login(client, email):
    r = client.post("/api/token", data={"username": email, "password": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _aluno_logado(client, prefixo):
    email = f"{prefixo}.{uuid.uuid4().hex[:8]}@f2.test"
    uid = _conta(email)
    return uid, email, _login(client, email)


def _token_staff(client, perfil):
    r = client.post("/api/admin/login", json={"password": SENHAS_ADMINISTRATIVAS[perfil]})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _matricula_e_pagamento(user_id, status="approved", created_at=UTC_NOITE, updated_at=UTC_NOITE,
                           enrolled_at=UTC_NOITE, enrollment_status="active"):
    ref = f"{CURSO}:f2:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, CURSO, ref)
    pid = Database.record_payment(enrollment_id, 250.0, "mercado_pago")
    Database.update_payment_status(pid, status, f"mp-f2-{uuid.uuid4().hex[:6]}")
    _executar("UPDATE payments SET created_at = ?, updated_at = ? WHERE id = ?", (created_at, updated_at, pid))
    _executar("UPDATE enrollments SET status = ?, enrolled_at = ? WHERE id = ?",
              (enrollment_status, enrolled_at, enrollment_id))
    return enrollment_id, pid


def _pdf_texto(client, token, pid):
    r = client.get(f"/api/student/payments/{pid}/receipt.pdf", headers=_auth(token))
    assert r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]!r}"
    _validar_estrutura(r.content)
    return _texto_do_pdf(r.content)


def _linha_emissao(texto):
    linhas = [l for l in texto.splitlines() if l.startswith("Data de emiss")]
    assert len(linhas) == 1, f"o PDF deve ter uma única linha 'Data de emissão': {texto!r}"
    return linhas[0]


def _inserir_uso(created_at, cost=0.0):
    _executar(
        "INSERT INTO ai_usage (created_at, channel, user_id, session_hash, call_type, model, prompt_tokens, "
        "completion_tokens, total_tokens, cost_usd, latency_ms, status) "
        "VALUES (?, 'anonymous', NULL, 'abcdef0123456789', 'answer', 'modelo-f2', 10, 10, 20, ?, 5, 'ok')",
        (created_at, cost),
    )


def _hoje_sp():
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def _ts(dia, hora):
    return f"{dia.isoformat()} {hora}"


@pytest.fixture
def agora_congelado(monkeypatch):
    """Congela o "agora" do backend em um instante UTC (seam: classe datetime importada pelos módulos do backend)."""

    def congelar(instante_utc: datetime):
        fixo = instante_utc.replace(tzinfo=timezone.utc)

        class DatetimeCongelado(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return fixo.astimezone().replace(tzinfo=None)
                return fixo.astimezone(tz)

            @classmethod
            def utcnow(cls):
                return fixo.replace(tzinfo=None)

            @classmethod
            def today(cls):
                return cls.now()

        trocados = 0
        for nome, modulo in list(sys.modules.items()):
            arquivo = getattr(modulo, "__file__", None) or ""
            try:
                dentro = Path(arquivo).resolve().is_relative_to(BACKEND_DIR) and "tests" not in Path(arquivo).parts
            except (OSError, ValueError):
                dentro = False
            if dentro and getattr(modulo, "datetime", None) is datetime:
                monkeypatch.setattr(modulo, "datetime", DatetimeCongelado)
                trocados += 1
        assert trocados, "seam: nenhum módulo do backend importa a classe datetime"
        return fixo

    return congelar


# =========================================================================================
# Recibo PDF
# =========================================================================================

def test_r1_pdf_imprime_a_data_e_hora_de_sao_paulo_sem_o_utc_cru(client):
    uid, _, token = _aluno_logado(client, "r1")
    _, pid = _matricula_e_pagamento(uid, created_at=UTC_NOITE, updated_at=UTC_NOITE)

    texto = _pdf_texto(client, token, pid)

    linha = _linha_emissao(texto)
    assert SP_NOITE in linha, f"a data de emissão deve ser a de São Paulo ({SP_NOITE!r}): {linha!r}"
    assert "22:30:00" not in texto, "formato dd/mm/aaaa HH:MM, sem segundos"
    for cru in ("2026-10-08", "01:30", "08/10/2026"):
        assert cru not in texto, f"o texto UTC {cru!r} não pode aparecer no PDF: {texto!r}"


@pytest.mark.parametrize("utc, sao_paulo", [
    ("2026-10-08 03:00:00", "08/10/2026 00:00"),   # fronteira: 03:00 UTC já é o mesmo dia em São Paulo
    ("2026-10-08 02:59:59", "07/10/2026 23:59"),   # um segundo antes: dia anterior (sem arredondar)
    ("2026-11-01 00:15:00", "31/10/2026 21:15"),   # virada de mês
    ("2027-01-01 02:00:00", "31/12/2026 23:00"),   # virada de ano
    ("2028-03-01 01:00:00", "29/02/2028 22:00"),   # ano bissexto
    ("2026-01-15 12:00:00", "15/01/2026 09:00"),   # verão: deslocamento continua -3 h (sem horário de verão)
    ("2026-07-20 18:45:00", "20/07/2026 15:45"),   # meio do dia, mesmo dia
])
def test_r2_pdf_converte_viradas_de_dia_mes_ano_e_bissexto(client, utc, sao_paulo):
    uid, _, token = _aluno_logado(client, "r2")
    _, pid = _matricula_e_pagamento(uid, created_at=utc, updated_at=utc)

    linha = _linha_emissao(_pdf_texto(client, token, pid))

    assert sao_paulo in linha, f"{utc} UTC deve sair como {sao_paulo!r}: {linha!r}"
    assert utc not in linha and utc[:10] not in linha


def test_r3_pdf_usa_o_updated_at_convertido_quando_existe(client):
    uid, _, token = _aluno_logado(client, "r3")
    _, pid = _matricula_e_pagamento(uid, created_at="2026-10-05 15:00:00", updated_at="2026-10-06 02:10:00")

    linha = _linha_emissao(_pdf_texto(client, token, pid))

    assert "05/10/2026 23:10" in linha, linha
    assert "05/10/2026 12:00" not in linha, "a data de emissão é a do updated_at, não a do created_at"


def test_r4_recibo_json_e_lista_de_pagamentos_continuam_em_utc(client):
    uid, _, token = _aluno_logado(client, "r4")
    _, pid = _matricula_e_pagamento(uid, created_at=UTC_NOITE, updated_at="2026-10-08 02:00:00")

    recibo = client.get(f"/api/student/payments/{pid}/receipt", headers=_auth(token))
    assert recibo.status_code == 200, recibo.text
    assert recibo.json()["receipt"]["issued_at"] == "2026-10-08 02:00:00"

    lista = client.get("/api/student/payments", headers=_auth(token))
    assert lista.status_code == 200, lista.text
    item = [p for p in lista.json()["payments"] if p["id"] == pid][0]
    assert item["created_at"] == UTC_NOITE
    assert item["updated_at"] == "2026-10-08 02:00:00"


# =========================================================================================
# Série diária da observabilidade (E7)
# =========================================================================================

def test_p1_per_day_agrupa_pelo_dia_de_sao_paulo(banco):
    dia = _hoje_sp() - timedelta(days=5)
    anterior, seguinte = dia - timedelta(days=1), dia + timedelta(days=1)
    _inserir_uso(_ts(dia, "02:59:59"), 0.01)          # São Paulo: dia anterior, 23:59:59
    _inserir_uso(_ts(dia, "03:00:00"), 0.02)          # São Paulo: dia, 00:00
    _inserir_uso(_ts(seguinte, "01:30:00"), 0.04)     # São Paulo: dia, 22:30
    _inserir_uso(_ts(seguinte, "03:30:00"), 0.08)     # São Paulo: dia seguinte, 00:30

    serie = {d["date"]: d for d in Database.get_ai_usage_per_day(14)}

    assert serie[anterior.isoformat()]["requests"] == 1
    assert serie[anterior.isoformat()]["cost_usd"] == pytest.approx(0.01, abs=1e-6)
    assert serie[dia.isoformat()]["requests"] == 2, "03:00 UTC e 01:30 UTC do dia seguinte são o mesmo dia em SP"
    assert serie[dia.isoformat()]["cost_usd"] == pytest.approx(0.06, abs=1e-6)
    assert serie[seguinte.isoformat()]["requests"] == 1
    assert serie[seguinte.isoformat()]["cost_usd"] == pytest.approx(0.08, abs=1e-6)
    assert sum(d["requests"] for d in serie.values()) == 4


def test_p2_hoje_da_janela_e_o_dia_de_sao_paulo(banco, agora_congelado):
    agora_congelado(datetime(2026, 10, 8, 1, 30, 0))   # em São Paulo ainda é 07/10/2026, 22:30
    _inserir_uso("2026-10-08 01:00:00", 0.5)           # SP 07/10 22:00 -> último dia da série
    _inserir_uso("2026-09-24 03:00:00", 0.25)          # SP 24/09 00:00 -> primeiro dia da série
    _inserir_uso("2026-09-24 02:00:00", 0.125)         # SP 23/09 23:00 -> fora da janela

    serie = Database.get_ai_usage_per_day(14)

    datas = [d["date"] for d in serie]
    assert len(serie) == 14
    assert datas[-1] == "2026-10-07", f"o 'hoje' da janela é o dia de São Paulo, veio {datas[-1]}"
    assert datas[0] == "2026-09-24", datas
    assert "2026-10-08" not in datas
    assert serie[-1]["requests"] == 1 and serie[-1]["cost_usd"] == pytest.approx(0.5, abs=1e-6)
    assert serie[0]["requests"] == 1 and serie[0]["cost_usd"] == pytest.approx(0.25, abs=1e-6)
    assert sum(d["requests"] for d in serie) == 2, "o uso de 23/09 em São Paulo está fora da janela"
    for d in serie:
        assert set(d) == {"date", "requests", "cost_usd"}, d


def test_p3_endpoint_devolve_a_serie_pelo_dia_de_sao_paulo_com_as_mesmas_chaves(client):
    dia = _hoje_sp() - timedelta(days=2)
    seguinte = dia + timedelta(days=1)
    _inserir_uso(_ts(seguinte, "01:30:00"), 0.3)      # SP: dia, 22:30
    _inserir_uso(_ts(seguinte, "03:30:00"), 0.7)      # SP: dia seguinte, 00:30

    admin = client.get("/api/dashboard/observabilidade-ia", headers=_auth(_token_staff(client, "admin")))
    suporte = client.get("/api/dashboard/observabilidade-ia", headers=_auth(_token_staff(client, "support")))
    assert admin.status_code == 200 and suporte.status_code == 200

    serie_admin = admin.json()["metrics"]["per_day"]
    serie_suporte = suporte.json()["metrics"]["per_day"]
    assert len(serie_admin) == 14
    assert serie_admin[-1]["date"] == _hoje_sp().isoformat(), "o último dia da série é o 'hoje' de São Paulo"
    por_data = {d["date"]: d for d in serie_admin}
    assert por_data[dia.isoformat()]["requests"] == 1
    assert por_data[dia.isoformat()]["cost_usd"] == pytest.approx(0.3, abs=1e-6)
    assert por_data[seguinte.isoformat()]["requests"] == 1
    assert por_data[seguinte.isoformat()]["cost_usd"] == pytest.approx(0.7, abs=1e-6)
    assert all(set(d) == {"date", "requests", "cost_usd"} for d in serie_admin)
    assert all(set(d) == {"date", "requests"} for d in serie_suporte), "Suporte continua sem custo"
    assert [(d["date"], d["requests"]) for d in serie_suporte] == [(d["date"], d["requests"]) for d in serie_admin]


# =========================================================================================
# Caracterização: a API JSON continua devolvendo o texto UTC do banco
# =========================================================================================

def test_c1_auditoria_continua_com_o_texto_utc(client):
    # audit_logs é só de inserção (E8): o evento já nasce com o horário UTC conhecido.
    log_id = _executar("INSERT INTO audit_logs (role, action, detail, created_at) VALUES ('admin', ?, ?, ?)",
                       ("course.update", "Evento F2 fuso", UTC_NOITE))

    r = client.get("/api/admin/audit-logs", headers=_auth(_token_staff(client, "admin")))

    assert r.status_code == 200, r.text
    log = [l for l in r.json()["logs"] if l["id"] == log_id][0]
    assert log["created_at"] == UTC_NOITE


def test_c2_matriculas_do_aluno_continuam_com_o_texto_utc(client):
    uid, _, token = _aluno_logado(client, "c2")
    enrollment_id, _ = _matricula_e_pagamento(uid, enrolled_at=UTC_NOITE)

    r = client.get("/api/student/enrollments", headers=_auth(token))

    assert r.status_code == 200, r.text
    item = [e for e in r.json()["enrollments"] if e["id"] == enrollment_id][0]
    assert item["enrolled_at"] == UTC_NOITE


def test_c3_dashboard_financeiro_continua_com_o_texto_utc(client):
    uid, _, _ = _aluno_logado(client, "c3")
    _, pid = _matricula_e_pagamento(uid, created_at=UTC_NOITE)

    r = client.get("/api/dashboard/financeiro", headers=_auth(_token_staff(client, "financial")))

    assert r.status_code == 200, r.text
    item = [p for p in r.json()["payments"] if p["id"] == pid][0]
    assert item["created_at"] == UTC_NOITE


def test_c4_dashboard_de_alunos_continua_com_o_texto_utc(client):
    uid, email, _ = _aluno_logado(client, "c4")
    _matricula_e_pagamento(uid, enrolled_at=UTC_NOITE)
    _executar("INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
              (uid, "pergunta f2", "2026-10-08 02:10:00"))

    r = client.get("/api/dashboard/alunos", headers=_auth(_token_staff(client, "support")))

    assert r.status_code == 200, r.text
    aluno = [s for s in r.json()["students"] if s["email"] == email][0]
    assert aluno["last_enrollment_at"] == UTC_NOITE
    assert aluno["last_chat_at"] == "2026-10-08 02:10:00"


def test_c5_turma_starts_on_so_de_dia_nao_e_deslocado(client):
    token = _token_staff(client, "admin")

    r = client.post("/api/admin/classes", headers=_auth(token),
                    json={"course_id": CURSO, "name": "Turma F2", "starts_on": "2026-11-01", "capacity": 10})

    assert r.status_code == 200, r.text
    assert r.json()["class"]["starts_on"] == "2026-11-01"
    lista = client.get("/api/admin/classes", headers=_auth(token), params={"course_id": CURSO})
    assert [t["starts_on"] for t in lista.json()["classes"]] == ["2026-11-01"]
