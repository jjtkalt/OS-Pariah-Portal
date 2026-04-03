import pytest
import hashlib

def generate_mock_hash(password, salt):
    """Helper to generate OpenSim's specific Double-MD5 password hash."""
    pass_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()
    return hashlib.md5(f"{pass_md5}:{salt}".encode('utf-8')).hexdigest()

# -------------------------------------------------------------------
# Test 1: Successful Login (Level 0 User)
# -------------------------------------------------------------------
def test_successful_login(client, db_cursor):
    password = "SecurePassword123!"
    salt = "random_salt_string"
    expected_hash = generate_mock_hash(password, salt)
    
    # 1. Mock the two database fetchone() calls the login route makes
    # Call 1: UserAccounts (Returns Level 0)
    # Call 2: Auth Table (Returns Password Hash)
    db_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-0000', 'userLevel': 0},
        {'passwordHash': expected_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/login', data={
        'first_name': 'Test',
        'last_name': 'Avatar',
        'password': password
    }, follow_redirects=True)
    
    assert b"Login successful!" in response.data

# -------------------------------------------------------------------
# Test 2: The Bouncer blocks a Banned User (Level -2)
# -------------------------------------------------------------------
def test_banned_user_blocked(client, db_cursor):
    password = "BadGuyPassword"
    salt = "bad_salt"
    expected_hash = generate_mock_hash(password, salt)
    
    # Mock Call 1 returns Level -2 (Banned)
    db_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-banned', 'userLevel': -2},
        {'passwordHash': expected_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/login', data={
        'first_name': 'Bad',
        'last_name': 'Guy',
        'password': password
    }, follow_redirects=True)
    
    # Assert they are bounced back to the login screen with the error
    assert b"Your account is currently locked, pending approval, or banned." in response.data
    assert b"Login successful!" not in response.data

# -------------------------------------------------------------------
# Test 3: Invalid Password Rejection
# -------------------------------------------------------------------
def test_invalid_password(client, db_cursor):
    password = "WrongPassword!"
    salt = "random_salt"
    
    # The database holds the hash for "CorrectPassword", not "WrongPassword!"
    real_hash = generate_mock_hash("CorrectPassword", salt)
    
    db_cursor.fetchone.side_effect = [
        {'PrincipalID': 'fake-uuid-0000', 'userLevel': 0},
        {'passwordHash': real_hash, 'passwordSalt': salt}
    ]
    
    response = client.post('/login', data={
        'first_name': 'Test',
        'last_name': 'Avatar',
        'password': password
    }, follow_redirects=True)
    
    assert b"Invalid avatar name or password" in response.data