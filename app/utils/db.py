from flask import current_app, g

import app as main_app


def get_robust_db():
    if "robust_conn" not in g:
        try:
            g.robust_conn = main_app.robust_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get Robust DB connection: {e}")
            raise
    return g.robust_conn


def get_app_db():
    if "app_conn" not in g:
        try:
            g.app_conn = main_app.app_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get OS-Pariah DB connection: {e}")
            raise
    return g.app_conn


def get_dynamic_config(key, default=None):
    from app.utils.schema import KNOWN_SETTINGS

    # --- META-VARIABLE INTERCEPTS ---
    # These keys don't exist in the DB or Schema directly; they are built on the fly!
    if key == "portal_url":
        # Result: https://portal.example.com
        return f"https://{get_dynamic_config('portal_subdomain')}.{get_dynamic_config('grid_domain')}"

    elif key == "public_robust_url":
        # Result: http://robust.example.com:8002
        return f"{get_dynamic_config('robust_protocol')}://{get_dynamic_config('robust_subdomain')}.{get_dynamic_config('grid_domain')}:{get_dynamic_config('robust_public_port')}"

    elif key == "private_robust_url":
        # Result: http://robust.example.com:8003
        return f"{get_dynamic_config('robust_protocol')}://{get_dynamic_config('robust_subdomain')}.{get_dynamic_config('grid_domain')}:{get_dynamic_config('robust_private_port')}"
    # --------------------------------

    # Authority order: DB override → KNOWN_SETTINGS schema default → call-site default.
    conn = get_app_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
        result = cursor.fetchone()
        if result:
            return result["config_value"]

    for _category, fields in KNOWN_SETTINGS.items():
        if key in fields:
            return fields[key].get("default", default)

    if default is not None:
        return default

    return ""
