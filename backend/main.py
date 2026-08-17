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
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel


load_dotenv()

app = FastAPI(title="Plateforme Linux d'examen")

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

CONFIG_DIR = BASE_DIR / "configs"
CONFIG_DIR.mkdir(exist_ok=True)

SUBMISSION_DIR = BASE_DIR / "submissions"
SUBMISSION_DIR.mkdir(exist_ok=True)

STATUS_DIR = BASE_DIR / "status"
STATUS_DIR.mkdir(exist_ok=True)

STATUS_HISTORY_DIR = BASE_DIR / "status_history"
STATUS_HISTORY_DIR.mkdir(exist_ok=True)

SUPPORT_REQUESTS_DIR = BASE_DIR / "support_requests"
SUPPORT_REQUESTS_DIR.mkdir(exist_ok=True)

PROFILE_DIR = BASE_DIR / "profile"
PROFILE_DIR.mkdir(exist_ok=True)

TEACHER_PROFILE_FILE = PROFILE_DIR / "teacher_profile.json"

NIXOS_CONFIG_FILE = PROJECT_DIR / "exam-client" / "generated" / "exam-configuration.nix"


ALLOWED_PACKAGES = {
    "python3",
    "gcc",
    "gdb",
    "make",
    "vim",
    "nano"
}


SECRET_KEY = "change-this-secret-key-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

TEACHER_USERNAME = "prof"
TEACHER_PASSWORD = "isen-prof"

