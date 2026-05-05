from functools import wraps
from flask import session, redirect, url_for, flash
from app.utils.schema import *

def get_policy_decline_level():
    """Robust userLevel used when a user declines updated policies (configurable)."""
    from app.utils.db import get_dynamic_config
    raw = get_dynamic_config('policy_decline_user_level')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -4

def is_policy_decline_session():
    """True if the logged-in user's Robust level matches the policy-decline lock tier."""
    try:
        return int(session.get('user_level', 0)) == get_policy_decline_level()
    except (TypeError, ValueError):
        return False

def require_active_user(f):
    """Bouncer: Ensures the user is logged in AND is not banned/pending."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('uuid'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
            
        lvl = int(session.get('user_level', 0))
        if lvl < 0:
            if is_policy_decline_session():
                flash('You must agree to the current policies before accessing that area.', 'info')
                return redirect(url_for('user.policy_agreement'))
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


def has_any_permissions():
    """True when session RBAC mask is non-zero (any portal permission bits assigned)."""
    try:
        return int(session.get('permissions', 0)) != 0
    except (TypeError, ValueError):
        return False


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