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
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'teacher',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

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
        CREATE TABLE IF NOT EXISTS package_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_teachers_username
        ON teachers(username)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_package_catalog_name
        ON package_catalog(name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_package_catalog_active
        ON package_catalog(is_active)
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

    current_time = datetime.now().isoformat(timespec="seconds")

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
        current_time,
    ))

    default_packages = [
        (
            "python3",
            "Python 3",
            "Interpréteur Python 3 pour les exercices de programmation."
        ),
        (
            "gcc",
            "GCC",
            "Compilateur C/C++ utilisé pour les examens de programmation système."
        ),
        (
            "gdb",
            "GDB",
            "Débogueur GNU pour analyser et corriger les programmes."
        ),
        (
            "make",
            "Make",
            "Outil d'automatisation de compilation via Makefile."
        ),
        (
            "vim",
            "Vim",
            "Éditeur de texte avancé en terminal."
        ),
        (
            "nano",
            "Nano",
            "Éditeur de texte simple en terminal."
        )
    ]

    for package in default_packages:
        cursor.execute("""
            INSERT OR IGNORE INTO package_catalog (
                name,
                display_name,
                description,
                is_active,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            package[0],
            package[1],
            package[2],
            1,
            current_time,
            current_time
        ))

    connection.commit()
    connection.close()