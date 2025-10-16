import sqlite3, datetime
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
user_id=1
minutes=30
note="Log automatique: grant fidélité (test)"
now=datetime.datetime.now().isoformat()

candidates=["bonus_transactions","bonus_history"]
inserted=False
for t in candidates:
    cur.execute("SELECT name FROM sqlite_master WHERE type=''table'' AND name=?", (t,))
    if not cur.fetchone():
        continue
    cur.execute(f"PRAGMA table_info('{t}')")
    cols=[c[1] for c in cur.fetchall()]
    # try amount-like columns
    for amount_col in ("amount","minutes","montant"):
        if amount_col in cols:
            try:
                cur.execute(f"INSERT INTO {t} (user_id, {amount_col}, created_at, note) VALUES (?,?,?,?)", (user_id, minutes, now, note))
                conn.commit()
                print("Inserted into", t, "using column", amount_col, "rowid:", cur.lastrowid)
                inserted=True
                break
            except Exception as e:
                print("Insert failed for", t, ":", e)
    if inserted:
        break
    # fallback generic insert if user_id + created_at available
    if "user_id" in cols and "created_at" in cols:
        try:
            cur.execute(f"INSERT INTO {t} (user_id, created_at, note) VALUES (?,?,?)", (user_id, now, note))
            conn.commit()
            print("Inserted into", t, "using generic columns. rowid:", cur.lastrowid)
            inserted=True
            break
        except Exception as e:
            print("Fallback insert failed for", t, ":", e)

if not inserted:
    print("Aucune insertion possible : structure non supportée.")
conn.close()
