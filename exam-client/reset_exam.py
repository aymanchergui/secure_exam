from pathlib import Path
import json
import shutil
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()
ARCHIVE_DIR = Path("archives")
SUBMITTED_MARKER = Path("submitted") / "last_submission.json"

if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("RESET_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

workspace = Path("runtime") / "home" / "exam" / config["student_id"] / "workspace"

archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
archives = list(ARCHIVE_DIR.glob(archive_pattern))

print("Vérification avant remise à zéro")
print("--------------------------------")

# 1. Vérifier qu'une archive locale existe
if not archives:
    print("Aucune archive locale trouvée.")
    print("Reset annulé pour éviter la perte des données étudiant.")
    write_log("RESET_ERROR", "Reset annulé : aucune archive locale trouvée")
    sys.exit(1)

latest_archive = max(archives, key=lambda p: p.stat().st_mtime)
print(f"Archive locale trouvée : {latest_archive}")

# 2. Vérifier que l'archive a été envoyée au serveur
if not SUBMITTED_MARKER.exists():
    print("Aucune preuve d'envoi serveur trouvée.")
    print("Reset annulé pour éviter la perte des données étudiant.")
    write_log("RESET_ERROR", "Reset annulé : archive non envoyée au serveur")
    sys.exit(1)

submitted_data = json.loads(SUBMITTED_MARKER.read_text(encoding="utf-8"))

if submitted_data.get("archive") != latest_archive.name:
    print("L'archive locale la plus récente ne correspond pas à l'archive envoyée.")
    print("Reset annulé pour éviter la perte des données étudiant.")
    write_log("RESET_ERROR", "Reset annulé : archive locale différente de l'archive envoyée")
    sys.exit(1)

print("Archive envoyée au serveur confirmée.")

# 3. Supprimer le workspace étudiant
if workspace.exists():
    shutil.rmtree(workspace)
    print(f"Dossier supprimé : {workspace}")

# 4. Recréer un workspace propre
workspace.mkdir(parents=True, exist_ok=True)
print(f"Dossier recréé proprement : {workspace}")

print("Remise à zéro terminée avec succès.")
write_log("RESET", "Remise à zéro terminée avec succès après confirmation de l'envoi serveur")