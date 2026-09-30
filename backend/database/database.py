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


def migrate_submissions_to_blob(connection):
    """
    Migration automatique de l'ancien stockage disque
    vers le stockage SQLite BLOB.

    Ancien :
        submissions.file_path

    Nouveau :
        submissions.content_type
        submissions.file_data
    """
    cursor = connection.cursor()

    cursor.execute(
        "PRAGMA table_info(submissions)"
    )

    columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    if not columns:
        return

    # Déjà entièrement migré.
    if (
        "file_data" in columns
        and "content_type" in columns
        and "file_path" not in columns
    ):
        return

    cursor.execute("""
        SELECT *
        FROM submissions
        ORDER BY id ASC
    """)

    rows = cursor.fetchall()

    migrated_rows = []

    for row in rows:
        keys = row.keys()

        file_data = None

        if "file_data" in keys:
            file_data = row["file_data"]

        content_type = "application/zip"

        if (
            "content_type" in keys
            and row["content_type"]
        ):
            content_type = str(
                row["content_type"]
            )

        # Ancien stockage sur disque.
        if file_data is None:
            legacy_file_path = ""

            if "file_path" in keys:
                legacy_file_path = str(
                    row["file_path"] or ""
                ).strip()

            if not legacy_file_path:
                raise RuntimeError(
                    "Migration impossible pour "
                    f"{row['filename']} : "
                    "aucun contenu BLOB et aucun chemin."
                )

            legacy_path = Path(
                legacy_file_path
            )

            if not legacy_path.is_absolute():
                legacy_path = (
                    BACKEND_DIR
                    / legacy_path
                )

            if not legacy_path.is_file():
                raise RuntimeError(
                    "Migration impossible : "
                    f"fichier absent pour "
                    f"{row['filename']} : "
                    f"{legacy_path}"
                )

            file_data = (
                legacy_path.read_bytes()
            )

        file_data = bytes(file_data)

        if not file_data:
            raise RuntimeError(
                "Migration impossible : "
                f"{row['filename']} est vide."
            )

        migrated_rows.append((
            row["id"],
            row["exam_id"],
            row["student_id"],
            row["machine_id"],
            row["filename"],
            round(
                len(file_data) / 1024,
                2
            ),
            content_type,
            sqlite3.Binary(file_data),
            row["created_at"]
        ))

    cursor.execute("""
        DROP TABLE IF EXISTS
        submissions_blob_migration
    """)

    cursor.execute("""
        CREATE TABLE
        submissions_blob_migration (
            id INTEGER
                PRIMARY KEY AUTOINCREMENT,

            exam_id TEXT NOT NULL,

            student_id TEXT NOT NULL,

            machine_id TEXT NOT NULL,

            filename TEXT
                NOT NULL UNIQUE,

            size_kb REAL NOT NULL,

            content_type TEXT
                NOT NULL
                DEFAULT 'application/zip',

            file_data BLOB NOT NULL,

            created_at TEXT NOT NULL
        )
    """)

    if migrated_rows:
        cursor.executemany("""
            INSERT INTO
            submissions_blob_migration (
                id,
                exam_id,
                student_id,
                machine_id,
                filename,
                size_kb,
                content_type,
                file_data,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, migrated_rows)

    cursor.execute("""
        DROP TABLE submissions
    """)

    cursor.execute("""
        ALTER TABLE
        submissions_blob_migration
        RENAME TO submissions
    """)

    connection.commit()


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
            size_kb REAL NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'application/zip',
            file_data BLOB NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    migrate_submissions_to_blob(connection)

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