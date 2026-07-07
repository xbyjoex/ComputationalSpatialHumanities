from datetime import datetime, timedelta, timezone

from src.api import telegram_approval


REG_ID = "3f0e8b9a-1234-4cde-9f00-abcdef012345"


def _build(email="max@example.org", full_name="Max"):
    requested = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    return telegram_approval.build_registration_message(
        REG_ID, email, full_name, requested, requested + timedelta(minutes=5)
    )


def test_inline_keyboard_carries_approve_and_reject_callbacks():
    payload = _build()
    buttons = payload["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == [
        f"reg:approve:{REG_ID}",
        f"reg:reject:{REG_ID}",
    ]
    # Telegram caps callback_data at 64 bytes
    assert all(len(b["callback_data"].encode()) <= 64 for b in buttons)


def test_message_contains_email_timestamp_and_deadline():
    payload = _build()
    assert "max@example.org" in payload["text"]
    assert "07.07.2026" in payload["text"]
    assert "5 Minuten" in payload["text"]
    assert payload["parse_mode"] == "HTML"


def test_message_escapes_html_in_user_input():
    payload = _build(email="a&b@x.de", full_name="<script>")
    assert "a&amp;b@x.de" in payload["text"]
    assert "&lt;script&gt;" in payload["text"]


def test_is_configured_false_without_env(monkeypatch):
    from src.api.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    assert telegram_approval.is_configured() is False

    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    assert telegram_approval.is_configured() is True
