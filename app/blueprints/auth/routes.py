import hashlib
import urllib.parse
import urllib.request
import json
import time
import secrets
import os
import jwt 
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives import serialization
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, flash, current_app, render_template, jsonify
from app.utils.db import get_robust_db, get_pariah_db, get_dynamic_config
from app.utils.robust_api import call_robust_api
from app.utils.notifications import send_password_reset_email

auth_bp = Blueprint('auth', __name__)

# --- Turnstile & Standard Login ---

def verify_turnstile(response_token):
    """Verifies the Cloudflare Turnstile token."""
    if not response_token:
        return False
    secret = get_dynamic_config('TURNSTILE_SECRET_KEY')
    url = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    data = urllib.parse.urlencode({'secret': secret, 'response': response_token}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            return result.get('success', False)
    except Exception as e:
        current_app.logger.error(f"Turnstile verification failed: {e}")
        return False

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        password = request.form.get('password', '')

        if not first_name or not last_name or not password:
            flash('Please fill out all fields.', 'error')
            return redirect(url_for('auth.login'))

        robust_conn = get_robust_db()
        try:
            with robust_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT PrincipalID, userLevel
                    FROM UserAccounts
                    WHERE FirstName = %s AND LastName = %s
                """, (first_name, last_name))
                account = cursor.fetchone()

                if not account:
                    flash('Invalid avatar name or password.', 'error')
                    return redirect(url_for('auth.login'))

                user_uuid = account['PrincipalID']

                cursor.execute("SELECT passwordHash, passwordSalt FROM auth WHERE UUID = %s", (user_uuid,))
                auth_data = cursor.fetchone()

                if not auth_data:
                    flash('Invalid avatar name or password.', 'error')
                    return redirect(url_for('auth.login'))

                pass_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()
                hash_string = f"{pass_md5}:{auth_data['passwordSalt']}"
                final_hash = hashlib.md5(hash_string.encode('utf-8')).hexdigest()

                if final_hash == auth_data['passwordHash']:

                    # --- THE GATEKEEPER / BOUNCER ---
                    if account['userLevel'] < 0:
                        flash('Your account is currently locked, pending approval, or banned.', 'error')
                        return redirect(url_for('auth.login'))
                    # --------------------------------

                    session['uuid'] = user_uuid
                    session['name'] = f"{first_name} {last_name}"
                    session['user_level'] = account['userLevel']
                    session['is_admin'] = account['userLevel'] >= 200

                    # Check if they were trying to log in via an external OIDC app
                    if 'next' in session:
                        next_url = session.pop('next')
                        return redirect(next_url)

                    flash('Login successful!', 'success')
                    return redirect(url_for('comms.news_feed'))
                else:
                    flash('Invalid avatar name or password.', 'error')
                    return redirect(url_for('auth.login'))

        except Exception as e:
            current_app.logger.error(f"Login Error: {e}")
            flash('A database error occurred.', 'error')
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    user_uuid = session.get('uuid')
    if user_uuid:
        pariah_conn = get_pariah_db()
        try:
            with pariah_conn.cursor() as cursor:
                cursor.execute("DELETE FROM oidc_auth_codes WHERE user_uuid = %s", (user_uuid,))
                cursor.execute("DELETE FROM oidc_access_tokens WHERE user_uuid = %s", (user_uuid,))
            pariah_conn.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to clear OIDC sessions on logout: {e}")
        
        session.clear()
        flash('You have been successfully and securely logged out.', 'success')
    return redirect(url_for('auth.login'))


# --- OIDC / SSO Routes ---

def get_private_key():
    """Loads the RSA private key for signing JWTs."""
    key_path = os.path.join(current_app.root_path, '..', 'private.pem')
    with open(key_path, 'rb') as f:
        return f.read()

@auth_bp.route('/.well-known/openid-configuration')
def oidc_discovery():
    """Standard OIDC Discovery document."""
    # The issuer domain must match what is configured in your portal settings
    domain = get_dynamic_config('portal_url')

    return jsonify({
        "issuer": domain,
        "authorization_endpoint": url_for('auth.authorize', _external=True),
        "token_endpoint": url_for('auth.token', _external=True),
        "userinfo_endpoint": url_for('auth.userinfo', _external=True),
        "jwks_uri": url_for('auth.jwks', _external=True),
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    })

@auth_bp.route('/.well-known/jwks.json')
def jwks():
    """Serves the Public Key so external apps can verify the JWT signatures."""
    key_path = os.path.join(current_app.root_path, '..', 'private.pem')

    try:
        with open(key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        public_key = private_key.public_key()

        # to_jwk returns a JSON string, so we must parse it into a dictionary first
        jwk_string = RSAAlgorithm.to_jwk(public_key)
        jwk_dict = json.loads(jwk_string)

        # Now we can safely add the necessary standard JWK attributes
        jwk_dict['kid'] = 'os-pariah-key-1'
        jwk_dict['use'] = 'sig'

        return jsonify({"keys": [jwk_dict]})
    except Exception as e:
        current_app.logger.error(f"Failed to generate JWKS: {e}")
        return jsonify({"error": "server_configuration_error"}), 500

@auth_bp.route('/authorize', methods=['GET'])
def authorize():
    """Step 1: Application requests authorization."""
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    nonce = request.args.get('nonce')

    if not client_id or not redirect_uri:
        return "Missing client_id or redirect_uri", 400

    if 'uuid' not in session:
        # Save the authorize request URL so we can bounce them back here after login
        session['next'] = request.url
        return redirect(url_for('auth.login'))

    auth_code = secrets.token_urlsafe(32)
    pariah_conn = get_pariah_db()
    
    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO oidc_auth_codes (code, user_uuid, client_id, nonce, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (auth_code, session['uuid'], client_id, nonce, int(time.time()) + 300)
            )
        pariah_conn.commit()
    except Exception as e:
        current_app.logger.error(f"OIDC Authorize Error: {e}")
        return "Database error", 500

    # Ensure the redirect_uri has the correct parameters attached
    parsed_url = urllib.parse.urlparse(redirect_uri)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params['code'] = [auth_code]
    if state:
        query_params['state'] = [state]
        
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    final_url = parsed_url._replace(query=new_query).geturl()
    
    return redirect(final_url)

@auth_bp.route('/token', methods=['POST'])
def token():
    """Step 2: Exchange auth code for JWT and Access Token."""
    client_id = request.form.get('client_id')
    code = request.form.get('code')

    if not client_id or not code:
        return jsonify({"error": "invalid_request"}), 400

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_uuid, nonce FROM oidc_auth_codes WHERE code = %s AND client_id = %s AND expires_at > %s", 
                (code, client_id, int(time.time()))
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "invalid_grant"}), 400
            
            cursor.execute("DELETE FROM oidc_auth_codes WHERE code = %s", (code,))
        pariah_conn.commit()
    except Exception as e:
        current_app.logger.error(f"OIDC Token Error: {e}")
        return jsonify({"error": "server_error"}), 500

    issued_at = int(time.time())
    expires_at = issued_at + 3600 # 1 hour
    domain = get_dynamic_config('portal_url')
    
    id_token_payload = {
        "iss": domain,
        "sub": row['user_uuid'],
        "aud": client_id,
        "exp": expires_at,
        "iat": issued_at
    }
    if row['nonce']: 
        id_token_payload["nonce"] = row['nonce']

    # Sign the token and include the kid header!
    id_token = jwt.encode(
        id_token_payload, 
        get_private_key(), 
        algorithm="RS256", 
        headers={"kid": "os-pariah-key-1"}
    )
    
    access_token = secrets.token_urlsafe(32)
    
    with pariah_conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO oidc_access_tokens (token, user_uuid, client_id, expires_at) VALUES (%s, %s, %s, %s)",
            (access_token, row['user_uuid'], client_id, expires_at)
        )
    pariah_conn.commit()

    return jsonify({
        "access_token": access_token, 
        "token_type": "Bearer", 
        "expires_in": 3600, 
        "id_token": id_token
    })

@auth_bp.route('/userinfo', methods=['GET', 'POST'])
def userinfo():
    """Step 3: Fetch user profile data using the Access Token."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "invalid_request"}), 401
        
    access_token = auth_header.split(' ')[1]
    
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT user_uuid FROM oidc_access_tokens WHERE token = %s AND expires_at > %s", (access_token, int(time.time())))
        row = cursor.fetchone()
        if not row: 
            return jsonify({"error": "invalid_token"}), 401
        user_uuid = row['user_uuid']

    robust_conn = get_robust_db()
    with robust_conn.cursor() as cursor:
        cursor.execute("SELECT FirstName, LastName FROM useraccounts WHERE PrincipalID = %s", (user_uuid,))
        account = cursor.fetchone()
        if account:
            full_name = f"{account['FirstName']} {account['LastName']}"
            return jsonify({
                "sub": user_uuid, 
                "name": full_name, 
                "preferred_username": full_name,
                "given_name": account['FirstName'],
                "family_name": account['LastName']
            })
            
    return jsonify({"error": "user_not_found"}), 404

@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        turnstile_response = request.form.get('cf-turnstile-response')

        if not verify_turnstile(turnstile_response):
            flash('Security check failed. Please try again.', 'error')
            return redirect(url_for('auth.forgot_password'))

        # Security Best Practice: Generic success message prevents user enumeration
        generic_success_message = "If an account matches that avatar name, a password reset link has been sent to its registered email address."

        if not first_name or not last_name:
            flash(generic_success_message, 'info')
            return redirect(url_for('auth.login'))

        robust_conn = get_robust_db()
        try:
            with robust_conn.cursor() as cursor:
                # Find the user's UUID and Email associated with this specific Avatar
                cursor.execute("SELECT PrincipalID, Email FROM useraccounts WHERE FirstName = %s AND LastName = %s", (first_name, last_name))
                account = cursor.fetchone()

                # Ensure the account exists AND actually has an email on file
                if account and account['Email']:
                    user_uuid = account['PrincipalID']
                    email = account['Email']
                    token = secrets.token_urlsafe(32)
                    expires_at = int(time.time()) + 3600 # 1 hour expiration

                    pariah_conn = get_pariah_db()
                    with pariah_conn.cursor() as p_cursor:
                        p_cursor.execute(
                            "INSERT INTO password_resets (token, user_uuid, expires_at) VALUES (%s, %s, %s)",
                            (token, user_uuid, expires_at)
                        )
                    pariah_conn.commit()

                    send_password_reset_email(email, token)

        except Exception as e:
            current_app.logger.error(f"Forgot password error: {e}")

        flash(generic_success_message, 'info')
        return redirect(url_for('auth.login'))

    site_key = get_dynamic_config('TURNSTILE_SITE_KEY')
    return render_template('auth/forgot.html', site_key=site_key)

@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    pariah_conn = get_pariah_db()

    # 1. Verify the token is valid and hasn't expired
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT user_uuid FROM password_resets WHERE token = %s AND expires_at > %s", (token, int(time.time())))
        reset_record = cursor.fetchone()

    if not reset_record:
        flash('That password reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user_uuid = reset_record['user_uuid']

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_password', token=token))

        # 2. Update the password safely via Robust API
        payload = {
            'PrincipalID': user_uuid,
            'Password': new_password
        }
        response_text = call_robust_api('setaccount', payload)

        if response_text and 'True' in response_text:
            # 3. Burn the token so it cannot be reused
            with pariah_conn.cursor() as cursor:
                cursor.execute("DELETE FROM password_resets WHERE token = %s", (token,))
            pariah_conn.commit()

            flash('Your password has been successfully updated. You may now log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Failed to update password. Please contact support.', 'error')

    return render_template('auth/reset.html', token=token)
