# Frontend - Interface Web OKU Desk

Interface web principale pour convertir des fichiers SVG en G-code.

## Fichiers

- **index.html** - Page principale de l'interface
- **style.css** - Styles CSS (dark mode, layout)
- **app.js** - Logique de l'application (file handling, UI, rendering)
- **svg-parser.js** - Parser SVG (extraction paths, couleurs, dimensions)
- **gcode-generator.js** - Générateur G-code (conversion SVG → G-code OKU Desk)

## Utilisation

Ouvrir `index.html` directement dans un navigateur moderne (pas besoin de serveur pour l'utilisation locale).

## Architecture

- **Parsing:** `svg-parser.js` extrait les données du SVG
- **Génération:** `gcode-generator.js` convertit en G-code
- **UI:** `app.js` gère l'interface et orchestre le tout

## Dépendances

Aucune dépendance externe requise (vanilla JavaScript).
