import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

GENERATED_DIR = Path("generated")
RULES_FILE = GENERATED_DIR / "network-rules.nft"
STATE_DIR = Path("runtime") / "network"
STATE_FILE = STATE_DIR / "network_rules_state.txt"

TABLE_FAMILY = "inet"
TABLE_NAME = "secure_exam"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def require_rules_file() -> None:
    if not RULES_FILE.exists():
        print(f"Erreur : fichier introuvable : {RULES_FILE}")
        print("Lance d'abord start_exam.py ou generate_network_rules.py.")
        sys.exit(1)


def require_nft() -> str:
    nft_path = shutil.which("nft")

    if nft_path is None:
        print("Erreur : nftables introuvable.")
        print("Lance le script dans un shell avec nftables :")
        print("nix-shell -p nftables")
        sys.exit(1)

    return nft_path


def require_root(action: str) -> None:
    if os.geteuid() != 0:
        print(f"Erreur : l'action '{action}' nécessite sudo.")
        print(f"Utilise : sudo python apply_network_rules.py --{action}")
        sys.exit(1)


def run_command(command: list[str], check: bool = True):
    result = subprocess.run(
        command,
        text=True,
        capture_output=True
    )

    if check and result.returncode != 0:
        print("Commande échouée :")
        print(" ".join(command))

        if result.stdout.strip():
            print("\nSTDOUT:")
            print(result.stdout.strip())

        if result.stderr.strip():
            print("\nSTDERR:")
            print(result.stderr.strip())

        sys.exit(result.returncode)

    return result


def check_rules() -> None:
    require_rules_file()
    nft_path = require_nft()

    print("Vérification syntaxique des règles réseau...")
    run_command([
        nft_path,
        "-c",
        "-f",
        str(RULES_FILE)
    ])

    print("Règles nftables valides.")


def apply_rules() -> None:
    require_root("apply")
    require_rules_file()
    nft_path = require_nft()

    print("Application des règles réseau strictes...")
    print(f"Fichier utilisé : {RULES_FILE}")

    run_command([
        nft_path,
        "-c",
        "-f",
        str(RULES_FILE)
    ])

    run_command([
        nft_path,
        "delete",
        "table",
        TABLE_FAMILY,
        TABLE_NAME
    ], check=False)

    run_command([
        nft_path,
        "-f",
        str(RULES_FILE)
    ])

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        f"applied_at={now_text()}\n"
        f"rules_file={RULES_FILE}\n"
        f"table={TABLE_FAMILY} {TABLE_NAME}\n",
        encoding="utf-8"
    )

    print("Règles réseau appliquées avec succès.")
    print("La politique cible toute la machine selon le fichier généré.")
    print("Pour annuler : sudo python apply_network_rules.py --reset")


def reset_rules() -> None:
    require_root("reset")
    nft_path = require_nft()

    print("Suppression des règles réseau SecureExam...")

    result = run_command([
        nft_path,
        "delete",
        "table",
        TABLE_FAMILY,
        TABLE_NAME
    ], check=False)

    if result.returncode == 0:
        print("Table nftables supprimée.")
    else:
        print("Aucune table SecureExam active à supprimer.")

    if STATE_FILE.exists():
        STATE_FILE.unlink()

    print("Réseau SecureExam réinitialisé.")


def show_status() -> None:
    nft_path = require_nft()

    result = run_command([
        nft_path,
        "list",
        "table",
        TABLE_FAMILY,
        TABLE_NAME
    ], check=False)

    if result.returncode == 0:
        print("Règles SecureExam actives :")
        print(result.stdout)
    else:
        print("Aucune règle SecureExam active.")

    if STATE_FILE.exists():
        print("\nÉtat local :")
        print(STATE_FILE.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Application contrôlée des règles réseau ISEN SecureExam."
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifie la syntaxe des règles sans les appliquer."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique réellement les règles réseau."
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Supprime les règles réseau SecureExam."
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche l'état des règles réseau SecureExam."
    )

    args = parser.parse_args()

    selected_actions = [
        args.check,
        args.apply,
        args.reset,
        args.status
    ]

    if sum(bool(action) for action in selected_actions) != 1:
        print("Choisis une seule action : --check, --apply, --reset ou --status")
        sys.exit(1)

    if args.check:
        check_rules()

    if args.apply:
        apply_rules()

    if args.reset:
        reset_rules()

    if args.status:
        show_status()


if __name__ == "__main__":
    main()