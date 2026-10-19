"""DS - Dívidas de segurança (D51): limite de 72 bytes do bcrypt, materiais no PUT do curso e corrida do token de senha.

Escritos ANTES da implementação. Onde a D51 aponta defeito o teste fica vermelho; onde ela diz que o código já
está correto (cadastro e definição de senha que recusam >72 bytes, atomicidade do token) o teste é uma guarda verde.

Contrato (D51):
  1. bcrypt 72 bytes:
     - `verify_password` devolve False (nunca erro) para senha com mais de 72 bytes em UTF-8;
     - `get_password_hash` levanta ValueError para mais de 72 bytes (72 exatos funcionam, inclusive com acentos);
     - POST /api/token com senha longa: 400 "Usuário ou senha inválidos"; conta de funcionário existente grava
       `staff.login_failed` (E8), conta de aluno não grava evento;
     - startup: conta de funcionário do .env com senha acima de 72 bytes NÃO é criada e vai um `[AVISO]` ao log
       (sem a senha); as contas válidas são criadas normalmente.
  2. PUT /api/admin/course/{id}: `materials` ausente PRESERVA os materiais (e `changes` da auditoria não o lista);
     `materials` enviado, inclusive [], SUBSTITUI. POST create-course sem `materials` grava [].
  3. Corrida do token: N pedidos simultâneos com o mesmo token -> exatamente um 200, os demais 400; a conta termina
     com a senha do vencedor e `used_at` preenchido.

Checklist: IDOR NÃO SE APLICA além do já coberto na E2 (nenhum endpoint novo; nenhum recebe id de usuário do
cliente; o alvo da definição de senha continua sendo o dono do token, E2/D17). Recurso pago só com matrícula ativa:
coberto no grupo B (aluno ativo continua vendo os materiais depois de um PUT que não os menciona; pending,
cancelled e refunded continuam sem nenhuma URL na resposta).

Convenções (padrão de test_e3/test_e8): banco temporário via conftest, rotas HTTP reais, cursos em diretório
temporário (fixture `cursos`, igual à da E8: redireciona COURSES_DIR e o `__file__` das rotas de curso e, ao
final, exige que backend/courses não tenha mudado). Nenhum teste toca backend/db.sqlite nem o Groq.

Escolhas conservadoras (ver relatório): `materials: null` no PUT não é testado (a D51 não diz); o aviso de startup
é procurado em stdout/stderr e no logging (a D51 não fixa o canal) e só se exige o marcador `[AVISO]` e a ausência
da senha; a conta de aluno com senha longa é montada por `get_password_hash` com os 72 primeiros bytes, que é como
o hash de uma conta antiga truncada ficaria.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from core.password_setup import emitir_token_definicao
from core.security import create_access_token, get_password_hash, verify_password
from db import Database


ERRO_LOGIN = "Usuário ou senha inválidos"
REPO_COURSES = Path(__file__).resolve().parent.parent / "courses"

SENHA_72_ASCII = "A" * 72
SENHA_72_ACENTOS = "ñ" * 30 + "A" * 12            # 30 x 2 bytes + 12 = 72 bytes, 42 caracteres
SENHA_72_SO_ACENTOS = "é" * 36                     # 36 x 2 bytes = 72 bytes
SENHAS_LONGAS = {
    "73_ascii": "A" * 73,
    "72_mais_x": "A" * 72 + "x",
    "100_ascii": "A" * 100,
    "1000_ascii": "A" * 1000,
}
MATERIAL_1 = {"title": "Apostila DS", "url": "https://materiais.test/ds/apostila.pdf", "type": "pdf"}
MATERIAL_2 = {"title": "Video DS", "url": "https://materiais.test/ds/video.mp4", "type": "video"}
MATERIAL_3 = {"title": "Planilha DS", "url": "https://materiais.test/ds/planilha.xlsx", "type": "xlsx"}


def test_constantes_de_senha_tem_o_tamanho_declarado():
    """Sanidade dos dados do teste: as senhas de borda têm exatamente os bytes que dizem ter."""
    assert len(SENHA_72_ASCII.encode("utf-8")) == 72
    assert len(SENHA_72_ACENTOS.encode("utf-8")) == 72 and len(SENHA_72_ACENTOS) < 72
    assert len(SENHA_72_SO_ACENTOS.encode("utf-8")) == 72
    assert len(("é" * 37).encode("utf-8")) == 74 and len("é" * 37) == 37


# --- Fixtures ---------------------------------------------------------------------------

def _foto_repo():
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir())


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Diretório temporário para as rotas de curso; backend/courses não pode mudar."""
    antes = _foto_repo()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_repo() == antes, "o teste alterou backend/courses (deveria usar o diretório temporário)"


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco ---------------------------------------------------------------------

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


