-- =============================================================================
-- Migration 009: Dataset families, year dimension, spatial normalization
-- =============================================================================
-- Adds:
--   * core.dataset_families + family columns on core.datasets — year-variant
--     datasets (Bundestagswahl 2021/2025, Vornamenstatistik 2014-2025, ...)
--     become one logical dataset with a year dimension.
--   * core.geo_features.year — the data vintage of a feature (not a validity
--     window; valid_from/valid_until keep that role).
--   * core.statistics.spatial_code — canonical Ortsteil/Stadtbezirk/Wahlbezirk
--     code. spatial_key stays raw because it is part of the upsert key.
--   * core.admin_boundaries.boundary_year — Wahlbezirk geometries change per
--     election; 0 means timeless (Ortsteile, Stadtbezirke).
--   * core.spatial_aliases + core.resolve_spatial_key() — name→code resolution
--     for the heterogeneous spatial keys found in source CSVs.

CREATE EXTENSION IF NOT EXISTS unaccent;

-- ── Logical dataset families ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.dataset_families (
    family_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    kind        TEXT NOT NULL DEFAULT 'year_dimension',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE core.datasets
    ADD COLUMN IF NOT EXISTS family_id   TEXT REFERENCES core.dataset_families(family_id),
    ADD COLUMN IF NOT EXISTS family_year SMALLINT;
CREATE INDEX IF NOT EXISTS idx_datasets_family ON core.datasets(family_id);

-- ── Year dimension on geo features ────────────────────────────────────────────
ALTER TABLE core.geo_features ADD COLUMN IF NOT EXISTS year SMALLINT;
CREATE INDEX IF NOT EXISTS idx_geo_features_dataset_year
    ON core.geo_features(dataset_id, year);

-- ── Canonical spatial code on statistics ──────────────────────────────────────
ALTER TABLE core.statistics ADD COLUMN IF NOT EXISTS spatial_code TEXT;
CREATE INDEX IF NOT EXISTS idx_statistics_spatial_code
    ON core.statistics(spatial_unit, spatial_code);
CREATE INDEX IF NOT EXISTS idx_statistics_metric_year
    ON core.statistics(metric_name, spatial_unit, period_year);

-- ── Year-versioned admin boundaries ───────────────────────────────────────────
ALTER TABLE core.admin_boundaries
    ADD COLUMN IF NOT EXISTS boundary_year SMALLINT NOT NULL DEFAULT 0;
DROP INDEX IF EXISTS core.idx_admin_type_code;
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_type_code_year
    ON core.admin_boundaries(boundary_type, code, boundary_year);

-- ── Name → code resolution ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.spatial_aliases (
    unit_type  TEXT NOT NULL,                    -- 'ortsteil' | 'stadtbezirk' | 'wahlbezirk'
    alias      TEXT NOT NULL,                    -- normalized name (core.norm_name)
    code       TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'boundary', -- 'boundary' | 'manual'
    PRIMARY KEY (unit_type, alias)
);

CREATE OR REPLACE FUNCTION core.norm_name(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT lower(unaccent(regexp_replace(
        replace(coalesce(t, ''), 'ß', 'ss'),
        '\s+', ' ', 'g')))::text
$$;

-- Resolves a raw spatial key (name, code, or 'code name' combo) to the
-- canonical admin_boundaries code. Cascade: exact alias → already a code →
-- leading embedded code → trigram fuzzy match on the boundary name.
CREATE OR REPLACE FUNCTION core.resolve_spatial_key(p_unit TEXT, p_raw TEXT)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT code FROM (
        (SELECT code, 1 AS prio, 1.0 AS sim FROM core.spatial_aliases
          WHERE unit_type = p_unit AND alias = core.norm_name(p_raw))
        UNION ALL
        (SELECT code, 2, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit AND code = btrim(p_raw))
        UNION ALL
        (SELECT code, 3, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND code = (regexp_match(btrim(p_raw), '^(\d{1,4})\b'))[1])
        UNION ALL
        (SELECT code, 4, similarity(core.norm_name(name), core.norm_name(p_raw))::float
           FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND similarity(core.norm_name(name), core.norm_name(p_raw)) > 0.45
          ORDER BY 3 DESC LIMIT 1)
    ) candidates
    ORDER BY prio, sim DESC
    LIMIT 1
$$;
