import pytest
from unittest.mock import patch

# -------------------------------------------------------------------
# Test 1: Successful Registration Workflow
# -------------------------------------------------------------------
@patch('app.blueprints.register.routes.verify_turnstile')
@patch('app.blueprints.register.routes.create_robust_user')
@patch('app.blueprints.register.routes.set_user_level')
@patch('app.blueprints.register.routes.send_verification_email')
def test_successful_registration(mock_send_email, mock_set_level, mock_create_robust, mock_turnstile, client, db_cursor):
    
    # 1. Setup our Mocks 
    mock_turnstile.return_value = True
    mock_create_robust.return_value = "fake-uuid-1234-5678"
    
    # 2. Simulate the User submitting the form
    essay_text = "This is a test essay that needs to be at least thirty words long so I am going to keep typing until I hit the required limit to pass the backend validation check and prove the system works."
    
    response = client.post('/register/', data={
        'cf-turnstile-response': 'dummy_token',
        'first_name': 'Test',
        'last_name': 'Avatar',
        'email': 'test@example.com',
        'password': 'SecurePassword123!',
        'inviter': 'Admin User',
        'policy_check': 'on',
        'age_check': 'on',
        'other_info': essay_text
    }, follow_redirects=True)

    # 3. Assertions
    mock_turnstile.assert_called_once_with('dummy_token')
    mock_create_robust.assert_called_once_with('Test', 'Avatar', 'SecurePassword123!', 'test@example.com')
    mock_set_level.assert_called_once_with('fake-uuid-1234-5678', -1)
    
    # Verify the SQL Insert
    assert db_cursor.execute.called, "Database cursor execute was not called."
    
    # Grab the exact SQL string the portal tried to run
    sql_queries_run = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("INSERT INTO pending_registrations" in q for q in sql_queries_run), "Did not attempt to insert registration into DB."
    
    assert mock_send_email.called, "Verification email was not dispatched."
    assert b"Registration successful!" in response.data


# -------------------------------------------------------------------
# Test 2: Failed Captcha Workflow
# -------------------------------------------------------------------
@patch('app.blueprints.register.routes.verify_turnstile')
def test_failed_captcha(mock_turnstile, client):
    mock_turnstile.return_value = False
    
    response = client.post('/register/', data={
        'cf-turnstile-response': 'bad_token',
        'first_name': 'Bot',
        'last_name': 'User',
        'email': 'bot@example.com',
        'password': 'password',
        'policy_check': 'on',
        'age_check': 'on'
    }, follow_redirects=True)
    
    assert b"Security check failed" in response.data