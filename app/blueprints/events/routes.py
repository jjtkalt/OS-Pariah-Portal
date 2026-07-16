import contextlib
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.blueprints.auth.routes import verify_turnstile
from app.blueprints.regions.routes import _user_can_control_region
from app.utils.audit import log_audit_action
from app.utils.auth_helpers import has_permission, rbac_required, require_active_user
from app.utils.db import get_dynamic_config, get_pariah_db
from app.utils.event_notifications import (
    broadcast_event_cancelled,
    notify_followers_cancelled,
    notify_submitter_decision,
    notify_suggestion_staff,
)
from app.utils.events import (
    CATEGORY_LABELS,
    EVENT_CATEGORIES,
    EVENT_TIERS,
    REMINDER_OFFSET_CHOICES,
    TIER_LABELS,
    build_ical_feed,
    build_rss_feed,
    calendar_month_grid,
    calendar_week_dates,
    calendar_week_start,
    default_reminder_offsets,
    event_form_defaults,
    expand_event_occurrences,
    expand_events_for_range,
    fetch_published_events,
    format_pacific,
    get_event_by_id,
    grid_today,
    group_occurrences_by_local_date,
    load_subscription_by_token,
    local_date_utc_range,
    local_month_utc_range,
    new_subscription_token,
    occurrence_local_date,
    parse_feed_filters,
    parse_local_datetime,
    parse_reminder_offsets_from_form,
    utc_now_naive,
    utc_to_local_parts,
)
from app.utils.markdown_safe import render_markdown
from app.utils.recurrence_form import (
    RECURRENCE_MODES,
    WEEKDAY_CODES,
    WEEKDAY_LABELS,
    _parse_start_date,
    format_recurrence_human,
    merge_recurrence_into_form,
    recurrence_from_form,
)
from app.utils.schema import (
    PERM_APPROVE_EVENTS,
    PERM_DELETE_EVENTS,
    PERM_MANAGE_EVENTS,
    PERM_MANAGE_REGION_EVENTS,
)

events_bp = Blueprint("events", __name__)


def _calendar_enabled():
    return str(get_dynamic_config("calendar_enabled", "true")).lower() == "true"


def _calendar_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _calendar_enabled():
            flash("The calendar is currently disabled.", "error")
            return redirect(url_for("comms.news_feed"))
        return f(*args, **kwargs)

    return wrapped


def _can_manage_any_event():
    return has_permission(PERM_MANAGE_EVENTS)


def _can_manage_event_record(event):
    if has_permission(PERM_MANAGE_EVENTS):
        return True
    return bool(
        event.get("event_tier") == "region"
        and event.get("region_uuid")
        and (
            has_permission(PERM_MANAGE_REGION_EVENTS)
            or _user_can_control_region(event["region_uuid"])
        )
    )


def _parse_form_datetimes(form, prefix=""):
    all_day = form.get(f"{prefix}all_day") == "on"
    starts_at = parse_local_datetime(
        form.get(f"{prefix}date_start", ""),
        form.get(f"{prefix}time_start", "") if not all_day else None,
        all_day=all_day,
    )
    ends_at = None
    if form.get(f"{prefix}date_end"):
        ends_at = parse_local_datetime(
            form.get(f"{prefix}date_end", ""),
            form.get(f"{prefix}time_end", "") if not all_day else None,
            all_day=all_day,
        )
    elif (
        not all_day
        and form.get(f"{prefix}time_end")
        and form.get(f"{prefix}date_start")
    ):
        ends_at = parse_local_datetime(
            form.get(f"{prefix}date_start", ""),
            form.get(f"{prefix}time_end", ""),
            all_day=False,
        )
    return starts_at, ends_at, all_day


def _parse_tri_bool(form_val):
    if form_val == "1":
        return 1
    if form_val == "0":
        return 0
    return None


