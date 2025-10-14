# app/bonus_simple.py
"""
Gestion du système "Bonus Simples" :
- Table bonus_transactions (migration incluse)
- Calcul automatique: 1 minute pour X FCFA (configurable)
- Bonus de bienvenue automatique (configurable)
- Historique / consultation / utilisation / admin credit/debit

Usage:
    from app.bonus_simple import BonusManager
    bm = BonusManager()             # utilise DATABASE_PATH via config.settings
    bm.run_migrations()             # à appeler une fois au démarrage
    bm.grant_bonus_on_payment(user_id=1, amount_fcfa=2000, payment_id="pay_123")
    balance = bm.get_bonus_balance(user_id=1)
    bm.use_bonus_for_session(user_id=1, minutes_to_use=10, session_id="sess_45")
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import math

# adapte l'import suivant à ta structure (comme dans admin_interface.py)
from models.database import DatabaseManager
from config.settings import DATABASE_PATH


class BonusManager:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db if db is not None else DatabaseManager(DATABASE_PATH)

    # ---------------- Migration / SQL ----------------
    def run_migrations(self) -> None:
        """
        Crée la table bonus_transactions et l'index, et initialise les clés config par défaut.
        Appeler au démarrage de l'application.
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS bonus_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            minutes_delta INTEGER NOT NULL,
            source TEXT NOT NULL,
            reference TEXT,
            created_at TEXT NOT NULL,
            operator_id INTEGER,
            notes TEXT
        );
        """
        create_index_sql = """
        CREATE INDEX IF NOT EXISTS idx_bonus_user ON bonus_transactions(user_id);
        """
        default_configs = {
            "bonus_enabled": "1",
            "bonus_fcfa_per_minute": "50",           # 50 FCFA -> 1 minute (par défaut)
            "bonus_min_unit_minutes": "1",
            "bonus_rounding": "floor",               # floor | ceil | none
            "bonus_apply_on": json.dumps(["achats", "prolongations", "recharges"]),
            "welcome_bonus_enabled": "1",
            "welcome_bonus_minutes": "15"
        }
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                # ensure config table exists (pattern used ailleurs)
                cur.execute("CREATE TABLE IF NOT EXISTS config (cle TEXT PRIMARY KEY, valeur TEXT)")
                cur.execute(create_table_sql)
                cur.execute(create_index_sql)
                # insert defaults if absent
                for k, v in default_configs.items():
                    cur.execute("SELECT valeur FROM config WHERE cle = ?", (k,))
                    if cur.fetchone() is None:
                        cur.execute("INSERT INTO config (cle, valeur) VALUES (?, ?)", (k, v))
                conn.commit()
        except Exception as e:
            # nève pas lever ici, log simplement - caller peut catcher
            raise RuntimeError(f"run_migrations failed: {e}")

    # ---------------- Config helpers (utilise la table config existante) ----------------
    def _get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT valeur FROM config WHERE cle = ?", (key,))
                row = cur.fetchone()
                return row[0] if row else default
        except Exception:
            return default

    def _set_config(self, key: str, value: str) -> None:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (key, value))
            conn.commit()

    # ---------------- Calcul / règles ----------------
    def compute_bonus_from_amount(self, amount_fcfa: int) -> int:
        """
        Retourne le nombre de minutes créditées pour un montant donné, selon la config.
        Respecte l'arrondi configuré (floor/ceil/none -> floor by default).
        """
        if amount_fcfa <= 0:
            return 0
        try:
            fcfa_per_min = int(self._get_config("bonus_fcfa_per_minute", "50") or 50)
        except Exception:
            fcfa_per_min = 50
        if fcfa_per_min <= 0:
            return 0
        try:
            rounding = (self._get_config("bonus_rounding", "floor") or "floor").lower()
        except Exception:
            rounding = "floor"
        raw = amount_fcfa / fcfa_per_min
        if rounding == "ceil":
            minutes = int(math.ceil(raw))
        elif rounding == "none":
            # prise en compte des décimales mais on renvoie un entier (on garde floor comme fallback)
            minutes = int(raw)
        else:
            # floor par défaut
            minutes = int(math.floor(raw))
        min_unit = int(self._get_config("bonus_min_unit_minutes", "1") or 1)
        if min_unit <= 1:
            return max(0, minutes)
        # appliquer unité minimale (ex: 5 minutes)
        if minutes <= 0:
            return 0
        # arrondir aux unités
        units = minutes // min_unit
        return units * min_unit

    # ---------------- Grant on payment ----------------
    def grant_bonus_on_payment(
        self,
        user_id: int,
        amount_fcfa: int,
        payment_id: Optional[str] = None,
        operator_id: Optional[int] = None,
        source_override: Optional[str] = None
    ) -> int:
        """
        Calcule et crédite automatiquement les minutes pour un paiement.
        Retourne le nombre de minutes ajoutées (0 si désactivé ou si montant insuffisant).
        - Vérifie la config 'bonus_enabled' (1/0).
        - Utilise 'bonus_apply_on' si besoin (mais on suppose que l'appelant indique s'il s'agit d'un paiement).
        """
        try:
            enabled = self._get_config("bonus_enabled", "1")
            if enabled not in (None, "", "1", 1):
                # si explicitement "0" -> disabled
                if str(enabled) == "0":
                    return 0
        except Exception:
            pass

        minutes = self.compute_bonus_from_amount(amount_fcfa)
        if minutes <= 0:
            return 0

        now = datetime.utcnow().isoformat()
        source = source_override or "payment"
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO bonus_transactions
                       (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, minutes, source, str(payment_id) if payment_id else None, now, operator_id, None)
                )
                conn.commit()
            return minutes
        except Exception as e:
            raise RuntimeError(f"grant_bonus_on_payment failed: {e}")

    # ---------------- Welcome bonus ----------------
    def apply_welcome_bonus_on_registration(self, user_id: int, operator_id: Optional[int] = None) -> int:
        """
        Applique le bonus de bienvenue si activé et si jamais attribué auparavant.
        Retourne minutes ajoutées (0 si déjà attribué ou désactivé).
        """
        try:
            enabled = self._get_config("welcome_bonus_enabled", "1")
            if str(enabled) == "0":
                return 0
        except Exception:
            pass

        try:
            welcome_minutes = int(self._get_config("welcome_bonus_minutes", "15") or 15)
        except Exception:
            welcome_minutes = 15
        if welcome_minutes <= 0:
            return 0

        # vérifier s'il y a déjà une transaction source='welcome' pour cet user
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(1) FROM bonus_transactions WHERE user_id = ? AND source = 'welcome'", (user_id,))
                row = cur.fetchone()
                if row and row[0] > 0:
                    return 0
                # sinon insérer
                now = datetime.utcnow().isoformat()
                cur.execute(
                    """INSERT INTO bonus_transactions
                       (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
                       VALUES (?, ?, 'welcome', ?, ?, ?, ?)""",
                    (user_id, welcome_minutes, None, now, operator_id, "welcome bonus automatique")
                )
                conn.commit()
            return welcome_minutes
        except Exception as e:
            raise RuntimeError(f"apply_welcome_bonus_on_registration failed: {e}")

    # ---------------- Use bonus for session ----------------
    def get_bonus_balance(self, user_id: int) -> int:
        """
        Retourne la somme des minutes (solde) pour l'utilisateur.
        """
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT SUM(minutes_delta) FROM bonus_transactions WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            raise RuntimeError(f"get_bonus_balance failed: {e}")

    def use_bonus_for_session(self, user_id: int, minutes_to_use: int, session_id: Optional[str] = None, operator_id: Optional[int] = None) -> bool:
        """
        Consume minutes pour une session (insère une transaction négative).
        Lève ValueError en cas de solde insuffisant ou d'arguments invalides.
        """
        if minutes_to_use <= 0:
            raise ValueError("minutes_to_use doit être > 0")
        balance = self.get_bonus_balance(user_id)
        if minutes_to_use > balance:
            raise ValueError("Solde insuffisant")
        now = datetime.utcnow().isoformat()
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO bonus_transactions
                       (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
                       VALUES (?, ?, 'session_use', ?, ?, ?, ?)""",
                    (user_id, -minutes_to_use, str(session_id) if session_id else None, now, operator_id, None)
                )
                conn.commit()
            return True
        except Exception as e:
            raise RuntimeError(f"use_bonus_for_session failed: {e}")

    # ---------------- Admin credit / debit ----------------
    def admin_credit(self, user_id: int, minutes: int, operator_id: Optional[int], notes: Optional[str] = None) -> None:
        if minutes <= 0:
            raise ValueError("minutes doit être > 0")
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO bonus_transactions
                   (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
                   VALUES (?, ?, 'admin', ?, ?, ?, ?)""",
                (user_id, minutes, None, now, operator_id, notes)
            )
            conn.commit()

    def admin_debit(self, user_id: int, minutes: int, operator_id: Optional[int], notes: Optional[str] = None) -> None:
        if minutes <= 0:
            raise ValueError("minutes doit être > 0")
        balance = self.get_bonus_balance(user_id)
        if minutes > balance:
            raise ValueError("Solde insuffisant pour débit admin")
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO bonus_transactions
                   (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
                   VALUES (?, ?, 'admin', ?, ?, ?, ?)""",
                (user_id, -minutes, None, now, operator_id, notes)
            )
            conn.commit()

    # ---------------- Historique / listing ----------------
    def list_bonus_history(self, user_id: Optional[int] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Retourne l'historique (par défaut trié DESC) avec solde recalculé pour chaque ligne.
        Pour inclure solde_after, on récupère les transactions asc, calcule cumul et renvoie en ordre DESC.
        """
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                params = []
                where = ""
                if user_id is not None:
                    where = "WHERE user_id = ?"
                    params.append(user_id)
                # récupérer en ASC pour calcul du solde progressif
                sql = f"SELECT id, user_id, minutes_delta, source, reference, created_at, operator_id, notes FROM bonus_transactions {where} ORDER BY created_at ASC, id ASC"
                cur.execute(sql, params)
                rows = cur.fetchall()
                # calculer solde_progressif
                history = []
                running = 0
                for r in rows:
                    running += int(r[2] or 0)
                    history.append({
                        "id": r[0],
                        "user_id": r[1],
                        "minutes_delta": int(r[2] or 0),
                        "source": r[3],
                        "reference": r[4],
                        "created_at": r[5],
                        "operator_id": r[6],
                        "notes": r[7],
                        "balance_after": running
                    })
                # retourner en DESC avec limit/offset
                history_desc = list(reversed(history))
                start = offset
                end = offset + limit
                return history_desc[start:end]
        except Exception as e:
            raise RuntimeError(f"list_bonus_history failed: {e}")
