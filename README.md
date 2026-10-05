# SecureExam

SecureExam est une plateforme de préparation et de supervision d’examens informatiques sur NixOS.

L’enseignant prépare l’épreuve depuis une interface web Angular, le backend FastAPI enregistre la configuration et génère l’environnement NixOS, puis un agent Go installé sur le poste d’examen récupère les commandes et applique la configuration. Les rendus étudiants sont ensuite centralisés côté serveur.

**Projet :** Bureau d’études ISEN — 2025/2026  
**Auteur :** Ayman CHERGUI  
**Référent / client :** Willy DUQUENOY  
**Version projet :** v1.0.9  
**Version de l’agent SecureExam Agent:** 0.4.1

---

## 1. Documentation principale

Les trois documents principaux de la livraison sont :

- [`README.md`](README.md) — vue d’ensemble et démarrage rapide ;
- [`docs/architecture-technique.md`](docs/architecture-technique.md) — architecture, composants et flux ;
- [`docs/guide-installation.md`](docs/guide-installation.md) — installation, configuration, ngrok, tokens et vérifications.

La référence finale reste toujours la version du code livrée.

---

## 2. Architecture en une vue

```text
                           +----------------------+
                           |   Frontend Angular   |
                           |      port 4200       |
                           +----------+-----------+
                                      |
                                      | HTTP / REST
                                      v
                           +----------------------+
                           |   Backend FastAPI    |
                           |      port 8000       |
                           +-----+-----------+----+
                                 |           |
                                 |           +------------------+
                                 |                              |
                                 v                              v
                         +---------------+              +---------------+
                         |    SQLite     |              |  Rendus / ZIP |
                         +---------------+              +---------------+
                                 ^
                                 |
                                 | API agent
                                 | X-SecureExam-Agent-Token
                                 |
                    +------------+-------------+
                    |  secureexam-agent (Go)   |
                    |      poste NixOS         |
                    +------------+-------------+
                                 |
                                 v
                    +--------------------------+
                    | NixOS / Nix / Bubblewrap |
                    | nftables / workspace exam |
                    +--------------------------+
```

Pour une VM ou un poste situé sur un autre réseau, le backend peut être exposé temporairement avec **ngrok**. Le tunnel utilisé par l’agent doit viser le **port 8000**.

---

## 3. Organisation du dépôt

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

| Chemin | Rôle |
|---|---|
| `backend/` | API FastAPI, authentification, configurations, commandes machine, génération NixOS et rendus |
| `frontend/` | Interface Angular enseignant / étudiant |
| `secureexam-agent/` | Agent Go exécuté sur le poste d’examen NixOS |
| `exam-client/` | **Composant complémentaire** : scripts et ressources auxiliaires autour du poste d’examen. Il ne remplace pas l’agent Go |
| `docs/` | Documentation principale du projet |
| `docker-compose.yml` | Lancement du frontend et du backend |

> `exam-client/` fait partie de la livraison comme composant complémentaire. Il ne doit pas être présenté comme le service principal de communication avec le backend : ce rôle appartient à `secureexam-agent/`.

---

## 4. Composants principaux

| Composant | Technologie | Rôle |
|---|---|---|
| Frontend | Angular / TypeScript | Création des examens, parcours étudiant, supervision et récupération des rendus |
| Backend | Python 3.12 / FastAPI / Uvicorn | API REST, authentification, logique métier et génération NixOS |
| Persistance | SQLite | Comptes, configurations, affectations, états et données de rendu |
| Agent | Go | Communication backend ↔ poste NixOS, polling, build/switch, états |
| Poste d’examen | NixOS / Nix | Construction et activation de l’environnement |
| Isolation | Bubblewrap, permissions Linux | Isolation de la session étudiant |
| Réseau | nftables | Application des restrictions réseau selon le profil |
| Déploiement web | Docker Compose / Nginx | Exécution du backend et du frontend |

---

## 5. Démarrage rapide avec Docker

Depuis la racine `secure_exam/` :

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Accès local :

```text
Frontend : http://localhost:4200
Backend  : http://localhost:8000
Health   : http://localhost:8000/health
API docs : http://localhost:8000/docs
```

Logs :

```bash
docker compose logs --tail=100 backend frontend
```

