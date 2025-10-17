import sqlite3, datetime, traceback
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
user_id = 1                # <- change si tu veux un autre user/client
minutes = 30               # <- nombre de minutes du grant
note = "Log automatique: grant fidélité (test)"
now = datetime.datetime.now().isoformat()

print("DB:", db)
inserted_any = False

# 1) Inserer dans bonus_transactions (nécessite minutes_delta and source)
try:
    cur.execute("""
        INSERT INTO bonus_transactions (user_id, minutes_delta, source, reference, created_at, operator_id, notes)
        VALUES (?, ?, ?, ?, ?, NULL, ?)
    """, (user_id, minutes, "fidelity_auto", "", now, note))
    conn.commit()
    print("Inserted into bonus_transactions, rowid:", cur.lastrowid)
    inserted_any = True
except Exception as e:
    print("FAILED to insert into bonus_transactions:", e)
    traceback.print_exc()

# 2) Si clients.id == user_id, inserer dans bonus_history (client_id, minutes_change, type, created_at, source)
try:
    cur.execute("SELECT id FROM clients WHERE id = ?", (user_id,))
    client_row = cur.fetchone()
    if client_row:
        try:
            cur.execute("""
                INSERT INTO bonus_history (client_id, type, minutes_change, montant_fcfa, source, created_at)
                VALUES (?, ?, ?, NULL, ?, ?)
            """, (user_id, "accrual", minutes, "fidelity_auto", now))
            conn.commit()
            print("Inserted into bonus_history, rowid:", cur.lastrowid)
            inserted_any = True
        except Exception as e:
            print("FAILED to insert into bonus_history:", e)
            traceback.print_exc()
    else:
        print("No client with id =", user_id, " -> skip bonus_history insertion")
except Exception as e:
    print("Error checking clients table:", e)
    traceback.print_exc()

if not inserted_any:
    print("Aucune insertion réalisée (regarde les erreurs ci-dessus).")
else:
    print('Done.')
conn.close()
