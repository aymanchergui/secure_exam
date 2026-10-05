# =============================================================================
# SecureExam - Backend FastAPI
# API principale : authentification, examens, profils, rendus, supervision,
# administration, espace étudiant, agent SecureExam et génération NixOS.
# =============================================================================

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
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header
from fastapi import BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Initialisation de l'application et configuration globale
# -----------------------------------------------------------------------------
load_dotenv()
app = FastAPI(title="Plateforme Linux d'examen")
init_database()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
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


# -----------------------------------------------------------------------------
# Modèles de données partagés
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
# Utilitaires généraux
# -----------------------------------------------------------------------------
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


def load_teacher_profile(
    teacher_id: int
):
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
            CASE
                WHEN photo_data IS NOT NULL
                 AND length(photo_data) > 0
                THEN 1
                ELSE 0
            END AS has_photo

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
            detail=(
                "Profil professeur introuvable."
            )
        )
    return {
        "fullName": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "department": row["department"],
        "school": row["school"],
        "hasPhoto": bool(
            row["has_photo"]
        )
    }


def save_teacher_profile(
    profile: TeacherProfile,
    teacher_id: int
):
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
                created_at,
                updated_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            teacher_id,
            profile.fullName,
            profile.email,
            profile.role,
            profile.department,
            profile.school,
            current_time,
            current_time
        ))
    connection.commit()
    connection.close()


def update_teacher_photo_blob(
    photo_name: str,
    photo_type: str,
    photo_data: bytes,
    teacher_id: int
):
    ensure_teacher_profile_scope()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE teacher_profiles

        SET
            photo_name = ?,
            photo_type = ?,
            photo_data = ?,
            updated_at = ?

        WHERE teacher_id = ?
    """, (
        photo_name,
        photo_type,
        photo_data,
        now_iso(),
        teacher_id
    ))
    if cursor.rowcount != 1:
        connection.rollback()
        connection.close()
        raise HTTPException(
            status_code=404,
            detail=(
                "Profil professeur introuvable."
            )
        )
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


def get_config_row_by_id_or_404(config_id: int):
    """Charge une configuration d'examen par son identifiant interne."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """

            SELECT *

            FROM exam_configs

            WHERE id = ?

            LIMIT 1

            """,
            (config_id,)
        )
        row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Configuration d'examen introuvable."
        )
    return row


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
    package_lines: list[str],
    sudo_allowed: bool

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

__SECUREEXAM_SUDO_PACKAGE__

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
    if sudo_allowed:
        sudo_definition = r"""

  secureExamSandboxSudo =

    pkgs.writeShellScriptBin "sudo" ''

      while [ "$#" -gt 0 ]; do



        case "$1" in



          -n|-H|-E|-S)

            shift

            ;;



          -u)

            shift



            if [ "''${1:-root}" != "root" ]; then

              echo "SecureExam: seul sudo -u root est autoris?." >&2

              exit 1

            fi



            shift

            ;;



          --)

            shift

            break

            ;;



          *)

            break

            ;;



        esac



      done



      if [ "$#" -eq 0 ]; then

        exit 0

      fi



      exec "$@"

    '';

"""
        sandbox_header = sandbox_header.replace(
            "let\n",
            (
                "let\n\n"
                + sudo_definition.strip("\n")
                + "\n\n"
            ),
            1
        )
        sandbox_header = sandbox_header.replace(
            "__SECUREEXAM_SUDO_PACKAGE__",
            "    secureExamSandboxSudo",
            1
        )
        sandbox_header = sandbox_header.replace(
            '--uid "$uid"',
            '--uid 0',
            1
        )
        sandbox_header = sandbox_header.replace(
            '--gid "$gid"',
            '--gid 0',
            1
        )
    else:
        sandbox_header = sandbox_header.replace(
            "__SECUREEXAM_SUDO_PACKAGE__",
            "",
            1
        )
    sandbox_header = (
        sandbox_header
        .replace(
            "__SECUREEXAM_PACKAGES__",
            package_block
        )
        .strip("\n")
    )

    # Supprime les lignes vides qui cassent les continuations shell "\"
    sandbox_header = re.sub(
        r'\\\n(?:[ \t]*\n)+',
        '\\\n',
        sandbox_header
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

    # =====================================================
    # SECUREEXAM : JAMAIS DE ROOT SUR L'HOTE
    # =====================================================
    nix_text = nix_text.replace(
        '      "wheel"\n',
        '',
        1
    )
    nix_text = re.sub(
        r'\n  security\.sudo\.extraRules = \[\n.*?\n  \];\n',
        '\n',
        nix_text,
        count=1,
        flags=re.S
    )

    # UID dynamique :
    # la sécurité cible maintenant le compte "exam"
    # et non plus un UID numérique fixe.
    # UID 1500 conserv? explicitement pour le compte exam.
    # Le launcher continue de v?rifier l'UID host 1500.
    # nftables conserve meta skuid 1500.
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


def _secureexam_platform_domain() -> str:
    # SECUREEXAM PLATFORM ACCESS v1 : adresse configurable dans le .env du backend.
    from urllib.parse import urlsplit

    load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))
    raw_url = os.getenv("SECUREEXAM_PLATFORM_URL", "").strip()
    error = (
        "SECUREEXAM_PLATFORM_URL doit contenir une URL HTTPS de plateforme "
        "avec un domaine valide, sans identifiants, chemin, ni port autre que 443."
    )
    try:
        if not raw_url or any(ord(char) <= 32 for char in raw_url) or "\\" in raw_url:
            raise ValueError(error)
        parsed = urlsplit(raw_url)
        domain = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or not domain
            or len(domain) > 253
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in domain.split(".")
            )
        ):
            raise ValueError(error)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=error) from exc
    return domain


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
    educ_domains = {
        "educ.isen.fr",
        "educ.isen-mediterranee.fr"
    }
    allowed_domains = [
        domain
        for domain in allowed_domains
        if domain not in educ_domains
    ]
    if educ_access:
        allowed_domains.append(
            "educ.isen-mediterranee.fr"
        )
    # La plateforme reste accessible même lorsque Internet et EDUC sont désactivés.
    platform_domain = _secureexam_platform_domain()
    if platform_domain not in allowed_domains:
        allowed_domains.append(platform_domain)
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
            "        for ip in $(dig +short A \"$domain\" | grep -E '^[0-9]+(\\.[0-9]+){3}$' || true); do"
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
            "        for ip in $(dig +short AAAA \"$domain\" | grep ':' || true); do"
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
        package_lines,
        sudo_allowed
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
            photo_name TEXT,
            photo_type TEXT,
            photo_data BLOB,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        PRAGMA table_info(teacher_profiles)
    """)
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }
    if "photo_name" not in columns:
        cursor.execute("""
            ALTER TABLE teacher_profiles
            ADD COLUMN photo_name TEXT
        """)
    if "photo_type" not in columns:
        cursor.execute("""
            ALTER TABLE teacher_profiles
            ADD COLUMN photo_type TEXT
        """)
    if "photo_data" not in columns:
        cursor.execute("""
            ALTER TABLE teacher_profiles
            ADD COLUMN photo_data BLOB
        """)
    connection.commit()
    cursor.execute("""
        PRAGMA table_info(teacher_profiles)
    """)
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    # ========================================================
    # MIGRATION LEGACY :
    # photo_path -> photo_data BLOB
    # ========================================================
    if "photo_path" in columns:
        cursor.execute("""
            SELECT
                id,
                photo_path,
                photo_data

            FROM teacher_profiles
        """)
        rows = cursor.fetchall()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp"
        }
        for row in rows:
            old_path = str(
                row["photo_path"]
                or ""
            ).strip()
            if (
                row["photo_data"] is not None
                or not old_path
            ):
                continue
            source = Path(old_path)
            if not source.is_absolute():
                source = (
                    BASE_DIR
                    / source
                )
            if not source.is_file():
                print(
                    "[SecureExam] "
                    "ancienne photo absente :",
                    source
                )
                continue
            data = source.read_bytes()
            if not data:
                continue
            extension = (
                source
                .suffix
                .lower()
            )
            cursor.execute("""
                UPDATE teacher_profiles

                SET
                    photo_name = ?,
                    photo_type = ?,
                    photo_data = ?

                WHERE id = ?
            """, (
                source.name,
                media_types.get(
                    extension,
                    "application/octet-stream"
                ),
                data,
                row["id"]
            ))
        connection.commit()

        # Reconstruire la table afin de supprimer
        # définitivement l'ancienne colonne photo_path.
        cursor.execute("""
            DROP TABLE IF EXISTS
            teacher_profiles_blob_tmp
        """)
        cursor.execute("""
            CREATE TABLE
            teacher_profiles_blob_tmp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT NOT NULL,
                school TEXT NOT NULL,
                photo_name TEXT,
                photo_type TEXT,
                photo_data BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            INSERT INTO
            teacher_profiles_blob_tmp (
                id,
                teacher_id,
                full_name,
                email,
                role,
                department,
                school,
                photo_name,
                photo_type,
                photo_data,
                created_at,
                updated_at
            )

            SELECT
                id,
                teacher_id,
                full_name,
                email,
                role,
                department,
                school,
                photo_name,
                photo_type,
                photo_data,
                created_at,
                updated_at

            FROM teacher_profiles
        """)
        cursor.execute("""
            DROP TABLE teacher_profiles
        """)
        cursor.execute("""
            ALTER TABLE
            teacher_profiles_blob_tmp

            RENAME TO
            teacher_profiles
        """)
        connection.commit()

    # ========================================================
    # PROFILS MANQUANTS
    # ========================================================
    current_time = now_iso()
    cursor.execute("""
        SELECT
            id,
            username

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
        if cursor.fetchone() is not None:
            continue
        cursor.execute("""
            INSERT INTO teacher_profiles (
                teacher_id,
                full_name,
                email,
                role,
                department,
                school,
                created_at,
                updated_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            teacher["id"],
            teacher["username"],
            f"{teacher['username']}@isen.fr",
            "Enseignant",
            "Département informatique",
            "ISEN",
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

# =========================================================
# SECUREEXAM_OFFICIAL_ENVIRONMENTS_V3
#
# Ces paquets sont nécessaires aux environnements
# officiels SecureExam.
#
# Ils sont :
# - créés automatiquement s'ils n'existent pas ;
# - réactivés automatiquement s'ils ont été désactivés ;
# - protégés contre désactivation / suppression.
# =========================================================
OFFICIAL_EXAM_PACKAGE_CATALOG_V3 = [
    {
        "name": "python3",
        "nix_name": "python3",
        "display_name": "Python 3",
        "description":
            "Interpréteur Python 3 pour algorithmique et scripting."
    },
    {
        "name": "vim",
        "nix_name": "vim",
        "display_name": "Vim",
        "description":
            "Éditeur de texte pour les environnements d'examen."
    },
    {
        "name": "gcc",
        "nix_name": "gcc",
        "display_name": "GCC",
        "description":
            "Compilateur GNU pour C et C++."
    },
    {
        "name": "gdb",
        "nix_name": "gdb",
        "display_name": "GDB",
        "description":
            "Débogueur GNU pour C et C++."
    },
    {
        "name": "gnumake",
        "nix_name": "gnumake",
        "display_name": "Make",
        "description":
            "GNU Make pour compilation et automatisation."
    },
    {
        "name": "jdk21",
        "nix_name": "jdk21",
        "display_name": "JDK 21",
        "description":
            "Kit de développement Java 21."
    },
    {
        "name": "maven",
        "nix_name": "maven",
        "display_name": "Maven",
        "description":
            "Gestionnaire de build pour projets Java."
    },
    {
        "name": "nodejs",
        "nix_name": "nodejs",
        "display_name": "Node.js",
        "description":
            "Runtime JavaScript Node.js pour développement Web."
    },
    {
        "name": "sqlite",
        "nix_name": "sqlite",
        "display_name": "SQLite",
        "description":
            "Base de données SQL locale légère."
    },
    {
        "name": "postgresql",
        "nix_name": "postgresql",
        "display_name": "PostgreSQL",
        "description":
            "Système de gestion de base de données PostgreSQL."
    },
    {
        "name": "bash",
        "nix_name": "bash",
        "display_name": "Bash",
        "description":
            "Shell GNU Bash."
    },
    {
        "name": "coreutils",
        "nix_name": "coreutils",
        "display_name": "GNU Coreutils",
        "description":
            "Commandes Unix fondamentales."
    },
    {
        "name": "gnugrep",
        "nix_name": "gnugrep",
        "display_name": "GNU Grep",
        "description":
            "Recherche et filtrage de texte."
    },
    {
        "name": "gnused",
        "nix_name": "gnused",
        "display_name": "GNU Sed",
        "description":
            "Transformation de flux texte."
    },
    {
        "name": "gawk",
        "nix_name": "gawk",
        "display_name": "GNU Awk",
        "description":
            "Traitement de données et de texte."
    }
]
OFFICIAL_EXAM_NIX_NAMES_V3 = {
    package["nix_name"]
    for package
    in OFFICIAL_EXAM_PACKAGE_CATALOG_V3
}
OFFICIAL_EXAM_NAMES_V3 = {
    package["name"]
    for package
    in OFFICIAL_EXAM_PACKAGE_CATALOG_V3
}


def is_official_exam_package_v3(
    package

) -> bool:
    if package is None:
        return False
    try:
        name = str(
            package["name"]
            or ""
        ).strip()
        nix_name = str(
            package["nix_name"]
            or ""
        ).strip()
    except Exception:
        return False
    return (
        name
        in OFFICIAL_EXAM_NAMES_V3
        or nix_name
        in OFFICIAL_EXAM_NIX_NAMES_V3
    )


def ensure_official_exam_packages_v3():

    # Cette fonction maintient l'invariant :
    # toutes les configurations officielles
    # doivent toujours être utilisables.
    ensure_package_catalog_nix_names()
    connection = get_connection()
    cursor = connection.cursor()
    current_time = now_iso()
    for package in (
        OFFICIAL_EXAM_PACKAGE_CATALOG_V3
    ):
        cursor.execute("""

            SELECT

                id,

                name,

                nix_name,

                is_active



            FROM package_catalog



            WHERE

                LOWER(name) = LOWER(?)

                OR LOWER(nix_name) = LOWER(?)



            LIMIT 1

        """, (
            package["name"],
            package["nix_name"]
        ))
        existing = cursor.fetchone()
        if existing is None:
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
                package["name"],
                package["nix_name"],
                package["display_name"],
                package["description"],
                1,
                current_time,
                current_time
            ))
            print(
                "[SecureExam] paquet officiel ajouté :",
                package["display_name"]
            )
        else:

            # On conserve le name existant pour ne pas
            # casser d'anciennes configurations.
            #
            # Exemple :
            # name = make
            # nix_name = gnumake
            cursor.execute("""

                UPDATE package_catalog



                SET

                    nix_name = ?,

                    display_name = ?,

                    description = ?,

                    is_active = 1,

                    updated_at = ?



                WHERE id = ?

            """, (
                package["nix_name"],
                package["display_name"],
                package["description"],
                current_time,
                existing["id"]
            ))
    connection.commit()
    connection.close()
    print(
        "[SecureExam] environnements officiels prêts."
    )


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
        package["canDelete"] = usage_count == 0 and not is_official_exam_package_v3(row)
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
    if is_official_exam_package_v3(
        package
    ):
        connection.close()
        raise HTTPException(
            status_code=409,
            detail={
                "message":
                    "Ce logiciel appartient à un "

                    "environnement officiel SecureExam "

                    "et ne peut pas être supprimé.",
                "usageCount":
                    1
            }
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
    if is_official_exam_package_v3(
        package
    ):
        connection.close()
        raise HTTPException(
            status_code=409,
            detail=(
                "Ce logiciel appartient à un "

                "environnement officiel SecureExam "

                "et doit rester actif."
            )
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
def get_teacher_profile(
    current_teacher: dict = Depends(
        get_current_teacher
    )
):
    profile = load_teacher_profile(
        current_teacher["id"]
    )
    has_photo = bool(
        profile["hasPhoto"]
    )
    return {
        "fullName":
            profile["fullName"],
        "email":
            profile["email"],
        "role":
            profile["role"],
        "department":
            profile["department"],
        "school":
            profile["school"],
        "hasPhoto":
            has_photo,
        "photoUrl": (
            f"/teacher-profile/photo/"
            f"{current_teacher['id']}"
            if has_photo
            else ""
        )
    }


@app.put("/teacher-profile")
def update_teacher_profile(
    profile: TeacherProfile,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):
    save_teacher_profile(
        profile,
        current_teacher["id"]
    )
    return {
        "message":
            "Profil professeur "
            "mis à jour avec succès.",
        "profile":
            profile.model_dump()
    }


@app.post("/teacher-profile/photo")
async def upload_teacher_profile_photo(
    photo: UploadFile = File(...),
    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):
    if photo.filename is None:
        raise HTTPException(
            status_code=400,
            detail="Fichier image invalide."
        )
    safe_filename = Path(
        photo.filename
    ).name
    extension = Path(
        safe_filename
    ).suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp"
    }
    if extension not in media_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "Format image non autorisé. "
                "Utilisez PNG, JPG, JPEG ou WEBP."
            )
        )
    photo_data = await photo.read()
    if not photo_data:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le fichier image est vide."
            )
        )
    max_size = (
        10
        * 1024
        * 1024
    )
    if len(photo_data) > max_size:
        raise HTTPException(
            status_code=413,
            detail=(
                "La photo dépasse "
                "la taille maximale de 10 Mo."
            )
        )
    teacher_id = (
        current_teacher["id"]
    )
    update_teacher_photo_blob(
        photo_name=safe_filename,
        photo_type=(
            media_types[extension]
        ),
        photo_data=photo_data,
        teacher_id=teacher_id
    )
    return {
        "message":
            "Photo de profil "
            "mise à jour avec succès.",
        "photoUrl":
            f"/teacher-profile/photo/"
            f"{teacher_id}"
    }


