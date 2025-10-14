# app/tickets_fidelite.py
"""
Tickets de fidélité - module complet

Fonctionnalités :
- run_migrations() : crée les tables nécessaires et insère configs par défaut.
- record_ticket_if_eligible(user_id, amount_fcfa, session_id=None, operator_id=None) :
    enregistre 1 ticket pour la date locale si le montant >= seuil et si pas déjà de ticket pour ce jour.
- _process_rewards_for_user(user_id) : calcule et attribue les récompenses 7j, 14j et JF30.
- admin_add_ticket / admin_revoke_ticket : pour intervention manuelle.
- list_tickets / list_grants / get_user_progress : utilitaires pour UI & debug.
- Intégration avec BonusManager (si présent) pour créditer minutes automatiquement.

Usage minimal :
    from app.tickets_fidelite import TicketsManager
    tm = TicketsManager()
    tm.run_migrations()
    tm.record_ticket_if_eligible(user_id=1, amount_fcfa=200)
"""

from datetime import datetime, timedelta, timezone, date
import json
import sqlite3
import os
import math
from typing import Optional, List, Dict, Any

# Try to import project's DatabaseManager and BonusManager; if unavailable, use fallbacks.
try:
    from models.database import DatabaseManager
except Exception:
    DatabaseManager = None

try:
    from app.bonus_simple import BonusManager
except Exception:
    BonusManager = None


# ----------- Fallback simple DB manager if project's DatabaseManager is absent -----------
class _SimpleDBManager:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        # create directory if needed
        if path != ":memory:":
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        return conn


