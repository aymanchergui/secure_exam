from pathlib import Path
import json
import sys

CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import get_config_path, get_workspace_path
from core.logger import write_log

CONFIG_FILE = get_config_path()

def load_config() -> dict:
    """
    Charge la configuration locale récupérée depuis le backend.
    """
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("STUDENT_WORK_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Configuration JSON invalide : {CONFIG_FILE}")
        print(error)
        write_log("STUDENT_WORK_ERROR", f"Configuration JSON invalide : {error}")
        sys.exit(1)

def main() -> None:
    """
    Simule un rendu étudiant dans le workspace.
    Ce script sert uniquement aux tests et à la démonstration.
    """
    config = load_config()
    workspace = get_workspace_path(config)
    workspace.mkdir(parents=True, exist_ok=True)

    main_file = workspace / "main.py"
    readme_file = workspace / "README.txt"

    main_file.write_text(
        'print("Hello SecureExam")\n',
        encoding="utf-8"
    )

    readme_file.write_text(
        "Rendu de test étudiant pour la démonstration SecureExam.\n",
        encoding="utf-8"
    )

    print("Travail étudiant simulé avec succès")
    print(f"Workspace : {workspace}")
    print(f"Fichier   : {main_file}")
    print(f"Fichier   : {readme_file}")

    write_log("STUDENT_WORK", f"Travail étudiant simulé dans : {workspace}")

if __name__ == "__main__":
    main()
