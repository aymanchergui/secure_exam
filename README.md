# ISEN SecureExam

**ISEN SecureExam** est une plateforme web de configuration, de supervision et de validation d’environnements Linux d’examen.

Le projet permet à un enseignant de préparer un environnement Linux sécurisé, reproductible et contrôlé pour une épreuve, tout en assurant la récupération des rendus étudiants et la remise à zéro du poste après l’examen.

---

## Informations projet

| Élément | Description |
|---|---|
| Nom du projet | ISEN SecureExam |
| Version | v1.0.9 |
| Cadre | Bureau d’étude ISEN 2026-2027 |
| Établissement | ISEN Méditerranée / Toulon |
| Développeur | Ayman CHERGUI |
| Contact développeur | ayman.chergui@isen.yncrea.fr |
| Site web | https://aymanchergui.com |
| Client / Référent | Willy DUQUENOY |
| Fonction | Directeur des Systèmes d’Information |
| Contact référent | willy.duquenoy@yncrea.fr |

---

## Présentation

ISEN SecureExam est un prototype fonctionnel permettant à un enseignant de préparer, contrôler et superviser un environnement Linux d’examen de manière sécurisée et reproductible.

Le besoin principal est le suivant :

> permettre à un enseignant de configurer rapidement un environnement Linux d’examen contrôlé, sans intervention manuelle sur chaque machine, tout en garantissant la récupération des rendus étudiants et la remise à zéro de l’environnement après l’épreuve.

La plateforme permet notamment de :

- créer une configuration d’examen ;
- sélectionner les logiciels autorisés ;
- définir les droits administrateur de l’étudiant ;
- définir une politique réseau ;
- gérer l’accès Internet, l’accès Educ et les domaines autorisés ;
- générer une configuration NixOS ;
- préparer un workspace étudiant ;
- suivre l’état des machines ;
- récupérer les rendus étudiants ;
- archiver les fichiers de travail ;
- envoyer les archives au serveur ;
- réinitialiser le workspace après confirmation d’envoi ;
- gérer un profil enseignant ;
- gérer une photo de profil ;
- envoyer et consulter des demandes de support ;
- séparer les données par enseignant ;
- consulter les informations du projet, les crédits et la version.

---

## Noyaux du projet

Le projet repose sur trois noyaux principaux :

```text
Backend FastAPI
→ API REST, authentification, base SQLite, supervision, support, rendus

Frontend Angular
→ interface enseignant, dashboard, configuration, profil, support, crédits

Exam-client Python
→ récupération de configuration, génération NixOS, application, sauvegarde, dépôt, reset
```

Architecture logique :

```text
Enseignant
   ↓
Frontend Angular
   ↓
Backend FastAPI + SQLite
   ↓
Machine d’examen
   ↓
Exam-client Python
   ↓
NixOS / Linux / Workspace étudiant
```

Chaîne fonctionnelle principale :

```text
Interface enseignant
→ création de configuration
→ récupération par la machine d’examen
→ génération NixOS
→ préparation du workspace
→ travail étudiant
→ archive ZIP
→ envoi au backend
→ confirmation de dépôt
→ reset sécurisé
```

---

## État actuel du projet

Le prototype dispose d’une chaîne complète et fonctionnelle :

```text
Création configuration
→ récupération client
→ génération configuration NixOS
→ génération politique réseau
→ application de l’environnement
→ simulation ou travail réel étudiant
→ sauvegarde ZIP
→ dépôt serveur
→ preuve locale d’envoi
→ reset sécurisé
```

Le projet prend en charge deux modes côté client :

```text
simulation → workspace local simulé dans exam-client/var/runtime/
real       → workspace réel NixOS dans /home/exam/<student_id>/workspace
```

Le mode réel NixOS a été validé avec :

- création de l’utilisateur système `exam` ;
- création d’un workspace réel ;
- application des permissions Linux ;
- disponibilité des paquets autorisés ;
- désactivation de `sudo` pour l’utilisateur étudiant ;
- génération des fichiers de suivi ;
- sauvegarde réelle du workspace ;
- envoi de l’archive au backend ;
- reset réel après confirmation de dépôt.

