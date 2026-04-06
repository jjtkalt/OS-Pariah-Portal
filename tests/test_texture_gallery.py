import pytest
from unittest.mock import patch, MagicMock
import os
import time

# --- 1. TEST THE CACHE CLEANUP ROUTINE ---

@patch('scripts.worker.os.listdir')
@patch('scripts.worker.os.path.getmtime')
@patch('scripts.worker.os.remove')
@patch('scripts.worker.os.path.exists')
@patch('scripts.worker.get_dynamic_config')
def test_clean_texture_cache(mock_get_config, mock_exists, mock_remove, mock_getmtime, mock_listdir):
    """Test that the cleanup routine correctly identifies and deletes old files."""
    from scripts.worker import clean_texture_cache

    # Setup mocks
    mock_get_config.return_value = '/fake/cache/dir'
    mock_exists.return_value = True
    # Provide two fake files in the directory
    mock_listdir.return_value = ['old_texture.jpg', 'new_texture.jpg', 'not_an_image.txt']

    current_time = time.time()

    # old_texture.jpg is 40 days old, new_texture.jpg is 10 days old
    def fake_getmtime(filepath):
        if 'old_texture' in filepath:
            return current_time - (40 * 86400)
        return current_time - (10 * 86400)

    mock_getmtime.side_effect = fake_getmtime

    # Run cleanup
    clean_texture_cache()

    # Assertions
    mock_remove.assert_called_once_with(os.path.join('/fake/cache/dir', 'old_texture.jpg'))


# --- 2. TEST THE GALLERY ROUTE ---

@patch('app.blueprints.admin.routes.get_robust_db')
def test_texture_gallery_access(mock_get_db, client):
    """Test that admins can view the gallery, and db queries execute."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # UPDATED: Match the new SQL structure!
    mock_cursor.fetchall.return_value = [
        {'id': '123', 'hash': 'abcdef', 'name': 'Test Texture', 'create_time': 1600000000, 'owner_uuid': 'user-uuid', 'owner_name': 'Test Avatar'}
    ]
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 200
    
    response = client.get('/admin/gallery')
    assert response.status_code == 200
    assert b'Texture Gallery' in response.data
    assert b'Test Texture' in response.data
    assert b'abcdef' in response.data
    assert b'Test Avatar' in response.data


# --- 3. TEST THE OPENCV SMART PROXY ---

@patch('app.blueprints.admin.routes.os.makedirs')
@patch('app.blueprints.admin.routes.os.access')
@patch('app.blueprints.admin.routes.os.path.exists')
@patch('app.blueprints.admin.routes.get_dynamic_config')
@patch('app.blueprints.admin.routes.send_from_directory')
def test_serve_texture_cached(mock_send_dir, mock_get_config, mock_exists, mock_access, mock_makedirs, client):
    """Test that an already cached texture skips OpenCV and serves directly."""

    def fake_config(key):
        if key == 'texture_cache_path': return '/fake/dir'
        if key == 'fsassets_path': return '/fake/fsassets'
        return None
    mock_get_config.side_effect = fake_config

    # Force the OS to pretend the cache directory is perfectly writable
    mock_access.return_value = True

    # Force os.path.exists to return True, implying the file is already converted and cached
    mock_exists.return_value = True
    mock_send_dir.return_value = "Fake Image Data"

    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-uuid'
        sess['is_admin'] = True

    response = client.get('/admin/texture/1a2b3c4d5e')

    assert response.status_code == 200
    mock_send_dir.assert_called_once_with('/fake/dir', '1a2b3c4d5e.jpg')


@patch('app.blueprints.admin.routes.cv2')
@patch('app.blueprints.admin.routes.gzip.open')
@patch('app.blueprints.admin.routes.os.makedirs')
@patch('app.blueprints.admin.routes.os.access')
@patch('app.blueprints.admin.routes.os.path.exists')
@patch('app.blueprints.admin.routes.get_dynamic_config')
@patch('app.blueprints.admin.routes.send_from_directory')
def test_serve_texture_unzipped_and_converted(mock_send_dir, mock_get_config, mock_exists, mock_access, mock_makedirs, mock_gzip, mock_cv2, client):
    """Test that a new texture is unzipped, decoded by OpenCV, and cached."""

    def fake_config(key):
        if key == 'texture_cache_path': return '/fake/cache'
        if key == 'fsassets_path': return '/fake/fsassets'
        return None
    mock_get_config.side_effect = fake_config
    # The cache dir exists, the cached file does NOT exist, the raw FSAsset GZ file DOES exist
    def fake_exists(path):
        if 'cache' in path and path.endswith('.jpg'): return False
        return True
    mock_exists.side_effect = fake_exists

    mock_access.return_value = True  # We have write permission

    # Mock GZIP returning fake bytes
    mock_file = MagicMock()
    mock_file.read.return_value = b"fake_j2c_bytes"
    mock_gzip.return_value.__enter__.return_value = mock_file

    # Mock OpenCV decoding successfully
    mock_cv2.imdecode.return_value = "Decoded_Matrix"
    mock_cv2.imencode.return_value = (True, b"fake_buffer") # Just in case it hits fallback

    mock_send_dir.return_value = "Fake Served Image"

    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-uuid'
        sess['is_admin'] = True

    response = client.get('/admin/texture/1a2b3c4d5e')

    assert response.status_code == 200
    mock_cv2.imwrite.assert_called_once_with(os.path.join('/fake/cache', '1a2b3c4d5e.jpg'), "Decoded_Matrix")


def test_serve_texture_invalid_hash(client):
    """Test that path traversal attacks or invalid hashes are blocked."""
    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-uuid'
        sess['is_admin'] = True

    # Includes non-hex characters - Should hit our explicit abort(400)
    response = client.get('/admin/texture/invalid_hash_with_symbols!')
    assert response.status_code == 400

    # Includes path traversal - Flask native Werkzeug blocks this at routing level
    response = client.get('/admin/texture/..%2f..%2fetc%2fpasswd')
    assert response.status_code == 404
