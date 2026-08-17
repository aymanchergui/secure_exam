from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "exam-client.log"


def write_log(action: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{timestamp}] [{action}] {message}\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    print(line.strip())