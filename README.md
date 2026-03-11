# SeaDrop

Plateforme sécurisée de dépôt de documents PDF. Chaque fichier est validé par magic bytes, re-sérialisé via pikepdf pour neutraliser les scripts actifs, puis téléversé sur Mega.nz.

---

## Table des matières

1. [Tech Stack](#tech-stack)
2. [Prérequis](#prérequis)
3. [Démarrage local](#démarrage-local)
4. [Variables d'environnement](#variables-denvironnement)
5. [Architecture](#architecture)
6. [Déploiement Docker](#déploiement-docker)
7. [Sécurité](#sécurité)
8. [Dépannage](#dépannage)

---

## Tech Stack

| Composant | Technologie |
|-----------|------------|
| **Runtime** | Python 3.11 |
| **Framework** | FastAPI + Uvicorn |
| **Validation PDF** | python-magic (libmagic) + pikepdf |
| **Stockage** | Mega.nz via `mega.py` |
| **Frontend** | HTML + Tailwind CSS (CDN) |
| **Conteneur** | Docker (python:3.11-slim-bookworm) |

---

## Prérequis

### Développement local

- Python 3.11+
- `libmagic1` installé sur le système :
  ```bash
  # Debian / Ubuntu
  sudo apt-get install libmagic1

  # macOS
  brew install libmagic
  ```
- Un compte [Mega.nz](https://mega.nz) avec email/mot de passe

### Déploiement Docker

- Docker 24+ — libmagic1 est installé automatiquement dans l'image

---

## Démarrage local

### 1. Cloner le dépôt

```bash
git clone https://github.com/<org>/seadrop.git
cd seadrop
```

### 2. Créer l'environnement virtuel

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows PowerShell
```

### 3. Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Éditez `.env` :

```env
MEGA_EMAIL="votre@email.com"
MEGA_PASSWORD="votre_mot_de_passe"
MEGA_FOLDER="seadrop_uploads"
MAX_FILE_SIZE_MB=50
```

### 5. Lancer l'application

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Ouvrez [http://localhost:8000](http://localhost:8000).

---

## Variables d'environnement

### Obligatoires

| Variable | Description |
|----------|-------------|
| `MEGA_EMAIL` | Email du compte Mega.nz |
| `MEGA_PASSWORD` | Mot de passe du compte Mega.nz |

> ⚠️ L'application refuse de démarrer si ces variables sont absentes ou vides (`validate_config()` lève une `RuntimeError` au boot).

### Optionnelles

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MEGA_FOLDER` | Dossier de destination sur Mega.nz | `seadrop_uploads` |
| `MAX_FILE_SIZE_MB` | Taille maximale des fichiers acceptés (Mo) | `50` |

---

## Architecture

### Structure du projet

```
seadrop/
├── main.py            # Point d'entrée FastAPI (routing, validation, orchestration)
├── security.py        # Validation MIME + sanitization pikepdf
├── mega_client.py     # Client Mega.nz (upload, gestion dossier, temp file)
├── index.html         # Frontend drag-and-drop (Tailwind CSS)
├── requirements.txt   # Dépendances Python (versions épinglées)
├── Dockerfile         # Build multi-stage Docker
├── .dockerignore      # Exclusions contexte Docker (secrets, pycache…)
└── .env.example       # Template des variables d'environnement
```

### Cycle de vie d'un upload

```
Browser (FormData POST /upload)
         │
         ▼
main.py — upload_document()
    ├── Validation extension (.pdf)
    ├── Validation Content-Type header
    ├── Lecture bytes + check taille (rejet HTTP 413 si > MAX_FILE_SIZE_MB)
    │
    ├── security.sanitize_pdf(file_bytes)
    │       ├── magic.from_buffer() → vérification MIME application/pdf
    │       └── pikepdf.Pdf.open() → re-sérialisation → BytesIO propre
    │
    └── mega_client.upload_file_to_mega(filename, clean_stream)
            ├── login(MEGA_EMAIL, MEGA_PASSWORD)
            ├── find/create folder MEGA_FOLDER
            ├── NamedTemporaryFile → client.upload()
            └── cleanup garanti (finally + contextlib.suppress)
```

### Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/` | Sert `index.html` |
| `POST` | `/upload` | Dépose un PDF sanitisé vers Mega.nz |
| `GET` | `/docs` | Swagger UI (FastAPI auto-généré) |
| `GET` | `/openapi.json` | Schéma OpenAPI |

### Codes de réponse

| Code | Cas |
|------|-----|
| `200` | Upload réussi |
| `400` | Extension invalide, Content-Type incorrect, PDF corrompu |
| `413` | Fichier trop volumineux |
| `500` | Erreur interne inattendue |
| `502` | Échec de communication avec Mega.nz |

---

## Déploiement Docker

### Build

```bash
docker build -t seadrop:latest .
```

Le build utilise un stage multi-stage :
- **builder** — compile les dépendances Python dans `/app/venv`
- **final** — image minimale slim, `appuser` non-root, sans outil de build

### Vérification sécurité image

```bash
# Aucun secret ne doit apparaître dans l'image
docker inspect seadrop:latest | grep -i "MEGA"
# → résultat vide attendu
```

### Run

```bash
# Via --env-file (recommandé)
docker run --rm -p 8000:8000 --env-file .env seadrop:latest

# Via --env inline
docker run --rm -p 8000:8000 \
  --env MEGA_EMAIL="votre@email.com" \
  --env MEGA_PASSWORD="votre_mot_de_passe" \
  seadrop:latest
```

### Healthcheck

Le Dockerfile inclut un healthcheck automatique :

```
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3
```

Vérifiez l'état :

```bash
docker ps
# HEALTHY = application opérationnelle
# UNHEALTHY = vérifiez les logs avec docker logs <container_id>
```

---

## Sécurité

### Mesures implémentées

| Vecteur | Mitigation |
|---------|------------|
| Upload fichier non-PDF | Extension + Content-Type + magic bytes (triple check) |
| PDF malveillant (scripts, XFA) | Re-sérialisation pikepdf élimine les objets actifs |
| DoS par fichier géant | Rejet HTTP 413 configurable via `MAX_FILE_SIZE_MB` |
| Log injection | `_safe_filename()` nettoie `\n`/`\r`/`\t` avant tout log |
| Secrets dans l'image | `ENV MEGA_*` absent du Dockerfile |
| Secrets dans `docker inspect` | Secrets injectés uniquement en runtime |
| Build silencieusement cassé | `pip install` sans `|| true` — fail-fast garanti |
| Élévation de privilège | Conteneur tourne en tant que `appuser` (non-root, no shell) |
| Fuite infos système dans erreurs | Messages génériques exposés, détails dans les logs serveur |

### Bonnes pratiques en production

- Placez l'application derrière un reverse proxy (nginx / Traefik) avec TLS.
- N'exposez **jamais** `MEGA_PASSWORD` dans les logs CI/CD.
- Activez `AUTH` si l'application n'est pas destinée à être publique.
- Auditez régulièrement les dépendances : `pip-audit -r requirements.txt`.

---

## Dépannage

### `RuntimeError: Variables d'environnement manquantes`

L'application refuse de démarrer si `MEGA_EMAIL` ou `MEGA_PASSWORD` est vide.

```bash
# Vérifiez que .env est bien chargé
cat .env | grep MEGA
```

### `SanitizationError: Type MIME non autorisé`

Le fichier uploadé n'est pas reconnu comme PDF par libmagic, même s'il a l'extension `.pdf`. Vérifiez que le fichier n'est pas corrompu ou renommé à tort.

### `MegaClientError: Erreur lors de l'upload`

1. Vérifiez que les credentials Mega.nz sont corrects.
2. Vérifiez la connexion réseau depuis le conteneur.
3. Vérifiez que le dossier `MEGA_FOLDER` n'a pas de caractères spéciaux.

### `libmagic` introuvable (développement local)

```bash
# Debian / Ubuntu
sudo apt-get install libmagic1

# macOS
brew install libmagic

# Windows : utiliser python-magic-bin (déjà dans requirements.txt)
```

### Le fichier temporaire n'est pas supprimé

Un échec de suppression est ignoré silencieusement (`contextlib.suppress`) pour ne pas masquer l'erreur principale. Vérifiez les permissions sur `/tmp` si les fichiers s'accumulent.
