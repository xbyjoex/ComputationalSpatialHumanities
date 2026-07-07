from src.telegram_bot import parse_registration_callback, _registration_outcome_text


def test_parse_valid_approve_and_reject():
    reg_id = "3f0e8b9a-1234-4cde-9f00-abcdef012345"
    assert parse_registration_callback(f"reg:approve:{reg_id}") == ("approve", reg_id)
    assert parse_registration_callback(f"reg:reject:{reg_id}") == ("reject", reg_id)


def test_parse_rejects_foreign_or_malformed_data():
    assert parse_registration_callback("") is None
    assert parse_registration_callback("etl-start") is None
    assert parse_registration_callback("reg:approve") is None
    assert parse_registration_callback("reg:delete:some-id") is None
    assert parse_registration_callback("other:approve:some-id") is None


def test_outcome_texts_cover_all_states():
    approved = _registration_outcome_text("approved", "a@b.de")
    assert "freigegeben" in approved and "a@b.de" in approved

    rejected = _registration_outcome_text("rejected", "a@b.de")
    assert "abgelehnt" in rejected

    expired = _registration_outcome_text("expired", "a@b.de")
    assert "abgelaufen" in expired and "kein Nutzer angelegt" in expired

    gone = _registration_outcome_text("gone", None)
    assert "nicht gefunden" in gone


def test_outcome_text_escapes_html():
    text = _registration_outcome_text("approved", "a&b@x.de")
    assert "a&amp;b@x.de" in text
