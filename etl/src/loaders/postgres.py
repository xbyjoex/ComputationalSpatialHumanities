"""PostgreSQL loaders for all target tables."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def upsert_dataset_registry(
    conn: psycopg.Connection, contracts: list[dict[str, Any]]
) -> int:
    """Sync the dataset_contracts.json into core.datasets."""
    with conn.cursor() as cur:
        count = 0
        for c in contracts:
            best = c.get("best_resource") or {}
            cur.execute(
                """
                INSERT INTO core.datasets
                    (id, name, title, schedule, has_geo, formats, best_url, best_format, resource_count, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title          = EXCLUDED.title,
                    schedule       = EXCLUDED.schedule,
                    has_geo        = EXCLUDED.has_geo,
                    formats        = EXCLUDED.formats,
                    best_url       = EXCLUDED.best_url,
                    best_format    = EXCLUDED.best_format,
                    resource_count = EXCLUDED.resource_count,
                    metadata       = EXCLUDED.metadata
                """,
                (
                    c["id"],
                    c["name"],
                    c["title"],
                    c["schedule"],
                    c["has_geo"],
                    c.get("formats", []),
                    best.get("url"),
                    best.get("format"),
                    c.get("resource_count", 0),
                    json.dumps(c),
                ),
            )
            count += 1
        conn.commit()
    return count


def log_etl_start(
    conn: psycopg.Connection, dataset_id: str, title: str, schedule: str
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_ingest.etl_runs (dataset_id, dataset_title, schedule, status)
            VALUES (%s, %s, %s, 'started')
            RETURNING id
            """,
            (dataset_id, title, schedule),
        )
        run_id: int = cur.fetchone()["id"]
        conn.commit()
    return run_id


def log_etl_finish(
    conn: psycopg.Connection,
    run_id: int,
    *,
    status: str,
    rows_extracted: int = 0,
    rows_loaded: int = 0,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE raw_ingest.etl_runs SET
                status         = %s,
                rows_extracted = %s,
                rows_loaded    = %s,
                error_message  = %s,
                finished_at    = NOW()
            WHERE id = %s
            """,
            (status, rows_extracted, rows_loaded, error_message, run_id),
        )
        cur.execute(
            "UPDATE core.datasets SET last_ingested = NOW() WHERE id = "
            "(SELECT dataset_id FROM raw_ingest.etl_runs WHERE id = %s)",
            (run_id,),
        )
        conn.commit()


def store_raw_payload(
    conn: psycopg.Connection,
    dataset_id: str,
    resource_url: str,
    fmt: str,
    payload: Any,
) -> None:
    """
    Record a small summary of the most recent ETL pull per dataset.

    Stores ONLY a summary dict ({"count": N, ...}) — never full records.
    If the caller passes a list, it is collapsed to {"count": len(list)} to
    prevent the disk blow-up that occurred when full payloads were persisted
    per run (see migration 005).

    Behaviour: one row per dataset_id (upsert), latest wins.
    """
    if isinstance(payload, list):
        summary: dict[str, Any] = {"count": len(payload)}
    elif isinstance(payload, dict):
        # Strip any large nested lists down to length markers.
        summary = {
            k: (f"<list len={len(v)}>" if isinstance(v, list) else v)
            for k, v in payload.items()
        }
    else:
        summary = {"value": str(payload)[:200]}

    summary_str = json.dumps(summary, ensure_ascii=False, default=str)
    checksum = hashlib.sha256(summary_str.encode()).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_ingest.payloads
                (dataset_id, resource_url, format, payload, checksum, ingested_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
            ON CONFLICT (dataset_id) DO UPDATE SET
                resource_url = EXCLUDED.resource_url,
                format       = EXCLUDED.format,
                payload      = EXCLUDED.payload,
                checksum     = EXCLUDED.checksum,
                ingested_at  = NOW()
            """,
            (dataset_id, resource_url, fmt, summary_str, checksum),
        )
        conn.commit()


