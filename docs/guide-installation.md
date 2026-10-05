# SecureExam — Guide d’installation et de mise en service

**Version documentaire :** 5 octobre 2026  
**Auteur :** Ayman CHERGUI  
**Référent / client :** Willy DUQUENOY

---

## 1. Objectif

Ce guide permet de remettre en service SecureExam à partir du dépôt :

```text
secure_exam/
├── backend/
├── docs/
├── exam-client/
├── frontend/
├── secureexam-agent/
├── docker-compose.yml
└── README.md
```

La plateforme se compose de deux ensembles distincts :

1. **plateforme web** : Angular + FastAPI + SQLite ;
2. **poste d’examen** : NixOS + agent Go `secureexam-agent`.

`exam-client/` est un **composant complémentaire** contenant des scripts et ressources auxiliaires. Il est conservé dans la livraison mais ne remplace pas l’agent Go.

---

## 2. Prérequis

### Serveur / ordinateur hébergeant la plateforme web

Prévoir :

- Docker Engine + Docker Compose, ou Docker Desktop ;
- accès réseau pour télécharger les images et dépendances lors du premier build ;
- ports `4200` et `8000` disponibles ;
- les sources complètes de SecureExam.

### Poste d’examen

Prévoir :

- NixOS ;
- le binaire ou le code source de `secureexam-agent` ;
- un service `secureexam-agent` ;
- accès réseau vers le backend ;
- les outils NixOS nécessaires au build/switch ;
- le compte `exam`.

### Accès distant facultatif

Si le backend n’est pas directement joignable depuis le poste NixOS :

- installer ngrok sur la machine qui héberge le backend ;
- disposer d’un compte ngrok et de son `NGROK_AUTHTOKEN`.

---

## 3. Vérifier l’arborescence

Depuis la racine :

```bash
ls
```

Les éléments principaux doivent être présents :

```text
backend
docs
exam-client
frontend
secureexam-agent
docker-compose.yml
README.md
```

Ne pas supprimer `exam-client/` : il reste un composant complémentaire du projet.

---

## 4. Préparer `backend/.env`

Si un modèle est fourni :

### Windows PowerShell

```powershell
if (!(Test-Path backend/.env)) {
    Copy-Item backend/.env.example backend/.env
}
```

### Linux / macOS

```bash
test -f backend/.env || cp backend/.env.example backend/.env
```

Ne jamais écraser automatiquement un `.env` déjà configuré.

---

## 5. Générer les secrets

Deux secrets SecureExam sont particulièrement importants :

```text
JWT_SECRET_KEY
SECUREEXAM_AGENT_TOKEN
```

Ils doivent être longs et aléatoires.

Avec Python :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Exécuter la commande deux fois et utiliser deux valeurs différentes :

```text
1re valeur → JWT_SECRET_KEY
2e valeur → SECUREEXAM_AGENT_TOKEN
```

---

## 6. Exemple de `backend/.env`

```dotenv
# =========================================================
# SecureExam - Backend
# =========================================================

JWT_SECRET_KEY=<SECRET_JWT_LONG_ET_ALEATOIRE>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120

# Doit être exactement le même côté agent Go
SECUREEXAM_AGENT_TOKEN=<SECRET_AGENT_LONG_ET_ALEATOIRE>

# Selon la procédure de création du premier compte livrée
TEACHER_USERNAME=<COMPTE_INITIAL>
TEACHER_PASSWORD=<MOT_DE_PASSE_INITIAL>

# SMTP uniquement si la fonction support e-mail est utilisée
# SMTP_HOST=
# SMTP_PORT=
# SMTP_USERNAME=
# SMTP_PASSWORD=
```

### Important

`JWT_SECRET_KEY` et `SECUREEXAM_AGENT_TOKEN` ont des rôles différents.

- `JWT_SECRET_KEY` signe les jetons des utilisateurs.
- `SECUREEXAM_AGENT_TOKEN` authentifie le poste NixOS auprès du backend.

Ne jamais utiliser le même secret pour les deux.

Les variables de compte initial doivent être vérifiées par rapport au mécanisme réellement livré. Ne pas supposer qu’un compte est créé automatiquement uniquement parce que `TEACHER_USERNAME` et `TEACHER_PASSWORD` existent dans le code.

