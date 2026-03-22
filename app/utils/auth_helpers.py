from functools import wraps
from flask import session, redirect, url_for, flash

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('uuid') or not session.get('is_admin'):
            flash('Access denied. Grid Staff only.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
