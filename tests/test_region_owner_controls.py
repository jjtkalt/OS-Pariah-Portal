from unittest.mock import patch, MagicMock

from app.utils.schema import PERM_APPROVE_USERS


@patch("app.blueprints.regions.routes.get_dynamic_config", return_value="owners")
@patch("app.blueprints.regions.routes._user_owned_region_uuids", return_value={"test-uuid"})
@patch("app.blueprints.regions.routes.get_pariah_db")
def test_owner_can_toggle_hud_when_setting_allows(mock_db, _mock_owned, _mock_cfg, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {"hud_list_users": 0, "region_name": "Owner Region"}

    with client.session_transaction() as sess:
        sess["uuid"] = "owner-123"
        sess["permissions"] = 0

    response = client.post("/regions/toggle_hud_list/test-uuid")
    assert response.status_code == 302
    mock_cursor.execute.assert_any_call(
        "UPDATE region_configs SET hud_list_users = %s WHERE region_uuid = %s",
        (1, "test-uuid"),
    )


@patch("app.blueprints.regions.routes.get_dynamic_config", return_value="owners")
@patch("app.blueprints.regions.routes._user_owned_region_uuids", return_value=set())
@patch("app.blueprints.regions.routes.get_pariah_db")
def test_non_owner_denied_without_region_control(mock_db, _mock_owned, _mock_cfg, client):
    with client.session_transaction() as sess:
        sess["uuid"] = "random-123"
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.post("/regions/toggle_hud_list/test-uuid")
    assert response.status_code == 302
    mock_db.assert_not_called()


@patch("app.blueprints.regions.routes.get_dynamic_config", return_value="owners")
@patch("app.blueprints.regions.routes._user_owned_region_uuids", return_value={"test-uuid"})
@patch("app.blueprints.regions.routes.subprocess.Popen")
@patch("app.blueprints.regions.routes.get_pariah_db")
def test_owner_can_restart_region_when_setting_allows(mock_db, mock_popen, _mock_owned, _mock_cfg, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {"region_name": "Owner Region"}

    with client.session_transaction() as sess:
        sess["uuid"] = "owner-123"
        sess["permissions"] = 0

    response = client.post("/regions/control/restart/test-uuid")
    assert response.status_code == 302
    assert mock_popen.called