@app.get(
    "/teacher-profile/photo/{teacher_id}"
)
def get_teacher_profile_photo_by_teacher(
    teacher_id: int
):
    ensure_teacher_profile_scope()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            photo_name,
            photo_type,
            photo_data

        FROM teacher_profiles

        WHERE teacher_id = ?

        LIMIT 1
    """, (
        teacher_id,
    ))
    row = cursor.fetchone()
    connection.close()
    if (
        row is None
        or row["photo_data"] is None
        or len(row["photo_data"]) == 0
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Photo de profil introuvable."
            )
        )
    filename = str(
        row["photo_name"]
        or f"profile_teacher_{teacher_id}"
    ).replace(
        '"',
        ""
    )
    return Response(
        content=bytes(
            row["photo_data"]
        ),
        media_type=(
            row["photo_type"]
            or "application/octet-stream"
        ),
        headers={
            "Content-Disposition":
                f'inline; filename="{filename}"',
            "Cache-Control":
                "no-store"
        }
    )


@app.get("/teacher-profile/photo")
def get_teacher_profile_photo():
    return (
        get_teacher_profile_photo_by_teacher(
            1
        )
    )


def _send_support_email_background(
    request_id: int,
    request: SupportRequest
) -> None:
    """
    Envoie l'email après la réponse HTTP.
    La demande est déjà enregistrée en base avant cette étape.
    """
    try:
        send_support_email(request)
        update_support_email_status(
            request_id,
            1
        )
    except Exception as exc:
        try:
            update_support_email_status(
                request_id,
                0
            )
        except Exception:
            pass
        print(
            f"[SUPPORT] Email non envoyé "
            f"pour la demande #{request_id}: {exc}"
        )


@app.post("/support-requests")
def create_support_request(
    request: SupportRequest,
    background_tasks: BackgroundTasks
):
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

    # La demande est enregistrée immédiatement.
    request_id = save_support_request_to_database(
        request=request,
        created_at=created_at,
        email_sent=0
    )

    # L'email part ensuite sans bloquer le navigateur.
    background_tasks.add_task(
        _send_support_email_background,
        request_id,
        request
    )
    return {
        "message":
            "Votre demande de support a bien été enregistrée "
            "et transmise au support.",
        "request_id": request_id
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


@app.post("/configs-legacy-without-roster")
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
    """

    Supprime une configuration appartenant au professeur connecté.



    La suppression est atomique et respecte l'ordre des dépendances :

    exam_roster_students -> exam_rosters -> exam_configs.



    Si l'examen n'existe plus pour aucun autre professeur, les affectations

    étudiantes associées à cet exam_id sont également retirées afin qu'un

    examen supprimé ne reste pas visible dans l'espace étudiant.

    """
    import sqlite3
    row, safe_filename = get_config_row_by_filename_or_404(
        filename,
        current_teacher["id"]
    )
    config_id = int(row["id"])
    exam_id = str(row["exam_id"])
    teacher_id = int(current_teacher["id"])
    connection = get_connection()
    try:
        connection.execute("PRAGMA busy_timeout = 10000")
        cursor = connection.cursor()

        # -------------------------------------------------
        # 1. Supprimer les lignes du CSV liées au roster
        # -------------------------------------------------
        cursor.execute(
            """

            SELECT id

            FROM exam_rosters

            WHERE exam_config_id = ?

            """,
            (config_id,)
        )
        roster_ids = [
            int(roster["id"])
            for roster in cursor.fetchall()
        ]
        deleted_roster_students = 0
        for roster_id in roster_ids:
            cursor.execute(
                """

                DELETE FROM exam_roster_students

                WHERE roster_id = ?

                """,
                (roster_id,)
            )
            deleted_roster_students += max(cursor.rowcount, 0)

        # -------------------------------------------------
        # 2. Supprimer le roster lié à la configuration
        # -------------------------------------------------
        cursor.execute(
            """

            DELETE FROM exam_rosters

            WHERE exam_config_id = ?

            """,
            (config_id,)
        )
        deleted_rosters = max(cursor.rowcount, 0)

        # -------------------------------------------------
        # 3. Vérifier si le même exam_id existe ailleurs
        # -------------------------------------------------
        cursor.execute(
            """

            SELECT COUNT(*) AS total

            FROM exam_configs

            WHERE exam_id = ?

              AND id <> ?

            """,
            (exam_id, config_id)
        )
        other_configs = int(cursor.fetchone()["total"])

        # Les affectations ne portent pas teacher_id/config_id dans le modèle
        # actuel. On ne les retire que si cette config est la dernière
        # portant cet exam_id, pour éviter de toucher un autre professeur.
        deleted_assignments = 0
        if other_configs == 0:
            cursor.execute(
                """

                DELETE FROM student_exam_assignments

                WHERE exam_id = ?

                """,
                (exam_id,)
            )
            deleted_assignments = max(cursor.rowcount, 0)

        # -------------------------------------------------
        # 4. Supprimer la configuration elle-même
        # -------------------------------------------------
        cursor.execute(
            """

            DELETE FROM exam_configs

            WHERE id = ?

              AND teacher_id = ?

            """,
            (config_id, teacher_id)
        )
        if cursor.rowcount != 1:
            raise HTTPException(
                status_code=404,
                detail="Configuration introuvable ou déjà supprimée."
            )
        connection.commit()
        print(
            "[SecureExam] configuration supprimée :",
            exam_id,
            {
                "roster_students": deleted_roster_students,
                "rosters": deleted_rosters,
                "student_assignments": deleted_assignments,
            }
        )
        return {
            "success": True,
            "message": "Configuration supprimée avec succès.",
            "file": safe_filename,
            "exam_id": exam_id,
            "deleted": {
                "roster_students": deleted_roster_students,
                "rosters": deleted_rosters,
                "student_assignments": deleted_assignments,
            },
        }
    except HTTPException:
        connection.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        connection.rollback()

        # Diagnostic lisible au lieu d'un 500 brut.
        raise HTTPException(
            status_code=409,
            detail=(
                "Impossible de supprimer cette configuration car une donnée "

                "SecureExam y est encore liée."
            )
        ) from exc
    except sqlite3.OperationalError as exc:
        connection.rollback()
        if "locked" in str(exc).lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    "La base SQLite est temporairement occupée. "

                    "Réessayez dans quelques secondes."
                )
            ) from exc
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.post("/submissions")
async def upload_submission(
    exam_id: str = Form(...),
    student_id: str = Form(...),
    machine_id: str = Form(...),
    archive: UploadFile = File(...),
    x_secureexam_agent_token:
        str | None
        = Header(default=None)
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    exam_id = (
        exam_id
        or ""
    ).strip()
    student_id = (
        student_id
        or ""
    ).strip()
    machine_id = (
        machine_id
        or ""
    ).strip()
    if (
        not exam_id
        or not student_id
        or not machine_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Examen, étudiant et machine "
                "sont obligatoires."
            )
        )
    if (
        archive.filename is None
        or not archive.filename
        .lower()
        .endswith(".zip")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Seules les archives ZIP "
                "sont acceptées."
            )
        )
    safe_filename = Path(
        archive.filename
    ).name
    archive_data = await archive.read()
    if not archive_data:
        raise HTTPException(
            status_code=400,
            detail="L'archive ZIP est vide."
        )
    size_kb = round(
        len(archive_data) / 1024,
        2
    )
    content_type = (
        archive.content_type
        or "application/zip"
    )
    created_at = now_text()
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT 1
            FROM exam_configs
            WHERE exam_id = ?
            LIMIT 1
        """, (
            exam_id,
        ))
        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Examen introuvable."
            )
        cursor.execute("""
            INSERT INTO submissions (
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
                ?, ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(filename)

            DO UPDATE SET
                exam_id = excluded.exam_id,
                student_id = excluded.student_id,
                machine_id = excluded.machine_id,
                size_kb = excluded.size_kb,
                content_type = excluded.content_type,
                file_data = excluded.file_data,
                created_at = excluded.created_at
        """, (
            exam_id,
            student_id,
            machine_id,
            safe_filename,
            size_kb,
            content_type,
            archive_data,
            created_at
        ))
        connection.commit()
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "message":
            "Archive reçue et enregistrée "
            "dans la base avec succès.",
        "file":
            safe_filename,
        "size_kb":
            size_kb
    }


@app.get("/submissions-list")
def list_submissions(
    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            s.filename

        FROM submissions s

        WHERE EXISTS (
            SELECT 1

            FROM exam_configs c

            WHERE c.exam_id = s.exam_id
              AND c.teacher_id = ?
        )

        ORDER BY
            s.created_at DESC
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


# SECUREEXAM_BULK_SUBMISSIONS_V1_BEGIN
def _secureexam_bulk_name(value, fallback):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or ""))
    safe = safe.strip("._-")[:80] or fallback
    if safe.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        safe = "_" + safe
    return safe


@app.get("/submissions-bulk-download")
def secureexam_download_all_submissions(
    exam_id: str,
    current_teacher: dict = Depends(get_current_teacher),
):
    from itertools import chain
    from tempfile import NamedTemporaryFile
    from zipfile import ZipFile, ZIP_STORED
    from starlette.background import BackgroundTask
    from starlette.responses import FileResponse

    exam_id = exam_id.strip()
    if not exam_id or len(exam_id) > 255:
        raise HTTPException(status_code=400, detail="Identifiant d'examen invalide.")
    connection = get_connection()
    temporary_path = None
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT s.rowid AS submission_id, s.student_id, s.machine_id,
                   s.filename, s.created_at, s.file_data
            FROM submissions s
            WHERE s.exam_id = ?
              AND EXISTS (
                  SELECT 1 FROM exam_configs c
                  WHERE c.exam_id = s.exam_id AND c.teacher_id = ?
              )
            ORDER BY s.student_id, s.created_at, s.rowid
        """, (exam_id, current_teacher["id"]))
        first = cursor.fetchone()
        if first is None:
            raise HTTPException(
                status_code=404,
                detail="Aucun rendu disponible pour cet examen.",
            )
        with NamedTemporaryFile(prefix="secureexam-rendus-", suffix=".zip", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        exam_folder = _secureexam_bulk_name(exam_id, "examen")
        manifest = {"exam_id": exam_id, "count": 0, "submissions": []}
        student_folders = {}
        used_student_folders = set()
        # Une archive étudiante à la fois ; les ZIP existants restent intacts.
        with ZipFile(temporary_path, "w", compression=ZIP_STORED, allowZip64=True) as archive:
            for row in chain((first,), cursor):
                if row["file_data"] is None or len(row["file_data"]) == 0:
                    raise HTTPException(
                        status_code=409,
                        detail="Un rendu ne contient pas son archive. Le téléchargement global a été annulé.",
                    )
                student_key = str(row["student_id"] or "")
                if student_key not in student_folders:
                    candidate = _secureexam_bulk_name(student_key, "etudiant")
                    if candidate.casefold() in used_student_folders:
                        candidate += f"-groupe-{row['submission_id']}"
                    student_folders[student_key] = candidate
                    used_student_folders.add(candidate.casefold())
                student_folder = student_folders[student_key]
                original_leaf = str(row["filename"] or "rendu.zip").replace("\\", "/").rsplit("/", 1)[-1]
                leaf = _secureexam_bulk_name(original_leaf, "rendu.zip")
                if not leaf.lower().endswith(".zip"):
                    leaf += ".zip"
                entry = f"{exam_folder}/{student_folder}/rendu-{row['submission_id']}-{leaf}"
                archive.writestr(entry, row["file_data"])
                manifest["submissions"].append({
                    "student_id": row["student_id"],
                    "machine_id": row["machine_id"],
                    "filename": row["filename"],
                    "created_at": row["created_at"],
                    "archive_entry": entry,
                })
                manifest["count"] += 1
            archive.writestr(
                f"{exam_folder}/manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        return FileResponse(
            str(temporary_path),
            filename=f"{exam_folder}_tous_les_rendus.zip",
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "X-SecureExam-Submission-Count": str(manifest["count"]),
            },
            background=BackgroundTask(temporary_path.unlink, missing_ok=True),
        )
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
# SECUREEXAM_BULK_SUBMISSIONS_V1_END

@app.get(
    "/submissions/{filename}/download"
)
def download_submission(
    filename: str,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):
    safe_filename = Path(
        filename
    ).name
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            s.file_data,
            s.content_type

        FROM submissions s

        WHERE s.filename = ?

          AND EXISTS (
              SELECT 1

              FROM exam_configs c

              WHERE c.exam_id = s.exam_id
                AND c.teacher_id = ?
          )

        LIMIT 1
    """, (
        safe_filename,
        current_teacher["id"]
    ))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Archive introuvable."
        )
    if row["file_data"] is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Archive présente en base "
                "mais contenu binaire absent."
            )
        )
    download_filename = (
        safe_filename.replace(
            '"',
            ""
        )
    )
    return Response(
        content=bytes(
            row["file_data"]
        ),
        media_type=(
            row["content_type"]
            or "application/zip"
        ),
        headers={
            "Content-Disposition":
                f'attachment; filename="{download_filename}"'
        }
    )


