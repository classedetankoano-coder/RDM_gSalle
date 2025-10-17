-- migrations/002_fidelity_indexes.sql
BEGIN TRANSACTION;

-- unique on (user_id, ticket_date) to avoid duplicate daily tickets (silently ignored if already unique via app logic)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_user_ticketdate ON tickets_fidelite (user_id, ticket_date);

-- helpful indexes for queries
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets_fidelite (user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_date ON tickets_fidelite (ticket_date);

CREATE INDEX IF NOT EXISTS idx_grants_user_date ON fidelity_reward_grants (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sequences_user ON fidelity_sequences (user_id);

COMMIT;
