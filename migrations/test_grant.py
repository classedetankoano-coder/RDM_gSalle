import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
from datetime import date, timedelta
from app.fidelity_helpers import insert_ticket_if_eligible, compute_reward_for_user, grant_fidelity_reward_if_eligible

db = "data/rdm_gsalle.db"
conn = sqlite3.connect(db)

# Utilisateur de test (utilisateur 1 existant dans ta DB — modifie si besoin)
user_id = 1

# Créer 3 tickets sur 3 jours (aujourd'hui, hier, avant-hier) pour déclencher le palier 3/7
today = date.today()
for d in range(0, 3):
    day = today - timedelta(days=d)
    ok, msg = insert_ticket_if_eligible(conn, user_id=user_id, amount_fcfa=150, ticket_day=day)
    print("insert", day.isoformat(), ok, msg)

# Calculer l'état avant grant
print("compute before grant:", compute_reward_for_user(conn, user_id))

# Essayer d'accorder le reward
res = grant_fidelity_reward_if_eligible(conn, user_id)
print("grant result:", res)

# Re-vérifier l'état et grants table
cur = conn.cursor()
cur.execute("SELECT id, user_id, tickets_count, minutes_awarded, created_at, expiry_at, notes FROM fidelity_reward_grants WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user_id,))
print("recent grants:")
for r in cur.fetchall():
    print(r)

# Voir clients.bonus_jeu (si présent)
try:
    cur.execute("SELECT id, bonus_jeu FROM clients WHERE id=?", (user_id,))
    print("client bonus_jeu:", cur.fetchone())
except Exception as e:
    print("clients table read error:", e)

conn.close()
