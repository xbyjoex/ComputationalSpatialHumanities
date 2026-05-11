"""Telegram bot: long-poll for commands to manually trigger ETL runs."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_etl_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="etl-cmd")

_HELP_TEXT = (
    "📋 <b>Verfügbare Befehle:</b>\n\n"
    "▶️ <code>etl-start</code> — Nightly ETL manuell starten (alle Datensätze)\n"
    "🔄 <code>etl-live</code>  — Live-Refresh manuell starten\n"
    "📊 <code>status</code>    — Aktuellen Scheduler-Status abfragen\n"
    "❓ <code>help</code>       — Diese Hilfe anzeigen"
)


def _call(method: str, **kwargs) -> dict:
    r = httpx.post(
        _API_BASE.format(token=settings.telegram_bot_token, method=method),
        json=kwargs,
        timeout=35,
    )
    r.raise_for_status()
    return r.json()


def _reply(text: str) -> None:
    try:
        _call("sendMessage", chat_id=settings.telegram_chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Telegram reply failed: %s", exc)


def _is_authorized(message: dict) -> bool:
    """Only accept messages from the configured chat ID."""
    return str(message.get("chat", {}).get("id", "")) == str(settings.telegram_chat_id)


def _run_safe(label: str, fn: Callable) -> None:
    if not _etl_lock.acquire(blocking=False):
        _reply("⏳ Ein ETL-Lauf ist bereits aktiv — bitte warten.")
        return
    try:
        fn()
    except Exception as exc:
        logger.error("ETL command '%s' crashed: %s", label, exc, exc_info=True)
    finally:
        _etl_lock.release()


def _handle(message: dict, run_nightly: Callable, run_live: Callable) -> None:
    if not _is_authorized(message):
        logger.warning(
            "Unauthorized Telegram message from chat_id=%s",
            message.get("chat", {}).get("id"),
        )
        return

    raw = message.get("text", "").strip()
    cmd = raw.lower().lstrip("/").replace("-", "").replace(" ", "")

    if cmd == "etlstart":
        _reply("▶️ <b>Nightly ETL wird gestartet...</b>\nDas dauert mehrere Minuten.")
        _executor.submit(_run_safe, "nightly", run_nightly)

    elif cmd == "etllive":
        _reply("🔄 <b>Live-Refresh wird gestartet...</b>")
        _executor.submit(_run_safe, "live", run_live)

    elif cmd == "status":
        state = "🔄 ETL-Lauf läuft gerade" if _etl_lock.locked() else "✅ Idle — kein aktiver Lauf"
        _reply(f"📊 <b>Scheduler-Status</b>\n{state}")

    elif cmd in ("help", "hilfe", "start"):
        _reply(_HELP_TEXT)

    else:
        _reply(
            f"❓ Unbekannter Befehl: <code>{raw}</code>\n\n"
            "Schreibe <code>help</code> für eine Übersicht."
        )


class TelegramPoller(threading.Thread):
    """Background daemon thread that long-polls Telegram for incoming commands."""

    def __init__(self, run_nightly: Callable, run_live: Callable) -> None:
        super().__init__(daemon=True, name="telegram-poller")
        self._run_nightly = run_nightly
        self._run_live = run_live
        self._offset = 0
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            logger.info("Telegram not configured — bot polling disabled")
            return

        logger.info("Telegram bot polling started (chat_id=%s)", settings.telegram_chat_id)
        while not self._stop_event.is_set():
            try:
                data = _call(
                    "getUpdates",
                    offset=self._offset,
                    timeout=30,
                    allowed_updates=["message"],
                )
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        _handle(msg, self._run_nightly, self._run_live)
            except httpx.ReadTimeout:
                pass  # long-poll expired normally, just retry
            except Exception as exc:
                logger.warning("Telegram polling error: %s", exc)
                self._stop_event.wait(timeout=15)
