"""QA do assistente com os arquivos do curso (D107). Roda com o modelo dublê: mede acesso, ciclo de vida, tipos de arquivo,
limites e ataques pelas fontes (`sources`) que a API devolve. O comportamento do modelo real está em test_qa_chat_llm_real.py.

Mesmas técnicas e catálogo de test_qa_istqb.py.
"""

import io
import json
import time
import zipfile

import pytest

from test_qa_istqb import _anexo, ct, novo_curso, s  # noqa: F401


def pdf(*linhas):
    from core.receipt_pdf import gerar_pdf_de_linhas  # noqa: PLC0415
    return gerar_pdf_de_linhas([("F1", linha) for linha in linhas])


def office(extensao, texto):
    parte, xml = {
        "docx": ("word/document.xml", f"<w:p><w:t>{texto}</w:t></w:p>"),
        "pptx": ("ppt/slides/slide1.xml", f"<a:p><a:t>{texto}</a:t></a:p>"),
        "xlsx": ("xl/sharedStrings.xml", f"<si><t>{texto}</t></si>"),
    }[extensao]
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(parte, xml)
    return pacote.getvalue()


def enviar(s, curso, dados, titulo="Apostila QA", nome="a.pdf", **extra):
    resposta = s.api("POST", f"/api/admin/courses/{curso}/contents/file", s.tk["admin"],
                     multipart={"file": _anexo(nome, dados), "module": "M", "title": titulo, **extra})
    assert resposta.s == 201, resposta.t
    return resposta.j["content"]


def curso_com_apostila(s, termo="xilofone", titulo="Apostila QA", **extra):
    _, corpo = novo_curso(s, s.tk["admin"], **extra)
    return corpo["id"], enviar(s, corpo["id"], pdf(f"Capitulo sobre {termo} aplicado ao trabalho"), titulo)


def fontes(resposta):
    assert resposta.s == 200, resposta.t
    return [f["title"] for f in resposta.j.get("sources", [])]


def perguntar(s, conta, termo="xilofone"):
    return fontes(s.post("/api/student/chat", {"message": f"Explique {termo}"}, conta.tk))


# ===================================================================== Quem acessa


@ct("CT-RAG-01", "SALA-IA", "DT", "Apostila só alimenta a resposta com matrícula ativa, em qualquer outro status não")
@pytest.mark.parametrize("status, acessa", [("active", True), ("pending", False), ("cancelled", False), ("refunded", False)])
def test_rag_status(s, status, acessa):
    curso, _ = curso_com_apostila(s)
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso, status=status)
    assert ("Apostila QA" in perguntar(s, aluno)) is acessa


@ct("CT-RAG-02", "SALA-IA", "SEC", "Aluno ativo de outro curso e visitante não recebem a apostila")
def test_rag_fora_do_curso(s):
    curso, _ = curso_com_apostila(s, titulo="Apostila Restrita")
    outro = s.aluno()
    s.matricula(outro.id)
    assert "Apostila Restrita" not in perguntar(s, outro)
    assert "Apostila Restrita" not in s.post("/api/chat", {"message": "Explique xilofone aplicado"}).t


@ct("CT-RAG-03", "SALA-IA", "ST", "Reembolso corta o acesso da mensagem seguinte; reativar devolve")
def test_rag_perde_acesso(s):
    curso, _ = curso_com_apostila(s)
    aluno = s.aluno()
    enrollment, pagamento = s.matricula(aluno.id, curso=curso)
    assert "Apostila QA" in perguntar(s, aluno)
    assert s.post(f"/api/payments/refund/{pagamento}", tk=s.tk["financial"]).s == 200
    assert "Apostila QA" not in perguntar(s, aluno)
    s.sql("UPDATE enrollments SET status = 'active' WHERE id = ?", enrollment)
    assert "Apostila QA" in perguntar(s, aluno)


