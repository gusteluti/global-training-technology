import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

class Database:
    """SQLite database for storing enrollments and payments"""
    
    DB_PATH = Path(__file__).parent / "db.sqlite"
    
    @staticmethod
    def init_db():
        """Initialize database tables"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        
        # Students table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Enrollments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                external_reference TEXT,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)
        Database._ensure_column(cursor, "enrollments", "external_reference", "TEXT")

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

        # Audit logs table (Fase 2 - Trilhas de Auditoria / Governança)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        print("✓ Database initialized")

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
        """Adds a column to an existing table if it isn't there yet (lightweight migration)."""
        existing_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    
    @staticmethod
    def add_student(email: str, name: str) -> Optional[int]:
        """Add a new student"""
        try:
            conn = sqlite3.connect(Database.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO students (email, name) VALUES (?, ?)",
                (email, name)
            )
            
            conn.commit()
            student_id = cursor.lastrowid
            conn.close()
            return student_id
        except sqlite3.IntegrityError:
            # Student already exists
            return None
    
    @staticmethod
    def get_or_create_student(email: str, name: str) -> int:
        """Return the existing student id for this email, creating it if needed."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM students WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            student_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO students (email, name) VALUES (?, ?)",
                (email, name)
            )
            conn.commit()
            student_id = cursor.lastrowid

        conn.close()
        return student_id

    @staticmethod
    def create_enrollment(student_id: int, course_id: str, external_reference: Optional[str] = None) -> int:
        """Create an enrollment"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO enrollments (student_id, course_id, external_reference) VALUES (?, ?, ?)",
            (student_id, course_id, external_reference)
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
        # Keep the enrollment status mirrored to the payment status for the dashboards.
        cursor.execute(
            "UPDATE enrollments SET status = ? WHERE external_reference = ?",
            (status, external_reference)
        )

        conn.commit()
        conn.close()
        return True

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
            JOIN students s ON s.id = e.student_id
            ORDER BY p.id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def add_audit_log(role: str, action: str, detail: str = ""):
        """Record a critical event performed in the employee area (Fase 2 - Audit Logs)."""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (role, action, detail) VALUES (?, ?, ?)",
            (role, action, detail)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def list_audit_logs(limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(Database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
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
                SUM(CASE WHEN e.status IN ('approved', 'active') THEN 1 ELSE 0 END) AS active_enrollments,
                MAX(e.enrolled_at) AS last_enrollment_at
            FROM students s
            LEFT JOIN enrollments e ON e.student_id = s.id
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
                SUM(CASE WHEN e.status = 'approved' THEN 1 ELSE 0 END) AS approved_enrollments,
                SUM(CASE WHEN e.status = 'pending' THEN 1 ELSE 0 END) AS pending_enrollments
            FROM enrollments e
            GROUP BY e.course_id
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_financial_summary() -> Dict:
        """Revenue totals by payment status (Dashboard Financeiro)."""
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
