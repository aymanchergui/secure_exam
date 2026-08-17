# ISEN SecureExam

Plateforme web de configuration et de supervision d'environnements Linux d'examen.

## Présentation

**ISEN SecureExam** est un prototype de plateforme permettant à un enseignant de préparer, contrôler et superviser un environnement Linux d'examen de manière reproductible et sécurisée.

L'objectif est de fournir une interface simple permettant de :

- créer une configuration d'examen ;
- sélectionner les paquets logiciels autorisés ;
- définir les droits administrateur de l'étudiant ;
- contrôler l'accès réseau ;
- générer une configuration exploitable par une machine Linux/NixOS ;
- suivre l'état des machines d'examen ;
- récupérer les rendus étudiants ;
- gérer un profil enseignant ;
- envoyer et consulter des demandes de support ;
- remettre l'environnement d'examen dans un état propre après l'épreuve.

Ce projet a été développé comme prototype fonctionnel dans le cadre d'un projet académique autour de la sécurisation et de la reproductibilité d'environnements Linux d'examen.

---

## Architecture générale

Le projet repose sur trois blocs principaux :

```text
Frontend Angular
→ interface enseignant

Backend FastAPI
→ API REST, authentification, stockage, envoi mail, supervision

Exam-client Python
→ récupération de configuration, génération NixOS, sauvegarde, rendu, reset
````

Structure du projet :

```text
secure_exam/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── configs/
│   ├── submissions/
│   ├── status/
│   ├── status_history/
│   ├── support_requests/
│   └── profile/
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
└── exam-client/
    ├── client_settings.json
    ├── fetch_config.py
    ├── apply_config.py
    ├── generate_nixos_config.py
    ├── backup_workspace.py
    ├── submit_archive.py
    ├── reset_exam.py
    ├── start_exam.py
    ├── finish_exam.py
    └── simulate_student_work.py
```

---

## Technologies utilisées

### Backend

* Python
* FastAPI
* Uvicorn
* JWT pour l'authentification
* PyJWT
* pwdlib / Argon2 pour le hash du mot de passe
* SMTP pour l'envoi automatique des demandes de support
* Stockage local JSON / fichiers pour la version prototype

### Frontend

* Angular
* TypeScript
* HTML
* CSS
* Angular HttpClient
* Lucide Icons en local

### Client machine d'examen

* Python
* Scripts de simulation machine
* Génération de configuration NixOS
* Sauvegarde ZIP
* Upload HTTP vers le backend
* Reset logique du workspace

### Système cible

* Linux
* NixOS
* nftables / firewall
* Politique réseau contrôlée
* Environnement reproductible

---

## Fonctionnalités principales

### Authentification enseignant

L'enseignant peut se connecter à une interface protégée par JWT.

Identifiants de test :

```text
Identifiant : prof
Mot de passe : isen-prof
```

Après connexion, le frontend stocke le token JWT et l'utilise dans les requêtes protégées avec l'en-tête :

```text
Authorization: Bearer <token>
```

---

### Dashboard enseignant

Le tableau de bord permet de :

* visualiser le nombre de configurations générées ;
* visualiser le nombre de rendus reçus ;
* visualiser le nombre de machines suivies ;
* créer une configuration d'examen ;
* consulter les configurations existantes ;
* télécharger les configurations JSON ;
* consulter les détails d'une configuration ;
* supprimer une configuration ;
* consulter les rendus étudiants ;
* télécharger les archives ZIP ;
* supprimer un rendu ;
* suivre l'état des machines ;
* consulter l'historique d'une machine ;
* consulter et télécharger la configuration NixOS générée.

---

### Création d'une configuration d'examen

L'enseignant peut définir :

* l'identifiant de l'examen ;
* l'identifiant de l'étudiant ;
* l'identifiant de la machine ;
* le workspace étudiant ;
* les paquets autorisés ;
* l'autorisation ou non de `sudo` ;
* l'autorisation ou non d'Internet ;
* l'autorisation ou non de l'accès Educ ;
* une liste de domaines autorisés.

Exemple de configuration générée :

```json
{
  "exam_id": "EXAM-PYTHON-2026",
  "student_id": "etu001",
  "machine_id": "PC01",
  "packages": ["python3", "gcc", "make"],
  "sudo": false,
  "internet": false,
  "educ_access": true,
  "allowed_domains": ["educ.isen.fr"],
  "workspace": "/home/exam/etu001/workspace"
}
```

---

### Profil professeur

Une page profil permet à l'enseignant de :

* consulter ses informations ;
* modifier son nom, son email, son rôle, son département et son établissement ;
* importer une photo de profil ;
* consulter les demandes de support envoyées depuis la page support.

Les données du profil sont stockées localement côté backend dans le prototype.

---

### Support enseignant

La page support permet d'envoyer une demande en cas de problème de connexion ou d'accès à la plateforme.

Le formulaire contient :

* nom complet ;
* email ;
* type de problème ;
* message.

Lorsqu'une demande est envoyée :

1. le frontend Angular envoie la demande au backend ;
2. le backend enregistre la demande ;
3. le backend envoie automatiquement un e-mail via SMTP ;
4. la demande apparaît dans la page profil professeur.

Le système SMTP utilise des variables d'environnement afin de ne pas exposer les identifiants dans le code.

Exemple de fichier `.env` côté backend :

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=example@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=example@gmail.com
SUPPORT_TO_EMAIL=support@example.com
```

