from pathlib import Path
import json
import os
import sys

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import (
    GENERATED_DIR,
    get_config_path,
    get_execution_mode,
    get_runtime_network_policy_path,
    get_workspace_path
)
from core.logger import write_log

CONFIG_FILE = get_config_path()

ALLOWED_PACKAGES = {
    "python3",
    "gcc",
    "gdb",
    "make",
    "gnumake",
    "vim",
    "nano",
    "git",
    "curl",
    "wget",
    "zip",
    "unzip",
    "node",
    "nodejs",
    "nodejs_22"
}

def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0

def check_exam_user_exists() -> tuple[int, int]:
    """
    Vérifie que l'utilisateur Linux/NixOS exam existe.
    Cette fonction est utilisée uniquement en mode réel.
    """
    if os.name == "nt":
        print("Mode réel indisponible sous Windows.")
        print("Le mode réel nécessite une machine Linux/NixOS avec l'utilisateur exam.")
        write_log("APPLY_ERROR", "Mode réel demandé sous Windows")
        sys.exit(1)

    try:
        import pwd
        import grp

        exam_uid = pwd.getpwnam("exam").pw_uid
        exam_gid = grp.getgrnam("exam").gr_gid
        return exam_uid, exam_gid
    except KeyError:
        print("Utilisateur ou groupe exam introuvable.")
        print("En mode réel, applique d'abord la configuration NixOS générée avec :")
        print(f"sudo cp {GENERATED_DIR / 'exam-configuration.nix'} /etc/nixos/exam-configuration.nix")
        print("sudo nixos-rebuild test")
        write_log("APPLY_ERROR", "Utilisateur ou groupe exam introuvable en mode réel")
        sys.exit(1)

def load_config() -> dict:
    """
    Charge la configuration récupérée depuis le backend.
    """
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("APPLY_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Configuration JSON invalide : {CONFIG_FILE}")
        print(error)
        write_log("APPLY_ERROR", f"Configuration JSON invalide : {error}")
        sys.exit(1)

def validate_packages(config: dict) -> None:
    """
    Vérifie que les paquets demandés appartiennent au catalogue autorisé côté client.
    """
    requested_packages = set(config.get("nix_packages", config.get("packages", [])))
    invalid_packages = requested_packages - ALLOWED_PACKAGES

    if invalid_packages:
        print("Paquets non autorisés détectés :")

        for package in sorted(invalid_packages):
            print(f" - {package}")

        write_log("APPLY_ERROR", f"Paquets non autorisés : {sorted(invalid_packages)}")
        sys.exit(1)

def write_network_policy_simulation(config: dict) -> Path:
    """
    En mode simulation, écrit une politique réseau lisible dans var/runtime/.
    Aucune règle système réelle n'est appliquée ici.
    """
    network_policy_file = get_runtime_network_policy_path()
    network_policy_file.parent.mkdir(parents=True, exist_ok=True)

    network_policy_file.write_text(
        "\n".join([
            f"exam_id={config['exam_id']}",
            f"student_id={config['student_id']}",
            f"machine_id={config['machine_id']}",
            f"internet={'allowed' if config['internet'] else 'blocked'}",
            f"educ_access={'allowed' if config['educ_access'] else 'blocked'}",
            "allowed_domains=" + ",".join(config.get("allowed_domains", []))
        ]),
        encoding="utf-8"
    )

    return network_policy_file

def prepare_workspace(config: dict, execution_mode: str) -> Path:
    """
    Prépare le workspace étudiant.
    - simulation : var/runtime/home/exam/<student>/workspace
    - réel : chemin défini par la configuration, sous /home/exam/
    """
    workspace = get_workspace_path(config)

    if execution_mode == "real":
        if not is_root():
            print("Mode réel détecté.")
            print("La préparation du workspace réel nécessite les droits root.")
            print("Relance avec :")
            print('sudo -E env "PYTHONPATH=$PYTHONPATH" "$(which python3)" flows/start_exam.py')
            write_log("APPLY_ERROR", "Mode réel lancé sans droits root")
            sys.exit(1)

        exam_uid, exam_gid = check_exam_user_exists()
        workspace.mkdir(parents=True, exist_ok=True)
        os.chown(workspace, exam_uid, exam_gid)
        os.chmod(workspace, 0o750)
        return workspace

    workspace.mkdir(parents=True, exist_ok=True)
    return workspace

def write_workspace_files(config: dict, workspace: Path, execution_mode: str) -> None:
    """
    Dépose dans le workspace des fichiers de suivi utiles pour l'étudiant,
    le surveillant ou la phase de diagnostic.
    """
    metadata_file = workspace / "exam_metadata.json"
    network_policy_file = workspace / "exam_network_policy.json"

    network_policy = {
        "internet": "allowed" if config["internet"] else "blocked",
        "educ_access": "allowed" if config["educ_access"] else "blocked",
        "allowed_domains": config.get("allowed_domains", []),
        "note": (
            "En mode réel, le filtrage réseau strict doit être appliqué par "
            "l'infrastructure NixOS, un proxy, un DNS contrôlé ou une passerelle réseau."
        )
    }

    metadata_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    network_policy_file.write_text(
        json.dumps(network_policy, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    if execution_mode == "real":
        exam_uid, exam_gid = check_exam_user_exists()

        for file in [metadata_file, network_policy_file]:
            os.chown(file, exam_uid, exam_gid)
            os.chmod(file, 0o640)

    print(f"Fichier de suivi créé : {metadata_file}")
    print(f"Politique réseau créée : {network_policy_file}")

def main() -> None:
    config = load_config()
    execution_mode = get_execution_mode()

    print("Application de la configuration d'examen")
    print("---------------------------------------")
    print(f"Mode d'exécution : {execution_mode}")

    validate_packages(config)

    print("Paquets autorisés :")

    for package in config.get("packages", []):
        print(f" - {package}")

    workspace = prepare_workspace(config, execution_mode)

    print(f"Dossier de travail créé/préparé : {workspace}")

    sudo_status = "activés" if config["sudo"] else "désactivés"
    print(f"Droits sudo : {sudo_status} pour l'examen")

    print("Politique réseau :")
    print(f" - Internet autorisé : {config['internet']}")
    print(f" - Accès Educ autorisé : {config['educ_access']}")
    print(f" - Domaines autorisés : {config.get('allowed_domains', [])}")

    if execution_mode == "simulation":
        network_policy_file = write_network_policy_simulation(config)
        print(f"Politique réseau simulée créée : {network_policy_file}")
    else:
        print(f"Mode réel : la politique réseau système est générée dans {GENERATED_DIR / 'network-policy.json'}")
        print("Elle peut ensuite être appliquée avec system/apply_network_rules.py --apply.")

    write_workspace_files(config, workspace, execution_mode)

    print("Configuration appliquée avec succès.")

    write_log(
        "APPLY",
        f"Configuration appliquée en mode {execution_mode} pour "
        f"{config['exam_id']} - {config['student_id']} - {config['machine_id']}"
    )

if __name__ == "__main__":
    main()
