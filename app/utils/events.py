"""Calendar events: timezone, recurrence, queries, feeds."""

import json
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil import rrule as dateutil_rrule
from icalendar import Calendar, Event as ICalEvent
from flask import url_for

from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.markdown_safe import strip_markdown_plain
from app.utils.recurrence_form import normalize_rrule_string

EVENT_TIERS = ('official', 'community', 'region', 'organizer')
EVENT_CATEGORIES = ('maintenance', 'social', 'class', 'competition', 'other')
EVENT_STATUSES = ('draft', 'published', 'cancelled')

TIER_LABELS = {
    'official': 'Official',
    'community': 'Community',
    'region': 'Region',
    'organizer': 'Organizer',
}

CATEGORY_LABELS = {
    'maintenance': 'Maintenance',
    'social': 'Social',
    'class': 'Class / Workshop',
    'competition': 'Competition',
    'other': 'Other',
}


def grid_tz():
    name = get_dynamic_config('grid_timezone') or 'America/Los_Angeles'
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo('America/Los_Angeles')


def utc_now_naive():
    return datetime.utcnow()


def parse_local_datetime(date_str, time_str=None, all_day=False):
    """Parse form input as grid-local time, return naive UTC for DB storage."""
    tz = grid_tz()
    if all_day or not time_str:
        dt_local = datetime.strptime(date_str.strip(), '%Y-%m-%d')
        if all_day:
            dt_local = dt_local.replace(hour=0, minute=0, second=0)
    else:
        dt_local = datetime.strptime(f"{date_str.strip()} {time_str.strip()}", '%Y-%m-%d %H:%M')
    dt_local = dt_local.replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_utc


def format_pacific(dt_utc, all_day=False):
    """Format UTC naive datetime for display in grid timezone."""
    if dt_utc is None:
        return ''
    if isinstance(dt_utc, str):
        dt_utc = datetime.fromisoformat(dt_utc.replace('Z', '+00:00')).replace(tzinfo=None)
    dt = dt_utc.replace(tzinfo=timezone.utc).astimezone(grid_tz())
    if all_day:
        return dt.strftime('%B %d, %Y') + ' (PT)'
    return dt.strftime('%B %d, %Y %I:%M %p') + ' PT'


def occurrence_local_date(dt_utc_naive):
    """Calendar day in grid timezone for a naive-UTC stored datetime."""
    if dt_utc_naive is None:
        return None
    if isinstance(dt_utc_naive, str):
        dt_utc_naive = datetime.fromisoformat(str(dt_utc_naive))
    return dt_utc_naive.replace(tzinfo=timezone.utc).astimezone(grid_tz()).date()


def local_date_utc_range(local_date):
    """Half-open naive-UTC range [start, end) for one grid-local calendar day."""
    tz = grid_tz()
    start_local = datetime.combine(local_date, datetime.min.time()).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def local_month_utc_range(year, month, expand_months=3):
    """Naive-UTC range from local month start through expand window."""
    tz = grid_tz()
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end_anchor = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end_anchor = datetime(year, month + 1, 1, tzinfo=tz)
    end_local = end_anchor + timedelta(days=expand_months * 31)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def group_occurrences_by_local_date(occurrences):
    """Bucket expanded occurrences by grid-local calendar date."""
    grouped = {}
    for occ in occurrences:
        d = occurrence_local_date(occ['occurrence_start'])
        grouped.setdefault(d, []).append(occ)
    return grouped


def grid_today():
    return datetime.now(grid_tz()).date()


def _duration_seconds(event):
    start = event['starts_at']
    end = event.get('ends_at') or start
    if isinstance(start, str):
        start = datetime.fromisoformat(str(start))
    if isinstance(end, str):
        end = datetime.fromisoformat(str(end))
    return max(0, int((end - start).total_seconds()))


