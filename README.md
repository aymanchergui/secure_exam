# ISEN SecureExam

Plateforme web de configuration, de supervision et de validation d'environnements Linux d'examen.

---

## Présentation

**ISEN SecureExam** est un prototype fonctionnel permettant à un enseignant de préparer, contrôler et superviser un environnement Linux d'examen de manière sécurisée et reproductible.

Le projet répond au besoin suivant :

> permettre à un enseignant de configurer rapidement un environnement Linux d'examen contrôlé, sans intervention manuelle sur chaque machine, tout en garantissant la récupération des rendus étudiants et la remise à zéro de l'environnement après l'épreuve.

La plateforme permet notamment de :

- créer une configuration d'examen ;
- sélectionner les logiciels autorisés ;
- définir les droits administrateur de l'étudiant ;
- définir une politique réseau ;
- générer une configuration NixOS ;
- préparer un workspace étudiant ;
- suivre l'état des machines ;
- récupérer les rendus étudiants ;
- archiver les fichiers de travail ;
- envoyer les archives au serveur ;
- réinitialiser le workspace après confirmation d'envoi ;
- gérer un profil enseignant ;
- envoyer et consulter des demandes de support.

Le projet a été développé comme prototype académique dans le cadre d'un travail autour de la sécurisation et de la reproductibilité d'environnements Linux d'examen.

---

## État actuel du projet

Le prototype dispose aujourd'hui d'une chaîne fonctionnelle complète :

```text
Interface enseignant
→ création de configuration
→ récupération par la machine d'examen
→ génération NixOS
→ préparation du workspace réel
→ travail étudiant
→ archive ZIP
→ envoi au backend
→ confirmation de dépôt
→ reset sécurisé
```

Le projet prend en charge deux modes d'exécution côté client :

```text
simulation → workspace local simulé dans exam-client/runtime/
real       → workspace réel NixOS dans /home/exam/<student_id>/workspace
```

Le mode réel NixOS a été validé avec :

- création de l'utilisateur système `exam` ;
- création d'un workspace réel ;
- application des permissions Linux ;
- disponibilité des paquets autorisés ;
- désactivation de `sudo` pour l'utilisateur étudiant ;
- génération de fichiers de suivi ;
- sauvegarde réelle du workspace ;
- envoi de l'archive au backend ;
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
- Lucide Icons en local

### Client machine d'examen

- Python
- Scripts client
- Génération de configuration NixOS
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

## Architecture générale

Le projet repose sur trois blocs principaux :

```text
Frontend Angular
→ interface enseignant

Backend FastAPI
→ API REST, authentification, base de données, supervision, support

Exam-client Python
→ récupération de configuration, génération NixOS, application, archive, dépôt, reset
```

Structure principale :

```text
secure_exam/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── secure_exam.db          # généré localement, non versionné
│   ├── profile/                    # photos de profil locales, non versionnées
│   └── submissions/                # archives ZIP reçues, non versionnées
│
├── frontend/
│   ├── angular.json
│   ├── package.json
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
│               ├── profile/
│               └── support/
│
├── exam-client/
│   ├── client_settings.json
│   ├── client_settings.py
│   ├── fetch_config.py
│   ├── apply_config.py
│   ├── generate_nixos_config.py
│   ├── start_exam.py
│   ├── backup_workspace.py
│   ├── submit_archive.py
│   ├── reset_exam.py
│   ├── finish_exam.py
│   ├── status_reporter.py
│   ├── logger.py
│   ├── simulate_student_work.py
│   └── demo_full.sh
│
└── docs/
    └── demo_nixos_reel.md
```

Les fichiers générés, les données locales et les secrets sont exclus du dépôt Git.

---

## Fonctionnalités principales

### 1. Authentification enseignant

L'enseignant peut se connecter à une interface protégée par JWT.

Après connexion, le frontend stocke le token JWT et l'utilise dans les requêtes protégées avec l'en-tête suivant :

```text
Authorization: Bearer <token>
```

Les routes sensibles du backend nécessitent ce token.

Les identifiants de test sont chargés depuis :

```text
backend/.env
```

---

### 2. Dashboard enseignant

Le dashboard permet de :

- visualiser le nombre de configurations créées ;
- visualiser le nombre de rendus reçus ;
- visualiser le nombre de machines suivies ;
- créer une configuration d'examen ;
- consulter les configurations existantes ;
- télécharger une configuration JSON ;
- supprimer une configuration ;
- consulter les rendus étudiants ;
- télécharger les archives ZIP ;
- supprimer un rendu ;
- consulter le dernier état d'une machine ;
- consulter l'historique d'une machine ;
- accéder aux informations de génération NixOS.

---

