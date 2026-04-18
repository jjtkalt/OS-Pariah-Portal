import requests
import urllib.parse
from flask import current_app
from app import cache
from app.utils.db import get_robust_db, get_dynamic_config

def call_robust_api(namespace, method, payload):
    """
    Sends an HTTP POST to the Robust private port.
    Returns the raw text response or None on failure.
    """
    # Force to string, strip whitespace
    base_url = str(get_dynamic_config('ROBUST_PRIVATE_URL')).strip()
    
    # Strip any trailing slashes
    base_url = base_url.rstrip('/')
    
    # Critical: If the admin put the old /accounts path in the config, strip it out!
    if base_url.endswith('/accounts'):
        base_url = base_url[:-9]

    # Now safely append the specific namespace
    # We remove any leading slashes from the namespace to ensure exactly one slash
    safe_namespace = namespace.lstrip('/')
    full_url = f"{base_url}/{safe_namespace}"
    
    payload['METHOD'] = method
    
    try:
        response = requests.post(full_url, data=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Robust API call failed for {method} at {full_url}: {e}")
        return None

def create_robust_user(first_name, last_name, password, email):
    """Creates a new user via the Robust API"""
    payload = {
        'FirstName': first_name,
        'LastName': last_name,
        'Password': password,
        'Email': email
    }
    response_text = call_robust_api('accounts', 'createuser', payload)
    
    if response_text and '<PrincipalID>' in response_text:
        import re
        # Extract the UUID from the XML response
        match = re.search(r'<PrincipalID>(.*?)</PrincipalID>', response_text)
        if match:
            return match.group(1)
            
    return None

def set_user_level(uuid, level):
    """Updates a user's access level."""
    payload = {
        'PrincipalID': uuid,
        'UserLevel': level
    }
    response_text = call_robust_api('accounts', 'setaccount', payload)
    return response_text and 'true' in response_text.lower()

def update_robust_name(uuid, first_name, last_name):
    """Updates an existing user's First and Last Name via the Robust API."""
    payload = {
        'PrincipalID': uuid,
        'FirstName': first_name,
        'LastName': last_name
    }
    response_text = call_robust_api('accounts', 'setaccount', payload)
    return response_text and 'true' in response_text.lower()

def update_robust_email(uuid, email):
    """Updates an existing user's Email via the Robust API."""
    payload = {
        'PrincipalID': uuid,
        'Email': email
    }
    response_text = call_robust_api('accounts', 'setaccount', payload)
    return response_text and 'true' in response_text.lower()

def update_user_password(user_uuid, new_password):
    """Safely updates the user's password via the Robust Auth API."""
    payload = {
        'PRINCIPAL': user_uuid,
        'PASSWORD': new_password
    }
    response_text = call_robust_api('auth/plain', 'setpassword', payload)
    
    # If the API crashed or timed out, it's an immediate failure
    if not response_text:
        return False
        
    # OpenSim setpassword can be weird. It might return True, <boolean>True</boolean>,
    # or even just a blank success string depending on the exact version.
    rt_lower = response_text.lower()
    
    # If it explicitly says true, we are good.
    if 'true' in rt_lower:
        return True
        
    # If it says false or error, it definitely failed.
    if 'false' in rt_lower or 'error' in rt_lower:
        return False
        
    # If it didn't crash, didn't error, and didn't explicitly say False,
    # we assume the update was successful (OpenSim often returns empty 200 OKs).
    return True

@cache.cached(timeout=300, key_prefix='total_regions_count')
def get_total_regions_count():
    """Fetches the total number of connected regions from Robust, cached for 5 minutes."""
    count = 0
    try:
        robust_conn = get_robust_db()
        with robust_conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(uuid) as region_count FROM regions")
            result = cursor.fetchone()
            if result and 'region_count' in result:
                count = result['region_count']
    except Exception as e:
        current_app.logger.error(f"Failed to fetch region count: {e}")
    return count