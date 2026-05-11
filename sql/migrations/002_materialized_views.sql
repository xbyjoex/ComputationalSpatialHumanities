-- =============================================================================
-- Migration 002: Mart materialized views for dashboard performance
-- =============================================================================

-- ── Latest Park+Ride occupancy per site ──────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.park_ride_latest AS
SELECT DISTINCT ON (site_id)
    site_id,
    site_name,
    total_spaces,
    occupied_spaces,
    free_spaces,
    occupancy_pct,
    geom,
    measured_at
FROM core.park_ride_occupancy
ORDER BY site_id, measured_at DESC;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_pr_latest_site ON mart.park_ride_latest(site_id);
CREATE INDEX IF NOT EXISTS idx_mart_pr_latest_geom ON mart.park_ride_latest USING gist(geom);

-- ── Bicycle counts: daily aggregates per counter, last 365 days ──────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.bicycle_daily AS
SELECT
    counter_id,
    counter_name,
    geom,
    period_start::DATE AS count_date,
    SUM(count_value)   AS daily_total,
    MAX(ingested_at)   AS last_updated
FROM core.bicycle_counts
WHERE count_period = 'day'
  AND period_start >= NOW() - INTERVAL '365 days'
GROUP BY counter_id, counter_name, geom, period_start::DATE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_bicy_daily ON mart.bicycle_daily(counter_id, count_date);
CREATE INDEX IF NOT EXISTS idx_mart_bicy_geom ON mart.bicycle_daily USING gist(geom);

-- ── Active traffic restrictions map layer ─────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.active_restrictions AS
SELECT
    id,
    restriction_id,
    dataset_id,
    restriction_type,
    title,
    description,
    geom,
    valid_from,
    valid_until,
    properties
FROM core.traffic_restrictions
WHERE (valid_until IS NULL OR valid_until > NOW())
  AND (valid_from  IS NULL OR valid_from  <= NOW());
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_restr_id   ON mart.active_restrictions(id);
CREATE INDEX IF NOT EXISTS idx_mart_restr_geom ON mart.active_restrictions USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_mart_restr_type ON mart.active_restrictions(restriction_type);

-- ── Statistics summary: latest value per dataset × spatial unit × metric ─────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.statistics_latest AS
SELECT DISTINCT ON (dataset_id, spatial_unit, spatial_key, metric_name)
    dataset_id,
    spatial_unit,
    spatial_key,
    metric_name,
    metric_unit,
    period_label,
    period_year,
    metric_value,
    ingested_at
FROM core.statistics
ORDER BY dataset_id, spatial_unit, spatial_key, metric_name, period_year DESC NULLS LAST, period_quarter DESC NULLS LAST, period_month DESC NULLS LAST;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_stats_latest_unique ON mart.statistics_latest(dataset_id, spatial_unit, spatial_key, metric_name);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_ds ON mart.statistics_latest(dataset_id);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_spatial ON mart.statistics_latest(spatial_unit, spatial_key);
CREATE INDEX IF NOT EXISTS idx_mart_stats_latest_metric ON mart.statistics_latest(metric_name);

-- ── Geo features map layer (geometry simplified for web performance) ──────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.geo_features_map AS
SELECT
    f.id,
    f.dataset_id,
    d.title  AS dataset_title,
    f.feature_type,
    f.name,
    f.description,
    -- Simplify geometry for zoom levels < 14 (tolerance ~20m at equator)
    CASE
        WHEN ST_NPoints(f.geom) > 100
        THEN ST_SimplifyPreserveTopology(f.geom, 0.0002)
        ELSE f.geom
    END AS geom,
    f.properties,
    f.valid_from,
    f.valid_until,
    f.updated_at
FROM core.geo_features f
JOIN core.datasets d ON d.id = f.dataset_id
WHERE d.is_active;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_gf_map_id ON mart.geo_features_map(id);
CREATE INDEX IF NOT EXISTS idx_mart_gf_map_geom ON mart.geo_features_map USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_mart_gf_map_dataset ON mart.geo_features_map(dataset_id);
CREATE INDEX IF NOT EXISTS idx_mart_gf_map_type ON mart.geo_features_map(feature_type);

-- ── Dataset ingestion status overview ────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.dataset_status AS
SELECT
    d.id,
    d.title,
    d.schedule,
    d.has_geo,
    d.best_format,
    d.last_ingested,
    r.last_run_status,
    r.last_run_at,
    r.last_run_rows
FROM core.datasets d
LEFT JOIN LATERAL (
    SELECT status AS last_run_status, started_at AS last_run_at, rows_loaded AS last_run_rows
    FROM raw_ingest.etl_runs
    WHERE dataset_id = d.id
    ORDER BY started_at DESC
    LIMIT 1
) r ON TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_ds_status_id ON mart.dataset_status(id);

-- ── Helper function to refresh all mart views ─────────────────────────────────
CREATE OR REPLACE FUNCTION mart.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.park_ride_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.statistics_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.geo_features_map;
    REFRESH MATERIALIZED VIEW mart.dataset_status;
END;
$$ LANGUAGE plpgsql;

-- ── Helper function to refresh only live-source views ────────────────────────
CREATE OR REPLACE FUNCTION mart.refresh_live()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.park_ride_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
END;
$$ LANGUAGE plpgsql;