Le fichier `.env` ne doit jamais être publié sur GitHub.

---

## Backend FastAPI

Le backend fournit une API REST permettant de gérer :

* l'authentification enseignant ;
* les configurations d'examen ;
* les rendus étudiants ;
* les statuts machines ;
* l'historique machines ;
* la configuration NixOS générée ;
* le profil professeur ;
* les demandes de support ;
* l'envoi d'e-mails SMTP.

Routes principales :

```text
GET  /
GET  /health

POST /auth/login
GET  /auth/me

GET  /dashboard

POST /configs
GET  /configs-list
GET  /configs/{exam_id}/{student_id}/{machine_id}
GET  /configs-file/{filename}
GET  /configs/{filename}/download
DELETE /configs/{filename}

POST /submissions
GET  /submissions-list
GET  /submissions/{filename}/download
DELETE /submissions/{filename}

POST /machine-status
GET  /machine-status-list
GET  /machine-status/{exam_id}/{student_id}/{machine_id}
GET  /machine-status-history/{exam_id}/{student_id}/{machine_id}

GET  /nixos-config
GET  /nixos-config/download

GET  /teacher-profile
PUT  /teacher-profile
POST /teacher-profile/photo
GET  /teacher-profile/photo

POST /support-requests
GET  /support-requests-list
```

---

## Client machine d'examen

Le client machine est un ensemble de scripts Python simulant le comportement d'une machine d'examen.

Il permet de :

* récupérer une configuration depuis le serveur ;
* appliquer la configuration en simulation ;
* générer une configuration NixOS ;
* créer un workspace étudiant ;
* simuler un travail étudiant ;
* créer une archive ZIP du workspace ;
* envoyer l'archive au serveur ;
* vérifier que l'envoi a réussi ;
* réinitialiser le workspace ;
* envoyer les statuts d'avancement au backend.

Fichier de configuration du client :

```text
exam-client/client_settings.json
```

Exemple :

```json
{
  "server_url": "http://127.0.0.1:8000",
  "exam_id": "EXAM-PYTHON-2026",
  "student_id": "etu001",
  "machine_id": "PC01"
}
```

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

La configuration NixOS générée représente :

* l'utilisateur d'examen ;
* les droits `sudo` ;
* les paquets autorisés ;
* le workspace étudiant ;
* l'activation du firewall ;
* l'activation de nftables ;
* les métadonnées de l'examen ;
* la politique réseau prévue.

Logique globale :

```text
Choix enseignant dans Angular
→ configuration JSON
→ récupération par exam-client
→ génération automatique NixOS
→ fichier exploitable sur une machine Linux/NixOS
```

---

## Politique réseau

Le prototype permet de représenter trois niveaux de contrôle réseau :

```text
Internet autorisé ou bloqué
Accès Educ autorisé ou bloqué
Domaines autorisés
```

Dans la version actuelle, la politique réseau est générée et documentée, mais elle n'est pas encore appliquée réellement au système.

Dans une version cible, l'application effective pourrait s'appuyer sur :

* nftables ;
* iptables ;
* un proxy ;
* un DNS contrôlé ;
* une passerelle réseau administrée par l'établissement ;
* une liste blanche IP/domaine validée par la DSI.

Le filtrage par nom de domaine nécessite une solution adaptée, car un pare-feu système filtre principalement par IP, port et interface.

---

## Sauvegarde, rendu et reset

Le client suit une logique sécurisée :

```text
workspace étudiant
→ archive ZIP locale
→ envoi au serveur
→ preuve d'envoi
→ reset du workspace
```

Le reset n'est exécuté que si :

* une archive locale existe ;
* l'archive a bien été envoyée au serveur ;
* la preuve d'envoi correspond à la dernière archive.

Cette logique évite de supprimer le travail étudiant avant la sauvegarde et l'envoi du rendu.

---

## Installation et lancement

### 1. Cloner le projet

```powershell
git clone https://github.com/aymanchergui/secure_exam.git
cd secure_exam
```

---

### 2. Lancer le backend

Créer et activer un environnement virtuel Python :

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Installer les dépendances :

```powershell
python -m pip install -r requirements.txt
```

