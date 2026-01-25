# OKU Desk - Backend API Test

Sous-projet pour tester l'architecture **Frontend HTML/JS + Backend Python/Inkscape**.

## Architecture

```
frontend/          → Interface web (HTML/JS)
backend/           → API Python (Flask) + Scripts Inkscape
nomadtech/         → Scripts Python originaux (symlink)
```

## Installation

### Backend

**Note:** Python 3.13 peut avoir des problèmes avec numpy/Pillow. Si l'installation échoue, utilisez Python 3.11 ou 3.12.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Mise à jour de pip pour Python 3.13
pip install --upgrade pip setuptools wheel

# Installation des dépendances
pip install -r requirements.txt

# Si ça échoue, version minimale (sans numpy/Pillow)
pip install -r requirements-minimal.txt
```

**Alternative avec Python 3.11/3.12:**
```bash
# Installer Python 3.11 via Homebrew
brew install python@3.11

# Utiliser Python 3.11 pour le venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend

Aucune installation nécessaire, juste ouvrir `frontend/index.html` dans un navigateur.

## Démarrage

1. **Démarrer le backend** :
```bash
cd backend
source venv/bin/activate
python app.py
```

2. **Ouvrir le frontend** :
- **Option 1 (recommandé):** Ouvrir `http://localhost:5001/app` dans un navigateur (servi par Flask)
- **Option 2:** Ouvrir `frontend/index.html` directement dans un navigateur
- **Option 3:** Servir avec un serveur local : `python -m http.server 8080` puis `http://localhost:8080/frontend/index.html`

## Structure

```
backend-api-test/
├── README.md
├── backend/
│   ├── app.py              # API Flask
│   ├── requirements.txt
│   ├── inkex_wrapper.py    # Wrapper pour simuler Inkscape API
│   └── gcode_service.py   # Service de génération G-code
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── nomadtech/             # Symlink vers les scripts originaux
```

## Note sur le port

Le backend utilise le port **5001** par défaut (au lieu de 5000) pour éviter les conflits avec **AirPlay Receiver** sur macOS.

Si le port 5001 est aussi occupé, le serveur trouvera automatiquement un port libre entre 5001-5010.

**Pour désactiver AirPlay Receiver sur macOS:**
1. System Settings → General → AirDrop & Handoff
2. Désactiver "AirPlay Receiver"

## Accès rapide

Une fois le backend démarré :

- **API Info:** http://localhost:5001/
- **Health Check:** http://localhost:5001/api/health
- **Frontend:** http://localhost:5001/app

## Status

🚧 **En développement** - Architecture de test
