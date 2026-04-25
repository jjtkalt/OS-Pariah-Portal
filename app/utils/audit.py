# app/utils/audit.py
from flask import request, session, current_app
from app.utils.db import get_pariah_db

def log_audit_action(action, details, target_uuid=None):
    """
    Safely logs an administrative action to the database.
    Fails gracefully so it doesn't crash the parent process.
    """
    # Safely grab context even if something weird happens
    try:
        admin_uuid = session.get('uuid', 'SYSTEM')
        admin_name = session.get('name', 'SYSTEM')
        ip_address = request.headers.get('X-Real-IP', request.remote_addr) if request else '127.0.0.1'

        conn = get_pariah_db()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_log (admin_uuid, admin_name, action, target_uuid, details, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (admin_uuid, admin_name, action, target_uuid, details, ip_address))
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"CRITICAL: Failed to write audit log ({action}): {e}")