import sqlite3
db="data/rdm_gsalle.db"
conn=sqlite3.connect(db)
cur=conn.cursor()
cur.execute("""
SELECT rowid, user_id, ticket_date, source, created_at, amount_fcfa, sequence_id, notes
FROM tickets_fidelite
WHERE rowid NOT IN (
  SELECT MAX(rowid) FROM tickets_fidelite GROUP BY user_id, ticket_date
)
ORDER BY user_id, ticket_date, created_at
""")
rows = cur.fetchall()
print("Lignes qui seraient supprimées (if any):")
for r in rows:
    print(r)
conn.close()
