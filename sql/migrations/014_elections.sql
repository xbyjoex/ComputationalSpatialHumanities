-- =============================================================================
-- Migration 014: Semantic election domain
-- =============================================================================
-- The 'Offene Wahldaten' CSVs carry per-party votes in anonymous columns
-- (D1/F1/E1...) keyed by the official ballot order. election_definitions.json
-- curates the column→party mapping per election (verified against the named
-- shares of the statistik.leipzig.de API); the domain loader
-- (etl/src/domains/elections.py) writes one row per Gebiet × Partei here.
-- vote_mode: erst_zweit (BTW/LTW), single (EW), kommunal (SRW, 3 Stimmen).
-- Votes always land in `zweitstimmen` for single/kommunal elections.

CREATE TABLE IF NOT EXISTS core.elections (
    election_id   TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    election_type TEXT NOT NULL,
    election_date DATE,
    year          SMALLINT NOT NULL,
    vote_mode     TEXT NOT NULL CHECK (vote_mode IN ('erst_zweit', 'single', 'kommunal')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.election_results (
    id               BIGSERIAL PRIMARY KEY,
    election_id      TEXT NOT NULL REFERENCES core.elections(election_id),
    dataset_id       TEXT NOT NULL REFERENCES core.datasets(id),
    level            TEXT NOT NULL CHECK (level IN ('wahlbezirk', 'ortsteil', 'stadtbezirk', 'stadt')),
    gebiet_code      TEXT NOT NULL,   -- gebiet-nr (4-stellig wahlbezirk) | Name (ortsteil) | 'leipzig'
    gebiet_name      TEXT,
    spatial_code     TEXT,            -- kanonischer Boundary-Code; NULL für stadt/Briefwahlbezirke
    party            TEXT NOT NULL,
    party_index      SMALLINT,        -- 1-basiert = D/F/E-Spaltenindex
    erststimmen      INTEGER,         -- NULL außer bei vote_mode='erst_zweit'
    zweitstimmen     INTEGER,
    -- Turnout je Gebiet, denormalisiert auf die Partei-Zeilen:
    wahlberechtigte  INTEGER,         -- A
    waehler          INTEGER,         -- B
    briefwaehler     INTEGER,         -- B1
    ungueltige_erst  INTEGER,         -- C
    gueltige_erst    INTEGER,         -- D
    ungueltige_zweit INTEGER,         -- E (bzw. C bei single/kommunal)
    gueltige_zweit   INTEGER,         -- F (bzw. D/E bei single/kommunal)
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (election_id, level, gebiet_code, party)
);
CREATE INDEX IF NOT EXISTS idx_election_results_lookup
    ON core.election_results(election_id, level, party);
CREATE INDEX IF NOT EXISTS idx_election_results_spatial
    ON core.election_results(level, spatial_code);
CREATE INDEX IF NOT EXISTS idx_election_results_dataset
    ON core.election_results(dataset_id);
