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
from .domains import elections
from .extractors import statistik_transform
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

    # Elections-Datensätze: 304/ETag-Skip nur, wenn die Zieltabelle für diesen
    # Datensatz auch Zeilen hat. Sonst bleibt core.election_results nach einem
    # Checksum-Eintrag aus der Vor-Elections-Ära für immer leer (Skip-Schleife).
    force_reload = False
    if elections.route_for(dataset_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM core.election_results WHERE dataset_id = %s) AS has_rows",
                    (dataset_id,),
                )
                force_reload = not cur.fetchone()["has_rows"]
        if force_reload:
            logger.info("[FORCE] %-60s election target empty — bypassing 304 skip", title[:60])

    stored_etag = stored.get("etag") if stored else None
    stored_lm = stored.get("last_modified") if stored else None
    new_etag = None
    new_lm = None

    try:
        with HttpExtractor() as ext:
            probe = ext.fetch_with_headers(url, etag=stored_etag, last_modified=stored_lm)

        new_etag = probe.headers.get("etag")
        new_lm = probe.headers.get("last-modified")

        if probe.status_code == 304 and not force_reload:
            logger.info("[SKIP] %-60s unchanged (304)", title[:60])
            _log_skip(dataset_id, title, schedule, "unchanged (304)")
            return "skipped", 0, 0

        # ETag present and unchanged → skip without downloading body
        if new_etag and new_etag == stored_etag and not force_reload:
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


def _contract_year(contract: dict[str, Any]) -> int | None:
    """Data vintage for year-variant family members (dataset_families.json)."""
    hints = contract.get("hints") or {}
    return hints.get("year") or contract.get("family_year")


