"""Session freshness: permissions / userLevel are re-read from the DBs on each request."""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.schema import PERM_MANAGE_SETTINGS, PERM_SUPER_ADMIN


@pytest.fixture
def refresh_app(app):
    """Opt in to the before_request session refresh (skipped under TESTING by default)."""
    app.config["REFRESH_SESSION_AUTH"] = True
    return app


def _robust_returning(row):
    robust_cursor = MagicMock()
    robust_cursor.fetchone.return_value = row
    robust_conn = MagicMock()
    robust_conn.cursor.return_value.__enter__.return_value = robust_cursor
    return robust_conn


def _rbac_db(db_cursor, permissions):
    """Make user_rbac lookups return *permissions*; everything else returns None."""

    def fetchone():
        last_sql = (
            db_cursor.execute.call_args[0][0] if db_cursor.execute.call_args else ""
        )
        if "FROM user_rbac" in last_sql:
            return {"permissions": permissions} if permissions is not None else None
        return None

    db_cursor.fetchone.side_effect = fetchone


def test_session_permissions_overwritten_from_db(refresh_app, client, db_cursor):
    """A stale cookie claiming Super Admin is downgraded to whatever user_rbac says."""
    _rbac_db(db_cursor, PERM_MANAGE_SETTINGS)

    with client.session_transaction() as sess:
        sess["uuid"] = "staff-uuid"
        sess["user_level"] = 250
        sess["permissions"] = PERM_SUPER_ADMIN

    with patch(
        "app.utils.db.get_robust_db", return_value=_robust_returning({"userLevel": 250})
    ):
        client.get("/admin/settings")

    with client.session_transaction() as sess:
        assert sess["permissions"] == PERM_MANAGE_SETTINGS
        assert sess["user_level"] == 250


def test_revoked_roles_lock_out_protected_route(refresh_app, client, db_cursor):
    """Removing a user's RBAC row takes effect on their very next request."""
    _rbac_db(db_cursor, None)

    with client.session_transaction() as sess:
        sess["uuid"] = "staff-uuid"
        sess["user_level"] = 250
        sess["permissions"] = PERM_MANAGE_SETTINGS

    with patch(
        "app.utils.db.get_robust_db", return_value=_robust_returning({"userLevel": 250})
    ):
        response = client.get("/admin/settings")

    assert response.status_code == 302
    assert "/admin/settings" not in response.headers["Location"]
    with client.session_transaction() as sess:
        assert sess["permissions"] == 0


def test_banned_user_session_is_cleared(refresh_app, client, db_cursor):
    """A negative Robust userLevel (ban) invalidates the session and redirects to login."""
    db_cursor.fetchone.return_value = (
        None  # policy_decline_user_level -> schema default
    )

    with client.session_transaction() as sess:
        sess["uuid"] = "banned-uuid"
        sess["user_level"] = 250
        sess["permissions"] = PERM_SUPER_ADMIN

    with patch(
        "app.utils.db.get_robust_db", return_value=_robust_returning({"userLevel": -1})
    ):
        response = client.get("/admin/settings")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    with client.session_transaction() as sess:
        assert "uuid" not in sess
        assert "permissions" not in sess


def test_refresh_skipped_for_static_and_login(refresh_app, client):
    """Static assets and the login endpoint never trigger the refresh queries."""
    with client.session_transaction() as sess:
        sess["uuid"] = "someone"
        sess["permissions"] = PERM_SUPER_ADMIN

    with patch("app.utils.db.get_robust_db") as mock_robust:
        client.get("/auth/login")
        client.get("/static/css/base.css")

    mock_robust.assert_not_called()


def test_security_headers_present(client):
    from urllib.parse import urlparse

    import app as main_app

    response = client.get("/manual.html")
    csp = response.headers["Content-Security-Policy"]
    # Exact policy from the app factory (avoids incomplete URL substring checks).
    assert csp == main_app.CONTENT_SECURITY_POLICY
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp

    # Parse CSP source tokens and verify Turnstile host via urlparse, not substring.
    turnstile_hosts = set()
    for directive in csp.split(";"):
        parts = directive.strip().split()
        if not parts:
            continue
        for source in parts[1:]:
            if source.startswith("https://"):
                turnstile_hosts.add(urlparse(source).hostname)
    assert "challenges.cloudflare.com" in turnstile_hosts

    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_upload_folder_outside_static(app):
    folder = app.config["UPLOAD_FOLDER"]
    assert folder.endswith("uploads/tickets")
    assert "static" not in folder.split("/")
