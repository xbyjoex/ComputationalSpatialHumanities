-- =============================================================================
-- Migration 008: Separate "current snapshot" from "historical time-series" for
-- Park+Ride.
--
-- Background: the WFS source has three different P+R endpoints:
--   - lastrecord       → 7 rows, current occupancy per site (live)
--   - zeitreihe        → 10019 rows, last-30-day history per site (nightly)
--   - standort_statisch→ 15 rows, static locations (nightly, generic geo)
--
-- Previously the dispatch keyword didn't match the actual dataset names, so
-- all three datasets fell through to the generic GeoJSON branch and were
-- written into core.geo_features. Every live refresh re-upserted 10019 rows
-- and 7 rows, generating WAL and CPU for zero useful change.
--
-- After this migration:
--   - core.park_ride_latest      single row per site, upserted every 5 min
--   - core.park_ride_occupancy   time-series, only written nightly
--                                UNIQUE (site_id, measured_at) so re-imports
--                                are no-ops
--   - mart.park_ride_latest      thin passthrough view (no longer derived
--                                via DISTINCT ON from the occupancy table)
-- =============================================================================

-- ── core.park_ride_latest — one row per site ───────────────────────────────
CREATE TABLE IF NOT EXISTS core.park_ride_latest (
    site_id         TEXT PRIMARY KEY,
    site_name       TEXT,
    total_spaces    INTEGER,
    occupied_spaces INTEGER,
    free_spaces     INTEGER,
    occupancy_pct   DOUBLE PRECISION GENERATED ALWAYS AS (
        CASE WHEN total_spaces > 0
             THEN (occupied_spaces::DOUBLE PRECISION / total_spaces) * 100
             ELSE NULL END
    ) STORED,
    geom            GEOMETRY(Point, 4326),
    measured_at     TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_latest_geom
    ON core.park_ride_latest USING gist(geom);

-- ── core.park_ride_occupancy — historical time-series ──────────────────────
-- Idempotent inserts: the WFS zeitreihe re-publishes the same 30-day window
-- on every poll, so each (site, measured_at) point must dedupe.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pr_site_measured
    ON core.park_ride_occupancy (site_id, measured_at);

-- ── Clean up: P+R rows that were mis-routed into core.geo_features ─────────
DELETE FROM core.geo_features
WHERE dataset_id IN (
    '55da7549-f64e-448d-a636-b84db35efbe5',   -- aktuelle Belegung
    '430a768c-7f00-47eb-a2a0-effd50a00023',   -- zeitreihe (historisch)
    'a2c3a1bd-d996-4fb7-9742-e756afe4e306'    -- standort_statisch
);

-- ── Recreate mart.park_ride_latest as a passthrough view ───────────────────
-- mart.refresh_live() previously refreshed this; remove the CONCURRENTLY call
-- in 002 by recreating the materialized view as a plain view.
DROP MATERIALIZED VIEW IF EXISTS mart.park_ride_latest;
CREATE VIEW mart.park_ride_latest AS
SELECT
    site_id, site_name, total_spaces, occupied_spaces, free_spaces,
    occupancy_pct, geom, measured_at
FROM core.park_ride_latest;

-- ── Update mart.refresh_live() to skip the (now non-materialised) view ─────
CREATE OR REPLACE FUNCTION mart.refresh_live()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
END;
$$ LANGUAGE plpgsql;

-- mart.refresh_all() also no longer needs to refresh park_ride_latest
CREATE OR REPLACE FUNCTION mart.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.statistics_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.geo_features_map;
    REFRESH MATERIALIZED VIEW mart.dataset_status;
END;
$$ LANGUAGE plpgsql;
