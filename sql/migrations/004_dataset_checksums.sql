-- =============================================================================
-- Migration 004: Per-dataset checksum cache for ETL change detection
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw_ingest.dataset_checksums (
    dataset_id    TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    etag          TEXT,
    last_modified TEXT,
    content_hash  TEXT,
    checked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
