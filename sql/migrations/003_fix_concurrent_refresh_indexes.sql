-- =============================================================================
-- Migration 003: Add missing unique indexes for CONCURRENT materialized view refresh
-- PostgreSQL requires a unique index on every materialized view that is
-- refreshed with REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- =============================================================================

-- mart.active_restrictions: id is the PK from core.traffic_restrictions
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_restr_id
    ON mart.active_restrictions(id);

-- mart.statistics_latest: composite of the DISTINCT ON columns
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_stats_latest_unique
    ON mart.statistics_latest(dataset_id, spatial_unit, spatial_key, metric_name);

-- mart.geo_features_map: id is the PK from core.geo_features
CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_gf_map_id
    ON mart.geo_features_map(id);
