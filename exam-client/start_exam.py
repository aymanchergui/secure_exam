import os
import subprocess
import sys

from client_settings import get_execution_mode
from logger import write_log
from status_reporter import report_status


STEPS = [
    ("FETCH", "fetch_config.py"),
    ("GENERATE_NIX", "generate_nixos_config.py"),
    ("APPLY", "apply_config.py"),
]


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def run_step(name: str, script: str):
    print(f"\n===== {name} =====")

    write_log("START_FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, script],
        text=True
    )

    if result.returncode != 0:
        write_log("START_FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")
        print(f"Erreur pendant l'étape : {name}")
        sys.exit(result.returncode)

    write_log("START_FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")


def main():
    execution_mode = get_execution_mode()

    print("Démarrage de l'environnement d'examen")
    print(f"Mode d'exécution : {execution_mode}")

    if execution_mode == "real" and not is_root():
        print("Mode réel détecté.")
        print("Le démarrage réel doit être lancé avec les droits root pour préparer /home/exam.")
        print("Commande conseillée :")
        print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" start_exam.py')
        write_log("START_FLOW_ERROR", "Mode réel lancé sans droits root")
        sys.exit(1)

    for name, script in STEPS:
        run_step(name, script)

    print("\nEnvironnement d'examen prêt.")
    write_log("START_FLOW", f"Environnement d'examen prêt en mode {execution_mode}")
    report_status("EXAM_READY", "SUCCESS", f"Environnement d'examen prêt en mode {execution_mode}")


if __name__ == "__main__":
    main()