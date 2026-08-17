from pathlib import Path
from datetime import datetime
import json
import zipfile
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()

if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("BACKUP_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

workspace = Path("runtime") / "home" / "exam" / config["student_id"] / "workspace"

archive_dir = Path("archives")
archive_dir.mkdir(exist_ok=True)

if not workspace.exists():
    print(f"Dossier de travail introuvable : {workspace}")
    write_log("BACKUP_ERROR", f"Dossier de travail introuvable : {workspace}")
    sys.exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

archive_name = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_{timestamp}.zip"
archive_path = archive_dir / archive_name

with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
    for file in workspace.rglob("*"):
        if file.is_file():
            zipf.write(file, file.relative_to(workspace))

print("Sauvegarde créée avec succès")
print(f"Workspace : {workspace}")
print(f"Archive   : {archive_path}")

write_log("BACKUP", f"Archive créée : {archive_path}")