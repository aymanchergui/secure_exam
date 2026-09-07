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
from typing import List, Optional

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

NIXOS_GENERATED_DIR = PROJECT_DIR / "exam-client" / "var" / "generated"
NIXOS_CONFIG_FILE = NIXOS_GENERATED_DIR / "exam-configuration.nix"
NIXOS_METADATA_FILE = NIXOS_GENERATED_DIR / "exam-metadata.json"

GLOBAL_STUDENT_ID = "GLOBAL"
GLOBAL_MACHINE_ID = "ALL_MACHINES"
GLOBAL_WORKSPACE = "/home/exam/workspace"


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}"
        )

    return value


SECRET_KEY = os.getenv("JWT_SECRET_KEY", "secureexam-dev-secret-key-2026")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120")
)

TEACHER_USERNAME = os.getenv("TEACHER_USERNAME", "prof")
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "1234")


password_hash = PasswordHash.recommended()
security = HTTPBearer()


class ExamConfig(BaseModel):
    exam_id: str
    packages: List[str]
    sudo: bool
    internet: bool
    educ_access: bool
    allowed_domains: List[str]
    exam_name: Optional[str] = None
    exam_date: Optional[str] = None
    exam_time: Optional[str] = None
    student_id: Optional[str] = None
    machine_id: Optional[str] = None
    workspace: Optional[str] = None


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
    server = None

    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
        server.starttls(context=context)
        server.login(smtp_username, smtp_password)
        server.send_message(email_message)
    finally:
        if server is not None:
            server.close()


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




def config_filename(
    exam_id: str,
    *_ignored
) -> str:
    return f"{exam_id}.json"




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


def get_config_row_by_filename_or_404(
    filename: str,
    teacher_id: int | None = None
):
    safe_filename = validate_config_filename(
        filename
    )

    stem = Path(
        safe_filename
    ).stem

    # -----------------------------------------------------
    # FORMAT ACTUEL
    # -----------------------------------------------------
    #
    # EXAM-C-2026.json
    #
    # => exam_id = EXAM-C-2026
    #
    # -----------------------------------------------------
    # COMPATIBILITE ANCIEN FORMAT
    # -----------------------------------------------------
    #
    # EXAM-C-2026_GLOBAL_ALL_MACHINES.json
    #
    # => exam_id = EXAM-C-2026
    #

    legacy_suffix = (
        "_GLOBAL_ALL_MACHINES"
    )

    if stem.endswith(
        legacy_suffix
    ):
        exam_id = stem[
            :-len(legacy_suffix)
        ]
    else:
        exam_id = stem


    connection = get_connection()
    cursor = connection.cursor()


    if teacher_id is None:

        cursor.execute("""
            SELECT *
            FROM exam_configs
            WHERE exam_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (
            exam_id,
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM exam_configs
            WHERE exam_id = ?
            AND teacher_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (
            exam_id,
            teacher_id
        ))


    row = cursor.fetchone()

    connection.close()


    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration introuvable "
                f"pour l'examen {exam_id}"
            )
        )


    # Toujours retourner le nouveau nom propre.
    clean_filename = config_filename(
        row["exam_id"]
    )

    return (
        row,
        clean_filename
    )



def row_to_config(row):
    package_names = json.loads(row["packages"])
    nix_package_names = get_nix_package_names_for_package_names(package_names)

    return {
        "exam_id": row["exam_id"],
        "exam_name": row["exam_name"] if "exam_name" in row.keys() and row["exam_name"] else row["exam_id"],
        "exam_date": row["exam_date"] if "exam_date" in row.keys() else "",
        "exam_time": row["exam_time"] if "exam_time" in row.keys() else "",
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

def get_config_row_for_teacher_or_404(
    exam_id: str,
    student_id: str,
    machine_id: str,
    teacher_id: int
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM exam_configs
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
        AND teacher_id = ?
        LIMIT 1
    """, (
        exam_id,
        student_id,
        machine_id,
        teacher_id
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Configuration introuvable"
        )

    return row

def get_generated_nixos_metadata_or_404() -> dict:
    if not NIXOS_METADATA_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Métadonnées NixOS introuvables. Lance start_exam.py pour générer la configuration."
        )

    try:
        metadata = json.loads(NIXOS_METADATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Métadonnées NixOS invalides."
        )

    exam_id = metadata.get("exam_id")
    student_id = metadata.get("student_id")
    machine_id = metadata.get("machine_id")

    if not exam_id or not student_id or not machine_id:
        raise HTTPException(
            status_code=500,
            detail="Métadonnées NixOS incomplètes."
        )

    return metadata


def ensure_generated_nixos_belongs_to_teacher(current_teacher: dict) -> dict:
    if not NIXOS_CONFIG_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration NixOS introuvable. Lance start_exam.py pour la générer."
        )

    metadata = get_generated_nixos_metadata_or_404()

    get_config_row_for_teacher_or_404(
        exam_id=metadata["exam_id"],
        student_id=metadata["student_id"],
        machine_id=metadata["machine_id"],
        teacher_id=current_teacher["id"]
    )

    return metadata



