-- =============================================================================
-- Migration 015: Indicator catalog + statistik.leipzig.de re-ingest
-- =============================================================================
-- 1) Canonical indicator registry over the statistik.leipzig.de metrics,
--    curated in indicator_catalog.json (synced by the scheduler).
-- 2) Cleanup: the statistik wide-by-year CSVs used to be ingested without
--    melting — year columns became metrics named "2001", and different
--    indicator rows collided on the statistics upsert key, silently
--    overwriting each other. The pipeline now melts these layouts
--    (etl/src/extractors/statistik_transform.py); all previously ingested
--    rows for statistik datasets are wrong and must go. Deleting the
--    checksums forces a full re-ingest on the next nightly run despite
--    unchanged ETags.

CREATE TABLE IF NOT EXISTS core.indicators (
    indicator_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    unit         TEXT,
    topic        TEXT,
    description  TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.indicator_metrics (
    indicator_id TEXT NOT NULL REFERENCES core.indicators(indicator_id) ON DELETE CASCADE,
    dataset_id   TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    PRIMARY KEY (dataset_id, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_indicator_metrics_ind
    ON core.indicator_metrics(indicator_id);

-- ── Re-ingest statistik datasets with the fixed melt ─────────────────────────
DELETE FROM core.statistics
WHERE dataset_id IN (
    SELECT id FROM core.datasets
    WHERE best_url LIKE '%statistik.leipzig.de/opendata/api%'
);

DELETE FROM raw_ingest.dataset_checksums
WHERE dataset_id IN (
    SELECT id FROM core.datasets
    WHERE best_url LIKE '%statistik.leipzig.de/opendata/api%'
);

REFRESH MATERIALIZED VIEW mart.statistics_latest;