### 3. Création d'une configuration d'examen

L'enseignant peut définir :

- l'identifiant de l'examen ;
- l'identifiant de l'étudiant ;
- l'identifiant de la machine ;
- le workspace étudiant ;
- les paquets logiciels autorisés ;
- l'autorisation ou non de `sudo` ;
- l'autorisation ou non d'Internet ;
- l'autorisation ou non de l'accès Educ ;
- une liste de domaines autorisés.

Exemple de configuration :

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

La configuration est enregistrée dans SQLite et peut ensuite être récupérée par le client machine via l'API.

---

### 4. Catalogue logiciel

Le catalogue logiciel permet de gérer les paquets disponibles pour les examens.

Fonctionnalités disponibles :

- affichage des paquets ;
- ajout d'un paquet ;
- activation d'un paquet ;
- désactivation d'un paquet ;
- filtrage des paquets actifs ou inactifs ;
- validation côté client et côté backend.

Les paquets désactivés ne peuvent pas être sélectionnés dans une nouvelle configuration.

---

### 5. Profil enseignant

Une page profil permet à l'enseignant de :

- consulter ses informations ;
- modifier son nom, email, rôle, département et établissement ;
- importer une photo de profil ;
- consulter les demandes de support envoyées.

Les informations sont stockées dans SQLite.

La photo est stockée localement dans :

```text
backend/profile/
```

La base de données stocke uniquement le chemin du fichier.

---

### 6. Support enseignant

La page support permet d'envoyer une demande en cas de problème.

Le formulaire contient :

- nom complet ;
- email ;
- type de problème ;
- message.

Lorsqu'une demande est envoyée :

1. le frontend transmet la demande au backend ;
2. le backend l'enregistre dans SQLite ;
3. le backend tente d'envoyer un e-mail via SMTP ;
4. la demande apparaît dans la page profil enseignant.

Les paramètres SMTP sont stockés dans le fichier `.env`.

---

## Backend FastAPI

Le backend fournit une API REST pour :

- l'authentification ;
- la gestion des configurations ;
- la gestion du catalogue logiciel ;
- la réception des rendus ;
- la supervision des machines ;
- la gestion des profils enseignants ;
- la gestion des demandes de support.

Routes principales :

```text
GET    /
GET    /health

POST   /auth/login
GET    /auth/me

GET    /dashboard

GET    /packages
POST   /packages
PATCH  /packages/{package_id}/enable
PATCH  /packages/{package_id}/disable

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

POST   /support-requests
GET    /support-requests-list
```

---

## Base de données SQLite

La base SQLite est créée automatiquement au lancement du backend :

```text
backend/database/secure_exam.db
```

Elle contient notamment les tables suivantes :

```text
teachers
teacher_profile
package_catalog
support_requests
exam_configs
submissions
machine_status
machine_status_history
```

Elle stocke :

- les comptes enseignants ;
- les profils enseignants ;
- le catalogue logiciel ;
- les demandes de support ;
- les configurations d'examen ;
- les métadonnées des rendus ;
- le dernier état des machines ;
- l'historique des machines.

Les fichiers volumineux ne sont pas stockés directement dans SQLite.

Ils restent sur le système de fichiers :

```text
backend/submissions/     → archives ZIP réelles des rendus étudiants
backend/profile/         → photos de profil
exam-client/generated/   → fichiers générés côté client
```

La base `secure_exam.db` est une donnée locale. Elle ne doit pas être publiée sur GitHub.

---

## Variables d'environnement

Le backend utilise un fichier `.env` :

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

Exemple de variables attendues :

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

## Installation du frontend

Depuis le dossier `frontend` :

```bash
cd frontend
npm install
ng serve
```

Sous Windows, si PowerShell bloque `ng`, utiliser :

```powershell
ng.cmd serve
```

L'interface est disponible sur :

```text
http://localhost:4200
```

---

## Client machine d'examen

Le client machine se trouve dans :

```text
exam-client/
```

Il permet de :

- récupérer la configuration depuis le backend ;
- générer une configuration NixOS ;
- préparer le workspace étudiant ;
- créer les fichiers de suivi ;
- sauvegarder le workspace ;
- envoyer l'archive au backend ;
- vérifier l'envoi ;
- réinitialiser le workspace ;
- envoyer les statuts d'avancement au backend.

---

## Configuration du client

Le fichier de configuration du client est :

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

Champs :

| Champ | Description |
|---|---|
| `server_url` | URL du backend FastAPI |
| `exam_id` | Identifiant de l'examen |
| `student_id` | Identifiant de l'étudiant |
| `machine_id` | Identifiant de la machine |
| `execution_mode` | `simulation` ou `real` |

---

