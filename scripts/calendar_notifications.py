"""Calendar notification scheduler for worker.py (requires Flask app context)."""

import json
from datetime import timedelta

from app.utils.db import get_dynamic_config, get_pariah_db
from app.utils.event_notifications import (
    log_notification_sent,
    notification_already_sent,
    send_event_email,
)
from app.utils.events import (
    expand_event_occurrences,
    expand_events_for_range,
    format_pacific,
    utc_now_naive,
)
from app.utils.grid_bot import enqueue_bot_message, enqueue_event_announcements


def process_calendar_notifications():
    if str(get_dynamic_config("calendar_enabled", "true")).lower() != "true":
        return

    now = utc_now_naive()
    window_end = now + timedelta(hours=2)
    occurrences = expand_events_for_range(now - timedelta(minutes=5), window_end)

    upcoming_min = int(get_dynamic_config("calendar_bot_upcoming_minutes") or 15)
    halfway_enabled = (
        str(get_dynamic_config("calendar_bot_halfway_enabled")).lower() == "true"
    )

    conn = get_pariah_db()
    for occ in occurrences:
        if occ["cancelled"]:
            continue
        ev = occ["series_event"]
        start = occ["occurrence_start"]
        eid = ev["id"]
        delta = (start - now).total_seconds()

        if 0 < delta <= upcoming_min * 60 + 30:
            ntype = "event_upcoming"
            if not notification_already_sent(eid, None, start, ntype):
                msg = f'Upcoming: "{ev["title"]}" starts at {format_pacific(start, ev.get("all_day"))}.'
                enqueue_event_announcements("calendar", ntype, msg, ev)
                log_notification_sent(eid, None, start, ntype)

        if -60 <= delta <= 60:
            ntype = "event_starting"
            if not notification_already_sent(eid, None, start, ntype):
                msg = f'Starting now: "{ev["title"]}" — {ev.get("location") or "see calendar"}.'
                enqueue_event_announcements("calendar", ntype, msg, ev)
                log_notification_sent(eid, None, start, ntype)

        if halfway_enabled and ev.get("ends_at"):
            end = occ["occurrence_end"]
            mid = start + (end - start) / 2
            if abs((now - mid).total_seconds()) <= 90:
                ntype = "event_halfway"
                if not notification_already_sent(eid, None, start, ntype):
                    msg = f'Halfway: "{ev["title"]}" is underway.'
                    enqueue_event_announcements("calendar", ntype, msg, ev)
                    log_notification_sent(eid, None, start, ntype)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT f.*, e.title, e.starts_at, e.ends_at, e.all_day, e.recurrence_rule,
                   e.region_uuid, e.status
            FROM event_follows f
            JOIN calendar_events e ON e.id = f.event_id
            WHERE e.status = 'published'
            """
        )
        follows = cursor.fetchall()

    for f in follows:
        offsets = f.get("reminder_offsets")
        if isinstance(offsets, str):
            try:
                offsets = json.loads(offsets)
            except json.JSONDecodeError:
                offsets = [86400, 3600]
        ev = {
            "id": f["event_id"],
            "title": f["title"],
            "starts_at": f["starts_at"],
            "ends_at": f["ends_at"],
            "all_day": f["all_day"],
            "recurrence_rule": f["recurrence_rule"],
            "region_uuid": f.get("region_uuid"),
            "status": f["status"],
        }
        for occ in expand_event_occurrences(ev, now, window_end + timedelta(days=7)):
            if occ["cancelled"]:
                continue
            start = occ["occurrence_start"]
            seconds_until = (start - now).total_seconds()
            for offset in offsets:
                if abs(seconds_until - int(offset)) <= 120:
                    ntype = f"reminder_{offset}"
                    uid = f["user_uuid"]
                    if notification_already_sent(ev["id"], uid, start, ntype):
                        continue
                    when = format_pacific(start, ev.get("all_day"))
                    body = f'Reminder: "{ev["title"]}" starts at {when}.'
                    if f.get("notify_email"):
                        send_event_email(uid, f"Event reminder: {ev['title']}", body)
                    if f.get("notify_inworld"):
                        enqueue_bot_message(
                            "calendar",
                            "event_reminder_im",
                            body,
                            target_uuid=uid,
                            delivery_channel="im",
                            metadata={"event_id": ev["id"]},
                        )
                    log_notification_sent(ev["id"], uid, start, ntype)
