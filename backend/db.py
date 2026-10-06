import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_class ON enrollments (class_id)")

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
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

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
        cursor.execute("SELECT id, email, name, password_hash, role, created_at FROM users WHERE email = ?", (email,))
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
            "created_at": row[5]
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
    def insert_password_setup_token(user_id: int, token_hash: str, expires_at: str) -> int:
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id, token_hash, expires_at),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_password_setup_token(token_hash: str) -> Optional[dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, user_id, expires_at, used_at FROM password_setup_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def definir_senha_com_token(token_id: int, user_id: int, password_hash: str) -> bool:
        """Marca o token como usado e grava a senha da conta dona dele, numa só transação.

        Recusa (False, sem alterar nada) se o token já foi usado ou se a conta já tem senha.
        """
        conn = sqlite3.connect(Database.DB_PATH, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                marcou = conn.execute(
                    "UPDATE password_setup_tokens SET used_at = CURRENT_TIMESTAMP "
                    "WHERE id = ? AND used_at IS NULL",
                    (token_id,),
                ).rowcount == 1
                definiu = marcou and conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash IS NULL",
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
    def reembolsar_pagamento_se_aprovado(payment_id: int) -> Dict:
        """Reembolso atômico: só `approved` vira `refunded` (pagamento e matrícula, mesma transação).

        `outcome`: not_found | refunded (alterou agora) | already_refunded | not_approved.
        Dois reembolsos simultâneos: um devolve `refunded`, os outros `already_refunded`.
        """
        conn = Database._abrir_transacao_imediata()
        try:
            pagamento = conn.execute(
                "SELECT id, enrollment_id, amount, status FROM payments WHERE id = ?", (payment_id,)
            ).fetchone()
            if pagamento is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            base = {
                "payment_id": pagamento["id"],
                "amount": pagamento["amount"],
                "payment_status_before": pagamento["status"],
                "enrollment_status_before": None,
            }
            if pagamento["status"] == "refunded":
                conn.execute("ROLLBACK")
                return {"outcome": "already_refunded", **base}
            if pagamento["status"] != "approved":
                conn.execute("ROLLBACK")
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
                conn.execute("ROLLBACK")
                return {"outcome": "already_refunded", **base}
            conn.execute(
                "UPDATE enrollments SET status = 'refunded' WHERE id = ?", (pagamento["enrollment_id"],)
            )
            conn.execute("COMMIT")
            return {"outcome": "refunded", **base}
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
                "SELECT id, course_id, status, enrolled_at FROM enrollments WHERE user_id = ? ORDER BY id DESC",
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
                "SELECT id, course_id, status, enrolled_at FROM enrollments WHERE id = ? AND user_id = ?",
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
    def get_payments_overview(limit: int = 50) -> List[Dict]:
        """Individual payments with student/course context (Dashboard Financeiro)."""
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
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
            LIMIT ?
        """, (limit,))
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

    AUDIT_LIST_DEFAULT_LIMIT = 100
    AUDIT_LIST_MAX_LIMIT = 500

    @staticmethod
    def list_audit_logs(limit: int = 100, action: Optional[str] = None, user_id: Optional[int] = None) -> List[Dict]:
        """Eventos do mais novo para o mais antigo. `limit` fica entre 1 e 500; `changes` volta como lista."""
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = Database.AUDIT_LIST_DEFAULT_LIMIT
        limit = max(1, min(limit, Database.AUDIT_LIST_MAX_LIMIT))

        where, params = [], []
        if action is not None:
            where.append("action = ?")
            params.append(action)
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""SELECT id, user_id, role, actor_email, actor_name, entity_type, entity_id,
                           action, detail, changes, created_at
                    FROM audit_logs {clause} ORDER BY id DESC LIMIT ?""",
                (*params, limit),
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
        """Série diária (UTC) dos últimos `days` dias consecutivos, terminando hoje, com zeros nos dias vazios."""
        hoje = datetime.now(timezone.utc).date()
        inicio = hoje - timedelta(days=days - 1)
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            por_dia = {
                dia: (requests, cost)
                for dia, requests, cost in conn.execute(
                    "SELECT date(created_at), COUNT(*), COALESCE(SUM(cost_usd), 0) FROM ai_usage "
                    "WHERE date(created_at) >= ? AND date(created_at) <= ? GROUP BY date(created_at)",
                    (inicio.isoformat(), hoje.isoformat()),
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
        return [dict(row) for row in rows]

    # --- Turmas (L1, D53) -------------------------------------------------------------------------
    # Contam nos números da turma só as matrículas 'active' e 'pending'; cancelled/refunded mantêm class_id
    # (histórico) mas não contam.

    _SQL_TURMAS = """
        SELECT c.id, c.course_id, c.name, c.starts_on, c.capacity,
               COALESCE(SUM(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END), 0) AS enrolled,
               COALESCE(SUM(CASE WHEN e.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
               COUNT(e.id) AS total
        FROM classes c
        LEFT JOIN enrollments e ON e.class_id = c.id AND e.status IN ('active', 'pending')
        {where}
        GROUP BY c.id
        ORDER BY c.course_id, (c.starts_on IS NULL), c.starts_on, c.name, c.id
    """

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
    def create_class(course_id: str, name: str, starts_on: Optional[str], capacity: Optional[int]) -> Optional[int]:
        """Cria a turma. None se o par (curso, nome) já existe."""
        conn = sqlite3.connect(Database.DB_PATH)
        try:
            cursor = conn.execute(
                "INSERT INTO classes (course_id, name, starts_on, capacity) VALUES (?, ?, ?, ?)",
                (course_id, name, starts_on, capacity),
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
        (name, starts_on, capacity; None limpa starts_on e capacity).

        `outcome`: not_found | duplicate_name | capacity_below_total | updated. Em `updated` devolve
        `before` e `after` (name, starts_on, capacity); nada é gravado nos demais casos.
        """
        if not Database._id_sqlite_valido(class_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            atual = conn.execute(
                "SELECT id, course_id, name, starts_on, capacity FROM classes WHERE id = ?", (class_id,)
            ).fetchone()
            if atual is None:
                conn.execute("ROLLBACK")
                return {"outcome": "not_found"}
            before = {campo: atual[campo] for campo in ("name", "starts_on", "capacity")}
            after = {**before, **changes}

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
                "UPDATE classes SET name = ?, starts_on = ?, capacity = ? WHERE id = ?",
                (after["name"], after["starts_on"], after["capacity"], class_id),
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
        Em `deleted` devolve `before` (name, starts_on, capacity)."""
        if not Database._id_sqlite_valido(class_id):
            return {"outcome": "not_found"}
        conn = Database._abrir_transacao_imediata()
        try:
            atual = conn.execute(
                "SELECT course_id, name, starts_on, capacity FROM classes WHERE id = ?", (class_id,)
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
                    "before": {campo: atual[campo] for campo in ("name", "starts_on", "capacity")}}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
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