def _event_row_from_form(form, created_by_uuid, created_by_name, status="draft"):
    starts_at, ends_at, all_day = _parse_form_datetimes(form)
    recurrence_until = None
    if form.get("recurrence_until_date"):
        recurrence_until = parse_local_datetime(
            form.get("recurrence_until_date"), None, all_day=True
        )
    start_date = _parse_start_date(form.get("date_start"))
    rrule, rrule_error = recurrence_from_form(form, start_date=start_date)

    return {
        "title": (form.get("title") or "").strip()[:255],
        "description": (form.get("description") or "").strip() or None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "all_day": all_day,
        "location": (form.get("location") or "").strip()[:512] or None,
        "slurl": (form.get("slurl") or "").strip()[:512] or None,
        "region_uuid": (form.get("region_uuid") or "").strip() or None,
        "organizer_uuid": (form.get("organizer_uuid") or "").strip() or None,
        "event_tier": form.get("event_tier") or "community",
        "category": form.get("category") or "other",
        "status": status,
        "recurrence_rule": rrule,
        "recurrence_until": recurrence_until,
        "announce_group_uuid": (form.get("announce_group_uuid") or "").strip() or None,
        "use_group_chat": _parse_tri_bool(form.get("use_group_chat", "")),
        "use_group_notice": _parse_tri_bool(form.get("use_group_notice", "")),
        "created_by_uuid": created_by_uuid,
        "created_by_name": created_by_name,
        "_recurrence_error": rrule_error,
    }


def _list_regions():
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT region_uuid, region_name FROM region_configs ORDER BY region_name ASC"
        )
        return cursor.fetchall()


def _filter_params_from_request():
    tier = request.args.get("tier", "").strip()
    tier_filter = [tier] if tier and tier != "all" else None
    return tier_filter


def _calendar_url(view="month", year=None, month=None, day=None, tier=None):
    today = datetime.now().date()
    kwargs = {
        "view": view,
        "year": year if year is not None else today.year,
        "month": month if month is not None else today.month,
        "day": day if day is not None else today.day,
    }
    if tier:
        kwargs["tier"] = tier
    return url_for("events.calendar_index", **kwargs)


def _calendar_back_url():
    return session.get("events_calendar_return") or url_for("events.calendar_index")


def _save_calendar_return(view, year, month, day, tier):
    session["events_calendar_return"] = url_for(
        "events.calendar_index",
        view=view,
        year=year,
        month=month,
        day=day,
        **({"tier": tier} if tier else {}),
    )


def _parse_focus_date(year, month, day, today):
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return today


def _calendar_common_context(
    view, year, month, day, tier, today, is_current_period, month_name
):
    return {
        "view": view,
        "year": year,
        "month": month,
        "day": day,
        "tier_filter": tier,
        "tier_labels": TIER_LABELS,
        "format_pacific": format_pacific,
        "today_year": today.year,
        "today_month": today.month,
        "today_day": today.day,
        "is_current_period": is_current_period,
        "today_url": _calendar_url(view, today.year, today.month, today.day, tier),
        "month_name": month_name,
    }


def _expand_range(range_start, range_end, tier_filter=None):
    show_cancelled = (
        str(get_dynamic_config("calendar_show_cancelled")).lower() == "true"
    )
    return expand_events_for_range(
        range_start,
        range_end,
        tier_filter=tier_filter,
        include_cancelled=show_cancelled,
    )


def _expand_month(year, month, tier_filter=None):
    months = int(get_dynamic_config("calendar_recurrence_expand_months") or 3)
    range_start, range_end = local_month_utc_range(year, month, expand_months=months)
    return _expand_range(range_start, range_end, tier_filter)


