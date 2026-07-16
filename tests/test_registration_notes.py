from datetime import datetime
from unittest.mock import MagicMock

from app.utils.registration_notes import (
    format_registration_application_note,
    save_registration_application_note,
)


def test_format_registration_application_note_includes_all_fields():
    note = format_registration_application_note(
        {
            "email": "user@example.com",
            "inviter": "Friend Avatar",
            "discord": "user#1234",
            "matrix": "@user:matrix.org",
            "other_info": "I love building regions.",
            "created_at": datetime(2025, 5, 23, 12, 0, 0),
        }
    )
    assert "[REGISTRATION APPLICATION]" in note
    assert "user@example.com" not in note
    assert "Email:" not in note
    assert "Friend Avatar" in note
    assert "user#1234" in note
    assert "@user:matrix.org" in note
    assert "I love building regions." in note
    assert "Submitted (UTC):" in note


def test_format_registration_application_note_handles_missing_optionals():
    note = format_registration_application_note({"email": "a@b.co"})
    assert "Inviter: (not provided)" in note
    assert "Other information:" in note
    assert "(not provided)" in note


def test_save_registration_application_note_inserts_row():
    cursor = MagicMock()
    save_registration_application_note(
        cursor,
        "user-uuid-123",
        {
            "email": "a@b.co",
            "inviter": "",
            "discord": "",
            "matrix": "",
            "other_info": "",
        },
    )
    cursor.execute.assert_called_once()
    query, args = cursor.execute.call_args[0]
    assert "INSERT INTO user_notes" in query
    assert args[0] == "user-uuid-123"
    assert args[1] == "SYSTEM"
    assert "[REGISTRATION APPLICATION]" in args[2]