def _secureexam_add_sandbox_v4(
    nix_text: str,
    package_lines: list[str]
) -> str:

    module_marker = (
        "{ config, pkgs, ... }:\n\n{"
    )

    if module_marker not in nix_text:
        raise RuntimeError(
            "En-tête module NixOS introuvable."
        )

    package_block = "\n".join(
        "    " + line.strip()
        for line in package_lines
        if line.strip()
    )

    sandbox_header = r"""
{ config, pkgs, ... }:

let

  secureExamPackages = [
__SECUREEXAM_PACKAGES__
  ];

  secureExamBasePackages = [
    pkgs.bashInteractive
    pkgs.coreutils
    pkgs.cacert
  ];

  secureExamEnv = pkgs.buildEnv {
    name = "secureexam-env";

    paths =
      secureExamBasePackages
      ++ secureExamPackages;

    pathsToLink = [
      "/bin"
      "/share"
    ];

    ignoreCollisions = true;
  };

  secureExamClosure = pkgs.closureInfo {
    rootPaths = [
      secureExamEnv
    ];
  };

  secureExamLauncher =
    pkgs.writeShellScriptBin
      "secureexam-session"
      ''

        set -euo pipefail

        uid="$(
          ${pkgs.coreutils}/bin/id -u
        )"

        gid="$(
          ${pkgs.coreutils}/bin/id -g
        )"

        if [ "$uid" != "1500" ]; then
          echo "SecureExam: accès refusé." >&2
          exit 1
        fi


        resolv="$(
          ${pkgs.coreutils}/bin/mktemp
        )"

        ${pkgs.coreutils}/bin/cat \
          /etc/resolv.conf \
          > "$resolv"

        ${pkgs.coreutils}/bin/chmod \
          0444 \
          "$resolv"


        cleanup() {
          ${pkgs.coreutils}/bin/rm \
            -f \
            "$resolv"
        }

        trap cleanup EXIT INT TERM


        storeArgs=()

        while IFS= read -r storePath; do

          if [ -n "$storePath" ]; then

            storeArgs+=(
              --ro-bind
              "$storePath"
              "$storePath"
            )

          fi

        done < ${secureExamClosure}/store-paths


        term="''${TERM:-xterm-256color}"


        ${pkgs.bubblewrap}/bin/bwrap \
          --die-with-parent \
          --new-session \
          --unshare-user \
          --uid "$uid" \
          --gid "$gid" \
          --disable-userns \
          --unshare-pid \
          --unshare-ipc \
          --unshare-uts \
          --unshare-cgroup-try \
          --cap-drop ALL \
          --clearenv \
          --dir /nix \
          --dir /nix/store \
          --dir /etc \
          --dir /opt \
          --dir /home \
          --dir /home/exam \
          --dir /run \
          --proc /proc \
          --dev /dev \
          --tmpfs /tmp \
          --bind \
            /home/exam/workspace \
            /home/exam/workspace \
          "''${storeArgs[@]}" \
          --ro-bind \
            ${secureExamEnv} \
            /opt/secureexam \
          --ro-bind \
            "$resolv" \
            /etc/resolv.conf \
          --ro-bind \
            /etc/hosts \
            /etc/hosts \
          --ro-bind \
            /etc/passwd \
            /etc/passwd \
          --ro-bind \
            /etc/group \
            /etc/group \
          --ro-bind \
            /etc/nsswitch.conf \
            /etc/nsswitch.conf \
          --setenv \
            HOME \
            /home/exam \
          --setenv \
            USER \
            exam \
          --setenv \
            LOGNAME \
            exam \
          --setenv \
            SHELL \
            /opt/secureexam/bin/bash \
          --setenv \
            PATH \
            /opt/secureexam/bin \
          --setenv \
            TERM \
            "$term" \
          --setenv \
            LANG \
            C.UTF-8 \
          --setenv \
            LC_ALL \
            C.UTF-8 \
          --setenv \
            SSL_CERT_FILE \
            ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt \
          --chdir \
            /home/exam/workspace \
          /opt/secureexam/bin/bash \
            --noprofile \
            --norc


        status=$?

        cleanup

        trap - EXIT INT TERM

        exit "$status"

      '';

in

{
"""

    sandbox_header = (
        sandbox_header
        .replace(
            "__SECUREEXAM_PACKAGES__",
            package_block
        )
        .strip("\n")
    )

    nix_text = nix_text.replace(
        module_marker,
        sandbox_header,
        1
    )


    shell_marker = (
        '    createHome = true;\n'
    )

    if shell_marker not in nix_text:
        raise RuntimeError(
            "createHome introuvable."
        )

    nix_text = nix_text.replace(
        shell_marker,
        (
            '    createHome = true;\n'
            '\n'
            '    shell = '
            '"${secureExamLauncher}'
            '/bin/secureexam-session";\n'
        ),
        1
    )


    workspace_marker = (
        "  systemd.tmpfiles.rules = ["
    )

    if workspace_marker not in nix_text:
        raise RuntimeError(
            "Bloc workspace introuvable."
        )

    nix_text = nix_text.replace(
        workspace_marker,
        (
            "  environment.systemPackages = [\n"
            "    secureExamLauncher\n"
            "  ];\n"
            "\n"
            + workspace_marker
        ),
        1
    )


    return nix_text



def _secureexam_finalize_nix_v4(
    nix_text: str,
    package_lines: list[str]
) -> str:

    nix_text = nix_text.replace(
        "# SecureExam STRICT POLICY v3",
        "# SecureExam STRICT POLICY v4",
        1
    )


    # UID dynamique :
    # la sécurité cible maintenant le compte "exam"
    # et non plus un UID numérique fixe.

    nix_text = nix_text.replace(
        "    uid = 1500;\n",
        "",
        1
    )


    nix_text = nix_text.replace(
        '        if [ "$uid" != "1500" ]; then',
        '        if [ "$(${pkgs.coreutils}/bin/id -un)" != "exam" ]; then',
        1
    )


    nix_text = nix_text.replace(
        "meta skuid 1500",
        'meta skuid "exam"'
    )


    # Le bundle CA doit être réellement visible
    # dans la sandbox pour HTTPS.

    closure_old = (
        "  secureExamClosure = pkgs.closureInfo {\n"
        "    rootPaths = [\n"
        "      secureExamEnv\n"
        "    ];\n"
        "  };"
    )

    closure_new = (
        "  secureExamClosure = pkgs.closureInfo {\n"
        "    rootPaths = [\n"
        "      secureExamEnv\n"
        "      pkgs.cacert\n"
        "    ];\n"
        "  };"
    )

    if closure_old in nix_text:
        nix_text = nix_text.replace(
            closure_old,
            closure_new,
            1
        )


    # Les logiciels ne doivent pas être installés
    # dans le profil normal de l'utilisateur exam.
    # Ils sont exposés uniquement dans la sandbox.

    user_packages_block = (
        "    packages = [\n"
    )

    if package_lines:
        user_packages_block += (
            "\n".join(package_lines)
            + "\n"
        )

    user_packages_block += (
        "    ];\n"
    )

    nix_text = nix_text.replace(
        user_packages_block,
        "",
        1
    )


    # Normalisation automatique du workspace.
    # Les fichiers déjà présents deviennent
    # utilisables par le compte exam.

    workspace_rule = (
        "  systemd.tmpfiles.rules = [\n"
        '    "d /home/exam/workspace 0700 exam users -"\n'
        "  ];\n"
    )

    workspace_service = (
        workspace_rule
        + "\n"
        + "  systemd.services.secureexam-workspace-permissions = {\n"
        + '    description = "SecureExam workspace permissions";\n'
        + "\n"
        + "    after = [\n"
        + '      "systemd-tmpfiles-setup.service"\n'
        + "    ];\n"
        + "\n"
        + "    before = [\n"
        + '      "display-manager.service"\n'
        + "    ];\n"
        + "\n"
        + "    wantedBy = [\n"
        + '      "multi-user.target"\n'
        + "    ];\n"
        + "\n"
        + "    serviceConfig = {\n"
        + '      Type = "oneshot";\n'
        + "    };\n"
        + "\n"
        + "    script = ''\n"
        + "      ${pkgs.coreutils}/bin/chown -R exam:users /home/exam/workspace\n"
        + "      ${pkgs.coreutils}/bin/chmod 0700 /home/exam/workspace\n"
        + "    '';\n"
        + "  };\n"
    )

    if (
        workspace_rule in nix_text
        and
        "secureexam-workspace-permissions"
        not in nix_text
    ):
        nix_text = nix_text.replace(
            workspace_rule,
            workspace_service,
            1
        )


    return nix_text


