import sqlite3, sys
db = "data/rdm_gsalle.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

print("DB:", db)
cur.execute("""
SELECT user_id, ticket_date, COUNT(*) as cnt
FROM tickets_fidelite
GROUP BY user_id, ticket_date
HAVING cnt > 1
ORDER BY cnt DESC
LIMIT 200
""")
dups = cur.fetchall()
print("Doublons (user_id, ticket_date, count) - up to 200 rows:")
for r in dups:
    print(r)

# show sample duplicate rows (first 50 rows)
print("\\nExemple de lignes doublons (rowid + colonnes) :")
cur.execute("""
SELECT rowid, user_id, ticket_date, source, created_at, amount_fcfa, sequence_id, notes
FROM tickets_fidelite
WHERE (user_id, ticket_date) IN (
  SELECT user_id, ticket_date FROM tickets_fidelite GROUP BY user_id, ticket_date HAVING COUNT(*)>1
)
ORDER BY user_id, ticket_date, created_at DESC
LIMIT 200
""")
for row in cur.fetchall():
    print(row)

conn.close()
