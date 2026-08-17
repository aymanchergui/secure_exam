from pathlib import Path
import json
import sys
import requests

from client_settings import SERVER_URL, get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()
ARCHIVE_DIR = Path("archives")
SUBMITTED_DIR = Path("submitted")
SUBMITTED_DIR.mkdir(exist_ok=True)

if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("SUBMIT_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
archives = list(ARCHIVE_DIR.glob(archive_pattern))

if not archives:
    print("Aucune archive à envoyer.")
    write_log("SUBMIT_ERROR", "Aucune archive à envoyer")
    sys.exit(1)

latest_archive = max(archives, key=lambda p: p.stat().st_mtime)

url = f"{SERVER_URL}/submissions"

with open(latest_archive, "rb") as file:
    files = {
        "archive": (latest_archive.name, file, "application/zip")
    }

    data = {
        "exam_id": config["exam_id"],
        "student_id": config["student_id"],
        "machine_id": config["machine_id"]
    }

    response = requests.post(url, data=data, files=files)

if response.status_code != 200:
    print("Erreur lors de l'envoi de l'archive")
    print(response.text)
    write_log("SUBMIT_ERROR", f"Erreur serveur : {response.text}")
    sys.exit(1)

print("Archive envoyée avec succès")
print(response.json())

write_log("SUBMIT", f"Archive envoyée au serveur : {latest_archive}")

marker_file = SUBMITTED_DIR / "last_submission.json"

marker_file.write_text(
    json.dumps(
        {
            "exam_id": config["exam_id"],
            "student_id": config["student_id"],
            "machine_id": config["machine_id"],
            "archive": latest_archive.name,
            "server_response": response.json()
        },
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

print(f"Preuve d'envoi créée : {marker_file}")