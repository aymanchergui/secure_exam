# Démonstration du cycle complet NixOS réel

## Objectif

Cette documentation décrit la démonstration complète du fonctionnement de SecureExam sur une machine NixOS réelle.

La démonstration permet de valider le scénario suivant :

```text
Configuration enseignant
→ récupération par la machine d'examen
→ génération NixOS
→ préparation du workspace réel
→ simulation d'un travail étudiant
→ archivage ZIP
→ envoi au backend
→ confirmation de dépôt
→ remise à zéro du workspace
```

Le but est de prouver que la plateforme ne fonctionne pas uniquement en simulation, mais aussi sur un vrai environnement NixOS avec un utilisateur système dédié.

---

## Prérequis

Avant de lancer la démonstration, le backend FastAPI doit être démarré.

Dans un premier terminal :

```bash
cd ~/secure_exam/backend
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Le terminal doit afficher :

```text
Uvicorn running on http://0.0.0.0:8000
```

Vérification possible :

```bash
curl http://127.0.0.1:8000/health
```

Réponse attendue :

```json
{
  "status": "ok",
  "message": "Serveur opérationnel"
}
```

---

## Configuration du client

Le fichier suivant doit être configuré :

```text
exam-client/client_settings.json
```

Exemple :

```json
{
  "server_url": "http://127.0.0.1:8000",
  "exam_id": "EXAM-PYTHON-2026",
  "student_id": "etu001",
  "machine_id": "PC01",
  "execution_mode": "real"
}
```

Le champ important est :

```json
"execution_mode": "real"
```

Il indique que le client travaille sur le vrai workspace NixOS :

```text
/home/exam/etu001/workspace
```

et non dans le workspace simulé :

```text
exam-client/runtime/home/exam/etu001/workspace
```

---

## Préparation NixOS

La configuration NixOS générée par le client se trouve dans :

```text
exam-client/generated/exam-configuration.nix
```

Elle peut être copiée dans la configuration système :

```bash
sudo cp ~/secure_exam/exam-client/generated/exam-configuration.nix /etc/nixos/exam-configuration.nix
```

Puis importée dans :

```text
/etc/nixos/configuration.nix
```

Exemple :

```nix
imports =
  [
    ./hardware-configuration.nix
    ./exam-configuration.nix
  ];
