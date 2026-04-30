import pytest
from unittest.mock import patch, MagicMock
from app.utils.schema import *

# -------------------------------------------------------------------
# Test 1: Prevent Self-Modification of Roles (SEV1 Fix)
# -------------------------------------------------------------------
def test_manage_roles_self_edit_blocked(client, db_cursor):
    """Proves a user cannot modify their own permissions."""
    
    # 1. Simulate an admin session
    with client.session_transaction() as sess:
        sess['uuid'] = 'admin-uuid-123'
        # FIX: Removed PERM_SUPER_ADMIN so the bouncer triggers!
        sess['permissions'] = PERM_MANAGE_ROLES 
        
    # 2. They attempt to POST to their OWN uuid
    response = client.post('/admin/users/admin-uuid-123/roles', data={
        'permissions': str(PERM_MANAGE_ROLES)
    }, follow_redirects=True)
    
    # 3. Assert the bouncer stopped them before touching the DB
    assert b"Security Violation: You cannot modify your own permissions" in response.data
    
    # Verify no INSERT/UPDATE was attempted
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert not any("INSERT INTO user_rbac" in q for q in sql_queries)

# -------------------------------------------------------------------
# Test 2: Preserve Super-Only Bits (SEV1 Fix)
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.get_robust_db')
def test_manage_roles_preserves_super_bits(mock_get_robust, client, db_cursor):
    """Proves a standard admin cannot wipe out Super Admin bits on a target user."""
    
    # 1. Setup Robust Mock to find the target user
    mock_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'FirstName': 'Target', 'LastName': 'User'}

    # 2. Tell the Pariah DB that the Target User is currently a Super Admin
    # FIX: Use side_effect to prevent crashing get_dynamic_config
    db_cursor.fetchone.side_effect = [{'permissions': PERM_SUPER_ADMIN}] + [None] * 20

    # 3. Simulate a Standard Admin (No Super Admin rights)
    with client.session_transaction() as sess:
        sess['uuid'] = 'standard-admin-uuid'
        sess['permissions'] = PERM_MANAGE_ROLES 
        
    # 4. Standard Admin attempts to save the target user with ONLY the "Add Notes" bit
    response = client.post('/admin/users/target-uuid-456/roles', data={
        'permissions': str(PERM_ADD_NOTES)
    }, follow_redirects=True)
    
    # 5. Assert the DB saved the combination of the NEW bit AND the PRESERVED super bit
    expected_bitmask = PERM_ADD_NOTES | PERM_SUPER_ADMIN
    
    saved_correctly = False
    for call in db_cursor.execute.call_args_list:
        query = call[0][0]
        args = call[0][1] if len(call[0]) > 1 else []
        if "INSERT INTO user_rbac" in query and args == ('target-uuid-456', expected_bitmask):
            saved_correctly = True
            break
            
    assert saved_correctly, f"Failed to preserve super_only bits. Expected bitmask: {expected_bitmask}"

# -------------------------------------------------------------------
# Test 3: PPI Search Blocked
# -------------------------------------------------------------------
def test_ppi_search_blocked_without_permission(client):
    """Proves admins cannot search by IP without PERM_VIEW_PPI."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'standard-admin-uuid'
        # Has lookup, but NOT PPI access
        sess['permissions'] = PERM_USER_LOOKUP 
        
    # Malicious direct URL manipulation
    response = client.get('/admin/users/lookup?type=ip&q=192.168.1.1', follow_redirects=True)
    
    # Assert the request was intercepted
    assert b"Unauthorized: You do not have clearance to search by connection PPI" in response.data