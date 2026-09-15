# Structure du Projet

Organisation réelle du dépôt OKU Desk Laser Interface.

> **Mise à jour 2026-09-15.** La version précédente décrivait `docs/`, `examples/`, `firmware/` et
> `nomadtech/` comme des dossiers du projet. Ils ne sont **pas distribués** dans le dépôt (exclus
> via `.gitignore`), ce qui rendait ce fichier trompeur pour quiconque clonait le projet.

## Vue d'ensemble

```
okudesk-laser-web-app/
├── frontend/                  # Interface web (aucun build, JS classique)
├── backend-api-test/          # ⚠️ LE VRAI BACKEND, malgré son nom
│   └── backend/               # Flask + moteur G-code + tests
├── backend/                   # Squelette obsolète — toutes les routes renvoient 501
├── raster-prototype/          # Troisième copie de la logique raster, non utilisée
├── deploy/                    # Docker + exemple de vhost nginx
├── Dockerfile                 # Image de production (python:3.12-slim + gunicorn)
├── docker-compose.yml         # Déploiement
├── pytest.ini
├── README.md · STRUCTURE.md · CREDITS.md · OPEN_SOURCE_RESEARCH.md
└── .gitignore
```

### ⚠️ Pièges à connaître

- **Le backend déployé est `backend-api-test/backend/`**, pas `backend/`. Le `Dockerfile` et
  `docker-compose.yml` pointent vers le premier. Le dossier `backend/` racine est un squelette
  dont toutes les routes renvoient `501` — il est conservé pour l'historique, pas exécuté.
- `raster-prototype/` est une troisième implémentation de la logique raster, non utilisée par
  l'application.
- Le nettoyage de ces deux dossiers est une tâche ouverte.

---

## Détails par dossier

### `/frontend/`

Interface web servie statiquement par Flask. Pas de build, pas de framework.

- `index.html` — application principale (mode vecteur)
- `style.css` — thème sombre, mise en page
- `app.js` — logique applicative : état, zoom/pan, placement, appels API
- `svg-parser.js` — parsing SVG → liste de jobs par couleur.
  **Doit rester cohérent avec `gcode_service._element_color()` et `_extract_drawables()`** :
  une couleur détectée ici mais non résolue côté serveur produit un job qui ne coupe rien.
- `gcode-generator.js` — moteur G-code client historique. **N'est plus utilisé pour produire les
  fichiers de découpe** (il ignore les transforms de groupe et plusieurs commandes de chemin) ;
  la génération passe toujours par le backend.
- `toolpath-preview.js` — rendu du parcours à partir du G-code réellement émis
- `raster.html` — page raster (rasterise les SVG dans le navigateur avant envoi)
- `fonts/` — Inter et JetBrains Mono auto-hébergées

---

### `/backend-api-test/backend/` — le backend réel

- `app.py` — routes Flask, sert aussi `frontend/`
- `gcode_service.py` — moteur SVG → G-code (vecteur et raster)
- `inkex_wrapper.py` — utilitaires hérités des extensions Inkscape
- `requirements.txt` — Flask, lxml, Pillow, numpy, gunicorn
- `tests/` — suite pytest (82 tests) :
  - `test_golden_files.py` — SVG de référence → `.gco` attendu
  - `test_laser_safety.py`, `test_disabled_jobs.py` — garde-fous sécurité laser
  - `test_transforms.py`, `test_path_to_points.py`, `test_svg_traversal.py`
  - `test_custom_origin.py`, `test_toolpath_optimization.py`
  - `test_raster_input_validation.py`, `test_gcode_dialect_contract.py`
  - `benchmark_toolpath.py` — mesure trajet à vide / distance de coupe avant-après
- `start.sh` — lancement en développement

---

### `/deploy/`

- `DEPLOY_DOCKER_NGINX.md` — instructions de déploiement
- `nginx-bouh.space.conf` — exemple de vhost

---

## Dossiers non distribués

Exclus via `.gitignore`, présents seulement dans les copies de travail :

| Dossier | Contenu | Raison |
|---|---|---|
| `nomadtech/` | scripts Inkscape NomadTech d'origine | référence, licence tierce |
| `firmware/` | binaire firmware de la machine | binaire volumineux |
| `examples/` | SVG/G-code de test | remplacé par `backend-api-test/backend/tests/fixtures/` |
| `docs/` | notes de rétro-ingénierie | jamais publiées |

Le `README.md` ne doit donc pas renvoyer vers `docs/` : ces fichiers n'existent pas pour un
utilisateur qui clone le dépôt.

---

## Navigation rapide

| Besoin | Chemin |
|---|---|
| Lancer l'application | `backend-api-test/start.sh`, ou `docker compose up -d --build` |
| Modifier le moteur G-code | `backend-api-test/backend/gcode_service.py` |
| Modifier l'interface | `frontend/app.js`, `frontend/style.css` |
| Lancer les tests | `python -m pytest` depuis la racine |
| Mesurer l'optimisation | `backend-api-test/backend/tests/benchmark_toolpath.py` |
