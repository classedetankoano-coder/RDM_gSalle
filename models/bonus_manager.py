# models/bonus_manager.py
"""
Gestion des bonus (bonus de jeu, bonus de bienvenue, historique).
Utilise l'objet DatabaseManager de ton projet (qui doit fournir get_connection()).
"""

from datetime import datetime
import json
import traceback

def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_bonus_tables(db):
    """
    Crée les tables nécessaires si elles n'existent pas.
    db: instance de DatabaseManager (doit implémenter get_connection()).
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS client_bonus (
                    client_id INTEGER PRIMARY KEY,
                    balance_minutes INTEGER NOT NULL DEFAULT 0,
                    last_updated TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bonus_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    type TEXT,                -- 'accrual', 'use', 'welcome', 'manual', 'adjust'
                    minutes_change INTEGER,   -- positive = ajout, negative = utilisation
                    montant_fcfa INTEGER,     -- montant qui a déclenché l'accrual (si applicable)
                    source TEXT,              -- ex: 'session_start:12', 'admin_manual'
                    created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bonus_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    unit_amount INTEGER NOT NULL,  -- ex: 50 (FCFA)
                    unit_minutes INTEGER NOT NULL, -- ex: 1 (minute)
                    active INTEGER DEFAULT 1,
                    applies_to_group_id INTEGER,   -- NULL => règle globale, sinon id de console_groups
                    UNIQUE(name)
                )
            """)
            conn.commit()
    except Exception as e:
        print("[bonus_manager] ensure_bonus_tables error:", e)
        traceback.print_exc()

