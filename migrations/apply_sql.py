import sys
from pathlib import Path
import sqlite3

if len(sys.argv) < 3:
    print("Usage: python migrations\\apply_sql.py <db_path> <sql_file>")
    sys.exit(1)

db_path = sys.argv[1]
sql_file = sys.argv[2]

db = Path(db_path)
sqlp = Path(sql_file)
if not db.exists():
    print("DB not found:", db)
    sys.exit(2)
if not sqlp.exists():
    print("SQL file not found:", sqlp)
    sys.exit(3)

print("Using DB:", db)
print("Applying SQL:", sqlp)
sql = sqlp.read_text(encoding='utf-8')

conn = sqlite3.connect(str(db))
try:
    conn.executescript(sql)
    conn.commit()
    print("SQL applied successfully.")
except Exception as e:
    print("Error applying SQL:", e)
    raise
finally:
    conn.close()
