import pytest
from unittest.mock import patch
from app import create_app

@pytest.fixture
def app():
    # We "patch" (mock) the subprocess.Popen call so running tests 
    # doesn't try to trigger real systemctl commands on the host OS.
    with patch('app.__init__.subprocess.Popen') as mock_popen:
        
        # Spin up the app using your factory
        app = create_app()
        
        # Force the app into testing mode
        app.config.update({
            "TESTING": True, # Why else do this?
            "WTF_CSRF_ENABLED": False, # Disables CSRF tokens so our test bot can submit forms
            "CACHE_TYPE": "SimpleCache" # Define the cache type to avoid the warnings
        })

        yield app

@pytest.fixture
def client(app):
    """A dummy web browser to send GET/POST requests to our app."""
    return app.test_client()
