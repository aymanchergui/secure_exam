from pathlib import Path
from urllib.request import urlopen
import json
import sys

# Permet d'exécuter ce fichier directement avec :
# python3 api/fetch_config.py
CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import SERVER_URL, EXAM_ID, STUDENT_ID, MACHINE_ID, get_config_path
from core.logger import write_log

HTTP_TIMEOUT_SECONDS = 10

def main() -> None:
    """
    Récupère la configuration d'examen depuis le backend SecureExam,
    puis l'enregistre dans var/downloaded/.
    """
    url = f"{SERVER_URL}/configs/{EXAM_ID}/{STUDENT_ID}/{MACHINE_ID}"

    try:
        with urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            config = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"Erreur lors de la récupération de la configuration : {error}")
        write_log("FETCH_ERROR", f"Erreur récupération configuration : {error}")
        sys.exit(1)

    output_file = get_config_path()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Configuration récupérée avec succès")
    print(f"Examen    : {config['exam_id']}")
    print(f"Étudiant  : {config['student_id']}")
    print(f"Machine   : {config['machine_id']}")
    print(f"Fichier   : {output_file}")

    write_log("FETCH", f"Configuration récupérée : {output_file}")

if __name__ == "__main__":
    main()
