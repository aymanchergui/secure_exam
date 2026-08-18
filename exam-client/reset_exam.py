from pathlib import Path
import json
import os
import shutil
import sys

from client_settings import get_config_path, get_execution_mode, get_workspace_path
from logger import write_log


CONFIG_FILE = get_config_path()
ARCHIVE_DIR = Path("archives")
SUBMITTED_MARKER = Path("submitted") / "last_submission.json"


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("RESET_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Configuration JSON invalide : {CONFIG_FILE}")
        print(error)
        write_log("RESET_ERROR", f"Configuration JSON invalide : {error}")
        sys.exit(1)


def set_exam_permissions(path: Path) -> None:
    """
    En mode réel, le workspace doit appartenir à exam:exam.
    Cette fonction est appelée uniquement sur Linux/NixOS.
    """
    if os.name == "nt":
        print("Mode réel indisponible sous Windows.")
        print("Le mode réel nécessite une machine Linux/NixOS avec l'utilisateur exam.")
        write_log("RESET_ERROR", "Mode réel demandé sous Windows")
        sys.exit(1)

    import pwd
    import grp

    try:
        exam_uid = pwd.getpwnam("exam").pw_uid
        exam_gid = grp.getgrnam("exam").gr_gid
    except KeyError:
        print("Utilisateur ou groupe exam introuvable.")
        print("Impossible d'appliquer les permissions du workspace réel.")
        write_log("RESET_ERROR", "Utilisateur ou groupe exam introuvable")
        sys.exit(1)

    os.chown(path, exam_uid, exam_gid)
    os.chmod(path, 0o750)


def find_latest_archive(config: dict) -> Path:
    archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
    archives = list(ARCHIVE_DIR.glob(archive_pattern))

    if not archives:
        print("Aucune archive locale trouvée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : aucune archive locale trouvée")
        sys.exit(1)

    return max(archives, key=lambda path: path.stat().st_mtime)


def load_submitted_marker() -> dict:
    if not SUBMITTED_MARKER.exists():
        print("Aucune preuve d'envoi serveur trouvée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : archive non envoyée au serveur")
        sys.exit(1)

    try:
        return json.loads(SUBMITTED_MARKER.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Preuve d'envoi invalide : {SUBMITTED_MARKER}")
        print(error)
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", f"Preuve d'envoi JSON invalide : {error}")
        sys.exit(1)


def validate_submission_marker(config: dict, latest_archive: Path, submitted_data: dict) -> None:
    expected_values = {
        "exam_id": config["exam_id"],
        "student_id": config["student_id"],
        "machine_id": config["machine_id"],
        "archive": latest_archive.name
    }

    for key, expected_value in expected_values.items():
        if submitted_data.get(key) != expected_value:
            print("La preuve d'envoi ne correspond pas à l'archive locale la plus récente.")
            print(f"Champ concerné : {key}")
            print(f"Valeur attendue : {expected_value}")
            print(f"Valeur trouvée   : {submitted_data.get(key)}")
            print("Reset annulé pour éviter la perte des données étudiant.")
            write_log("RESET_ERROR", "Reset annulé : preuve d'envoi incohérente")
            sys.exit(1)


def reset_workspace(workspace: Path, execution_mode: str) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
        print(f"Dossier supprimé : {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)

    if execution_mode == "real":
        set_exam_permissions(workspace)

    print(f"Dossier recréé proprement : {workspace}")


def main() -> None:
    config = load_config()
    execution_mode = get_execution_mode()
    workspace = get_workspace_path(config)

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print(f"Le workspace réel appartient à l'utilisateur exam : {workspace}")
        print("Relance la fin d'examen avec :")
        print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" finish_exam.py')
        write_log("RESET_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    print("Vérification avant remise à zéro")
    print("--------------------------------")
    print(f"Mode      : {execution_mode}")
    print(f"Workspace : {workspace}")

    latest_archive = find_latest_archive(config)
    print(f"Archive locale trouvée : {latest_archive}")

    submitted_data = load_submitted_marker()
    validate_submission_marker(config, latest_archive, submitted_data)

    print("Archive envoyée au serveur confirmée.")

    reset_workspace(workspace, execution_mode)

    print("Remise à zéro terminée avec succès.")

    write_log("RESET", f"Mode : {execution_mode}")
    write_log("RESET", "Remise à zéro terminée avec succès après confirmation de l'envoi serveur")


if __name__ == "__main__":
    main()