@events_bp.route("/")
@_calendar_required
@require_active_user
def calendar_index():
    view = request.args.get("view", "month")
    tier_filter = _filter_params_from_request()
    tier = tier_filter[0] if tier_filter else None
    today = grid_today()

    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        day = int(request.args.get("day", today.day))
    except (TypeError, ValueError):
        year, month, day = today.year, today.month, today.day

    focus = _parse_focus_date(year, month, day, today)

    if view == "schedule":
        schedule_days = int(request.args.get("days", 60))
        range_start, range_end = local_date_utc_range(focus)
        _, range_end = local_date_utc_range(focus + timedelta(days=schedule_days))
        occurrences = _expand_range(range_start, range_end, tier_filter)
        schedule_grouped = group_occurrences_by_local_date(occurrences)
        prev_focus = focus - timedelta(days=30)
        next_focus = focus + timedelta(days=30)
        is_current = focus == today
        ctx = _calendar_common_context(
            view,
            focus.year,
            focus.month,
            focus.day,
            tier,
            today,
            is_current,
            f"Schedule from {focus.strftime('%B %d, %Y')}",
        )
        ctx.update(
            {
                "schedule_grouped": schedule_grouped,
                "prev_year": prev_focus.year,
                "prev_month": prev_focus.month,
                "prev_day": prev_focus.day,
                "next_year": next_focus.year,
                "next_month": next_focus.month,
                "next_day": next_focus.day,
            }
        )
        _save_calendar_return(view, focus.year, focus.month, focus.day, tier)
        return render_template("events/calendar.html", **ctx)

    if view == "week":
        week_start = calendar_week_start(focus)
        week_dates = calendar_week_dates(week_start)
        range_start, _ = local_date_utc_range(week_start)
        _, range_end = local_date_utc_range(week_start + timedelta(days=7))
        occurrences = _expand_range(range_start, range_end, tier_filter)
        by_date = group_occurrences_by_local_date(occurrences)
        prev_focus = week_start - timedelta(days=7)
        next_focus = week_start + timedelta(days=7)
        is_current = today in week_dates
        ctx = _calendar_common_context(
            view,
            focus.year,
            focus.month,
            focus.day,
            tier,
            today,
            is_current,
            f"Week of {week_start.strftime('%B %d, %Y')}",
        )
        ctx.update(
            {
                "week_dates": week_dates,
                "week_start": week_start,
                "by_date": by_date,
                "prev_year": prev_focus.year,
                "prev_month": prev_focus.month,
                "prev_day": prev_focus.day,
                "next_year": next_focus.year,
                "next_month": next_focus.month,
                "next_day": next_focus.day,
            }
        )
        _save_calendar_return(view, focus.year, focus.month, focus.day, tier)
        return render_template("events/calendar.html", **ctx)

    if view == "day":
        range_start, range_end = local_date_utc_range(focus)
        occurrences = _expand_range(range_start, range_end, tier_filter)
        day_occurrences = [
            occ
            for occ in occurrences
            if occurrence_local_date(occ["occurrence_start"]) == focus
        ]
        prev_focus = focus - timedelta(days=1)
        next_focus = focus + timedelta(days=1)
        is_current = focus == today
        ctx = _calendar_common_context(
            view,
            focus.year,
            focus.month,
            focus.day,
            tier,
            today,
            is_current,
            focus.strftime("%A, %B %d, %Y"),
        )
        ctx.update(
            {
                "day_occurrences": day_occurrences,
                "focus_date": focus,
                "prev_year": prev_focus.year,
                "prev_month": prev_focus.month,
                "prev_day": prev_focus.day,
                "next_year": next_focus.year,
                "next_month": next_focus.month,
                "next_day": next_focus.day,
            }
        )
        _save_calendar_return(view, focus.year, focus.month, focus.day, tier)
        return render_template("events/calendar.html", **ctx)

    occurrences = _expand_month(year, month, tier_filter)
    by_date = group_occurrences_by_local_date(occurrences)

    weeks = calendar_month_grid(year, month)
    prev_m, prev_y = (12, year - 1) if month == 1 else (month - 1, year)
    next_m, next_y = (1, year + 1) if month == 12 else (month + 1, year)
    is_current = (year, month) == (today.year, today.month)

    ctx = _calendar_common_context(
        view,
        year,
        month,
        day,
        tier,
        today,
        is_current,
        datetime(year, month, 1).strftime("%B %Y"),
    )
    ctx.update(
        {
            "weeks": weeks,
            "by_date": by_date,
            "prev_month": prev_m,
            "prev_year": prev_y,
            "next_month": next_m,
            "next_year": next_y,
        }
    )
    _save_calendar_return(view, year, month, day, tier)
    return render_template("events/calendar.html", **ctx)


@events_bp.route("/schedule")
@_calendar_required
@require_active_user
def schedule():
    """Legacy URL — redirect to unified calendar schedule view."""
    tier = request.args.get("tier", "").strip()
    args = {"view": "schedule"}
    for key in ("year", "month", "day", "days"):
        if request.args.get(key):
            args[key] = request.args.get(key)
    if tier:
        args["tier"] = tier
    return redirect(url_for("events.calendar_index", **args))


