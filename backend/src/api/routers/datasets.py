from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..auth import CurrentUser
from ..db import get_conn

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_datasets(
    _user: CurrentUser,
    schedule: str | None = Query(None, description="nightly or live"),
    has_geo: bool | None = Query(None),
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
    if search:
        conditions.append("title ILIKE %s")
        params.append(f"%{search}%")

    where = " AND ".join(conditions)

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT COUNT(*) AS total FROM core.datasets WHERE {where}", params
            )
            total = (await cur.fetchone())["total"]

            await cur.execute(
                f"""
                SELECT id, title, schedule, has_geo, formats, best_format, last_ingested, is_active
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
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Dataset not found")

            await cur.execute(
                """
                SELECT status, started_at, finished_at, rows_loaded, error_message
                FROM raw_ingest.etl_runs
                WHERE dataset_id = %s
                ORDER BY started_at DESC
                LIMIT 10
                """,
                (dataset_id,),
            )
            runs = await cur.fetchall()

    return {"dataset": row, "recent_runs": runs}
