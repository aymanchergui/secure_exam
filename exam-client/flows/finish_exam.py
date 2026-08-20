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

# Fin d'examen sécurisée :
# 1. sauvegarde du workspace
# 2. envoi de l'archive au backend
# 3. reset uniquement si l'envoi est confirmé
STEPS = [
    ("BACKUP", "workspace/backup_workspace.py"),
    ("SUBMIT", "api/submit_archive.py"),
    ("RESET", "system/reset_exam.py"),
]

def run_step(name: str, script: str) -> None:
    print(f"\n===== {name} =====")

    write_log("FINISH_FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, str(CLIENT_ROOT / script)],
        text=True,
        cwd=CLIENT_ROOT
    )

    if result.returncode != 0:
        write_log("FINISH_FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")
        print(f"Erreur pendant l'étape : {name}")
        print("Fin d'examen arrêtée pour éviter la perte des données étudiant.")
        sys.exit(result.returncode)

    write_log("FINISH_FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")

def main() -> None:
    print("Fin de l'examen : sauvegarde, envoi et remise à zéro")

    for name, script in STEPS:
        run_step(name, script)

    print("\nFin d'examen traitée avec succès.")
    write_log("FINISH_FLOW", "Fin d'examen traitée avec succès")
    report_status("EXAM_FINISHED", "SUCCESS", "Fin d'examen traitée avec succès")

if __name__ == "__main__":
    main()
