# État d'avancement du projet

## ✅ Fonctionnel

- [x] Architecture backend API (Flask)
- [x] Frontend web (HTML/JS)
- [x] Communication API ↔ Frontend
- [x] Validation SVG
- [x] Health check API
- [x] Détection automatique de port
- [x] Gestion CORS
- [x] Service de frontend via Flask (`/app`)

## 🚧 En développement

- [ ] **Génération G-code vectoriel** - `gcode_service.py` à implémenter
- [ ] **Génération G-code raster** - Pas encore commencé
- [ ] **Wrapper Inkscape API** - Structure de base créée, à compléter

## 📋 Prochaines étapes

### 1. Implémenter `gcode_service.py`

Pour que la génération G-code fonctionne, il faut :

1. **Adapter `inkex_wrapper.py`** pour simuler complètement l'API Inkscape
   - Implémenter toutes les fonctions utilisées par les scripts Python
   - Parser SVG avec `lxml` au lieu de l'API Inkscape interne

2. **Extraire la logique** de `2.1_Nomadtech-OkuDesk_Contornos.py`
   - Identifier les parties qui génèrent le G-code
   - Adapter pour fonctionner avec le wrapper

3. **Tester** avec des SVG simples
   - Un rectangle
   - Un cercle
   - Des paths simples

### 2. Documentation

- [ ] Guide d'implémentation du wrapper
- [ ] Exemples de test
- [ ] Documentation API complète

## 🔍 Debugging

Si tu vois une erreur 500 sur `/api/generate-vector` :

1. **C'est normal** - Le service n'est pas encore implémenté
2. **Le message d'erreur** devrait maintenant être plus clair (501 Not Implemented)
3. **Pour tester la génération G-code**, utilise l'interface web pure : `oku-laser-interface/index.html`

## 📝 Notes

- Le backend API est une **architecture de test** pour voir si on peut réutiliser les scripts Python
- L'interface web pure (`oku-laser-interface/`) fonctionne déjà et génère du G-code
- L'objectif est de combiner les deux : interface web moderne + scripts Python validés
