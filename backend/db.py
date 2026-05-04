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