Créer un fichier `.env` si l'envoi SMTP est utilisé :

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=example@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=example@gmail.com
SUPPORT_TO_EMAIL=support@example.com
```

Lancer le serveur :

```powershell
python -m uvicorn main:app --reload
```

Le backend est disponible sur :

```text
http://127.0.0.1:8000
```

Documentation Swagger :

```text
http://127.0.0.1:8000/docs
```

---

### 3. Lancer le frontend Angular

Dans un deuxième terminal :

```powershell
cd frontend
npm install
ng.cmd serve
```

L'interface est disponible sur :

```text
http://localhost:4200
```

---

### 4. Lancer le client machine

Dans un troisième terminal :

```powershell
cd exam-client
python start_exam.py
python simulate_student_work.py
python finish_exam.py
```

---

## Scénario de démonstration

1. Lancer le backend FastAPI.
2. Lancer le frontend Angular.
3. Se connecter avec les identifiants de test.
4. Créer une configuration d'examen.
5. Lancer `python start_exam.py` côté `exam-client`.
6. Vérifier la génération NixOS dans le dashboard.
7. Lancer `python simulate_student_work.py`.
8. Lancer `python finish_exam.py`.
9. Vérifier le rendu ZIP dans Angular.
10. Consulter l'état machine et l'historique.
11. Tester la page support.
12. Consulter les demandes support depuis la page profil.

---

## Stockage actuel des données

Dans cette version prototype, la persistance est assurée par un stockage local sous forme de fichiers JSON, ZIP et images.

```text
backend/configs/              → configurations d'examen
backend/submissions/          → archives ZIP reçues
backend/status/               → dernier état machine
backend/status_history/       → historique machine
backend/support_requests/     → demandes support
backend/profile/              → profil professeur et photo
exam-client/generated/        → fichiers NixOS générés
exam-client/archives/         → archives locales du client
exam-client/runtime/          → workspace simulé
exam-client/logs/             → logs du client
```

Ces dossiers sont exclus du dépôt Git lorsqu'ils contiennent des données générées ou sensibles.

Une évolution prévue consiste à migrer la persistance vers une base de données SQLite, puis éventuellement PostgreSQL selon les besoins du déploiement.

---

## Sécurité

La version actuelle inclut déjà :

* authentification enseignant par JWT ;
* hash du mot de passe avec Argon2 ;
* routes protégées côté backend ;
* token transmis dans l'en-tête `Authorization` ;
* séparation frontend / backend / client machine ;
* stockage SMTP via variables d'environnement ;
* exclusion du fichier `.env` du dépôt Git ;
* validation des paquets autorisés ;
* vérification de l'envoi du rendu avant reset.

Points à renforcer pour une version production :

* sortir la clé JWT du code source ;
* gérer plusieurs comptes enseignants ;
* ajouter des rôles : enseignant, administrateur, surveillant ;
* utiliser une base de données ;
* ajouter une expiration/rotation plus avancée des tokens ;
* sécuriser davantage l'upload de fichiers ;
* appliquer réellement les règles réseau sur Linux/NixOS ;
* intégrer une authentification institutionnelle si nécessaire.

---

## Partie réalisée et partie simulée

### Réalisé dans le prototype

* Interface Angular moderne ;
* authentification JWT ;
* dashboard enseignant ;
* création de configurations ;
* validation des paquets ;
* génération de configuration JSON ;
* client Python de récupération ;
* génération de configuration NixOS ;
* sauvegarde ZIP ;
* upload des rendus ;
* suivi d'état machine ;
* historique machine ;
* page support ;
* envoi automatique d'e-mail SMTP ;
* profil professeur ;
* modification de photo de profil ;
* consultation des demandes support ;
* téléchargement de fichiers.

### Simulé dans le prototype actuel

* installation réelle des paquets système ;
* modification réelle des droits Linux ;
* application réelle des règles réseau ;
* reset complet d'une machine NixOS ;
* déploiement sur un parc physique ;
* exécution réelle de `nixos-rebuild`.

Le prototype fonctionne sous Windows pour le développement, mais la cible finale reste une machine Linux/NixOS contrôlée par l'établissement.

---

## Limites actuelles

* stockage local fichier au lieu d'une base de données ;
* un seul compte enseignant de test ;
* clé JWT encore définie dans le code ;
* politique réseau générée mais non appliquée réellement ;
* configuration NixOS générée mais non encore appliquée avec `nixos-rebuild`;
* reset limité à un workspace simulé ;
* absence de tests automatisés ;
* déploiement multi-machines non encore validé physiquement.

---

## Évolutions prévues

* migration vers SQLite ;
* gestion multi-utilisateurs ;
* gestion des rôles : enseignant, administrateur, surveillant ;
* amélioration de la sécurité JWT ;
* externalisation complète des secrets ;
* application réelle de la configuration NixOS ;
* intégration d'un cache local de paquets ;
* mise en place d'un vrai filtrage réseau ;
* ajout de tests backend et frontend ;
* amélioration des logs ;
* export de rapports d'examen ;
* reset complet par image système, snapshot ou profil NixOS ;
* déploiement sur plusieurs machines d'examen.

---

## Auteur

Projet développé par **Ayman Chergui**.

---

## Licence

Projet académique / prototype de démonstration.

---

## Conclusion

ISEN SecureExam valide une chaîne fonctionnelle complète pour la configuration, le suivi et la récupération de rendus dans un environnement Linux d'examen.

Le prototype démontre :

* une interface enseignant sécurisée ;
* une API backend protégée ;
* une génération automatique de configuration ;
* une logique de supervision machine ;
* une génération NixOS ;
* une sauvegarde sécurisée des rendus ;
* un module support avec notification e-mail ;
* une base solide pour une évolution vers un déploiement réel.
