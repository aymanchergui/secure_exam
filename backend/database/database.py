import sqlite3
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

DATABASE_FILE = DATABASE_DIR / "secure_exam.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            school TEXT NOT NULL,
            photo_path TEXT,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            email_sent INTEGER NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            packages TEXT NOT NULL,
            sudo INTEGER NOT NULL,
            internet INTEGER NOT NULL,
            educ_access INTEGER NOT NULL,
            allowed_domains TEXT NOT NULL,
            workspace TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(exam_id, student_id, machine_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            filename TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            size_kb REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machine_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            step TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(exam_id, student_id, machine_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machine_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            step TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_exam_configs_identity
        ON exam_configs(exam_id, student_id, machine_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_identity
        ON submissions(exam_id, student_id, machine_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_machine_status_identity
        ON machine_status(exam_id, student_id, machine_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_machine_status_history_identity
        ON machine_status_history(exam_id, student_id, machine_id)
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO teacher_profile (
            id,
            full_name,
            email,
            role,
            department,
            school,
            photo_path,
            updated_at
        )
        VALUES (
            1,
            'Professeur ISEN',
            'prof@isen.fr',
            'Enseignant',
            'Informatique / Systèmes Linux',
            'ISEN SecureExam',
            NULL,
            ?
        )
    """, (
        datetime.now().isoformat(timespec="seconds"),
    ))

    connection.commit()
    connection.close()