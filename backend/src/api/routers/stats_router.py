"""Statistics / analytics endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cached
from ..db import get_conn

router = APIRouter(prefix="/stats", tags=["statistics"])


@router.get("/metrics")
@cached(ttl=300)
async def list_metrics(
    _user: CurrentUser,
    dataset_id: str | None = Query(None),
    spatial_unit: str | None = Query(None),
    grouped: bool = Query(False),
) -> Any:
    """Metrics that can actually be visualized.

    Only numeric values count as metrics; for a concrete spatial unit
    (ortsteil/stadtbezirk/wahlbezirk) the metric must additionally have rows
    with a resolved spatial_code — otherwise it cannot join a boundary and
    would render an empty choropleth.

    grouped=true folds metric variants into the canonical indicator catalog
    (core.indicators): [{indicator_id, name, unit, topic, metrics: [...]}];
    uncatalogued metrics come last with indicator_id null.
    """
    conditions = ["metric_value IS NOT NULL"]
    params: list[Any] = []
    if dataset_id:
        conditions.append("dataset_id = %s")
        params.append(dataset_id)
    if spatial_unit:
        conditions.append("spatial_unit = %s")
        params.append(spatial_unit)
        if spatial_unit != "city":
            conditions.append("spatial_code IS NOT NULL")
    where = " AND ".join(conditions)

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            if not grouped:
                await cur.execute(
                    f"SELECT DISTINCT metric_name FROM mart.statistics_latest WHERE {where} ORDER BY 1",
                    params,
                )
                rows = await cur.fetchall()
                return [r["metric_name"] for r in rows]

            await cur.execute(
                f"""
                SELECT i.indicator_id, i.name, i.unit, i.topic,
                       ARRAY_AGG(DISTINCT m.metric_name) AS metrics
                FROM (
                    SELECT DISTINCT dataset_id, metric_name
                    FROM mart.statistics_latest WHERE {where}
                ) m
                LEFT JOIN core.indicator_metrics im
                    ON im.dataset_id = m.dataset_id AND im.metric_name = m.metric_name
                LEFT JOIN core.indicators i ON i.indicator_id = im.indicator_id
                GROUP BY i.indicator_id, i.name, i.unit, i.topic
                ORDER BY i.topic NULLS LAST, i.name NULLS LAST
                """,
                params,
            )
            rows = await cur.fetchall()
    return ORJSONResponse(rows)


@router.get("/timeseries")
@cached(ttl=300)
async def timeseries(
    _user: CurrentUser,
    dataset_id: str,
    metric_name: str,
    spatial_unit: str = Query("city"),
    spatial_key: str | None = Query(None),
) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    spatial_key, period_label, period_year, period_quarter,
                    metric_value, metric_unit
                FROM core.statistics
                WHERE dataset_id = %s
                  AND metric_name = %s
                  AND spatial_unit = %s
                  AND (%s::text IS NULL OR spatial_key = %s)
                ORDER BY period_year, period_quarter NULLS LAST
                """,
                (dataset_id, metric_name, spatial_unit, spatial_key, spatial_key),
            )
            rows = await cur.fetchall()

    return ORJSONResponse(
        {
            "dataset_id": dataset_id,
            "metric": metric_name,
            "spatial_unit": spatial_unit,
            "series": [
                {
                    "key": r["spatial_key"],
                    "period": r["period_label"],
                    "year": r["period_year"],
                    "value": r["metric_value"],
                    "unit": r["metric_unit"],
                }
                for r in rows
            ],
        }
    )


@router.get("/correlation")
@cached(ttl=600)
async def correlation(
    _user: CurrentUser,
    metric_a: str,
    metric_b: str,
    spatial_unit: str = Query("ortsteil"),
    period_year: int | None = Query(None),
) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    a.spatial_key,
                    a.metric_value  AS value_a,
                    b.metric_value  AS value_b
                FROM mart.statistics_latest a
                JOIN mart.statistics_latest b
                    ON  a.spatial_unit = b.spatial_unit
                    AND a.spatial_key  = b.spatial_key
                    AND (%s::int IS NULL OR a.period_year = %s)
                    AND (%s::int IS NULL OR b.period_year = %s)
                WHERE a.metric_name  = %s
                  AND b.metric_name  = %s
                  AND a.spatial_unit = %s
                  AND a.metric_value IS NOT NULL
                  AND b.metric_value IS NOT NULL
                ORDER BY a.spatial_key
                """,
                (
                    period_year, period_year, period_year, period_year,
                    metric_a, metric_b, spatial_unit,
                ),
            )
            rows = await cur.fetchall()

    if not rows:
        return ORJSONResponse({"metric_a": metric_a, "metric_b": metric_b, "pearson_r": None, "points": []})

    xs = [r["value_a"] for r in rows]
    ys = [r["value_b"] for r in rows]
    pearson_r = _pearson(xs, ys)

    return ORJSONResponse(
        {
            "metric_a": metric_a,
            "metric_b": metric_b,
            "spatial_unit": spatial_unit,
            "pearson_r": pearson_r,
            "points": [
                {"key": r["spatial_key"], "x": r["value_a"], "y": r["value_b"]}
                for r in rows
            ],
        }
    )


@router.get("/choropleth")
@cached(ttl=300)
async def choropleth(
    _user: CurrentUser,
    metric_name: str,
    spatial_unit: str = Query("ortsteil"),
    period_year: int | None = Query(None),
    dataset_id: str | None = Query(None),
) -> ORJSONResponse:
    # Joins on the canonical spatial_code (resolved by ETL); city-level values
    # have no boundary and intentionally never reach the map. Wahlbezirk
    # geometries are versioned per election, hence the boundary_year match.
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT ON (s.spatial_code)
                    s.spatial_key,
                    s.spatial_code,
                    s.metric_value,
                    s.metric_unit,
                    s.period_year,
                    ST_AsGeoJSON(b.geom)::jsonb AS geometry,
                    b.name AS boundary_name
                FROM core.statistics s
                JOIN core.admin_boundaries b
                    ON b.boundary_type = s.spatial_unit
                    AND b.code = s.spatial_code
                    AND (b.boundary_year = 0 OR b.boundary_year = s.period_year)
                WHERE s.metric_name  = %s
                  AND s.spatial_unit = %s
                  AND s.spatial_unit <> 'city'
                  AND s.spatial_code IS NOT NULL
                  AND (%s::int IS NULL OR s.period_year = %s)
                  AND (%s::text IS NULL OR s.dataset_id = %s)
                  AND s.metric_value IS NOT NULL
                ORDER BY s.spatial_code, s.period_year DESC NULLS LAST
                """,
                (
                    metric_name, spatial_unit,
                    period_year, period_year,
                    dataset_id, dataset_id,
                ),
            )
            rows = await cur.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": r["geometry"],
            "properties": {
                "spatial_key": r["spatial_key"],
                "spatial_code": r["spatial_code"],
                "name": r["boundary_name"],
                "metric_name": metric_name,
                "metric_value": r["metric_value"],
                "metric_unit": r["metric_unit"],
                "period_year": r["period_year"],
            },
        }
        for r in rows
        if r["geometry"]
    ]
    return ORJSONResponse({"type": "FeatureCollection", "features": features})


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom_x = sum((x - mx) ** 2 for x in xs) ** 0.5
    denom_y = sum((y - my) ** 2 for y in ys) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return None
    return round(num / (denom_x * denom_y), 4)
