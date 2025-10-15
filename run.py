#!/usr/bin/env python3
"""
RDM gSalle - Système de Gestion de Salle de Jeux
Créé pour Joseph Tankoano
"""

import os
import sys
from pathlib import Path

# Ajouter le dossier du projet au path Python
sys.path.append(str(Path(__file__).parent))

from interfaces.login import LoginWindow
from config.settings import DATABASE_PATH

def main():
    print("🎮 RDM gSalle - Démarrage...")
    
    # Créer le dossier data s'il n'existe pas
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    
    # Lancer l'interface de connexion
    app = LoginWindow()
    app.run()

if __name__ == "__main__":
    main()
