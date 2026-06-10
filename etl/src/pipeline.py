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
    count_dataset_rows,
    get_dataset_checksum,
    log_etl_finish,
    log_etl_start,
    record_change_log,
    store_raw_payload,
    upsert_bicycle_counts,
    upsert_dataset_checksum,
    upsert_geo_features,
    upsert_park_ride_history,
    upsert_park_ride_latest,
    upsert_statistics,
    upsert_traffic_restrictions,
)

logger = logging.getLogger(__name__)

# Datasets served from statistik.leipzig.de JSON API
STATISTIK_API_URL = "statistik.leipzig.de/opendata/api"

# Formats we intentionally skip — no viable extraction path
SKIP_FORMATS = {"PDF", "XLS"}


def _log_skip(dataset_id: str, title: str, schedule: str, reason: str) -> None:
    """Skips als Lauf protokollieren, damit der Datensatz-Status nicht auf
    einem alten Fehlschlag stehen bleibt (z. B. nach einmaliger Quellen-Störung)."""
    try:
        with get_conn() as conn:
            run_id = log_etl_start(conn, dataset_id, title, schedule)
        with get_conn() as conn:
            log_etl_finish(conn, run_id, status="skipped", error_message=reason)
    except Exception as exc:
        logger.warning("Could not log skip for %s: %s", title, exc)


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
        _log_skip(dataset_id, title, schedule, "no resource URL")
        return "skipped", 0, 0

    if fmt in SKIP_FORMATS:
        logger.info("Skipping %s — unsupported format %s", title, fmt)
        _log_skip(dataset_id, title, schedule, f"unsupported format {fmt}")
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
            _log_skip(dataset_id, title, schedule, "unchanged (304)")
            return "skipped", 0, 0

        # ETag present and unchanged → skip without downloading body
        if new_etag and new_etag == stored_etag:
            logger.info("[SKIP] %-60s unchanged (etag)", title[:60])
            with get_conn() as conn:
                upsert_dataset_checksum(conn, dataset_id, url, new_etag, new_lm, None)
            _log_skip(dataset_id, title, schedule, "unchanged (etag)")
            return "skipped", 0, 0
    except Exception as exc:
        logger.debug("Change-detection HEAD failed for %s: %s — proceeding", title, exc)

    # ── Normal ETL ───────────────────────────────────────────────────────────
    with get_conn() as conn:
        run_id = log_etl_start(conn, dataset_id, title, schedule)

    try:
        rows_extracted, rows_loaded, target_table = _dispatch(contract, url, fmt)
        # Data-quality guard: the generic fallback stores only a raw summary
        # (0 core rows). Surface that in the run log instead of failing silently.
        dq_note = None
        if rows_extracted > 0 and rows_loaded == 0 and not target_table:
            dq_note = "DQ: raw-only ingest (no core rows)"
            logger.warning(
                "[DQ] %-60s extracted %d rows but loaded none to core tables (fmt=%s)",
                title[:60], rows_extracted, fmt,
            )
        with get_conn() as conn:
            log_etl_finish(
                conn,
                run_id,
                status="success",
                rows_extracted=rows_extracted,
                rows_loaded=rows_loaded,
                error_message=dq_note,
            )
        with get_conn() as conn:
            upsert_dataset_checksum(conn, dataset_id, url, new_etag, new_lm, None)
        if target_table:
            try:
                with get_conn() as conn:
                    total_after = count_dataset_rows(conn, dataset_id, target_table)
                    record_change_log(
                        conn, dataset_id, run_id, target_table, rows_loaded, total_after
                    )
            except Exception as exc:
                logger.warning("change_log write failed for %s: %s", dataset_id, exc)
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
) -> tuple[int, int, str]:
    """Route to specialised handler or generic fallback.

    Returns (rows_extracted, rows_loaded, target_table). target_table is the
    fully-qualified core table that received the rows (used by change_log);
    empty string when no rows were written to a tracked core table.
    """
    dataset_id = contract["id"]
    name = contract.get("name", "")
    title = contract.get("title", "")

    # ── Park+Ride: three distinct WFS endpoints, distinguished by URL ────────
    # - lastrecord       → live snapshot, one row per site (overwritten)
    # - zeitreihe        → 30-day history, idempotent on (site_id, measured_at)
    # - standort_statisch→ static locations, no occupancy → generic geo path
    if "pr_anlage_belegung_lastrecord" in url:
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_park_ride_latest(conn, feats)
            return len(feats), loaded, "core.park_ride_latest"

    if "pr_anlage_belegung_zeitreihe" in url:
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_park_ride_history(conn, feats)
            return len(feats), loaded, "core.park_ride_occupancy"

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
        return len(records), loaded, "core.bicycle_counts"

    # ── Traffic restrictions ─────────────────────────────────────────────────
    if "verkehrsraum" in name.lower() or "baustell" in name.lower():
        rtype = "polygon" if "polygon" in name.lower() else "point"
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_traffic_restrictions(conn, dataset_id, feats, restriction_type=rtype)
            return len(feats), loaded, "core.traffic_restrictions"

    # ── GTFS (transit feed) ──────────────────────────────────────────────────
    if fmt == "GTFS":
        with GtfsExtractor() as ext:
            stops = ext.extract_stops(url)
            routes = ext.extract_routes(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, stops, feature_type="gtfs_stop")
            store_raw_payload(conn, dataset_id, url, fmt, {"stops": len(stops), "routes": len(routes)})
        return len(stops) + len(routes), loaded, "core.geo_features"

    # ── SHP / Shapefile ──────────────────────────────────────────────────────
    if fmt in ("SHP", "GPKG"):
        with ShapefileExtractor() as ext:
            feats = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded, "core.geo_features"

    # ── ZIP archive (GeoJSON / CSV inside) ───────────────────────────────────
    if fmt == "ZIP":
        with ZipExtractor() as ext:
            detected_fmt, content = ext.extract(url)
        if detected_fmt == "GeoJSON":
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, content, feature_type=name[:64])
                store_raw_payload(conn, dataset_id, url, fmt, {"count": len(content)})
            return len(content), loaded, "core.geo_features"
        if detected_fmt == "CSV":
            with get_conn() as conn:
                loaded = upsert_statistics(conn, dataset_id, content)
                store_raw_payload(conn, dataset_id, url, fmt, {"count": len(content)})
            return len(content), loaded, "core.statistics"
        if detected_fmt == "SHP":
            # Re-extract via ShapefileExtractor (it handles the ZIP itself)
            with ShapefileExtractor() as ext:
                feats = ext.extract(url)
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            return len(feats), loaded, "core.geo_features"
        logger.info("ZIP from %s: unrecognised content, storing raw", url)
        with get_conn() as conn:
            store_raw_payload(conn, dataset_id, url, fmt, {"detected": detected_fmt})
        return 0, 0, ""

    # ── Excel / ODS ──────────────────────────────────────────────────────────
    if fmt in ("XLSX", "ODS"):
        with ExcelExtractor() as ext:
            records = ext.extract(url, fmt=fmt)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── XML ──────────────────────────────────────────────────────────────────
    if fmt == "XML":
        with XmlExtractor() as ext:
            records = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── Generic GeoJSON / WFS ────────────────────────────────────────────────
    if fmt in ("GEOJSON", "WFS") or (fmt == "GPKG" and "geojson" in url.lower()):
        with GeoJsonExtractor() as ext:
            feats = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64])
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded, "core.geo_features"

    # ── Statistics JSON API ──────────────────────────────────────────────────
    if fmt == "JSON" and STATISTIK_API_URL in url:
        with StatistikApiExtractor() as ext:
            records = ext.extract_values(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── CSV fallback ─────────────────────────────────────────────────────────
    if fmt == "CSV":
        with CsvExtractor() as ext:
            records = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── Unhandled: record a summary so dashboards can see the run ────────────
    logger.info("No handler for %s (fmt=%s), recording summary only", title, fmt)
    with HttpExtractor() as ext:
        try:
            payload = ext.get_json(url)
            size = len(payload) if isinstance(payload, (list, dict)) else 1
            with get_conn() as conn:
                store_raw_payload(conn, dataset_id, url, fmt, {"count": size, "type": "json"})
            return 1, 0, ""
        except Exception:
            raw = ext.get_text(url)
            with get_conn() as conn:
                store_raw_payload(
                    conn, dataset_id, url, fmt,
                    {"count": 1, "type": "text", "bytes": len(raw)},
                )
            return 1, 0, ""
