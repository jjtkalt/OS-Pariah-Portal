import os

# Avoid editing this file directly.  Edit the /etc/os_pariah/os-pariah.conf and keep it secure.


class Config:
    # Flask Security
    # Platform standard: SECRET_KEY is auto-generated into /etc/os_pariah/secrets on first
    # start (scripts/ensure_secrets.py). FLASK_SECRET_KEY remains a fallback so existing
    # deployments that still set it keep working. The literal default is dev-only.
    SECRET_KEY = (
        os.environ.get("SECRET_KEY")
        or os.environ.get("FLASK_SECRET_KEY")
        or "dev-only-insecure-secret-change-me"
    )
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ---------------------------------------------------------
    # DATABASE OS_Pariah (Portal) - READ/WRITE
    # ---------------------------------------------------------
    PARIAH_DB_HOST = os.environ.get("PARIAH_DB_HOST", "127.0.0.1")
    PARIAH_DB_USER = os.environ.get("PARIAH_DB_USER", "pariah_user")
    PARIAH_DB_PASS = os.environ.get("PARIAH_DB_PASS", "pariah_password")
    PARIAH_DB_NAME = os.environ.get("PARIAH_DB_NAME", "os_pariah")

    # ---------------------------------------------------------
    # DATABASE ROBUST (OpenSim) - READ ONLY
    # ---------------------------------------------------------
    ROBUST_DB_HOST = os.environ.get("ROBUST_DB_HOST", "127.0.0.1")
    ROBUST_DB_USER = os.environ.get("ROBUST_DB_USER", "robust_ro")
    ROBUST_DB_PASS = os.environ.get("ROBUST_DB_PASS", "robust_password")
    ROBUST_DB_NAME = os.environ.get("ROBUST_DB_NAME", "robust")
