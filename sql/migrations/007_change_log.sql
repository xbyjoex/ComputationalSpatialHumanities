-- =============================================================================
-- Migration 007: change_log — per-ETL-run accounting of row-level changes.
--
-- One entry per (dataset, run, target table). Lets the explorer UI show
-- "wann hat sich der Datensatz verändert und wie".
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw_ingest.change_log (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      TEXT NOT NULL,
    run_id          BIGINT REFERENCES raw_ingest.etl_runs(id) ON DELETE SET NULL,
    target_table    TEXT NOT NULL,
    rows_added      INTEGER NOT NULL DEFAULT 0,
    rows_updated    INTEGER NOT NULL DEFAULT 0,
    rows_total_after INTEGER,
    sample_changes  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_change_log_dataset_created
    ON raw_ingest.change_log (dataset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_log_run
    ON raw_ingest.change_log (run_id);
