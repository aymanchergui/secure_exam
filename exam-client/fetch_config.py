from urllib.request import urlopen
import json
import sys

from client_settings import SERVER_URL, EXAM_ID, STUDENT_ID, MACHINE_ID, get_config_path
from logger import write_log


url = f"{SERVER_URL}/configs/{EXAM_ID}/{STUDENT_ID}/{MACHINE_ID}"

try:
    with urlopen(url) as response:
        config = json.loads(response.read().decode("utf-8"))

except Exception as e:
    print(f"Erreur lors de la récupération de la configuration : {e}")
    write_log("FETCH_ERROR", f"Erreur récupération configuration : {e}")
    sys.exit(1)


output_file = get_config_path()
output_file.parent.mkdir(exist_ok=True)

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