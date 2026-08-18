from pathlib import Path
import json
import os
import sys

try:
    import requests
except ModuleNotFoundError:
    print("Module Python manquant : requests")
    print("Relance le client avec :")
    print("nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl")
    sys.exit(1)

from client_settings import SERVER_URL, get_config_path
from logger import write_log


CONFIG_FILE = get_config_path()
ARCHIVE_DIR = Path("archives")
SUBMITTED_DIR = Path("submitted")
HTTP_TIMEOUT_SECONDS = 10


def restore_file_owner_for_user(path: Path) -> None:
    """
    Si le script est lancé avec sudo, le fichier de preuve peut être créé par root.
    On le redonne à l'utilisateur original pour garder le dossier propre.
    """
    sudo_uid = os.getenv("SUDO_UID")
    sudo_gid = os.getenv("SUDO_GID")

    if sudo_uid is None or sudo_gid is None:
        return

    try:
        os.chown(path, int(sudo_uid), int(sudo_gid))
    except Exception:
        pass


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"Configuration introuvable : {CONFIG_FILE}")
        write_log("SUBMIT_ERROR", f"Configuration introuvable : {CONFIG_FILE}")
        sys.exit(1)

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"Configuration invalide : {CONFIG_FILE}")
        print(error)
        write_log("SUBMIT_ERROR", f"Configuration JSON invalide : {error}")
        sys.exit(1)


def find_latest_archive(config: dict) -> Path:
    archive_pattern = f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_*.zip"
    archives = list(ARCHIVE_DIR.glob(archive_pattern))

    if not archives:
        print("Aucune archive à envoyer.")
        print("Fin d'examen arrêtée : le reset ne sera pas exécuté.")
        write_log("SUBMIT_ERROR", "Aucune archive à envoyer")
        sys.exit(1)

    return max(archives, key=lambda path: path.stat().st_mtime)


def send_archive(config: dict, latest_archive: Path) -> dict:
    url = f"{SERVER_URL}/submissions"

    data = {
        "exam_id": config["exam_id"],
        "student_id": config["student_id"],
        "machine_id": config["machine_id"]
    }

    print(f"Archive sélectionnée : {latest_archive}")
    print(f"Envoi vers le backend : {url}")

    try:
        with open(latest_archive, "rb") as file:
            files = {
                "archive": (latest_archive.name, file, "application/zip")
            }

            response = requests.post(
                url,
                data=data,
                files=files,
                timeout=HTTP_TIMEOUT_SECONDS
            )

    except requests.exceptions.Timeout:
        print("Erreur : délai dépassé pendant l'envoi de l'archive.")
        print(f"Backend ciblé : {SERVER_URL}")
        print("Vérifie que le serveur FastAPI est lancé.")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("SUBMIT_ERROR", "Timeout pendant l'envoi de l'archive")
        sys.exit(1)

    except requests.exceptions.ConnectionError:
        print("Erreur : impossible de contacter le backend FastAPI.")
        print(f"Backend ciblé : {SERVER_URL}")
        print("Vérifie que le serveur est lancé avec :")
        print("python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("SUBMIT_ERROR", f"Connexion impossible au backend : {SERVER_URL}")
        sys.exit(1)

    except requests.exceptions.RequestException as error:
        print("Erreur réseau pendant l'envoi de l'archive.")
        print(error)
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("SUBMIT_ERROR", f"Erreur réseau : {error}")
        sys.exit(1)

    if not 200 <= response.status_code < 300:
        print("Erreur lors de l'envoi de l'archive.")
        print(f"Code HTTP : {response.status_code}")
        print("Réponse serveur :")
        print(response.text)
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("SUBMIT_ERROR", f"Erreur serveur HTTP {response.status_code} : {response.text}")
        sys.exit(1)

    try:
        return response.json()
    except ValueError:
        print("Erreur : le serveur a répondu sans JSON valide.")
        print("Réponse serveur :")
        print(response.text)
        print("Reset annulé pour éviter la perte des données étudiant.")
        write_log("SUBMIT_ERROR", "Réponse serveur JSON invalide")
        sys.exit(1)


def write_submission_marker(config: dict, latest_archive: Path, server_response: dict) -> Path:
    SUBMITTED_DIR.mkdir(exist_ok=True)

    marker_file = SUBMITTED_DIR / "last_submission.json"

    marker_data = {
        "exam_id": config["exam_id"],
        "student_id": config["student_id"],
        "machine_id": config["machine_id"],
        "archive": latest_archive.name,
        "server_response": server_response
    }

    marker_file.write_text(
        json.dumps(marker_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    restore_file_owner_for_user(marker_file)

    return marker_file



def archive_already_submitted(config: dict, latest_archive: Path) -> bool:
    """
    Évite de renvoyer deux fois la même archive.
    On considère une archive déjà envoyée si elle correspond à la preuve locale.
    """
    marker_file = SUBMITTED_DIR / "last_submission.json"

    if not marker_file.exists():
        return False

    try:
        marker_data = json.loads(marker_file.read_text(encoding="utf-8"))
    except Exception:
        return False

    return (
        marker_data.get("exam_id") == config["exam_id"]
        and marker_data.get("student_id") == config["student_id"]
        and marker_data.get("machine_id") == config["machine_id"]
        and marker_data.get("archive") == latest_archive.name
    )


def main() -> None:
    config = load_config()
    latest_archive = find_latest_archive(config)

    if archive_already_submitted(config, latest_archive):
        print("Archive déjà envoyée.")
        print(f"Archive : {latest_archive}")
        print("Aucun nouvel envoi effectué.")
        print("La preuve locale d'envoi existe déjà.")
        write_log("SUBMIT", f"Archive déjà envoyée, envoi ignoré : {latest_archive}")
        return

    server_response = send_archive(config, latest_archive)

    print("Archive envoyée avec succès")
    print(server_response)

    write_log("SUBMIT", f"Archive envoyée au serveur : {latest_archive}")

    marker_file = write_submission_marker(config, latest_archive, server_response)

    print(f"Preuve d'envoi créée : {marker_file}")


if __name__ == "__main__":
    main()
