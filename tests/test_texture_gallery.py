import os
import time
from unittest.mock import MagicMock, call, patch

from app.utils.schema import PERM_VIEW_ASSETS
from app.utils.texture_gallery import (
    fetch_textures_from_snapshot,
    fetch_textures_inverted,
    normalize_owner_names,
    replace_texture_gallery_snapshot,
    snapshot_count,
)

# --- 1. TEST THE CACHE CLEANUP ROUTINE ---


@patch("scripts.worker.os.listdir")
@patch("scripts.worker.os.path.getmtime")
@patch("scripts.worker.os.remove")
@patch("scripts.worker.os.path.exists")
@patch("scripts.worker.get_dynamic_config")
def test_clean_texture_cache(
    mock_get_config, mock_exists, mock_remove, mock_getmtime, mock_listdir
):
    """Test that the cleanup routine correctly identifies and deletes old files."""
    from scripts.worker import clean_texture_cache

    def fake_get_config(key, default=None):
        if key == "texture_cache_path":
            return "/fake/cache/dir"
        if key == "texture_cache_retention_days":
            return "30"
        return default

    mock_get_config.side_effect = fake_get_config
    mock_exists.return_value = True
    # Provide two fake files in the directory
    mock_listdir.return_value = [
        "old_texture.jpg",
        "new_texture.jpg",
        "not_an_image.txt",
    ]

    current_time = time.time()

    # old_texture.jpg is 40 days old, new_texture.jpg is 10 days old
    def fake_getmtime(filepath):
        if "old_texture" in filepath:
            return current_time - (40 * 86400)
        return current_time - (10 * 86400)

    mock_getmtime.side_effect = fake_getmtime

    # Run cleanup
    clean_texture_cache()

    # Assertions
    mock_remove.assert_called_once_with(
        os.path.join("/fake/cache/dir", "old_texture.jpg")
    )


# --- 2. GALLERY LISTING HELPERS ---


def test_normalize_owner_names_fills_missing():
    rows = [{"owner_name": None}, {"owner_name": "Ada Lovelace"}]
    out = normalize_owner_names(rows)
    assert out[0]["owner_name"] == "System / Orphaned / HG"
    assert out[1]["owner_name"] == "Ada Lovelace"


def test_fetch_textures_inverted_global_uses_candidate_subquery():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = [
        {
            "id": "asset-1",
            "hash": "abc",
            "name": "Tex",
            "create_time": 100,
            "owner_uuid": "u1",
            "owner_name": "Owner",
        }
    ]

    rows = fetch_textures_inverted(conn, limit=48, offset=0)
    assert len(rows) == 1
    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "FROM (" in sql
    assert "FROM fsassets" in sql
    assert "ORDER BY create_time DESC" in sql
    assert "LIMIT %s" in sql
    # candidate limit, baked, mesh, page limit, offset
    assert params[0] >= 200
    assert params[-2:] == (48, 0)


def test_fetch_textures_inverted_owner_filters_avatar():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = []

    fetch_textures_inverted(conn, limit=48, offset=96, owner_uuid="user-uuid")
    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "i.avatarID = %s" in sql
    assert params[0] == "user-uuid"
    assert params[-2:] == (48, 96)


def test_snapshot_round_trip_helpers():
    count_conn = MagicMock()
    count_cursor = MagicMock()
    count_conn.cursor.return_value.__enter__.return_value = count_cursor
    count_cursor.fetchone.return_value = {"c": 2}
    assert snapshot_count(count_conn) == 2

    fetch_conn = MagicMock()
    fetch_cursor = MagicMock()
    fetch_conn.cursor.return_value.__enter__.return_value = fetch_cursor
    fetch_cursor.fetchall.return_value = [
        {
            "id": "a1",
            "hash": "h1",
            "name": "N",
            "create_time": 1,
            "owner_uuid": "u",
            "owner_name": None,
        }
    ]
    rows = fetch_textures_from_snapshot(fetch_conn, limit=48, offset=0)
    assert rows[0]["owner_name"] == "System / Orphaned / HG"

    write_conn = MagicMock()
    write_cursor = MagicMock()
    write_conn.cursor.return_value.__enter__.return_value = write_cursor
    replace_texture_gallery_snapshot(
        write_conn,
        [
            {
                "hash": "h1",
                "id": "a1",
                "name": "N",
                "create_time": 1,
                "owner_uuid": "u",
                "owner_name": "Name",
            }
        ],
    )
    assert write_cursor.execute.call_args_list[0] == call(
        "DELETE FROM texture_gallery_snapshot"
    )
    assert write_cursor.executemany.called
    write_conn.commit.assert_called()