---

## Technologies utilisées

### Backend

- Python
- FastAPI
- Uvicorn
- SQLite
- JWT
- PyJWT
- Argon2 / pwdlib pour le hash des mots de passe
- python-dotenv
- SMTP pour les demandes de support

### Frontend

- Angular
- TypeScript
- HTML
- CSS
- Angular HttpClient
- Lucide Icons
- Fichier de version dynamique

### Exam-client

- Python
- Scripts client
- Génération de configuration NixOS
- Génération de politique réseau
- Sauvegarde ZIP
- Upload HTTP vers le backend
- Reset sécurisé du workspace
- Mode simulation
- Mode réel NixOS

### Système cible

- Linux
- NixOS
- nftables / firewall
- Workspace système dédié
- Environnement reproductible

---

## Structure générale du dépôt

```text
secure_exam/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── secure_exam.db              # généré localement, non versionné
│   ├── profile/                        # photos de profil locales, non versionnées
│   └── submissions/                    # archives ZIP reçues, non versionnées
│
├── frontend/
│   ├── angular.json
│   ├── package.json
│   ├── public/
│   │   └── assets/
│   │       ├── secure_exam_logo.png
│   │       ├── isen_logo.png
│   │       └── VERSION
│   └── src/
│       ├── index.html
│       └── app/
│           ├── app.ts
│           ├── app.html
│           ├── app.css
│           ├── app.config.ts
│           └── components/
│               ├── authentication/
│               ├── header/
│               ├── header-auth/
│               ├── profile/
│               └── support/
│
├── exam-client/
│   ├── api/
│   │   ├── fetch_config.py
│   │   ├── status_reporter.py
│   │   └── submit_archive.py
│   ├── config/
│   │   ├── client_settings.py
│   │   ├── client_settings.json        # local, non versionné
│   │   └── client_settings.example.json
│   ├── core/
│   │   └── logger.py
│   ├── flows/
│   │   ├── start_exam.py
│   │   ├── finish_exam.py
│   │   ├── exam_runner.py
│   │   └── demo_full.sh
│   ├── generation/
│   │   ├── generate_nixos_config.py
│   │   └── generate_network_rules.py
│   ├── system/
│   │   ├── apply_config.py
│   │   ├── apply_network_rules.py
│   │   └── reset_exam.py
│   ├── workspace/
│   │   ├── backup_workspace.py
│   │   └── simulate_student_work.py
│   ├── var/                            # runtime local, non versionné
│   │   ├── archives/
│   │   ├── downloaded/
│   │   ├── generated/
│   │   ├── logs/
│   │   ├── runtime/
│   │   └── submitted/
│   ├── tools/
│   ├── backup/
│   └── README.md
│
└── docs/
    └── demo_nixos_reel.md
```

Les fichiers générés, les données locales, les archives, les logs, les secrets et les bases locales sont exclus du dépôt Git.

---

# 1. Backend FastAPI

## Rôle du backend

Le backend est le noyau serveur du projet.

Il fournit :

- l’API REST ;
- l’authentification enseignant ;
- la gestion des profils enseignants ;
- la gestion des configurations d’examen ;
- la gestion du catalogue logiciel ;
- la réception des rendus étudiants ;
- la supervision des machines ;
- la gestion de l’historique machine ;
- la gestion des demandes de support ;
- l’envoi SMTP des demandes support ;
- la génération et le téléchargement des données utiles au client.

---

## Base de données SQLite

La base est créée automatiquement au lancement du backend :

```text
backend/database/secure_exam.db
```

Tables principales :

```text
teachers
teacher_profiles
package_catalog
support_requests
exam_configs
submissions
machine_status
machine_status_history
```

La base stocke notamment :

- les comptes enseignants ;
- les profils enseignants ;
- les chemins des photos de profil ;
- le catalogue logiciel ;
- les demandes de support ;
- les configurations d’examen ;
- les métadonnées des rendus ;
- le dernier état des machines ;
- l’historique des machines.

Les fichiers volumineux ne sont pas stockés directement dans SQLite.

