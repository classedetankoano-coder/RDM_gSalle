import sqlite3
db = "data/rdm_gsalle.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM tickets_fidelite")
before = cur.fetchone()[0]

# count groups duplicate
cur.execute("SELECT COUNT(*) FROM (SELECT user_id, ticket_date FROM tickets_fidelite GROUP BY user_id, ticket_date HAVING COUNT(*)>1)")
dup_groups = cur.fetchone()[0]
print("Nombre de groupes doublons :", dup_groups)

# show which rowids would be deleted (for info)
cur.execute("""
SELECT rowid, user_id, ticket_date, created_at FROM tickets_fidelite
WHERE rowid NOT IN (SELECT MAX(rowid) FROM tickets_fidelite GROUP BY user_id, ticket_date)
ORDER BY user_id, ticket_date
""")
to_delete = cur.fetchall()
print("Rowids candidats à suppression (preview):")
for r in to_delete:
    print(" ", r)

# delete duplicates keeping the row with the MAX(rowid) (usually the most recent insertion)
cur.execute("""
DELETE FROM tickets_fidelite
WHERE rowid NOT IN (
  SELECT MAX(rowid) FROM tickets_fidelite GROUP BY user_id, ticket_date
)
""")
conn.commit()

cur.execute("SELECT COUNT(*) FROM tickets_fidelite")
after = cur.fetchone()[0]
deleted = before - after
print("Avant:", before, "Après:", after, "Supprimés:", deleted)
conn.close()
