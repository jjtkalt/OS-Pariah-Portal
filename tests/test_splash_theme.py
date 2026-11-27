from datetime import datetime
from unittest.mock import patch

from app.utils.schema import KNOWN_SETTINGS


def _config(overrides):
    """get_dynamic_config stand-in: overrides first, then the schema defaults."""

    def fake(key, *args, **kwargs):
        if key in overrides:
            return overrides[key]
        for group in KNOWN_SETTINGS.values():
            if key in group:
                return group[key]["default"]
        return None

    return fake


NEWS = [
    {
        "id": 1,
        "title": "Maintenance tonight",
        "body": "Grid restarts at midnight.",
        "author_name": "Staff",
        "created_at": datetime(2026, 11, 25, 12, 0),
        "is_alert": 1,
    },
    {
        "id": 2,
        "title": "New region",
        "body": "Welcome to the new region.",
        "author_name": "Staff",
        "created_at": datetime(2026, 11, 24, 12, 0),
        "is_alert": 0,
    },
]


def _get_splash(client, db_cursor, overrides=None):
    db_cursor.fetchall.return_value = NEWS
    with (
        patch("app.blueprints.comms.routes.fetch_all_online_users", return_value=[]),
        patch("app.blueprints.comms.routes.get_total_regions_count", return_value=7),
        patch("app.utils.db.get_dynamic_config", side_effect=_config(overrides or {})),
    ):
        return client.get("/comms/splash")


def test_splash_uses_configured_theme_assets(client, db_cursor):
    response = _get_splash(
        client,
        db_cursor,
        {
            "custom_css_path": "/static/css/my-theme.css",
            "portal_background_image": "/static/images/my-bg.png",
            "portal_favicon": "/static/images/my.ico",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/static/css/my-theme.css"' in html
    assert "/static/images/my-bg.png" in html
    assert "--portal-background-image" in html
    assert 'href="/static/images/my.ico"' in html


def test_splash_defaults_to_base_css_via_setting(client, db_cursor):
    html = _get_splash(client, db_cursor).get_data(as_text=True)

    assert 'href="/static/css/base.css"' in html
    assert "/static/images/background.png" in html


def test_splash_has_no_inline_theme_overrides_and_stays_standalone(client, db_cursor):
    html = _get_splash(client, db_cursor).get_data(as_text=True)

    # Theme classes instead of inline styles / hard-coded colors.
    assert 'class="main splash-screen"' in html
    assert "group--danger" in html
    assert "group--accent" in html
    assert "border-left:" not in html
    assert "border-bottom: 1px solid" not in html
    # Viewer page stays lightweight: no nav bar, Turnstile, or CSRF script.
    assert "nav-bar" not in html
    assert "challenges.cloudflare.com" not in html
    assert "csrf-token" not in html