def generate_nixos_config_preview(config_data: dict) -> str:

    exam_id = str(
        config_data.get("exam_id")
        or ""
    ).strip()

    exam_name = str(
        config_data.get("exam_name")
        or exam_id
    ).strip()

    exam_date = str(
        config_data.get("exam_date")
        or config_data.get("scheduled_date")
        or ""
    ).strip()

    exam_time = str(
        config_data.get("exam_time")
        or config_data.get("scheduled_time")
        or ""
    ).strip()

    sudo_allowed = bool(
        config_data.get("sudo")
    )

    internet_allowed = bool(
        config_data.get("internet")
    )

    educ_access = bool(
        config_data.get("educ_access")
    )

    workspace = "/home/exam/workspace"

    packages = (
        config_data.get("nix_packages")
        or config_data.get("packages")
        or []
    )


    def nix_package_expression(
        package_name: str
    ) -> str:

        parts = [
            part.strip()
            for part in str(
                package_name
            ).split(".")
            if part.strip()
        ]

        if not parts:
            raise HTTPException(
                status_code=400,
                detail="Nom de paquet NixOS invalide."
            )

        for part in parts:

            if not re.fullmatch(
                r"[A-Za-z0-9_+\-]+",
                part
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Nom de paquet NixOS invalide : "
                        + str(package_name)
                    )
                )

        return (
            "pkgs"
            + "".join(
                "."
                + json.dumps(part)
                for part in parts
            )
        )


    package_lines = [
        "      "
        + nix_package_expression(package)
        for package in packages
    ]


    raw_domains = (
        config_data.get("allowed_domains")
        or []
    )

    allowed_domains = []


    for raw_domain in raw_domains:

        domain = str(
            raw_domain
        ).strip().lower().rstrip(".")

        if not domain:
            continue

        if not re.fullmatch(
            r"[a-z0-9]"
            r"(?:[a-z0-9.-]*[a-z0-9])?",
            domain
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Domaine invalide : "
                    + domain
                )
            )

        if (
            ".." in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Domaine invalide : "
                    + domain
                )
            )

        if domain not in allowed_domains:
            allowed_domains.append(
                domain
            )


    if (
        educ_access
        and "educ.isen-mediterranee.fr"
        not in allowed_domains
    ):
        allowed_domains.append(
            "educ.isen-mediterranee.fr"
        )


    lines = []

    lines.append(
        "# SecureExam STRICT POLICY v4"
    )

    lines.append(
        "# "
        + exam_id
        + " | "
        + exam_name
        + " | "
        + exam_date
        + " "
        + exam_time
    )

    lines.append("")
    lines.append(
        "{ config, pkgs, ... }:"
    )
    lines.append("")
    lines.append("{")
    lines.append("")


    # =====================================================
    # USER
    # =====================================================

    lines.append(
        "  users.users.exam = {"
    )

    lines.append(
        "    isNormalUser = true;"
    )

    lines.append(
        "    uid = 1500;"
    )

    lines.append(
        '    home = "/home/exam";'
    )

    lines.append(
        "    createHome = true;"
    )

    lines.append("")

    lines.append(
        "    extraGroups = ["
    )

    lines.append(
        '      "users"'
    )

    if sudo_allowed:
        lines.append(
            '      "wheel"'
        )

    lines.append(
        "    ];"
    )

    lines.append("")

    lines.append(
        "    packages = ["
    )

    if package_lines:
        lines.extend(
            package_lines
        )

    lines.append(
        "    ];"
    )

    lines.append(
        "  };"
    )

    lines.append("")


    # =====================================================
    # WORKSPACE
    # =====================================================

    lines.append(
        "  systemd.tmpfiles.rules = ["
    )

    lines.append(
        '    "d '
        + workspace
        + ' 0700 exam users -"'
    )

    lines.append(
        "  ];"
    )

    lines.append("")


    # =====================================================
    # SUDO
    # =====================================================

    lines.append(
        "  security.sudo.enable = true;"
    )

    if sudo_allowed:

        lines.append("")

        lines.append(
            "  security.sudo.extraRules = ["
        )

        lines.append(
            "    {"
        )

        lines.append(
            '      users = [ "exam" ];'
        )

        lines.append(
            "      commands = ["
        )

        lines.append(
            "        {"
        )

        lines.append(
            '          command = "ALL";'
        )

        lines.append(
            '          options = [ "NOPASSWD" ];'
        )

        lines.append(
            "        }"
        )

        lines.append(
            "      ];"
        )

        lines.append(
            "    }"
        )

        lines.append(
            "  ];"
        )

    lines.append("")


    # =====================================================
    # NIX ACCESS
    # =====================================================

    lines.append(
        "  nix.settings.allowed-users = ["
    )

    lines.append(
        '    "root"'
    )

    lines.append(
        '    "@wheel"'
    )

    lines.append(
        "  ];"
    )

    lines.append("")


    # =====================================================
    # POLKIT
    # =====================================================

    lines.append(
        "  security.polkit.enable = true;"
    )

    lines.append("")

    lines.append(
        "  security.polkit.extraConfig = ''"
    )

    lines.append(
        "    polkit.addRule(function(action, subject) {"
    )

    lines.append(
        '      if (subject.user === "exam") {'
    )

    lines.append(
        "        return polkit.Result.NO;"
    )

    lines.append(
        "      }"
    )

    lines.append(
        "    });"
    )

    lines.append(
        "  '';"
    )

    lines.append("")


    # =====================================================
    # SSH
    # =====================================================

    lines.append(
        "  services.openssh.settings.DenyUsers = ["
    )

    lines.append(
        '    "exam"'
    )

    lines.append(
        "  ];"
    )

    lines.append("")


    # =====================================================
    # NETWORK BASE
    # =====================================================

    lines.append(
        "  networking.firewall.enable = true;"
    )

    lines.append(
        "  networking.nftables.enable = true;"
    )

    lines.append("")


    # =====================================================
    # INTERNET COMPLET
    # =====================================================

    if internet_allowed:

        pass


    # =====================================================
    # INTERNET OFF + DOMAINES AUTORISES
    # =====================================================

    elif allowed_domains:

        lines.append(
            "  services.resolved.enable = true;"
        )

        lines.append("")

        lines.append(
            "  networking.nftables.ruleset = ''"
        )

        lines.append(
            "    table inet secureexam {"
        )

        lines.append(
            "      set allowed_v4 {"
        )

        lines.append(
            "        type ipv4_addr"
        )

        lines.append(
            "      }"
        )

        lines.append(
            "      set allowed_v6 {"
        )

        lines.append(
            "        type ipv6_addr"
        )

        lines.append(
            "      }"
        )

        lines.append(
            "      chain output {"
        )

        lines.append(
            "        type filter hook output priority -50;"
        )

        lines.append(
            "        policy accept;"
        )

        lines.append(
            '        meta skuid 1500 '
            'oifname "lo" accept'
        )

        lines.append(
            "        meta skuid 1500 "
            "ip daddr @allowed_v4 "
            "tcp dport { 80, 443 } accept"
        )

        lines.append(
            "        meta skuid 1500 "
            "ip6 daddr @allowed_v6 "
            "tcp dport { 80, 443 } accept"
        )

        lines.append(
            "        meta skuid 1500 reject"
        )

        lines.append(
            "      }"
        )

        lines.append(
            "    }"
        )

        lines.append(
            "  '';"
        )

        lines.append("")


        shell_domains = " ".join(
            json.dumps(domain)
            for domain in allowed_domains
        )


        lines.append(
            "  systemd.services."
            "secureexam-refresh-allowlist = {"
        )

        lines.append(
            "    after = ["
        )

        lines.append(
            '      "network-online.target"'
        )

        lines.append(
            '      "nftables.service"'
        )

        lines.append(
            '      "systemd-resolved.service"'
        )

        lines.append(
            "    ];"
        )

        lines.append("")

        lines.append(
            "    wants = ["
        )

        lines.append(
            '      "network-online.target"'
        )

        lines.append(
            "    ];"
        )

        lines.append("")

        lines.append(
            "    wantedBy = ["
        )

        lines.append(
            '      "multi-user.target"'
        )

        lines.append(
            "    ];"
        )

        lines.append("")

        lines.append(
            "    path = ["
        )

        lines.append(
            "      pkgs.nftables"
        )

        lines.append(
            "      pkgs.dnsutils"
        )

        lines.append(
            "      pkgs.gnugrep"
        )

        lines.append(
            "      pkgs.coreutils"
        )

        lines.append(
            "    ];"
        )

        lines.append("")

        lines.append(
            "    serviceConfig = {"
        )

        lines.append(
            '      Type = "oneshot";'
        )

        lines.append(
            "    };"
        )

        lines.append("")

        lines.append(
            "    script = ''"
        )

        lines.append(
            "      set -eu"
        )

        lines.append("")

        lines.append(
            "      nft flush set "
            "inet secureexam allowed_v4 "
            "|| true"
        )

        lines.append(
            "      nft flush set "
            "inet secureexam allowed_v6 "
            "|| true"
        )

        lines.append("")

        lines.append(
            "      for domain in "
            + shell_domains
            + "; do"
        )

        lines.append(
            '        for ip in $('
        )

        lines.append(
            '          dig +short A "$domain"'
        )

        lines.append(
            "          | grep -E "
            "'^[0-9]+(\\.[0-9]+){3}$'"
        )

        lines.append(
            "          || true"
        )

        lines.append(
            "        ); do"
        )

        lines.append(
            "          nft add element "
            "inet secureexam allowed_v4 "
            '"{ $ip }" || true'
        )

        lines.append(
            "        done"
        )

        lines.append("")

        lines.append(
            "        for ip in $("
        )

        lines.append(
            '          dig +short AAAA "$domain"'
        )

        lines.append(
            "          | grep ':'"
        )

        lines.append(
            "          || true"
        )

        lines.append(
            "        ); do"
        )

        lines.append(
            "          nft add element "
            "inet secureexam allowed_v6 "
            '"{ $ip }" || true'
        )

        lines.append(
            "        done"
        )

        lines.append(
            "      done"
        )

        lines.append(
            "    '';"
        )

        lines.append(
            "  };"
        )

        lines.append("")

        lines.append(
            "  systemd.timers."
            "secureexam-refresh-allowlist = {"
        )

        lines.append(
            "    wantedBy = ["
        )

        lines.append(
            '      "timers.target"'
        )

        lines.append(
            "    ];"
        )

        lines.append("")

        lines.append(
            "    timerConfig = {"
        )

        lines.append(
            '      OnBootSec = "5s";'
        )

        lines.append(
            '      OnUnitActiveSec = "2min";'
        )

        lines.append(
            "    };"
        )

        lines.append(
            "  };"
        )


    # =====================================================
    # INTERNET OFF TOTAL
    # =====================================================

    else:

        lines.append(
            "  networking.nftables.ruleset = ''"
        )

        lines.append(
            "    table inet secureexam {"
        )

        lines.append(
            "      chain output {"
        )

        lines.append(
            "        type filter hook output priority -50;"
        )

        lines.append(
            "        policy accept;"
        )

        lines.append(
            '        meta skuid 1500 '
            'oifname "lo" accept'
        )

        lines.append(
            "        meta skuid 1500 reject"
        )

        lines.append(
            "      }"
        )

        lines.append(
            "    }"
        )

        lines.append(
            "  '';"
        )


    lines.append("")
    lines.append("}")

    nix_text = "\n".join(lines) + "\n"

    nix_text = _secureexam_add_sandbox_v4(
        nix_text,
        package_lines
    )

    return _secureexam_finalize_nix_v4(
        nix_text,
        package_lines
    )

