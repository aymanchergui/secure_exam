from pathlib import Path
import sys

CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from config.client_settings import SERVER_URL, EXAM_ID, STUDENT_ID, MACHINE_ID
from core.logger import write_log

try:
    import requests
except ModuleNotFoundError:
    requests = None

HTTP_TIMEOUT_SECONDS = 5

def report_status(step: str, status: str, message: str) -> None:
    """
    Envoie l'état courant de la machine au backend.

    Important :
    Le reporting ne doit jamais bloquer le déroulement de l'examen.
    Si le module requests est absent ou si le backend ne répond pas,
    on écrit seulement l'erreur dans les logs locaux.
    """
    if requests is None:
        write_log(
            "STATUS_SKIPPED",
            f"{step} - {status} - {message} | module requests absent"
        )
        return

    url = f"{SERVER_URL}/machine-status"

    payload = {
        "exam_id": EXAM_ID,
        "student_id": STUDENT_ID,
        "machine_id": MACHINE_ID,
        "step": step,
        "status": status,
        "message": message
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=HTTP_TIMEOUT_SECONDS
        )

        if response.status_code != 200:
            write_log("STATUS_ERROR", f"Erreur serveur statut : {response.text}")
            return

        write_log("STATUS", f"{step} - {status} - {message}")

    except Exception as error:
        write_log("STATUS_ERROR", f"Impossible d'envoyer le statut : {error}")
