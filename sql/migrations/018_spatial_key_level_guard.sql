-- 018_spatial_key_level_guard.sql
--
-- Fix: core.resolve_spatial_key() mapped names of one administrative level onto
-- codes of another. The trigram fallback (branch 4) scores
-- similarity('grunau-mitte', 'mitte') above the 0.45 threshold, so the
-- Stadtbezirk "Mitte" resolved to the Ortsteil code 62. Same for
-- "Südost" -> 02 (Zentrum-Südost) and "Nordwest" -> 05 (Zentrum-Nordwest).
--
-- Root cause outside our control: the source files mix Ortsteil, Stadtbezirk and
-- city-total rows in one file without a level column, so the loader tags every
-- row with the same spatial_unit and the resolver has to guess.
--
-- 13862 rows across 42 datasets carried a wrong Ortsteil code, inflating the 2024
-- population sum to 805218 instead of the correct 632560.
--
-- Guard: never fuzzy-match a raw key that is the exact name of a *different*
-- boundary type. Exact matches (branches 1-3) are unaffected, so a name that
-- legitimately exists on the requested level still resolves.

CREATE OR REPLACE FUNCTION core.resolve_spatial_key(p_unit TEXT, p_raw TEXT)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT code FROM (
        (SELECT code, 1 AS prio, 1.0 AS sim FROM core.spatial_aliases
          WHERE unit_type = p_unit AND alias = core.norm_name(p_raw))
        UNION ALL
        (SELECT code, 2, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit AND code = btrim(p_raw))
        UNION ALL
        -- \y = word boundary in Postgres regex (\b would be backspace)
        (SELECT code, 3, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND code = (regexp_match(btrim(p_raw), '^(\d{1,4})\y'))[1])
        UNION ALL
        (SELECT code, 4, similarity(core.norm_name(name), core.norm_name(p_raw))::float
           FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND similarity(core.norm_name(name), core.norm_name(p_raw)) > 0.45
            AND NOT EXISTS (
                SELECT 1 FROM core.admin_boundaries other
                 WHERE other.boundary_type <> p_unit
                   AND core.norm_name(other.name) = core.norm_name(p_raw)
            )
          ORDER BY 3 DESC LIMIT 1)
    ) candidates
    ORDER BY prio, sim DESC
    LIMIT 1
$$;

-- One-time repair: drop the codes that were assigned from a foreign level name.
-- Idempotent: after the function fix, no new rows can enter this state.
UPDATE core.statistics s
   SET spatial_code = NULL
 WHERE s.spatial_code IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM core.admin_boundaries other
        WHERE other.boundary_type <> s.spatial_unit
          AND core.norm_name(other.name) = core.norm_name(s.spatial_key)
   );