def save_support_request_to_database(
    request: SupportRequest,
    created_at: str,
    email_sent: int,
    teacher_id: int | None = None
) -> int:
    ensure_support_requests_teacher_scope()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO support_requests (
            teacher_id,
            full_name,
            email,
            subject,
            message,
            created_at,
            email_sent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        teacher_id,
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

    if "exam_name" not in columns:
        cursor.execute("""
            ALTER TABLE exam_configs
            ADD COLUMN exam_name TEXT
        """)

    if "exam_date" not in columns:
        cursor.execute("""
            ALTER TABLE exam_configs
            ADD COLUMN exam_date TEXT
        """)

    if "exam_time" not in columns:
        cursor.execute("""
            ALTER TABLE exam_configs
            ADD COLUMN exam_time TEXT
        """)

    cursor.execute("""
        UPDATE exam_configs
        SET teacher_id = 1
        WHERE teacher_id IS NULL
    """)

    cursor.execute("""
        UPDATE exam_configs
        SET exam_name = exam_id
        WHERE exam_name IS NULL OR TRIM(exam_name) = ''
    """)

    cursor.execute("""
        UPDATE exam_configs
        SET exam_date = ''
        WHERE exam_date IS NULL
    """)

    cursor.execute("""
        UPDATE exam_configs
        SET exam_time = ''
        WHERE exam_time IS NULL
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



def ensure_support_requests_teacher_scope():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("PRAGMA table_info(support_requests)")
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    if "teacher_id" not in columns:
        cursor.execute("""
            ALTER TABLE support_requests
            ADD COLUMN teacher_id INTEGER
        """)

    connection.commit()
    connection.close()


seed_default_teacher_account()
ensure_package_catalog_nix_names()
ensure_exam_configs_teacher_scope()
ensure_teacher_profile_scope()
ensure_support_requests_teacher_scope()


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
    username = (login_request.username or "").strip()
    password = login_request.password or ""

    teacher = get_teacher_by_username(username)

    if teacher is None:
        raise HTTPException(
            status_code=401,
            detail="Identifiant enseignant incorrect."
        )

    if not bool(teacher["is_active"]):
        raise HTTPException(
            status_code=401,
            detail="Compte désactivé."
        )

    if not verify_password(password, teacher["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Mot de passe enseignant incorrect."
        )

    access_token = create_access_token(
        data={
            "sub": teacher["username"],
            "username": teacher["username"],
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



@app.post("/teacher-support-requests")
def create_teacher_support_request(
    request: SupportRequest,
    current_teacher: dict = Depends(get_current_teacher)
):
    if not request.fullName.strip():
        raise HTTPException(status_code=400, detail="Le nom complet est obligatoire.")

    if not request.email.strip():
        raise HTTPException(status_code=400, detail="L'email est obligatoire.")

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Le message est obligatoire.")

    created_at = now_iso()

    request_id = save_support_request_to_database(
        request=request,
        created_at=created_at,
        email_sent=0,
        teacher_id=current_teacher["id"]
    )

    try:
        send_support_email(request)
        update_support_email_status(request_id, 1)
    except Exception as exc:
        update_support_email_status(request_id, 0)
        raise HTTPException(
            status_code=500,
            detail=f"Demande enregistrée, mais email non envoyé : {exc}"
        )

    return {
        "message": "Demande support envoyée par email avec succès.",
        "request_id": request_id,
        "email_sent": True
    }


@app.get("/support-requests-list")
def list_support_requests(current_teacher: dict = Depends(get_current_teacher)):
    ensure_support_requests_teacher_scope()

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
        WHERE teacher_id = ?
        ORDER BY id DESC
    """, (
        current_teacher["id"],
    ))

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
    exam_id = (config.exam_id or "").strip()

    if not exam_id:
        raise HTTPException(
            status_code=400,
            detail="L'identifiant de l'examen est obligatoire."
        )

    requested_packages = set(config.packages or [])
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

    # Configuration globale : le professeur ne choisit pas étudiant / machine / workspace.
    # Ces informations seront identifiées au lancement de l'examen.
    student_id = GLOBAL_STUDENT_ID
    machine_id = GLOBAL_MACHINE_ID
    workspace = GLOBAL_WORKSPACE

    exam_name = (config.exam_name or exam_id).strip() or exam_id
    exam_date = (config.exam_date or "").strip()
    exam_time = (config.exam_time or "").strip()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM exam_configs
        WHERE teacher_id = ?
        AND exam_id = ?
        LIMIT 1
    """, (
        teacher_id,
        exam_id
    ))

    existing_config = cursor.fetchone()

    if existing_config is not None:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail="Une configuration globale existe déjà pour cet examen. Supprimez l'ancienne configuration avant d'en recréer une."
        )

    created_at = now_iso()
    updated_at = created_at

    cursor.execute("""
        INSERT INTO exam_configs (
            teacher_id,
            exam_id,
            exam_name,
            exam_date,
            exam_time,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        teacher_id,
        exam_id,
        exam_name,
        exam_date,
        exam_time,
        student_id,
        machine_id,
        json.dumps(config.packages or [], ensure_ascii=False),
        int(config.sudo),
        int(config.internet),
        int(config.educ_access),
        json.dumps(config.allowed_domains or [], ensure_ascii=False),
        workspace,
        created_at,
        updated_at
    ))

    connection.commit()
    connection.close()

    filename = config_filename(
        exam_id,
        student_id,
        machine_id
    )

    return {
        "message": "Configuration globale d'examen enregistrée avec succès.",
        "file": filename,
        "created_at": created_at
    }



