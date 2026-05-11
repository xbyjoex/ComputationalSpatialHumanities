"""Telegram notifications for ETL pipeline events."""

from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send(text: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        r = httpx.post(
            _TELEGRAM_API.format(token=settings.telegram_bot_token),
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        r.raise_for_status()
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)


def notify_nightly_start(count: int) -> None:
    _send(f"🌙 <b>Nightly ETL gestartet</b>\n{count} Datensätze werden verarbeitet...")


def notify_nightly_done(stats: dict) -> None:
    ok = stats.get("success", 0)
    fail = stats.get("failed", 0)
    skip = stats.get("skipped", 0)
    icon = "✅" if fail == 0 else "⚠️"
    _send(
        f"{icon} <b>Nightly ETL abgeschlossen</b>\n"
        f"✓ Erfolg: {ok}\n"
        f"✗ Fehler: {fail}\n"
        f"⊘ Übersprungen: {skip}"
    )


def notify_nightly_error(error: str) -> None:
    _send(f"❌ <b>Nightly ETL — kritischer Fehler</b>\n<code>{error[:500]}</code>")


def notify_mart_refresh_failed(error: str) -> None:
    _send(f"❌ <b>Mart-Refresh fehlgeschlagen</b>\n<code>{error[:500]}</code>")


def notify_live_mart_failed(error: str) -> None:
    _send(f"⚠️ <b>Live Mart-Refresh Fehler</b>\n<code>{error[:300]}</code>")
