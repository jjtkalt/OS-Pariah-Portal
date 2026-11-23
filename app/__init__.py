import fcntl
import os
import subprocess

import pymysql
from dbutils.pooled_db import PooledDB
from flask import Flask, flash, g, redirect, request, session, url_for
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import validate_secret_key
from app.error_handlers import register_error_handlers

cache = Cache()
csrf = CSRFProtect()

robust_pool = None
app_pool = None


def resolve_grid_identity_asset(key):
    """Grid Identity asset paths fall back to the schema default when blanked out."""
    from app.utils.db import get_dynamic_config
    from app.utils.schema import KNOWN_SETTINGS

    value = (get_dynamic_config(key) or "").strip()
    if not value:
        value = KNOWN_SETTINGS["Grid Identity"][key]["default"]
    return value


# Pragmatic Content-Security-Policy (also set by nginx in packaged installs; Flask sends it
# too so dev / `flask run` / any non-nginx front end gets the same protection).
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self';"
)

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)

# Production state directory (created by the RPM). When present it becomes Flask's
# instance_path so uploads live OUTSIDE the code tree and OUTSIDE app/static.
PRODUCTION_STATE_DIR = "/var/lib/os-pariah"


def create_app(config_class="app.config.Config"):
    # instance_path: /var/lib/os-pariah when it exists (packaged install), otherwise
    # Flask's default <project>/instance directory (development).
    if os.path.isdir(PRODUCTION_STATE_DIR):
        app = Flask(__name__, instance_path=PRODUCTION_STATE_DIR)
    else:
        app = Flask(__name__)
    app.config.from_object(config_class)
    validate_secret_key(app)

    # Ticket attachments are private (served only via tickets.view_attachment after an
    # ownership / staff check). They must never live under app/static: nginx serves
    # /static/ directly and would expose them without authentication.
    # Override with OS_PARIAH_UPLOAD_FOLDER (see .env.example).
    app.config["UPLOAD_FOLDER"] = os.environ.get(
        "OS_PARIAH_UPLOAD_FOLDER"
    ) or os.path.join(app.instance_path, "uploads", "tickets")

    # Trust X-Forwarded-For / Proto only. Do NOT trust Host or Prefix — nginx clears
    # X-Forwarded-Host/Prefix and sets Host itself (host-header poisoning defense).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    csrf.init_app(app)
    register_error_handlers(app)

    with app.app_context():
        init_db_pools(app)

        # Initialize caching AFTER the config has been updated from the database
        cache.init_app(app)

        # --- WORKER STORM FIX: Only run in production/dev, NEVER in tests ---
        if not app.config.get("TESTING"):
            try:
                runtime_dir = "/run/os-pariah"
                lock_path = (
                    f"{runtime_dir}/iar_worker.lock"
                    if os.path.isdir(runtime_dir)
                    else "/tmp/.os-pariah-iar-worker.lock"
                )
                # Keep the lock file open for the worker lifetime (intentional; do not use
                # a context manager or the GC will release the flock).
                app._iar_lock_file = open(  # noqa: SIM115
                    lock_path, "w"
                )

                # Request an Exclusive, Non-Blocking lock (LOCK_EX | LOCK_NB)
                fcntl.flock(app._iar_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # If the code reaches this line, this worker WON the race!
                subprocess.Popen(
                    [
                        "/usr/bin/sudo",
                        "/bin/systemctl",
                        "start",
                        "os-pariah-worker-iar.service",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            except BlockingIOError:
                # Another worker already holds the lock. Quietly move on.
                pass
            except Exception as e:
                app.logger.error(f"Failed to wake IAR worker on boot: {e}")
        # --------------------------------------------------------------

    # Inject global variables into all Jinja2 templates automatically
    @app.context_processor
    def inject_globals():
        from app.utils import auth_helpers
        from app.utils.db import get_dynamic_config
        from app.utils.schema import RBAC_SCHEMA
        from app.utils.version import get_portal_version

        portal_background_image = resolve_grid_identity_asset("portal_background_image")
        portal_favicon = resolve_grid_identity_asset("portal_favicon")

        return {
            "grid_name": get_dynamic_config("grid_name"),
            "grid_website_url": get_dynamic_config("grid_website_url"),
            "turnstile_site_key": get_dynamic_config("TURNSTILE_SITE_KEY"),
            "custom_css_path": get_dynamic_config("custom_css_path"),
            "portal_background_image": portal_background_image,
            "portal_favicon": portal_favicon,
            "portal_version": get_portal_version(),
            "has_permission": auth_helpers.has_permission,
            "has_any_permissions": auth_helpers.has_any_permissions,
            "PERMS": auth_helpers,  # Allows {{ PERMS.PERM_SUPER_ADMIN }} in HTML
            "RBAC_SCHEMA": RBAC_SCHEMA,
            "check_bit": lambda mask, bit: bool(mask & bit),
        }

    from .blueprints.admin.routes import admin_bp
    from .blueprints.admin.user_mgmt import user_mgmt_bp
    from .blueprints.api.routes import api_bp
    from .blueprints.auth.routes import auth_bp
    from .blueprints.comms.routes import comms_bp
    from .blueprints.events.routes import events_bp
    from .blueprints.policies.routes import policies_bp
    from .blueprints.regions.routes import regions_bp
    from .blueprints.register.routes import register_bp
    from .blueprints.tickets.routes import tickets_bp
    from .blueprints.user.routes import user_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(register_bp, url_prefix="/register")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(tickets_bp, url_prefix="/tickets")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(user_mgmt_bp, url_prefix="/admin/users")
    app.register_blueprint(user_bp, url_prefix="/user")
    app.register_blueprint(comms_bp, url_prefix="/comms")
    app.register_blueprint(regions_bp, url_prefix="/regions")
    app.register_blueprint(policies_bp, url_prefix="/policies")
    app.register_blueprint(events_bp, url_prefix="/events")

    # Bot API uses its own bearer/token auth; OIDC token uses client_secret.
    csrf.exempt(api_bp)
    from app.blueprints.auth.routes import token as oidc_token_view

    csrf.exempt(oidc_token_view)

    @app.before_request
    def refresh_session_permissions():
        """Re-sync session permissions / userLevel from the DBs on every request.

        This is how bans (set_user_level), role changes (manage_roles) and level changes
        invalidate already-issued session cookies: no cookie kill is needed on those
        success paths because the next request overwrites session['permissions'] and
        session['user_level'], and logs out users whose Robust userLevel is now negative
        (unless it is the policy-decline tier).
        """
        # Tests set session permissions directly; opt in with REFRESH_SESSION_AUTH.
        if app.config.get("TESTING") and not app.config.get("REFRESH_SESSION_AUTH"):
            return
        if "uuid" not in session:
            return
        if request.endpoint in ("static", "auth.login", "auth.logout"):
            return

        from app.utils.auth_helpers import refresh_session_auth

        return refresh_session_auth()

    @app.before_request
    def require_policy_agreement():
        # --- TEST BOT IMMUNITY ---
        if app.config.get("TESTING"):
            return
        # -------------------------

        from app.utils.auth_helpers import is_policy_decline_session
        from app.utils.db import get_app_db, get_dynamic_config

        if "uuid" not in session:
            return

        # Account is at the configurable "declined policies" Robust tier: only auth, API, policy bouncer, and policy document views
        if is_policy_decline_session():
            if request.blueprint in ["auth", "api"] or request.endpoint in [
                "static",
                "manual",
                "favicon",
                "user.policy_agreement",
                "policies.view_policy",
            ]:
                return
            flash(
                "You must review and agree to the grid policies to restore access.",
                "info",
            )
            return redirect(url_for("user.policy_agreement"))

        exempt_blueprints = ["auth", "api"]
        if request.blueprint in exempt_blueprints or request.endpoint in [
            "static",
            "manual",
            "favicon",
            "user.policy_agreement",
            "policies.view_policy",
        ]:
            return

        current_version = get_dynamic_config("global_policy_version")

        # Bypass completely if the grid hasn't set up policies yet
        if current_version == "0.0":
            return

        app_conn = get_app_db()
        with app_conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM policy_agreements WHERE user_uuid = %s AND policy_version = %s",
                (session["uuid"], current_version),
            )
            agreed = cursor.fetchone()

        if not agreed:
            flash("You must agree to the updated policies before continuing.", "info")
            return redirect(url_for("user.policy_agreement"))

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response

    @app.teardown_appcontext
    def close_db_connections(exception):
        robust_conn = g.pop("robust_conn", None)
        if robust_conn is not None:
            robust_conn.close()

        app_conn = g.pop("app_conn", None)
        if app_conn is not None:
            app_conn.close()

    @app.route("/")
    def index():
        return redirect(url_for("comms.news_feed"))

    @app.route("/manual.html")
    def manual():
        """Fallback when nginx is not serving the static manual (dev / flask run)."""
        from flask import send_from_directory

        static_manual = os.path.join(app.static_folder, "manual.html")
        if os.path.isfile(static_manual):
            return send_from_directory(app.static_folder, "manual.html")
        from flask import render_template

        return render_template("manual.html")

    @app.route("/favicon.ico")
    def favicon():
        """Root shortcut icon for clients that probe /favicon.ico without a link tag."""
        return redirect(resolve_grid_identity_asset("portal_favicon"))

    @app.route("/docs")
    def docs():
        from flask import render_template

        from app.utils.db import get_app_db

        app_conn = get_app_db()
        with app_conn.cursor() as cursor:
            cursor.execute(
                "SELECT slug, title, category, requires_login FROM policies ORDER BY title ASC"
            )
            all_docs = cursor.fetchall()

        # Split the documents into their respective categories
        policies = [d for d in all_docs if d["category"] == "Policy"]
        guides = [d for d in all_docs if d["category"] == "Guide"]
        resources = [d for d in all_docs if d["category"] == "Resource"]

        return render_template(
            "docs/index.html", policies=policies, guides=guides, resources=resources
        )

    return app


def init_db_pools(app):
    global robust_pool, app_pool
    try:
        # 1. Initialize OS-Pariah Pool FIRST from system config
        app_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            blocking=True,
            ping=1,
            host=app.config["OS_PARIAH_DB_HOST"],
            user=app.config["OS_PARIAH_DB_USER"],
            password=app.config["OS_PARIAH_DB_PASS"],
            database=app.config["OS_PARIAH_DB_NAME"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

        # 2. Fetch dynamic portal settings (cache, session) from the config table
        conn = app_pool.connection()
        db_configs = {}
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_key, config_value FROM config")
            for row in cursor.fetchall():
                db_configs[row["config_key"]] = row["config_value"]
        conn.close()

        # 3. Apply DB-driven settings directly to the Flask App Config
        app.config["PERMANENT_SESSION_LIFETIME"] = int(
            db_configs.get("PERMANENT_SESSION_LIFETIME", 28800)
        )
        app.config["CACHE_TYPE"] = db_configs.get("CACHE_TYPE", "SimpleCache")
        app.config["CACHE_DEFAULT_TIMEOUT"] = int(
            db_configs.get("CACHE_DEFAULT_TIMEOUT", 30)
        )

        # 4. Initialize Robust Pool using system config (NO LONGER RELIES ON PORTAL DB)
        robust_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            blocking=True,
            ping=1,
            host=app.config.get("ROBUST_DB_HOST", "127.0.0.1"),
            user=app.config.get("ROBUST_DB_USER", "robust_user"),
            password=app.config.get("ROBUST_DB_PASS", "robust_password"),
            database=app.config.get("ROBUST_DB_NAME", "robust"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

        app.logger.info("Successfully initialized dual MariaDB connection pools.")
    except Exception as e:
        app.logger.critical(f"CRITICAL: Failed to initialize database pools: {e}")
