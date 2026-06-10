"""Generic per-dataset column profiling for the data explorer.

Computes per-column statistics (numeric: min/max/mean/median/stddev/null
share; categorical: distinct count + top values; temporal: range) and
on-demand histograms. Column identifiers are NEVER taken from the request:
they are validated against _PROFILE_SPECS, or — for core.statistics metric
names and core.geo_features JSONB property keys — passed as bound query
parameters (values, not identifiers).

Heavy work is bounded: 15s statement timeout, property-key detection on a
2000-row sample, at most 30 metrics / 12 property keys per profile. Results
are cached by the endpoints with a data-version key (see routers/datasets.py).
"""

from __future__ import annotations

from typing import Any

_NUM_RE = r"^-?[0-9]+([.,][0-9]+)?$"
HISTOGRAM_BUCKETS = 20
_PROP_SAMPLE = 2000
_MAX_PROP_KEYS = 12
_MAX_NUMERIC_PROPS = 8

# Tables whose rows carry a dataset_id column (mirror of routers/datasets.py;
# duplicated here to avoid a circular import).
_DATASET_ID_TABLES = {
    "core.geo_features",
    "core.statistics",
    "core.traffic_restrictions",
    "core.election_results",
}

# Static column specs for the small domain tables. These names are
# interpolated into SQL — they must stay hardcoded.
_PROFILE_SPECS: dict[str, dict[str, list[str]]] = {
    "core.park_ride_occupancy": {
        "numeric": ["total_spaces", "occupied_spaces", "free_spaces", "occupancy_pct"],
        "categorical": ["site_name"],
        "temporal": ["measured_at"],
    },
    "core.park_ride_latest": {
        "numeric": ["total_spaces", "occupied_spaces", "free_spaces", "occupancy_pct"],
        "categorical": ["site_name"],
        "temporal": ["measured_at"],
    },
    "core.bicycle_counts": {
        "numeric": ["count_value"],
        "categorical": ["counter_name", "count_period"],
        "temporal": ["period_start"],
    },
    "core.traffic_restrictions": {
        "numeric": [],
        "categorical": ["restriction_type", "title"],
        "temporal": ["valid_from", "valid_until"],
    },
    "core.election_results": {
        "numeric": ["erststimmen", "zweitstimmen", "wahlberechtigte", "waehler"],
        "categorical": ["party", "level", "gebiet_name"],
        "temporal": [],
    },
}


def _where(target: str) -> tuple[str, list[Any]]:
    if target in _DATASET_ID_TABLES:
        return "dataset_id = %s", ["__DATASET__"]
    return "TRUE", []


async def _set_timeout(conn) -> None:
    async with conn.cursor() as cur:
        await cur.execute("SET LOCAL statement_timeout = '15s'")


