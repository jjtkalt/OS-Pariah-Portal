"""Grid Service Bot message queue."""

import json

from flask import current_app, request

from app.utils.db import get_dynamic_config, get_pariah_db

MAX_WRONG_REGION_RETRIES = 20


def get_grid_bot_uuid():
    return (get_dynamic_config("grid_bot_uuid") or "").strip()


def is_grid_bot_uuid(uuid):
    bot = get_grid_bot_uuid()
    return bool(bot and uuid and str(uuid).strip() == bot)


def enqueue_bot_message(
    source,
    message_type,
    message_body,
    target_uuid=None,
    target_region_uuid=None,
    target_group_uuid=None,
    delivery_channel="region",
    notice_subject=None,
    metadata=None,
    priority="normal",
):
    """Insert a pending message for the in-world bot to deliver."""
    body = (message_body or "").strip()
    if not body:
        return None
    meta_json = json.dumps(metadata) if metadata is not None else None
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bot_message_queue
                (source, message_type, delivery_channel, target_uuid, target_region_uuid,
                 target_group_uuid, message_body, notice_subject, priority, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source,
                message_type,
                delivery_channel,
                target_uuid,
                target_region_uuid,
                target_group_uuid,
                body[:4000],
                (notice_subject or "")[:255] or None,
                priority,
                meta_json,
            ),
        )
        row_id = cursor.lastrowid
    conn.commit()
    return row_id


def event_group_settings(event):
    """Resolve group chat/notice flags and group UUID for an event."""
    default_chat = (
        str(get_dynamic_config("calendar_default_use_group_chat", "false")).lower()
        == "true"
    )
    default_notice = (
        str(get_dynamic_config("calendar_default_use_group_notice", "false")).lower()
        == "true"
    )
    ugc = event.get("use_group_chat")
    ugn = event.get("use_group_notice")
    use_chat = default_chat if ugc is None else bool(ugc)
    use_notice = default_notice if ugn is None else bool(ugn)
    group = (
        event.get("announce_group_uuid")
        or get_dynamic_config("grid_bot_announce_group_uuid")
        or ""
    ).strip()
    return use_chat, use_notice, group or None


def enqueue_event_announcements(
    source, message_type, body, event, priority="normal", subject=None
):
    """Fan out region chat, group chat, and group notice deliveries for calendar events."""
    subject = (subject or event.get("title") or "Grid Event")[:255]
    region = event.get("region_uuid") or (
        get_dynamic_config("grid_bot_announce_region_uuid") or None
    )
    meta = {"event_id": event.get("id")}

    enqueue_bot_message(
        source,
        message_type,
        body,
        target_region_uuid=region,
        delivery_channel="region",
        metadata=meta,
        priority=priority,
    )

    use_chat, use_notice, group = event_group_settings(event)
    if group and use_chat:
        enqueue_bot_message(
            source,
            message_type,
            body,
            target_group_uuid=group,
            delivery_channel="group_chat",
            metadata=meta,
            priority=priority,
        )
    if group and use_notice:
        enqueue_bot_message(
            source,
            message_type,
            body,
            target_group_uuid=group,
            delivery_channel="group_notice",
            notice_subject=subject,
            metadata=meta,
            priority=priority,
        )