@events_bp.route("/search")
@_calendar_required
@require_active_user
def search():
    q = (request.args.get("q") or "").strip()
    results = []
    if q:
        conn = get_pariah_db()
        like = f"%{q}%"
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.*, r.region_name FROM calendar_events e
                LEFT JOIN region_configs r ON e.region_uuid = r.region_uuid
                WHERE e.status = 'published' AND e.event_tier = 'official'
                  AND e.recurrence_parent_id IS NULL
                  AND (e.title LIKE %s OR e.description LIKE %s OR e.location LIKE %s)
                ORDER BY e.starts_at ASC LIMIT 50
                """,
                (like, like, like),
            )
            results = cursor.fetchall()
    return render_template(
        "events/search.html",
        q=q,
        results=results,
        format_pacific=format_pacific,
        tier_labels=TIER_LABELS,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/my-suggestions/<int:sid>/withdraw", methods=["POST"])
@_calendar_required
@require_active_user
def withdraw_suggestion(sid):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id FROM event_suggestions
            WHERE id = %s AND submitter_uuid = %s AND status = 'pending'
            """,
            (sid, session["uuid"]),
        )
        if not cursor.fetchone():
            flash("Suggestion not found or cannot be withdrawn.", "error")
            return redirect(url_for("events.my_suggestions"))
        cursor.execute(
            "UPDATE event_suggestions SET status = 'withdrawn' WHERE id = %s",
            (sid,),
        )
    conn.commit()
    flash("Suggestion withdrawn.", "success")
    return redirect(url_for("events.my_suggestions"))


@events_bp.route("/<int:event_id>")
@_calendar_required
@require_active_user
def detail(event_id):
    event = get_event_by_id(event_id)
    if not event or event["status"] not in ("published", "draft", "cancelled"):
        flash("Event not found.", "error")
        return redirect(url_for("events.calendar_index"))

    if event["status"] == "draft" and not _can_manage_event_record(event):
        flash("Event not found.", "error")
        return redirect(url_for("events.calendar_index"))

    following = None
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_follows WHERE user_uuid = %s AND event_id = %s",
            (session["uuid"], event_id),
        )
        following = cursor.fetchone()

    upcoming_occurrences = []
    if event.get("recurrence_rule") and event["status"] == "published":
        now = utc_now_naive()
        upcoming_occurrences = [
            occ
            for occ in expand_event_occurrences(event, now, now + timedelta(days=90))
            if not occ["cancelled"]
        ][:20]

    return render_template(
        "events/detail.html",
        event=event,
        description_html=render_markdown(event.get("description") or ""),
        format_pacific=format_pacific,
        tier_labels=TIER_LABELS,
        category_labels=CATEGORY_LABELS,
        following=following,
        can_manage=_can_manage_event_record(event),
        upcoming_occurrences=upcoming_occurrences,
        back_url=_calendar_back_url(),
        recurrence_summary=format_recurrence_human(
            event.get("recurrence_rule"),
            event.get("recurrence_until"),
            event.get("all_day"),
        ),
    )


