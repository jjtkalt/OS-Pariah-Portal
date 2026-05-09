import pytest
from unittest.mock import patch
from app.utils.schema import *

def _known_setting_default_int(key: str) -> int:
    """
    Default used by get_dynamic_config when no config row exists.
    Tests force fetchone() -> None (see conftest), so ban levels must match KNOWN_SETTINGS.
    """
    for _category, fields in KNOWN_SETTINGS.items():
        if key in fields:
            return int(fields[key]["default"])
    raise KeyError(key)

# -------------------------------------------------------------------
# Test 1: Creating a Ban (Cascading DB & Severity Level Sync)
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
@patch('app.blueprints.admin.user_mgmt.subprocess.Popen')
def test_create_ban_cascading(mock_popen, mock_set_level, client, db_cursor):
    """MAC ban applies ban_level_mac from settings (schema default when DB row absent) and triggers sync."""
    
    # Inject Super Admin Session
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['permissions'] = PERM_ISSUE_BANS

    response = client.post('/admin/users/bans/create', data={
        'reason': 'Griefing Sandbox',
        'type': 'mac',
        'uuids': 'bad-guy-uuid',
        'macs': '00:11:22:33:44:55'
    }, follow_redirects=True)

    # 1. Assert DB Inserts successfully cascaded
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("INSERT INTO bans_master" in q for q in sql_queries)
    assert any("INSERT INTO bans_mac" in q for q in sql_queries)
    assert any("INSERT INTO bans_uuid" in q for q in sql_queries)

    expected_mac_level = _known_setting_default_int("ban_level_mac")
    mock_set_level.assert_called_with("bad-guy-uuid", expected_mac_level)

    # 3. Assert Firewall Worker was triggered
    assert mock_popen.called, "Firewall sync worker was not triggered on ban creation."

    # 4. Check UI response
    assert b"Ban created and actively enforced successfully" in response.data

# -------------------------------------------------------------------
# Test 1b: Linked accounts (e.g. gatekeeper-discovered alts) get the tier level
# -------------------------------------------------------------------
@patch("app.blueprints.admin.user_mgmt._collect_ban_evidence")
@patch("app.blueprints.admin.user_mgmt.set_user_level")
@patch("app.blueprints.admin.user_mgmt.subprocess.Popen")
def test_create_ban_sets_level_on_all_linked_accounts(
    mock_popen, mock_set_level, mock_evidence, client, db_cursor
):
    """MAC/IP/host bans expand linked UUIDs; every linked account must receive ban_level_*."""
    mock_evidence.return_value = {
        "linked_uuids": {"primary-uuid", "alt-from-gatekeeper"},
        "grid_by_uuid": {},
        "notes_text": "snapshot",
        "observed_ips": set(),
        "observed_macs": set(),
        "observed_hostids": set(),
    }

    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_ISSUE_BANS

    client.post(
        "/admin/users/bans/create",
        data={
            "reason": "MAC grief",
            "type": "mac",
            "uuids": "primary-uuid",
            "macs": "aa:bb:cc:dd:ee:ff",
        },
        follow_redirects=True,
    )

    enforced = {call.args[0] for call in mock_set_level.call_args_list}
    assert enforced == {"primary-uuid", "alt-from-gatekeeper"}
    expected_mac_level = _known_setting_default_int("ban_level_mac")
    for call in mock_set_level.call_args_list:
        assert call.args[1] == expected_mac_level


# -------------------------------------------------------------------
# Test 2: Deleting a Ban (Restoration & Firewall Sync)
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
@patch('app.blueprints.admin.user_mgmt.subprocess.Popen')
def test_delete_ban(mock_popen, mock_set_level, client, db_cursor):
    """Proves deleting a ban restores users to Level 0 and flushes the firewall."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['permissions'] = PERM_ISSUE_BANS

    # Mock the DB returning the UUID tied to the ban we are deleting,
    # and then return an empty list when the redirect loads the Ban Table UI!
    db_cursor.fetchall.side_effect = [
        [{'uuid': 'bad-guy-uuid'}], 
        [],  # bans_related_uuid
        []
    ]

    response = client.post('/admin/users/bans/1/delete', follow_redirects=True)

    # 1. Assert DB Deletion
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("DELETE FROM bans_master" in q for q in sql_queries)

    # 2. Assert Robust API restored them to Level 0
    mock_set_level.assert_called_with('bad-guy-uuid', 0)

    # 3. Assert Firewall Worker Triggered to remove the IP/HostID
    assert mock_popen.called, "Firewall sync worker was not triggered on ban deletion."

    assert b"associated avatars have been restored" in response.data

# -------------------------------------------------------------------
# Test 3: Manual Promotion
# -------------------------------------------------------------------
@patch('app.blueprints.admin.user_mgmt.set_user_level')
def test_manual_user_promotion(mock_set_level, client):
    """Proves Super Admins can manually adjust a user level (e.g., Promotion)."""
    
    with client.session_transaction() as sess:
        sess['uuid'] = 'super-admin-uuid'
        sess['permissions'] = PERM_MANAGE_ROLES

    response = client.post('/admin/users/good-guy-uuid/set_level', data={
        'new_level': '200'
    }, follow_redirects=True)

    # Assert Robust API bumped them to 200
    mock_set_level.assert_called_with('good-guy-uuid', 200)
    assert b"User level successfully updated to 200" in response.data