@ct("CT-RAG-04", "SALA-IA", "DT", "Mesmo assunto em dois cursos: cada aluno recebe só a apostila do seu")
def test_rag_dois_cursos(s):
    curso_a, _ = curso_com_apostila(s, titulo="Apostila A")
    curso_b, _ = curso_com_apostila(s, titulo="Apostila B")
    aluno_a, aluno_b, dos_dois = s.aluno(), s.aluno(), s.aluno()
    s.matricula(aluno_a.id, curso=curso_a)
    s.matricula(aluno_b.id, curso=curso_b)
    s.matricula(dos_dois.id, curso=curso_a)
    s.matricula(dos_dois.id, curso=curso_b)
    assert "Apostila B" not in perguntar(s, aluno_a) and "Apostila A" in perguntar(s, aluno_a)
    assert "Apostila A" not in perguntar(s, aluno_b) and "Apostila B" in perguntar(s, aluno_b)
    assert {"Apostila A", "Apostila B"} <= set(perguntar(s, dos_dois))


@ct("CT-RAG-05", "SALA-IA", "EP", "Curso arquivado continua respondendo a quem tem matrícula ativa")
def test_rag_curso_arquivado(s):
    curso, _ = curso_com_apostila(s)
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    assert s.post(f"/api/admin/course/{curso}/archive", tk=s.tk["admin"]).s == 200
    assert "Apostila QA" in perguntar(s, aluno)


@ct("CT-RAG-06", "SALA-IA", "SEC", "Funcionário não usa o chat do aluno e o corpo não escolhe o curso")
def test_rag_perfil_e_corpo(s):
    curso, _ = curso_com_apostila(s)
    assert s.post("/api/student/chat", {"message": "xilofone"}, s.tk["support"]).s == 403
    aluno = s.aluno()
    corpo = {"message": "Explique xilofone aplicado", "course_id": curso, "cursos_ativos": [curso], "user_id": 1}
    assert "Apostila QA" not in fontes(s.post("/api/student/chat", corpo, aluno.tk))


# ===================================================================== Ciclo de vida


@ct("CT-RAG-25", "SALA-IA", "SEC", "Chat na sala fica só naquele curso; curso sem matrícula ativa enviado no corpo é ignorado")
def test_rag_chat_na_sala(s):
    curso_a, _ = curso_com_apostila(s, titulo="Apostila A")
    curso_b, _ = curso_com_apostila(s, titulo="Apostila B")
    fora, _ = curso_com_apostila(s, titulo="Apostila Fora")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso_a)
    s.matricula(aluno.id, curso=curso_b)
    pergunta = {"message": "Explique xilofone"}
    assert {"Apostila A", "Apostila B"} <= set(fontes(s.post("/api/student/chat", pergunta, aluno.tk)))
    na_sala = fontes(s.post("/api/student/chat", {**pergunta, "course_id": curso_a}, aluno.tk))
    assert "Apostila A" in na_sala and "Apostila B" not in na_sala
    assert "Apostila Fora" not in fontes(s.post("/api/student/chat", {**pergunta, "course_id": fora}, aluno.tk))
    assert s.post("/api/student/chat", {**pergunta, "course_id": 123}, aluno.tk).s == 422


@ct("CT-RAG-26", "SALA-IA", "EP", "Verbo da pergunta acha a política: 'como eu cancelo' cita Cancelamento")
@pytest.mark.parametrize("pergunta", ["como eu cancelo?", "quero cancelar", "da pra parcelar?"])
def test_rag_verbos(s, pergunta):
    assert fontes(s.post("/api/student/chat", {"message": pergunta}, s.aluno().tk))


@ct("CT-RAG-27", "SALA-IA", "BVA", "Assunto presente em muitos cursos continua achando a apostila do próprio aluno")
def test_rag_assunto_comum(s):
    for _ in range(4):
        curso_com_apostila(s, "contabilidade", "Apostila de Outro Curso")
    curso, _ = curso_com_apostila(s, "contabilidade", "Apostila do Meu Curso")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    assert "Apostila do Meu Curso" in perguntar(s, aluno, "contabilidade")


