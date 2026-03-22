# OS Pariah Portal

**The kittens are safe with me.** I take server load, resource management, and secure code extremely seriously. We will build this portal to be lean, asynchronous where it counts, and heavily cached at the CDN layer to protect your overworked Robust server.

Keeping the portal's state, configuration, and logs in a dedicated `OS_Pariah` database while limiting OpenSim interactions to Read-Only queries and atomic XMLRPC/HTTP calls is the definitive way to prevent table locking and keep the grid flying.

## Assessment of Current Assets

We have a fantastic foundation. Here is how we will adapt the existing work:

* OIDC Auth Bridge: We already have the core logic in Python handling login, logout, and API authorization. We will integrate this into the main portal, ensuring it safely handles endpoints like `/authorize`, `/token`, and `/userinfo` while reading user levels from OpenSim.

* Registration: We will migrate this from the current PHP SPA to Python 3.11. We will integrate Cloudflare Turnstile, implement the required Robust HTTP POST to port 8003, and build the configurable admin approval workflow.

* Help Tickets: The current Flask-based ticket app is a great starting point. We will merge its models into the `OS_Pariah` database and adapt its Matrix notification system.

* Gatekeeper & Bans: We will convert the PHP logic and bash script parsing  into a Python background worker or cron-triggered Flask CLI command that writes cleanly to the `OS_Pariah` DB.

* Online Lister: The current PHP online lister works, but polling the DB every 30-120 seconds for every user is brutal. We will implement a caching solution (likely using Flask-Caching with an in-memory or Redis backend) to serve this data instantly without touching Robust on every request.

## Proposed Development Roadmap

To ensure we don't break anything and keep the kittens purring, we will break this epic into five distinct stages.

### [Stage 1: Foundation and Architecture](#foundation-and-architecture)
* Initialize the Flask 3.11 application structure (Blueprints for routing).
* Set up the `Config.py` and dynamic database configuration system.
* Design the SQLAlchemy/PyMySQL models for the `OS_Pariah` database (Configuration, Policies, Custom User Notes).
* Implement a `central.css` file and build a responsive, tabbed HTML5 Jinja2 base template.

### [Stage 2: Core Identity and Registration](#core-identity-and-registration)
* Implement the Python OIDC Bridge for login/logout and JWT generation.
* Build the new Python Registration portal with Cloudflare Turnstile, email verification, and the Robust `createuser` API call.
* Build the Admin Approval Dashboard.

### [Stage 3: Support and Community](#support-and-community)
* Port and integrate the current Help Ticket system.
* Build the highly-cached Online Lister and Grid Monitor APIs.
* Implement the Communications / News Feed module.

### [Stage 4: Admin and Grid Operations](#admin-and-grid-operations)
* Convert Gatekeeper logging and Ban Management to Python.
* Build the User Control dashboard (name changes, passwords, inventory view).
* Implement the WebXML `Region.ini` generator and region management tools.

### [Stage 5: Polish and Documentation](#polish-and-documentation)
* Finalize CDN caching headers for Nginx.
* Complete the tabbed HTML documentation for Users, Admins, and Installers.

## Foundation and Architecture

Laying a solid foundation is the best way to ensure this portal remains fast, secure, and completely decoupled from your core OpenSimulator operations.

By moving elements like the OIDC state out of local SQLite files and keeping Gatekeeper logs out of the `Robust` database, we ensure your web application can scale across multiple Gunicorn workers without file-locking issues, all while keeping the OpenSim database strictly read-heavy.

Here is the proposed architecture for the `OS_Pariah` database and the Flask application structure.

### The `OS_Pariah` Database Schema

This dedicated MariaDB instance will house everything the portal needs to function independently. We will avoid any direct foreign keys to the `Robust` database, relying instead on OpenSim's `PrincipalID` (UUID) as a logical link.

#### System & Configuration
* `config`: Stores portal settings as key-value pairs (e.g., `require_invite_code`, `approval_required`) to allow admin toggles without code deploys.
* `policy_agreements`: Tracks `user_uuid`, `policy_version`, and `agreed_at` to pester users when Terms of Service or Privacy Policies update.

#### Authentication & OIDC (Migrated from SQLite )
* `oidc_clients`: Authorized applications (like Matrix or Discord).
* `oidc_auth_codes`: Temporary codes with short expirations.
* `oidc_access_tokens`: Active JWT/bearer tokens for API access.


#### Helpdesk Tickets (Migrated from `ticketapp.py`)
* `tickets`: The core ticket data (`user_uuid`, `category`, `subject`, `status`, etc.).
* `ticket_replies`: Linked to tickets for conversation tracking.
* `ticket_attachments`: Safely tracks uploaded files (`original_filename`, `stored_filename`, `mimetype`).

#### Security & Auditing
* `bans_master` & `bans_*`: The relational ban tables (`bans_username`, `bans_ip`, `bans_mac`, etc.) to support multi-vector banning.
* `user_notes`: Tracks staff warnings and notes (`user_uuid`, `admin_uuid`, `note`, `timestamp`).
* `gatekeeper_log`: Consolidated from the bash parser scripts to track `inbound_from`, `user_ip`, `user_mac`, and `user_host_id` directly in the Pariah DB.

### Flask Application Structure

To support an epic of this size, we will use the **Flask Application Factory** pattern combined with **Blueprints**. This keeps the code modular, makes it incredibly easy to cache specific routes via CDN, and ensures database connection pools are handled safely on startup.

```text
os_pariah_portal/
├── app/
│   ├── __init__.py          # App factory, CDN caching init, DB pool setup
│   ├── config.py            # Base configs, loads dynamic pairs from DB
│   ├── blueprints/
│   │   ├── auth/            # OIDC Provider, Login, Logout, Turnstile
│   │   ├── register/        # Registration flows, Email Verification
│   │   ├── tickets/         # User/Admin Helpdesk routes
│   │   ├── admin/           # Ban UI, User Notes, Approvals, Region Mgmt
│   │   ├── user/            # Passwords, Inventory, Profile, IAR backups
│   │   └── api/             # High-speed cached endpoints (Online Lister, Grid Monitor)
│   ├── utils/
│   │   ├── db.py            # PyMySQL PooledDB logic
│   │   ├── robust_api.py    # XMLRPC/HTTP wrappers for Robust calls
│   │   └── matrix.py        # Webhook generators for Matrix/Discord
│   ├── templates/
│   │   ├── base.html        # Main Jinja2 layout linking central.css
│   │   └── ...              # Module-specific templates
│   └── static/
│       ├── css/
│       │   └── central.css  # The centralized stylesheet
│       └── js/              # Async loaders, UI interactions
├── wsgi.py                  # Gunicorn entry point
└── requirements.txt         # Python 3.11 dependencies
```

**Modularity:** If the Helpdesk module fails, the OIDC login bridge stays up.

**Connection Pooling:** We will use `PooledDB` (as seen in your Auth script ) for both `OS_Pariah` and `Robust` connections to prevent connection thrashing under heavy load.

**Caching Readiness:** By separating the API Blueprint, we can easily inject memory-caching specifically for the Online Lister logic, preventing those 40+ database hits per minute.

### Bootstrap and Configuration

Building this core correctly ensures that no matter how much traffic hits the portal, the OpenSimulator grid will not even notice the load.

Here is the foundational bootstrap code. We will use the Flask Application Factory pattern. This ensures that when Gunicorn spins up multiple worker processes, each process safely initializes its own database connection pools, preventing deadlocks.

We are also carrying over the `ProxyFix` implementation to ensure Cloudflare and Nginx pass the correct client IPs to the application, which is critical for the Gatekeeper and Ban modules.

#### `app/config.py` (The Bootstrap Configuration)

This file handles the bare minimum required to get the application breathing: database credentials and security keys. All *operational* configurations (like `require_invite_code`) will be loaded dynamically from the `OS_Pariah` database later.

```python
import os

class Config:
    # Flask Security
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'super_secret_pariah_session_key')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # Caching Setup (Vital for the Online Lister)
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache') # Can swap to 'RedisCache' later
    CACHE_DEFAULT_TIMEOUT = 30 # Default 30 seconds

    # ---------------------------------------------------------
    # DATABASE 1: Robust (OpenSim) - STRICTLY READ-HEAVY
    # ---------------------------------------------------------
    ROBUST_DB_HOST = os.environ.get('ROBUST_DB_HOST', '127.0.0.1')
    ROBUST_DB_USER = os.environ.get('ROBUST_DB_USER', 'opensim_ro')
    ROBUST_DB_PASS = os.environ.get('ROBUST_DB_PASS', 'robust_password')
    ROBUST_DB_NAME = os.environ.get('ROBUST_DB_NAME', 'robust')

    # ---------------------------------------------------------
    # DATABASE 2: OS_Pariah (Portal) - READ/WRITE
    # ---------------------------------------------------------
    PARIAH_DB_HOST = os.environ.get('PARIAH_DB_HOST', '127.0.0.1')
    PARIAH_DB_USER = os.environ.get('PARIAH_DB_USER', 'pariah_user')
    PARIAH_DB_PASS = os.environ.get('PARIAH_DB_PASS', 'pariah_password')
    PARIAH_DB_NAME = os.environ.get('PARIAH_DB_NAME', 'os_pariah')
```

#### `app/__init__.py` (The Application Factory)

This file initializes Flask, sets up the caching mechanism, configures the dual database connection pools, and prepares the Blueprint structure for our modules.

```python
from flask import Flask, g
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_caching import Cache
from dbutils.pooled_db import PooledDB
import pymysql

# Initialize caching globally so Blueprints can import it
cache = Cache()

# Global variables to hold our DB pools at the application level
robust_pool = None
pariah_pool = None

def create_app(config_class='app.config.Config'):
    """Construct the core application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Plugins
    cache.init_app(app)

    # Crucial for Cloudflare/Nginx HTTPS and real IP detection
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Initialize Database Pools within the app context
    with app.app_context():
        init_db_pools(app)

    # Register Blueprints (We will build these out next)
    # from .blueprints.auth import auth_bp
    # from .blueprints.api import api_bp
    # app.register_blueprint(auth_bp, url_prefix='/auth')
    # app.register_blueprint(api_bp, url_prefix='/api')

    @app.teardown_appcontext
    def close_db_connections(exception):
        robust_conn = g.pop('robust_conn', None)
        if robust_conn is not None:
            robust_conn.close()
            
        pariah_conn = g.pop('pariah_conn', None)
        if pariah_conn is not None:
            pariah_conn.close()

    return app

def init_db_pools(app):
    global robust_pool, pariah_pool
    
    try:
        # Robust Pool (Optimized for fast, short read queries)
        robust_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            blocking=True,
            ping=1, # Ping the server to reconnect if dropped
            host=app.config['ROBUST_DB_HOST'],
            user=app.config['ROBUST_DB_USER'],
            password=app.config['ROBUST_DB_PASS'],
            database=app.config['ROBUST_DB_NAME'],
            cursorclass=pymysql.cursors.DictCursor
        )
        
        # Pariah Pool (For our portal's read/write operations)
        pariah_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            blocking=True,
            ping=1,
            host=app.config['PARIAH_DB_HOST'],
            user=app.config['PARIAH_DB_USER'],
            password=app.config['PARIAH_DB_PASS'],
            database=app.config['PARIAH_DB_NAME'],
            cursorclass=pymysql.cursors.DictCursor
        )
        app.logger.info("Successfully initialized dual MariaDB connection pools.")
    except Exception as e:
        app.logger.critical(f"CRITICAL: Failed to initialize database pools: {e}")
```

By attaching `close_db_connections` to Flask's `@app.teardown_appcontext`, we guarantee that even if a script errors out or a user drops their connection mid-load, the MariaDB connection is instantly released back to the `PooledDB` manager. No hanging connections, no memory leaks, and absolutely no dead kittens.

## Core Identity and Registration

This is where we strictly enforce our "Read-Heavy Robust, Read/Write Pariah" rule to ensure maximum performance and grid stability.

### Database Design

First, we will draft `app/utils/db.py`. This file provides safe, request-bound database connections and includes the logic to pull dynamic configurations directly from the `OS_Pariah` database, allowing us change grid settings on the fly without restarting Gunicorn.

#### The Database & Config Utilities (`app/utils/db.py`)

```python
from flask import g, current_app
# We import the pools initialized in the app factory
from app import robust_pool, pariah_pool

def get_robust_db():
    """
    Returns a read-only connection to the OpenSim Robust database.
    Reuses the connection if one already exists for the current request context.
    """
    if 'robust_conn' not in g:
        try:
            # Grab a connection from the pre-warmed PyMySQL pool
            g.robust_conn = robust_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get Robust DB connection: {e}")
            raise
    return g.robust_conn

def get_pariah_db():
    """
    Returns a read/write connection to the Pariah Portal database.
    """
    if 'pariah_conn' not in g:
        try:
            g.pariah_conn = pariah_pool.connection()
        except Exception as e:
            current_app.logger.error(f"Failed to get Pariah DB connection: {e}")
            raise
    return g.pariah_conn

def get_dynamic_config(key, default=None):
    """
    Fetches a configuration value from the OS_Pariah config table.
    In the production environment, this function should be wrapped with 
    the @cache.memoize decorator to prevent constant DB hits.
    """
    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
            result = cursor.fetchone()
            if result:
                return result['config_value']
            return default
    except Exception as e:
        current_app.logger.error(f"Error fetching config '{key}': {e}")
        return default
```

#### Migrating the OIDC Auth Bridge (`app/blueprints/auth/routes.py`)

