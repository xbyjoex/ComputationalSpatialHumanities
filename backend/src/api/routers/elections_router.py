"""Unified election results (semantic domain, core.election_results)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cached
from ..db import get_conn
from ..spectrum import compute_spectrum

router = APIRouter(prefix="/elections", tags=["elections"])

_LEVELS = ("wahlbezirk", "ortsteil", "stadtbezirk", "stadt")


@router.get("")
@cached(ttl=3600)
async def list_elections(_user: CurrentUser) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT e.election_id, e.title, e.election_type, e.election_date,
                       e.year, e.vote_mode,
                       ARRAY_AGG(DISTINCT r.level) AS levels,
                       COUNT(DISTINCT r.party) AS party_count
                FROM core.elections e
                LEFT JOIN core.election_results r ON r.election_id = e.election_id
                GROUP BY e.election_id
                ORDER BY e.election_date DESC NULLS LAST
                """
            )
            rows = await cur.fetchall()
    return ORJSONResponse(rows)


_SPECTRUM_LEVELS = ("wahlbezirk", "ortsteil", "stadtbezirk")
_SPECTRUM_TITLES = {
    "bundestagswahl": "Bundestagswahl",
    "europawahl": "Europawahl",
    "landtagswahl": "Landtagswahl",
    "stadtratswahl": "Stadtratswahl",
    "oberbuergermeisterwahl": "Oberbürgermeisterwahl",
}


@router.get("/spectrum/options")
@cached(ttl=3600)
async def spectrum_options(_user: CurrentUser) -> ORJSONResponse:
    """Verfügbare (Wahltyp, Jahr, Ebene)-Kombinationen + Partei-Register."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT election_type, year,
                       array_agg(DISTINCT level ORDER BY level) AS levels
                FROM mart.election_party_shares
                GROUP BY election_type, year
                ORDER BY election_type, year DESC
                """
            )
            combos = await cur.fetchall()
            await cur.execute(
                """
                SELECT key, name, position, color
                FROM core.parties
                ORDER BY position NULLS LAST, key
                """
            )
            parties = await cur.fetchall()

    grouped: dict[str, list[dict]] = {}
    for c in combos:
        grouped.setdefault(c["election_type"], []).append(
            {"year": c["year"], "levels": c["levels"]}
        )
    elections = [
        {"election_type": t, "title": _SPECTRUM_TITLES.get(t, t.title()), "years": years}
        for t, years in grouped.items()
    ]
    return ORJSONResponse({"elections": elections, "parties": parties})


@router.get("/spectrum")
@cached(ttl=3600)
async def election_spectrum(
    _user: CurrentUser,
    election_type: str = Query(..., max_length=50),
    year: int = Query(...),
    level: str = Query("ortsteil"),
) -> ORJSONResponse:
    """Links-Rechts-Score + Parteiverteilung je Gebiet als GeoJSON.

    Ein Fetch versorgt Kartenfarbe UND Hover-Pies (parties in den Properties).
    Wahlbezirk-Geometrien sind je Wahljahr versioniert (boundary_year).
    """
    if level not in _SPECTRUM_LEVELS:
        raise HTTPException(status_code=400, detail=f"level muss eines von {_SPECTRUM_LEVELS} sein")
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT eps.spatial_code,
                       COALESCE(b.name, min(eps.gebiet_name)) AS name,
                       max(eps.turnout_pct)                   AS turnout_pct,
                       ST_AsGeoJSON(b.geom)::jsonb            AS geometry,
                       jsonb_agg(jsonb_build_object(
                           'key',      eps.party_key,
                           'name',     eps.party_name,
                           'position', eps.party_position,
                           'color',    eps.party_color,
                           'share',    eps.share_pct
                       )) AS shares
                FROM mart.election_party_shares eps
                JOIN core.admin_boundaries b
                    ON b.boundary_type = eps.level
                    AND b.code = eps.spatial_code
                    AND (b.boundary_year = 0 OR b.boundary_year = eps.year)
                WHERE eps.election_type = %s AND eps.year = %s AND eps.level = %s
                GROUP BY eps.spatial_code, b.name, b.geom
                """,
                (election_type, year, level),
            )
            rows = await cur.fetchall()

    features = []
    for r in rows:
        spec = compute_spectrum(r["shares"])
        features.append(
            {
                "type": "Feature",
                "geometry": r["geometry"],
                "properties": {
                    "gebiet_code": r["spatial_code"],
                    "name": r["name"],
                    "score": spec["score"],
                    "coverage_pct": spec["coverage_pct"],
                    "turnout_pct": float(r["turnout_pct"]) if r["turnout_pct"] is not None else None,
                    "parties": spec["parties"],
                },
            }
        )
    return ORJSONResponse({"type": "FeatureCollection", "features": features})


@router.get("/{election_id}/summary")
@cached(ttl=3600)
async def election_summary(election_id: str, _user: CurrentUser) -> ORJSONResponse:
    """Stadtweites Partei-Ranking + Wahlbeteiligung."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM core.elections WHERE election_id = %s", (election_id,)
            )
            election = await cur.fetchone()
            if not election:
                raise HTTPException(status_code=404, detail="Wahl nicht gefunden")

            await cur.execute(
                """
                SELECT r.party, r.party_index, r.erststimmen, r.zweitstimmen,
                       ROUND(r.zweitstimmen::numeric * 100 / NULLIF(r.gueltige_zweit, 0), 2) AS anteil_pct,
                       r.wahlberechtigte, r.waehler, r.briefwaehler, r.gueltige_zweit,
                       p.color AS party_color
                FROM core.election_results r
                LEFT JOIN core.party_aliases pa ON pa.alias_norm = lower(trim(r.party))
                LEFT JOIN core.parties p ON p.key = pa.party_key
                WHERE r.election_id = %s AND r.level = 'stadt'
                ORDER BY r.zweitstimmen DESC NULLS LAST
                """,
                (election_id,),
            )
            parties = await cur.fetchall()

    turnout = None
    if parties and parties[0]["wahlberechtigte"]:
        turnout = round(parties[0]["waehler"] * 100 / parties[0]["wahlberechtigte"], 2)
    return ORJSONResponse(
        {
            "election": election,
            "turnout_pct": turnout,
            "parties": [
                {k: v for k, v in p.items()
                 if k not in ("wahlberechtigte", "waehler", "briefwaehler", "gueltige_zweit")}
                for p in parties
            ],
        }
    )


