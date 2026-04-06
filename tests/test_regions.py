import pytest
from unittest.mock import patch, MagicMock

# --- TOGGLE STATE TESTS ---

@patch('app.blueprints.regions.routes.get_pariah_db')
def test_toggle_state_unauthorized(mock_db, client):
    """Ensure users below level 200 cannot toggle region state."""
    with client.session_transaction() as sess:
        sess['uuid'] = 'user-123'
        sess['is_admin'] = True
        sess['user_level'] = 100 # Too low
        
    response = client.post('/regions/toggle_state/test-uuid')
    assert response.status_code == 302 # Redirects away
    
    # Ensure DB was never even called
    mock_db.assert_not_called()


@patch('app.blueprints.regions.routes.get_pariah_db')
def test_toggle_state_success(mock_db, client):
    """Ensure Admins (Level 200+) can successfully toggle a region's state."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock finding an active region in the database
    mock_cursor.fetchone.return_value = {'is_active': 1, 'region_name': 'TestRegion'}
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-123'
        sess['is_admin'] = True  # FIX: Tell the bouncer we are an admin
        sess['user_level'] = 200
        
    response = client.post('/regions/toggle_state/test-uuid')
    
    # Verify the UPDATE query was fired with the new state (0)
    mock_cursor.execute.assert_any_call("UPDATE region_configs SET is_active = %s WHERE region_uuid = %s", (0, 'test-uuid'))
    assert response.status_code == 302


# --- DELETE TESTS & GUARDRAILS ---

@patch('app.blueprints.regions.routes.get_pariah_db')
def test_delete_region_safety_lock(mock_db, client):
    """Ensure Delete fails if the region is still active, even for Level 250 Super Admins."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock the region as currently ACTIVE
    mock_cursor.fetchone.return_value = {'is_active': 1, 'region_name': 'TestRegion'}
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'superadmin-123'
        sess['is_admin'] = True  # FIX: Tell the bouncer we are an admin
        sess['user_level'] = 250
        
    response = client.post('/regions/delete/test-uuid')
    
    # Verify the DELETE query was NEVER called due to the safety lock
    for call in mock_cursor.execute.call_args_list:
        assert "DELETE FROM region_configs" not in call[0][0]
        
    assert response.status_code == 302


@patch('app.blueprints.regions.routes.get_pariah_db')
def test_delete_region_success(mock_db, client):
    """Ensure Delete succeeds if the region is explicitly disabled AND user is Level 250."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock the region as explicitly DISABLED
    mock_cursor.fetchone.return_value = {'is_active': 0, 'region_name': 'TestRegion'}
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'superadmin-123'
        sess['is_admin'] = True  # FIX: Tell the bouncer we are an admin
        sess['user_level'] = 250
        
    response = client.post('/regions/delete/test-uuid')
    
    # Verify the DELETE query successfully fired
    mock_cursor.execute.assert_any_call("DELETE FROM region_configs WHERE region_uuid = %s", ('test-uuid',))
    assert response.status_code == 302


# --- WEBXML DELIVERY TESTS ---

@patch('app.blueprints.regions.routes.get_dynamic_config')
@patch('app.blueprints.regions.routes.get_pariah_db')
def test_webxml_blocks_disabled_region(mock_db, mock_get_config, client):
    """Ensure WebXML returns a 403 Forbidden if the simulator requests a disabled config."""
    # Whitelist the local test IP
    mock_get_config.return_value = '127.0.0.1' 
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock the region as explicitly DISABLED
    mock_cursor.fetchone.return_value = {'is_active': 0, 'region_name': 'TestRegion'}
    
    # Simulate an incoming request from the simulator
    response = client.get('/regions/api/config/test-uuid.xml', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    
    assert response.status_code == 403
    assert b"Region Disabled By Administrator" in response.data