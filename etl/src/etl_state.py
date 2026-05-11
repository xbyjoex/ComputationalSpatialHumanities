"""Shared in-memory ETL progress state, readable by the Telegram bot."""

from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()

_state: dict = {
    "running": False,
    "kind": None,          # "nightly" | "live"
    "total": 0,
    "done": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "started_at": None,    # time.monotonic()
    "failed_names": [],
}


def start(kind: str, total: int) -> None:
    with _lock:
        _state.update(
            running=True, kind=kind, total=total,
            done=0, success=0, failed=0, skipped=0,
            started_at=time.monotonic(), failed_names=[],
        )


def update(status: str, name: Optional[str] = None) -> None:
    with _lock:
        _state["done"] += 1
        _state[status] = _state.get(status, 0) + 1
        if status == "failed" and name:
            _state["failed_names"].append(name)


def finish() -> None:
    with _lock:
        _state["running"] = False


def snapshot() -> dict:
    with _lock:
        s = dict(_state)
    elapsed = time.monotonic() - s["started_at"] if s["started_at"] else 0
    s["elapsed"] = elapsed
    return s