def claim_pending_messages(limit=20):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, source, message_type, delivery_channel, target_uuid,
                   target_region_uuid, target_group_uuid, message_body, notice_subject,
                   priority, metadata, retry_count
            FROM bot_message_queue
            WHERE status = 'pending'
            ORDER BY FIELD(priority, 'high', 'normal'), created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    for row in rows:
        if row.get("metadata") and isinstance(row["metadata"], str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except json.JSONDecodeError:
                row["metadata"] = {}
        row.setdefault("delivery_channel", "region")
    return rows


def mark_message_claimed(message_id):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE bot_message_queue
            SET status = 'claimed', claimed_at = NOW()
            WHERE id = %s AND status = 'pending'
            """,
            (message_id,),
        )
        ok = cursor.rowcount > 0
    conn.commit()
    return ok


def ack_message(message_id, success=True, error=None):
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        if success:
            cursor.execute(
                """
                UPDATE bot_message_queue
                SET status = 'delivered', delivered_at = NOW(), last_error = NULL
                WHERE id = %s
                """,
                (message_id,),
            )
        elif error == "wrong_region":
            cursor.execute(
                """
                UPDATE bot_message_queue
                SET status = IF(retry_count + 1 >= %s, 'failed', 'pending'),
                    claimed_at = NULL,
                    retry_count = retry_count + 1,
                    last_error = %s
                WHERE id = %s
                """,
                (MAX_WRONG_REGION_RETRIES, error[:512], message_id),
            )
        else:
            cursor.execute(
                """
                UPDATE bot_message_queue
                SET status = 'failed', retry_count = retry_count + 1,
                    last_error = %s
                WHERE id = %s
                """,
                ((error or "unknown")[:512], message_id),
            )
    conn.commit()


def retry_failed_messages(message_ids=None):
    """Admin: reset failed (or selected) messages to pending."""
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        if message_ids:
            placeholders = ",".join(["%s"] * len(message_ids))
            cursor.execute(
                f"""
                UPDATE bot_message_queue
                SET status = 'pending', claimed_at = NULL, last_error = NULL
                WHERE id IN ({placeholders}) AND status IN ('failed', 'claimed')
                """,
                list(message_ids),
            )
        else:
            cursor.execute(
                """
                UPDATE bot_message_queue
                SET status = 'pending', claimed_at = NULL, last_error = NULL
                WHERE status = 'failed'
                """
            )
    conn.commit()
    return cursor.rowcount


def get_queue_stats():
    conn = get_pariah_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT status, COUNT(*) AS c FROM bot_message_queue GROUP BY status"
        )
        stats = {row["status"]: row["c"] for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT id, source, message_type, delivery_channel, status, priority,
                   message_body, notice_subject, retry_count, last_error,
                   created_at, claimed_at, delivered_at
            FROM bot_message_queue
            ORDER BY id DESC LIMIT 100
            """
        )
        recent = cursor.fetchall()
    return stats, recent


def format_message_text_line(msg):
    """LSL-friendly pipe-delimited line (8 fields)."""
    body = (msg.get("message_body") or "").replace("|", "/").replace("\n", " ")
    subject = (msg.get("notice_subject") or "").replace("|", "/").replace("\n", " ")
    return "|".join(
        [
            str(msg["id"]),
            msg.get("message_type") or "",
            msg.get("target_uuid") or "",
            msg.get("target_region_name") or "",
            msg.get("target_group_uuid") or "",
            msg.get("delivery_channel") or "region",
            subject,
            body,
        ]
    )


def verify_bot_api_request():
    token = (get_dynamic_config("grid_bot_api_token") or "").strip()
    if not token:
        current_app.logger.warning("Grid bot API token not configured")
        return False
    supplied = (
        request.headers.get("X-Grid-Bot-Token") or request.args.get("token") or ""
    ).strip()
    return bool(supplied and supplied == token)


def enrich_bot_messages(messages):
    if not messages:
        return messages
    region_uuids = {
        m["target_region_uuid"] for m in messages if m.get("target_region_uuid")
    }
    names = {}
    if region_uuids:
        conn = get_pariah_db()
        placeholders = ",".join(["%s"] * len(region_uuids))
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT region_uuid, region_name FROM region_configs WHERE region_uuid IN ({placeholders})",
                list(region_uuids),
            )
            for row in cursor.fetchall():
                names[row["region_uuid"]] = row["region_name"]
    for msg in messages:
        ru = msg.get("target_region_uuid")
        msg["target_region_name"] = names.get(ru, "") if ru else ""
    return messages