Ils restent sur le système de fichiers :

```text
backend/submissions/     → archives ZIP reçues
backend/profile/         → photos de profil
exam-client/var/         → fichiers générés côté client
```

La base `secure_exam.db` est une donnée locale. Elle ne doit pas être publiée sur GitHub.

---

## Authentification

L’enseignant se connecte via :

```text
POST /auth/login
```

Après connexion, le backend retourne un token JWT.

Le frontend utilise ensuite ce token dans les requêtes protégées :

```text
Authorization: Bearer <token>
```

Les routes sensibles sont protégées par JWT.

Les mots de passe sont hashés avec Argon2 / pwdlib.

---

## Routes principales

```text
GET    /
GET    /health

POST   /auth/login
GET    /auth/me

GET    /dashboard

GET    /packages
POST   /packages
GET    /packages/search/{query}
PATCH  /packages/{package_id}/enable
PATCH  /packages/{package_id}/disable
DELETE /packages/{package_id}

POST   /configs
GET    /configs-list
GET    /configs/{exam_id}/{student_id}/{machine_id}
GET    /configs-file/{filename}
GET    /configs/{filename}/download
DELETE /configs/{filename}

POST   /submissions
GET    /submissions-list
GET    /submissions/{filename}/download
DELETE /submissions/{filename}

POST   /machine-status
GET    /machine-status-list
GET    /machine-status/{exam_id}/{student_id}/{machine_id}
GET    /machine-status-history/{exam_id}/{student_id}/{machine_id}

GET    /nixos-config
GET    /nixos-config/download

GET    /teacher-profile
PUT    /teacher-profile
POST   /teacher-profile/photo
GET    /teacher-profile/photo
GET    /teacher-profile/photo/{teacher_id}

POST   /support-requests
POST   /teacher-support-requests
GET    /support-requests-list
```

---

## Variables d’environnement

Le backend utilise :

```text
backend/.env
```

Un modèle est fourni :

```text
backend/.env.example
```

Créer le fichier local :

### Linux / NixOS

```bash
cd backend
cp .env.example .env
```

### Windows PowerShell

```powershell
cd backend
Copy-Item .env.example .env
```

Exemple :

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=replace_with_smtp_username
SMTP_PASSWORD=replace_with_smtp_app_password
SMTP_FROM_EMAIL=replace_with_sender_email
SUPPORT_TO_EMAIL=replace_with_support_email

JWT_SECRET_KEY=replace_with_long_random_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120