def upsert_geo_features(
    conn: psycopg.Connection,
    dataset_id: str,
    features: list[dict[str, Any]],
    feature_type: str = "",
) -> int:
    loaded = 0
    with conn.cursor() as cur:
        for feat in features:
            props = feat.get("properties") or {}
            geom_dict = feat.get("geometry")
            if not geom_dict:
                continue

            geom_wkt = None
            try:
                from shapely.geometry import shape

                geom_obj = shape(geom_dict)
                geom_wkt = geom_obj.wkt
            except Exception:
                pass

            if not geom_wkt:
                continue

            feature_id = str(
                props.get("id") or props.get("ID") or props.get("objectid") or ""
            )
            name = str(props.get("name") or props.get("Name") or props.get("bezeichnung") or "")
            desc = str(props.get("description") or props.get("beschreibung") or "")
            props_json = json.dumps(props)

            # dedup_key is computed in SQL so it matches the backfill in
            # migration 006 exactly (same hash inputs / ordering).
            cur.execute(
                """
                INSERT INTO core.geo_features
                    (dataset_id, feature_id, feature_type, name, description,
                     geom, properties, dedup_key)
                VALUES (
                    %s, %s, %s, %s, %s,
                    ST_Force2D(ST_GeomFromText(%s, 4326)),
                    %s::jsonb,
                    COALESCE(
                        NULLIF(%s, ''),
                        MD5(%s::jsonb::text || ST_AsEWKT(ST_Force2D(ST_GeomFromText(%s, 4326))))
                    )
                )
                ON CONFLICT (dataset_id, dedup_key) DO UPDATE SET
                    feature_id   = EXCLUDED.feature_id,
                    feature_type = EXCLUDED.feature_type,
                    name         = EXCLUDED.name,
                    description  = EXCLUDED.description,
                    geom         = EXCLUDED.geom,
                    properties   = EXCLUDED.properties,
                    updated_at   = NOW()
                """,
                (
                    dataset_id,
                    feature_id or None,
                    feature_type,
                    name or None,
                    desc or None,
                    geom_wkt,
                    props_json,
                    feature_id,
                    props_json,
                    geom_wkt,
                ),
            )
            loaded += 1
        conn.commit()
    return loaded


def upsert_statistics(
    conn: psycopg.Connection,
    dataset_id: str,
    records: list[dict[str, Any]],
    spatial_unit: str = "city",
) -> int:
    """
    Generic statistics loader. Tries to detect period and value columns
    from the record structure.
    """
    _SKIP_KEYS = {
        "Jahr", "year", "Periode", "periode", "period",
        "Ortsteil", "ortsteil", "Stadtbezirk", "stadtbezirk", "Gebiet",
    }
    _BATCH = 500

    rows: list[tuple] = []
    for rec in records:
        year = None
        period_label = ""
        period_type = "year"
        su = spatial_unit

        for k in ("Jahr", "year", "Periode", "periode", "period"):
            if k in rec:
                try:
                    year = int(str(rec[k])[:4])
                    period_label = str(rec[k])
                except (ValueError, TypeError):
                    pass
                break

        spatial_key = "Leipzig"
        for k in ("Ortsteil", "ortsteil", "Stadtbezirk", "stadtbezirk", "Gebiet"):
            if k in rec and rec[k]:
                spatial_key = str(rec[k])
                su = "ortsteil" if "ortsteil" in k.lower() else ("stadtbezirk" if "stadtbezirk" in k.lower() else su)
                break

        for metric_name, raw_val in rec.items():
            if metric_name in _SKIP_KEYS:
                continue
            try:
                metric_value = float(str(raw_val).replace(",", "."))
            except (ValueError, TypeError):
                metric_value = None
            rows.append((
                dataset_id, period_type, period_label, year, None, None,
                su, spatial_key, metric_name, metric_value,
            ))

    loaded = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), _BATCH):
            batch = rows[i : i + _BATCH]
            cur.executemany(
                """
                INSERT INTO core.statistics
                    (dataset_id, period_type, period_label, period_year, period_quarter,
                     period_month, spatial_unit, spatial_key, metric_name, metric_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id, period_label, spatial_unit, spatial_key, metric_name)
                DO UPDATE SET
                    period_type    = EXCLUDED.period_type,
                    period_year    = EXCLUDED.period_year,
                    period_quarter = EXCLUDED.period_quarter,
                    period_month   = EXCLUDED.period_month,
                    metric_value   = EXCLUDED.metric_value,
                    ingested_at    = NOW()
                """,
                batch,
            )
            loaded += len(batch)
        conn.commit()
    return loaded


