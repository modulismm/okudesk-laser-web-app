# OKU Desk Backend API

Backend Python qui expose les scripts Inkscape comme API REST.

## Installation

```bash
cd backend
pip install -r requirements.txt
```

## Démarrage

```bash
python app.py
```

L'API sera accessible sur `http://localhost:5000`

## Endpoints

- `GET /api/health` - Health check
- `POST /api/generate-vector` - Génère G-code vectoriel depuis SVG
- `POST /api/generate-raster` - Génère G-code raster depuis image

## Architecture

```
Frontend (HTML/JS) → HTTP POST → Backend (Python) → Scripts Inkscape → G-code
```

## Adaptation nécessaire

Les scripts Python Inkscape doivent être adaptés pour fonctionner sans Inkscape :

1. **Créer un wrapper** qui simule l'API `inkex`
2. **Parser SVG** avec `lxml` au lieu de l'API Inkscape interne
3. **Extraire la logique** de génération G-code des scripts existants