@app.delete(
    "/submissions/{filename}"
)
def delete_submission(
    filename: str,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):
    safe_filename = Path(
        filename
    ).name
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT
                s.id

            FROM submissions s

            WHERE s.filename = ?

              AND EXISTS (
                  SELECT 1

                  FROM exam_configs c

                  WHERE c.exam_id = s.exam_id
                    AND c.teacher_id = ?
              )

            LIMIT 1
        """, (
            safe_filename,
            current_teacher["id"]
        ))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Archive introuvable."
            )
        cursor.execute("""
            DELETE FROM submissions
            WHERE id = ?
        """, (
            row["id"],
        ))
        connection.commit()
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "message":
            "Archive supprimée avec succès.",
        "file":
            safe_filename
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
            ec.id,
            ec.exam_id,
            ec.exam_name,
            ec.exam_date,
            ec.exam_time,
            ec.student_id,
            ec.machine_id,
            ec.workspace,
            ec.created_at,
            ec.updated_at,

            er.original_filename
                AS roster_filename,

            er.students_count
                AS roster_count,

            er.status
                AS roster_status,

            er.sent_at

        FROM exam_configs ec

        LEFT JOIN exam_rosters er
            ON er.exam_config_id = ec.id

        WHERE ec.teacher_id = ?

        ORDER BY
            ec.updated_at DESC,
            ec.id DESC

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

            "id":
                int(row["id"]),

            "filename":
                filename,

            "exam_id":
                row["exam_id"],

            "exam_name":
                (
                    row["exam_name"]
                    if (
                        "exam_name" in row.keys()
                        and row["exam_name"]
                    )
                    else row["exam_id"]
                ),

            "exam_date":
                (
                    row["exam_date"]
                    if "exam_date" in row.keys()
                    else ""
                ),

            "exam_time":
                (
                    row["exam_time"]
                    if "exam_time" in row.keys()
                    else ""
                ),

            "workspace":
                row["workspace"],

            "created_at":
                row["created_at"],

            "updated_at":
                row["updated_at"],

            # ===============================================
            # MEME SOURCE DE VERITE QUE ADMIN
            # ===============================================

            "roster_filename":
                (
                    row["roster_filename"]
                    if (
                        "roster_filename" in row.keys()
                        and row["roster_filename"]
                    )
                    else ""
                ),

            "roster_count":
                (
                    int(
                        row["roster_count"]
                        or 0
                    )
                    if "roster_count" in row.keys()
                    else 0
                ),

            "roster_status":
                (
                    row["roster_status"]
                    if (
                        "roster_status" in row.keys()
                        and row["roster_status"]
                    )
                    else "MISSING"
                ),

            "sent_at":
                (
                    row["sent_at"]
                    if "sent_at" in row.keys()
                    else None
                ),

            "download_url":
                f"/configs/{filename}/download",

            "nixos_config_url":
                f"/configs/{filename}/nixos-config",

            "nixos_config_download_url":
                f"/configs/{filename}/nixos-config/download"

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
# SECUREEXAM ADMIN AUTH
# =========================================================
from pydantic import BaseModel as _AdminBaseModel
from fastapi import HTTPException as _AdminHTTPException
import os as _admin_os
from datetime import datetime as _AdminDateTime, timedelta as _AdminTimedelta

class AdminLoginRequest(_AdminBaseModel):
    username: str
    password: str


@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest):
    admin_username = _admin_os.getenv("ADMIN_USERNAME", "administrateur")
    admin_password = _admin_os.getenv("ADMIN_PASSWORD", "1234")
    entered_username = (payload.username or "").strip()
    entered_password = payload.password or ""
    if entered_username != admin_username:
        raise _AdminHTTPException(
            status_code=401,
            detail="Identifiant administrateur incorrect."
        )
    if entered_password != admin_password:
        raise _AdminHTTPException(
            status_code=401,
            detail="Mot de passe administrateur incorrect."
        )
    token_data = {
        "sub": admin_username,
        "username": admin_username,
        "role": "admin"
    }
    if "create_access_token" in globals():
        access_token = globals()["create_access_token"](data=token_data)
    else:
        expire = _AdminDateTime.utcnow() + _AdminTimedelta(hours=8)
        token_data.update({"exp": expire})
        access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": "admin",
        "username": admin_username
    }

# =========================================================
# SECUREEXAM ADMIN PROFILE SUPPORT
# =========================================================
from pathlib import Path as _AdminPath
import sqlite3 as _admin_sqlite3
from datetime import datetime as _AdminDateTime
from typing import Optional as _AdminOptional
from fastapi import Header as _AdminHeader, Depends as _AdminDepends, HTTPException as _AdminHTTPException
from pydantic import BaseModel as _AdminBaseModel

def _admin_database_path():
    database_path = globals().get("DATABASE_PATH") or globals().get("DB_PATH")
    if database_path:
        return _AdminPath(database_path)
    return _AdminPath(__file__).resolve().parent / "database" / "secure_exam.db"


def _admin_connect():
    database_path = _admin_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _admin_sqlite3.connect(str(database_path))
    connection.row_factory = _admin_sqlite3.Row
    return connection


def _admin_init_tables():
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS admin_profiles (

            id INTEGER PRIMARY KEY CHECK (id = 1),

            full_name TEXT NOT NULL DEFAULT 'Administrateur',

            email TEXT NOT NULL DEFAULT '',

            phone TEXT NOT NULL DEFAULT '',

            room TEXT NOT NULL DEFAULT '',

            notes TEXT NOT NULL DEFAULT '',

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL

        )

    """)
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS admin_support_requests (

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
    now = _AdminDateTime.utcnow().isoformat(timespec="seconds")
    cursor.execute("""

        INSERT OR IGNORE INTO admin_profiles (

            id, full_name, email, phone, room, notes, created_at, updated_at

        )

        VALUES (

            1,

            'Administrateur',

            'administrateur@isen.fr',

            '',

            '',

            'Compte administrateur utilisé pour la récupération des configurations NixOS.',

            ?,

            ?

        )

    """, (now, now))
    connection.commit()
    connection.close()


def _get_current_admin(authorization: _AdminOptional[str] = _AdminHeader(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _AdminHTTPException(status_code=401, detail="Token administrateur manquant.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[globals().get("ALGORITHM", "HS256")]
        )
    except Exception:
        raise _AdminHTTPException(status_code=401, detail="Token administrateur invalide.")
    if payload.get("role") != "admin":
        raise _AdminHTTPException(status_code=403, detail="Accès réservé au administrateur.")
    return payload


class AdminProfilePayload(_AdminBaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    room: str = ""
    notes: str = ""


class AdminSupportPayload(_AdminBaseModel):
    subject: str
    category: str
    priority: str
    message: str


@app.get("/admin/profile")
def get_admin_profile(current_admin: dict = _AdminDepends(_get_current_admin)):
    _admin_init_tables()
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM admin_profiles WHERE id = 1")
    row = cursor.fetchone()
    connection.close()
    if not row:
        raise _AdminHTTPException(status_code=404, detail="Profil administrateur introuvable.")
    return dict(row)


@app.put("/admin/profile")
def update_admin_profile(
    payload: AdminProfilePayload,
    current_admin: dict = _AdminDepends(_get_current_admin)

):
    _admin_init_tables()
    now = _AdminDateTime.utcnow().isoformat(timespec="seconds")
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("""

        UPDATE admin_profiles

        SET full_name = ?,

            email = ?,

            phone = ?,

            room = ?,

            notes = ?,

            updated_at = ?

        WHERE id = 1

    """, (
        payload.full_name.strip() or "Administrateur",
        payload.email.strip(),
        payload.phone.strip(),
        payload.room.strip(),
        payload.notes.strip(),
        now
    ))
    connection.commit()
    cursor.execute("SELECT * FROM admin_profiles WHERE id = 1")
    row = cursor.fetchone()
    connection.close()
    return dict(row)


@app.get("/admin/support")
def list_admin_support_requests(current_admin: dict = _AdminDepends(_get_current_admin)):
    _admin_init_tables()
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT id, username, subject, category, priority, message, status, created_at

        FROM admin_support_requests

        ORDER BY id DESC

    """)
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


@app.post("/admin/support")
def create_admin_support_request(
    payload: AdminSupportPayload,
    current_admin: dict = _AdminDepends(_get_current_admin)

):
    _admin_init_tables()
    subject = payload.subject.strip()
    message = payload.message.strip()
    if not subject or not message:
        raise _AdminHTTPException(
            status_code=400,
            detail="Le sujet et le message sont obligatoires."
        )
    now = _AdminDateTime.utcnow().isoformat(timespec="seconds")
    username = current_admin.get("username") or current_admin.get("sub") or "administrateur"
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("""

        INSERT INTO admin_support_requests (

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

        FROM admin_support_requests

        WHERE id = ?

    """, (request_id,))
    row = cursor.fetchone()
    connection.close()
    return dict(row)

# =========================================================
# SECUREEXAM ADMIN PUBLIC SUPPORT
# =========================================================


@app.post("/admin/support/public")
def create_public_admin_support_request(payload: AdminSupportPayload):
    _admin_init_tables()
    subject = payload.subject.strip()
    message = payload.message.strip()
    if not subject or not message:
        raise _AdminHTTPException(
            status_code=400,
            detail="Le sujet et le message sont obligatoires."
        )
    now = _AdminDateTime.utcnow().isoformat(timespec="seconds")
    connection = _admin_connect()
    cursor = connection.cursor()
    cursor.execute("""

        INSERT INTO admin_support_requests (

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

        FROM admin_support_requests

        WHERE id = ?

    """, (request_id,))
    row = cursor.fetchone()
    connection.close()
    return dict(row)

# =========================================================
# SECUREEXAM ADMIN CONFIGS
# =========================================================


@app.get("/admin/configs")
def list_admin_configs(
    current_admin: dict = _AdminDepends(_get_current_admin)

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
            "json_download_url": f"/admin/configs/{row['id']}/download",
            "nixos_config_url": f"/admin/configs/{row['id']}/nixos-config",
            "nixos_config_download_url": f"/admin/configs/{row['id']}/nixos-config/download"
        })
    return {
        "count": len(configs),
        "configs": configs
    }


@app.get("/admin/configs/{config_id}/download")
def download_admin_config(
    config_id: int,
    current_admin: dict = _AdminDepends(_get_current_admin)

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


@app.get("/admin/configs/{config_id}/nixos-config")
def get_admin_config_nixos_preview(
    config_id: int,
    current_admin: dict = _AdminDepends(_get_current_admin)

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


@app.get("/admin/configs/{config_id}/nixos-config/download")
def download_admin_config_nixos_preview(
    config_id: int,
    current_admin: dict = _AdminDepends(_get_current_admin)

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
# SECUREEXAM_ADMIN_NIXOS_V1
# =========================================================


def _admin_get_exam_config_or_404(
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
        raise _AdminHTTPException(
            status_code=404,
            detail="Configuration d'examen introuvable."
        )
    return row


@app.get("/admin/nixos-configs")
def list_admin_nixos_configs(
    current_admin: dict = _AdminDepends(
        _get_current_admin
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
    "/admin/nixos-configs/{config_id}"
)


def get_admin_nixos_config(
    config_id: int,
    current_admin: dict = _AdminDepends(
        _get_current_admin
    )

):
    row = _admin_get_exam_config_or_404(
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
    "/admin/nixos-configs/{config_id}/download"
)


def download_admin_nixos_config(
    config_id: int,
    current_admin: dict = _AdminDepends(
        _get_current_admin
    )

):
    row = _admin_get_exam_config_or_404(
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

# =========================================================
# SECUREEXAM STUDENT SPACE V1
# =========================================================
from fastapi import Header as _StudentHeader
from fastapi import Depends as _StudentDepends
from fastapi import HTTPException as _StudentHTTPException
from pydantic import BaseModel as _StudentBaseModel
from typing import Optional as _StudentOptional

class StudentLoginRequest(_StudentBaseModel):
    username: str
    password: str


def _student_init_tables():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS student_accounts (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL UNIQUE,

            student_number TEXT NOT NULL UNIQUE,

            password_hash TEXT NOT NULL,

            full_name TEXT NOT NULL,

            email TEXT NOT NULL DEFAULT '',

            is_active INTEGER NOT NULL DEFAULT 1,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL

        )

    """)
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS student_exam_assignments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            student_id INTEGER NOT NULL,

            exam_id TEXT NOT NULL,

            machine_id TEXT NOT NULL DEFAULT '',

            status TEXT NOT NULL DEFAULT 'A_VENIR',

            assigned_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,

            UNIQUE(student_id, exam_id),

            FOREIGN KEY(student_id)

                REFERENCES student_accounts(id)

        )

    """)
    username = (
        os.getenv(
            "STUDENT_USERNAME",
            "etu001"
        )
        .strip()
    )
    student_number = (
        os.getenv(
            "STUDENT_NUMBER",
            username
        )
        .strip()
    )
    raw_password = os.getenv(
        "STUDENT_PASSWORD",
        "1234"
    )
    full_name = (
        os.getenv(
            "STUDENT_FULL_NAME",
            "Étudiant Test"
        )
        .strip()
    )
    email = (
        os.getenv(
            "STUDENT_EMAIL",
            f"{username}@isen.fr"
        )
        .strip()
    )
    current_time = now_iso()
    cursor.execute("""

        SELECT

            id,

            password_hash

        FROM student_accounts

        WHERE username = ?

        LIMIT 1

    """, (
        username,
    ))
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute("""

            INSERT INTO student_accounts (

                username,

                student_number,

                password_hash,

                full_name,

                email,

                is_active,

                created_at,

                updated_at

            )

            VALUES (?, ?, ?, ?, ?, 1, ?, ?)

        """, (
            username,
            student_number,
            password_hash.hash(
                raw_password
            ),
            full_name,
            email,
            current_time,
            current_time
        ))
    else:
        password_is_current = False
        try:
            password_is_current = (
                verify_password(
                    raw_password,
                    existing[
                        "password_hash"
                    ]
                )
            )
        except Exception:
            password_is_current = False
        new_password_hash = (
            existing["password_hash"]
            if password_is_current
            else password_hash.hash(
                raw_password
            )
        )
        cursor.execute("""

            UPDATE student_accounts

            SET

                student_number = ?,

                password_hash = ?,

                full_name = ?,

                email = ?,

                is_active = 1,

                updated_at = ?

            WHERE id = ?

        """, (
            student_number,
            new_password_hash,
            full_name,
            email,
            current_time,
            existing["id"]
        ))
    connection.commit()
    connection.close()


def _student_by_username(
    username: str

):
    _student_init_tables()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            id,

            username,

            student_number,

            password_hash,

            full_name,

            email,

            is_active,

            created_at,

            updated_at

        FROM student_accounts

        WHERE username = ?

        LIMIT 1

    """, (
        username,
    ))
    row = cursor.fetchone()
    connection.close()
    return row


def _get_current_student(
    authorization:
        _StudentOptional[str]
        = _StudentHeader(
            default=None
        )

):
    if (
        not authorization
        or not authorization
        .lower()
        .startswith("bearer ")
    ):
        raise _StudentHTTPException(
            status_code=401,
            detail=(
                "Token étudiant manquant."
            )
        )
    token = authorization.split(
        " ",
        1
    )[1].strip()
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[
                ALGORITHM
            ]
        )
    except Exception:
        raise _StudentHTTPException(
            status_code=401,
            detail=(
                "Token étudiant invalide "

                "ou expiré."
            )
        )
    if payload.get(
        "role"
    ) != "student":
        raise _StudentHTTPException(
            status_code=403,
            detail=(
                "Accès réservé "

                "aux étudiants."
            )
        )
    username = (
        payload.get("username")
        or payload.get("sub")
        or ""
    )
    student = (
        _student_by_username(
            username
        )
    )
    if student is None:
        raise _StudentHTTPException(
            status_code=401,
            detail=(
                "Compte étudiant "

                "introuvable."
            )
        )
    if not bool(
        student["is_active"]
    ):
        raise _StudentHTTPException(
            status_code=403,
            detail=(
                "Compte étudiant "

                "désactivé."
            )
        )
    return {
        "id":
            student["id"],
        "username":
            student["username"],
        "student_number":
            student[
                "student_number"
            ],
        "full_name":
            student["full_name"],
        "email":
            student["email"],
        "role":
            "student"
    }


@app.post(
    "/student/login"
)


def student_login(
    payload:
        StudentLoginRequest

):
    _student_init_tables()
    username = (
        payload.username
        or ""
    ).strip()
    password = (
        payload.password
        or ""
    )
    if (
        not username
        or not password
    ):
        raise _StudentHTTPException(
            status_code=400,
            detail=(
                "Identifiant et mot "

                "de passe obligatoires."
            )
        )
    student = (
        _student_by_username(
            username
        )
    )
    if student is None:
        raise _StudentHTTPException(
            status_code=401,
            detail=(
                "Identifiants étudiant "

                "incorrects."
            )
        )
    if not bool(
        student["is_active"]
    ):
        raise _StudentHTTPException(
            status_code=403,
            detail=(
                "Compte étudiant "

                "désactivé."
            )
        )
    try:
        valid_password = (
            verify_password(
                password,
                student[
                    "password_hash"
                ]
            )
        )
    except Exception:
        valid_password = False
    if not valid_password:
        raise _StudentHTTPException(
            status_code=401,
            detail=(
                "Identifiants étudiant "

                "incorrects."
            )
        )
    token_data = {
        "sub":
            student["username"],
        "username":
            student["username"],
        "student_id":
            student["id"],
        "student_number":
            student[
                "student_number"
            ],
        "role":
            "student"
    }
    access_token = (
        create_access_token(
            data=token_data
        )
    )
    return {
        "access_token":
            access_token,
        "token_type":
            "bearer",
        "role":
            "student",
        "username":
            student["username"],
        "student_number":
            student[
                "student_number"
            ],
        "full_name":
            student["full_name"]
    }


@app.get(
    "/student/me"
)


def student_me(
    current_student:
        dict
        = _StudentDepends(
            _get_current_student
        )

):
    return current_student


def _student_ensure_assignment_runtime_columns():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        PRAGMA table_info(

            student_exam_assignments

        )

    """)
    columns = {
        row["name"]
        for row in cursor.fetchall()
    }
    if "started_at" not in columns:
        cursor.execute("""

            ALTER TABLE

                student_exam_assignments

            ADD COLUMN

                started_at TEXT

        """)
    connection.commit()
    connection.close()



# =========================================================
# SECUREEXAM_EXAM_ATTACHMENTS_V1
#
# Pieces complementaires associees a une configuration.
#
# - stockage SQLite BLOB
# - PDF uniquement
# - 5 fichiers maximum
# - 10 Mo maximum par fichier
# - invisibles avant EN_COURS
# =========================================================


SECUREEXAM_ATTACHMENT_MAX_FILES = 5

SECUREEXAM_ATTACHMENT_MAX_BYTES = (
    10
    * 1024
    * 1024
)


def _secureexam_exam_attachments_init():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS
        exam_attachments (

            id INTEGER PRIMARY KEY
                AUTOINCREMENT,

            exam_config_id INTEGER
                NOT NULL,

            original_filename TEXT
                NOT NULL,

            content_type TEXT
                NOT NULL,

            size_bytes INTEGER
                NOT NULL,

            file_data BLOB
                NOT NULL,

            created_at TEXT
                NOT NULL,

            updated_at TEXT
                NOT NULL,

            FOREIGN KEY(exam_config_id)
                REFERENCES exam_configs(id)
                ON DELETE CASCADE
        )
    """)


    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_exam_attachments_config

        ON exam_attachments (
            exam_config_id,
            id
        )
    """)


    connection.commit()
    connection.close()



def _secureexam_student_visible_attachments(
    cursor,
    assignment_status,
    config_id
):

    status = str(
        assignment_status
        or ""
    ).strip().upper()


    # IMPORTANT :
    # rien n'est meme revele avant
    # l'application effective de NixOS.
    if (
        status != "EN_COURS"
        or config_id is None
    ):
        return []


    cursor.execute("""
        SELECT
            id,
            original_filename,
            content_type,
            size_bytes,
            created_at

        FROM exam_attachments

        WHERE exam_config_id = ?

        ORDER BY
            id ASC
    """, (
        int(config_id),
    ))


    rows = cursor.fetchall()


    return [
        {
            "id":
                int(row["id"]),

            "filename":
                row["original_filename"],

            "content_type":
                row["content_type"],

            "size_bytes":
                int(
                    row["size_bytes"]
                    or 0
                ),

            "size_kb":
                round(
                    int(
                        row["size_bytes"]
                        or 0
                    )
                    / 1024,
                    1
                ),

            "created_at":
                row["created_at"],
        }

        for row in rows
    ]



@app.post(
    "/teacher/exam-delivery/"
    "{config_id}/attachments"
)
async def teacher_replace_exam_attachments(
    config_id: int,

    files:
        Optional[
            List[UploadFile]
        ]
        = File(
            default=None
        ),

    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):

    _secureexam_exam_attachments_init()
    _roster_init_tables()


    teacher_id = int(
        current_teacher["id"]
    )


    connection = get_connection()
    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            ec.id,
            ec.exam_id,
            er.status AS roster_status

        FROM exam_configs ec

        LEFT JOIN exam_rosters er
            ON er.exam_config_id = ec.id

        WHERE
            ec.id = ?
            AND ec.teacher_id = ?

        LIMIT 1
    """, (
        config_id,
        teacher_id,
    ))


    exam = cursor.fetchone()


    if exam is None:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration introuvable "
                "ou non autorisee."
            )
        )


    roster_status = str(
        exam["roster_status"]
        or ""
    ).upper()


    if roster_status == "SENT":

        connection.close()

        raise HTTPException(
            status_code=409,
            detail=(
                "Cet examen a deja "
                "ete envoye."
            )
        )


    uploads = list(
        files
        or []
    )


    if (
        len(uploads)
        >
        SECUREEXAM_ATTACHMENT_MAX_FILES
    ):

        connection.close()

        raise HTTPException(
            status_code=400,
            detail=(
                "Maximum 5 fichiers PDF."
            )
        )


    prepared = []


    for upload in uploads:

        original_name = Path(
            upload.filename
            or "document.pdf"
        ).name


        if (
            Path(original_name)
            .suffix
            .lower()
            != ".pdf"
        ):

            connection.close()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Seuls les fichiers PDF "
                    "sont autorises."
                )
            )


        data = await upload.read()


        if not data:

            connection.close()

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Le fichier "
                    f"{original_name} "
                    "est vide."
                )
            )


        if (
            len(data)
            >
            SECUREEXAM_ATTACHMENT_MAX_BYTES
        ):

            connection.close()

            raise HTTPException(
                status_code=413,
                detail=(
                    f"Le fichier "
                    f"{original_name} "
                    "depasse 10 Mo."
                )
            )


        # Verification signature PDF.
        if not data.startswith(
            b"%PDF-"
        ):

            connection.close()

            raise HTTPException(
                status_code=400,
                detail=(
                    f"{original_name} "
                    "n'est pas un PDF valide."
                )
            )


        prepared.append({
            "filename":
                original_name,

            "content_type":
                "application/pdf",

            "data":
                data,

            "size":
                len(data),
        })


    current_time = now_iso()


    try:

        connection.execute(
            "BEGIN"
        )


        # Le contenu du popup remplace
        # la selection precedente.
        cursor.execute("""
            DELETE FROM exam_attachments

            WHERE exam_config_id = ?
        """, (
            config_id,
        ))


        for item in prepared:

            cursor.execute("""
                INSERT INTO exam_attachments (
                    exam_config_id,
                    original_filename,
                    content_type,
                    size_bytes,
                    file_data,
                    created_at,
                    updated_at
                )

                VALUES (
                    ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                config_id,
                item["filename"],
                item["content_type"],
                item["size"],
                item["data"],
                current_time,
                current_time,
            ))


        connection.commit()


    except Exception:

        connection.rollback()
        connection.close()
        raise


    connection.close()


    return {
        "success":
            True,

        "exam_id":
            exam["exam_id"],

        "attachments_count":
            len(prepared),

        "attachments": [
            {
                "filename":
                    item["filename"],

                "size_bytes":
                    item["size"],
            }

            for item in prepared
        ],
    }



@app.get(
    "/student/exams/"
    "{assignment_id}/attachments/"
    "{attachment_id}/download"
)
def student_download_exam_attachment(
    assignment_id: int,
    attachment_id: int,

    current_student:
        dict
        = _StudentDepends(
            _get_current_student
        )
):

    _student_init_tables()
    _secureexam_exam_attachments_init()


    connection = get_connection()
    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            id,
            exam_id,
            status

        FROM student_exam_assignments

        WHERE
            id = ?
            AND student_id = ?

        LIMIT 1
    """, (
        assignment_id,
        current_student["id"],
    ))


    assignment = cursor.fetchone()


    if assignment is None:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail=(
                "Affectation etudiante "
                "introuvable."
            )
        )


    status = str(
        assignment["status"]
        or ""
    ).upper()


    # SECURITE BACKEND :
    # meme avec l'URL exacte,
    # aucun document avant EN_COURS.
    if status != "EN_COURS":

        connection.close()

        raise HTTPException(
            status_code=403,
            detail=(
                "Les pieces complementaires "
                "ne sont accessibles qu'apres "
                "le demarrage effectif "
                "de l'examen."
            )
        )


    cursor.execute("""
        SELECT id

        FROM exam_configs

        WHERE exam_id = ?

        ORDER BY
            updated_at DESC,
            id DESC

        LIMIT 1
    """, (
        assignment["exam_id"],
    ))


    config = cursor.fetchone()


    if config is None:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration d'examen "
                "introuvable."
            )
        )


    cursor.execute("""
        SELECT
            id,
            original_filename,
            content_type,
            file_data

        FROM exam_attachments

        WHERE
            id = ?
            AND exam_config_id = ?

        LIMIT 1
    """, (
        attachment_id,
        config["id"],
    ))


    attachment = cursor.fetchone()

    connection.close()


    if attachment is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Piece complementaire "
                "introuvable."
            )
        )


    from urllib.parse import quote


    filename = str(
        attachment[
            "original_filename"
        ]
        or "document.pdf"
    )


    encoded_name = quote(
        filename
    )


    return Response(
        content=
            attachment["file_data"],

        media_type=
            attachment["content_type"]
            or "application/pdf",

        headers={
            "Content-Disposition":
                (
                    "inline; "
                    "filename*=UTF-8''"
                    + encoded_name
                )
        }
    )



