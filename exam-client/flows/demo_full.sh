#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$CLIENT_ROOT"

echo "========================================"
echo " Démonstration cycle complet NixOS réel "
echo "========================================"

PYTHON_BIN="$(which python3)"
export PYTHONPATH="$CLIENT_ROOT:${PYTHONPATH:-}"

echo ""
echo "[1/7] Vérification du backend FastAPI..."
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

echo ""
echo "[2/7] Vérification du module requests..."
python3 -c "import requests; print('requests OK')"

echo ""
echo "[3/7] Vérification de la configuration client..."
python3 - <<'PY'
from config.client_settings import SETTINGS_FILE, SERVER_URL, EXAM_ID, STUDENT_ID, MACHINE_ID, get_execution_mode
print("Settings :", SETTINGS_FILE)
print("Backend  :", SERVER_URL)
print("Exam     :", EXAM_ID)
print("Student  :", STUDENT_ID)
print("Machine  :", MACHINE_ID)
print("Mode     :", get_execution_mode())
PY

echo ""
echo "[4/7] Démarrage de l'examen..."
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" flows/start_exam.py

echo ""
echo "[5/7] Simulation du travail étudiant..."

WORKSPACE="$(python3 - <<'PY'
import json
from config.client_settings import get_config_path, get_workspace_path
config = json.loads(get_config_path().read_text(encoding="utf-8"))
print(get_workspace_path(config))
PY
)"

echo "Workspace détecté : $WORKSPACE"

sudo mkdir -p "$WORKSPACE"

if id exam >/dev/null 2>&1; then
  sudo chown -R exam:exam "$WORKSPACE"
  sudo -u exam -H bash -lc "cat > '$WORKSPACE/main.py' <<'PY'
print(\"demo soutenance secure exam\")
PY"
  sudo -u exam -H bash -lc "cat > '$WORKSPACE/README.txt' <<'TXT'
Rendu de démonstration SecureExam.
TXT"
else
  echo "Utilisateur exam introuvable, écriture avec l'utilisateur courant."
  cat > "$WORKSPACE/main.py" <<'PY'
print("demo soutenance secure exam")
PY
  cat > "$WORKSPACE/README.txt" <<'TXT'
Rendu de démonstration SecureExam.
TXT
fi

echo "Contenu du workspace avant fin d'examen :"
sudo ls -la "$WORKSPACE"

echo ""
echo "[6/7] Fin d'examen : backup, submit, reset..."
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" flows/finish_exam.py

echo ""
echo "[7/7] Vérifications finales..."

echo ""
echo "Workspace après reset :"
sudo ls -la "$WORKSPACE"

echo ""
echo "Dernière archive créée :"
ARCHIVE_PREFIX="$(python3 - <<'PY'
import json
from config.client_settings import get_config_path
config = json.loads(get_config_path().read_text(encoding="utf-8"))
print(f"{config['exam_id']}_{config['student_id']}_{config['machine_id']}_")
PY
)"

LATEST="$(ls -t var/archives/${ARCHIVE_PREFIX}*.zip | head -n 1)"
echo "$LATEST"

echo ""
echo "Contenu de l'archive :"
unzip -l "$LATEST"

echo ""
echo "Rapport de reset :"
cat var/submitted/last_reset_report.json | python3 -m json.tool

echo ""
echo "Soumissions côté backend :"
TOKEN="$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"prof","password":"1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

curl -s \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/submissions-list \
  | python3 -m json.tool

echo ""
echo "========================================"
echo " Démonstration terminée avec succès."
echo "========================================"
