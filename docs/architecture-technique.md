# Architecture technique — SecureExam

**Version documentaire :** 5 octobre 2026  
**Auteur :** Ayman CHERGUI  
**Projet :** Bureau d’études ISEN 2025/2026  
**Référent / client :** Willy DUQUENOY

---

## 1. Objectif et périmètre

SecureExam est une plateforme permettant de préparer un examen informatique, de construire un environnement NixOS correspondant aux règles choisies par l’enseignant, de l’appliquer sur un poste d’examen et de centraliser les rendus étudiants.

La version documentée s’appuie sur :

- un frontend Angular ;
- un backend FastAPI ;
- une base SQLite ;
- un agent Go exécuté sur le poste NixOS ;
- Nix/NixOS pour la construction de l’environnement ;
- Bubblewrap et les mécanismes Linux pour l’isolation ;
- nftables pour les restrictions réseau ;
- Docker Compose et Nginx pour la plateforme web ;
- ngrok en option pour rendre le backend accessible depuis un réseau différent.

Le dossier `exam-client/` est conservé comme **composant complémentaire** du projet. Il contient des scripts et ressources auxiliaires autour du poste d’examen, mais il ne remplace pas l’agent Go `secureexam-agent`, qui assure la communication active avec le backend dans l’architecture principale.

---

## 2. Architecture globale

```text
┌──────────────────────────────────────────────────────────────────────┐
│                         PLATEFORME WEB                               │
│                                                                      │
│  ┌────────────────────┐       HTTP / REST       ┌─────────────────┐ │
│  │ Frontend Angular   │ ──────────────────────> │ Backend FastAPI │ │
│  │ port 4200          │ <────────────────────── │ port 8000       │ │
│  └────────────────────┘                         └───────┬─────────┘ │
│                                                        │           │
│                                             ┌──────────┴─────────┐ │
│                                             │                    │ │
│                                             v                    v │
│                                      ┌─────────────┐      ┌──────────┐
│                                      │   SQLite    │      │ Rendus   │
│                                      └─────────────┘      │ ZIP/meta │
│                                                           └──────────┘
└──────────────────────────────────────────────────────────────────────┘
                                  ^
                                  |
                                  | HTTPS / API agent
                                  | X-SecureExam-Agent-Token
                                  |
                     ┌────────────┴─────────────┐
                     │  secureexam-agent (Go)  │
                     │     service systemd      │
                     └────────────┬─────────────┘
                                  |
                                  v
                     ┌──────────────────────────┐
                     │       Poste NixOS        │
                     │ Nix / Bubblewrap /       │
                     │ nftables / compte exam   │
                     └──────────────────────────┘
```

Si le backend n’est pas directement joignable depuis le poste NixOS, un tunnel ngrok peut être inséré entre l’agent et le port `8000`.

---

## 3. Composants

| Composant | Technologie | Responsabilité |
|---|---|---|
| Interface web | Angular, TypeScript, HTML, CSS | Préparation des examens, parcours étudiant, supervision et rendus |
| Backend | Python 3.12, FastAPI, Uvicorn | Authentification, API, configurations, commandes agent, génération NixOS |
| Persistance | SQLite | Comptes, configurations, affectations, états et métadonnées |
| Agent principal | Go | Enregistrement machine, heartbeat, polling, build/switch NixOS, remontée d’état |
| Poste d’examen | NixOS / Nix | Application de la configuration système |
| Isolation | Bubblewrap, permissions Linux | Limitation de l’environnement étudiant |
| Réseau | nftables | Autorisation ou blocage des flux réseau |
| Déploiement web | Docker Compose, Nginx | Exécution des services web |
| Accès distant optionnel | ngrok | Tunnel HTTPS vers le backend ou le frontend |
| Outils complémentaires | `exam-client/` | Scripts et ressources auxiliaires du poste d’examen |

---

## 4. Organisation du dépôt

```text
secure_exam/
├── backend/
├── docs/
│   ├── architecture-technique.md
│   └── guide-installation.md
├── exam-client/
├── frontend/
├── secureexam-agent/
├── docker-compose.yml
└── README.md
```

### 4.1 `backend/`

Contient l’API FastAPI, notamment :

- authentification et JWT ;
- gestion des enseignants et étudiants ;
- configuration des examens ;
- génération NixOS ;
- commandes destinées aux machines ;
- suivi des agents ;
- réception et consultation des rendus ;
- accès SQLite.

### 4.2 `frontend/`

Contient l’application Angular et les vues :

- espace enseignant ;
- espace étudiant ;
- administration selon les droits ;
- consultation des machines ;
- consultation et téléchargement des rendus.

### 4.3 `secureexam-agent/`

