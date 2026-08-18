# Architecture technique - ISEN SecureExam

## Objectif du document

Ce document décrit l'architecture technique de la plateforme ISEN SecureExam.

Il présente les différents composants du projet, leurs responsabilités, les échanges entre les modules et le scénario complet validé sur une machine NixOS réelle.

---

## Vue d'ensemble

ISEN SecureExam repose sur trois composants principaux :

```text
Frontend Angular
→ interface enseignant

Backend FastAPI
→ API REST, authentification, base de données, supervision

Exam-client Python
→ client machine d'examen, génération NixOS, backup, dépôt, reset
```

Le fonctionnement global est le suivant :

```text
Enseignant
→ crée une configuration dans l'interface web
→ backend enregistre la configuration
→ machine d'examen récupère la configuration
→ client génère une configuration NixOS
→ workspace étudiant préparé
→ étudiant travaille
→ client archive le workspace
→ archive envoyée au backend
→ workspace remis à zéro après confirmation
```

---

## 1. Frontend Angular

Le frontend constitue l'interface utilisée par l'enseignant.

Il permet de :

- se connecter ;
- créer une configuration d'examen ;
- sélectionner les paquets autorisés ;
- définir les droits sudo ;
- définir les options réseau ;
- consulter les configurations existantes ;
- consulter les rendus étudiants ;
- suivre l'état des machines ;
- gérer le profil enseignant ;
- envoyer une demande de support.

Le frontend communique avec le backend via des requêtes HTTP.

Les routes protégées utilisent un token JWT transmis avec l'en-tête :

```text
Authorization: Bearer <token>
```

---

## 2. Backend FastAPI

Le backend est le point central de la plateforme.

Il assure :

- l'authentification des enseignants ;
- la gestion des configurations ;
- la gestion du catalogue logiciel ;
- la réception des archives ZIP ;
- le suivi des machines ;
- la gestion des profils enseignants ;
- la gestion des demandes de support ;
- la persistance des données dans SQLite.

Le backend expose une API REST utilisée à la fois par :

```text
Frontend Angular
Exam-client Python
```

---

## 3. Base SQLite

La base de données locale est stockée dans :

```text
backend/database/secure_exam.db
```

Elle contient les données applicatives principales :

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

Les fichiers volumineux ne sont pas stockés directement dans SQLite.

Les archives ZIP sont stockées dans :

```text
backend/submissions/
```

La base ne stocke que les métadonnées et les noms de fichiers.

---

## 4. Exam-client Python

Le client d'examen est exécuté sur la machine Linux/NixOS.

Il est responsable de :

- récupérer la configuration d'examen depuis le backend ;
- générer une configuration NixOS ;
- préparer le workspace étudiant ;
- créer les fichiers de suivi ;
- sauvegarder le workspace ;
- envoyer l'archive au backend ;
- remettre le workspace à zéro ;
- envoyer les statuts d'avancement au backend.

Scripts principaux :

```text
fetch_config.py
apply_config.py
generate_nixos_config.py
start_exam.py
backup_workspace.py
submit_archive.py
reset_exam.py
finish_exam.py
status_reporter.py
logger.py
demo_full.sh
```

---

## 5. Modes d'exécution

Le client supporte deux modes.

### Mode simulation

Le mode simulation permet de tester sans modifier le système réel.

Workspace utilisé :

```text
exam-client/runtime/home/exam/<student_id>/workspace
```

Ce mode est utile pour :

- développement ;
- tests rapides ;
- démonstration sans droits root ;
- validation logique du cycle.

### Mode réel NixOS

Le mode réel travaille sur le vrai workspace système :

```text
/home/exam/<student_id>/workspace
```

Ce mode nécessite les droits administrateur pour préparer et réinitialiser le workspace.

Il a été validé sur une machine NixOS avec :

```text
utilisateur exam
workspace réel
permissions Linux
paquets autorisés
droits sudo contrôlés
backup réel
submit backend
reset réel
```

---

## 6. Configuration client

Le client utilise le fichier :

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

Le champ `execution_mode` permet de choisir le mode :

```text
simulation
real
```

---

## 7. Cycle de démarrage d'un examen

Le démarrage est lancé avec :

```bash
start_exam.py
```

Il exécute trois étapes :

```text
FETCH
GENERATE_NIX
APPLY
```