# --- 3. TEST THE GALLERY ROUTE ---


def test_texture_gallery_uses_snapshot_when_populated(client):
    """Global gallery reads Pariah snapshot when rows exist."""
    snap_rows = [
        {
            "id": "123",
            "hash": "abcdef",
            "name": "Test Texture",
            "create_time": 1600000000,
            "owner_uuid": "user-uuid",
            "owner_name": "Test Avatar",
        }
    ]

    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_VIEW_ASSETS

    with (
        patch("app.blueprints.admin.routes.snapshot_count", return_value=1),
        patch(
            "app.blueprints.admin.routes.fetch_textures_from_snapshot",
            return_value=snap_rows,
        ) as mock_fetch,
        patch("app.blueprints.admin.routes.fetch_textures_inverted") as mock_inverted,
        patch("app.blueprints.admin.routes.get_pariah_db", return_value=MagicMock()),
    ):
        response = client.get("/admin/gallery")

    assert response.status_code == 200
    assert b"Texture Gallery" in response.data
    assert b"Test Texture" in response.data
    assert b"abcdef" in response.data
    assert b"Test Avatar" in response.data
    mock_fetch.assert_called_once()
    mock_inverted.assert_not_called()


def test_texture_gallery_uuid_uses_inverted_robust(client):
    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_VIEW_ASSETS

    with patch(
        "app.blueprints.admin.routes.fetch_textures_inverted",
        return_value=[
            {
                "id": "123",
                "hash": "aabbcc",
                "name": "User Tex",
                "create_time": 1600000000,
                "owner_uuid": "target-uuid",
                "owner_name": "Target User",
            }
        ],
    ) as mock_inverted:
        response = client.get("/admin/gallery?uuid=target-uuid")

    assert response.status_code == 200
    assert b"User Tex" in response.data
    mock_inverted.assert_called_once()
    assert mock_inverted.call_args.kwargs["owner_uuid"] == "target-uuid"


def test_fetch_textures_for_snapshot_uses_time_window():
    from app.utils.texture_gallery import fetch_textures_for_snapshot

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = []

    fetch_textures_for_snapshot(conn, since_unix=1_700_000_000, max_rows=50000)
    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "f.create_time >= %s" in sql
    assert "FROM fsassets f" in sql
    assert "FROM (" not in sql
    assert params[-2:] == (1_700_000_000, 50000)


@patch("scripts.worker.get_pariah_db")
@patch("scripts.worker.get_robust_db")
@patch("scripts.worker.get_dynamic_config")
@patch("scripts.worker.time.time", return_value=1_720_000_000)
def test_refresh_texture_gallery_snapshot(
    _mock_time, mock_get_config, mock_get_robust, mock_get_pariah
):
    from scripts.worker import refresh_texture_gallery_snapshot

    def fake_config(key, default=None):
        if key == "texture_gallery_snapshot_days":
            return "14"
        if key == "texture_gallery_snapshot_limit":
            return "50000"
        return default

    mock_get_config.side_effect = fake_config
    robust = MagicMock()
    pariah = MagicMock()
    mock_get_robust.return_value = robust
    mock_get_pariah.return_value = pariah

    with (
        patch(
            "app.utils.texture_gallery.fetch_textures_for_snapshot",
            return_value=[{"hash": "h", "id": "i", "name": "n", "create_time": 1}],
        ) as mock_fetch,
        patch(
            "app.utils.texture_gallery.replace_texture_gallery_snapshot",
            return_value=1,
        ) as mock_replace,
    ):
        refresh_texture_gallery_snapshot()

    mock_fetch.assert_called_once_with(
        robust, since_unix=1_720_000_000 - (14 * 86400), max_rows=50000
    )
    mock_replace.assert_called_once()
    robust.close.assert_called_once()
    pariah.close.assert_called_once()


