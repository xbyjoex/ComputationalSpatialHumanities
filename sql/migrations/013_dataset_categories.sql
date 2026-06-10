-- =============================================================================
-- Migration 013: Thematic dataset categories
-- =============================================================================
-- Categories mirror the opendata.leipzig.de CKAN groups (13 DCAT themes,
-- German titles) plus a "sonstiges" fallback; curated in
-- dataset_categories.json and synced by the ETL scheduler on startup.

CREATE TABLE IF NOT EXISTS core.dataset_categories (
    category_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    position    SMALLINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE core.datasets
    ADD COLUMN IF NOT EXISTS categories TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_datasets_categories
    ON core.datasets USING gin(categories);

-- Slug lookups for /datasets/by-slug/{slug}; names verified unique across
-- all 398 contracts — the index makes future collisions loud.
CREATE UNIQUE INDEX IF NOT EXISTS idx_datasets_name_unique ON core.datasets(name);
