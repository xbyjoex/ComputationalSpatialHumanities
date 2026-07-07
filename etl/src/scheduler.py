"""
Scheduler: runs nightly full ETL + frequent live-source refresh.

- Nightly: all 398 dataset contracts processed sequentially at 02:00
- Live: 18 live contracts polled every ETL_LIVE_INTERVAL_SECONDS (default 5 min)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

import schedule

from .boundaries import seed_boundaries_safe
from .cache_bump import bump_tiles_version
from .config import settings
from .domains import elections
from .domains.elections import sync_elections
from .db import get_conn, run_migrations
from . import etl_state
from .loaders.postgres import (
    sync_dataset_categories,
    sync_dataset_families,
    sync_indicator_catalog,
    upsert_dataset_registry,
)
from .notifier import (
    notify_mart_refresh_failed,
    notify_nightly_done,
    notify_nightly_error,
    notify_nightly_progress,
    notify_nightly_start,
    notify_live_mart_failed,
)
from .pipeline import run_dataset
from .telegram_bot import TelegramPoller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scheduler")

_shutdown = False


def _handle_signal(sig: int, frame: object) -> None:
    global _shutdown
    logger.info("Received signal %d, shutting down gracefully", sig)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def load_families() -> dict:
    """Load the curated dataset_families.json (empty config if absent)."""
    path = Path(settings.families_path)
    if not path.exists():
        # Local dev fallback: repo root next to dataset_contracts.json
        repo_root_path = Path(__file__).resolve().parents[2] / "dataset_families.json"
        path = repo_root_path if repo_root_path.exists() else path
    if not path.exists():
        logger.warning("No dataset_families.json found — families disabled")
        return {"families": [], "dataset_hints": {}}
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    logger.info(
        "Loaded %d dataset families, %d dataset hints",
        len(config.get("families", [])), len(config.get("dataset_hints", {})),
    )
    return config


def load_categories() -> dict:
    """Load the generated dataset_categories.json (empty config if absent)."""
    path = Path(settings.categories_path)
    if not path.exists():
        repo_root_path = Path(__file__).resolve().parents[2] / "dataset_categories.json"
        path = repo_root_path if repo_root_path.exists() else path
    if not path.exists():
        logger.warning("No dataset_categories.json found — categories disabled")
        return {"categories": [], "memberships": {}}
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    logger.info(
        "Loaded %d categories, %d memberships",
        len(config.get("categories", [])), len(config.get("memberships", {})),
    )
    return config


def load_contracts() -> tuple[list[dict], list[dict], dict]:
    """Load dataset contracts, stamp family metadata, split nightly / live."""
    path = settings.contracts_path
    with open(path, encoding="utf-8") as f:
        all_contracts = json.load(f)

    families = load_families()
    member_map = {
        m["dataset_id"]: (fam["family_id"], m.get("year"))
        for fam in families.get("families", [])
        for m in fam.get("members", [])
    }
    hints = families.get("dataset_hints", {})
    for contract in all_contracts:
        if contract["id"] in member_map:
            contract["family_id"], contract["family_year"] = member_map[contract["id"]]
        if contract["id"] in hints:
            contract["hints"] = hints[contract["id"]]

    nightly = [c for c in all_contracts if c["schedule"] == "nightly"]
    live = [c for c in all_contracts if c["schedule"] == "live"]
    logger.info("Loaded %d nightly, %d live contracts", len(nightly), len(live))
    return nightly, live, families


_PROGRESS_INTERVAL = 50  # edit message every N datasets


def run_nightly(nightly: list[dict]) -> None:
    logger.info("=== NIGHTLY ETL START (%d datasets) ===", len(nightly))
    # Refresh admin boundaries + spatial aliases first so statistics ingested
    # below resolve their spatial_code against current geometries.
    seed_boundaries_safe(nightly)
    total = len(nightly)
    etl_state.start("nightly", total)
    msg_id = notify_nightly_start(total)
    t0 = time.monotonic()

    try:
        for i, contract in enumerate(nightly, 1):
            if _shutdown:
                logger.warning("Shutdown requested, stopping nightly ETL early")
                break
            status, _, _ = run_dataset(contract)
            name = contract.get("title", contract.get("id", "?"))
            etl_state.update(status, name if status == "failed" else None)
            if i % _PROGRESS_INTERVAL == 0:
                s = etl_state.snapshot()
                notify_nightly_progress(
                    msg_id, i, total,
                    s["success"], s["failed"], s["skipped"],
                    s["failed_names"], s["elapsed"],
                )
    except Exception as exc:
        logger.error("Nightly ETL crashed: %s", exc, exc_info=True)
        etl_state.finish()
        notify_nightly_error(str(exc), msg_id)
        return

    # Refresh all mart views after nightly ETL
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT mart.refresh_all()")
                conn.commit()
        logger.info("Mart views refreshed")
        # Geo features changed → invalidate the per-tile Redis cache.
        # Live cycles do not bump: live tables are not in the tile path.
        bump_tiles_version()
    except Exception as exc:
        logger.error("Failed to refresh mart views: %s", exc)
        notify_mart_refresh_failed(str(exc))

    # Retention sweep — keeps live time-series and audit log bounded.
    # raw_ingest.payloads now holds a single summary row per dataset (upsert),
    # so no retention is needed there.
    retention_sql = [
        ("park_ride_occupancy",
         "DELETE FROM core.park_ride_occupancy WHERE measured_at < NOW() - INTERVAL '30 days'"),
        ("bicycle_counts",
         "DELETE FROM core.bicycle_counts WHERE period_start < NOW() - INTERVAL '365 days'"),
        ("etl_runs",
         "DELETE FROM raw_ingest.etl_runs WHERE started_at < NOW() - INTERVAL '90 days'"),
    ]
    for name, sql in retention_sql:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    deleted = cur.rowcount
                    conn.commit()
            logger.info("Retention %s: removed %d rows", name, deleted)
        except Exception as exc:
            logger.warning("Retention %s failed: %s", name, exc)

    etl_state.finish()
    s = etl_state.snapshot()
    stats = {"success": s["success"], "failed": s["failed"], "skipped": s["skipped"]}
    elapsed = time.monotonic() - t0
    logger.info("=== NIGHTLY ETL DONE: %s in %.0fs ===", stats, elapsed)
    notify_nightly_done(msg_id, stats, s["failed_names"], elapsed)


def run_live(live: list[dict]) -> None:
    logger.info("--- Live refresh (%d datasets) ---", len(live))
    for contract in live:
        if _shutdown:
            break
        run_dataset(contract)

    # Refresh only live-relevant mart views
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT mart.refresh_live()")
                conn.commit()
    except Exception as exc:
        logger.error("Live mart refresh failed: %s", exc)
        notify_live_mart_failed(str(exc))


def main() -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running DB migrations...")
    run_migrations()

    nightly, live, families = load_contracts()

    # Sync dataset registry into DB
    with get_conn() as conn:
        n = upsert_dataset_registry(conn, nightly + live)
        logger.info("Dataset registry synced: %d records", n)

    # Family membership + year-dimension backfill
    try:
        with get_conn() as conn:
            members = sync_dataset_families(conn, families)
            logger.info("Dataset families synced: %d member datasets", members)
    except Exception as exc:
        logger.error("Family sync failed: %s", exc)

    # Thematic categories (dataset_categories.json, mirrors CKAN groups)
    try:
        with get_conn() as conn:
            n_cat = sync_dataset_categories(conn, load_categories())
            logger.info("Dataset categories synced: %d memberships", n_cat)
    except Exception as exc:
        logger.error("Category sync failed: %s", exc)

    # Election domain registry + legacy statistics cleanup
    try:
        with get_conn() as conn:
            n_elections = sync_elections(conn, elections.load_definitions())
            logger.info("Elections synced: %d definitions", n_elections)
    except Exception as exc:
        logger.error("Election sync failed: %s", exc)

    # Partei-Register (party_registry.json → core.parties/party_aliases)
    try:
        with get_conn() as conn:
            n_parties = elections.sync_parties(conn, elections.load_party_registry())
            logger.info("Parties synced: %d", n_parties)
    except Exception as exc:
        logger.error("Party sync failed: %s", exc)

    # Spektrum-View einmal beim Start füllen (sonst erst nach dem Nightly)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("REFRESH MATERIALIZED VIEW mart.election_party_shares")
                conn.commit()
    except Exception as exc:
        logger.warning("election_party_shares startup refresh failed: %s", exc)

    # Indicator catalog (canonical metric registry)
    try:
        path = Path(settings.indicators_path)
        if not path.exists():
            repo_root_path = Path(__file__).resolve().parents[2] / "indicator_catalog.json"
            path = repo_root_path if repo_root_path.exists() else path
        if path.exists():
            with open(path, encoding="utf-8") as f:
                catalog = json.load(f)
            with get_conn() as conn:
                n_ind = sync_indicator_catalog(conn, catalog)
                logger.info("Indicator catalog synced: %d indicators", n_ind)
        else:
            logger.warning("No indicator_catalog.json found — catalog disabled")
    except Exception as exc:
        logger.error("Indicator catalog sync failed: %s", exc)

    # Seed admin boundaries once at startup so choropleths work without
    # waiting for the 02:00 nightly run.
    seed_boundaries_safe(nightly + live)

    # Schedule nightly at 02:00 UTC
    schedule.every().day.at("02:00").do(run_nightly, nightly)

    # Schedule live refresh every N seconds
    interval = settings.live_interval
    schedule.every(interval).seconds.do(run_live, live)

    # Run live immediately on startup
    logger.info("Running initial live refresh...")
    run_live(live)

    # Start Telegram bot in background (no-op if not configured)
    poller = TelegramPoller(
        run_nightly=lambda: run_nightly(nightly),
        run_live=lambda: run_live(live),
    )
    poller.start()

    logger.info(
        "Scheduler ready. Nightly at 02:00 UTC, live every %ds", interval
    )

    while not _shutdown:
        schedule.run_pending()
        time.sleep(5)

    poller.stop()
    logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