@ct("CT-RAG-07", "SALA-IA", "ST", "Oculto sai, republicado volta, trocado muda o texto, excluído some, sem reiniciar")
def test_rag_ciclo(s):
    curso, item = curso_com_apostila(s)
    admin, aluno = s.tk["admin"], s.aluno()
    s.matricula(aluno.id, curso=curso)
    assert "Apostila QA" in perguntar(s, aluno)
    s.put(f"/api/admin/contents/{item['id']}", {**item, "published": False}, admin)
    assert perguntar(s, aluno) == []
    s.put(f"/api/admin/contents/{item['id']}", {**item, "published": True}, admin)
    assert "Apostila QA" in perguntar(s, aluno)
    novo = pdf("Capitulo sobre clarinete aplicado ao trabalho")
    assert s.api("PUT", f"/api/admin/contents/{item['id']}/file", admin, multipart={"file": _anexo(dados=novo)}).s == 200
    assert perguntar(s, aluno) == [] and "Apostila QA" in perguntar(s, aluno, "clarinete")
    assert s.delete(f"/api/admin/contents/{item['id']}", admin).s == 200
    assert perguntar(s, aluno, "clarinete") == []


@ct("CT-RAG-08", "SALA-IA", "UC", "Título novo aparece na fonte; arquivo novo vale na pergunta seguinte")
def test_rag_titulo_e_novo(s):
    curso, item = curso_com_apostila(s)
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    perguntar(s, aluno)
    s.put(f"/api/admin/contents/{item['id']}", {**item, "title": "Nome Novo"}, s.tk["admin"])
    assert "Nome Novo" in perguntar(s, aluno)
    enviar(s, curso, pdf("Capitulo sobre trombone aplicado"), "Segunda Apostila")
    assert "Segunda Apostila" in perguntar(s, aluno, "trombone")


@ct("CT-RAG-09", "SALA-IA", "EG", "Excluir o curso tira a apostila do índice")
def test_rag_curso_excluido(s):
    curso, _ = curso_com_apostila(s, "fagote", "Apostila Fagote")
    aluno = s.aluno()
    assert s.delete(f"/api/admin/course/{curso}", s.tk["admin"]).s == 200
    assert "Apostila Fagote" not in perguntar(s, aluno, "fagote")
    documentos = s.sql("SELECT COUNT(*) FROM course_contents WHERE course_id = ?", curso)[0][0]
    assert documentos == 0


# ===================================================================== Tipos de arquivo


@ct("CT-RAG-10", "SALA-IA", "EP", "PDF, Word, PowerPoint e Excel são lidos")
@pytest.mark.parametrize("extensao", ["pdf", "docx", "pptx", "xlsx"])
def test_rag_tipos(s, extensao):
    _, corpo = novo_curso(s, s.tk["admin"])
    dados = pdf("Capitulo sobre oboe aplicado") if extensao == "pdf" else office(extensao, "Capitulo sobre oboe aplicado")
    item = enviar(s, corpo["id"], dados, nome=f"a.{extensao}")
    assert item["text_status"] == "ok"
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    assert "Apostila QA" in perguntar(s, aluno, "oboe")


@ct("CT-RAG-11", "SALA-IA", "EP", "ZIP, PDF sem texto e arquivo corrompido ficam fora, com aviso à Gestão, sem erro")
@pytest.mark.parametrize("nome, dados", [
    ("a.zip", b"PK\x03\x04conteudo"), ("a.pdf", b"%PDF-1.4 sem paginas"), ("a.docx", b"PK quebrado"),
    ("a.xlsx", b"PK\x05\x06" + b"\0" * 18),
], ids=["zip", "pdf-sem-texto", "docx-corrompido", "xlsx-vazio"])
def test_rag_sem_texto(s, nome, dados):
    _, corpo = novo_curso(s, s.tk["admin"])
    assert enviar(s, corpo["id"], dados, nome=nome)["text_status"] == "empty"


