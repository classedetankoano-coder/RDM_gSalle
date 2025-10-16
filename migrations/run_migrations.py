#!/usr/bin/env python3
# migrations/run_migrations.py
import importlib.util
from pathlib import Path
import sqlite3
import sys

ROOT = Path.cwd()
settings_path = ROOT / "config" / "settings.py"

def load_db_path():
    if settings_path.exists():
        spec = importlib.util.spec_from_file_location("rdm_settings", str(settings_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        db = getattr(mod, "DATABASE_PATH", None)
        if db:
            dbp = Path(db)
            if not dbp.is_absolute():
                dbp = (ROOT / dbp).resolve()
            return str(dbp)
    # fallback candidates
    candidates = [
        ROOT / "data" / "rdm_gsalle.db",
        ROOT / "data" / "database.db",
        ROOT / "database" / "rdm.db",
    ]
    for c in candidates:
        if c.exists():
            return str(c.resolve())
    raise FileNotFoundError("Database path not found. Edit config/settings.py or pass DB path as argument.")

def run_sql_file(db_path, sql_file):
    print("Applying migration:", sql_file)
    sql = Path(sql_file).read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
        print("Migration applied successfully.")
    except Exception as e:
        print("Error applying migration:", e)
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = None
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = load_db_path()
    sql_file = ROOT / "migrations" / "001_create_fidelity_tables.sql"
    if not sql_file.exists():
        print("Migration file not found:", sql_file)
        sys.exit(1)
    print("Using DB:", db_path)
    run_sql_file(db_path, sql_file)
