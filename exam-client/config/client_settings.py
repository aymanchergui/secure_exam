from pathlib import Path
import json
import sys

CLIENT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = CLIENT_ROOT / "config"
VAR_DIR = CLIENT_ROOT / "var"

DOWNLOAD_DIR = VAR_DIR / "downloaded"
GENERATED_DIR = VAR_DIR / "generated"
ARCHIVE_DIR = VAR_DIR / "archives"
LOG_DIR = VAR_DIR / "logs"
RUNTIME_DIR = VAR_DIR / "runtime"
SUBMITTED_DIR = VAR_DIR / "submitted"

SETTINGS_FILE = CONFIG_DIR / "client_settings.json"
ALLOWED_EXECUTION_MODES = {"simulation", "real"}

for directory in [
    DOWNLOAD_DIR,
    GENERATED_DIR,
    ARCHIVE_DIR,
    LOG_DIR,
    RUNTIME_DIR,
    SUBMITTED_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        print(f"Fichier de paramètres introuvable : {SETTINGS_FILE}")
        print("Le fichier attendu est : config/client_settings.json")
        sys.exit(1)

    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Fichier de paramètres invalide : {SETTINGS_FILE}")
        print(error)
        sys.exit(1)

settings = load_settings()

SERVER_URL = settings["server_url"].rstrip("/")
EXAM_ID = settings["exam_id"]
STUDENT_ID = settings["student_id"]
MACHINE_ID = settings["machine_id"]
EXECUTION_MODE = str(settings.get("execution_mode", "simulation")).strip().lower()

if EXECUTION_MODE not in ALLOWED_EXECUTION_MODES:
    print(f"Mode d'exécution invalide : {EXECUTION_MODE}")
    print("Valeurs autorisées : simulation ou real")
    sys.exit(1)

def get_execution_mode() -> str:
    return EXECUTION_MODE

def get_config_filename() -> str:
    return f"{EXAM_ID}_{STUDENT_ID}_{MACHINE_ID}.json"

def get_config_path() -> Path:
    return DOWNLOAD_DIR / get_config_filename()

def get_workspace_path(config: dict) -> Path:
    if EXECUTION_MODE == "real":
        workspace = Path(config["workspace"])

        if not workspace.as_posix().startswith("/home/exam/"):
            print(f"Workspace réel refusé pour sécurité : {workspace}")
            print("Le workspace réel doit être sous /home/exam/")
            sys.exit(1)

        return workspace

    return RUNTIME_DIR / "home" / "exam" / config["student_id"] / "workspace"

def get_runtime_network_policy_path() -> Path:
    return RUNTIME_DIR / "system" / "network_policy.txt"