password_hash = PasswordHash.recommended()
TEACHER_PASSWORD_HASH = password_hash.hash(TEACHER_PASSWORD)

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


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


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

        if username != TEACHER_USERNAME or role != "teacher":
            raise HTTPException(
                status_code=401,
                detail="Token invalide"
            )

        return {
            "username": username,
            "role": role
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
{datetime.now().isoformat(timespec="seconds")}
"""
    )

    context = ssl.create_default_context()

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls(context=context)
        server.login(smtp_username, smtp_password)
        server.send_message(email_message)


def get_default_teacher_profile():
    return {
        "fullName": "Professeur ISEN",
        "email": "prof@isen.fr",
        "role": "Enseignant",
        "department": "Informatique / Systèmes Linux",
        "school": "ISEN SecureExam"
    }


def load_teacher_profile():
    if not TEACHER_PROFILE_FILE.exists():
        default_profile = get_default_teacher_profile()

        TEACHER_PROFILE_FILE.write_text(
            json.dumps(default_profile, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        return default_profile

    return json.loads(
        TEACHER_PROFILE_FILE.read_text(encoding="utf-8")
    )


def save_teacher_profile(profile: TeacherProfile):
    TEACHER_PROFILE_FILE.write_text(
        json.dumps(profile.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


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
    if login_request.username != TEACHER_USERNAME:
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects"
        )

    if not verify_password(
        login_request.password,
        TEACHER_PASSWORD_HASH
    ):
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects"
        )

    access_token = create_access_token(
        data={
            "sub": TEACHER_USERNAME,
            "role": "teacher"
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.get("/auth/me")
def auth_me(current_teacher: dict = Depends(get_current_teacher)):
    return current_teacher


@app.get("/teacher-profile")
def get_teacher_profile(current_teacher: dict = Depends(get_current_teacher)):
    profile = load_teacher_profile()
    photo_files = list(PROFILE_DIR.glob("profile_photo.*"))

    return {
        **profile,
        "hasPhoto": len(photo_files) > 0,
        "photoUrl": "/teacher-profile/photo" if photo_files else ""
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

    with open(photo_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    return {
        "message": "Photo de profil mise à jour avec succès.",
        "photoUrl": "/teacher-profile/photo"
    }


@app.get("/teacher-profile/photo")
def get_teacher_profile_photo():
    photo_files = list(PROFILE_DIR.glob("profile_photo.*"))

    if not photo_files:
        raise HTTPException(
            status_code=404,
            detail="Photo de profil introuvable."
        )

    photo_path = photo_files[0]
    extension = photo_path.suffix.lower()

    media_type = "image/png"

    if extension in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"

    if extension == ".webp":
        media_type = "image/webp"

    return FileResponse(
        path=photo_path,
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

    created_at = datetime.now().isoformat(timespec="seconds")

    saved_request = {
        "created_at": created_at,
        "fullName": request.fullName,
        "email": request.email,
        "subject": request.subject,
        "message": request.message
    }

    filename = f"support_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    file_path = SUPPORT_REQUESTS_DIR / filename

    file_path.write_text(
        json.dumps(saved_request, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    try:
        send_support_email(request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Demande enregistrée, mais email non envoyé : {exc}"
        )

    return {
        "message": "Votre demande de support a été envoyée par email avec succès."
    }


@app.get("/support-requests-list")
def list_support_requests(current_teacher: dict = Depends(get_current_teacher)):
    requests = []

    support_files = sorted(
        SUPPORT_REQUESTS_DIR.glob("*.json"),
        key=lambda file: file.stat().st_mtime,
        reverse=True
    )

    for file in support_files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))

            requests.append({
                "filename": file.name,
                "created_at": data.get("created_at", ""),
                "fullName": data.get("fullName", ""),
                "email": data.get("email", ""),
                "subject": data.get("subject", ""),
                "message": data.get("message", "")
            })

        except json.JSONDecodeError:
            continue

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
    invalid_packages = requested_packages - ALLOWED_PACKAGES

    if invalid_packages:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Paquets non autorisés",
                "invalid_packages": list(invalid_packages)
            }
        )

    filename = f"{config.exam_id}_{config.student_id}_{config.machine_id}.json"
    file_path = CONFIG_DIR / filename

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

    return {
        "message": "Configuration générée avec succès",
        "file": filename
    }


@app.get("/configs/{exam_id}/{student_id}/{machine_id}")
def get_config(exam_id: str, student_id: str, machine_id: str):
    filename = f"{exam_id}_{student_id}_{machine_id}.json"
    file_path = CONFIG_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/configs-list")
def list_configs(current_teacher: dict = Depends(get_current_teacher)):
    files = [file.name for file in CONFIG_DIR.glob("*.json")]

    return {
        "count": len(files),
        "configs": files
    }


@app.get("/configs/{filename}/download")
def download_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    safe_filename = Path(filename).name
    file_path = CONFIG_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/json"
    )


@app.get("/configs-file/{filename}")
def get_config_by_filename(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    safe_filename = Path(filename).name
    file_path = CONFIG_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.delete("/configs/{filename}")
def delete_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    safe_filename = Path(filename).name
    file_path = CONFIG_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    file_path.unlink()

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
    if archive.filename is None or not archive.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Seules les archives ZIP sont acceptées"
        )

    safe_filename = Path(archive.filename).name
    file_path = SUBMISSION_DIR / safe_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(archive.file, buffer)

    return {
        "message": "Archive reçue avec succès",
        "file": safe_filename
    }


@app.get("/submissions-list")
def list_submissions(current_teacher: dict = Depends(get_current_teacher)):
    files = [file.name for file in SUBMISSION_DIR.glob("*.zip")]

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
    file_path = SUBMISSION_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Archive introuvable"
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
    file_path = SUBMISSION_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Archive introuvable"
        )

    file_path.unlink()

    return {
        "message": "Archive supprimée avec succès",
        "file": safe_filename
    }


@app.post("/machine-status")
def update_machine_status(status: MachineStatus):
    filename = f"{status.exam_id}_{status.student_id}_{status.machine_id}.json"

    latest_file_path = STATUS_DIR / filename
    history_file_path = STATUS_HISTORY_DIR / filename

    status_data = status.model_dump()
    status_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(latest_file_path, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2, ensure_ascii=False)

    if history_file_path.exists():
        with open(history_file_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []

    history.append(status_data)

    with open(history_file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return {
        "message": "Statut machine mis à jour",
        "status": status_data
    }


@app.get("/machine-status/{exam_id}/{student_id}/{machine_id}")
def get_machine_status(exam_id: str, student_id: str, machine_id: str):
    filename = f"{exam_id}_{student_id}_{machine_id}.json"
    file_path = STATUS_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Statut introuvable"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/machine-status-list")
def list_machine_status(current_teacher: dict = Depends(get_current_teacher)):
    files = [file.name for file in STATUS_DIR.glob("*.json")]

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
    filename = f"{exam_id}_{student_id}_{machine_id}.json"
    file_path = STATUS_HISTORY_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Historique introuvable"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/dashboard")
def dashboard(current_teacher: dict = Depends(get_current_teacher)):
    configs = []

    for file in CONFIG_DIR.glob("*.json"):
        configs.append({
            "filename": file.name,
            "download_url": f"/configs/{file.name}/download"
        })

    submission_files = sorted(
        SUBMISSION_DIR.glob("*.zip"),
        key=lambda file: file.stat().st_mtime,
        reverse=True
    )

    submissions = []

    for file in submission_files:
        submissions.append({
            "filename": file.name,
            "size_kb": round(file.stat().st_size / 1024, 2),
            "created_at": datetime.fromtimestamp(
                file.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "download_url": f"/submissions/{file.name}/download"
        })

    machine_statuses = []

    for file in STATUS_DIR.glob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            machine_statuses.append(json.load(f))

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