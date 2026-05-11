"""
Core ETL pipeline: handles one dataset contract end-to-end.
Dispatches to the right extractor/loader based on format and dataset type.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from .config import settings
from .db import get_conn
from .extractors.base import HttpExtractor
from .extractors.csv_extractor import CsvExtractor
from .extractors.geojson_extractor import GeoJsonExtractor
from .extractors.json_extractor import StatistikApiExtractor
from .loaders.postgres import (
    log_etl_finish,
    log_etl_start,
    store_raw_payload,
    upsert_bicycle_counts,
    upsert_geo_features,
    upsert_park_ride,
    upsert_statistics,
    upsert_traffic_restrictions,
)

logger = logging.getLogger(__name__)

# Dataset IDs that have specialised handlers
PARK_RIDE_IDS = {
    "aktuelle-belegung-park-ride",
    "historische-belegung-park-ride",
}
BICYCLE_HOURLY_IDS = {"dauerzaehlstellen-radverkehr-stunden"}
BICYCLE_DAILY_IDS = {"dauerzaehlstellen-radverkehr-tage"}
TRAFFIC_RESTRICTION_IDS = {
    "verkehrsraumeinschraenkungen-polygone",
    "verkehrsraumeinschraenkungen-punkte",
}

# Datasets served from statistik.leipzig.de JSON API
STATISTIK_API_URL = "statistik.leipzig.de/opendata/api"

# Formats we intentionally skip — binary/complex formats with no handler
SKIP_FORMATS = {"GTFS", "ZIP", "PDF", "XLS", "XLSX", "ODS", "SHP", "GPKG"}


def run_dataset(contract: dict[str, Any]) -> tuple[str, int, int]:
    """
    Run ETL for a single dataset contract.

    Returns (status, rows_extracted, rows_loaded).
    """
    dataset_id = contract["id"]
    title = contract["title"]
    schedule = contract["schedule"]
    best = contract.get("best_resource") or {}
    url = best.get("url", "")
    fmt = best.get("format", "")

    if not url:
        logger.info("Skipping %s — no resource URL", title)
        return "skipped", 0, 0

    if fmt in SKIP_FORMATS:
        logger.info("Skipping %s — unsupported format %s", title, fmt)
        return "skipped", 0, 0

    with get_conn() as conn:
        run_id = log_etl_start(conn, dataset_id, title, schedule)

    try:
        rows_extracted, rows_loaded = _dispatch(contract, url, fmt)
        with get_conn() as conn:
            log_etl_finish(
                conn,
                run_id,
                status="success",
                rows_extracted=rows_extracted,
                rows_loaded=rows_loaded,
            )
        logger.info("[OK] %-60s rows=%d", title[:60], rows_loaded)
        return "success", rows_extracted, rows_loaded

    except Exception as exc:
        logger.error("[FAIL] %s: %s", title, exc, exc_info=True)
        with get_conn() as conn:
            log_etl_finish(
                conn,
                run_id,
                status="failed",
                error_message=str(exc)[:1000],
            )
        return "failed", 0, 0


def _dispatch(
    contract: dict[str, Any], url: str, fmt: str
) -> tuple[int, int]:
    """Route to specialised handler or generic fallback."""
    dataset_id = contract["id"]
    name = contract.get("name", "")

    # ── Park+Ride live occupancy ─────────────────────────────────────────────
    if any(kw in name.lower() for kw in ("park-ride", "pr_anlage")):
        if fmt in ("GeoJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_park_ride(conn, feats)
            return len(feats), loaded

    # ── Bicycle counters ─────────────────────────────────────────────────────
    if "dauerzaehlstell" in name.lower() or "radverkehr" in name.lower():
        period = "hour" if "stunde" in name.lower() else "day"
        if fmt == "GeoJSON":
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            records = [f.get("properties", {}) for f in feats]
        else:
            with CsvExtractor() as ext:
                records = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_bicycle_counts(conn, records, count_period=period)
        return len(records), loaded

    # ── Traffic restrictions ─────────────────────────────────────────────────
    if "verkehrsraum" in name.lower() or "baustell" in name.lower():
        rtype = "polygon" if "polygon" in name.lower() else "point"
        if fmt in ("GeoJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_traffic_restrictions(conn, dataset_id, feats, restriction_type=rtype)
            return len(feats), loaded

    # ── Generic GeoJSON / WFS ────────────────────────────────────────────────
    if fmt in ("GeoJSON", "WFS") or (fmt == "GPKG" and "geojson" in url.lower()):
        with GeoJsonExtractor() as ext:
            feats = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded

    # ── Statistics JSON API ──────────────────────────────────────────────────
    if fmt == "JSON" and STATISTIK_API_URL in url:
        with StatistikApiExtractor() as ext:
            records = ext.extract_values(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, records)
        return len(records), loaded

    # ── CSV fallback ─────────────────────────────────────────────────────────
    if fmt == "CSV":
        with CsvExtractor() as ext:
            records = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, records)
        return len(records), loaded

    # ── Unhandled: store raw payload for manual review ───────────────────────
    logger.info("No handler for %s (fmt=%s), storing raw", contract["title"], fmt)
    with HttpExtractor() as ext:
        try:
            payload = ext.get_json(url)
            with get_conn() as conn:
                store_raw_payload(conn, dataset_id, url, fmt, payload)
            return 1, 0
        except Exception:
            raw = ext.get_text(url)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO raw_ingest.payloads (dataset_id, resource_url, format, raw_text) "
                        "VALUES (%s, %s, %s, %s)",
                        (dataset_id, url, fmt, raw[:100_000]),
                    )
                    conn.commit()
            return 1, 0
