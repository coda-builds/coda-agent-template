-- ═══════════════════════════════════════════════════════════════════════════
--  Coda Agent Template — Supabase Database Schema
--
--  Run this script once in the Supabase SQL Editor to create all required
--  tables, indexes, and Row Level Security (RLS) policies.
--
--  Two tables:
--    conversations — one row per session
--    messages      — append-only message log
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Enable UUID extension ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── conversations ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT        PRIMARY KEY,              -- UUID string from the application
    current_state   TEXT        NOT NULL,                 -- Name of the active state
    turn_count      INTEGER     NOT NULL DEFAULT 0,       -- Total turns processed
    metadata        JSONB       NOT NULL DEFAULT '{}',    -- Arbitrary client-supplied data
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Automatically update updated_at on every row update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS conversations_updated_at ON conversations;
CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ── messages ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT        NOT NULL,
    state           TEXT,                                 -- Agent state when message was generated
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
-- Fetch all messages for a conversation in order — used on every turn.
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at
    ON messages (conversation_id, created_at ASC);

-- Filter conversations by state — useful for analytics dashboards.
CREATE INDEX IF NOT EXISTS idx_conversations_current_state
    ON conversations (current_state);

-- Filter conversations by metadata fields (e.g. user_id).
CREATE INDEX IF NOT EXISTS idx_conversations_metadata
    ON conversations USING GIN (metadata);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- The backend uses the SERVICE_ROLE key, which bypasses RLS.
-- RLS is enabled here to prevent accidental public access if the ANON key
-- is ever used.

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Deny all access via the anon/public key by default.
-- The service role key bypasses these policies automatically.
DROP POLICY IF EXISTS conversations_deny_anon ON conversations;
CREATE POLICY conversations_deny_anon ON conversations
    FOR ALL TO anon USING (false);

DROP POLICY IF EXISTS messages_deny_anon ON messages;
CREATE POLICY messages_deny_anon ON messages
    FOR ALL TO anon USING (false);

-- ── Verification query ────────────────────────────────────────────────────────
-- After running this script, run the following to confirm:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public' AND table_name IN ('conversations', 'messages');