@ct("CT-RAG-12", "SALA-IA", "EP", "Vídeo e link externo não entram no índice")
def test_rag_video_e_link(s):
    _, corpo = novo_curso(s, s.tk["admin"])
    rota = f"/api/admin/courses/{corpo['id']}/contents"
    s.post(rota, {"module": "M", "title": "Sobre harpa", "kind": "video",
                  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, s.tk["admin"])
    s.post(rota, {"module": "M", "title": "Mais harpa", "kind": "link", "url": "https://materiais.test/h"}, s.tk["admin"])
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    # Os títulos entram só na lista do curso; vídeo e link não viram documento próprio.
    assert all(titulo.startswith("Conteúdos do curso") for titulo in perguntar(s, aluno, "harpa"))


# ===================================================================== Limites e busca


@ct("CT-RAG-13", "SALA-IA", "EP", "Busca ignora acento e caixa, nos dois sentidos")
@pytest.mark.parametrize("no_arquivo, na_pergunta", [("função", "funcao"), ("funcao", "função"), ("FUNÇÃO", "função"),
                                                     ("acentuação", "ACENTUACAO")], ids=str)
def test_rag_acento(s, no_arquivo, na_pergunta):
    _, corpo = novo_curso(s, s.tk["admin"])
    enviar(s, corpo["id"], office("docx", f"Capitulo sobre {no_arquivo} aplicada"), nome="a.docx")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    assert "Apostila QA" in perguntar(s, aluno, na_pergunta)


@ct("CT-RAG-14", "SALA-IA", "BVA", "No máximo 3 fontes por resposta, com várias apostilas sobre o assunto")
def test_rag_limite_fontes(s):
    _, corpo = novo_curso(s, s.tk["admin"])
    for numero in range(5):
        enviar(s, corpo["id"], pdf(f"Capitulo {numero} sobre pandeiro aplicado"), f"Apostila {numero}")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    achadas = perguntar(s, aluno, "pandeiro")
    assert 1 <= len(achadas) <= 3


@ct("CT-RAG-15", "SALA-IA", "BVA", "Texto longo é dividido: termo no fim de um arquivo grande é encontrado")
def test_rag_texto_longo(s):
    _, corpo = novo_curso(s, s.tk["admin"])
    enviar(s, corpo["id"], office("docx", "palavra " * 8000 + "bandolim no final"), nome="a.docx")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    assert "Apostila QA" in perguntar(s, aluno, "bandolim")


@ct("CT-RAG-16", "SALA-IA", "BVA", "Teto de 400 mil caracteres: o que passa do teto não é lido e nada quebra")
def test_rag_teto(s):
    _, corpo = novo_curso(s, s.tk["admin"])
    item = enviar(s, corpo["id"], office("docx", "cavaquinho " + "x " * 210_000 + "alaude"), nome="a.docx")
    assert item["text_status"] == "ok"
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    assert "Apostila QA" in perguntar(s, aluno, "cavaquinho")
    assert perguntar(s, aluno, "alaude") == []


@ct("CT-RAG-17", "SALA-IA", "SEC", "Arquivo compactado malicioso (60 MB de XML) é ignorado sem travar o envio")
def test_rag_zip_bomb(s):
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr("word/document.xml", b"0" * (60 * 1024 * 1024))
    _, corpo = novo_curso(s, s.tk["admin"])
    inicio = time.time()
    assert enviar(s, corpo["id"], pacote.getvalue(), nome="a.docx")["text_status"] == "empty"
    assert time.time() - inicio < 15


@ct("CT-RAG-18", "SALA-IA", "EG", "Sintaxe da busca na pergunta nunca gera erro")
@pytest.mark.parametrize("pergunta", ['"', '""', "*", "xilofone*", "NEAR(a b)", "a AND OR NOT", "x:y", "'; DROP TABLE users;--",
                                      "( ) { } ^ -", "🎓🎓🎓", "a" * 2000], ids=lambda v: v[:12])
def test_rag_sintaxe(s, pergunta):
    corpo = s.post("/api/student/chat", {"message": pergunta}, s.aluno().tk)
    assert corpo.s == 200 and corpo.j["status"] == "success"


@ct("CT-RAG-19", "SALA-IA", "UC", "Pergunta de política segue citando a base institucional para quem tem apostila")
def test_rag_nao_atropela_politica(s):
    _, corpo = novo_curso(s, s.tk["admin"])
    enviar(s, corpo["id"], pdf("Texto sobre o prazo de entrega do trabalho final"), "Apostila do Prazo")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=corpo["id"])
    titulos = fontes(s.post("/api/student/chat", {"message": "Qual o prazo de cancelamento e reembolso?"}, aluno.tk))
    assert any("ancelamento" in t for t in titulos), titulos


# ===================================================================== Vazamentos


@ct("CT-RAG-20", "SALA-IA", "SEC", "Resposta e fontes não expõem caminho, nome interno nem id de outro arquivo")
def test_rag_sem_interno(s):
    curso, item = curso_com_apostila(s)
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    resposta = s.post("/api/student/chat", {"message": "Explique xilofone aplicado"}, aluno.tk)
    nome = s.sql("SELECT stored_name FROM course_contents WHERE id = ?", item["id"])[0][0]
    assert nome not in resposta.t and "conteudos" not in resposta.t and "uploads" not in resposta.t


