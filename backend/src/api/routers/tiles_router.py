"""Vector-tile endpoint: PostGIS ST_AsMVT over the unified geo layer.

Replaces the bbox-GeoJSON path (hard 5000-feature cap) — MapLibre consumes
the tiles natively, so even Baumkataster-scale datasets render completely.

Tiles carry thin attributes only (no JSONB properties) to stay small; full
feature properties come from GET /map/feature/{id} on click. The year filter
is applied client-side in the MapLibre style — tiles contain all years, which
keeps the per-tile Redis cache from fragmenting per year.

Live layers (Park+Ride, bicycle counters, restrictions) are intentionally NOT
served as tiles: they are tiny GeoJSON payloads polled every 60-300 s, and
routing them through the 24h tile cache would defeat their freshness.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cache_get_bytes, cache_set_bytes, cached, tiles_version
from ..db import get_conn

router = APIRouter(prefix="/map", tags=["tiles"])

MVT_CONTENT_TYPE = "application/vnd.mapbox-vector-tile"
TILE_TTL_SECONDS = 86_400  # invalidated via tiles:version bump after nightly ETL
TILE_FEATURE_LIMIT = 20_000  # RAM guard for low-zoom tiles on the 4 GB VPS
MAX_FILTER_IDS = 25

_TILE_SQL = """
WITH bounds AS (
    SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS env,
           -- margin matches the 64/4096 MVT buffer so edge features clip cleanly
           ST_TileEnvelope(%(z)s, %(x)s, %(y)s, margin => 0.015625) AS env_margin
),
src AS (
    SELECT f.id, f.dataset_id, d.family_id, f.year, f.feature_type, f.name,
           d.title AS dataset_title, f.geom
    FROM core.geo_features f
    JOIN core.datasets d ON d.id = f.dataset_id AND d.is_active
    CROSS JOIN bounds b
    WHERE f.geom && ST_Transform(b.env_margin, 4326)
      AND (
            (%(dataset_ids)s::text[] IS NOT NULL AND f.dataset_id = ANY(%(dataset_ids)s::text[]))
         OR (%(family_ids)s::text[]  IS NOT NULL AND d.family_id  = ANY(%(family_ids)s::text[]))
      )
    LIMIT %(feature_limit)s
),
mvtgeom AS (
    SELECT ST_AsMVTGeom(ST_Transform(s.geom, 3857), b.env, 4096, 64, true) AS geom,
           s.id, s.dataset_id, s.family_id, s.year, s.feature_type, s.name,
           s.dataset_title
    FROM src s CROSS JOIN bounds b
)
SELECT ST_AsMVT(mvtgeom.*, 'features', 4096, 'geom', 'id') AS tile
FROM mvtgeom
WHERE geom IS NOT NULL
"""


@router.get("/tiles/{z}/{x}/{y}.pbf")
async def get_tile(
    _user: CurrentUser,
    z: int,
    x: int,
    y: int,
    dataset_ids: list[str] | None = Query(None),
    family_ids: list[str] | None = Query(None),
) -> Response:
    if not 0 <= z <= 18:
        raise HTTPException(status_code=400, detail="zoom out of range (0-18)")
    max_index = 1 << z
    if not (0 <= x < max_index and 0 <= y < max_index):
        raise HTTPException(status_code=400, detail="tile index out of range")
    if not dataset_ids and not family_ids:
        raise HTTPException(
            status_code=400, detail="dataset_ids or family_ids required"
        )
    if len(dataset_ids or []) + len(family_ids or []) > MAX_FILTER_IDS:
        raise HTTPException(
            status_code=400, detail=f"at most {MAX_FILTER_IDS} ids per request"
        )

    filter_hash = hashlib.sha1(
        "|".join(sorted(dataset_ids or []) + ["~"] + sorted(family_ids or [])).encode()
    ).hexdigest()[:16]
    version = await tiles_version()
    cache_key = f"tile:{version}:{z}/{x}/{y}:{filter_hash}"

    tile = await cache_get_bytes(cache_key)
    if tile is None:
        async with get_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _TILE_SQL,
                    {
                        "z": z,
                        "x": x,
                        "y": y,
                        "dataset_ids": dataset_ids,
                        "family_ids": family_ids,
                        "feature_limit": TILE_FEATURE_LIMIT,
                    },
                )
                row = await cur.fetchone()
        tile = bytes(row["tile"]) if row and row["tile"] is not None else b""
        await cache_set_bytes(cache_key, tile, TILE_TTL_SECONDS)

    if not tile:
        return Response(status_code=204)
    return Response(content=tile, media_type=MVT_CONTENT_TYPE)


@router.get("/feature/{feature_id}")
@cached(ttl=300)
async def get_feature_detail(
    _user: CurrentUser,
    feature_id: int,
) -> ORJSONResponse:
    """Full properties for a single feature — tiles only carry thin attributes."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT f.id, f.dataset_id, d.title AS dataset_title, d.family_id,
                       f.feature_type, f.name, f.description, f.year,
                       f.properties, f.valid_from, f.valid_until, f.updated_at
                FROM core.geo_features f
                JOIN core.datasets d ON d.id = f.dataset_id
                WHERE f.id = %s
                """,
                (feature_id,),
            )
            row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return ORJSONResponse(
        {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in row.items()
        }
    )
