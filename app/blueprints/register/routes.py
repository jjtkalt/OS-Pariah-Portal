import uuid
import re
from flask import Blueprint, request, render_template, flash, redirect, url_for, current_app
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.robust_api import create_robust_user, set_user_level
from app.blueprints.auth.routes import verify_turnstile
from app.utils.notifications import send_verification_email, notify_staff_new_app

register_bp = Blueprint('register', __name__)

def validate_invite_code(code):
    """Stub for future invite code validation logic."""
    return True

@register_bp.route('/', methods=['GET', 'POST'])
def register():
    # Fetch dynamic configurations from OS_Pariah DB
    require_approval = get_dynamic_config('require_admin_approval', 'true') == 'true'
    require_other_info = get_dynamic_config('require_other_info', 'true') == 'true'
    require_invite_code = get_dynamic_config('require_invite_code', 'false') == 'true'

    if request.method == 'GET':
        site_key = get_dynamic_config('TURNSTILE_SITE_KEY', '3x00000000000000000000FF')

        # Fetch the dynamic policy links
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("SELECT slug, title FROM policies ORDER BY title ASC")
            active_policies = cursor.fetchall()

        return render_template(
            'register/index.html', 
            site_key=site_key,
            require_other_info=require_other_info,
            require_invite_code=require_invite_code,
            policies=active_policies # Pass them to the template
        )

    # --- 1. Security & Bot Check ---
    turnstile_response = request.form.get('cf-turnstile-response')
    if not verify_turnstile(turnstile_response):
        flash('Security check failed. Please ensure you are human.', 'error')
        return redirect(url_for('register.register'))

    # --- 2. Collect Mandatory Fields ---
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    inviter = request.form.get('inviter', '').strip()
    discord = request.form.get('discord_handle', '').strip() # Optional
    matrix = request.form.get('matrix_handle', '').strip() # Optional
    
    # --- 3. Policy & Age Verification ---
    policy_check = request.form.get('policy_check')
    age_check = request.form.get('age_check')
    if not policy_check or not age_check:
        flash('You must agree to the policies and attest you are 18+.', 'error')
        return redirect(url_for('register.register'))

    # --- 4. Dynamic Field Validation ---
    other_info = ""
    if require_other_info:
        other_info = request.form.get('other_info', '').strip()
        word_count = len(re.findall(r'\w+', other_info))
        if word_count < 30:
            flash('Your "Other Information" must be at least 30 words.', 'error')
            return redirect(url_for('register.register'))

    if require_invite_code:
        invite_code = request.form.get('invite_code', '').strip()
        if not validate_invite_code(invite_code):
            flash('Invalid or expired invite code.', 'error')
            return redirect(url_for('register.register'))

    # --- 5. Safely Create User in OpenSim (Level -1) ---
    new_uuid = create_robust_user(first_name, last_name, password, email)
    
    if not new_uuid:
        flash('Registration failed. The avatar name might already be taken or the grid is offline.', 'error')
        return redirect(url_for('register.register'))
        
    # Immediately lock the account by setting level to -1
    set_user_level(new_uuid, -1)

    # --- 6. Track Registration State in Pariah DB ---
    verification_token = uuid.uuid4().hex
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO pending_registrations
               (user_uuid, email, inviter, discord, matrix, other_info, verification_token, requires_approval, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (new_uuid, email, inviter, discord, matrix, other_info, verification_token, require_approval, 'pending_email')
        )
    pariah_conn.commit()

    # --- 7. Dispatch Workflows ---
    send_verification_email(email, verification_token)
    
    flash('Registration successful! Please check your email to verify your address.', 'success')
    return redirect(url_for('auth.login'))

@register_bp.route('/verify/<token>')
def verify_email(token):
    pariah_conn = get_pariah_db()
    
    try:
        # 1. Look up the token
        with pariah_conn.cursor() as cursor:
            cursor.execute("""
                SELECT user_uuid, email, requires_approval, status, inviter, discord, matrix, other_info 
                FROM pending_registrations 
                WHERE verification_token = %s
            """, (token,))
            reg = cursor.fetchone()

        if not reg:
            flash('Invalid or expired verification link.', 'error')
            return redirect(url_for('auth.login'))

        if reg['status'] != 'pending_email':
            flash('This email address has already been verified.', 'info')
            return redirect(url_for('auth.login'))

        user_uuid = reg['user_uuid']
        
        # 2. Safely grab their first and last name from Robust for the staff notification
        robust_conn = get_robust_db()
        first_name, last_name = "Unknown", "User"
        with robust_conn.cursor() as r_cursor:
            r_cursor.execute("SELECT FirstName, LastName FROM useraccounts WHERE PrincipalID = %s", (user_uuid,))
            account = r_cursor.fetchone()
            if account:
                first_name, last_name = account['FirstName'], account['LastName']

        # 3. Process the Verification
        with pariah_conn.cursor() as cursor:
            if reg['requires_approval']:
                # Change state so it shows up in the Admin Approvals Dashboard
                cursor.execute("UPDATE pending_registrations SET status = 'pending_approval' WHERE user_uuid = %s", (user_uuid,))
                flash('Email verified! Your account is now awaiting staff approval. You will receive an email once approved.', 'success')
                
                # Ping staff NOW, because we know they are a real human with a working email!
                notify_staff_new_app(first_name, last_name, user_uuid, reg['inviter'], reg['discord'], reg['matrix'], reg['other_info'])
            else:
                # No admin approval required! Auto-activate them immediately.
                cursor.execute("UPDATE pending_registrations SET status = 'approved' WHERE user_uuid = %s", (user_uuid,))
                set_user_level(user_uuid, 0)
                flash('Email verified! Your account has been activated and you can now log in to the grid.', 'success')
        
        pariah_conn.commit()

    except Exception as e:
        current_app.logger.error(f"Error during email verification: {e}")
        flash('An internal error occurred during verification. Please contact support.', 'error')

    return redirect(url_for('auth.login'))