@ct("CT-RAG-21", "SALA-IA", "SEC", "Histórico guarda só a conversa, sem o trecho da apostila")
def test_rag_historico(s):
    curso, _ = curso_com_apostila(s, "sanfona")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    perguntar(s, aluno, "sanfona")
    assert "aplicado ao trabalho" not in s.get("/api/student/chat/history", aluno.tk).t


@ct("CT-RAG-22", "SALA-IA", "SEC", "Listas da Gestão e do aluno não carregam o texto extraído")
def test_rag_texto_nao_vaza(s):
    curso, _ = curso_com_apostila(s, "rabeca")
    aluno = s.aluno()
    enrollment, _ = s.matricula(aluno.id, curso=curso)
    for resposta in (s.get(f"/api/admin/courses/{curso}/contents", s.tk["admin"]),
                     s.get(f"/api/student/enrollments/{enrollment}/room", aluno.tk)):
        assert resposta.s == 200 and "rabeca" not in resposta.t and "extracted_text" not in resposta.t


@ct("CT-RAG-23", "SALA-IA", "SEC", "Exportação LGPD e catálogo público não trazem o texto da apostila")
def test_rag_exportacao(s):
    curso, _ = curso_com_apostila(s, "ocarina")
    aluno = s.aluno()
    s.matricula(aluno.id, curso=curso)
    assert "ocarina" not in s.get("/api/student/me/export", aluno.tk).t
    assert "ocarina" not in s.get("/api/courses").t


@ct("CT-RAG-24", "SALA-IA", "CONC", "Três alunos perguntando ao mesmo tempo, durante um envio, recebem só o que podem")
def test_rag_concorrencia(s):
    import concurrent.futures  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    curso, _ = curso_com_apostila(s, "theremim", "Apostila Paralela")
    ativos = [s.aluno() for _ in range(2)]
    for conta in ativos:
        s.matricula(conta.id, curso=curso)
    fora = s.aluno()

    def perguntar_http(conta):
        pedido = urllib.request.Request(
            s.alvo["api"] + "/api/student/chat", method="POST",
            data=json.dumps({"message": "Explique theremim aplicado"}).encode(),
            headers={"Authorization": f"Bearer {conta.tk}", "Content-Type": "application/json"})
        return urllib.request.urlopen(pedido, timeout=30).read().decode()

    with concurrent.futures.ThreadPoolExecutor(3) as grupo:
        futuros = {conta.id: grupo.submit(perguntar_http, conta) for conta in ativos + [fora]}
        enviar(s, curso, pdf("Outro texto qualquer"), "Durante")
        respostas = {chave: futuro.result() for chave, futuro in futuros.items()}
    assert all("Apostila Paralela" in respostas[conta.id] for conta in ativos)
    assert "Apostila Paralela" not in respostas[fora.id]


# ===================================================================== Pontos fracos da rodada anterior


@ct("CT-DAS-09", "E1.2-Cursos", "UC", "Taxa de conversão: conta exata com matrículas aprovadas sobre o total")
def test_conversao_exata(s):
    _, corpo = novo_curso(s, s.tk["admin"], name="Curso Conversão")
    for status, pagamento in (("active", "approved"), ("active", "approved"), ("pending", "pending"), ("pending", "pending")):
        s.matricula(s.aluno().id, curso=corpo["id"], status=status, pagamento=pagamento)
    cursos = s.get("/api/dashboard/cursos", s.tk["admin"]).j
    item = next(c for c in cursos["courses"] if c["id"] == corpo["id"])
    assert item["conversion_rate"] == 50.0, item


@ct("CT-DAS-10", "E1.2-Financeiro", "UC", "Projeção de receita: é a média exata da receita dos meses")
def test_projecao_receita(s):
    painel = s.get("/api/dashboard/financeiro", s.tk["financial"]).j
    meses = [mes["revenue"] for mes in painel["monthly_revenue"]]
    assert meses, "a suíte semeia pagamentos aprovados"
    assert painel["totals"]["projected_next_month"] == round(sum(meses) / len(meses), 2)
