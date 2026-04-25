from flask import Flask, g, request, session, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_caching import Cache
from dbutils.pooled_db import PooledDB
import pymysql
import subprocess
import os
import fcntl

cache = Cache()

robust_pool = None
pariah_pool = None

def create_app(config_class='app.config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    with app.app_context():
        init_db_pools(app)

        # Initialize caching AFTER the config has been updated from the database
        cache.init_app(app)

        # --- WORKER STORM FIX: Only run in production/dev, NEVER in tests ---
        if not app.config.get('TESTING'):
            try:
                # Attach the file to the app object so Python's Garbage Collector doesn't destroy it!
                app._iar_lock_file = open('/tmp/.pariah_iar_worker.lock', 'w')
                
                # Request an Exclusive, Non-Blocking lock (LOCK_EX | LOCK_NB)
                fcntl.flock(app._iar_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                # If the code reaches this line, this worker WON the race!
                subprocess.Popen(
                    ["/usr/bin/sudo", "/bin/systemctl", "start", "pariah-worker-iar.service"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
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
        from app.utils.db import get_dynamic_config
        from app.utils import auth_helpers
        from app.utils.schema import RBAC_SCHEMA

        return {
            'grid_name': get_dynamic_config('grid_name'),
            'grid_website_url': get_dynamic_config('grid_website_url'),
            'turnstile_site_key': get_dynamic_config('TURNSTILE_SITE_KEY'),
            'custom_css_path': get_dynamic_config('custom_css_path'),
            'has_permission': auth_helpers.has_permission,
            'PERMS': auth_helpers, # Allows {{ PERMS.PERM_SUPER_ADMIN }} in HTML
            'RBAC_SCHEMA': RBAC_SCHEMA,
            'check_bit': lambda mask, bit: bool(mask & bit)
        }

    from .blueprints.auth.routes import auth_bp
    from .blueprints.register.routes import register_bp
    from .blueprints.api.routes import api_bp
    from .blueprints.tickets.routes import tickets_bp
    from .blueprints.admin.routes import admin_bp
    from .blueprints.admin.user_mgmt import user_mgmt_bp
    from .blueprints.user.routes import user_bp
    from .blueprints.comms.routes import comms_bp
    from .blueprints.regions.routes import regions_bp
    from .blueprints.policies.routes import policies_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(register_bp, url_prefix='/register')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(tickets_bp, url_prefix='/tickets')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_mgmt_bp, url_prefix='/admin/users')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(comms_bp, url_prefix='/comms')
    app.register_blueprint(regions_bp, url_prefix='/regions')
    app.register_blueprint(policies_bp, url_prefix='/policies')

    @app.before_request
    def require_policy_agreement():
        # --- TEST BOT IMMUNITY ---
        if app.config.get('TESTING'):
            return
        # -------------------------
        
        from app.utils.db import get_pariah_db, get_dynamic_config
        
        if 'uuid' not in session:
            return
            
        exempt_blueprints = ['auth', 'api']
        if request.blueprint in exempt_blueprints or request.endpoint in ['static', 'user.policy_agreement', 'policies.view_policy']:
            return
            
        current_version = get_dynamic_config('global_policy_version')

        # Bypass completely if the grid hasn't set up policies yet
        if current_version == '0.0':
            return

        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM policy_agreements WHERE user_uuid = %s AND policy_version = %s",
                (session['uuid'], current_version)
            )
            agreed = cursor.fetchone()
            
        if not agreed:
            flash("You must agree to the updated policies before continuing.", "info")
            return redirect(url_for('user.policy_agreement'))

    @app.teardown_appcontext
    def close_db_connections(exception):
        robust_conn = g.pop('robust_conn', None)
        if robust_conn is not None:
            robust_conn.close()

        pariah_conn = g.pop('pariah_conn', None)
        if pariah_conn is not None:
            pariah_conn.close()

    @app.route('/')
    def index():
        return redirect(url_for('comms.news_feed'))

    @app.route('/docs')
    def docs():
        from flask import render_template
        from app.utils.db import get_pariah_db
        
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("SELECT slug, title, category, requires_login FROM policies ORDER BY title ASC")
            all_docs = cursor.fetchall()

        # Split the documents into their respective categories
        policies = [d for d in all_docs if d['category'] == 'Policy']
        guides = [d for d in all_docs if d['category'] == 'Guide']
        resources = [d for d in all_docs if d['category'] == 'Resource']

        return render_template('docs/index.html', policies=policies, guides=guides, resources=resources)

    return app

def init_db_pools(app):
    global robust_pool, pariah_pool
    try:
        # 1. Initialize Pariah Pool FIRST from system config
        pariah_pool = PooledDB(
            creator=pymysql, maxconnections=10, mincached=2, blocking=True, ping=1,
            host=app.config['PARIAH_DB_HOST'], user=app.config['PARIAH_DB_USER'],
            password=app.config['PARIAH_DB_PASS'], database=app.config['PARIAH_DB_NAME'],
            cursorclass=pymysql.cursors.DictCursor
        )

        # 2. Fetch dynamic portal settings (cache, session) from the config table
        conn = pariah_pool.connection()
        db_configs = {}
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_key, config_value FROM config")
            for row in cursor.fetchall():
                db_configs[row['config_key']] = row['config_value']
        conn.close()

        # 3. Apply DB-driven settings directly to the Flask App Config
        app.config['PERMANENT_SESSION_LIFETIME'] = int(db_configs.get('PERMANENT_SESSION_LIFETIME', 28800))
        app.config['CACHE_TYPE'] = db_configs.get('CACHE_TYPE', 'SimpleCache')
        app.config['CACHE_DEFAULT_TIMEOUT'] = int(db_configs.get('CACHE_DEFAULT_TIMEOUT', 30))

        # 4. Initialize Robust Pool using system config (NO LONGER RELIES ON PARIAH DB)
        robust_pool = PooledDB(
            creator=pymysql, maxconnections=10, mincached=2, blocking=True, ping=1,
            host=app.config.get('ROBUST_DB_HOST', '127.0.0.1'),
            user=app.config.get('ROBUST_DB_USER', 'robust_user'),
            password=app.config.get('ROBUST_DB_PASS', 'robust_password'),
            database=app.config.get('ROBUST_DB_NAME', 'robust'),
            cursorclass=pymysql.cursors.DictCursor
        )

        app.logger.info("Successfully initialized dual MariaDB connection pools.")
    except Exception as e:
        app.logger.critical(f"CRITICAL: Failed to initialize database pools: {e}")