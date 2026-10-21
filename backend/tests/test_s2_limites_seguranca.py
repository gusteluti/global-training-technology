"""S2/S9/S10 - Limite de tentativas de login, limite de taxa e id de curso (D79, modo autonomo D69).

Escritos ANTES da implementacao. Devem falhar agora: /api/token e /api/admin/login nao limitam tentativas, /api/chat e
os checkouts nao limitam taxa, o ManagerAgent nao tem teto de sessoes anonimas e o `id` do curso nao e validado (o
create grava fora do diretorio de cursos com `..\\x`, e as rotas com `course_id` na URL montam caminho de arquivo com
qualquer texto).

Contrato (D79, textos exatos):
  S10 POST /api/admin/create-course so aceita `id` que case com ^[a-z0-9][a-z0-9_-]{0,63}$ (string inteira); senao
      422 detail ERRO_ID e nada e gravado. Rotas com `course_id` na URL (GET/PUT/DELETE do curso, archive/unarchive,
      turmas publicas, alunos do curso e CSV): id fora do padrao -> 404 igual ao de curso inexistente, sem montar
      caminho de arquivo (nem para arquivo legado com nome fora do padrao, nem para arquivo fora do diretorio).
  S2  POST /api/token: 5 falhas do MESMO e-mail (sem caixa, aparado) em 15 min bloqueiam o e-mail por 15 min; 20
      falhas do MESMO IP em 15 min bloqueiam o IP por 15 min. Bloqueado -> 429 detail ERRO_LOGIN, mesmo com a senha
      certa. E-mail inexistente conta igual. Sucesso zera as falhas do e-mail. POST /api/admin/login: limite por IP.
      Estado na tabela `login_attempts` (sobrevive a restart). Primeiro bloqueio grava `auth.locked` (e-mail
      mascarado ou IP; nunca a senha).
  S9  POST /api/chat: 30 mensagens por minuto por IP -> 429 ERRO_CHAT; teto de 5000 sessoes anonimas (descarta a
      menos recente). Checkouts (aluno e landing): 10 por minuto por IP (e por aluno no fluxo logado) -> 429
      ERRO_CHECKOUT. Estado em memoria criado no startup do app.
  IP = request.client.host (X-Forwarded-For nao e confiavel).

Grupos
  A  S10 create-course: ids invalidos -> 422 texto exato, nada gravado (nem no diretorio pai); ids validos criam
  B  S10 rotas com course_id na URL (e checkouts com course_id no corpo): id fora do padrao -> 404 de inexistente
  C  S2 login por e-mail (caixa/espacos, inexistente sem enumeracao, sucesso zera, janela, persistencia, staff)
  D  S2 login por IP (/api/token e /api/admin/login legado), X-Forwarded-For ignorado
  E  S2 auditoria `auth.locked`
  F  S9 chat anonimo (30/min por IP, outro IP livre, XFF ignorado, teto de sessoes, reinicio no startup)
  G  S9 checkouts (10/min por IP e por aluno, nada criado no 429, reinicio no startup)
  R  Regressoes: chamadas normais nao sao afetadas

Convencoes e escolhas de forma do teste (ver relatorio do agente-testes):
  - IP variado com o parametro `client=(host, porta)` do TestClient. O primeiro cliente usa `with` (dispara o
    startup); os clientes de outro IP sao criados SEM `with`, para compartilhar o mesmo estado do app sem novo startup.
  - 429 de chat e checkout: o texto exato pode vir em `detail` (padrao HTTPException) ou em `message` (padrao do
    corpo do chat); o login exige `detail` (padrao do /api/token).
  - Janela de 15 min do login: o teste "avanca o relogio" recuando TODAS as datas da tabela `login_attempts` (texto
    ISO ou epoch), sem depender do nome das colunas. Isso tambem prova que o estado vem da tabela.
  - Teto de sessoes: o teste troca `agents.manager_agent.MAX_ANON_SESSIONS` (nome escolhido pelo teste, padrao 5000)
    por 3. "Menos recente" = a sessao criada e usada ha mais tempo (o teste nao distingue criacao de uso).
  - Banco temporario do conftest; cursos em diretorio temporario (padrao F1: COURSES_DIR e __file__ de admin.routes);
    catalogo do bot temporario (D70); LLM e Mercado Pago falsos. Nada toca backend/db.sqlite, backend/courses, o
    Groq ou a rede.
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import admin.routes as admin_routes
from agents.groq_client import GroqChatClient
from core.security import Role, create_access_token, create_admin_token, get_password_hash
from db import Database

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_COURSES = BACKEND_DIR / "courses"

ERRO_ID = "Id do curso inválido: use letras minúsculas, números, _ ou -."
ERRO_LOGIN = "Muitas tentativas. Tente novamente em alguns minutos."
ERRO_CHAT = "Muitas mensagens em pouco tempo. Aguarde um instante."
ERRO_CHECKOUT = "Muitas tentativas de compra em pouco tempo. Aguarde um instante."
ERRO_CREDENCIAIS = "Usuário ou senha inválidos"
DETAIL_404 = "Course not found"

SENHA = "senha-certa-s2-2026"
SENHA_ERRADA = "senha-errada-s2"
SENHA_LEGADO = "admin123"  # ADMIN_PASSWORD do conftest
ROTA_LOGIN = "/api/token"
ROTA_LEGADO = "/api/admin/login"
ROTA_CHAT = "/api/chat"
ROTA_ALUNO = "/api/student/checkout"
ROTA_LANDING = "/api/payments/create-checkout"
CURSO = "curso_s2"
PRECO = 120.0
URL_GATEWAY = "https://mp.test/s2/checkout"
IP_A = ("10.20.30.40", 50001)
IP_B = ("10.20.30.41", 50002)


# =========================================================================================
# Fixtures
# =========================================================================================

def _foto_arvore(raiz):
    """Todos os arquivos e pastas sob `raiz` (exceto o SQLite temporario), com tamanho e mtime."""
    raiz = Path(raiz)
    if not raiz.exists():
        return []
    itens = []
    for p in raiz.rglob("*"):
        if p.name.startswith("db.sqlite"):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        itens.append((str(p.relative_to(raiz)), p.is_dir(), st.st_size if p.is_file() else 0,
                      st.st_mtime_ns if p.is_file() else 0))
    return sorted(itens)


def _foto_backend():
    """Arquivos do topo de backend/ e de backend/courses (o create com `..` nao pode gravar aqui)."""
    topo = sorted(p.name for p in BACKEND_DIR.iterdir())
    cursos = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REPO_COURSES.iterdir()) \
        if REPO_COURSES.exists() else []
    return topo, cursos


@pytest.fixture(autouse=True)
def ambiente_s2(monkeypatch, tmp_path):
    """Pagamento simulado desligado; token de gateway de teste; nada vem do backend/.env local."""
    monkeypatch.delenv("PAYMENTS_MOCK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN", "TEST-fake-s2")
    monkeypatch.setenv("PASSWORD_LINK_OUTBOX", str(tmp_path / "outbox.jsonl"))


def _dados_curso(course_id, nome="Curso S2", preco=PRECO):
    return {
        "id": course_id, "name": nome, "description": f"Descricao de {nome}", "price": preco,
        "duration_hours": 10, "level": "Iniciante", "target_audience": "Todos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta?", "answer": "Resposta."}],
        "system_prompt": f"Voce e o assistente do {nome}.",
        "materials": [],
    }


def _escrever(diretorio, nome_arquivo, dados):
    (Path(diretorio) / nome_arquivo).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def cursos(tmp_path, monkeypatch):
    """Diretorio temporario de cursos: um curso valido, um arquivo legado com id fora do padrao e, FORA do diretorio
    (no pai, tmp_path), um arquivo 'segredo.json' que so seria lido por travessia de caminho."""
    antes = _foto_backend()
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    _escrever(diretorio, f"{CURSO}.json", _dados_curso(CURSO))
    _escrever(diretorio, "Legado_X.json", _dados_curso("Legado_X", "Curso Legado Maiusculo"))
    _escrever(diretorio, "com espaco.json", _dados_curso("com espaco", "Curso Legado Com Espaco"))
    _escrever(tmp_path, "segredo.json", _dados_curso("segredo", "Curso Segredo Fora Do Diretorio", 1.0))
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    monkeypatch.setattr(admin_routes, "__file__", str(tmp_path / "admin" / "routes.py"))
    yield diretorio
    assert _foto_backend() == antes, "o teste alterou backend/ ou backend/courses (deveria usar o diretorio temporario)"


@pytest.fixture
def bot_no_diretorio_temporario(cursos, catalogo_bot):
    """Catalogo do bot isolado (D70); os cursos do admin ficam no diretorio temporario de `cursos`."""
    return catalogo_bot


class LLMFalso:
    def __init__(self):
        self.chamadas = 0

    def responder(self, messages, max_tokens):
        self.chamadas += 1
        if max_tokens is not None and max_tokens <= 300:
            return "GENERAL"
        return f"RESPOSTA-S2-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def llm(monkeypatch):
    falso = LLMFalso()

    def create(self, messages, max_tokens=1024, temperature=0.7):
        return falso.responder(messages, max_tokens)

    monkeypatch.setattr(GroqChatClient, "create_chat_completion", create)
    return falso


@pytest.fixture
def app_s2(banco, cursos, bot_no_diretorio_temporario, llm):
    from app import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app_s2):
    """Cliente principal (IP_A), com startup."""
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as c:
        yield c


def _outro_ip(app, ip=IP_B):
    """Cliente de outro IP no MESMO app (sem `with`: nao dispara novo startup, compartilha o estado)."""
    return TestClient(app, client=ip, raise_server_exceptions=False)


class GatewayFalso:
    def __init__(self):
        self.post_chamadas = []

    def post(self, url, *args, **kwargs):
        self.post_chamadas.append((url, kwargs))
        n = len(self.post_chamadas)
        resposta = MagicMock(status_code=201)
        resposta.json.return_value = {"id": f"pref-s2-{n}", "init_point": f"{URL_GATEWAY}/{n}"}
        resposta.text = json.dumps({"id": f"pref-s2-{n}"})
        return resposta

    def get(self, url, *args, **kwargs):
        resposta = MagicMock(status_code=404)
        resposta.json.return_value = {"message": "not found"}
        resposta.text = '{"message": "not found"}'
        return resposta


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


def _admin():
    return {"Authorization": f"Bearer {create_admin_token(Role.ADMIN)}"}


def _conta(email, nome="Aluno S2", perfil="student", senha=SENHA):
    user_id = Database.add_user(email, nome, get_password_hash(senha), role=perfil)
    assert user_id is not None, f"seed: conta {email} ja existe"
    token = create_access_token({"user_id": user_id, "email": email, "role": perfil})
    return SimpleNamespace(id=user_id, email=email, token=token)


def _login(c, email, senha, **kwargs):
    return c.post(ROTA_LOGIN, data={"username": email, "password": senha}, **kwargs)


def _resumo(r):
    try:
        corpo = r.json()
    except Exception:
        corpo = r.text
    return r.status_code, corpo


def _falhar(c, email, vezes):
    """`vezes` logins com senha errada; cada um tem de ser a falha comum (400), nao o bloqueio."""
    resumos = []
    for i in range(vezes):
        r = _login(c, email, SENHA_ERRADA)
        assert r.status_code == 400, f"falha {i + 1} de {email!r}: esperado 400, veio {_resumo(r)}"
        resumos.append(_resumo(r))
    return resumos


def _assert_429_login(r):
    assert r.status_code == 429, f"esperado 429 (bloqueado), veio {_resumo(r)}"
    assert r.json().get("detail") == ERRO_LOGIN, f"texto do 429 diferente: {r.json()}"
    assert "access_token" not in r.text


def _assert_login_ok(r):
    assert r.status_code == 200, f"esperado 200, veio {_resumo(r)}"
    assert r.json().get("access_token")


def _texto(r):
    corpo = r.json()
    if isinstance(corpo.get("detail"), str):
        return corpo["detail"]
    return corpo.get("message")


def _tabela_existe(nome):
    return bool(_sql("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (nome,)))


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def _recuar(valor, minutos):
    """Recua um valor de data (texto ISO ou epoch em s/ms) em `minutos`, preservando o formato. Outros: igual."""
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, (int, float)):
        if 1e9 <= valor < 1e10:
            return type(valor)(valor - minutos * 60)
        if 1e12 <= valor < 1e13:
            return type(valor)(valor - minutos * 60_000)
        return valor
    if isinstance(valor, str) and _ISO.match(valor.strip()):
        texto = valor.strip()
        zulu = texto.endswith("Z")
        dt = datetime.fromisoformat(texto[:-1] + "+00:00" if zulu else texto)
        novo = dt - timedelta(minutes=minutos)
        timespec = "seconds"
        if "." in texto:
            timespec = "microseconds"
        elif texto.count(":") == 1 or (len(texto) >= 16 and texto[16:17] not in (":",)):
            timespec = "minutes"
        saida = novo.isoformat(sep=texto[10], timespec=timespec)
        if zulu:
            saida = saida.replace("+00:00", "Z")
        return saida
    return valor


def _avancar_relogio(minutos):
    """'Avanca o relogio' do limite de login recuando todas as datas gravadas em `login_attempts`."""
    assert _tabela_existe("login_attempts"), "tabela login_attempts nao existe (estado do limite tem de ir para o banco)"
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(login_attempts)")]
        linhas = conn.execute(f"SELECT rowid, {', '.join(colunas)} FROM login_attempts").fetchall()
        alteradas = 0
        for linha in linhas:
            rowid, valores = linha[0], linha[1:]
            novos = {col: _recuar(v, minutos) for col, v in zip(colunas, valores)}
            mudou = {col: v for col, v in novos.items() if v != dict(zip(colunas, valores))[col]}
            if mudou:
                alteradas += 1
                sets = ", ".join(f"{col} = ?" for col in mudou)
                conn.execute(f"UPDATE login_attempts SET {sets} WHERE rowid = ?", (*mudou.values(), rowid))
        conn.commit()
    finally:
        conn.close()
    assert alteradas > 0, "nenhuma data reconhecivel em login_attempts (texto ISO ou epoch) para recuar"


def _eventos(action):
    return _sql("SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))


def _contagens():
    return {
        "users": len(_sql("SELECT id FROM users")),
        "enrollments": len(_sql("SELECT id FROM enrollments")),
        "payments": len(_sql("SELECT id FROM payments")),
    }


def _foto_compras():
    return (
        _sql("SELECT id, user_id, course_id, status, external_reference FROM enrollments ORDER BY id"),
        _sql("SELECT id, enrollment_id, amount, status, payment_method, transaction_id FROM payments ORDER BY id"),
    )


def _chat(c, texto="Quais cursos voces oferecem?", session_id=None, **kwargs):
    corpo = {"message": texto}
    if session_id is not None:
        corpo["session_id"] = session_id
    return c.post(ROTA_CHAT, json=corpo, **kwargs)


def _comprar_aluno(c, token, course_id=CURSO):
    return c.post(ROTA_ALUNO, json={"course_id": course_id}, headers={"Authorization": f"Bearer {token}"})


def _comprar_landing(c, email, course_id=CURSO):
    return c.post(ROTA_LANDING, json={"course_id": course_id, "payer": {"name": "Comprador S2", "email": email}})


# =========================================================================================
# A - S10: id do curso no create
# =========================================================================================

IDS_INVALIDOS = [
    pytest.param("../x", id="pai-barra"),
    pytest.param("..\\x", id="pai-contrabarra"),
    pytest.param("a/b", id="barra"),
    pytest.param("A_Maiusculo", id="maiuscula"),
    pytest.param("com espaço", id="espaco"),
    pytest.param("", id="vazio"),
    pytest.param("a" * 65, id="65-caracteres"),
    pytest.param(".json", id="ponto-json"),
    pytest.param("-comeca-com-hifen", id="inicio-hifen"),
    pytest.param("_comeca-com-sublinhado", id="inicio-sublinhado"),
    pytest.param("ação", id="acento"),
    pytest.param("abc\n", id="quebra-de-linha-no-fim"),
    pytest.param("abc.json", id="com-ponto"),
]

IDS_VALIDOS = [
    pytest.param("a", id="1-caractere"),
    pytest.param("0curso", id="inicio-digito"),
    pytest.param("curso-novo_2026", id="hifen-e-sublinhado"),
    pytest.param("b" * 64, id="64-caracteres"),
]


@pytest.mark.parametrize("course_id", IDS_INVALIDOS)
def test_a1_create_com_id_invalido_devolve_422_com_texto_exato_e_nada_e_gravado(client, cursos, tmp_path, course_id):
    antes = _foto_arvore(tmp_path)
    eventos_antes = len(_eventos("course.create"))
    r = client.post("/api/admin/create-course", json=_dados_curso(course_id), headers=_admin())
    assert r.status_code == 422, f"id {course_id!r}: esperado 422, veio {_resumo(r)}"
    assert r.json().get("detail") == ERRO_ID, f"id {course_id!r}: detail diferente: {r.json()}"
    # nada gravado: nem no diretorio de cursos, nem no diretorio pai (tmp_path), nem em backend/ (fixture `cursos`)
    assert _foto_arvore(tmp_path) == antes, f"id {course_id!r}: arquivo criado ou alterado"
    assert len(_eventos("course.create")) == eventos_antes, "422 nao grava course.create"


@pytest.mark.parametrize("course_id", IDS_VALIDOS)
def test_a2_create_com_id_valido_continua_criando(client, cursos, course_id):
    r = client.post("/api/admin/create-course", json=_dados_curso(course_id), headers=_admin())
    assert r.status_code == 200, f"id {course_id!r}: esperado 200, veio {_resumo(r)}"
    arquivo = cursos / f"{course_id}.json"
    assert arquivo.exists(), f"id {course_id!r}: arquivo do curso nao foi criado em {cursos}"
    assert json.loads(arquivo.read_text(encoding="utf-8"))["id"] == course_id


def test_a3_id_invalido_sem_token_e_401_e_com_perfil_sem_permissao_e_403_sem_gravar(client, cursos, tmp_path):
    antes = _foto_arvore(tmp_path)
    sem_token = client.post("/api/admin/create-course", json=_dados_curso("../x"))
    assert sem_token.status_code == 401, _resumo(sem_token)
    suporte = client.post("/api/admin/create-course", json=_dados_curso("../x"),
                          headers={"Authorization": f"Bearer {create_admin_token(Role.SUPPORT)}"})
    assert suporte.status_code == 403, _resumo(suporte)
    assert _foto_arvore(tmp_path) == antes


def test_a4_id_duplicado_valido_continua_400(client, cursos):
    r = client.post("/api/admin/create-course", json=_dados_curso(CURSO), headers=_admin())
    assert r.status_code == 400, _resumo(r)


# =========================================================================================
# B - S10: course_id na URL (e no corpo dos checkouts) fora do padrao -> 404 de inexistente
# =========================================================================================

# Ids que montariam caminho de arquivo existente hoje: arquivo legado com nome fora do padrao (maiuscula, espaco) e
# arquivo FORA do diretorio de cursos alcancado por contrabarra (Windows).
IDS_URL_INVALIDOS = [
    pytest.param("Legado_X", id="legado-maiusculo"),
    pytest.param("com espaco", id="legado-com-espaco"),
    pytest.param("..\\segredo", id="travessia-contrabarra"),
]


def _rotas(course_id):
    """(metodo, caminho, kwargs) de toda rota com course_id na URL. O id vai codificado na URL."""
    from urllib.parse import quote

    cid = quote(course_id, safe="")
    corpo = _dados_curso("corpo_valido_s2")  # id do corpo valido: o teste isola o id da URL
    return [
        ("GET", f"/api/admin/course/{cid}", {}),
        ("PUT", f"/api/admin/course/{cid}", {"json": corpo}),
        ("DELETE", f"/api/admin/course/{cid}", {}),
        ("POST", f"/api/admin/course/{cid}/archive", {}),
        ("POST", f"/api/admin/course/{cid}/unarchive", {}),
        ("GET", f"/api/courses/{cid}/turmas", {}),
        ("GET", f"/api/dashboard/cursos/{cid}/alunos", {}),
        ("GET", f"/api/dashboard/cursos/{cid}/alunos.csv", {}),
    ]


@pytest.mark.parametrize("course_id", IDS_URL_INVALIDOS)
def test_b1_rotas_com_course_id_invalido_na_url_respondem_como_curso_inexistente(client, cursos, tmp_path, course_id):
    antes = _foto_arvore(tmp_path)
    inexistentes = {(m, i): _resumo(client.request(m, c, headers=_admin(), **k))
                    for i, (m, c, k) in enumerate(_rotas("nao_existe_s2"))}
    for i, (metodo, caminho, kwargs) in enumerate(_rotas(course_id)):
        r = client.request(metodo, caminho, headers=_admin(), **kwargs)
        esperado = inexistentes[(metodo, i)]
        assert esperado[0] == 404, f"controle: {metodo} {caminho} com id inexistente devolveu {esperado}"
        assert _resumo(r) == esperado, f"{metodo} {caminho}: esperado {esperado} (inexistente), veio {_resumo(r)}"
    assert _foto_arvore(tmp_path) == antes, "rota com id invalido alterou, removeu ou criou arquivo"


def test_b2_get_com_travessia_nao_le_arquivo_fora_do_diretorio(client, cursos):
    r = client.get("/api/admin/course/..%5Csegredo", headers=_admin())
    assert r.status_code == 404, _resumo(r)
    assert "Fora Do Diretorio" not in r.text
    publico = client.get("/api/courses/..%5Csegredo/turmas")
    assert publico.status_code == 404, _resumo(publico)


def test_b3_curso_com_id_valido_continua_igual_nas_rotas(client, cursos):
    r = client.get(f"/api/admin/course/{CURSO}", headers=_admin())
    assert r.status_code == 200, _resumo(r)
    assert r.json()["course"]["id"] == CURSO
    assert client.get(f"/api/courses/{CURSO}/turmas").status_code == 200
    assert client.get(f"/api/dashboard/cursos/{CURSO}/alunos", headers=_admin()).status_code == 200


def test_b4_turma_nao_e_criada_para_curso_com_id_fora_do_padrao(client, cursos):
    for course_id in ("Legado_X", "com espaco", "..\\segredo"):
        r = client.post("/api/admin/classes", json={"course_id": course_id, "name": "Turma S2"}, headers=_admin())
        assert r.status_code == 404, f"{course_id!r}: {_resumo(r)}"
    assert _sql("SELECT id FROM classes") == []


@pytest.mark.parametrize("course_id", ["..\\segredo", "Legado_X"])
def test_b5_checkouts_com_course_id_fora_do_padrao_nao_vendem_nada(client, cursos, gw, course_id):
    """Extensao mecanica da D79 ("id fora do padrao nunca monta caminho"): o checkout le o curso pelo mesmo caminho."""
    aluno = _conta("aluno.b5@s2.test")
    antes = _contagens()
    r_aluno = _comprar_aluno(client, aluno.token, course_id)
    r_landing = _comprar_landing(client, "landing.b5@s2.test", course_id)
    assert r_aluno.status_code == 404, _resumo(r_aluno)
    assert r_landing.status_code == 404, _resumo(r_landing)
    assert _contagens() == antes
    assert gw.post_chamadas == []


# =========================================================================================
# C - S2: login por e-mail
# =========================================================================================

def test_c1_cinco_falhas_bloqueiam_e_a_sexta_com_a_senha_certa_recebe_429(client):
    conta = _conta("ana.c1@s2.test")
    _falhar(client, conta.email, 5)
    _assert_429_login(_login(client, conta.email, SENHA))


def test_c2_quatro_falhas_ainda_deixam_entrar(client):
    conta = _conta("ana.c2@s2.test")
    _falhar(client, conta.email, 4)
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_c3_caixa_e_espacos_do_email_nao_contornam_o_limite(client):
    conta = _conta("ana.c3@s2.test")
    variantes = ["ANA.C3@S2.TEST", " ana.c3@s2.test", "Ana.C3@s2.test ", "  aNa.c3@S2.test  ", "ana.c3@s2.test"]
    for email in variantes:
        r = _login(client, email, SENHA_ERRADA)
        assert r.status_code == 400, f"{email!r}: {_resumo(r)}"
    _assert_429_login(_login(client, conta.email, SENHA))
    _assert_429_login(_login(client, "ANA.C3@S2.TEST", SENHA))


def test_c4_email_inexistente_bloqueia_igual_e_as_respostas_sao_identicas(client):
    conta = _conta("ana.c4@s2.test")
    existente = _falhar(client, conta.email, 5) + [_resumo(_login(client, conta.email, SENHA))]
    inexistente = _falhar(client, "ninguem.c4@s2.test", 5) + [_resumo(_login(client, "ninguem.c4@s2.test", SENHA))]
    assert existente[-1][0] == 429 and existente[-1][1].get("detail") == ERRO_LOGIN, existente[-1]
    assert existente == inexistente, f"respostas diferentes (enumeracao): {existente} x {inexistente}"
    for status, corpo in existente[:5]:
        assert (status, corpo.get("detail")) == (400, ERRO_CREDENCIAIS)


def test_c5_bloqueio_de_um_email_nao_afeta_outro_email(client):
    bloqueada = _conta("ana.c5@s2.test")
    livre = _conta("bia.c5@s2.test")
    _falhar(client, bloqueada.email, 5)
    _assert_429_login(_login(client, bloqueada.email, SENHA))
    _assert_login_ok(_login(client, livre.email, SENHA))


def test_c6_bloqueio_do_email_vale_de_outro_ip(app_s2, client):
    conta = _conta("ana.c6@s2.test")
    _falhar(client, conta.email, 5)
    _assert_429_login(_login(_outro_ip(app_s2), conta.email, SENHA))


def test_c7_sucesso_antes_do_limite_zera_as_falhas_do_email(client):
    conta = _conta("ana.c7@s2.test")
    _falhar(client, conta.email, 4)
    _assert_login_ok(_login(client, conta.email, SENHA))
    _falhar(client, conta.email, 4)
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_c8_bloqueio_dura_quinze_minutos(client):
    conta = _conta("ana.c8@s2.test")
    _falhar(client, conta.email, 5)
    _avancar_relogio(14)
    _assert_429_login(_login(client, conta.email, SENHA))
    _avancar_relogio(2)
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_c9_falhas_fora_da_janela_de_quinze_minutos_nao_contam(client):
    conta = _conta("ana.c9@s2.test")
    _falhar(client, conta.email, 4)
    _avancar_relogio(16)
    _falhar(client, conta.email, 4)
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_c10_estado_fica_na_tabela_e_sobrevive_a_novo_app(app_s2):
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as primeiro:
        conta = _conta("ana.c10@s2.test")
        _falhar(primeiro, conta.email, 5)
    assert _tabela_existe("login_attempts"), "estado do limite de login tem de ficar na tabela login_attempts"
    assert _sql("SELECT COUNT(*) AS n FROM login_attempts")[0]["n"] >= 1
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as reiniciado:
        _assert_429_login(_login(reiniciado, conta.email, SENHA))


def test_c11_conta_de_funcionario_tambem_e_limitada(client):
    gestora = _conta("gestora.c11@s2.test", "Gestora S2", perfil="admin")
    _falhar(client, gestora.email, 5)
    _assert_429_login(_login(client, gestora.email, SENHA))
    assert not _eventos("staff.login") or all(
        e.get("actor_email") != gestora.email for e in _eventos("staff.login")
    ), "login bloqueado nao pode gravar staff.login (sucesso)"


# =========================================================================================
# D - S2: login por IP
# =========================================================================================

def test_d1_vinte_falhas_do_mesmo_ip_com_emails_diferentes_bloqueiam_o_ip(client):
    conta = _conta("ana.d1@s2.test")
    for i in range(20):
        r = _login(client, f"outro{i}.d1@s2.test", SENHA_ERRADA)
        assert r.status_code == 400, f"falha {i + 1}: {_resumo(r)}"
    _assert_429_login(_login(client, conta.email, SENHA))


def test_d2_dezenove_falhas_do_ip_ainda_deixam_entrar(client):
    conta = _conta("ana.d2@s2.test")
    for i in range(19):
        assert _login(client, f"outro{i}.d2@s2.test", SENHA_ERRADA).status_code == 400
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_d3_bloqueio_do_ip_nao_afeta_outro_ip(app_s2, client):
    conta = _conta("ana.d3@s2.test")
    for i in range(20):
        _login(client, f"outro{i}.d3@s2.test", SENHA_ERRADA)
    _assert_429_login(_login(client, conta.email, SENHA))
    _assert_login_ok(_login(_outro_ip(app_s2), conta.email, SENHA))


def test_d4_x_forwarded_for_nao_contorna_nem_transfere_o_bloqueio(app_s2, client):
    conta = _conta("ana.d4@s2.test")
    for i in range(20):
        _login(client, f"outro{i}.d4@s2.test", SENHA_ERRADA, headers={"X-Forwarded-For": f"172.16.0.{i + 1}"})
    # o cliente bloqueado nao se livra declarando outro IP
    _assert_429_login(_login(client, conta.email, SENHA, headers={"X-Forwarded-For": "8.8.8.8"}))
    # outro cliente que declara o IP bloqueado nao e bloqueado
    outro = _outro_ip(app_s2)
    _assert_login_ok(_login(outro, conta.email, SENHA, headers={"X-Forwarded-For": IP_A[0]}))


def test_d5_bloqueio_do_ip_dura_quinze_minutos(client):
    conta = _conta("ana.d5@s2.test")
    for i in range(20):
        _login(client, f"outro{i}.d5@s2.test", SENHA_ERRADA)
    _avancar_relogio(14)
    _assert_429_login(_login(client, conta.email, SENHA))
    _avancar_relogio(2)
    _assert_login_ok(_login(client, conta.email, SENHA))


def test_d6_login_legado_bloqueia_por_ip_mesmo_com_a_senha_certa(app_s2, client):
    for i in range(20):
        r = client.post(ROTA_LEGADO, json={"password": f"errada-{i}"})
        assert r.status_code == 401, f"falha {i + 1}: {_resumo(r)}"
    r = client.post(ROTA_LEGADO, json={"password": SENHA_LEGADO})
    assert r.status_code == 429, _resumo(r)
    assert r.json().get("detail") == ERRO_LOGIN
    assert "token" not in r.json()
    outro = _outro_ip(app_s2).post(ROTA_LEGADO, json={"password": SENHA_LEGADO})
    assert outro.status_code == 200, _resumo(outro)


def test_d7_login_legado_com_poucas_falhas_continua_funcionando(client):
    for i in range(5):
        assert client.post(ROTA_LEGADO, json={"password": f"errada-{i}"}).status_code == 401
    r = client.post(ROTA_LEGADO, json={"password": SENHA_LEGADO})
    assert r.status_code == 200, _resumo(r)
    assert r.json().get("token")


# =========================================================================================
# E - S2: auditoria auth.locked
# =========================================================================================

def _textos_do_evento(evento):
    return " | ".join(str(v) for v in evento.values() if v is not None).lower()


def test_e1_bloqueio_por_email_grava_auth_locked_uma_vez_sem_senha_nem_email_completo(client):
    conta = _conta("carla.e1@s2.test")
    _falhar(client, conta.email, 5)
    for _ in range(3):
        _assert_429_login(_login(client, conta.email, SENHA))
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1, f"esperado 1 auth.locked por bloqueio, vieram {len(eventos)}"
    texto = _textos_do_evento(eventos[0])
    assert SENHA_ERRADA.lower() not in texto and SENHA.lower() not in texto, "a senha foi para a auditoria"
    assert conta.email.lower() not in texto, f"e-mail completo na auditoria: {eventos[0]}"


def test_e2_bloqueio_por_ip_grava_auth_locked_uma_vez(client):
    for i in range(23):
        _login(client, f"outro{i}.e2@s2.test", SENHA_ERRADA)
    eventos = _eventos("auth.locked")
    assert len(eventos) == 1, f"esperado 1 auth.locked por bloqueio, vieram {len(eventos)}: {eventos}"
    texto = _textos_do_evento(eventos[0])
    assert SENHA_ERRADA.lower() not in texto
    assert not any(f"outro{i}.e2@s2.test" in texto for i in range(23)), "e-mail completo na auditoria"


def test_e3_falhas_abaixo_do_limite_nao_gravam_auth_locked(client):
    conta = _conta("carla.e3@s2.test")
    _falhar(client, conta.email, 4)
    assert _eventos("auth.locked") == []


# =========================================================================================
# F - S9: chat anonimo
# =========================================================================================

def test_f1_trinta_mensagens_passam_e_a_31a_recebe_429_sem_chamar_o_llm(client, llm):
    for i in range(30):
        r = _chat(client, f"Pergunta numero {i}")
        assert r.status_code == 200, f"mensagem {i + 1}: {_resumo(r)}"
        assert r.json().get("status") == "success", f"mensagem {i + 1}: {r.json()}"
    chamadas = llm.chamadas
    r = _chat(client, "Pergunta 31")
    assert r.status_code == 429, f"31a mensagem: esperado 429, veio {_resumo(r)}"
    assert _texto(r) == ERRO_CHAT, r.json()
    assert llm.chamadas == chamadas, "a mensagem barrada pelo limite nao pode chegar ao LLM"


def test_f2_limite_do_chat_nao_afeta_outro_ip(app_s2, client):
    for _ in range(31):
        _chat(client)
    assert _chat(client).status_code == 429
    r = _chat(_outro_ip(app_s2))
    assert r.status_code == 200, _resumo(r)
    assert r.json().get("status") == "success"


def test_f3_x_forwarded_for_nao_contorna_o_limite_do_chat(client):
    for i in range(30):
        _chat(client, headers={"X-Forwarded-For": f"172.16.1.{i + 1}"})
    r = _chat(client, headers={"X-Forwarded-For": "8.8.4.4"})
    assert r.status_code == 429, _resumo(r)


def test_f4_limite_do_chat_reinicia_com_novo_app(app_s2):
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as primeiro:
        for _ in range(30):
            _chat(primeiro)
        assert _chat(primeiro).status_code == 429
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as reiniciado:
        r = _chat(reiniciado)
        assert r.status_code == 200, _resumo(r)


def test_f5_teto_padrao_de_sessoes_anonimas_e_5000():
    import agents.manager_agent as modulo

    assert getattr(modulo, "MAX_ANON_SESSIONS", None) == 5000, "teto MAX_ANON_SESSIONS (5000) ausente"


def test_f6_teto_de_sessoes_descarta_a_menos_recente(app_s2, monkeypatch):
    import agents.manager_agent as modulo

    assert hasattr(modulo, "MAX_ANON_SESSIONS"), "teto MAX_ANON_SESSIONS ausente em agents.manager_agent"
    monkeypatch.setattr(modulo, "MAX_ANON_SESSIONS", 3)
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as c:
        ids = []
        for i in range(4):
            r = _chat(c, f"Abrindo sessao {i}")
            assert r.status_code == 200, _resumo(r)
            ids.append(r.json()["session_id"])
        assert len(set(ids)) == 4
        sessoes = app_s2.state.manager_agent.sessions
        assert len(sessoes) <= 3, f"teto 3 excedido: {len(sessoes)} sessoes em memoria"
        assert ids[0] not in sessoes, "a sessao menos recente deveria ter sido descartada"
        for sid in ids[1:]:
            assert sid in sessoes, "sessoes mais recentes nao podem ser descartadas"
        # a sessao descartada nao e mais aceita: o servidor abre outra
        r = _chat(c, "Voltando a sessao antiga", session_id=ids[0])
        assert r.status_code == 200
        assert r.json()["session_id"] != ids[0]
        assert len(app_s2.state.manager_agent.sessions) <= 3


# =========================================================================================
# G - S9: checkouts
# =========================================================================================

def test_g1_checkout_do_aluno_11a_tentativa_no_minuto_recebe_429_sem_criar_nada(client, gw):
    aluno = _conta("aluno.g1@s2.test")
    for i in range(10):
        r = _comprar_aluno(client, aluno.token)
        assert r.status_code != 429, f"tentativa {i + 1} nao pode ser barrada: {_resumo(r)}"
    antes, chamadas = _foto_compras(), len(gw.post_chamadas)
    r = _comprar_aluno(client, aluno.token)
    assert r.status_code == 429, f"11a tentativa: esperado 429, veio {_resumo(r)}"
    assert _texto(r) == ERRO_CHECKOUT, r.json()
    assert _foto_compras() == antes, "o 429 nao pode criar nem alterar matricula ou pagamento"
    assert len(gw.post_chamadas) == chamadas, "o 429 nao pode chamar o gateway"


def test_g2_checkout_da_landing_11a_tentativa_no_minuto_recebe_429_sem_criar_nada(client, gw):
    for i in range(10):
        r = _comprar_landing(client, f"comprador{i}.g2@s2.test")
        assert r.status_code != 429, f"tentativa {i + 1} nao pode ser barrada: {_resumo(r)}"
    antes, contagens, chamadas = _foto_compras(), _contagens(), len(gw.post_chamadas)
    r = _comprar_landing(client, "comprador11.g2@s2.test")
    assert r.status_code == 429, f"11a tentativa: esperado 429, veio {_resumo(r)}"
    assert _texto(r) == ERRO_CHECKOUT, r.json()
    assert _foto_compras() == antes and _contagens() == contagens, "o 429 nao pode criar conta, matricula ou pagamento"
    assert len(gw.post_chamadas) == chamadas
    assert Database.get_user_by_email("comprador11.g2@s2.test") is None


def test_g3_limite_do_aluno_vale_de_outro_ip(app_s2, client, gw):
    aluno = _conta("aluno.g3@s2.test")
    for _ in range(10):
        _comprar_aluno(client, aluno.token)
    r = _comprar_aluno(_outro_ip(app_s2), aluno.token)
    assert r.status_code == 429, f"limite por aluno: esperado 429 de outro IP, veio {_resumo(r)}"
    assert _texto(r) == ERRO_CHECKOUT


def test_g4_limite_por_ip_vale_para_outro_aluno_no_mesmo_ip(client, gw):
    ana = _conta("ana.g4@s2.test")
    bia = _conta("bia.g4@s2.test")
    for _ in range(10):
        _comprar_aluno(client, ana.token)
    r = _comprar_aluno(client, bia.token)
    assert r.status_code == 429, f"limite por IP: esperado 429, veio {_resumo(r)}"


def test_g5_limite_da_landing_nao_afeta_outro_ip(app_s2, client, gw):
    for i in range(10):
        _comprar_landing(client, f"comprador{i}.g5@s2.test")
    assert _comprar_landing(client, "comprador10.g5@s2.test").status_code == 429
    r = _comprar_landing(_outro_ip(app_s2), "comprador11.g5@s2.test")
    assert r.status_code == 200, _resumo(r)


def test_g6_limite_de_checkout_reinicia_com_novo_app(app_s2, gw):
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as primeiro:
        for i in range(10):
            _comprar_landing(primeiro, f"comprador{i}.g6@s2.test")
        assert _comprar_landing(primeiro, "comprador10.g6@s2.test").status_code == 429
    with TestClient(app_s2, client=IP_A, raise_server_exceptions=False) as reiniciado:
        r = _comprar_landing(reiniciado, "comprador11.g6@s2.test")
        assert r.status_code == 200, _resumo(r)


def test_g7_x_forwarded_for_nao_contorna_o_limite_de_checkout(client, gw):
    for i in range(10):
        _comprar_landing(client, f"comprador{i}.g7@s2.test")
    r = client.post(ROTA_LANDING, json={"course_id": CURSO, "payer": {"name": "Comprador S2", "email": "x.g7@s2.test"}},
                    headers={"X-Forwarded-For": "8.8.8.8"})
    assert r.status_code == 429, _resumo(r)


# =========================================================================================
# R - Regressoes: uso normal nao e afetado
# =========================================================================================

def test_r1_logins_certos_repetidos_nunca_sao_bloqueados(client):
    conta = _conta("ana.r1@s2.test")
    for i in range(25):
        r = _login(client, conta.email, SENHA)
        assert r.status_code == 200, f"login certo {i + 1}: {_resumo(r)}"
    assert _eventos("auth.locked") == []


def test_r2_senha_errada_continua_400_com_o_texto_de_sempre(client):
    conta = _conta("ana.r2@s2.test")
    r = _login(client, conta.email, SENHA_ERRADA)
    assert (r.status_code, r.json().get("detail")) == (400, ERRO_CREDENCIAIS)


def test_r3_chat_e_checkout_normais_seguem_funcionando(client, gw):
    r = _chat(client)
    assert r.status_code == 200 and r.json().get("status") == "success", _resumo(r)
    aluno = _conta("aluno.r3@s2.test")
    compra = _comprar_aluno(client, aluno.token)
    assert compra.status_code == 200, _resumo(compra)
    landing = _comprar_landing(client, "landing.r3@s2.test")
    assert landing.status_code == 200, _resumo(landing)


def test_r4_limites_de_chat_e_checkout_sao_independentes(client, gw):
    for _ in range(10):
        _comprar_landing(client, f"c{uuid.uuid4().hex[:6]}.r4@s2.test")
    assert _comprar_landing(client, "ultimo.r4@s2.test").status_code == 429
    r = _chat(client)
    assert r.status_code == 200, "o limite de checkout nao pode bloquear o chat"
    conta = _conta("ana.r4@s2.test")
    _assert_login_ok(_login(client, conta.email, SENHA))
