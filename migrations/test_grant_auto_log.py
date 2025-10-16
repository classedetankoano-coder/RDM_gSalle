import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
from datetime import date, timedelta
from app.fidelity_helpers import insert_ticket_if_eligible, compute_reward_for_user, grant_fidelity_reward_if_eligible

db = "data/rdm_gsalle.db"
conn = sqlite3.connect(db)
user_id = 1
today = date.today()

print("== create tickets for last 3 days ==")
for d in range(0, 3):
    day = today - timedelta(days=d)
    ok, msg = insert_ticket_if_eligible(conn, user_id=user_id, amount_fcfa=150, ticket_day=day)
    print("insert", day.isoformat(), ok, msg)

print("\n== compute before grant ==")
print(compute_reward_for_user(conn, user_id))

print("\n== attempt grant ==")
res = grant_fidelity_reward_if_eligible(conn, user_id)
print("grant result:", res)

cur = conn.cursor()
print("\n== recent fidelity_reward_grants ==")
cur.execute("SELECT id, user_id, tickets_count, minutes_awarded, created_at FROM fidelity_reward_grants WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user_id,))
for r in cur.fetchall():
    print(r)

print("\n== recent bonus_transactions ==")
try:
    cur.execute("SELECT rowid, * FROM bonus_transactions ORDER BY rowid DESC LIMIT 5")
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print("bonus_transactions read error:", e)

print("\n== recent bonus_history ==")
try:
    cur.execute("SELECT rowid, * FROM bonus_history ORDER BY rowid DESC LIMIT 5")
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print("bonus_history read error:", e)

conn.close()
