import requests
import urllib.parse
from flask import current_app

def call_robust_api(method, payload):
    """
    Sends an HTTP POST to the Robust private port.
    Returns the raw text response or None on failure.
    """
    base_url = current_app.config.get('ROBUST_PRIVATE_URL', 'http://127.0.0.1:8003/accounts')
    payload['METHOD'] = method # e.g., 'createuser' or 'setaccount'
    
    try:
        # Robust expects standard form-encoded data for these XMLRPC-style handlers
        response = requests.post(base_url, data=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Robust API call failed for {method}: {e}")
        return None

def create_robust_user(first_name, last_name, password, email):
    """
    Creates a new user via the Robust API.
    Returns the new user's UUID string if successful, or None.
    """
    payload = {
        'FirstName': first_name,
        'LastName': last_name,
        'Password': password,
        'Email': email
    }
    
    response_text = call_robust_api('createuser', payload)
    
    if response_text and '<PrincipalID>' in response_text:
        import re
        # Extract the UUID from the XML response
        match = re.search(r'<PrincipalID>(.*?)</PrincipalID>', response_text)
        if match:
            return match.group(1)
            
    return None

def set_user_level(uuid, level):
    """
    Updates a user's access level (e.g., -1 for pending, 0 for approved).
    """
    payload = {
        'PrincipalID': uuid,
        'UserLevel': level
    }
    response_text = call_robust_api('setaccount', payload)
    
    if response_text and 'True' in response_text: # Assuming Robust returns True on success
        return True
    return False
