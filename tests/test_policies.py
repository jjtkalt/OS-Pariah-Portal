import pytest
from unittest.mock import patch
from app.utils.schema import PERM_MANAGE_GUIDES

# UPDATED: Point to the exact module where get_dynamic_config lives
@patch('app.utils.db.get_dynamic_config')
def test_policy_bouncer_intercept(mock_config, app, client, db_cursor):
    """Proves that if a logged-in user hasn't signed the latest policies, they are redirected."""
    
    # 1. TEMPORARILY REVOKE TEST BOT IMMUNITY
    app.config['TESTING'] = False
    
    # Force the bouncer to think the grid is actively enforcing Version 1.0
    mock_config.return_value = "1.0"
    
    # Tell the fake database: "When the bouncer asks if they agreed, say No (None)."
    db_cursor.fetchone.return_value = None
    
    # Simulate a logged-in user
    with client.session_transaction() as sess:
        sess['uuid'] = 'standard-user-uuid'
    
    # The user tries to go to the Helpdesk
    response = client.get('/tickets/', follow_redirects=False)
    
    # 2. Assert the Bouncer did its job!
    assert response.status_code == 302, "Bouncer failed to issue a redirect."
    assert '/user/policies/agree' in response.location, "Bouncer redirected to the wrong page."

    # 3. RESTORE IMMUNITY for the rest of the tests
    app.config['TESTING'] = True

# Cross-Category Edit Blocked
def test_cross_category_edit_blocked(client, db_cursor):
    """Proves a Guide Manager cannot hijack a Legal Policy."""
    
    # 1. Tell the DB the document being requested is a Legal Policy
    # FIX: Use side_effect so get_dynamic_config doesn't crash during template render
    db_cursor.fetchone.side_effect = [{
        'slug': 'tos', 'title': 'Terms of Service', 'category': 'Policy', 'requires_login': 0
    }] + [None] * 20
    
    # 2. Simulate a user who only manages Guides
    with client.session_transaction() as sess:
        sess['uuid'] = 'guide-manager-uuid'
        sess['permissions'] = PERM_MANAGE_GUIDES
        
    # 3. Attempt to POST an edit to the 'tos' slug
    response = client.post('/policies/admin/edit/tos', data={
        'title': 'Hacked TOS',
        'body': 'You owe me all your lindens.',
        'category': 'Guide' # Trying to change the category to bypass
    }, follow_redirects=True)
    
    # 4. Assert the bouncer stopped them
    assert b"Unauthorized or document not found" in response.data
    
    # Verify no UPDATE was attempted
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert not any("UPDATE policies" in q for q in sql_queries)