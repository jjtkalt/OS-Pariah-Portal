import pytest
import sys
from unittest.mock import patch, MagicMock

if sys.platform == "win32":
    mock_fcntl = MagicMock()
    sys.modules["fcntl"] = mock_fcntl

from app import create_app
import app as main_app

@pytest.fixture
def db_cursor():
    """A global mock cursor we can use in our tests to assert SQL queries."""
    return MagicMock()

@pytest.fixture
def app(db_cursor):
    # Patch Popen to prevent rogue systemctl restarts
    with patch('app.__init__.subprocess.Popen') as mock_popen:
        
        # Boot the app
        app = create_app()

        # --- THE GLOBAL DATABASE SANDBOX ---
        # Overwrite the failed DB pools with Mocks
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        
        # Wire the pool to the connection, and the connection to the db_cursor
        mock_pool.connection.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = db_cursor
        
        # Force fetchone() to return None so get_dynamic_config gracefully uses our KNOWN_SETTINGS schema
        db_cursor.fetchone.return_value = None

        # Inject our mocks globally into the running app
        main_app.pariah_pool = mock_pool
        main_app.robust_pool = MagicMock()

        # Force the app into testing mode
        app.config.update({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "CACHE_TYPE": "SimpleCache"
        })

        yield app

@pytest.fixture
def client(app):
    """A dummy web browser to send GET/POST requests to our app."""
    return app.test_client()