@events_bp.route("/<int:event_id>/follow", methods=["GET", "POST"])
@_calendar_required
@require_active_user
def follow(event_id):
    event = get_event_by_id(event_id)
    if not event or event["status"] != "published":
        flash("Cannot follow this event.", "error")
        return redirect(url_for("events.calendar_index"))

    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_follows WHERE user_uuid = %s AND event_id = %s",
            (session["uuid"], event_id),
        )
        following = cursor.fetchone()

    if request.method == "POST":
        notify_email = request.form.get("notify_email") == "on"
        notify_inworld = request.form.get("notify_inworld") == "on"
        offsets = parse_reminder_offsets_from_form(request.form)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO event_follows
                    (user_uuid, event_id, notify_email, notify_inworld, reminder_offsets)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    notify_email = VALUES(notify_email),
                    notify_inworld = VALUES(notify_inworld),
                    reminder_offsets = VALUES(reminder_offsets)
                """,
                (
                    session["uuid"],
                    event_id,
                    notify_email,
                    notify_inworld,
                    json.dumps(offsets),
                ),
            )
        conn.commit()
        flash("You are now following this event.", "success")
        return redirect(url_for("events.detail", event_id=event_id))

    selected_offsets = default_reminder_offsets()
    if following and following.get("reminder_offsets"):
        raw = following["reminder_offsets"]
        if isinstance(raw, str):
            with contextlib.suppress(json.JSONDecodeError):
                selected_offsets = json.loads(raw)
        elif isinstance(raw, list):
            selected_offsets = raw

    return render_template(
        "events/follow.html",
        event=event,
        default_offsets=default_reminder_offsets(),
        offset_choices=REMINDER_OFFSET_CHOICES,
        following=following,
        selected_offsets=selected_offsets,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/suggest", methods=["GET", "POST"])
@_calendar_required
@require_active_user
def suggest():
    if str(get_dynamic_config("calendar_allow_suggestions")).lower() != "true":
        flash("Event suggestions are currently disabled.", "error")
        return redirect(url_for("events.calendar_index"))

    conn = get_pariah_db()
    if request.method == "POST":
        if not verify_turnstile(request.form.get("cf-turnstile-response")):
            flash("Captcha verification failed.", "error")
            return redirect(url_for("events.suggest"))

        limit = int(get_dynamic_config("calendar_suggestion_rate_limit") or 3)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS c FROM event_suggestions WHERE submitter_uuid = %s AND status = 'pending'",
                (session["uuid"],),
            )
            if cursor.fetchone()["c"] >= limit:
                flash(f"You already have {limit} pending suggestions.", "error")
                return redirect(url_for("events.my_suggestions"))

        row = _event_row_from_form(request.form, session["uuid"], session["name"])
        row["event_tier"] = request.form.get("event_tier") or "organizer"
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO event_suggestions
                    (submitter_uuid, submitter_name, title, description, starts_at, ends_at,
                     all_day, location, slurl, region_uuid, event_tier, category,
                     recurrence_rule, recurrence_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session["uuid"],
                    session["name"],
                    row["title"],
                    row["description"],
                    row["starts_at"],
                    row["ends_at"],
                    row["all_day"],
                    row["location"],
                    row["slurl"],
                    row["region_uuid"],
                    row["event_tier"],
                    row["category"],
                    row["recurrence_rule"],
                    row["recurrence_until"],
                ),
            )
            sid = cursor.lastrowid
        conn.commit()
        notify_suggestion_staff(row["title"], session["name"], sid)
        flash("Your event suggestion has been submitted for review.", "success")
        return redirect(url_for("events.my_suggestions"))

    return render_template(
        "events/suggest.html",
        form=event_form_defaults(),
        regions=_list_regions(),
        tiers=EVENT_TIERS,
        categories=EVENT_CATEGORIES,
        tier_labels=TIER_LABELS,
        category_labels=CATEGORY_LABELS,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/my-suggestions")
@_calendar_required
@require_active_user
def my_suggestions():
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM event_suggestions WHERE submitter_uuid = %s
            ORDER BY created_at DESC LIMIT 50
            """,
            (session["uuid"],),
        )
        items = cursor.fetchall()
    return render_template(
        "events/my_suggestions.html",
        items=items,
        format_pacific=format_pacific,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/moderation")
@_calendar_required
@rbac_required(PERM_APPROVE_EVENTS)
def moderation():
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.*, r.region_name FROM event_suggestions s
            LEFT JOIN region_configs r ON s.region_uuid = r.region_uuid
            WHERE s.status = 'pending' ORDER BY s.created_at ASC
            """
        )
        pending = cursor.fetchall()
    return render_template(
        "events/moderation.html",
        pending=pending,
        format_pacific=format_pacific,
        description_html=lambda t: render_markdown(t or ""),
        back_url=url_for("comms.news_feed"),
    )


@events_bp.route("/moderation/<int:sid>/approve", methods=["POST"])
@_calendar_required
@rbac_required(PERM_APPROVE_EVENTS)
def approve_suggestion(sid):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_suggestions WHERE id = %s AND status = 'pending'",
            (sid,),
        )
        sug = cursor.fetchone()
        if not sug:
            flash("Suggestion not found or already processed.", "error")
            return redirect(url_for("events.moderation"))

        cursor.execute(
            """
            INSERT INTO calendar_events
                (title, description, starts_at, ends_at, all_day, location, slurl,
                 region_uuid, organizer_uuid, event_tier, category, status,
                 recurrence_rule, recurrence_until, source_suggestion_id,
                 created_by_uuid, created_by_name, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published',
                    %s, %s, %s, %s, %s, NOW())
            """,
            (
                sug["title"],
                sug["description"],
                sug["starts_at"],
                sug["ends_at"],
                sug["all_day"],
                sug["location"],
                sug["slurl"],
                sug["region_uuid"],
                sug["submitter_uuid"],
                sug["event_tier"],
                sug["category"],
                sug["recurrence_rule"],
                sug["recurrence_until"],
                sid,
                session["uuid"],
                session["name"],
            ),
        )
        cursor.execute(
            """
            UPDATE event_suggestions SET status = 'approved', reviewed_by_uuid = %s,
                   reviewed_at = NOW(), staff_notes = %s WHERE id = %s
            """,
            (session["uuid"], request.form.get("staff_notes"), sid),
        )
    conn.commit()
    notify_submitter_decision(sug["submitter_uuid"], True, sug["title"])
    log_audit_action(
        "Event approved", f"Suggestion #{sid} -> published", sug["submitter_uuid"]
    )
    flash("Event suggestion approved and published.", "success")
    return redirect(url_for("events.moderation"))


@events_bp.route("/moderation/<int:sid>/reject", methods=["POST"])
@_calendar_required
@rbac_required(PERM_APPROVE_EVENTS)
def reject_suggestion(sid):
    notes = (request.form.get("staff_notes") or "").strip()
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_suggestions WHERE id = %s AND status = 'pending'",
            (sid,),
        )
        sug = cursor.fetchone()
        if not sug:
            flash("Suggestion not found.", "error")
            return redirect(url_for("events.moderation"))
        cursor.execute(
            """
            UPDATE event_suggestions SET status = 'rejected', reviewed_by_uuid = %s,
                   reviewed_at = NOW(), staff_notes = %s WHERE id = %s
            """,
            (session["uuid"], notes, sid),
        )
    conn.commit()
    notify_submitter_decision(sug["submitter_uuid"], False, sug["title"], notes)
    log_audit_action("Event rejected", f"Suggestion #{sid}", sug["submitter_uuid"])
    flash("Event suggestion rejected.", "info")
    return redirect(url_for("events.moderation"))


@events_bp.route("/new", methods=["GET", "POST"])
@events_bp.route("/<int:event_id>/edit", methods=["GET", "POST"])
@_calendar_required
@require_active_user
def manage_event(event_id=None):
    event = get_event_by_id(event_id) if event_id else None
    if event_id and not event:
        flash("Event not found.", "error")
        return redirect(url_for("events.calendar_index"))
    if event and not _can_manage_event_record(event):
        flash("Unauthorized.", "error")
        return redirect(url_for("events.calendar_index"))
    if (
        not event_id
        and not _can_manage_any_event()
        and not has_permission(PERM_MANAGE_REGION_EVENTS)
    ):
        flash("Unauthorized.", "error")
        return redirect(url_for("events.calendar_index"))

    if request.method == "POST":
        manage_url = (
            url_for("events.manage_event", event_id=event_id)
            if event_id
            else url_for("events.manage_event")
        )
        row = _event_row_from_form(request.form, session["uuid"], session["name"])
        if row.get("_recurrence_error"):
            flash(row["_recurrence_error"], "error")
            return redirect(manage_url)
        if not row["title"] or not row["starts_at"]:
            flash("Title and start date are required.", "error")
            return redirect(manage_url)

        action = request.form.get("action", "save")
        if action == "publish":
            row["status"] = "published"
        elif event:
            row["status"] = event["status"]
        else:
            row["status"] = "draft"

        conn = get_pariah_db()
        if event_id:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE calendar_events SET title=%s, description=%s, starts_at=%s, ends_at=%s,
                        all_day=%s, location=%s, slurl=%s, region_uuid=%s, organizer_uuid=%s,
                        event_tier=%s, category=%s, status=%s, recurrence_rule=%s, recurrence_until=%s,
                        announce_group_uuid=%s, use_group_chat=%s, use_group_notice=%s,
                        published_at = CASE WHEN %s = 'published' AND published_at IS NULL THEN NOW() ELSE published_at END
                    WHERE id = %s
                    """,
                    (
                        row["title"],
                        row["description"],
                        row["starts_at"],
                        row["ends_at"],
                        row["all_day"],
                        row["location"],
                        row["slurl"],
                        row["region_uuid"],
                        row["organizer_uuid"],
                        row["event_tier"],
                        row["category"],
                        row["status"],
                        row["recurrence_rule"],
                        row["recurrence_until"],
                        row["announce_group_uuid"],
                        row["use_group_chat"],
                        row["use_group_notice"],
                        row["status"],
                        event_id,
                    ),
                )
            conn.commit()
            log_audit_action("Event updated", row["title"], target_uuid=None)
            flash("Event updated.", "success")
            return redirect(url_for("events.detail", event_id=event_id))

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO calendar_events
                    (title, description, starts_at, ends_at, all_day, location, slurl,
                     region_uuid, organizer_uuid, event_tier, category, status,
                     recurrence_rule, recurrence_until, announce_group_uuid,
                     use_group_chat, use_group_notice,
                     created_by_uuid, created_by_name, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s = 'published' THEN NOW() ELSE NULL END)
                """,
                (
                    row["title"],
                    row["description"],
                    row["starts_at"],
                    row["ends_at"],
                    row["all_day"],
                    row["location"],
                    row["slurl"],
                    row["region_uuid"],
                    row["organizer_uuid"],
                    row["event_tier"],
                    row["category"],
                    row["status"],
                    row["recurrence_rule"],
                    row["recurrence_until"],
                    row["announce_group_uuid"],
                    row["use_group_chat"],
                    row["use_group_notice"],
                    session["uuid"],
                    session["name"],
                    row["status"],
                ),
            )
            new_id = cursor.lastrowid
        conn.commit()
        log_audit_action("Event created", row["title"])
        flash("Event created.", "success")
        return redirect(url_for("events.detail", event_id=new_id))

    form = event_form_defaults()
    if event:
        ds, ts = utc_to_local_parts(event["starts_at"])
        de, te = utc_to_local_parts(event.get("ends_at"))
        form = {
            "title": event["title"],
            "description": event.get("description") or "",
            "date_start": ds,
            "time_start": ts if not event.get("all_day") else "",
            "date_end": de,
            "time_end": te if event.get("ends_at") and not event.get("all_day") else "",
            "all_day": event.get("all_day"),
            "location": event.get("location") or "",
            "slurl": event.get("slurl") or "",
            "region_uuid": event.get("region_uuid") or "",
            "event_tier": event.get("event_tier"),
            "category": event.get("category"),
            "announce_group_uuid": event.get("announce_group_uuid") or "",
            "use_group_chat": ""
            if event.get("use_group_chat") is None
            else ("1" if event["use_group_chat"] else "0"),
            "use_group_notice": ""
            if event.get("use_group_notice") is None
            else ("1" if event["use_group_notice"] else "0"),
        }
        merge_recurrence_into_form(
            form,
            rrule_str=event.get("recurrence_rule"),
            starts_at=event["starts_at"],
            recurrence_until=event.get("recurrence_until"),
        )

    return render_template(
        "events/form.html",
        event=event,
        form=form,
        regions=_list_regions(),
        tiers=EVENT_TIERS,
        categories=EVENT_CATEGORIES,
        tier_labels=TIER_LABELS,
        category_labels=CATEGORY_LABELS,
        recurrence_modes=RECURRENCE_MODES,
        weekday_codes=WEEKDAY_CODES,
        weekday_labels=WEEKDAY_LABELS,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/<int:event_id>/cancel", methods=["POST"])
@_calendar_required
@require_active_user
def cancel_event(event_id):
    event = get_event_by_id(event_id)
    if not event or not _can_manage_event_record(event):
        flash("Unauthorized.", "error")
        return redirect(url_for("events.calendar_index"))

    scope = request.form.get("cancel_scope", "series")
    occ_raw = request.form.get("occurrence_start")

    conn = get_pariah_db()
    if scope == "occurrence" and occ_raw and event.get("recurrence_rule"):
        occ = datetime.fromisoformat(occ_raw)
        cancelled = json.loads(event.get("cancelled_occurrences") or "[]")
        cancelled.append(occ.replace(microsecond=0).isoformat())
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE calendar_events SET cancelled_occurrences = %s WHERE id = %s",
                (json.dumps(cancelled), event_id),
            )
        conn.commit()
        notify_followers_cancelled(event, occ)
        broadcast_event_cancelled(event, occ)
        log_audit_action("Event occurrence cancelled", f"{event['title']} @ {occ_raw}")
        flash("Occurrence cancelled.", "success")
    else:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE calendar_events SET status = 'cancelled', cancelled_at = NOW() WHERE id = %s",
                (event_id,),
            )
        conn.commit()
        notify_followers_cancelled(event)
        broadcast_event_cancelled(event)
        log_audit_action("Event series cancelled", event["title"])
        flash("Event cancelled.", "success")

    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.route("/<int:event_id>/delete", methods=["POST"])
@_calendar_required
@rbac_required(PERM_DELETE_EVENTS)
def delete_event(event_id):
    conn = get_pariah_db()
    event = get_event_by_id(event_id)
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM calendar_events WHERE id = %s", (event_id,))
    conn.commit()
    if event:
        log_audit_action("Event deleted", event["title"])
    flash("Event permanently deleted.", "success")
    return redirect(url_for("events.calendar_index"))


@events_bp.route("/subscribe", methods=["GET", "POST"])
@_calendar_required
def subscribe():
    feed_url_ics = feed_url_rss = None
    if request.method == "POST":
        tiers = request.form.getlist("tiers")
        categories = request.form.getlist("categories")
        regions = request.form.getlist("regions")
        token = new_subscription_token()
        conn = get_pariah_db()
        user_uuid = session.get("uuid")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO event_feed_subscriptions
                    (user_uuid, subscription_token, filter_tiers, filter_categories, filter_regions)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user_uuid,
                    token,
                    json.dumps(tiers) if tiers else None,
                    json.dumps(categories) if categories else None,
                    json.dumps(regions) if regions else None,
                ),
            )
        conn.commit()
        base = url_for("events.feed_ics", token=token, _external=True)
        feed_url_ics = base
        feed_url_rss = url_for("events.feed_rss", token=token, _external=True)

    return render_template(
        "events/subscribe.html",
        regions=_list_regions(),
        tiers=EVENT_TIERS,
        categories=EVENT_CATEGORIES,
        tier_labels=TIER_LABELS,
        category_labels=CATEGORY_LABELS,
        feed_url_ics=feed_url_ics,
        feed_url_rss=feed_url_rss,
        back_url=_calendar_back_url(),
    )


@events_bp.route("/my-subscriptions")
@_calendar_required
@require_active_user
def my_subscriptions():
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM event_feed_subscriptions WHERE user_uuid = %s ORDER BY created_at DESC",
            (session["uuid"],),
        )
        subs = cursor.fetchall()
        cursor.execute(
            """
            SELECT f.*, e.title FROM event_follows f
            JOIN calendar_events e ON e.id = f.event_id
            WHERE f.user_uuid = %s ORDER BY f.created_at DESC
            """,
            (session["uuid"],),
        )
        follows = cursor.fetchall()
    return render_template(
        "events/my_subscriptions.html",
        subs=subs,
        follows=follows,
        back_url=_calendar_back_url(),
    )


def _feed_response(format_ics=True):
    token = request.args.get("token")
    token_row = load_subscription_by_token(token) if token else None
    tiers, categories, regions = parse_feed_filters(request.args, token_row)
    if not token_row and not any(
        [
            request.args.get("tier"),
            request.args.get("category"),
            request.args.get("region"),
            token,
        ]
    ):
        tiers = categories = regions = None

    events = fetch_published_events(tiers, categories, regions)
    host = request.url_root.rstrip("/")

    if format_ics:
        body = build_ical_feed(events, host)
        return Response(body, mimetype="text/calendar; charset=utf-8")
    grid_name = get_dynamic_config("grid_name") or "Grid"
    body = build_rss_feed(events, host, grid_name)
    return Response(body, mimetype="application/rss+xml; charset=utf-8")


@events_bp.route("/feed.ics")
@events_bp.route("/<int:event_id>.ics")
def feed_ics(event_id=None):
    if event_id:
        event = get_event_by_id(event_id)
        if not event or event["status"] != "published":
            return Response("Not found", status=404)
        body = build_ical_feed([event], request.url_root.rstrip("/"))
        return Response(body, mimetype="text/calendar; charset=utf-8")
    return _feed_response(format_ics=True)


@events_bp.route("/feed.rss")
def feed_rss():
    return _feed_response(format_ics=False)
