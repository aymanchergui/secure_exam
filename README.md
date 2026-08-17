# Plateforme de configuration d'environnements Linux d'examen

## 1. Présentation du projet

Ce projet est un prototype de plateforme permettant à un enseignant de préparer un environnement Linux d'examen de manière contrôlée, reproductible et sécurisée.

L'objectif est de permettre à un enseignant de :

- se connecter à une interface web sécurisée ;
- créer une configuration d'examen ;
- choisir les paquets logiciels autorisés ;
- définir les droits administrateur de l'étudiant ;
- définir une politique réseau ;
- générer une configuration exploitable par une machine Linux/NixOS ;
- suivre l'état des machines d'examen ;
- récupérer les rendus étudiants ;
- remettre l'environnement d'examen dans un état propre après l'épreuve.

Le projet repose sur une architecture en trois parties :

```text
Frontend Angular
→ interface enseignant

Backend FastAPI
→ API, authentification, stockage des configurations, rendus et statuts

Exam-client Python
→ récupération de la configuration, génération NixOS, sauvegarde, envoi et reset
````

---

## 2. Architecture générale

```text
exam_platform/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── configs/
│   ├── submissions/
│   ├── status/
│   └── status_history/
│
├── frontend/
│   └── src/app/
│       ├── app.ts
│       ├── app.html
│       ├── app.css
│       └── app.config.ts
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
    ├── generated/
    ├── runtime/
    ├── archives/
    ├── submitted/
    └── logs/
```

---

## 3. Technologies utilisées

### Backend

* Python
* FastAPI
* Uvicorn
* JWT pour l'authentification
* PyJWT
* pwdlib / Argon2 pour le hash du mot de passe

### Frontend

* Angular
* TypeScript
* HTML / CSS
* HttpClient Angular

### Client machine d'examen

* Python
* Scripts de simulation machine
* Génération de configuration NixOS
* Sauvegarde ZIP
* Upload HTTP vers le backend

### Système cible

* Linux
* NixOS
* Pare-feu / nftables
* Politique réseau contrôlée
* Environnement reproductible

---

## 4. Fonctionnalités réalisées

### Interface enseignant

L'enseignant peut :

* se connecter avec un identifiant et un mot de passe ;
* accéder à un tableau de bord protégé ;
* créer une configuration d'examen ;
* sélectionner les paquets autorisés ;
* choisir si sudo est autorisé ;
* choisir si Internet est autorisé ;
* choisir si l'accès Educ est autorisé ;
* définir une liste de domaines autorisés ;
* consulter les configurations générées ;
* télécharger les configurations JSON ;
* consulter et télécharger la configuration NixOS générée ;
* consulter l'état des machines ;
* consulter l'historique d'une machine ;
* télécharger les rendus étudiants ;
* supprimer une configuration ou un rendu ;
* se déconnecter.

### Backend FastAPI

Le backend fournit :

* une API REST ;
* une authentification enseignant par JWT ;
* une protection des routes administratives ;
* la création de configurations JSON ;
* la validation des paquets autorisés ;
* le stockage des configurations ;
* le stockage des rendus étudiants ;
* le stockage du dernier état machine ;
* le stockage de l'historique machine ;
* le téléchargement des fichiers protégés.

### Client machine d'examen

Le client machine permet de :

* récupérer la configuration depuis le serveur ;
* appliquer la configuration en simulation ;
* générer une configuration NixOS ;
* créer un workspace étudiant ;
* simuler un travail étudiant ;
* sauvegarder le workspace dans une archive ZIP ;
* envoyer l'archive au serveur ;
* vérifier que l'archive a bien été envoyée ;
* remettre le workspace dans un état propre ;
* envoyer les statuts d'avancement au backend.

---

## 5. Authentification

L'authentification enseignant repose sur un système JWT.

Le backend expose une route :

```text
POST /auth/login
```

L'enseignant envoie :

```json
{
  "username": "prof",
  "password": "isen-prof"
}
```

Le serveur vérifie les identifiants, puis renvoie un jeton JWT :

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

Le frontend Angular stocke ce token et l'utilise ensuite dans les requêtes protégées avec l'en-tête HTTP :

```text
Authorization: Bearer <token>
```

Les routes sensibles comme le tableau de bord, la création de configuration, la suppression et les téléchargements protégés nécessitent ce token.

Pour un environnement de production, la clé secrète JWT et les identifiants ne doivent pas être écrits directement dans le code. Ils doivent être placés dans des variables d'environnement ou dans un système sécurisé de gestion de secrets.

---

## 6. Lancement du backend

Depuis un terminal PowerShell :

```powershell
cd C:\Users\lione\Desktop\exam_platform\backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Le backend est disponible sur :

