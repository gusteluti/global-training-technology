import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.fuso import MODIFICADOR_SQLITE_SP, dia_sao_paulo

class Database:
    """SQLite database: contas de usuário, alunos, matrículas, pagamentos e trilha de auditoria."""

    DB_PATH = Path(__file__).parent / "db.sqlite"

    @staticmethod
    def init_db():
        """Initialize database tables"""
        # isolation_level=None: controle explícito da transação da migração.
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None)
        cursor = conn.cursor()

        # Identidade unificada (E1): users, enrollments.user_id e status padronizado.
        # Tudo ou nada: se qualquer passo falhar, o banco volta ao estado anterior.
        cursor.execute("BEGIN IMMEDIATE")
        try:
            Database._migrar_identidade_e1(cursor)
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            conn.close()
            raise

        # L1 (D53): turmas. Matrícula sem turma tem class_id nulo; bancos antigos ganham a coluna sem perda.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id TEXT NOT NULL,
                name TEXT NOT NULL,
                starts_on TEXT,
                capacity INTEGER CHECK (capacity IS NULL OR capacity >= 1),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (course_id, name)
            )
        """)
        Database._ensure_column(cursor, "enrollments", "class_id", "INTEGER")
        # U8 (D83): término e horário da turma. Bancos antigos ganham as colunas nulas (idempotente).
        Database._ensure_column(cursor, "classes", "ends_on", "TEXT")
        Database._ensure_column(cursor, "classes", "schedule", "TEXT")
        # S4/S5 (D80): conta ativa e versão do token. Bancos antigos ganham as colunas com os padrões (idempotente).
        Database._ensure_column(cursor, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
        Database._ensure_column(cursor, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
        # U3 (D80): telefone do perfil do aluno, fora de `users` (a tabela de contas só ganha as colunas da D80).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                phone TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_class ON enrollments (class_id)")
        # F5a (D75): fim da reserva de vaga do checkout, em UTC 'AAAA-MM-DD HH:MM:SS' (mesmo formato de
        # CURRENT_TIMESTAMP). Nulo = sem reserva (atribuída pela Gestão ou anterior à F5a).
        Database._ensure_column(cursor, "enrollments", "reserved_until", "TEXT")

        # Payments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enrollment_id INTEGER NOT NULL,
                amount FLOAT NOT NULL,
                status TEXT DEFAULT 'pending',
                payment_method TEXT,
                transaction_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (enrollment_id) REFERENCES enrollments(id)
            )
        """)

        # E9 (D48): o mesmo transaction_id não pode estar em dois pagamentos (índice único parcial,
        # só valores não nulos). Base antiga com duplicados: não derruba a inicialização; o índice
        # fica sem ser criado, o problema é registrado e a transição do webhook segue conferindo o
        # transaction_id antes de gravar.
        try:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_transaction_id_unique "
                "ON payments (transaction_id) WHERE transaction_id IS NOT NULL"
            )
        except sqlite3.DatabaseError as exc:
            print(f"[AVISO] Indice unico de payments.transaction_id nao criado ({type(exc).__name__}): "
                  "ha transaction_id repetido na base; corrija os duplicados e reinicie.")

        # Tokens de definição de senha (E2, D12). Guarda só o SHA-256 do token, nunca o token em claro.
        # used_at marca o uso único; expires_at é UTC (48 h após a emissão).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_setup_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                purpose TEXT NOT NULL DEFAULT 'setup',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # B1 (D60): finalidade do token ('setup' definição de senha, 'reset' redefinição). Bancos antigos
        # ganham a coluna; os tokens que já existiam viram 'setup'. Idempotente.
        Database._ensure_column(cursor, "password_setup_tokens", "purpose", "TEXT NOT NULL DEFAULT 'setup'")

        # Audit logs table (Trilhas de auditoria). Schema único: aceita eventos de
        # conta (user_id) e de perfil de funcionário (role). Bases criadas pelas
        # versões anteriores recebem as colunas que faltam.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        Database._ensure_column(cursor, "audit_logs", "user_id", "INTEGER")
        Database._ensure_column(cursor, "audit_logs", "role", "TEXT")
        Database._ensure_column(cursor, "audit_logs", "detail", "TEXT")
        # E8 (D45): responsável pela pessoa, entidade afetada e alteração estruturada.
        Database._ensure_column(cursor, "audit_logs", "actor_email", "TEXT")
        Database._ensure_column(cursor, "audit_logs", "actor_name", "TEXT")
        Database._ensure_column(cursor, "audit_logs", "entity_type", "TEXT")
        Database._ensure_column(cursor, "audit_logs", "entity_id", "TEXT")
        Database._ensure_column(cursor, "audit_logs", "changes", "TEXT")
        # Trilha append-only: o próprio banco recusa UPDATE e DELETE (também em bases antigas).
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'audit_logs e append-only: UPDATE nao permitido');
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'audit_logs e append-only: DELETE nao permitido');
            END
        """)

        # Histórico do chatbot autenticado (E5, D35): uma conversa contínua por aluno.
        # role é 'user' (mensagem do aluno) ou 'assistant' (resposta do bot).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages (user_id, id)")

        # Observabilidade de IA (E7, D42). ai_usage: uma linha por chamada ao Groq (usage, custo no momento da
        # chamada, latência). ai_interactions: uma linha por mensagem que chegou ao pipeline do chatbot.
        # Nunca guardam texto de mensagem (exceto `topic` mascarado, só no canal anônimo e só 'unresolved'),
        # texto de exceção nem o id cru da sessão anônima (session_hash é prefixo de sha256).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL CHECK (channel IN ('anonymous', 'student')),
                user_id INTEGER,
                session_hash TEXT,
                call_type TEXT NOT NULL CHECK (call_type IN ('route', 'answer')),
                model TEXT,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL CHECK (status IN ('ok', 'error'))
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage (created_at)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL CHECK (channel IN ('anonymous', 'student')),
                user_id INTEGER,
                session_hash TEXT,
                course_id TEXT,
                outcome TEXT NOT NULL
                    CHECK (outcome IN ('answered', 'unresolved', 'input_blocked', 'output_blocked', 'llm_error')),
                topic TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_interactions_user ON ai_interactions (user_id, id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_interactions_session ON ai_interactions (session_hash, id)")
        # F6 (D77): uma linha por ação de handoff para o WhatsApp emitida. Mesma identidade da E7 (user_id do JWT
        # ou session_hash); nunca o número, texto de mensagem nem o id cru da sessão.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL CHECK (channel IN ('anonymous', 'student')),
                user_id INTEGER,
                session_hash TEXT,
                reason TEXT NOT NULL
                    CHECK (reason IN ('user_request', 'llm_failures', 'token_budget', 'unresolved')),
                course_id TEXT
            )
        """)

        # S2 (D79): limite de tentativas de login. Uma linha por falha ('fail') ou bloqueio ('lock') de um e-mail
        # normalizado ou de um IP. Datas em UTC no formato de CURRENT_TIMESTAMP. Nunca guarda senha.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK (scope IN ('email', 'ip')),
                key TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('fail', 'lock')),
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_key ON login_attempts (scope, key, kind, created_at)"
        )

        # U5 (D82): pedido de cancelamento em 7 dias. Um pedido `open` por matrícula (índice único parcial);
        # recusados e aprovados ficam como histórico. Datas em UTC no formato de CURRENT_TIMESTAMP.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cancellation_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enrollment_id INTEGER NOT NULL,
                payment_id INTEGER,
                user_id INTEGER NOT NULL,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'approved', 'rejected')),
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decided_at TIMESTAMP,
                decision_reason TEXT,
                FOREIGN KEY (enrollment_id) REFERENCES enrollments(id),
                FOREIGN KEY (payment_id) REFERENCES payments(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_cancellation_requests_enrollment ON cancellation_requests (enrollment_id, id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_cancellation_requests_open "
            "ON cancellation_requests (enrollment_id) WHERE status = 'open'"
        )

        conn.commit()
        conn.close()
        print("[OK] Database initialized")

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
        """Adds a column to an existing table if it isn't there yet (lightweight migration)."""
        existing_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # Status de matrícula fechado (decisão do PM): pending, active, cancelled, refunded.
    MATRICULA_STATUS = ("pending", "active", "cancelled", "refunded")

    # Status de pagamento (vocabulário do Mercado Pago) -> status de matrícula.
    # Status de pagamento fora deste mapa não altera a matrícula.
    MATRICULA_POR_PAGAMENTO = {
        "approved": "active",
        "refunded": "refunded",
        "charged_back": "refunded",  # D49.1: estorno devolve o dinheiro ao comprador e revoga o acesso
        "rejected": "cancelled",
        "cancelled": "cancelled",
        "pending": "pending",
        "in_process": "pending",
    }

    _DDL_ENROLLMENTS = """
        CREATE TABLE {nome} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'active', 'cancelled', 'refunded')),
            external_reference TEXT,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            class_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """

    @staticmethod
    def _enrollments_ja_migrada(cursor: sqlite3.Cursor) -> bool:
        colunas = {row[1] for row in cursor.execute("PRAGMA table_info(enrollments)")}
        sql = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'enrollments'"
        ).fetchone()[0] or ""
        return "user_id" in colunas and "student_id" not in colunas and "CHECK" in sql.upper()

    @staticmethod
    def _migrar_identidade_e1(cursor: sqlite3.Cursor):
        """Migração idempotente da E1. Roda dentro de uma transação (ver init_db).

        - students -> users (role 'student', sem senha). E-mails já existentes em users
          são preservados como estão (INSERT OR IGNORE: não rebaixa papel nem apaga senha).
        - enrollments: ganha user_id (por e-mail) e status normalizado com CHECK.
          SQLite não adiciona CHECK com ALTER, então a tabela é reconstruída.
        - students é removida ao final, depois de copiada para users.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT,
                role TEXT DEFAULT 'student',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        tabelas = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        tem_students = "students" in tabelas

        if tem_students:
            cursor.execute("""
                INSERT OR IGNORE INTO users (email, name, password_hash, role, created_at)
                SELECT email, name, NULL, 'student', created_at FROM students
            """)

        if "enrollments" not in tabelas:
            cursor.execute(Database._DDL_ENROLLMENTS.format(nome="enrollments"))
        elif not Database._enrollments_ja_migrada(cursor):
            Database._ensure_column(cursor, "enrollments", "external_reference", "TEXT")
            total_antes = cursor.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0]

            cursor.execute(Database._DDL_ENROLLMENTS.format(nome="enrollments_novo"))
            cursor.execute("""
                INSERT INTO enrollments_novo (id, user_id, course_id, status, external_reference, enrolled_at)
                SELECT
                    e.id,
                    (SELECT u.id FROM students s JOIN users u ON u.email = s.email WHERE s.id = e.student_id),
                    e.course_id,
                    CASE e.status
                        WHEN 'approved' THEN 'active'
                        WHEN 'completed' THEN 'active'
                        WHEN 'active' THEN 'active'
                        WHEN 'rejected' THEN 'cancelled'
                        WHEN 'cancelled' THEN 'cancelled'
                        WHEN 'refunded' THEN 'refunded'
                        WHEN 'in_process' THEN 'pending'
                        ELSE 'pending'
                    END,
                    e.external_reference,
                    e.enrolled_at
                FROM enrollments e
            """)
            total_depois = cursor.execute("SELECT COUNT(*) FROM enrollments_novo").fetchone()[0]
            if total_depois != total_antes:
                raise RuntimeError(
                    f"Migração E1 abortada: {total_antes} matrículas antigas, {total_depois} copiadas."
                )

            cursor.execute("DROP TABLE enrollments")
            cursor.execute("ALTER TABLE enrollments_novo RENAME TO enrollments")

        if tem_students:
            cursor.execute("DROP TABLE students")

    @staticmethod
    def get_or_create_user(email: str, name: str) -> int:
        """Id da conta do aluno para este e-mail; cria como role 'student' sem senha se não existir.
        Conta existente (inclusive de funcionário) não é alterada."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            user_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, NULL, 'student')",
                (email, name)
            )
            conn.commit()
            user_id = cursor.lastrowid

        conn.close()
        return user_id

    @staticmethod
    def add_user(email: str, name: str, password_hash: Optional[str] = None, role: str = "student") -> Optional[int]:
        """Add a new user (student or staff)"""
        try:
            conn = sqlite3.connect(Database.DB_PATH)
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (email, name, password_hash, role)
            )

            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, name, password_hash, role, created_at, is_active, token_version "
            "FROM users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "email": row[1],
            "name": row[2],
            "password_hash": row[3],
            "role": row[4],
            "created_at": row[5],
            "is_active": row[6],
            "token_version": row[7],
        }

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, email, name, password_hash, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_session_user(user_id) -> Optional[dict]:
        """Conta conferida em toda requisição com JWT de conta (D80): uma consulta só."""
        if not Database._id_sqlite_valido(user_id):
            return None
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, email, name, role, created_at, is_active, token_version FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def set_student_active(user_id, ativo: bool) -> Optional[Dict]:
        """Desativa/reativa uma conta de aluno (S4, D80). None se o id não for de aluno. Idempotente: só muda na
        transição. Desativar incrementa token_version na mesma instrução."""
        if not Database._id_sqlite_valido(user_id):
            return None
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT is_active FROM users WHERE id = ? AND role = 'student'", (user_id,)
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                mudou = bool(row[0]) != bool(ativo)
                if mudou:
                    if ativo:
                        conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
                    else:
                        conn.execute(
                            "UPDATE users SET is_active = 0, token_version = token_version + 1 WHERE id = ?",
                            (user_id,),
                        )
                conn.execute("COMMIT")
                return {"changed": mudou, "is_active": bool(ativo)}
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @staticmethod
    def get_student_profile(user_id: int) -> Optional[Dict]:
        """Perfil do aluno (U3, D80): id, nome, e-mail e telefone. Sem hash de senha nem token_version."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT u.id, u.name, u.email, p.phone
                   FROM users u LEFT JOIN user_profiles p ON p.user_id = u.id
                   WHERE u.id = ?""",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def update_student_profile(user_id: int, name: str, phone: Optional[str], alterar_telefone: bool) -> None:
        """Grava o nome (e, se pedido, o telefone) da conta do próprio aluno numa transação. E-mail nunca muda."""
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
                if alterar_telefone:
                    conn.execute(
                        """INSERT INTO user_profiles (user_id, phone, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(user_id) DO UPDATE SET phone = excluded.phone,
                           updated_at = CURRENT_TIMESTAMP""",
                        (user_id, phone),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @staticmethod
    def get_password_hash_and_version(user_id: int) -> Optional[Dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT password_hash, token_version FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def trocar_senha(user_id: int, hash_atual: Optional[str], versao_atual: int, novo_hash: str) -> Optional[int]:
        """Troca de senha logado (S5, D80): grava o hash novo e incrementa token_version na mesma instrução, só se a
        senha e a versão ainda são as conferidas (a corrida perde). Devolve a versão nova, ou None se nada mudou."""
        conn = sqlite3.connect(Database.DB_PATH, timeout=30)
        try:
            mudou = conn.execute(
                "UPDATE users SET password_hash = ?, token_version = token_version + 1 "
                "WHERE id = ? AND password_hash IS ? AND token_version = ? AND is_active = 1",
                (novo_hash, user_id, hash_atual, versao_atual),
            ).rowcount == 1
            conn.commit()
            return versao_atual + 1 if mudou else None
        finally:
            conn.close()

    @staticmethod
    def get_user_by_external_reference(external_reference: str) -> Optional[dict]:
        """Conta dona da matrícula ligada a esta referência de compra (usada pelo webhook)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT u.id, u.email, u.name, u.password_hash, u.role
                   FROM enrollments e JOIN users u ON u.id = e.user_id
                   WHERE e.external_reference = ? LIMIT 1""",
                (external_reference,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def insert_password_setup_token(user_id: int, token_hash: str, expires_at: str, purpose: str = "setup") -> int:
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, purpose) VALUES (?, ?, ?, ?)",
                (user_id, token_hash, expires_at, purpose),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # B1 (D60): no máximo 3 tokens emitidos por conta numa janela móvel de 1 hora (qualquer finalidade).
    LIMITE_TOKENS_POR_HORA = 3

    @staticmethod
    def count_recent_password_tokens(user_id: int, janela_minutos: int = 60) -> int:
        """Tokens (de qualquer finalidade, usados ou não) emitidos para a conta na janela móvel, por created_at."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM password_setup_tokens WHERE user_id = ? "
                "AND created_at > datetime('now', ?)",
                (user_id, f"-{int(janela_minutos)} minutes"),
            ).fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def emitir_token_com_limite(user_id: int, token_hash: str, expires_at: str, purpose: str,
                                limite: int = LIMITE_TOKENS_POR_HORA, janela_minutos: int = 60) -> bool:
        """Emissão atômica (BEGIN IMMEDIATE): conta os tokens da janela, invalida os abertos anteriores da mesma
        conta e finalidade e insere o novo, tudo na mesma transação. False (nada gravado) se o limite foi atingido."""
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                recentes = conn.execute(
                    "SELECT COUNT(*) FROM password_setup_tokens WHERE user_id = ? "
                    "AND created_at > datetime('now', ?)",
                    (user_id, f"-{int(janela_minutos)} minutes"),
                ).fetchone()[0]
                if recentes >= limite:
                    conn.execute("ROLLBACK")
                    return False
                conn.execute(
                    "UPDATE password_setup_tokens SET used_at = CURRENT_TIMESTAMP "
                    "WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
                    (user_id, purpose),
                )
                conn.execute(
                    "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at, purpose) VALUES (?, ?, ?, ?)",
                    (user_id, token_hash, expires_at, purpose),
                )
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @staticmethod
    def get_password_setup_token(token_hash: str) -> Optional[dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, user_id, expires_at, used_at, purpose FROM password_setup_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def definir_senha_com_token(token_id: int, user_id: int, password_hash: str) -> bool:
        """Marca o token como usado e grava a senha da conta dona dele, numa só transação.

        Só vale para token de definição ('setup'). Recusa (False, sem alterar nada) se o token já foi usado,
        se não é 'setup' ou se a conta já tem senha.
        """
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                marcou = conn.execute(
                    "UPDATE password_setup_tokens SET used_at = CURRENT_TIMESTAMP "
                    "WHERE id = ? AND used_at IS NULL AND purpose = 'setup'",
                    (token_id,),
                ).rowcount == 1
                definiu = marcou and conn.execute(
                    "UPDATE users SET password_hash = ?, token_version = token_version + 1 "
                    "WHERE id = ? AND password_hash IS NULL",
                    (password_hash, user_id),
                ).rowcount == 1
                if not definiu:
                    conn.execute("ROLLBACK")
                    return False
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @staticmethod
    def redefinir_senha_com_token(token_hash: str, password_hash: str, agora: str) -> Optional[str]:
        """Consumo atômico do token de redefinição (BEGIN IMMEDIATE, B1/D60). Só vale token 'reset', não usado,
        não expirado (`agora` em UTC, 'YYYY-MM-DD HH:MM:SS') e de conta de aluno. Marca o token como usado, troca a
        senha da conta DONA do token e invalida os demais tokens abertos dela. Devolve o e-mail da conta, ou None
        (sem alterar nada) se a redefinição não valeu."""
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT t.id, t.user_id, u.email FROM password_setup_tokens t "
                    "JOIN users u ON u.id = t.user_id "
                    "WHERE t.token_hash = ? AND t.purpose = 'reset' AND t.used_at IS NULL "
                    "AND t.expires_at > ? AND u.role = 'student'",
                    (token_hash, agora),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                _token_id, user_id, email = row
                conn.execute(
                    "UPDATE password_setup_tokens SET used_at = CURRENT_TIMESTAMP "
                    "WHERE user_id = ? AND used_at IS NULL",
                    (user_id,),
                )
                # S5 (D80): a troca de senha e a revogação dos tokens antigos vão na mesma instrução.
                conn.execute(
                    "UPDATE users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                    (password_hash, user_id),
                )
                conn.execute("COMMIT")
                return email
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    @staticmethod
    def get_revenue_totals() -> Dict:
        """Totais de receita para o dashboard da aplicação Angular.
        Conta 'approved' (vocabulário do Mercado Pago) e 'completed' (vocabulário da versão anterior)."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status IN ('approved', 'completed')")
        total = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        conn.close()
        return {"total_revenue": total, "pending_payments": pending}

    @staticmethod
    def get_student_metrics():
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'student'")
        total_students = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM enrollments WHERE status = 'active'")
        active_enrollments = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM enrollments WHERE status = 'active'")
        active_students = cursor.fetchone()[0]
        conn.close()
        return {
            "total_students": total_students,
            "active_students": active_students,
            "active_enrollments": active_enrollments,
        }

    @staticmethod
    def get_course_metrics():
        # Basic metrics by reading course files
        courses_dir = Path(__file__).parent / "courses"
        metrics = []
        if courses_dir.exists():
            for cf in courses_dir.glob("*.json"):
                try:
                    import json as _json
                    with open(cf, 'r', encoding='utf-8') as f:
                        data = _json.load(f)
                    metrics.append({
                        "id": data.get('id'),
                        "name": data.get('name'),
                        "price": data.get('price'),
                        "enrolled_count": 0
                    })
                except Exception:
                    continue
        return metrics

    @staticmethod
    def create_enrollment(user_id: int, course_id: str, external_reference: Optional[str] = None) -> int:
        """Create an enrollment (status inicial 'pending')"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO enrollments (user_id, course_id, status, external_reference) VALUES (?, ?, 'pending', ?)",
            (user_id, course_id, external_reference)
        )

        conn.commit()
        enrollment_id = cursor.lastrowid
        conn.close()
        return enrollment_id

    @staticmethod
    def record_payment(enrollment_id: int, amount: float, payment_method: str) -> int:
        """Record a payment"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO payments (enrollment_id, amount, payment_method, status)
               VALUES (?, ?, ?, ?)""",
            (enrollment_id, amount, payment_method, "pending")
        )

        conn.commit()
        payment_id = cursor.lastrowid
        conn.close()
        return payment_id

    @staticmethod
    def situacao_compra_do_curso(user_id: int, course_id: str) -> Optional[Dict]:
        """S1 (D72): matrícula do usuário no curso que impede ou é retomada numa nova compra.

        Devolve {"status": "active"} se houver matrícula ativa (prevalece sobre pendente); senão a pendente
        mais recente como {"status": "pending", "enrollment_id", "external_reference", "payment_id"}
        (payment_id = pagamento mais recente da matrícula, ou None); senão None.
        `cancelled`/`refunded` não contam."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            ativa = conn.execute(
                "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ? AND status = 'active' LIMIT 1",
                (user_id, course_id),
            ).fetchone()
            if ativa:
                return {"status": "active"}
            pendente = conn.execute(
                """SELECT e.id, e.external_reference,
                          (SELECT p.id FROM payments p WHERE p.enrollment_id = e.id
                           ORDER BY p.id DESC LIMIT 1) AS payment_id
                   FROM enrollments e
                   WHERE e.user_id = ? AND e.course_id = ? AND e.status = 'pending'
                     AND e.external_reference IS NOT NULL
                   ORDER BY e.id DESC LIMIT 1""",
                (user_id, course_id),
            ).fetchone()
            if not pendente:
                return None
            return {
                "status": "pending",
                "enrollment_id": pendente["id"],
                "external_reference": pendente["external_reference"],
                "payment_id": pendente["payment_id"],
            }
        finally:
            conn.close()

    @staticmethod
    def atualizar_valor_pagamento_pendente(payment_id: int, amount: float) -> bool:
        """S1 (D72): atualiza o valor de um pagamento ainda `pending` (preço do catálogo mudou)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                """UPDATE payments SET amount = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'pending' AND amount != ?""",
                (amount, payment_id, amount),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    # --- F5a (D75): turma no checkout, reserva de vaga e lotação ---------------------------------------
    RESERVA_VAGA = timedelta(minutes=30)

    # Ocupação de uma turma PARA VENDA (não muda os números do dashboard L1): active + pending com reserva
    # válida + pending sem reserva. `id != ?` exclui a própria matrícula (retomada e webhook).
    _SQL_OCUPACAO_VENDA = """
        SELECT COUNT(*) FROM enrollments
        WHERE class_id = ? AND id != ?
          AND (status = 'active'
               OR (status = 'pending' AND (reserved_until IS NULL OR reserved_until > ?)))
    """

    @staticmethod
    def _utc_texto(instante: datetime) -> str:
        """Instante UTC no formato do banco (o mesmo de CURRENT_TIMESTAMP)."""
        return instante.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _conferir_turma_para_venda(conn: sqlite3.Connection, course_id: str, class_id, excluir_enrollment_id,
                                   agora: datetime) -> str:
        """'ok' | 'not_found' (inexistente, de outro curso ou já iniciada em São Paulo) | 'full'."""
        if not Database._id_sqlite_valido(class_id):
            return "not_found"
        turma = conn.execute(
            "SELECT id, course_id, starts_on, capacity FROM classes WHERE id = ?", (class_id,)
        ).fetchone()
        if turma is None or turma[1] != course_id:
            return "not_found"
        if turma[2] is not None and str(turma[2]) < dia_sao_paulo(agora).isoformat():
            return "not_found"
        capacidade = turma[3]
        if capacidade is None:
            return "ok"
        ocupadas = conn.execute(
            Database._SQL_OCUPACAO_VENDA,
            (class_id, excluir_enrollment_id if excluir_enrollment_id is not None else -1,
             Database._utc_texto(agora)),
        ).fetchone()[0]
        return "full" if ocupadas >= capacidade else "ok"

    @staticmethod
    def conferir_turma_para_venda(course_id: str, class_id, excluir_enrollment_id: Optional[int] = None) -> str:
        """Conferência prévia (sem lock), antes do gateway. A decisão final é a de `reservar_vaga_no_checkout`."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            return Database._conferir_turma_para_venda(
                conn, course_id, class_id, excluir_enrollment_id, datetime.now(timezone.utc)
            )
        finally:
            conn.close()

    @staticmethod
    def reservar_vaga_no_checkout(
        course_id: str,
        class_id: int,
        *,
        amount: float,
        payment_method: str,
        external_reference: str,
        pendente_enrollment_id: Optional[int] = None,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        nome: Optional[str] = None,
    ) -> Dict:
        """Conferência de vaga e gravação na MESMA transação (BEGIN IMMEDIATE): duas compras da última vaga
        não vendem as duas. Retomada (pendente_enrollment_id): troca a turma e renova a reserva da pendente
        (a própria reserva não conta contra ela) e reaproveita o pagamento pendente. Compra nova: cria a conta
        (landing, por e-mail, se não existir), a matrícula 'pending' com turma e reserva e o pagamento.

        Devolve {"outcome": "ok" | "not_found" | "full" | "stale", "enrollment_id", "payment_id"}.
        Só "ok" grava. "stale": a pendente deixou de estar pendente durante a compra."""
        agora = datetime.now(timezone.utc)
        conn = Database._abrir_transacao_imediata()
        try:
            outcome = Database._conferir_turma_para_venda(conn, course_id, class_id, pendente_enrollment_id, agora)
            if outcome != "ok":
                conn.execute("ROLLBACK")
                return {"outcome": outcome, "enrollment_id": None, "payment_id": None}
            reserva = Database._utc_texto(agora + Database.RESERVA_VAGA)

            if pendente_enrollment_id is not None:
                atualizadas = conn.execute(
                    "UPDATE enrollments SET class_id = ?, reserved_until = ? WHERE id = ? AND status = 'pending'",
                    (class_id, reserva, pendente_enrollment_id),
                ).rowcount
                if atualizadas != 1:
                    conn.execute("ROLLBACK")
                    return {"outcome": "stale", "enrollment_id": None, "payment_id": None}
                enrollment_id = pendente_enrollment_id
                pagamento = conn.execute(
                    "SELECT id FROM payments WHERE enrollment_id = ? ORDER BY id DESC LIMIT 1", (enrollment_id,)
                ).fetchone()
                if pagamento is None:
                    payment_id = conn.execute(
                        "INSERT INTO payments (enrollment_id, amount, payment_method, status) "
                        "VALUES (?, ?, ?, 'pending')",
                        (enrollment_id, amount, payment_method),
                    ).lastrowid
                else:
                    payment_id = pagamento["id"]
                    conn.execute(
                        """UPDATE payments SET amount = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE id = ? AND status = 'pending' AND amount != ?""",
                        (amount, payment_id, amount),
                    )
            else:
                if user_id is None:
                    conta = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                    if conta is not None:
                        user_id = conta["id"]
                    else:
                        user_id = conn.execute(
                            "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, NULL, 'student')",
                            (email, nome),
                        ).lastrowid
                enrollment_id = conn.execute(
                    """INSERT INTO enrollments (user_id, course_id, status, external_reference, class_id,
                                                reserved_until)
                       VALUES (?, ?, 'pending', ?, ?, ?)""",
                    (user_id, course_id, external_reference, class_id, reserva),
                ).lastrowid
                payment_id = conn.execute(
                    "INSERT INTO payments (enrollment_id, amount, payment_method, status) VALUES (?, ?, ?, 'pending')",
                    (enrollment_id, amount, payment_method),
                ).lastrowid
            conn.execute("COMMIT")
            return {"outcome": "ok", "enrollment_id": enrollment_id, "payment_id": payment_id}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def list_open_classes_for_sale(course_id: str) -> List[Dict]:
        """Turmas abertas do curso (início nulo ou >= hoje em São Paulo) com vagas para venda.
        `seats_left` nulo sem capacidade; nunca negativo. Ordem: início (nulos por último) e nome."""
        agora = datetime.now(timezone.utc)
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            turmas = conn.execute(
                """SELECT id, name, starts_on, ends_on, schedule, capacity FROM classes
                   WHERE course_id = ? AND (starts_on IS NULL OR starts_on >= ?)
                   ORDER BY (starts_on IS NULL), starts_on, name, id""",
                (course_id, dia_sao_paulo(agora).isoformat()),
            ).fetchall()
            resultado = []
            for turma in turmas:
                seats_left = None
                if turma["capacity"] is not None:
                    ocupadas = conn.execute(
                        Database._SQL_OCUPACAO_VENDA, (turma["id"], -1, Database._utc_texto(agora))
                    ).fetchone()[0]
                    seats_left = max(turma["capacity"] - ocupadas, 0)
                resultado.append({
                    "id": turma["id"],
                    "name": turma["name"],
                    "starts_on": turma["starts_on"],
                    "ends_on": turma["ends_on"],
                    "schedule": turma["schedule"],
                    "capacity": turma["capacity"],
                    "seats_left": seats_left,
                })
            return resultado
        finally:
            conn.close()

    # E9 (D48/D49.5): update_payment_status* mantêm o comportamento anterior, com uma exceção imposta pelo
    # índice único de transaction_id: se outro pagamento já tem esse transaction_id, o status é atualizado
    # e o transaction_id do pagamento fica como estava (em vez de estourar IntegrityError).
    _SQL_ATUALIZAR_STATUS_SEM_COLISAO = """
        UPDATE payments SET status = ?,
            transaction_id = CASE
                WHEN ? IS NOT NULL AND EXISTS (SELECT 1 FROM payments o WHERE o.transaction_id = ? AND o.id != ?)
                THEN transaction_id ELSE ? END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?"""

    @staticmethod
    def update_payment_status(payment_id: int, status: str, transaction_id: Optional[str] = None):
        """Update payment status"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            Database._SQL_ATUALIZAR_STATUS_SEM_COLISAO,
            (status, transaction_id, transaction_id, payment_id, transaction_id, payment_id)
        )

        conn.commit()
        conn.close()

    @staticmethod
    def update_payment_status_by_reference(external_reference: str, status: str, transaction_id: Optional[str] = None) -> bool:
        """Update the most recent payment tied to an enrollment's external_reference (used by the payment webhook)."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """SELECT p.id FROM payments p
               JOIN enrollments e ON e.id = p.enrollment_id
               WHERE e.external_reference = ?
               ORDER BY p.id DESC LIMIT 1""",
            (external_reference,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False

        cursor.execute(
            Database._SQL_ATUALIZAR_STATUS_SEM_COLISAO,
            (status, transaction_id, transaction_id, row[0], transaction_id, row[0])
        )
        # A matrícula segue o status do pagamento pelo mapa fechado; status desconhecido não a altera.
        status_matricula = Database.MATRICULA_POR_PAGAMENTO.get(status)
        if status_matricula:
            cursor.execute(
                "UPDATE enrollments SET status = ? WHERE external_reference = ?",
                (status_matricula, external_reference)
            )

        conn.commit()
        conn.close()
        return True

    @staticmethod
    def mark_payment_refunded(payment_id: int) -> bool:
        """Reembolso: marca o pagamento e a matrícula dele como refunded (mesma transação)."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET status = 'refunded', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payment_id,)
        )
        if cursor.rowcount == 0:
            conn.close()
            return False
        cursor.execute(
            """UPDATE enrollments SET status = 'refunded'
               WHERE id = (SELECT enrollment_id FROM payments WHERE id = ?)""",
            (payment_id,)
        )
        conn.commit()
        conn.close()
        return True

    # E9 (D48/D49): máquina de estados do pagamento, usada só pelo webhook e pelo reembolso.
    PAGAMENTO_STATUS_WEBHOOK = tuple(MATRICULA_POR_PAGAMENTO)
    PAGAMENTO_TERMINAIS = ("refunded", "charged_back")

    @staticmethod
    def _abrir_transacao_imediata() -> sqlite3.Connection:
        """Conexão com BEGIN IMMEDIATE já aberto: escritores concorrentes esperam em fila (timeout 30 s)."""
        conn = sqlite3.connect(Database.DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            conn.close()
            raise
        return conn

    @staticmethod
    def aplicar_transicao_pagamento_webhook(
        external_reference: str,
        novo_status: str,
        transaction_id: str,
        valor_confere=None,
    ) -> Dict:
        """Transição de status vinda do webhook, atômica (BEGIN IMMEDIATE): decide e grava na mesma transação.

        Devolve {"outcome": ..., "payment_id", "amount", "status_before"}. `outcome`:
        unknown_reference | unsupported_status | terminal | duplicate | stale | amount_mismatch |
        duplicate_transaction | applied. Só `applied` altera o banco (pagamento e matrícula juntos).

        `valor_confere(pagamento: dict) -> bool` é chamado (dentro da transação) só quando um `approved`
        mudaria o pagamento; falso -> amount_mismatch, sem alteração.
        Regras (D48/D49): refunded e charged_back são terminais; approved só vai para refunded/charged_back;
        refunded/charged_back só a partir de approved; mesmo status é no-op; os demais movem-se livremente.
        """
        vazio = {"payment_id": None, "amount": None, "status_before": None}
        if novo_status not in Database.PAGAMENTO_STATUS_WEBHOOK:
            return {"outcome": "unsupported_status", **vazio}

        conn = Database._abrir_transacao_imediata()
        try:
            pagamento = conn.execute(
                """SELECT p.id, p.enrollment_id, p.amount, p.status
                   FROM payments p JOIN enrollments e ON e.id = p.enrollment_id
                   WHERE e.external_reference = ?
                   ORDER BY p.id DESC LIMIT 1""",
                (external_reference,),
            ).fetchone()
            if pagamento is None:
                conn.execute("ROLLBACK")
                return {"outcome": "unknown_reference", **vazio}

            anterior = pagamento["status"]
            resultado = {
                "payment_id": pagamento["id"],
                "amount": pagamento["amount"],
                "status_before": anterior,
            }

            def encerrar(outcome: str) -> Dict:
                conn.execute("ROLLBACK")
                return {"outcome": outcome, **resultado}

            if anterior in Database.PAGAMENTO_TERMINAIS:
                return encerrar("terminal")
            if anterior == novo_status:
                return encerrar("duplicate")
            if anterior == "approved" and novo_status not in Database.PAGAMENTO_TERMINAIS:
                return encerrar("stale")
            if novo_status in Database.PAGAMENTO_TERMINAIS and anterior != "approved":
                return encerrar("stale")
            if novo_status == "approved" and valor_confere is not None and not valor_confere(dict(pagamento)):
                return encerrar("amount_mismatch")
            outro = conn.execute(
                "SELECT id FROM payments WHERE transaction_id = ? AND id != ?",
                (transaction_id, pagamento["id"]),
            ).fetchone()
            if outro is not None:
                return encerrar("duplicate_transaction")

            atualizadas = conn.execute(
                """UPDATE payments SET status = ?, transaction_id = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = ?""",
                (novo_status, transaction_id, pagamento["id"], anterior),
            ).rowcount
            if atualizadas != 1:
                return encerrar("duplicate")
            status_matricula = Database.MATRICULA_POR_PAGAMENTO.get(novo_status)
            if status_matricula:
                conn.execute(
                    "UPDATE enrollments SET status = ? WHERE id = ?",
                    (status_matricula, pagamento["enrollment_id"]),
                )
            if status_matricula == "active":
                resultado["class_overflow"] = Database._tirar_da_turma_se_lotada(conn, pagamento["enrollment_id"])
            if novo_status == "approved":
                # S6 (D81): aprovação de um pagamento que a expiração tinha cancelado (evento gravado pela rota).
                resultado["approved_after_expiry"] = conn.execute(
                    "SELECT 1 FROM audit_logs WHERE action = ? AND entity_type = 'payment' AND entity_id = ? LIMIT 1",
                    (Database.EVENTO_PAGAMENTO_EXPIRADO, str(pagamento["id"])),
                ).fetchone() is not None
            conn.execute("COMMIT")
            return {"outcome": "applied", **resultado}
        except sqlite3.IntegrityError:
            # Índice único parcial de transaction_id (corrida entre dois pagamentos): nada é gravado.
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            return {"outcome": "duplicate_transaction", **vazio}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def _tirar_da_turma_se_lotada(conn: sqlite3.Connection, enrollment_id: int) -> Optional[Dict]:
        """S8 (D75), dentro da transação do webhook: matrícula ativada com reserva já vencida numa turma que
        os outros lotaram fica sem turma. Devolve {"enrollment_id", "class_id", "class_name"} quando tirou;
        None caso contrário (sem turma, sem reserva, reserva válida, sem capacidade ou com vaga)."""
        agora = datetime.now(timezone.utc)
        linha = conn.execute(
            """SELECT e.class_id, e.reserved_until, c.capacity, c.name
               FROM enrollments e JOIN classes c ON c.id = e.class_id
               WHERE e.id = ?""",
            (enrollment_id,),
        ).fetchone()
        if linha is None or linha["reserved_until"] is None or linha["capacity"] is None:
            return None
        if str(linha["reserved_until"]) > Database._utc_texto(agora):
            return None
        ocupadas = conn.execute(
            Database._SQL_OCUPACAO_VENDA, (linha["class_id"], enrollment_id, Database._utc_texto(agora))
        ).fetchone()[0]
        if ocupadas < linha["capacity"]:
            return None
        conn.execute("UPDATE enrollments SET class_id = NULL WHERE id = ?", (enrollment_id,))
        return {"enrollment_id": enrollment_id, "class_id": linha["class_id"], "class_name": linha["name"]}

    @staticmethod
    def _reembolsar_na_transacao(conn: sqlite3.Connection, payment_id: int) -> Dict:
        """Regra do reembolso da E9 dentro de uma transação já aberta (não faz COMMIT nem ROLLBACK).

        `outcome`: not_found | refunded (alterou agora) | already_refunded | not_approved. Quando reembolsa,
        o pedido de cancelamento `open` da matrícula (U5, D82) passa a `approved` na mesma transação.
        """
        pagamento = conn.execute(
            "SELECT id, enrollment_id, amount, status FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if pagamento is None:
            return {"outcome": "not_found"}
        base = {
            "payment_id": pagamento["id"],
            "amount": pagamento["amount"],
            "payment_status_before": pagamento["status"],
            "enrollment_status_before": None,
        }
        if pagamento["status"] == "refunded":
            return {"outcome": "already_refunded", **base}
        if pagamento["status"] != "approved":
            return {"outcome": "not_approved", **base}

        matricula = conn.execute(
            "SELECT status FROM enrollments WHERE id = ?", (pagamento["enrollment_id"],)
        ).fetchone()
        base["enrollment_status_before"] = matricula["status"] if matricula else None
        atualizadas = conn.execute(
            "UPDATE payments SET status = 'refunded', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'approved'",
            (payment_id,),
        ).rowcount
        if atualizadas != 1:
            return {"outcome": "already_refunded", **base}
        conn.execute(
            "UPDATE enrollments SET status = 'refunded' WHERE id = ?", (pagamento["enrollment_id"],)
        )
        conn.execute(
            "UPDATE cancellation_requests SET status = 'approved', decided_at = CURRENT_TIMESTAMP "
            "WHERE enrollment_id = ? AND status = 'open'",
            (pagamento["enrollment_id"],),
        )
        return {"outcome": "refunded", **base}

    @staticmethod
    def reembolsar_pagamento_se_aprovado(payment_id: int) -> Dict:
        """Reembolso atômico: só `approved` vira `refunded` (pagamento e matrícula, mesma transação).

        `outcome`: not_found | refunded (alterou agora) | already_refunded | not_approved.
        Dois reembolsos simultâneos: um devolve `refunded`, os outros `already_refunded`.
        U5 (D82): o pedido de cancelamento `open` da matrícula reembolsada passa a `approved`, na mesma transação.
        """
        conn = Database._abrir_transacao_imediata()
        try:
            resultado = Database._reembolsar_na_transacao(conn, payment_id)
            conn.execute("COMMIT" if resultado["outcome"] == "refunded" else "ROLLBACK")
            return resultado
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # --- U5 (D82): pedido de cancelamento em 7 dias ------------------------------------------------------------
    PRAZO_CANCELAMENTO = timedelta(days=7)
    CANCELAMENTO_STATUS = ("open", "approved", "rejected")

    _SQL_ULTIMO_APROVADO = """
        SELECT id, amount, payment_method, created_at, updated_at FROM payments
        WHERE enrollment_id = ? AND status = 'approved' ORDER BY id DESC LIMIT 1"""

    @staticmethod
    def _instante_utc(valor) -> Optional[datetime]:
        """Data do SQLite (UTC, 'AAAA-MM-DD HH:MM:SS' ou ISO) como datetime com fuso; None se ilegível."""
        if not valor:
            return None
        try:
            instante = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)

    @staticmethod
    def _impedimento_cancelamento(status_matricula: str, tem_aberto: bool, pagamento: Optional[Dict],
                                  agora: Optional[datetime] = None) -> Optional[str]:
        """Primeira condição da D82 que impede o pedido, na ordem do contrato; None quando pode pedir.

        not_active | already_open | no_refundable_payment | expired. `pagamento` é o último aprovado da matrícula
        (sem ele não há o que reembolsar). Data de aprovação ilegível conta como prazo vencido."""
        if status_matricula != "active":
            return "not_active"
        if tem_aberto:
            return "already_open"
        if pagamento is None or not float(pagamento["amount"] or 0) or pagamento["payment_method"] == "manual":
            return "no_refundable_payment"
        aprovado_em = Database._instante_utc(pagamento["updated_at"] or pagamento["created_at"])
        agora = agora or datetime.now(timezone.utc)
        if aprovado_em is None or agora - aprovado_em > Database.PRAZO_CANCELAMENTO:
            return "expired"
        return None

    @staticmethod
    def _tem_pedido_aberto(conn: sqlite3.Connection, enrollment_id: int) -> bool:
        return conn.execute(
            "SELECT 1 FROM cancellation_requests WHERE enrollment_id = ? AND status = 'open' LIMIT 1",
            (enrollment_id,),
        ).fetchone() is not None

    @staticmethod
    def cancelamento_das_matriculas(user_id: int) -> Dict[int, Dict]:
        """Por matrícula do aluno: {"cancellation": pedido mais recente ou None, "can_request_cancellation": bool}."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            agora = datetime.now(timezone.utc)
            situacao = {}
            for matricula in conn.execute("SELECT id, status FROM enrollments WHERE user_id = ?", (user_id,)).fetchall():
                ultimo = conn.execute(
                    """SELECT status, requested_at, decided_at, decision_reason FROM cancellation_requests
                       WHERE enrollment_id = ? ORDER BY id DESC LIMIT 1""",
                    (matricula["id"],),
                ).fetchone()
                pagamento = conn.execute(Database._SQL_ULTIMO_APROVADO, (matricula["id"],)).fetchone()
                impedimento = Database._impedimento_cancelamento(
                    matricula["status"], Database._tem_pedido_aberto(conn, matricula["id"]),
                    dict(pagamento) if pagamento else None, agora,
                )
                situacao[matricula["id"]] = {
                    "cancellation": dict(ultimo) if ultimo else None,
                    "can_request_cancellation": impedimento is None,
                }
            return situacao
        finally:
            conn.close()

    @staticmethod
    def criar_pedido_cancelamento(enrollment_id: int, user_id: int, reason: Optional[str]) -> Dict:
        """Pedido de cancelamento do aluno (D82), atômico: confere as condições e grava na mesma transação.

        `outcome`: not_found (inexistente ou alheia) | not_active | already_open | no_refundable_payment |
        expired | created (com request_id, payment_id e amount)."""
        if not Database._id_sqlite_valido(enrollment_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            matricula = conn.execute(
                "SELECT id, status FROM enrollments WHERE id = ? AND user_id = ?", (enrollment_id, user_id)
            ).fetchone()
            if matricula is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            pagamento = conn.execute(Database._SQL_ULTIMO_APROVADO, (enrollment_id,)).fetchone()
            pagamento = dict(pagamento) if pagamento else None
            impedimento = Database._impedimento_cancelamento(
                matricula["status"], Database._tem_pedido_aberto(conn, enrollment_id), pagamento
            )
            if impedimento is not None:
                conn.execute("ROLLBACK")
                return {"outcome": impedimento}
            request_id = conn.execute(
                "INSERT INTO cancellation_requests (enrollment_id, payment_id, user_id, reason) VALUES (?, ?, ?, ?)",
                (enrollment_id, pagamento["id"], user_id, reason),
            ).lastrowid
            conn.execute("COMMIT")
            return {"outcome": "created", "request_id": request_id, "payment_id": pagamento["id"],
                    "amount": pagamento["amount"]}
        except sqlite3.IntegrityError:
            # Índice único parcial: outro pedido `open` da mesma matrícula entrou primeiro.
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            return {"outcome": "already_open"}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def listar_pedidos_cancelamento(status: str = "open") -> List[Dict]:
        """Pedidos de cancelamento de um status, com aluno, curso e valor do pagamento (Financeiro e Gestão)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT r.id, r.enrollment_id, r.payment_id, u.name AS student_name, u.email AS student_email,
                          e.course_id, p.amount, r.requested_at, r.reason, r.status,
                          r.decided_at, r.decision_reason
                   FROM cancellation_requests r
                   JOIN enrollments e ON e.id = r.enrollment_id
                   JOIN users u ON u.id = e.user_id
                   LEFT JOIN payments p ON p.id = r.payment_id
                   WHERE r.status = ?
                   ORDER BY r.id""",
                (status,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def aprovar_pedido_cancelamento(request_id: int) -> Dict:
        """Aprovação atômica (D82): na mesma transação (BEGIN IMMEDIATE), confere o pedido `open`, aplica o
        reembolso da E9 e marca `approved` (condição no UPDATE). Aprovações simultâneas: uma passa, as demais
        `already_decided`.

        `outcome`: not_found | already_decided | not_approved (pagamento não está aprovado; nada muda) |
        approved (com `refund`: resultado do reembolso, `refunded` ou `already_refunded`)."""
        if not Database._id_sqlite_valido(request_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            pedido = conn.execute(
                "SELECT id, enrollment_id, payment_id, status FROM cancellation_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if pedido is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            if pedido["status"] != "open":
                conn.execute("ROLLBACK")
                return {"outcome": "already_decided"}
            reembolso = Database._reembolsar_na_transacao(conn, pedido["payment_id"])
            if reembolso["outcome"] not in ("refunded", "already_refunded"):
                conn.execute("ROLLBACK")
                return {"outcome": "not_approved", "refund": reembolso}
            # O reembolso feito agora já marcou o pedido; se o pagamento já estava reembolsado, marca aqui.
            conn.execute(
                "UPDATE cancellation_requests SET status = 'approved', decided_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status = 'open'",
                (request_id,),
            )
            status = conn.execute("SELECT status FROM cancellation_requests WHERE id = ?", (request_id,)).fetchone()
            if status["status"] != "approved":
                conn.execute("ROLLBACK")
                return {"outcome": "already_decided"}
            conn.execute("COMMIT")
            return {"outcome": "approved", "enrollment_id": pedido["enrollment_id"], "refund": reembolso}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def recusar_pedido_cancelamento(request_id: int, decision_reason: str) -> Dict:
        """Recusa atômica (D82): só `open` vira `rejected` (condição no UPDATE).
        `outcome`: not_found | already_decided | rejected."""
        if not Database._id_sqlite_valido(request_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            pedido = conn.execute(
                "SELECT id, enrollment_id FROM cancellation_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if pedido is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            atualizadas = conn.execute(
                "UPDATE cancellation_requests SET status = 'rejected', decided_at = CURRENT_TIMESTAMP, "
                "decision_reason = ? WHERE id = ? AND status = 'open'",
                (decision_reason, request_id),
            ).rowcount
            if atualizadas != 1:
                conn.execute("ROLLBACK")
                return {"outcome": "already_decided"}
            conn.execute("COMMIT")
            return {"outcome": "rejected", "enrollment_id": pedido["enrollment_id"]}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # --- S6 (D81): expiração de pagamento pendente ---------------------------------------------------------------
    PRAZO_PENDENTE = timedelta(days=7)
    EVENTO_PAGAMENTO_EXPIRADO = "payment.expired"

    _SQL_PENDENTES_VENCIDOS = """
        SELECT p.id, p.enrollment_id FROM payments p
        WHERE p.status = 'pending' AND p.created_at IS NOT NULL
          AND datetime(p.created_at) < datetime(?)
        ORDER BY p.id"""

    @staticmethod
    def expirar_pendentes() -> int:
        """S6 (D81): pagamento `pending` criado há mais de 7 dias (payments.created_at, UTC) passa a `cancelled`,
        com a matrícula `pending` dele, liberando a vaga. Grava `payment.expired` por pagamento expirado, na mesma
        transação. Idempotente (o que já expirou não é `pending`). Leitura prévia sem lock: sem vencidos, não
        abre transação de escrita. Devolve quantos pagamentos expiraram."""
        limite = Database._utc_texto(datetime.now(timezone.utc) - Database.PRAZO_PENDENTE)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            if conn.execute(Database._SQL_PENDENTES_VENCIDOS + " LIMIT 1", (limite,)).fetchone() is None:
                return 0
        finally:
            conn.close()

        conn = Database._abrir_transacao_imediata()
        try:
            expirados = 0
            for pagamento in conn.execute(Database._SQL_PENDENTES_VENCIDOS, (limite,)).fetchall():
                atualizado = conn.execute(
                    "UPDATE payments SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ? AND status = 'pending'",
                    (pagamento["id"],),
                ).rowcount
                if atualizado != 1:
                    continue
                matricula = conn.execute(
                    "UPDATE enrollments SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                    (pagamento["enrollment_id"],),
                ).rowcount
                mudancas = [{"field": "payment.status", "before": "pending", "after": "cancelled"}]
                if matricula == 1:
                    mudancas.append({"field": "enrollment.status", "before": "pending", "after": "cancelled"})
                conn.execute(
                    """INSERT INTO audit_logs (user_id, role, action, detail, entity_type, entity_id, changes)
                       VALUES (NULL, 'system', ?, ?, 'payment', ?, ?)""",
                    (
                        Database.EVENTO_PAGAMENTO_EXPIRADO,
                        f"Pagamento #{pagamento['id']}: pendente há mais de 7 dias, expirado "
                        f"(matrícula #{pagamento['enrollment_id']} cancelada)",
                        str(pagamento["id"]),
                        json.dumps(mudancas, ensure_ascii=False),
                    ),
                )
                expirados += 1
            conn.execute("COMMIT")
            return expirados
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # --- U4 (D81): matrícula manual pela Gestão ------------------------------------------------------------------

    @staticmethod
    def matricular_manualmente(
        email: str,
        nome: str,
        course_id: str,
        class_id: Optional[int],
        amount: float,
        external_reference: str,
    ) -> Dict:
        """Matrícula manual numa transação (BEGIN IMMEDIATE): conta (criada sem senha, se não existir), matrícula
        `active` e pagamento `approved` `manual`. Uma `pending` do mesmo curso é reaproveitada (vira `active`; os
        pagamentos pendentes dela viram `cancelled` e o pagamento manual é acrescentado).

        `outcome`: ok | staff | already_active | class_not_found | class_full. Só `ok` grava.
        Em `ok`: user_id, user_created, enrollment_id, payment_id, reused (bool), class_id, class_name."""
        agora = datetime.now(timezone.utc)
        conn = Database._abrir_transacao_imediata()
        try:
            def recusar(outcome: str) -> Dict:
                conn.execute("ROLLBACK")
                return {"outcome": outcome}

            conta = conn.execute("SELECT id, role FROM users WHERE email = ?", (email,)).fetchone()
            if conta is not None and (conta["role"] or "student") != "student":
                return recusar("staff")

            pendente = None
            if conta is not None:
                ativa = conn.execute(
                    "SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ? AND status = 'active' LIMIT 1",
                    (conta["id"], course_id),
                ).fetchone()
                if ativa is not None:
                    return recusar("already_active")
                pendente = conn.execute(
                    """SELECT id, class_id FROM enrollments
                       WHERE user_id = ? AND course_id = ? AND status = 'pending'
                       ORDER BY id DESC LIMIT 1""",
                    (conta["id"], course_id),
                ).fetchone()

            if class_id is not None:
                turma = Database._conferir_turma_para_venda(
                    conn, course_id, class_id, pendente["id"] if pendente is not None else None, agora
                )
                if turma == "not_found":
                    return recusar("class_not_found")
                if turma == "full":
                    return recusar("class_full")

            user_created = conta is None
            if user_created:
                user_id = conn.execute(
                    "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, NULL, 'student')",
                    (email, nome),
                ).lastrowid
            else:
                user_id = conta["id"]

            if pendente is not None:
                enrollment_id = pendente["id"]
                turma_final = class_id if class_id is not None else pendente["class_id"]
                conn.execute(
                    "UPDATE enrollments SET status = 'active', class_id = ? WHERE id = ?",
                    (turma_final, enrollment_id),
                )
                conn.execute(
                    "UPDATE payments SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP "
                    "WHERE enrollment_id = ? AND status = 'pending'",
                    (enrollment_id,),
                )
            else:
                turma_final = class_id
                enrollment_id = conn.execute(
                    """INSERT INTO enrollments (user_id, course_id, status, external_reference, class_id)
                       VALUES (?, ?, 'active', ?, ?)""",
                    (user_id, course_id, external_reference, class_id),
                ).lastrowid
            payment_id = conn.execute(
                "INSERT INTO payments (enrollment_id, amount, payment_method, status) "
                "VALUES (?, ?, 'manual', 'approved')",
                (enrollment_id, amount),
            ).lastrowid

            nome_turma = None
            if turma_final is not None:
                linha = conn.execute("SELECT name FROM classes WHERE id = ?", (turma_final,)).fetchone()
                nome_turma = linha["name"] if linha else None
            conn.execute("COMMIT")
            return {
                "outcome": "ok",
                "user_id": user_id,
                "user_created": user_created,
                "enrollment_id": enrollment_id,
                "payment_id": payment_id,
                "reused": pendente is not None,
                "class_id": turma_final,
                "class_name": nome_turma,
            }
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def list_enrollments_for_user(user_id: int) -> List[Dict]:
        """Matrículas de UMA conta (painel do aluno). O filtro por user_id fica no SQL."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT e.id, e.course_id, e.status, e.enrolled_at,
                          c.name AS class_name, c.starts_on AS class_starts_on,
                          c.ends_on AS class_ends_on, c.schedule AS class_schedule
                   FROM enrollments e LEFT JOIN classes c ON c.id = e.class_id
                   WHERE e.user_id = ? ORDER BY e.id DESC""",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def get_enrollment_for_user(enrollment_id: int, user_id: int) -> Optional[Dict]:
        """Uma matrícula, só se pertencer a user_id. Matrícula alheia e inexistente devolvem None (E3, IDOR)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT e.id, e.course_id, e.status, e.enrolled_at,
                          c.name AS class_name, c.starts_on AS class_starts_on,
                          c.ends_on AS class_ends_on, c.schedule AS class_schedule
                   FROM enrollments e LEFT JOIN classes c ON c.id = e.class_id
                   WHERE e.id = ? AND e.user_id = ?""",
                (enrollment_id, user_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def list_payments_for_user(user_id: int) -> List[Dict]:
        """Histórico financeiro de UMA conta de aluno.

        O vínculo com ``enrollments.user_id`` fica no SQL, para que a camada
        HTTP nunca receba pagamentos de outra conta para filtrar em memória.
        """
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT p.id, p.enrollment_id, p.amount, p.status,
                          p.payment_method, p.transaction_id, p.created_at, p.updated_at,
                          e.course_id
                   FROM payments p
                   JOIN enrollments e ON e.id = p.enrollment_id
                   WHERE e.user_id = ?
                   ORDER BY p.id DESC""",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def get_payment_for_user(payment_id: int, user_id: int) -> Optional[Dict]:
        """Pagamento somente quando pertence ao aluno indicado.

        A ausência no resultado representa tanto id inexistente quanto recurso
        de terceiro, permitindo à rota usar a mesma resposta 404 (IDOR).
        """
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT p.id, p.enrollment_id, p.amount, p.status,
                          p.payment_method, p.transaction_id, p.created_at, p.updated_at,
                          e.course_id
                   FROM payments p
                   JOIN enrollments e ON e.id = p.enrollment_id
                   WHERE p.id = ? AND e.user_id = ?""",
                (payment_id, user_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_payment_by_id(payment_id: int) -> Optional[Dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_payments_overview(limit: Optional[int] = 50) -> List[Dict]:
        """Individual payments with student/course context (Dashboard Financeiro).

        `limit=None` devolve todos (U1, D74: a lista do painel pagina e filtra na rota)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        limite_sql = "" if limit is None else "LIMIT ?"
        params = () if limit is None else (limit,)
        cursor.execute(f"""
            SELECT
                p.id,
                p.amount,
                p.status,
                p.payment_method,
                p.created_at,
                e.course_id,
                s.name AS student_name,
                s.email AS student_email
            FROM payments p
            JOIN enrollments e ON e.id = p.enrollment_id
            JOIN users s ON s.id = e.user_id
            ORDER BY p.id DESC
            {limite_sql}
        """, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def add_audit_log(
        action: str,
        detail: str = "",
        *,
        role: Optional[str] = None,
        user_id: Optional[int] = None,
        actor_email: Optional[str] = None,
        actor_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id=None,
        changes: Optional[list] = None,
    ) -> int:
        """Registra um evento crítico (Trilhas de auditoria).

        `role` identifica o perfil de funcionário que agiu (ex.: 'admin'); `user_id`,
        a conta de usuário. Sem nenhum dos dois, o evento é marcado como 'system'.
        E8 (D45): `actor_email`/`actor_name` identificam a pessoa, `entity_type`/`entity_id` o
        recurso afetado e `changes` a lista de {"field","before","after"} (gravada como JSON em texto).
        """
        changes_json = None
        if changes is not None:
            changes_json = changes if isinstance(changes, str) else json.dumps(changes, ensure_ascii=False)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO audit_logs
                   (user_id, role, action, detail, actor_email, actor_name, entity_type, entity_id, changes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, role or "system", action, detail, actor_email, actor_name,
                    entity_type, None if entity_id is None else str(entity_id), changes_json,
                )
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # --- Limite de tentativas de login (S2, D79) ------------------------------------------------

    @staticmethod
    def login_bloqueado(chaves: List[Tuple[str, str]], desde: str) -> bool:
        """Há bloqueio ('lock') criado depois de `desde` para alguma das chaves (scope, key)?"""
        if not chaves:
            return False
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            for scope, key in chaves:
                linha = conn.execute(
                    "SELECT 1 FROM login_attempts WHERE scope = ? AND key = ? AND kind = 'lock' AND created_at > ? "
                    "LIMIT 1",
                    (scope, key, desde),
                ).fetchone()
                if linha:
                    return True
            return False
        finally:
            conn.close()

    @staticmethod
    def registrar_falha_de_login(chaves: List[Tuple[str, str, int]], agora: str, desde: str,
                                 descartar_antes_de: str) -> List[Tuple[str, str]]:
        """Grava uma falha para cada chave (scope, key, limite) e, atomicamente, um bloqueio para cada chave que
        chegou ao limite de falhas depois de `desde` e ainda não tem bloqueio vigente. Devolve as chaves
        bloqueadas agora (um evento de auditoria por bloqueio). Linhas anteriores a `descartar_antes_de` saem."""
        novos_bloqueios = []
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM login_attempts WHERE created_at < ?", (descartar_antes_de,))
                for scope, key, limite in chaves:
                    conn.execute(
                        "INSERT INTO login_attempts (scope, key, kind, created_at) VALUES (?, ?, 'fail', ?)",
                        (scope, key, agora),
                    )
                    falhas = conn.execute(
                        "SELECT COUNT(*) FROM login_attempts WHERE scope = ? AND key = ? AND kind = 'fail' "
                        "AND created_at > ?",
                        (scope, key, desde),
                    ).fetchone()[0]
                    if falhas < limite:
                        continue
                    vigente = conn.execute(
                        "SELECT 1 FROM login_attempts WHERE scope = ? AND key = ? AND kind = 'lock' "
                        "AND created_at > ? LIMIT 1",
                        (scope, key, desde),
                    ).fetchone()
                    if vigente:
                        continue
                    conn.execute(
                        "INSERT INTO login_attempts (scope, key, kind, created_at) VALUES (?, ?, 'lock', ?)",
                        (scope, key, agora),
                    )
                    novos_bloqueios.append((scope, key))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return novos_bloqueios

    @staticmethod
    def limpar_falhas_de_login(scope: str, key: str) -> None:
        """Login certo zera as falhas daquela chave (os bloqueios não mudam)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            conn.execute("DELETE FROM login_attempts WHERE scope = ? AND key = ? AND kind = 'fail'", (scope, key))
            conn.commit()
        finally:
            conn.close()

    AUDIT_LIST_DEFAULT_LIMIT = 100
    AUDIT_LIST_MAX_LIMIT = 500

    @staticmethod
    def list_audit_logs(
        limit: int = 100,
        action: Optional[str] = None,
        user_id: Optional[int] = None,
        *,
        q: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        offset: int = 0,
    ) -> List[Dict]:
        """Eventos do mais novo para o mais antigo. `limit` fica entre 1 e 500; `changes` volta como lista.

        U1 (D74): `q` procura na descrição ou no e-mail do responsável (LIKE com escape); `date_from`/`date_to`
        ('AAAA-MM-DD', já validados) são dias de São Paulo, inclusivos; `offset` pula os primeiros eventos.
        """
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = Database.AUDIT_LIST_DEFAULT_LIMIT
        limit = max(1, min(limit, Database.AUDIT_LIST_MAX_LIMIT))
        try:
            offset = max(0, int(offset or 0))
        except (TypeError, ValueError):
            offset = 0

        where, params = [], []
        if action is not None:
            where.append("action = ?")
            params.append(action)
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        if q:
            padrao = "%" + q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            where.append("(detail LIKE ? ESCAPE '!' OR actor_email LIKE ? ESCAPE '!')")
            params.extend([padrao, padrao])
        if date_from:
            where.append("date(created_at, ?) >= ?")
            params.extend([MODIFICADOR_SQLITE_SP, date_from])
        if date_to:
            where.append("date(created_at, ?) <= ?")
            params.extend([MODIFICADOR_SQLITE_SP, date_to])
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""SELECT id, user_id, role, actor_email, actor_name, entity_type, entity_id,
                           action, detail, changes, created_at
                    FROM audit_logs {clause} ORDER BY id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        finally:
            conn.close()

        logs = []
        for row in rows:
            item = dict(row)
            item["changes"] = Database._parse_changes(item["changes"])
            logs.append(item)
        return logs

    @staticmethod
    def _parse_changes(raw) -> list:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def get_enrollment_by_id(enrollment_id: int) -> Optional[Dict]:
        """Matrícula por id (uso interno de funcionário, ex.: estado antes do reembolso)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def add_chat_exchange(user_id: int, user_content: str, assistant_content: str) -> None:
        """Grava as duas linhas de uma troca (aluno e bot) na mesma transação (E5)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            conn.execute(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', ?)",
                (user_id, user_content),
            )
            conn.execute(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'assistant', ?)",
                (user_id, assistant_content),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def list_chat_messages(user_id: int, limit: Optional[int] = None) -> List[Dict]:
        """Mensagens de UMA conta em ordem cronológica crescente. Com limit, as mais recentes.
        O filtro por user_id fica no SQL (E5, IDOR)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            if limit is None:
                rows = conn.execute(
                    "SELECT role, content, created_at FROM chat_messages WHERE user_id = ? ORDER BY id ASC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content, created_at FROM ("
                    "SELECT id, role, content, created_at FROM chat_messages "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                    (user_id, limit),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def list_active_course_ids_for_user(user_id: int) -> List[str]:
        """Ids dos cursos com matrícula 'active' de UMA conta, sem repetição (E5)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            rows = conn.execute(
                "SELECT DISTINCT course_id FROM enrollments WHERE user_id = ? AND status = 'active' "
                "ORDER BY course_id",
                (user_id,),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    # --- Observabilidade de IA (E7, D42) --------------------------------------------------------

    AI_OUTCOMES = ("answered", "unresolved", "input_blocked", "output_blocked", "llm_error")

    @staticmethod
    def add_ai_usage(*, channel: str, user_id: Optional[int], session_hash: Optional[str], call_type: str,
                     model: Optional[str], prompt_tokens: int, completion_tokens: int, total_tokens: int,
                     cost_usd: float, latency_ms: int, status: str) -> int:
        """Uma linha por chamada ao Groq. O custo já vem calculado (preço do momento da chamada)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                """INSERT INTO ai_usage (channel, user_id, session_hash, call_type, model, prompt_tokens,
                                         completion_tokens, total_tokens, cost_usd, latency_ms, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (channel, user_id, session_hash, call_type, model, prompt_tokens, completion_tokens,
                 total_tokens, cost_usd, latency_ms, status),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def add_ai_interaction(*, channel: str, user_id: Optional[int], session_hash: Optional[str],
                           course_id: Optional[str], outcome: str, topic: Optional[str]) -> int:
        """Uma linha por mensagem que chegou ao pipeline. `topic` já vem mascarado (ou None)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                """INSERT INTO ai_interactions (channel, user_id, session_hash, course_id, outcome, topic)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (channel, user_id, session_hash, course_id, outcome, topic),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_ai_interaction_stats() -> Dict:
        """Contagens das interações para o painel de observabilidade (chaves antigas e outcomes)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            outcomes = {outcome: 0 for outcome in Database.AI_OUTCOMES}
            for outcome, total in conn.execute("SELECT outcome, COUNT(*) FROM ai_interactions GROUP BY outcome"):
                outcomes[outcome] = total

            sessoes_anonimas = conn.execute(
                "SELECT COUNT(DISTINCT session_hash) FROM ai_interactions "
                "WHERE channel = 'anonymous' AND session_hash IS NOT NULL"
            ).fetchone()[0]
            alunos = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM ai_interactions WHERE channel = 'student' AND user_id IS NOT NULL"
            ).fetchone()[0]
            por_curso = {
                course_id: total
                for course_id, total in conn.execute(
                    "SELECT course_id, COUNT(*) FROM ai_interactions "
                    "WHERE course_id IS NOT NULL AND outcome != 'input_blocked' "
                    "GROUP BY course_id ORDER BY COUNT(*) DESC, course_id"
                )
            }
            return {
                "total_sessions": sessoes_anonimas + alunos,
                "total_messages": sum(total for outcome, total in outcomes.items() if outcome != "input_blocked"),
                "course_specific_messages": sum(por_curso.values()),
                "unresolved_messages": outcomes["unresolved"],
                "messages_per_course": por_curso,
                "outcomes": outcomes,
            }
        finally:
            conn.close()

    @staticmethod
    def get_ai_usage_totals() -> Dict:
        """Totais de ai_usage. `requests` conta todas as chamadas (inclusive as de erro)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            row = conn.execute(
                """SELECT COUNT(*),
                          COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0),
                          COALESCE(SUM(prompt_tokens), 0),
                          COALESCE(SUM(completion_tokens), 0),
                          COALESCE(SUM(total_tokens), 0),
                          COALESCE(AVG(latency_ms), 0),
                          COALESCE(SUM(cost_usd), 0)
                   FROM ai_usage"""
            ).fetchone()
            return {
                "requests": row[0],
                "errors": row[1],
                "prompt_tokens": row[2],
                "completion_tokens": row[3],
                "total_tokens": row[4],
                "avg_latency_ms": round(row[5], 1),
                "cost_usd": round(row[6], 6),
            }
        finally:
            conn.close()

    @staticmethod
    def get_ai_usage_per_day(days: int = 14) -> List[Dict]:
        """Série diária dos últimos `days` dias consecutivos, terminando hoje, com zeros nos dias vazios.

        F2 (D71): o dia é o de São Paulo (UTC -3 h fixo), tanto no agrupamento quanto no "hoje" da janela.
        """
        hoje = dia_sao_paulo(datetime.now(timezone.utc))
        inicio = hoje - timedelta(days=days - 1)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            por_dia = {
                dia: (requests, cost)
                for dia, requests, cost in conn.execute(
                    "SELECT date(created_at, ?) AS dia, COUNT(*), COALESCE(SUM(cost_usd), 0) FROM ai_usage "
                    "WHERE date(created_at, ?) >= ? AND date(created_at, ?) <= ? GROUP BY dia",
                    (MODIFICADOR_SQLITE_SP, MODIFICADOR_SQLITE_SP, inicio.isoformat(),
                     MODIFICADOR_SQLITE_SP, hoje.isoformat()),
                )
            }
        finally:
            conn.close()
        serie = []
        for deslocamento in range(days):
            dia = (inicio + timedelta(days=deslocamento)).isoformat()
            requests, cost = por_dia.get(dia, (0, 0))
            serie.append({"date": dia, "requests": requests, "cost_usd": round(cost, 6)})
        return serie

    # --- Handoff para o WhatsApp (F6, D77) -----------------------------------------------------

    HANDOFF_REASONS = ("user_request", "llm_failures", "token_budget", "unresolved")

    @staticmethod
    def _filtro_conversa(channel: str, user_id: Optional[int], session_hash: Optional[str]) -> Tuple[str, tuple]:
        """WHERE da conversa (D77): anônimo pela sessão (hash); aluno pelo user_id no dia de São Paulo."""
        if channel == "student":
            return (
                "channel = 'student' AND user_id = ? AND date(created_at, ?) = date('now', ?)",
                (user_id, MODIFICADOR_SQLITE_SP, MODIFICADOR_SQLITE_SP),
            )
        return "channel = 'anonymous' AND session_hash = ?", (session_hash,)

    @staticmethod
    def get_conversation_outcomes(channel: str, user_id: Optional[int], session_hash: Optional[str],
                                  limit: int) -> List[str]:
        """Outcomes das últimas `limit` interações da conversa, da mais recente para a mais antiga."""
        where, params = Database._filtro_conversa(channel, user_id, session_hash)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            rows = conn.execute(
                f"SELECT outcome FROM ai_interactions WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    @staticmethod
    def get_conversation_tokens(channel: str, user_id: Optional[int], session_hash: Optional[str]) -> int:
        """Soma de total_tokens (ai_usage) da conversa."""
        where, params = Database._filtro_conversa(channel, user_id, session_hash)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            return conn.execute(
                f"SELECT COALESCE(SUM(total_tokens), 0) FROM ai_usage WHERE {where}", params
            ).fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def add_ai_handoff(*, channel: str, user_id: Optional[int], session_hash: Optional[str], reason: str,
                       course_id: Optional[str]) -> int:
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                "INSERT INTO ai_handoffs (channel, user_id, session_hash, reason, course_id) VALUES (?, ?, ?, ?, ?)",
                (channel, user_id, session_hash, reason, course_id),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_ai_handoff_stats() -> Dict:
        """`handoff {total, by_reason, rate}` do painel (D77). Conversa: anônimo = session_hash distinto;
        aluno = (user_id, dia de São Paulo) distinto, contadas a partir de ai_interactions. rate em fração 0..1."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            por_motivo = {motivo: 0 for motivo in Database.HANDOFF_REASONS}
            for motivo, total in conn.execute("SELECT reason, COUNT(*) FROM ai_handoffs GROUP BY reason"):
                if motivo in por_motivo:
                    por_motivo[motivo] = total
            chave = (
                "CASE WHEN channel = 'anonymous' THEN 'a:' || session_hash "
                "ELSE 's:' || user_id || ':' || date(created_at, ?) END"
            )
            filtro = (
                "(channel = 'anonymous' AND session_hash IS NOT NULL) "
                "OR (channel = 'student' AND user_id IS NOT NULL)"
            )
            conversas = conn.execute(
                f"SELECT COUNT(DISTINCT {chave}) FROM ai_interactions WHERE {filtro}", (MODIFICADOR_SQLITE_SP,)
            ).fetchone()[0]
            com_handoff = conn.execute(
                f"SELECT COUNT(DISTINCT {chave}) FROM ai_handoffs WHERE {filtro}", (MODIFICADOR_SQLITE_SP,)
            ).fetchone()[0]
            return {
                "total": sum(por_motivo.values()),
                "by_reason": por_motivo,
                "rate": round(min(com_handoff / conversas, 1), 4) if conversas else 0,
            }
        finally:
            conn.close()

    @staticmethod
    def get_ai_conversion() -> Dict:
        """Conversão de atendimento (D42): alunos com >= 1 mensagem no chat autenticado que ganharam uma
        matrícula 'active' com enrolled_at posterior à primeira mensagem, sobre os alunos que conversaram."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            row = conn.execute(
                """WITH primeira AS (
                       SELECT user_id, MIN(created_at) AS primeira_mensagem
                       FROM ai_interactions
                       WHERE channel = 'student' AND user_id IS NOT NULL
                       GROUP BY user_id
                   )
                   SELECT COUNT(*),
                          COALESCE(SUM(CASE WHEN EXISTS (
                              SELECT 1 FROM enrollments e
                              WHERE e.user_id = primeira.user_id AND e.status = 'active'
                                AND e.enrolled_at > primeira.primeira_mensagem
                          ) THEN 1 ELSE 0 END), 0)
                   FROM primeira"""
            ).fetchone()
            return {"students_with_chat": row[0], "converted": row[1]}
        finally:
            conn.close()

    @staticmethod
    def get_ai_unresolved_topics(limit: int = 10) -> List[Dict]:
        """Tópicos mascarados do canal anônimo, agrupados por texto, em ordem decrescente de contagem."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            rows = conn.execute(
                """SELECT topic, COUNT(*) AS total FROM ai_interactions
                   WHERE channel = 'anonymous' AND outcome = 'unresolved' AND topic IS NOT NULL
                   GROUP BY topic ORDER BY total DESC, topic ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [{"topic": topic, "count": total} for topic, total in rows]
        finally:
            conn.close()

    @staticmethod
    def get_students_overview() -> List[Dict]:
        """Students with their enrollment counts and latest status (Dashboard de Alunos)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.id,
                s.email,
                s.name,
                s.created_at,
                s.is_active,
                COUNT(e.id) AS total_enrollments,
                SUM(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END) AS active_enrollments,
                MAX(e.enrolled_at) AS last_enrollment_at,
                (SELECT COUNT(*) FROM chat_messages c
                  WHERE c.user_id = s.id AND c.role = 'user') AS chat_messages,
                (SELECT c.created_at FROM chat_messages c
                  WHERE c.user_id = s.id AND c.role = 'user'
                  ORDER BY c.id DESC LIMIT 1) AS last_chat_at
            FROM users s
            LEFT JOIN enrollments e ON e.user_id = s.id
            WHERE s.role = 'student'
            GROUP BY s.id
            ORDER BY last_enrollment_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [{**dict(row), "is_active": bool(row["is_active"])} for row in rows]

    # --- Turmas (L1, D53) -------------------------------------------------------------------------
    # Contam nos números da turma só as matrículas 'active' e 'pending'; cancelled/refunded mantêm class_id
    # (histórico) mas não contam.

    _SQL_TURMAS = """
        SELECT c.id, c.course_id, c.name, c.starts_on, c.ends_on, c.schedule, c.capacity,
               COALESCE(SUM(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END), 0) AS enrolled,
               COALESCE(SUM(CASE WHEN e.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
               COUNT(e.id) AS total
        FROM classes c
        LEFT JOIN enrollments e ON e.class_id = c.id AND e.status IN ('active', 'pending')
        {where}
        GROUP BY c.id
        ORDER BY c.course_id, (c.starts_on IS NULL), c.starts_on, c.name, c.id
    """

    _CAMPOS_TURMA = ("name", "starts_on", "ends_on", "schedule", "capacity")

    @staticmethod
    def _id_sqlite_valido(valor) -> bool:
        """Inteiro que cabe no INTEGER do SQLite (ids enormes vindos da URL não devem virar 500)."""
        return isinstance(valor, int) and -(2 ** 63) <= valor < 2 ** 63

    @staticmethod
    def list_classes(course_id: Optional[str] = None) -> List[Dict]:
        """Turmas com contagens (enrolled=active, pending, total), por curso e depois por data e nome."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            if course_id is None:
                rows = conn.execute(Database._SQL_TURMAS.format(where="")).fetchall()
            else:
                rows = conn.execute(
                    Database._SQL_TURMAS.format(where="WHERE c.course_id = ?"), (course_id,)
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def get_class(class_id: int) -> Optional[Dict]:
        """Uma turma com contagens, ou None."""
        if not Database._id_sqlite_valido(class_id):
            return None
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                Database._SQL_TURMAS.format(where="WHERE c.id = ?"), (class_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_unassigned_counts() -> Dict[str, Dict]:
        """Por curso: matrículas pending/active sem turma ({"total", "active", "pending"})."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            rows = conn.execute(
                """SELECT course_id,
                          SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)
                   FROM enrollments
                   WHERE class_id IS NULL AND status IN ('active', 'pending')
                   GROUP BY course_id"""
            ).fetchall()
            return {
                course_id: {"total": (ativas or 0) + (pendentes or 0), "active": ativas or 0, "pending": pendentes or 0}
                for course_id, ativas, pendentes in rows
            }
        finally:
            conn.close()

    @staticmethod
    def create_class(course_id: str, name: str, starts_on: Optional[str], capacity: Optional[int],
                     ends_on: Optional[str] = None, schedule: Optional[str] = None) -> Optional[int]:
        """Cria a turma. None se o par (curso, nome) já existe. `ends_on` e `schedule` (U8, D83) são opcionais."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                "INSERT INTO classes (course_id, name, starts_on, ends_on, schedule, capacity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (course_id, name, starts_on, ends_on, schedule, capacity),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    @staticmethod
    def update_class(class_id: int, changes: Dict) -> Dict:
        """Atualização parcial atômica (BEGIN IMMEDIATE). `changes` tem só os campos enviados
        (name, starts_on, ends_on, schedule, capacity; None limpa todos menos name).

        `outcome`: not_found | duplicate_name | ends_before_start | capacity_below_total | updated. Em `updated`
        devolve `before` e `after` (name, starts_on, ends_on, schedule, capacity); nada é gravado nos demais casos.
        Término e início são comparados com o par final (enviado ou o do banco), U8 (D83).
        """
        if not Database._id_sqlite_valido(class_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            atual = conn.execute(
                "SELECT id, course_id, name, starts_on, ends_on, schedule, capacity FROM classes WHERE id = ?",
                (class_id,),
            ).fetchone()
            if atual is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            before = {campo: atual[campo] for campo in Database._CAMPOS_TURMA}
            after = {**before, **changes}

            if (after["starts_on"] is not None and after["ends_on"] is not None
                    and after["ends_on"] < after["starts_on"]):
                conn.execute("ROLLBACK")
                return {"outcome": "ends_before_start"}

            if after["name"] != before["name"]:
                repetido = conn.execute(
                    "SELECT 1 FROM classes WHERE course_id = ? AND name = ? AND id != ?",
                    (atual["course_id"], after["name"], class_id),
                ).fetchone()
                if repetido is not None:
                    conn.execute("ROLLBACK")
                    return {"outcome": "duplicate_name"}
            if "capacity" in changes and after["capacity"] is not None:
                total = conn.execute(
                    "SELECT COUNT(*) FROM enrollments WHERE class_id = ? AND status IN ('active', 'pending')",
                    (class_id,),
                ).fetchone()[0]
                if after["capacity"] < total:
                    conn.execute("ROLLBACK")
                    return {"outcome": "capacity_below_total"}

            conn.execute(
                "UPDATE classes SET name = ?, starts_on = ?, ends_on = ?, schedule = ?, capacity = ? WHERE id = ?",
                (after["name"], after["starts_on"], after["ends_on"], after["schedule"], after["capacity"], class_id),
            )
            conn.execute("COMMIT")
            return {"outcome": "updated", "course_id": atual["course_id"], "before": before, "after": after}
        except sqlite3.IntegrityError:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            return {"outcome": "duplicate_name"}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def delete_class(class_id: int) -> Dict:
        """Remove a turma, atômico. `outcome`: not_found | has_enrollments (qualquer status, histórico) | deleted.
        Em `deleted` devolve `before` (name, starts_on, ends_on, schedule, capacity)."""
        if not Database._id_sqlite_valido(class_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            atual = conn.execute(
                "SELECT course_id, name, starts_on, ends_on, schedule, capacity FROM classes WHERE id = ?", (class_id,)
            ).fetchone()
            if atual is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            if conn.execute("SELECT 1 FROM enrollments WHERE class_id = ? LIMIT 1", (class_id,)).fetchone():
                conn.execute("ROLLBACK")
                return {"outcome": "has_enrollments"}
            conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
            conn.execute("COMMIT")
            return {"outcome": "deleted", "course_id": atual["course_id"],
                    "before": {campo: atual[campo] for campo in Database._CAMPOS_TURMA}}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def excluir_curso_sem_matriculas(course_id: str, remover_arquivo) -> Dict:
        """Exclusão de curso (F1, D68), atômica. `outcome`: has_enrollments (qualquer status) | deleted.

        Com o lock de escrita (BEGIN IMMEDIATE) aberto: confere que não há matrícula do curso, remove as
        turmas dele e chama `remover_arquivo()` (apaga o JSON). Um checkout concorrente espera o lock, então
        nenhuma matrícula nasce entre a conferência e a remoção. Se apagar o arquivo falhar, nada muda no banco.
        """
        conn = Database._abrir_transacao_imediata()
        try:
            if conn.execute("SELECT 1 FROM enrollments WHERE course_id = ? LIMIT 1", (course_id,)).fetchone():
                conn.execute("ROLLBACK")
                return {"outcome": "has_enrollments"}
            removidas = conn.execute("DELETE FROM classes WHERE course_id = ?", (course_id,)).rowcount
            remover_arquivo()
            conn.execute("COMMIT")
            return {"outcome": "deleted", "classes_removed": removidas}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def count_enrollments_by_course() -> Dict[str, int]:
        """Total de matrículas (todos os status) por curso (F1: `enrollments_count` da lista da Gestão)."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            rows = conn.execute("SELECT course_id, COUNT(*) FROM enrollments GROUP BY course_id").fetchall()
            return {course_id: int(total) for course_id, total in rows}
        finally:
            conn.close()

    @staticmethod
    def list_enrollments_for_course(course_id: str) -> List[Dict]:
        """Matrículas de um curso para a Gestão/Suporte. Sem dados de pagamento nem de conta além de nome e e-mail."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT e.id, u.name AS student_name, u.email AS student_email,
                          e.status, e.class_id, e.enrolled_at
                   FROM enrollments e JOIN users u ON u.id = e.user_id
                   WHERE e.course_id = ?
                   ORDER BY e.id""",
                (course_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --- Detalhe do aluno e alunos do curso (F3/F4, D73) -------------------------------------------

    @staticmethod
    def get_student_detail(user_id: int) -> Optional[Dict]:
        """Conta de aluno com matrículas (e turma), pagamentos e resumo do chat. None se o id não for de aluno
        (inexistente, funcionário ou fora do INTEGER do SQLite). Sem hash de senha."""
        if not Database._id_sqlite_valido(user_id):
            return None
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            aluno = conn.execute(
                """SELECT u.id, u.name, u.email, u.created_at, u.is_active,
                          (SELECT COUNT(*) FROM chat_messages c
                            WHERE c.user_id = u.id AND c.role = 'user') AS chat_messages,
                          (SELECT c.created_at FROM chat_messages c
                            WHERE c.user_id = u.id AND c.role = 'user'
                            ORDER BY c.id DESC LIMIT 1) AS last_chat_at
                   FROM users u WHERE u.id = ? AND u.role = 'student'""",
                (user_id,),
            ).fetchone()
            if aluno is None:
                return None
            matriculas = conn.execute(
                """SELECT e.id AS enrollment_id, e.course_id, e.class_id, c.name AS class_name,
                          c.starts_on AS class_starts_on, c.ends_on AS class_ends_on,
                          c.schedule AS class_schedule, e.status, e.enrolled_at
                   FROM enrollments e LEFT JOIN classes c ON c.id = e.class_id
                   WHERE e.user_id = ?
                   ORDER BY e.enrolled_at DESC, e.id DESC""",
                (user_id,),
            ).fetchall()
            pagamentos = conn.execute(
                """SELECT p.id AS payment_id, p.enrollment_id, e.course_id, p.status, p.created_at, p.amount
                   FROM payments p JOIN enrollments e ON e.id = p.enrollment_id
                   WHERE e.user_id = ?
                   ORDER BY p.created_at DESC, p.id DESC""",
                (user_id,),
            ).fetchall()
            return {
                "student": dict(aluno),
                "enrollments": [dict(row) for row in matriculas],
                "payments": [dict(row) for row in pagamentos],
            }
        finally:
            conn.close()

    @staticmethod
    def list_students_of_course(course_id: str, status: Optional[str] = None, class_id=None,
                                sem_turma: bool = False) -> List[Dict]:
        """Matrículas de um curso com aluno, turma e o último pagamento da matrícula (status e valor).
        Filtros opcionais: status; turma (class_id) ou sem turma. Mais recente primeiro."""
        where = ["e.course_id = ?"]
        params: list = [course_id]
        if status is not None:
            where.append("e.status = ?")
            params.append(status)
        if sem_turma:
            where.append("e.class_id IS NULL")
        elif class_id is not None:
            if not Database._id_sqlite_valido(class_id):
                return []
            where.append("e.class_id = ?")
            params.append(class_id)
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""SELECT u.id AS user_id, u.name, u.email, e.id AS enrollment_id, e.status, e.enrolled_at,
                           e.class_id, c.name AS class_name,
                           p.status AS payment_status, p.amount
                    FROM enrollments e
                    JOIN users u ON u.id = e.user_id
                    LEFT JOIN classes c ON c.id = e.class_id
                    LEFT JOIN payments p ON p.id = (
                        SELECT MAX(p2.id) FROM payments p2 WHERE p2.enrollment_id = e.id)
                    WHERE {" AND ".join(where)}
                    ORDER BY e.enrolled_at DESC, e.id DESC""",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def assign_enrollment_class(enrollment_id: int, class_id: Optional[int]) -> Dict:
        """Atribui a matrícula a uma turma (ou remove com None). Atômico (BEGIN IMMEDIATE): a checagem de
        capacidade e a gravação acontecem na mesma transação, então duas atribuições simultâneas não
        estouram a última vaga.

        `outcome`: enrollment_not_found | class_not_found | other_course | invalid_status | full |
        unchanged (já estava assim, sem alteração) | changed. Em unchanged/changed devolve `before_class` e
        `after_class` ({id, name} ou None) e `course_id`.
        """
        if not Database._id_sqlite_valido(enrollment_id):
            return {"outcome": "enrollment_not_found"}
        if class_id is not None and not Database._id_sqlite_valido(class_id):
            return {"outcome": "class_not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            matricula = conn.execute(
                "SELECT id, course_id, status, class_id FROM enrollments WHERE id = ?", (enrollment_id,)
            ).fetchone()
            if matricula is None:
                conn.execute("ROLLBACK")
                return {"outcome": "enrollment_not_found"}

            def turma_ref(turma_id):
                if turma_id is None:
                    return None
                linha = conn.execute("SELECT id, name FROM classes WHERE id = ?", (turma_id,)).fetchone()
                return {"id": turma_id, "name": linha["name"] if linha else None}

            before_class = turma_ref(matricula["class_id"])
            base = {"course_id": matricula["course_id"], "before_class": before_class}

            if class_id is None:
                if matricula["class_id"] is None:
                    conn.execute("ROLLBACK")
                    return {"outcome": "unchanged", **base, "after_class": None}
                conn.execute("UPDATE enrollments SET class_id = NULL WHERE id = ?", (enrollment_id,))
                conn.execute("COMMIT")
                return {"outcome": "changed", **base, "after_class": None}

            turma = conn.execute(
                "SELECT id, course_id, name, capacity FROM classes WHERE id = ?", (class_id,)
            ).fetchone()
            if turma is None:
                conn.execute("ROLLBACK")
                return {"outcome": "class_not_found"}
            if turma["course_id"] != matricula["course_id"]:
                conn.execute("ROLLBACK")
                return {"outcome": "other_course"}
            if matricula["status"] not in ("pending", "active"):
                conn.execute("ROLLBACK")
                return {"outcome": "invalid_status"}
            after_class = {"id": turma["id"], "name": turma["name"]}
            if matricula["class_id"] == class_id:
                conn.execute("ROLLBACK")
                return {"outcome": "unchanged", **base, "after_class": after_class}
            if turma["capacity"] is not None:
                ocupadas = conn.execute(
                    "SELECT COUNT(*) FROM enrollments "
                    "WHERE class_id = ? AND status IN ('active', 'pending') AND id != ?",
                    (class_id, enrollment_id),
                ).fetchone()[0]
                if ocupadas >= turma["capacity"]:
                    conn.execute("ROLLBACK")
                    return {"outcome": "full"}
            conn.execute("UPDATE enrollments SET class_id = ? WHERE id = ?", (class_id, enrollment_id))
            conn.execute("COMMIT")
            return {"outcome": "changed", **base, "after_class": after_class}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def get_courses_overview() -> List[Dict]:
        """Enrollment counts and conversion per course (Dashboard de Cursos)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                e.course_id,
                COUNT(e.id) AS total_enrollments,
                SUM(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END) AS approved_enrollments,
                SUM(CASE WHEN e.status = 'pending' THEN 1 ELSE 0 END) AS pending_enrollments
            FROM enrollments e
            GROUP BY e.course_id
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_financial_summary() -> Dict:
        """Revenue totals by payment status (Dashboard Financeiro do admin.html)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, COUNT(*) AS total, COALESCE(SUM(amount), 0) AS amount
            FROM payments
            GROUP BY status
        """)
        by_status = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT
                strftime('%Y-%m', created_at) AS month,
                COALESCE(SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END), 0) AS revenue
            FROM payments
            GROUP BY month
            ORDER BY month DESC
            LIMIT 6
        """)
        by_month = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {"by_status": by_status, "by_month": by_month}

# Initialize database on import
Database.init_db()