def _acoes():
    return [e["action"] for e in _sql("SELECT action FROM audit_logs ORDER BY id")]


def _dump_auditoria():
    return json.dumps(_sql("SELECT * FROM audit_logs"), ensure_ascii=False, default=str)


# --- Helpers de contas e HTTP ---------------------------------------------------------------

def _conta(email, perfil, senha):
    """Conta com senha em bcrypt. `senha` precisa caber em 72 bytes (o hash é calculado pela produção)."""
    user_id = Database.add_user(email, f"Conta {perfil}", get_password_hash(senha), role=perfil)
    assert user_id is not None, f"seed: conta {email} já existe"
    return user_id


def _login(client, email, senha):
    return client.post("/api/token", data={"username": email, "password": senha})


def _login_ok(client, email, senha):
    r = _login(client, email, senha)
    assert r.status_code == 200, f"login de {email} deveria funcionar: HTTP {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_token():
    user_id = Database.add_user("gestor.ds@ds.test", "Gestor DS", None, role="admin")
    return create_access_token({"user_id": user_id, "email": "gestor.ds@ds.test", "role": "admin"})


# =========================================================================================
# Grupo A - limite de 72 bytes do bcrypt
# =========================================================================================

# --- A1: funções de senha, direto ----------------------------------------------------------

@pytest.mark.parametrize("senha", [SENHA_72_ASCII, SENHA_72_ACENTOS, SENHA_72_SO_ACENTOS],
                         ids=["72_ascii", "72_acentos_mistos", "72_so_acentos"])
def test_a1_hash_de_72_bytes_funciona_e_verifica(senha):
    hash_ = get_password_hash(senha)
    assert verify_password(senha, hash_) is True
    assert verify_password(senha + "x", hash_) is False, "o 73º byte não pode ser ignorado"


@pytest.mark.parametrize("senha", [
    "A" * 73, "A" * 100, "A" * 1000, "é" * 37, "é" * 36 + "A",
], ids=["73_ascii", "100_ascii", "1000_ascii", "74_bytes_37_caracteres", "73_bytes_acentos"])
def test_a2_get_password_hash_levanta_value_error_acima_de_72_bytes(senha):
    with pytest.raises(ValueError):
        get_password_hash(senha)


@pytest.mark.parametrize("longa", list(SENHAS_LONGAS.values()), ids=list(SENHAS_LONGAS))
def test_a3_verify_password_devolve_false_acima_de_72_bytes(longa):
    hash_ = get_password_hash(SENHA_72_ASCII)
    assert verify_password(longa, hash_) is False   # nunca True (truncamento) e nunca exceção


def test_a3b_verify_password_com_acentos_acima_de_72_bytes_devolve_false():
    hash_ = get_password_hash(SENHA_72_ACENTOS)
    assert verify_password(SENHA_72_ACENTOS + "x", hash_) is False
    assert verify_password("ñ" * 37, get_password_hash("ñ" * 36)) is False


def test_a3c_verify_password_sem_hash_continua_false():
    assert verify_password("qualquer-senha-ok", None) is False
    assert verify_password("A" * 100, None) is False


# --- A2: login de aluno ----------------------------------------------------------------------

@pytest.mark.parametrize("senha", [SENHA_72_ASCII, SENHA_72_ACENTOS, SENHA_72_SO_ACENTOS],
                         ids=["72_ascii", "72_acentos_mistos", "72_so_acentos"])
def test_a4_aluno_com_senha_de_exatamente_72_bytes_faz_login(client, senha):
    _conta("aluno.72@ds.test", "student", senha)
    token = _login_ok(client, "aluno.72@ds.test", senha)
    assert token


@pytest.mark.parametrize("longa", list(SENHAS_LONGAS.values()), ids=list(SENHAS_LONGAS))
def test_a5_senha_acima_de_72_bytes_nao_autentica_conta_de_72_ascii(client, longa):
    _conta("aluno.a5@ds.test", "student", SENHA_72_ASCII)
    r = _login(client, "aluno.a5@ds.test", longa)
    assert r.status_code == 400, f"senha de {len(longa.encode())} bytes: HTTP {r.status_code} {r.text[:200]}"
    assert r.json()["detail"] == ERRO_LOGIN
    assert "access_token" not in r.text
    _login_ok(client, "aluno.a5@ds.test", SENHA_72_ASCII)          # a senha de verdade segue valendo


