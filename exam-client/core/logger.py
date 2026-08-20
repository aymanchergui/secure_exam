from pathlib import Path
from datetime import datetime

# Racine du client SecureExam :
# exam-client/
CLIENT_ROOT = Path(__file__).resolve().parents[1]

# Tous les fichiers générés localement sont rangés dans var/
LOG_DIR = CLIENT_ROOT / "var" / "logs"
LOG_FILE = LOG_DIR / "exam-client.log"

def write_log(action: str, message: str) -> None:
    """
    Écrit un événement dans le fichier de log local du client.

    Exemple de ligne :
    [2026-08-20 10:22:00] [FETCH] Configuration récupérée
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{action}] {message}"

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")

    print(line)
