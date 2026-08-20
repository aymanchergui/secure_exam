from pathlib import Path
import os
import subprocess
import sys

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import get_execution_mode
from core.logger import write_log
from api.status_reporter import report_status

# Démarrage réel d'un poste d'examen.
# Cette commande prépare uniquement l'environnement avant le début de l'épreuve.
STEPS = [
    ("FETCH", "api/fetch_config.py"),
    ("GENERATE_NIX", "generation/generate_nixos_config.py"),
    ("GENERATE_NETWORK_RULES", "generation/generate_network_rules.py"),
    ("APPLY", "system/apply_config.py"),
]

def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0

def run_step(name: str, script: str) -> None:
    print(f"\n===== {name} =====")

    write_log("START_FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, str(CLIENT_ROOT / script)],
        text=True,
        cwd=CLIENT_ROOT
    )

    if result.returncode != 0:
        write_log("START_FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")
        print(f"Erreur pendant l'étape : {name}")
        sys.exit(result.returncode)

    write_log("START_FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")

def main() -> None:
    execution_mode = get_execution_mode()

    print("Démarrage de l'environnement d'examen")
    print(f"Mode d'exécution : {execution_mode}")

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print("Le démarrage réel doit être lancé avec les droits root pour préparer /home/exam.")
        print("Commande conseillée :")
        print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" flows/start_exam.py')
        write_log("START_FLOW_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    for name, script in STEPS:
        run_step(name, script)

    print("\nEnvironnement d'examen prêt.")
    write_log("START_FLOW", f"Environnement d'examen prêt en mode {execution_mode}")
    report_status("EXAM_READY", "SUCCESS", f"Environnement d'examen prêt en mode {execution_mode}")

if __name__ == "__main__":
    main()
