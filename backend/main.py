import json
import os
import re
import shutil
import subprocess
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import List

import jwt
from dotenv import load_dotenv
from database.database import init_database, get_connection
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel


load_dotenv()

app = FastAPI(title="Plateforme Linux d'examen")
init_database()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://192.168.231.128:4200"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

SUBMISSION_DIR = BASE_DIR / "submissions"
SUBMISSION_DIR.mkdir(exist_ok=True)

PROFILE_DIR = BASE_DIR / "profile"
PROFILE_DIR.mkdir(exist_ok=True)

NIXOS_CONFIG_FILE = PROJECT_DIR / "exam-client" / "var" / "generated" / "exam-configuration.nix"


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}"
        )

    return value


SECRET_KEY = get_required_env("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120")
)

TEACHER_USERNAME = get_required_env("TEACHER_USERNAME")
TEACHER_PASSWORD = get_required_env("TEACHER_PASSWORD")


password_hash = PasswordHash.recommended()
security = HTTPBearer()


class ExamConfig(BaseModel):
    exam_id: str
    student_id: str
    machine_id: str
    packages: List[str]
    sudo: bool
    internet: bool
    educ_access: bool
    allowed_domains: List[str]
    workspace: str


class MachineStatus(BaseModel):
    exam_id: str
    student_id: str
    machine_id: str
    step: str
    status: str
    message: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class SupportRequest(BaseModel):
    fullName: str
    email: str
    subject: str
    message: str


class TeacherProfile(BaseModel):
    fullName: str
    email: str
    role: str
    department: str
    school: str


class PackageCreate(BaseModel):
    name: str
    description: str
    displayName: str | None = None
    nixName: str | None = None
    description: str
    displayName: str | None = None
    nixName: str | None = None


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_backend_file_path(file_path: str) -> Path:
    path = Path(file_path)

    if path.is_absolute():
        return path

    return BASE_DIR / path


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_teacher_by_username(username: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            username,
            password_hash,
            role,
            is_active
        FROM teachers
        WHERE username = ?
    """, (
        username,
    ))

    teacher = cursor.fetchone()
    connection.close()

    return teacher


def teacher_row_to_public_dict(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "isActive": bool(row["is_active"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"]
    }


def package_row_to_public_dict(row):
    row_keys = row.keys()
    nix_name = row["name"]

    if "nix_name" in row_keys and row["nix_name"]:
        nix_name = row["nix_name"]

    return {
        "id": row["id"],
        "name": row["name"],
        "nixName": nix_name,
        "displayName": row["display_name"],
        "description": row["description"],
        "isActive": bool(row["is_active"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"]
    }


def get_active_package_names() -> set[str]:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM package_catalog
        WHERE is_active = 1
    """)

    rows = cursor.fetchall()
    connection.close()

    return {
        row["name"]
        for row in rows
    }


def seed_default_teacher_account():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            password_hash
        FROM teachers
        WHERE username = ?
    """, (
        TEACHER_USERNAME,
    ))

    existing_teacher = cursor.fetchone()
    current_time = now_iso()

    if existing_teacher is None:
        cursor.execute("""
            INSERT INTO teachers (
                username,
                password_hash,
                role,
                is_active,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            TEACHER_USERNAME,
            password_hash.hash(TEACHER_PASSWORD),
            "teacher",
            1,
            current_time,
            current_time
        ))
    else:
        try:
            password_is_current = verify_password(
                TEACHER_PASSWORD,
                existing_teacher["password_hash"]
            )
        except Exception:
            password_is_current = False

        if not password_is_current:
            cursor.execute("""
                UPDATE teachers
                SET
                    password_hash = ?,
                    role = ?,
                    is_active = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                password_hash.hash(TEACHER_PASSWORD),
                "teacher",
                1,
                current_time,
                existing_teacher["id"]
            ))

    connection.commit()
    connection.close()


def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt


def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("sub")
        role = payload.get("role")

        if username is None or role is None:
            raise HTTPException(
                status_code=401,
                detail="Token invalide"
            )

        teacher = get_teacher_by_username(username)

        if teacher is None:
            raise HTTPException(
                status_code=401,
                detail="Utilisateur introuvable"
            )

        if not bool(teacher["is_active"]):
            raise HTTPException(
                status_code=401,
                detail="Compte désactivé"
            )

        if teacher["role"] != role:
            raise HTTPException(
                status_code=401,
                detail="Rôle invalide"
            )

        return {
            "id": teacher["id"],
            "username": teacher["username"],
            "role": teacher["role"]
        }

    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token invalide ou expiré"
        )


def send_support_email(request: SupportRequest) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL")
    support_to_email = os.getenv("SUPPORT_TO_EMAIL")

    if not all([
        smtp_host,
        smtp_username,
        smtp_password,
        smtp_from_email,
        support_to_email
    ]):
        raise RuntimeError("Configuration SMTP incomplète.")

    email_message = EmailMessage()
    email_message["Subject"] = f"[ISEN SecureExam] {request.subject}"
    email_message["From"] = smtp_from_email
    email_message["To"] = support_to_email
    email_message["Reply-To"] = request.email

    email_message.set_content(
        f"""
Nouvelle demande de support ISEN SecureExam

Nom complet :
{request.fullName}

Email :
{request.email}

Type de problème :
{request.subject}

Message :
{request.message}

Date :
{now_iso()}
"""
    )

    context = ssl.create_default_context()

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls(context=context)
        server.login(smtp_username, smtp_password)
        server.send_message(email_message)


def load_teacher_profile(teacher_id: int):
    ensure_teacher_profile_scope()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            full_name,
            email,
            role,
            department,
            school,
            photo_path
        FROM teacher_profiles
        WHERE teacher_id = ?
        LIMIT 1
    """, (
        teacher_id,
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Profil professeur introuvable."
        )

    return {
        "fullName": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "department": row["department"],
        "school": row["school"],
        "photoPath": row["photo_path"]
    }


def save_teacher_profile(profile: TeacherProfile, teacher_id: int):
    ensure_teacher_profile_scope()

    connection = get_connection()
    cursor = connection.cursor()

    current_time = now_iso()

    cursor.execute("""
        UPDATE teacher_profiles
        SET
            full_name = ?,
            email = ?,
            role = ?,
            department = ?,
            school = ?,
            updated_at = ?
        WHERE teacher_id = ?
    """, (
        profile.fullName,
        profile.email,
        profile.role,
        profile.department,
        profile.school,
        current_time,
        teacher_id
    ))

    if cursor.rowcount == 0:
        cursor.execute("""
            INSERT INTO teacher_profiles (
                teacher_id,
                full_name,
                email,
                role,
                department,
                school,
                photo_path,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            teacher_id,
            profile.fullName,
            profile.email,
            profile.role,
            profile.department,
            profile.school,
            "",
            current_time,
            current_time
        ))

    connection.commit()
    connection.close()


def update_teacher_photo_path(photo_path: str, teacher_id: int):
    ensure_teacher_profile_scope()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE teacher_profiles
        SET
            photo_path = ?,
            updated_at = ?
        WHERE teacher_id = ?
    """, (
        photo_path,
        now_iso(),
        teacher_id
    ))

    connection.commit()
    connection.close()




def config_filename(exam_id: str, student_id: str, machine_id: str) -> str:
    return f"{exam_id}_{student_id}_{machine_id}.json"


def validate_config_filename(filename: str) -> str:
    safe_filename = Path(filename).name

    if safe_filename != filename:
        raise HTTPException(
            status_code=400,
            detail="Nom de fichier de configuration invalide."
        )

    if not safe_filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Nom de fichier de configuration invalide."
        )

    return safe_filename


