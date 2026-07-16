"""
Shared environment loading for CLI scripts under scripts/.

/etc/os_pariah/os-pariah.conf is installed from .env.example (KEY=value), same as
worker.py and wsgi — not ConfigParser INI with [sections].
"""

import logging
import os
import sys

import pymysql
from dotenv import load_dotenv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)


def load_pariah_dotenv():
    """Match worker.py / wsgi.py: system config first, then project .env, then secrets."""
    if os.path.exists("/etc/os_pariah/os-pariah.conf"):
        load_dotenv("/etc/os_pariah/os-pariah.conf")
    else:
        load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

    # Load the auto-generated SECRET_KEY without overriding existing environment values.
    if _SCRIPT_DIR not in sys.path:
        sys.path.insert(0, _SCRIPT_DIR)
    from ensure_secrets import load_secrets_file

    load_secrets_file()


def get_pariah_db_connection():
    load_pariah_dotenv()
    return pymysql.connect(
        host=os.environ.get("PARIAH_DB_HOST", "127.0.0.1"),
        user=os.environ.get("PARIAH_DB_USER", "pariah_user"),
        password=os.environ.get("PARIAH_DB_PASS", "pariah_password"),
        database=os.environ.get("PARIAH_DB_NAME", "os_pariah"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_dynamic_config_for_scripts(conn, key, default=None):
    """
    Resolve a portal setting the same way worker.py does: DB row first, then KNOWN_SETTINGS default.

    Standalone scripts cannot use app.utils.db.get_dynamic_config (Flask app context).
    """
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from app.utils.schema import KNOWN_SETTINGS

    with conn.cursor() as cursor:
        cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
        result = cursor.fetchone()
        if result:
            return result["config_value"]

    for _category, settings in KNOWN_SETTINGS.items():
        if key in settings:
            return settings[key].get("default", default)

    return default


def configure_sync_logging(name: str) -> logging.Logger:
    """stderr plus /var/log/os_pariah/sync_workers.log when writable (matches packaged deployments)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)
    log_dir = "/var/log/os_pariah"
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "sync_workers.log")
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning(
            "Could not write to %s/sync_workers.log; using stderr only.", log_dir
        )
    logger.propagate = False
    return logger
