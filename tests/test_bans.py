import pytest
from unittest.mock import patch

# -------------------------------------------------------------------
# Test 1: Creating a Ban (Cascading DB & Severity Level Sync)
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
@patch('app.blueprints.admin.user_mgmt.subprocess.Popen')
def test_create_ban_cascading(mock_popen, mock_set_level, client, db_cursor):
    """Proves that a MAC ban sets the user to -12 and triggers the firewall sync."""
    
    # Inject Super Admin Session
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    response = client.post('/admin/users/bans/create', data={
        'reason': 'Griefing Sandbox',
        'type': 'mac',
        'uuids': 'bad-guy-uuid',
        'macs': '00:11:22:33:44:55'
    }, follow_redirects=True)

    # 1. Assert DB Inserts successfully cascaded
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("INSERT INTO bans_master" in q for q in sql_queries)
    assert any("INSERT INTO bans_mac" in q for q in sql_queries)
    assert any("INSERT INTO bans_uuid" in q for q in sql_queries)

    # 2. Assert Robust API was called with the exact MAC ban level (-12)
    mock_set_level.assert_called_with('bad-guy-uuid', -12)

    # 3. Assert Firewall Worker was triggered
    assert mock_popen.called, "Firewall sync worker was not triggered on ban creation."

    # 4. Check UI response
    assert b"Ban created and actively enforced successfully" in response.data

# -------------------------------------------------------------------
# Test 2: Deleting a Ban (Restoration & Firewall Sync)
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
@patch('app.blueprints.admin.user_mgmt.subprocess.Popen')
def test_delete_ban(mock_popen, mock_set_level, client, db_cursor):
    """Proves deleting a ban restores users to Level 0 and flushes the firewall."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    # Mock the DB returning the UUID tied to the ban we are deleting,
    # and then return an empty list when the redirect loads the Ban Table UI!
    db_cursor.fetchall.side_effect = [
        [{'uuid': 'bad-guy-uuid'}], 
        []
    ]

    response = client.post('/admin/users/bans/1/delete', follow_redirects=True)

    # 1. Assert DB Deletion
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("DELETE FROM bans_master" in q for q in sql_queries)

    # 2. Assert Robust API restored them to Level 0
    mock_set_level.assert_called_with('bad-guy-uuid', 0)

    # 3. Assert Firewall Worker Triggered to remove the IP/HostID
    assert mock_popen.called, "Firewall sync worker was not triggered on ban deletion."

    assert b"associated avatars have been restored" in response.data

# -------------------------------------------------------------------
# Test 3: Manual Promotion
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
def test_manual_user_promotion(mock_set_level, client):
    """Proves Super Admins can manually adjust a user level (e.g., Promotion)."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    response = client.post('/admin/users/good-guy-uuid/set_level', data={
        'new_level': '200'
    }, follow_redirects=True)

    # Assert Robust API bumped them to 200
    mock_set_level.assert_called_with('good-guy-uuid', 200)
    assert b"User level successfully updated to 200" in response.data