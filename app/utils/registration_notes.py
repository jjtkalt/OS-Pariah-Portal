# app/utils/registration_notes.py
"""Persist registration application details into staff user notes."""

REGISTRATION_NOTE_ADMIN_UUID = "SYSTEM"


def format_registration_application_note(record):
    """Build a staff note body from a registration / pending_registrations row."""
    lines = ["[REGISTRATION APPLICATION]"]

    created_at = record.get("created_at")
    if created_at:
        lines.append(f"Submitted (UTC): {created_at}")

    inviter = (record.get("inviter") or "").strip()
    lines.append(f"Inviter: {inviter or '(not provided)'}")

    discord = (record.get("discord") or "").strip()
    lines.append(f"Discord: {discord or '(not provided)'}")

    matrix = (record.get("matrix") or "").strip()
    lines.append(f"Matrix: {matrix or '(not provided)'}")

    other_info = (record.get("other_info") or "").strip()
    lines.append("")
    lines.append("Other information:")
    lines.append(other_info if other_info else "(not provided)")

    return "\n".join(lines)


def save_registration_application_note(cursor, user_uuid, record, admin_uuid=None):
    """Insert the registration application into user_notes (same transaction as caller)."""
    admin_uuid = admin_uuid or REGISTRATION_NOTE_ADMIN_UUID
    note = format_registration_application_note(record)
    cursor.execute(
        "INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)",
        (user_uuid, admin_uuid, note),
    )