@app.get("/runtime/configs/{exam_id}/{student_id}/{machine_id}")
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
            exam_name,
            exam_date,
            exam_time,
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
            "exam_id": row["exam_id"],
            "exam_name": row["exam_name"] if "exam_name" in row.keys() and row["exam_name"] else row["exam_id"],
            "exam_date": row["exam_date"] if "exam_date" in row.keys() else "",
            "exam_time": row["exam_time"] if "exam_time" in row.keys() else "",
            "workspace": row["workspace"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "download_url": f"/configs/{filename}/download",
            "nixos_config_url": f"/configs/{filename}/nixos-config",
            "nixos_config_download_url": f"/configs/{filename}/nixos-config/download"
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
    row, safe_filename = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )

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
    row, _ = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )

    return row_to_config(row)


@app.delete("/configs/{filename}")
def delete_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, safe_filename = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM exam_configs
        WHERE exam_id = ?
        AND student_id = ?
        AND machine_id = ?
        AND teacher_id = ?
    """, (
        row["exam_id"],
        row["student_id"],
        row["machine_id"],
        current_teacher["id"]
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
            exam_name,
            exam_date,
            exam_time,
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
            "exam_id": row["exam_id"],
            "exam_name": row["exam_name"] if "exam_name" in row.keys() and row["exam_name"] else row["exam_id"],
            "exam_date": row["exam_date"] if "exam_date" in row.keys() else "",
            "exam_time": row["exam_time"] if "exam_time" in row.keys() else "",
            "workspace": row["workspace"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "download_url": f"/configs/{filename}/download",
            "nixos_config_url": f"/configs/{filename}/nixos-config",
            "nixos_config_download_url": f"/configs/{filename}/nixos-config/download"
        })

    cursor.execute("""
        SELECT
            s.exam_id,
            s.student_id,
            s.machine_id,
            s.filename,
            s.size_kb,
            s.created_at,
            c.created_at AS exam_created_at,
            c.updated_at AS exam_updated_at
        FROM submissions s
        INNER JOIN exam_configs c
            ON c.exam_id = s.exam_id
        WHERE c.teacher_id = ?
        ORDER BY c.created_at DESC, s.created_at DESC
    """, (
        current_teacher["id"],
    ))

    submission_rows = cursor.fetchall()

    submissions = []

    for row in submission_rows:
        submissions.append({
            "exam_id": row["exam_id"],
            "student_id": row["student_id"],
            "machine_id": row["machine_id"],
            "filename": row["filename"],
            "size_kb": row["size_kb"],
            "created_at": row["created_at"],
            "exam_created_at": row["exam_created_at"],
            "exam_updated_at": row["exam_updated_at"],
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




@app.get("/configs/{filename}/nixos-config")
def get_nixos_config_for_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, safe_filename = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )

    config_data = row_to_config(row)
    content = generate_nixos_config_preview(config_data)

    return {
        "filename": f"{Path(safe_filename).stem}_exam-configuration.nix",
        "source_config": safe_filename,
        "content": content
    }


@app.get("/configs/{filename}/nixos-config/download")
def download_nixos_config_for_config(
    filename: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    row, safe_filename = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )

    config_data = row_to_config(row)
    content = generate_nixos_config_preview(config_data)
    output_filename = f"{Path(safe_filename).stem}_exam-configuration.nix"

    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{output_filename}"'
        }
    )




# =========================================================
# SECUREEXAM_LEGACY_CONFIG_ROUTE_AFTER_NIXOS
# Compatibilité ancien exam-client.
#
# Cette route DOIT rester après :
# /configs/{filename}/nixos-config
# /configs/{filename}/nixos-config/download
# =========================================================

@app.get(
    "/configs/{exam_id}/{student_id}/{machine_id}"
)
def get_config_legacy(
    exam_id: str,
    student_id: str,
    machine_id: str
):
    return get_config(
        exam_id=exam_id,
        student_id=student_id,
        machine_id=machine_id
    )


@app.get("/nixos-config")
def get_nixos_config(current_teacher: dict = Depends(get_current_teacher)):
    metadata = ensure_generated_nixos_belongs_to_teacher(current_teacher)
    content = NIXOS_CONFIG_FILE.read_text(encoding="utf-8")

    return {
        "filename": NIXOS_CONFIG_FILE.name,
        "source_config": config_filename(
            metadata["exam_id"],
            metadata["student_id"],
            metadata["machine_id"]
        ),
        "content": content
    }


@app.get("/nixos-config/download")
def download_nixos_config(current_teacher: dict = Depends(get_current_teacher)):
    metadata = ensure_generated_nixos_belongs_to_teacher(current_teacher)

    return FileResponse(
        path=NIXOS_CONFIG_FILE,
        filename=f"{metadata['exam_id']}_{metadata['student_id']}_{metadata['machine_id']}_exam-configuration.nix",
        media_type="text/plain"
    )

# =========================================================
# SECUREEXAM SUPERVISOR AUTH
# =========================================================

from pydantic import BaseModel as _SupervisorBaseModel
from fastapi import HTTPException as _SupervisorHTTPException
import os as _supervisor_os
from datetime import datetime as _SupervisorDateTime, timedelta as _SupervisorTimedelta

class SupervisorLoginRequest(_SupervisorBaseModel):
    username: str
    password: str

@app.post("/supervisor/login")
def supervisor_login(payload: SupervisorLoginRequest):
    supervisor_username = _supervisor_os.getenv("SUPERVISOR_USERNAME", "surveillant")
    supervisor_password = _supervisor_os.getenv("SUPERVISOR_PASSWORD", "1234")

    entered_username = (payload.username or "").strip()
    entered_password = payload.password or ""

    if entered_username != supervisor_username:
        raise _SupervisorHTTPException(
            status_code=401,
            detail="Identifiant surveillant incorrect."
        )

    if entered_password != supervisor_password:
        raise _SupervisorHTTPException(
            status_code=401,
            detail="Mot de passe surveillant incorrect."
        )

    token_data = {
        "sub": supervisor_username,
        "username": supervisor_username,
        "role": "supervisor"
    }

    if "create_access_token" in globals():
        access_token = globals()["create_access_token"](data=token_data)
    else:
        expire = _SupervisorDateTime.utcnow() + _SupervisorTimedelta(hours=8)
        token_data.update({"exp": expire})
        access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": "supervisor",
        "username": supervisor_username
    }


# =========================================================
# SECUREEXAM SUPERVISOR PROFILE SUPPORT
# =========================================================

from pathlib import Path as _SupervisorPath
import sqlite3 as _supervisor_sqlite3
from datetime import datetime as _SupervisorDateTime
from typing import Optional as _SupervisorOptional
from fastapi import Header as _SupervisorHeader, Depends as _SupervisorDepends, HTTPException as _SupervisorHTTPException
from pydantic import BaseModel as _SupervisorBaseModel


def _supervisor_database_path():
    database_path = globals().get("DATABASE_PATH") or globals().get("DB_PATH")

    if database_path:
        return _SupervisorPath(database_path)

    return _SupervisorPath(__file__).resolve().parent / "database" / "secure_exam.db"


def _supervisor_connect():
    database_path = _supervisor_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = _supervisor_sqlite3.connect(str(database_path))
    connection.row_factory = _supervisor_sqlite3.Row
    return connection


def _supervisor_init_tables():
    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_profiles (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            full_name TEXT NOT NULL DEFAULT 'Surveillant',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            room TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_support_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            subject TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OUVERT',
            created_at TEXT NOT NULL
        )
    """)

    now = _SupervisorDateTime.utcnow().isoformat(timespec="seconds")

    cursor.execute("""
        INSERT OR IGNORE INTO supervisor_profiles (
            id, full_name, email, phone, room, notes, created_at, updated_at
        )
        VALUES (
            1,
            'Surveillant',
            'surveillant@isen.fr',
            '',
            '',
            'Compte surveillant utilisé pour la récupération des configurations NixOS.',
            ?,
            ?
        )
    """, (now, now))

    connection.commit()
    connection.close()


