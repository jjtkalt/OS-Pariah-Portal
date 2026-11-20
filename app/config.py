import os
import warnings

# Avoid editing this file directly.  Edit the /etc/os-pariah/os-pariah.conf and keep it secure.

_INSECURE_SECRET = "dev-only-insecure-secret-change-me"


class Config:
    # Flask Security
    # Platform standard: SECRET_KEY is auto-generated into /etc/os-pariah/secrets on first
    # start (scripts/ensure_secrets.py). FLASK_SECRET_KEY remains a fallback so existing
    # deployments that still set it keep working. The literal default is refused outside
    # TESTING / explicit FLASK_ENV=development.
    SECRET_KEY = (
        os.environ.get("SECRET_KEY")
        or os.environ.get("FLASK_SECRET_KEY")
        or _INSECURE_SECRET
    )
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True
    # Match nginx client_max_body_size 10M
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # ---------------------------------------------------------
    # DATABASE OS-Pariah (Portal) - READ/WRITE
    # ---------------------------------------------------------
    OS_PARIAH_DB_HOST = os.environ.get("OS_PARIAH_DB_HOST", "127.0.0.1")
    OS_PARIAH_DB_USER = os.environ.get("OS_PARIAH_DB_USER", "os-pariah")
    OS_PARIAH_DB_PASS = os.environ.get("OS_PARIAH_DB_PASS", "os-pariah-password")
    OS_PARIAH_DB_NAME = os.environ.get("OS_PARIAH_DB_NAME", "os_pariah")

    # ---------------------------------------------------------
    # DATABASE ROBUST (OpenSim) - READ ONLY
    # ---------------------------------------------------------
    ROBUST_DB_HOST = os.environ.get("ROBUST_DB_HOST", "127.0.0.1")
    ROBUST_DB_USER = os.environ.get("ROBUST_DB_USER", "robust_ro")
    ROBUST_DB_PASS = os.environ.get("ROBUST_DB_PASS", "robust_password")
    ROBUST_DB_NAME = os.environ.get("ROBUST_DB_NAME", "robust")


class DevelopmentConfig(Config):
    """Local development only — allows the insecure SECRET_KEY fallback."""

    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key-not-for-production"
    CACHE_TYPE = "SimpleCache"


class ProductionConfig(Config):
    """Production: refuse to start with the insecure default SECRET_KEY."""

    pass


def validate_secret_key(app):
    """Fail closed when SECRET_KEY is the insecure default outside test/dev."""
    key = app.config.get("SECRET_KEY")
    if key != _INSECURE_SECRET:
        return
    if app.config.get("TESTING"):
        return
    env = (os.environ.get("FLASK_ENV") or os.environ.get("FLASK_DEBUG") or "").lower()
    if env in ("development", "1", "true") or app.config.get("DEBUG"):
        warnings.warn(
            "Using insecure default SECRET_KEY; set SECRET_KEY in /etc/os-pariah/secrets",
            UserWarning,
            stacklevel=2,
        )
        return
    raise RuntimeError(
        "Refusing to start with the insecure default SECRET_KEY. "
        "Ensure /etc/os-pariah/secrets is generated (migrate.py / ensure_secret_key) "
        "or set SECRET_KEY / FLASK_SECRET_KEY in the environment."
    )
