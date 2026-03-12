-- SLR Multi-Agent Pipeline — Database Initialization
-- Run against the existing Azure PostgreSQL / PostGIS database.
-- Safe to re-run (all statements are idempotent).

-- ─────────────────────────────────────────────────────────────
--  1. Clean-data schema (Agent 2 — DIO writes here)
-- ─────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS clean_data;

-- DIO populates these tables via its MCP tools:
--   clean_data.claims_processed   — cleaned NFIP claims
--   clean_data.parcels_clipped    — spatially clipped parcel geometries

-- ─────────────────────────────────────────────────────────────
--  2. Agent audit log (all agents append here)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    agent       TEXT        NOT NULL,   -- 'DIO' | 'MEL' | 'SIMO'
    tool        TEXT        NOT NULL,
    params      JSONB,
    summary     TEXT,
    status      TEXT        CHECK (status IN ('success', 'error')),
    ts          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_agent_ts ON agent_audit_log (agent, ts DESC);

-- ─────────────────────────────────────────────────────────────
--  3. DB roles for principle-of-least-privilege
--     (run once as superuser; skip if roles already exist)
-- ─────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'slr_readonly') THEN
        CREATE ROLE slr_readonly NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'slr_dio_writer') THEN
        CREATE ROLE slr_dio_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'slr_simo_writer') NOINHERIT THEN
        CREATE ROLE slr_simo_writer NOLOGIN;
    END IF;
END
$$;

-- Read-only on existing public tables
GRANT USAGE ON SCHEMA public TO slr_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO slr_readonly;

-- DIO can write to clean_data schema only
GRANT ALL ON SCHEMA clean_data TO slr_dio_writer;
GRANT CREATE ON SCHEMA clean_data TO slr_dio_writer;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA clean_data TO slr_dio_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA clean_data TO slr_dio_writer;
GRANT INSERT ON agent_audit_log TO slr_dio_writer;

-- SIMO can write to parcel_damage and invalidate tile_cache
GRANT SELECT ON parcels_cliplayer TO slr_simo_writer;
GRANT INSERT, UPDATE, DELETE ON parcel_damage TO slr_simo_writer;
GRANT DELETE ON tile_cache TO slr_simo_writer;
GRANT INSERT ON agent_audit_log TO slr_simo_writer;
