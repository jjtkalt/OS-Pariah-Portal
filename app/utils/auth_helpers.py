from functools import wraps
from flask import session, redirect, url_for, flash

def require_active_user(f):
    """Bouncer: Ensures the user is logged in AND is not banned/pending."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('uuid'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
            
        if int(session.get('user_level', 0)) < 0:
            session.clear()
            flash('Your account access has been restricted.', 'error')
            return redirect(url_for('auth.login'))
            
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('uuid') or not session.get('is_admin'):
            flash('Access denied. Grid Staff only.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
