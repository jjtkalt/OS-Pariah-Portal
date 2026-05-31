"""Calendar event email and bot notifications (not portal news/notices)."""

import json
from flask import current_app, url_for

from app.utils.db import get_pariah_db, get_dynamic_config, get_robust_db
from app.utils.grid_bot import enqueue_bot_message, enqueue_event_announcements
from app.utils.events import format_pacific
from app.utils.notifications import send_matrix_discord_webhook


def _user_email(user_uuid):
    try:
        conn = get_robust_db()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT Email FROM useraccounts WHERE PrincipalID = %s",
                (user_uuid,),
            )
            row = cursor.fetchone()
            return (row['Email'] or '').strip() if row else ''
    except Exception as e:
        current_app.logger.error(f"Failed to fetch email for {user_uuid}: {e}")
        return ''


def send_event_email(user_uuid, subject, body):
    import smtplib
    from email.message import EmailMessage

    to_email = _user_email(user_uuid)
    if not to_email:
        return False
    grid_name = get_dynamic_config('grid_name')
    smtp_server = get_dynamic_config('smtp_server')
    smtp_port = int(get_dynamic_config('smtp_port') or 587)
    smtp_user = get_dynamic_config('smtp_user')
    smtp_pass = get_dynamic_config('smtp_pass')
    smtp_from = get_dynamic_config('smtp_from')
    if not smtp_server:
        current_app.logger.warning(f"SMTP not configured; event email to {to_email}: {subject}")
        return False
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = smtp_from
    msg['To'] = to_email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Event email failed for {to_email}: {e}")
        return False


def notify_suggestion_staff(title, submitter_name, suggestion_id):
    send_matrix_discord_webhook(
        title='📅 New Event Suggestion',
        message=f"**{title}** submitted by **{submitter_name}** (ID #{suggestion_id})",
        color=15844367,
    )


def notify_submitter_decision(submitter_uuid, approved, title, staff_notes=None):
    grid_name = get_dynamic_config('grid_name')
    if approved:
        subject = f'Your event suggestion was approved — {grid_name}'
        body = f"Good news! Your event \"{title}\" has been approved and published on the grid calendar.\n\n- {grid_name}"
        im = f"Your event \"{title}\" was approved and is now on the calendar."
    else:
        subject = f'Your event suggestion was not approved — {grid_name}'
        body = f"Your event suggestion \"{title}\" was not approved."
        if staff_notes:
            body += f"\n\nStaff note: {staff_notes}"
        body += f"\n\n- {grid_name}"
        im = f"Your event suggestion \"{title}\" was not approved."
        if staff_notes:
            im += f" Note: {staff_notes[:200]}"

    send_event_email(submitter_uuid, subject, body)
    enqueue_bot_message(
        'calendar', 'event_reminder_im', im,
        target_uuid=submitter_uuid, delivery_channel='im', priority='normal',
    )


def broadcast_event_cancelled(event, occurrence_start=None):
    """Grid-wide / region bot announcement for cancellation."""
    title = event['title']
    when = format_pacific(occurrence_start or event['starts_at'], event.get('all_day'))
    if occurrence_start and event.get('recurrence_rule'):
        msg = f"CANCELLED: \"{title}\" on {when} has been cancelled."
    else:
        msg = f"CANCELLED: \"{title}\" ({when}) has been cancelled."

    enqueue_event_announcements(
        'calendar', 'event_cancelled', msg, event, priority='high',
    )


def notify_followers_cancelled(event, occurrence_start=None):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT user_uuid, notify_email, notify_inworld FROM event_follows WHERE event_id = %s",
            (event['id'],),
        )
        followers = cursor.fetchall()

    when = format_pacific(occurrence_start or event['starts_at'], event.get('all_day'))
    title = event['title']
    for f in followers:
        if f.get('notify_email'):
            send_event_email(
                f['user_uuid'],
                f'Event cancelled: {title}',
                f"The event \"{title}\" scheduled for {when} has been cancelled.\n",
            )
        if f.get('notify_inworld'):
            enqueue_bot_message(
                'calendar', 'event_cancel_im',
                f"Event cancelled: \"{title}\" on {when}.",
                target_uuid=f['user_uuid'],
                delivery_channel='im',
                priority='high',
                metadata={'event_id': event['id']},
            )


def log_notification_sent(event_id, user_uuid, occurrence_start, notification_type):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        try:
            cursor.execute(
                """
                INSERT INTO event_notification_log
                    (event_id, user_uuid, occurrence_start, notification_type)
                VALUES (%s, %s, %s, %s)
                """,
                (event_id, user_uuid, occurrence_start, notification_type),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False


def notification_already_sent(event_id, user_uuid, occurrence_start, notification_type):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM event_notification_log
            WHERE event_id = %s AND user_uuid <=> %s
              AND occurrence_start = %s AND notification_type = %s
            LIMIT 1
            """,
            (event_id, user_uuid, occurrence_start, notification_type),
        )
        return cursor.fetchone() is not None