def upsert_park_ride(
    conn: psycopg.Connection, features: list[dict[str, Any]]
) -> int:
    loaded = 0
    with conn.cursor() as cur:
        for feat in features:
            props = feat.get("properties") or {}
            geom_dict = feat.get("geometry")
            geom_wkt = None
            if geom_dict:
                try:
                    from shapely.geometry import shape
                    geom_wkt = shape(geom_dict).wkt
                except Exception:
                    pass

            try:
                cur.execute(
                    """
                    INSERT INTO core.park_ride_occupancy
                        (site_id, site_name, total_spaces, occupied_spaces, free_spaces, geom, measured_at)
                    VALUES (%s, %s, %s, %s, %s,
                            CASE WHEN %s IS NOT NULL THEN ST_GeomFromText(%s, 4326) ELSE NULL END,
                            COALESCE(%s::timestamptz, NOW()))
                    """,
                    (
                        str(props.get("id") or props.get("ID") or ""),
                        str(props.get("name") or props.get("Name") or ""),
                        _safe_int(props.get("gesamt") or props.get("total")),
                        _safe_int(props.get("belegt") or props.get("occupied")),
                        _safe_int(props.get("frei") or props.get("free")),
                        geom_wkt,
                        geom_wkt,
                        props.get("timestamp") or props.get("measured_at"),
                    ),
                )
                loaded += 1
            except Exception as exc:
                logger.debug("park_ride upsert error: %s", exc)
        conn.commit()
    return loaded


def upsert_bicycle_counts(
    conn: psycopg.Connection,
    records: list[dict[str, Any]],
    count_period: str = "day",
) -> int:
    loaded = 0
    with conn.cursor() as cur:
        for rec in records:
            try:
                counter_id = str(
                    rec.get("zaehlstellen_id")
                    or rec.get("counter_id")
                    or rec.get("ID")
                    or ""
                )
                counter_name = str(rec.get("name") or rec.get("Name") or "")
                period_start = rec.get("datum") or rec.get("date") or rec.get("timestamp")
                count_value = _safe_int(
                    rec.get("gesamt") or rec.get("total") or rec.get("count")
                )

                geom_wkt = None
                lat = _safe_float(rec.get("lat") or rec.get("latitude"))
                lon = _safe_float(rec.get("lon") or rec.get("longitude"))
                if lat and lon:
                    geom_wkt = f"POINT({lon} {lat})"

                cur.execute(
                    """
                    INSERT INTO core.bicycle_counts
                        (counter_id, counter_name, geom, count_period, period_start, count_value)
                    VALUES (%s, %s,
                            CASE WHEN %s IS NOT NULL THEN ST_GeomFromText(%s, 4326) ELSE NULL END,
                            %s, %s::timestamptz, %s)
                    ON CONFLICT (counter_id, count_period, period_start) DO UPDATE
                        SET count_value = EXCLUDED.count_value
                    """,
                    (
                        counter_id,
                        counter_name or None,
                        geom_wkt,
                        geom_wkt,
                        count_period,
                        period_start,
                        count_value,
                    ),
                )
                loaded += 1
            except Exception as exc:
                logger.debug("bicycle_count upsert error: %s", exc)
        conn.commit()
    return loaded


def upsert_traffic_restrictions(
    conn: psycopg.Connection,
    dataset_id: str,
    features: list[dict[str, Any]],
    restriction_type: str = "",
) -> int:
    loaded = 0
    with conn.cursor() as cur:
        for feat in features:
            props = feat.get("properties") or {}
            geom_dict = feat.get("geometry")
            if not geom_dict:
                continue

            geom_wkt = None
            try:
                from shapely.geometry import shape
                geom_wkt = shape(geom_dict).wkt
            except Exception:
                pass

            if not geom_wkt:
                continue

            restriction_id = str(props.get("id") or props.get("ID") or "")
            props_json = json.dumps(props)
            cur.execute(
                """
                INSERT INTO core.traffic_restrictions
                    (restriction_id, dataset_id, restriction_type, title, description,
                     geom, valid_from, valid_until, properties, dedup_key)
                VALUES (
                    %s, %s, %s, %s, %s,
                    ST_GeomFromText(%s, 4326),
                    %s, %s, %s::jsonb,
                    COALESCE(
                        NULLIF(%s, ''),
                        MD5(%s::jsonb::text || ST_AsEWKT(ST_GeomFromText(%s, 4326)))
                    )
                )
                ON CONFLICT (dataset_id, dedup_key) DO UPDATE SET
                    restriction_id   = EXCLUDED.restriction_id,
                    restriction_type = EXCLUDED.restriction_type,
                    title            = EXCLUDED.title,
                    description      = EXCLUDED.description,
                    geom             = EXCLUDED.geom,
                    valid_from       = EXCLUDED.valid_from,
                    valid_until      = EXCLUDED.valid_until,
                    properties       = EXCLUDED.properties,
                    updated_at       = NOW()
                """,
                (
                    restriction_id,
                    dataset_id,
                    restriction_type,
                    str(props.get("title") or props.get("bezeichnung") or ""),
                    str(props.get("description") or props.get("beschreibung") or ""),
                    geom_wkt,
                    props.get("beginn") or props.get("valid_from"),
                    props.get("ende") or props.get("valid_until"),
                    props_json,
                    restriction_id,
                    props_json,
                    geom_wkt,
                ),
            )
            loaded += 1
        conn.commit()
    return loaded


