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

from .config import settings
from .db import get_conn, run_migrations
from .loaders.postgres import upsert_dataset_registry
from .pipeline import run_dataset

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


def load_contracts() -> tuple[list[dict], list[dict]]:
    """Load dataset contracts and split into nightly / live buckets."""
    path = settings.contracts_path
    with open(path, encoding="utf-8") as f:
        all_contracts = json.load(f)
    nightly = [c for c in all_contracts if c["schedule"] == "nightly"]
    live = [c for c in all_contracts if c["schedule"] == "live"]
    logger.info("Loaded %d nightly, %d live contracts", len(nightly), len(live))
    return nightly, live


def run_nightly(nightly: list[dict]) -> None:
    logger.info("=== NIGHTLY ETL START (%d datasets) ===", len(nightly))
    stats = {"success": 0, "failed": 0, "skipped": 0}
    for contract in nightly:
        if _shutdown:
            logger.warning("Shutdown requested, stopping nightly ETL early")
            break
        status, _, _ = run_dataset(contract)
        stats[status] = stats.get(status, 0) + 1

    # Refresh all mart views after nightly ETL
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT mart.refresh_all()")
                conn.commit()
        logger.info("Mart views refreshed")
    except Exception as exc:
        logger.error("Failed to refresh mart views: %s", exc)

    logger.info("=== NIGHTLY ETL DONE: %s ===", stats)


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


def main() -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running DB migrations...")
    run_migrations()

    nightly, live = load_contracts()

    # Sync dataset registry into DB
    with get_conn() as conn:
        n = upsert_dataset_registry(conn, nightly + live)
        logger.info("Dataset registry synced: %d records", n)

    # Schedule nightly at 02:00 UTC
    schedule.every().day.at("02:00").do(run_nightly, nightly)

    # Schedule live refresh every N seconds
    interval = settings.live_interval
    schedule.every(interval).seconds.do(run_live, live)

    # Run live immediately on startup
    logger.info("Running initial live refresh...")
    run_live(live)

    logger.info(
        "Scheduler ready. Nightly at 02:00 UTC, live every %ds", interval
    )

    while not _shutdown:
        schedule.run_pending()
        time.sleep(5)

    logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