def _parse_json_list(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (TypeError, json.JSONDecodeError):
        return []


def _occurrence_cancelled(event, occ_start):
    cancelled = _parse_json_list(event.get('cancelled_occurrences'))
    occ_iso = occ_start.replace(microsecond=0).isoformat()
    for c in cancelled:
        if str(c).startswith(occ_iso[:16]):
            return True
    return False


def expand_event_occurrences(event, range_start, range_end):
    """
    Expand a calendar_events row into occurrence dicts within [range_start, range_end].
    Each occurrence: {event_id, occurrence_start, occurrence_end, series_event, cancelled}
    """
    if isinstance(range_start, str):
        range_start = datetime.fromisoformat(range_start)
    if isinstance(range_end, str):
        range_end = datetime.fromisoformat(range_end)

    start = event['starts_at']
    if isinstance(start, str):
        start = datetime.fromisoformat(str(start))
    end = event.get('ends_at') or start
    if isinstance(end, str):
        end = datetime.fromisoformat(str(end))
    duration = end - start

    series_cancelled = event.get('status') == 'cancelled'
    rrule_str = event.get('recurrence_rule')

    if not rrule_str:
        if range_start <= start <= range_end:
            return [{
                'event_id': event['id'],
                'occurrence_start': start,
                'occurrence_end': end,
                'series_event': event,
                'cancelled': series_cancelled or _occurrence_cancelled(event, start),
            }]
        return []

    try:
        rule = dateutil_rrule.rrulestr(
            f"RRULE:{normalize_rrule_string(rrule_str)}",
            dtstart=start.replace(tzinfo=timezone.utc),
        )
    except (ValueError, TypeError, KeyError):
        if range_start <= start <= range_end:
            return [{
                'event_id': event['id'],
                'occurrence_start': start,
                'occurrence_end': end,
                'series_event': event,
                'cancelled': series_cancelled or _occurrence_cancelled(event, start),
            }]
        return []

    until = event.get('recurrence_until')
    if until:
        if isinstance(until, str):
            until = datetime.fromisoformat(str(until))
        rule = rule.replace(until=until.replace(tzinfo=timezone.utc))

    rs = range_start.replace(tzinfo=timezone.utc)
    re = range_end.replace(tzinfo=timezone.utc)
    occurrences = []
    try:
        occ_iter = rule.between(rs, re, inc=True)
    except (ValueError, TypeError):
        occ_iter = []
    for occ in occ_iter:
        occ_naive = occ.astimezone(timezone.utc).replace(tzinfo=None)
        occ_end = occ_naive + duration
        cancelled = series_cancelled or _occurrence_cancelled(event, occ_naive)
        occurrences.append({
            'event_id': event['id'],
            'occurrence_start': occ_naive,
            'occurrence_end': occ_end,
            'series_event': event,
            'cancelled': cancelled,
        })
    return occurrences


def fetch_published_events(tier_filter=None, category_filter=None, region_filter=None):
    conn = get_pariah_db()
    query = """
        SELECT e.*, r.region_name
        FROM calendar_events e
        LEFT JOIN region_configs r ON e.region_uuid = r.region_uuid
        WHERE e.status = 'published' AND e.recurrence_parent_id IS NULL
    """
    params = []
    if tier_filter:
        placeholders = ','.join(['%s'] * len(tier_filter))
        query += f" AND e.event_tier IN ({placeholders})"
        params.extend(tier_filter)
    if category_filter:
        placeholders = ','.join(['%s'] * len(category_filter))
        query += f" AND e.category IN ({placeholders})"
        params.extend(category_filter)
    if region_filter:
        placeholders = ','.join(['%s'] * len(region_filter))
        query += f" AND e.region_uuid IN ({placeholders})"
        params.extend(region_filter)
    query += " ORDER BY e.starts_at ASC"
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def expand_events_for_range(range_start, range_end, tier_filter=None, category_filter=None,
                            region_filter=None, include_cancelled=False):
    events = fetch_published_events(tier_filter, category_filter, region_filter)
    expanded = []
    for ev in events:
        for occ in expand_event_occurrences(ev, range_start, range_end):
            if not include_cancelled and occ['cancelled']:
                continue
            expanded.append(occ)
    expanded.sort(key=lambda x: x['occurrence_start'])
    return expanded


def get_event_by_id(event_id):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.*, r.region_name
            FROM calendar_events e
            LEFT JOIN region_configs r ON e.region_uuid = r.region_uuid
            WHERE e.id = %s
            """,
            (event_id,),
        )
        return cursor.fetchone()


def parse_feed_filters(request_args, token_row=None):
    """Build filter lists from query params or saved subscription token."""
    if token_row:
        tiers = _parse_json_list(token_row.get('filter_tiers'))
        categories = _parse_json_list(token_row.get('filter_categories'))
        regions = _parse_json_list(token_row.get('filter_regions'))
        return tiers or None, categories or None, regions or None

    tier_raw = (request_args.get('tier') or '').strip()
    cat_raw = (request_args.get('category') or '').strip()
    reg_raw = (request_args.get('region') or '').strip()

    tiers = [t.strip() for t in tier_raw.split(',') if t.strip()] if tier_raw else None
    categories = [c.strip() for c in cat_raw.split(',') if c.strip()] if cat_raw else None
    regions = [r.strip() for r in reg_raw.split(',') if r.strip()] if reg_raw else None
    return tiers, categories, regions


def load_subscription_by_token(token):
    if not token:
        return None
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_feed_subscriptions WHERE subscription_token = %s",
            (token.strip(),),
        )
        return cursor.fetchone()


def build_ical_feed(events, request_host_url):
    cal = Calendar()
    cal.add('prodid', '-//OS Pariah Portal//Calendar//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('X-WR-TIMEZONE', str(grid_tz().key))

    tz = grid_tz()
    for ev in events[:200]:
        ical_ev = ICalEvent()
        uid = f"pariah-event-{ev['id']}@portal"
        ical_ev.add('uid', uid)
        ical_ev.add('summary', ev['title'])
        if ev.get('description'):
            ical_ev.add('description', strip_markdown_plain(ev['description'], 2000))
        if ev.get('location'):
            ical_ev.add('location', ev['location'])

        start = ev['starts_at']
        if isinstance(start, str):
            start = datetime.fromisoformat(str(start))
        start_local = start.replace(tzinfo=timezone.utc).astimezone(tz)

        if ev.get('all_day'):
            ical_ev.add('dtstart', start_local.date())
            if ev.get('ends_at'):
                end = ev['ends_at']
                if isinstance(end, str):
                    end = datetime.fromisoformat(str(end))
                end_local = end.replace(tzinfo=timezone.utc).astimezone(tz)
                ical_ev.add('dtend', end_local.date())
        else:
            ical_ev.add('dtstart', start_local)
            end = ev.get('ends_at') or start
            if isinstance(end, str):
                end = datetime.fromisoformat(str(end))
            end_local = end.replace(tzinfo=timezone.utc).astimezone(tz)
            ical_ev.add('dtend', end_local)

        if ev.get('recurrence_rule'):
            ical_ev.add('rrule', ev['recurrence_rule'].replace('RRULE:', ''))
        if ev.get('status') == 'cancelled':
            ical_ev.add('status', 'CANCELLED')

        ical_ev.add('url', f"{request_host_url}/events/{ev['id']}")
        cal.add_component(ical_ev)

    return cal.to_ical()


def build_rss_feed(events, request_host_url, grid_name='Grid'):
    items = []
    for ev in events[:200]:
        start = ev['starts_at']
        pub = start.strftime('%a, %d %b %Y %H:%M:%S +0000') if hasattr(start, 'strftime') else ''
        desc = strip_markdown_plain(ev.get('description') or '', 500)
        link = f"{request_host_url}/events/{ev['id']}"
        items.append(f"""
    <item>
      <title>{_xml_escape(ev['title'])}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub}</pubDate>
      <description>{_xml_escape(desc)}</description>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{_xml_escape(grid_name)} Events</title>
    <link>{request_host_url}/events</link>
    <description>Grid calendar events</description>
    {''.join(items)}
  </channel>
