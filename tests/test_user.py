import pytest
from unittest.mock import patch, MagicMock

@patch('app.utils.robust_api.requests.post')
def test_update_password_success(mock_post, client, app):
    """Proves the portal constructs the correct auth/plain URL and payload."""
    
    # Fake a successful 200 OK response from the OpenSim Auth service
    mock_response = MagicMock()
    mock_response.text = "<boolean>true</boolean>"
    mock_post.return_value = mock_response
    
    # Log in as a normal user
    with client.session_transaction() as sess:
        sess['uuid'] = 'fake-user-uuid'
        
    # Submit the password change form
    response = client.post('/user/profile/password', data={
        'new_password': 'SuperSecretPassword123!',
        'confirm_password': 'SuperSecretPassword123!'
    }, follow_redirects=True)
    
    # 1. Assert the request was actually made!
    assert mock_post.called, "The portal never tried to send the API request."
    
    # 2. Inspect EXACTLY what the portal tried to send
    called_url = mock_post.call_args[0][0]
    called_data = mock_post.call_args[1]['data']
    
    assert called_url.endswith('/auth/plain'), f"Sent to wrong namespace: {called_url}"
    assert called_data['METHOD'] == 'setpassword', "Used the wrong API method."
    assert called_data['PRINCIPAL'] == 'fake-user-uuid', "Did not send the correct user UUID."
    assert called_data['PASSWORD'] == 'SuperSecretPassword123!', "Did not send the new password."
    
    # 3. Assert the user got the success message
    assert b'Password updated successfully' in response.data