def get_config_row_by_filename_or_404(filename: str):
    safe_filename = validate_config_filename(filename)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM exam_configs
        WHERE exam_id || '_' || student_id || '_' || machine_id || '.json' = ?
        ORDER BY updated_at DESC
    """, (
        safe_filename,
    ))

    rows = cursor.fetchall()
    connection.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Nom de fichier ambigu. Utilisez des identifiants sans collision."
        )

    return rows[0], safe_filename


def row_to_config(row):
    package_names = json.loads(row["packages"])
    nix_package_names = get_nix_package_names_for_package_names(package_names)

    return {
        "exam_id": row["exam_id"],
        "student_id": row["student_id"],
        "machine_id": row["machine_id"],
        "packages": package_names,
        "nix_packages": nix_package_names,
        "sudo": bool(row["sudo"]),
        "internet": bool(row["internet"]),
        "educ_access": bool(row["educ_access"]),
        "allowed_domains": json.loads(row["allowed_domains"]),
        "workspace": row["workspace"],
        "created_at": row["created_at"] if "created_at" in row.keys() else None,
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else None
    }


def get_config_row_or_404(exam_id: str, student_id: str, machine_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM exam_configs
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
    """, (
        exam_id,
        student_id,
        machine_id
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    return row


def save_support_request_to_database(
    request: SupportRequest,
    created_at: str,
    email_sent: int
) -> int:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO support_requests (
            full_name,
            email,
            subject,
            message,
            created_at,
            email_sent
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        request.fullName,
        request.email,
        request.subject,
        request.message,
        created_at,
        email_sent
    ))

    request_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return int(request_id)


