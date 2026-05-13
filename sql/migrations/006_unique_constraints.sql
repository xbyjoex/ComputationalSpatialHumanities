-- =============================================================================
-- Migration 006: Real UNIQUE constraints so loaders can upsert idempotently.
--
-- After this migration the loaders must target these conflict keys:
--   core.geo_features            ON CONFLICT (dataset_id, dedup_key)
--   core.statistics              ON CONFLICT (dataset_id, period_label,
--                                              spatial_unit, spatial_key,
--                                              metric_name)
--   core.traffic_restrictions    ON CONFLICT (dataset_id, dedup_key)
-- =============================================================================

-- ── core.geo_features ───────────────────────────────────────────────────────
ALTER TABLE core.geo_features ADD COLUMN IF NOT EXISTS dedup_key TEXT;

UPDATE core.geo_features
SET dedup_key = COALESCE(
    NULLIF(feature_id, ''),
    MD5(COALESCE(properties::text, '') || COALESCE(ST_AsEWKT(geom), ''))
)
WHERE dedup_key IS NULL;

ALTER TABLE core.geo_features ALTER COLUMN dedup_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_geo_features_dataset_dedup
    ON core.geo_features (dataset_id, dedup_key);

-- ── core.traffic_restrictions ───────────────────────────────────────────────
ALTER TABLE core.traffic_restrictions ADD COLUMN IF NOT EXISTS dedup_key TEXT;

UPDATE core.traffic_restrictions
SET dedup_key = COALESCE(
    NULLIF(restriction_id, ''),
    MD5(COALESCE(properties::text, '') || COALESCE(ST_AsEWKT(geom), ''))
)
WHERE dedup_key IS NULL;

ALTER TABLE core.traffic_restrictions ALTER COLUMN dedup_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_traffic_restrictions_dataset_dedup
    ON core.traffic_restrictions (dataset_id, dedup_key);

-- ── core.statistics ─────────────────────────────────────────────────────────
-- Normalise nulls so the unique constraint can be plain-column and ON CONFLICT
-- can reference it without expressions.
UPDATE core.statistics SET period_label  = '' WHERE period_label  IS NULL;
UPDATE core.statistics SET spatial_unit  = '' WHERE spatial_unit  IS NULL;
UPDATE core.statistics SET spatial_key   = '' WHERE spatial_key   IS NULL;

ALTER TABLE core.statistics
    ALTER COLUMN period_label SET DEFAULT '',
    ALTER COLUMN period_label SET NOT NULL,
    ALTER COLUMN spatial_unit SET DEFAULT '',
    ALTER COLUMN spatial_unit SET NOT NULL,
    ALTER COLUMN spatial_key  SET DEFAULT '',
    ALTER COLUMN spatial_key  SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_statistics_natural_key
    ON core.statistics (dataset_id, period_label, spatial_unit, spatial_key, metric_name);

-- ── raw_ingest.payloads: one summary row per dataset ──────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_payloads_dataset
    ON raw_ingest.payloads (dataset_id);

-- The raw_text column is no longer written; drop to reclaim space.
ALTER TABLE raw_ingest.payloads DROP COLUMN IF EXISTS raw_text;

-- ── Drop redundant raw_payload column on core.statistics ───────────────────
-- The full record is already kept once (most recent) in raw_ingest.payloads.
-- Storing it again per metric row inflated the table without adding value.
ALTER TABLE core.statistics DROP COLUMN IF EXISTS raw_payload;

-- Drop the now-orphaned GIN index on the dropped column (no-op if gone)
DROP INDEX IF EXISTS core.idx_statistics_payload;

-- Reclaim disk after column drop
VACUUM FULL core.statistics;
VACUUM FULL core.geo_features;
VACUUM FULL core.traffic_restrictions;
VACUUM FULL raw_ingest.payloads;
