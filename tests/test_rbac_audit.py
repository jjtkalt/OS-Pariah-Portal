from unittest.mock import MagicMock, patch

from app.utils.schema import (
    PERM_ADD_NOTES,
    PERM_SUPER_ADMIN,
    PERM_USER_LOOKUP,
    format_rbac_labels,
)


def test_format_rbac_labels_none():
    assert format_rbac_labels(0) == "(none)"


def test_format_rbac_labels_single_and_multiple():
    assert format_rbac_labels(PERM_USER_LOOKUP) == "Gatekeeper Lookup"
    labels = format_rbac_labels(PERM_ADD_NOTES | PERM_SUPER_ADMIN)
    assert "Add Staff Notes" in labels
    assert "Super Admin" in labels


@patch("app.blueprints.admin.user_mgmt.set_user_level")
@patch("app.blueprints.admin.user_mgmt.get_robust_db")
@patch("app.blueprints.admin.user_mgmt.log_audit_action")
def test_manage_roles_audit_logs_old_and_new(
    mock_audit, mock_get_robust, mock_set_level, client, db_cursor
):
    mock_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = (
        mock_cursor
    )
    mock_cursor.fetchone.return_value = {
        "FirstName": "Target",
        "LastName": "User",
        "userLevel": 0,
    }

    db_cursor.fetchone.side_effect = [{"permissions": PERM_USER_LOOKUP}] + [None] * 20

    with client.session_transaction() as sess:
        sess["uuid"] = "admin-uuid"
        sess["permissions"] = PERM_SUPER_ADMIN

    client.post(
        "/admin/users/target-uuid/roles",
        data={"permissions": [str(PERM_ADD_NOTES)]},
        follow_redirects=True,
    )

    mock_audit.assert_called_once()
    action, details = mock_audit.call_args[0]
    assert action == "Update Roles"
    assert "Changed from Gatekeeper Lookup to Add Staff Notes" in details
    assert mock_audit.call_args[1]["target_uuid"] == "target-uuid"
