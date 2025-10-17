import sqlite3
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
for t in ("bonus_transactions","bonus_history"):
    print("==", t, "==")
    try:
        cur.execute(f"SELECT rowid, * FROM {t} ORDER BY rowid DESC LIMIT 10")
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(r)
        else:
            print("(vide)")
    except Exception as e:
        print("Erreur lecture", t, ":", e)
    print()
conn.close()
