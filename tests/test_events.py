"""Tests for calendar / events module."""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.utils.events import (
    calendar_month_grid,
    calendar_week_dates,
    calendar_week_start,
    expand_event_occurrences,
    group_occurrences_by_local_date,
    occurrence_local_date,
    parse_local_datetime,
    parse_reminder_offsets_from_form,
)
from app.utils.grid_bot import (
    MAX_WRONG_REGION_RETRIES,
    ack_message,
    enqueue_event_announcements,
    format_message_text_line,
    is_grid_bot_uuid,
)
from app.utils.markdown_safe import render_markdown as md_render
from app.utils.schema import PERM_APPROVE_EVENTS


def test_parse_local_datetime(app):
    with app.app_context():
        utc = parse_local_datetime("2026-06-15", "14:30", all_day=False)
    assert utc is not None
    assert isinstance(utc, datetime)


def test_occurrence_local_date_evening_pacific(app):
    """Evening PT events must bucket on the local calendar day, not UTC date."""
    from datetime import date

    with app.app_context():
        utc = parse_local_datetime("2026-05-24", "19:00", all_day=False)
        assert utc.date() == date(2026, 5, 25)
        assert occurrence_local_date(utc) == date(2026, 5, 24)


def test_group_occurrences_by_local_date(app):
    from datetime import date

    with app.app_context():
        ev = {
            "id": 1,
            "starts_at": parse_local_datetime("2026-05-24", "10:00", all_day=False),
            "ends_at": parse_local_datetime("2026-05-24", "11:00", all_day=False),
            "recurrence_rule": None,
            "status": "published",
            "cancelled_occurrences": None,
        }
        ev2 = {
            "id": 2,
            "starts_at": parse_local_datetime("2026-05-24", "19:00", all_day=False),
            "ends_at": parse_local_datetime("2026-05-24", "20:00", all_day=False),
            "recurrence_rule": None,
            "status": "published",
            "cancelled_occurrences": None,
        }
        occs = expand_event_occurrences(
            ev, datetime(2026, 5, 1), datetime(2026, 6, 1)
        ) + expand_event_occurrences(ev2, datetime(2026, 5, 1), datetime(2026, 6, 1))
        grouped = group_occurrences_by_local_date(occs)
        assert len(grouped[date(2026, 5, 24)]) == 2


def test_expand_single_event():
    ev = {
        "id": 1,
        "starts_at": datetime(2026, 6, 15, 19, 0),
        "ends_at": datetime(2026, 6, 15, 21, 0),
        "recurrence_rule": None,
        "status": "published",
        "cancelled_occurrences": None,
    }
    occs = expand_event_occurrences(
        ev,
        datetime(2026, 6, 1),
        datetime(2026, 6, 30),
    )
    assert len(occs) == 1
    assert occs[0]["event_id"] == 1


def test_markdown_strips_script():
    html = md_render("Hello **world**<script>alert(1)</script>")
    assert "world" in html
    assert "script" not in html.lower()


@patch("app.utils.grid_bot.get_dynamic_config")
def test_grid_bot_uuid_protected(mock_cfg):
    mock_cfg.return_value = "bot-uuid-123"
    assert is_grid_bot_uuid("bot-uuid-123") is True
    assert is_grid_bot_uuid("other-uuid") is False


