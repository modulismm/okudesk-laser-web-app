#!/bin/bash
# Script de démarrage rapide pour le backend API

echo "🚀 Démarrage OKU Desk Backend API"
echo ""

cd "$(dirname "$0")/backend"

# Détecter la meilleure version de Python (3.11/3.12 préférés pour compatibilité)
PYTHON_CMD="python3"
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    echo "✅ Utilisation de Python 3.11 (meilleure compatibilité)"
elif command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    echo "✅ Utilisation de Python 3.12"
else
    echo "⚠️  Utilisation de Python 3.13 (peut avoir des problèmes avec numpy/Pillow)"
fi

# Vérifier si venv existe
if [ ! -d "venv" ]; then
    echo "📦 Création de l'environnement virtuel avec $PYTHON_CMD..."
    $PYTHON_CMD -m venv venv
fi

# Activer venv
echo "🔌 Activation de l'environnement virtuel..."
source venv/bin/activate

# Installer les dépendances
echo "📥 Installation des dépendances..."
echo "   (Mise à jour de pip/setuptools/wheel pour Python 3.13...)"
pip install --upgrade pip setuptools wheel

# Essayer d'installer les dépendances complètes
if pip install -q -r requirements.txt; then
    echo "✅ Toutes les dépendances installées"
else
    echo "⚠️  Installation complète échouée, installation minimale..."
    pip install -q -r requirements-minimal.txt
    echo "⚠️  Note: numpy et Pillow non installés (nécessaires pour le traitement d'images)"
fi

# Démarrer le serveur
echo ""
echo "✅ Démarrage du serveur API..."
echo "   Frontend: Ouvre frontend/index.html dans un navigateur"
echo "   API: http://localhost:5001 (ou port auto-détecté)"
echo "   Note: Port changé à 5001 pour éviter conflit avec AirPlay sur macOS"
echo ""
python app.py