TEACHER_USERNAME=prof
TEACHER_PASSWORD=1234
```

Le fichier `.env` ne doit jamais être publié sur GitHub.

---

## Installation du backend

### Linux / NixOS

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Windows PowerShell

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Vérifier le backend :

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

Documentation Swagger :

```text
http://127.0.0.1:8000/docs
```

---

# 2. Frontend Angular

## Rôle du frontend

Le frontend est l’interface enseignant de la plateforme.

Il permet :

- l’authentification enseignant ;
- l’accès au dashboard ;
- la création des configurations d’examen ;
- la gestion du catalogue logiciel ;
- la consultation des configurations existantes ;
- le téléchargement des configurations JSON ;
- la consultation de la configuration NixOS générée ;
- la consultation des machines suivies ;
- la consultation des rendus étudiants ;
- le filtrage des rendus par examen et date ;
- la gestion du profil enseignant ;
- la gestion de la photo de profil ;
- la consultation des demandes support ;
- l’envoi de demandes support depuis le profil ;
- l’accès à la page support depuis l’authentification ;
- l’affichage professionnel des crédits, licences et version projet.

---

## Composants principaux

```text
authentication/  → page de connexion enseignant
header/          → header principal après connexion
header-auth/     → header public pour authentification/support + crédits
profile/         → profil enseignant, photo, support historique
support/         → formulaire support avant connexion
```

---

## Version frontend

La version est stockée dans :

```text
frontend/public/assets/VERSION
```

Exemple :

```text
1.0.9
```

Elle est chargée dynamiquement par le composant :

```text
frontend/src/app/components/header-auth/header-auth.ts
```

L’interface affiche ensuite :

```text
v1.0.9
```

---

## Installation du frontend

Depuis le dossier `frontend` :

```bash
cd frontend
npm install
npx ng serve --host 0.0.0.0 --port 4200
```

Sous Windows, si PowerShell bloque `ng`, utiliser :

```powershell
ng.cmd serve
```

Interface locale :

```text
http://localhost:4200
```

Depuis une VM, ouvrir le port si nécessaire :

```bash
sudo nixos-firewall-tool open tcp 4200
```

---

## Build frontend

```bash
cd frontend
npx ng build
```

Les fichiers compilés sont générés dans :

```text
frontend/dist/
```

---

## Notes Angular CLI

Ce projet frontend est basé sur Angular CLI.

Commandes utiles :

```bash
ng serve
ng build
ng generate component component-name
ng test
```

Documentation Angular CLI :

```text
https://angular.dev/tools/cli
```

---

# 3. Exam-client Python

## Rôle de l’exam-client

L’exam-client est le noyau installé ou exécuté sur la machine d’examen.

Il permet de :

- récupérer la configuration depuis le backend ;
- générer une configuration NixOS ;
- générer une politique réseau ;
- préparer le workspace étudiant ;
- appliquer les droits système ;
- vérifier les paquets autorisés ;
- simuler un travail étudiant ;
- sauvegarder le workspace ;
- créer une archive ZIP ;
- envoyer l’archive au backend ;
- créer une preuve locale d’envoi ;
- réinitialiser le workspace uniquement après confirmation d’envoi ;
- envoyer des statuts d’avancement au backend.

---

## Structure de l’exam-client

```text
exam-client/
├── api/
│   ├── fetch_config.py
│   ├── status_reporter.py
│   └── submit_archive.py
├── config/
│   ├── client_settings.py
│   ├── client_settings.json
│   └── client_settings.example.json
├── core/
│   └── logger.py
├── flows/
│   ├── start_exam.py
│   ├── finish_exam.py
│   ├── exam_runner.py
│   └── demo_full.sh
├── generation/
│   ├── generate_nixos_config.py
│   └── generate_network_rules.py
├── system/
│   ├── apply_config.py
│   ├── apply_network_rules.py
│   └── reset_exam.py
├── workspace/
│   ├── backup_workspace.py
│   └── simulate_student_work.py
└── var/
    ├── archives/
    ├── downloaded/
    ├── generated/
    ├── logs/
    ├── runtime/
    └── submitted/
```

---

## Configuration du client

Le fichier local est :

```text
exam-client/config/client_settings.json
```

Exemple :

```json
{
  "server_url": "http://127.0.0.1:8000",
  "exam_id": "EXAM-PYTHON-2026",
  "student_id": "etu001",
  "machine_id": "PC01",
  "workspace": "/home/exam/etu001/workspace",
  "execution_mode": "simulation"
}
```

Champs :

| Champ | Description |
|---|---|
| `server_url` | URL du backend FastAPI |
| `exam_id` | Identifiant de l’examen |
| `student_id` | Identifiant de l’étudiant |
| `machine_id` | Identifiant de la machine |
| `workspace` | Workspace cible |
| `execution_mode` | `simulation` ou `real` |

---

## Modes d’exécution

### Mode simulation

Le mode simulation permet de tester le client sans modifier le vrai système.

Workspace utilisé :

```text
exam-client/var/runtime/home/exam/<student_id>/workspace
```

### Mode réel NixOS

Le mode réel travaille directement sur le workspace système :

```text
/home/exam/<student_id>/workspace
```

Ce mode nécessite les droits administrateur pour préparer et réinitialiser le workspace.

---

## Démarrage d’un examen

Depuis `exam-client` :

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl nftables
python3 flows/start_exam.py
```

Étapes exécutées :

```text
FETCH
GENERATE_NIX
GENERATE_NETWORK_RULES
APPLY
```

Cette commande permet de :

