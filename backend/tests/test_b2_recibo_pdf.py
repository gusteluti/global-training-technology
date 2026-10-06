"""B2 — Recibo em PDF (D63).

Contrato (D63):
  - GET /api/student/payments/{id}/receipt.pdf: só aluno; o dono vem do JWT (user_id do cliente é ignorado).
    Pagamento alheio ou inexistente: o MESMO 404 e o mesmo corpo do recibo JSON, verificado ANTES do status.
    Sem token ou token forjado: 401. Funcionário (JWT ou token administrativo legado): 403.
  - Só pagamento 'approved' ou 'refunded' gera PDF; os demais: 409 com texto exato.
  - 200 com Content-Type application/pdf, Content-Disposition attachment; filename="recibo-<id>.pdf",
    Cache-Control no-store, corpo que começa com %PDF-1. e termina com %%EOF, até 20 KB.
  - PDF em Python puro, Helvetica/WinAnsiEncoding (cp1252; o que não cabe vira '?'), SEM compressão,
    com (, ) e \\ escapados e xref válida. Os testes validam a estrutura SEM biblioteca de PDF (parse manual).
  - Texto: "RECIBO DE PAGAMENTO", "Global Training Technology", id do recibo, nome do aluno (nunca o e-mail),
    curso, valor "R$ 250,00" (sem separador de milhar, vírgula decimal, duas casas), status, forma de
    pagamento, id da transação quando houver, data de emissão (= issued_at do recibo JSON) e, só em
    'refunded', a linha "Pagamento reembolsado.". Nada de outro aluno, token, URL de material ou hash.
  - GET /api/student/payments: cada item ganha receipt_pdf_url; os campos antigos não mudam.

Fixtures: banco temporário (fixture `banco`), cursos em diretório temporário (admin.routes.COURSES_DIR),
contas e pagamentos criados com Database.*, login real por POST /api/token. Nenhum teste toca db.sqlite.

Testes:
  A0   extrator de strings do teste decodifica escapes (apoio, não depende da produção)
  A1   200 com Content-Type, Content-Disposition, Cache-Control e Content-Length corretos
  A2   corpo: começa com %PDF-1., termina com %%EOF, até 20 KB
  A3   estrutura: startxref -> xref, uma entrada por objeto, offsets exatos, trailer /Root e /Size
  A4   stream de conteúdo: /Length igual ao tamanho real, sem /Filter, fonte Helvetica/WinAnsiEncoding
  A5   conteúdo: título, empresa, id do recibo, aluno, curso, valor, status, forma, transação, emissão
  A6   valores: formatação R$ com vírgula decimal, duas casas, sem separador de milhar
  A7   nome/curso com acento (cp1252) e com ( ) \\ não quebram o PDF nem deslocam o xref
  A8   caracteres fora de cp1252 viram '?' sem quebrar
  A9   'Pagamento reembolsado.' só em refunded; approved e refunded geram PDF
  A10  id da transação ausente: a linha some; presente: aparece
  A11  nada de e-mail, token, URL de material, hash de senha, nem dado de outro aluno/pagamento
  A12  status que não geram PDF: 409 com o texto exato (pending, rejected, cancelled, in_process, charged_back)
  A13  IDOR: alheio e inexistente = mesmo 404 e mesmo corpo do recibo JSON, mesmo quando alheio está pending
  A14  401: sem token, token forjado, lixo
  A15  403: admin, financeiro, suporte (JWT e token administrativo legado)
  A16  user_id na query é ignorado
  A17  lista de pagamentos ganha receipt_pdf_url; campos antigos intactos
  A18  recibo JSON e rota antiga seguem inalterados (guarda)
  A19  determinismo: duas chamadas iguais; data vem do pagamento, não do relógio
  A20  compatibilidade: pagamento sem transaction_id e sem updated_at usa created_at
  A21  curso sem arquivo no catálogo: usa o id do curso como nome
"""

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

import admin.routes as admin_routes
from core.security import get_password_hash
from db import Database


SENHA = "senha-aluno-b2-2026"
ROTA_PAGAMENTOS = "/api/student/payments"
ERRO_404 = "Pagamento não encontrado."
ERRO_409 = "Recibo em PDF disponível apenas para pagamentos aprovados ou reembolsados."
LIMITE_BYTES = 20 * 1024

CURSO_ACENTO = "curso-b2-acento"
NOME_ACENTO = "Programação Avançada em Python"
CURSO_ESCAPES = "curso-b2-escapes"
NOME_ESCAPES = "Lógica (Básico) \\ Módulo 2"
URL_MATERIAL = "https://materiais.test/b2/apostila-secreta.pdf"
URL_MATERIAL_2 = "https://materiais.test/b2/video-secreto.mp4"
MATERIAIS = [
    {"title": "Apostila secreta", "url": URL_MATERIAL, "type": "pdf"},
    {"title": "Video secreto", "url": URL_MATERIAL_2, "type": "video"},
]
CURSO_OUTRO = "curso-b2-do-outro"
NOME_OUTRO = "Curso Reservado do Outro Aluno"

