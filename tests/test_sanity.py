def test_app_is_testing(app):
    """Ensures the test configuration successfully overrides the main config."""
    assert app.config['TESTING'] is True

def test_home_page_loads(client):
    """
    Simulates a user navigating to the root URL (/). 
    Depending on your routing, it should either return 200 OK (if they can see a homepage)
    or 302 Found (if it immediately redirects a guest to the login screen).
    It should NOT return 500 (Server Error) or 404 (Not Found).
    """
    response = client.get('/')
    assert response.status_code in [200, 302]