_secureexam_exam_attachments_init()


# /SECUREEXAM_EXAM_ATTACHMENTS_V1


@app.get(
    "/student/dashboard"
)


def student_dashboard(
    current_student:
        dict
        = _StudentDepends(
            _get_current_student
        )

):
    _student_init_tables()
    _student_ensure_assignment_runtime_columns()
    _secureexam_exam_attachments_init()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            id,

            exam_id,

            machine_id,

            status,

            assigned_at,

            updated_at,

            started_at

        FROM student_exam_assignments

        WHERE student_id = ?

        ORDER BY

            assigned_at DESC,

            id DESC

    """, (
        current_student["id"],
    ))
    assignment_rows = cursor.fetchall()
    exams = []
    for assignment in assignment_rows:
        cursor.execute("""

            SELECT *

            FROM exam_configs

            WHERE exam_id = ?

            ORDER BY

                updated_at DESC,

                id DESC

            LIMIT 1

        """, (
            assignment["exam_id"],
        ))
        config_row = cursor.fetchone()
        config_ready = (
            config_row is not None
        )
        config = None
        exam_name = (
            assignment["exam_id"]
        )
        exam_date = ""
        exam_time = ""
        if config_row is not None:
            config_data = row_to_config(
                config_row
            )
            exam_name = (
                config_data.get(
                    "exam_name"
                )
                or assignment[
                    "exam_id"
                ]
            )
            exam_date = (
                config_data.get(
                    "exam_date"
                )
                or ""
            )
            exam_time = (
                config_data.get(
                    "exam_time"
                )
                or ""
            )
            config = {
                "packages":
                    config_data.get(
                        "packages"
                    )
                    or [],
                "sudo":
                    bool(
                        config_data.get(
                            "sudo"
                        )
                    ),
                "internet":
                    bool(
                        config_data.get(
                            "internet"
                        )
                    ),
                "educ_access":
                    bool(
                        config_data.get(
                            "educ_access"
                        )
                    ),
                "allowed_domains":
                    config_data.get(
                        "allowed_domains"
                    )
                    or [],
                "nix_filename":
                    (
                        assignment[
                            "exam_id"
                        ]
                        + "_exam-configuration.nix"
                    )
            }
        attachments = (
            _secureexam_student_visible_attachments(
                cursor,
                assignment["status"],
                (
                    int(config_row["id"])
                    if config_row is not None
                    else None
                )
            )
        )

        exams.append({
            "assignment_id":
                assignment["id"],
            "exam_id":
                assignment["exam_id"],
            "exam_name":
                exam_name,
            "exam_date":
                exam_date,
            "exam_time":
                exam_time,
            "machine_id":
                assignment[
                    "machine_id"
                ]
                or "",
            "status":
                assignment[
                    "status"
                ]
                or "A_VENIR",
            "assigned_at":
                assignment[
                    "assigned_at"
                ],
            "started_at":
                assignment[
                    "started_at"
                ],
            "config_ready":
                config_ready,

            "attachments":
                attachments,

            "config":
                config
        })
    connection.close()
    return {
        "student": {
            "id":
                current_student["id"],
            "username":
                current_student[
                    "username"
                ],
            "student_number":
                current_student[
                    "student_number"
                ],
            "full_name":
                current_student[
                    "full_name"
                ],
            "email":
                current_student[
                    "email"
                ]
        },
        "exams":
            exams,
        "exams_count":
            len(exams)
    }

# =========================================================
# SECUREEXAM_AGENT_V1_START
# =========================================================
from fastapi import Header as _AgentHeader
from pydantic import BaseModel as _AgentBaseModel
import hmac as _agent_hmac

SECUREEXAM_AGENT_ONLINE_TTL_SECONDS = 30
SECUREEXAM_AGENT_CLAIM_TIMEOUT_SECONDS = 120


class SecureExamAgentRegisterRequest(
    _AgentBaseModel
):
    machine_id: str
    hostname: str
    os_name: str
    version: str


class SecureExamAgentHeartbeatRequest(
    _AgentBaseModel
):
    machine_id: str
    state: str = "IDLE"


class SecureExamAgentCompleteRequest(
    _AgentBaseModel
):
    machine_id: str
    status: str
    message: str = ""


def _secureexam_agent_require_token(
    token: str | None
):
    expected = str(
        os.getenv(
            "SECUREEXAM_AGENT_TOKEN",
            ""
        )
        or ""
    ).strip()
    supplied = str(
        token
        or ""
    ).strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "SECUREEXAM_AGENT_TOKEN "
                "non configure."
            )
        )
    if (
        not supplied
        or not _agent_hmac.compare_digest(
            supplied,
            expected
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Token agent invalide."
        )


def _secureexam_agent_init_tables():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS
        secureexam_agent_machines (
            machine_id TEXT PRIMARY KEY,
            hostname TEXT NOT NULL DEFAULT '',
            os_name TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'IDLE',
            last_seen TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS
        secureexam_agent_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT NOT NULL,
            command_type TEXT NOT NULL,
            exam_id TEXT NOT NULL,
            assignment_id INTEGER NOT NULL,
            student_number TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            claimed_at TEXT,
            completed_at TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_secureexam_agent_commands_machine_status
        ON secureexam_agent_commands (
            machine_id,
            status,
            id
        )
    """)
    connection.commit()
    connection.close()


def _secureexam_agent_online_threshold():
    return (
        datetime.now()
        - timedelta(
            seconds=
                SECUREEXAM_AGENT_ONLINE_TTL_SECONDS
        )
    ).isoformat(
        timespec="seconds"
    )


def _secureexam_agent_resolve_target(
    cursor,
    requested_machine_id: str
) -> str:
    requested = str(
        requested_machine_id
        or ""
    ).strip()
    threshold = (
        _secureexam_agent_online_threshold()
    )
    if requested:
        cursor.execute("""
            SELECT machine_id
            FROM secureexam_agent_machines
            WHERE
                machine_id = ?
            AND
                last_seen >= ?
            LIMIT 1
        """, (
            requested,
            threshold
        ))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "L'agent SecureExam de cette "
                    "machine n'est pas en ligne."
                )
            )
        return str(
            row["machine_id"]
        )
    cursor.execute("""
        SELECT machine_id
        FROM secureexam_agent_machines
        WHERE last_seen >= ?
        ORDER BY
            last_seen DESC,
            machine_id ASC
    """, (
        threshold,
    ))
    rows = cursor.fetchall()
    if len(rows) == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Aucun agent SecureExam "
                "n'est actuellement en ligne."
            )
        )
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Plusieurs machines SecureExam "
                "sont en ligne. Association "
                "machine/etudiant requise."
            )
        )
    return str(
        rows[0]["machine_id"]
    )


def _secureexam_agent_enqueue_start(
    cursor,
    machine_id: str,
    exam_id: str,
    assignment_id: int,
    student_number: str
) -> int:
    cursor.execute("""
        SELECT id
        FROM secureexam_agent_commands
        WHERE
            assignment_id = ?
        AND
            command_type = 'START_EXAM'
        AND
            status IN (
                'PENDING',
                'CLAIMED',
                'DONE'
            )
        ORDER BY id DESC
        LIMIT 1
    """, (
        assignment_id,
    ))
    existing = cursor.fetchone()
    if existing is not None:
        return int(
            existing["id"]
        )
    current_time = now_iso()
    payload = json.dumps(
        {
            "exam_id":
                exam_id,
            "student_number":
                student_number,
            "machine_id":
                machine_id
        },
        ensure_ascii=False
    )
    cursor.execute("""
        INSERT INTO
        secureexam_agent_commands (
            machine_id,
            command_type,
            exam_id,
            assignment_id,
            student_number,
            payload,
            status,
            created_at
        )
        VALUES (
            ?,
            'START_EXAM',
            ?,
            ?,
            ?,
            ?,
            'PENDING',
            ?
        )
    """, (
        machine_id,
        exam_id,
        assignment_id,
        student_number,
        payload,
        current_time
    ))
    return int(
        cursor.lastrowid
    )



def _secureexam_agent_enqueue_end(
    cursor,
    machine_id: str,
    exam_id: str,
    assignment_id: int,
    student_number: str
) -> int:

    cursor.execute("""
        SELECT id
        FROM secureexam_agent_commands

        WHERE
            assignment_id = ?

        AND
            command_type = 'END_EXAM'

        AND
            status IN (
                'PENDING',
                'CLAIMED',
                'DONE'
            )

        ORDER BY id DESC
        LIMIT 1
    """, (
        assignment_id,
    ))

    existing = cursor.fetchone()

    if existing is not None:
        return int(
            existing["id"]
        )

    current_time = now_iso()

    payload = json.dumps(
        {
            "exam_id":
                exam_id,

            "student_number":
                student_number,

            "machine_id":
                machine_id,

            "workspace":
                "/home/exam/workspace"
        },
        ensure_ascii=False
    )

    cursor.execute("""
        INSERT INTO
            secureexam_agent_commands (
                machine_id,
                command_type,
                exam_id,
                assignment_id,
                student_number,
                payload,
                status,
                created_at
            )

        VALUES (
            ?,
            'END_EXAM',
            ?,
            ?,
            ?,
            ?,
            'PENDING',
            ?
        )
    """, (
        machine_id,
        exam_id,
        assignment_id,
        student_number,
        payload,
        current_time
    ))

    return int(
        cursor.lastrowid
    )



@app.post("/agent/register")
def secureexam_agent_register(
    payload:
        SecureExamAgentRegisterRequest,
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    _secureexam_agent_init_tables()
    machine_id = (
        payload.machine_id.strip()
    )
    if not machine_id:
        raise HTTPException(
            status_code=400,
            detail="machine_id obligatoire."
        )
    current_time = now_iso()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO
        secureexam_agent_machines (
            machine_id,
            hostname,
            os_name,
            version,
            state,
            last_seen,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, 'IDLE',
            ?, ?, ?
        )
        ON CONFLICT(machine_id)
        DO UPDATE SET
            hostname = excluded.hostname,
            os_name = excluded.os_name,
            version = excluded.version,
            state = 'IDLE',
            last_seen = excluded.last_seen,
            updated_at = excluded.updated_at
    """, (
        machine_id,
        payload.hostname.strip(),
        payload.os_name.strip(),
        payload.version.strip(),
        current_time,
        current_time,
        current_time
    ))
    connection.commit()
    connection.close()
    return {
        "success": True,
        "machine_id": machine_id,
        "state": "IDLE"
    }


@app.post("/agent/heartbeat")
def secureexam_agent_heartbeat(
    payload:
        SecureExamAgentHeartbeatRequest,
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    _secureexam_agent_init_tables()
    machine_id = (
        payload.machine_id.strip()
    )
    state = (
        payload.state.strip().upper()
        or "IDLE"
    )
    current_time = now_iso()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE secureexam_agent_machines
        SET
            state = ?,
            last_seen = ?,
            updated_at = ?
        WHERE machine_id = ?
    """, (
        state,
        current_time,
        current_time,
        machine_id
    ))
    if cursor.rowcount != 1:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Agent non enregistre."
        )
    connection.commit()
    connection.close()
    return {
        "success": True,
        "machine_id": machine_id,
        "state": state
    }


