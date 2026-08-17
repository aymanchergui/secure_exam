import subprocess
import sys

from logger import write_log
from status_reporter import report_status


STEPS = [
    ("FETCH", "fetch_config.py"),
    ("APPLY", "apply_config.py"),
    ("GENERATE_NIX", "generate_nixos_config.py"),
]


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
    print("Démarrage de l'environnement d'examen")

    for name, script in STEPS:
        run_step(name, script)

    print("\nEnvironnement d'examen prêt.")
    write_log("START_FLOW", "Environnement d'examen prêt")
    report_status("EXAM_READY", "SUCCESS", "Environnement d'examen prêt")


if __name__ == "__main__":
    main()