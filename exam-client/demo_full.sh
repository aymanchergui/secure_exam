#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "========================================"
echo " Démonstration cycle complet NixOS réel "
echo "========================================"

echo ""
echo "[1/6] Vérification du backend FastAPI..."
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

echo ""
echo "[2/6] Vérification du module requests..."
python3 -c "import requests; print('requests OK')"

echo ""
echo "[3/6] Démarrage réel de l'examen..."
PYTHON_BIN="$(which python3)"
sudo -E env "PYTHONPATH=${PYTHONPATH:-}" "$PYTHON_BIN" start_exam.py

echo ""
echo "[4/6] Simulation du travail étudiant..."
sudo -u exam -H bash -lc 'echo "print(\"demo soutenance secure exam\")" > /home/exam/etu001/workspace/main.py'
sudo -u exam -H bash -lc 'ls -la /home/exam/etu001/workspace'

echo ""
echo "[5/6] Fin d'examen : backup, submit, reset..."
sudo -E env "PYTHONPATH=${PYTHONPATH:-}" "$PYTHON_BIN" finish_exam.py

echo ""
echo "[6/6] Vérifications finales..."
echo ""
echo "Workspace réel après reset :"
sudo ls -la /home/exam/etu001/workspace

echo ""
echo "Dernière archive créée :"
LATEST="$(ls -t archives/EXAM-PYTHON-2026_etu001_PC01_*.zip | head -n 1)"
echo "$LATEST"

echo ""
echo "Contenu de l'archive :"
unzip -l "$LATEST"

echo ""
echo "Soumissions côté backend :"
TOKEN="$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"prof","password":"1234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

curl -s http://127.0.0.1:8000/submissions-list \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "========================================"
echo " Démonstration terminée avec succès."
echo "========================================"