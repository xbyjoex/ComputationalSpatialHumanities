-- =============================================================================
-- Migration 016: Partei-Register + vereinheitlichte Wahl-Anteile (Spektrum-Karte)
-- =============================================================================

-- ── Kuratiertes Partei-Register (sync aus party_registry.json) ───────────────
CREATE TABLE IF NOT EXISTS core.parties (
    key       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    position  REAL,              -- Links-Rechts (Sitzordnung); NULL = ohne Score
    color     TEXT NOT NULL,
    aliases   TEXT[] NOT NULL DEFAULT '{}'
);

-- Normalisierter Alias-Lookup für SQL-Joins (lower(trim(alias)) → key)
CREATE TABLE IF NOT EXISTS core.party_aliases (
    alias_norm TEXT PRIMARY KEY,
    party_key  TEXT NOT NULL REFERENCES core.parties(key) ON DELETE CASCADE
);

-- kleinräumig-Statistik-Datensatz → Wahltyp (sync aus election_definitions.json)
CREATE TABLE IF NOT EXISTS core.election_sources (
    dataset_id    TEXT PRIMARY KEY REFERENCES core.datasets(id),
    election_type TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'kleinraeumig'
);

-- ── Vereinheitlichte Parteianteile über beide Quellen ────────────────────────
-- Quelle A: core.election_results (exakte Stimmen, moderne Wahlen).
-- Quelle B: core.statistics kleinräumig ('Stimmenanteile X'), nur für
--           (Wahltyp, Jahr, Ebene)-Kombinationen, die A nicht liefert.
-- GROUP BY je Quelle: mehrere gebiet_codes können auf denselben spatial_code
-- auflösen (Namens-Aliase) — Stimmen werden summiert, Anteile neu berechnet.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.election_party_shares AS
WITH results_src AS (
    SELECT e.election_type,
           e.year,
           r.level,
           r.spatial_code,
           min(r.gebiet_name)  AS gebiet_name,
           r.party             AS raw_party,
           sum(r.zweitstimmen)::numeric * 100 / NULLIF(sum(r.gueltige_zweit), 0) AS share_pct,
           sum(r.zweitstimmen) AS votes,
           sum(r.waehler)::numeric * 100 / NULLIF(sum(r.wahlberechtigte), 0)     AS turnout_pct,
           'results'::text     AS source
    FROM core.election_results r
    JOIN core.elections e ON e.election_id = r.election_id
    WHERE r.spatial_code IS NOT NULL
      AND r.zweitstimmen IS NOT NULL
    GROUP BY e.election_type, e.year, r.level, r.spatial_code, r.party
),
turnout_b AS (
    SELECT dataset_id, spatial_code, period_year,
           avg(metric_value) AS turnout_pct
    FROM core.statistics
    WHERE metric_name = 'Wahlbeteiligung' AND spatial_code IS NOT NULL
    GROUP BY dataset_id, spatial_code, period_year
),
statistik_src AS (
    SELECT es.election_type,
           s.period_year          AS year,
           s.spatial_unit         AS level,
           s.spatial_code,
           min(s.spatial_key)     AS gebiet_name,
           substring(s.metric_name FROM 16) AS raw_party,   -- 'Stimmenanteile ' abschneiden
           avg(s.metric_value)    AS share_pct,
           NULL::bigint           AS votes,
           min(t.turnout_pct)     AS turnout_pct,
           'statistik'::text      AS source
    FROM core.statistics s
    JOIN core.election_sources es ON es.dataset_id = s.dataset_id
    LEFT JOIN turnout_b t
        ON t.dataset_id = s.dataset_id
       AND t.spatial_code = s.spatial_code
       AND t.period_year = s.period_year
    WHERE s.metric_name LIKE 'Stimmenanteile %'
      AND s.spatial_code IS NOT NULL
      AND s.period_year IS NOT NULL
      AND s.metric_value IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM core.election_results r2
          JOIN core.elections e2 ON e2.election_id = r2.election_id
          WHERE e2.election_type = es.election_type
            AND e2.year          = s.period_year
            AND r2.level         = s.spatial_unit
            AND r2.spatial_code IS NOT NULL
      )
    GROUP BY es.election_type, s.period_year, s.spatial_unit, s.spatial_code,
             substring(s.metric_name FROM 16)
),
unified AS (
    SELECT * FROM results_src
    UNION ALL
    SELECT * FROM statistik_src
)
SELECT u.election_type,
       u.year,
       u.level,
       u.spatial_code,
       u.gebiet_name,
       u.raw_party,
       p.key                          AS party_key,
       COALESCE(p.name, u.raw_party)  AS party_name,
       p.position                     AS party_position,
       p.color                        AS party_color,
       u.share_pct,
       u.votes,
       u.turnout_pct,
       u.source
FROM unified u
LEFT JOIN core.party_aliases pa ON pa.alias_norm = lower(trim(u.raw_party))
LEFT JOIN core.parties p        ON p.key = pa.party_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_eps_unique
    ON mart.election_party_shares(election_type, year, level, spatial_code, raw_party);
CREATE INDEX IF NOT EXISTS idx_mart_eps_lookup
    ON mart.election_party_shares(election_type, year, level);

-- ── refresh_all um die neue View erweitern (Basis: aktuelle Fassung aus 011) ──
CREATE OR REPLACE FUNCTION mart.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.statistics_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.election_party_shares;
    REFRESH MATERIALIZED VIEW mart.dataset_status;
END;
$$ LANGUAGE plpgsql;