def update_support_email_status(request_id: int, email_sent: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE support_requests
        SET email_sent = ?
        WHERE id = ?
    """, (
        email_sent,
        request_id
    ))

    connection.commit()
    connection.close()


NIX_PACKAGE_OVERRIDES = {
    "make": "gnumake"
}

PACKAGE_DISPLAY_OVERRIDES = {
    "gcc": "GCC",
    "gdb": "GDB",
    "git": "Git",
    "gnumake": "Make",
    "htop": "Htop",
    "make": "Make",
    "nano": "Nano",
    "python3": "Python 3",
    "vim": "Vim"
}


def ensure_package_catalog_nix_names():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("PRAGMA table_info(package_catalog)")
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    if "nix_name" not in columns:
        cursor.execute("""
            ALTER TABLE package_catalog
            ADD COLUMN nix_name TEXT
        """)

    cursor.execute("""
        SELECT id, name, nix_name
        FROM package_catalog
    """)

    rows = cursor.fetchall()

    for row in rows:
        current_nix_name = row["nix_name"]

        if current_nix_name is None or not str(current_nix_name).strip():
            default_nix_name = NIX_PACKAGE_OVERRIDES.get(
                row["name"],
                row["name"]
            )

            cursor.execute("""
                UPDATE package_catalog
                SET nix_name = ?, updated_at = ?
                WHERE id = ?
            """, (
                default_nix_name,
                now_iso(),
                row["id"]
            ))

    connection.commit()
    connection.close()


def normalize_package_identifier(value: str) -> str:
    return value.strip().lower()


def validate_package_identifier(value: str, label: str) -> str:
    cleaned_value = normalize_package_identifier(value)

    if not cleaned_value:
        raise HTTPException(
            status_code=400,
            detail=f"{label} obligatoire."
        )

    if not re.fullmatch(r"[a-zA-Z0-9._+-]+", cleaned_value):
        raise HTTPException(
            status_code=400,
            detail=f"{label} invalide. Utilisez seulement lettres, chiffres, points, tirets, underscores ou +."
        )

    return cleaned_value


def nix_attr_expression(nix_name: str) -> str:
    parts = nix_name.split(".")
    quoted_parts = ".".join(
        json.dumps(part)
        for part in parts
        if part
    )

    return f"(import <nixpkgs> {{}}).{quoted_parts}.name"


def verify_nix_package_exists(nix_name: str) -> str:
    nix_binary = shutil.which("nix")

    if nix_binary is None:
        raise HTTPException(
            status_code=503,
            detail="Commande nix introuvable sur le backend. Vérification NixOS impossible."
        )

    commands = [
        [
            nix_binary,
            "eval",
            "--extra-experimental-features",
            "nix-command flakes",
            "--raw",
            f"nixpkgs#{nix_name}.name"
        ],
        [
            nix_binary,
            "eval",
            "--extra-experimental-features",
            "nix-command",
            "--impure",
            "--raw",
            "--expr",
            nix_attr_expression(nix_name)
        ]
    ]

    last_error = ""

    for command in commands:
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=45
            )
        except subprocess.TimeoutExpired:
            last_error = "La vérification du paquet NixOS a expiré."
            continue

        if result.returncode == 0:
            resolved_name = result.stdout.strip()

            if not resolved_name:
                resolved_name = nix_name

            return resolved_name

        last_error = result.stderr.strip()

    raise HTTPException(
        status_code=400,
        detail={
            "message": "Paquet NixOS introuvable.",
            "nixName": nix_name,
            "error": last_error
        }
    )


def get_nix_package_names_for_package_names(package_names: list[str]) -> list[str]:
    if not package_names:
        return []

    placeholders = ",".join(["?"] * len(package_names))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(f"""
        SELECT name, nix_name
        FROM package_catalog
        WHERE name IN ({placeholders})
    """, package_names)

    rows = cursor.fetchall()
    connection.close()

    mapping = {}

    for row in rows:
        mapping[row["name"]] = row["nix_name"] or row["name"]

    nix_package_names = []

    for package_name in package_names:
        nix_package_names.append(
            mapping.get(
                package_name,
                NIX_PACKAGE_OVERRIDES.get(package_name, package_name)
            )
        )

    return nix_package_names



def ensure_exam_configs_teacher_scope():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("PRAGMA table_info(exam_configs)")
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    if "teacher_id" not in columns:
        cursor.execute("""
            ALTER TABLE exam_configs
            ADD COLUMN teacher_id INTEGER
        """)

    cursor.execute("""
        UPDATE exam_configs
        SET teacher_id = 1
        WHERE teacher_id IS NULL
    """)

    connection.commit()
    connection.close()



def ensure_teacher_profile_scope():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            school TEXT NOT NULL,
            photo_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    current_time = now_iso()

    cursor.execute("""
        SELECT id, username
        FROM teachers
        WHERE is_active = 1
        ORDER BY id ASC
    """)

    teachers = cursor.fetchall()

    for teacher in teachers:
        cursor.execute("""
            SELECT id
            FROM teacher_profiles
            WHERE teacher_id = ?
            LIMIT 1
        """, (
            teacher["id"],
        ))

        existing_profile = cursor.fetchone()

        if existing_profile is not None:
            continue

        cursor.execute("""
            INSERT INTO teacher_profiles (
                teacher_id,
                full_name,
                email,
                role,
                department,
                school,
                photo_path,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            teacher["id"],
            teacher["username"],
            f"{teacher['username']}@isen.fr",
            "Enseignant",
            "Département informatique",
            "ISEN",
            "",
            current_time,
            current_time
        ))

    connection.commit()
    connection.close()


seed_default_teacher_account()
ensure_package_catalog_nix_names()
ensure_exam_configs_teacher_scope()
ensure_teacher_profile_scope()


@app.get("/")
def root():
    return {
        "message": "API Plateforme Linux d'examen",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "message": "Serveur opérationnel"
    }