# --- 4. TEST THE OPENCV SMART PROXY ---


@patch("app.blueprints.admin.routes.os.makedirs")
@patch("app.blueprints.admin.routes.os.access")
@patch("app.blueprints.admin.routes.os.path.exists")
@patch("app.blueprints.admin.routes.get_dynamic_config")
@patch("app.blueprints.admin.routes.send_from_directory")
def test_serve_texture_cached(
    mock_send_dir, mock_get_config, mock_exists, mock_access, mock_makedirs, client
):
    """Test that an already cached texture skips OpenCV and serves directly."""

    def fake_config(key):
        if key == "texture_cache_path":
            return "/fake/dir"
        if key == "fsassets_path":
            return "/fake/fsassets"
        return None

    mock_get_config.side_effect = fake_config

    # Force the OS to pretend the cache directory is perfectly writable
    mock_access.return_value = True

    # Force os.path.exists to return True, implying the file is already converted and cached
    mock_exists.return_value = True
    mock_send_dir.return_value = "Fake Image Data"

    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_VIEW_ASSETS

    response = client.get("/admin/texture/1a2b3c4d5e")

    assert response.status_code == 200
    mock_send_dir.assert_called_once_with("/fake/dir", "1a2b3c4d5e.jpg")


@patch("app.blueprints.admin.routes.cv2")
@patch("app.blueprints.admin.routes.gzip.open")
@patch("app.blueprints.admin.routes.os.makedirs")
@patch("app.blueprints.admin.routes.os.access")
@patch("app.blueprints.admin.routes.os.path.exists")
@patch("app.blueprints.admin.routes.get_dynamic_config")
@patch("app.blueprints.admin.routes.send_from_directory")
def test_serve_texture_unzipped_and_converted(
    mock_send_dir,
    mock_get_config,
    mock_exists,
    mock_access,
    mock_makedirs,
    mock_gzip,
    mock_cv2,
    client,
):
    """Test that a new texture is unzipped, decoded by OpenCV, and cached."""

    def fake_config(key):
        if key == "texture_cache_path":
            return "/fake/cache"
        if key == "fsassets_path":
            return "/fake/fsassets"
        return None

    mock_get_config.side_effect = fake_config

    # The cache dir exists, the cached file does NOT exist, the raw FSAsset GZ file DOES exist
    def fake_exists(path):
        return not ("cache" in path and path.endswith(".jpg"))

    mock_exists.side_effect = fake_exists

    mock_access.return_value = True  # We have write permission

    # Mock GZIP returning fake bytes
    mock_file = MagicMock()
    mock_file.read.return_value = b"fake_j2c_bytes"
    mock_gzip.return_value.__enter__.return_value = mock_file

    # Mock OpenCV decoding successfully
    mock_cv2.imdecode.return_value = "Decoded_Matrix"
    mock_cv2.imencode.return_value = (
        True,
        b"fake_buffer",
    )  # Just in case it hits fallback

    mock_send_dir.return_value = "Fake Served Image"

    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_VIEW_ASSETS

    response = client.get("/admin/texture/1a2b3c4d5e")

    assert response.status_code == 200
    mock_cv2.imwrite.assert_called_once_with(
        os.path.join("/fake/cache", "1a2b3c4d5e.jpg"), "Decoded_Matrix"
    )


def test_serve_texture_invalid_hash(client):
    """Test that path traversal attacks or invalid hashes are blocked."""
    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_VIEW_ASSETS

    # Includes non-hex characters - Should hit our explicit abort(400)
    response = client.get("/admin/texture/invalid_hash_with_symbols!")
    assert response.status_code == 400

    # Includes path traversal - Flask native Werkzeug blocks this at routing level
    response = client.get("/admin/texture/..%2f..%2fetc%2fpasswd")
    assert response.status_code == 404
