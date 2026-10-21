"""LGPD (U7, D89): aceite de termos, exportação e exclusão dos dados pelo próprio aluno.

Exclusão = anonimização: a conta perde nome, e-mail, telefone, senha, conversas do chat e tokens; matrículas e
pagamentos ficam (sem dado pessoal) porque o registro financeiro é obrigação legal (LGPD art. 16, I). A trilha de
auditoria é append-only (E8) e também fica.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from db import Database

VERSAO_TERMOS = "2026-10"


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def garantir_colunas() -> None:
    conn = sqlite3.connect(Database.DB_PATH)
    try:
        cursor = conn.cursor()
        Database._ensure_column(cursor, "users", "terms_accepted_at", "TEXT")
        Database._ensure_column(cursor, "users", "terms_version", "TEXT")
        conn.commit()
    finally:
        conn.close()


def registrar_aceite(user_id: int) -> None:
    garantir_colunas()
    conn = _conectar()
    try:
        conn.execute("UPDATE users SET terms_accepted_at = ?, terms_version = ? WHERE id = ?",
                     (_agora(), VERSAO_TERMOS, user_id))
    finally:
        conn.close()


def _linhas(conn, sql: str, params=()) -> list:
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError:  # tabela opcional ausente em banco antigo
        return []


def exportar(user_id: int) -> Optional[Dict]:
    garantir_colunas()
    conn = _conectar()
    try:
        conta = conn.execute(
            "SELECT id, name, email, created_at, terms_accepted_at, terms_version FROM users "
            "WHERE id = ? AND role = 'student'", (user_id,)
        ).fetchone()
        if conta is None:
            return None
        perfil = _linhas(conn, "SELECT phone FROM user_profiles WHERE user_id = ?", (user_id,))
        matriculas = _linhas(conn, "SELECT id, course_id, status, enrolled_at FROM enrollments WHERE user_id = ? "
                                   "ORDER BY id", (user_id,))
        pagamentos = _linhas(conn, "SELECT p.id, p.enrollment_id, p.amount, p.payment_method, p.status, p.created_at "
                                   "FROM payments p JOIN enrollments e ON e.id = p.enrollment_id "
                                   "WHERE e.user_id = ? ORDER BY p.id", (user_id,))
        conversas = _linhas(conn, "SELECT role, content, created_at FROM chat_messages WHERE user_id = ? ORDER BY id",
                            (user_id,))
        cancelamentos = _linhas(conn, "SELECT c.enrollment_id, c.status, c.reason, c.requested_at "
                                      "FROM cancellation_requests c JOIN enrollments e ON e.id = c.enrollment_id "
                                      "WHERE e.user_id = ? ORDER BY c.id", (user_id,))
        return {
            "gerado_em": _agora(),
            "conta": {**dict(conta), "phone": perfil[0]["phone"] if perfil else None},
            "matriculas": matriculas,
            "pagamentos": pagamentos,
            "conversas_do_chat": conversas,
            "pedidos_de_cancelamento": cancelamentos,
        }
    finally:
        conn.close()


def anonimizar(user_id: int) -> Optional[str]:
    """Anonimiza a conta do aluno numa transação. Devolve o e-mail antigo (para limpar limites) ou None."""
    conn = _conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conta = conn.execute("SELECT email FROM users WHERE id = ? AND role = 'student'", (user_id,)).fetchone()
        if conta is None:
            conn.execute("ROLLBACK")
            return None
        conn.execute(
            "UPDATE users SET name = 'Conta excluída', email = ?, password_hash = NULL, is_active = 0, "
            "token_version = token_version + 1 WHERE id = ?",
            (f"excluido-{user_id}@anonimo.invalid", user_id),
        )
        for sql in ("DELETE FROM user_profiles WHERE user_id = ?",
                    "DELETE FROM chat_messages WHERE user_id = ?",
                    "DELETE FROM password_setup_tokens WHERE user_id = ?"):
            try:
                conn.execute(sql, (user_id,))
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("UPDATE cancellation_requests SET reason = NULL WHERE enrollment_id IN "
                         "(SELECT id FROM enrollments WHERE user_id = ?)", (user_id,))
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM login_attempts WHERE scope = 'email' AND key = ?", (conta["email"].lower(),))
        except sqlite3.OperationalError:
            pass
        conn.execute("COMMIT")
        return conta["email"]
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
