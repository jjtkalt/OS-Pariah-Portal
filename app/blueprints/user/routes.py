import os
import uuid
import subprocess
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app, send_from_directory
from app.utils.db import get_pariah_db, get_dynamic_config
from app.utils.robust_api import call_robust_api, update_robust_email
from app.utils.notifications import send_verification_email, send_email_change_verification

user_bp = Blueprint('user', __name__, url_prefix='/user')

def update_robust_password(user_uuid, new_password):
    """Safely updates the user's password via the Robust API."""
    payload = {
        'PrincipalID': user_uuid,
        'Password': new_password
    }
    response_text = call_robust_api('setaccount', payload)
    return response_text and 'True' in response_text

@user_bp.route('/profile', methods=['GET'])
def profile():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT status, requested_at, file_path FROM iar_backups WHERE user_uuid = %s ORDER BY requested_at DESC LIMIT 5", (session['uuid'],))
        backups = cursor.fetchall()
        
    return render_template('user/profile.html', backups=backups)

@user_bp.route('/profile/password', methods=['POST'])
def update_password():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('user.profile'))
        
    if update_robust_password(session['uuid'], new_password):
        flash('Password updated successfully.', 'success')
    else:
        flash('Failed to update password. Please try again.', 'error')
        
    return redirect(url_for('user.profile'))

@user_bp.route('/profile/email', methods=['POST'])
def request_email_change():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))

    new_email = request.form.get('new_email').strip()
    verification_token = uuid.uuid4().hex

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO pending_registrations (user_uuid, email, verification_token, requires_approval, status) 
            VALUES (%s, %s, %s, FALSE, 'pending_email_change')
            ON DUPLICATE KEY UPDATE email = VALUES(email), verification_token = VALUES(verification_token), status='pending_email_change'
        """, (session['uuid'], new_email, verification_token))
    pariah_conn.commit()

    send_email_change_verification(new_email, verification_token)
    flash('A verification link has been sent to your new email address.', 'info')
    return redirect(url_for('user.profile'))

@user_bp.route('/verify-email/<token>')
def verify_email_change(token):
    """Dedicated endpoint for verifying an email update, bypassing the new-user workflow."""
    pariah_conn = get_pariah_db()
    
    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute("""
                SELECT user_uuid, email, status 
                FROM pending_registrations 
                WHERE verification_token = %s
            """, (token,))
            reg = cursor.fetchone()

        if not reg or reg['status'] != 'pending_email_change':
            flash('Invalid or expired email verification link.', 'error')
            return redirect(url_for('user.profile'))

        # Use the Robust API to update the email securely
        if update_robust_email(reg['user_uuid'], reg['email']):
            # Clean up the pending row
            with pariah_conn.cursor() as cursor:
                cursor.execute("DELETE FROM pending_registrations WHERE user_uuid = %s AND status = 'pending_email_change'", (reg['user_uuid'],))
            pariah_conn.commit()
            flash('Your email address has been successfully updated.', 'success')
        else:
            flash('Failed to update email address in the grid database.', 'error')

    except Exception as e:
        current_app.logger.error(f"Error during email change verification: {e}")
        flash('An internal error occurred during verification. Please contact support.', 'error')

    return redirect(url_for('user.profile'))

@user_bp.route('/profile/backup', methods=['POST'])
def request_iar_backup():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))
        
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM iar_backups WHERE user_uuid = %s AND status IN ('pending', 'processing')", (session['uuid'],))
        if cursor.fetchone()['count'] > 0:
            flash('You already have a backup in progress.', 'error')
            return redirect(url_for('user.profile'))
            
        cursor.execute("INSERT INTO iar_backups (user_uuid, status) VALUES (%s, 'pending')", (session['uuid'],))
    pariah_conn.commit()
    
    try:
        subprocess.Popen(["/usr/bin/sudo", "/bin/systemctl", "start", "pariah-worker-iar.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        current_app.logger.error(f"Failed to trigger IAR worker service: {e}")
    
    flash('Your inventory backup has been queued. You will be notified when it is ready for download.', 'success')
    return redirect(url_for('user.profile'))

@user_bp.route('/policies/agree', methods=['GET', 'POST'])
def policy_agreement():
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))

    current_version = get_dynamic_config('global_policy_version')
    pariah_conn = get_pariah_db()

    if request.method == 'POST':
        if request.form.get('agree') == 'yes':
            with pariah_conn.cursor() as cursor:
                cursor.execute(
                    "INSERT IGNORE INTO policy_agreements (user_uuid, policy_version) VALUES (%s, %s)",
                    (session['uuid'], current_version)
                )
            pariah_conn.commit()
            flash('Thank you for agreeing to the updated grid policies.', 'success')
            return redirect(url_for('comms.news_feed'))
        else:
            flash('You must agree to the policies to access the portal.', 'error')

    last_agreed = None
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT MAX(agreed_at) as last_agreed FROM policy_agreements WHERE user_uuid = %s", (session['uuid'],))
        row = cursor.fetchone()
        if row and row['last_agreed']:
            last_agreed = row['last_agreed']

    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT slug, title, updated_at FROM policies WHERE category = 'Policy' ORDER BY title ASC")
        active_policies = cursor.fetchall()

    return render_template('user/policy_agreement.html', version=current_version, policies=active_policies, last_agreed=last_agreed)

@user_bp.route('/downloads/<path:filename>')
def download_iar(filename):
    """Securely serves the IAR backup only if the user owns it."""
    if not session.get('uuid'):
        return redirect(url_for('auth.login'))

    # Security check: Does this user actually own this file?
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM iar_backups WHERE file_path = %s AND user_uuid = %s", (filename, session['uuid']))
        if not cursor.fetchone():
            flash("Access denied. You do not have permission to download this file.", "error")
            return redirect(url_for('user.profile'))

    # PROPER FIX: Use dynamic config, no string stripping hacks needed
    downloads_dir = get_dynamic_config('IAR_OUTPUT_DIR')
    
    if not downloads_dir:
        flash("System error: IAR output directory is not configured.", "error")
        return redirect(url_for('user.profile'))

    full_path = os.path.join(downloads_dir, filename)

    # Gracefully handle missing files
    if not os.path.exists(full_path):
        flash("The requested backup file could not be found on the server. Please generate a new one.", "error")
        return redirect(url_for('user.profile'))

    return send_from_directory(downloads_dir, filename, as_attachment=True)
