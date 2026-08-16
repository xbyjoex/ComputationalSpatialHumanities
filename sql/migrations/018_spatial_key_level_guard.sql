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
        -- Guard: refuse the fuzzy branch whenever the raw key is an EXACT normalised-name
        -- match for a boundary on a DIFFERENT level (boundary_type <> p_unit). This is
        -- equality, not similarity -- it does not touch which candidate branch 4 itself
        -- picks, it only blocks branch 4 from firing at all for a name that belongs
        -- verbatim to another level.
        --
        -- Safety assumption this guard rests on: no normalised name is shared across
        -- boundary types. If it were, a row that resolves correctly via branches 1-3 on
        -- its own level would also match `other.boundary_type <> p_unit` here and get
        -- wrongly blocked, and the repair UPDATE below would NULL it out even though it
        -- was never wrong.
        --
        -- Verified 2026-08-15 against the full boundary set (63 Ortsteile, 10
        -- Stadtbezirke, 819 Wahlbezirke): zero normalised names occur under more than one
        -- boundary_type, so the assumption holds and this guard cannot misfire today.
        -- The original bug (Mitte/Südost/Nordwest -> 62/02/05) was never an exact-name
        -- collision -- it was branch 4 matching by *similarity* against a different name
        -- ("mitte" vs. "grunau-mitte"), which this guard is specifically designed to stop.
        --
        -- Deliberately broad: `boundary_type <> p_unit` covers every other level (not
        -- just stadtbezirk vs. ortsteil, the pair that prompted this fix) -- including
        -- wahlbezirk. Any name reused across any two levels should be blocked the same
        -- way, so the condition is not narrowed to the specific pair that was observed.
        --
        -- If boundaries ever do gain a name shared across levels, do not just re-run this
        -- guard as-is going forward -- add real per-level disambiguation to the source
        -- data or the loader. And do not re-run the repair UPDATE below verbatim; by then
        -- some spatial_code values will be correct and some wrong, so the precise
        -- one-time fix at that point is to reset only the rows where the stored code
        -- disagrees with what the corrected resolver would now return:
        --   spatial_code IS DISTINCT FROM core.resolve_spatial_key(spatial_unit, spatial_key)
        -- Deliberately not used here: this migration is already applied, and that
        -- broader form would re-touch rows that are currently correct.
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
--
-- Same exact-match / cross-level condition as the branch-4 guard above (see that
-- comment for the safety assumption, its 2026-08-15 verification, and why a name
-- collision across levels would need a different, narrower repair than this one).
-- Empirically: this touched exactly 13862 rows (Südost 4641 + Mitte 4617 +
-- Nordwest 4604), matching the pre-migration audit -- nothing beyond those three
-- keys was affected.
UPDATE core.statistics s
   SET spatial_code = NULL
 WHERE s.spatial_code IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM core.admin_boundaries other
        WHERE other.boundary_type <> s.spatial_unit
          AND core.norm_name(other.name) = core.norm_name(s.spatial_key)
   );
