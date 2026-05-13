-- =============================================================================
-- Migration 005: Deduplicate bloated tables + apply retention windows
--
-- Background: prior loader versions used ON CONFLICT DO NOTHING with no real
-- unique constraint, so every nightly ETL run re-inserted ALL rows as
-- duplicates. raw_ingest.payloads additionally stored the full records list
-- per run. Disk usage went from ~0 GB to ~40 GB in 3 days.
--
-- This migration:
--   1. Deletes duplicate rows in core.geo_features / statistics /
--      traffic_restrictions (keep newest by id).
--   2. Trims raw_ingest.payloads to the latest entry per dataset.
--   3. Applies retention to live time-series tables:
--        - core.park_ride_occupancy: 30 days
--        - core.bicycle_counts:      365 days
--        - raw_ingest.etl_runs:      90 days
--   4. VACUUM FULL on the affected tables to return disk to the OS.
--
-- Migration 006 follows with the real UNIQUE constraints + ON CONFLICT
-- targets so the bug cannot reoccur.
-- =============================================================================

-- ── core.geo_features: dedup by (dataset_id, feature_id) or geom+props hash ──
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY
                dataset_id,
                COALESCE(
                    NULLIF(feature_id, ''),
                    MD5(COALESCE(properties::text, '') || COALESCE(ST_AsEWKT(geom), ''))
                )
            ORDER BY id DESC
        ) AS rn
    FROM core.geo_features
)
DELETE FROM core.geo_features f
USING ranked r
WHERE f.id = r.id AND r.rn > 1;

-- ── core.statistics: dedup by full natural key ─────────────────────────────
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY
                dataset_id,
                COALESCE(period_label, ''),
                COALESCE(spatial_unit, ''),
                COALESCE(spatial_key, ''),
                metric_name
            ORDER BY id DESC
        ) AS rn
    FROM core.statistics
)
DELETE FROM core.statistics s
USING ranked r
WHERE s.id = r.id AND r.rn > 1;

-- ── core.traffic_restrictions: dedup by (dataset_id, restriction_id) ───────
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY
                dataset_id,
                COALESCE(
                    NULLIF(restriction_id, ''),
                    MD5(COALESCE(properties::text, '') || COALESCE(ST_AsEWKT(geom), ''))
                )
            ORDER BY id DESC
        ) AS rn
    FROM core.traffic_restrictions
)
DELETE FROM core.traffic_restrictions t
USING ranked r
WHERE t.id = r.id AND r.rn > 1;

-- ── raw_ingest.payloads: keep only the most recent row per dataset ─────────
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY dataset_id ORDER BY ingested_at DESC, id DESC) AS rn
    FROM raw_ingest.payloads
)
DELETE FROM raw_ingest.payloads p
USING ranked r
WHERE p.id = r.id AND r.rn > 1;

-- ── Retention: live time-series tables ─────────────────────────────────────
DELETE FROM core.park_ride_occupancy WHERE measured_at < NOW() - INTERVAL '30 days';
DELETE FROM core.bicycle_counts      WHERE period_start < NOW() - INTERVAL '365 days';
DELETE FROM raw_ingest.etl_runs      WHERE started_at  < NOW() - INTERVAL '90 days';

-- NOTE: VACUUM FULL would reclaim disk here, but it cannot run inside the
-- implicit transaction psycopg uses for multi-statement migrations. If you
-- ever need to reclaim disk after this migration on a bloated DB, run the
-- manual VACUUM block documented in docs/DEPLOYMENT.md ("Disk voll").