@router.get("/{election_id}/results")
@cached(ttl=3600)
async def election_results(
    election_id: str,
    _user: CurrentUser,
    level: str = Query("wahlbezirk"),
    party: str | None = Query(None, max_length=100),
    limit: int = Query(500, le=5000),
    offset: int = Query(0, ge=0),
) -> ORJSONResponse:
    if level not in _LEVELS:
        raise HTTPException(status_code=400, detail=f"level muss eines von {_LEVELS} sein")
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) AS n FROM core.election_results
                WHERE election_id = %s AND level = %s
                  AND (%s::text IS NULL OR party = %s)
                """,
                (election_id, level, party, party),
            )
            total = (await cur.fetchone())["n"]
            await cur.execute(
                """
                SELECT gebiet_code, gebiet_name, spatial_code, party, party_index,
                       erststimmen, zweitstimmen,
                       ROUND(zweitstimmen::numeric * 100 / NULLIF(gueltige_zweit, 0), 2) AS anteil_pct,
                       wahlberechtigte, waehler, briefwaehler,
                       gueltige_erst, gueltige_zweit
                FROM core.election_results
                WHERE election_id = %s AND level = %s
                  AND (%s::text IS NULL OR party = %s)
                ORDER BY gebiet_code, party_index
                LIMIT %s OFFSET %s
                """,
                (election_id, level, party, party, limit, offset),
            )
            rows = await cur.fetchall()
    return ORJSONResponse({"total": total, "limit": limit, "offset": offset, "items": rows})


@router.get("/{election_id}/choropleth")
@cached(ttl=3600)
async def election_choropleth(
    election_id: str,
    _user: CurrentUser,
    party: str,
    level: str = Query("wahlbezirk"),
) -> ORJSONResponse:
    """Stimmenanteil einer Partei je Gebiet als GeoJSON — Map-Hook.

    Wahlbezirk-Geometrien sind je Wahljahr versioniert (boundary_year).
    """
    if level not in ("wahlbezirk", "ortsteil", "stadtbezirk"):
        raise HTTPException(status_code=400, detail="level nicht kartierbar")
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT r.gebiet_code, r.gebiet_name, r.party,
                       r.zweitstimmen,
                       ROUND(r.zweitstimmen::numeric * 100 / NULLIF(r.gueltige_zweit, 0), 2) AS anteil_pct,
                       ST_AsGeoJSON(b.geom)::jsonb AS geometry,
                       b.name AS boundary_name
                FROM core.election_results r
                JOIN core.elections e ON e.election_id = r.election_id
                JOIN core.admin_boundaries b
                    ON b.boundary_type = r.level
                    AND b.code = r.spatial_code
                    AND (b.boundary_year = 0 OR b.boundary_year = e.year)
                WHERE r.election_id = %s AND r.level = %s AND r.party = %s
                  AND r.spatial_code IS NOT NULL
                """,
                (election_id, level, party),
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": r["geometry"],
            "properties": {
                "gebiet_code": r["gebiet_code"],
                "name": r["boundary_name"] or r["gebiet_name"],
                "party": r["party"],
                "zweitstimmen": r["zweitstimmen"],
                "metric_value": float(r["anteil_pct"]) if r["anteil_pct"] is not None else None,
                "metric_unit": "%",
            },
        }
        for r in rows
        if r["geometry"]
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})