- récupérer la configuration depuis le backend ;
- générer les fichiers NixOS ;
- générer les règles réseau ;
- préparer le workspace ;
- créer les fichiers `exam_metadata.json` et `exam_network_policy.json` ;
- envoyer les statuts d’avancement.

---

## Fin d’un examen

```bash
cd exam-client
python3 flows/finish_exam.py
```

Étapes exécutées :

```text
BACKUP
SUBMIT
RESET
```

Cette commande permet de :

- créer une archive ZIP du workspace ;
- envoyer l’archive au backend ;
- créer une preuve locale d’envoi ;
- réinitialiser le workspace uniquement après confirmation ;
- envoyer les statuts d’avancement.

---

## Démonstration complète

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl nftables
python3 flows/exam_runner.py
```

Étapes exécutées :

```text
FETCH
GENERATE_NIX
GENERATE_NETWORK_RULES
APPLY
STUDENT_WORK
BACKUP
SUBMIT
RESET
```

Résultat attendu :

```text
Chaîne complète exécutée avec succès.
```

---

## Génération NixOS

Le script :

```text
exam-client/generation/generate_nixos_config.py
```

génère :

```text
exam-client/var/generated/exam-configuration.nix
exam-client/var/generated/exam-metadata.json
exam-client/var/generated/network-policy.json
```

La configuration générée représente :

- l’utilisateur d’examen `exam` ;
- les paquets autorisés ;
- les droits sudo ;
- le workspace étudiant ;
- les métadonnées d’examen ;
- la politique réseau prévue.

---

## Génération réseau

Le script :

```text
exam-client/generation/generate_network_rules.py
```

génère :

```text
exam-client/var/generated/network-rules.nft
exam-client/var/generated/network-policy-report.txt
exam-client/var/generated/network-resolved-domains.json
```

Validation syntaxique nftables :

```bash
sudo -E env "PYTHONPATH=$PWD:${PYTHONPATH:-}" "$(which python3)" system/apply_network_rules.py --check
```

---

## Application réelle sur NixOS

Copier la configuration générée :

```bash
sudo cp ~/secure_exam/exam-client/var/generated/exam-configuration.nix /etc/nixos/exam-configuration.nix
```

Modifier :

```text
/etc/nixos/configuration.nix
```

Ajouter l’import :

```nix
imports =
  [
    ./hardware-configuration.nix
    ./exam-configuration.nix
  ];
```

Tester la configuration :

```bash
sudo nixos-rebuild test
```

Vérifications utiles :

```bash
getent passwd exam
sudo ls -la /home/exam/etu001/workspace
sudo -u exam -H bash -lc 'whoami; groups; sudo -n true; echo sudo_exit:$?'
```

Si `sudo_exit` est différent de `0`, l’utilisateur `exam` ne dispose pas de sudo.

---

## Politique réseau

Le prototype permet de représenter :

```text
Internet autorisé ou bloqué
Accès Educ autorisé ou bloqué
Domaines autorisés
```

Les fichiers générés sont :

```text
exam-client/var/generated/network-policy.json
exam-client/var/generated/network-rules.nft
/home/exam/<student_id>/workspace/exam_network_policy.json
```

L’application réseau stricte dépend de l’intégration avec l’infrastructure DSI :

- proxy ;
- DNS contrôlé ;
- passerelle réseau ;
- règles nftables ;
- listes blanches IP/domaines ;
- VLAN ou réseau d’examen.

---

# Fonctionnalités détaillées

## Création d’une configuration d’examen

L’enseignant peut définir :

- l’identifiant de l’examen ;
- l’identifiant de l’étudiant ;
- l’identifiant de la machine ;
- le workspace étudiant ;
- les paquets logiciels autorisés ;
- l’autorisation ou non de `sudo` ;
- l’autorisation ou non d’Internet ;
- l’autorisation ou non de l’accès Educ ;
- une liste de domaines autorisés.

Exemple :

```json
{
  "exam_id": "EXAM-PYTHON-2026",
  "student_id": "etu001",
  "machine_id": "PC01",
  "packages": ["gcc", "make", "nano", "python3"],
  "sudo": false,
  "internet": true,
  "educ_access": false,
  "allowed_domains": ["github.com"],
  "workspace": "/home/exam/etu001/workspace"
}
```

---

## Catalogue logiciel

Le catalogue logiciel permet de gérer les paquets disponibles pour les examens.

Fonctionnalités :

- affichage des paquets ;
- recherche de paquets ;
- ajout d’un paquet ;
- activation d’un paquet ;
- désactivation d’un paquet ;
- suppression d’un paquet ;
- filtrage des paquets actifs/inactifs ;
- validation côté frontend ;
- validation côté backend.

Les paquets désactivés ne peuvent pas être sélectionnés dans une nouvelle configuration.

---

## Dashboard enseignant

Le dashboard permet de :

- visualiser le nombre de configurations créées ;
- visualiser le nombre de rendus reçus ;
- visualiser le nombre de machines suivies ;
- créer une configuration d’examen ;
- consulter les configurations existantes ;
- télécharger une configuration JSON ;
- supprimer une configuration ;
- consulter les rendus étudiants ;
- grouper les rendus par examen ;
- filtrer les rendus par examen et date ;
- télécharger les archives ZIP ;
- supprimer un rendu ;
- consulter le dernier état d’une machine ;
- consulter l’historique d’une machine ;
- consulter et télécharger la configuration NixOS générée.

---

## Profil enseignant

La page profil permet à l’enseignant de :

- consulter ses informations ;
- modifier son nom, email, rôle, département et établissement ;
- importer une photo de profil ;
- consulter ses demandes support ;
- créer une demande support depuis son profil.

Les informations sont stockées dans SQLite.

La photo est stockée localement dans :

```text
backend/profile/
```

La base stocke uniquement le chemin du fichier.

---

## Support enseignant

Deux accès support existent :

```text
Page support publique
→ accessible depuis la page d’authentification

