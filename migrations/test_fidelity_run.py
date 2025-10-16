import sys, os
# 👉 ajoute le dossier racine du projet dans sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from app.fidelity_helpers import insert_ticket_if_eligible, compute_reward_for_user

conn = sqlite3.connect("data/rdm_gsalle.db")
ok, msg = insert_ticket_if_eligible(conn, user_id=1, amount_fcfa=150)
print("insert:", ok, msg)
print("reward:", compute_reward_for_user(conn, 1))
conn.close()
