from unittest.mock import patch

from app.utils.schema import PERM_APPROVE_USERS, PERM_MANAGE_SETTINGS


# -------------------------------------------------------------------
# Test 1: Unauthorized Access (Standard Admin tries to peek)
# -------------------------------------------------------------------
def test_settings_unauthorized(client):
    """Proves that an Admin without PERM_MANAGE_SETTINGS gets rejected."""

    with client.session_transaction() as sess:
        sess["uuid"] = "fake-admin-uuid"
        # Give them some admin rights, but NOT settings management
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.get("/admin/settings", follow_redirects=True)
    # The new decorator flashes this exact message
    assert b"Unauthorized: You lack the required portal permissions." in response.data


# -------------------------------------------------------------------
# Test 2: Successful Settings Update (Authorized Admin via AJAX)
# -------------------------------------------------------------------
def test_settings_update_success(client, db_cursor):
    """Proves an Admin with PERM_MANAGE_SETTINGS can UPSERT new settings via the AJAX endpoint."""

    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS  # Inject the exact right bit!

    # Target the NEW atomic AJAX endpoint
    response = client.post(
        "/admin/settings/update_single",
        data={"key": "cfg_grid_name", "value": "My Awesome Test Grid"},
        follow_redirects=True,
    )

    # 1. Verify the database was touched
    assert db_cursor.execute.called, "Database cursor execute was not called."

    # 2. Verify the exact UPSERT query was executed
    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    upsert_query_found = any("INSERT INTO config" in q for q in sql_queries)
    assert upsert_query_found, "Did not attempt to save settings to the database."

    # 3. Verify the JSON success response (AJAX returns JSON now, not HTML flash messages)
    assert b"success" in response.data


def test_settings_update_selectable_rejects_invalid(client):
    """Selectable settings only accept values listed in schema options."""
    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS

    response = client.post(
        "/admin/settings/update_single",
        data={"key": "region_owner_control_level", "value": "not_a_real_mode"},
    )
    assert response.status_code == 400
    assert b"not allowed" in response.data


def test_settings_update_selectable_accepts_valid(client, db_cursor):
    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS

    response = client.post(
        "/admin/settings/update_single",
        data={"key": "region_owner_control_level", "value": "owners"},
    )
    assert response.status_code == 200
    assert b"success" in response.data


# -------------------------------------------------------------------
# Test 3: Successful Settings Add (Authorized Admin)
# -------------------------------------------------------------------
def test_settings_add_success(client, db_cursor):
    """Proves an Admin with PERM_MANAGE_SETTINGS can inject a custom variable."""

    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS

    response = client.post(
        "/admin/settings/add",
        data={"new_key": "my_custom_key", "new_value": "My Custom Value"},
        follow_redirects=True,
    )

    inserted = False
    for call in db_cursor.execute.call_args_list:
        query = call[0][0]
        args = call[0][1] if len(call[0]) > 1 else []
        if "INSERT INTO config (config_key, config_value)" in query and args == (
            "my_custom_key",
            "My Custom Value",
        ):
            inserted = True
            break

    assert inserted, (
        "The INSERT query for the new custom setting was not executed correctly."
    )
    assert b"successfully added" in response.data


# -------------------------------------------------------------------
# Test 4: Successful Settings Delete (Authorized Admin)
# -------------------------------------------------------------------
def test_settings_delete_success(client, db_cursor):
    """Proves an Admin with PERM_MANAGE_SETTINGS can delete a setting and revert it."""

    with client.session_transaction() as sess:
        sess["uuid"] = "super-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS

    response = client.post(
        "/admin/settings/delete",
        data={"target_key": "grid_name"},
        follow_redirects=True,
    )

    deleted = False
    for call in db_cursor.execute.call_args_list:
        query = call[0][0]
        args = call[0][1] if len(call[0]) > 1 else []
        if "DELETE FROM config WHERE config_key =" in query and args == ("grid_name",):
            deleted = True
            break

    assert deleted, "The DELETE query was not executed correctly."
    assert b"deleted and reverted to system default" in response.data


# -------------------------------------------------------------------
# Registration Approvals
# -------------------------------------------------------------------
def test_approvals_unauthorized(client):
    with client.session_transaction() as sess:
        sess["uuid"] = "fake-admin-uuid"
        sess["permissions"] = PERM_MANAGE_SETTINGS

    response = client.get("/admin/approvals", follow_redirects=True)
    assert b"Unauthorized: You lack the required portal permissions." in response.data


def test_approvals_email_view(client, db_cursor):
    db_cursor.fetchall.return_value = []

    with client.session_transaction() as sess:
        sess["uuid"] = "approver-uuid"
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.get("/admin/approvals?view=email")
    assert response.status_code == 200
    assert b"Awaiting Email Verification" in response.data
    assert b"have not yet verified their email address" in response.data
    assert b"btn-danger btn-reject" not in response.data

    sql_queries = [call[0][0] for call in db_cursor.execute.call_args_list]
    assert any("WHERE status = %s" in q for q in sql_queries)
    status_args = next(
        call[0][1]
        for call in db_cursor.execute.call_args_list
        if "pending_registrations" in call[0][0]
    )
    assert status_args == ("pending_email",)


@patch("app.blueprints.admin.routes.send_verification_email")
def test_resend_verification_success(mock_send_email, client, db_cursor):
    db_cursor.rowcount = 1
    db_cursor.fetchone.return_value = {"email": "pending@example.com"}

    with client.session_transaction() as sess:
        sess["uuid"] = "approver-uuid"
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.post(
        "/admin/approvals/resend-verification",
        data={
            "uuid": "fake-uuid-1234",
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "success"
    mock_send_email.assert_called_once()
    assert mock_send_email.call_args[0][0] == "pending@example.com"

    update_calls = [
        call
        for call in db_cursor.execute.call_args_list
        if "verification_token" in call[0][0]
    ]
    assert update_calls, "Did not rotate the verification token."


@patch("app.blueprints.admin.routes.send_verification_email")
def test_resend_verification_wrong_status(mock_send_email, client, db_cursor):
    db_cursor.rowcount = 0
    db_cursor.fetchone.return_value = {"status": "pending_approval"}

    with client.session_transaction() as sess:
        sess["uuid"] = "approver-uuid"
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.post(
        "/admin/approvals/resend-verification",
        data={
            "uuid": "fake-uuid-1234",
        },
    )

    assert response.status_code == 400
    assert "not awaiting email verification" in response.json["message"]
    mock_send_email.assert_not_called()