---

# PARTIE A — INSTALLATION AVEC DOCKER

## 7. Vérifier Docker

Depuis `secure_exam/` :

```bash
docker version
docker compose version
```

Puis :

```bash
docker compose config --quiet
```

Aucune erreur ne doit être retournée.

---

## 8. Construire et lancer SecureExam

```bash
docker compose up -d --build
```

Vérifier :

```bash
docker compose ps
```

Les services backend et frontend doivent être actifs.

---

## 9. Vérifier le backend

```bash
curl http://localhost:8000/health
```

Ou ouvrir :

```text
http://localhost:8000/health
```

Documentation FastAPI si elle est activée :

```text
http://localhost:8000/docs
```

---

## 10. Vérifier le frontend

Ouvrir :

```text
http://localhost:4200
```

Le frontend Docker est servi par Nginx.

Si Angular utilise des chemins `/api/...`, Nginx doit les transmettre au service backend.

Exemple :

```nginx
location ^~ /api/ {
    proxy_pass http://backend:8000/;
}
```

Le slash final retire le préfixe `/api/` :

```text
/api/health  →  backend:8000/health
```

Après modification :

```bash
docker compose up -d --build frontend
docker compose exec frontend nginx -t
```

---

## 11. Logs Docker

```bash
docker compose logs --tail=100 backend frontend
```

Suivi en direct :

```bash
docker compose logs -f backend frontend
```

---

# PARTIE B — LANCEMENT MANUEL

## 12. Backend sous Windows

Depuis :

```text
secure_exam/backend
```

Créer l’environnement :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Lancer :

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --env-file .env
```

---

## 13. Backend sous Linux / macOS

```bash
cd secure_exam/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --env-file .env
```

---

## 14. Frontend Angular

Depuis :

```text
secure_exam/frontend
```

Installer :

```bash
npm ci
```

Lancer :

```bash
npx ng serve --host 0.0.0.0 --port 4200 --proxy-config proxy.conf.json
```

Sous Windows, si nécessaire :

```powershell
npm.cmd ci
npx.cmd ng serve --host 0.0.0.0 --port 4200 --proxy-config proxy.conf.json
```

Vérifier :

```text
http://localhost:4200
http://localhost:4200/api/health
```

La seconde URL doit renvoyer le backend si le proxy Angular est utilisé.

---

# PARTIE C — NGROK

## 15. Pourquoi ngrok ?

ngrok est utile lorsque :

```text
Backend sur PC Windows
        |
        | Internet / réseau différent
        v
VM ou poste NixOS
```

et que la VM ne peut pas joindre directement l’IP locale du backend.

ngrok n’est pas obligatoire si une adresse LAN, VPN ou serveur accessible est déjà disponible.

---

## 16. Configurer ngrok

Installer ngrok puis enregistrer le token du compte :

```bash
ngrok config add-authtoken <NGROK_AUTHTOKEN>
```

### Attention aux trois secrets

```text
NGROK_AUTHTOKEN
    = authentification du client ngrok

JWT_SECRET_KEY
    = signature des JWT utilisateurs

SECUREEXAM_AGENT_TOKEN
    = authentification de l'agent Go auprès du backend
