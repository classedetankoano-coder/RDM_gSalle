-- migrations/001_create_fidelity_tables.sql
BEGIN TRANSACTION;

-- Table tickets_fidelite : un ticket par client par jour (unique)
CREATE TABLE IF NOT EXISTS tickets_fidelite (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL,
  date_jour TEXT NOT NULL,           -- 'YYYY-MM-DD'
  source TEXT NOT NULL DEFAULT 'auto', -- 'auto' | 'manual' | 'admin'
  note TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(client_id, date_jour) ON CONFLICT IGNORE
);

CREATE INDEX IF NOT EXISTS idx_tickets_client_date ON tickets_fidelite (client_id, date_jour);

-- Table fidelity_reward_grants : historique des récompenses accordées
CREATE TABLE IF NOT EXISTS fidelity_reward_grants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL,
  grant_date TEXT NOT NULL DEFAULT (datetime('now')),
  window_start TEXT,    -- optional: start of counted window (YYYY-MM-DD)
  window_end TEXT,      -- optional: end of counted window (YYYY-MM-DD)
  tickets_count INTEGER,
  minutes_granted INTEGER,
  source TEXT DEFAULT 'auto',  -- 'auto' | 'manual'
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_grants_client_date ON fidelity_reward_grants (client_id, grant_date);

COMMIT;
