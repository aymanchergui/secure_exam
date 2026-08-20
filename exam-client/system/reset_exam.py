from pathlib import Path
from datetime import datetime
import json
import os
import shutil
import subprocess
import sys

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import (
    ARCHIVE_DIR,
    SUBMITTED_DIR,
    get_config_path,
    get_execution_mode,
    get_workspace_path
)
from core.logger import write_log

CONFIG_FILE = get_config_path()
SUBMITTED_MARKER = SUBMITTED_DIR / "last_submission.json"
RESET_REPORT = SUBMITTED_DIR / "last_reset_report.json"

def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0

def load_config() -> dict:
    """
    Charge la configuration d'examen locale.
    """
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
    """
    if os.name == "nt":
        print("Mode réel indisponible sous Windows.")
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
    """
    Retrouve la dernière archive locale correspondant à cette configuration.
    Le reset est interdit si aucune archive locale n'existe.
    """
    archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
    archives = list(ARCHIVE_DIR.glob(archive_pattern))

    if not archives:
        print("Aucune archive locale trouvée.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("RESET_ERROR", "Reset annulé : aucune archive locale trouvée")
        sys.exit(1)

    return max(archives, key=lambda path: path.stat().st_mtime)

def load_submitted_marker() -> dict:
    """
    Charge la preuve locale d'envoi serveur.
    Le reset est interdit si cette preuve n'existe pas.
    """
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
    """
    Vérifie que la preuve d'envoi correspond exactement à la dernière archive locale.
    Cela évite de supprimer le workspace si le mauvais fichier a été envoyé.
    """
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

def reset_network_rules(execution_mode: str) -> dict:
    """
    En mode réel, retire les règles nftables SecureExam.
    En simulation, aucune règle système n'est appliquée, donc rien à retirer.
    """
    report = {
        "attempted": False,
        "status": "SKIPPED",
        "message": "Mode simulation : aucune règle réseau système à retirer."
    }

    if execution_mode != "real":
        return report

    script = CLIENT_ROOT / "system" / "apply_network_rules.py"

    if not script.exists():
        report.update({
            "attempted": True,
            "status": "ERROR",
            "message": f"{script} introuvable."
        })
        write_log("RESET_NETWORK_ERROR", report["message"])
        return report

    print("Remise à zéro des règles réseau nftables...")

    result = subprocess.run(
        [sys.executable, str(script), "--reset"],
        text=True,
        cwd=CLIENT_ROOT
    )

    report["attempted"] = True

    if result.returncode == 0:
        report["status"] = "SUCCESS"
        report["message"] = "Règles réseau supprimées ou déjà absentes."
        write_log("RESET_NETWORK", report["message"])
    else:
        report["status"] = "ERROR"
        report["message"] = "Échec du reset réseau. Intervention administrateur nécessaire."
        write_log("RESET_NETWORK_ERROR", report["message"])
        print(report["message"])
        print("Commande de secours : sudo nft delete table inet secure_exam")

    return report

def reset_workspace(workspace: Path, execution_mode: str) -> None:
    """
    Supprime le workspace étudiant puis le recrée proprement.
    """
    if workspace.exists():
        shutil.rmtree(workspace)
        print(f"Dossier supprimé : {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)

    if execution_mode == "real":
        set_exam_permissions(workspace)

    print(f"Dossier recréé proprement : {workspace}")

def write_reset_report(config: dict, workspace: Path, archive: Path, network_report: dict) -> None:
    """
    Écrit une preuve locale de reset.
    """
    RESET_REPORT.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "exam_id": config["exam_id"],
        "student_id": config["student_id"],
        "machine_id": config["machine_id"],
        "workspace": str(workspace),
        "archive_confirmed": archive.name,
        "network_reset": network_report,
        "reset_at": datetime.now().isoformat(timespec="seconds"),
        "status": "RESET_DONE"
    }

    RESET_REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"Rapport de reset créé : {RESET_REPORT}")
    write_log("RESET", f"Rapport de reset créé : {RESET_REPORT}")

def main() -> None:
    config = load_config()
    execution_mode = get_execution_mode()
    workspace = get_workspace_path(config)

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print(f"Le workspace réel appartient à l'utilisateur exam : {workspace}")
        print("Relance la fin d'examen avec :")
        print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" flows/finish_exam.py')
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

    network_report = reset_network_rules(execution_mode)
    reset_workspace(workspace, execution_mode)
    write_reset_report(config, workspace, latest_archive, network_report)

    print("Remise à zéro terminée avec succès.")

    write_log("RESET", f"Mode : {execution_mode}")
    write_log("RESET", "Remise à zéro terminée avec succès après confirmation de l'envoi serveur")

if __name__ == "__main__":
    main()
