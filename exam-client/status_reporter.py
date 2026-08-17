import requests

from client_settings import SERVER_URL, EXAM_ID, STUDENT_ID, MACHINE_ID
from logger import write_log


def report_status(step: str, status: str, message: str):
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
        response = requests.post(url, json=payload)

        if response.status_code != 200:
            write_log("STATUS_ERROR", f"Erreur serveur statut : {response.text}")
            return

        write_log("STATUS", f"{step} - {status} - {message}")

    except Exception as e:
        write_log("STATUS_ERROR", f"Impossible d'envoyer le statut : {e}")