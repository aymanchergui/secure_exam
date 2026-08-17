from pathlib import Path
from datetime import datetime
import json
import sys

from client_settings import get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()

ALLOWED_PACKAGE_MAP = {
    "python3": "python3",
    "gcc": "gcc",
    "gdb": "gdb",
    "make": "gnumake",
    "vim": "vim",
    "nano": "nano"
}


def nix_bool(value: bool) -> str:
    return "true" if value else "false"


def nix_list(values: list[str]) -> str:
    if not values:
        return "[ ]"

    lines = "\n".join([f'    "{value}"' for value in values])
    return f"[\n{lines}\n  ]"


def build_workspace_tmpfiles_rules(workspace: str) -> list[str]:
    path = Path(workspace)
    parts = path.parts

    rules = []

    current = Path(parts[0])

    for part in parts[1:]:
        current = current / part

        if str(current).startswith("/home/exam"):
            rules.append(f'd {current.as_posix()} 0750 exam exam -')

    return rules


if not CONFIG_FILE.exists():
    print(f"Configuration introuvable : {CONFIG_FILE}")
    write_log("NIX_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)


config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

requested_packages = config.get("packages", [])
invalid_packages = [
    package for package in requested_packages
    if package not in ALLOWED_PACKAGE_MAP
]

if invalid_packages:
    print("Paquets non autorisés détectés :")
    for package in invalid_packages:
        print(f" - {package}")

    write_log("NIX_ERROR", f"Paquets non autorisés : {invalid_packages}")
    sys.exit(1)


generated_dir = Path("generated")
generated_dir.mkdir(exist_ok=True)

nix_file = generated_dir / "exam-configuration.nix"
metadata_file = generated_dir / "exam-metadata.json"
network_policy_file = generated_dir / "network-policy.json"

generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

nix_packages = [
    ALLOWED_PACKAGE_MAP[package]
    for package in requested_packages
]

packages_block = "\n    ".join(nix_packages)

sudo_extra_groups = '[ "wheel" ]' if config["sudo"] else "[ ]"
sudo_enable = nix_bool(config["sudo"])
sudo_wheel_needs_password = "false" if config["sudo"] else "true"

workspace = config["workspace"]
tmpfiles_rules = build_workspace_tmpfiles_rules(workspace)

tmpfiles_block = "\n".join([
    f'    "{rule}"'
    for rule in tmpfiles_rules
])

metadata = {
    "exam_id": config["exam_id"],
    "student_id": config["student_id"],
    "machine_id": config["machine_id"],
    "workspace": config["workspace"],
    "packages": config["packages"],
    "sudo": config["sudo"],
    "internet": config["internet"],
    "educ_access": config["educ_access"],
    "allowed_domains": config["allowed_domains"],
    "generated_at": generated_at
}

network_policy = {
    "internet": "allowed" if config["internet"] else "blocked",
    "educ_access": "allowed" if config["educ_access"] else "blocked",
    "allowed_domains": config["allowed_domains"],
    "note": (
        "Le filtrage par domaine doit être appliqué via DNS contrôlé, proxy, "
        "ou conversion domaine vers IP par l'infrastructure réseau."
    )
}

metadata_file.write_text(
    json.dumps(metadata, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

network_policy_file.write_text(
    json.dumps(network_policy, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
network_policy_json = json.dumps(network_policy, indent=2, ensure_ascii=False)

nix_content = f"""{{ config, pkgs, lib, ... }}:

# ---------------------------------------------------------------------------
# Configuration NixOS générée automatiquement par la plateforme d'examen
# ---------------------------------------------------------------------------
#
# Examen   : {config["exam_id"]}
# Étudiant : {config["student_id"]}
# Machine  : {config["machine_id"]}
# Générée  : {generated_at}
#
# Ce fichier traduit les choix de l'enseignant en configuration système NixOS.
# Il peut être importé dans /etc/nixos/configuration.nix sur une machine cible.
#
# Exemple :
#
# imports = [
#   ./exam-configuration.nix
# ];
#
# ---------------------------------------------------------------------------

let
  examId = "{config["exam_id"]}";
  studentId = "{config["student_id"]}";
  machineId = "{config["machine_id"]}";
  examWorkspace = "{workspace}";
in
{{
  # -------------------------------------------------------------------------
  # 1. Utilisateur d'examen
  # -------------------------------------------------------------------------
  #
  # L'utilisateur "exam" représente le compte utilisé pendant l'épreuve.
  # Les droits sudo dépendent directement du choix effectué par l'enseignant.

  users.groups.exam = {{}};

  users.users.exam = {{
    isNormalUser = true;
    description = "Utilisateur d'examen";
    group = "exam";
    home = "/home/exam";
    createHome = true;
    extraGroups = {sudo_extra_groups};
  }};

  # -------------------------------------------------------------------------
  # 2. Droits administrateur
  # -------------------------------------------------------------------------
  #
  # sudo = {config["sudo"]}
  #
  # Si sudo est désactivé, l'étudiant ne possède pas de droits administrateur.
  # Si sudo est activé, l'utilisateur exam appartient au groupe wheel.

  security.sudo.enable = {sudo_enable};
  security.sudo.wheelNeedsPassword = {sudo_wheel_needs_password};

  # -------------------------------------------------------------------------
  # 3. Paquets autorisés pour l'examen
  # -------------------------------------------------------------------------
  #
  # La liste provient du catalogue validé côté serveur.
  # Aucun paquet arbitraire ne doit être accepté.

  environment.systemPackages = with pkgs; [
    {packages_block}
  ];

  # -------------------------------------------------------------------------
  # 4. Espace de travail étudiant
  # -------------------------------------------------------------------------
  #
  # Le workspace est créé avec des droits limités.
  # Il correspond au dossier qui sera sauvegardé puis remis à zéro.

  systemd.tmpfiles.rules = [
{tmpfiles_block}
  ];

  # -------------------------------------------------------------------------
  # 5. Politique réseau prévue
  # -------------------------------------------------------------------------
  #
  # Internet autorisé : {config["internet"]}
  # Accès Educ autorisé : {config["educ_access"]}
  # Domaines autorisés : {", ".join(config["allowed_domains"])}
  #
  # Remarque importante :
  # NixOS/nftables filtre principalement par IP, port et interface.
  # Le filtrage par nom de domaine doit être traité avec un DNS contrôlé,
  # un proxy, une passerelle réseau ou une conversion domaine -> IP validée
  # par l'infrastructure de l'école.
  #
  # Dans ce prototype, la politique est générée dans :
  # /etc/exam/network-policy.json

  networking.firewall.enable = true;
  networking.nftables.enable = true;

  environment.etc."exam/network-policy.json".text = ''
{network_policy_json}
  '';

  # -------------------------------------------------------------------------
  # 6. Métadonnées d'examen
  # -------------------------------------------------------------------------
  #
  # Ces informations permettent d'identifier clairement la configuration
  # appliquée à une machine donnée.

  environment.etc."exam/metadata.json".text = ''
{metadata_json}
  '';
}}
"""

nix_file.write_text(nix_content, encoding="utf-8")

print("Configuration NixOS générée avec succès")
print(f"Fichier NixOS      : {nix_file}")
print(f"Métadonnées        : {metadata_file}")
print(f"Politique réseau   : {network_policy_file}")

write_log("NIX", f"Configuration NixOS générée : {nix_file}")
write_log("NIX", f"Métadonnées générées : {metadata_file}")
write_log("NIX", f"Politique réseau générée : {network_policy_file}")