@pytest.mark.parametrize("senha, longa", [
    (SENHA_72_ACENTOS, SENHA_72_ACENTOS + "x"),
    (SENHA_72_ACENTOS, SENHA_72_ACENTOS + "ñ" * 20),
    (SENHA_72_SO_ACENTOS, SENHA_72_SO_ACENTOS + "é"),
], ids=["acentos_mais_x", "acentos_mais_20_enes", "so_acentos_mais_e"])
def test_a6_senha_com_acentos_acima_de_72_bytes_nao_autentica(client, senha, longa):
    _conta("aluno.a6@ds.test", "student", senha)
    r = _login(client, "aluno.a6@ds.test", longa)
    assert r.status_code == 400, f"HTTP {r.status_code} {r.text[:200]}"
    assert r.json()["detail"] == ERRO_LOGIN
    _login_ok(client, "aluno.a6@ds.test", senha)


def test_a7_senha_longa_para_email_inexistente_e_400_generico(client):
    r = _login(client, "ninguem.a7@ds.test", "A" * 1000)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == ERRO_LOGIN


def test_a7b_senha_longa_para_conta_sem_senha_e_400_generico(client):
    Database.get_or_create_user("sem.senha.a7b@ds.test", "Sem Senha")
    r = _login(client, "sem.senha.a7b@ds.test", "A" * 100)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == ERRO_LOGIN


def test_a8_login_de_aluno_com_senha_longa_nao_gera_evento_de_auditoria(client):
    _conta("aluno.a8@ds.test", "student", SENHA_72_ASCII)
    assert _login(client, "aluno.a8@ds.test", "A" * 73).status_code == 400
    assert _acoes() == [], f"login de aluno (certo ou errado) não é auditado: {_acoes()}"


# --- A3: cadastro e definição de senha seguem recusando (guarda verde) ----------------------

@pytest.mark.parametrize("longa", ["A" * 73, "é" * 37, "A" * 1000], ids=["73_ascii", "74_bytes", "1000_ascii"])
def test_a9_cadastro_recusa_senha_acima_de_72_bytes(client, longa):
    email = f"cadastro.{uuid.uuid4().hex[:8]}@ds.test"
    r = client.post("/api/auth/register", json={"name": "Aluno DS", "email": email, "password": longa})
    assert r.status_code == 400, f"HTTP {r.status_code} {r.text[:200]}"
    assert _usuario(email) is None, "nenhuma conta pode ser criada com senha longa"


@pytest.mark.parametrize("senha", [SENHA_72_ASCII, SENHA_72_ACENTOS], ids=["72_ascii", "72_acentos_mistos"])
def test_a10_cadastro_aceita_72_bytes_e_o_login_funciona(client, senha):
    email = "cadastro.72@ds.test"
    r = client.post("/api/auth/register", json={"name": "Aluno DS", "email": email, "password": senha})
    assert r.status_code == 200, r.text
    assert _usuario(email)["password_hash"], "a conta nasce com senha"
    _login_ok(client, email, senha)
    assert _login(client, email, senha + "x").status_code == 400


@pytest.mark.parametrize("longa", ["A" * 73, "é" * 37, "A" * 1000], ids=["73_ascii", "74_bytes", "1000_ascii"])
def test_a11_definicao_de_senha_recusa_acima_de_72_bytes_sem_consumir_o_token(client, longa):
    user_id = Database.get_or_create_user("definicao.a11@ds.test", "Aluno A11")
    token = emitir_token_definicao(user_id)
    r = client.post("/api/auth/password-setup", json={"token": token, "password": longa})
    assert r.status_code == 400, f"HTTP {r.status_code} {r.text[:200]}"
    assert _usuario("definicao.a11@ds.test")["password_hash"] is None
    assert _sql("SELECT used_at FROM password_setup_tokens WHERE user_id = ?", (user_id,))[0]["used_at"] is None
    # o mesmo token ainda serve para uma senha válida de 72 bytes
    ok = client.post("/api/auth/password-setup", json={"token": token, "password": SENHA_72_ACENTOS})
    assert ok.status_code == 200, ok.text
    _login_ok(client, "definicao.a11@ds.test", SENHA_72_ACENTOS)


# --- A4: funcionário existente ----------------------------------------------------------------