@app.get(
    "/agent/commands/{machine_id}/next"
)
def secureexam_agent_next_command(
    machine_id: str,
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    _secureexam_agent_init_tables()
    machine_id = machine_id.strip()
    current_time = now_iso()
    expired_claim = (
        datetime.now()
        - timedelta(
            seconds=
                SECUREEXAM_AGENT_CLAIM_TIMEOUT_SECONDS
        )
    ).isoformat(
        timespec="seconds"
    )
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE secureexam_agent_machines
        SET
            last_seen = ?,
            updated_at = ?
        WHERE machine_id = ?
    """, (
        current_time,
        current_time,
        machine_id
    ))
    if cursor.rowcount != 1:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail="Agent non enregistre."
        )
    cursor.execute("""
        UPDATE secureexam_agent_commands
        SET
            status = 'PENDING',
            claimed_at = NULL
        WHERE
            machine_id = ?
        AND
            status = 'CLAIMED'
        AND
            claimed_at IS NOT NULL
        AND
            claimed_at < ?
    """, (
        machine_id,
        expired_claim
    ))
    cursor.execute("""
        SELECT
            id,
            machine_id,
            command_type,
            exam_id,
            assignment_id,
            student_number,
            payload,
            created_at
        FROM secureexam_agent_commands
        WHERE
            machine_id = ?
        AND
            status = 'PENDING'
        ORDER BY id ASC
        LIMIT 1
    """, (
        machine_id,
    ))
    row = cursor.fetchone()
    if row is None:
        connection.commit()
        connection.close()
        return {
            "command": None
        }
    cursor.execute("""
        UPDATE secureexam_agent_commands
        SET
            status = 'CLAIMED',
            claimed_at = ?
        WHERE
            id = ?
        AND
            status = 'PENDING'
    """, (
        current_time,
        row["id"]
    ))
    if cursor.rowcount != 1:
        connection.commit()
        connection.close()
        return {
            "command": None
        }
    connection.commit()
    connection.close()
    try:
        command_payload = json.loads(
            row["payload"]
            or "{}"
        )
    except Exception:
        command_payload = {}
    return {
        "command": {
            "id":
                int(row["id"]),
            "type":
                row["command_type"],
            "exam_id":
                row["exam_id"],
            "assignment_id":
                int(row["assignment_id"]),
            "student_number":
                row["student_number"],
            "machine_id":
                row["machine_id"],
            "payload":
                command_payload,
            "created_at":
                row["created_at"]
        }
    }


@app.get("/agent/config/{exam_id}")
def secureexam_agent_config(
    exam_id: str,
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT *
        FROM exam_configs
        WHERE exam_id = ?
        ORDER BY
            updated_at DESC,
            id DESC
        LIMIT 1
    """, (
        exam_id,
    ))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration examen "
                "introuvable."
            )
        )
    config_data = row_to_config(
        row
    )
    nix_content = (
        generate_nixos_config_preview(
            config_data
        )
    )
    return {
        "exam_id":
            exam_id,
        "filename":
            (
                exam_id
                + "_exam-configuration.nix"
            ),
        "content":
            nix_content
    }


@app.post(
    "/agent/commands/{command_id}/complete"
)
def secureexam_agent_complete_command(
    command_id: int,
    payload:
        SecureExamAgentCompleteRequest,
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )

    status = (
        payload.status
        .strip()
        .upper()
    )

    if status not in {
        "DONE",
        "ERROR"
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "status doit etre "
                "DONE ou ERROR."
            )
        )

    machine_id = (
        payload.machine_id
        .strip()
    )

    current_time = now_iso()

    connection = get_connection()
    cursor = connection.cursor()

    started_at = None

    try:

        cursor.execute("""
            SELECT
                id,
                machine_id,
                command_type,
                exam_id,
                assignment_id,
                status

            FROM secureexam_agent_commands

            WHERE
                id = ?
            AND
                machine_id = ?

            LIMIT 1
        """, (
            command_id,
            machine_id
        ))

        command = cursor.fetchone()

        if command is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Commande agent "
                    "introuvable."
                )
            )

        command_type = str(
            command["command_type"]
            or ""
        ).upper()

        if command_type not in {
            "START_EXAM",
            "END_EXAM"
        }:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Type de commande invalide."
                )
            )


        # ==================================================
        # START_EXAM
        # ==================================================

        if command_type == "START_EXAM":

            if status == "DONE":

                cursor.execute("""
                    UPDATE student_exam_assignments

                    SET
                        status = 'EN_COURS',

                        started_at =
                            COALESCE(
                                started_at,
                                ?
                            ),

                        updated_at = ?

                    WHERE
                        id = ?

                    AND
                        machine_id = ?

                    AND
                        status IN (
                            'PREPARING',
                            'EN_COURS'
                        )
                """, (
                    current_time,
                    current_time,
                    command["assignment_id"],
                    machine_id
                ))

                if cursor.rowcount != 1:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Affectation incompatible "
                            "avec START_EXAM."
                        )
                    )

                cursor.execute("""
                    SELECT started_at

                    FROM student_exam_assignments

                    WHERE id = ?

                    LIMIT 1
                """, (
                    command["assignment_id"],
                ))

                assignment = cursor.fetchone()

                started_at = (
                    assignment["started_at"]
                    if assignment
                    else current_time
                )

                machine_state = "READY"
                assignment_status = "EN_COURS"

            else:

                cursor.execute("""
                    UPDATE student_exam_assignments

                    SET
                        status = 'START_ERROR',
                        started_at = NULL,
                        updated_at = ?

                    WHERE
                        id = ?

                    AND
                        machine_id = ?

                    AND
                        status = 'PREPARING'
                """, (
                    current_time,
                    command["assignment_id"],
                    machine_id
                ))

                machine_state = "ERROR"
                assignment_status = "START_ERROR"


        # ==================================================
        # END_EXAM
        # ==================================================

        else:

            if status == "DONE":

                cursor.execute("""
                    UPDATE student_exam_assignments

                    SET
                        status = 'TERMINE',
                        updated_at = ?

                    WHERE
                        id = ?

                    AND
                        machine_id = ?

                    AND
                        status IN (
                            'FINALIZING',
                            'TERMINE'
                        )
                """, (
                    current_time,
                    command["assignment_id"],
                    machine_id
                ))

                if cursor.rowcount != 1:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Affectation incompatible "
                            "avec END_EXAM."
                        )
                    )

                machine_state = "IDLE"
                assignment_status = "TERMINE"

            else:

                cursor.execute("""
                    UPDATE student_exam_assignments

                    SET
                        status = 'END_ERROR',
                        updated_at = ?

                    WHERE
                        id = ?

                    AND
                        machine_id = ?

                    AND
                        status = 'FINALIZING'
                """, (
                    current_time,
                    command["assignment_id"],
                    machine_id
                ))

                machine_state = "ERROR"
                assignment_status = "END_ERROR"


        cursor.execute("""
            UPDATE secureexam_agent_commands

            SET
                status = ?,
                message = ?,
                completed_at = ?

            WHERE
                id = ?

            AND
                machine_id = ?
        """, (
            status,
            payload.message,
            current_time,
            command_id,
            machine_id
        ))


        cursor.execute("""
            UPDATE secureexam_agent_machines

            SET
                state = ?,
                last_seen = ?,
                updated_at = ?

            WHERE machine_id = ?
        """, (
            machine_state,
            current_time,
            current_time,
            machine_id
        ))


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        connection.close()


    return {
        "success":
            True,

        "command_id":
            command_id,

        "command_type":
            command_type,

        "status":
            status,

        "machine_state":
            machine_state,

        "assignment_status":
            assignment_status,

        "started_at":
            started_at
    }



@app.get("/agent/machines")
def secureexam_agent_list_machines(
    x_secureexam_agent_token:
        str | None
        = _AgentHeader(
            default=None
        )
):
    _secureexam_agent_require_token(
        x_secureexam_agent_token
    )
    _secureexam_agent_init_tables()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            machine_id,
            hostname,
            os_name,
            version,
            state,
            last_seen
        FROM secureexam_agent_machines
        ORDER BY last_seen DESC
    """)
    rows = cursor.fetchall()
    connection.close()
    return {
        "count":
            len(rows),
        "machines": [
            {
                "machine_id":
                    row["machine_id"],
                "hostname":
                    row["hostname"],
                "os_name":
                    row["os_name"],
                "version":
                    row["version"],
                "state":
                    row["state"],
                "last_seen":
                    row["last_seen"]
            }
            for row in rows
        ]
    }

# =========================================================
# SECUREEXAM_AGENT_V1_END
# =========================================================


@app.post(
    "/student/exams/{assignment_id}/start"
)
def student_start_exam(
    assignment_id: int,
    current_student:
        dict
        = _StudentDepends(
            _get_current_student
        )
):
    _student_init_tables()
    _student_ensure_assignment_runtime_columns()
    _secureexam_agent_init_tables()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            id,
            exam_id,
            student_id,
            machine_id,
            status,
            started_at

        FROM student_exam_assignments

        WHERE
            id = ?
        AND
            student_id = ?

        LIMIT 1
    """, (
        assignment_id,
        current_student["id"]
    ))
    assignment = cursor.fetchone()
    if assignment is None:
        connection.close()
        raise _StudentHTTPException(
            status_code=404,
            detail=(
                "Examen affecte "
                "introuvable."
            )
        )
    current_status = str(
        assignment["status"]
        or ""
    ).upper()
    if current_status in {
        "TERMINE",
        "TERMINEE",
        "CLOTURE",
        "CLOTUREE"
    }:
        connection.close()
        raise _StudentHTTPException(
            status_code=409,
            detail=(
                "Cet examen est deja termine."
            )
        )

    # ---------------------------------------------
    # Deja lance :
    # ne jamais redemarrer le chrono.
    # ---------------------------------------------
    if (
        current_status == "EN_COURS"
        and assignment["started_at"]
    ):
        result = {
            "success":
                True,
            "assignment_id":
                assignment_id,
            "exam_id":
                assignment["exam_id"],
            "status":
                "EN_COURS",
            "started_at":
                assignment["started_at"],
            "configuration_applied":
                True,
            "agent_command_id":
                None,
            "machine_id":
                assignment["machine_id"]
                or "",
            "agent_status":
                "READY"
        }
        connection.close()
        return result
    cursor.execute("""
        SELECT id

        FROM exam_configs

        WHERE exam_id = ?

        ORDER BY
            updated_at DESC,
            id DESC

        LIMIT 1
    """, (
        assignment["exam_id"],
    ))
    config = cursor.fetchone()
    if config is None:
        connection.close()
        raise _StudentHTTPException(
            status_code=409,
            detail=(
                "La configuration de cet "
                "examen n'est pas prete."
            )
        )
    try:
        machine_id = (
            _secureexam_agent_resolve_target(
                cursor,
                assignment["machine_id"]
                or ""
            )
        )
    except HTTPException:
        connection.close()
        raise

    # ---------------------------------------------
    # IMPORTANT
    #
    # Ici la machine doit encore se preparer.
    #
    # AUCUN started_at.
    # AUCUN chrono.
    # ---------------------------------------------
    cursor.execute("""
        UPDATE student_exam_assignments

        SET
            status = 'PREPARING',
            started_at = NULL,
            machine_id = ?,
            updated_at = ?

        WHERE
            id = ?
        AND
            student_id = ?
    """, (
        machine_id,
        now_iso(),
        assignment_id,
        current_student["id"]
    ))
    command_id = (
        _secureexam_agent_enqueue_start(
            cursor=cursor,
            machine_id=
                machine_id,
            exam_id=
                assignment["exam_id"],
            assignment_id=
                assignment_id,
            student_number=
                current_student[
                    "student_number"
                ]
        )
    )
    connection.commit()
    connection.close()
    return {
        "success":
            True,
        "assignment_id":
            assignment_id,
        "exam_id":
            assignment["exam_id"],
        "status":
            "PREPARING",
        "started_at":
            None,
        "configuration_applied":
            False,
        "agent_command_id":
            command_id,
        "machine_id":
            machine_id,
        "agent_status":
            "PENDING"
    }


@app.post(
    "/student/exams/{assignment_id}/finish"
)
def student_finish_exam(
    assignment_id: int,

    current_student:
        dict
        = _StudentDepends(
            _get_current_student
        )
):
    _student_init_tables()
    _student_ensure_assignment_runtime_columns()
    _secureexam_agent_init_tables()

    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute("""
            SELECT
                id,
                exam_id,
                student_id,
                machine_id,
                status,
                started_at

            FROM student_exam_assignments

            WHERE
                id = ?

            AND
                student_id = ?

            LIMIT 1
        """, (
            assignment_id,
            current_student["id"]
        ))

        assignment = cursor.fetchone()

        if assignment is None:

            raise _StudentHTTPException(
                status_code=404,
                detail=(
                    "Examen affecte "
                    "introuvable."
                )
            )


        current_status = str(
            assignment["status"]
            or ""
        ).upper()


        if current_status in {
            "TERMINE",
            "TERMINEE",
            "CLOTURE",
            "CLOTUREE"
        }:

            return {
                "success":
                    True,

                "assignment_id":
                    assignment_id,

                "exam_id":
                    assignment["exam_id"],

                "status":
                    "TERMINE",

                "agent_command_id":
                    None,

                "machine_id":
                    assignment["machine_id"]
                    or ""
            }


        if current_status == "FINALIZING":

            cursor.execute("""
                SELECT id

                FROM secureexam_agent_commands

                WHERE
                    assignment_id = ?

                AND
                    command_type = 'END_EXAM'

                AND
                    status IN (
                        'PENDING',
                        'CLAIMED',
                        'DONE'
                    )

                ORDER BY id DESC

                LIMIT 1
            """, (
                assignment_id,
            ))

            command = cursor.fetchone()

            return {
                "success":
                    True,

                "assignment_id":
                    assignment_id,

                "exam_id":
                    assignment["exam_id"],

                "status":
                    "FINALIZING",

                "agent_command_id":
                    (
                        int(command["id"])
                        if command
                        else None
                    ),

                "machine_id":
                    assignment["machine_id"]
                    or ""
            }


        if current_status not in {
            "EN_COURS",
            "END_ERROR"
        }:

            raise _StudentHTTPException(
                status_code=409,
                detail=(
                    "L'examen ne peut pas "
                    "etre termine dans son "
                    "etat actuel."
                )
            )


        machine_id = (
            _secureexam_agent_resolve_target(
                cursor,

                assignment["machine_id"]
                or ""
            )
        )


        command_id = (
            _secureexam_agent_enqueue_end(
                cursor=cursor,

                machine_id=
                    machine_id,

                exam_id=
                    assignment["exam_id"],

                assignment_id=
                    assignment_id,

                student_number=
                    current_student[
                        "student_number"
                    ]
            )
        )


        cursor.execute("""
            UPDATE student_exam_assignments

            SET
                status = 'FINALIZING',
                machine_id = ?,
                updated_at = ?

            WHERE
                id = ?

            AND
                student_id = ?
        """, (
            machine_id,
            now_iso(),
            assignment_id,
            current_student["id"]
        ))


        connection.commit()


        return {
            "success":
                True,

            "assignment_id":
                assignment_id,

            "exam_id":
                assignment["exam_id"],

            "status":
                "FINALIZING",

            "agent_command_id":
                command_id,

            "machine_id":
                machine_id
        }


    except Exception:

        connection.rollback()
        raise


    finally:

        connection.close()



_student_init_tables()

# =========================================================
# SECUREEXAM_EXAM_ROSTER_DELIVERY_V1
# =========================================================
from fastapi import (
    File as _RosterFile,
    Form as _RosterForm,
    UploadFile as _RosterUploadFile,
    Header as _RosterHeader,
    Depends as _RosterDepends,
    HTTPException as _RosterHTTPException,
)
import csv as _roster_csv
import io as _roster_io
import json as _roster_json
import re as _roster_re

def _roster_init_tables():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS exam_rosters (

            id INTEGER PRIMARY KEY AUTOINCREMENT,



            exam_config_id INTEGER NOT NULL UNIQUE,

            teacher_id INTEGER NOT NULL,

            exam_id TEXT NOT NULL,



            original_filename TEXT NOT NULL,

            students_count INTEGER NOT NULL DEFAULT 0,



            status TEXT NOT NULL DEFAULT 'READY',



            sent_at TEXT,

            sent_by TEXT,



            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,



            FOREIGN KEY(exam_config_id)

                REFERENCES exam_configs(id)

        )

    """)
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS exam_roster_students (

            id INTEGER PRIMARY KEY AUTOINCREMENT,



            roster_id INTEGER NOT NULL,

            line_number INTEGER NOT NULL,



            student_number TEXT NOT NULL,

            full_name TEXT NOT NULL,

            email TEXT NOT NULL,



            created_at TEXT NOT NULL,



            UNIQUE(

                roster_id,

                student_number

            ),



            FOREIGN KEY(roster_id)

                REFERENCES exam_rosters(id)

        )

    """)
    connection.commit()
    connection.close()


