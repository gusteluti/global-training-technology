import sqlite3
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

    @staticmethod
    def update_payment_status(payment_id: int, status: str, transaction_id: Optional[str] = None):
        """Update payment status"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """UPDATE payments SET status = ?, transaction_id = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, transaction_id, payment_id)
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
            """UPDATE payments SET status = ?, transaction_id = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, transaction_id, row[0])
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
    def add_audit_log(action: str, detail: str = "", *, role: Optional[str] = None, user_id: Optional[int] = None) -> int:
        """Registra um evento crítico (Trilhas de auditoria).

        `role` identifica o perfil de funcionário que agiu (ex.: 'admin'); `user_id`,
        a conta de usuário. Sem nenhum dos dois, o evento é marcado como 'system'.
        """
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, role, action, detail) VALUES (?, ?, ?, ?)",
            (user_id, role or "system", action, detail)
        )
        conn.commit()
        log_id = cursor.lastrowid
        conn.close()
        return log_id

    @staticmethod
    def list_audit_logs(limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, role, action, detail, created_at FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

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
                MAX(e.enrolled_at) AS last_enrollment_at
            FROM users s
            LEFT JOIN enrollments e ON e.user_id = s.id
            WHERE s.role = 'student'
            GROUP BY s.id
            ORDER BY last_enrollment_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

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
