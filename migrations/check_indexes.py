import sqlite3
db="data/rdm_gsalle.db"
c=sqlite3.connect(db).cursor()
print("Indexes on tickets_fidelite:")
c.execute("PRAGMA index_list('tickets_fidelite')")
print(c.fetchall())
print()
print("Indexes on fidelity_reward_grants:")
c.execute("PRAGMA index_list('fidelity_reward_grants')")
print(c.fetchall())