Support profil
→ accessible une fois connecté
```

Le formulaire contient :

- nom complet ;
- email ;
- type de problème ;
- message.

Lorsqu’une demande est envoyée :

1. le frontend transmet la demande au backend ;
2. le backend l’enregistre dans SQLite ;
3. le backend tente d’envoyer un e-mail via SMTP ;
4. la demande apparaît dans l’historique support du professeur concerné.

Les paramètres SMTP sont stockés dans `.env`.

---

# Sécurité

Le prototype inclut plusieurs mécanismes de sécurité :

- authentification par JWT ;
- hash des mots de passe avec Argon2 ;
- routes backend protégées ;
- séparation des données par enseignant ;
- filtrage des configurations par professeur ;
- filtrage des demandes support par professeur ;
- validation du catalogue logiciel ;
- refus des paquets non autorisés ;
- utilisateur système dédié `exam` ;
- contrôle des droits sudo ;
- refus d’un workspace réel hors de `/home/exam/` ;
- archive locale avant reset ;
- reset uniquement après confirmation d’envoi serveur ;
- exclusion des secrets et données locales du dépôt Git.

---

# Sauvegarde et reset

La logique de fin d’examen est sécurisée :

```text
workspace étudiant
→ archive ZIP locale
→ envoi au serveur
→ preuve d’envoi
→ reset du workspace
```

Le reset est annulé si :

- aucune archive locale n’existe ;
- aucune preuve d’envoi serveur n’existe ;
- l’archive locale la plus récente ne correspond pas à l’archive envoyée.

Cette logique évite la perte du travail étudiant.

---

# Fichiers non versionnés

Les éléments suivants ne doivent pas être publiés sur GitHub :

```text
backend/.env
backend/venv/
backend/database/*.db
backend/database/*.sqlite
backend/database/*.sqlite3
backend/submissions/
backend/profile/

frontend/node_modules/
frontend/.angular/
frontend/dist/

exam-client/config/client_settings.json
exam-client/var/
exam-client/backup/
exam-client/tools/
```

Le fichier `.env.example` est versionné pour documenter les variables nécessaires.

---

# Commandes utiles

## Ouvrir les ports sur NixOS

```bash
sudo nixos-firewall-tool open tcp 4200
sudo nixos-firewall-tool open tcp 8000
```

## Lancer le backend

```bash
cd backend
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Lancer le frontend

```bash
cd frontend
nix-shell -p nodejs_22
npx ng serve --host 0.0.0.0 --port 4200
```

## Lancer le client en simulation

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl nftables
python3 flows/exam_runner.py
```

## Démarrer uniquement l’examen

```bash
cd exam-client
python3 flows/start_exam.py
```

## Terminer uniquement l’examen

```bash
cd exam-client
python3 flows/finish_exam.py
```

## Vérifier le workspace réel

```bash
sudo ls -la /home/exam/etu001/workspace
```

## Vérifier la dernière archive

```bash
cd exam-client
ls -lt var/archives | head
unzip -l var/archives/<archive>.zip
```

## Vérifier le rapport de reset

```bash
cat exam-client/var/submitted/last_reset_report.json | python3 -m json.tool
```

---

# Scénario validé

Le scénario validé est le suivant :

```text
Configuration enseignant
→ récupération par la machine d’examen
→ génération NixOS
→ génération réseau
→ préparation du workspace
→ travail étudiant
→ archivage ZIP
→ envoi au backend
→ confirmation d’envoi
→ reset sécurisé du workspace
```

Exemple d’archive générée :

```text
EXAM-PYTHON-2026_etu001_PC01_YYYYMMDD_HHMMSS.zip
```

Contenu attendu :

```text
main.py
README.txt
exam_metadata.json
exam_network_policy.json
```

---

# Limites actuelles

Le prototype est fonctionnel, mais certaines parties restent à industrialiser :

- application réseau stricte à intégrer avec l’infrastructure réelle ;
- déploiement multi-machines non automatisé ;
- supervision multi-salles à compléter ;
- tests automatisés backend/frontend à ajouter ;
- application NixOS encore semi-manuelle via `nixos-rebuild test` ;
- intégration DSI à prévoir pour le réseau, le parc machines et les politiques système ;
- authentification institutionnelle à prévoir pour un usage réel.

---

# Perspectives d’amélioration

Évolutions possibles :

- appliquer réellement les règles réseau ;
- intégrer un proxy ou DNS contrôlé ;
- automatiser l’application NixOS complète ;
- ajouter une gestion multi-salles ;
- ajouter une interface administrateur DSI ;
- ajouter une signature ou un hash des archives ;
- ajouter une vérification d’intégrité côté serveur ;
- ajouter des tests backend et frontend ;
- améliorer le dashboard de supervision ;
- automatiser le déploiement sur plusieurs machines ;
- intégrer une authentification institutionnelle ;
- ajouter une gestion de rôles avancée ;
- ajouter une gestion de tokens machine.

---

# Documentation complémentaire

Une documentation dédiée à la démonstration réelle NixOS est disponible dans :

```text
docs/demo_nixos_reel.md
```

Elle décrit le scénario complet de validation sur machine NixOS réelle.

---

# Auteur

Projet développé par :

```text
Ayman CHERGUI
Étudiant ingénieur à l’ISEN
Email : ayman.chergui@isen.yncrea.fr
Site : https://aymanchergui.com
```

---

# Client / Référent

```text
Willy DUQUENOY
Directeur des Systèmes d’Information
Email : willy.duquenoy@yncrea.fr
Profil : https://isen-mediterranee.fr/membre/willy-duquenoy-2/
```

---

# Licence

Ce projet est réalisé dans un cadre académique pour le bureau d’étude ISEN 2026-2027.

Il est destiné à un usage pédagogique et démonstratif.

Toute mise en production nécessite une validation technique, réseau et sécurité par l’établissement.

---

# Conclusion

ISEN SecureExam démontre une chaîne complète de configuration et de supervision d’un environnement Linux d’examen.

Le prototype permet de passer d’une configuration créée par un enseignant à un environnement NixOS contrôlé, avec workspace étudiant, droits système, politique réseau, sauvegarde du rendu, dépôt serveur et remise à zéro sécurisée.

Le cœur technique du projet est fonctionnel et constitue une base solide pour une évolution vers un déploiement réel en environnement académique.