@app.post("/auth/login", response_model=TokenResponse)
def login(login_request: LoginRequest):
    teacher = get_teacher_by_username(login_request.username)

    if teacher is None:
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects"
        )

    if not bool(teacher["is_active"]):
        raise HTTPException(
            status_code=401,
            detail="Compte désactivé"
        )

    if not verify_password(
        login_request.password,
        teacher["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects"
        )

    access_token = create_access_token(
        data={
            "sub": teacher["username"],
            "role": teacher["role"]
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.get("/auth/me")
def auth_me(current_teacher: dict = Depends(get_current_teacher)):
    return current_teacher


@app.get("/teachers")
def list_teachers(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            username,
            role,
            is_active,
            created_at,
            updated_at
        FROM teachers
        ORDER BY id ASC
    """)

    rows = cursor.fetchall()
    connection.close()

    teachers = []

    for row in rows:
        teachers.append(teacher_row_to_public_dict(row))

    return {
        "count": len(teachers),
        "teachers": teachers
    }


@app.get("/teachers/{teacher_id}")
def get_teacher(
    teacher_id: int,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            username,
            role,
            is_active,
            created_at,
            updated_at
        FROM teachers
        WHERE id = ?
    """, (
        teacher_id,
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Enseignant introuvable."
        )

    return teacher_row_to_public_dict(row)


@app.get("/packages")
def list_packages(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        ORDER BY name ASC
    """)

    rows = cursor.fetchall()
    connection.close()

    packages = []

    for row in rows:
        packages.append(package_row_to_public_dict(row))

    return {
        "count": len(packages),
        "packages": packages
    }


@app.get("/packages/active")
def list_active_packages(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE is_active = 1
        ORDER BY name ASC
    """)

    rows = cursor.fetchall()
    connection.close()

    packages = []

    for row in rows:
        packages.append(package_row_to_public_dict(row))

    return {
        "count": len(packages),
        "packages": packages
    }




PACKAGE_VERIFY_CACHE = {}
NIX_ATTR_NAMES_CACHE = None
PACKAGE_SEARCH_CACHE = {}

PACKAGE_DISPLAY_OVERRIDES = {
    "gcc": "GCC",
    "gdb": "GDB",
    "git": "Git",
    "gitfull": "Git Full",
    "gitminimal": "Git Minimal",
    "gnumake": "Make",
    "htop": "Htop",
    "make": "Make",
    "nano": "Nano",
    "python": "Python",
    "python3": "Python 3",
    "vim": "Vim"
}


def generate_package_display_name(package_name: str, nix_name: str) -> str:
    package_name = package_name.strip().lower()
    nix_name = nix_name.strip().lower()
    clean_key = nix_name.replace("-", "").replace("_", "")

    if package_name in PACKAGE_DISPLAY_OVERRIDES:
        return PACKAGE_DISPLAY_OVERRIDES[package_name]

    if nix_name in PACKAGE_DISPLAY_OVERRIDES:
        return PACKAGE_DISPLAY_OVERRIDES[nix_name]

    if clean_key in PACKAGE_DISPLAY_OVERRIDES:
        return PACKAGE_DISPLAY_OVERRIDES[clean_key]

    readable_name = package_name.replace("-", " ").replace("_", " ").replace(".", " ")

    return " ".join(
        word[:1].upper() + word[1:]
        for word in readable_name.split()
        if word
    )


def verify_nix_package_exists_cached(nix_name: str) -> str:
    nix_name = nix_name.strip()

    if nix_name in PACKAGE_VERIFY_CACHE:
        return PACKAGE_VERIFY_CACHE[nix_name]

    resolved_name = verify_nix_package_exists(nix_name)
    PACKAGE_VERIFY_CACHE[nix_name] = resolved_name

    return resolved_name


def extract_package_version(resolved_name: str) -> str:
    match = re.search(r"-(\d[^\s]*)$", resolved_name)

    if match:
        return match.group(1)

    return resolved_name


def get_existing_package_keys() -> set[str]:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name, nix_name
        FROM package_catalog
    """)

    rows = cursor.fetchall()
    connection.close()

    keys = set()

    for row in rows:
        keys.add(row["name"])

        if row["nix_name"]:
            keys.add(row["nix_name"])

    return keys


def get_nix_attr_names() -> list[str]:
    global NIX_ATTR_NAMES_CACHE

    if NIX_ATTR_NAMES_CACHE is not None:
        return NIX_ATTR_NAMES_CACHE

    nix_binary = shutil.which("nix")

    if nix_binary is None:
        raise HTTPException(
            status_code=503,
            detail="Commande nix introuvable sur le backend."
        )

    command = [
        nix_binary,
        "eval",
        "--extra-experimental-features",
        "nix-command",
        "--impure",
        "--json",
        "--expr",
        "builtins.attrNames (import <nixpkgs> {})"
    ]

    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=90
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="Chargement de la liste Nixpkgs expiré."
        )

    if result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Impossible de lire les paquets Nixpkgs.",
                "error": result.stderr.strip()
            }
        )

    try:
        NIX_ATTR_NAMES_CACHE = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Réponse Nixpkgs invalide."
        )

    return NIX_ATTR_NAMES_CACHE


def get_nix_metadata_for_attrs(attr_names: list[str]) -> list[dict]:
    if not attr_names:
        return []

    nix_binary = shutil.which("nix")

    if nix_binary is None:
        raise HTTPException(
            status_code=503,
            detail="Commande nix introuvable sur le backend."
        )

    attrs_json = json.dumps(attr_names)

    expr = """
let
  pkgs = import <nixpkgs> {};
  attrs = builtins.fromJSON ATTRS_JSON_PLACEHOLDER;

  read = name:
    let attempt = builtins.tryEval (builtins.getAttr name pkgs);
    in
      if (!attempt.success) then null
      else
        let p = attempt.value;
        in
          if builtins.isAttrs p && ((p ? pname) || (p ? version) || (p ? name)) then {
            nixName = name;
            pname = if p ? pname then p.pname else name;
            version = if p ? version then p.version else "";
            fullName = if p ? name then p.name else name;
            description = if p ? meta && p.meta ? description then p.meta.description else "";
          } else null;
in
  builtins.filter (x: x != null) (map read attrs)
""".replace("ATTRS_JSON_PLACEHOLDER", json.dumps(attrs_json))

    command = [
        nix_binary,
        "eval",
        "--extra-experimental-features",
        "nix-command",
        "--impure",
        "--json",
        "--expr",
        expr
    ]

    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="Chargement des versions du paquet expiré."
        )

    if result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Impossible de lire les métadonnées du paquet.",
                "error": result.stderr.strip()
            }
        )

    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Métadonnées Nixpkgs invalides."
        )


def package_attr_score(attr_name: str, query: str) -> tuple:
    attr_lower = attr_name.lower()
    query = query.lower()

    if attr_lower == query:
        return (0, attr_lower)

    if attr_lower.startswith(query):
        return (1, attr_lower)

    if query in attr_lower:
        return (2, attr_lower)

    return (9, attr_lower)


def build_package_version_candidates(query: str) -> list[dict]:
    query = validate_package_identifier(
        query,
        "Le nom du paquet"
    )

    if len(query) < 2:
        raise HTTPException(
            status_code=400,
            detail="Saisissez au moins 2 caractères."
        )

    cache_key = query.lower()

    if cache_key in PACKAGE_SEARCH_CACHE:
        return PACKAGE_SEARCH_CACHE[cache_key]

    candidate_attrs = [query]

    all_attrs = get_nix_attr_names()

    matched_attrs = [
        attr for attr in all_attrs
        if query.lower() in attr.lower()
    ]

    matched_attrs.sort(key=lambda attr: package_attr_score(attr, query))

    for attr in matched_attrs[:50]:
        if attr not in candidate_attrs:
            candidate_attrs.append(attr)

    metadata_items = get_nix_metadata_for_attrs(candidate_attrs)
    existing_keys = get_existing_package_keys()

    candidates = []
    seen = set()

    for item in metadata_items:
        nix_name = item.get("nixName", "").strip()

        if not nix_name or nix_name in seen:
            continue

        seen.add(nix_name)

        pname = item.get("pname") or nix_name
        version = item.get("version") or extract_package_version(item.get("fullName", nix_name))
        full_name = item.get("fullName") or f"{pname}-{version}"
        description = item.get("description") or ""
        display_name = generate_package_display_name(pname, nix_name)
        technical_name = nix_name.lower()

        candidates.append({
            "name": technical_name,
            "nixName": nix_name,
            "displayName": display_name,
            "version": version,
            "description": description,
            "verifiedNixPackage": full_name,
            "catalogExists": technical_name in existing_keys or nix_name in existing_keys
        })

    candidates.sort(key=lambda candidate: package_attr_score(candidate["nixName"], query))

    PACKAGE_SEARCH_CACHE[cache_key] = candidates[:25]

    return PACKAGE_SEARCH_CACHE[cache_key]



def count_package_usage_in_configs(package_name: str, nix_name: str | None = None) -> int:
    targets = {package_name}

    if nix_name:
        targets.add(nix_name)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT packages
        FROM exam_configs
    """)

    rows = cursor.fetchall()
    connection.close()

    usage_count = 0

    for row in rows:
        try:
            config_packages = json.loads(row["packages"])
        except Exception:
            continue

        if any(package in targets for package in config_packages):
            usage_count += 1

    return usage_count


@app.get("/packages/management")
def get_packages_management(
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        ORDER BY display_name ASC
    """)

    rows = cursor.fetchall()
    connection.close()

    packages = []

    for row in rows:
        package = package_row_to_public_dict(row)
        usage_count = count_package_usage_in_configs(row["name"], row["nix_name"])

        package["usageCount"] = usage_count
        package["canDelete"] = usage_count == 0

        packages.append(package)

    return {
        "count": len(packages),
        "packages": packages
    }


@app.delete("/packages/{package_id}")
def delete_package(
    package_id: int,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    package = cursor.fetchone()

    if package is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Paquet introuvable."
        )

    usage_count = count_package_usage_in_configs(
        package["name"],
        package["nix_name"]
    )

    if usage_count > 0:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Ce paquet est déjà utilisé dans une ou plusieurs configurations. Il peut être désactivé, mais pas supprimé.",
                "usageCount": usage_count
            }
        )

    cursor.execute("""
        DELETE FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    connection.commit()
    connection.close()

    return {
        "message": "Paquet supprimé définitivement du catalogue.",
        "deletedPackageId": package_id
    }



@app.get("/packages/search/{package_query}")
def search_packages_for_catalog(
    package_query: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    candidates = build_package_version_candidates(package_query)

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="Paquet introuvable dans Nixpkgs."
        )

    return {
        "query": package_query.strip().lower(),
        "count": len(candidates),
        "candidates": candidates
    }


@app.get("/packages/verify/{package_name}")
def verify_package_for_catalog(
    package_name: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    name = validate_package_identifier(
        package_name,
        "Le nom du paquet"
    )

    nix_name = NIX_PACKAGE_OVERRIDES.get(name, name)

    resolved_nix_name = verify_nix_package_exists_cached(nix_name)
    display_name = generate_package_display_name(name, nix_name)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM package_catalog
        WHERE name = ?
    """, (
        name,
    ))

    existing_package = cursor.fetchone()
    connection.close()

    return {
        "exists": True,
        "catalogExists": existing_package is not None,
        "name": name,
        "nixName": nix_name,
        "displayName": display_name,
        "verifiedNixPackage": resolved_nix_name
    }


@app.post("/packages")
def create_package(
    package: PackageCreate,
    current_teacher: dict = Depends(get_current_teacher)
):
    name = validate_package_identifier(
        package.name,
        "Le nom du paquet"
    )

    raw_nix_name = package.nixName.strip() if package.nixName else ""
    if not raw_nix_name:
        raw_nix_name = NIX_PACKAGE_OVERRIDES.get(name, name)

    nix_name = validate_package_identifier(
        raw_nix_name,
        "Le nom NixOS du paquet"
    )

    description = package.description.strip()

    if not description:
        raise HTTPException(
            status_code=400,
            detail="La description du paquet est obligatoire."
        )

    display_name = package.displayName.strip() if package.displayName else ""
    if not display_name:
        display_name = generate_package_display_name(name, nix_name)

    resolved_nix_name = verify_nix_package_exists_cached(nix_name)
    current_time = now_iso()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM package_catalog
        WHERE name = ? OR nix_name = ?
    """, (
        name,
        nix_name
    ))

    existing_package = cursor.fetchone()

    if existing_package is not None:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail="Ce paquet existe déjà dans le catalogue."
        )

    cursor.execute("""
        INSERT INTO package_catalog (
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        nix_name,
        display_name,
        description,
        1,
        current_time,
        current_time
    ))

    package_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return {
        "message": "Paquet ajouté au catalogue avec succès.",
        "verifiedNixPackage": resolved_nix_name,
        "package": {
            "id": package_id,
            "name": name,
            "nixName": nix_name,
            "displayName": display_name,
            "description": description,
            "isActive": True,
            "createdAt": current_time,
            "updatedAt": current_time
        }
    }


@app.patch("/packages/{package_id}/disable")
def disable_package(
    package_id: int,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    package = cursor.fetchone()

    if package is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Paquet logiciel introuvable."
        )

    if not bool(package["is_active"]):
        connection.close()
        return {
            "message": "Ce paquet logiciel est déjà désactivé.",
            "package": package_row_to_public_dict(package)
        }

    current_time = now_iso()

    cursor.execute("""
        UPDATE package_catalog
        SET
            is_active = 0,
            updated_at = ?
        WHERE id = ?
    """, (
        current_time,
        package_id
    ))

    connection.commit()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    updated_package = cursor.fetchone()
    connection.close()

    return {
        "message": "Paquet logiciel désactivé avec succès.",
        "package": package_row_to_public_dict(updated_package)
    }


@app.patch("/packages/{package_id}/enable")
def enable_package(
    package_id: int,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    package = cursor.fetchone()

    if package is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Paquet logiciel introuvable."
        )

    if bool(package["is_active"]):
        connection.close()
        return {
            "message": "Ce paquet logiciel est déjà actif.",
            "package": package_row_to_public_dict(package)
        }

    current_time = now_iso()

    cursor.execute("""
        UPDATE package_catalog
        SET
            is_active = 1,
            updated_at = ?
        WHERE id = ?
    """, (
        current_time,
        package_id
    ))

    connection.commit()

    cursor.execute("""
        SELECT
            id,
            name,
            nix_name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        FROM package_catalog
        WHERE id = ?
    """, (
        package_id,
    ))

    updated_package = cursor.fetchone()
    connection.close()

    return {
        "message": "Paquet logiciel réactivé avec succès.",
        "package": package_row_to_public_dict(updated_package)
    }


@app.get("/database/stats")
def get_database_stats(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    tables = {
        "teachers": "Enseignants",
        "teacher_profiles": "Profils professeurs",
        "package_catalog": "Catalogue logiciels",
        "support_requests": "Demandes support",
        "exam_configs": "Configurations d'examen",
        "submissions": "Soumissions",
        "machine_status": "Statuts machines",
        "machine_status_history": "Historique statuts machines"
    }

    stats = []

    for table_name, label in tables.items():
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
        row = cursor.fetchone()

        stats.append({
            "table": table_name,
            "label": label,
            "count": row["total"]
        })

    connection.close()

    return {
        "database": "SQLite",
        "status": "ok",
        "tables": stats
    }


@app.get("/teacher-profile")
def get_teacher_profile(current_teacher: dict = Depends(get_current_teacher)):
    profile = load_teacher_profile(current_teacher["id"])
    photo_path = profile.get("photoPath")

    has_photo = False

    if photo_path:
        has_photo = resolve_backend_file_path(photo_path).exists()

    return {
        "fullName": profile["fullName"],
        "email": profile["email"],
        "role": profile["role"],
        "department": profile["department"],
        "school": profile["school"],
        "hasPhoto": has_photo,
        "photoUrl": f"/teacher-profile/photo/{current_teacher['id']}" if has_photo else ""
    }


@app.put("/teacher-profile")
def update_teacher_profile(
    profile: TeacherProfile,
    current_teacher: dict = Depends(get_current_teacher)
):
    save_teacher_profile(profile, current_teacher["id"])

    return {
        "message": "Profil professeur mis à jour avec succès.",
        "profile": profile.model_dump()
    }


@app.post("/teacher-profile/photo")
async def upload_teacher_profile_photo(
    photo: UploadFile = File(...),
    current_teacher: dict = Depends(get_current_teacher)
):
    if photo.filename is None:
        raise HTTPException(
            status_code=400,
            detail="Fichier image invalide."
        )

    extension = Path(photo.filename).suffix.lower()

    allowed_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Format image non autorisé. Utilisez PNG, JPG, JPEG ou WEBP."
        )

    teacher_id = current_teacher["id"]

    for old_photo in PROFILE_DIR.glob(f"profile_photo_teacher_{teacher_id}.*"):
        old_photo.unlink()

    photo_path = PROFILE_DIR / f"profile_photo_teacher_{teacher_id}{extension}"
    relative_photo_path = f"profile/{photo_path.name}"

    with open(photo_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    update_teacher_photo_path(relative_photo_path, teacher_id)

    return {
        "message": "Photo de profil mise à jour avec succès.",
        "photoUrl": f"/teacher-profile/photo/{teacher_id}"
    }


@app.get("/teacher-profile/photo/{teacher_id}")
def get_teacher_profile_photo_by_teacher(teacher_id: int):
    profile = load_teacher_profile(teacher_id)
    photo_path = profile.get("photoPath")

    if not photo_path:
        raise HTTPException(
            status_code=404,
            detail="Photo de profil introuvable."
        )

    photo_file = resolve_backend_file_path(photo_path)

    if not photo_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Photo de profil introuvable."
        )

    extension = photo_file.suffix.lower()
    media_type = "image/png"

    if extension in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"

    if extension == ".webp":
        media_type = "image/webp"

    return FileResponse(
        path=photo_file,
        media_type=media_type
    )


@app.get("/teacher-profile/photo")
def get_teacher_profile_photo():
    return get_teacher_profile_photo_by_teacher(1)




@app.post("/support-requests")
def create_support_request(request: SupportRequest):
    if not request.fullName.strip():
        raise HTTPException(
            status_code=400,
            detail="Le nom complet est obligatoire."
        )

    if not request.email.strip():
        raise HTTPException(
            status_code=400,
            detail="L'email est obligatoire."
        )

    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Le message est obligatoire."
        )

    created_at = now_iso()

    request_id = save_support_request_to_database(
        request=request,
        created_at=created_at,
        email_sent=0
    )

    try:
        send_support_email(request)
        update_support_email_status(request_id, 1)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Demande enregistrée en base, mais email non envoyé : {exc}"
        )

    return {
        "message": "Votre demande de support a été envoyée par email avec succès."
    }


@app.get("/support-requests-list")
def list_support_requests(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            full_name,
            email,
            subject,
            message,
            created_at,
            email_sent
        FROM support_requests
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    requests = []

    for row in rows:
        requests.append({
            "id": row["id"],
            "filename": f"database-request-{row['id']}",
            "created_at": row["created_at"],
            "fullName": row["full_name"],
            "email": row["email"],
            "subject": row["subject"],
            "message": row["message"],
            "emailSent": bool(row["email_sent"])
        })

    return {
        "count": len(requests),
        "support_requests": requests
    }


@app.post("/configs")
def create_config(
    config: ExamConfig,
    current_teacher: dict = Depends(get_current_teacher)
):
    requested_packages = set(config.packages)
    allowed_packages = get_active_package_names()
    invalid_packages = requested_packages - allowed_packages

    if invalid_packages:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Paquets non autorisés",
                "invalid_packages": sorted(list(invalid_packages))
            }
        )

    teacher_id = current_teacher["id"]

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM exam_configs
        WHERE teacher_id = ?
        AND exam_id = ?
        AND student_id = ?
        AND machine_id = ?
        LIMIT 1
    """, (
        teacher_id,
        config.exam_id,
        config.student_id,
        config.machine_id
    ))

    existing_config = cursor.fetchone()

    if existing_config is not None:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail="Cette configuration existe déjà dans votre espace. Pour la recréer, supprimez d’abord l’ancienne configuration."
        )

    created_at = now_iso()
    updated_at = created_at

    cursor.execute("""
        INSERT INTO exam_configs (
            teacher_id,
            exam_id,
            student_id,
            machine_id,
            packages,
            sudo,
            internet,
            educ_access,
            allowed_domains,
            workspace,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        teacher_id,
        config.exam_id,
        config.student_id,
        config.machine_id,
        json.dumps(config.packages, ensure_ascii=False),
        int(config.sudo),
        int(config.internet),
        int(config.educ_access),
        json.dumps(config.allowed_domains, ensure_ascii=False),
        config.workspace,
        created_at,
        updated_at
    ))

    connection.commit()
    connection.close()

    filename = config_filename(
        config.exam_id,
        config.student_id,
        config.machine_id
    )

    return {
        "message": "Configuration enregistrée en base avec succès",
        "file": filename,
        "created_at": created_at
    }




@app.get("/configs/{exam_id}/{student_id}/{machine_id}")
def get_config(exam_id: str, student_id: str, machine_id: str):
    row = get_config_row_or_404(
        exam_id=exam_id,
        student_id=student_id,
        machine_id=machine_id
    )

    return row_to_config(row)


@app.get("/configs-list")
def list_configs(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            exam_id,
            student_id,
            machine_id,
            workspace,
            created_at,
            updated_at
        FROM exam_configs
        WHERE teacher_id = ?
        ORDER BY updated_at DESC
    """, (
        current_teacher["id"],
    ))

    rows = cursor.fetchall()
    connection.close()

    files = []
    configs_details = []

    for row in rows:
        filename = config_filename(
            row["exam_id"],
            row["student_id"],
            row["machine_id"]
        )

        files.append(filename)

        configs_details.append({
            "filename": filename,
            "workspace": row["workspace"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "download_url": f"/configs/{filename}/download"
        })

    return {
        "count": len(files),
        "configs": files,
        "configs_details": configs_details
    }




@app.get("/configs/{filename}/download")
def download_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, safe_filename = get_config_row_by_filename_or_404(filename)

    config_data = row_to_config(row)

    content = json.dumps(
        config_data,
        indent=2,
        ensure_ascii=False
    )

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"'
        }
    )


@app.get("/configs-file/{filename}")
def get_config_by_filename(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, _ = get_config_row_by_filename_or_404(filename)

    return row_to_config(row)


@app.delete("/configs/{filename}")
def delete_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, safe_filename = get_config_row_by_filename_or_404(filename)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM exam_configs
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
    """, (
        row["exam_id"],
        row["student_id"],
        row["machine_id"]
    ))

    deleted_count = cursor.rowcount

    connection.commit()
    connection.close()

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    return {
        "message": "Configuration supprimée avec succès",
        "file": safe_filename
    }


@app.post("/submissions")
async def upload_submission(
    exam_id: str = Form(...),
    student_id: str = Form(...),
    machine_id: str = Form(...),
    archive: UploadFile = File(...)
):
    if archive.filename is None or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Seules les archives ZIP sont acceptées"
        )

    safe_filename = Path(archive.filename).name
    file_path = SUBMISSION_DIR / safe_filename
    relative_file_path = f"submissions/{safe_filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(archive.file, buffer)

    size_kb = round(file_path.stat().st_size / 1024, 2)
    created_at = now_text()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO submissions (
            exam_id,
            student_id,
            machine_id,
            filename,
            file_path,
            size_kb,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filename)
        DO UPDATE SET
            exam_id = excluded.exam_id,
            student_id = excluded.student_id,
            machine_id = excluded.machine_id,
            file_path = excluded.file_path,
            size_kb = excluded.size_kb,
            created_at = excluded.created_at
    """, (
        exam_id,
        student_id,
        machine_id,
        safe_filename,
        relative_file_path,
        size_kb,
        created_at
    ))

    connection.commit()
    connection.close()

    return {
        "message": "Archive reçue et enregistrée en base avec succès",
        "file": safe_filename
    }


@app.get("/submissions-list")
def list_submissions(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT s.filename
        FROM submissions s
        INNER JOIN exam_configs c
            ON c.exam_id = s.exam_id
            AND c.student_id = s.student_id
            AND c.machine_id = s.machine_id
        WHERE c.teacher_id = ?
        ORDER BY s.created_at DESC
    """, (
        current_teacher["id"],
    ))

    rows = cursor.fetchall()
    connection.close()

    files = [
        row["filename"]
        for row in rows
    ]

    return {
        "count": len(files),
        "submissions": files
    }




@app.get("/submissions/{filename}/download")
def download_submission(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    safe_filename = Path(filename).name

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT file_path
        FROM submissions
        WHERE filename = ?
    """, (
        safe_filename,
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Archive introuvable"
        )

    file_path = resolve_backend_file_path(row["file_path"])

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Fichier archive absent du disque"
        )

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/zip"
    )