Contient l’agent Go installé sur le poste NixOS.

Il assure notamment :

- l’identification de la machine ;
- l’enregistrement auprès du backend ;
- les heartbeats ;
- le polling des commandes ;
- la récupération des configurations ;
- les opérations NixOS ;
- la remontée des états `DONE` / `ERROR`.

### 4.4 `exam-client/`

`exam-client/` est un **composant complémentaire**.

Il peut contenir des scripts, fichiers de configuration et outils auxiliaires utiles autour du poste d’examen. Il ne doit pas être confondu avec le service Go principal et ne doit pas être supprimé de la livraison simplement parce qu’il n’assure pas le polling courant de l’agent.

---

## 5. Frontend Angular

Le frontend transmet les actions utilisateur au backend par HTTP.

L’authentification applicative utilise un JWT :

```http
Authorization: Bearer <JWT_UTILISATEUR>
```

Les autorisations sensibles doivent toujours être contrôlées côté backend. La seule restriction d’un bouton ou d’une page Angular ne constitue pas une protection suffisante.

En développement local, `proxy.conf.json` peut rediriger les appels `/api/...` vers :

```text
http://127.0.0.1:8000
```

En conteneur, Nginx doit soit utiliser une URL backend accessible, soit proxifier `/api/` vers le service Compose :

```text
http://backend:8000/
```

---

## 6. Backend FastAPI

Le backend centralise l’état de la plateforme et expose les API utilisées par le frontend et par l’agent.

Le backend écoute sur :

```text
0.0.0.0:8000
```

Route de vérification :

```text
GET /health
```

Les opérations de l’agent comprennent notamment :

```text
POST /agent/register
POST /agent/heartbeat
GET  /agent/commands/{machine_id}/next
GET  /agent/config/{exam_id}
POST /agent/commands/{command_id}/complete
```

---

## 7. Authentification et secrets

Trois secrets peuvent intervenir dans l’environnement de démonstration. Ils ont des rôles totalement différents.

| Secret | Utilisé par | Fonction |
|---|---|---|
| `JWT_SECRET_KEY` | Backend | Signer les JWT utilisateurs |
| `SECUREEXAM_AGENT_TOKEN` | Backend + agent Go | Authentifier la machine auprès de l’API |
| `NGROK_AUTHTOKEN` | CLI ngrok | Authentifier le poste qui crée le tunnel ngrok |

### 7.1 JWT utilisateur

Le backend signe les jetons utilisateur avec :

```text
JWT_SECRET_KEY
JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES
```

### 7.2 Token de l’agent

L’agent envoie le secret partagé dans l’en-tête :

```http
X-SecureExam-Agent-Token: <SECUREEXAM_AGENT_TOKEN>
```

La valeur doit être identique :

```text
backend/.env
        ↕ même valeur
service secureexam-agent sur NixOS
```

Un token différent entraîne un refus d’authentification.

### 7.3 Token ngrok

`NGROK_AUTHTOKEN` sert uniquement à authentifier le client ngrok auprès du service ngrok.

Il ne doit jamais être utilisé comme JWT ou comme token agent.

---

## 8. Agent Go et machine NixOS

Variables de configuration de l’agent :

| Variable | Rôle | Valeur par défaut / comportement |
|---|---|---|
| `SECUREEXAM_BACKEND_URL` | URL de l’API SecureExam | `http://127.0.0.1:8000` si non fournie |
| `SECUREEXAM_AGENT_TOKEN` | Secret partagé | Obligatoire |
| `SECUREEXAM_MACHINE_ID` | Identifiant de machine | Détecté via `/etc/machine-id` si absent |
| `SECUREEXAM_STATE_DIR` | État local de l’agent | `/var/lib/secureexam-agent` sous Linux |

Valeurs de la machine de référence observées lors des derniers essais :

```text
Service   : secureexam-agent
Compte    : exam
UID       : 1500
Home      : /home/exam
Workspace : /home/exam/workspace
```

Le service doit disposer des privilèges nécessaires pour exécuter les opérations NixOS. Ces privilèges ne doivent pas être confondus avec les droits accordés au compte étudiant.

---

## 9. Cycle START_EXAM

Le flux principal est :

```text
Étudiant
   |
   | Démarrer l'examen
   v
Frontend
   |
   v
Backend
   |
   | crée START_EXAM
   v
Agent Go
   |
   | récupère le module NixOS
   | sauvegarde / utilise la baseline
   | vérifie la syntaxe
   | nixos-rebuild build
   | nixos-rebuild switch
   v
Poste prêt
```

Séquence détaillée :

