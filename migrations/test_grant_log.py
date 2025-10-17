import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
from datetime import date, timedelta
from app.fidelity_helpers import insert_ticket_if_eligible, compute_reward_for_user, grant_fidelity_reward_if_eligible

db = "data/rdm_gsalle.db"
conn = sqlite3.connect(db)

user_id = 1
today = date.today()

# ensure tickets for last 3 days exist
for d in range(0, 3):
    day = today - timedelta(days=d)
    ok, msg = insert_ticket_if_eligible(conn, user_id=user_id, amount_fcfa=150, ticket_day=day)
    print("insert", day.isoformat(), ok, msg)

print("compute before grant:", compute_reward_for_user(conn, user_id))

res = grant_fidelity_reward_if_eligible(conn, user_id)
print("grant result:", res)

cur = conn.cursor()
cur.execute("SELECT id, user_id, tickets_count, minutes_awarded, created_at FROM fidelity_reward_grants WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user_id,))
print("recent grants:")
for r in cur.fetchall():
    print(r)

# ✅ correction ici
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('bonus_history','bonus_transactions')")
tables = [r[0] for r in cur.fetchall()]
print('found log tables:', tables)
for t in tables:
    print('\nContents of', t)
    try:
        cur.execute(f"SELECT rowid, * FROM {t} WHERE rowid > 0 ORDER BY rowid DESC LIMIT 5")
        for row in cur.fetchall():
            print(row)
    except Exception as e:
        print('error reading table', t, e)

conn.close()
