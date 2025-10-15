import sqlite3
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
import json

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialise toutes les tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Table utilisateurs (admin, co-admin, gérant)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'co_admin', 'manager')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')
            
            # Table clients
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT NOT NULL,
                    telephone TEXT UNIQUE,
                    email TEXT,
                    date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    bonus_jeu INTEGER DEFAULT 0,
                    tickets_fidelite INTEGER DEFAULT 0,
                    derniere_visite TIMESTAMP,
                    statut TEXT DEFAULT 'actif'
                )
            ''')
            
            # Table postes/consoles
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS postes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero INTEGER UNIQUE NOT NULL,
                    nom TEXT NOT NULL,
                    type_console TEXT NOT NULL,
                    statut TEXT DEFAULT 'libre' CHECK(statut IN ('libre', 'occupe', 'maintenance')),
                    switch_port INTEGER,
                    icone TEXT DEFAULT 'console.png'
                )
            ''')
            
            # Table sessions de jeu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    poste_id INTEGER NOT NULL,
                    debut TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fin TIMESTAMP,
                    duree_payee INTEGER NOT NULL,
                    duree_bonus INTEGER DEFAULT 0,
                    montant_paye INTEGER NOT NULL,
                    statut TEXT DEFAULT 'en_cours' CHECK(statut IN ('en_cours', 'termine', 'expire')),
                    FOREIGN KEY (client_id) REFERENCES clients (id),
                    FOREIGN KEY (poste_id) REFERENCES postes (id)
                )
            ''')
            
            # Table configuration
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    cle TEXT PRIMARY KEY,
                    valeur TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            
        # Créer l'admin par défaut si n'existe pas
        self.create_default_admin()
    
    def create_default_admin(self):
        """Crée le compte admin par défaut"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if cursor.fetchone()[0] == 0:
                # Mot de passe par défaut: "admin123"
                password_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", password_hash.decode(), "admin")
                )
                conn.commit()
                print("✅ Compte admin créé - Username: admin, Password: admin123")
