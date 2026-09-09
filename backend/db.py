import sqlite3
from pathlib import Path
from typing import Optional

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
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)
        
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
        
        # Users table (students and staff)
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

        # Audit logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        conn.commit()
        conn.close()
        print("✓ Database initialized")
    
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
    def add_audit_log(user_id: Optional[int], action: str, details: Optional[str] = None) -> int:
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()
        log_id = cursor.lastrowid
        conn.close()
        return log_id

    @staticmethod
    def get_audit_logs(limit: int = 100):
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, action, details, created_at FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {"id": r[0], "user_id": r[1], "action": r[2], "details": r[3], "created_at": r[4]} for r in rows
        ]

    @staticmethod
    def get_financial_summary():
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'completed'")
        total = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        conn.close()
        return {"total_revenue": total, "pending_payments": pending}

    @staticmethod
    def get_student_metrics():
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM enrollments WHERE status = 'active'")
        active_enrollments = cursor.fetchone()[0]
        conn.close()
        return {"total_students": total_students, "active_enrollments": active_enrollments}

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
    def create_enrollment(student_id: int, course_id: str) -> int:
        """Create an enrollment"""
        conn = sqlite3.connect(Database.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO enrollments (student_id, course_id) VALUES (?, ?)",
            (student_id, course_id)
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

# Initialize database on import
Database.init_db()
