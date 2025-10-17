import sqlite3, datetime, traceback
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
user_id = 1
minutes = 30
note = "Log automatique: grant fidélité (test)"
now = datetime.datetime.now().isoformat()

candidates = ["bonus_transactions","bonus_history"]
inserted = False
for t in candidates:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
    if not cur.fetchone():
        # table not present
        continue
    cur.execute(f"PRAGMA table_info('{t}')")
    cols = [c[1] for c in cur.fetchall()]
    print("Trying table:", t, "columns:", cols)
    # list of possible amount-like columns (more options)
    amount_candidates = ("amount","minutes","montant","montant_fcfa","valeur")
    created_candidates = ("created_at","created","date","timestamp","ts")
    note_candidates = ("note","notes","description","comment")
    # try amount-like insert first
    used_col = None
    for amount_col in amount_candidates:
        if amount_col in cols:
            try:
                cur.execute(f"INSERT INTO {t} (user_id, {amount_col}, created_at, note) VALUES (?,?,?,?)", (user_id, minutes, now, note))
                conn.commit()
                print("Inserted into", t, "using", amount_col, "rowid:", cur.lastrowid)
                inserted = True
                used_col = amount_col
                break
            except Exception as e:
                print("Insert failed with amount_col", amount_col, ":", e)
                # try next
    if inserted:
        break
    # fallback: insert using user_id + created + note if present
    if "user_id" in cols:
        # find a created-like column
        created_col = next((c for c in created_candidates if c in cols), None)
        note_col = next((c for c in note_candidates if c in cols), None)
        cols_to_try = []
        if created_col and note_col:
            cols_to_try.append( (f"(user_id, {created_col}, {note_col})", (user_id, now, note)) )
        if created_col:
            cols_to_try.append( (f"(user_id, {created_col})", (user_id, now)) )
        # try each fallback option
        for colspec, vals in cols_to_try:
            try:
                cur.execute(f"INSERT INTO {t} {colspec} VALUES ({','.join(['?']*len(vals))})", vals)
                conn.commit()
                print("Inserted into", t, "using fallback", colspec, "rowid:", cur.lastrowid)
                inserted = True
                break
            except Exception as e:
                print("Fallback insert failed for", t, colspec, ":", e)
    if inserted:
        break

if not inserted:
    print("Aucune insertion possible : structure non supportée ou contraintes NOT NULL empêchent l'insertion.")
conn.close()
