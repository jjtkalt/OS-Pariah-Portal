import pytest
import hashlib
from unittest.mock import patch, MagicMock

def generate_mock_hash(password, salt):
    """Helper to generate OpenSim's specific Double-MD5 password hash."""
    pass_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()
    return hashlib.md5(f"{pass_md5}:{salt}".encode('utf-8')).hexdigest()

# -------------------------------------------------------------------
# Test 1: Successful Login (Level 0 User)
# -------------------------------------------------------------------
@patch('app.blueprints.auth.routes.get_robust_db')
def test_successful_login(mock_get_robust, client):
    password = "SecurePassword123!"
    salt = "random_salt_string"
    expected_hash = generate_mock_hash(password, salt)
    
    # Give Robust its own isolated fake cursor
    mock_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    
    # 1. UserAccounts Check, 2. Password Hash Check
    mock_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-0000', 'userLevel': 0},
        {'passwordHash': expected_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/auth/login', data={
        'first_name': 'Test',
        'last_name': 'Avatar',
        'password': password
    }, follow_redirects=True)
    
    assert b"Login successful!" in response.data

# -------------------------------------------------------------------
# Test 2: The Bouncer blocks a Banned User (Level -2)
# -------------------------------------------------------------------
@patch('app.blueprints.auth.routes.get_robust_db')
def test_banned_user_blocked(mock_get_robust, client):
    password = "BadGuyPassword"
    salt = "bad_salt"
    expected_hash = generate_mock_hash(password, salt)
    
    mock_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-banned', 'userLevel': -2},
        {'passwordHash': expected_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/auth/login', data={
        'first_name': 'Bad',
        'last_name': 'Guy',
        'password': password
    }, follow_redirects=True)
    
    assert b"Your account is currently locked, pending approval, or banned." in response.data

# -------------------------------------------------------------------
# Test 3: Invalid Password Rejection
# -------------------------------------------------------------------
@patch('app.blueprints.auth.routes.get_robust_db')
def test_invalid_password(mock_get_robust, client):
    password = "WrongPassword!"
    salt = "random_salt"
    real_hash = generate_mock_hash("CorrectPassword", salt)
    
    mock_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-0000', 'userLevel': 0},
        {'passwordHash': real_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/auth/login', data={
        'first_name': 'Test',
        'last_name': 'Avatar',
        'password': password
    }, follow_redirects=True)
    
    assert b"Invalid avatar name or password" in response.data