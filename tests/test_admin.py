import pytest

# -------------------------------------------------------------------
# Test 1: Unauthorized Access (Standard Admin tries to peek)
# -------------------------------------------------------------------
def test_settings_unauthorized(client):
    """Proves that a Level 200 Admin gets rejected from Level 250 pages/actions."""
    
    # Inject a fake session for a Level 200 Admin
    with client.session_transaction() as sess:
        sess['uuid'] = 'fake-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 200  # Not high enough!

    # Check the main UI page
    response = client.get('/admin/settings', follow_redirects=True)
    assert b"Unauthorized: Only Level 250+" in response.data

    # Check the Add route
    response_add = client.post('/admin/settings/add', data={'new_key': 'test', 'new_value': 'test'}, follow_redirects=True)
    assert b"Unauthorized" in response_add.data

    # Check the Delete route
    response_delete = client.post('/admin/settings/delete', data={'target_key': 'test'}, follow_redirects=True)
    assert b"Unauthorized" in response_delete.data


# -------------------------------------------------------------------
# Test 2: Successful Settings Update (Super Admin)
# -------------------------------------------------------------------
def test_settings_update_success(client, db_cursor):
    """Proves a Level 250 Admin can successfully UPSERT new system settings."""
    
    # Inject a fake session for a Level 250 Super Admin
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    # Simulate hitting "Save" on the Settings Form
    response = client.post('/admin/settings', data={
        'cfg_grid_name': 'My Awesome Test Grid',
        'cfg_smtp_port': '2525'
    }, follow_redirects=True)

    # 1. Assert the SQL Upsert ran
    assert db_cursor.execute.called, "Database cursor execute was not called."
    
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    upsert_query_found = any("INSERT INTO config" in q for q in sql_queries)
    assert upsert_query_found, "Did not attempt to save settings to the database."

    # 2. Assert the user sees the success message
    assert b"System settings saved" in response.data


# -------------------------------------------------------------------
# Test 3: Successful Settings Add (Super Admin)
# -------------------------------------------------------------------
def test_settings_add_success(client, db_cursor):
    """Proves a Level 250 Admin can inject a custom variable."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    response = client.post('/admin/settings/add', data={
        'new_key': 'my_custom_key',
        'new_value': 'My Custom Value'
    }, follow_redirects=True)

    inserted = False
    for call in db_cursor.execute.call_args_list:
        query = call[0][0]
        args = call[0][1] if len(call[0]) > 1 else []
        if "INSERT INTO config (config_key, config_value)" in query and args == ('my_custom_key', 'My Custom Value'):
            inserted = True
            break

    assert inserted, "The INSERT query for the new custom setting was not executed correctly."
    assert b"successfully added" in response.data


# -------------------------------------------------------------------
# Test 4: Successful Settings Delete (Super Admin)
# -------------------------------------------------------------------
def test_settings_delete_success(client, db_cursor):
    """Proves a Level 250 Admin can delete a setting and revert it."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 250

    response = client.post('/admin/settings/delete', data={
        'target_key': 'grid_name'
    }, follow_redirects=True)

    deleted = False
    for call in db_cursor.execute.call_args_list:
        query = call[0][0]
        args = call[0][1] if len(call[0]) > 1 else []
        if "DELETE FROM config WHERE config_key =" in query and args == ('grid_name',):
            deleted = True
            break

    assert deleted, "The DELETE query was not executed correctly."
    assert b"deleted and reverted to system default" in response.data