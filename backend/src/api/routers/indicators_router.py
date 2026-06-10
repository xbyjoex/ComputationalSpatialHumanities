"""Canonical indicator catalog over the statistik.leipzig.de metrics."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from ..auth import CurrentUser
from ..cache import cached
from ..db import get_conn

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("/topics")
@cached(ttl=600)
async def list_topics(_user: CurrentUser) -> ORJSONResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT topic, COUNT(*) AS indicator_count
                FROM core.indicators
                WHERE topic IS NOT NULL
                GROUP BY topic ORDER BY indicator_count DESC
                """
            )
            rows = await cur.fetchall()
    return ORJSONResponse(rows)


@router.get("")
@cached(ttl=600)
async def list_indicators(
    _user: CurrentUser,
    topic: str | None = Query(None, max_length=100),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> ORJSONResponse:
    """Catalog with availability (spatial units / latest year from the mart)."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT i.indicator_id, i.name, i.unit, i.topic,
                       COUNT(DISTINCT im.dataset_id) AS source_count,
                       ARRAY_AGG(DISTINCT s.spatial_unit)
                           FILTER (WHERE s.spatial_unit IS NOT NULL) AS spatial_units,
                       MAX(s.period_year) AS latest_year
                FROM core.indicators i
                LEFT JOIN core.indicator_metrics im USING (indicator_id)
                LEFT JOIN mart.statistics_latest s
                    ON s.dataset_id = im.dataset_id AND s.metric_name = im.metric_name
                WHERE (%s::text IS NULL OR i.topic = %s)
                  AND (%s::text IS NULL OR i.name ILIKE %s)
                GROUP BY i.indicator_id
                ORDER BY i.name
                LIMIT %s OFFSET %s
                """,
                (topic, topic, search, f"%{search}%" if search else None, limit, offset),
            )
            rows = await cur.fetchall()
    return ORJSONResponse(rows)


@router.get("/{indicator_id}/timeseries")
@cached(ttl=600)
async def indicator_timeseries(
    indicator_id: str,
    _user: CurrentUser,
    spatial_unit: str | None = Query(None),
    spatial_code: str | None = Query(None, max_length=50),
) -> ORJSONResponse:
    """Union of all metric variants behind one canonical indicator."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM core.indicators WHERE indicator_id = %s",
                (indicator_id,),
            )
            indicator = await cur.fetchone()
            if not indicator:
                raise HTTPException(status_code=404, detail="Indikator nicht gefunden")

            await cur.execute(
                """
                SELECT s.period_label, s.period_year, s.spatial_unit,
                       s.spatial_key, s.spatial_code, s.metric_value,
                       COALESCE(s.metric_unit, %s) AS unit
                FROM core.statistics s
                JOIN core.indicator_metrics im
                    ON im.dataset_id = s.dataset_id AND im.metric_name = s.metric_name
                WHERE im.indicator_id = %s
                  AND (%s::text IS NULL OR s.spatial_unit = %s)
                  AND (%s::text IS NULL OR s.spatial_code = %s)
                  AND s.metric_value IS NOT NULL
                ORDER BY s.period_year NULLS LAST, s.period_label
                """,
                (
                    indicator["unit"], indicator_id,
                    spatial_unit, spatial_unit,
                    spatial_code, spatial_code,
                ),
            )
            rows = await cur.fetchall()
    return ORJSONResponse({"indicator": indicator, "series": rows})
