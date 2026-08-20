from pathlib import Path
import subprocess
import sys

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from core.logger import write_log
from api.status_reporter import report_status

# Scénario complet utilisé pour une démonstration de bout en bout.
# Il simule le cycle complet machine :
# récupération config -> génération -> application -> travail étudiant -> sauvegarde -> envoi -> reset.
STEPS = [
    ("FETCH", "api/fetch_config.py"),
    ("GENERATE_NIX", "generation/generate_nixos_config.py"),
    ("GENERATE_NETWORK_RULES", "generation/generate_network_rules.py"),
    ("APPLY", "system/apply_config.py"),
    ("STUDENT_WORK", "workspace/simulate_student_work.py"),
    ("BACKUP", "workspace/backup_workspace.py"),
    ("SUBMIT", "api/submit_archive.py"),
    ("RESET", "system/reset_exam.py"),
]

def run_step(name: str, script: str) -> None:
    print(f"\n===== {name} =====")

    write_log("FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, str(CLIENT_ROOT / script)],
        text=True,
        cwd=CLIENT_ROOT
    )

    if result.returncode != 0:
        write_log("FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")
        print(f"Erreur pendant l'étape : {name}")
        sys.exit(result.returncode)

    write_log("FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")

def main() -> None:
    print("Démarrage de la chaîne complète machine SecureExam")

    for name, script in STEPS:
        run_step(name, script)

    print("\nChaîne complète exécutée avec succès.")
    write_log("FLOW", "Chaîne complète exécutée avec succès")
    report_status("FLOW", "SUCCESS", "Chaîne complète exécutée avec succès")

if __name__ == "__main__":
    main()
