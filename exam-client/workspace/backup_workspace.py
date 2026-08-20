from pathlib import Path
from datetime import datetime
import json
import os
import sys
import zipfile

CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import (
    ARCHIVE_DIR,
    get_config_path,
    get_execution_mode,
    get_workspace_path
)
from core.logger import write_log

CONFIG_FILE = get_config_path()

def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0

def restore_file_owner_for_user(path: Path) -> None:
    """
    Si le script est lancé avec sudo, l'archive peut être créée par root.
    On la redonne à l'utilisateur original pour faciliter la suite.
    """
    sudo_uid = os.getenv("SUDO_UID")
    sudo_gid = os.getenv("SUDO_GID")

    if sudo_uid is None or sudo_gid is None:
        return

    try:
        os.chown(path, int(sudo_uid), int(sudo_gid))
    except Exception:
        pass

def load_config() -> dict:
    """
    Charge la configuration d'examen récupérée depuis le backend.
    """
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("BACKUP_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Configuration invalide : {CONFIG_FILE}")
        print(error)
        write_log("BACKUP_ERROR", f"Configuration JSON invalide : {error}")
        sys.exit(1)

def create_archive(config: dict, workspace: Path) -> Path:
    """
    Crée une archive ZIP du workspace étudiant.
    Les liens symboliques sont ignorés pour éviter de sortir du dossier de rendu.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_{timestamp}.zip"
    archive_path = ARCHIVE_DIR / archive_name

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in workspace.rglob("*"):
            if file.is_file() and not file.is_symlink():
                zipf.write(file, file.relative_to(workspace))

    restore_file_owner_for_user(archive_path)

    return archive_path

def main() -> None:
    config = load_config()
    execution_mode = get_execution_mode()
    workspace = get_workspace_path(config)

    if not workspace.exists():
        print(f"Dossier de travail introuvable : {workspace}")
        write_log("BACKUP_ERROR", f"Dossier de travail introuvable : {workspace}")
        sys.exit(1)

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print(f"Le workspace réel appartient à l'utilisateur exam : {workspace}")
        print("Relance la fin d'examen avec :")
        print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" flows/finish_exam.py')
        write_log("BACKUP_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    archive_path = create_archive(config, workspace)

    print("Sauvegarde créée avec succès")
    print(f"Mode      : {execution_mode}")
    print(f"Workspace : {workspace}")
    print(f"Archive   : {archive_path}")

    write_log("BACKUP", f"Mode : {execution_mode}")
    write_log("BACKUP", f"Workspace sauvegardé : {workspace}")
    write_log("BACKUP", f"Archive créée : {archive_path}")

if __name__ == "__main__":
    main()
