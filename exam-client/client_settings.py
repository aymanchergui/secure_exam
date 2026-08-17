from pathlib import Path
import json
import sys

SETTINGS_FILE = Path("client_settings.json")


def load_settings():
    if not SETTINGS_FILE.exists():
        print(f"Fichier de paramètres introuvable : {SETTINGS_FILE}")
        sys.exit(1)

    return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))


settings = load_settings()

SERVER_URL = settings["server_url"].rstrip("/")
EXAM_ID = settings["exam_id"]
STUDENT_ID = settings["student_id"]
MACHINE_ID = settings["machine_id"]


def get_config_filename():
    return f"{EXAM_ID}_{STUDENT_ID}_{MACHINE_ID}.json"


def get_config_path():
    return Path("downloaded") / get_config_filename()