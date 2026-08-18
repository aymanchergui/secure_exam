from pathlib import Path
from datetime import datetime
import json
import os
import sys
import zipfile

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()
SETTINGS_FILE = Path("client_settings.json")
ARCHIVE_DIR = Path("archives")


def load_json_file(path: Path, default: dict) -> dict:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def get_execution_mode() -> str:
    settings = load_json_file(SETTINGS_FILE, {})
    mode = settings.get("execution_mode", "simulation")
    mode = str(mode).strip().lower()

    if mode not in ["simulation", "real"]:
        print(f"Mode d'exécution invalide : {mode}")
        print("Valeurs autorisées : simulation ou real")
        sys.exit(1)

    return mode


def get_workspace_path(config: dict, execution_mode: str) -> Path:
    if execution_mode == "real":
        workspace = Path(config["workspace"])

        if not workspace.as_posix().startswith("/home/exam/"):
            print(f"Workspace réel refusé pour sécurité : {workspace}")
            print("Le workspace réel doit être sous /home/exam/")
            sys.exit(1)

        return workspace

    return Path("runtime") / "home" / "exam" / config["student_id"] / "workspace"


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def restore_file_owner_for_user(path: Path) -> None:
    """
    Si le script est lancé avec sudo, l'archive est créée par root.
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


def main() -> None:
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("BACKUP_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    execution_mode = get_execution_mode()
    workspace = get_workspace_path(config, execution_mode)

    ARCHIVE_DIR.mkdir(exist_ok=True)

    if not workspace.exists():
        print(f"Dossier de travail introuvable : {workspace}")
        write_log("BACKUP_ERROR", f"Dossier de travail introuvable : {workspace}")
        sys.exit(1)

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print(f"Le workspace réel appartient à l'utilisateur exam : {workspace}")
        print("Relance la fin d'examen avec :")
        print('sudo -E "$(which python3)" finish_exam.py')
        write_log("BACKUP_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_{timestamp}.zip"
    archive_path = ARCHIVE_DIR / archive_name

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in workspace.rglob("*"):
            if file.is_file() and not file.is_symlink():
                zipf.write(file, file.relative_to(workspace))

    restore_file_owner_for_user(archive_path)

    print("Sauvegarde créée avec succès")
    print(f"Mode      : {execution_mode}")
    print(f"Workspace : {workspace}")
    print(f"Archive   : {archive_path}")

    write_log("BACKUP", f"Mode : {execution_mode}")
    write_log("BACKUP", f"Workspace sauvegardé : {workspace}")
    write_log("BACKUP", f"Archive créée : {archive_path}")


if __name__ == "__main__":
    main()