# ── Change log ─────────────────────────────────────────────────────────────

# Map dataset traits → target table for change tracking.
# park_ride_occupancy and bicycle_counts don't carry dataset_id, so the count
# applies to the whole table; for the others we filter by dataset_id.
_DATASET_ID_TABLES = {
    "core.geo_features",
    "core.statistics",
    "core.traffic_restrictions",
}


def count_dataset_rows(
    conn: psycopg.Connection, dataset_id: str, target_table: str
) -> int:
    if target_table in _DATASET_ID_TABLES:
        sql = f"SELECT COUNT(*) AS n FROM {target_table} WHERE dataset_id = %s"
        params: tuple = (dataset_id,)
    else:
        sql = f"SELECT COUNT(*) AS n FROM {target_table}"
        params = ()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row["n"]) if row else 0


def record_change_log(
    conn: psycopg.Connection,
    dataset_id: str,
    run_id: int | None,
    target_table: str,
    rows_loaded: int,
    rows_total_after: int,
) -> None:
    """
    Best-effort accounting: rows_added is derived from total-row delta vs.
    the previous change_log entry for this dataset+table. rows_updated is
    rows_loaded minus rows_added (clamped to 0). Suppresses no-op entries
    where nothing changed since the previous run.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rows_total_after
            FROM raw_ingest.change_log
            WHERE dataset_id = %s AND target_table = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (dataset_id, target_table),
        )
        prev_row = cur.fetchone()
        prev_total = int(prev_row["rows_total_after"]) if prev_row and prev_row["rows_total_after"] is not None else 0

        rows_added = max(0, rows_total_after - prev_total)
        rows_updated = max(0, rows_loaded - rows_added)

        # Skip no-op entries (nothing changed AND no rows touched this run)
        if rows_added == 0 and rows_updated == 0 and rows_loaded == 0 and prev_row is not None:
            return

        cur.execute(
            """
            INSERT INTO raw_ingest.change_log
                (dataset_id, run_id, target_table, rows_added, rows_updated, rows_total_after)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (dataset_id, run_id, target_table, rows_added, rows_updated, rows_total_after),
        )
        conn.commit()


def get_dataset_checksum(conn: psycopg.Connection, dataset_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT etag, last_modified, content_hash FROM raw_ingest.dataset_checksums WHERE dataset_id = %s",
            (dataset_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_dataset_checksum(
    conn: psycopg.Connection,
    dataset_id: str,
    url: str,
    etag: str | None,
    last_modified: str | None,
    content_hash: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_ingest.dataset_checksums
                (dataset_id, url, etag, last_modified, content_hash, checked_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (dataset_id) DO UPDATE SET
                url           = EXCLUDED.url,
                etag          = EXCLUDED.etag,
                last_modified = EXCLUDED.last_modified,
                content_hash  = EXCLUDED.content_hash,
                checked_at    = NOW()
            """,
            (dataset_id, url, etag, last_modified, content_hash),
        )
        conn.commit()


def _safe_int(val: Any) -> int | None:
    try:
        return int(float(str(val).replace(",", "."))) if val is not None else None
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(str(val).replace(",", ".")) if val is not None else None
    except (ValueError, TypeError):
        return None
