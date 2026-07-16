"""Tests for human-friendly recurrence form helpers."""

from datetime import date, datetime

from app.utils.events import expand_event_occurrences
from app.utils.recurrence_form import (
    build_recurrence_rule,
    format_recurrence_human,
    normalize_rrule_string,
    parse_recurrence_for_form,
    recurrence_from_form,
)


class _FakeForm(dict):
    def getlist(self, key):
        v = self.get(key)
        if v is None:
            return []
        return v if isinstance(v, list) else [v]


def test_build_weekly_from_start_date():
    start = date(2026, 5, 24)  # Sunday
    assert build_recurrence_rule("weekly", start_date=start) == "FREQ=WEEKLY;BYDAY=SU"


def test_build_weekly_multiple_days():
    rule = build_recurrence_rule("weekly", weekly_days=["TU", "TH"])
    assert rule == "FREQ=WEEKLY;BYDAY=TU,TH"


def test_normalize_legacy_spaces():
    assert normalize_rrule_string("FREQ=WEEKLY; BYDAY=SA") == "FREQ=WEEKLY;BYDAY=SA"


def test_parse_roundtrip_weekly():
    parsed = parse_recurrence_for_form("FREQ=WEEKLY;BYDAY=MO,WE")
    assert parsed["recurrence_mode"] == "weekly"
    assert parsed["recurrence_weekly_days"] == ["MO", "WE"]


def test_recurrence_from_form_none():
    form = _FakeForm({"recurrence_mode": "none"})
    rule, err = recurrence_from_form(form, date(2026, 6, 1))
    assert rule is None
    assert err is None


def test_malformed_rrule_does_not_crash_expand(app):
    with app.app_context():
        ev = {
            "id": 99,
            "starts_at": datetime(2026, 6, 1, 19, 0),
            "ends_at": datetime(2026, 6, 1, 21, 0),
            "recurrence_rule": "FREQ=WEEKLY BYDAY=SA",
            "status": "published",
            "cancelled_occurrences": None,
        }
        occs = expand_event_occurrences(
            ev,
            datetime(2026, 6, 1),
            datetime(2026, 6, 30),
        )
        assert len(occs) >= 1


def test_format_recurrence_human_weekly():
    text = format_recurrence_human("FREQ=WEEKLY;BYDAY=SA")
    assert "Saturday" in text