def test_calendar_requires_login(client):
    response = client.get("/events/", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/auth/login" in response.headers.get("Location", "")


def test_feed_ics_public(client):
    response = client.get("/events/feed.ics")
    assert response.status_code == 200
    assert b"VCALENDAR" in response.data or response.content_type.startswith(
        "text/calendar"
    )


def test_moderation_requires_permission(client):
    with client.session_transaction() as sess:
        sess["uuid"] = "user-1"
        sess["permissions"] = 0
        sess["user_level"] = 0
    response = client.get("/events/moderation", follow_redirects=True)
    assert response.status_code == 200


def test_moderation_access_with_permission(client, db_cursor):
    db_cursor.fetchall.return_value = []
    with client.session_transaction() as sess:
        sess["uuid"] = "staff-1"
        sess["permissions"] = PERM_APPROVE_EVENTS
        sess["user_level"] = 1
        sess["name"] = "Staff User"
    response = client.get("/events/moderation")
    assert response.status_code == 200


def test_bot_api_unauthorized(client):
    response = client.get("/api/bot/queue")
    assert response.status_code == 401


@patch("app.utils.grid_bot.get_dynamic_config")
def test_bot_queue_text_format(mock_cfg, client, db_cursor):
    mock_cfg.side_effect = lambda k, default=None: {
        "grid_bot_api_token": "test-token",
    }.get(k, default or "")
    db_cursor.fetchall.return_value = []
    response = client.get("/api/bot/queue?format=text&token=test-token")
    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")


@patch("app.utils.grid_bot.get_dynamic_config")
def test_bot_ack_get(mock_cfg, client, db_cursor):
    mock_cfg.side_effect = lambda k, default=None: {
        "grid_bot_api_token": "test-token",
    }.get(k, default or "")
    response = client.get("/api/bot/ack/1?format=text&token=test-token&success=1")
    assert response.status_code == 200


def test_format_message_text_line_eight_fields():
    line = format_message_text_line(
        {
            "id": 42,
            "message_type": "event_upcoming",
            "target_uuid": "",
            "target_region_name": "Welcome",
            "target_group_uuid": "group-uuid",
            "delivery_channel": "group_notice",
            "notice_subject": "Party Tonight",
            "message_body": "Starts at 7pm",
        }
    )
    parts = line.split("|")
    assert len(parts) == 8
    assert parts[5] == "group_notice"
    assert parts[6] == "Party Tonight"


@patch("app.utils.grid_bot.get_pariah_db")
def test_ack_wrong_region_requeues(mock_db):
    cursor = mock_db.return_value.cursor.return_value.__enter__.return_value
    ack_message(99, success=False, error="wrong_region")
    sql = cursor.execute.call_args[0][0]
    assert "wrong_region" in cursor.execute.call_args[0][1][1]
    assert str(MAX_WRONG_REGION_RETRIES) in sql or "retry_count" in sql


@patch("app.utils.grid_bot.enqueue_bot_message")
@patch("app.utils.grid_bot.get_dynamic_config")
def test_enqueue_event_announcements_fans_out(mock_cfg, mock_enqueue):
    mock_cfg.side_effect = lambda k, default=None: {
        "grid_bot_announce_group_uuid": "default-group",
        "calendar_default_use_group_chat": "true",
        "calendar_default_use_group_notice": "true",
    }.get(k, default or "")
    event = {"id": 1, "title": "Test Event", "region_uuid": "region-1"}
    enqueue_event_announcements("calendar", "event_upcoming", "Hello", event)
    assert mock_enqueue.call_count == 3


def test_parse_reminder_offsets_from_form():
    class Form:
        def getlist(self, key):
            return ["86400", "3600"] if key == "reminder_offset" else []

        def get(self, key, default=None):
            return ""

    assert parse_reminder_offsets_from_form(Form()) == [86400, 3600]


def test_calendar_week_helpers():
    from datetime import date

    start = calendar_week_start(date(2026, 5, 23))  # Saturday
    assert start.weekday() == 6  # Sunday
    assert len(calendar_week_dates(start)) == 7


def test_calendar_month_grid_sunday_columns():
    """Month grid columns match Sun–Sat headers (not calendar.monthrange Mon=0)."""
    from datetime import date

    weeks = calendar_month_grid(2026, 5)
    may_24 = date(2026, 5, 24)
    assert may_24.weekday() == 6  # Sunday
    for week in weeks:
        for col, cell in enumerate(week):
            if cell == may_24:
                assert col == 0, "May 24 2026 should appear in the Sunday column"
                return
    pytest.fail("May 24 2026 not found in month grid")
