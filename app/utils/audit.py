# app/utils/audit.py
import contextlib

from flask import current_app, session

import app as main_app


def log_audit_action(action, details, target_uuid=None):
    """
    Safely logs an administrative action to the database.

    Uses a dedicated pool connection so audit commits cannot end the caller's
    request transaction early (partial bans / mid-flow commits).
    Fails gracefully so it doesn't crash the parent process.
    """
    conn = None
    try:
        admin_uuid = session.get("uuid", "SYSTEM")
        admin_name = session.get("name", "SYSTEM")
        if main_app.app_pool is None:
            raise RuntimeError("app_pool is not initialized")
        conn = main_app.app_pool.connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_log (admin_uuid, admin_name, action, target_uuid, details)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (admin_uuid, admin_name, action, target_uuid, details),
            )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"CRITICAL: Failed to write audit log ({action}): {e}")
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.rollback()
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
