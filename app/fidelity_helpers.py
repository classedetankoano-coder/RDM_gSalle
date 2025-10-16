# app/fidelity_helpers.py
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB = str(Path(__file__).resolve().parents[1] / "data" / "rdm_gsalle.db")

def _detect_schema(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info('tickets_fidelite')")
    cols = [r[1] for r in cur.fetchall()]
    cur.execute("PRAGMA table_info('fidelity_reward_grants')")
    grants_cols = [r[1] for r in cur.fetchall()]

    mapping = {}
    mapping['ticket_user_col'] = 'user_id' if 'user_id' in cols else ('client_id' if 'client_id' in cols else None)
    mapping['ticket_date_col'] = 'ticket_date' if 'ticket_date' in cols else ('date_jour' if 'date_jour' in cols else None)
    mapping['grant_user_col'] = 'user_id' if 'user_id' in grants_cols else ('client_id' if 'client_id' in grants_cols else None)
    mapping['grant_minutes_col'] = 'minutes_awarded' if 'minutes_awarded' in grants_cols else ('minutes_granted' if 'minutes_granted' in grants_cols else None)
    return mapping

def count_tickets(conn, user_id, start_date, end_date):
    m = _detect_schema(conn)
    ucol = m['ticket_user_col']
    dcol = m['ticket_date_col']
    if not ucol or not dcol:
        raise RuntimeError("Tickets table missing expected columns.")
    cur = conn.cursor()
    cur.execute(f"""
      SELECT COUNT(DISTINCT {dcol}) FROM tickets_fidelite
      WHERE {ucol}=? AND {dcol} BETWEEN ? AND ?
    """, (user_id, start_date.isoformat(), end_date.isoformat()))
    return cur.fetchone()[0]

def insert_ticket_if_eligible(conn, user_id, amount_fcfa, source='auto', ticket_day=None, min_fcfa=100):
    if ticket_day is None:
        ticket_day = date.today()
    m = _detect_schema(conn)
    ucol = m['ticket_user_col']; dcol = m['ticket_date_col']
    if not ucol or not dcol:
        raise RuntimeError("Tickets table missing expected columns.")
    if amount_fcfa < min_fcfa:
        return False, "Amount below threshold"
    cur = conn.cursor()
    try:
        cur.execute(f"""
           INSERT OR IGNORE INTO tickets_fidelite ({ucol}, {dcol}, source, created_at, amount_fcfa)
           VALUES (?, ?, ?, datetime('now'), ?)
        """, (user_id, ticket_day.isoformat(), source, amount_fcfa))
        conn.commit()
        cur.execute(f"SELECT 1 FROM tickets_fidelite WHERE {ucol}=? AND {dcol}=? LIMIT 1", (user_id, ticket_day.isoformat()))
        exists = cur.fetchone() is not None
        return exists, "Inserted or already exists"
    except Exception:
        conn.rollback()
        raise

def compute_reward_for_user(conn, user_id, ref_date=None, cfg=None):
    if ref_date is None:
        ref_date = date.today()
    if cfg is None:
        cfg = {
            "ticket_min_fcfa": 100,
            "window_days_primary": 7,
            "window_days_extended": 14,
            "primary_rewards": {"3": 15, "4": 30, "5": 35, "6": 40, "7": 50},
            "extended_rewards": {"8": 55, "9": 65, "10": 70, "11": 75, "12": 80, "13": 90, "14": 105},
            "min_required_first7": 3,
            "expire_after_days": 14
        }
    w7 = cfg['window_days_primary']
    w14 = cfg['window_days_extended']
    start7 = ref_date - timedelta(days=w7-1)
    start14 = ref_date - timedelta(days=w14-1)

    t7 = count_tickets(conn, user_id, start7, ref_date)
    if t7 < cfg['min_required_first7']:
        return {'tickets_7': t7, 'tickets_14': 0, 'minutes': 0, 'granted': False, 'window_start_7': start7, 'window_end_7': ref_date}

    minutes = cfg['primary_rewards'].get(str(t7), 0)
    t14 = count_tickets(conn, user_id, start14, ref_date)
    if t14 > 7:
        minutes = cfg['extended_rewards'].get(str(t14), minutes)
    return {'tickets_7': t7, 'tickets_14': t14, 'minutes': minutes, 'granted': minutes > 0, 'window_start_7': start7, 'window_end_7': ref_date, 'window_start_14': start14, 'window_end_14': ref_date}

def _grant_exists(conn, user_id, tickets_count, window_start_date, window_end_date):
    cur = conn.cursor()
    start_ts = window_start_date.isoformat() + " 00:00:00"
    end_ts = window_end_date.isoformat() + " 23:59:59"
    cur.execute("""
      SELECT COUNT(*) FROM fidelity_reward_grants
      WHERE user_id=? AND tickets_count=? AND created_at BETWEEN ? AND ?
    """, (user_id, tickets_count, start_ts, end_ts))
    return cur.fetchone()[0] > 0

def _log_to_bonus_transactions(conn, user_id, minutes, note, source="fidelity_auto"):
    cur = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cur.execute("""
            INSERT INTO bonus_transactions (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
        """, (user_id, minutes, source, "", now, note))
        conn.commit()
        return ("bonus_transactions", cur.lastrowid)
    except Exception:
        conn.rollback()
        return (None, None)

def _log_to_bonus_history_if_client(conn, user_id, minutes, note, source="fidelity_auto"):
    cur = conn.cursor()
    now = datetime.now().isoformat()
    # check if client exists with same id
    cur.execute("SELECT id FROM clients WHERE id = ?", (user_id,))
    if not cur.fetchone():
        return (None, None)
    try:
        cur.execute("""
            INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at)
            VALUES (?, ?, ?, NULL, ?, ?)
        """, (user_id, "accrual", minutes, source, now))
        conn.commit()
        return ("bonus_history", cur.lastrowid)
    except Exception:
        conn.rollback()
        return (None, None)

def grant_fidelity_reward_if_eligible(conn, user_id, ref_date=None, cfg=None):
    """
    Crée un grant dans fidelity_reward_grants si eligible, puis journalise :
      - toujours dans bonus_transactions (user side)
      - dans bonus_history si clients.id == user_id (si client existe)
    Retourne un dict avec le détail de l'action.
    """
    if ref_date is None:
        ref_date = date.today()
    if cfg is None:
        cfg = {
            "ticket_min_fcfa": 100,
            "window_days_primary": 7,
            "window_days_extended": 14,
            "primary_rewards": {"3": 15, "4": 30, "5": 35, "6": 40, "7": 50},
            "extended_rewards": {"8": 55, "9": 65, "10": 70, "11": 75, "12": 80, "13": 90, "14": 105},
            "min_required_first7": 3,
            "expire_after_days": 14
        }

    reward = compute_reward_for_user(conn, user_id, ref_date=ref_date, cfg=cfg)
    if not reward.get("granted", False):
        return {"granted": False, "reason": "Not reached threshold", "reward": reward}

    # decide window & count for idempotence
    tickets_7 = reward.get("tickets_7", 0)
    tickets_14 = reward.get("tickets_14", 0)
    if tickets_14 and tickets_14 > 7:
        tickets_count = tickets_14
        window_start = reward.get("window_start_14")
        window_end = reward.get("window_end_14")
    else:
        tickets_count = tickets_7
        window_start = reward.get("window_start_7")
        window_end = reward.get("window_end_7")

    minutes = reward.get("minutes", 0)
    if minutes <= 0:
        return {"granted": False, "reason": "Calculated minutes is zero", "reward": reward}

    # idempotence on grants
    if _grant_exists(conn, user_id, tickets_count, window_start, window_end):
        return {"granted": False, "reason": "Already granted for this window and tickets_count", "reward": reward}

    cur = conn.cursor()
    expire_after = cfg.get("expire_after_days", 14)
    expiry_date = (ref_date + timedelta(days=expire_after)).isoformat()

    # create grant
    try:
        cur.execute("""
          INSERT INTO fidelity_reward_grants
            (user_id, grant_type, tickets_count, minutes_awarded, created_at, expiry_at, source_reference, used, notes)
          VALUES (?, ?, ?, ?, datetime('now'), ?, ?, 0, ?)
        """, (user_id, 'auto', tickets_count, minutes, expiry_date, '', 'Granted automatically'))
        conn.commit()
        grant_rowid = cur.lastrowid
    except Exception:
        conn.rollback()
        raise

    # logging: bonus_transactions (always) + bonus_history (if client exists)
    logged = {}
    bt_table, bt_row = _log_to_bonus_transactions(conn, user_id, minutes, f"Fidelity grant auto ({tickets_count} tickets -> {minutes} min)")
    logged['bonus_transactions'] = (bt_table, bt_row)
    bh_table, bh_row = _log_to_bonus_history_if_client(conn, user_id, minutes, f"Fidelity grant auto ({tickets_count} tickets -> {minutes} min)")
    logged['bonus_history'] = (bh_table, bh_row)

    return {"granted": True, "tickets_count": tickets_count, "minutes": minutes, "grant_rowid": grant_rowid, "logged": logged}