def _roster_normalize_header(
    value: str

) -> str:
    text = str(
        value or ""
    ).strip().lower()
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )
    text = _roster_re.sub(
        r"[^a-z0-9]+",
        "_",
        text
    )
    return text.strip("_")


def _roster_parse_csv(
    content: bytes,
    filename: str,

) -> list[dict]:
    if not filename.lower().endswith(".csv"):
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le fichier des étudiants "

                "doit être au format CSV."
            )
        )
    if len(content) > 2 * 1024 * 1024:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le fichier CSV est trop volumineux "

                "(maximum 2 Mo)."
            )
        )
    try:
        text = content.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le CSV doit être encodé en UTF-8."
            )
        )
    if not text.strip():
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le fichier CSV est vide."
            )
        )
    sample = text[:4096]
    try:
        dialect = _roster_csv.Sniffer().sniff(
            sample,
            delimiters=",;\t"
        )
    except _roster_csv.Error:
        first_line = (
            text.splitlines()[0]
            if text.splitlines()
            else ""
        )
        delimiter = (
            ";"
            if first_line.count(";")
            > first_line.count(",")
            else ","
        )
        class _FallbackDialect(
            _roster_csv.Dialect
        ):
            delimiter = delimiter
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = _roster_csv.QUOTE_MINIMAL
        dialect = _FallbackDialect
    reader = _roster_csv.DictReader(
        _roster_io.StringIO(text),
        dialect=dialect
    )
    if not reader.fieldnames:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "En-têtes CSV introuvables."
            )
        )
    normalized_headers = {
        _roster_normalize_header(
            field
        ): field
        for field in reader.fieldnames
        if field is not None
    }
    student_number_aliases = [
        "student_number",
        "numero_etudiant",
        "num_etudiant",
        "student_id",
        "identifiant",
        "numero",
    ]
    full_name_aliases = [
        "full_name",
        "nom_complet",
        "nom_prenom",
        "name",
    ]
    email_aliases = [
        "email",
        "mail",
        "adresse_email",
    ]
    def find_header(
        aliases: list[str]
    ):
        for alias in aliases:
            if alias in normalized_headers:
                return normalized_headers[
                    alias
                ]
        return None
    number_header = find_header(
        student_number_aliases
    )
    name_header = find_header(
        full_name_aliases
    )
    email_header = find_header(
        email_aliases
    )
    first_name_header = (
        normalized_headers.get("prenom")
        or normalized_headers.get(
            "first_name"
        )
    )
    last_name_header = (
        normalized_headers.get("nom")
        or normalized_headers.get(
            "last_name"
        )
    )
    if not number_header:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Colonne étudiant manquante. "

                "Utilisez student_number."
            )
        )
    if (
        not name_header
        and not (
            first_name_header
            and last_name_header
        )
    ):
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Colonne nom manquante. "

                "Utilisez full_name."
            )
        )
    if not email_header:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Colonne email manquante. "

                "Utilisez email."
            )
        )
    students = []
    seen_numbers = set()
    for line_number, row in enumerate(
        reader,
        start=2
    ):
        if not row:
            continue
        student_number = str(
            row.get(
                number_header,
                ""
            )
            or ""
        ).strip()
        if name_header:
            full_name = str(
                row.get(
                    name_header,
                    ""
                )
                or ""
            ).strip()
        else:
            first_name = str(
                row.get(
                    first_name_header,
                    ""
                )
                or ""
            ).strip()
            last_name = str(
                row.get(
                    last_name_header,
                    ""
                )
                or ""
            ).strip()
            full_name = (
                first_name
                + " "
                + last_name
            ).strip()
        email = str(
            row.get(
                email_header,
                ""
            )
            or ""
        ).strip()
        if (
            not student_number
            and not full_name
            and not email
        ):
            continue
        if not student_number:
            raise _RosterHTTPException(
                status_code=400,
                detail=(
                    f"Ligne {line_number} : "

                    "numéro étudiant manquant."
                )
            )
        if not full_name:
            raise _RosterHTTPException(
                status_code=400,
                detail=(
                    f"Ligne {line_number} : "

                    "nom étudiant manquant."
                )
            )
        if (
            not email
            or "@" not in email
        ):
            raise _RosterHTTPException(
                status_code=400,
                detail=(
                    f"Ligne {line_number} : "

                    "email étudiant invalide."
                )
            )
        normalized_number = (
            student_number.lower()
        )
        if normalized_number in seen_numbers:
            raise _RosterHTTPException(
                status_code=400,
                detail=(
                    "Numéro étudiant dupliqué "

                    f"dans le CSV : {student_number}"
                )
            )
        seen_numbers.add(
            normalized_number
        )
        students.append({
            "line_number":
                line_number,
            "student_number":
                student_number,
            "full_name":
                full_name,
            "email":
                email,
        })
    if not students:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le CSV ne contient aucun étudiant."
            )
        )
    return students


def _roster_parse_json_list(
    raw_value: str,
    field_name: str,

) -> list:
    try:
        value = _roster_json.loads(
            raw_value or "[]"
        )
    except _roster_json.JSONDecodeError:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                f"{field_name} invalide."
            )
        )
    if not isinstance(
        value,
        list
    ):
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                f"{field_name} doit être une liste."
            )
        )
    return value

# ---------------------------------------------------------
# Création examen + CSV obligatoire
# ---------------------------------------------------------


@app.post("/configs")
async def create_config_with_student_roster(
    exam_id:
        str
        = _RosterForm(...),
    exam_name:
        str
        = _RosterForm(...),
    exam_date:
        str
        = _RosterForm(...),
    exam_time:
        str
        = _RosterForm(...),
    packages_json:
        str
        = _RosterForm("[]"),
    sudo:
        bool
        = _RosterForm(False),
    internet:
        bool
        = _RosterForm(False),
    educ_access:
        bool
        = _RosterForm(False),
    allowed_domains_json:
        str
        = _RosterForm("[]"),
    roster_file:
        _RosterUploadFile
        = _RosterFile(...),
    current_teacher:
        dict
        = _RosterDepends(
            get_current_teacher
        ),

):
    _roster_init_tables()
    clean_exam_id = (
        exam_id or ""
    ).strip()
    clean_exam_name = (
        exam_name
        or clean_exam_id
    ).strip()
    clean_exam_date = (
        exam_date or ""
    ).strip()
    clean_exam_time = (
        exam_time or ""
    ).strip()
    if not clean_exam_id:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "L'identifiant de l'examen "

                "est obligatoire."
            )
        )
    if not clean_exam_name:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le nom de l'examen "

                "est obligatoire."
            )
        )
    if not clean_exam_date:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "La date de l'examen "

                "est obligatoire."
            )
        )
    if not clean_exam_time:
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "L'heure de l'examen "

                "est obligatoire."
            )
        )
    if (
        roster_file.filename is None
        or not roster_file.filename.strip()
    ):
        raise _RosterHTTPException(
            status_code=400,
            detail=(
                "Le fichier CSV des étudiants "

                "est obligatoire."
            )
        )
    roster_content = await roster_file.read()
    students = _roster_parse_csv(
        roster_content,
        roster_file.filename
    )
    packages = _roster_parse_json_list(
        packages_json,
        "packages"
    )
    allowed_domains = (
        _roster_parse_json_list(
            allowed_domains_json,
            "allowed_domains"
        )
    )
    requested_packages = set(
        str(item).strip()
        for item in packages
        if str(item).strip()
    )
    allowed_packages = (
        get_active_package_names()
    )
    invalid_packages = (
        requested_packages
        - allowed_packages
    )
    if invalid_packages:
        raise _RosterHTTPException(
            status_code=400,
            detail={
                "message":
                    "Paquets non autorisés",
                "invalid_packages":
                    sorted(
                        list(
                            invalid_packages
                        )
                    ),
            }
        )
    teacher_id = int(
        current_teacher["id"]
    )
    student_id = globals().get(
        "GLOBAL_STUDENT_ID",
        "GLOBAL"
    )
    machine_id = globals().get(
        "GLOBAL_MACHINE_ID",
        "ALL_MACHINES"
    )
    workspace = globals().get(
        "GLOBAL_WORKSPACE",
        "/home/exam/workspace"
    )
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""

            SELECT id

            FROM exam_configs

            WHERE

                teacher_id = ?

            AND

                exam_id = ?

            LIMIT 1

        """, (
            teacher_id,
            clean_exam_id,
        ))
        existing_config = (
            cursor.fetchone()
        )
        if existing_config is not None:
            raise _RosterHTTPException(
                status_code=409,
                detail=(
                    "Une configuration globale "

                    "existe déjà pour cet examen. "

                    "Supprimez l'ancienne avant "

                    "d'en recréer une."
                )
            )
        current_time = now_iso()
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

            VALUES (

                ?, ?, ?, ?, ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?, ?

            )

        """, (
            teacher_id,
            clean_exam_id,
            clean_exam_name,
            clean_exam_date,
            clean_exam_time,
            student_id,
            machine_id,
            _roster_json.dumps(
                packages,
                ensure_ascii=False
            ),
            int(bool(sudo)),
            int(bool(internet)),
            int(bool(educ_access)),
            _roster_json.dumps(
                allowed_domains,
                ensure_ascii=False
            ),
            workspace,
            current_time,
            current_time,
        ))
        config_id = int(
            cursor.lastrowid
        )
        cursor.execute("""

            INSERT INTO exam_rosters (

                exam_config_id,

                teacher_id,

                exam_id,

                original_filename,

                students_count,

                status,

                created_at,

                updated_at

            )

            VALUES (

                ?, ?, ?, ?, ?, 'READY', ?, ?

            )

        """, (
            config_id,
            teacher_id,
            clean_exam_id,
            Path(
                roster_file.filename
            ).name,
            len(students),
            current_time,
            current_time,
        ))
        roster_id = int(
            cursor.lastrowid
        )
        for student in students:
            cursor.execute("""

                INSERT INTO exam_roster_students (

                    roster_id,

                    line_number,

                    student_number,

                    full_name,

                    email,

                    created_at

                )

                VALUES (?, ?, ?, ?, ?, ?)

            """, (
                roster_id,
                student["line_number"],
                student["student_number"],
                student["full_name"],
                student["email"],
                current_time,
            ))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        raise
    connection.close()
    filename = config_filename(
        clean_exam_id,
        student_id,
        machine_id
    )
    return {
        "message":
            "Configuration et liste étudiants "

            "enregistrées avec succès.",
        "config_id":
            config_id,
        "file":
            filename,
        "roster": {
            "filename":
                Path(
                    roster_file.filename
                ).name,
            "students_count":
                len(students),
            "status":
                "READY",
        },
        "created_at":
            current_time,
    }

# ---------------------------------------------------------
# Auth admin autonome pour les routes de diffusion.
# Accepte admin + ancien supervisor pour migration.
# ---------------------------------------------------------


def _roster_current_admin(
    authorization:
        str | None
        = _RosterHeader(
            default=None
        )

):
    if (
        not authorization
        or not authorization.startswith(
            "Bearer "
        )
    ):
        raise _RosterHTTPException(
            status_code=401,
            detail=(
                "Authentification admin requise."
            )
        )
    token = authorization[
        len("Bearer "):
    ].strip()
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[
                ALGORITHM
            ]
        )
    except Exception:
        raise _RosterHTTPException(
            status_code=401,
            detail=(
                "Session admin invalide "

                "ou expirée."
            )
        )
    role = str(
        payload.get("role")
        or ""
    ).lower()
    if role not in {
        "admin",
        "supervisor",
    }:
        raise _RosterHTTPException(
            status_code=403,
            detail=(
                "Accès réservé "

                "à l'administrateur."
            )
        )
    return payload

# ---------------------------------------------------------
# Liste Admin :
# Config + professeur + CSV + statut diffusion
# ---------------------------------------------------------


@app.get(
    "/admin/exam-delivery"
)


def list_admin_exam_delivery(
    current_admin:
        dict
        = _RosterDepends(
            _roster_current_admin
        )

):
    _roster_init_tables()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            ec.id,

            ec.exam_id,

            ec.exam_name,

            ec.exam_date,

            ec.exam_time,

            ec.created_at,

            ec.updated_at,



            COALESCE(

                tp.full_name,

                t.username,

                'Professeur'

            ) AS professor_name,



            er.id AS roster_id,

            er.original_filename,

            er.students_count,

            er.status AS roster_status,

            er.sent_at



        FROM exam_configs ec



        LEFT JOIN teacher_profiles tp

            ON tp.teacher_id = ec.teacher_id



        LEFT JOIN teachers t

            ON t.id = ec.teacher_id



        LEFT JOIN exam_rosters er

            ON er.exam_config_id = ec.id



        ORDER BY

            ec.updated_at DESC,

            ec.id DESC

    """)
    rows = cursor.fetchall()
    connection.close()
    result = []
    for row in rows:
        keys = row.keys()
        exam_id = (
            row["exam_id"]
            or f"exam-{row['id']}"
        )
        result.append({
            "id":
                row["id"],
            "exam_id":
                exam_id,
            "exam_name":
                row["exam_name"]
                or exam_id,
            "professor_name":
                row["professor_name"]
                or "Professeur",
            "exam_date":
                row["exam_date"]
                or "",
            "exam_time":
                row["exam_time"]
                or "",
            "nix_filename":
                f"{exam_id}_exam-configuration.nix",
            "created_at":
                row["created_at"],
            "updated_at":
                row["updated_at"],
            "roster_id":
                row["roster_id"]
                if "roster_id" in keys
                else None,
            "roster_filename":
                row["original_filename"]
                if (
                    "original_filename" in keys
                    and row["original_filename"]
                )
                else "",
            "roster_count":
                int(
                    row["students_count"]
                    or 0
                )
                if (
                    "students_count" in keys
                )
                else 0,
            "roster_status":
                row["roster_status"]
                if (
                    "roster_status" in keys
                    and row["roster_status"]
                )
                else "MISSING",
            "sent_at":
                row["sent_at"]
                if "sent_at" in keys
                else None,
        })
    return result

# ---------------------------------------------------------
# Visualiser exactement les étudiants du CSV
# ---------------------------------------------------------


@app.get(
    "/admin/exam-delivery/{config_id}/roster"
)


def get_admin_exam_roster(
    config_id: int,
    current_admin:
        dict
        = _RosterDepends(
            _roster_current_admin
        )

):
    _roster_init_tables()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            ec.id,

            ec.exam_id,

            ec.exam_name,



            er.id AS roster_id,

            er.original_filename,

            er.students_count,

            er.status,

            er.sent_at



        FROM exam_configs ec



        LEFT JOIN exam_rosters er

            ON er.exam_config_id = ec.id



        WHERE ec.id = ?



        LIMIT 1

    """, (
        config_id,
    ))
    exam = cursor.fetchone()
    if exam is None:
        connection.close()
        raise _RosterHTTPException(
            status_code=404,
            detail=(
                "Configuration d'examen "

                "introuvable."
            )
        )
    if exam["roster_id"] is None:
        connection.close()
        raise _RosterHTTPException(
            status_code=404,
            detail=(
                "Aucune liste CSV associée "

                "à cet examen."
            )
        )
    cursor.execute("""

        SELECT

            line_number,

            student_number,

            full_name,

            email



        FROM exam_roster_students



        WHERE roster_id = ?



        ORDER BY

            line_number ASC,

            id ASC

    """, (
        exam["roster_id"],
    ))
    rows = cursor.fetchall()
    connection.close()
    return {
        "config_id":
            config_id,
        "exam_id":
            exam["exam_id"],
        "exam_name":
            exam["exam_name"]
            or exam["exam_id"],
        "filename":
            exam["original_filename"],
        "students_count":
            len(rows),
        "status":
            exam["status"],
        "sent_at":
            exam["sent_at"],
        "students": [
            {
                "line_number":
                    row["line_number"],
                "student_number":
                    row["student_number"],
                "full_name":
                    row["full_name"],
                "email":
                    row["email"],
            }
            for row in rows
        ],
    }

# ---------------------------------------------------------
# ENVOYER :
# Affectation EXACTE aux étudiants du CSV.
# Aucun envoi partiel.
# ---------------------------------------------------------


@app.post(
    "/admin/exam-delivery/{config_id}/send"
)