## Modes d'exécution

### Mode simulation

Le mode simulation permet de tester le client sans modifier le vrai système.

Workspace utilisé :

```text
exam-client/runtime/home/exam/<student_id>/workspace
```

### Mode réel NixOS

Le mode réel travaille directement sur le workspace système :

```text
/home/exam/<student_id>/workspace
```

Ce mode nécessite les droits administrateur pour préparer et réinitialiser le workspace.

---

## Démarrage d'un examen

Depuis `exam-client` :

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl
```

Lancer le démarrage :

```bash
PYTHON_BIN="$(which python3)"
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" start_exam.py
```

Cette commande effectue :

```text
FETCH
GENERATE_NIX
APPLY
```

Elle permet de :

- récupérer la configuration depuis le backend ;
- générer les fichiers NixOS ;
- préparer le workspace réel ;
- créer les fichiers `exam_metadata.json` et `exam_network_policy.json` ;
- envoyer le statut `EXAM_READY`.

---

## Fin d'un examen

Depuis `exam-client` :

```bash
PYTHON_BIN="$(which python3)"
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" finish_exam.py
```

Cette commande effectue :

```text
BACKUP
SUBMIT
RESET
```

Elle permet de :

- créer une archive ZIP du workspace ;
- envoyer l'archive au backend ;
- créer une preuve locale d'envoi ;
- réinitialiser le workspace uniquement après confirmation ;
- envoyer le statut `EXAM_FINISHED`.

---

## Génération NixOS

Le script suivant :

```text
exam-client/generate_nixos_config.py
```

génère automatiquement :

```text
exam-client/generated/exam-configuration.nix
exam-client/generated/exam-metadata.json
exam-client/generated/network-policy.json
```

La configuration générée représente :

- l'utilisateur d'examen `exam` ;
- les paquets autorisés ;
- les droits sudo de l'étudiant ;
- le workspace étudiant ;
- les métadonnées d'examen ;
- la politique réseau prévue.

---

## Application réelle sur NixOS

Copier la configuration générée :

```bash
sudo cp ~/secure_exam/exam-client/generated/exam-configuration.nix /etc/nixos/exam-configuration.nix
```

Modifier :

```text
/etc/nixos/configuration.nix
```

Ajouter l'import :

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

Si `sudo_exit` est différent de `0`, l'utilisateur `exam` ne dispose pas de sudo.

---

## Script de démonstration complet

Le script :

```text
exam-client/demo_full.sh
```

permet de lancer une démonstration complète du cycle réel.

### Terminal 1 : backend

```bash
cd backend
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 : démonstration

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl
chmod +x demo_full.sh
./demo_full.sh
```

Le script effectue automatiquement :

1. vérification du backend ;
2. vérification du module `requests` ;
3. démarrage réel de l'examen ;
4. simulation du travail étudiant ;
5. sauvegarde du workspace ;
6. envoi de l'archive au backend ;
7. reset du workspace ;
8. vérification de l'archive ;
9. vérification des soumissions côté backend.

Résultat attendu :

```text
Démonstration terminée avec succès.
```

---

## Scénario validé

Le scénario réel validé est le suivant :

```text
Configuration enseignant
→ récupération par la machine d'examen
→ génération NixOS
→ préparation du workspace réel
→ travail étudiant
→ archivage ZIP
→ envoi au backend
→ confirmation d'envoi
→ reset sécurisé du workspace
```

Exemple d'archive générée :

```text
EXAM-PYTHON-2026_etu001_PC01_YYYYMMDD_HHMMSS.zip
```

Contenu attendu :

```text
main.py
exam_metadata.json
exam_network_policy.json
```

---

## Politique réseau

Le prototype permet de représenter :

```text
Internet autorisé ou bloqué
Accès Educ autorisé ou bloqué
Domaines autorisés
```

La politique est générée dans :

```text
generated/network-policy.json
/etc/exam/network-policy.json
/home/exam/<student_id>/workspace/exam_network_policy.json
```

Le filtrage réseau strict par domaine n'est pas encore appliqué automatiquement.

Une version cible pourrait s'appuyer sur :

- un proxy ;
- un DNS contrôlé ;
- une passerelle réseau ;
- des règles `nftables` basées sur des IP validées ;
- une intégration avec l'infrastructure réseau de l'établissement.

---

## Sécurité

Le prototype inclut plusieurs mécanismes de sécurité :

- authentification par JWT ;
- hash des mots de passe avec Argon2 ;
- routes backend protégées ;
- séparation des données par enseignant ;
- validation du catalogue logiciel ;
- refus des paquets non autorisés ;
- utilisateur système dédié `exam` ;
- contrôle des droits sudo ;
- refus d'un workspace réel hors de `/home/exam/` ;
- archive locale avant reset ;
- reset uniquement après confirmation d'envoi serveur ;
- exclusion des secrets et données locales du dépôt Git.

---

## Sauvegarde et reset

La logique de fin d'examen est sécurisée :

```text
workspace étudiant
→ archive ZIP locale
→ envoi au serveur
→ preuve d'envoi
→ reset du workspace
```

Le reset est annulé si :

- aucune archive locale n'existe ;
- aucune preuve d'envoi serveur n'existe ;
- l'archive locale la plus récente ne correspond pas à l'archive envoyée.

Cette logique évite la perte du travail étudiant.

---

## Fichiers non versionnés

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

exam-client/archives/
exam-client/downloaded/
exam-client/generated/
exam-client/logs/
exam-client/runtime/
exam-client/submitted/
```

