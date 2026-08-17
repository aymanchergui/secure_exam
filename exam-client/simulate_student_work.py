from pathlib import Path
import json
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()

if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("STUDENT_WORK_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

workspace = Path("runtime") / "home" / "exam" / config["student_id"] / "workspace"
workspace.mkdir(parents=True, exist_ok=True)

student_file = workspace / "main.py"

student_file.write_text(
    'print("Hello exam")\n',
    encoding="utf-8"
)

print(f"Fichier étudiant créé : {student_file}")
write_log("STUDENT_WORK", f"Fichier étudiant créé : {student_file}")