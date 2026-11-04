"""Dados de demonstração para testar o sistema na própria máquina (D107).

Uso, a partir de backend/:  python seed_demo.py

Cria contas de teste, turmas, matrículas e conteúdos nos cursos que já vêm em backend/courses. Pode rodar mais de uma vez:
o que já existe é mantido. Recusa rodar com APP_ENV=production, porque as senhas abaixo são públicas.
"""

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from core import conteudos  # noqa: E402
from core.receipt_pdf import gerar_pdf_de_linhas  # noqa: E402
from core.security import get_password_hash  # noqa: E402
from db import Database  # noqa: E402

SENHA = "Senha-Demo-2026"
CURSOS = Path(__file__).parent / "courses"
EXCEL, PYTHON, C_SHARP = "excel_profissional", "python_profissional", "c_e_c"
VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

EQUIPE = (("gestao@demo.test", "Gestão Demo", "admin"), ("financeiro@demo.test", "Financeiro Demo", "financial"),
          ("suporte@demo.test", "Suporte Demo", "support"))
# nome, e-mail, matrículas (curso, status da matrícula, status do pagamento, dias atrás)
ALUNOS = (
    ("Rafael Lima", "rafael@demo.test", ((EXCEL, "active", "approved", 2),)),
    ("Marina Souza", "marina@demo.test", ((EXCEL, "active", "approved", 2), (PYTHON, "pending", "pending", 1),
                                          (C_SHARP, "refunded", "refunded", 20))),
    ("Ana Paula Ribeiro", "ana@demo.test", ((PYTHON, "active", "approved", 40),)),
    ("Bruno Cardoso", "bruno@demo.test", ((EXCEL, "cancelled", "cancelled", 5),)),
)
GUIA = (("F2", "Guia rapido de PROCV"), ("F1", ""),
        ("F1", "O PROCV busca um valor na primeira coluna de uma tabela."),
        ("F1", "Ele devolve o dado da coluna indicada, na mesma linha."),
        ("F1", "O quarto argumento FALSO exige correspondencia exata."),
        ("F1", "Use sempre FALSO em listas sem ordenacao."),
        ("F1", "O erro N/D significa que o valor nao esta na primeira coluna."))
APOSTILA = (("F2", "Apostila do modulo 1: formulas essenciais"), ("F1", ""),
            ("F1", "SOMASE soma os valores que atendem a um criterio."),
            ("F1", "CONT.SE conta as celulas que atendem a um criterio."),
            ("F1", "SE devolve um valor quando o teste e verdadeiro e outro quando e falso."))


def garantir_conta(email, nome, perfil, senha):
    conta = Database.get_user_by_email(email)
    return conta["id"] if conta else Database.add_user(email, nome, senha, role=perfil)


def preco(course_id):
    return float(json.loads((CURSOS / f"{course_id}.json").read_text(encoding="utf-8"))["price"])


def garantir_matricula(conn, user_id, course_id, status, pagamento, dias, turma):
    existente = conn.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?", (user_id, course_id)).fetchone()
    if existente:
        return
    matricula = conn.execute("INSERT INTO enrollments (user_id, course_id, status, class_id) VALUES (?, ?, ?, ?)",
                             (user_id, course_id, status, turma)).lastrowid
    conn.execute(
        """INSERT INTO payments (enrollment_id, amount, status, payment_method, transaction_id, created_at, updated_at)
           VALUES (?, ?, ?, 'credit_card', ?, datetime('now', ?), datetime('now', ?))""",
        (matricula, preco(course_id), pagamento, f"demo-{uuid.uuid4().hex}", f"-{dias} days", f"-{dias} days"))


def garantir_turma(course_id, nome, inicio, fim, horario, capacidade):
    turma = next((t for t in Database.list_classes() if t["course_id"] == course_id and t["name"] == nome), None)
    return turma["id"] if turma else Database.create_class(course_id, nome, inicio, capacidade, fim, horario)


def garantir_arquivo(course_id, modulo, titulo, nome, linhas):
    dados = gerar_pdf_de_linhas(list(linhas))
    conteudo = conteudos.criar(course_id, {
        "module": modulo, "title": titulo, "kind": "file", "file_name": nome,
        "stored_name": conteudos.salvar_arquivo(".pdf", dados)})
    conteudos.preparar_texto(conteudo)


def garantir_conteudos(course_id):
    if conteudos.listar(course_id):
        return
    conteudos.criar(course_id, {"module": "Módulo 1: Fórmulas", "title": "Aula 1: Fórmulas essenciais", "kind": "video", "url": VIDEO})
    garantir_arquivo(course_id, "Módulo 1: Fórmulas", "Apostila do módulo 1", "apostila-modulo-1.pdf", APOSTILA)
    garantir_arquivo(course_id, "Módulo 1: Fórmulas", "Guia rápido de PROCV", "guia-procv.pdf", GUIA)
    conteudos.criar(course_id, {"module": "Módulo 2: Tabelas", "title": "Aula 2: Tabelas dinâmicas", "kind": "video", "url": VIDEO})
    conteudos.criar(course_id, {"module": conteudos.MODULO_EXTRAS, "title": "Atalhos do Excel", "kind": "link", "is_extra": True,
                                "url": "https://support.microsoft.com/pt-br/excel"})


def semear():
    senha = get_password_hash(SENHA)
    for email, nome, perfil in EQUIPE:
        garantir_conta(email, nome, perfil, senha)
    noite = garantir_turma(EXCEL, "Turma Noite", "2030-03-10", "2030-05-20", "Seg e Qua, 19h às 22h", 20)
    garantir_turma(EXCEL, "Turma Sábado", "2030-04-06", None, "Sábados, 9h às 13h", 15)
    ids = {email: garantir_conta(email, nome, "student", senha) for nome, email, _ in ALUNOS}
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        for _, email, matriculas in ALUNOS:
            user_id = ids[email]
            for curso, status, pagamento, dias in matriculas:
                garantir_matricula(conn, user_id, curso, status, pagamento, dias, noite if curso == EXCEL else None)
        conn.commit()
    finally:
        conn.close()
    garantir_conteudos(EXCEL)


def main():
    if (os.getenv("APP_ENV") or "").strip().lower() == "production":
        sys.exit("Recusado: seed_demo.py não roda com APP_ENV=production, porque as senhas são públicas.")
    semear()
    print(f"Pronto. Senha de todas as contas: {SENHA}")
    for email, _, perfil in EQUIPE:
        print(f"  {perfil:10} {email}")
    for nome, email, _ in ALUNOS:
        print(f"  aluno      {email} ({nome})")


if __name__ == "__main__":
    main()
