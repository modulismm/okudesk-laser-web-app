"""
Configuration pour le backend API
"""

# Port par défaut (5001 pour éviter conflit avec AirPlay sur macOS)
DEFAULT_PORT = 5001

# Ports à essayer si le port par défaut est occupé
PORT_RANGE = range(5001, 5011)