# ----------- TicketsManager -----------
class TicketsManager:
    def __init__(self, db: Optional[Any] = None, db_path: Optional[str] = None, bonus_manager: Optional[Any] = None, local_tz: str = "Africa/Ouagadougou"):
        """
        db: either an instance of DatabaseManager (with .get_connection()) or None
        db_path: if db is None, you can specify a sqlite file path
        bonus_manager: instance of BonusManager (optional)
        """
        if db is None:
            if DatabaseManager and db_path is None:
                try:
                    # try to import project config settings
                    from config.settings import DATABASE_PATH
                    db_path = DATABASE_PATH
                except Exception:
                    db_path = db_path or ":memory:"
            db_obj = None
            if DatabaseManager and db_path is not None and db_path != ":memory:":
                try:
                    db_obj = DatabaseManager(db_path)
                except Exception:
                    db_obj = _SimpleDBManager(db_path or ":memory:")
            else:
                db_obj = _SimpleDBManager(db_path or ":memory:")
            self.db = db_obj
        else:
            self.db = db
        # BonusManager
        if bonus_manager is not None:
            self.bonus_manager = bonus_manager
        else:
            if BonusManager:
                try:
                    # try reuse same DB if possible
                    self.bonus_manager = BonusManager(self.db)
                except Exception:
                    try:
                        self.bonus_manager = BonusManager()
                    except Exception:
                        self.bonus_manager = None
            else:
                self.bonus_manager = None
        self.local_tz = local_tz

    # ---------------- Migrations ----------------
    def run_migrations(self) -> None:
        """
        Crée les tables nécessaires (tickets_fidelite, fidelity_sequences, fidelity_reward_grants)
        et insère les configurations par défaut dans la table 'config' (si elle existe ou sera créée).
        """
        create_tickets = """
        CREATE TABLE IF NOT EXISTS tickets_fidelite (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticket_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            session_id TEXT,
            amount_fcfa INTEGER,
            sequence_id INTEGER,
            expired INTEGER DEFAULT 0,
            notes TEXT
        );
        """
        create_seq = """
        CREATE TABLE IF NOT EXISTS fidelity_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        create_grants = """
        CREATE TABLE IF NOT EXISTS fidelity_reward_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            grant_type TEXT NOT NULL,
            tickets_count INTEGER NOT NULL,
            minutes_awarded INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expiry_at TEXT,
            source_reference TEXT,
            used INTEGER DEFAULT 0,
            notes TEXT
        );
        """
        idx_tickets = "CREATE INDEX IF NOT EXISTS idx_tickets_user_date ON tickets_fidelite(user_id, ticket_date);"
        idx_grants = "CREATE INDEX IF NOT EXISTS idx_reward_user ON fidelity_reward_grants(user_id);"
        default_configs = {
            "fidelity_enabled": "1",
            "fidelity_threshold_fcfa": "100",
            "fidelity_window_days_7": "7",
            "fidelity_window_days_14": "14",
            "fidelity_window_days_30": "30",
            "fidelity_rewards_7d": json.dumps([{"tickets":3,"minutes":15},{"tickets":4,"minutes":30},{"tickets":5,"minutes":35},{"tickets":6,"minutes":40},{"tickets":7,"minutes":50}]),
            "fidelity_rewards_14d": json.dumps([{"tickets":8,"add_minutes":5},{"tickets":9,"add_minutes":5},{"tickets":10,"add_minutes":10},{"tickets":11,"add_minutes":5},{"tickets":12,"add_minutes":5},{"tickets":13,"add_minutes":10},{"tickets":14,"add_minutes":15}]),
            "fidelity_jf30_min_tickets": "12",
            "fidelity_jf30_per_ticket_minutes": "2",
            "fidelity_jf30_expiry_days": "10"
        }
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                # ensure config table exists
                cur.execute("CREATE TABLE IF NOT EXISTS config (cle TEXT PRIMARY KEY, valeur TEXT)")
                cur.execute(create_tickets)
                cur.execute(create_seq)
                cur.execute(create_grants)
                cur.execute(idx_tickets)
                cur.execute(idx_grants)
                # insert defaults if absent
                for k, v in default_configs.items():
                    cur.execute("SELECT valeur FROM config WHERE cle = ?", (k,))
                    if cur.fetchone() is None:
                        cur.execute("INSERT INTO config (cle, valeur) VALUES (?, ?)", (k, v))
                conn.commit()
        except Exception as e:
            raise RuntimeError(f"run_migrations failed: {e}")

    # ---------------- Config helpers ----------------
    def _get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT valeur FROM config WHERE cle = ?", (key,))
                r = cur.fetchone()
                if r:
                    # r may be Row or tuple
                    return r[0] if isinstance(r, (list, tuple)) else r[0]
        except Exception:
            pass
        return default

    def _set_config(self, key: str, value: str) -> None:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (key, value))
            conn.commit()

    def _get_config_json(self, key: str, default=None):
        raw = self._get_config(key, None)
        if raw is None:
            return default if default is not None else []
        try:
            return json.loads(raw)
        except Exception:
            return default if default is not None else []

    # ---------------- Date util ----------------
    def _today_local_str(self) -> str:
        """Return local date string 'YYYY-MM-DD' using local_tz if possible."""
        try:
            from zoneinfo import ZoneInfo
            d = datetime.now(tz=ZoneInfo(self.local_tz)).date()
        except Exception:
            # fallback: use UTC date (acceptable)
            d = datetime.utcnow().date()
        return d.isoformat()

    # ---------------- Sequence helpers ----------------
    def _get_active_sequence(self, user_id: int) -> Optional[int]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM fidelity_sequences WHERE user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1", (user_id,))
            r = cur.fetchone()
            return (r[0] if r else None) if isinstance(r, (list, tuple, sqlite3.Row)) else None

    def _create_sequence(self, user_id: int, start_date: str) -> int:
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO fidelity_sequences (user_id, start_date, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
                        (user_id, start_date, now, now))
            conn.commit()
            return cur.lastrowid

    def _update_sequence_status(self, sequence_id: int, status: str):
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE fidelity_sequences SET status = ?, updated_at = ? WHERE id = ?", (status, now, sequence_id))
            conn.commit()

    # ---------------- Core: record ticket ----------------
    def record_ticket_if_eligible(self, user_id: int, amount_fcfa: int, session_id: Optional[str] = None, operator_id: Optional[int] = None, force: bool = False) -> bool:
        """
        Enregistre 1 ticket pour la date locale si :
         - système activé
         - amount_fcfa >= threshold
         - l'utilisateur n'a pas déjà eu un ticket pour cette date (sauf force=True)
        Retourne True si un ticket a été inséré.
        """
        enabled = str(self._get_config("fidelity_enabled", "1") or "1")
        if enabled == "0" and not force:
            return False
        try:
            threshold = int(self._get_config("fidelity_threshold_fcfa", "100") or 100)
        except Exception:
            threshold = 100
        if amount_fcfa < threshold and not force:
            return False

        ticket_date = self._today_local_str()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # vérifier existence ticket du jour non-expiré
            cur.execute("SELECT id FROM tickets_fidelite WHERE user_id = ? AND ticket_date = ? AND expired = 0", (user_id, ticket_date))
            if cur.fetchone() and not force:
                return False
            # trouver ou créer sequence active
            seq_id = self._get_active_sequence(user_id)
            if not seq_id:
                seq_id = self._create_sequence(user_id, ticket_date)
            now = datetime.utcnow().isoformat()
            cur.execute("INSERT INTO tickets_fidelite (user_id, ticket_date, created_at, source, session_id, amount_fcfa, sequence_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (user_id, ticket_date, now, 'auto' if not operator_id else 'manual', session_id, amount_fcfa if amount_fcfa is not None else None, seq_id))
            conn.commit()
            ticket_id = cur.lastrowid

        # after insertion, process rewards for this user (sync)
        try:
            self._process_rewards_for_user(user_id, sequence_id=seq_id)
        except Exception:
            # avoid raising to caller
            pass
        return True

    # ---------------- Process rewards ----------------
    def _process_rewards_for_user(self, user_id: int, sequence_id: Optional[int] = None) -> None:
        """
        Calcul et attribution des récompenses selon :
         - 7 jours : barème principal (fidelity_rewards_7d)
         - 14 jours : add_minutes (fidelity_rewards_14d) uniquement si la séquence initiale a été validée (au moins 3 tickets dans 7 premiers jours)
         - JF30 : si tickets >= threshold sur 30 jours -> minutes = per_ticket * tickets, expiry according to config
        Le système enregistre chaque récompense dans fidelity_reward_grants et crédite les minutes via BonusManager si présent.
        """
        # load tickets non-expired
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ticket_date FROM tickets_fidelite WHERE user_id = ? AND expired = 0 ORDER BY ticket_date ASC", (user_id,))
            rows = cur.fetchall()
            # normalize ticket_dates to list of strings
            ticket_dates = []
            for r in rows:
                if isinstance(r, (list, tuple)):
                    ticket_dates.append(r[0])
                elif isinstance(r, sqlite3.Row):
                    ticket_dates.append(r["ticket_date"])
                else:
                    # fallback assume first element
                    ticket_dates.append(r[0])

        if not ticket_dates:
            return

        # helper: count tickets in sliding window ending at end_date (inclusive)
        def count_in_window(end_date_str: str, days: int) -> int:
            end = datetime.fromisoformat(end_date_str).date()
            start = end - timedelta(days=days - 1)
            return sum(1 for d in ticket_dates if start <= datetime.fromisoformat(d).date() <= end)

        # ---- 7-day reward ----
        rewards_7d = self._get_config_json("fidelity_rewards_7d", [])
        # consider last ticket_date as window end
        last_date = ticket_dates[-1]
        cnt7 = count_in_window(last_date, 7)
        # find highest applicable reward (largest tickets <= cnt7)
        applicable_7d = None
        for r in sorted(rewards_7d, key=lambda x: x.get("tickets", 0)):
            if cnt7 >= int(r.get("tickets", 0)):
                applicable_7d = r
        if applicable_7d:
            tickets_req = int(applicable_7d.get("tickets", 0))
            minutes = int(applicable_7d.get("minutes", 0))
            # ensure not already granted for this window end
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                src_ref = f"7d_window_end:{last_date}"
                cur.execute("SELECT COUNT(1) FROM fidelity_reward_grants WHERE user_id = ? AND grant_type = '7d' AND source_reference = ?", (user_id, src_ref))
                row = cur.fetchone()
                exists = int(row[0]) if row else 0
                if exists == 0:
                    now = datetime.utcnow().isoformat()
                    cur.execute("INSERT INTO fidelity_reward_grants (user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                                (user_id, '7d', tickets_req, minutes, now, None, src_ref, f"7d reward for {tickets_req} tickets"))
                    conn.commit()
                    # credit via BonusManager if available
                    try:
                        if self.bonus_manager:
                            self.bonus_manager.admin_credit(user_id, minutes, operator_id=None, notes=f"Fidelity 7d ({tickets_req} tickets)")
                    except Exception:
                        pass

        # ---- 14-day extension rewards ----
        rewards_14d = self._get_config_json("fidelity_rewards_14d", [])
        # Check if user has at least one 7d grant ever
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(1) FROM fidelity_reward_grants WHERE user_id = ? AND grant_type = '7d'", (user_id,))
            row = cur.fetchone()
            has_7d = int(row[0]) if row else 0

        if has_7d:
            last_date_for_14 = ticket_dates[-1]
            cnt14 = count_in_window(last_date_for_14, 14)
            # apply each mapping entry if not already applied for this end window
            for mapping in sorted(rewards_14d, key=lambda x: int(x.get("tickets", 0))):
                tickets_req = int(mapping.get("tickets", 0))
                add_minutes = int(mapping.get("add_minutes", 0))
                if cnt14 >= tickets_req:
                    src_ref = f"14d_window_end:{last_date_for_14}:req{tickets_req}"
                    with self.db.get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(1) FROM fidelity_reward_grants WHERE user_id = ? AND grant_type = '14d' AND source_reference = ?", (user_id, src_ref))
                        row = cur.fetchone()
                        exists = int(row[0]) if row else 0
                        if exists == 0:
                            now = datetime.utcnow().isoformat()
                            cur.execute("INSERT INTO fidelity_reward_grants (user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                                        (user_id, '14d', tickets_req, add_minutes, now, None, src_ref, f"14d add {add_minutes} min for {tickets_req} tickets"))
                            conn.commit()
                            try:
                                if self.bonus_manager:
                                    self.bonus_manager.admin_credit(user_id, add_minutes, operator_id=None, notes=f"Fidelity 14d add {add_minutes} min for {tickets_req} tickets")
                            except Exception:
                                pass

        # ---- JF30 reward (30 days) ----
        try:
            threshold30 = int(self._get_config("fidelity_jf30_min_tickets", "12") or 12)
            per_ticket_min = int(self._get_config("fidelity_jf30_per_ticket_minutes", "2") or 2)
            expiry_days = int(self._get_config("fidelity_jf30_expiry_days", "10") or 10)
        except Exception:
            threshold30, per_ticket_min, expiry_days = 12, 2, 10

        # compute tickets in last 30 days (ending at last_date)
        def count_last_n(end_date_str: str, n: int):
            end = datetime.fromisoformat(end_date_str).date()
            start = end - timedelta(days=n-1)
            return sum(1 for d in ticket_dates if start <= datetime.fromisoformat(d).date() <= end)

        cnt30 = count_last_n(last_date, 30)
        if cnt30 >= threshold30:
            src_ref = f"jf30_window_end:{last_date}:cnt{cnt30}"
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(1) FROM fidelity_reward_grants WHERE user_id = ? AND grant_type = 'jf30' AND source_reference = ?", (user_id, src_ref))
                row = cur.fetchone()
                exists = int(row[0]) if row else 0
                if exists == 0:
                    minutes = cnt30 * per_ticket_min
                    now = datetime.utcnow().isoformat()
                    expiry_at = (datetime.utcnow() + timedelta(days=expiry_days)).isoformat()
                    cur.execute("INSERT INTO fidelity_reward_grants (user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                                (user_id, 'jf30', cnt30, minutes, now, expiry_at, src_ref, f"JF30 reward {cnt30} tickets"))
                    conn.commit()
                    try:
                        if self.bonus_manager:
                            self.bonus_manager.admin_credit(user_id, minutes, operator_id=None, notes=f"JF30 reward {cnt30} tickets")
                    except Exception:
                        pass

        # ---- Expire sequences that didn't reach 3 tickets in their first 7 days ----
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, start_date, status FROM fidelity_sequences WHERE user_id = ? AND status = 'active'", (user_id,))
            seqs = cur.fetchall()
            for s in seqs:
                # s may be Row or tuple
                seq_id = s[0] if isinstance(s, (list, tuple, sqlite3.Row)) else s[0]
                start_date = s[1]
                start = datetime.fromisoformat(start_date).date()
                end = start + timedelta(days=6)
                today_local = datetime.fromisoformat(last_date).date()
                if today_local <= end:
                    continue
                cur.execute("SELECT COUNT(1) FROM tickets_fidelite WHERE user_id = ? AND sequence_id = ? AND expired = 0 AND ticket_date BETWEEN ? AND ?", (user_id, seq_id, start.isoformat(), end.isoformat()))
                row = cur.fetchone()
                cnt_initial = int(row[0]) if row else 0
                if cnt_initial < 3:
                    cur.execute("UPDATE fidelity_sequences SET status = 'expired', updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), seq_id))
                    cur.execute("UPDATE tickets_fidelite SET expired = 1, notes = COALESCE(notes, '') || ? WHERE sequence_id = ?", (f"Expired by rule: initial 7d had {cnt_initial} tickets; ", seq_id))
                    conn.commit()
                else:
                    cur.execute("UPDATE fidelity_sequences SET status = 'validated', updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), seq_id))
                    conn.commit()

    # ---------------- Admin functions ----------------
    def admin_add_ticket(self, user_id: int, ticket_date_str: str, operator_id: Optional[int] = None, notes: Optional[str] = None) -> int:
        """
        Ajoute manuellement un ticket pour une date donnée (ticket_date_str format 'YYYY-MM-DD').
        Retourne l'id du ticket inséré.
        """
        seq_id = self._get_active_sequence(user_id)
        if not seq_id:
            seq_id = self._create_sequence(user_id, ticket_date_str)
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO tickets_fidelite (user_id, ticket_date, created_at, source, session_id, amount_fcfa, sequence_id, expired, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                        (user_id, ticket_date_str, now, 'manual', None, None, seq_id, notes or "admin add"))
            conn.commit()
            tid = cur.lastrowid
        try:
            self._process_rewards_for_user(user_id, sequence_id=seq_id)
        except Exception:
            pass
        return tid

    def admin_revoke_ticket(self, ticket_id: int, operator_id: Optional[int] = None, reason: Optional[str] = None) -> bool:
        """
        Marque un ticket comme expiré / révoqué.
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE tickets_fidelite SET expired = 1, notes = COALESCE(notes, '') || ? WHERE id = ?", (f"Revoked: {reason or 'admin'}", ticket_id))
            conn.commit()
            return cur.rowcount > 0

    def admin_force_grant(self, user_id: int, grant_type: str, minutes: int, tickets_count: int = 0, expiry_days: Optional[int] = None, notes: Optional[str] = None) -> int:
        """
        Permet à l'admin d'attribuer une récompense manuellement.
        Retourne id du grant.
        """
        now = datetime.utcnow().isoformat()
        expiry = (datetime.utcnow() + timedelta(days=expiry_days)).isoformat() if expiry_days else None
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO fidelity_reward_grants (user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                        (user_id, grant_type, tickets_count, minutes, now, expiry, "admin_force", notes or "admin manual grant"))
            conn.commit()
            gid = cur.lastrowid
        try:
            if self.bonus_manager:
                self.bonus_manager.admin_credit(user_id, minutes, operator_id=None, notes=f"Admin forced grant {grant_type}")
        except Exception:
            pass
        return gid

    # ---------------- Listing / Query ----------------
    def _rows_to_dicts(self, cur, rows):
        """
        Convertit la liste de rows (qui peuvent être tuples ou sqlite3.Row) en liste de dicts
        en utilisant cur.description pour les noms de colonnes si nécessaire.
        """
        if not rows:
            return []
        # If row is sqlite3.Row, it supports keys()
        first = rows[0]
        if isinstance(first, sqlite3.Row):
            return [dict(r) for r in rows]
        # else build dicts using description
        colnames = [c[0] for c in cur.description] if cur.description else []
        dicts = []
        for r in rows:
            d = {}
            for i, col in enumerate(colnames):
                try:
                    d[col] = r[i]
                except Exception:
                    d[col] = None
            dicts.append(d)
        return dicts

    def list_tickets(self, user_id: Optional[int] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            if user_id is None:
                cur.execute("SELECT id, user_id, ticket_date, created_at, source, session_id, amount_fcfa, sequence_id, expired, notes FROM tickets_fidelite ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
            else:
                cur.execute("SELECT id, user_id, ticket_date, created_at, source, session_id, amount_fcfa, sequence_id, expired, notes FROM tickets_fidelite WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (user_id, limit, offset))
            rows = cur.fetchall()
            return self._rows_to_dicts(cur, rows)

    def list_grants(self, user_id: Optional[int] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            if user_id is None:
                cur.execute("SELECT id, user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes FROM fidelity_reward_grants ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
            else:
                cur.execute("SELECT id, user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes FROM fidelity_reward_grants WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (user_id, limit, offset))
            rows = cur.fetchall()
            return self._rows_to_dicts(cur, rows)

    def get_user_progress(self, user_id: int, reference_date: Optional[str] = None) -> Dict[str, int]:
        """
        Retourne le nombre de tickets dans les fenêtres 7/14/30 jours se terminant à reference_date (ou today).
        """
        if reference_date is None:
            reference_date = self._today_local_str()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ticket_date FROM tickets_fidelite WHERE user_id = ? AND expired = 0 ORDER BY ticket_date ASC", (user_id,))
            rows = cur.fetchall()
            ticket_dates = []
            for r in rows:
                if isinstance(r, (list, tuple)):
                    ticket_dates.append(r[0])
                elif isinstance(r, sqlite3.Row):
                    ticket_dates.append(r["ticket_date"])
                else:
                    ticket_dates.append(r[0])
        ref = datetime.fromisoformat(reference_date).date()
        def count_window(days):
            start = ref - timedelta(days=days-1)
            return sum(1 for d in ticket_dates if start <= datetime.fromisoformat(d).date() <= ref)
        return {"7d": count_window(7), "14d": count_window(14), "30d": count_window(30)}

    # ---------------- Cleanup helpers ----------------
    def revoke_expired_grants(self):
        """
        Optionnel : scan grants with expiry_at in past and mark used=2 or similar.
        """
        now = datetime.utcnow().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE fidelity_reward_grants SET used = 2 WHERE expiry_at IS NOT NULL AND expiry_at < ?", (now,))
            conn.commit()

# ----------------------- Basic tests (standalone) -----------------------
if __name__ == "__main__":
    print("=== Tests basiques pour app/tickets_fidelite.py ===")
    # Use a temporary sqlite file in current folder to avoid touching production DB
    TEST_DB = "tickets_test_db.sqlite"
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass

    # instantiate TicketsManager (will use fallback _SimpleDBManager if DatabaseManager not present)
    if DatabaseManager:
        try:
            tm = TicketsManager(db_path=TEST_DB)
        except Exception:
            tm = TicketsManager(db=_SimpleDBManager(TEST_DB))
    else:
        tm = TicketsManager(db=_SimpleDBManager(TEST_DB))

    print("Run migrations...")
    tm.run_migrations()
    print("Migrations ok.")

    # Create a fake user in users table if not exists (helpful if DB has users table)
    try:
        with tm.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)")
            cur.execute("INSERT OR IGNORE INTO users (id, username, password, role) VALUES (1, 'testuser', 'x', 'user')")
            conn.commit()
    except Exception:
        pass

    uid = 1
    print(f"Simuler 4 jours de jeu pour user {uid} (>=100 FCFA) ...")
    # simulate adding tickets for past 4 days by admin_add_ticket
    today = datetime.utcnow().date()
    added = []
    for d in range(4):
        day = today - timedelta(days=(3 - d))  # 4 consecutive days ending today
        ds = day.isoformat()
        tid = tm.admin_add_ticket(uid, ds, notes=f"test add {ds}")
        added.append((ds, tid))
    print("Tickets ajoutés:", added)

    print("Process rewards (should create a 3-ticket or 4-ticket reward depending on count)...")
    tm._process_rewards_for_user(uid)
    grants = tm.list_grants(uid)
    print("Grants:", grants)

    print("Add many tickets to reach JF30 threshold (simulate 12 tickets in last 30 days)")
    # add 12 tickets over last 12 days
    for i in range(12):
        day = today - timedelta(days=i)
        ds = day.isoformat()
        try:
            tm.admin_add_ticket(uid, ds, notes="jf30 test")
        except Exception:
            pass
    tm._process_rewards_for_user(uid)
    grants = tm.list_grants(uid)
    print("Grants after jf30 simulation:", grants)

    print("List recent tickets:")
    tickets = tm.list_tickets(uid, limit=50)
    for t in tickets[:10]:
        print(t)

    print("User progress (today):", tm.get_user_progress(uid))
    print("Tests terminés. Vérifie le fichier:", TEST_DB)
