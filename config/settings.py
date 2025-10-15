import os
from pathlib import Path

# Dossier racine du projet
BASE_DIR = Path(__file__).parent.parent

# Base de données
DATABASE_PATH = BASE_DIR / "data" / "rdm_gsalle.db"

# Configuration des postes
MAX_POSTES = 20
DEFAULT_POSTES = 6

# Configuration réseau
API_HOST = "localhost"
API_PORT = 8000

# Sécurité
SECRET_KEY = "votre-clé-secrète-très-longue-et-complexe"

# Bonus par défaut
BONUS_BIENVENUE = 15  # minutes
BONUS_PAR_50_FCFA = 1  # minute

# Tarifs par défaut (FCFA)
TARIFS_DEFAULT = {
    "PS2": {50: 6, 100: 15, 200: 35},
    "PS3": {50: 5, 100: 12, 200: 30},
    "PS4": {50: 4, 100: 10, 200: 25},
    "PS5": {50: 3, 100: 8, 200: 20}
}