```text
http://127.0.0.1:8000
```

La documentation Swagger est disponible sur :

```text
http://127.0.0.1:8000/docs
```

---

## 7. Lancement du frontend Angular

Depuis un deuxième terminal PowerShell :

```powershell
cd C:\Users\lione\Desktop\exam_platform\frontend
ng.cmd serve
```

L'interface Angular est disponible sur :

```text
http://localhost:4200
```

Identifiants de test :

```text
Identifiant : prof
Mot de passe : isen-prof
```

---

## 8. Configuration du client machine

Le fichier de configuration du client se trouve ici :

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

Ce fichier indique au client machine :

* l'adresse du serveur ;
* l'identifiant de l'examen ;
* l'identifiant de l'étudiant ;
* l'identifiant de la machine.

---

## 9. Scénario complet de démonstration

### Étape 1 — Lancer le backend

```powershell
cd C:\Users\lione\Desktop\exam_platform\backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

### Étape 2 — Lancer Angular

```powershell
cd C:\Users\lione\Desktop\exam_platform\frontend
ng.cmd serve
```

### Étape 3 — Connexion enseignant

Dans le navigateur :

```text
http://localhost:4200
```

Se connecter avec :

```text
Identifiant : prof
Mot de passe : isen-prof
```

### Étape 4 — Créer une configuration d'examen

Depuis l'interface :

* renseigner l'examen ;
* renseigner l'étudiant ;
* renseigner la machine ;
* choisir les paquets ;
* choisir sudo oui/non ;
* choisir Internet oui/non ;
* choisir Educ oui/non ;
* définir les domaines autorisés ;
* cliquer sur "Créer la configuration".

Le backend crée alors un fichier JSON dans :

```text
backend/configs/
```

### Étape 5 — Démarrer l'environnement d'examen

Depuis un troisième terminal :

```powershell
cd C:\Users\lione\Desktop\exam_platform\exam-client
python start_exam.py
```

Ce script exécute :

```text
fetch_config.py
apply_config.py
generate_nixos_config.py
```

Il permet de :

* récupérer la configuration ;
* appliquer la configuration en simulation ;
* générer le fichier NixOS ;
* envoyer les statuts au backend.

### Étape 6 — Simuler un travail étudiant

```powershell
python simulate_student_work.py
```

Ce script crée un fichier de travail étudiant dans le workspace simulé.

### Étape 7 — Terminer l'examen

```powershell
python finish_exam.py
```

Ce script exécute :

```text
backup_workspace.py
submit_archive.py
reset_exam.py
```

Il permet de :

* créer une archive ZIP du workspace ;
* envoyer le rendu au serveur ;
* vérifier que l'envoi a réussi ;
* remettre le workspace dans un état propre.

### Étape 8 — Vérifier dans le dashboard

Dans Angular :

* cliquer sur "Actualiser" ;
* vérifier les rendus reçus ;
* télécharger l'archive ZIP ;
* consulter l'état des machines ;
* consulter l'historique ;
* consulter la configuration NixOS ;
* télécharger le fichier `.nix`.

---

## 10. Génération NixOS

Le script suivant :

```text
exam-client/generate_nixos_config.py
```

lit la configuration JSON récupérée depuis le serveur et génère :

```text
exam-client/generated/exam-configuration.nix
exam-client/generated/exam-metadata.json
exam-client/generated/network-policy.json
```

Le fichier `exam-configuration.nix` contient :

* l'utilisateur d'examen `exam` ;
* les groupes système ;
* les droits sudo selon le choix enseignant ;
* les paquets autorisés ;
* le workspace étudiant ;
* l'activation du firewall ;
* l'activation de nftables ;
* la politique réseau prévue ;
* les métadonnées de l'examen.

Exemple de logique :

```text
Choix enseignant dans Angular
→ configuration JSON
→ génération automatique d'un fichier NixOS
→ fichier exploitable sur une machine Linux/NixOS
```

Cette partie permet de faire le lien entre la configuration fonctionnelle créée par l'enseignant et la configuration système cible.

---

## 11. Politique réseau

La configuration permet de représenter trois niveaux de politique réseau :

```text
Internet autorisé ou bloqué
Accès Educ autorisé ou bloqué
Domaines autorisés
```

Dans le prototype, la politique réseau est générée sous forme de fichier JSON et documentée dans la configuration NixOS.

Dans une version réelle, l'application effective de cette politique pourrait utiliser :

* nftables ;
* iptables ;
* un proxy ;
* un DNS contrôlé ;
* une passerelle réseau administrée par l'établissement ;
* une liste blanche IP/domaine validée par la DSI.

Le filtrage par domaine nécessite une attention particulière, car un pare-feu système filtre principalement par IP, port et interface. Le filtrage par nom de domaine doit donc être traité avec une solution réseau adaptée.

---

## 12. Sauvegarde, rendu et reset

Le client machine suit une logique sécurisée :

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

Cela évite de supprimer le travail étudiant avant sauvegarde.

---

## 13. Partie réelle et partie simulée

### Réalisé réellement dans le prototype

* interface Angular ;
* authentification JWT ;
* création de configuration ;
* validation des paquets ;
* stockage JSON ;
* récupération de configuration par client ;
* génération NixOS ;
* sauvegarde ZIP ;
* upload des rendus ;
* historique machine ;
* téléchargement des fichiers ;
* reset logique du workspace simulé.

### Simulé dans le prototype actuel

* installation réelle des paquets système ;
* modification réelle des droits Linux ;
* application réelle des règles réseau ;
* reset complet d'une machine NixOS ;
* déploiement sur plusieurs machines physiques.

Le prototype actuel fonctionne sous Windows pour le développement. La cible réelle reste une machine Linux/NixOS contrôlée par l'établissement.

---

## 14. Limites actuelles

Les principales limites du prototype sont :

* absence de base de données persistante ;
* utilisateurs enseignants définis localement dans le code ;
* clé JWT définie dans le code ;
* application système NixOS non encore exécutée avec `nixos-rebuild`;
* politique réseau générée mais non appliquée réellement ;
* fonctionnement multi-machines non encore testé sur un parc physique ;
* reset machine limité à un workspace simulé.

---

## 15. Évolutions possibles

Les améliorations possibles sont :

* ajouter une base de données ;
* gérer plusieurs enseignants ;
* utiliser des variables d'environnement pour les secrets ;
* ajouter des rôles plus complets : enseignant, administrateur, surveillant ;
* appliquer réellement la configuration sur une machine NixOS ;
* intégrer un cache local de paquets ;
* mettre en place un vrai filtrage réseau ;
* tester le système sur plusieurs machines ;
* automatiser le reset complet par image système ou snapshot ;
* améliorer le découpage Angular en composants.

---

## 16. Conclusion

Ce prototype valide la chaîne fonctionnelle principale d'une plateforme de configuration d'environnements Linux d'examen.

Il permet à un enseignant authentifié de créer une configuration, de générer un environnement cible NixOS, de suivre les machines, de récupérer les rendus étudiants et de contrôler le cycle de fin d'examen.

Même si certaines actions système sont encore simulées, le projet démontre l'architecture, le flux fonctionnel et la logique de sécurité nécessaires pour évoluer vers un déploiement réel sur machines Linux/NixOS.

````

Après avoir créé le fichier :

```powershell id="8r683t"
cd C:\Users\lione\Desktop\exam_platform
notepad README.md
````