### FETCH

Le client récupère la configuration depuis le backend :

```text
GET /configs/{exam_id}/{student_id}/{machine_id}
```

### GENERATE_NIX

Le client génère :

```text
generated/exam-configuration.nix
generated/exam-metadata.json
generated/network-policy.json
```

### APPLY

Le client prépare le workspace étudiant.

En mode réel :

```text
/home/exam/<student_id>/workspace
```

Il crée également :

```text
exam_metadata.json
exam_network_policy.json
```

---

## 8. Cycle de fin d'examen

La fin d'examen est lancée avec :

```bash
finish_exam.py
```

Elle exécute trois étapes :

```text
BACKUP
SUBMIT
RESET
```

### BACKUP

Le workspace étudiant est archivé en ZIP.

Nom d'archive :

```text
<exam_id>_<student_id>_<machine_id>_<timestamp>.zip
```

### SUBMIT

L'archive est envoyée au backend :

```text
POST /submissions
```

Le backend enregistre :

- le fichier ZIP ;
- les métadonnées de soumission ;
- la date d'envoi ;
- l'association examen / étudiant / machine.

### RESET

Le reset est effectué uniquement si :

```text
1. une archive locale existe ;
2. une preuve d'envoi serveur existe ;
3. l'archive locale correspond à l'archive envoyée.
```

Cette logique évite la perte du travail étudiant.

---

## 9. Génération NixOS

Le fichier généré :

```text
generated/exam-configuration.nix
```

permet de représenter la configuration système de l'examen.

Il contient notamment :

- la création de l'utilisateur `exam` ;
- les paquets autorisés ;
- la gestion des droits sudo ;
- le workspace étudiant ;
- les métadonnées d'examen ;
- la politique réseau prévue.

La configuration peut être copiée dans :

```text
/etc/nixos/exam-configuration.nix
```

puis importée dans :

```text
/etc/nixos/configuration.nix
```

Application de test :

```bash
sudo nixos-rebuild test
```

---

## 10. Sécurité

Le prototype intègre plusieurs sécurités :

```text
JWT pour les routes protégées
hash des mots de passe avec Argon2
séparation des données par enseignant
validation des paquets autorisés
refus des paquets non reconnus
workspace réel limité à /home/exam/
utilisateur système exam dédié
droits sudo contrôlés par configuration
archive avant reset
preuve d'envoi avant suppression
exclusion des secrets du dépôt Git
```

---

## 11. Supervision machine

Le client envoie des statuts au backend pendant le cycle :

```text
FETCH RUNNING / SUCCESS
GENERATE_NIX RUNNING / SUCCESS
APPLY RUNNING / SUCCESS
EXAM_READY SUCCESS
BACKUP RUNNING / SUCCESS
SUBMIT RUNNING / SUCCESS
RESET RUNNING / SUCCESS
EXAM_FINISHED SUCCESS
```

Ces statuts permettent de suivre l'état d'une machine d'examen depuis l'interface enseignant.

---

## 12. Script de démonstration

Le script :

```text
exam-client/demo_full.sh
```

automatise le scénario complet :

```text
vérification backend
start_exam.py réel
simulation travail étudiant
finish_exam.py réel
vérification archive
vérification reset
vérification backend
```

Il permet de présenter le projet avec une seule commande :

```bash
./demo_full.sh
```

---

## 13. Scénario validé

Le scénario réel validé est :

```text
Configuration enseignant
→ récupération backend
→ génération NixOS
→ préparation workspace réel
→ création fichier étudiant
→ archive ZIP
→ upload backend
→ preuve d'envoi
→ reset sécurisé
→ soumission visible côté backend
```

Ce scénario valide le cœur technique du projet.

---

## 14. Limites techniques actuelles

La politique réseau est générée, mais le filtrage strict par domaine n'est pas encore appliqué automatiquement.

Une version cible devra intégrer :

```text
proxy
DNS contrôlé
passerelle réseau
nftables avec IP validées
intégration DSI
```

Le déploiement multi-machines reste également à industrialiser.

---

## Conclusion

L'architecture actuelle permet de démontrer un cycle complet d'examen Linux contrôlé.

Le prototype couvre :

```text
configuration enseignant
supervision backend
génération NixOS
workspace réel
sauvegarde
dépôt serveur
reset sécurisé
```