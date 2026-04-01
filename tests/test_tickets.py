import pytest
from unittest.mock import patch

# -------------------------------------------------------------------
# Test 1: Successful Guest Ticket Submission
# -------------------------------------------------------------------
@patch('app.blueprints.tickets.routes.verify_turnstile')
@patch('app.blueprints.tickets.routes.send_matrix_discord_webhook')
def test_guest_ticket_success(mock_webhook, mock_turnstile, client, db_cursor):
    # Setup Mocks
    mock_turnstile.return_value = True
    
    # Simulate a guest filling out the support form
    response = client.post('/tickets/new', data={
        'cf-turnstile-response': 'valid_token',
        'email': 'guest@example.com',
        'subject': 'Cannot connect to region',
        'category': 'Technical Support',
        'message': 'My viewer gets stuck at connecting to region.'
    }, follow_redirects=True)

    # 1. Assert Captcha was checked
    mock_turnstile.assert_called_once_with('valid_token')

    # 2. Assert the Database Insert fired
    assert db_cursor.execute.called, "Database cursor execute was not called."
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("INSERT INTO tickets" in q for q in sql_queries), "Did not attempt to insert ticket into DB."

    # 3. Assert the Webhook fired
    assert mock_webhook.called, "Discord/Matrix webhook was not triggered."

    # 4. Assert the user sees the success message
    assert b"Your ticket has been submitted successfully!" in response.data

# -------------------------------------------------------------------
# Test 2: Guest Forgets Email Address
# -------------------------------------------------------------------
@patch('app.blueprints.tickets.routes.verify_turnstile')
def test_guest_ticket_missing_email(mock_turnstile, client):
    mock_turnstile.return_value = True
    
    response = client.post('/tickets/new', data={
        'cf-turnstile-response': 'valid_token',
        'email': '',  # Blank email!
        'subject': 'Help',
        'category': 'General Support',
        'message': 'Testing missing email'
    }, follow_redirects=True)

    # Assert the form rejected them with the correct error
    assert b"An email address is required for guest tickets" in response.data

# -------------------------------------------------------------------
# Test 3: Guest Fails Captcha
# -------------------------------------------------------------------
@patch('app.blueprints.tickets.routes.verify_turnstile')
def test_guest_ticket_failed_captcha(mock_turnstile, client):
    # Simulate a bot failing the Turnstile check
    mock_turnstile.return_value = False
    
    response = client.post('/tickets/new', data={
        'cf-turnstile-response': 'bad_bot_token',
        'email': 'bot@example.com',
        'subject': 'Spam',
        'category': 'General Support',
        'message': 'Buy my cheap raybans'
    }, follow_redirects=True)

    # Assert the bouncer stopped them
    assert b"Security check failed" in response.data