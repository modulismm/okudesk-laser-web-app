# Guide de dépannage

## Problème: Erreur lors de l'installation des dépendances

### Symptôme
```
error: subprocess-exited-with-error
× Getting requirements to build wheel did not run successfully.
```

### Solutions

#### 1. Utiliser Python 3.11 ou 3.12 (recommandé)

Le script `start.sh` détecte automatiquement Python 3.11/3.12. Si ce n'est pas le cas :

```bash
# Vérifier les versions disponibles
python3.11 --version
python3.12 --version

# Créer venv manuellement avec Python 3.11
cd backend
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 2. Mise à jour de pip/setuptools/wheel

```bash
cd backend
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 3. Installation minimale (sans numpy/Pillow)

Si numpy/Pillow continuent d'échouer, utilisez la version minimale :

```bash
cd backend
source venv/bin/activate
pip install -r requirements-minimal.txt
```

**Note:** Sans numpy/Pillow, certaines fonctionnalités (raster, thumbnails) ne fonctionneront pas, mais l'API de base fonctionnera.

#### 4. Installation manuelle des packages problématiques

```bash
# Installer numpy depuis source (peut prendre du temps)
pip install numpy --no-binary numpy

# Ou utiliser une version plus récente
pip install numpy>=1.26.0
```

## Problème: Backend ne démarre pas

### Port 5000 occupé (AirPlay sur macOS)

Le backend utilise maintenant le port **5001** par défaut pour éviter les conflits avec AirPlay Receiver.

Si le port 5001 est aussi occupé, le serveur trouvera automatiquement un port libre (5001-5010).

**Pour désactiver AirPlay Receiver:**
1. System Settings → General → AirDrop & Handoff
2. Désactiver "AirPlay Receiver"

### Vérifier que Flask est installé
```bash
cd backend
source venv/bin/activate
python -c "import flask; print(flask.__version__)"
```

### Vérifier les ports utilisés
```bash
# Vérifier si les ports sont utilisés
lsof -i :5001
lsof -i :5000
```

## Problème: Frontend ne peut pas se connecter au backend

### Vérifier CORS
Le backend doit avoir `CORS(app)` dans `app.py` (déjà présent).

### Vérifier l'URL de l'API
Dans `frontend/index.html`, vérifier :
```javascript
const API_URL = 'http://localhost:5000';
```

### Tester l'API manuellement
```bash
curl http://localhost:5000/api/health
```

Devrait retourner :
```json
{"status":"ok","message":"OKU Desk API is running","version":"0.1.0"}
```

## Problème: Import errors dans les scripts Python

### Vérifier le symlink nomadtech
```bash
cd backend-api-test
ls -la nomadtech
# Devrait montrer: nomadtech -> ../nomadtech
```

Si le symlink n'existe pas :
```bash
ln -s ../nomadtech nomadtech
```

## Problème: G-code generation not implemented

C'est normal ! Le service `gcode_service.py` doit être implémenté pour adapter les scripts Inkscape.

Voir `inkex_wrapper.py` pour la structure de base.
