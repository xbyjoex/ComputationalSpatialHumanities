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
    payload_str = json.dumps(payload, ensure_ascii=False, default=str)
    checksum = hashlib.sha256(payload_str.encode()).hexdigest()

    with conn.cursor() as cur:
        # Skip if identical payload was stored recently
        cur.execute(
            "SELECT 1 FROM raw_ingest.payloads WHERE dataset_id=%s AND checksum=%s "
            "AND ingested_at > NOW() - INTERVAL '25 hours' LIMIT 1",
            (dataset_id, checksum),
        )
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO raw_ingest.payloads (dataset_id, resource_url, format, payload, checksum)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (dataset_id, resource_url, fmt, json.dumps(payload), checksum),
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
                from shapely import wkt

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

            cur.execute(
                """
                INSERT INTO core.geo_features
                    (dataset_id, feature_id, feature_type, name, description, geom, properties)
                VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    dataset_id,
                    feature_id or None,
                    feature_type,
                    name or None,
                    desc or None,
                    geom_wkt,
                    json.dumps(props),
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
    loaded = 0
    with conn.cursor() as cur:
        for rec in records:
            # Detect period
            year = None
            quarter = None
            month = None
            period_label = None
            period_type = "year"

            for k in ("Jahr", "year", "Periode", "periode", "period"):
                if k in rec:
                    try:
                        year = int(str(rec[k])[:4])
                        period_label = str(rec[k])
                    except (ValueError, TypeError):
                        pass
                    break

            # Detect spatial key
            spatial_key = "Leipzig"
            for k in ("Ortsteil", "ortsteil", "Stadtbezirk", "stadtbezirk", "Gebiet"):
                if k in rec and rec[k]:
                    spatial_key = str(rec[k])
                    if "ortsteil" in k.lower():
                        spatial_unit = "ortsteil"
                    elif "stadtbezirk" in k.lower():
                        spatial_unit = "stadtbezirk"
                    break

            # Each remaining numeric column is a metric
            skip_keys = {
                "Jahr", "year", "Periode", "periode", "period",
                "Ortsteil", "ortsteil", "Stadtbezirk", "stadtbezirk", "Gebiet",
            }
            for metric_name, raw_val in rec.items():
                if metric_name in skip_keys:
                    continue
                try:
                    metric_value = float(str(raw_val).replace(",", "."))
                except (ValueError, TypeError):
                    metric_value = None

                cur.execute(
                    """
                    INSERT INTO core.statistics
                        (dataset_id, period_type, period_label, period_year, period_quarter,
                         period_month, spatial_unit, spatial_key, metric_name, metric_value, raw_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        dataset_id,
                        period_type,
                        period_label,
                        year,
                        quarter,
                        month,
                        spatial_unit,
                        spatial_key,
                        metric_name,
                        metric_value,
                        json.dumps(rec),
                    ),
                )
                loaded += 1
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

            cur.execute(
                """
                INSERT INTO core.traffic_restrictions
                    (restriction_id, dataset_id, restriction_type, title, description,
                     geom, valid_from, valid_until, properties)
                VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(props.get("id") or props.get("ID") or ""),
                    dataset_id,
                    restriction_type,
                    str(props.get("title") or props.get("bezeichnung") or ""),
                    str(props.get("description") or props.get("beschreibung") or ""),
                    geom_wkt,
                    props.get("beginn") or props.get("valid_from"),
                    props.get("ende") or props.get("valid_until"),
                    json.dumps(props),
                ),
            )
            loaded += 1
        conn.commit()
    return loaded


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