---

## 6. Configuration essentielle

Créer `backend/.env` à partir de `backend/.env.example` lorsqu’il est fourni.

Exemple minimal :

```dotenv
JWT_SECRET_KEY=<SECRET_JWT_LONG_ET_ALEATOIRE>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120

SECUREEXAM_AGENT_TOKEN=<SECRET_AGENT_LONG_ET_ALEATOIRE>

# Selon la procédure d'initialisation réellement livrée :
TEACHER_USERNAME=<COMPTE_INITIAL>
TEACHER_PASSWORD=<MOT_DE_PASSE_INITIAL>
```

Deux secrets ne doivent pas être confondus :

| Secret | Utilisation |
|---|---|
| `JWT_SECRET_KEY` | Signature des jetons de connexion des utilisateurs |
| `SECUREEXAM_AGENT_TOKEN` | Authentification entre l’agent Go et le backend |

Le token agent doit être **exactement identique** côté backend et côté poste NixOS.

---

## 7. Agent NixOS

Paramètres utilisés par l’agent :

```text
SECUREEXAM_BACKEND_URL
SECUREEXAM_AGENT_TOKEN
SECUREEXAM_MACHINE_ID
SECUREEXAM_STATE_DIR
```

Valeurs observées lors des derniers essais :

```text
Service   : secureexam-agent
Utilisateur étudiant : exam
UID       : 1500
Workspace : /home/exam/workspace
State dir : /var/lib/secureexam-agent
```

Contrôles :

```bash
systemctl status secureexam-agent --no-pager
sudo journalctl -u secureexam-agent -n 80 --no-pager
getent passwd exam
sudo ls -ld /home/exam/workspace
```

Logs en direct :

```bash
sudo journalctl -u secureexam-agent -f
```

---

## 8. Accès distant avec ngrok

ngrok est utile lorsque le poste NixOS ne peut pas joindre directement l’adresse locale du serveur.

### Authentifier ngrok

```bash
ngrok config add-authtoken <NGROK_AUTHTOKEN>
```

### Exposer le backend

```bash
ngrok http 8000
```

ngrok fournit une URL HTTPS de la forme :

```text
https://xxxxx.ngrok-free.app
```

Cette URL devient alors la valeur de :

```text
SECUREEXAM_BACKEND_URL=https://xxxxx.ngrok-free.app
```

sur le poste NixOS.

> `NGROK_AUTHTOKEN` est uniquement le secret du compte ngrok.  
> Il ne remplace ni `JWT_SECRET_KEY` ni `SECUREEXAM_AGENT_TOKEN`.

Pour exposer uniquement l’interface web, le tunnel peut viser `4200`. Pour l’agent Go, c’est bien le **backend 8000** qui doit être joignable.

---

## 9. Vérification d’un examen

Workflow attendu :

1. L’enseignant crée/configure l’examen.
2. L’étudiant ouvre l’épreuve et clique sur **Démarrer l’examen**.
3. Le backend crée la commande destinée au poste.
4. L’agent récupère la configuration.
5. NixOS construit puis active l’environnement.
6. L’étudiant travaille dans `/home/exam/workspace`.
7. Le rendu est collecté et transmis au backend.
8. L’enseignant récupère et vérifie l’archive.

Profils utilisés lors des derniers essais :

| Profil | Sudo | Internet | EDUC |
|---|---:|---:|---:|
| Python | Non | Non | Oui |
| C++ | Oui | Oui | Oui |

---

## 10. Sécurité et livraison

Ne jamais versionner :

- `backend/.env` contenant de vrais secrets ;
- le `NGROK_AUTHTOKEN` ;
- le vrai `SECUREEXAM_AGENT_TOKEN` ;
- des mots de passe réels ;
- des rendus étudiants réels ;
- `.venv/`, `node_modules/`, caches et fichiers temporaires.

À conserver dans la livraison :

- `.env.example` sans secrets ;
- Dockerfiles ;
- `docker-compose.yml` ;
- `frontend/package-lock.json` ;
- `secureexam-agent/go.mod` ;
- scripts et configurations NixOS nécessaires ;
- les trois documents principaux du projet.

Pour l’installation complète, consulter [`docs/guide-installation.md`](docs/guide-installation.md).
