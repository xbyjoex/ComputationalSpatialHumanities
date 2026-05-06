-- =============================================================================
-- Migration 001: Core schemas, tables, indexes
-- =============================================================================

-- ── Schemas ───────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw_ingest;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS auth;

-- ── Auth tables ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth.users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name   TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked     BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON auth.refresh_tokens(user_id);

-- ── ETL audit log ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_ingest.etl_runs (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      TEXT NOT NULL,
    dataset_title   TEXT,
    schedule        TEXT NOT NULL CHECK (schedule IN ('nightly','live')),
    status          TEXT NOT NULL CHECK (status IN ('started','success','failed','skipped')),
    rows_extracted  INTEGER,
    rows_loaded     INTEGER,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER GENERATED ALWAYS AS (
        CASE WHEN finished_at IS NOT NULL
             THEN EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER * 1000
             ELSE NULL END
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_etl_runs_dataset ON raw_ingest.etl_runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_etl_runs_started ON raw_ingest.etl_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_runs_status ON raw_ingest.etl_runs(status);

-- ── Dataset registry ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.datasets (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    title           TEXT NOT NULL,
    schedule        TEXT NOT NULL CHECK (schedule IN ('nightly','live')),
    has_geo         BOOLEAN NOT NULL DEFAULT FALSE,
    formats         TEXT[],
    best_url        TEXT,
    best_format     TEXT,
    resource_count  INTEGER NOT NULL DEFAULT 0,
    last_ingested   TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS idx_datasets_schedule ON core.datasets(schedule);
CREATE INDEX IF NOT EXISTS idx_datasets_has_geo ON core.datasets(has_geo);
CREATE INDEX IF NOT EXISTS idx_datasets_title_trgm ON core.datasets USING gin(title gin_trgm_ops);

-- ── Generic statistical data (non-geo) ────────────────────────────────────────
-- Stores time-series statistics from statistik.leipzig.de API
CREATE TABLE IF NOT EXISTS core.statistics (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      TEXT NOT NULL REFERENCES core.datasets(id),
    period_type     TEXT,          -- 'year', 'quarter', 'month'
    period_label    TEXT,          -- '2023', '2023-Q1', '2023-01'
    period_year     SMALLINT,
    period_quarter  SMALLINT,
    period_month    SMALLINT,
    spatial_unit    TEXT,          -- 'city', 'ortsteil', 'stadtbezirk', 'wahlbezirk'
    spatial_key     TEXT,          -- code or name of the spatial unit
    metric_name     TEXT NOT NULL,
    metric_value    DOUBLE PRECISION,
    metric_unit     TEXT,
    raw_payload     JSONB,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_statistics_dataset ON core.statistics(dataset_id);
CREATE INDEX IF NOT EXISTS idx_statistics_period ON core.statistics(period_year, period_quarter);
CREATE INDEX IF NOT EXISTS idx_statistics_spatial ON core.statistics(spatial_unit, spatial_key);
CREATE INDEX IF NOT EXISTS idx_statistics_metric ON core.statistics(metric_name);
CREATE INDEX IF NOT EXISTS idx_statistics_payload ON core.statistics USING gin(raw_payload);

-- ── Geo features table ────────────────────────────────────────────────────────
-- Single table for all vector geo datasets, discriminated by dataset_id
CREATE TABLE IF NOT EXISTS core.geo_features (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      TEXT NOT NULL REFERENCES core.datasets(id),
    feature_id      TEXT,          -- original feature ID from source
    feature_type    TEXT,          -- e.g. 'Baustelle', 'ParkRide', 'Radweg'
    name            TEXT,
    description     TEXT,
    geom            GEOMETRY(Geometry, 4326),
    properties      JSONB,
    valid_from      TIMESTAMPTZ,
    valid_until     TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_geo_features_dataset ON core.geo_features(dataset_id);
CREATE INDEX IF NOT EXISTS idx_geo_features_geom ON core.geo_features USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_geo_features_feature_type ON core.geo_features(feature_type);
CREATE INDEX IF NOT EXISTS idx_geo_features_props ON core.geo_features USING gin(properties);

-- ── Park+Ride live occupancy ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.park_ride_occupancy (
    id              BIGSERIAL PRIMARY KEY,
    site_id         TEXT NOT NULL,
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
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_site ON core.park_ride_occupancy(site_id);
CREATE INDEX IF NOT EXISTS idx_pr_measured ON core.park_ride_occupancy(measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_pr_geom ON core.park_ride_occupancy USING gist(geom);

-- ── Bicycle counters (live, hourly/daily) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.bicycle_counts (
    id              BIGSERIAL PRIMARY KEY,
    counter_id      TEXT NOT NULL,
    counter_name    TEXT,
    geom            GEOMETRY(Point, 4326),
    count_period    TEXT NOT NULL CHECK (count_period IN ('hour','day')),
    period_start    TIMESTAMPTZ NOT NULL,
    count_value     INTEGER,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (counter_id, count_period, period_start)
);
CREATE INDEX IF NOT EXISTS idx_bicycle_counter ON core.bicycle_counts(counter_id);
CREATE INDEX IF NOT EXISTS idx_bicycle_period ON core.bicycle_counts(count_period, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_bicycle_geom ON core.bicycle_counts USING gist(geom);

-- ── Traffic restrictions (baustellen / verkehrsraum) ─────────────────────────
CREATE TABLE IF NOT EXISTS core.traffic_restrictions (
    id              BIGSERIAL PRIMARY KEY,
    restriction_id  TEXT,
    dataset_id      TEXT NOT NULL REFERENCES core.datasets(id),
    restriction_type TEXT,
    title           TEXT,
    description     TEXT,
    geom            GEOMETRY(Geometry, 4326),
    valid_from      TIMESTAMPTZ,
    valid_until     TIMESTAMPTZ,
    properties      JSONB,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tr_dataset ON core.traffic_restrictions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_tr_geom ON core.traffic_restrictions USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_tr_valid ON core.traffic_restrictions(valid_from, valid_until);

-- ── Admin boundaries / spatial reference ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.admin_boundaries (
    id              SERIAL PRIMARY KEY,
    boundary_type   TEXT NOT NULL, -- 'stadtbezirk', 'ortsteil', 'wahlbezirk', 'wahlkreis'
    code            TEXT,
    name            TEXT NOT NULL,
    geom            GEOMETRY(MultiPolygon, 4326),
    parent_code     TEXT,
    area_sqm        DOUBLE PRECISION GENERATED ALWAYS AS (
        CASE WHEN geom IS NOT NULL THEN ST_Area(geom::geography) ELSE NULL END
    ) STORED
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_type_code ON core.admin_boundaries(boundary_type, code);
CREATE INDEX IF NOT EXISTS idx_admin_geom ON core.admin_boundaries USING gist(geom);
CREATE INDEX IF NOT EXISTS idx_admin_name_trgm ON core.admin_boundaries USING gin(name gin_trgm_ops);

-- ── GTFS transit data ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.transit_stops (
    stop_id         TEXT PRIMARY KEY,
    stop_name       TEXT,
    stop_code       TEXT,
    stop_desc       TEXT,
    geom            GEOMETRY(Point, 4326),
    location_type   SMALLINT,
    parent_station  TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_transit_stops_geom ON core.transit_stops USING gist(geom);

CREATE TABLE IF NOT EXISTS core.transit_routes (
    route_id        TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name  TEXT,
    route_type      SMALLINT,
    route_color     TEXT,
    route_text_color TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Raw payload store (for datasets without structured parsers) ───────────────
CREATE TABLE IF NOT EXISTS raw_ingest.payloads (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      TEXT NOT NULL,
    resource_url    TEXT NOT NULL,
    format          TEXT,
    payload         JSONB,
    raw_text        TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum        TEXT,
    is_processed    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_payloads_dataset ON raw_ingest.payloads(dataset_id);
CREATE INDEX IF NOT EXISTS idx_payloads_processed ON raw_ingest.payloads(is_processed) WHERE NOT is_processed;