Le fichier `.env.example` est versionné pour documenter les variables nécessaires.

---

## Limites actuelles

Le prototype est fonctionnel, mais certaines parties restent à industrialiser :

- application réseau stricte encore à intégrer ;
- déploiement multi-machines non automatisé ;
- supervision multi-salles à compléter ;
- pas encore de tests automatisés complets ;
- application NixOS encore semi-manuelle via `nixos-rebuild test` ;
- intégration DSI à prévoir pour le réseau, le parc machines et les politiques système.

---

## Perspectives d'amélioration

Évolutions possibles :

- appliquer réellement les règles réseau ;
- intégrer un proxy ou DNS contrôlé ;
- automatiser l'application NixOS complète ;
- ajouter une gestion multi-salles ;
- ajouter une interface administrateur DSI ;
- ajouter une signature ou un hash des archives ;
- ajouter une vérification d'intégrité côté serveur ;
- ajouter des tests backend et frontend ;
- améliorer le dashboard de supervision ;
- automatiser le déploiement sur plusieurs machines ;
- intégrer une authentification institutionnelle.

---

## Commandes utiles
sudo nixos-firewall-tool open tcp 4200
sudo nixos-firewall-tool open tcp 8000
### Lancer le backend

```bash
cd backend
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Lancer le frontend

```bash
cd frontend
ng serve
```

### Lancer le client en mode réel

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl
PYTHON_BIN="$(which python3)"
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" start_exam.py
```

### Terminer l'examen

```bash
PYTHON_BIN="$(which python3)"
sudo -E env "PYTHONPATH=$PYTHONPATH" "$PYTHON_BIN" finish_exam.py
```

### Lancer la démo complète

```bash
cd exam-client
nix-shell -p 'python312.withPackages (ps: [ ps.requests ])' zip unzip curl
./demo_full.sh
```

### Vérifier le workspace réel

```bash
sudo ls -la /home/exam/etu001/workspace
```

### Vérifier la dernière archive

```bash
LATEST=$(ls -t archives/EXAM-PYTHON-2026_etu001_PC01_*.zip | head -n 1)
echo "$LATEST"
unzip -l "$LATEST"
```

---

## Documentation complémentaire

Une documentation dédiée à la démonstration réelle NixOS est disponible dans :

```text
docs/demo_nixos_reel.md
```

Elle décrit le scénario complet de validation sur machine NixOS réelle.

---

## Auteur

Projet développé par **Ayman Chergui**.

---

## Licence

ayman chergui . ayman.chergui@isen.yncrea.fr

---

## Conclusion

**ISEN SecureExam** démontre une chaîne complète de configuration et de supervision d'un environnement Linux d'examen.

Le prototype permet de passer d'une configuration créée par un enseignant à un environnement NixOS réel, avec workspace étudiant, droits contrôlés, sauvegarde du rendu, dépôt serveur et remise à zéro sécurisée.

Le cœur technique du projet est fonctionnel et constitue une base solide pour une évolution vers un déploiement réel en environnement académique.


# SecureExam Client

Client machine pour récupérer une configuration d'examen, préparer l'environnement Linux/NixOS, sauvegarder le rendu étudiant, l'envoyer au backend et remettre le poste dans un état propre.

## Structure

- `api/` : échanges avec le backend SecureExam.
- `generation/` : génération des fichiers NixOS et réseau.
- `system/` : application système, réseau et reset.
- `workspace/` : sauvegarde et simulation du travail étudiant.
- `core/` : fonctions communes, logs.
- `config/` : configuration locale du client.
- `flows/` : scénarios complets de démarrage et fin d'examen.
- `var/` : fichiers générés localement, archives, logs, runtime et preuves.
- `tools/` : scripts temporaires ou outils de maintenance.
- `backup/` : sauvegardes locales non versionnées.


# Frontend

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 22.1.3.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