```

Application temporaire de la configuration :

```bash
sudo nixos-rebuild test
```

Cette commande permet de tester la configuration sans l'inscrire définitivement comme configuration active au prochain démarrage.

---

## Vérifications système

Après application de la configuration NixOS, l'utilisateur d'examen doit exister :

```bash
getent passwd exam
```

Résultat attendu :

```text
exam:x:...:Utilisateur d'examen:/home/exam:/run/current-system/sw/bin/bash
```

Le workspace réel doit exister :

```bash
sudo ls -la /home/exam/etu001/workspace
```

L'utilisateur `exam` ne doit pas disposer de sudo lorsque l'enseignant a désactivé cette option :

```bash
sudo -u exam -H bash -lc 'whoami; groups; sudo -n true; echo sudo_exit:$?'
```

Résultat attendu :

```text
exam
exam
sudo_exit:1
```

Un code différent de `0` signifie que l'utilisateur `exam` ne peut pas utiliser sudo.

---

## Lancement de la démonstration complète

Dans un second terminal :

```bash
cd ~/secure_exam/exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl
```

Puis lancer le script :

```bash
chmod +x demo_full.sh
./demo_full.sh
```

---

## Rôle du script `demo_full.sh`

Le script exécute automatiquement tout le cycle réel.

Il effectue les étapes suivantes :

```text
1. Vérification du backend FastAPI
2. Vérification du module Python requests
3. Démarrage réel de l'examen
4. Récupération de la configuration depuis le backend
5. Génération de la configuration NixOS
6. Application de la configuration côté client
7. Préparation du workspace réel
8. Simulation du travail étudiant
9. Sauvegarde du workspace
10. Envoi de l'archive au backend
11. Confirmation de l'envoi
12. Remise à zéro du workspace
13. Vérification de l'archive
14. Vérification des soumissions côté backend
```

---

## Étape 1 : vérification du backend

Le script commence par vérifier que le backend répond :

```bash
curl http://127.0.0.1:8000/health
```

Réponse attendue :

```json
{
  "status": "ok",
  "message": "Serveur opérationnel"
}
```

---

## Étape 2 : démarrage réel de l'examen

Le script lance :

```bash
start_exam.py
```

Cette étape effectue :

```text
FETCH
GENERATE_NIX
APPLY
```

### FETCH

La machine récupère la configuration depuis le backend.

Exemple :

```text
Configuration récupérée avec succès
Examen    : EXAM-PYTHON-2026
Étudiant  : etu001
Machine   : PC01
```

### GENERATE_NIX

Le client génère les fichiers NixOS :

```text
generated/exam-configuration.nix
generated/exam-metadata.json
generated/network-policy.json
```

### APPLY

Le client prépare le workspace réel :

```text
/home/exam/etu001/workspace
```

Il crée également les fichiers de suivi :

```text
exam_metadata.json
exam_network_policy.json
```

---

## Étape 3 : simulation du travail étudiant

Le script crée un fichier étudiant dans le workspace réel :

```text
/home/exam/etu001/workspace/main.py
```

Exemple :

```python
print("demo soutenance secure exam")
```

Cette étape simule le travail produit par l'étudiant pendant l'examen.

---

## Étape 4 : fin d'examen

Le script lance :

```bash
finish_exam.py
```

Cette étape exécute :

```text
BACKUP
SUBMIT
RESET
```

### BACKUP

Le workspace réel est archivé en ZIP.

Exemple :

```text
archives/EXAM-PYTHON-2026_etu001_PC01_YYYYMMDD_HHMMSS.zip
```

### SUBMIT

L'archive ZIP est envoyée au backend FastAPI.

Exemple de réponse attendue :

```text
Archive envoyée avec succès
Archive reçue et enregistrée en base avec succès
```

### RESET

Après confirmation de l'envoi serveur, le workspace réel est supprimé puis recréé proprement.

Cette sécurité évite de supprimer les fichiers étudiants avant leur sauvegarde et leur dépôt.

---

## Vérifications finales

Le script vérifie que le workspace est vide après reset :

```bash
sudo ls -la /home/exam/etu001/workspace
```

Résultat attendu :

```text
.
..
```

Le script affiche aussi la dernière archive créée :

```bash
unzip -l archives/EXAM-PYTHON-2026_etu001_PC01_YYYYMMDD_HHMMSS.zip
```

Contenu attendu :

```text
main.py
exam_network_policy.json
exam_metadata.json
```

Enfin, le script interroge le backend pour vérifier que la soumission apparaît côté serveur :

```text
/submissions-list
```

Exemple :

```json
{
  "count": 4,
  "submissions": [
    "EXAM-PYTHON-2026_etu001_PC01_20260818_134446.zip"
  ]
}
```

---

## Résultat attendu

À la fin, le terminal doit afficher :

```text
Démonstration terminée avec succès.
```

Cela valide que le cycle complet fonctionne sur NixOS réel :

```text
start_exam.py réel
→ travail étudiant
→ finish_exam.py réel
→ archive
→ dépôt serveur
→ reset sécurisé
```

---

## Résultat validé

La démonstration a permis de valider :

```text
Backend FastAPI opérationnel
Configuration récupérée depuis le backend
Configuration NixOS générée
Workspace réel préparé
Utilisateur exam utilisé
Droits sudo désactivés pour exam
Travail étudiant sauvegardé
Archive envoyée au backend
Soumission enregistrée en base
Workspace remis à zéro après confirmation
```

---

## Sécurité de la remise à zéro

Le reset du workspace n'est effectué que si deux conditions sont respectées :

```text
1. Une archive locale existe
2. L'archive locale correspond à l'archive confirmée comme envoyée au backend
```

Si l'une de ces conditions échoue, la remise à zéro est annulée pour éviter la perte du travail étudiant.

---

## Limite actuelle

La politique réseau est générée dans :

```text
generated/network-policy.json
/etc/exam/network-policy.json
/home/exam/etu001/workspace/exam_network_policy.json
```

Cependant, le filtrage réseau strict par domaine n'est pas encore appliqué automatiquement.

Le filtrage par domaine nécessite une intégration avec une solution réseau réelle :

```text
proxy
DNS contrôlé
passerelle réseau
règles nftables basées sur des IP validées
```

Cette partie est identifiée comme une limite actuelle et une perspective d'amélioration.

---

## Conclusion

Cette démonstration valide le cœur technique du projet SecureExam.

Elle montre qu'une configuration créée côté enseignant peut être récupérée par une machine NixOS, transformée en configuration système, appliquée à un workspace réel, puis utilisée dans un cycle complet d'examen avec sauvegarde, dépôt serveur et remise à zéro sécurisée.