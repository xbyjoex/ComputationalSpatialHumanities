-- =============================================================================
-- Migration 012: Remove NULL-valued pseudo-metrics
-- =============================================================================
-- The generic statistics loader used to store EVERY source column as a
-- metric, including text columns (Wahl_text, Vorname, Wahlkreis_Name, ...)
-- whose values never parse to a number. Those rows carry metric_value NULL,
-- can never be visualized, and flooded the metric dropdowns. The loader now
-- skips non-numeric values at ingest (etl/src/loaders/postgres.py); this
-- cleans up what already landed.

DELETE FROM core.statistics WHERE metric_value IS NULL;

-- Blocking refresh on purpose: CONCURRENTLY is not allowed inside the
-- migration transaction. Runs once, the nightly refresh takes over after.
REFRESH MATERIALIZED VIEW mart.statistics_latest;