@pytest.mark.parametrize("perfil", ["admin", "financial", "support"])
@pytest.mark.parametrize("longa", ["A" * 73, "A" * 1000], ids=["73_ascii", "1000_ascii"])
def test_a12_funcionario_com_senha_longa_recebe_400_e_staff_login_failed(client, perfil, longa):
    email = f"{perfil}.a12@ds.test"
    user_id = _conta(email, perfil, SENHA_72_ASCII)
    r = _login(client, email, longa)
    assert r.status_code == 400, f"HTTP {r.status_code} {r.text[:200]}"
    assert r.json()["detail"] == ERRO_LOGIN
    assert _acoes() == ["staff.login_failed"], f"esperado só staff.login_failed, veio {_acoes()}"
    evento = _sql("SELECT * FROM audit_logs")[0]
    assert evento["user_id"] in (None, user_id) and evento["actor_email"] in (None, email), evento
    assert longa not in _dump_auditoria(), "a senha digitada nunca é gravada na trilha"


def test_a12b_funcionario_com_72_bytes_exatos_faz_login_e_grava_staff_login(client):
    _conta("gestor.a12b@ds.test", "admin", SENHA_72_ACENTOS)
    _login_ok(client, "gestor.a12b@ds.test", SENHA_72_ACENTOS)
    assert _acoes() == ["staff.login"], _acoes()


# --- A5: startup com contas do .env ---------------------------------------------------------------

def _env_funcionarios(monkeypatch, admin_senha, fin_senha, sup_senha):
    for prefixo, senha in (("ADMIN", admin_senha), ("FINANCIAL", fin_senha), ("SUPPORT", sup_senha)):
        monkeypatch.setenv(f"{prefixo}_EMAIL", f"{prefixo.lower()}.env@ds.test")
        monkeypatch.setenv(f"{prefixo}_PASSWORD", senha)


def test_a13_startup_nao_cria_conta_do_env_com_senha_acima_de_72_bytes(banco, cursos, monkeypatch, capsys, caplog):
    senha_longa = "SenhaLongaDoAdminNoEnv-" + "X" * 60                      # > 72 bytes
    assert len(senha_longa.encode()) > 72
    _env_funcionarios(monkeypatch, senha_longa, SENHA_72_ACENTOS, SENHA_72_ASCII)
    from app import app as fastapi_app

    with caplog.at_level("DEBUG"):
        with TestClient(fastapi_app) as c:
            assert _usuario("admin.env@ds.test") is None, "conta com senha acima de 72 bytes não pode ser criada"
            fin = _usuario("financial.env@ds.test")
            sup = _usuario("support.env@ds.test")
            assert fin is not None and fin["role"] == "financial", "as contas válidas continuam sendo criadas"
            assert sup is not None and sup["role"] == "support", "as contas válidas continuam sendo criadas"
            _login_ok(c, "financial.env@ds.test", SENHA_72_ACENTOS)
            _login_ok(c, "support.env@ds.test", SENHA_72_ASCII)
            r = _login(c, "admin.env@ds.test", senha_longa)
            assert r.status_code == 400 and r.json()["detail"] == ERRO_LOGIN

    saida = capsys.readouterr()
    log = saida.out + saida.err + caplog.text
    assert "[AVISO]" in log, f"esperado um [AVISO] no log para a conta não criada; log = {log[-800:]!r}"
    assert senha_longa not in log, "o log nunca pode conter a senha"
    assert "X" * 20 not in log, "o log nunca pode conter trechos da senha"


def test_a14_startup_cria_todas_as_contas_validas_do_env_inclusive_72_bytes(banco, cursos, monkeypatch, capsys):
    _env_funcionarios(monkeypatch, SENHA_72_ACENTOS, SENHA_72_ASCII, SENHA_72_SO_ACENTOS)
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        for prefixo, perfil, senha in (("admin", "admin", SENHA_72_ACENTOS),
                                       ("financial", "financial", SENHA_72_ASCII),
                                       ("support", "support", SENHA_72_SO_ACENTOS)):
            conta = _usuario(f"{prefixo}.env@ds.test")
            assert conta is not None and conta["role"] == perfil, f"conta {prefixo} deveria ser criada"
            _login_ok(c, conta["email"], senha)
    saida = capsys.readouterr()
    for senha in (SENHA_72_ACENTOS, SENHA_72_ASCII, SENHA_72_SO_ACENTOS):
        assert senha not in saida.out + saida.err, "o log nunca contém a senha"


# =========================================================================================
# Grupo B - PUT /api/admin/course/{id} e materiais
# =========================================================================================

def _curso(course_id="curso_ds_a", **mud):
    base = {
        "id": course_id, "name": "Curso DS", "description": "Descricao original", "price": 100.0,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Todos",
        "objectives": ["obj1"], "topics": ["top1"], "benefits": ["ben1"],
        "faq": [{"question": "q1", "answer": "a1"}], "system_prompt": "prompt original",
    }
    base.update(mud)
    return base


