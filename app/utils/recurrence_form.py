"""Human-friendly recurrence form fields ↔ iCalendar RRULE."""

import re
from datetime import datetime

RECURRENCE_MODES = (
    ('none', 'Does not repeat'),
    ('daily', 'Every day'),
    ('weekly', 'Every week'),
    ('biweekly', 'Every 2 weeks'),
    ('monthly', 'Every month (same date)'),
)

WEEKDAY_CODES = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')
WEEKDAY_LABELS = {
    'MO': 'Monday', 'TU': 'Tuesday', 'WE': 'Wednesday', 'TH': 'Thursday',
    'FR': 'Friday', 'SA': 'Saturday', 'SU': 'Sunday',
}


def _python_weekday_to_code(weekday):
    """datetime.weekday(): Mon=0 → MO."""
    return WEEKDAY_CODES[weekday % 7]


def _parse_start_date(date_str):
    if not date_str or not str(date_str).strip():
        return None
    try:
        return datetime.strptime(str(date_str).strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def normalize_rrule_string(rrule_str):
    """Best-effort cleanup for legacy stored rules (not for new user input)."""
    if not rrule_str:
        return ''
    s = str(rrule_str).strip().upper()
    if s.startswith('RRULE:'):
        s = s[6:]
    s = re.sub(r'\s+', '', s)
    return s


def _rrule_parts(rrule_str):
    norm = normalize_rrule_string(rrule_str)
    if not norm:
        return {}
    parts = {}
    for piece in norm.split(';'):
        if '=' in piece:
            k, v = piece.split('=', 1)
            parts[k.strip()] = v.strip()
    return parts


def build_recurrence_rule(mode, start_date=None, weekly_days=None):
    """Build RRULE string from form selections. Returns None if not recurring."""
    mode = (mode or 'none').strip().lower()
    if mode in ('', 'none'):
        return None

    if mode == 'daily':
        return 'FREQ=DAILY'

    if mode == 'weekly':
        days = [d for d in (weekly_days or []) if d in WEEKDAY_CODES]
        if not days and start_date:
            days = [_python_weekday_to_code(start_date.weekday())]
        if not days:
            return None
        return f"FREQ=WEEKLY;BYDAY={','.join(days)}"

    if mode == 'biweekly':
        if start_date:
            day = _python_weekday_to_code(start_date.weekday())
            return f"FREQ=WEEKLY;INTERVAL=2;BYDAY={day}"
        return 'FREQ=WEEKLY;INTERVAL=2'

    if mode == 'monthly':
        if start_date:
            return f"FREQ=MONTHLY;BYMONTHDAY={start_date.day}"
        return 'FREQ=MONTHLY'

    return None


def parse_recurrence_for_form(rrule_str, start_date=None):
    """
    Map stored RRULE to form field values.
    Returns recurrence_mode, recurrence_weekly_days, recurrence_custom_rule.
    """
    base = {
        'recurrence_mode': 'none',
        'recurrence_weekly_days': [],
        'recurrence_custom_rule': '',
    }
    if not rrule_str:
        return base

    parts = _rrule_parts(rrule_str)
    if not parts.get('FREQ'):
        base['recurrence_mode'] = 'custom'
        base['recurrence_custom_rule'] = normalize_rrule_string(rrule_str)
        return base

    freq = parts['FREQ']
    try:
        interval = int(parts.get('INTERVAL', '1') or '1')
    except ValueError:
        interval = 1

    if freq == 'DAILY' and interval == 1 and 'BYDAY' not in parts:
        base['recurrence_mode'] = 'daily'
        return base

    if freq == 'WEEKLY':
        byday = parts.get('BYDAY', '')
        days = [d for d in re.split(r'[,]', byday) if d in WEEKDAY_CODES]
        if interval == 2:
            base['recurrence_mode'] = 'biweekly'
            base['recurrence_weekly_days'] = days
            return base
        if interval == 1:
            base['recurrence_mode'] = 'weekly'
            base['recurrence_weekly_days'] = days
            return base

    if freq == 'MONTHLY' and parts.get('BYMONTHDAY') and interval == 1:
        base['recurrence_mode'] = 'monthly'
        return base

    base['recurrence_mode'] = 'custom'
    base['recurrence_custom_rule'] = normalize_rrule_string(rrule_str)
    return base


def recurrence_from_form(form, start_date=None):
    """Parse request form into (recurrence_rule, error_message)."""
    mode = (form.get('recurrence_mode') or 'none').strip().lower()

    if mode == 'custom':
        legacy = (form.get('recurrence_rule_legacy') or '').strip()
        if legacy:
            return normalize_rrule_string(legacy) or None, None
        return None, None

    if not start_date:
        start_date = _parse_start_date(form.get('date_start'))

    weekly_days = form.getlist('recurrence_weekly_days')
    rule = build_recurrence_rule(mode, start_date=start_date, weekly_days=weekly_days)
    if mode == 'weekly' and not rule:
        return None, 'Select at least one day of the week for a weekly repeat.'
    return rule, None


def recurrence_form_defaults():
    return {
        'recurrence_mode': 'none',
        'recurrence_weekly_days': [],
        'recurrence_custom_rule': '',
        'recurrence_until_date': '',
    }


def merge_recurrence_into_form(form_dict, rrule_str=None, starts_at=None, recurrence_until=None):
    """Add recurrence UI fields to an event form dict."""
    start_date = None
    if starts_at:
        if isinstance(starts_at, str):
            starts_at = datetime.fromisoformat(str(starts_at))
        start_date = starts_at.date() if hasattr(starts_at, 'date') else None

    parsed = parse_recurrence_for_form(rrule_str, start_date)
    form_dict.update(parsed)
    if recurrence_until:
        from app.utils.events import utc_to_local_parts
        ru, _ = utc_to_local_parts(recurrence_until)
        form_dict['recurrence_until_date'] = ru
    return form_dict


def format_recurrence_human(rrule_str, recurrence_until=None, all_day=False):
    """Plain-language summary for event detail pages."""
    if not rrule_str:
        return ''

    parsed = parse_recurrence_for_form(rrule_str)
    mode = parsed['recurrence_mode']

    if mode == 'custom':
        text = 'Custom repeat pattern'
    elif mode == 'daily':
        text = 'Repeats every day'
    elif mode == 'weekly':
        days = parsed['recurrence_weekly_days']
        if days:
            names = [WEEKDAY_LABELS.get(d, d) for d in days]
            text = 'Repeats every week on ' + ', '.join(names)
        else:
            text = 'Repeats every week'
    elif mode == 'biweekly':
        days = parsed['recurrence_weekly_days']
        if days:
            text = 'Repeats every 2 weeks on ' + WEEKDAY_LABELS.get(days[0], days[0])
        else:
            text = 'Repeats every 2 weeks'
    elif mode == 'monthly':
        text = 'Repeats every month on the same date'
    else:
        return ''

    if recurrence_until:
        from app.utils.events import format_pacific
        text += f', until {format_pacific(recurrence_until, all_day=all_day)}'
    else:
        text += ', no end date'
    return text
