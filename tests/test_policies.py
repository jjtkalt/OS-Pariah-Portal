import pytest

# -------------------------------------------------------------------
# Test 1: The Policy Bouncer Intercepts Unsigned Users
# -------------------------------------------------------------------
def test_policy_bouncer_intercept(app, client, db_cursor):
    """Proves that if a logged-in user hasn't signed the latest policies, they are redirected."""
    
    # 1. TEMPORARILY REVOKE TEST BOT IMMUNITY
    app.config['TESTING'] = False 
    
    # Tell the fake database: "When the bouncer asks if they agreed, say No (None)."
    db_cursor.fetchone.return_value = None 

    # Simulate a logged-in user
    with client.session_transaction() as sess:
        sess['uuid'] = 'standard-user-uuid'

    # The user tries to go to the Helpdesk
    # Notice we set follow_redirects=False so we can inspect the exact interception!
    response = client.get('/tickets/', follow_redirects=False)

    # 2. Assert the Bouncer did its job!
    assert response.status_code == 302, "Bouncer failed to issue a redirect."
    assert '/user/policies/agree' in response.location, "Bouncer redirected to the wrong page."

    # 3. RESTORE IMMUNITY for the rest of the tests
    app.config['TESTING'] = True