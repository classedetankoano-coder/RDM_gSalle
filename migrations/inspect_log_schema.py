import sqlite3
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
for t in ("bonus_history","bonus_transactions"):
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,))
    row=cur.fetchone()
    print("TABLE:", t)
    print(" CREATE SQL:", row[0] if row else "<not found>")
    cur.execute(f"PRAGMA table_info('{t}')")
    cols=cur.fetchall()
    if cols:
        for c in cols:
            # c: (cid, name, type, notnull, dflt_value, pk)
            print("  -", c[1], "-", c[2], ("NOTNULL" if c[3] else ""))
    else:
        print("  (no columns / table missing)")
    print()
conn.close()
