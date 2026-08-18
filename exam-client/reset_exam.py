from pathlib import Path
import json
import os
import pwd
import grp
import shutil
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()
SETTINGS_FILE = Path("client_settings.json")
ARCHIVE_DIR = Path("archives")
SUBMITTED_MARKER = Path("submitted") / "last_submission.json"


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


def set_exam_permissions(path: Path) -> None:
    """
    En mode réel, le workspace doit appartenir à exam:exam.
    """
    exam_uid = pwd.getpwnam("exam").pw_uid
    exam_gid = grp.getgrnam("exam").gr_gid

    os.chown(path, exam_uid, exam_gid)
    os.chmod(path, 0o750)


def main() -> None:
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("RESET_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    execution_mode = get_execution_mode()
    workspace = get_workspace_path(config, execution_mode)

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print(f"Le workspace réel appartient à l'utilisateur exam : {workspace}")
        print("Relance la fin d'examen avec :")
        print('sudo -E "$(which python3)" finish_exam.py')
        write_log("RESET_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
    archives = list(ARCHIVE_DIR.glob(archive_pattern))

    print("Vérification avant remise à zéro")
    print("--------------------------------")
    print(f"Mode      : {execution_mode}")
    print(f"Workspace : {workspace}")

    if not archives:
        print("Aucune archive locale trouvée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : aucune archive locale trouvée")
        sys.exit(1)

    latest_archive = max(archives, key=lambda p: p.stat().st_mtime)
    print(f"Archive locale trouvée : {latest_archive}")

    if not SUBMITTED_MARKER.exists():
        print("Aucune preuve d'envoi serveur trouvée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : archive non envoyée au serveur")
        sys.exit(1)

    submitted_data = json.loads(SUBMITTED_MARKER.read_text(encoding="utf-8"))

    if submitted_data.get("archive") != latest_archive.name:
        print("L'archive locale la plus récente ne correspond pas à l'archive envoyée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : archive locale différente de l'archive envoyée")
        sys.exit(1)

    print("Archive envoyée au serveur confirmée.")

    if workspace.exists():
        shutil.rmtree(workspace)
        print(f"Dossier supprimé : {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)

    if execution_mode == "real":
        set_exam_permissions(workspace)

    print(f"Dossier recréé proprement : {workspace}")
    print("Remise à zéro terminée avec succès.")

    write_log("RESET", f"Mode : {execution_mode}")
    write_log("RESET", "Remise à zéro terminée avec succès après confirmation de l'envoi serveur")


if __name__ == "__main__":
    main()