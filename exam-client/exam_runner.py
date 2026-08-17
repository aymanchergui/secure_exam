import subprocess
import sys

from logger import write_log
from status_reporter import report_status


STEPS = [
    ("FETCH", "fetch_config.py"),
    ("APPLY", "apply_config.py"),
    ("GENERATE_NIX", "generate_nixos_config.py"),
    ("STUDENT_WORK", "simulate_student_work.py"),
    ("BACKUP", "backup_workspace.py"),
    ("SUBMIT", "submit_archive.py"),
    ("RESET", "reset_exam.py"),
]


def run_step(name: str, script: str):
    print(f"\n===== {name} =====")

    write_log("FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, script],
        text=True
    )

    if result.returncode != 0:
        write_log("FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")

        print(f"Erreur pendant l'étape : {name}")
        sys.exit(result.returncode)

    write_log("FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")


def main():
    print("Démarrage de la chaîne machine d'examen")

    for name, script in STEPS:
        run_step(name, script)

    print("\nChaîne complète exécutée avec succès.")
    write_log("FLOW", "Chaîne complète exécutée avec succès")
    report_status("FLOW", "SUCCESS", "Chaîne complète exécutée avec succès")


if __name__ == "__main__":
    main()