def _stat_kwargs(contract: dict[str, Any]) -> dict[str, Any]:
    """Loader overrides from dataset_families.json hints."""
    hints = contract.get("hints") or {}
    kwargs: dict[str, Any] = {}
    if hints.get("spatial_unit"):
        kwargs["spatial_unit"] = hints["spatial_unit"]
    if hints.get("spatial_key_column"):
        kwargs["spatial_key_column"] = hints["spatial_key_column"]
    if hints.get("skip_columns"):
        kwargs["skip_columns"] = hints["skip_columns"]
    year = _contract_year(contract)
    if year:
        kwargs["default_year"] = year
    return kwargs


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
    year = _contract_year(contract)
    stat_kwargs = _stat_kwargs(contract)

    # ── Semantic domains first: curated configs beat format heuristics ──────
    election_route = elections.route_for(dataset_id)
    if election_route:
        return elections.run_election_dataset(contract, url, *election_route)

    # ── Park+Ride: live occupancy + history → unified geo layer ──────────────
    # The MVT map reads core.geo_features, so both Park+Ride feeds land there
    # (the old core.park_ride_* tables are retired). Distinguished by URL:
    # - lastrecord → live snapshot; dedup_key = site id ⇒ one row/site, the
    #   `ON CONFLICT … DO UPDATE` overwrites occupancy every 5 min.
    # - zeitreihe  → 30-day history; objectid per record ⇒ time-in-geo points
    #   (occupancy over time via properties.phenomenontime).
    if "pr_anlage_belegung_lastrecord" in url and fmt in ("GEOJSON", "WFS"):
        with GeoJsonExtractor() as ext:
            feats = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type="park_ride")
        return len(feats), loaded, "core.geo_features"

    if "pr_anlage_belegung_zeitreihe" in url and fmt in ("GEOJSON", "WFS"):
        with GeoJsonExtractor() as ext:
            feats = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type="park_ride_history")
        return len(feats), loaded, "core.geo_features"

    # ── Radverkehr Dauerzählstellen → unified geo layer ──────────────────────
    # Source CRS is EPSG:25833 (UTM33) — GeoJsonExtractor reprojects to WGS84.
    # Standorte = counter points; *anzahl/gesamt = per-station counts over time
    # (time-in-geo via properties.phenomenontime + count).
    if "dauerzaehlstell" in name.lower() or "radverkehr" in name.lower():
        is_count = any(k in name.lower() for k in ("anzahl", "gesamt")) or "zeitreihe" in url.lower()
        ftype = "bicycle_count" if is_count else "bicycle_station"
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=ftype)
            return len(feats), loaded, "core.geo_features"
        # Legacy CSV fallback (no current source uses it)
        with CsvExtractor() as ext:
            records = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_bicycle_counts(conn, records, count_period="day")
        return len(records), loaded, "core.bicycle_counts"

    # ── Traffic restrictions ─────────────────────────────────────────────────
    if "verkehrsraum" in name.lower() or "baustell" in name.lower():
        rtype = "polygon" if "polygon" in name.lower() else "point"
        if fmt in ("GEOJSON", "WFS"):
            with GeoJsonExtractor() as ext:
                feats = ext.extract_all(url)
            with get_conn() as conn:
                # Full-snapshot WFS (current restrictions only) — sweep rows
                # this run didn't touch so per-request volatile ids / the
                # daily fme_tstamp don't duplicate the table forever.
                loaded = upsert_traffic_restrictions(
                    conn, dataset_id, feats, restriction_type=rtype, sweep_stale=True
                )
            return len(feats), loaded, "core.traffic_restrictions"

    # ── GTFS (transit feed) ──────────────────────────────────────────────────
    if fmt == "GTFS":
        with GtfsExtractor() as ext:
            stops = ext.extract_stops(url)
            routes = ext.extract_routes(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, stops, feature_type="gtfs_stop", year=year)
            store_raw_payload(conn, dataset_id, url, fmt, {"stops": len(stops), "routes": len(routes)})
        return len(stops) + len(routes), loaded, "core.geo_features"

    # ── SHP / Shapefile ──────────────────────────────────────────────────────
    if fmt in ("SHP", "GPKG"):
        with ShapefileExtractor() as ext:
            feats = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64], year=year)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded, "core.geo_features"

    # ── ZIP archive (GeoJSON / CSV inside) ───────────────────────────────────
    if fmt == "ZIP":
        with ZipExtractor() as ext:
            detected_fmt, content = ext.extract(url)
        if detected_fmt == "GeoJSON":
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, content, feature_type=name[:64], year=year)
                store_raw_payload(conn, dataset_id, url, fmt, {"count": len(content)})
            return len(content), loaded, "core.geo_features"
        if detected_fmt == "CSV":
            with get_conn() as conn:
                loaded = upsert_statistics(conn, dataset_id, content, **stat_kwargs)
                store_raw_payload(conn, dataset_id, url, fmt, {"count": len(content)})
            return len(content), loaded, "core.statistics"
        if detected_fmt == "SHP":
            # Re-extract via ShapefileExtractor (it handles the ZIP itself)
            with ShapefileExtractor() as ext:
                feats = ext.extract(url)
            with get_conn() as conn:
                loaded = upsert_geo_features(conn, dataset_id, feats, feature_type=name[:64], year=year)
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
            loaded = upsert_statistics(conn, dataset_id, records, **stat_kwargs)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── XML ──────────────────────────────────────────────────────────────────
    if fmt == "XML":
        with XmlExtractor() as ext:
            records = ext.extract(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records, **stat_kwargs)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(records), loaded, "core.statistics"

    # ── Generic GeoJSON / WFS ────────────────────────────────────────────────
    # Full-snapshot semantics: every run should mirror the source exactly, so
    # sweep_stale removes rows this run didn't touch. Needed because some WFS
    # sources (e.g. Baumkataster) hand out new volatile feature ids per
    # request, which defeats the ON CONFLICT dedup and previously caused
    # unbounded duplicate growth (7M dupes / 12 GB in core.geo_features).
    if fmt in ("GEOJSON", "WFS") or (fmt == "GPKG" and "geojson" in url.lower()):
        with GeoJsonExtractor() as ext:
            feats = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_geo_features(
                conn, dataset_id, feats, feature_type=name[:64], year=year, sweep_stale=True,
            )
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(feats)})
        return len(feats), loaded, "core.geo_features"

    # ── statistik.leipzig.de API (wide-by-year → melt to long) ──────────────
    if STATISTIK_API_URL in url and fmt in ("CSV", "JSON"):
        units: dict[str, str] = {}
        if fmt == "JSON":
            with StatistikApiExtractor() as ext:
                raw_rows = ext.extract_values(url)
            if "kdvalues" in url:
                records = statistik_transform.melt_kdvalues(raw_rows)
            else:
                records, units = statistik_transform.melt_json_values(raw_rows)
        else:
            with CsvExtractor() as ext:
                raw_rows = ext.extract_all(url)
            if "kdvalues" in url:
                records = statistik_transform.melt_kdvalues(raw_rows)
            else:
                records, units = statistik_transform.melt_values(raw_rows)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records, units=units, **stat_kwargs)
            store_raw_payload(conn, dataset_id, url, fmt, {"count": len(records)})
        return len(raw_rows), loaded, "core.statistics"

    # ── CSV fallback ─────────────────────────────────────────────────────────
    if fmt == "CSV":
        with CsvExtractor() as ext:
            records = ext.extract_all(url)
        with get_conn() as conn:
            loaded = upsert_statistics(conn, dataset_id, records, **stat_kwargs)
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
