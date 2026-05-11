"""Telegram notifications for ETL pipeline events."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _api(method: str, payload: dict) -> Optional[dict]:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return None
    try:
        r = httpx.post(
            _BASE.format(token=settings.telegram_bot_token, method=method),
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("Telegram %s failed: %s", method, exc)
        return None


def _send(text: str) -> Optional[int]:
    """Send a message; returns message_id or None."""
    data = _api("sendMessage", {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
    })
    if data and data.get("ok"):
        return data["result"]["message_id"]
    return None


def _edit(message_id: int, text: str) -> None:
    """Edit an existing message in-place."""
    _api("editMessageText", {
        "chat_id": settings.telegram_chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    })


def _progress_bar(done: int, total: int, width: int = 16) -> str:
    filled = int(width * done / total) if total else 0
    return "▓" * filled + "░" * (width - filled)


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


# ── Public API ─────────────────────────────────────────────────────────────────

def notify_nightly_start(count: int) -> Optional[int]:
    """Send start message; returns message_id for later edits."""
    text = (
        f"🌙 <b>Nightly ETL gestartet</b>\n"
        f"{_progress_bar(0, count)} 0/{count} (0%)\n"
        f"✓ 0  ✗ 0  ⊘ 0"
    )
    return _send(text)


def notify_nightly_progress(
    message_id: Optional[int],
    done: int,
    total: int,
    success: int,
    failed: int,
    skipped: int,
    failed_names: list[str],
    elapsed: float,
) -> None:
    """Edit the start message with current progress."""
    if not message_id:
        return
    pct = int(100 * done / total) if total else 0
    bar = _progress_bar(done, total)
    lines = [
        f"🌙 <b>Nightly ETL läuft…</b>",
        f"{bar} {done}/{total} ({pct}%)",
        f"✓ {success}  ✗ {failed}  ⊘ {skipped}  ⏱ {_format_duration(elapsed)}",
    ]
    if failed_names:
        sample = failed_names[-5:]  # last 5 failures
        lines.append("\n<b>Letzte Fehler:</b>")
        for name in sample:
            lines.append(f"  • {name[:60]}")
    _edit(message_id, "\n".join(lines))


def notify_nightly_done(
    message_id: Optional[int],
    stats: dict,
    failed_names: list[str],
    elapsed: float,
) -> None:
    ok = stats.get("success", 0)
    fail = stats.get("failed", 0)
    skip = stats.get("skipped", 0)
    total = ok + fail + skip
    icon = "✅" if fail == 0 else "⚠️"
    bar = _progress_bar(total, total)
    lines = [
        f"{icon} <b>Nightly ETL abgeschlossen</b>",
        f"{bar} {total}/{total} (100%)",
        f"✓ {ok}  ✗ {fail}  ⊘ {skip}  ⏱ {_format_duration(elapsed)}",
    ]
    if failed_names:
        lines.append(f"\n<b>Fehlgeschlagene Datensätze ({len(failed_names)}):</b>")
        for name in failed_names[:20]:
            lines.append(f"  • {name[:60]}")
        if len(failed_names) > 20:
            lines.append(f"  … und {len(failed_names) - 20} weitere")
    text = "\n".join(lines)
    if message_id:
        _edit(message_id, text)
    else:
        _send(text)


def notify_nightly_error(error: str, message_id: Optional[int] = None) -> None:
    text = f"❌ <b>Nightly ETL — kritischer Fehler</b>\n<code>{error[:500]}</code>"
    if message_id:
        _edit(message_id, text)
    else:
        _send(text)


def notify_mart_refresh_failed(error: str) -> None:
    _send(f"❌ <b>Mart-Refresh fehlgeschlagen</b>\n<code>{error[:500]}</code>")


def notify_live_mart_failed(error: str) -> None:
    _send(f"⚠️ <b>Live Mart-Refresh Fehler</b>\n<code>{error[:300]}</code>")