```

Ils ne sont pas interchangeables.

---

## 17. Exposer le backend

Vérifier d’abord :

```text
http://localhost:8000/health
```

Puis lancer :

```bash
ngrok http 8000
```

ngrok affiche une URL HTTPS ressemblant à :

```text
https://xxxxx.ngrok-free.app
```

Tester :

```bash
curl https://xxxxx.ngrok-free.app/health
```

---

## 18. URL à utiliser côté NixOS

Si ngrok fournit :

```text
https://xxxxx.ngrok-free.app
```

alors l’agent doit utiliser :

```text
SECUREEXAM_BACKEND_URL=https://xxxxx.ngrok-free.app
```

Ne pas ajouter `:8000` derrière l’URL ngrok HTTPS.

### Important

Avec une URL ngrok gratuite non réservée, l’URL peut changer après redémarrage du tunnel.

Si elle change :

1. récupérer la nouvelle URL ;
2. modifier `SECUREEXAM_BACKEND_URL` ;
3. redémarrer l’agent.

---

## 19. Exposer le frontend — facultatif

Pour rendre uniquement l’interface accessible à distance :

```bash
ngrok http 4200
```

Mais pour `secureexam-agent`, le tunnel important reste celui du :

```text
backend : 8000
```

---

# PARTIE D — AGENT GO SUR NIXOS

## 20. Paramètres de l’agent

L’agent utilise :

```text
SECUREEXAM_BACKEND_URL
SECUREEXAM_AGENT_TOKEN
SECUREEXAM_MACHINE_ID
SECUREEXAM_STATE_DIR
```

Valeurs de référence :

```text
SECUREEXAM_STATE_DIR=/var/lib/secureexam-agent
```

`SECUREEXAM_MACHINE_ID` peut être omis si l’agent détecte correctement `/etc/machine-id`.

---

## 21. Vérifier l’installation existante

```bash
systemctl status secureexam-agent --no-pager
sudo journalctl -u secureexam-agent -n 80 --no-pager
getent passwd exam
sudo ls -ld /home/exam/workspace
```

Résultats attendus :

```text
service : actif
compte  : exam
UID     : 1500
workspace : /home/exam/workspace
```

---

## 22. Configurer l’agent sur un poste déjà préparé

Sur une machine de démonstration utilisant systemd, un override peut être utilisé.

```bash
sudo systemctl edit secureexam-agent
```

Ajouter :

```ini
[Service]
Environment="SECUREEXAM_BACKEND_URL=https://xxxxx.ngrok-free.app"
Environment="SECUREEXAM_AGENT_TOKEN=<MEME_TOKEN_QUE_BACKEND_ENV>"
Environment="SECUREEXAM_STATE_DIR=/var/lib/secureexam-agent"
```

Optionnel :

```ini
Environment="SECUREEXAM_MACHINE_ID=<IDENTIFIANT_MACHINE>"
```

Puis :

```bash
sudo systemctl daemon-reload
sudo systemctl restart secureexam-agent
sudo systemctl status secureexam-agent --no-pager -l
```

> Pour une installation NixOS reproductible, intégrer ces paramètres dans la définition NixOS du service plutôt que de dépendre uniquement d’un override manuel.

---

## 23. Vérifier la connexion de l’agent

Logs :

```bash
sudo journalctl -u secureexam-agent -n 100 --no-pager -l
```

En direct :

```bash
sudo journalctl -u secureexam-agent -f -l
```

Le journal doit montrer :

- l’identifiant de machine ;
- l’URL backend ;
- l’enregistrement de la machine ;
- les heartbeats ;
- l’absence d’erreur répétée d’authentification.

Dans l’interface enseignant, la machine doit apparaître avec un état récent.

---

## 24. Tester le backend depuis NixOS

Si `curl` est disponible :

```bash
curl -i https://xxxxx.ngrok-free.app/health
```

ou en LAN :

```bash
curl -i http://ADRESSE_BACKEND:8000/health
```

Si cette étape échoue, l’agent ne pourra pas fonctionner correctement.

---

## 25. Erreurs de token

### Backend sans token agent configuré

Le backend peut refuser la communication si :

```text
SECUREEXAM_AGENT_TOKEN
```

n’est pas défini côté serveur.

### Token différent

Si :

```text
backend/.env
SECUREEXAM_AGENT_TOKEN=AAA
```

mais côté NixOS :

```text
SECUREEXAM_AGENT_TOKEN=BBB
```

l’agent sera refusé.

La valeur doit être **strictement la même**.

---

# PARTIE E — VALIDATION DE BOUT EN BOUT

## 26. Préparer un examen

Dans l’espace enseignant :

1. créer ou sélectionner un examen ;
2. sélectionner les logiciels ;
3. définir sudo ;
4. définir Internet ;
5. définir EDUC ;
6. ajouter les domaines autorisés si nécessaire ;
7. affecter l’étudiant ;
8. publier/préparer l’examen.

---

## 27. Démarrer côté étudiant

L’étudiant :

1. se connecte ;
2. ouvre l’examen ;
3. clique sur **Démarrer l’examen**.

Pendant ce temps :

```bash
sudo journalctl -u secureexam-agent -f
```

Le workflow doit enchaîner :

```text
commande START_EXAM
↓
récupération configuration
↓
validation Nix
↓
nixos-rebuild build
↓
nixos-rebuild switch
↓
poste prêt
```

---

## 28. Vérifier le compte étudiant

```bash
getent passwd exam
sudo ls -ld /home/exam/workspace
```

Puis :

```bash
sudo -iu exam
```

Dans la session :

```bash
whoami
id
pwd
```

Valeur attendue :

```text
exam
```

Workspace :

```text
/home/exam/workspace
```

---

## 29. Vérifier le rendu

Après le travail étudiant :

1. déclencher la fin ou le dépôt ;
2. observer les logs de l’agent ;
3. ouvrir l’espace enseignant ;
4. retrouver le rendu ;
5. télécharger le ZIP ;
6. ouvrir le ZIP ;
7. vérifier le contenu réel du travail.

La restauration du système et le nettoyage du workspace doivent être contrôlés séparément.

---

# PARTIE F — EXPLOITATION

## 30. Commandes Docker utiles

```bash
docker compose ps
docker compose logs --tail=100 backend frontend
docker compose stop
docker compose start
docker compose up -d --build
```

---

## 31. Sauvegarde

Le Compose persiste le dossier :

```text
./backend/database
```

dans :

```text
/app/database
```

Avant une sauvegarde importante :

```bash
docker compose stop
```

Copier le dossier de données, puis :

```bash
docker compose start
```

Si les ZIP ou photos sont enregistrés en dehors de SQLite, leurs répertoires doivent également être sauvegardés.

---

## 32. Dépannage rapide

| Symptôme | Vérification |
|---|---|
| Docker ne démarre pas | Docker Engine/Desktop actif |
| Port 4200 occupé | autre frontend déjà lancé |
| Port 8000 occupé | autre backend déjà lancé |
| `/health` inaccessible | logs backend + `.env` |
| Frontend affiche HTML au lieu de JSON sur `/api` | proxy Angular/Nginx |
| Agent absent | `SECUREEXAM_BACKEND_URL`, réseau, service |
| Erreur 401 agent | vérifier `SECUREEXAM_AGENT_TOKEN` des deux côtés |
| Erreur 503 agent | vérifier que le token est configuré côté backend |
| URL ngrok inaccessible | tunnel arrêté ou URL changée |
| Machine visible mais START_EXAM échoue | logs agent + erreur Nix |
| Rendu absent | logs d’envoi + stockage backend |

---

## 33. Checklist finale de remise

Avant de remettre le projet :

- [ ] `README.md` présent ;
- [ ] `docs/architecture-technique.md` présent ;
- [ ] `docs/guide-installation.md` présent ;
- [ ] `backend/.env.example` présent et sans secret ;
- [ ] aucun vrai `.env` versionné ;
- [ ] aucun token ngrok versionné ;
- [ ] aucun token agent réel versionné ;
- [ ] `docker compose config --quiet` fonctionne ;
- [ ] backend accessible sur `/health` ;
- [ ] frontend accessible ;
- [ ] agent `secureexam-agent` actif ;
- [ ] machine visible dans la plateforme ;
- [ ] même `SECUREEXAM_AGENT_TOKEN` côté serveur et agent ;
- [ ] URL `SECUREEXAM_BACKEND_URL` correcte ;
- [ ] tunnel ngrok documenté si utilisé ;
- [ ] examen de test démarré ;
- [ ] rendu téléchargé et vérifié.

---

## 34. Résumé essentiel

Pour un déploiement de démonstration distant :

```text
1. Configurer backend/.env
2. docker compose up -d --build
3. Vérifier http://localhost:8000/health
4. ngrok config add-authtoken <NGROK_AUTHTOKEN>
5. ngrok http 8000
6. Copier l'URL HTTPS
7. Mettre cette URL dans SECUREEXAM_BACKEND_URL côté NixOS
8. Mettre le même SECUREEXAM_AGENT_TOKEN côté backend et agent
9. Redémarrer secureexam-agent
10. Vérifier les logs et la machine dans l'interface
11. Lancer un examen de test
12. Vérifier le rendu
```

C’est la chaîne minimale à conserver pour pouvoir reprendre SecureExam rapidement.
