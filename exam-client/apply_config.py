from pathlib import Path
import json
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()

ALLOWED_PACKAGES = {
    "python3",
    "gcc",
    "gdb",
    "make",
    "vim",
    "nano"
}

if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("APPLY_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

print("Application de la configuration d'examen")
print("---------------------------------------")

# 1. Vérification des paquets
requested_packages = set(config["packages"])
invalid_packages = requested_packages - ALLOWED_PACKAGES

if invalid_packages:
    print("Paquets non autorisés détectés :")
    for package in invalid_packages:
        print(f" - {package}")

    write_log("APPLY_ERROR", f"Paquets non autorisés : {list(invalid_packages)}")
    sys.exit(1)

print("Paquets autorisés :")
for package in config["packages"]:
    print(f" - {package}")

# 2. Création du dossier étudiant
local_workspace = Path("runtime") / "home" / "exam" / config["student_id"] / "workspace"
local_workspace.mkdir(parents=True, exist_ok=True)

print(f"Dossier de travail créé : {local_workspace}")

# 3. Simulation des droits sudo
if config["sudo"]:
    sudo_status = "activés"
else:
    sudo_status = "désactivés"

print(f"Droits sudo : {sudo_status} pour l'examen")

# 4. Simulation de la politique réseau
print("Politique réseau :")
print(f" - Internet autorisé : {config['internet']}")
print(f" - Accès Educ autorisé : {config['educ_access']}")
print(f" - Domaines autorisés : {config['allowed_domains']}")

network_dir = Path("runtime") / "system"
network_dir.mkdir(parents=True, exist_ok=True)

network_policy_file = network_dir / "network_policy.txt"

network_policy_file.write_text(
    "\n".join([
        f"exam_id={config['exam_id']}",
        f"student_id={config['student_id']}",
        f"machine_id={config['machine_id']}",
        f"internet={'allowed' if config['internet'] else 'blocked'}",
        f"educ_access={'allowed' if config['educ_access'] else 'blocked'}",
        "allowed_domains=" + ",".join(config["allowed_domains"])
    ]),
    encoding="utf-8"
)

print(f"Politique réseau simulée créée : {network_policy_file}")

# 5. Création d'un fichier de suivi dans le workspace
metadata_file = local_workspace / "exam_metadata.json"

metadata_file.write_text(
    json.dumps(config, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("Configuration appliquée avec succès.")
print(f"Fichier de suivi créé : {metadata_file}")

write_log(
    "APPLY",
    f"Configuration appliquée pour {config['exam_id']} - {config['student_id']} - {config['machine_id']}"
)

write_log(
    "NETWORK",
    f"Politique réseau simulée créée : {network_policy_file}"
)