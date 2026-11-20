"""Tests for worker retention cleanup (IAR + texture cache)."""

import os
from unittest.mock import MagicMock, call, patch

# --- IAR cleanup ---


@patch("scripts.worker.os.remove")
@patch("scripts.worker.os.path.exists")
@patch("scripts.worker.get_dynamic_config_int")
@patch("scripts.worker.get_dynamic_config")
@patch("scripts.worker.get_app_db")
def test_cleanup_old_iars_removes_expired_keeps_recent(
    mock_get_db,
    mock_get_config,
    mock_get_config_int,
    mock_exists,
    mock_remove,
):
    """Expired completed IARs are deleted; younger ones are left alone by the SQL filter."""
    from scripts.worker import cleanup_old_iars

    mock_get_config_int.return_value = 7
    mock_get_config.return_value = "/fake/iars"
    mock_exists.return_value = True

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_get_db.return_value = conn

    # Query returns only rows older than retention (worker relies on SQL DATE_SUB).
    cursor.fetchall.return_value = [
        {"id": 10, "file_path": "backup_Old_Avatar_20200101.iar"},
        {"id": 11, "file_path": "backup_Also_Old_20200102.iar"},
    ]
    cursor.rowcount = 0

    cleanup_old_iars()

    mock_get_config_int.assert_called_with("iar_retention_days", minimum=1)
    mock_remove.assert_has_calls(
        [
            call("/fake/iars/backup_Old_Avatar_20200101.iar"),
            call("/fake/iars/backup_Also_Old_20200102.iar"),
        ],
        any_order=True,
    )
    delete_calls = [
        c
        for c in cursor.execute.call_args_list
        if c.args and "DELETE FROM iar_backups" in c.args[0]
    ]
    assert len(delete_calls) == 2
    conn.commit.assert_called_once()


@patch("scripts.worker.os.remove")
@patch("scripts.worker.os.path.exists")
@patch("scripts.worker.get_dynamic_config_int")
@patch("scripts.worker.get_dynamic_config")
@patch("scripts.worker.get_app_db")
def test_cleanup_old_iars_noop_when_none_expired(
    mock_get_db,
    mock_get_config,
    mock_get_config_int,
    mock_exists,
    mock_remove,
):
    """When SQL returns no expired rows, no files are removed."""
    from scripts.worker import cleanup_old_iars

    mock_get_config_int.return_value = 7
    mock_get_config.return_value = "/fake/iars"

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_get_db.return_value = conn
    cursor.fetchall.return_value = []
    cursor.rowcount = 0

    cleanup_old_iars()

    mock_remove.assert_not_called()
    mock_exists.assert_not_called()
    assert not any(
        c.args and "DELETE FROM iar_backups" in c.args[0]
        for c in cursor.execute.call_args_list
    )


@patch("scripts.worker.os.remove")
@patch("scripts.worker.os.path.exists")
@patch("scripts.worker.get_dynamic_config_int")
@patch("scripts.worker.get_dynamic_config")
@patch("scripts.worker.get_app_db")
def test_cleanup_old_iars_uses_configured_retention_in_sql(
    mock_get_db,
    mock_get_config,
    mock_get_config_int,
    mock_exists,
    mock_remove,
):
    """Retention days from config are bound into the DATE_SUB query (not a hard-coded value)."""
    from scripts.worker import cleanup_old_iars

    mock_get_config_int.return_value = 3
    mock_get_config.return_value = "/fake/iars"

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_get_db.return_value = conn
    cursor.fetchall.return_value = []
    cursor.rowcount = 0

    cleanup_old_iars()

    select = cursor.execute.call_args_list[0]
    assert "DATE_SUB(NOW(), INTERVAL %s DAY)" in select.args[0]
    assert select.args[1] == (3,)


@patch("scripts.worker.get_app_db")
def test_get_dynamic_config_prefers_schema_over_call_default(mock_get_db):
    """DB miss must resolve from KNOWN_SETTINGS, not a misleading call-site default."""
    from scripts import worker as worker_mod

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    mock_get_db.return_value = conn
    cursor.fetchone.return_value = None  # no DB override

    # Schema default for iar_retention_days is "7"; a misleading call-site 30 must lose.
    raw = worker_mod.get_dynamic_config("iar_retention_days", 30)
    assert str(raw) == "7"
    assert worker_mod.get_dynamic_config_int("iar_retention_days", default=30) == 7


# --- Texture cache (age keep/clear) ---


@patch("scripts.worker.os.listdir")
@patch("scripts.worker.os.path.getmtime")
@patch("scripts.worker.os.remove")
@patch("scripts.worker.os.path.exists")
@patch("scripts.worker.get_dynamic_config_int")
@patch("scripts.worker.get_dynamic_config")
def test_clean_texture_cache_respects_age_boundary(
    mock_get_config,
    mock_get_config_int,
    mock_exists,
    mock_remove,
    mock_getmtime,
    mock_listdir,
):
    """Files older than retention are removed; younger JPGs and non-JPGs are kept."""
    from scripts.worker import clean_texture_cache

    mock_get_config.side_effect = lambda key, default=None: (
        "/fake/cache" if key == "texture_cache_path" else default
    )
    mock_get_config_int.return_value = 30
    mock_exists.return_value = True
    mock_listdir.return_value = [
        "expired.jpg",
        "fresh.jpg",
        "notes.txt",
    ]

    now = 1_700_000_000.0

    def fake_mtime(path):
        if path.endswith("expired.jpg"):
            return now - (40 * 86400)
        return now - (10 * 86400)

    mock_getmtime.side_effect = fake_mtime

    with patch("scripts.worker.time.time", return_value=now):
        clean_texture_cache()

    mock_remove.assert_called_once_with(os.path.join("/fake/cache", "expired.jpg"))
