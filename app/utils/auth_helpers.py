from functools import wraps

from flask import flash, redirect, session, url_for

from app.utils import schema as _schema

# Re-export every PERM_* bit so templates can use {{ PERMS.PERM_* }} via the
# context_processor that injects this module as `PERMS` (see app/__init__.py).
for _name in dir(_schema):
    if _name.startswith("PERM_"):
        globals()[_name] = getattr(_schema, _name)

PERM_SUPER_ADMIN = _schema.PERM_SUPER_ADMIN


def get_policy_decline_level():
    """Robust userLevel used when a user declines updated policies (configurable)."""
    from app.utils.db import get_dynamic_config

    raw = get_dynamic_config("policy_decline_user_level")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -4


def is_policy_decline_session():
    """True if the logged-in user's Robust level matches the policy-decline lock tier."""
    try:
        return int(session.get("user_level", 0)) == get_policy_decline_level()
    except (TypeError, ValueError):
        return False


def refresh_session_auth():
    """Re-sync the logged-in session with Robust userLevel and portal RBAC.

    Called from ``before_request`` on every authenticated request (one PK lookup on
    Robust UserAccounts plus one on user_rbac). This is what makes bans (set_user_level),
    role changes (manage_roles) and level changes take effect immediately without
    needing to expire or kill the signed session cookie.

    Returns a redirect Response when the session was invalidated (account removed or
    locked/banned), otherwise ``None``.
    """
    from flask import current_app

    from app.utils.db import get_app_db, get_robust_db

    user_uuid = session.get("uuid")
    if not user_uuid:
        return None

    # --- Robust userLevel (authoritative for bans / policy-decline tier) ---
    level = None
    try:
        robust_conn = get_robust_db()
        with robust_conn.cursor() as cursor:
            cursor.execute(
                "SELECT userLevel FROM UserAccounts WHERE PrincipalID = %s",
                (user_uuid,),
            )
            row = cursor.fetchone()
        if row is None:
            session.clear()
            flash("Your account could not be found. Please log in again.", "error")
            return redirect(url_for("auth.login"))
        level = int(row["userLevel"])
    except Exception as e:
        # Robust unavailable: keep the cached level rather than locking everyone out,
        # but still refresh portal permissions below.
        current_app.logger.error(
            f"Session refresh: Robust userLevel lookup failed: {e}"
        )

    if level is not None:
        if level < 0 and level != get_policy_decline_level():
            session.clear()
            flash("Your account access has been restricted.", "error")
            return redirect(url_for("auth.login"))
        session["user_level"] = level
        session["is_admin"] = level >= 200

    # --- Portal RBAC (mirrors login hydration: level 0 / 200 / negative => no RBAC) ---
    try:
        effective = int(session.get("user_level", 0))
    except (TypeError, ValueError):
        effective = 0

    permissions = 0
    if effective > 0 and effective != 200:
        app_conn = get_app_db()
        with app_conn.cursor() as cursor:
            cursor.execute(
                "SELECT permissions FROM user_rbac WHERE user_uuid = %s",
                (user_uuid,),
            )
            rbac_row = cursor.fetchone()
        if rbac_row:
            permissions = int(rbac_row["permissions"])
    session["permissions"] = permissions
    return None


def require_active_user(f):
    """Bouncer: Ensures the user is logged in AND is not banned/pending."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("uuid"):
            flash("Please log in to access this page.", "error")
            return redirect(url_for("auth.login"))

        lvl = int(session.get("user_level", 0))
        if lvl < 0:
            if is_policy_decline_session():
                flash(
                    "You must agree to the current policies before accessing that area.",
                    "info",
                )
                return redirect(url_for("user.policy_agreement"))
            session.clear()
            flash("Your account access has been restricted.", "error")
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)

    return decorated_function


def has_permission(required_bit):
    """Core Logic: Checks if the current session user has the required permission."""
    user_perms = session.get("permissions", 0)

    # Master Key check: Bit 0 (PERM_SUPER_ADMIN) grants everything
    if user_perms & PERM_SUPER_ADMIN:
        return True

    # Bitwise AND comparison
    return bool(user_perms & required_bit)


def has_any_permissions():
    """True when session RBAC mask is non-zero (any portal permission bits assigned)."""
    try:
        return int(session.get("permissions", 0)) != 0
    except (TypeError, ValueError):
        return False


def rbac_required(permission):
    """Decorator for Flask routes."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("uuid"):
                flash("Please log in.", "error")
                return redirect(url_for("auth.login"))

            if not has_permission(permission):
                flash(
                    "Unauthorized: You lack the required portal permissions.", "error"
                )
                return redirect(url_for("comms.news_feed"))

            return f(*args, **kwargs)

        return decorated_function

    return decorator
