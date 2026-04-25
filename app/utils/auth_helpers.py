from functools import wraps
from flask import session, redirect, url_for, flash
from app.utils.schema import *

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

def has_permission(required_bit):
    """Core Logic: Checks if the current session user has the required permission."""
    user_perms = session.get('permissions', 0)
    
    # Master Key check: Bit 0 (PERM_SUPER_ADMIN) grants everything
    if user_perms & PERM_SUPER_ADMIN:
        return True
        
    # Bitwise AND comparison
    return bool(user_perms & required_bit)

def rbac_required(permission):
    """Decorator for Flask routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('uuid'):
                flash('Please log in.', 'error')
                return redirect(url_for('auth.login'))
            
            if not has_permission(permission):
                flash('Unauthorized: You lack the required portal permissions.', 'error')
                return redirect(url_for('comms.news_feed'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator