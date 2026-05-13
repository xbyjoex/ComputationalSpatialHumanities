from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..auth import CurrentUser
from ..db import get_conn

router = APIRouter(prefix="/datasets", tags=["datasets"])


# Tables that carry a dataset_id column and can be filtered per dataset.
_DATASET_ID_TABLES = {
    "core.geo_features",
    "core.statistics",
    "core.traffic_restrictions",
}

# Whitelist for direct interpolation — request paths never reach SQL strings
# except through this lookup, so SQL injection on the table name is impossible.
_ALLOWED_TARGETS = _DATASET_ID_TABLES | {
    "core.park_ride_occupancy",
    "core.bicycle_counts",
}


async def _resolve_target_table(conn, dataset_id: str) -> str | None:
    """Look up the most recently used target table for a dataset.

    Falls back to a heuristic on core.datasets.has_geo if no change_log exists.
    Returns None if no data has been loaded for this dataset.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT target_table FROM raw_ingest.change_log
            WHERE dataset_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (dataset_id,),
        )
        row = await cur.fetchone()
        if row and row["target_table"] in _ALLOWED_TARGETS:
            return row["target_table"]

        # Fallback: probe the three dataset_id-carrying tables.
        for t in ("core.geo_features", "core.statistics", "core.traffic_restrictions"):
            await cur.execute(
                f"SELECT 1 FROM {t} WHERE dataset_id = %s LIMIT 1", (dataset_id,)
            )
            if await cur.fetchone():
                return t
    return None


@router.get("")
async def list_datasets(
    _user: CurrentUser,
    schedule: str | None = Query(None, description="nightly or live"),
    has_geo: bool | None = Query(None),
    fmt: str | None = Query(None, alias="format", description="best_format filter"),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    conditions = ["TRUE"]
    params: list[Any] = []

    if schedule:
        conditions.append("schedule = %s")
        params.append(schedule)
    if has_geo is not None:
        conditions.append("has_geo = %s")
        params.append(has_geo)
    if fmt:
        conditions.append("best_format = %s")
        params.append(fmt.upper())
    if search:
        conditions.append("(title ILIKE %s OR id ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT COUNT(*) AS total FROM core.datasets WHERE {where}", params
            )
            total = (await cur.fetchone())["total"]

            await cur.execute(
                f"""
                SELECT id, title, schedule, has_geo, formats, best_format,
                       best_url, last_ingested, is_active
                FROM core.datasets
                WHERE {where}
                ORDER BY title
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = await cur.fetchall()

    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@router.get("/status")
async def dataset_status(_user: CurrentUser) -> list[dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM mart.dataset_status ORDER BY title")
            return await cur.fetchall()


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, _user: CurrentUser) -> dict[str, Any]:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM core.datasets WHERE id = %s", (dataset_id,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dataset not found")

            await cur.execute(
                """
                SELECT status, started_at, finished_at, rows_loaded, rows_extracted,
                       duration_ms, error_message
                FROM raw_ingest.etl_runs
                WHERE dataset_id = %s
                ORDER BY started_at DESC
                LIMIT 10
                """,
                (dataset_id,),
            )
            runs = await cur.fetchall()

        target = await _resolve_target_table(conn, dataset_id)
        row_count = 0
        if target:
            async with conn.cursor() as cur:
                if target in _DATASET_ID_TABLES:
                    await cur.execute(
                        f"SELECT COUNT(*) AS n FROM {target} WHERE dataset_id = %s",
                        (dataset_id,),
                    )
                else:
                    await cur.execute(f"SELECT COUNT(*) AS n FROM {target}")
                row_count = (await cur.fetchone())["n"]

    return {
        "dataset": row,
        "target_table": target,
        "row_count": row_count,
        "recent_runs": runs,
    }


@router.get("/{dataset_id}/rows")
async def get_dataset_rows(
    dataset_id: str,
    _user: CurrentUser,
    search: str | None = Query(None, max_length=200),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Paginated raw rows for a dataset, returned as generic JSON objects."""
    async with get_conn() as conn:
        target = await _resolve_target_table(conn, dataset_id)
        if not target:
            return {"target_table": None, "total": 0, "items": [], "columns": []}

        params: list[Any] = []
        where = "TRUE"
        if target in _DATASET_ID_TABLES:
            where = "dataset_id = %s"
            params.append(dataset_id)

        # Column projection per target table (avoids huge geom/JSONB blobs).
        if target == "core.geo_features":
            cols = "id, feature_id, feature_type, name, description, properties, ingested_at, updated_at"
            search_cols = ("name", "description", "feature_id")
        elif target == "core.statistics":
            cols = "id, period_label, period_year, spatial_unit, spatial_key, metric_name, metric_value, metric_unit, ingested_at"
            search_cols = ("metric_name", "spatial_key", "period_label")
        elif target == "core.traffic_restrictions":
            cols = "id, restriction_id, restriction_type, title, description, valid_from, valid_until, properties, ingested_at"
            search_cols = ("title", "description", "restriction_id")
        elif target == "core.park_ride_occupancy":
            cols = "id, site_id, site_name, total_spaces, occupied_spaces, free_spaces, occupancy_pct, measured_at"
            search_cols = ("site_name", "site_id")
        elif target == "core.bicycle_counts":
            cols = "id, counter_id, counter_name, count_period, period_start, count_value"
            search_cols = ("counter_name", "counter_id")
        else:
            raise HTTPException(status_code=400, detail="Unsupported target table")

        if search:
            ors = " OR ".join(f"{c} ILIKE %s" for c in search_cols)
            where += f" AND ({ors})"
            params.extend([f"%{search}%"] * len(search_cols))

        async with conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) AS n FROM {target} WHERE {where}", params)
            total = (await cur.fetchone())["n"]

            await cur.execute(
                f"SELECT {cols} FROM {target} WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            items = await cur.fetchall()

    columns = [c.strip() for c in cols.split(",")]
    return {
        "target_table": target,
        "total": total,
        "limit": limit,
        "offset": offset,
        "columns": columns,
        "items": items,
    }


@router.get("/{dataset_id}/stats")
async def get_dataset_stats(dataset_id: str, _user: CurrentUser) -> dict[str, Any]:
    """Basic statistics over the dataset's rows. Shape depends on target table."""
    async with get_conn() as conn:
        target = await _resolve_target_table(conn, dataset_id)
        if not target:
            return {"target_table": None, "summary": {}}

        async with conn.cursor() as cur:
            if target == "core.statistics":
                await cur.execute(
                    """
                    SELECT metric_name,
                           COUNT(*)            AS n,
                           MIN(metric_value)   AS min,
                           MAX(metric_value)   AS max,
                           AVG(metric_value)   AS avg,
                           MIN(period_year)    AS year_min,
                           MAX(period_year)    AS year_max
                    FROM core.statistics
                    WHERE dataset_id = %s
                    GROUP BY metric_name
                    ORDER BY metric_name
                    LIMIT 50
                    """,
                    (dataset_id,),
                )
                per_metric = await cur.fetchall()
                await cur.execute(
                    "SELECT COUNT(*) AS n, COUNT(DISTINCT spatial_key) AS spatial_units "
                    "FROM core.statistics WHERE dataset_id = %s",
                    (dataset_id,),
                )
                head = await cur.fetchone()
                return {
                    "target_table": target,
                    "summary": head,
                    "per_metric": per_metric,
                }

            if target == "core.geo_features":
                await cur.execute(
                    """
                    SELECT feature_type, COUNT(*) AS n
                    FROM core.geo_features
                    WHERE dataset_id = %s
                    GROUP BY feature_type
                    ORDER BY n DESC LIMIT 20
                    """,
                    (dataset_id,),
                )
                per_type = await cur.fetchall()
                await cur.execute(
                    """
                    SELECT COUNT(*) AS n,
                           MIN(ingested_at) AS first_seen,
                           MAX(updated_at)  AS last_updated
                    FROM core.geo_features
                    WHERE dataset_id = %s
                    """,
                    (dataset_id,),
                )
                head = await cur.fetchone()
                return {"target_table": target, "summary": head, "per_type": per_type}

            if target == "core.traffic_restrictions":
                await cur.execute(
                    """
                    SELECT restriction_type, COUNT(*) AS n
                    FROM core.traffic_restrictions
                    WHERE dataset_id = %s
                    GROUP BY restriction_type
                    ORDER BY n DESC
                    """,
                    (dataset_id,),
                )
                per_type = await cur.fetchall()
                await cur.execute(
                    """
                    SELECT COUNT(*) AS n,
                           COUNT(*) FILTER (WHERE valid_until IS NULL OR valid_until > NOW()) AS active
                    FROM core.traffic_restrictions
                    WHERE dataset_id = %s
                    """,
                    (dataset_id,),
                )
                head = await cur.fetchone()
                return {"target_table": target, "summary": head, "per_type": per_type}

            if target == "core.park_ride_occupancy":
                await cur.execute(
                    """
                    SELECT site_name,
                           COUNT(*)             AS n,
                           AVG(occupancy_pct)   AS avg_occ,
                           MAX(occupancy_pct)   AS max_occ
                    FROM core.park_ride_occupancy
                    GROUP BY site_name ORDER BY n DESC LIMIT 30
                    """
                )
                per_site = await cur.fetchall()
                return {"target_table": target, "per_site": per_site}

            if target == "core.bicycle_counts":
                await cur.execute(
                    """
                    SELECT counter_name,
                           COUNT(*) AS n,
                           SUM(count_value) AS total,
                           AVG(count_value) AS avg
                    FROM core.bicycle_counts
                    GROUP BY counter_name ORDER BY total DESC NULLS LAST LIMIT 30
                    """
                )
                per_counter = await cur.fetchall()
                return {"target_table": target, "per_counter": per_counter}

    return {"target_table": target, "summary": {}}


@router.get("/{dataset_id}/history")
async def get_dataset_history(
    dataset_id: str,
    _user: CurrentUser,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    """ETL change history for a dataset: when did the data change, by how much."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT c.id, c.run_id, c.target_table, c.rows_added,
                       c.rows_updated, c.rows_total_after, c.created_at,
                       r.status, r.started_at, r.duration_ms, r.error_message
                FROM raw_ingest.change_log c
                LEFT JOIN raw_ingest.etl_runs r ON r.id = c.run_id
                WHERE c.dataset_id = %s
                ORDER BY c.created_at DESC
                LIMIT %s
                """,
                (dataset_id, limit),
            )
            history = await cur.fetchall()

            await cur.execute(
                """
                SELECT id, status, started_at, finished_at, rows_loaded,
                       rows_extracted, duration_ms, error_message
                FROM raw_ingest.etl_runs
                WHERE dataset_id = %s
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (dataset_id, limit),
            )
            runs = await cur.fetchall()

    return {"history": history, "runs": runs}
