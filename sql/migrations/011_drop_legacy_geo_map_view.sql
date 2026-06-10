-- =============================================================================
-- Migration 011: Drop the legacy geo map view
-- =============================================================================
-- The unified layer is served as vector tiles directly from core.geo_features
-- (backend/src/api/routers/tiles_router.py). mart.geo_features_map duplicated
-- all ~4M features with simplified geometries for the removed /map/features
-- bbox endpoint — dropping it frees that footprint and shortens the nightly
-- refresh.

DROP MATERIALIZED VIEW IF EXISTS mart.geo_features_map;

CREATE OR REPLACE FUNCTION mart.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.statistics_latest;
    REFRESH MATERIALIZED VIEW mart.dataset_status;
END;
$$ LANGUAGE plpgsql;