# ---------- Rules helpers ----------
def list_rules(db):
    """Retourne la liste des règles (globales et par groupe)."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, unit_amount, unit_minutes, active, applies_to_group_id FROM bonus_rules ORDER BY id")
            rows = cursor.fetchall()
            rules = []
            for r in rows:
                rules.append({
                    "id": r[0],
                    "name": r[1],
                    "unit_amount": int(r[2]),
                    "unit_minutes": int(r[3]),
                    "active": bool(r[4]),
                    "applies_to_group_id": r[5]
                })
            return rules
    except Exception as e:
        print("[bonus_manager] list_rules error:", e)
        traceback.print_exc()
        return []

def create_or_update_rule(db, name, unit_amount, unit_minutes, applies_to_group_id=None, active=1):
    """
    Crée ou met à jour une règle (par nom unique).
    Retourne le dict de la règle insérée / modifiée.
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # check existing by name
            cursor.execute("SELECT id FROM bonus_rules WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                rule_id = row[0]
                cursor.execute(
                    "UPDATE bonus_rules SET unit_amount = ?, unit_minutes = ?, applies_to_group_id = ?, active = ? WHERE id = ?",
                    (unit_amount, unit_minutes, applies_to_group_id, int(active), rule_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO bonus_rules (name, unit_amount, unit_minutes, active, applies_to_group_id) VALUES (?, ?, ?, ?, ?)",
                    (name, unit_amount, unit_minutes, int(active), applies_to_group_id)
                )
                rule_id = cursor.lastrowid
            conn.commit()
            return {"id": rule_id, "name": name, "unit_amount": unit_amount, "unit_minutes": unit_minutes, "active": bool(active), "applies_to_group_id": applies_to_group_id}
    except Exception as e:
        print("[bonus_manager] create_or_update_rule error:", e)
        traceback.print_exc()
        return None

def delete_rule(db, rule_id):
    """Supprime une règle par id."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bonus_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return True
    except Exception as e:
        print("[bonus_manager] delete_rule error:", e)
        traceback.print_exc()
        return False

def get_rule_for_group(db, group_id):
    """
    Règle spécifique au groupe (prioritaire).
    Retourne dict {unit_amount, unit_minutes} ou None.
    """
    try:
        if group_id is None:
            return None
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT unit_amount, unit_minutes FROM bonus_rules WHERE applies_to_group_id = ? AND active=1 ORDER BY id DESC LIMIT 1", (group_id,))
            row = cursor.fetchone()
            if row:
                return {"unit_amount": int(row[0]), "unit_minutes": int(row[1])}
    except Exception as e:
        print("[bonus_manager] get_rule_for_group error:", e)
        traceback.print_exc()
    return None

def get_global_bonus_rule(db):
    """Règle globale si aucune règle par groupe n'existe."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT unit_amount, unit_minutes FROM bonus_rules WHERE applies_to_group_id IS NULL AND active=1 ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return {"unit_amount": int(row[0]), "unit_minutes": int(row[1])}
    except Exception as e:
        print("[bonus_manager] get_global_bonus_rule error:", e)
        traceback.print_exc()
    # valeurs de secours
    return {"unit_amount": 50, "unit_minutes": 1}

# ---------- Core logic ----------
def compute_bonus_minutes(db, montant_fcfa, group_id=None):
    """
    Calcule les minutes de bonus à attribuer pour un montant donné.
    Priorité : règle group_id active > règle globale
    """
    try:
        rule = get_rule_for_group(db, group_id)
        if not rule:
            rule = get_global_bonus_rule(db)
        unit_amount = int(rule.get("unit_amount", 50))
        unit_minutes = int(rule.get("unit_minutes", 1))
        if unit_amount <= 0 or unit_minutes <= 0:
            return 0
        times = int(montant_fcfa) // unit_amount
        return int(times * unit_minutes)
    except Exception as e:
        print("[bonus_manager] compute_bonus_minutes error:", e)
        traceback.print_exc()
        return 0

def award_bonus_for_payment(db, client_id, montant_fcfa, source=None, group_id=None):
    """
    Attribue automatiquement des minutes bonus suite à un paiement.
    - client_id : identifiant du client (user)
    - montant_fcfa : montant payé (int)
    - source : texte libre, ex: 'session_start:5'
    - group_id : optionnel, priorise règle par groupe
    Retourne minutes attribuées (int).
    """
    try:
        minutes = compute_bonus_minutes(db, montant_fcfa, group_id=group_id)
        if minutes <= 0:
            return 0
        now = _now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO client_bonus (client_id, balance_minutes, last_updated) VALUES (?, ?, ?)", (client_id, 0, now))
            cursor.execute("UPDATE client_bonus SET balance_minutes = balance_minutes + ?, last_updated = ? WHERE client_id = ?", (minutes, now, client_id))
            cursor.execute("INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (client_id, 'accrual', minutes, int(montant_fcfa), source or 'payment', now))
            conn.commit()
        return minutes
    except Exception as e:
        print("[bonus_manager] award_bonus_for_payment error:", e)
        traceback.print_exc()
        return 0

def apply_bonus_to_session(db, client_id, minutes_to_use, session_id=None, source=None):
    """
    Utilise des minutes bonus pour une session (dédits).
    - minutes_to_use : valeur demandée (sera limitée au solde)
    - session_id : id optionnel de session (pour historisation)
    - source : texte optionnel
    Retourne minutes réellement utilisées.
    """
    try:
        now = _now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO client_bonus (client_id, balance_minutes, last_updated) VALUES (?, ?, ?)", (client_id, 0, now))
            cursor.execute("SELECT balance_minutes FROM client_bonus WHERE client_id = ?", (client_id,))
            row = cursor.fetchone()
            balance = int(row[0]) if row and row[0] is not None else 0
            use = int(minutes_to_use)
            if use > balance:
                use = balance
            if use <= 0:
                return 0
            cursor.execute("UPDATE client_bonus SET balance_minutes = balance_minutes - ?, last_updated = ? WHERE client_id = ?", (use, now, client_id))
            src = source or (f"session:{session_id}" if session_id else "manual_use")
            cursor.execute("INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (client_id, 'use', -use, None, src, now))
            conn.commit()
            return use
    except Exception as e:
        print("[bonus_manager] apply_bonus_to_session error:", e)
        traceback.print_exc()
        return 0

def award_welcome_bonus(db, client_id, welcome_minutes=15, force=False):
    """
    Attribue le bonus de bienvenue lors de la création du compte.
    - welcome_minutes : entier (par défaut 15)
    - force : si True, force l'ajout même si le client a déjà un solde > 0
    Retourne minutes ajoutées (0 si désactivé ou déjà traité).
    """
    try:
        if not welcome_minutes or int(welcome_minutes) <= 0:
            return 0
        now = _now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO client_bonus (client_id, balance_minutes, last_updated) VALUES (?, ?, ?)", (client_id, 0, now))
            if not force:
                # si le client a déjà des enregistrements welcome dans l'historique, ne pas réattribuer
                cursor.execute("SELECT COUNT(*) FROM bonus_history WHERE client_id = ? AND type = 'welcome'", (client_id,))
                if cursor.fetchone()[0] > 0:
                    return 0
            cursor.execute("UPDATE client_bonus SET balance_minutes = balance_minutes + ?, last_updated = ? WHERE client_id = ?", (int(welcome_minutes), now, client_id))
            cursor.execute("INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (client_id, 'welcome', int(welcome_minutes), None, 'registration', now))
            conn.commit()
            return int(welcome_minutes)
    except Exception as e:
        print("[bonus_manager] award_welcome_bonus error:", e)
        traceback.print_exc()
        return 0

# ---------- Utilities ----------
def get_client_bonus_balance(db, client_id):
    """Retourne le solde actuel de minutes bonus pour un client (int)."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance_minutes FROM client_bonus WHERE client_id = ?", (client_id,))
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        print("[bonus_manager] get_client_bonus_balance error:", e)
        traceback.print_exc()
        return 0

def get_bonus_history(db, client_id=None, limit=200):
    """
    Retourne l'historique des bonus.
    - si client_id fourni, filtre par client
    - limite le nombre d'entrées
    Retourne une liste de dicts (ordered desc).
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            if client_id is not None:
                cursor.execute("SELECT id, client_id, type, minutes_change, montant_fcfa, source, created_at FROM bonus_history WHERE client_id = ? ORDER BY created_at DESC, id DESC LIMIT ?", (client_id, int(limit)))
            else:
                cursor.execute("SELECT id, client_id, type, minutes_change, montant_fcfa, source, created_at FROM bonus_history ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),))
            rows = cursor.fetchall()
            out = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "client_id": r[1],
                    "type": r[2],
                    "minutes_change": int(r[3]) if r[3] is not None else 0,
                    "montant_fcfa": int(r[4]) if r[4] is not None else None,
                    "source": r[5],
                    "created_at": r[6]
                })
            return out
    except Exception as e:
        print("[bonus_manager] get_bonus_history error:", e)
        traceback.print_exc()
        return []

def grant_manual_bonus(db, client_id, minutes, reason="admin_manual"):
    """
    Ajoute manuellement des minutes à un client (utilisation admin).
    Retourne minutes ajoutées.
    """
    try:
        minutes = int(minutes)
        if minutes == 0:
            return 0
        now = _now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO client_bonus (client_id, balance_minutes, last_updated) VALUES (?, ?, ?)", (client_id, 0, now))
            cursor.execute("UPDATE client_bonus SET balance_minutes = balance_minutes + ?, last_updated = ? WHERE client_id = ?", (minutes, now, client_id))
            cursor.execute("INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (client_id, 'manual', minutes, None, reason, now))
            conn.commit()
            return minutes
    except Exception as e:
        print("[bonus_manager] grant_manual_bonus error:", e)
        traceback.print_exc()
        return 0

def adjust_client_bonus(db, client_id, new_balance, reason="admin_adjust"):
    """
    Ajuste explicitement le solde d'un client (set).
    Enregistre l'ajustement sous forme d'historique (difference).
    """
    try:
        now = _now_str()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO client_bonus (client_id, balance_minutes, last_updated) VALUES (?, ?, ?)", (client_id, 0, now))
            cursor.execute("SELECT balance_minutes FROM client_bonus WHERE client_id = ?", (client_id,))
            row = cursor.fetchone()
            old = int(row[0]) if row and row[0] is not None else 0
            diff = int(new_balance) - old
            cursor.execute("UPDATE client_bonus SET balance_minutes = ?, last_updated = ? WHERE client_id = ?", (int(new_balance), now, client_id))
            if diff != 0:
                cursor.execute("INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                               (client_id, 'adjust', diff, None, reason, now))
            conn.commit()
            return diff
    except Exception as e:
        print("[bonus_manager] adjust_client_bonus error:", e)
        traceback.print_exc()
        return 0
