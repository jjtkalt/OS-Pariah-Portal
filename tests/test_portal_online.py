from unittest.mock import patch

from app.utils.schema import PERM_ONLINE_HUD_ALL, PERM_USER_LOOKUP


@patch("app.blueprints.comms.routes.get_online_snapshot")
def test_online_users_requires_login(mock_snapshot, client):
    response = client.get("/comms/online")
    assert response.status_code == 302
    assert "/auth/login" in response.location
    mock_snapshot.assert_not_called()


@patch("app.blueprints.comms.routes.get_online_snapshot")
def test_online_users_public_regions_only(mock_snapshot, client):
    mock_snapshot.return_value = {
        "total_online": 5,
        "users": [{"name": "Alice A", "region": "Welcome", "is_hg": False}],
        "show_all_regions": False,
    }

    with client.session_transaction() as sess:
        sess["uuid"] = "user-123"
        sess["user_level"] = 0
        sess["permissions"] = 0

    response = client.get("/comms/online")
    assert response.status_code == 200
    mock_snapshot.assert_called_once_with(False)
    assert b"Total Users Online" in response.data
    assert b"5" in response.data
    assert b"Alice A" in response.data
    assert b"public HUD-listable" in response.data


@patch("app.blueprints.comms.routes.get_online_snapshot")
def test_online_users_all_regions_with_permission(mock_snapshot, client):
    mock_snapshot.return_value = {
        "total_online": 5,
        "users": [
            {"name": "Alice A", "region": "Welcome", "is_hg": False},
            {"name": "Bob B", "region": "Private Estate", "is_hg": False},
        ],
        "show_all_regions": True,
    }

    with client.session_transaction() as sess:
        sess["uuid"] = "staff-123"
        sess["user_level"] = 201
        sess["permissions"] = PERM_ONLINE_HUD_ALL | PERM_USER_LOOKUP

    response = client.get("/comms/online")
    assert response.status_code == 200
    mock_snapshot.assert_called_once_with(True)
    assert b"all regions" in response.data
    assert b"Private Estate" in response.data


@patch("app.blueprints.api.routes._hud_listable_region_names")
@patch("app.blueprints.api.routes.fetch_all_online_users")
def test_get_online_snapshot_matches_hud_behavior(mock_fetch, mock_hud_names):
    from app.blueprints.api.routes import get_online_snapshot

    mock_fetch.return_value = [
        {"name": "Alice A", "region": "Welcome", "is_hg": False},
        {"name": "Bob B", "region": "Private Estate", "is_hg": False},
    ]
    mock_hud_names.return_value = {"welcome"}

    public = get_online_snapshot(False)
    assert public["total_online"] == 2
    assert len(public["users"]) == 1
    assert public["users"][0]["name"] == "Alice A"

    full = get_online_snapshot(True)
    assert full["total_online"] == 2
    assert len(full["users"]) == 2
