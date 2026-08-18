import json
import os
import shutil
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
        "http://127.0.0.1:4200"
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

NIXOS_CONFIG_FILE = PROJECT_DIR / "exam-client" / "generated" / "exam-configuration.nix"


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
    displayName: str
    description: str


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
    return {
        "id": row["id"],
        "name": row["name"],
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


def load_teacher_profile():
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
        FROM teacher_profile
        WHERE id = 1
    """)

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


def save_teacher_profile(profile: TeacherProfile):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE teacher_profile
        SET
            full_name = ?,
            email = ?,
            role = ?,
            department = ?,
            school = ?,
            updated_at = ?
        WHERE id = 1
    """, (
        profile.fullName,
        profile.email,
        profile.role,
        profile.department,
        profile.school,
        now_iso()
    ))

    connection.commit()
    connection.close()


def update_teacher_photo_path(photo_path: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE teacher_profile
        SET
            photo_path = ?,
            updated_at = ?
        WHERE id = 1
    """, (
        photo_path,
        now_iso()
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
    return {
        "exam_id": row["exam_id"],
        "student_id": row["student_id"],
        "machine_id": row["machine_id"],
        "packages": json.loads(row["packages"]),
        "sudo": bool(row["sudo"]),
        "internet": bool(row["internet"]),
        "educ_access": bool(row["educ_access"]),
        "allowed_domains": json.loads(row["allowed_domains"]),
        "workspace": row["workspace"]
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


seed_default_teacher_account()


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


@app.post("/packages")
def create_package(
    package: PackageCreate,
    current_teacher: dict = Depends(get_current_teacher)
):
    name = package.name.strip().lower()
    display_name = package.displayName.strip()
    description = package.description.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Le nom technique du paquet est obligatoire."
        )

    if not display_name:
        raise HTTPException(
            status_code=400,
            detail="Le nom affiché du paquet est obligatoire."
        )

    if not description:
        raise HTTPException(
            status_code=400,
            detail="La description du paquet est obligatoire."
        )

    if not name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Le nom technique doit contenir seulement des lettres, chiffres, tirets ou underscores."
        )

    current_time = now_iso()

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

    if existing_package is not None:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail="Ce paquet existe déjà dans le catalogue."
        )

    cursor.execute("""
        INSERT INTO package_catalog (
            name,
            display_name,
            description,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
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
        "package": {
            "id": package_id,
            "name": name,
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
        "teacher_profile": "Profil professeur",
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
    profile = load_teacher_profile()
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
        "photoUrl": "/teacher-profile/photo" if has_photo else ""
    }


@app.put("/teacher-profile")
def update_teacher_profile(
    profile: TeacherProfile,
    current_teacher: dict = Depends(get_current_teacher)
):
    save_teacher_profile(profile)

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

    for old_photo in PROFILE_DIR.glob("profile_photo.*"):
        old_photo.unlink()

    photo_path = PROFILE_DIR / f"profile_photo{extension}"
    relative_photo_path = f"profile/{photo_path.name}"

    with open(photo_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    update_teacher_photo_path(relative_photo_path)

    return {
        "message": "Photo de profil mise à jour avec succès.",
        "photoUrl": "/teacher-profile/photo"
    }


@app.get("/teacher-profile/photo")
def get_teacher_profile_photo():
    profile = load_teacher_profile()
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

    created_at = now_iso()
    updated_at = created_at

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO exam_configs (
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exam_id, student_id, machine_id)
        DO UPDATE SET
            packages = excluded.packages,
            sudo = excluded.sudo,
            internet = excluded.internet,
            educ_access = excluded.educ_access,
            allowed_domains = excluded.allowed_domains,
            workspace = excluded.workspace,
            updated_at = excluded.updated_at
    """, (
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
        "file": filename
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
        SELECT exam_id, student_id, machine_id
        FROM exam_configs
        ORDER BY updated_at DESC
    """)

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
        "configs": files
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
        SELECT filename
        FROM submissions
        ORDER BY created_at DESC
    """)

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
        SELECT exam_id, student_id, machine_id
        FROM machine_status
        ORDER BY created_at DESC
    """)

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
        SELECT exam_id, student_id, machine_id
        FROM exam_configs
        ORDER BY updated_at DESC
    """)

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
            "download_url": f"/configs/{filename}/download"
        })

    cursor.execute("""
        SELECT
            filename,
            size_kb,
            created_at
        FROM submissions
        ORDER BY created_at DESC
    """)

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
            exam_id,
            student_id,
            machine_id,
            step,
            status,
            message,
            created_at
        FROM machine_status
        ORDER BY created_at DESC
    """)

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