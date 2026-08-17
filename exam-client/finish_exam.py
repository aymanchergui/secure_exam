import subprocess
import sys

from logger import write_log
from status_reporter import report_status


STEPS = [
    ("BACKUP", "backup_workspace.py"),
    ("SUBMIT", "submit_archive.py"),
    ("RESET", "reset_exam.py"),
]


def run_step(name: str, script: str):
    print(f"\n===== {name} =====")

    write_log("FINISH_FLOW", f"Début étape : {name}")
    report_status(name, "RUNNING", f"Début étape : {name}")

    result = subprocess.run(
        [sys.executable, script],
        text=True
    )

    if result.returncode != 0:
        write_log("FINISH_FLOW_ERROR", f"Échec étape : {name}")
        report_status(name, "ERROR", f"Échec étape : {name}")
        print(f"Erreur pendant l'étape : {name}")
        sys.exit(result.returncode)

    write_log("FINISH_FLOW", f"Fin étape : {name}")
    report_status(name, "SUCCESS", f"Fin étape : {name}")


def main():
    print("Fin de l'examen : sauvegarde, envoi et remise à zéro")

    for name, script in STEPS:
        run_step(name, script)

    print("\nFin d'examen traitée avec succès.")
    write_log("FINISH_FLOW", "Fin d'examen traitée avec succès")
    report_status("EXAM_FINISHED", "SUCCESS", "Fin d'examen traitée avec succès")


if __name__ == "__main__":
    main()