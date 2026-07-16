from unittest.mock import MagicMock, patch


@patch("app.utils.robust_api.requests.post")
def test_update_password_success(mock_post, client, app):
    """Proves the portal constructs the correct auth/plain URL and payload."""

    # Fake a successful 200 OK response from the OpenSim Auth service
    mock_response = MagicMock()
    mock_response.text = "<boolean>true</boolean>"
    mock_post.return_value = mock_response

    # Log in as a normal user
    with client.session_transaction() as sess:
        sess["uuid"] = "fake-user-uuid"

    # Submit the password change form
    response = client.post(
        "/user/profile/password",
        data={
            "new_password": "SuperSecretPassword123!",
            "confirm_password": "SuperSecretPassword123!",
        },
        follow_redirects=True,
    )

    # 1. Assert the request was actually made!
    assert mock_post.called, "The portal never tried to send the API request."

    # 2. Inspect EXACTLY what the portal tried to send
    called_url = mock_post.call_args[0][0]
    called_data = mock_post.call_args[1]["data"]

    assert called_url.endswith("/auth/plain"), f"Sent to wrong namespace: {called_url}"
    assert called_data["METHOD"] == "setpassword", "Used the wrong API method."
    assert called_data["PRINCIPAL"] == "fake-user-uuid", (
        "Did not send the correct user UUID."
    )
    assert called_data["PASSWORD"] == "SuperSecretPassword123!", (
        "Did not send the new password."
    )

    # 3. Assert the user got the success message
    assert b"Password updated successfully" in response.data


@patch("app.blueprints.auth.routes.update_user_password", return_value=True)
@patch("app.blueprints.auth.routes.verify_turnstile", return_value=True)
@patch("app.blueprints.auth.routes.send_password_reset_email")
@patch("app.blueprints.auth.routes.get_robust_db")
@patch(
    "app.utils.password_resets.secrets.token_urlsafe", return_value="fixed-reset-token"
)
def test_password_reset_workflow_mints_and_burns_token(
    mock_token,
    mock_get_robust,
    mock_send_email,
    mock_verify_turnstile,
    mock_update_user_password,
    client,
    app,
    db_cursor,
):
    """
    Verifies the complete reset workflow:
    - minting a token deletes expired + existing user tokens first
    - reset consumes token and deletes all remaining tokens for the user
    """
    # Robust lookup for forgot-password flow
    robust_cursor = MagicMock()
    mock_get_robust.return_value.cursor.return_value.__enter__.return_value = (
        robust_cursor
    )
    robust_cursor.fetchone.return_value = {
        "PrincipalID": "fake-user-uuid",
        "Email": "user@example.com",
    }

    # --- Step 1: request a reset token ---
    db_cursor.reset_mock()
    resp = client.post(
        "/auth/forgot",
        data={
            "first_name": "Test",
            "last_name": "Avatar",
            "cf-turnstile-response": "turnstile-ok",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    mock_send_email.assert_called_once_with("user@example.com", "fixed-reset-token")

    # The exact timestamp argument varies; assert by SQL order instead of full tuple equality.
    sqls = [c.args[0] for c in db_cursor.execute.call_args_list]
    assert sqls[0].startswith("DELETE FROM password_resets WHERE expires_at <=")
    assert sqls[1] == "DELETE FROM password_resets WHERE user_uuid = %s"
    assert (
        sqls[2]
        == "INSERT INTO password_resets (token, user_uuid, expires_at) VALUES (%s, %s, %s)"
    )

    # --- Step 2: use the token to reset the password ---
    # reset route first SELECTs the token record
    db_cursor.reset_mock()
    db_cursor.fetchone.return_value = {"user_uuid": "fake-user-uuid"}

    resp2 = client.post(
        "/auth/reset/fixed-reset-token",
        data={
            "new_password": "NewPass123!",
            "confirm_password": "NewPass123!",
        },
        follow_redirects=False,
    )
    assert resp2.status_code in (302, 303)
    assert mock_update_user_password.called

    sqls2 = [c.args[0] for c in db_cursor.execute.call_args_list]
    assert sqls2[0].startswith(
        "DELETE FROM password_resets WHERE expires_at <="
    )  # opportunistic purge
    assert sqls2[1].startswith("SELECT user_uuid FROM password_resets WHERE token = %s")
    assert "DELETE FROM password_resets WHERE user_uuid = %s" in sqls2