@app.delete("/submissions/{filename}")
def delete_submission(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    safe_filename = Path(filename).name

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT file_path
        FROM submissions
        WHERE filename = ?
    """, (
        safe_filename,
    ))

    row = cursor.fetchone()

    if row is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Archive introuvable"
        )

    file_path = resolve_backend_file_path(row["file_path"])

    if file_path.exists():
        file_path.unlink()

    cursor.execute("""
        DELETE FROM submissions
        WHERE filename = ?
    """, (
        safe_filename,
    ))

    connection.commit()
    connection.close()

    return {
        "message": "Archive supprimée avec succès",
        "file": safe_filename
    }


@app.post("/machine-status")
def update_machine_status(status: MachineStatus):
    created_at = now_text()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO machine_status (
            exam_id,
            student_id,
            machine_id,
            step,
            status,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exam_id, student_id, machine_id)
        DO UPDATE SET
            step = excluded.step,
            status = excluded.status,
            message = excluded.message,
            created_at = excluded.created_at
    """, (
        status.exam_id,
        status.student_id,
        status.machine_id,
        status.step,
        status.status,
        status.message,
        created_at
    ))

    cursor.execute("""
        INSERT INTO machine_status_history (
            exam_id,
            student_id,
            machine_id,
            step,
            status,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        status.exam_id,
        status.student_id,
        status.machine_id,
        status.step,
        status.status,
        status.message,
        created_at
    ))

    connection.commit()
    connection.close()

    status_data = status.model_dump()
    status_data["created_at"] = created_at

    return {
        "message": "Statut machine mis à jour en base",
        "status": status_data
    }


@app.get("/machine-status/{exam_id}/{student_id}/{machine_id}")
def get_machine_status(exam_id: str, student_id: str, machine_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM machine_status
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
    """, (
        exam_id,
        student_id,
        machine_id
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Statut introuvable"
        )

    return {
        "exam_id": row["exam_id"],
        "student_id": row["student_id"],
        "machine_id": row["machine_id"],
        "step": row["step"],
        "status": row["status"],
        "message": row["message"],
        "created_at": row["created_at"]
    }


@app.get("/machine-status-list")
def list_machine_status(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            m.exam_id,
            m.student_id,
            m.machine_id
        FROM machine_status m
        INNER JOIN exam_configs c
            ON c.exam_id = m.exam_id
            AND c.student_id = m.student_id
            AND c.machine_id = m.machine_id
        WHERE c.teacher_id = ?
        ORDER BY m.created_at DESC
    """, (
        current_teacher["id"],
    ))

    rows = cursor.fetchall()
    connection.close()

    files = [
        config_filename(
            row["exam_id"],
            row["student_id"],
            row["machine_id"]
        )
        for row in rows
    ]

    return {
        "count": len(files),
        "statuses": files
    }




@app.get("/machine-status-history/{exam_id}/{student_id}/{machine_id}")
def get_machine_status_history(
    exam_id: str,
    student_id: str,
    machine_id: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            exam_id,
            student_id,
            machine_id,
            step,
            status,
            message,
            created_at
        FROM machine_status_history
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
        ORDER BY id ASC
    """, (
        exam_id,
        student_id,
        machine_id
    ))

    rows = cursor.fetchall()
    connection.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Historique introuvable"
        )

    history = []

    for row in rows:
        history.append({
            "exam_id": row["exam_id"],
            "student_id": row["student_id"],
            "machine_id": row["machine_id"],
            "step": row["step"],
            "status": row["status"],
            "message": row["message"],
            "created_at": row["created_at"]
        })

    return history


