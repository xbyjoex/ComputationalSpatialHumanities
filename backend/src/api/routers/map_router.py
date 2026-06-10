"""Map-specific endpoints: live layers, boundaries, feature-group listing."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cached
from ..db import get_conn

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/feature-datasets")
@cached(ttl=600)
async def get_feature_datasets(_user: CurrentUser) -> ORJSONResponse:
    """List selectable groups for the unified geo layer.

    Year-variant dataset families collapse into a single group with the
    available years; standalone datasets appear as their own group.
    """
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COALESCE(d.family_id, f.dataset_id)          AS group_id,
                    COALESCE(fam.title, MIN(d.title))            AS title,
                    (d.family_id IS NOT NULL)                    AS is_family,
                    ARRAY_AGG(DISTINCT f.dataset_id)             AS dataset_ids,
                    ARRAY_AGG(DISTINCT f.year ORDER BY f.year)
                        FILTER (WHERE f.year IS NOT NULL)        AS years,
                    COUNT(*)                                     AS feature_count,
                    ARRAY_AGG(DISTINCT ST_GeometryType(f.geom))  AS geometry_types
                FROM core.geo_features f
                JOIN core.datasets d ON d.id = f.dataset_id AND d.is_active
                LEFT JOIN core.dataset_families fam ON fam.family_id = d.family_id
                GROUP BY 1, 3, fam.title
                ORDER BY 2
                """
            )
            rows = await cur.fetchall()

    return ORJSONResponse(
        [
            {
                "group_id": r["group_id"],
                "title": r["title"],
                "is_family": r["is_family"],
                "dataset_ids": r["dataset_ids"],
                "years": r["years"] or [],
                "feature_count": r["feature_count"],
                "geometry_types": r["geometry_types"],
            }
            for r in rows
        ]
    )


@router.get("/park-ride")
@cached(ttl=60)
async def get_park_ride(_user: CurrentUser) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    site_id, site_name, total_spaces, occupied_spaces,
                    free_spaces, ROUND(occupancy_pct::numeric, 1) AS occupancy_pct,
                    ST_AsGeoJSON(geom)::jsonb AS geometry,
                    measured_at
                FROM mart.park_ride_latest
                """
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": r["geometry"],
            "properties": {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in r.items()
                if k != "geometry"
            },
        }
        for r in rows
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})


@router.get("/bicycle-counters")
@cached(ttl=120)
async def get_bicycle_counters(
    _user: CurrentUser,
    days: int = Query(7, ge=1, le=365),
) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    counter_id, counter_name,
                    ST_AsGeoJSON(geom)::jsonb AS geometry,
                    ARRAY_AGG(
                        json_build_object('date', count_date, 'count', daily_total)
                        ORDER BY count_date
                    ) AS time_series
                FROM mart.bicycle_daily
                WHERE count_date >= CURRENT_DATE - (%s || ' days')::INTERVAL
                GROUP BY counter_id, counter_name, geom
                """,
                (str(days),),
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": r["geometry"],
            "properties": {
                "counter_id": r["counter_id"],
                "counter_name": r["counter_name"],
                "time_series": r["time_series"],
            },
        }
        for r in rows
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})


@router.get("/restrictions")
@cached(ttl=120)
async def get_active_restrictions(_user: CurrentUser) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    id, restriction_id, dataset_id, restriction_type, title, description,
                    ST_AsGeoJSON(geom)::jsonb AS geometry,
                    valid_from, valid_until, properties
                FROM mart.active_restrictions
                LIMIT 5000
                """
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "geometry": r["geometry"],
            "properties": {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in r.items()
                if k not in ("geometry", "id")
            },
        }
        for r in rows
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})


@router.get("/admin-boundaries")
@cached(ttl=3600)
async def get_admin_boundaries(
    _user: CurrentUser,
    boundary_type: str = Query("ortsteil"),
) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT code, name, parent_code,
                       ST_AsGeoJSON(geom)::jsonb AS geometry
                FROM core.admin_boundaries
                WHERE boundary_type = %s
                """,
                (boundary_type,),
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "properties": {"code": r["code"], "name": r["name"], "parent_code": r["parent_code"]},
            "geometry": r["geometry"],
        }
        for r in rows
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})
