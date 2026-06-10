-- =============================================================================
-- Migration 010: mart.statistics_latest with canonical spatial_code
-- =============================================================================
-- Materialized views cannot gain columns via CREATE OR REPLACE — recreate.
-- The unique index must be back in place before the next CONCURRENTLY refresh
-- (mart.refresh_all from migration 008 keeps working unchanged).

DROP MATERIALIZED VIEW IF EXISTS mart.statistics_latest;

CREATE MATERIALIZED VIEW mart.statistics_latest AS
SELECT DISTINCT ON (dataset_id, spatial_unit, spatial_key, metric_name)
    dataset_id,
    spatial_unit,
    spatial_key,
    spatial_code,
    metric_name,
    metric_unit,
    period_label,
    period_year,
    metric_value,
    ingested_at
FROM core.statistics
ORDER BY dataset_id, spatial_unit, spatial_key, metric_name,
         period_year DESC NULLS LAST, period_quarter DESC NULLS LAST, period_month DESC NULLS LAST;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_stats_latest_unique
    ON mart.statistics_latest(dataset_id, spatial_unit, spatial_key, metric_name);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_ds ON mart.statistics_latest(dataset_id);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_spatial ON mart.statistics_latest(spatial_unit, spatial_key);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_code ON mart.statistics_latest(spatial_unit, spatial_code);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_metric ON mart.statistics_latest(metric_name);
