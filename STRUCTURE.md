# Structure du Projet

Documentation de l'organisation du projet OKU Desk Laser Interface.

## Vue d'ensemble

```
oku-laser-interface/
├── frontend/              # Interface web principale
├── docs/                  # Documentation complète
├── examples/              # Fichiers de test et exemples
├── firmware/              # Firmware de la machine
├── nomadtech/             # Scripts Python originaux (Inkscape)
├── backend/               # Backend API (exemple)
├── backend-api-test/      # Sous-projet backend API REST
├── README.md              # Documentation principale
├── STRUCTURE.md           # Ce fichier
└── .gitignore            # Fichiers à ignorer par Git
```

## Détails par dossier

### `/frontend/`

Interface web principale pour convertir SVG en G-code.

**Fichiers:**
- `index.html` - Page principale de l'interface
- `style.css` - Styles CSS (dark mode, layout)
- `app.js` - Logique de l'application
- `svg-parser.js` - Parser SVG
- `gcode-generator.js` - Générateur G-code
- `README.md` - Documentation du frontend

**Utilisation:** Ouvrir `index.html` directement dans un navigateur.

---

### `/docs/`

Documentation complète du projet.

**Fichiers:**
- `README.md` - Index de la documentation
- `README_REFERENCE.md` - Guide de navigation
- `REFERENCE_DOCUMENTATION.md` - Documentation de référence complète
- `TECHNICAL_IMPLEMENTATION_GUIDE.md` - Guide d'implémentation
- `IMPLEMENTATION_COMPARISON.md` - Comparaison Python vs Web
- `OPEN_SOURCE_RESEARCH.md` - Recherche solutions open-source
- `DOCUMENTATION_SUMMARY.md` - Résumé exécutif

**Utilisation:** Commencer par `README.md` ou `README_REFERENCE.md`.

---

### `/examples/`

Fichiers de test et exemples.

**Contenu:**
- Fichiers SVG de test (`*.svg`)
- Fichiers G-code générés (`*.gco`)
- Exemple frontend API (`frontend-api-example.html`)

**Utilisation:** Pour tester le parser SVG et valider la génération G-code.

---

### `/firmware/`

Firmware de la machine OKU Desk.

**Fichiers:**
- `firmware_okudesk.bin` - Firmware binaire
- `README.md` - Documentation du firmware

**Note:** Le firmware a été analysé pour identifier le type (Smoothieware modifié).

---

### `/nomadtech/`

Scripts Python originaux pour Inkscape.

**Fichiers:**
- `2.1_Nomadtech-OkuDesk_Contornos.py` - Génération Vector
- `2.1_Nomadtech-OkuDesk_Raster.py` - Génération Raster
- `2.1_Nomadtech-OkuDesk_Contornos.inx` - Interface Inkscape
- `2.1_Nomadtech-OkuDesk_Raster.inx` - Interface Inkscape
- `translations.py` - Traductions
- `logo.svg` - Logo

**Note:** Ces scripts sont la référence pour comprendre le format G-code OKU Desk.

---

### `/backend/`

Backend API exemple (première version).

**Fichiers:**
- `app.py` - Application Flask
- `requirements.txt` - Dépendances Python
- `README.md` - Documentation

**Note:** Version simplifiée, voir `/backend-api-test/` pour la version complète.

---

### `/backend-api-test/`

Sous-projet backend API REST complet.

**Structure:**
- `backend/` - Application Flask avec routes API
- `frontend/` - Frontend adapté pour API
- `start.sh` - Script de démarrage
- `README.md` - Documentation complète
- `QUICK_START.md` - Guide de démarrage rapide
- `TROUBLESHOOTING.md` - Guide de dépannage
- `STATUS.md` - Statut du projet

**Utilisation:** Voir `README.md` dans ce dossier.

---

## Fichiers racine

- **README.md** - Documentation principale du projet
- **STRUCTURE.md** - Ce fichier (documentation de l'organisation)
- **.gitignore** - Fichiers à ignorer par Git

---

## Navigation rapide

### Pour utiliser l'interface
→ `frontend/index.html`

### Pour comprendre le système
→ `docs/README_REFERENCE.md`

### Pour implémenter des améliorations
→ `docs/TECHNICAL_IMPLEMENTATION_GUIDE.md`

### Pour tester
→ `examples/` (fichiers SVG et G-code)

### Pour contribuer
→ `docs/IMPLEMENTATION_COMPARISON.md` (liste des améliorations)

---

## Historique de l'organisation

**Date:** 2026-01-24  
**Version:** v1.0

Cette structure a été organisée pour :
- Séparer clairement les différents composants
- Faciliter la navigation et la maintenance
- Préparer pour la publication open-source
- Améliorer la lisibilité du projet

---

## Notes

- Les dossiers `venv/` et `__pycache__/` sont ignorés par Git (voir `.gitignore`)
- Les fichiers de documentation sont en Markdown pour faciliter la lecture
- Chaque dossier principal a son propre `README.md` pour la documentation locale