Now that we have safe database access, we can migrate the Python OIDC OpenSim Bridge. We are moving away from local SQLite and pointing the OIDC state tracking (auth codes, access tokens) to the `OS_Pariah` database. We are also explicitly swapping Google's reCAPTCHA for Cloudflare's Turnstile. (You're welcome, Hudson)

```python
import hashlib
import urllib.parse
import urllib.request
import json
from flask import Blueprint, request, session, redirect, url_for, flash, current_app, render_template
from app.utils.db import get_robust_db, get_pariah_db, get_dynamic_config

auth_bp = Blueprint('auth', __name__)

def verify_turnstile(response_token):
    """Verifies the Cloudflare Turnstile token."""
    if not response_token:
        return False
    secret = current_app.config.get('TURNSTILE_SECRET_KEY') # Fetched from env
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
    if request.method == 'GET':
        if request.args.get('next'):
            session['next'] = request.args.get('next')
        # Pass the site key to the template for Turnstile rendering
        site_key = current_app.config.get('TURNSTILE_SITE_KEY') 
        return render_template('auth/login.html', site_key=site_key)

    # Verify Cloudflare Turnstile instead of reCAPTCHA
    turnstile_response = request.form.get('cf-turnstile-response')
    if not verify_turnstile(turnstile_response):
        flash('Security check failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    # 2. Process Username formatting
    username = request.form.get('username', '').strip()
    pwd = request.form.get('password')

    parts = username.split(maxsplit=1)
    if len(parts) == 2:
        first, last = parts[0], parts[1]
    elif len(parts) == 1:
        first, last = parts[0], "Resident"
    else:
        flash('Please enter your avatar name.', 'error')
        return redirect(url_for('auth.login'))

    # 3. Read-Only check against Robust Database
    robust_conn = get_robust_db()
    with robust_conn.cursor() as cursor:
        cursor.execute("SELECT PrincipalID as uuid, userLevel FROM useraccounts WHERE FirstName = %s AND LastName = %s", (first, last))
        account = cursor.fetchone()
        
        if account:
            cursor.execute("SELECT passwordHash, passwordSalt FROM auth WHERE UUID = %s", (account['uuid'],))
            auth = cursor.fetchone()
            
            if auth:
                # OpenSim password hashing logic
                md5_pwd = hashlib.md5(pwd.encode('utf-8')).hexdigest()
                check_str = md5_pwd + ":" + auth['passwordSalt']
                final_hash = hashlib.md5(check_str.encode('utf-8')).hexdigest()
                
                if final_hash == auth['passwordHash']:
                    # Password matches! Set session.
                    session['uuid'] = account['uuid']
                    session['name'] = f"{first} {last}"
                    session['is_admin'] = account['userLevel'] >= 200
                    session['user_level'] = account['userLevel']
                    
                    flash('Login successful.', 'success')
                    return redirect(session.pop('next', url_for('index')))

    flash('Invalid credentials.', 'error')
    return redirect(url_for('auth.login'))

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    user_uuid = session.get('uuid')
    if user_uuid:
        # Clean up OIDC state from Pariah DB (was SQLite)
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("DELETE FROM oidc_auth_codes WHERE user_uuid = %s", (user_uuid,))
            cursor.execute("DELETE FROM oidc_access_tokens WHERE user_uuid = %s", (user_uuid,))
        pariah_conn.commit()
        
        session.clear()
        flash('You have been successfully and securely logged out.', 'success')
    return redirect(url_for('auth.login'))
```

**No More SQLite Bottlenecks:** By shifting `oidc_auth_codes` and `oidc_access_tokens` to MariaDB (`get_pariah_db()`), we completely eliminate the file-locking issues that plague SQLite when multiple Nginx/Gunicorn workers try to read/write tokens simultaneously.

**Turnstile Integration:** We successfully ripped out Google reCAPTCHA and replaced it with Cloudflare Turnstile verification, keeping the stack lean and privacy-focused.

**Strictly Read-Only on Robust:** Notice that in the `login()` function, `robust_conn` only ever executes `SELECT` statements. The kittens are safe.

#### Completing the OIDC Endpoints (`app/blueprints/auth/routes.py`)

We are adapting the original `AuthOIDCApp.py` logic, but routing the read/write operations for state tracking into our dedicated `pariah_conn` pool.

This handles the OAuth2/OIDC flow safely.

```python
import time
import secrets
import jwt # PyJWT
from functools import wraps
from flask import jsonify, request, session, redirect, url_for, current_app

# --- Helper for API Auth ---
def get_private_key():
    """Loads the RSA private key for signing JWTs."""
    # In production, pull this path from the dynamic config or env or other centralized secrets store
    with open('private.pem', 'r') as f:
        return f.read()

# --- OIDC Routes ---
@auth_bp.route('/.well-known/openid-configuration')
def oidc_discovery():
    """Standard OIDC Discovery document."""
    domain = current_app.config.get('DOMAIN', 'https://example.com')
    return jsonify({
        "issuer": domain,
        "authorization_endpoint": f"{domain}/auth/authorize",
        "token_endpoint": f"{domain}/auth/token",
        "userinfo_endpoint": f"{domain}/auth/userinfo",
        "jwks_uri": f"{domain}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    })

@auth_bp.route('/authorize', methods=['GET'])
def authorize():
    """Step 1: Application requests authorization."""
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    nonce = request.args.get('nonce')

    if 'uuid' not in session:
        session['next'] = request.url
        return redirect(url_for('auth.login'))

    # Generate a secure auth code
    auth_code = secrets.token_urlsafe(32)
    pariah_conn = get_pariah_db()
    
    with pariah_conn.cursor() as cursor:
        # Save state to the Pariah DB
        cursor.execute(
            "INSERT INTO oidc_auth_codes (code, user_uuid, client_id, nonce, expires_at) VALUES (%s, %s, %s, %s, %s)",
            (auth_code, session['uuid'], client_id, nonce, int(time.time()) + 300)
        )
    pariah_conn.commit()

    return redirect(f"{redirect_uri}?{urllib.parse.urlencode({'code': auth_code, 'state': state})}")

@auth_bp.route('/token', methods=['POST'])
def token():
    """Step 2: Exchange auth code for JWT and Access Token."""
    client_id = request.form.get('client_id')
    code = request.form.get('code')

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Validate the auth code
        cursor.execute(
            "SELECT user_uuid, nonce FROM oidc_auth_codes WHERE code = %s AND client_id = %s AND expires_at > %s", 
            (code, client_id, int(time.time()))
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "invalid_grant"}), 400
        
        # Burn the code so it cannot be reused
        cursor.execute("DELETE FROM oidc_auth_codes WHERE code = %s", (code,))
    pariah_conn.commit()

    issued_at = int(time.time())
    expires_at = issued_at + 3600 # 1 hour expiration
    
    id_token_payload = {
        "iss": current_app.config.get('DOMAIN', 'https://example.com'),
        "sub": row['user_uuid'],
        "aud": client_id,
        "exp": expires_at,
        "iat": issued_at
    }
    if row['nonce']: 
        id_token_payload["nonce"] = row['nonce']

    id_token = jwt.encode(id_token_payload, get_private_key(), algorithm="RS256")
    access_token = secrets.token_urlsafe(32)
    
    with pariah_conn.cursor() as cursor:
        # Store the active access token
        cursor.execute(
            "INSERT INTO oidc_access_tokens (token, user_uuid, client_id, expires_at) VALUES (%s, %s, %s, %s)",
            (access_token, row['user_uuid'], client_id, expires_at)
        )
    pariah_conn.commit()

    return jsonify({"access_token": access_token, "token_type": "Bearer", "expires_in": 3600, "id_token": id_token})

@auth_bp.route('/userinfo', methods=['GET', 'POST'])
def userinfo():
    """Step 3: Fetch user profile data using the Access Token."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "invalid_request"}), 401
        
    access_token = auth_header.split(' ')[1]
    
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Verify token is valid and not expired
        cursor.execute("SELECT user_uuid FROM oidc_access_tokens WHERE token = %s AND expires_at > %s", (access_token, int(time.time())))
        row = cursor.fetchone()
        if not row: 
            return jsonify({"error": "invalid_token"}), 401
        user_uuid = row['user_uuid']

    # Read from the Robust DB to get the user's name
    robust_conn = get_robust_db()
    with robust_conn.cursor() as cursor:
        cursor.execute("SELECT FirstName, LastName FROM useraccounts WHERE PrincipalID = %s", (user_uuid,))
        account = cursor.fetchone()
        if account:
            full_name = f"{account['FirstName']} {account['LastName']}"
            return jsonify({"sub": user_uuid, "name": full_name, "preferred_username": full_name})
            
    return jsonify({"error": "user_not_found"}), 404
```

#### The Robust API Wrapper (`app/utils/robust_api.py`)

Now that identity is secure, we need a safe way to write to OpenSimulator for tasks like Registration and Approvals. We must *not* modify the OpenSim database directly to create users, but instead use a `createuser` HTTP POST call to the Robust private port (8003).

This wrapper isolates those HTTP calls, keeping them atomic and ensuring failures are handled gracefully without crashing the portal.

```python
import requests
import urllib.parse
from flask import current_app

def call_robust_api(method, payload):
    """
    Sends an HTTP POST to the Robust private port.
    Returns the raw text response or None on failure.
    """
    base_url = current_app.config.get('ROBUST_PRIVATE_URL', 'http://127.0.0.1:8003/accounts')
    payload['METHOD'] = method # e.g., 'createuser' or 'setaccount'
    
    try:
        # Robust expects standard form-encoded data for these XMLRPC-style handlers
        response = requests.post(base_url, data=payload, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Robust API call failed for {method}: {e}")
        return None

def create_robust_user(first_name, last_name, password, email):
    """
    Creates a new user via the Robust API.
    Returns the new user's UUID string if successful, or None.
    """
    payload = {
        'FirstName': first_name,
        'LastName': last_name,
        'Password': password,
        'Email': email
    }
    
    response_text = call_robust_api('createuser', payload)
    
    if response_text and '<PrincipalID>' in response_text:
        import re
        # Extract the UUID from the XML response
        match = re.search(r'<PrincipalID>(.*?)</PrincipalID>', response_text)
        if match:
            return match.group(1)
            
    return None

def set_user_level(uuid, level):
    """
    Updates a user's access level (e.g., -1 for pending, 0 for approved).
    """
    payload = {
        'PrincipalID': uuid,
        'UserLevel': level
    }
    response_text = call_robust_api('setaccount', payload)
    
    if response_text and 'True' in response_text: # Assuming Robust returns True on success
        return True
    return False
```

By enforcing API usage for write actions (like `createuser` and `setaccount` ), we ensure that OpenSimulator's internal caching and memory states remain synchronized. If we bypassed Robust and wrote directly to the `useraccounts` SQL table, OpenSim would not realize the user exists until it was restarted, leading to massive user confusion and... dead kittens.

### Registration Pipeline

This is where the magic happens. We are going to build a registration pipeline that is incredibly robust (pun intended), completely configurable on the fly, and fiercely protective of the grid's security.

Before we write the code, we need to address a critical security architecture decision.

**The Password Dilemma:** The OpenSimulator `createuser` API requires the user's desired password in plain text so it can properly hash and salt it internally. If we delay calling `createuser` until *after* an admin approves them (which could take days), we would be forced to store their plain-text password in our `OS_Pariah` database while they wait. **That is a massive security risk and an almost guaranteed kitten casualty.**

**The Safe Solution:** When a user submits a valid registration, we will call `createuser` to let Robust safely hash and store the password, but we will instantly call `setaccount` to set their `UserLevel` to `-1` (preventing login). We will then use the `OS_Pariah` database to track their verification/approval status. Once approved, the portal will update their `UserLevel` to `0`.

Here is the Registration Blueprint implementing your configurable workflows, Cloudflare Turnstile, and strict validation.

#### The Registration Blueprint (`app/blueprints/register/routes.py`)

```python
import uuid
import re
from flask import Blueprint, request, render_template, flash, redirect, url_for, current_app
from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.robust_api import create_robust_user, set_user_level
from app.blueprints.auth.routes import verify_turnstile # Reuse our Turnstile logic

register_bp = Blueprint('register', __name__)

@register_bp.route('/', methods=['GET', 'POST'])
def register():
    # Fetch dynamic configurations from OS_Pariah DB
    require_approval = get_dynamic_config('require_admin_approval', 'true') == 'true'
    require_other_info = get_dynamic_config('require_other_info', 'true') == 'true'
    require_invite_code = get_dynamic_config('require_invite_code', 'false') == 'true'

    if request.method == 'GET':
        site_key = current_app.config.get('TURNSTILE_SITE_KEY')
        return render_template(
            'register/index.html', 
            site_key=site_key,
            require_other_info=require_other_info,
            require_invite_code=require_invite_code
        )

    # --- 1. Security & Bot Check ---
    turnstile_response = request.form.get('cf-turnstile-response')
    if not verify_turnstile(turnstile_response):
        flash('Security check failed. Please ensure you are human.', 'error')
        return redirect(url_for('register.register'))

    # --- 2. Collect Mandatory Fields ---
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    inviter = request.form.get('inviter', '').strip()
    discord = request.form.get('discord_handle', '').strip() # Optional
    
    # --- 3. Policy & Age Verification ---
    policy_check = request.form.get('policy_check')
    age_check = request.form.get('age_check')
    if not policy_check or not age_check:
        flash('You must agree to the policies and attest you are 18+.', 'error')
        return redirect(url_for('register.register'))

    # --- 4. Dynamic Field Validation ---
    other_info = ""
    if require_other_info:
        other_info = request.form.get('other_info', '').strip()
        word_count = len(re.findall(r'\w+', other_info))
        if word_count < 30:
            flash('Your "Other Information" must be at least 30 words.', 'error')
            return redirect(url_for('register.register'))

    if require_invite_code:
        invite_code = request.form.get('invite_code', '').strip()
        if not validate_invite_code(invite_code): # Helper function (to be built)
            flash('Invalid or expired invite code.', 'error')
            return redirect(url_for('register.register'))

    # --- 5. Safely Create User in OpenSim (Level -1) ---
    new_uuid = create_robust_user(first_name, last_name, password, email)
    
    if not new_uuid:
        flash('Registration failed. The avatar name might already be taken or the grid is offline.', 'error')
        return redirect(url_for('register.register'))
        
    # Immediately lock the account by setting level to -1
    set_user_level(new_uuid, -1)

    # --- 6. Track Registration State in Pariah DB ---
    verification_token = uuid.uuid4().hex
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO pending_registrations 
               (user_uuid, email, inviter, discord, other_info, verification_token, requires_approval, status) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (new_uuid, email, inviter, discord, other_info, verification_token, require_approval, 'pending_email')
        )
    pariah_conn.commit()

    # --- 7. Dispatch Workflows ---
    send_verification_email(email, verification_token)
    
    # Webhook Notification to Matrix/Discord
    notify_staff_new_app(first_name, last_name, new_uuid, inviter, other_info)

    flash('Registration successful! Please check your email to verify your address.', 'success')
    return redirect(url_for('auth.login'))

# --- Helper Functions (Stubs for modularity) ---
def validate_invite_code(code):
    """Checks the Pariah DB to ensure the code is valid and unused."""
    pass

def send_verification_email(email, token):
    """Generates the unique link and emails the user."""
    pass

def notify_staff_new_app(first, last, uuid, inviter, info):
    """Sends a formatted JSON payload to the configured Matrix/Discord webhook."""
    pass
```
 
**Dynamic Configuration:** Notice how `get_dynamic_config` pulls flags like `require_admin_approval` directly from the database. We will build an admin page later with simple toggle switches, and the registration logic will instantly adapt without needing to restart the Python application.

**Data Safety:** By creating the user in Robust but locking them to Level `-1`, OpenSim handles the dangerous cryptography (password hashing) while our portal securely handles the workflow tracking.

**Bot Prevention:** We process Cloudflare Turnstile *before* we even look at the form data, immediately rejecting automated spam without wasting database queries.

### Admin Registration Dashboard

Instead of just pulling names and emails from Robust, we will query our `OS_Pariah` database so admins can actually read the "Other Information" and Discord handles submitted by the applicants.

Once an admin clicks "Approve," we will call Robust to update the `UserLevel` to `0`, send an approval email to the user, and fire off a webhook to Matrix.

#### The Admin Authorization Decorator (`app/utils/auth_helpers.py`)

First, a quick helper to protect our admin routes. If a user isn't Level 200+, they get bounced.

```python
from functools import wraps
from flask import session, redirect, url_for, flash

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('uuid') or not session.get('is_admin'):
            flash('Access denied. Grid Staff only.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
```

#### The Admin Blueprint (`app/blueprints/admin/routes.py`)

This blueprint handles the pending queues and the atomic AJAX approvals you designed.

```python
from flask import Blueprint, render_template, request, jsonify, current_app
from app.utils.auth_helpers import require_admin
from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.robust_api import set_user_level
from app.utils.notifications import send_matrix_discord_webhook, send_approval_email

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/approvals', methods=['GET'])
@require_admin
def pending_approvals():
    """Renders the dashboard of users waiting for Level 0 access."""
    pariah_conn = get_pariah_db()
    pending_users = []
    
    with pariah_conn.cursor() as cursor:
        # Fetch rich registration data directly from our portal DB
        cursor.execute("""
            SELECT user_uuid, email, inviter, discord, other_info, created_at 
            FROM pending_registrations 
            WHERE status = 'pending_approval' 
            ORDER BY created_at ASC
        """)
        pending_users = cursor.fetchall()
        
    return render_template('admin/approvals.html', users=pending_users)

@admin_bp.route('/approvals/approve', methods=['POST'])
@require_admin
def approve_user():
    """AJAX endpoint to approve a user and grant Level 0 access."""
    uuid = request.form.get('uuid')
    email = request.form.get('email')
    
    if not uuid:
        return jsonify({'status': 'error', 'message': 'Missing UUID.'}), 400

    # 1. ROBUST Call: setaccount (Update UserLevel to 0)
    # This safely replicates the previously used cURL call
    if set_user_level(uuid, 0):
        
        # 2. Update Pariah DB state
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("UPDATE pending_registrations SET status = 'approved' WHERE user_uuid = %s", (uuid,))
        pariah_conn.commit()

        # 3. Asynchronous Notifications
        grid_name = get_dynamic_config('grid_name', 'OS Pariah')
        
        # Email the user
        send_approval_email(email, grid_name)
        
        # Webhook to Discord/Matrix
        send_matrix_discord_webhook(
            title="✅ Account Approved",
            message=f"A pending user ({uuid}) has been approved and set to Level 0.",
            color=3066993 # Green
        )
        
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'ROBUST API failed. Is the grid offline?'}), 500
```

#### The Notification Engine (`app/utils/notifications.py`)

Notices can be sent to Matrix and Discord, configurable based on the portal settings.

```python
import requests
import urllib.request
import json
import uuid
from flask import current_app
from app.utils.db import get_dynamic_config

def send_matrix_discord_webhook(title, message, color=3447003, fields=None):
    """
    Fires off notifications to Discord and/or Matrix based on dynamic config.
    """
    discord_url = get_dynamic_config('discord_webhook_url')
    matrix_url = get_dynamic_config('matrix_webhook_url')
    matrix_token = get_dynamic_config('matrix_access_token')
    matrix_room = get_dynamic_config('matrix_room_id')

    # Discord payload
    if discord_url:
        discord_data = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "fields": fields or []
            }]
        }
        try:
            requests.post(discord_url, json=discord_data, timeout=5)
        except Exception as e:
            current_app.logger.error(f"Discord webhook failed: {e}")

    # Matrix payload
    if matrix_url and matrix_token and matrix_room:
        txn_id = str(uuid.uuid4())
        base_url = matrix_url.rstrip('/')
        url = f"{base_url}/_matrix/client/v3/rooms/{urllib.parse.quote(matrix_room)}/send/m.room.message/{txn_id}"
        
        # Simple text fallback for Matrix
        matrix_body = f"[{title}]\n{message}"
        payload = json.dumps({"msgtype": "m.text", "body": matrix_body}).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='PUT')
        req.add_header('Authorization', f'Bearer {matrix_token}')
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except Exception as e:
            current_app.logger.error(f"Matrix webhook failed: {e}")

def send_approval_email(to_email, grid_name):
    """Sends the welcome email to the user."""
    # In production, this should use smtplib or an API like SendGrid/Mailgun
    subject = f"Your {grid_name} Account is Approved!"
    body = f"Hello,\n\nYour application to {grid_name} has been approved by our staff! You may now log into the grid using the viewer of your choice.\n\nWelcome to the community!\n- The Staff"
    
    current_app.logger.info(f"Sending approval email to {to_email}: {subject}")
    # Actual SMTP logic goes here
```

**Security:** The admin endpoints are strictly protected by our OIDC-validated session. No hardcoded passwords.

**Resilience:** The notification engine uses timeouts (`timeout=5`). If Discord or Matrix goes down, your Admin Portal won't hang, freeze, or crash while waiting for a response. The user still gets approved.

**Decoupled Data:** By keeping the rich registration data (like `other_info`) in the `OS_Pariah` database, we avoid trying to shoehorn custom string data into OpenSim's strict `UserAccounts` table.

## Support and Community

### Online Lister

Having 20 users with HUDs polling the database every 30 seconds results in 40 calls a minute. That is a massive, unnecessary impact on a Robust database that is already working hard.

To fix this, we will use **Flask-Caching** (which we initialized in `__init__.py`). Instead of caching the final HTML output, we will cache the *raw database query results* for a configurable amount of time (e.g., 30 seconds). When a HUD requests the list, the portal pulls the cached list from memory, checks the user's permissions, filters out private regions if necessary, and returns the formatted text. **One database hit per 30 seconds, no matter if there are 10 or 1,000 users online.**

We are also completely removing the old, insecure override password. Instead, we will implement dynamic logic: checking for a logged-in admin session OR validating the `X-Forwarded-For` IP against authorized region hosts combined with the `X-Secondlife-Owner-Key` UUID.

#### The High-Speed API Blueprint (`app/blueprints/api/routes.py`)

Here is the code that will power the HUDs securely and efficiently.

```python
import re
from flask import Blueprint, request, session, current_app
from app import cache
from app.utils.db import get_robust_db, get_pariah_db, get_dynamic_config

api_bp = Blueprint('api', __name__, url_prefix='/api')

def has_admin_view_access():
    """
    Determines if the requester should see ALL regions (ignoring the public listable filter).
    Replaces the legacy override password.
    """
    # Condition 1: Logged into the portal as an Admin
    if session.get('uuid') and session.get('is_admin'):
        return True

    # Condition 2: Request comes from an authorized Region Host IP AND the UUID belongs to an Admin
    # X-Forwarded-For is safe to use here because we configured ProxyFix in __init__.py
    client_ip = request.remote_addr 
    owner_uuid = request.headers.get('X-Secondlife-Owner-Key')
    
    # Fetch configured region host IPs from OS_Pariah config
    region_hosts_str = get_dynamic_config('region_host_ips', '')
    authorized_ips = [ip.strip() for ip in region_hosts_str.split(',') if ip.strip()]

    if client_ip in authorized_ips and owner_uuid:
        # Verify if the owner_uuid has admin view access
        robust_conn = get_robust_db()
        with robust_conn.cursor() as cursor:
            cursor.execute("SELECT userLevel FROM useraccounts WHERE PrincipalID = %s", (owner_uuid,))
            account = cursor.fetchone()
            if account and account['userLevel'] >= 200:
                return True

    return False

@cache.cached(timeout=30, key_prefix='raw_online_users')
def fetch_all_online_users():
    """
    Queries the Robust database for all online users (Local and Hypergrid).
    This function's output is cached in memory for 30 seconds.
    """
    robust_conn = get_robust_db()
    users_online = []
    
    try:
        with robust_conn.cursor() as cursor:
            # 1. Local Users
            cursor.execute("""
                SELECT UA.FirstName, UA.LastName, r.regionName 
                FROM useraccounts UA 
                INNER JOIN presence p ON UA.PrincipalID = p.UserID 
                JOIN regions r ON r.uuid = p.RegionID
            """)
            for row in cursor.fetchall():
                # Clean up region name formatting as per original script
                region_use = re.sub(r"\s\d+$", "", row['regionName'])
                users_online.append({
                    'name': f"{row['FirstName']} {row['LastName']}",
                    'region': region_use,
                    'is_hg': False
                })

            # 2. Hypergrid Users
            cursor.execute("""
                SELECT 
                    SUBSTRING_INDEX(SUBSTRING_INDEX(g.UserId, ';', -1), ' ', 1) As FirstName, 
                    SUBSTRING_INDEX(SUBSTRING_INDEX(g.UserId, ';', -1), ' ', -1) As LastName, 
                    r.regionName 
                FROM griduser g 
                INNER JOIN presence p ON p.UserID = SUBSTRING(g.UserId, 1, 36) 
                JOIN regions r ON r.uuid = p.RegionID 
                WHERE LOCATE(';', g.UserId) <> 0
            """)
            for row in cursor.fetchall():
                region_use = re.sub(r"\s\d+$", "", row['regionName'])
                users_online.append({
                    'name': f"{row['FirstName']} {row['LastName']} (HG)",
                    'region': region_use,
                    'is_hg': True
                })
    except Exception as e:
        current_app.logger.error(f"Error fetching online users: {e}")
        
    # Sort alphabetically by name
    return sorted(users_online, key=lambda k: k['name'])


@api_bp.route('/online', methods=['GET'])
def online_lister():
    """
    The main endpoint for the in-world HUD and website widget.
    """
    # 1. Fetch the raw list from memory cache
    all_users = fetch_all_online_users()
    
    # 2. Check Permissions
    show_all = has_admin_view_access()
    
    # 3. Filter regions if not an admin
    filtered_users = []
    if show_all:
        filtered_users = all_users
    else:
        # Fetch the list of allowed public regions from OS_Pariah DB
        # Replaces the hardcoded ["Sandbox", "Sea ", "Welcome"] list
        listable_str = get_dynamic_config('listable_regions', 'Welcome, Sandbox')
        listable_regions = [r.strip().lower() for r in listable_str.split(',') if r.strip()]
        
        for user in all_users:
            if user['region'].lower() in listable_regions:
                filtered_users.append(user)

    # 4. Format Output exactly as the HUD expects (for now):
    # Total Online Users: X<br>
    # User Name,Region<br>
    output_lines = [f"Total Online Users: {len(filtered_users)}<br>"]
    for user in filtered_users:
        output_lines.append(f"{user['name']},{user['region']}<br>")

    # Return as raw text/html so the HUD parser doesn't break
    return "".join(output_lines), 200, {'Content-Type': 'text/html; charset=utf-8'}
```

**The Kitten Shield (Caching):** If 40 HUDs request this page at exactly the same second, the `fetch_all_online_users` function runs *exactly once*. The other 39 requests pull the list directly from Python's memory. The database load drops to near zero for this endpoint.

**Dynamic Region Control:** The old script had a hardcoded `$listableRegions` array. We have replaced this by pulling a comma-separated string from `get_dynamic_config('listable_regions')`. Region owners or portal admins can update this string in the portal dashboard, and the changes apply instantly without restarting the server.

**Secure Admin Overrides:** The legacy PHP `$_REQUEST['admin'] == $admin_override` parameter was vulnerable if intercepted or leaked. We now strictly check either the secure web session or verify the combination of the `X-Forwarded-For` Server IP against the `X-Secondlife-Owner-Key` UUID.

### Help Ticket System

The original `ticketapp.py` is well-structured and already handles file attachments and Cloudflare Turnstile.  We will fold this into a new `tickets` Blueprint. Instead of relying on a hardcoded `config.py` for Matrix tokens and SMTP settings, we will pull those dynamically from the `OS_Pariah` database using the `get_dynamic_config()` helper we built. This means if the Matrix bot token changes, a fast update of it in the portal UI, and the ticket system instantly uses the new token without a reboot.

We will also route all ticket reads, writes, and attachment metadata to `pariah_conn` to keep the Robust database completely isolated from support operations.  Just to cover the paranoia aspect.

#### The Tickets Blueprint (`app/blueprints/tickets/routes.py`)

Here is the integration of the ticket creation and viewing logic into the Flask Factory architecture.

```python
import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_from_directory
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.blueprints.auth.routes import verify_turnstile
from app.utils.notifications import send_matrix_discord_webhook

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

def allowed_file(filename):
    """Verifies file extensions against dynamic portal config."""
    allowed_exts = get_dynamic_config('allowed_attachment_exts', 'png,jpg,jpeg,gif,txt,pdf,log').split(',')
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts

@tickets_bp.route('/')
def index():
    """Displays the ticket dashboard for users and admins."""
    user_uuid = session.get('uuid')
    is_admin = session.get('is_admin', False)
    status_filter = request.args.get('status', 'All Open')
    tickets = []

    if user_uuid:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            if is_admin:
                if status_filter == 'All Open':
                    open_statuses = ('Open', 'In Progress', 'On Hold', 'Waiting on User', 'Waiting on Staff')
                    cursor.execute("SELECT * FROM tickets WHERE status IN %s ORDER BY updated_at DESC", (open_statuses,))
                elif status_filter == 'All Tickets':
                    cursor.execute("SELECT * FROM tickets ORDER BY updated_at DESC")
                elif status_filter:
                    cursor.execute("SELECT * FROM tickets WHERE status = %s ORDER BY updated_at DESC", (status_filter,))
            else:
                # Users only see their own tickets
                cursor.execute("SELECT * FROM tickets WHERE user_uuid = %s ORDER BY updated_at DESC", (user_uuid,))
            tickets = cursor.fetchall()

    site_key = current_app.config.get('TURNSTILE_SITE_KEY')
    return render_template('tickets/index.html', tickets=tickets, site_key=site_key, current_filter=status_filter)

@tickets_bp.route('/new', methods=['POST'])
def new_ticket():
    """Handles new ticket submissions with optional file attachments."""
    subject = request.form.get('subject')
    category = request.form.get('category')
    body = request.form.get('body')
    user_uuid = session.get('uuid')
    email = request.form.get('email')
    guest_ip = None

    # Protect against unauthenticated spam
    if not user_uuid:
        turnstile_response = request.form.get('cf-turnstile-response')
        if not verify_turnstile(turnstile_response):
            flash('Security check failed. Please try again.', 'error')
            return redirect(url_for('tickets.index'))
        guest_ip = request.headers.get('X-Real-IP', request.remote_addr)

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # 1. Create the Core Ticket
        cursor.execute(
            """INSERT INTO tickets (user_uuid, user_email, user_name, category, subject, body, guest_ip) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_uuid, email, session.get('name'), category, subject, body, guest_ip)
        )
        ticket_id = cursor.lastrowid

        # 2. Safely Process Attachments
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename != '' and allowed_file(file.filename):
                original_name = secure_filename(file.filename)
                ext = original_name.rsplit('.', 1)[1].lower()
                stored_name = f"{uuid.uuid4().hex}.{ext}"

                upload_folder = get_dynamic_config('upload_folder_path', '/tmp/pariah_uploads')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, stored_name))

                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                
                cursor.execute(
                    """INSERT INTO ticket_attachments 
                       (ticket_id, original_filename, stored_filename, mimetype, file_size) 
                       VALUES (%s, %s, %s, %s, %s)""",
                    (ticket_id, original_name, stored_name, file.mimetype, file_size)
                )
    pariah_conn.commit()

    # 3. Asynchronous Webhook Notification
    sender = session.get('name', email)
    send_matrix_discord_webhook(
        title=f"🆕 New Ticket #{ticket_id}",
        message=f"[{category}] opened by {sender}: {subject}",
        color=16753920 # Orange for tickets
    )

    flash('Ticket submitted successfully.', 'success')
    return redirect(url_for('tickets.index'))

@tickets_bp.route('/<int:ticket_id>')
def view_ticket(ticket_id):
    """Displays a specific ticket and its replies."""
    user_uuid = session.get('uuid')
    is_admin = session.get('is_admin', False)
    admins = []

    if not user_uuid:
        flash('You must be logged in to view tickets.', 'error')
        return redirect(url_for('auth.login'))

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            flash('Ticket not found.', 'error')
            return redirect(url_for('tickets.index'))
            
        # Permission check: Must be admin or the ticket owner
        if not is_admin and ticket['user_uuid'] != user_uuid:
            flash('Access denied. You do not own this ticket.', 'error')
            return redirect(url_for('tickets.index'))

        cursor.execute("SELECT * FROM ticket_replies WHERE ticket_id = %s ORDER BY created_at ASC", (ticket_id,))
        replies = cursor.fetchall()

        cursor.execute("SELECT * FROM ticket_attachments WHERE ticket_id = %s", (ticket_id,))
        attachments = cursor.fetchall()

    # If Admin, fetch the list of other admins from Robust so they can delegate the ticket
    if is_admin:
        robust_conn = get_robust_db()
        with robust_conn.cursor() as r_cursor:
            r_cursor.execute("SELECT PrincipalID, FirstName, LastName FROM useraccounts WHERE userLevel >= 200 ORDER BY FirstName ASC")
            for row in r_cursor.fetchall():
                admin_name = f"{row['FirstName']} {row['LastName']}" if row['LastName'] != 'Resident' else row['FirstName']
                admins.append({'uuid': row['PrincipalID'], 'name': admin_name})

    return render_template('tickets/ticket_view.html', ticket=ticket, replies=replies, admins=admins, attachments=attachments)
```

**Isolated IO (File Storage):** Attachments are uploaded to a hidden folder (`get_dynamic_config('upload_folder_path')`), renamed to a secure UUID `stored_name` , and only delivered to the user via Flask's `send_from_directory` after an RBAC permission check . There is zero chance of malicious scripts executing in the web root.

**Unified Notifications:** By swapping out the static `send_matrix_notification`  with our unified `send_matrix_discord_webhook`, tickets now integrate seamlessly into the configurable notification architecture we built for user registrations.

**Data Integrity:** Ticket state, replies, and attachment metadata are strictly stored in `OS_Pariah`. The only interaction with OpenSimulator is a fast `SELECT` to grab the current list of level 200+ admins for delegation.

The ticket API (for external bots creating tickets) and the reply/status-change functions follow this exact same pattern.

## Admin and Grid Operations

The grid is currently controlled by a set of bash scripts.  While functional, bringing the control and care of the grid into a central UI will allow for a much more accessible infrastructure.

### User Control Dashboard

Currently we have a bash script that parses Robust logs and drops the data into four distinct Gatekeeper tables (`gatekeeper_from`, `gatekeeper_ip`, `gatekeeper_mac`, `gatekeeper_host_id` ), alongside a comprehensive ban schema (`bans_master`, `bans_username`, `bans_ip`, etc. ).

We are going to merge this logic into the Flask `admin` Blueprint. We will house all these tracking tables in the `OS_Pariah` database to keep the Robust database fast. Most importantly, we will actively enforce bans at the user level by setting their `userlevel` to a negative number using our safe `set_user_level` API wrapper, rather than just keeping a passive record.

#### The User Management Blueprint (`app/blueprints/admin/user_mgmt.py`)

Here is the Flask implementation for Gatekeeper Lookups, User Notes, and Active Banning.

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils.db import get_pariah_db, get_robust_db
from app.utils.auth_helpers import require_admin
from app.utils.robust_api import set_user_level

user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/admin/users')

@user_mgmt_bp.route('/lookup', methods=['GET'])
@require_admin
def gatekeeper_lookup():
    """
    Replaces GatekeeperLookup.php.
    Cross-references IP, MAC, HostID, and Inbound From to find alt accounts.
    """
    search_type = request.args.get('type', 'exact_user') # Default search
    query_raw = request.args.get('q', '').strip()
    
    if not query_raw:
        return render_template('admin/lookup.html', results=None)

    pariah_conn = get_pariah_db()
    uuids = set()
    
    # Map search types to their respective tables
    table_map = {
        'ip': ('gatekeeper_ip', 'user_ip'),
        'mac': ('gatekeeper_mac', 'user_mac'),
        'host_id': ('gatekeeper_host_id', 'user_host_id'),
        'from': ('gatekeeper_from', 'inbound_from')
    }

    try:
        with pariah_conn.cursor() as cursor:
            if search_type == 'exact_user':
                # Search across all tables for the exact username
                for table in ['gatekeeper_ip', 'gatekeeper_mac', 'gatekeeper_from', 'gatekeeper_host_id']:
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE user_name = %s", (query_raw,))
                    uuids.update([row['user_uuid'] for row in cursor.fetchall()])
            
            elif search_type in table_map:
                # Search specific hardware/network identifier
                table, column = table_map[search_type]
                cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE {column} = %s", (query_raw,))
                uuids.update([row['user_uuid'] for row in cursor.fetchall()])
            
            elif search_type == 'uuid':
                uuids.add(query_raw)

            # Once we have the linked UUIDs, fetch all known identifiers for them
            results = {
                'usernames': set(), 'ips': set(), 'macs': set(), 'host_ids': set()
            }
            if uuids:
                format_strings = ','.join(['%s'] * len(uuids))
                uuid_tuple = tuple(uuids)
                
                # Fetch linked IPs
                cursor.execute(f"SELECT DISTINCT user_ip FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['ips'].update([r['user_ip'] for r in cursor.fetchall() if r['user_ip']])
                
                # Fetch linked MACs
                cursor.execute(f"SELECT DISTINCT user_mac FROM gatekeeper_mac WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['macs'].update([r['user_mac'] for r in cursor.fetchall() if r['user_mac']])

                # Fetch linked Host IDs
                cursor.execute(f"SELECT DISTINCT user_host_id FROM gatekeeper_host_id WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['host_ids'].update([r['user_host_id'] for r in cursor.fetchall() if r['user_host_id']])

    except Exception as e:
        current_app.logger.error(f"Gatekeeper lookup error: {e}")
        flash('Database query failed.', 'error')

    return render_template('admin/lookup.html', query=query_raw, search_type=search_type, results=results, uuids=list(uuids))


@user_mgmt_bp.route('/<uuid>/notes', methods=['GET', 'POST'])
@require_admin
def user_notes(uuid):
    """
    Manages staff warnings and notes for a specific user.
    Track warnings tied to user records.
    """
    pariah_conn = get_pariah_db()
    
    if request.method == 'POST':
        note_body = request.form.get('note', '').strip()
        admin_uuid = session.get('uuid')
        
        if note_body:
            with pariah_conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)",
                    (uuid, admin_uuid, note_body)
                )
            pariah_conn.commit()
            flash('Note added successfully.', 'success')
            return redirect(url_for('user_mgmt.user_notes', uuid=uuid))

    # Fetch existing notes
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM user_notes WHERE user_uuid = %s ORDER BY created_at DESC", (uuid,))
        notes = cursor.fetchall()
        
    return render_template('admin/user_notes.html', target_uuid=uuid, notes=notes)


@user_mgmt_bp.route('/bans/create', methods=['GET', 'POST'])
@require_admin
def create_ban():
    """
    Replaces BanRecords.php creation logic and implements active API enforcement.
    """
    if request.method == 'GET':
        return render_template('admin/create_ban.html')

    reason = request.form.get('reason', '').strip()
    ban_type = request.form.get('type', 'account').strip()
    
    # Process multi-line inputs
    uuids = [u.strip() for u in request.form.get('uuids', '').split('\n') if u.strip()]
    ips = [i.strip() for i in request.form.get('ips', '').split('\n') if i.strip()]
    macs = [m.strip() for m in request.form.get('macs', '').split('\n') if m.strip()]
    hostids = [h.strip() for h in request.form.get('hostids', '').split('\n') if h.strip()]

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # 1. Insert into bans_master
            cursor.execute("INSERT INTO bans_master (reason, type) VALUES (%s, %s)", (reason, ban_type))
            ban_id = cursor.lastrowid

            # 2. Insert hardware/network bans
            for ip in ips:
                cursor.execute("INSERT INTO bans_ip (banid, ip) VALUES (%s, %s)", (ban_id, ip))
            for mac in macs:
                cursor.execute("INSERT INTO bans_mac (banid, mac) VALUES (%s, %s)", (ban_id, mac))
            for hostid in hostids:
                cursor.execute("INSERT INTO bans_host_id (banid, hostid) VALUES (%s, %s)", (ban_id, hostid))

            # 3. Insert UUID bans AND actively enforce them
            for uuid in uuids:
                # Store the UUID ban record
                cursor.execute("INSERT INTO bans_uuid (banid, uuid) VALUES (%s, %s)", (ban_id, uuid))
                
                # ACTIVE ENFORCEMENT: Set user level to a negative number
                # We use -5 for permanently banned users to distinguish from -1 (pending approval)
                if ban_type in ['account', 'mixed']:
                    set_user_level(uuid, -5)
                    current_app.logger.info(f"Actively enforced ban on UUID {uuid} via Robust API.")

        pariah_conn.commit()
        flash(f'Ban ID {ban_id} created and enforced successfully.', 'success')
    except Exception as e:
        current_app.logger.error(f"Ban creation failed: {e}")
        flash('Failed to create ban. Check logs.', 'error')

    return redirect(url_for('user_mgmt.gatekeeper_lookup'))
```

**Automated Enforcement:** Instead of just recording a ban and hoping the admin remembers to manually lock the account, the portal actively calls the OpenSim Robust API (`set_user_level(uuid, -5)`) to implement the ban at the user level the instant you click "Submit".

**Database Integrity:** We maintain the `bans_master` and child tables schema but execute them inside a unified PyMySQL transaction block (`pariah_conn.commit()`). If one piece of the ban fails to write, the whole transaction safely rolls back.

**No File Locking:** By moving Gatekeeper lookups to the `OS_Pariah` database, we completely avoid locking up OpenSim log files while admins are actively searching for alt accounts.

*(Note: The actual background ingestion of the Robust log file into these SQL tables can be handled by a simple `flask cli` script that runs via cron, ensuring it never collides with web traffic).*

### Region Management

The attempt to completely eliminate the need to manually edit `Region.ini` files across multiple servers.

OpenSimulator expects a very specific Nini XML format. By moving this configuration into the `OS_Pariah` database, grid administrators can spin up, move, or reconfigure regions entirely from the web portal. When an OpenSim region server starts, it will simply make an HTTP call to our portal, fetch its XML configuration, and boot up.

#### The Region Management Blueprint (`app/blueprints/regions/routes.py`)

This blueprint serves two purposes: it provides the public-facing (but IP-restricted) API for the OpenSim servers to fetch their XML, and it provides the protected admin interface to edit those settings.

```python
import dicttoxml
from flask import Blueprint, render_template, request, Response, flash, redirect, url_for, current_app
from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.auth_helpers import require_admin

regions_bp = Blueprint('regions', __name__, url_prefix='/regions')

# --- 1. The WebXML API for OpenSim Servers ---

@regions_bp.route('/api/config/<region_uuid>.xml', methods=['GET'])
def get_region_xml(region_uuid):
    """
    Serves the dynamic Nini XML configuration to the OpenSimulator region server.
    """
    # Security: Verify the request is coming from an authorized Region Host IP
    client_ip = request.remote_addr
    region_hosts_str = get_dynamic_config('region_host_ips', '')
    authorized_ips = [ip.strip() for ip in region_hosts_str.split(',') if ip.strip()]

    if client_ip not in authorized_ips:
        current_app.logger.warning(f"Unauthorized WebXML request from {client_ip} for region {region_uuid}")
        return Response("<error>Unauthorized</error>", status=403, mimetype='application/xml')

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # Fetch the base region info
            cursor.execute("SELECT region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
            region_info = cursor.fetchone()
            
            if not region_info:
                return Response("<error>Region Not Found</error>", status=404, mimetype='application/xml')

            # Fetch all key-value settings for this region
            cursor.execute("SELECT setting_key, setting_value FROM region_settings WHERE region_uuid = %s", (region_uuid,))
            settings = cursor.fetchall()

        # Build the Nini XML structure strictly matching the provided example
        xml_output = [f'<Nini>\n  <Section Name="{region_info["region_name"]}">']
        
        # Ensure RegionUUID is always present, cause... yeah
        xml_output.append(f'    <Key Name="RegionUUID" Value="{region_uuid}" />')
        
        for setting in settings:
            # Ignore RegionUUID if it was accidentally duplicated in the settings table
            if setting['setting_key'] != 'RegionUUID':
                xml_output.append(f'    <Key Name="{setting["setting_key"]}" Value="{setting["setting_value"]}" />')
        
        xml_output.append('  </Section>\n</Nini>')
        final_xml = "\n".join(xml_output)

        return Response(final_xml, mimetype='application/xml')

    except Exception as e:
        current_app.logger.error(f"Failed to generate WebXML for {region_uuid}: {e}")
        return Response("<error>Internal Server Error</error>", status=500, mimetype='application/xml')


# --- 2. The Admin Interface for Region Management ---

@regions_bp.route('/manage', methods=['GET'])
@require_admin
def manage_regions():
    """
    Dashboard to list and manage all regions stored in the portal. This probably needs review. Including the example from OpenSimulator, but there are items either listed that we don't want to track, or items that we should track (EG: estate info?)
    """
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            SELECT rc.region_uuid, rc.region_name, rs.setting_value as internal_port 
            FROM region_configs rc
            LEFT JOIN region_settings rs ON rc.region_uuid = rs.region_uuid AND rs.setting_key = 'InternalPort'
            ORDER BY rc.region_name ASC
        """)
        regions = cursor.fetchall()
        
    return render_template('admin/manage_regions.html', regions=regions)

@regions_bp.route('/edit/<region_uuid>', methods=['GET', 'POST'])
@require_admin
def edit_region(region_uuid):
    """Allows admins to update location coordinates, ports, and limits."""
    pariah_conn = get_pariah_db()
    
    if request.method == 'POST':
        # Collect standard OpenSim region settings
        settings_to_update = {
            'Location': request.form.get('Location'),
            'InternalAddress': request.form.get('InternalAddress', '0.0.0.0'),
            'InternalPort': request.form.get('InternalPort'),
            'AllowAlternatePorts': request.form.get('AllowAlternatePorts', 'False'), # This must always be False
            'ExternalHostName': request.form.get('ExternalHostName'),
            'MaxPrims': request.form.get('MaxPrims', '15000'),
            'MaxAgents': request.form.get('MaxAgents', '40'),
            'RegionType': request.form.get('RegionType', '0'),
            'SizeX': request.form.get('SizeX', '256'),
            'SizeY': request.form.get('SizeY', '256'),
            'MaptileStaticUUID': request.form.get('MaptileStaticUUID', '00000000-0000-0000-0000-000000000000') # This isn't needed as we generate dynamically
        }

        try:
            with pariah_conn.cursor() as cursor:
                # Update region name if changed
                new_name = request.form.get('region_name')
                if new_name:
                    cursor.execute("UPDATE region_configs SET region_name = %s WHERE region_uuid = %s", (new_name, region_uuid))

                # Upsert all settings
                for key, value in settings_to_update.items():
                    if value: # Only update if a value was provided
                        cursor.execute("""
                            INSERT INTO region_settings (region_uuid, setting_key, setting_value) 
                            VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                        """, (region_uuid, key, value))
            
            pariah_conn.commit()
            flash('Region configuration updated successfully.', 'success')
        except Exception as e:
            current_app.logger.error(f"Failed to update region config: {e}")
            flash('Database update failed.', 'error')

        return redirect(url_for('regions.edit_region', region_uuid=region_uuid))

    # GET request: Load current settings
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
        region = cursor.fetchone()
        
        cursor.execute("SELECT setting_key, setting_value FROM region_settings WHERE region_uuid = %s", (region_uuid,))
        # Convert list of dicts to a single flat dictionary for the Jinja2 template
        current_settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

    return render_template('admin/edit_region.html', region=region, settings=current_settings, region_uuid=region_uuid)
```

**Zero Downtime Updates:** Change a region's `ExternalHostName` or `MaxPrims` in the portal, and the moment you restart that specific simulator, it pulls the fresh XML. No SSH, no `vi Region.ini`, no syntax errors.

**IP Whitelisting:** The XML endpoint is completely open to simple `GET` requests so OpenSim can read it easily, but it uses `request.remote_addr` checked against your dynamic configuration to drop requests from unauthorized IP addresses.  We don't have to lock this down more since all of the information that is provided in regions, is available for users to see via data server queries.

**Database Separation:** Because `region_configs` and `region_settings` live in the `OS_Pariah` database, grid administrators can manipulate these settings all day long without placing a single read/write lock on the core Robust database.

### User Profile Controls and Communications System

Giving users the power to manage their own profiles reduces the administrative burden, and a solid communications feed keeps the community engaged.

Note: We must be extremely careful with **IAR (Inventory Archive) backups**. Generating an IAR is a heavy process that locks up OpenSimulator inventory threads. If we make the user wait for the IAR to generate synchronously during a web request, Nginx will time out, the user will refresh the page, triggering *another* IAR backup... and a whole litter of kittens will perish in the resulting server crash.

We will implement an **Asynchronous Job Queue** in the `OS_Pariah` database for backups. The user clicks "Request Backup," the portal instantly says "Queued!", and a background cron worker (or systemd trigger) safely negotiates the heavy lifting with OpenSim.

#### The User Profile Controls (`app/blueprints/user/routes.py`)

This blueprint allows users to safely update their passwords and emails, and queue inventory backups.

```python
import uuid
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from app.utils.db import get_pariah_db
from app.utils.robust_api import call_robust_api # We reuse our safe API wrapper
from app.utils.notifications import send_verification_email # Stubbed earlier

user_bp = Blueprint('user', __name__, url_prefix='/user')

def update_robust_password(uuid, new_password):
    """Safely updates the user's password via the Robust API."""
    # We use the HTTP POST method to the private port, just like createuser
    payload = {
        'PrincipalID': uuid,
        'Password': new_password
    }
    # Using 'setaccount' or the specific OpenSim update method
    response_text = call_robust_api('setaccount', payload)
    return response_text and 'True' in response_text

@user_bp.route('/profile', methods=['GET'])
def profile():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Check if the user has pending IAR backups
        cursor.execute("SELECT status, requested_at FROM iar_backups WHERE user_uuid = %s ORDER BY requested_at DESC LIMIT 5", (session['uuid'],))
        backups = cursor.fetchall()
        
    return render_template('user/profile.html', backups=backups)

@user_bp.route('/profile/password', methods=['POST'])
def update_password():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('user.profile'))
        
    # Safely update password in OpenSim without touching the DB directly
    if update_robust_password(session['uuid'], new_password):
        flash('Password updated successfully.', 'success')
    else:
        flash('Failed to update password. Please try again.', 'error')
        
    return redirect(url_for('user.profile'))

@user_bp.route('/profile/email', methods=['POST'])
def request_email_change():
    """Initiates the email verification flow for a new email address."""
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    new_email = request.form.get('new_email').strip()
    verification_token = uuid.uuid4().hex
    
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO pending_email_changes (user_uuid, new_email, token) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE new_email = VALUES(new_email), token = VALUES(token)
        """, (session['uuid'], new_email, verification_token))
    pariah_conn.commit()
    
    send_verification_email(new_email, verification_token)
    flash('A verification link has been sent to your new email address.', 'info')
    return redirect(url_for('user.profile'))

@user_bp.route('/profile/backup', methods=['POST'])
def request_iar_backup():
    """Queues an IAR backup safely in the OS_Pariah DB."""
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Prevent users from spamming the queue
        cursor.execute("SELECT COUNT(*) as count FROM iar_backups WHERE user_uuid = %s AND status IN ('pending', 'processing')", (session['uuid'],))
        if cursor.fetchone()['count'] > 0:
            flash('You already have a backup in progress.', 'error')
            return redirect(url_for('user.profile'))
            
        cursor.execute("INSERT INTO iar_backups (user_uuid, status) VALUES (%s, 'pending')", (session['uuid'],))
    pariah_conn.commit()
    
    flash('Your inventory backup has been queued. You will be notified when it is ready for download.', 'success')
    return redirect(url_for('user.profile'))
```

#### The Communications & News Feed System (`app/blueprints/comms/routes.py`)

This module allows admins to post global news that shows up on the portal dashboard, and send targeted notices.

```python
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from app.utils.db import get_pariah_db
from app.utils.auth_helpers import require_admin

comms_bp = Blueprint('comms', __name__, url_prefix='/comms')

@comms_bp.route('/news', methods=['GET'])
def news_feed():
    """Publicly accessible news feed and global alerts."""
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, title, body, author_name, created_at, is_alert 
            FROM global_news 
            ORDER BY created_at DESC LIMIT 20
        """)
        news_items = cursor.fetchall()
        
    return render_template('comms/news_feed.html', news_items=news_items)

@comms_bp.route('/admin/post', methods=['GET', 'POST'])
@require_admin
def post_news():
    """Admin interface to post news or global alerts."""
    if request.method == 'POST':
        title = request.form.get('title')
        body = request.form.get('body')
        is_alert = request.form.get('is_alert') == 'on' # High priority sticky alert
        
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO global_news (title, body, author_uuid, author_name, is_alert) 
                VALUES (%s, %s, %s, %s, %s)
            """, (title, body, session['uuid'], session['name'], is_alert))
        pariah_conn.commit()
        
        flash('News item posted successfully.', 'success')
        return redirect(url_for('comms.news_feed'))
        
    return render_template('comms/post_news.html')

@comms_bp.route('/notices', methods=['GET'])
def user_notices():
    """User-specific inbox for ticket updates, backup completions, etc."""
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Fetch unread notices
        cursor.execute("""
            SELECT id, message, created_at, is_read 
            FROM user_notices 
            WHERE user_uuid = %s 
            ORDER BY created_at DESC LIMIT 50
        """, (session['uuid'],))
        notices = cursor.fetchall()
        
        # Mark as read
        cursor.execute("UPDATE user_notices SET is_read = TRUE WHERE user_uuid = %s AND is_read = FALSE", (session['uuid'],))
    pariah_conn.commit()
    
    return render_template('comms/user_notices.html', notices=notices)
```

**Delegated Processing:** By utilizing the `iar_backups` and `user_notices` tables in the `OS_Pariah` database, the web portal stays fast. A separate Python background script (running via Cron, SystemD, or Celery) can safely execute RemoteAdmin calls to OpenSim for IAR generation, update the database to 'complete', and insert a row into `user_notices` telling the user their file is ready.

**Read-Heavy Optimization:** The news feed only hits the `OS_Pariah` DB, allowing thousands of users to read grid updates without generating a single query against the OpenSimulator database.

**Robust Security:** Changing a password uses the exact same `call_robust_api` wrapper we built for `createuser`, ensuring that OpenSim natively handles the MD5 hash and salting inside its own architecture.

## Polish and Documentation

The core modules mapped:

* ✅ **Architecture:** Flask Factory, PyMySQL PooledDB, OS_Pariah DB.
* ✅ **Identity:** Python OIDC Bridge, Cloudflare Turnstile, Token Management.
* ✅ **Registration:** Dynamic Workflows, Matrix/Discord Webhooks, Safe API provisioning.
* ✅ **Helpdesk:** Secure attachments, threaded replies.
* ✅ **Grid Monitor:** 30-second Memory Caching for Online Listers.
* ✅ **Admin Controls:** Active API Bans, Gatekeeper Tracking, User Notes.
* ✅ **Region Mgmt:** Dynamic WebXML generator for `Region.ini`.
* ✅ **User & Comms:** Profile Management, Async IAR Queues, News Feeds.

With everything else established, we now can focus on the actual parts and keeping them themed and modular for easy of upkeep.

### Basic Nginx and Database setup

Establishing the database schema and the reverse-proxy/WSGI configuration right now lays the concrete for the rest of this epic. It gives us a strict map of our data.

#### The `OS_Pariah` Database Schema (MariaDB)

This schema isolates all portal data from your OpenSimulator `Robust` database. It incorporates the OIDC tables , the Gatekeeper tables , the Ban tracking tables , and our new operational tables.

```sql
-- OS Pariah Portal Database Foundation
CREATE DATABASE IF NOT EXISTS `os_pariah` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `os_pariah`;

-- ==========================================
-- 1. SYSTEM CONFIGURATION
-- ==========================================
CREATE TABLE IF NOT EXISTS `config` (
  `config_key` VARCHAR(100) PRIMARY KEY,
  `config_value` TEXT NOT NULL,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ==========================================
-- 2. OIDC IDENTITY BRIDGE
-- ==========================================
CREATE TABLE IF NOT EXISTS `oidc_clients` (
  `client_id` VARCHAR(100) PRIMARY KEY,
  `client_secret` VARCHAR(255) NOT NULL,
  `redirect_uri` TEXT NOT NULL,
  `app_name` VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `oidc_auth_codes` (
  `code` VARCHAR(100) PRIMARY KEY,
  `user_uuid` CHAR(36) NOT NULL,
  `client_id` VARCHAR(100) NOT NULL,
  `nonce` VARCHAR(255),
  `expires_at` BIGINT NOT NULL,
  INDEX `idx_auth_codes_expires` (`expires_at`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `oidc_access_tokens` (
  `token` VARCHAR(100) PRIMARY KEY,
  `user_uuid` CHAR(36) NOT NULL,
  `client_id` VARCHAR(100),
  `expires_at` BIGINT NOT NULL,
  INDEX `idx_access_tokens_expires` (`expires_at`)
) ENGINE=InnoDB;

-- ==========================================
-- 3. GATEKEEPER LOGS (Migrated from Robust DB)
-- ==========================================
CREATE TABLE IF NOT EXISTS `gatekeeper_from` (
  `user_uuid` CHAR(36) NOT NULL,
  `date_time` VARCHAR(24) NOT NULL,
  `user_name` TEXT NOT NULL,
  `inbound_from` VARCHAR(200) NOT NULL,
  `entered` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_uuid`, `inbound_from`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `gatekeeper_ip` (
  `user_uuid` CHAR(36) NOT NULL,
  `date_time` VARCHAR(24) NOT NULL,
  `user_name` TEXT NOT NULL,
  `user_ip` VARCHAR(45) NOT NULL,
  `entered` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_uuid`, `user_ip`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `gatekeeper_mac` (
  `user_uuid` CHAR(36) NOT NULL,
  `date_time` VARCHAR(24) NOT NULL,
  `user_name` TEXT NOT NULL,
  `user_mac` VARCHAR(50) NOT NULL,
  `entered` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_uuid`, `user_mac`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `gatekeeper_host_id` (
  `user_uuid` CHAR(36) NOT NULL,
  `date_time` VARCHAR(24) NOT NULL,
  `user_name` TEXT NOT NULL,
  `user_host_id` VARCHAR(255) NOT NULL,
  `entered` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_uuid`, `user_host_id`)
) ENGINE=InnoDB;

-- ==========================================
-- 4. BAN MANAGEMENT
-- ==========================================
CREATE TABLE IF NOT EXISTS `bans_master` (
  `banid` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `reason` TEXT,
  `type` ENUM('account','mac','hostid','ip','uuid','mixed') NOT NULL DEFAULT 'account'
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `bans_username` (
  `banid` INT UNSIGNED NOT NULL,
  `userName` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`banid`, `userName`),
  CONSTRAINT `fk_bans_username` FOREIGN KEY (`banid`) REFERENCES `bans_master`(`banid`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `bans_ip` (
  `banid` INT UNSIGNED NOT NULL,
  `ip` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`banid`, `ip`),
  CONSTRAINT `fk_bans_ip` FOREIGN KEY (`banid`) REFERENCES `bans_master`(`banid`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `bans_mac` (
  `banid` INT UNSIGNED NOT NULL,
  `mac` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`banid`, `mac`),
  CONSTRAINT `fk_bans_mac` FOREIGN KEY (`banid`) REFERENCES `bans_master`(`banid`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `bans_host_id` (
  `banid` INT UNSIGNED NOT NULL,
  `hostid` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`banid`, `hostid`),
  CONSTRAINT `fk_bans_host` FOREIGN KEY (`banid`) REFERENCES `bans_master`(`banid`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `bans_uuid` (
  `banid` INT UNSIGNED NOT NULL,
  `uuid` CHAR(36) NOT NULL,
  `grid` VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`banid`, `uuid`),
  CONSTRAINT `fk_bans_uuid` FOREIGN KEY (`banid`) REFERENCES `bans_master`(`banid`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ==========================================
-- 5. HELPDESK TICKETS
-- ==========================================
CREATE TABLE IF NOT EXISTS `tickets` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_uuid` CHAR(36) DEFAULT NULL,
  `user_email` VARCHAR(255) DEFAULT NULL,
  `user_name` VARCHAR(100) DEFAULT NULL,
  `category` VARCHAR(50) NOT NULL,
  `subject` VARCHAR(200) NOT NULL,
  `body` TEXT NOT NULL,
  `status` ENUM('Open','In Progress','Waiting on User','Waiting on Staff','On Hold','Completed','Will not work','No Response','Withdrawn') DEFAULT 'Open',
  `assigned_to_uuid` CHAR(36) DEFAULT NULL,
  `assigned_to_name` VARCHAR(100) DEFAULT NULL,
  `guest_ip` VARCHAR(45) DEFAULT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `ticket_replies` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `ticket_id` INT UNSIGNED NOT NULL,
  `replier_uuid` CHAR(36) DEFAULT NULL,
  `replier_email` VARCHAR(255) DEFAULT NULL,
  `body` TEXT NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_ticket_reply` FOREIGN KEY (`ticket_id`) REFERENCES `tickets`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `ticket_attachments` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `ticket_id` INT UNSIGNED NOT NULL,
  `reply_id` INT UNSIGNED DEFAULT NULL,
  `original_filename` VARCHAR(255) NOT NULL,
  `stored_filename` VARCHAR(255) NOT NULL,
  `mimetype` VARCHAR(100) NOT NULL,
  `file_size` INT UNSIGNED NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_ticket_attach` FOREIGN KEY (`ticket_id`) REFERENCES `tickets`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ==========================================
-- 6. REGISTRATIONS & REGIONS
-- ==========================================
CREATE TABLE IF NOT EXISTS `pending_registrations` (
  `user_uuid` CHAR(36) PRIMARY KEY,
  `email` VARCHAR(255) NOT NULL,
  `inviter` VARCHAR(100),
  `discord` VARCHAR(100),
  `other_info` TEXT,
  `verification_token` VARCHAR(64),
  `requires_approval` BOOLEAN DEFAULT TRUE,
  `status` ENUM('pending_email', 'pending_approval', 'approved', 'rejected') DEFAULT 'pending_email',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `region_configs` (
  `region_uuid` CHAR(36) PRIMARY KEY,
  `region_name` VARCHAR(100) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `region_settings` (
  `region_uuid` CHAR(36) NOT NULL,
  `setting_key` VARCHAR(100) NOT NULL,
  `setting_value` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`region_uuid`, `setting_key`),
  CONSTRAINT `fk_region_settings` FOREIGN KEY (`region_uuid`) REFERENCES `region_configs`(`region_uuid`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ==========================================
-- 7. COMMS & USER WORKFLOWS
-- ==========================================
CREATE TABLE IF NOT EXISTS `user_notes` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_uuid` CHAR(36) NOT NULL,
  `admin_uuid` CHAR(36) NOT NULL,
  `note` TEXT NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `iar_backups` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_uuid` CHAR(36) NOT NULL,
  `status` ENUM('pending','processing','completed','failed') DEFAULT 'pending',
  `file_path` VARCHAR(255) DEFAULT NULL,
  `requested_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `completed_at` TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB;
```

#### Gunicorn WSGI Configuration (`/etc/systemd/system/pariah.service`)

Gunicorn is our application server. To maximize performance and ensure Python's Global Interpreter Lock (GIL) doesn't bottleneck us during heavy API hits, we use multiple worker processes. Crucially, we must tell Gunicorn to trust Nginx so the `ProxyFix` correctly assigns the client IP.

```ini
[Unit]
Description=Gunicorn instance to serve OS Pariah Portal
After=network.target

[Service]
User=opensim
Group=opensim
WorkingDirectory=/home/opensim/os_pariah_portal
Environment="PATH=/home/opensim/os_pariah_portal/venv/bin"
# Set database and secret keys via EnvironmentFile or directly here
EnvironmentFile=/home/opensim/os_pariah_portal/.env

# Gunicorn Command:
# -w 4: 4 Worker processes (Adjust based on CPU cores)
# --forwarded-allow-ips="127.0.0.1": CRITICAL for ProxyFix to trust Nginx
# -b 127.0.0.1:5000: Bind locally only. Nginx will handle the public web.
# Note: We will might be using the installed python311-gunicorn
#       package and not a venv to allow the OS to handle updates, but
#       this could change. For now, I will embrace the "Best Practice"
#       of using a 'safe' venv and review later.
ExecStart=/home/opensim/os_pariah_portal/venv/bin/gunicorn \
    --workers 4 \
    --forwarded-allow-ips="127.0.0.1" \
    --bind 127.0.0.1:5000 \
    --access-logfile /home/opensim/Log/pariah_access.log \
    --error-logfile /home/opensim/Log/pariah_error.log \
    wsgi:app

Restart=always

[Install]
WantedBy=multi-user.target
```

#### Nginx Reverse Proxy Configuration (`/etc/nginx/conf.d/pariah.conf`)

Nginx acts as the shield. It handles SSL (communicating with Cloudflare), serves static CSS/JS instantly without waking up Python, and correctly passes the real visitor IP to Gunicorn.

```nginx
server {
    listen 80;
    listen [::]:80;
    # Cloudflare handles SSL termination, but please use local SSL and change to listen 443 ssl - Let's Encrypt is simple, and we are dealing with user data!
    server_name portal.example.com;

    # Limit payload size for ticket attachments (e.g., 10MB)
    client_max_body_size 10M;

    # 1. Serve Static Files Directly (Bypasses Python completely for speed)
    location /static/ {
        alias /home/opensim/os_pariah_portal/app/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # 2. Main WSGI Proxy Pass to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        
        # CRITICAL HEADERS: Pass the real client IP through Cloudflare and Nginx to Python
        proxy_set_header Host $host;
        # If using Cloudflare, CF-Connecting-IP is the true user IP
        proxy_set_header X-Real-IP $http_cf_connecting_ip; 
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts - Give the portal time if Robust is responding slowly
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }

    # 3. Dedicated Location for WebXML API (OpenSim Regions fetching config)
    location /regions/api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        # We must know the exact region host IP to allow the fetch - This probably needs more information, will review during testing
        proxy_set_header X-Real-IP $remote_addr; 
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 4. Deny access to hidden/system files
    location ~ /\. {
        deny all;
    }
}
```

With these three pieces (the `os_pariah` Database Schema, the `pariah.service` Gunicorn definition, and the `pariah.conf` Nginx server block), the entire Epic has its environment established.

We have mapped:

1. Python Blueprint Architecture (Auth, Registration, API, Admin, Regions, User, Comms)
2. Dual connection pooling for safe Read/Write operations.
3. The complete database schema.
4. The server deployment definitions.

### Templates

To minimize cognitive load, we must keep the interface predictable, scannable, and highly responsive. If a user has to guess where a button is or if an action was successful, the experience degrades.

We will expand the basic CSS with CSS variables for easy theming, clean navigation tabs, and clear user feedback mechanisms (alerts and loading spinners).  And we will use Jinja2 templates to keep things controlled and on theme.

#### The Enhanced Stylesheet (`app/static/css/central.css`)

Following suggestions for modernization of the properties and added the necessary components for our new modules.

```css
/* =========================================================
   OS Pariah Portal - Central Stylesheet
   Optimized for low cognitive load and high readability
   ========================================================= */

:root {
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --bg-color: #f8fafc;
  --text-main: #1e293b;
  --text-muted: #64748b;
  --border-color: #e2e8f0;
  --card-bg: rgba(255, 255, 255, 0.95);
  --success: #10b981;
  --success-bg: #dcfce7;
  --danger: #ef4444;
  --danger-bg: #fee2e2;
  --info: #0ea5e9;
  --info-bg: #e0f2fe;
}

html, body {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: 'Inter', Arial, Helvetica, sans-serif;
  color: var(--text-main);
  background-color: var(--bg-color);
}

/* --- Layout & Containers --- */
.background {
  position: relative;
  min-height: 100vh;
  width: 100vw;
  /* Easily brandable background */
  background-image: url('https://example.com/example.png');
  background-repeat: no-repeat;
  background-position: center;
  background-attachment: fixed;
  background-size: cover;
}

.main {
  position: absolute;
  top: 10%;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  max-width: 1000px;
  max-height: 85vh;
  overflow-y: auto;
  background: var(--card-bg);
  padding: 24px;
  border-radius: 12px;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
}

.center { text-align: center; }

/* --- Navigation & Tabs --- */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid var(--border-color);
  padding-bottom: 12px;
  margin-bottom: 24px;
}
.nav-links a {
  text-decoration: none;
  color: var(--text-main);
  font-weight: 600;
  margin-right: 16px;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background 0.2s;
}
.nav-links a:hover { background: var(--border-color); }
.nav-links a.active { background: var(--primary); color: white; }

/* --- Forms & Inputs --- */
fieldset { border: 1px solid var(--border-color); padding: 16px; border-radius: 8px; margin-bottom: 20px; }
legend { font-weight: bold; color: var(--primary); padding: 0 8px; }
form { margin-bottom: 18px; }

label { display: block; font-size: 0.9rem; font-weight: 600; margin-bottom: 6px; }
label.radio { display: inline-block; margin-right: 12px; font-weight: normal; }

input[type="text"], input[type="password"], input[type="email"], textarea, select {
  width: 100%;
  padding: 10px;
  margin-bottom: 16px;
  border: 1px solid #ccc;
  border-radius: 6px;
  box-sizing: border-box;
  font-family: inherit;
  transition: border-color 0.2s;
}
input:focus, textarea:focus, select:focus { border-color: var(--primary); outline: none; }

button, .btn {
  background: var(--primary);
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
  transition: background 0.2s;
}
button:hover, .btn:hover { background: var(--primary-hover); }
button:disabled { background: #cbd5e1; cursor: not-allowed; }

.btn-danger { background: var(--danger); }
.btn-danger:hover { background: #b91c1c; }

/* --- Tables & Data --- */
table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; }
th, td { border-bottom: 1px solid var(--border-color); padding: 12px 8px; text-align: left; }
th { background: #f1f5f9; color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }
tr:hover { background: #f8fafc; }

.group { margin: 10px 0; padding: 12px; border: 1px solid var(--border-color); border-radius: 6px; background: #fafafa; overflow-y: auto; max-height: 300px; }
.group h2 { margin: 0 0 10px 0; font-size: 1.1rem; color: var(--primary); }

.uuid { font-family: monospace; font-size: 0.95rem; color: var(--text-muted); }
.uuidlist { font-family: monospace; background: #f1f5f9; padding: 12px; border-radius: 6px; }

/* --- Alerts & Feedback --- */
.alert { padding: 12px 16px; margin-bottom: 20px; border-radius: 6px; font-weight: 500; }
.alert.success { background: var(--success-bg); color: #166534; border-left: 4px solid var(--success); }
.alert.error { background: var(--danger-bg); color: #991b1b; border-left: 4px solid var(--danger); }
.alert.info { background: var(--info-bg); color: #075985; border-left: 4px solid var(--info); }

/* --- Async Loading Spinner --- */
.spinner {
  display: inline-block;
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 1s linear infinite;
  vertical-align: middle;
  margin-left: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

#### The Master Layout (`app/templates/base.html`)

This acts as the skeleton for every page in the portal. It handles the dynamic navigation (showing Admin links only to Level 200+ users), renders the Flash messages , and provides the content block.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}OS Pariah Portal{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/central.css') }}">
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body>

<div class="background">
    <div class="main">
        
        <div class="nav-bar">
            <div>
                <h2 style="margin: 0; color: var(--primary);">OS Pariah</h2>
            </div>
            
            <div class="nav-links">
                <a href="{{ url_for('comms.news_feed') }}">Home</a>
                <a href="{{ url_for('tickets.index') }}">Helpdesk</a>
                
                {% if session.get('uuid') %}
                    <a href="{{ url_for('user.profile') }}">My Profile</a>
                    
                    {% if session.get('is_admin') %}
                        <a href="{{ url_for('admin.pending_approvals') }}" style="color: var(--danger);">Approvals</a>
                        <a href="{{ url_for('user_mgmt.gatekeeper_lookup') }}">Users & Bans</a>
                        <a href="{{ url_for('regions.manage_regions') }}">Regions</a>
                    {% endif %}
                    
                    <a href="{{ url_for('auth.logout') }}" class="btn-danger" style="color: white;">Logout</a>
                {% else %}
                    <a href="{{ url_for('auth.login') }}" class="btn">Login</a>
                    <a href="{{ url_for('register.register') }}">Register</a>
                {% endif %}
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
        
    </div>
</div>

<script src="{{ url_for('static', filename='js/main.js') }}"></script>
{% block scripts %}{% endblock %}

</body>
</html>
```

#### The Registration Template (`app/templates/register/index.html`)

To demonstrate how the `base.html` wrap works in practice, here is the Registration template. It utilizes your required Cloudflare Turnstile logic, includes the robust password checking, and dynamically hides/shows fields based on the configurations we pull from the database.

```html
{% extends 'base.html' %}

{% block title %}Register - OS Pariah Portal{% endblock %}

{% block content %}
<div class="center">
    <h1>Join the Grid</h1>
    <p style="color: var(--text-muted); margin-bottom: 24px;">Create your OpenSimulator avatar below.</p>
</div>

<form id="regForm" method="POST" action="{{ url_for('register.register') }}" onsubmit="showLoading()">
    
    <fieldset>
        <legend>Avatar Identity</legend>
        <div style="display: flex; gap: 12px;">
            <div style="flex: 1;">
                <label>First Name</label>
                <input type="text" name="first_name" placeholder="John" required>
            </div>
            <div style="flex: 1;">
                <label>Last Name</label>
                <input type="text" name="last_name" placeholder="Resident" required>
            </div>
        </div>
        
        <label>Email Address</label>
        <input type="email" name="email" placeholder="you@example.com" required>
        
        <label>Password</label>
        <input type="password" id="passField" name="password" required>
        <small id="strengthText" style="color: var(--danger); font-weight: bold;">Strength: Too Short</small>
    </fieldset>

    <fieldset>
        <legend>Community</legend>
        <label>Invited By (Avatar Name)</label>
        <input type="text" name="inviter" required>
        
        <label>Discord Handle (Optional)</label>
        <input type="text" name="discord_handle" placeholder="User#0000">

        {% if require_invite_code %}
            <label>Invitation Code <span style="color: var(--danger);">*</span></label>
            <input type="text" name="invite_code" placeholder="XXXX-XXXX-XXXX" required>
        {% endif %}

        {% if require_other_info %}
            <label>Other Information <span style="color: var(--danger);">*</span></label>
            <textarea id="infoField" name="other_info" rows="4" placeholder="How did you hear about us? Why do you want to join?" required></textarea>
            <div id="wordCount" style="font-size: 0.8rem; text-align: right; color: var(--danger);">0 / 30 words</div>
        {% endif %}
    </fieldset>

    <div style="background: var(--info-bg); padding: 16px; border-radius: 8px; margin-bottom: 20px;">
        <label class="radio">
            <input type="checkbox" id="policyCheck" name="policy_check" required>
            I agree to comply with the <a href="/policies/tos.html" target="_blank">Terms of Service</a>, <a href="/policies/privacy.html" target="_blank">Privacy Policy</a>, and Code of Conduct.
        </label>
        <br><br>
        <label class="radio">
            <input type="checkbox" id="ageCheck" name="age_check" required>
            I attest that I am at least 18 years of age.
        </label>
    </div>

    <div style="display: flex; justify-content: center; margin-bottom: 20px;">
        <div class="cf-turnstile" data-sitekey="{{ site_key }}" data-callback="enableSubmit"></div>
    </div>

    <button type="submit" id="submitBtn" style="width: 100%; font-size: 1.1rem; padding: 14px;" disabled>
        <span id="btnText">Submit Application</span>
        <div id="btnSpinner" class="spinner" style="display: none;"></div>
    </button>
</form>
{% endblock %}

{% block scripts %}
<script>
    // UX Script to enforce word counts and enable the button safely
    const infoField = document.getElementById('infoField');
    const wordCount = document.getElementById('wordCount');
    const submitBtn = document.getElementById('submitBtn');
    let captchaSolved = false;
    let requiresInfo = {{ 'true' if require_other_info else 'false' }};

    function enableSubmit() {
        captchaSolved = true;
        validateForm();
    }

    function validateForm() {
        let isReady = captchaSolved && document.getElementById('policyCheck').checked && document.getElementById('ageCheck').checked;
        
        if (requiresInfo && infoField) {
            const words = infoField.value.trim().split(/\s+/).filter(w => w.length > 0).length;
            wordCount.textContent = `${words} / 30 words`;
            if (words >= 30) {
                wordCount.style.color = "var(--success)";
            } else {
                wordCount.style.color = "var(--danger)";
                isReady = false;
            }
        }
        submitBtn.disabled = !isReady;
    }

    if (infoField) infoField.addEventListener('input', validateForm);
    document.getElementById('policyCheck').addEventListener('change', validateForm);
    document.getElementById('ageCheck').addEventListener('change', validateForm);

    function showLoading() {
        document.getElementById('btnText').textContent = "Processing...";
        document.getElementById('btnSpinner').style.display = "inline-block";
        submitBtn.style.opacity = "0.8";
    }
</script>
{% endblock %}
```

By leveraging `base.html` with `{% block content %}`, every subsequent page (the Ticket Dashboard, Gatekeeper Lookups, Region Management) will inherit this exact responsive layout, navigation bar, and central stylesheet, yielding a consistent user experience.

### Admin Approvals Dashboard UI

This interface is critical because it represents the bottleneck between a user registering and actually being able to log into the grid. We will use the modern `fetch()` API to hit the `/admin/approvals/approve` endpoint we built earlier.

#### The Admin Approvals Template (`app/templates/admin/approvals.html`)

This template extends our `base.html` and populates the table using the data fetched from the `OS_Pariah` database.

```html
{% extends 'base.html' %}

{% block title %}Pending Approvals - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>Pending Registrations (Level -1)</h2>
</div>

<p style="color: var(--text-muted); margin-bottom: 24px;">
    These users have completed registration and verified their emails, but are locked at Level -1. Approving them will grant Level 0 access via the Robust API.
</p>

{% if users %}
    <div class="group" style="max-height: 70vh; padding: 0;">
        <table style="margin: 0;">
            <thead>
                <tr>
                    <th>Avatar Name / UUID</th>
                    <th>Contact Info</th>
                    <th>Invited By</th>
                    <th>Application Details</th>
                    <th style="text-align: center;">Action</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr id="row_{{ user.user_uuid }}" style="transition: opacity 0.5s ease;">
                    <td>
                        <strong>{{ user.first_name }} {{ user.last_name }}</strong><br>
                        <span class="uuid">{{ user.user_uuid }}</span>
                    </td>
                    <td>
                        <a href="mailto:{{ user.email }}" style="color: var(--primary); text-decoration: none;">{{ user.email }}</a><br>
                        {% if user.discord %}
                            <span style="font-size: 0.85rem; color: #6366f1;">Discord: {{ user.discord }}</span>
                        {% endif %}
                    </td>
                    <td>{{ user.inviter }}</td>
                    <td>
                        <div style="font-size: 0.85rem; max-width: 250px; overflow-wrap: break-word;">
                            {{ user.other_info }}
                        </div>
                        <span style="font-size: 0.8rem; color: var(--text-muted);">Applied: {{ user.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
                    </td>
                    <td style="text-align: center; vertical-align: middle;">
                        <button class="btn btn-approve" style="background-color: var(--success);" 
                                onclick="approveUser('{{ user.user_uuid }}', '{{ user.email }}', 'row_{{ user.user_uuid }}')">
                            <span class="btn-text">Approve</span>
                            <div class="spinner" style="display: none;"></div>
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
{% else %}
    <div class="center group" style="padding: 40px;">
        <h3 style="color: var(--success);">All caught up!</h3>
        <p style="color: var(--text-muted);">There are currently no users awaiting approval.</p>
    </div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
    function approveUser(uuid, email, rowId) {
        if (!confirm(`Are you sure you want to approve this user and grant them Level 0 access?`)) return;

        const row = document.getElementById(rowId);
        const btn = row.querySelector('.btn-approve');
        const text = btn.querySelector('.btn-text');
        const spinner = btn.querySelector('.spinner');

        // UI Loading State
        btn.disabled = true;
        text.style.display = 'none';
        spinner.style.display = 'inline-block';

        // Prepare AJAX Payload
        const formData = new URLSearchParams();
        formData.append('uuid', uuid);
        formData.append('email', email);

        // Send atomic write to backend
        fetch('{{ url_for("admin.approve_user") }}', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData.toString()
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Fade out and remove the row gently - showy, but cool
                row.style.opacity = '0';
                setTimeout(() => {
                    row.remove();
                    // Check if table is empty
                    if (document.querySelectorAll('tbody tr').length === 0) {
                        location.reload(); // Reload to show the "All caught up" state
                    }
                }, 500); // Wait 500ms for CSS transition to finish
            } else {
                alert("Approval Failed: " + data.message);
                btn.disabled = false;
                text.style.display = 'inline-block';
                spinner.style.display = 'none';
            }
        })
        .catch(err => {
            alert("Network error. Check console.");
            console.error(err);
            btn.disabled = false;
            text.style.display = 'inline-block';
            spinner.style.display = 'none';
        });
    }
</script>
{% endblock %}
```

**Rich Context:** Because we are pulling from the `OS_Pariah` database instead of just OpenSim's tables, admins can actually read the "Other Information" and see the Discord/Matrix handle right next to the approve button.

**Safe Executions:** The javascript uses `encodeURIComponent` internally via `URLSearchParams`, ensuring weird characters in emails don't break the HTTP POST.

**No Reloading:** Admins can rapidly click through a queue of 10 users, firing off 10 asynchronous requests to OpenSim, without ever waiting for the page to refresh.

### User WebUI

This interface is dedicated to grid administrators because it offloads basic support tasks directly to the users. Users can change their own Robust passwords, update their emails, and request their IAR (Inventory Archive) backups without opening a support ticket.

We are going to implement UX guardrails here. If a user clicks "Request Backup", we will disable the button so they cannot spam the asynchronous queue and accidentally crush the server.

#### The User Profile Template (`app/templates/user/profile.html`)

This template extends our `base.html` and uses the tabbed `.group` and `fieldset` classes we defined in `central.css`.

```html
{% extends 'base.html' %}

{% block title %}My Profile - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>Avatar Profile: {{ session.get('name') }}</h2>
</div>

<p style="color: var(--text-muted); margin-bottom: 24px;">
    Manage your OpenSimulator security, contact details, and inventory backups here.
</p>

<div style="display: flex; flex-wrap: wrap; gap: 20px;">

    <div style="flex: 1; min-width: 300px;">
        
        <form method="POST" action="{{ url_for('user.update_password') }}" onsubmit="return validatePassword()">
            <fieldset>
                <legend>Update Password</legend>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0;">
                    Changes here sync instantly with the OpenSim grid.
                </p>
                
                <label>New Password</label>
                <input type="password" id="new_password" name="new_password" required>
                
                <label>Confirm Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required>
                <small id="passMatchText" style="color: var(--danger); display: none;">Passwords do not match.</small>
                
                <button type="submit" id="passSubmitBtn" style="margin-top: 10px; width: 100%;">Change Password</button>
            </fieldset>
        </form>

        <form method="POST" action="{{ url_for('user.request_email_change') }}" onsubmit="showLoading('emailSpinner', 'emailBtn')">
            <fieldset>
                <legend>Update Email Address</legend>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0;">
                    You will need to click a verification link sent to the new address.
                </p>
                
                <label>New Email</label>
                <input type="email" name="new_email" placeholder="new.email@example.com" required>
                
                <button type="submit" id="emailBtn" style="margin-top: 10px; width: 100%;">
                    <span>Request Change</span>
                    <div id="emailSpinner" class="spinner" style="display: none;"></div>
                </button>
            </fieldset>
        </form>
    </div>

    <div style="flex: 1; min-width: 300px;">
        <div class="group" style="max-height: none;">
            <legend style="font-size: 1.1rem; padding: 0;">Inventory Backups (IAR)</legend>
            <p style="font-size: 0.85rem; color: var(--text-muted);">
                You can request a complete archive of your inventory. This is processed in the background to keep the grid stable.
            </p>

            {% if backups %}
                <table style="margin-bottom: 20px;">
                    <thead>
                        <tr>
                            <th>Date Requested</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for backup in backups %}
                        <tr>
                            <td style="font-size: 0.85rem;">{{ backup.requested_at.strftime('%Y-%m-%d %H:%M') }}</td>
                            <td>
                                {% if backup.status == 'pending' %}
                                    <span style="color: var(--info); font-weight: bold;">Queued</span>
                                {% elif backup.status == 'processing' %}
                                    <span style="color: var(--primary); font-weight: bold;">Processing...</span>
                                {% elif backup.status == 'completed' %}
                                    <span style="color: var(--success); font-weight: bold;">Ready</span>
                                {% elif backup.status == 'failed' %}
                                    <span style="color: var(--danger); font-weight: bold;">Failed</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if backup.status == 'completed' and backup.file_path %}
                                    <a href="/downloads/{{ backup.file_path }}" class="btn" style="padding: 4px 8px; font-size: 0.8rem;">Download</a>
                                {% else %}
                                    <span style="color: var(--text-muted); font-size: 0.8rem;">N/A</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div class="alert info" style="font-size: 0.85rem;">You have no recent backups.</div>
            {% endif %}

            {% set has_active = false %}
            {% for backup in backups %}
                {% if backup.status in ['pending', 'processing'] %}
                    {% set has_active = true %}
                {% endif %}
            {% endfor %}

            <form method="POST" action="{{ url_for('user.request_iar_backup') }}" onsubmit="showLoading('iarSpinner', 'iarBtn')">
                <button type="submit" id="iarBtn" style="width: 100%; background: var(--success);" {% if has_active %}disabled{% endif %}>
                    <span>Request New IAR Backup</span>
                    <div id="iarSpinner" class="spinner" style="display: none;"></div>
                </button>
                {% if has_active %}
                    <p style="font-size: 0.8rem; color: var(--danger); text-align: center; margin-top: 8px;">
                        You already have a backup in progress. Please wait for it to finish.
                    </p>
                {% endif %}
            </form>

        </div>
    </div>

</div>
{% endblock %}

{% block scripts %}
<script>
    // UX Script: Prevent submission if passwords don't match
    const newPass = document.getElementById('new_password');
    const confPass = document.getElementById('confirm_password');
    const matchText = document.getElementById('passMatchText');

    function checkMatch() {
        if (confPass.value.length > 0 && newPass.value !== confPass.value) {
            matchText.style.display = 'block';
            return false;
        } else {
            matchText.style.display = 'none';
            return true;
        }
    }

    newPass.addEventListener('input', checkMatch);
    confPass.addEventListener('input', checkMatch);

    function validatePassword() {
        if (!checkMatch() || newPass.value === '') {
            matchText.style.display = 'block';
            return false;
        }
        showLoading('passSpinner', 'passSubmitBtn'); // Assumes you add a spinner to the button
        return true;
    }

    // Generic loading spinner toggle for buttons
    function showLoading(spinnerId, btnId) {
        document.getElementById(spinnerId).style.display = "inline-block";
        const btn = document.getElementById(btnId);
        btn.style.opacity = "0.8";
        // We don't disable the button immediately here because it can block the actual form submission in some browsers  (Oops?)
    }
</script>
{% endblock %}
```

**The IAR Safety Lock:** By checking the `backups` array passed from the Python route, we use Jinja2 (`{% if has_active %}disabled{% endif %}`) to instantly gray out the "Request New IAR Backup" button if a job is already in the queue. No spamming allowed.

**Instant OpenSim Sync:** We clearly inform the user that password changes sync instantly. When they hit submit, our Python route uses `call_robust_api('setaccount')` to immediately rewrite the hash in OpenSim. *mic drop*

**Client-Side Validation:** The JavaScript prevents the server from even receiving a request if the user typos their password confirmation, saving precious network and processing overhead.

### The Helpdesk UI

The original ticket system (`ticketapp.py` and its templates) had a fantastic, feature-rich view for individual tickets, including threaded replies, attachment handling, and specific admin delegation controls . We are going to adapt `ticket_view.html` to use our new responsive `central.css` framework, ensuring the experience is seamless and consistent with the rest of the portal.

We will preserve the logic that allows admins to claim, assign, and delete tickets, while allowing users to withdraw or reopen them based on the ticket's current status .

#### The Ticket View Template (`app/templates/tickets/ticket_view.html`)

This template dynamically shifts its interface based on whether the logged-in user is an admin or a standard user. (Magic?)

```html
{% extends 'base.html' %}

{% block title %}Ticket #{{ ticket.id }} - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>
        <a href="{{ url_for('tickets.index') }}" style="text-decoration: none; color: var(--text-muted); font-size: 1rem;">&larr; Back to Dashboard</a><br>
        #{{ ticket.id }}: {{ ticket.subject }}
    </h2>
    <div style="text-align: right;">
        <span style="background: var(--border-color); padding: 6px 12px; border-radius: 6px; font-weight: bold; margin-right: 8px; font-size: 0.85rem;">
            {{ ticket.category }}
        </span>
        {% set status_color = 'var(--primary)' %}
        {% if ticket.status in ['Completed', 'Withdrawn', 'Will not work'] %}
            {% set status_color = 'var(--text-muted)' %}
        {% elif ticket.status == 'Waiting on User' %}
            {% set status_color = '#f59e0b' %} {% endif %}
        <span style="background: {{ status_color }}; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold; font-size: 0.85rem;">
            Status: {{ ticket.status }}
        </span>
    </div>
</div>

<div class="group" style="max-height: none; background: white;">
    <p style="color: var(--text-muted); font-size: 0.85rem; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-top: 0;">
        {% if ticket.assigned_to_name %}<strong>Assigned to:</strong> {{ ticket.assigned_to_name }} <br>{% endif %}
        <strong>Opened by:</strong> {% if ticket.user_uuid %}{{ ticket.user_name or 'OpenSim User' }}{% else %}{{ ticket.user_email }} (Guest){% endif %} <br>
        {% if session.get('is_admin') and ticket.guest_ip %}
            <span style="color: var(--danger);"><strong>Guest IP:</strong> {{ ticket.guest_ip }}</span> <br>
        {% endif %}
        <strong>Created:</strong> {{ ticket.created_at.strftime('%Y-%m-%d %H:%M') }}
    </p>
    
    <p style="white-space: pre-wrap; line-height: 1.5;">{{ ticket.body }}</p>
    
    {% if attachments %}
        <div style="margin-top: 15px; padding: 12px; background: var(--bg-color); border-radius: 6px; border: 1px solid var(--border-color);">
            <strong style="color: var(--text-main); font-size: 0.9rem;">Attachments:</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 0.9rem;">
            {% for file in attachments %}
                {% if not file.reply_id %}
                <li>
                    <a href="{{ url_for('tickets.serve_attachment', ticket_id=ticket.id, attachment_id=file.id) }}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 600;">
                        &#128206; {{ file.original_filename }}
                    </a>
                    <span style="color: var(--text-muted); font-size: 0.8rem;">({{ (file.file_size / 1024) | round(1) }} KB)</span>
                </li>
                {% endif %}
            {% endfor %}
            </ul>
        </div>
    {% endif %}
</div>

{% if replies %}
    <h3 style="margin-top: 30px; margin-bottom: 10px; color: var(--text-main);">Conversation</h3>
    {% for reply in replies %}
    <div class="group" style="max-height: none; border-left: 4px solid var(--primary); margin-bottom: 16px;">
        <strong style="color: var(--text-main);">{{ reply.replier_email }}</strong>
        <span style="color: var(--text-muted); font-size: 0.8rem; margin-left: 10px;">{{ reply.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
        <p style="margin-top: 10px; white-space: pre-wrap; line-height: 1.5;">{{ reply.body }}</p>

        <ul style="margin: 10px 0 0 0; padding-left: 0; list-style-type: none;">
            {% for file in attachments %}
                {% if file.reply_id == reply.id %}
                <li style="margin-bottom: 6px;">
                    <a href="{{ url_for('tickets.serve_attachment', ticket_id=ticket.id, attachment_id=file.id) }}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 600;">
                        &#128206; Attachment: {{ file.original_filename }}
                    </a>
                    <span style="color: var(--text-muted); font-size: 0.8rem;">({{ (file.file_size / 1024) | round(1) }} KB)</span>
                </li>
                {% endif %}
            {% endfor %}
        </ul>
    </div>
    {% endfor %}
{% endif %}

{% if ticket.status in ['Open', 'In Progress', 'On Hold', 'Waiting on User', 'Waiting on Staff'] %}
    <div style="margin-top: 30px;">
        <form action="{{ url_for('tickets.reply_ticket', ticket_id=ticket.id) }}" method="POST" enctype="multipart/form-data">
            <fieldset>
                <legend>Add Reply</legend>
                <textarea name="body" rows="4" placeholder="Type your reply here..." required></textarea>

                <div style="margin: 12px 0;">
                    <label for="attachment">Attach File (Optional):</label>
                    <input type="file" name="attachment" id="attachment" accept=".png,.jpg,.jpeg,.gif,.txt,.pdf,.log" style="padding: 8px; border: 1px dashed var(--border-color); background: var(--bg-color);">
                </div>
                <button type="submit">Post Reply</button>
            </fieldset>
        </form>
    </div>
{% else %}
    <div class="alert info" style="margin-top: 20px;">This ticket is currently closed. You must re-open it to reply.</div>
{% endif %}

<div class="group" style="margin-top: 30px; background: var(--bg-color);">
    <h3 style="margin-top: 0;">Ticket Actions</h3>

    {% if session.get('is_admin') %}
        {% if ticket.status in ['Open', 'In Progress', 'On Hold', 'Waiting on User', 'Waiting on Staff'] %}
        <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px dashed var(--border-color); display: flex; align-items: center; flex-wrap: wrap; gap: 12px;">
            
            <form action="{{ url_for('tickets.assign_ticket', ticket_id=ticket.id) }}" method="POST" style="margin: 0;">
                {% if not ticket.assigned_to_uuid %}
                    <input type="hidden" name="action" value="claim">
                    <button type="submit" style="background: var(--info);">Claim Ticket</button>
                {% elif ticket.assigned_to_uuid == session.get('uuid') %}
                    <input type="hidden" name="action" value="unassign">
                    <button type="submit" style="background: var(--text-muted);">Unassign Me</button>
                {% else %}
                    <span style="color: #b45309; font-weight: bold; margin-right: 10px;">Assigned to {{ ticket.assigned_to_name }}</span>
                    <input type="hidden" name="action" value="claim">
                    <button type="submit" style="background: var(--info);" onclick="return confirm('Take this from {{ ticket.assigned_to_name }}?');">Steal Ticket</button>
                {% endif %}
            </form>

            <form action="{{ url_for('tickets.assign_ticket', ticket_id=ticket.id) }}" method="POST" style="margin: 0; display: flex; align-items: center; gap: 8px;">
                <input type="hidden" name="action" value="assign_other">
                <select name="assignee_data" required style="margin: 0; width: auto; padding: 8px;">
                    <option value="" disabled selected>Delegate to...</option>
                    {% for admin in admins %}
                        <option value="{{ admin.uuid }}|{{ admin.name }}">{{ admin.name }}</option>
                    {% endfor %}
                </select>
                <button type="submit">Assign</button>
            </form>
        </div>
        {% endif %}

        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <form action="{{ url_for('tickets.update_ticket_status', ticket_id=ticket.id) }}" method="POST" style="margin: 0; display: flex; align-items: center; gap: 8px;">
                <select name="status" style="margin: 0; width: auto; padding: 8px;">
                    <option value="Open" {% if ticket.status == 'Open' %}selected{% endif %}>Open</option>
                    <option value="In Progress" {% if ticket.status == 'In Progress' %}selected{% endif %}>In Progress</option>
                    <option value="On Hold" {% if ticket.status == 'On Hold' %}selected{% endif %}>On Hold</option>
                    <option value="Waiting on User" {% if ticket.status == 'Waiting on User' %}selected{% endif %}>Waiting on User</option>
                    <option value="Waiting on Staff" {% if ticket.status == 'Waiting on Staff' %}selected{% endif %}>Waiting on Staff</option>
                    <option value="Completed" {% if ticket.status == 'Completed' %}selected{% endif %}>Completed</option>
                    <option value="Will not work" {% if ticket.status == 'Will not work' %}selected{% endif %}>Will not work</option>
                    <option value="No Response" {% if ticket.status == 'No Response' %}selected{% endif %}>No Response</option>
                </select>
                <button type="submit" style="background: var(--success);">Update Status</button>
            </form>

            {% if session.get('user_level', 0) >= 250 %}
            <form action="{{ url_for('tickets.delete_ticket', ticket_id=ticket.id) }}" method="POST" style="margin: 0;" onsubmit="return confirm('WARNING: This will permanently delete this ticket. Are you sure?');">
                <button type="submit" class="btn-danger">Delete Ticket</button>
            </form>
            {% endif %}
        </div>

    {% else %}
        {% if ticket.status in ['Completed', 'Withdrawn', 'Will not work', 'No Response'] %}
            <form action="{{ url_for('tickets.update_ticket_status', ticket_id=ticket.id) }}" method="POST" style="margin: 0;">
                <input type="hidden" name="status" value="Open">
                <button type="submit" style="background: var(--success);">Re-Open Ticket</button>
            </form>
        {% else %}
            <form action="{{ url_for('tickets.update_ticket_status', ticket_id=ticket.id) }}" method="POST" style="margin: 0;" onsubmit="return confirm('Are you sure you want to withdraw this ticket?');">
                <input type="hidden" name="status" value="Withdrawn">
                <button type="submit" class="btn-danger">Withdraw Ticket</button>
            </form>
        {% endif %}
    {% endif %}
</div>
{% endblock %}
```

**Contextual Guardrails:** The template relies heavily on Jinja2 logic (`{% if session.get('is_admin') %}`) to completely hide destructive actions, like assigning tickets or deleting them, from standard users .

**Clear Visual State:** We added conditional styling to the status badge. If a ticket is "Waiting on User," it turns Amber, drawing the user's eye to it so they know an action is required. If it's closed, it turns muted gray.

**Flexbox Layout:** By wrapping the admin actions in `display: flex; flex-wrap: wrap; gap: 12px;`, the buttons will elegantly stack on mobile devices and line up cleanly on desktop displays, keeping the interface uncluttered.

### Communications UI

This system allows global alerts, messages, and notices to be tracked for users. We separated this into two distinct views: a global **News Feed** (which can double as the portal's homepage) and a private **My Notices** inbox for individual users.

#### The Global News Feed (`app/templates/comms/news_feed.html`)

This acts as the public face of the grid's communications. It highlights critical alerts in red while keeping standard news items clean and readable.

```html
{% extends 'base.html' %}

{% block title %}Grid News & Alerts - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>Grid News & Announcements</h2>
    {% if session.get('is_admin') %}
        <a href="{{ url_for('comms.post_news') }}" class="btn" style="background: var(--success);">+ Post Update</a>
    {% endif %}
</div>

<p style="color: var(--text-muted); margin-bottom: 24px;">
    Stay up to date with the latest maintenance schedules, events, and grid updates.
</p>

{% if news_items %}
    <div style="display: flex; flex-direction: column; gap: 16px;">
        {% for item in news_items %}
            <div class="group" style="max-height: none; {% if item.is_alert %}border-left: 4px solid var(--danger); background: var(--danger-bg);{% else %}border-left: 4px solid var(--primary); background: var(--card-bg);{% endif %} padding: 16px;">
                
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <h3 style="margin: 0; {% if item.is_alert %}color: var(--danger);{% else %}color: var(--primary);{% endif %}">
                        {% if item.is_alert %}🚨 ALERT: {% endif %}{{ item.title }}
                    </h3>
                    <span style="font-size: 0.8rem; color: var(--text-muted);">
                        {{ item.created_at.strftime('%B %d, %Y') }}
                    </span>
                </div>
                
                <p style="margin: 0 0 12px 0; white-space: pre-wrap; line-height: 1.5; color: var(--text-main);">{{ item.body }}</p>
                
                <div style="font-size: 0.8rem; color: var(--text-muted); border-top: 1px dashed var(--border-color); padding-top: 8px;">
                    Posted by: <strong>{{ item.author_name }}</strong>
                </div>
            </div>
        {% endfor %}
    </div>
{% else %}
    <div class="alert info">There are currently no news items to display.</div>
{% endif %}
{% endblock %}
```

#### The User Notices Inbox (`app/templates/comms/user_notices.html`)

When a user's IAR backup finishes or an admin approves their account, the asynchronous background worker generates a notice. This inbox displays those alerts. Because the Python route marks them as "read" the moment this page loads, we use CSS to distinguish between brand-new alerts and older ones.

```html
{% extends 'base.html' %}

{% block title %}My Notices - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>My Notices</h2>
</div>

<p style="color: var(--text-muted); margin-bottom: 24px;">
    System notifications, ticket updates, and backup alerts.
</p>

{% if notices %}
    <div style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden;">
        <table style="margin: 0; width: 100%;">
            <tbody>
                {% for notice in notices %}
                <tr style="{% if not notice.is_read %}background: var(--info-bg); font-weight: 600;{% endif %} border-bottom: 1px solid var(--border-color);">
                    <td style="width: 150px; color: var(--text-muted); font-size: 0.85rem; vertical-align: top; padding-top: 16px;">
                        {{ notice.created_at.strftime('%Y-%m-%d %H:%M') }}
                    </td>
                    <td style="padding: 16px; line-height: 1.4; color: var(--text-main);">
                        {{ notice.message }}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
{% else %}
    <div class="center group" style="padding: 40px;">
        <h3 style="color: var(--text-muted);">You're all caught up!</h3>
        <p style="color: var(--text-muted);">You have no system notices.</p>
    </div>
{% endif %}
{% endblock %}
```

#### Admin Post News Form (`app/templates/comms/post_news.html`)

A simple, secure interface for admins to broadcast to the grid.

```html
{% extends 'base.html' %}

{% block title %}Post News - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>
        <a href="{{ url_for('comms.news_feed') }}" style="text-decoration: none; color: var(--text-muted); font-size: 1rem;">&larr; Back to News</a><br>
        Post Grid Announcement
    </h2>
</div>

<form method="POST" action="{{ url_for('comms.post_news') }}" onsubmit="showLoading('newsSpinner', 'newsBtn')">
    <fieldset>
        <legend>Announcement Details</legend>
        
        <label>Headline / Title</label>
        <input type="text" name="title" placeholder="e.g., Scheduled Maintenance for Sunday" required>
        
        <label>Message Body</label>
        <textarea name="body" rows="6" placeholder="Type your announcement here..." required></textarea>
        
        <div style="background: var(--danger-bg); border: 1px solid var(--danger); padding: 12px; border-radius: 6px; margin-top: 10px;">
            <label class="radio" style="margin: 0; color: var(--danger); font-weight: bold;">
                <input type="checkbox" name="is_alert">
                Mark as Critical Alert (Highlights in Red)
            </label>
        </div>
        
        <button type="submit" id="newsBtn" style="margin-top: 16px; width: 100%;">
            <span>Publish Announcement</span>
            <div id="newsSpinner" class="spinner" style="display: none;"></div>
        </button>
    </fieldset>
</form>
{% endblock %}

{% block scripts %}
<script>
    function showLoading(spinnerId, btnId) {
        document.getElementById(spinnerId).style.display = "inline-block";
        document.getElementById(btnId).style.opacity = "0.8";
    }
</script>
{% endblock %}
```

**Immediate Visual Context:** By checking `{% if item.is_alert %}`, we dynamically swap the CSS classes to flood the background of the news item with a subtle red (`var(--danger-bg)`), instantly drawing user attention without needing complex JavaScript.

**Zero OpenSim Load:** Both the global news and the user notices pull entirely from the `OS_Pariah` read-write database. Your users can hit F5 on the news page all day long and the OpenSim Robust server will never feel a thing.

### The Background Worker (`worker.py`)

The background worker script. It replaces the legacy `parserobust` bash script and adds the asynchronous IAR backup processor.

By running this as a scheduled Cron job (or a continuous systemd service), parsing giant log files or generating multi-gigabyte IAR backups will not block the web portal or the OpenSim threads.

This is in the root of the `os_pariah_portal` directory. It uses the same database configuration as the web portal.

```python
import os
import re
import time
import uuid
import xmlrpc.client
import pymysql
from dotenv import load_dotenv

# Load environment variables (same as the web portal)
load_dotenv('.env')

# Database Config
PARIAH_DB_HOST = os.environ.get('PARIAH_DB_HOST', '127.0.0.1')
PARIAH_DB_USER = os.environ.get('PARIAH_DB_USER', 'pariah_user')
PARIAH_DB_PASS = os.environ.get('PARIAH_DB_PASS', 'pariah_password')
PARIAH_DB_NAME = os.environ.get('PARIAH_DB_NAME', 'os_pariah')

# Log Parsing Config
ROBUST_LOG_PATH = os.environ.get('ROBUST_LOG_PATH', '/home/opensim/Log/Robust-main.log')
LOG_STATE_FILE = '/tmp/pariah_robust_log.state'

# OpenSim RemoteAdmin Config (For IAR generation)
# Note: IARs are generated at the Region level, not Robust. For this, we always default to the first sim (port 9000) assumed to be Admin1.
REGION_XMLRPC_URL = os.environ.get('REGION_XMLRPC_URL', 'http://127.0.0.1:9000/')
REGION_XMLRPC_PASS = os.environ.get('REGION_XMLRPC_PASS', 'secret_remote_admin_pass')
IAR_OUTPUT_DIR = os.environ.get('IAR_OUTPUT_DIR', '/home/opensim/os_pariah_portal/app/static/downloads')

def get_db():
    """Returns a standalone connection to the OS_Pariah DB."""
    return pymysql.connect(
        host=PARIAH_DB_HOST, user=PARIAH_DB_USER, 
        password=PARIAH_DB_PASS, database=PARIAH_DB_NAME, 
        cursorclass=pymysql.cursors.DictCursor
    )

# ==========================================
# 1. GATEKEEPER LOG PARSER
# ==========================================
def parse_gatekeeper_logs():
    """
    Replaces the 'parserobust' bash script. 
    Reads the Robust log, extracts Gatekeeper login requests, and writes to the DB.
    """
    print("Starting Gatekeeper log ingestion...")
    if not os.path.exists(ROBUST_LOG_PATH):
        print(f"Log file not found: {ROBUST_LOG_PATH}")
        return

    # Read the last processed byte position to avoid re-parsing the whole file
    last_pos = 0
    if os.path.exists(LOG_STATE_FILE):
        with open(LOG_STATE_FILE, 'r') as f:
            last_pos = int(f.read().strip() or 0)

    # If the file shrank (log rotation), reset position to 0
    if os.path.getsize(ROBUST_LOG_PATH) < last_pos:
        last_pos = 0

    conn = get_db()
    inserted_count = 0

    # Regex to capture the exact string from your bash script logic
    # Example Target: [GATEKEEPER SERVICE]: Login request ...
    gatekeeper_regex = re.compile(r'\[GATEKEEPER SERVICE\]: Login request')

    try:
        with open(ROBUST_LOG_PATH, 'r', encoding='utf-8', errors='replace') as log_file:
            log_file.seek(last_pos)
            
            with conn.cursor() as cursor:
                for line in log_file:
                    if gatekeeper_regex.search(line):
                        # Extract data exactly as the bash script did, but safer
                        # This requires standard OpenSim log formatting logic.
                        # Assuming a standard log line structure:
                        # 2026-03-09 12:00:00,123 INFO - [GATEKEEPER SERVICE]: Login request for First Last (UUID) from ... IP:x, MAC:y, HostID:z
                        
                        try:
                            # Parse out the UUID
                            uuid_match = re.search(r'\(([a-f0-9\-]{36})\)', line, re.IGNORECASE)
                            if not uuid_match: continue
                            user_uuid = uuid_match.group(1)

                            # Parse Name (Bash logic handled names with dots or spaces)
                            # Simple extraction: look for "request for <name> ("
                            name_match = re.search(r'request for (.*?) \(', line)
                            user_name = name_match.group(1).replace('.', ' ') if name_match else "Unknown"

                            # [cite_start]Parse Network Data [cite: 58-62]
                            ip_match = re.search(r'IP:([^\s,]*)', line)
                            mac_match = re.search(r'MAC:([^\s,]*)', line)
                            hostid_match = re.search(r'HostID:([^\s,]*)', line)
                            from_match = re.search(r'from ([^\s]*)', line)

                            date_time = line[:19] # Grabs the 'YYYY-MM-DD HH:MM:SS' at the start

                            # Insert into the Pariah tracking tables using REPLACE to handle duplicates
                            if from_match:
                                cursor.execute("REPLACE INTO gatekeeper_from (user_uuid, date_time, user_name, inbound_from) VALUES (%s, %s, %s, %s)", 
                                               (user_uuid, date_time, user_name, from_match.group(1)))
                            if ip_match:
                                cursor.execute("REPLACE INTO gatekeeper_ip (user_uuid, date_time, user_name, user_ip) VALUES (%s, %s, %s, %s)", 
                                               (user_uuid, date_time, user_name, ip_match.group(1)))
                            if mac_match:
                                cursor.execute("REPLACE INTO gatekeeper_mac (user_uuid, date_time, user_name, user_mac) VALUES (%s, %s, %s, %s)", 
                                               (user_uuid, date_time, user_name, mac_match.group(1)))
                            if hostid_match:
                                cursor.execute("REPLACE INTO gatekeeper_host_id (user_uuid, date_time, user_name, user_host_id) VALUES (%s, %s, %s, %s)", 
                                               (user_uuid, date_time, user_name, hostid_match.group(1)))
                                               
                            inserted_count += 1
                        except Exception as parse_error:
                            print(f"Error parsing line: {parse_error}")
                            continue

            conn.commit()
            
            # Save our new byte offset so we don't re-read these lines next time
            with open(LOG_STATE_FILE, 'w') as state_file:
                state_file.write(str(log_file.tell()))
                
        print(f"Gatekeeper parsing complete. Processed {inserted_count} new logins.")
    except Exception as e:
        print(f"Log parser failed: {e}")
    finally:
        conn.close()


# ==========================================
# 2. ASYNCHRONOUS IAR BACKUP QUEUE
# ==========================================
def process_iar_backups():
    """
    Checks the OS_Pariah DB for pending IAR backup requests, triggers OpenSim 
    RemoteAdmin to generate them, and sends a notification to the user.
    """
    print("Checking for pending IAR backups...")
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            # Grab one pending backup at a time to avoid slamming the simulator
            cursor.execute("SELECT id, user_uuid FROM iar_backups WHERE status = 'pending' LIMIT 1")
            backup = cursor.fetchone()
            
            if not backup:
                return

            backup_id = backup['id']
            user_uuid = backup['user_uuid']
            
            # Mark as processing
            cursor.execute("UPDATE iar_backups SET status = 'processing' WHERE id = %s", (backup_id,))
            conn.commit()
            
            print(f"Processing IAR for User UUID: {user_uuid}")

            # Define the secure output file
            os.makedirs(IAR_OUTPUT_DIR, exist_ok=True)
            filename = f"backup_{user_uuid}_{int(time.time())}.iar"
            full_path = os.path.join(IAR_OUTPUT_DIR, filename)

            # Trigger the OpenSim Region RemoteAdmin command
            # Using standard OpenSim RemoteAdmin 'admin_save_iar'
            try:
                server = xmlrpc.client.ServerProxy(REGION_XMLRPC_URL)
                request_params = {
                    'password': REGION_XMLRPC_PASS,
                    'user': user_uuid,
                    'path': '/*', # Backup entire inventory
                    'filename': full_path
                }
                
                # Make the blocking call to the region server
                response = server.admin_save_iar(request_params)
                
                if response.get('success'):
                    # Success! Update the database
                    cursor.execute("UPDATE iar_backups SET status = 'completed', file_path = %s, completed_at = CURRENT_TIMESTAMP WHERE id = %s", 
                                   (filename, backup_id))
                                   
                    # Notify the user via the in-portal notices system
                    success_msg = f"Your Inventory Archive (IAR) backup has completed successfully and is ready for download."
                    cursor.execute("INSERT INTO user_notices (user_uuid, message) VALUES (%s, %s)", (user_uuid, success_msg))
                    
                    print(f"IAR backup completed successfully for {user_uuid}.")
                else:
                    raise Exception(response.get('error', 'Unknown OpenSim RemoteAdmin error.'))
                    
            except Exception as iar_error:
                print(f"IAR generation failed: {iar_error}")
                # Mark as failed and notify the user
                cursor.execute("UPDATE iar_backups SET status = 'failed' WHERE id = %s", (backup_id,))
                
                fail_msg = "Your Inventory Archive (IAR) backup failed to generate. Please contact support."
                cursor.execute("INSERT INTO user_notices (user_uuid, message) VALUES (%s, %s)", (user_uuid, fail_msg))

            conn.commit()
            
    except Exception as e:
        print(f"IAR processor encountered a critical error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # When triggered by cron, run both tasks sequentially
    parse_gatekeeper_logs()
    process_iar_backups()
```

**Setting it to process via Cron** Add this single line to run the worker every minute: `* * * * * /home/opensim/os_pariah_portal/venv/bin/python /home/opensim/os_pariah_portal/worker.py >> /home/opensim/Log/pariah_worker.log 2>&1`

**Byte-Offset Log Tracking:** Instead of copying log files and grepping through massive data blocks like the old bash script, the Python worker stores its exact byte location in `/tmp/pariah_robust_log.state`. It reads *only* the new lines appended since the last minute. This takes milliseconds.

**Synchronous Safety:** Generating an IAR locks OpenSim inventory threads. By wrapping it in `LIMIT 1` and triggering it via cron, we ensure that even if 50 users request a backup simultaneously, the worker gently hands them to OpenSim *one at a time*, preventing server lockups and kitten casualties.

**Closed Feedback Loop:** If OpenSim fails to generate the IAR, the worker gracefully catches the XMLRPC error, marks the database job as `failed`, and drops a system notice directly into the user's portal inbox .

### Documentation

A system this powerful is only as good as its documentation. If an installer cannot figure out how to deploy it, or an admin forgets how the ban system interacts with OpenSimulator, we risk confusing the users and, by extension, endangering the kittens.

We will build a clean, client-side tabbed interface so that visitors can instantly switch contexts without a page reload.

#### The Documentation Hub (`app/templates/docs/index.html`)

This template uses a simple Vanilla JavaScript tab system to keep the interface lightning-fast and uncluttered.

```html
{% extends 'base.html' %}

{% block title %}Documentation - OS Pariah Portal{% endblock %}

{% block content %}
<div class="nav-bar" style="border-bottom: none; margin-bottom: 10px;">
    <h2>OS Pariah Portal Documentation</h2>
</div>

<p style="color: var(--text-muted); margin-bottom: 24px;">
    Select a guide below to learn how to install, manage, develop, or use the portal.
</p>

<div style="display: flex; border-bottom: 2px solid var(--border-color); margin-bottom: 20px;">
    <button class="tab-button active" onclick="openTab(event, 'tab-users')" style="background: none; color: var(--text-main); border: none; border-bottom: 3px solid var(--primary); border-radius: 0; padding: 10px 20px; font-weight: bold; cursor: pointer;">Users</button>
    
    <button class="tab-button" onclick="openTab(event, 'tab-admins')" style="background: none; color: var(--text-muted); border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 10px 20px; font-weight: bold; cursor: pointer;">Administrators</button>
    
    <button class="tab-button" onclick="openTab(event, 'tab-installers')" style="background: none; color: var(--text-muted); border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 10px 20px; font-weight: bold; cursor: pointer;">Installers</button>
    
    <button class="tab-button" onclick="openTab(event, 'tab-developers')" style="background: none; color: var(--text-muted); border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 10px 20px; font-weight: bold; cursor: pointer;">Developers</button>
</div>

<div id="tab-users" class="tab-content" style="display: block;">
    <h3>User Guide</h3>
    <div class="group">
        <h4>1. Registration & Approval</h4>
        <p>To join the grid, fill out the registration form. Your account will be created but locked until staff approves it. You will receive an email once you are granted access.</p>
        
        <h4>2. Managing Your Profile</h4>
        <p>Navigate to <strong>My Profile</strong> to securely change your OpenSim password, update your email address, or request an Inventory Archive (IAR) backup. Backups run asynchronously; you will receive a Notice when your file is ready for download.</p>
        
        <h4>3. Helpdesk</h4>
        <p>If you encounter issues, use the <strong>Helpdesk</strong> to submit a ticket. You can attach screenshots or logs to assist staff.</p>
    </div>
</div>

<div id="tab-admins" class="tab-content" style="display: none;">
    <h3>Administrator Guide</h3>
    <div class="group">
        <h4>1. Approving Users</h4>
        <p>Pending registrations are locked at Level -1. Using the <strong>Approvals</strong> dashboard, reviewing the applicant's "Other Information", and clicking "Approve" will update their OpenSim level to 0 and notify them via email.</p>
        
        <h4>2. Bans & Gatekeeper</h4>
        <p>The <strong>Users & Bans</strong> tab allows you to cross-reference alt accounts using IP, MAC, and Host ID. Creating a ban actively locks the target user out of the grid by setting their UserLevel to a negative number.</p>
        
        <h4>3. Region Management</h4>
        <p>Region configurations are stored in the database. When you update limits or ports in the <strong>Regions</strong> tab, the simulator will automatically fetch the new XML configuration upon its next restart.</p>
    </div>
</div>

<div id="tab-installers" class="tab-content" style="display: none;">
    <h3>Installation & Deployment</h3>
    <div class="group">
        <h4>1. System Requirements</h4>
        <ul>
            <li><strong>OS:</strong> openSUSE Leap 15.6</li>
            <li><strong>Language:</strong> Python 3.11</li>
            <li><strong>Web Server:</strong> Nginx reverse proxying to Gunicorn WSGI.</li>
            <li><strong>Database:</strong> MariaDB (Requires two separate databases: `robust` and `os_pariah`).</li>
        </ul>
        
        <h4>2. Setup Instructions</h4>
        <ol>
            <li>Clone the portal repository to `/home/opensim/os_pariah_portal`.</li>
            <li>Create a Python virtual environment and `pip install -r requirements.txt`.</li>
            <li>Execute the `schema.sql` script to build the `os_pariah` database.</li>
            <li>Configure `/etc/systemd/system/pariah.service` and start the Gunicorn worker.</li>
            <li>Configure Nginx with `ProxyFix` headers to ensure accurate IP logging.</li>
        </ol>
    </div>
</div>

<div id="tab-developers" class="tab-content" style="display: none;">
    <h3>Developer Architecture</h3>
    <div class="group">
        <h4>1. Database Isolation</h4>
        <p>To prevent table locking on the grid, all portal configuration, tickets, and OIDC tokens are kept in the `os_pariah` database. The `robust` database is treated as read-heavy.</p>
        
        <h4>2. Robust API Wrapper</h4>
        <p>Do not write directly to OpenSim's tables for user creation. The portal uses an HTTP POST to the Robust private port (8003) with the `createuser` method.</p>
        
        <h4>3. OIDC Bridge</h4>
        <p>The portal acts as an Identity Provider. External apps (like Matrix) can authenticate users via the `/authorize`, `/token`, and `/userinfo` endpoints, which utilize short-lived JWTs.</p>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    function openTab(evt, tabId) {
        // Hide all tab contents
        var tabContents = document.getElementsByClassName("tab-content");
        for (var i = 0; i < tabContents.length; i++) {
            tabContents[i].style.display = "none";
        }
        
        // Remove 'active' styling from all buttons
        var tabButtons = document.getElementsByClassName("tab-button");
        for (var i = 0; i < tabButtons.length; i++) {
            tabButtons[i].style.color = "var(--text-muted)";
            tabButtons[i].style.borderBottom = "3px solid transparent";
        }
        
        // Show the current tab, and add an "active" class to the button that opened the tab
        document.getElementById(tabId).style.display = "block";
        evt.currentTarget.style.color = "var(--text-main)";
        evt.currentTarget.style.borderBottom = "3px solid var(--primary)";
    }
</script>
{% endblock %}
```

## The Draft of this Epic is Complete! 🎉

We have done the basic layout of the "OS Pariah: Portal" architecture.

We migrated the messy PHP and shell scripts into a clean, cohesive, secure, deeply integrated, object-oriented Python 3.11 environment on openSUSE. We protected the OpenSimulator grid's performance by decoupling the read/write operations and designed an interface optimized for minimal cognitive load. We mapped the UI, the Database, the Nginx/Gunicorn deployments, the asynchronous job queues, and the WebXML region configurations.

Here is a quick recap of the payload we've scoped to be part of this Portal:

* **Database Schema:** The isolated `os_pariah` structure.
* **Deployment Configs:** Nginx and Gunicorn systemd setups for openSUSE.
* **Application Factory:** Dynamic routing, DB connection pooling, and configuration caching.
* **OIDC Auth Bridge:** Secure, DB-backed identity management.
* **Registration & Approvals:** Turnstile-protected, Matrix-notified workflows.
* **High-Speed Online Lister:** 30-second memory-cached grid monitor.
* **Admin Controls:** Gatekeeper parsing , User Notes, and Active Banning.
* **Region Management:** WebXML generation for `Region.ini`.
* **Helpdesk:** Secure attachment handling and threaded replies.
* **User Controls:** Password resets, async IAR queues, and global News Feeds.
