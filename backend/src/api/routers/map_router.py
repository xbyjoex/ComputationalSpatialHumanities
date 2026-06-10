"""Map-specific endpoints: bbox queries, live layers, geo features."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cached
from ..db import get_conn

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/features")
@cached(ttl=30)
async def get_map_features(
    _user: CurrentUser,
    xmin: float = Query(..., description="Bounding box west longitude"),
    ymin: float = Query(..., description="Bounding box south latitude"),
    xmax: float = Query(..., description="Bounding box east longitude"),
    ymax: float = Query(..., description="Bounding box north latitude"),
    dataset_ids: list[str] | None = Query(None),
    feature_types: list[str] | None = Query(None),
    limit: int = Query(2000, le=5000),
) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    id, dataset_id, dataset_title, feature_type, name,
                    ST_AsGeoJSON(geom)::jsonb AS geometry,
                    properties, valid_from, valid_until
                FROM mart.geo_features_map
                WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  AND (%s::text[] IS NULL OR dataset_id = ANY(%s))
                  AND (%s::text[] IS NULL OR feature_type = ANY(%s))
                LIMIT %s
                """,
                (xmin, ymin, xmax, ymax, dataset_ids, dataset_ids, feature_types, feature_types, limit),
            )
            rows = await cur.fetchall()

    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "id": r["id"],
                "geometry": r["geometry"],
                "properties": {
                    "dataset_id": r["dataset_id"],
                    "dataset_title": r["dataset_title"],
                    "feature_type": r["feature_type"],
                    "name": r["name"],
                    "valid_from": r["valid_from"].isoformat() if r["valid_from"] else None,
                    "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
                    **(r["properties"] or {}),
                },
            }
        )

    return ORJSONResponse({"type": "FeatureCollection", "features": features})


@router.get("/feature-datasets")
@cached(ttl=600)
async def get_feature_datasets(_user: CurrentUser) -> ORJSONResponse:
    """List all datasets that have features in the unified geo layer."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    dataset_id,
                    dataset_title,
                    COUNT(*) AS feature_count,
                    ARRAY_AGG(DISTINCT ST_GeometryType(geom)) AS geometry_types
                FROM mart.geo_features_map
                GROUP BY dataset_id, dataset_title
                ORDER BY dataset_title
                """
            )
            rows = await cur.fetchall()

    return ORJSONResponse(
        [
            {
                "dataset_id": r["dataset_id"],
                "dataset_title": r["dataset_title"],
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