def send_exam_to_roster_students(
    config_id: int,
    current_admin:
        dict
        = _RosterDepends(
            _roster_current_admin
        )

):
    _roster_init_tables()
    if (
        "_student_init_tables"
        in globals()
    ):
        globals()[
            "_student_init_tables"
        ]()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            ec.id,

            ec.exam_id,

            ec.exam_name,



            er.id AS roster_id,

            er.status,

            er.sent_at



        FROM exam_configs ec



        INNER JOIN exam_rosters er

            ON er.exam_config_id = ec.id



        WHERE ec.id = ?



        LIMIT 1

    """, (
        config_id,
    ))
    exam = cursor.fetchone()
    if exam is None:
        connection.close()
        raise _RosterHTTPException(
            status_code=404,
            detail=(
                "Configuration ou liste "

                "étudiants introuvable."
            )
        )
    cursor.execute("""

        SELECT

            student_number,

            full_name,

            email



        FROM exam_roster_students



        WHERE roster_id = ?



        ORDER BY

            line_number ASC,

            id ASC

    """, (
        exam["roster_id"],
    ))
    roster_students = (
        cursor.fetchall()
    )
    if not roster_students:
        connection.close()
        raise _RosterHTTPException(
            status_code=409,
            detail=(
                "La liste étudiants est vide."
            )
        )
    resolved_students = []
    missing_students = []
    for roster_student in roster_students:
        cursor.execute("""

            SELECT

                id,

                username,

                student_number,

                full_name,

                email



            FROM student_accounts



            WHERE

                student_number = ?

            AND

                is_active = 1



            LIMIT 1

        """, (
            roster_student[
                "student_number"
            ],
        ))
        account = cursor.fetchone()
        if account is None:
            missing_students.append({
                "student_number":
                    roster_student[
                        "student_number"
                    ],
                "full_name":
                    roster_student[
                        "full_name"
                    ],
                "email":
                    roster_student[
                        "email"
                    ],
            })
        else:
            resolved_students.append(
                account
            )

    # AUCUN envoi partiel.
    if missing_students:
        connection.close()
        raise _RosterHTTPException(
            status_code=409,
            detail={
                "message":
                    (
                        "Envoi annulé : certains "

                        "étudiants n'ont pas de "

                        "compte SecureExam."
                    ),
                "missing_students":
                    missing_students,
                "missing_count":
                    len(
                        missing_students
                    ),
            }
        )

    # Déjà envoyé = idempotent.
    if (
        str(
            exam["status"]
            or ""
        ).upper()
        == "SENT"
    ):
        connection.close()
        return {
            "success":
                True,
            "already_sent":
                True,
            "exam_id":
                exam["exam_id"],
            "students_count":
                len(
                    resolved_students
                ),
            "sent_at":
                exam["sent_at"],
        }
    current_time = now_iso()
    try:
        connection.execute(
            "BEGIN"
        )
        allowed_student_ids = [
            int(
                account["id"]
            )
            for account
            in resolved_students
        ]

        # -------------------------------------------------
        # EXACTEMENT la liste CSV :
        # on retire toute affectation préalable externe
        # à la liste AVANT le premier envoi.
        # -------------------------------------------------
        placeholders = ",".join(
            "?"
            for _
            in allowed_student_ids
        )
        cursor.execute(
            f"""

            DELETE FROM student_exam_assignments



            WHERE

                exam_id = ?



            AND

                student_id NOT IN (

                    {placeholders}

                )

            """,
            [
                exam["exam_id"],
                *allowed_student_ids,
            ]
        )
        for account in resolved_students:
            cursor.execute("""

                INSERT OR IGNORE INTO

                    student_exam_assignments (

                        student_id,

                        exam_id,

                        machine_id,

                        status,

                        assigned_at,

                        updated_at

                    )



                VALUES (

                    ?, ?, '', 'A_VENIR', ?, ?

                )

            """, (
                account["id"],
                exam["exam_id"],
                current_time,
                current_time,
            ))
        admin_username = str(
            current_admin.get(
                "username"
            )
            or current_admin.get(
                "sub"
            )
            or "admin"
        )
        cursor.execute("""

            UPDATE exam_rosters



            SET

                status = 'SENT',

                sent_at = ?,

                sent_by = ?,

                updated_at = ?



            WHERE id = ?

        """, (
            current_time,
            admin_username,
            current_time,
            exam["roster_id"],
        ))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        raise
    connection.close()
    return {
        "success":
            True,
        "already_sent":
            False,
        "exam_id":
            exam["exam_id"],
        "students_count":
            len(
                resolved_students
            ),
        "sent_at":
            current_time,
        "message":
            (
                f"Examen envoyé à "

                f"{len(resolved_students)} "

                f"étudiant(s)."
            ),
    }

_roster_init_tables()







# =========================================================
# SECUREEXAM_TEACHER_DELIVERY_V5
#
# M?me logique d'envoi que l'administrateur.
# La seule diff?rence :
# le professeur ne peut envoyer que SA configuration.
# =========================================================


@app.post(
    "/teacher/exam-delivery/{config_id}/send"
)
def send_teacher_exam_to_students(
    config_id: int,

    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):

    _roster_init_tables()

    teacher_id = int(
        current_teacher["id"]
    )


    # -----------------------------------------------------
    # V?rification de propri?t?.
    # -----------------------------------------------------

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id

        FROM exam_configs

        WHERE
            id = ?
            AND teacher_id = ?

        LIMIT 1
    """, (
        config_id,
        teacher_id,
    ))

    owned_config = cursor.fetchone()

    connection.close()


    if owned_config is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration introuvable "
                "ou non autoris?e."
            )
        )


    # -----------------------------------------------------
    # UNE SEULE LOGIQUE METIER.
    #
    # On appelle directement la fonction Admin existante :
    #
    # - lecture CSV
    # - v?rification comptes ?tudiants
    # - aucun envoi partiel
    # - cr?ation affectations
    # - status = SENT
    # - sent_at
    # -----------------------------------------------------

    return send_exam_to_roster_students(
        config_id=config_id,
        current_admin=current_teacher
    )


# /SECUREEXAM_TEACHER_DELIVERY_V5




# =========================================================
# SECUREEXAM_TEACHER_ROSTER_PREVIEW_V1
# Meme liste CSV que l'espace Admin,
# avec controle de propriete professeur.
# =========================================================

@app.get(
    "/teacher/exam-delivery/{config_id}/roster"
)
def get_teacher_exam_roster(
    config_id: int,

    current_teacher:
        dict = Depends(
            get_current_teacher
        )
):

    _roster_init_tables()

    teacher_id = int(
        current_teacher["id"]
    )

    connection = get_connection()
    cursor = connection.cursor()


    cursor.execute("""
        SELECT id

        FROM exam_configs

        WHERE
            id = ?
            AND teacher_id = ?

        LIMIT 1

    """, (
        config_id,
        teacher_id,
    ))


    owned_config = cursor.fetchone()

    connection.close()


    if owned_config is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration introuvable "
                "ou non autorisee."
            )
        )


    # Meme fonction de lecture CSV que l'Admin.
    return get_admin_exam_roster(
        config_id=config_id,
        current_admin=current_teacher
    )


# /SECUREEXAM_TEACHER_ROSTER_PREVIEW_V1


# /SECUREEXAM_EXAM_ROSTER_DELIVERY_V1
# =========================================================
# SECUREEXAM_OFFICIAL_ENVIRONMENTS_V3_STARTUP
# =========================================================
ensure_official_exam_packages_v3()

# =========================================================
# SECUREEXAM CUSTOM ENVIRONMENTS SAVE FIX V6
# =========================================================


def ensure_secureexam_custom_environments_v6():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS custom_exam_environments (



            id INTEGER

                PRIMARY KEY

                AUTOINCREMENT,



            teacher_id INTEGER

                NOT NULL,



            name TEXT

                NOT NULL

                COLLATE NOCASE,



            packages TEXT

                NOT NULL,



            created_at TEXT

                NOT NULL,



            updated_at TEXT

                NOT NULL,



            UNIQUE(

                teacher_id,

                name

            )

        )

    """)
    connection.commit()
    connection.close()


def secureexam_custom_environment_dict(
    row

):
    try:
        packages = json.loads(
            row["packages"] or "[]"
        )
    except Exception:
        packages = []
    return {
        "id":
            row["id"],
        "name":
            row["name"],
        "packages":
            packages,
        "created_at":
            row["created_at"],
        "updated_at":
            row["updated_at"]
    }


@app.get(
    "/exam-environments/custom"
)


def secureexam_list_custom_environments_v6(
    current_teacher:
        dict = Depends(
            get_current_teacher
        )

):
    ensure_secureexam_custom_environments_v6()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            id,

            name,

            packages,

            created_at,

            updated_at



        FROM custom_exam_environments



        WHERE teacher_id = ?



        ORDER BY

            updated_at DESC,

            id DESC

    """, (
        current_teacher["id"],
    ))
    rows = cursor.fetchall()
    connection.close()
    environments = [
        secureexam_custom_environment_dict(
            row
        )
        for row
        in rows
    ]
    return {
        "count":
            len(environments),
        "environments":
            environments
    }

# =========================================================
# SECUREEXAM_CUSTOM_ENVIRONMENT_RULES_V12
# =========================================================
SECUREEXAM_RESERVED_ENVIRONMENT_NAMES_V12 = (
    "Python",
    "C / C++",
    "Java / POO",
    "Web",
    "SQL / BDD",
    "Linux / Shell",
)


class SecureExamCustomEnvironmentPayloadV12(
    BaseModel

):
    name: str
    packages: List[str]


def ensure_custom_environment_table_v12():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        CREATE TABLE IF NOT EXISTS

        custom_exam_environments (



            id INTEGER

                PRIMARY KEY

                AUTOINCREMENT,



            teacher_id INTEGER

                NOT NULL,



            name TEXT

                NOT NULL,



            packages TEXT

                NOT NULL,



            created_at TEXT

                NOT NULL,



            updated_at TEXT

                NOT NULL

        )

    """)
    connection.commit()
    connection.close()


def normalize_environment_name_v12(
    value: str

) -> str:
    text = str(
        value
        or ""
    ).strip().casefold()

    # Permet également de considérer :
    #
    # C/C++
    # C / C++
    #
    # comme le même nom.
    return re.sub(
        r"[^a-z0-9+]+",
        "",
        text
    )


def reserved_environment_name_v12(
    value: str

):
    normalized = (
        normalize_environment_name_v12(
            value
        )
    )
    for official_name in (
        SECUREEXAM_RESERVED_ENVIRONMENT_NAMES_V12
    ):
        if (
            normalize_environment_name_v12(
                official_name
            )
            == normalized
        ):
            return official_name
    return None


def validate_custom_environment_name_v12(
    value: str,
    teacher_id: int,
    current_environment_id=None

) -> str:
    name = str(
        value
        or ""
    ).strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le nom de la configuration "

                "personnalisée est obligatoire."
            )
        )
    if len(name) > 80:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le nom de la configuration "

                "ne peut pas dépasser "

                "80 caractères."
            )
        )
    reserved_name = (
        reserved_environment_name_v12(
            name
        )
    )
    if reserved_name:
        raise HTTPException(
            status_code=409,
            detail=(
                f'Le nom "{reserved_name}" est '

                "réservé à une configuration "

                "officielle SecureExam. "

                "Choisissez un autre nom."
            )
        )
    ensure_custom_environment_table_v12()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            id,

            name



        FROM custom_exam_environments



        WHERE teacher_id = ?

    """, (
        teacher_id,
    ))
    rows = cursor.fetchall()
    connection.close()
    normalized_name = (
        normalize_environment_name_v12(
            name
        )
    )
    for row in rows:
        row_id = int(
            row["id"]
        )
        if (
            current_environment_id
            is not None
            and row_id
            == int(
                current_environment_id
            )
        ):
            continue
        if (
            normalize_environment_name_v12(
                row["name"]
            )
            == normalized_name
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Vous possédez déjà une "

                    "configuration personnalisée "

                    f'nommée "{row["name"]}".'
                )
            )
    return name


def validate_custom_environment_packages_v12(
    packages

):
    result = []
    seen = set()
    for raw_value in (
        packages
        or []
    ):
        value = str(
            raw_value
            or ""
        ).strip()
        if (
            not value
            or value in seen
        ):
            continue
        seen.add(
            value
        )
        result.append(
            value
        )
    if not result:
        raise HTTPException(
            status_code=400,
            detail=(
                "Sélectionnez au moins "

                "un logiciel."
            )
        )
    active_packages = (
        get_active_package_names()
    )
    invalid = [
        package_name
        for package_name
        in result
        if package_name
        not in active_packages
    ]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "message":
                    "Certains logiciels ne sont "

                    "pas disponibles dans "

                    "la bibliothèque SecureExam.",
                "invalid_packages":
                    invalid
            }
        )
    return result


def custom_environment_to_dict_v12(
    row

):
    try:
        packages = json.loads(
            row["packages"]
            or "[]"
        )
    except Exception:
        packages = []
    return {
        "id":
            row["id"],
        "name":
            row["name"],
        "packages":
            packages,
        "created_at":
            row["created_at"],
        "updated_at":
            row["updated_at"]
    }

ensure_custom_environment_table_v12()


@app.post(
    "/exam-environments/custom"
)


def create_custom_environment_v12(
    payload:
        SecureExamCustomEnvironmentPayloadV12,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )

):
    teacher_id = int(
        current_teacher["id"]
    )
    name = (
        validate_custom_environment_name_v12(
            payload.name,
            teacher_id
        )
    )
    packages = (
        validate_custom_environment_packages_v12(
            payload.packages
        )
    )
    timestamp = now_iso()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        INSERT INTO custom_exam_environments (

            teacher_id,

            name,

            packages,

            created_at,

            updated_at

        )

        VALUES (?, ?, ?, ?, ?)

    """, (
        teacher_id,
        name,
        json.dumps(
            packages,
            ensure_ascii=False
        ),
        timestamp,
        timestamp
    ))
    environment_id = int(
        cursor.lastrowid
    )
    connection.commit()
    cursor.execute("""

        SELECT

            id,

            name,

            packages,

            created_at,

            updated_at



        FROM custom_exam_environments



        WHERE

            id = ?

            AND teacher_id = ?



        LIMIT 1

    """, (
        environment_id,
        teacher_id
    ))
    row = cursor.fetchone()
    connection.close()
    return {
        "success":
            True,
        "message":
            "Configuration personnalisée enregistrée.",
        "environment":
            custom_environment_to_dict_v12(
                row
            )
    }


@app.put(
    "/exam-environments/custom/{environment_id}"
)


def update_custom_environment_v12(
    environment_id: int,
    payload:
        SecureExamCustomEnvironmentPayloadV12,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )

):
    teacher_id = int(
        current_teacher["id"]
    )
    ensure_custom_environment_table_v12()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT id



        FROM custom_exam_environments



        WHERE

            id = ?

            AND teacher_id = ?



        LIMIT 1

    """, (
        environment_id,
        teacher_id
    ))
    if cursor.fetchone() is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration personnalisée "

                "introuvable."
            )
        )
    connection.close()
    name = (
        validate_custom_environment_name_v12(
            payload.name,
            teacher_id,
            environment_id
        )
    )
    packages = (
        validate_custom_environment_packages_v12(
            payload.packages
        )
    )
    timestamp = now_iso()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        UPDATE custom_exam_environments



        SET

            name = ?,

            packages = ?,

            updated_at = ?



        WHERE

            id = ?

            AND teacher_id = ?

    """, (
        name,
        json.dumps(
            packages,
            ensure_ascii=False
        ),
        timestamp,
        environment_id,
        teacher_id
    ))
    connection.commit()
    cursor.execute("""

        SELECT

            id,

            name,

            packages,

            created_at,

            updated_at



        FROM custom_exam_environments



        WHERE

            id = ?

            AND teacher_id = ?



        LIMIT 1

    """, (
        environment_id,
        teacher_id
    ))
    row = cursor.fetchone()
    connection.close()
    return {
        "success":
            True,
        "message":
            "Configuration personnalisée mise à jour.",
        "environment":
            custom_environment_to_dict_v12(
                row
            )
    }


@app.delete(
    "/exam-environments/custom/{environment_id}"
)


def delete_custom_environment_v12(
    environment_id: int,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )

):
    teacher_id = int(
        current_teacher["id"]
    )
    ensure_custom_environment_table_v12()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""

        SELECT

            id,

            name



        FROM custom_exam_environments



        WHERE

            id = ?

            AND teacher_id = ?



        LIMIT 1

    """, (
        environment_id,
        teacher_id
    ))
    environment = cursor.fetchone()
    if environment is None:
        connection.close()
        raise HTTPException(
            status_code=404,
            detail=(
                "Configuration personnalisée "

                "introuvable ou non autorisée."
            )
        )
    deleted_name = (
        environment["name"]
    )
    cursor.execute("""

        DELETE FROM custom_exam_environments



        WHERE

            id = ?

            AND teacher_id = ?

    """, (
        environment_id,
        teacher_id
    ))
    if cursor.rowcount != 1:
        connection.rollback()
        connection.close()
        raise HTTPException(
            status_code=500,
            detail=(
                "La configuration n'a pas "

                "pu être supprimée."
            )
        )
    connection.commit()
    connection.close()
    return {
        "success":
            True,
        "message":
            (
                f'Configuration "{deleted_name}" '

                "supprimée."
            ),
        "deleted_environment_id":
            environment_id
    }

# =========================================================
# SECUREEXAM_NIXPKGS_TERMINAL_V2
#
# Terminal contrôlé pour les environnements personnalisés.
#
# Exemple professeur :
#
#   add python 3.12
#   add gcc
#   add nodejs 22
#   remove python312
#   list
#
# Le backend Windows interroge search.nixos.org.
# Aucun shell libre n'est exécuté.
# =========================================================


