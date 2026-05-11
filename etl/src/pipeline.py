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
from .extractors.excel_extractor import ExcelExtractor
from .extractors.geojson_extractor import GeoJsonExtractor
from .extractors.gtfs_extractor import GtfsExtractor
from .extractors.json_extractor import StatistikApiExtractor
from .extractors.shapefile_extractor import ShapefileExtractor
from .extractors.xml_extractor import XmlExtractor
from .extractors.zip_extractor import ZipExtractor
from .loaders.postgres import (
    get_dataset_checksum,
    log_etl_finish,
    log_etl_start,
    store_raw_payload,
    upsert_bicycle_counts,
    upsert_dataset_checksum,
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

# Formats we intentionally skip — no viable extraction path
SKIP_FORMATS = {"PDF", "XLS"}


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
    fmt = (best.get("format", "") or "").upper()

    if not url:
        logger.info("Skipping %s — no resource URL", title)
        return "skipped", 0, 0

    if fmt in SKIP_FORMATS:
        logger.info("Skipping %s — unsupported format %s", title, fmt)
        return "skipped", 0, 0

    # ── Change detection via HEAD (no body download) ─────────────────────────
    with get_conn() as conn:
        stored = get_dataset_checksum(conn, dataset_id)

    stored_etag = stored.get("etag") if stored else None
    stored_lm = stored.get("last_modified") if stored else None
    new_etag = None
    new_lm = None

    try:
        with HttpExtractor() as ext:
            probe = ext.fetch_with_headers(url, etag=stored_etag, last_modified=stored_lm)

        new_etag = probe.headers.get("etag")
        new_lm = probe.headers.get("last-modified")

        if probe.status_code == 304:
            logger.info("[SKIP] %-60s unchanged (304)", title[:60])
            return "skipped", 0, 0

        # ETag present and unchanged → skip without downloading body
        if new_etag and new_etag == stored_etag:
            logger.info("[SKIP] %-60s unchanged (etag)", title[:60])
            with get_conn() as conn:
                upsert_dataset_checksum(conn, dataset_id, url, new_etag, new_lm, None)
            return "skipped", 0, 0
    except Exception as exc:
        logger.debug("Change-detection HEAD failed for %s: %s — proceeding", title, exc)

    # ── Normal ETL ───────────────────────────────────────────────────────────
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
        with get_conn() as conn:
            upsert_dataset_checksum(conn, dataset_id, url, new_etag, new_lm, None)
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
    title = contract.get("title", "")

    # ── Park+Ride live occupancy ─────────────────────────────────────────────
    if any(kw in name.lower() for kw in ("park-ride", "pr_anlage")):
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_park_ride(conn, feats)
            return len(feats), loaded

    # ── Bicycle counters ─────────────────────────────────────────────────────
    if "dauerzaehlstell" in name.lower() or "radverkehr" in name.lower():
        period = "hour" if "stunde" in name.lower() else "day"
        if fmt == "GEOJSON":
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
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_traffic_restrictions(conn, dataset_id, feats, restriction_type=rtype)
            return len(feats), loaded

    # ── GTFS (transit feed) ──────────────────────────────────────────────────
    if fmt == "GTFS":
        with GtfsExtractor() as ext:
            stops = ext.extract_stops(url)
            routes = ext.extract_routes(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, stops, feature_type="gtfs_stop")
            store_raw_payload(conn, dataset_id, url, fmt, {"stops": len(stops), "routes": len(routes)})
        return len(stops) + len(routes), loaded

    # ── SHP / Shapefile ──────────────────────────────────────────────────────
    if fmt in ("SHP", "GPKG"):
        with ShapefileExtractor() as ext:
            feats = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded

    # ── ZIP archive (GeoJSON / CSV inside) ───────────────────────────────────
    if fmt == "ZIP":
        with ZipExtractor() as ext:
            detected_fmt, content = ext.extract(url)
        if detected_fmt == "GeoJSON":
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, content, feature_type=name[:64])
                store_raw_payload(conn, dataset_id, url, fmt, {"count": len(content)})
            return len(content), loaded
        if detected_fmt == "CSV":
            with get_conn() as conn:
                loaded = upsert_statistics(conn, dataset_id, content)
                store_raw_payload(conn, dataset_id, url, fmt, content)
            return len(content), loaded
        if detected_fmt == "SHP":
            # Re-extract via ShapefileExtractor (it handles the ZIP itself)
            with ShapefileExtractor() as ext:
                feats = ext.extract(url)
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            return len(feats), loaded
        logger.info("ZIP from %s: unrecognised content, storing raw", url)
        with get_conn() as conn:
            store_raw_payload(conn, dataset_id, url, fmt, {"detected": detected_fmt})
        return 0, 0

    # ── Excel / ODS ──────────────────────────────────────────────────────────
    if fmt in ("XLSX", "ODS"):
        with ExcelExtractor() as ext:
            records = ext.extract(url, fmt=fmt)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, records)
        return len(records), loaded

    # ── XML ──────────────────────────────────────────────────────────────────
    if fmt == "XML":
        with XmlExtractor() as ext:
            records = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, records)
        return len(records), loaded

    # ── Generic GeoJSON / WFS ────────────────────────────────────────────────
    if fmt in ("GEOJSON", "WFS") or (fmt == "GPKG" and "geojson" in url.lower()):
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
    logger.info("No handler for %s (fmt=%s), storing raw", title, fmt)
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