NOME_ALUNO = "José Átila Çelik"
NOME_ESCAPE_ALUNO = "Ana (Teste) \\ Lima"
CAMPOS_ANTIGOS_PAGAMENTO = {
    "id", "enrollment_id", "course_id", "course_name", "amount", "status",
    "payment_method", "transaction_id", "created_at", "updated_at", "receipt_url",
}
CAMPOS_RECIBO_JSON = {
    "payment_id", "enrollment_id", "course_id", "course_name", "amount", "status",
    "payment_method", "transaction_id", "issued_at",
}


# --- Fixtures ----------------------------------------------------------------------------

@pytest.fixture
def cursos(tmp_path, monkeypatch):
    diretorio = tmp_path / "courses"
    diretorio.mkdir()
    base = {"description": "Curso de teste B2", "price": 100.0, "materials": MATERIAIS}
    for curso_id, nome in ((CURSO_ACENTO, NOME_ACENTO), (CURSO_ESCAPES, NOME_ESCAPES), (CURSO_OUTRO, NOME_OUTRO)):
        (diretorio / f"{curso_id}.json").write_text(
            json.dumps({"id": curso_id, "name": nome, **base}), encoding="utf-8")
    monkeypatch.setattr(admin_routes, "COURSES_DIR", diretorio)
    return diretorio


@pytest.fixture
def client(banco, cursos):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


# --- Helpers de banco --------------------------------------------------------------------

def _executar(sql, params=()):
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _conta(email, nome="Aluno B2", role="student"):
    user_id = Database.add_user(email, nome, get_password_hash(SENHA), role=role)
    assert user_id is not None, f"seed: conta {email} já existe"
    return user_id


def _pagamento(user_id, course_id, amount, status, transaction_id=None, payment_id=None,
               created_at=None, updated_at=None, enrollment_status=None):
    """Pagamento real (create_enrollment + record_payment + update_payment_status).

    payment_id força um id distintivo (evita falso verde com ids pequenos); created_at/updated_at fixam as datas.
    """
    ref = f"{course_id}:b2:{uuid.uuid4().hex}"
    enrollment_id = Database.create_enrollment(user_id, course_id, ref)
    pid = Database.record_payment(enrollment_id, amount, "mercado_pago")
    Database.update_payment_status(pid, status, transaction_id)
    if payment_id is not None:
        _executar("UPDATE payments SET id = ? WHERE id = ?", (payment_id, pid))
        pid = payment_id
    if created_at is not None:
        _executar("UPDATE payments SET created_at = ? WHERE id = ?", (created_at, pid))
    if updated_at is not None:
        _executar("UPDATE payments SET updated_at = ? WHERE id = ?", (updated_at, pid))
    if enrollment_status is not None:
        _executar("UPDATE enrollments SET status = ? WHERE id = ?", (enrollment_status, enrollment_id))
    return pid