def _criar_ok(client, token, payload):
    r = client.post("/api/admin/create-course", json=payload, headers=_auth(token))
    assert r.status_code == 200, r.text
    return r


def _put(client, token, course_id, payload):
    return client.put(f"/api/admin/course/{course_id}", json=payload, headers=_auth(token))


def _put_ok(client, token, course_id, payload):
    r = _put(client, token, course_id, payload)
    assert r.status_code == 200, r.text
    return r


def _arquivo(cursos, course_id):
    return json.loads((cursos / f"{course_id}.json").read_text(encoding="utf-8"))


def _eventos_do_curso(course_id):
    return [e for e in _sql("SELECT * FROM audit_logs WHERE entity_id = ? ORDER BY id", (course_id,))
            if e["action"] in ("course.update", "course.price_change")]


def _mudancas(evento):
    valor = evento["changes"]
    lista = [] if valor in (None, "") else (json.loads(valor) if isinstance(valor, str) else valor)
    return {item["field"]: item for item in lista}


def _ultimo_evento(course_id):
    eventos = _eventos_do_curso(course_id)
    assert eventos, f"nenhum evento course.update/course.price_change para {course_id}"
    return eventos[-1]


def _aluno_com_matricula(client, email, course_id, status):
    """Aluno com senha e uma matrícula no status pedido (pending é o inicial; os demais por UPDATE direto)."""
    user_id = _conta(email, "student", SENHA_72_ASCII)
    enrollment_id = Database.create_enrollment(user_id, course_id, f"{course_id}:ds:{uuid.uuid4().hex}")
    Database.record_payment(enrollment_id, 100.0, "mercado_pago")
    if status != "pending":
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (status, enrollment_id))
    token = _login_ok(client, email, SENHA_72_ASCII)
    return SimpleNamespace(user_id=user_id, enrollment_id=enrollment_id, token=token, status=status)


def _minha_matricula(client, aluno):
    r = client.get("/api/student/enrollments", headers=_auth(aluno.token))
    assert r.status_code == 200, r.text
    corpo = r.json()
    itens = corpo["enrollments"] if isinstance(corpo, dict) and "enrollments" in corpo else corpo
    item = [i for i in itens if i["id"] == aluno.enrollment_id]
    assert len(item) == 1, itens
    return r, item[0]


def _urls(item):
    return {m["url"] for m in (item.get("materials") or [])}


def test_b0_setup_cursos_vao_para_diretorio_temporario(client, cursos):
    _criar_ok(client, _admin_token(), _curso("curso_ds_setup"))
    assert (cursos / "curso_ds_setup.json").exists()
    assert not (REPO_COURSES / "curso_ds_setup.json").exists()