def _get_current_supervisor(authorization: _SupervisorOptional[str] = _SupervisorHeader(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _SupervisorHTTPException(status_code=401, detail="Token surveillant manquant.")

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[globals().get("ALGORITHM", "HS256")]
        )
    except Exception:
        raise _SupervisorHTTPException(status_code=401, detail="Token surveillant invalide.")

    if payload.get("role") != "supervisor":
        raise _SupervisorHTTPException(status_code=403, detail="Accès réservé au surveillant.")

    return payload


class SupervisorProfilePayload(_SupervisorBaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    room: str = ""
    notes: str = ""


class SupervisorSupportPayload(_SupervisorBaseModel):
    subject: str
    category: str
    priority: str
    message: str


@app.get("/supervisor/profile")
def get_supervisor_profile(current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)):
    _supervisor_init_tables()

    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM supervisor_profiles WHERE id = 1")
    row = cursor.fetchone()

    connection.close()

    if not row:
        raise _SupervisorHTTPException(status_code=404, detail="Profil surveillant introuvable.")

    return dict(row)


@app.put("/supervisor/profile")
def update_supervisor_profile(
    payload: SupervisorProfilePayload,
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    _supervisor_init_tables()

    now = _SupervisorDateTime.utcnow().isoformat(timespec="seconds")

    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE supervisor_profiles
        SET full_name = ?,
            email = ?,
            phone = ?,
            room = ?,
            notes = ?,
            updated_at = ?
        WHERE id = 1
    """, (
        payload.full_name.strip() or "Surveillant",
        payload.email.strip(),
        payload.phone.strip(),
        payload.room.strip(),
        payload.notes.strip(),
        now
    ))

    connection.commit()

    cursor.execute("SELECT * FROM supervisor_profiles WHERE id = 1")
    row = cursor.fetchone()

    connection.close()

    return dict(row)


@app.get("/supervisor/support")
def list_supervisor_support_requests(current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)):
    _supervisor_init_tables()

    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, username, subject, category, priority, message, status, created_at
        FROM supervisor_support_requests
        ORDER BY id DESC
    """)

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    return rows


@app.post("/supervisor/support")
def create_supervisor_support_request(
    payload: SupervisorSupportPayload,
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    _supervisor_init_tables()

    subject = payload.subject.strip()
    message = payload.message.strip()

    if not subject or not message:
        raise _SupervisorHTTPException(
            status_code=400,
            detail="Le sujet et le message sont obligatoires."
        )

    now = _SupervisorDateTime.utcnow().isoformat(timespec="seconds")
    username = current_supervisor.get("username") or current_supervisor.get("sub") or "surveillant"

    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO supervisor_support_requests (
            username, subject, category, priority, message, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'OUVERT', ?)
    """, (
        username,
        subject,
        payload.category.strip() or "Général",
        payload.priority.strip() or "Normale",
        message,
        now
    ))

    connection.commit()
    request_id = cursor.lastrowid

    cursor.execute("""
        SELECT id, username, subject, category, priority, message, status, created_at
        FROM supervisor_support_requests
        WHERE id = ?
    """, (request_id,))

    row = cursor.fetchone()
    connection.close()

    return dict(row)

# =========================================================
# SECUREEXAM SUPERVISOR PUBLIC SUPPORT
# =========================================================

@app.post("/supervisor/support/public")
def create_public_supervisor_support_request(payload: SupervisorSupportPayload):
    _supervisor_init_tables()

    subject = payload.subject.strip()
    message = payload.message.strip()

    if not subject or not message:
        raise _SupervisorHTTPException(
            status_code=400,
            detail="Le sujet et le message sont obligatoires."
        )

    now = _SupervisorDateTime.utcnow().isoformat(timespec="seconds")

    connection = _supervisor_connect()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO supervisor_support_requests (
            username, subject, category, priority, message, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'OUVERT', ?)
    """, (
        "visiteur_non_connecte",
        subject,
        payload.category.strip() or "Connexion",
        payload.priority.strip() or "Normale",
        message,
        now
    ))

    connection.commit()
    request_id = cursor.lastrowid

    cursor.execute("""
        SELECT id, username, subject, category, priority, message, status, created_at
        FROM supervisor_support_requests
        WHERE id = ?
    """, (request_id,))

    row = cursor.fetchone()
    connection.close()

    return dict(row)


# =========================================================
# SECUREEXAM SUPERVISOR CONFIGS
# =========================================================

@app.get("/supervisor/configs")
def list_supervisor_configs(
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            teacher_id,
            exam_id,
            exam_name,
            exam_date,
            exam_time,
            student_id,
            machine_id,
            workspace,
            created_at,
            updated_at
        FROM exam_configs
        ORDER BY updated_at DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    configs = []

    for row in rows:
        filename = config_filename(
            row["exam_id"],
            row["student_id"],
            row["machine_id"]
        )

        configs.append({
            "id": row["id"],
            "teacher_id": row["teacher_id"],
            "filename": filename,
            "exam_id": row["exam_id"],
            "exam_name": row["exam_name"] if "exam_name" in row.keys() and row["exam_name"] else row["exam_id"],
            "exam_date": row["exam_date"] if "exam_date" in row.keys() else "",
            "exam_time": row["exam_time"] if "exam_time" in row.keys() else "",
            "workspace": row["workspace"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "json_download_url": f"/supervisor/configs/{row['id']}/download",
            "nixos_config_url": f"/supervisor/configs/{row['id']}/nixos-config",
            "nixos_config_download_url": f"/supervisor/configs/{row['id']}/nixos-config/download"
        })

    return {
        "count": len(configs),
        "configs": configs
    }


@app.get("/supervisor/configs/{config_id}/download")
def download_supervisor_config(
    config_id: int,
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    row = get_config_row_by_id_or_404(config_id)
    config_data = row_to_config(row)

    filename = config_filename(
        row["exam_id"],
        row["student_id"],
        row["machine_id"]
    )

    return Response(
        content=json.dumps(config_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@app.get("/supervisor/configs/{config_id}/nixos-config")
def get_supervisor_nixos_config(
    config_id: int,
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    row = get_config_row_by_id_or_404(config_id)
    config_data = row_to_config(row)
    filename = config_filename(
        row["exam_id"],
        row["student_id"],
        row["machine_id"]
    )

    return {
        "filename": f"{Path(filename).stem}_exam-configuration.nix",
        "source_config": filename,
        "content": generate_nixos_config_preview(config_data)
    }


@app.get("/supervisor/configs/{config_id}/nixos-config/download")
def download_supervisor_nixos_config(
    config_id: int,
    current_supervisor: dict = _SupervisorDepends(_get_current_supervisor)
):
    row = get_config_row_by_id_or_404(config_id)
    config_data = row_to_config(row)

    filename = config_filename(
        row["exam_id"],
        row["student_id"],
        row["machine_id"]
    )

    output_filename = f"{Path(filename).stem}_exam-configuration.nix"

    return Response(
        content=generate_nixos_config_preview(config_data),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{output_filename}"'
        }
    )

# =========================================================
# SECUREEXAM RUNTIME IDENTIFICATION
# =========================================================

class ExamRuntimeIdentificationRequest(BaseModel):
    exam_id: str
    student_id: str
    machine_id: str
    workspace: Optional[str] = None


def ensure_exam_runtime_sessions_table():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_runtime_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            workspace TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'IDENTIFIED',
            created_at TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


@app.post("/exam-runtime/identify")
def identify_exam_runtime(payload: ExamRuntimeIdentificationRequest):
    ensure_exam_runtime_sessions_table()

    exam_id = payload.exam_id.strip()
    student_id = payload.student_id.strip()
    machine_id = payload.machine_id.strip()

    if not exam_id or not student_id or not machine_id:
        raise HTTPException(
            status_code=400,
            detail="Examen, étudiant et machine sont obligatoires au lancement de l'examen."
        )

    workspace = payload.workspace or f"/home/exam/{student_id}/workspace"
    created_at = now_iso()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO exam_runtime_sessions (
            exam_id,
            student_id,
            machine_id,
            workspace,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'IDENTIFIED', ?)
    """, (
        exam_id,
        student_id,
        machine_id,
        workspace,
        created_at
    ))

    connection.commit()
    session_id = cursor.lastrowid

    cursor.execute("""
        SELECT id, exam_id, student_id, machine_id, workspace, status, created_at
        FROM exam_runtime_sessions
        WHERE id = ?
    """, (
        session_id,
    ))

    row = cursor.fetchone()
    connection.close()

    return dict(row)


@app.get("/exam-runtime/sessions/{exam_id}")
def list_exam_runtime_sessions(
    exam_id: str,
    current_teacher: dict = Depends(get_current_teacher)
):
    ensure_exam_runtime_sessions_table()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, exam_id, student_id, machine_id, workspace, status, created_at
        FROM exam_runtime_sessions
        WHERE exam_id = ?
        ORDER BY id DESC
    """, (
        exam_id,
    ))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    return {
        "count": len(rows),
        "sessions": rows
    }


# =========================================================
# SECUREEXAM_SUPERVISOR_NIXOS_V1
# =========================================================

def _supervisor_get_exam_config_or_404(
    config_id: int
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            ec.*,
            COALESCE(
                tp.full_name,
                t.username,
                'Professeur'
            ) AS professor_name
        FROM exam_configs ec
        LEFT JOIN teacher_profiles tp
            ON tp.teacher_id = ec.teacher_id
        LEFT JOIN teachers t
            ON t.id = ec.teacher_id
        WHERE ec.id = ?
        LIMIT 1
    """, (
        config_id,
    ))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise _SupervisorHTTPException(
            status_code=404,
            detail="Configuration d'examen introuvable."
        )

    return row


@app.get("/supervisor/nixos-configs")
def list_supervisor_nixos_configs(
    current_supervisor: dict = _SupervisorDepends(
        _get_current_supervisor
    )
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            ec.*,
            COALESCE(
                tp.full_name,
                t.username,
                'Professeur'
            ) AS professor_name
        FROM exam_configs ec
        LEFT JOIN teacher_profiles tp
            ON tp.teacher_id = ec.teacher_id
        LEFT JOIN teachers t
            ON t.id = ec.teacher_id
        ORDER BY
            ec.updated_at DESC,
            ec.id DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    result = []

    for row in rows:

        keys = row.keys()

        exam_id = str(
            row["exam_id"] or ""
        ).strip()

        exam_name = (
            row["exam_name"]
            if (
                "exam_name" in keys
                and row["exam_name"]
            )
            else exam_id
        )

        exam_date = (
            row["exam_date"]
            if "exam_date" in keys
            else ""
        )

        exam_time = (
            row["exam_time"]
            if "exam_time" in keys
            else ""
        )

        result.append({
            "id": row["id"],
            "exam_id": exam_id,
            "exam_name": exam_name,
            "exam_date": exam_date or "",
            "exam_time": exam_time or "",
            "nix_filename":
                f"{exam_id}_exam-configuration.nix",
            "created_at":
                row["created_at"]
                if "created_at" in keys
                else None,
            "updated_at":
                row["updated_at"]
                if "updated_at" in keys
                else None
        })

    return result


@app.get(
    "/supervisor/nixos-configs/{config_id}"
)
def get_supervisor_nixos_config(
    config_id: int,
    current_supervisor: dict = _SupervisorDepends(
        _get_current_supervisor
    )
):
    row = _supervisor_get_exam_config_or_404(
        config_id
    )

    config_data = row_to_config(row)

    content = generate_nixos_config_preview(
        config_data
    )

    exam_id = config_data.get(
        "exam_id"
    ) or f"exam-{config_id}"

    return {
        "id": config_id,
        "exam_id": exam_id,
        "exam_name":
            config_data.get("exam_name")
            or exam_id,
        "professor_name": (
            row["professor_name"]
            if (
                "professor_name" in row.keys()
                and row["professor_name"]
            )
            else "Professeur"
        ),
        "filename":
            f"{exam_id}_exam-configuration.nix",
        "content": content
    }


@app.get(
    "/supervisor/nixos-configs/{config_id}/download"
)
def download_supervisor_nixos_config(
    config_id: int,
    current_supervisor: dict = _SupervisorDepends(
        _get_current_supervisor
    )
):
    row = _supervisor_get_exam_config_or_404(
        config_id
    )

    config_data = row_to_config(row)

    content = generate_nixos_config_preview(
        config_data
    )

    exam_id = config_data.get(
        "exam_id"
    ) or f"exam-{config_id}"

    output_filename = (
        f"{exam_id}_exam-configuration.nix"
    )

    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition":
                f'attachment; filename="{output_filename}"'
        }
    )