</rss>"""


def _xml_escape(s):
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def calendar_month_grid(year, month):
    """Return weeks as lists of date objects (None for padding). Columns are Sun–Sat."""
    _, days_in_month = monthrange(year, month)
    first_day = datetime(year, month, 1).date()
    # datetime.weekday(): Mon=0 … Sun=6 → Sun-first column index
    leading_blanks = (first_day.weekday() + 1) % 7
    weeks = []
    week = [None] * leading_blanks
    for day in range(1, days_in_month + 1):
        week.append(datetime(year, month, day).date())
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)
    return weeks


def calendar_week_start(date_obj):
    """Sunday-start week containing date_obj."""
    days_since_sunday = (date_obj.weekday() + 1) % 7
    return date_obj - timedelta(days=days_since_sunday)


def calendar_week_dates(week_start):
    return [week_start + timedelta(days=i) for i in range(7)]


REMINDER_OFFSET_CHOICES = [
    (604800, '7 days before'),
    (86400, '24 hours before'),
    (3600, '1 hour before'),
    (1800, '30 minutes before'),
    (900, '15 minutes before'),
]


def parse_reminder_offsets_from_form(form):
    offsets = []
    for val in form.getlist('reminder_offset'):
        try:
            offsets.append(int(val))
        except (TypeError, ValueError):
            pass
    custom = (form.get('reminder_custom_minutes') or '').strip()
    if custom.isdigit():
        offsets.append(int(custom) * 60)
    if not offsets:
        return default_reminder_offsets()
    return sorted(set(offsets), reverse=True)


def default_reminder_offsets():
    raw = get_dynamic_config('calendar_default_reminder_offsets') or '[86400, 3600]'
    try:
        offsets = json.loads(raw)
        return [int(x) for x in offsets]
    except (TypeError, json.JSONDecodeError, ValueError):
        return [86400, 3600]


def new_subscription_token():
    return str(uuid.uuid4())


def utc_to_local_parts(dt_utc):
    """Return (date_str, time_str) in grid timezone for form fields."""
    if not dt_utc:
        return '', ''
    if isinstance(dt_utc, str):
        dt_utc = datetime.fromisoformat(str(dt_utc))
    dt = dt_utc.replace(tzinfo=timezone.utc).astimezone(grid_tz())
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M')


def event_form_defaults():
    return {
        'title': '',
        'description': '',
        'date_start': '',
        'time_start': '',
        'date_end': '',
        'time_end': '',
        'all_day': False,
        'location': '',
        'slurl': '',
        'region_uuid': '',
        'event_tier': 'community',
        'category': 'other',
        'recurrence_rule': '',
        'recurrence_until_date': '',
        'recurrence_mode': 'none',
        'recurrence_weekly_days': [],
        'recurrence_custom_rule': '',
        'announce_group_uuid': '',
        'use_group_chat': '',
        'use_group_notice': '',
    }