def test_b1_put_sem_materials_preserva_os_materiais_gravados(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b1", materials=[MATERIAL_1, MATERIAL_2]))
    assert _arquivo(cursos, "curso_ds_b1")["materials"] == [MATERIAL_1, MATERIAL_2]

    novo = _curso("curso_ds_b1", duration_hours=12)
    assert "materials" not in novo
    _put_ok(client, admin, "curso_ds_b1", novo)

    gravado = _arquivo(cursos, "curso_ds_b1")
    assert gravado["duration_hours"] == 12, "o PUT deve aplicar os demais campos"
    assert gravado["materials"] == [MATERIAL_1, MATERIAL_2], "PUT sem `materials` não pode apagar os materiais"
    # a leitura administrativa também enxerga os materiais
    r = client.get("/api/admin/course/curso_ds_b1", headers=_auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["course"]["materials"] == [MATERIAL_1, MATERIAL_2]


def test_b2_trilha_nao_lista_materials_quando_o_put_nao_o_menciona(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b2", materials=[MATERIAL_1]))
    _put_ok(client, admin, "curso_ds_b2", _curso("curso_ds_b2", duration_hours=15))

    evento = _ultimo_evento("curso_ds_b2")
    assert evento["action"] == "course.update"
    mud = _mudancas(evento)
    assert set(mud) == {"duration_hours"}, f"changes deveria listar só duration_hours, veio {sorted(mud)}"


def test_b3_put_com_preco_novo_sem_materials_gera_price_change_sem_materials(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b3", materials=[MATERIAL_1, MATERIAL_2]))
    _put_ok(client, admin, "curso_ds_b3", _curso("curso_ds_b3", price=250.0))

    assert _arquivo(cursos, "curso_ds_b3")["materials"] == [MATERIAL_1, MATERIAL_2]
    evento = _ultimo_evento("curso_ds_b3")
    assert evento["action"] == "course.price_change"
    mud = _mudancas(evento)
    assert set(mud) == {"price"}, f"changes deveria listar só price, veio {sorted(mud)}"


def test_b4_put_com_materials_vazio_limpa_de_proposito_e_a_trilha_registra(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b4", materials=[MATERIAL_1, MATERIAL_2]))
    _put_ok(client, admin, "curso_ds_b4", _curso("curso_ds_b4", materials=[]))

    assert _arquivo(cursos, "curso_ds_b4")["materials"] == []
    mud = _mudancas(_ultimo_evento("curso_ds_b4"))
    assert "materials" in mud, f"limpar os materiais é uma mudança e deve estar na trilha: {sorted(mud)}"
    assert mud["materials"]["before"] in ([MATERIAL_1, MATERIAL_2], json.dumps([MATERIAL_1, MATERIAL_2]),
                                          json.dumps([MATERIAL_1, MATERIAL_2], ensure_ascii=False))
    assert mud["materials"]["after"] in ([], "[]")


def test_b5_put_com_novos_materiais_substitui_e_a_trilha_registra(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b5", materials=[MATERIAL_1]))
    _put_ok(client, admin, "curso_ds_b5", _curso("curso_ds_b5", materials=[MATERIAL_2, MATERIAL_3]))

    assert _arquivo(cursos, "curso_ds_b5")["materials"] == [MATERIAL_2, MATERIAL_3]
    mud = _mudancas(_ultimo_evento("curso_ds_b5"))
    assert "materials" in mud, sorted(mud)


def test_b6_put_com_os_mesmos_materiais_nao_registra_mudanca_de_materials(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b6", materials=[MATERIAL_1]))
    _put_ok(client, admin, "curso_ds_b6", _curso("curso_ds_b6", materials=[MATERIAL_1], duration_hours=11))

    assert _arquivo(cursos, "curso_ds_b6")["materials"] == [MATERIAL_1]
    assert set(_mudancas(_ultimo_evento("curso_ds_b6"))) == {"duration_hours"}


def test_b7_create_course_sem_materials_grava_lista_vazia(client, cursos):
    _criar_ok(client, _admin_token(), _curso("curso_ds_b7"))
    gravado = _arquivo(cursos, "curso_ds_b7")
    assert gravado.get("materials") == [], f"create-course sem materials grava [], veio {gravado.get('materials')!r}"


def test_b8_curso_antigo_sem_o_campo_materials_continua_aceito_no_put(client, cursos):
    antigo = {k: v for k, v in _curso("curso_ds_b8").items()}
    (cursos / "curso_ds_b8.json").write_text(json.dumps(antigo), encoding="utf-8")
    admin = _admin_token()

    _put_ok(client, admin, "curso_ds_b8", _curso("curso_ds_b8", duration_hours=20))

    gravado = _arquivo(cursos, "curso_ds_b8")
    assert gravado["duration_hours"] == 20
    assert not gravado.get("materials"), f"curso sem materiais continua sem materiais: {gravado.get('materials')!r}"
    assert "materials" not in _mudancas(_ultimo_evento("curso_ds_b8"))


@pytest.mark.parametrize("campo", ["objectives", "topics", "benefits", "faq"])
def test_b9_campos_de_lista_obrigatorios_continuam_obrigatorios(client, cursos, campo):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b9", materials=[MATERIAL_1]))
    antes = _arquivo(cursos, "curso_ds_b9")

    sem_campo = _curso("curso_ds_b9", duration_hours=99)
    del sem_campo[campo]
    r = _put(client, admin, "curso_ds_b9", sem_campo)
    assert r.status_code == 422, f"PUT sem {campo}: HTTP {r.status_code} {r.text[:200]}"
    assert _arquivo(cursos, "curso_ds_b9") == antes, "PUT rejeitado não pode alterar o arquivo do curso"

    sem_campo["id"] = "curso_ds_b9_novo"
    r = client.post("/api/admin/create-course", json=sem_campo, headers=_auth(admin))
    assert r.status_code == 422, f"POST sem {campo}: HTTP {r.status_code} {r.text[:200]}"
    assert not (cursos / "curso_ds_b9_novo.json").exists()


def test_b10_aluno_ativo_continua_vendo_os_materiais_depois_de_um_put_que_nao_os_menciona(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b10", materials=[MATERIAL_1, MATERIAL_2]))
    aluno = _aluno_com_matricula(client, "ativo.b10@ds.test", "curso_ds_b10", "active")

    _, antes = _minha_matricula(client, aluno)
    assert _urls(antes) == {MATERIAL_1["url"], MATERIAL_2["url"]}, "seed: o aluno ativo vê os materiais"

    _put_ok(client, admin, "curso_ds_b10", _curso("curso_ds_b10", description="Descricao nova"))

    r, depois = _minha_matricula(client, aluno)
    assert depois["status"] == "active"
    assert _urls(depois) == {MATERIAL_1["url"], MATERIAL_2["url"]}, \
        "o PUT que não menciona `materials` não pode tirar os materiais do aluno com matrícula ativa"


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_b11_sem_matricula_ativa_nenhuma_url_aparece_antes_nem_depois_do_put(client, cursos, status):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b11", materials=[MATERIAL_1, MATERIAL_2]))
    aluno = _aluno_com_matricula(client, f"inativo.b11.{status}@ds.test", "curso_ds_b11", status)

    def checar():
        r, item = _minha_matricula(client, aluno)
        assert item["status"] == status
        assert not item.get("materials"), f"{status} não libera materiais: {item.get('materials')}"
        for material in (MATERIAL_1, MATERIAL_2, MATERIAL_3):
            assert material["url"] not in r.text, f"URL de material vazou para matrícula {status}"

    checar()
    _put_ok(client, admin, "curso_ds_b11", _curso("curso_ds_b11", description="Descricao nova"))   # sem materials
    checar()
    _put_ok(client, admin, "curso_ds_b11", _curso("curso_ds_b11", materials=[MATERIAL_3]))        # troca
    checar()


def test_b12_aluno_ativo_ve_os_materiais_novos_apos_substituicao_e_nenhum_apos_limpar(client, cursos):
    admin = _admin_token()
    _criar_ok(client, admin, _curso("curso_ds_b12", materials=[MATERIAL_1]))
    aluno = _aluno_com_matricula(client, "ativo.b12@ds.test", "curso_ds_b12", "active")

    _put_ok(client, admin, "curso_ds_b12", _curso("curso_ds_b12", materials=[MATERIAL_2]))
    r, item = _minha_matricula(client, aluno)
    assert _urls(item) == {MATERIAL_2["url"]}
    assert MATERIAL_1["url"] not in r.text

    _put_ok(client, admin, "curso_ds_b12", _curso("curso_ds_b12", materials=[]))
    _, item = _minha_matricula(client, aluno)
    assert item["materials"] == []


# =========================================================================================
# Grupo C - corrida no token de definição de senha
# =========================================================================================

N_CONCORRENTES = 8


def _conta_sem_senha(email):
    user_id = Database.get_or_create_user(email, "Aluno Corrida")
    assert _usuario(email)["password_hash"] is None
    return user_id, emitir_token_definicao(user_id)


def _disparar_simultaneos(tarefa, quantidade):
    """Executa `tarefa(i)` em `quantidade` threads liberadas juntas por uma barreira; devolve os resultados em ordem."""
    barreira = threading.Barrier(quantidade)
    resultados = [None] * quantidade
    erros = []

    def trabalhador(i):
        try:
            barreira.wait(timeout=30)
            resultados[i] = tarefa(i)
        except Exception as exc:  # noqa: BLE001 - o teste reporta qualquer falha de thread
            erros.append((i, repr(exc)))

    threads = [threading.Thread(target=trabalhador, args=(i,)) for i in range(quantidade)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not erros, f"threads com erro: {erros}"
    assert all(r is not None for r in resultados), "alguma thread não terminou"
    return resultados


@pytest.mark.parametrize("rodada", [1, 2, 3])
def test_c1_pedidos_simultaneos_com_o_mesmo_token_so_um_vence(client, rodada):
    from app import app as fastapi_app

    email = f"corrida.c1.{rodada}@ds.test"
    user_id, token = _conta_sem_senha(email)
    senhas = [f"senha-concorrente-{rodada}-{i}-ok" for i in range(N_CONCORRENTES)]

    def tarefa(i):
        # Um TestClient por thread, sem `with`: cada requisição roda no próprio laço de eventos (concorrência real).
        r = TestClient(fastapi_app).post("/api/auth/password-setup", json={"token": token, "password": senhas[i]})
        return (i, r.status_code, r.text)

    resultados = _disparar_simultaneos(tarefa, N_CONCORRENTES)

    codigos = sorted(codigo for _, codigo, _ in resultados)
    assert codigos == [200] + [400] * (N_CONCORRENTES - 1), f"respostas = {[(i, c) for i, c, _ in resultados]}"
    vencedor = [i for i, codigo, _ in resultados if codigo == 200][0]

    _login_ok(client, email, senhas[vencedor])                       # a conta ficou com a senha do vencedor
    for i, senha in enumerate(senhas):
        if i != vencedor:
            r = _login(client, email, senha)
            assert r.status_code == 400, f"a senha do perdedor {i} não pode autenticar (HTTP {r.status_code})"

    registro = _sql("SELECT * FROM password_setup_tokens WHERE user_id = ?", (user_id,))
    assert len(registro) == 1 and registro[0]["used_at"] is not None, registro
    # os perdedores não ecoam token nem senha
    for _, codigo, texto in resultados:
        if codigo == 400:
            assert token not in texto and all(s not in texto for s in senhas)


@pytest.mark.parametrize("rodada", [1, 2, 3])
def test_c2_corrida_direta_no_banco_so_uma_definicao_vence(banco, rodada):
    """Mesma garantia, sem HTTP: `definir_senha_pelo_token` em threads sobre o mesmo token."""
    from core.password_setup import definir_senha_pelo_token

    email = f"corrida.c2.{rodada}@ds.test"
    user_id, token = _conta_sem_senha(email)
    senhas = [f"senha-direta-{rodada}-{i}-ok" for i in range(N_CONCORRENTES)]

    resultados = _disparar_simultaneos(lambda i: (i, definir_senha_pelo_token(token, senhas[i])), N_CONCORRENTES)

    vencedores = [i for i, ok in resultados if ok is True]
    assert len(vencedores) == 1, f"exatamente uma definição deveria vencer, venceram {vencedores}"
    assert [ok for _, ok in resultados].count(False) == N_CONCORRENTES - 1
    hash_final = _usuario(email)["password_hash"]
    assert verify_password(senhas[vencedores[0]], hash_final) is True
    assert not any(verify_password(s, hash_final) for i, s in enumerate(senhas) if i != vencedores[0])
    assert _sql("SELECT used_at FROM password_setup_tokens WHERE user_id = ?", (user_id,))[0]["used_at"] is not None


def test_c3_token_usado_e_recusado_e_nao_troca_a_senha(client):
    email = "usado.c3@ds.test"
    _, token = _conta_sem_senha(email)
    primeira, segunda = "primeira-senha-c3-ok", "segunda-senha-c3-ok"
    assert client.post("/api/auth/password-setup", json={"token": token, "password": primeira}).status_code == 200
    r = client.post("/api/auth/password-setup", json={"token": token, "password": segunda})
    assert r.status_code == 400, r.text
    _login_ok(client, email, primeira)
    assert _login(client, email, segunda).status_code == 400


def test_c4_token_expirado_e_recusado_e_a_conta_continua_sem_senha(client):
    email = "expirado.c4@ds.test"
    user_id, token = _conta_sem_senha(email)
    passado = (datetime.utcnow() - timedelta(hours=1)).isoformat(sep=" ", timespec="seconds")
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE user_id = ?", (passado, user_id))

    r = client.post("/api/auth/password-setup", json={"token": token, "password": "senha-tarde-demais-ok"})
    assert r.status_code == 400, r.text
    assert _usuario(email)["password_hash"] is None
    assert _sql("SELECT used_at FROM password_setup_tokens WHERE user_id = ?", (user_id,))[0]["used_at"] is None
    assert _login(client, email, "senha-tarde-demais-ok").status_code == 400


def test_c5_token_inexistente_ou_forjado_e_recusado(client):
    email = "forjado.c5@ds.test"
    _conta_sem_senha(email)
    for token in ("token-que-nunca-foi-emitido-" + "x" * 32, "", "A" * 1000):
        r = client.post("/api/auth/password-setup", json={"token": token, "password": "senha-valida-c5-ok"})
        assert r.status_code == 400, f"token {token[:20]!r}: HTTP {r.status_code} {r.text[:200]}"
    assert _usuario(email)["password_hash"] is None


def test_c6_user_id_do_cliente_e_ignorado_no_corpo(client):
    """IDOR (já coberto na E2): o alvo é sempre o dono do token, mesmo com user_id de outra conta no corpo."""
    dono, token = _conta_sem_senha("dono.c6@ds.test")
    outro, _ = _conta_sem_senha("outro.c6@ds.test")
    r = client.post("/api/auth/password-setup",
                    json={"token": token, "password": "senha-do-dono-c6-ok", "user_id": outro})
    assert r.status_code == 200, r.text
    assert _usuario("dono.c6@ds.test")["password_hash"]
    assert _usuario("outro.c6@ds.test")["password_hash"] is None
    assert dono != outro