def _num(row: dict[str, Any], name: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    n = row.get("n") or 0
    non_null = row.get("non_null") or 0
    col: dict[str, Any] = {
        "name": name,
        "kind": "numeric",
        "n": n,
        "non_null": non_null,
        "null_share": round(1 - non_null / n, 4) if n else None,
        "min": row.get("min"),
        "max": row.get("max"),
        "mean": row.get("mean"),
        "median": row.get("median"),
        "stddev": row.get("stddev"),
        "histogram_column": name,
    }
    if extra:
        col.update(extra)
    return col


async def build_profile(conn, dataset_id: str, target: str) -> dict[str, Any]:
    await _set_timeout(conn)
    if target == "core.statistics":
        columns = await _profile_statistics(conn, dataset_id)
    elif target == "core.geo_features":
        columns = await _profile_geo_features(conn, dataset_id)
    elif target in _PROFILE_SPECS:
        columns = await _profile_spec_table(conn, dataset_id, target)
    else:
        columns = []

    where, params = _where(target)
    params = [dataset_id if p == "__DATASET__" else p for p in params]
    async with conn.cursor() as cur:
        await cur.execute(f"SELECT COUNT(*) AS n FROM {target} WHERE {where}", params)
        row_count = (await cur.fetchone())["n"]

    return {"target_table": target, "row_count": row_count, "columns": columns}


async def _profile_spec_table(conn, dataset_id: str, target: str) -> list[dict[str, Any]]:
    spec = _PROFILE_SPECS[target]
    where, params = _where(target)
    params = [dataset_id if p == "__DATASET__" else p for p in params]
    columns: list[dict[str, Any]] = []

    async with conn.cursor() as cur:
        for col in spec["numeric"]:
            await cur.execute(
                f"""
                SELECT COUNT(*) AS n, COUNT({col}) AS non_null,
                       MIN({col})::float AS min, MAX({col})::float AS max,
                       AVG({col})::float AS mean, STDDEV_SAMP({col})::float AS stddev,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {col}) AS median
                FROM {target} WHERE {where}
                """,
                params,
            )
            columns.append(_num(await cur.fetchone(), col))

        for col in spec["categorical"]:
            await cur.execute(
                f"""
                SELECT COUNT(DISTINCT {col}) AS distinct_n, COUNT(*) AS n,
                       COUNT({col}) AS non_null
                FROM {target} WHERE {where}
                """,
                params,
            )
            head = await cur.fetchone()
            await cur.execute(
                f"""
                SELECT {col} AS value, COUNT(*) AS n FROM {target}
                WHERE {where} AND {col} IS NOT NULL
                GROUP BY {col} ORDER BY n DESC LIMIT 10
                """,
                params,
            )
            top = await cur.fetchall()
            columns.append(
                {
                    "name": col,
                    "kind": "categorical",
                    "n": head["n"],
                    "non_null": head["non_null"],
                    "distinct": head["distinct_n"],
                    "top": [{"value": t["value"], "n": t["n"]} for t in top],
                }
            )

        for col in spec["temporal"]:
            await cur.execute(
                f"SELECT MIN({col}) AS min, MAX({col}) AS max FROM {target} WHERE {where}",
                params,
            )
            row = await cur.fetchone()
            columns.append(
                {
                    "name": col,
                    "kind": "date",
                    "min": row["min"].isoformat() if row["min"] else None,
                    "max": row["max"].isoformat() if row["max"] else None,
                }
            )
    return columns


async def _profile_statistics(conn, dataset_id: str) -> list[dict[str, Any]]:
    """Long-format statistics pivot on metric_name — each metric is a column."""
    columns: list[dict[str, Any]] = []
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT metric_name,
                   COUNT(*) AS n, COUNT(metric_value) AS non_null,
                   MIN(metric_value) AS min, MAX(metric_value) AS max,
                   AVG(metric_value) AS mean, STDDEV_SAMP(metric_value) AS stddev,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY metric_value) AS median,
                   MIN(period_year) AS year_min, MAX(period_year) AS year_max
            FROM core.statistics
            WHERE dataset_id = %s
            GROUP BY metric_name
            ORDER BY n DESC, metric_name
            LIMIT 30
            """,
            (dataset_id,),
        )
        for row in await cur.fetchall():
            columns.append(
                _num(row, row["metric_name"],
                     {"year_min": row["year_min"], "year_max": row["year_max"]})
            )

        for col in ("spatial_key", "period_label"):
            await cur.execute(
                f"""
                SELECT COUNT(DISTINCT {col}) AS distinct_n, COUNT(*) AS n,
                       COUNT({col}) AS non_null
                FROM core.statistics WHERE dataset_id = %s
                """,
                (dataset_id,),
            )
            head = await cur.fetchone()
            if not head["distinct_n"]:
                continue
            await cur.execute(
                f"""
                SELECT {col} AS value, COUNT(*) AS n FROM core.statistics
                WHERE dataset_id = %s AND {col} IS NOT NULL
                GROUP BY {col} ORDER BY n DESC LIMIT 10
                """,
                (dataset_id,),
            )
            top = await cur.fetchall()
            columns.append(
                {
                    "name": col,
                    "kind": "categorical",
                    "n": head["n"],
                    "non_null": head["non_null"],
                    "distinct": head["distinct_n"],
                    "top": [{"value": t["value"], "n": t["n"]} for t in top],
                }
            )
    return columns


async def _profile_geo_features(conn, dataset_id: str) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT GeometryType(geom) AS value, COUNT(*) AS n
            FROM core.geo_features WHERE dataset_id = %s
            GROUP BY 1 ORDER BY n DESC
            """,
            (dataset_id,),
        )
        geom_types = await cur.fetchall()
        columns.append(
            {
                "name": "Geometrie",
                "kind": "categorical",
                "n": sum(g["n"] for g in geom_types),
                "non_null": sum(g["n"] for g in geom_types),
                "distinct": len(geom_types),
                "top": [{"value": g["value"], "n": g["n"]} for g in geom_types],
            }
        )

        await cur.execute(
            "SELECT MIN(year) AS min, MAX(year) AS max FROM core.geo_features WHERE dataset_id = %s",
            (dataset_id,),
        )
        years = await cur.fetchone()
        if years["min"] is not None:
            columns.append(
                {"name": "Jahr", "kind": "date", "min": years["min"], "max": years["max"]}
            )

        # Property keys from a bounded sample (4 GB VPS guard)
        await cur.execute(
            """
            SELECT key, COUNT(*) AS n FROM (
                SELECT jsonb_object_keys(properties) AS key
                FROM (
                    SELECT properties FROM core.geo_features
                    WHERE dataset_id = %s AND properties IS NOT NULL
                    LIMIT %s
                ) sample
            ) keys
            GROUP BY key ORDER BY n DESC LIMIT %s
            """,
            (dataset_id, _PROP_SAMPLE, _MAX_PROP_KEYS),
        )
        keys = [r["key"] for r in await cur.fetchall()]

        numeric_done = 0
        for key in keys:
            await cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE properties->>%s ~ %s) AS numeric_n,
                       COUNT(properties->>%s) AS non_null
                FROM (
                    SELECT properties FROM core.geo_features
                    WHERE dataset_id = %s AND properties IS NOT NULL
                    LIMIT %s
                ) sample
                """,
                (key, _NUM_RE, key, dataset_id, _PROP_SAMPLE),
            )
            probe = await cur.fetchone()
            is_numeric = (
                probe["non_null"] > 0
                and probe["numeric_n"] / probe["non_null"] >= 0.8
                and numeric_done < _MAX_NUMERIC_PROPS
            )

            if is_numeric:
                numeric_done += 1
                await cur.execute(
                    """
                    SELECT COUNT(*) AS n, COUNT(v) AS non_null,
                           MIN(v) AS min, MAX(v) AS max, AVG(v) AS mean,
                           STDDEV_SAMP(v) AS stddev,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) AS median
                    FROM (
                        SELECT CASE WHEN properties->>%s ~ %s
                                    THEN replace(properties->>%s, ',', '.')::float
                               END AS v
                        FROM core.geo_features WHERE dataset_id = %s
                    ) vals
                    """,
                    (key, _NUM_RE, key, dataset_id),
                )
                col = _num(await cur.fetchone(), key)
                col["histogram_column"] = f"prop:{key}"
                columns.append(col)
            else:
                await cur.execute(
                    """
                    SELECT properties->>%s AS value, COUNT(*) AS n
                    FROM core.geo_features
                    WHERE dataset_id = %s AND properties->>%s IS NOT NULL
                    GROUP BY 1 ORDER BY n DESC LIMIT 10
                    """,
                    (key, dataset_id, key),
                )
                top = await cur.fetchall()
                await cur.execute(
                    """
                    SELECT COUNT(DISTINCT properties->>%s) AS distinct_n,
                           COUNT(*) AS n, COUNT(properties->>%s) AS non_null
                    FROM core.geo_features WHERE dataset_id = %s
                    """,
                    (key, key, dataset_id),
                )
                head = await cur.fetchone()
                columns.append(
                    {
                        "name": key,
                        "kind": "categorical",
                        "n": head["n"],
                        "non_null": head["non_null"],
                        "distinct": head["distinct_n"],
                        "top": [{"value": t["value"], "n": t["n"]} for t in top],
                    }
                )
    return columns


async def build_histogram(
    conn, dataset_id: str, target: str, column: str
) -> dict[str, Any] | None:
    """≤20-bucket histogram for one numeric column. Returns None if the
    column is not histogrammable for this target."""
    await _set_timeout(conn)

    if target == "core.statistics":
        value_sql = "metric_value"
        from_sql = "core.statistics"
        where_sql = "dataset_id = %s AND metric_name = %s"
        params: list[Any] = [dataset_id, column]
    elif target == "core.geo_features" and column.startswith("prop:"):
        key = column[5:]
        value_sql = "v"
        from_sql = (
            "(SELECT CASE WHEN properties->>%s ~ %s "
            "THEN replace(properties->>%s, ',', '.')::float END AS v "
            "FROM core.geo_features WHERE dataset_id = %s) vals"
        )
        where_sql = "TRUE"
        params = [key, _NUM_RE, key, dataset_id]
    elif target in _PROFILE_SPECS and column in _PROFILE_SPECS[target]["numeric"]:
        value_sql = column
        from_sql = target
        if target in _DATASET_ID_TABLES:
            where_sql = "dataset_id = %s"
            params = [dataset_id]
        else:
            where_sql = "TRUE"
            params = []
    else:
        return None

    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT MIN({value_sql})::float AS lo, MAX({value_sql})::float AS hi,
                   COUNT({value_sql}) AS non_null
            FROM {from_sql} WHERE {where_sql}
            """,
            params,
        )
        bounds = await cur.fetchone()
        lo, hi = bounds["lo"], bounds["hi"]
        if lo is None or bounds["non_null"] == 0:
            return {"column": column, "lo": None, "hi": None, "buckets": []}
        if lo == hi:
            return {
                "column": column, "lo": lo, "hi": hi,
                "buckets": [{"lo": lo, "hi": hi, "n": bounds["non_null"]}],
            }

        # Placeholder order in the SQL: width_bucket args first, then the
        # from_sql/where_sql placeholders in their original order.
        await cur.execute(
            f"""
            SELECT width_bucket({value_sql}, %s, %s, %s) AS bucket, COUNT(*) AS n
            FROM {from_sql}
            WHERE {where_sql} AND {value_sql} IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """,
            [lo, hi, HISTOGRAM_BUCKETS, *params],
        )
        rows = await cur.fetchall()

    counts = [0] * HISTOGRAM_BUCKETS
    for row in rows:
        # width_bucket returns buckets+1 for v == hi — fold into the last one
        idx = min(max(int(row["bucket"]), 1), HISTOGRAM_BUCKETS) - 1
        counts[idx] += row["n"]
    step = (hi - lo) / HISTOGRAM_BUCKETS
    buckets = [
        {"lo": lo + i * step, "hi": lo + (i + 1) * step, "n": counts[i]}
        for i in range(HISTOGRAM_BUCKETS)
    ]
    return {"column": column, "lo": lo, "hi": hi, "buckets": buckets}
