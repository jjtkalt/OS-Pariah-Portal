import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

import jwt
from cryptography.hazmat.primitives import serialization
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jwt.algorithms import RSAAlgorithm

from app.utils.auth_helpers import get_policy_decline_level
from app.utils.db import get_app_db, get_dynamic_config, get_robust_db
from app.utils.notifications import send_password_reset_email
from app.utils.password_resets import (
    create_password_reset_token,
    purge_expired_password_reset_tokens,
)
from app.utils.robust_api import update_user_password
from app.utils.schema import PERM_SUPER_ADMIN

auth_bp = Blueprint("auth", __name__)

# --- Turnstile & Standard Login ---


def verify_turnstile(response_token):
    """Verifies the Cloudflare Turnstile token."""
    if not response_token:
        return False
    secret = (get_dynamic_config("TURNSTILE_SECRET_KEY") or "").strip()
    if not secret:
        current_app.logger.warning(
            "TURNSTILE_SECRET_KEY is not configured; rejecting captcha."
        )
        return False
    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    data = urllib.parse.urlencode(
        {"secret": secret, "response": response_token}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data)

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode())
            return result.get("success", False)
    except Exception as e:
        current_app.logger.error(f"Turnstile verification failed: {e}")
        return False


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        password = request.form.get("password", "")

        if not first_name or not last_name or not password:
            flash("Please fill out all fields.", "error")
            return redirect(url_for("auth.login"))

        robust_conn = get_robust_db()
        try:
            with robust_conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT PrincipalID, userLevel
                    FROM UserAccounts
                    WHERE FirstName = %s AND LastName = %s
                """,
                    (first_name, last_name),
                )
                account = cursor.fetchone()

                if not account:
                    flash("Invalid avatar name or password.", "error")
                    return redirect(url_for("auth.login"))

                user_uuid = account["PrincipalID"]

                cursor.execute(
                    "SELECT passwordHash, passwordSalt FROM auth WHERE UUID = %s",
                    (user_uuid,),
                )
                auth_data = cursor.fetchone()

                if not auth_data:
                    flash("Invalid avatar name or password.", "error")
                    return redirect(url_for("auth.login"))

                pass_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
                hash_string = f"{pass_md5}:{auth_data['passwordSalt']}"
                final_hash = hashlib.md5(hash_string.encode("utf-8")).hexdigest()

                if final_hash == auth_data["passwordHash"]:
                    # --- THE GATEKEEPER / BOUNCER ---
                    decline_level = get_policy_decline_level()
                    ul = account["userLevel"]
                    if ul < 0 and ul != decline_level:
                        flash(
                            "Your account is currently locked, pending approval, or banned.",
                            "error",
                        )
                        return redirect(url_for("auth.login"))
                    # --------------------------------

                    session["uuid"] = user_uuid
                    session["name"] = f"{first_name} {last_name}"
                    session["user_level"] = account["userLevel"]
                    session["is_admin"] = account["userLevel"] >= 200

                    # --- OPTIMIZED RBAC HYDRATION ---
                    # Convention:
                    # - userLevel 0: normal user, never checks portal RBAC
                    # - userLevel 200: in-world admin WITHOUT portal RBAC (skip RBAC lookup)
                    # - userLevel 201: in-world admin that SHOULD load portal RBAC
                    # - other >0 staff tiers: load portal RBAC
                    ul_int = 0
                    try:
                        ul_int = int(account["userLevel"])
                    except (TypeError, ValueError):
                        ul_int = 0

                    if ul_int > 0 and ul_int != 200:
                        app_conn = get_app_db()
                        with app_conn.cursor() as p_cursor:
                            p_cursor.execute(
                                "SELECT permissions FROM user_rbac WHERE user_uuid = %s",
                                (user_uuid,),
                            )
                            rbac_row = p_cursor.fetchone()
                            if rbac_row:
                                # Normal login for an existing staff member
                                session["permissions"] = rbac_row["permissions"]
                            else:
                                # --- THE BOOTSTRAP LOGIC ---
                                # Only the explicitly configured ADMIN_UUID (migrate.py /
                                # PlatformStandards ADR-012) may receive an automatic
                                # Super Admin grant. userLevel >= 250 alone is not enough —
                                # that path was a privilege-escalation vector via set_level.
                                admin_uuid = (
                                    os.environ.get("ADMIN_UUID") or ""
                                ).strip()
                                if admin_uuid and user_uuid == admin_uuid:
                                    p_cursor.execute(
                                        "INSERT INTO user_rbac (user_uuid, permissions) VALUES (%s, %s)",
                                        (user_uuid, PERM_SUPER_ADMIN),
                                    )
                                    app_conn.commit()
                                    session["permissions"] = PERM_SUPER_ADMIN
                                    flash(
                                        "Bootstrap: Super Admin permissions granted for configured ADMIN_UUID.",
                                        "info",
                                    )
                                    current_app.logger.info(
                                        f"Bootstrap: Auto-granted PERM_SUPER_ADMIN to {first_name} {last_name}."
                                    )
                                else:
                                    # Staff tier with no assigned portal roles yet
                                    session["permissions"] = 0
                    else:
                        session["permissions"] = 0
                    # --------------------------------

                    # Check if they were trying to log in via an external OIDC app
                    if "next" in session:
                        next_url = session.pop("next")
                        # Only allow same-origin relative paths (block open redirects)
                        if (
                            isinstance(next_url, str)
                            and next_url.startswith("/")
                            and not next_url.startswith("//")
                        ):
                            return redirect(next_url)

                    if ul == decline_level:
                        flash(
                            "Your grid access is paused until you agree to the current policies.",
                            "info",
                        )
                        return redirect(url_for("user.policy_agreement"))

                    flash("Login successful!", "success")
                    return redirect(url_for("comms.news_feed"))
                else:
                    flash("Invalid avatar name or password.", "error")
                    return redirect(url_for("auth.login"))

        except Exception as e:
            current_app.logger.error(f"Login Error: {e}")
            flash("A database error occurred.", "error")
            return redirect(url_for("auth.login"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    user_uuid = session.get("uuid")
    if user_uuid:
        app_conn = get_app_db()
        try:
            with app_conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM oidc_auth_codes WHERE user_uuid = %s", (user_uuid,)
                )
                cursor.execute(
                    "DELETE FROM oidc_access_tokens WHERE user_uuid = %s", (user_uuid,)
                )
            app_conn.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to clear OIDC sessions on logout: {e}")

        session.clear()
        flash("You have been successfully and securely logged out.", "success")
    return redirect(url_for("auth.login"))


# --- OIDC / SSO Routes ---


def _oidc_key_path():
    """Prefer /etc/os-pariah/oidc_private.pem; fall back to install-root private.pem."""
    for path in (
        "/etc/os-pariah/oidc_private.pem",
        os.path.join(current_app.root_path, "..", "private.pem"),
    ):
        if os.path.isfile(path):
            return path
    return "/etc/os-pariah/oidc_private.pem"


def get_private_key():
    """Loads the RSA private key for signing JWTs."""
    with open(_oidc_key_path(), "rb") as f:
        return f.read()


def _lookup_oidc_client(client_id):
    """Return oidc_clients row or None. OIDC is disabled when no clients are registered."""
    if not client_id:
        return None
    app_conn = get_app_db()
    with app_conn.cursor() as cursor:
        cursor.execute(
            "SELECT client_id, client_secret, redirect_uri, app_name FROM oidc_clients WHERE client_id = %s",
            (client_id,),
        )
        return cursor.fetchone()


def _oidc_redirect_allowed(client_row, redirect_uri):
    """Exact match against the registered redirect_uri (comma-separated allowlist)."""
    if not client_row or not redirect_uri:
        return False
    allowed = [
        u.strip()
        for u in (client_row.get("redirect_uri") or "").split(",")
        if u.strip()
    ]
    return redirect_uri in allowed


@auth_bp.route("/.well-known/openid-configuration")
def oidc_discovery():
    """Standard OIDC Discovery document."""
    from app.utils.urls import absolute_portal_url

    domain = get_dynamic_config("portal_url")

    return jsonify(
        {
            "issuer": domain,
            "authorization_endpoint": absolute_portal_url("auth.authorize"),
            "token_endpoint": absolute_portal_url("auth.token"),
            "userinfo_endpoint": absolute_portal_url("auth.userinfo"),
            "jwks_uri": absolute_portal_url("auth.jwks"),
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )


@auth_bp.route("/.well-known/jwks.json")
def jwks():
    """Serves the Public Key so external apps can verify the JWT signatures."""
    try:
        with open(_oidc_key_path(), "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        public_key = private_key.public_key()

        # to_jwk returns a JSON string, so we must parse it into a dictionary first
        jwk_string = RSAAlgorithm.to_jwk(public_key)
        jwk_dict = json.loads(jwk_string)

        # Now we can safely add the necessary standard JWK attributes
        jwk_dict["kid"] = "os-pariah-key-1"
        jwk_dict["use"] = "sig"

        return jsonify({"keys": [jwk_dict]})
    except Exception as e:
        current_app.logger.error(f"Failed to generate JWKS: {e}")
        return jsonify({"error": "server_configuration_error"}), 500


@auth_bp.route("/authorize", methods=["GET"])
def authorize():
    """Step 1: Application requests authorization."""
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    state = request.args.get("state")
    nonce = request.args.get("nonce")

    if not client_id or not redirect_uri:
        return "Missing client_id or redirect_uri", 400

    client = _lookup_oidc_client(client_id)
    if not client:
        return (
            "OIDC client is not registered. Insert a row into oidc_clients before use.",
            400,
        )
    if not _oidc_redirect_allowed(client, redirect_uri):
        return "redirect_uri does not match the registered client", 400

    if "uuid" not in session:
        # Save only the relative authorize path (never an attacker-controlled host)
        session["next"] = request.full_path if request.query_string else request.path
        if session["next"].endswith("?"):
            session["next"] = session["next"][:-1]
        return redirect(url_for("auth.login"))

    from app.utils.auth_helpers import is_policy_decline_session

    if is_policy_decline_session():
        flash(
            "You must agree to the current grid policies before using external applications.",
            "info",
        )
        return redirect(url_for("user.policy_agreement"))

    auth_code = secrets.token_urlsafe(32)
    app_conn = get_app_db()

    try:
        with app_conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO oidc_auth_codes (code, user_uuid, client_id, nonce, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (auth_code, session["uuid"], client_id, nonce, int(time.time()) + 300),
            )
        app_conn.commit()
    except Exception as e:
        current_app.logger.error(f"OIDC Authorize Error: {e}")
        return "Database error", 500

    # Ensure the redirect_uri has the correct parameters attached
    parsed_url = urllib.parse.urlparse(redirect_uri)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params["code"] = [auth_code]
    if state:
        query_params["state"] = [state]

    new_query = urllib.parse.urlencode(query_params, doseq=True)
    final_url = parsed_url._replace(query=new_query).geturl()

    return redirect(final_url)


@auth_bp.route("/token", methods=["POST"])
def token():
    """Step 2: Exchange auth code for JWT and Access Token."""
    import hmac

    client_id = request.form.get("client_id")
    client_secret = request.form.get("client_secret") or ""
    code = request.form.get("code")
    redirect_uri = request.form.get("redirect_uri")

    if not client_id or not code:
        return jsonify({"error": "invalid_request"}), 400

    client = _lookup_oidc_client(client_id)
    if not client:
        return jsonify({"error": "invalid_client"}), 401
    if not hmac.compare_digest(client_secret, client.get("client_secret") or ""):
        return jsonify({"error": "invalid_client"}), 401
    if redirect_uri and not _oidc_redirect_allowed(client, redirect_uri):
        return jsonify({"error": "invalid_grant"}), 400

    app_conn = get_app_db()
    try:
        with app_conn.cursor() as cursor:
            # Atomic consume: DELETE … RETURNING is unavailable on older MariaDB;
            # use affected-row count after a single DELETE with the SELECT predicates.
            cursor.execute(
                "SELECT user_uuid, nonce FROM oidc_auth_codes WHERE code = %s AND client_id = %s AND expires_at > %s",
                (code, client_id, int(time.time())),
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "invalid_grant"}), 400

            cursor.execute(
                "DELETE FROM oidc_auth_codes WHERE code = %s AND client_id = %s",
                (code, client_id),
            )
            if cursor.rowcount != 1:
                app_conn.rollback()
                return jsonify({"error": "invalid_grant"}), 400
        app_conn.commit()
    except Exception as e:
        current_app.logger.error(f"OIDC Token Error: {e}")
        return jsonify({"error": "server_error"}), 500

    try:
        private_key = get_private_key()
    except OSError as e:
        current_app.logger.error(f"OIDC signing key missing after code consume: {e}")
        return jsonify({"error": "server_error"}), 500

    issued_at = int(time.time())
    expires_at = issued_at + 3600  # 1 hour
    domain = get_dynamic_config("portal_url")

    id_token_payload = {
        "iss": domain,
        "sub": row["user_uuid"],
        "aud": client_id,
        "exp": expires_at,
        "iat": issued_at,
    }
    if row["nonce"]:
        id_token_payload["nonce"] = row["nonce"]

    # Sign the token and include the kid header!
    id_token = jwt.encode(
        id_token_payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "os-pariah-key-1"},
    )

    access_token = secrets.token_urlsafe(32)

    with app_conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO oidc_access_tokens (token, user_uuid, client_id, expires_at) VALUES (%s, %s, %s, %s)",
            (access_token, row["user_uuid"], client_id, expires_at),
        )
    app_conn.commit()

    return jsonify(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": id_token,
        }
    )


@auth_bp.route("/userinfo", methods=["GET", "POST"])
def userinfo():
    """Step 3: Fetch user profile data using the Access Token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "invalid_request"}), 401

    access_token = auth_header.split(" ")[1]

    app_conn = get_app_db()
    with app_conn.cursor() as cursor:
        cursor.execute(
            "SELECT user_uuid FROM oidc_access_tokens WHERE token = %s AND expires_at > %s",
            (access_token, int(time.time())),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "invalid_token"}), 401
        user_uuid = row["user_uuid"]

    robust_conn = get_robust_db()
    with robust_conn.cursor() as cursor:
        cursor.execute(
            "SELECT FirstName, LastName FROM useraccounts WHERE PrincipalID = %s",
            (user_uuid,),
        )
        account = cursor.fetchone()
        if account:
            full_name = f"{account['FirstName']} {account['LastName']}"
            return jsonify(
                {
                    "sub": user_uuid,
                    "name": full_name,
                    "preferred_username": full_name,
                    "given_name": account["FirstName"],
                    "family_name": account["LastName"],
                }
            )

    return jsonify({"error": "user_not_found"}), 404


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        turnstile_response = request.form.get("cf-turnstile-response")

        if not verify_turnstile(turnstile_response):
            flash("Security check failed. Please try again.", "error")
            return redirect(url_for("auth.forgot_password"))

        # Security Best Practice: Generic success message prevents user enumeration
        generic_success_message = "If an account matches that avatar name, a password reset link has been sent to its registered email address."

        if not first_name or not last_name:
            flash(generic_success_message, "info")
            return redirect(url_for("auth.login"))

        robust_conn = get_robust_db()
        try:
            with robust_conn.cursor() as cursor:
                # Find the user's UUID and Email associated with this specific Avatar
                cursor.execute(
                    "SELECT PrincipalID, Email FROM useraccounts WHERE FirstName = %s AND LastName = %s",
                    (first_name, last_name),
                )
                account = cursor.fetchone()

                # Ensure the account exists AND actually has an email on file
                if account and account["Email"]:
                    user_uuid = account["PrincipalID"]
                    email = account["Email"]
                    app_conn = get_app_db()
                    token, _expires_at = create_password_reset_token(
                        app_conn, user_uuid, ttl_seconds=3600
                    )

                    send_password_reset_email(email, token)

        except Exception as e:
            current_app.logger.error(f"Forgot password error: {e}")

        flash(generic_success_message, "info")
        return redirect(url_for("auth.login"))

    site_key = get_dynamic_config("TURNSTILE_SITE_KEY")
    return render_template("auth/forgot.html", site_key=site_key)


@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    app_conn = get_app_db()
    purge_expired_password_reset_tokens(app_conn)

    # 1. Verify the token is valid and hasn't expired
    with app_conn.cursor() as cursor:
        cursor.execute(
            "SELECT user_uuid FROM password_resets WHERE token = %s AND expires_at > %s",
            (token, int(time.time())),
        )
        reset_record = cursor.fetchone()

    if not reset_record:
        flash(
            "That password reset link is invalid or has expired. Please request a new one.",
            "error",
        )
        return redirect(url_for("auth.forgot_password"))

    user_uuid = reset_record["user_uuid"]

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.reset_password", token=token))

        if update_user_password(user_uuid, new_password):
            # 3. Burn all outstanding tokens for this user (cleans up duplicates)
            with app_conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM password_resets WHERE user_uuid = %s", (user_uuid,)
                )
            app_conn.commit()

            flash(
                "Your password has been successfully updated. You may now log in.",
                "success",
            )
            return redirect(url_for("auth.login"))
        else:
            flash("Failed to update password. Please contact support.", "error")

    return render_template("auth/reset.html", token=token)
