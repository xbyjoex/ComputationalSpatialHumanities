"""Telegram sender for the registration-approval flow.

The backend only SENDS the approval request (message with inline keyboard)
to the same admin chat the ETL notifier uses. The button presses (callback
queries) are handled by the ETL service's long-polling bot
(etl/src/telegram_bot.py), which approves/rejects the pending row in
auth.pending_registrations and creates the user on approval.
"""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_BERLIN = ZoneInfo("Europe/Berlin")


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def build_registration_message(
    reg_id: str,
    email: str,
    full_name: str | None,
    requested_at: datetime,
    expires_at: datetime,
) -> dict:
    """Build the sendMessage payload (text + inline approve/reject keyboard)."""
    text = "\n".join(
        [
            "🔐 <b>Neue Registrierungsanfrage</b>",
            f"E-Mail: <code>{escape(email)}</code>",
            f"Name: {escape(full_name) if full_name else '—'}",
            f"Zeit: {requested_at.astimezone(_BERLIN):%d.%m.%Y %H:%M:%S}",
            f"⏳ Freigabe bis {expires_at.astimezone(_BERLIN):%H:%M:%S} möglich (5 Minuten).",
        ]
    )
    return {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✅ Freigeben", "callback_data": f"reg:approve:{reg_id}"},
                    {"text": "🚫 Ablehnen", "callback_data": f"reg:reject:{reg_id}"},
                ]
            ]
        },
    }


async def send_registration_request(
    reg_id: str,
    email: str,
    full_name: str | None,
    requested_at: datetime,
    expires_at: datetime,
) -> bool:
    """Announce the registration attempt in the admin chat; True on success."""
    if not is_configured():
        return False
    payload = build_registration_message(reg_id, email, full_name, requested_at, expires_at)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                _API_BASE.format(token=settings.telegram_bot_token, method="sendMessage"),
                json=payload,
            )
            r.raise_for_status()
            return bool(r.json().get("ok"))
    except Exception as exc:
        logger.warning("Telegram registration request failed: %s", exc)
        return False