class SecureExamNixpkgsTerminalRequestV2(BaseModel):
    command: str
    packages: Optional[List[str]] = None

SECUREEXAM_NIXPKGS_CHANNEL_V2 = (
    os.getenv(
        "SECUREEXAM_NIXPKGS_CHANNEL",
        "unstable"
    )
    .strip()
)
SECUREEXAM_NIXOS_SEARCH_USER_V2 = (
    os.getenv(
        "SECUREEXAM_NIXOS_SEARCH_USER",
        "aWVSALXpZv"
    )
)
SECUREEXAM_NIXOS_SEARCH_PASSWORD_V2 = (
    os.getenv(
        "SECUREEXAM_NIXOS_SEARCH_PASSWORD",
        "X8gPHnzL52wFEekuxsfQ9cSh"
    )
)
SECUREEXAM_NIXOS_SEARCH_SCHEMA_V2 = 48


def secureexam_terminal_normalize_v2(
    value

) -> str:
    return str(
        value
        or ""
    ).strip()


def secureexam_terminal_package_key_v2(
    value

) -> str:
    return re.sub(
        r"[^a-z0-9+._-]+",
        "",
        secureexam_terminal_normalize_v2(
            value
        ).casefold()
    )


def secureexam_nixos_auth_header_v2() -> str:
    import base64
    raw = (
        f"{SECUREEXAM_NIXOS_SEARCH_USER_V2}:"

        f"{SECUREEXAM_NIXOS_SEARCH_PASSWORD_V2}"
    )
    encoded = base64.b64encode(
        raw.encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


def secureexam_nixos_request_v2(
    url: str,
    payload: dict | None = None,
    method: str = "POST"

):
    import urllib.request
    import urllib.error
    data = None
    if payload is not None:
        data = json.dumps(
            payload
        ).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=data,
        method=method
    )
    request.add_header(
        "Authorization",
        secureexam_nixos_auth_header_v2()
    )
    request.add_header(
        "Content-Type",
        "application/json"
    )
    request.add_header(
        "User-Agent",
        "SecureExam/1.0"
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(
                body.decode("utf-8")
            )
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = (
                error.read()
                .decode(
                    "utf-8",
                    errors="replace"
                )
            )
        except Exception:
            pass
        raise RuntimeError(
            f"NixOS Search HTTP {error.code}: {body}"
        )
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Impossible de joindre search.nixos.org : "

            f"{error}"
        )


def secureexam_probe_schema_v2(
    schema: int,
    channel: str

) -> bool:
    import urllib.request
    import urllib.error
    url = (
        "https://search.nixos.org/backend/"

        f"latest-{schema}-nixos-{channel}"
    )
    request = urllib.request.Request(
        url=url,
        method="HEAD"
    )
    request.add_header(
        "Authorization",
        secureexam_nixos_auth_header_v2()
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=8
        ) as response:
            return (
                response.status
                == 200
            )
    except Exception:
        return False


def secureexam_resolve_schema_v2(
    channel: str

) -> int:
    current = (
        SECUREEXAM_NIXOS_SEARCH_SCHEMA_V2
    )
    candidates = [
        current,
        current + 5,
        current + 4,
        current + 3,
        current + 2,
        current + 1,
        current - 1,
        current - 2,
        current - 3,
        current - 4,
        current - 5,
    ]
    for schema in candidates:
        if schema <= 0:
            continue
        if secureexam_probe_schema_v2(
            schema,
            channel
        ):
            return schema
    raise RuntimeError(
        "Impossible de trouver l'index "

        "Nixpkgs actif sur search.nixos.org."
    )


def secureexam_build_nix_search_query_v2(
    query: str,
    size: int = 50

) -> dict:
    return {
        "from":
            0,
        "size":
            size,
        "query": {
            "bool": {
                "filter": [
                    {
                        "term": {
                            "type": {
                                "value":
                                    "package"
                            }
                        }
                    }
                ],
                "must": [
                    {
                        "dis_max": {
                            "tie_breaker":
                                0.7,
                            "queries": [
                                {
                                    "multi_match": {
                                        "type":
                                            "cross_fields",
                                        "query":
                                            query,
                                        "analyzer":
                                            "whitespace",
                                        "operator":
                                            "and",
                                        "fields": [
                                            "package_attr_name^9",
                                            "package_attr_name.*^5.4",
                                            "package_pname^6",
                                            "package_pname.*^3.6",
                                            "package_description^1.3",
                                            "package_longDescription^1"
                                        ]
                                    }
                                },
                                {
                                    "multi_match": {
                                        "type":
                                            "best_fields",
                                        "query":
                                            query,
                                        "analyzer":
                                            "whitespace",
                                        "operator":
                                            "and",
                                        "fields": [
                                            "package_programs^7.5"
                                        ],
                                        "fuzziness":
                                            1
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }


def secureexam_search_nixpkgs_v2(
    package_query: str

) -> list[dict]:
    query = (
        secureexam_terminal_normalize_v2(
            package_query
        )
    )
    if len(query) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le nom du logiciel doit "

                "contenir au moins 2 caractères."
            )
        )
    if not re.fullmatch(
        r"[a-zA-Z0-9._+\-]+",
        query
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Nom de logiciel invalide."
            )
        )
    channel = (
        SECUREEXAM_NIXPKGS_CHANNEL_V2
    )
    if not re.fullmatch(
        r"(?:unstable|\d{2}\.\d{2})",
        channel
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "SECUREEXAM_NIXPKGS_CHANNEL "

                "est invalide."
            )
        )
    try:
        schema = (
            secureexam_resolve_schema_v2(
                channel
            )
        )
        url = (
            "https://search.nixos.org/backend/"

            f"latest-{schema}-nixos-{channel}"

            "/_search"
        )
        response = (
            secureexam_nixos_request_v2(
                url,
                secureexam_build_nix_search_query_v2(
                    query
                )
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message":
                    (
                        "Impossible d'interroger "

                        "Nixpkgs."
                    ),
                "error":
                    str(error)
            }
        )
    hits = (
        response
        .get("hits", {})
        .get("hits", [])
    )
    result = []
    for hit in hits:
        source = (
            hit.get(
                "_source",
                {}
            )
            or {}
        )
        nix_name = str(
            source.get(
                "package_attr_name",
                ""
            )
            or ""
        ).strip()
        pname = str(
            source.get(
                "package_pname",
                ""
            )
            or nix_name
        ).strip()
        version = str(
            source.get(
                "package_pversion",
                ""
            )
            or ""
        ).strip()
        description = str(
            source.get(
                "package_description",
                ""
            )
            or ""
        ).strip()
        if not nix_name:
            continue
        if not re.fullmatch(
            r"[a-zA-Z0-9._+\-]+",
            nix_name
        ):
            continue
        result.append({
            "nixName":
                nix_name,
            "pname":
                pname,
            "version":
                version,
            "description":
                description,
            "channel":
                channel,
            "verified":
                True
        })
    return result


def secureexam_version_matches_v2(
    actual_version: str,
    requested_version: str

) -> bool:
    actual = str(
        actual_version
        or ""
    ).strip().lower()
    requested = str(
        requested_version
        or ""
    ).strip().lower()
    if requested.startswith("v"):
        requested = requested[1:]
    if actual.startswith("v"):
        actual = actual[1:]
    if not requested:
        return True
    if actual == requested:
        return True
    for separator in (
        ".",
        "-",
        "+",
        "_"
    ):
        if actual.startswith(
            requested + separator
        ):
            return True
    return False


def secureexam_candidate_score_v2(
    candidate: dict,
    package_query: str

):
    query = (
        secureexam_terminal_package_key_v2(
            package_query
        )
    )
    nix_name = (
        secureexam_terminal_package_key_v2(
            candidate.get(
                "nixName",
                ""
            )
        )
    )
    pname = (
        secureexam_terminal_package_key_v2(
            candidate.get(
                "pname",
                ""
            )
        )
    )
    if nix_name == query:
        return (
            0,
            len(nix_name)
        )
    if pname == query:
        return (
            1,
            len(nix_name)
        )
    if nix_name.startswith(
        query
    ):
        return (
            2,
            len(nix_name)
        )
    if pname.startswith(
        query
    ):
        return (
            3,
            len(nix_name)
        )
    if query in nix_name:
        return (
            4,
            len(nix_name)
        )
    return (
        5,
        len(nix_name)
    )


def secureexam_resolve_package_v2(
    package_query: str,
    requested_version: str = ""

) -> dict:
    candidates = (
        secureexam_search_nixpkgs_v2(
            package_query
        )
    )
    if requested_version:
        candidates = [
            candidate
            for candidate
            in candidates
            if secureexam_version_matches_v2(
                candidate.get(
                    "version",
                    ""
                ),
                requested_version
            )
        ]
    if not candidates:
        suffix = (
            f" version {requested_version}"
            if requested_version
            else ""
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Aucun paquet Nixpkgs correspondant "

                f"à {package_query}{suffix}."
            )
        )
    candidates.sort(
        key=lambda candidate:
            secureexam_candidate_score_v2(
                candidate,
                package_query
            )
    )
    return candidates[0]


def secureexam_catalog_package_v2(
    nix_candidate: dict

):
    nix_name = (
        nix_candidate["nixName"]
    )
    version = str(
        nix_candidate.get(
            "version",
            ""
        )
        or ""
    ).strip()
    pname = str(
        nix_candidate.get(
            "pname",
            nix_name
        )
        or nix_name
    ).strip()
    description = str(
        nix_candidate.get(
            "description",
            ""
        )
        or ""
    ).strip()
    display_name = pname
    if version:
        display_name = (
            f"{pname} {version}"
        )
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



        WHERE

            LOWER(name) = LOWER(?)

            OR LOWER(nix_name) = LOWER(?)



        LIMIT 1

    """, (
        nix_name,
        nix_name
    ))
    existing = (
        cursor.fetchone()
    )
    if existing is not None:
        if not bool(
            existing["is_active"]
        ):
            connection.close()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Ce paquet existe dans "

                    "SecureExam mais il est "

                    "désactivé."
                )
            )
        connection.close()
        return {
            "id":
                existing["id"],
            "name":
                existing["name"],
            "nixName":
                existing["nix_name"]
                or existing["name"],
            "displayName":
                existing["display_name"],
            "description":
                existing["description"],
            "version":
                version,
            "channel":
                nix_candidate.get(
                    "channel",
                    ""
                ),
            "verified":
                True,
            "catalogCreated":
                False
        }
    current_time = (
        now_iso()
    )
    if not description:
        description = (
            f"Paquet Nixpkgs {nix_name}."
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

        VALUES (?, ?, ?, ?, 1, ?, ?)

    """, (
        nix_name,
        nix_name,
        display_name,
        description,
        current_time,
        current_time
    ))
    package_id = int(
        cursor.lastrowid
    )
    connection.commit()
    connection.close()
    return {
        "id":
            package_id,
        "name":
            nix_name,
        "nixName":
            nix_name,
        "displayName":
            display_name,
        "description":
            description,
        "version":
            version,
        "channel":
            nix_candidate.get(
                "channel",
                ""
            ),
        "verified":
            True,
        "catalogCreated":
            True
    }


def secureexam_terminal_items_v2(
    package_names

) -> list[dict]:
    clean_names = []
    for value in (
        package_names
        or []
    ):
        name = (
            secureexam_terminal_normalize_v2(
                value
            )
        )
        if (
            name
            and name not in clean_names
        ):
            clean_names.append(
                name
            )
    if not clean_names:
        return []
    placeholders = ",".join(
        "?"
        for _ in clean_names
    )
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        f"""

        SELECT

            id,

            name,

            nix_name,

            display_name,

            description,

            is_active



        FROM package_catalog



        WHERE name IN ({placeholders})

        """,
        tuple(
            clean_names
        )
    )
    rows = (
        cursor.fetchall()
    )
    connection.close()
    by_name = {
        row["name"]:
            row
        for row in rows
    }
    result = []
    for name in clean_names:
        row = by_name.get(
            name
        )
        if row is None:
            continue
        result.append({
            "id":
                row["id"],
            "name":
                row["name"],
            "nixName":
                row["nix_name"]
                or row["name"],
            "displayName":
                row["display_name"],
            "description":
                row["description"],
            "isActive":
                bool(
                    row["is_active"]
                )
        })
    return result


@app.post(
    "/exam-environments/package-terminal"
)


def secureexam_package_terminal_v2(
    payload:
        SecureExamNixpkgsTerminalRequestV2,
    current_teacher:
        dict = Depends(
            get_current_teacher
        )

):
    command = (
        secureexam_terminal_normalize_v2(
            payload.command
        )
    )
    packages = []
    for value in (
        payload.packages
        or []
    ):
        name = (
            secureexam_terminal_normalize_v2(
                value
            )
        )
        if (
            name
            and name not in packages
        ):
            packages.append(
                name
            )
    if not command:
        raise HTTPException(
            status_code=400,
            detail="Commande vide."
        )
    parts = (
        command.split()
    )
    action = (
        parts[0].casefold()
    )

    # -----------------------------------------------------
    # HELP
    # -----------------------------------------------------
    if action in {
        "help",
        "aide",
        "?"
    }:
        return {
            "success":
                True,
            "action":
                "help",
            "message":
                (
                    "Commandes : "

                    "add <logiciel> [version], "

                    "remove <paquet>, "

                    "list, clear, help."
                ),
            "packages":
                packages,
            "items":
                secureexam_terminal_items_v2(
                    packages
                ),
            "channel":
                SECUREEXAM_NIXPKGS_CHANNEL_V2
        }

    # -----------------------------------------------------
    # LIST
    # -----------------------------------------------------
    if action == "list":
        return {
            "success":
                True,
            "action":
                "list",
            "message":
                (
                    f"{len(packages)} paquet(s) "

                    "dans l'environnement."
                ),
            "packages":
                packages,
            "items":
                secureexam_terminal_items_v2(
                    packages
                ),
            "channel":
                SECUREEXAM_NIXPKGS_CHANNEL_V2
        }

    # -----------------------------------------------------
    # CLEAR
    # -----------------------------------------------------
    if action == "clear":
        return {
            "success":
                True,
            "action":
                "clear",
            "message":
                "Liste vidée.",
            "packages":
                [],
            "items":
                [],
            "channel":
                SECUREEXAM_NIXPKGS_CHANNEL_V2
        }

    # -----------------------------------------------------
    # ADD
    # -----------------------------------------------------
    if action == "add":
        if len(parts) not in {
            2,
            3
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Syntaxe : "

                    "add <logiciel> [version]. "

                    "Exemple : "

                    "add python 3.12"
                )
            )
        package_query = (
            parts[1]
        )
        requested_version = (
            parts[2]
            if len(parts) == 3
            else ""
        )
        if requested_version:
            if not re.fullmatch(
                r"[vV]?[0-9][a-zA-Z0-9._+\-]*",
                requested_version
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Version invalide."
                    )
                )
        candidate = (
            secureexam_resolve_package_v2(
                package_query,
                requested_version
            )
        )
        package = (
            secureexam_catalog_package_v2(
                candidate
            )
        )
        package_name = (
            package["name"]
        )
        added = (
            package_name
            not in packages
        )
        if added:
            packages.append(
                package_name
            )
        return {
            "success":
                True,
            "action":
                "add",
            "message":
                (
                    f'{package["displayName"]} '
                    + (
                        "ajouté à l'environnement."
                        if added
                        else
                        "est déjà présent."
                    )
                ),
            "package":
                package,
            "packages":
                packages,
            "items":
                secureexam_terminal_items_v2(
                    packages
                ),
            "source":
                "search.nixos.org",
            "onlineVerified":
                True,
            "channel":
                SECUREEXAM_NIXPKGS_CHANNEL_V2
        }

    # -----------------------------------------------------
    # REMOVE
    # -----------------------------------------------------
    if action in {
        "remove",
        "rm"
    }:
        if len(parts) != 2:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Syntaxe : "

                    "remove <paquet>"
                )
            )
        requested = (
            secureexam_terminal_package_key_v2(
                parts[1]
            )
        )
        removed = None
        items = (
            secureexam_terminal_items_v2(
                packages
            )
        )
        for item in items:
            keys = {
                secureexam_terminal_package_key_v2(
                    item["name"]
                ),
                secureexam_terminal_package_key_v2(
                    item["nixName"]
                ),
                secureexam_terminal_package_key_v2(
                    item["displayName"]
                )
            }
            if requested in keys:
                removed = (
                    item["name"]
                )
                break
        if removed is not None:
            packages = [
                name
                for name
                in packages
                if name != removed
            ]
        return {
            "success":
                True,
            "action":
                "remove",
            "message":
                (
                    f"{removed} retiré."
                    if removed
                    else
                    "Paquet absent de l'environnement."
                ),
            "removed":
                removed is not None,
            "packages":
                packages,
            "items":
                secureexam_terminal_items_v2(
                    packages
                ),
            "channel":
                SECUREEXAM_NIXPKGS_CHANNEL_V2
        }
    raise HTTPException(
        status_code=400,
        detail=(
            "Commande inconnue. "

            "Tapez help."
        )
    )

# /SECUREEXAM_NIXPKGS_TERMINAL_V2
