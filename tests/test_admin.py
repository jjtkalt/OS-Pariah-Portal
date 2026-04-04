import pytest

# -------------------------------------------------------------------
# Test 1: Unauthorized Access (Standard Admin tries to peek)
# -------------------------------------------------------------------
def test_settings_unauthorized(client):
    """Proves that a Level 200 Admin gets rejected from the Level 250 page."""
    
    # Inject a fake session for a Level 200 Admin
    with client.session_transaction() as sess:
        sess['uuid'] = 'fake-admin-uuid'
        sess['is_admin'] = True
        sess['user_level'] = 200  # Not high enough!

    response = client.get('/admin/settings', follow_redirects=True)
    
    # Assert they got booted back to the news feed
    assert b"Unauthorized: Only Level 250+ Super Admins can access System Settings." in response.data


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
    upsert_query_found = any("INSERT INTO config (config_key, config_value" in q for q in sql_queries)
    assert upsert_query_found, "Did not attempt to save settings to the database."

    # 2. Assert the user sees the success message
    assert b"System settings updated successfully" in response.data