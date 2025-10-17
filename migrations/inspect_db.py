# migrations/inspect_db.py
# Usage: python migrations/inspect_db.py
import sqlite3
from pathlib import Path
import importlib.util, sys

ROOT = Path.cwd()
# try to auto-detect DB path from config/settings.py
db_candidates = []
settings_file = ROOT / "config" / "settings.py"
if settings_file.exists():
    try:
        spec = importlib.util.spec_from_file_location("rdm_settings", str(settings_file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dbp = getattr(mod, "DATABASE_PATH", None)
        if dbp:
            dbp = Path(dbp)
            if not dbp.is_absolute():
                dbp = (ROOT / dbp).resolve()
            db_candidates.append(str(dbp))
    except Exception:
        pass

# common fallbacks
db_candidates += [
    str(ROOT / "data" / "rdm_gsalle.db"),
    str(ROOT / "data" / "database.db"),
    str(ROOT / "database" / "rdm.db")
]

db_path = None
for c in db_candidates:
    if c and Path(c).exists():
        db_path = c
        break

if not db_path:
    print("ERROR: Aucune DB trouvée automatiquement. Indique le chemin en argument.")
    sys.exit(1)

print("Using DB:", db_path)
con = sqlite3.connect(db_path)
cur = con.cursor()

print("\n--- Tables (sqlite_master) ---")
cur.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view','trigger') ORDER BY type,name;")
rows = cur.fetchall()
for name, typ, sql in rows:
    print(f"{typ:6} | {name}")
    if sql:
        # print only first line of SQL to keep output readable
        first = sql.strip().splitlines()[0]
        print("     ", first[:300])

print("\n--- Checking specific tables/schema ---")
targets = ["tickets_fidelite", "fidelity_reward_grants", "tickets", "clients", "users", "fidelity_sequences"]
for t in targets:
    try:
        cur.execute(f"PRAGMA table_info('{t}');")
        info = cur.fetchall()
        if info:
            print(f"\nTable {t} columns:")
            for col in info:
                # (cid, name, type, notnull, dflt_value, pk)
                print("  ", col[1], col[2], "pk" if col[5] else "")
        else:
            print(f"\nTable {t} : NOT FOUND")
    except Exception as e:
        print(f"\nError checking {t}: {e}")

print("\n--- Searching for occurrences of 'client_id' in sqlite_master SQL ---")
cur.execute("SELECT name, type, sql FROM sqlite_master WHERE sql LIKE '%client_id%'")
rows = cur.fetchall()
if rows:
    for name, typ, sql in rows:
        print(f"Found in {typ} '{name}':")
        print(" ", (sql.strip().splitlines())[0][:400])
else:
    print("No occurrences of 'client_id' found in sqlite_master SQL.")

con.close()
print("\n--- END of inspection ---")