def _login(client, email):
    r = client.post("/api/token", data={"username": email, "password": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _rota_pdf(payment_id):
    return f"{ROTA_PAGAMENTOS}/{payment_id}/receipt.pdf"


def _rota_json(payment_id):
    return f"{ROTA_PAGAMENTOS}/{payment_id}/receipt"


def _aluno_logado(client, email, nome="Aluno B2"):
    user_id = _conta(email, nome)
    return user_id, _login(client, email)


def _pdf_ok(client, token, payment_id, **params):
    r = client.get(_rota_pdf(payment_id), headers=_auth(token), params=params or None)
    assert r.status_code == 200, f"GET {_rota_pdf(payment_id)}: HTTP {r.status_code} {r.text[:200]!r}"
    return r


def _recibo_json(client, token, payment_id):
    r = client.get(_rota_json(payment_id), headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()["receipt"]


# --- Parser de PDF mínimo, só para o teste (sem biblioteca de PDF) ------------------------

def _objetos(corpo: bytes):
    """{numero: bytes do objeto (entre 'N 0 obj' e 'endobj')} lendo o arquivo todo."""
    achados = {}
    for m in re.finditer(rb"(?m)^(\d+) 0 obj\b(.*?)endobj", corpo, re.DOTALL):
        achados[int(m.group(1))] = m.group(2)
    return achados


def _extrair_strings(stream: bytes):
    """Strings literais (entre parênteses) de um stream de conteúdo, com escapes decodificados, em cp1252."""
    saida = []
    i, n = 0, len(stream)
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < n:
        if stream[i] != 0x28:  # '('
            i += 1
            continue
        profundidade, buf = 1, bytearray()
        i += 1
        while i < n:
            c = stream[i]
            if c == 0x5C:  # '\'
                i += 1
                if i >= n:
                    break
                p = stream[i]
                if p in (0x28, 0x29, 0x5C):
                    buf.append(p)
                elif p in escapes:
                    buf.append(escapes[p])
                elif 0x30 <= p <= 0x37:
                    octal = bytes([p])
                    while len(octal) < 3 and i + 1 < n and 0x30 <= stream[i + 1] <= 0x37:
                        i += 1
                        octal += bytes([stream[i]])
                    buf.append(int(octal, 8) & 0xFF)
                elif p in (10, 13):
                    pass  # continuação de linha
                else:
                    buf.append(p)
            elif c == 0x28:
                profundidade += 1
                buf.append(c)
            elif c == 0x29:
                profundidade -= 1
                if profundidade == 0:
                    break
                buf.append(c)
            else:
                buf.append(c)
            i += 1
        saida.append(bytes(buf).decode("cp1252", errors="replace"))
        i += 1
    return saida


def _streams(corpo: bytes):
    """Lista de (dicionario_bytes, dados_brutos_apos_stream_ate_endstream) de cada objeto com stream."""
    achados = []
    for numero, obj in _objetos(corpo).items():
        m = re.search(rb"(?<!end)stream\r?\n", obj)
        if not m:
            continue
        resto = obj[m.end():]
        fim = resto.rfind(b"endstream")
        assert fim >= 0, f"objeto {numero}: stream sem endstream"
        achados.append((numero, obj[:m.start()], resto[:fim]))
    return achados


def _texto_do_pdf(corpo: bytes) -> str:
    """Todo o texto desenhado (strings dos streams), uma por linha."""
    streams = _streams(corpo)
    assert streams, "o PDF não tem nenhum stream de conteúdo"
    strings = []
    for _, _, dados in streams:
        strings.extend(_extrair_strings(dados))
    return "\n".join(strings)


def _validar_estrutura(corpo: bytes):
    assert corpo.startswith(b"%PDF-1."), corpo[:20]
    assert corpo.rstrip().endswith(b"%%EOF"), corpo[-30:]

    # startxref aponta para a linha 'xref'
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", corpo)
    assert m, "startxref ausente ou fora do final do arquivo"
    offset_xref = int(m.group(1))
    assert corpo[offset_xref:offset_xref + 4] == b"xref", f"startxref={offset_xref} não aponta para 'xref'"

    # tabela xref: uma subseção '0 N', N entradas de 20 bytes
    cab = re.match(rb"xref\s*\r?\n(\d+) (\d+)\s*\r?\n", corpo[offset_xref:])
    assert cab, "cabeçalho da xref inválido"
    primeiro, total = int(cab.group(1)), int(cab.group(2))
    assert primeiro == 0, "a xref deve começar no objeto 0"
    inicio = offset_xref + cab.end()
    entradas = []
    for k in range(total):
        bruto = corpo[inicio + 20 * k: inicio + 20 * (k + 1)]
        # formato da especificação: 10 dígitos, espaço, 5 dígitos, espaço, n|f e fim de linha de 2 bytes
        e = re.fullmatch(rb"(\d{10}) (\d{5}) ([nf])(?: \n| \r|\r\n)", bruto)
        assert e, f"entrada {k} da xref não tem 20 bytes válidos: {bruto!r}"
        entradas.append((int(e.group(1)), int(e.group(2)), e.group(3)))
    assert entradas[0][2] == b"f", "a entrada 0 da xref deve ser livre (f)"

    # uma entrada por objeto, cada offset aponta exatamente para 'N 0 obj'
    objetos = _objetos(corpo)
    assert set(objetos) == set(range(1, total)), f"objetos {sorted(objetos)} x xref de {total} entradas"
    for numero in range(1, total):
        offset, _, tipo = entradas[numero]
        assert tipo == b"n"
        alvo = f"{numero} 0 obj".encode()
        assert corpo[offset:offset + len(alvo)] == alvo, (
            f"offset {offset} do objeto {numero} não aponta para {alvo!r}: {corpo[offset:offset + 12]!r}")

    # trailer: /Root e /Size coerentes
    trailer = re.search(rb"trailer\s*<<(.*?)>>\s*startxref", corpo, re.DOTALL)
    assert trailer, "trailer ausente"
    size = re.search(rb"/Size\s+(\d+)", trailer.group(1))
    root = re.search(rb"/Root\s+(\d+) 0 R", trailer.group(1))
    assert size and int(size.group(1)) == total, f"/Size {size and size.group(1)} != {total}"
    assert root and int(root.group(1)) in objetos, "/Root não aponta para um objeto existente"
    assert b"/Catalog" in objetos[int(root.group(1))], "/Root não é o catálogo"

    # streams: /Length direto igual ao tamanho real, sem filtro (sem compressão)
    assert b"/Filter" not in corpo, "o PDF não deve ter compressão (/Filter)"
    streams = _streams(corpo)
    assert streams, "sem stream de conteúdo"
    for numero, dicionario, dados in streams:
        ln = re.search(rb"/Length\s+(\d+)(\s+\d+\s+R)?", dicionario)
        assert ln and not ln.group(2), f"objeto {numero}: /Length direto ausente"
        tamanho = int(ln.group(1))
        assert dados[tamanho:] in (b"", b"\n", b"\r\n", b"\r"), (
            f"objeto {numero}: /Length={tamanho}, stream real tem {len(dados)} bytes ({dados[tamanho:][:10]!r} sobrando)")
        assert len(dados) >= tamanho
    # fonte e codificação do contrato
    assert b"/Helvetica" in corpo
    assert b"/WinAnsiEncoding" in corpo


# --- A0 ---------------------------------------------------------------------------------

def test_a0_extrator_de_strings_decodifica_escapes_e_cp1252():
    stream = b"BT (Ana \\(Teste\\) \\\\ Lima) Tj (Jos\\351 (aninhado) ok) Tj (\xe7) Tj ET"
    assert _extrair_strings(stream) == ["Ana (Teste) \\ Lima", "José (aninhado) ok", "ç"]


# --- A1, A2, A3, A4: cabeçalhos, corpo e estrutura -----------------------------------------

def test_a1_resposta_200_com_cabecalhos_do_contrato(client):
    uid, token = _aluno_logado(client, "a1@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a1", payment_id=7201)

    r = _pdf_ok(client, token, pid)

    assert r.headers["content-type"].split(";")[0].strip() == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="recibo-7201.pdf"'
    assert r.headers["cache-control"] == "no-store"
    assert int(r.headers["content-length"]) == len(r.content)


def test_a2_corpo_e_bytes_pdf_com_marcadores_e_tamanho_limitado(client):
    uid, token = _aluno_logado(client, "a2@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a2")

    r = _pdf_ok(client, token, pid)

    corpo = r.content
    assert isinstance(corpo, bytes)
    assert corpo.startswith(b"%PDF-1.")
    assert corpo.rstrip().endswith(b"%%EOF")
    assert 200 < len(corpo) <= LIMITE_BYTES


@pytest.mark.parametrize("status", ["approved", "refunded"])
def test_a3_estrutura_xref_trailer_e_offsets_exatos(client, status):
    uid, token = _aluno_logado(client, f"a3.{status}@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, status, f"mp-a3-{status}")

    corpo = _pdf_ok(client, token, pid).content

    _validar_estrutura(corpo)


def test_a4_stream_de_conteudo_tem_length_real_e_nao_e_comprimido(client):
    uid, token = _aluno_logado(client, "a4@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a4")

    corpo = _pdf_ok(client, token, pid).content

    streams = _streams(corpo)
    assert len(streams) >= 1
    assert b"/Filter" not in corpo
    for numero, dicionario, dados in streams:
        tamanho = int(re.search(rb"/Length\s+(\d+)", dicionario).group(1))
        assert dados[tamanho:] in (b"", b"\n", b"\r\n", b"\r"), f"objeto {numero}: /Length inconsistente"
    # texto legível sem descompressão
    assert "RECIBO DE PAGAMENTO" in _texto_do_pdf(corpo)


# --- A5: conteúdo ------------------------------------------------------------------------

def test_a5_conteudo_do_recibo_aprovado(client):
    uid, token = _aluno_logado(client, "a5@b2.test", NOME_ALUNO)
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-recibo-a5-991", payment_id=48213,
                     created_at="2024-02-28 09:00:00", updated_at="2024-02-29 13:45:10")
    recibo = _recibo_json(client, token, pid)

    corpo = _pdf_ok(client, token, pid).content
    texto = _texto_do_pdf(corpo)

    assert "RECIBO DE PAGAMENTO" in texto
    assert "Global Training Technology" in texto
    assert "48213" in texto
    assert NOME_ALUNO in texto, texto
    assert NOME_ACENTO in texto, texto
    assert re.findall(r"R\$\s*([0-9.,]+)", texto) and set(re.findall(r"R\$\s*([0-9.,]+)", texto)) == {"250,00"}
    assert "R$ 250,00" in texto
    assert "approved" in texto or "Aprovado" in texto or "aprovado" in texto
    assert "mercado_pago" in texto or "Mercado Pago" in texto
    assert "mp-recibo-a5-991" in texto
    assert recibo["issued_at"] == "2024-02-29 13:45:10"
    assert recibo["issued_at"] in texto, texto
    assert "Pagamento reembolsado." not in texto


@pytest.mark.parametrize("valor, esperado", [
    (250.00, "250,00"),
    (0.5, "0,50"),
    (1234.5, "1234,50"),
    (199.9, "199,90"),
    (0.0, "0,00"),
    (1234567.89, "1234567,89"),
])
def test_a6_formatacao_do_valor_sem_milhar_virgula_decimal_duas_casas(client, valor, esperado):
    uid, token = _aluno_logado(client, f"a6.{str(valor).replace('.', '_')}@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, valor, "approved", f"mp-a6-{str(valor).replace('.', '_')}")

    texto = _texto_do_pdf(_pdf_ok(client, token, pid).content)

    assert f"R$ {esperado}" in texto, texto
    assert set(re.findall(r"R\$\s*([0-9.,]+)", texto)) == {esperado}, texto


# --- A7, A8: escapes e cp1252 ------------------------------------------------------------

@pytest.mark.parametrize("nome", [
    "José Átila Çelik",
    "Ana (Teste) \\ Lima",
    "Bia ))( Costa",
    "C:\\pasta\\(x)",
])
def test_a7_nome_com_acento_parenteses_e_barra_nao_quebra_o_pdf(client, nome):
    uid, token = _aluno_logado(client, f"a7.{uuid.uuid4().hex[:8]}@b2.test", nome)
    pid = _pagamento(uid, CURSO_ESCAPES, 99.0, "approved", f"mp-a7-{uuid.uuid4().hex[:6]}")

    corpo = _pdf_ok(client, token, pid).content

    _validar_estrutura(corpo)
    texto = _texto_do_pdf(corpo)
    assert nome in texto, texto
    assert NOME_ESCAPES in texto, texto  # curso com ( ) \ e acento


def test_a8_caracteres_fora_de_cp1252_viram_interrogacao_sem_quebrar(client):
    uid, token = _aluno_logado(client, "a8@b2.test", "田中 Silva")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a8")

    r = _pdf_ok(client, token, pid)

    _validar_estrutura(r.content)
    texto = _texto_do_pdf(r.content)
    assert "?? Silva" in texto, texto
    assert "田".encode("utf-8") not in r.content
    assert "中".encode("utf-8") not in r.content


# --- A9, A10: status e linhas condicionais -----------------------------------------------

def test_a9_linha_de_reembolso_so_em_refunded(client):
    uid, token = _aluno_logado(client, "a9@b2.test")
    aprovado = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a9-ok")
    reembolsado = _pagamento(uid, CURSO_ESCAPES, 120.00, "refunded", "mp-a9-ref")

    texto_ok = _texto_do_pdf(_pdf_ok(client, token, aprovado).content)
    texto_ref = _texto_do_pdf(_pdf_ok(client, token, reembolsado).content)

    assert "Pagamento reembolsado." not in texto_ok
    assert "reembols" not in texto_ok.lower()
    assert "Pagamento reembolsado." in texto_ref
    assert "refunded" in texto_ref or "Reembolsado" in texto_ref or "reembolsado" in texto_ref
    assert "R$ 120,00" in texto_ref


def test_a10_id_da_transacao_aparece_quando_ha_e_a_linha_some_quando_nulo(client):
    uid, token = _aluno_logado(client, "a10@b2.test")
    com = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a10-com-transacao")
    sem = _pagamento(uid, CURSO_ESCAPES, 250.00, "approved", None)

    texto_com = _texto_do_pdf(_pdf_ok(client, token, com).content)
    texto_sem = _texto_do_pdf(_pdf_ok(client, token, sem).content)

    assert "mp-a10-com-transacao" in texto_com
    assert "transa" in texto_com.lower()
    assert "transa" not in texto_sem.lower(), texto_sem  # nenhum rótulo de transação
    assert "None" not in texto_sem and "null" not in texto_sem.lower()
    assert "mp-a10-com-transacao" not in texto_sem


# --- A11: nada que não deva sair ---------------------------------------------------------

def test_a11_pdf_nao_traz_email_token_url_de_material_hash_nem_dado_de_outro(client):
    email_a, email_b = "dono.a11@b2.test", "outro.a11@b2.test"
    alice, token = _aluno_logado(client, email_a, "Alice Dona Do Recibo")
    bob = _conta(email_b, "Bob Outro Aluno")
    meu = _pagamento(alice, CURSO_ACENTO, 250.00, "approved", "mp-a11-meu", enrollment_status="active")
    meu_2 = _pagamento(alice, CURSO_ESCAPES, 77.00, "approved", "mp-a11-meu-2", enrollment_status="active")
    _pagamento(bob, CURSO_OUTRO, 777.00, "approved", "mp-a11-do-bob", enrollment_status="active")
    hash_alice = Database.get_user_by_email(email_a)["password_hash"]
    hash_bob = Database.get_user_by_email(email_b)["password_hash"]
    assert hash_alice and hash_bob

    r = _pdf_ok(client, token, meu)
    corpo = r.content
    texto = _texto_do_pdf(corpo)
    bruto = corpo.decode("latin-1")

    assert email_a not in bruto and email_b not in bruto
    assert b"@" not in corpo
    assert token not in bruto and "eyJ" not in bruto
    assert "Bearer" not in bruto
    assert hash_alice not in bruto and hash_bob not in bruto
    assert URL_MATERIAL not in bruto and URL_MATERIAL_2 not in bruto
    assert "http" not in bruto.lower()
    assert "Apostila secreta" not in texto and "Video secreto" not in texto
    assert "Bob" not in bruto and NOME_OUTRO not in texto and "mp-a11-do-bob" not in bruto
    assert "777" not in texto
    # outro pagamento do MESMO aluno também não vaza para este recibo
    assert "mp-a11-meu-2" not in bruto and NOME_ESCAPES not in texto
    assert not any(h.lower().startswith("set-cookie") for h in r.headers)
    assert meu_2 != meu


# --- A12: status que não geram PDF -------------------------------------------------------

@pytest.mark.parametrize("status", ["pending", "rejected", "cancelled", "in_process", "charged_back"])
def test_a12_status_sem_recibo_devolvem_409_com_o_texto_exato(client, status):
    uid, token = _aluno_logado(client, f"a12.{status}@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, status, f"mp-a12-{status}", enrollment_status="active")

    r = client.get(_rota_pdf(pid), headers=_auth(token))

    assert r.status_code == 409, f"{status}: esperado 409, veio {r.status_code}"
    assert r.json() == {"detail": ERRO_409}
    assert not r.content.startswith(b"%PDF")
    assert "pdf" not in r.headers.get("content-type", "").lower()
    assert URL_MATERIAL not in r.text


# --- A13: IDOR ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_do_alheio", ["approved", "refunded", "pending", "cancelled"])
def test_a13_idor_alheio_e_inexistente_sao_o_mesmo_404_do_recibo_json(client, status_do_alheio):
    sufixo = status_do_alheio
    _, token = _aluno_logado(client, f"idor.a.{sufixo}@b2.test", "Alice")
    bob = _conta(f"idor.b.{sufixo}@b2.test", "Bob Reservado")
    alheio = _pagamento(bob, CURSO_OUTRO, 321.00, status_do_alheio, f"mp-idor-{sufixo}")

    pdf_alheio = client.get(_rota_pdf(alheio), headers=_auth(token))
    pdf_inexistente = client.get(_rota_pdf(999999), headers=_auth(token))
    json_alheio = client.get(_rota_json(alheio), headers=_auth(token))
    json_inexistente = client.get(_rota_json(999999), headers=_auth(token))

    assert pdf_alheio.status_code == 404, f"alheio {status_do_alheio}: veio {pdf_alheio.status_code}"
    assert pdf_inexistente.status_code == 404
    assert pdf_alheio.json() == pdf_inexistente.json() == {"detail": ERRO_404}
    assert pdf_alheio.json() == json_alheio.json() == json_inexistente.json()
    assert pdf_alheio.status_code == json_alheio.status_code
    for r in (pdf_alheio, pdf_inexistente):
        assert "pdf" not in r.headers.get("content-type", "").lower()
        assert "attachment" not in r.headers.get("content-disposition", "").lower()
        assert NOME_OUTRO not in r.text and f"mp-idor-{sufixo}" not in r.text and "Bob" not in r.text
        assert not r.content.startswith(b"%PDF")


# --- A14, A15: autenticação e perfil -----------------------------------------------------

def test_a14_sem_token_token_forjado_e_lixo_recebem_401(client):
    uid, token = _aluno_logado(client, "a14@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a14")
    assert client.get(_rota_pdf(pid), headers=_auth(token)).status_code == 200
    forjado = jose_jwt.encode(
        {"user_id": uid, "email": "a14@b2.test", "role": "student",
         "exp": datetime.utcnow() + timedelta(hours=1)},
        "segredo-do-atacante-que-nao-e-o-real", algorithm="HS256")

    sem_token = client.get(_rota_pdf(pid))
    com_forjado = client.get(_rota_pdf(pid), headers=_auth(forjado))
    com_lixo = client.get(_rota_pdf(pid), headers=_auth("isto-nao-e-um-jwt"))

    assert sem_token.status_code == 401
    assert com_forjado.status_code == 401
    assert com_lixo.status_code == 401
    for r in (sem_token, com_forjado, com_lixo):
        assert not r.content.startswith(b"%PDF")


@pytest.mark.parametrize("perfil", ["admin", "financial", "support"])
def test_a15_funcionario_com_jwt_recebe_403(client, perfil):
    uid, _ = _aluno_logado(client, f"dono.a15.{perfil}@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", f"mp-a15-{perfil}")
    _conta(f"{perfil}.a15@b2.test", f"Func {perfil}", role=perfil)
    token = _login(client, f"{perfil}.a15@b2.test")

    r = client.get(_rota_pdf(pid), headers=_auth(token))

    assert r.status_code == 403, f"{perfil}: esperado 403, veio {r.status_code}"
    assert not r.content.startswith(b"%PDF")


@pytest.mark.parametrize("senha_env, perfil", [("admin123", "admin"), ("fin123", "financial"), ("sup123", "support")])
def test_a15b_funcionario_com_token_administrativo_legado_recebe_403(client, senha_env, perfil):
    uid, _ = _aluno_logado(client, f"dono.a15b.{perfil}@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", f"mp-a15b-{perfil}")
    login = client.post("/api/admin/login", json={"password": senha_env})
    assert login.status_code == 200, login.text

    r = client.get(_rota_pdf(pid), headers=_auth(login.json()["token"]))

    assert r.status_code == 403, f"{perfil} (legado): esperado 403, veio {r.status_code}"
    assert not r.content.startswith(b"%PDF")


# --- A16: user_id do cliente é ignorado ---------------------------------------------------

def test_a16_user_id_na_query_e_ignorado(client):
    alice, token = _aluno_logado(client, "a16.alice@b2.test", "Alice Dona")
    bob = _conta("a16.bob@b2.test", "Bob Alheio")
    meu = _pagamento(alice, CURSO_ACENTO, 250.00, "approved", "mp-a16-meu")
    do_bob = _pagamento(bob, CURSO_OUTRO, 321.00, "approved", "mp-a16-bob")

    com_id_do_bob = client.get(_rota_pdf(meu), headers=_auth(token), params={"user_id": bob})
    com_id_qualquer = client.get(_rota_pdf(meu), headers=_auth(token), params={"user_id": 999999})
    tentativa = client.get(_rota_pdf(do_bob), headers=_auth(token), params={"user_id": bob})
    inexistente = client.get(_rota_pdf(999999), headers=_auth(token))

    assert com_id_do_bob.status_code == 200
    assert "Alice Dona" in _texto_do_pdf(com_id_do_bob.content)
    assert "Bob Alheio" not in com_id_do_bob.content.decode("latin-1")
    assert com_id_qualquer.status_code == 200
    assert "Alice Dona" in _texto_do_pdf(com_id_qualquer.content)
    assert tentativa.status_code == 404
    assert tentativa.json() == inexistente.json() == {"detail": ERRO_404}


# --- A17: lista de pagamentos ------------------------------------------------------------

def test_a17_lista_ganha_receipt_pdf_url_e_mantem_os_campos_antigos(client):
    alice, token = _aluno_logado(client, "a17.alice@b2.test")
    bob = _conta("a17.bob@b2.test")
    aprovado = _pagamento(alice, "curso-python", 199.90, "approved", "mp-a17-1")
    pendente = _pagamento(alice, "curso-angular", 99.50, "pending")
    reembolsado = _pagamento(alice, CURSO_ACENTO, 50.00, "refunded", "mp-a17-3")
    _pagamento(bob, "curso-secreto", 777.00, "approved", "mp-a17-bob")

    r = client.get(ROTA_PAGAMENTOS, headers=_auth(token))

    assert r.status_code == 200, r.text
    pagamentos = r.json()["payments"]
    assert {p["id"] for p in pagamentos} == {aprovado, pendente, reembolsado}
    assert "mp-a17-bob" not in r.text and "curso-secreto" not in r.text
    por_id = {p["id"]: p for p in pagamentos}
    for pid in (aprovado, pendente, reembolsado):
        item = por_id[pid]
        assert item["receipt_pdf_url"] == f"/api/student/payments/{pid}/receipt.pdf"
        assert item["receipt_url"] == f"/api/student/payments/{pid}/receipt"
        assert set(item) == CAMPOS_ANTIGOS_PAGAMENTO | {"receipt_pdf_url"}
    # campos antigos com os mesmos valores da E4
    assert por_id[aprovado]["amount"] == 199.90
    assert por_id[aprovado]["status"] == "approved"
    assert por_id[aprovado]["course_id"] == "curso-python"
    assert por_id[aprovado]["payment_method"] == "mercado_pago"
    assert por_id[aprovado]["transaction_id"] == "mp-a17-1"
    assert por_id[aprovado]["created_at"] and por_id[aprovado]["updated_at"]
    assert por_id[pendente]["status"] == "pending"
    assert por_id[pendente]["transaction_id"] is None
    assert por_id[reembolsado]["course_name"] == NOME_ACENTO


def test_a17b_url_da_lista_baixa_o_pdf(client):
    alice, token = _aluno_logado(client, "a17b@b2.test")
    pid = _pagamento(alice, CURSO_ACENTO, 250.00, "approved", "mp-a17b")
    item = client.get(ROTA_PAGAMENTOS, headers=_auth(token)).json()["payments"][0]

    r = client.get(item["receipt_pdf_url"], headers=_auth(token))

    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-1.")
    assert f'recibo-{pid}.pdf' in r.headers["content-disposition"]


# --- A18: guarda do recibo JSON ----------------------------------------------------------

def test_a18_recibo_json_e_rota_antiga_seguem_inalterados(client):
    uid, token = _aluno_logado(client, "a18@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a18",
                     created_at="2024-02-28 09:00:00", updated_at="2024-02-29 13:45:10")

    r = client.get(_rota_json(pid), headers=_auth(token))

    assert r.status_code == 200
    assert "json" in r.headers["content-type"]
    corpo = r.json()
    assert set(corpo) == {"status", "receipt"}
    assert corpo["status"] == "success"
    assert corpo["receipt"] == {
        "payment_id": pid,
        "enrollment_id": corpo["receipt"]["enrollment_id"],
        "course_id": CURSO_ACENTO,
        "course_name": NOME_ACENTO,
        "amount": 250.00,
        "status": "approved",
        "payment_method": "mercado_pago",
        "transaction_id": "mp-a18",
        "issued_at": "2024-02-29 13:45:10",
    }
    assert set(corpo["receipt"]) == CAMPOS_RECIBO_JSON


# --- A19: determinismo -------------------------------------------------------------------

def test_a19_duas_chamadas_devolvem_o_mesmo_conteudo_e_a_data_vem_do_pagamento(client):
    uid, token = _aluno_logado(client, "a19@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 250.00, "approved", "mp-a19",
                     created_at="2020-01-02 03:04:05", updated_at="2020-01-03 04:05:06")

    primeira = _pdf_ok(client, token, pid)
    segunda = _pdf_ok(client, token, pid)

    assert primeira.content == segunda.content
    assert int(primeira.headers["content-length"]) == len(primeira.content)
    assert int(segunda.headers["content-length"]) == len(segunda.content)
    texto = _texto_do_pdf(primeira.content)
    assert "2020-01-03 04:05:06" in texto
    hoje = date.today()
    assert hoje.isoformat() not in texto and hoje.strftime("%d/%m/%Y") not in texto, "a data não pode vir do relógio"


# --- A20: compatibilidade com pagamento antigo -------------------------------------------

def test_a20_pagamento_antigo_sem_transaction_id_e_sem_updated_at_usa_created_at(client):
    uid, token = _aluno_logado(client, "a20@b2.test")
    pid = _pagamento(uid, CURSO_ACENTO, 80.00, "approved", None, created_at="2019-05-06 07:08:09")
    _executar("UPDATE payments SET updated_at = NULL, transaction_id = NULL WHERE id = ?", (pid,))
    recibo = _recibo_json(client, token, pid)
    assert recibo["issued_at"] == "2019-05-06 07:08:09"
    assert recibo["transaction_id"] is None

    r = _pdf_ok(client, token, pid)

    _validar_estrutura(r.content)
    texto = _texto_do_pdf(r.content)
    assert "2019-05-06 07:08:09" in texto, texto
    assert "R$ 80,00" in texto
    assert "transa" not in texto.lower()
    assert "None" not in texto and "null" not in texto.lower()


# --- A21: curso fora do catálogo ---------------------------------------------------------

def test_a21_curso_sem_arquivo_no_catalogo_usa_o_id_como_nome(client):
    uid, token = _aluno_logado(client, "a21@b2.test")
    pid = _pagamento(uid, "curso-removido-b2", 45.00, "approved", "mp-a21")
    assert _recibo_json(client, token, pid)["course_name"] == "curso-removido-b2"

    r = _pdf_ok(client, token, pid)

    _validar_estrutura(r.content)
    assert "curso-removido-b2" in _texto_do_pdf(r.content)
