from unittest.mock import patch, MagicMock

from app.utils.schema import PERM_APPROVE_USERS, PERM_MANAGE_REGIONS


@patch("app.blueprints.api.routes._hud_listable_region_names")
@patch("app.blueprints.api.routes.fetch_all_online_users")
def test_online_lister_public_filters_by_region_config(mock_fetch_users, mock_hud_names, client):
    mock_fetch_users.return_value = [
        {"name": "Alice A", "region": "Welcome", "is_hg": False},
        {"name": "Bob B", "region": "Private Estate", "is_hg": False},
    ]
    mock_hud_names.return_value = {"welcome"}

    response = client.get("/api/online")
    assert response.status_code == 200
    assert b"Total Online Users: 2" in response.data
    assert b"Alice A,Welcome" in response.data
    assert b"Bob B,Private Estate" not in response.data


@patch("app.blueprints.api.routes.has_admin_view_access", return_value=True)
@patch("app.blueprints.api.routes._hud_listable_region_names")
@patch("app.blueprints.api.routes.fetch_all_online_users")
def test_online_lister_admin_view_shows_all_regions(
    mock_fetch_users, mock_hud_names, _mock_admin, client
):
    mock_fetch_users.return_value = [
        {"name": "Alice A", "region": "Welcome", "is_hg": False},
        {"name": "Bob B", "region": "Private Estate", "is_hg": False},
    ]
    mock_hud_names.return_value = set()

    response = client.get("/api/online")
    assert response.status_code == 200
    assert b"Alice A,Welcome" in response.data
    assert b"Bob B,Private Estate" in response.data


@patch("app.blueprints.regions.routes.get_pariah_db")
def test_toggle_hud_list_unauthorized(mock_db, client):
    with client.session_transaction() as sess:
        sess["uuid"] = "user-123"
        sess["permissions"] = PERM_APPROVE_USERS

    response = client.post("/regions/toggle_hud_list/test-uuid")
    assert response.status_code == 302
    mock_db.assert_not_called()


@patch("app.blueprints.regions.routes.get_pariah_db")
def test_toggle_hud_list_success(mock_db, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {"hud_list_users": 0, "region_name": "Welcome"}

    with client.session_transaction() as sess:
        sess["uuid"] = "admin-123"
        sess["permissions"] = PERM_MANAGE_REGIONS

    response = client.post("/regions/toggle_hud_list/test-uuid")
    assert response.status_code == 302
    mock_cursor.execute.assert_any_call(
        "UPDATE region_configs SET hud_list_users = %s WHERE region_uuid = %s",
        (1, "test-uuid"),
    )
