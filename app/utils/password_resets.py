import secrets
import time


def purge_expired_password_reset_tokens(conn, now_ts: int | None = None) -> int:
    """
    Deletes expired password reset tokens.

    Returns the number of rows deleted (best-effort; depends on connector).
    """
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM password_resets WHERE expires_at <= %s", (now_ts,))
        return getattr(cursor, "rowcount", 0) or 0


def create_password_reset_token(
    conn,
    user_uuid: str,
    *,
    ttl_seconds: int = 3600,
    now_ts: int | None = None,
    delete_existing_for_user: bool = True,
    purge_expired: bool = True,
) -> tuple[str, int]:
    """
    Creates a new password reset token for a user.

    Policy:
    - Optionally purge expired tokens first
    - Optionally delete any existing tokens for this user (ensures 1 active token/user)
    - Insert a fresh token row
    """
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    expires_at = now_ts + int(ttl_seconds)

    if purge_expired:
        purge_expired_password_reset_tokens(conn, now_ts=now_ts)

    with conn.cursor() as cursor:
        if delete_existing_for_user:
            cursor.execute("DELETE FROM password_resets WHERE user_uuid = %s", (user_uuid,))

        token = secrets.token_urlsafe(32)
        cursor.execute(
            "INSERT INTO password_resets (token, user_uuid, expires_at) VALUES (%s, %s, %s)",
            (token, user_uuid, expires_at),
        )

    conn.commit()
    return token, expires_at