@app.get("/dashboard")
def dashboard(current_teacher: dict = Depends(get_current_teacher)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            exam_id,
            student_id,
            machine_id,
            workspace,
            created_at,
            updated_at
        FROM exam_configs
        WHERE teacher_id = ?
        ORDER BY updated_at DESC
    """, (
        current_teacher["id"],
    ))

    config_rows = cursor.fetchall()

    configs = []

    for row in config_rows:
        filename = config_filename(
            row["exam_id"],
            row["student_id"],
            row["machine_id"]
        )

        configs.append({
            "filename": filename,
            "workspace": row["workspace"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "download_url": f"/configs/{filename}/download"
        })

    cursor.execute("""
        SELECT
            s.filename,
            s.size_kb,
            s.created_at
        FROM submissions s
        INNER JOIN exam_configs c
            ON c.exam_id = s.exam_id
            AND c.student_id = s.student_id
            AND c.machine_id = s.machine_id
        WHERE c.teacher_id = ?
        ORDER BY s.created_at DESC
    """, (
        current_teacher["id"],
    ))

    submission_rows = cursor.fetchall()

    submissions = []

    for row in submission_rows:
        submissions.append({
            "filename": row["filename"],
            "size_kb": row["size_kb"],
            "created_at": row["created_at"],
            "download_url": f"/submissions/{row['filename']}/download"
        })

    cursor.execute("""
        SELECT
            m.exam_id,
            m.student_id,
            m.machine_id,
            m.step,
            m.status,
            m.message,
            m.created_at
        FROM machine_status m
        INNER JOIN exam_configs c
            ON c.exam_id = m.exam_id
            AND c.student_id = m.student_id
            AND c.machine_id = m.machine_id
        WHERE c.teacher_id = ?
        ORDER BY m.created_at DESC
    """, (
        current_teacher["id"],
    ))

    machine_rows = cursor.fetchall()
    connection.close()

    machine_statuses = []

    for row in machine_rows:
        machine_statuses.append({
            "exam_id": row["exam_id"],
            "student_id": row["student_id"],
            "machine_id": row["machine_id"],
            "step": row["step"],
            "status": row["status"],
            "message": row["message"],
            "created_at": row["created_at"]
        })

    return {
        "configs_count": len(configs),
        "submissions_count": len(submissions),
        "machines_count": len(machine_statuses),
        "configs": configs,
        "submissions": submissions,
        "machine_statuses": machine_statuses
    }




@app.get("/nixos-config")
def get_nixos_config(current_teacher: dict = Depends(get_current_teacher)):
    if not NIXOS_CONFIG_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration NixOS introuvable. Lance start_exam.py pour la générer."
        )

    content = NIXOS_CONFIG_FILE.read_text(encoding="utf-8")

    return {
        "filename": NIXOS_CONFIG_FILE.name,
        "content": content
    }


@app.get("/nixos-config/download")
def download_nixos_config(current_teacher: dict = Depends(get_current_teacher)):
    if not NIXOS_CONFIG_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration NixOS introuvable. Lance start_exam.py pour la générer."
        )

    return FileResponse(
        path=NIXOS_CONFIG_FILE,
        filename=NIXOS_CONFIG_FILE.name,
        media_type="text/plain"
    )