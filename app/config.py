import os

class Config:
    # Flask Security
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'super_secret_pariah_session_key')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ---------------------------------------------------------
    # DATABASE OS_Pariah (Portal) - READ/WRITE
    # ---------------------------------------------------------
    PARIAH_DB_HOST = os.environ.get('PARIAH_DB_HOST', '127.0.0.1')
    PARIAH_DB_USER = os.environ.get('PARIAH_DB_USER', 'pariah_user')
    PARIAH_DB_PASS = os.environ.get('PARIAH_DB_PASS', 'pariah_password')
    PARIAH_DB_NAME = os.environ.get('PARIAH_DB_NAME', 'os_pariah')

    # ---------------------------------------------------------
    # DATABASE ROBUST (OpenSim) - READ ONLY
    # ---------------------------------------------------------
    ROBUST_DB_HOST = os.environ.get('ROBUST_DB_HOST', '127.0.0.1')
    ROBUST_DB_USER = os.environ.get('ROBUST_DB_USER', 'robust_ro')
    ROBUST_DB_PASS = os.environ.get('ROBUST_DB_PASS', 'robust_password')
    ROBUST_DB_NAME = os.environ.get('ROBUST_DB_NAME', 'robust')