1. le backend crée une commande `START_EXAM` ;
2. l’agent récupère la commande ;
3. l’agent télécharge la configuration NixOS ;
4. l’état système de référence est conservé pour le retour arrière ;
5. la configuration générée est préparée localement ;
6. la syntaxe Nix est contrôlée ;
7. `nixos-rebuild build` construit la nouvelle génération ;
8. `nixos-rebuild switch` l’active ;
9. l’agent vérifie le nouvel état ;
10. la commande est clôturée en `DONE` ou `ERROR`.

---

## 10. Environnement étudiant

Paramètres principaux :

```text
Utilisateur : exam
UID         : 1500
Workspace   : /home/exam/workspace
Permissions : 0700
```

La session d’examen combine :

- compte Linux dédié ;
- workspace limité ;
- Nix store en lecture seule dans la sandbox ;
- Bubblewrap ;
- suppression ou limitation des capacités ;
- environnement reconstruit ;
- restrictions sudo selon le profil ;
- règles nftables selon le profil réseau.

---

## 11. Politique réseau

Les profils peuvent combiner :

- Internet autorisé ou interdit ;
- accès EDUC autorisé ;
- domaines supplémentaires autorisés.

L’objectif est que les règles appliquées au compte `exam` correspondent au profil défini par l’enseignant.

Exemples de profils utilisés lors des essais :

| Profil | Sudo | Internet | EDUC |
|---|---:|---:|---:|
| Python | Non | Non | Oui |
| C++ | Oui | Oui | Oui |

Le filtrage par domaine doit tenir compte des résolutions DNS, adresses variables et services partagés. Une validation sur plusieurs réseaux reste nécessaire avant industrialisation.

---

## 12. ngrok et accès depuis un réseau différent

### 12.1 Cas local

Si la VM NixOS peut joindre directement l’hôte :

```text
SECUREEXAM_BACKEND_URL=http://ADRESSE_SERVEUR:8000
```

### 12.2 Cas distant

Si la VM et le backend ne sont pas sur un réseau directement joignable :

```bash
ngrok config add-authtoken <NGROK_AUTHTOKEN>
ngrok http 8000
```

Exemple d’URL fournie :

```text
https://xxxxx.ngrok-free.app
```

L’agent utilise alors :

```text
SECUREEXAM_BACKEND_URL=https://xxxxx.ngrok-free.app
```

Le backend reste localement sur `8000`. ngrok fournit seulement le point d’entrée HTTPS public.

### 12.3 Frontend

Si l’objectif est uniquement d’ouvrir l’interface Angular à distance :

```bash
ngrok http 4200
```

Pour la communication de l’agent, le tunnel nécessaire vise le **backend 8000**.

---

## 13. Docker Compose

La plateforme web est séparée du poste NixOS.

```text
Docker Compose
├── backend  : hôte 8000 → conteneur 8000
└── frontend : hôte 4200 → conteneur 80
```

Le poste NixOS et `secureexam-agent` sont installés séparément.

Commandes principales :

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend frontend
```

---

## 14. Stockage et persistance

Le Compose monte :

```yaml
volumes:
  - ./backend/database:/app/database
```

La base SQLite utilisée par le backend doit donc être située dans ce chemin persistant pour être conservée lors de la recréation du conteneur.

Si les ZIP, photos ou autres fichiers sont stockés en dehors de SQLite, leur répertoire doit également disposer d’un stockage persistant et être intégré à la stratégie de sauvegarde.

---

## 15. Rendus et fin de session

Le fonctionnement attendu est :

1. collecter le workspace ;
2. créer l’archive de rendu ;
3. envoyer le rendu au backend ;
4. rendre le fichier disponible côté enseignant ;
5. vérifier le dépôt ;
6. effectuer la restauration et le nettoyage prévus.

La restauration NixOS et le nettoyage des fichiers étudiant sont deux opérations différentes.

Le comportement exact en cas d’échec d’envoi doit rester cohérent avec le code Go livré : le travail ne doit pas être détruit avant qu’une stratégie de reprise ou une preuve de dépôt adaptée soit disponible.

---

## 16. Sécurité de la livraison

Ne pas versionner les secrets réels :

```text
backend/.env
NGROK_AUTHTOKEN
SECUREEXAM_AGENT_TOKEN réel
mots de passe réels
JWT_SECRET_KEY réel
```

Fournir à la place :

```text
backend/.env.example
```

avec des placeholders.

Les secrets doivent être renouvelés pour chaque installation réelle.

---

## 17. Documents associés

- [`../README.md`](../README.md) — présentation générale ;
- [`guide-installation.md`](guide-installation.md) — installation complète et mise en service.

Ces trois documents constituent la documentation principale de la remise SecureExam.
