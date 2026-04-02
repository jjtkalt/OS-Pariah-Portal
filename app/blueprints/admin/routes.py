from flask import Blueprint, render_template, request, jsonify, current_app, session, flash, redirect, url_for
from app.utils.auth_helpers import require_admin
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.robust_api import set_user_level
from app.utils.notifications import send_matrix_discord_webhook, send_approval_email

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/approvals', methods=['GET'])
@require_admin
def pending_approvals():
    """Renders the dashboard of users waiting for Level 0 access."""
    pariah_conn = get_pariah_db()
    pending_users = []

    # 1. Fetch the pending registration metadata from our portal database
    with pariah_conn.cursor() as cursor:
        cursor.execute("""
            SELECT user_uuid, email, inviter, discord, matrix, other_info, created_at
            FROM pending_registrations
            WHERE status = 'pending_approval'
            ORDER BY created_at ASC
        """)
        pending_records = cursor.fetchall()

    if not pending_records:
        return render_template('admin/approvals.html', users=[])

    # 2. Extract UUIDs and fetch their actual names from the Robust database
    robust_conn = get_robust_db()
    uuids = [record['user_uuid'] for record in pending_records]

    format_strings = ','.join(['%s'] * len(uuids))
    user_names = {}

    try:
        with robust_conn.cursor() as r_cursor:
            r_cursor.execute(f"SELECT PrincipalID, FirstName, LastName FROM useraccounts WHERE PrincipalID IN ({format_strings})", tuple(uuids))
            for row in r_cursor.fetchall():
                user_names[row['PrincipalID']] = {
                    'first_name': row['FirstName'],
                    'last_name': row['LastName']
                }
    except Exception as e:
        current_app.logger.error(f"Failed to fetch user names from Robust: {e}")

    # 3. Merge the names into our records for the template
    for record in pending_records:
        uuid = record['user_uuid']
        record['first_name'] = user_names.get(uuid, {}).get('first_name', 'Unknown')
        record['last_name'] = user_names.get(uuid, {}).get('last_name', 'User')
        pending_users.append(record)

    return render_template('admin/approvals.html', users=pending_users)

@admin_bp.route('/approvals/approve', methods=['POST'])
@require_admin
def approve_user():
    """AJAX endpoint to approve a user and grant Level 0 access."""
    uuid = request.form.get('uuid')
    email = request.form.get('email')

    if not uuid:
        return jsonify({'status': 'error', 'message': 'Missing UUID.'}), 400

    try:
        # 1. ROBUST Call: setaccount (Update UserLevel to 0)
        if set_user_level(uuid, 0):
            # 2. Update Pariah DB state
            pariah_conn = get_pariah_db()
            with pariah_conn.cursor() as cursor:
                cursor.execute("UPDATE pending_registrations SET status = 'approved' WHERE user_uuid = %s", (uuid,))
            pariah_conn.commit()

            # 3. Asynchronous Notifications
            grid_name = get_dynamic_config('grid_name')
            send_approval_email(email, grid_name)

            send_matrix_discord_webhook(
                title="✅ Account Approved",
                message=f"A pending user ({uuid}) has been approved and set to Level 0.",
                color=3066993 # Green
            )
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'ROBUST API failed. Check if port 8003 is accessible.'})
    except Exception as e:
        current_app.logger.error(f"Approval exception: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@admin_bp.route('/approvals/reject', methods=['POST'])
@require_admin
def reject_user():
    """AJAX endpoint to reject a user, leaving them locked out."""
    uuid = request.form.get('uuid')

    if not uuid:
        return jsonify({'status': 'error', 'message': 'Missing UUID.'}), 400

    try:
        # We will update this -5 logic in our next sweep to use the dynamic config!
        rejected_level = int(get_dynamic_config('rejected_user_level'))

        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("UPDATE pending_registrations SET status = 'rejected' WHERE user_uuid = %s", (uuid,))
        pariah_conn.commit()

        set_user_level(uuid, rejected_level)

        return jsonify({'status': 'success'})
    except Exception as e:
        current_app.logger.error(f"Rejection exception: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@admin_bp.route('/settings', methods=['GET', 'POST'])
@require_admin
def system_settings():
    """Level 250+ Admin dashboard to configure dynamic portal settings."""
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized: Only Level 250+ Super Admins can access System Settings.", "error")
        return redirect(url_for('comms.news_feed'))

    pariah_conn = get_pariah_db()

    if request.method == 'POST':
        try:
            with pariah_conn.cursor() as cursor:
                for key, value in request.form.items():
                    if key.startswith('cfg_'):
                        actual_key = key.replace('cfg_', '')
                        # FIX: Using UPSERT so brand-new schema keys are safely inserted
                        cursor.execute("""
                            INSERT INTO config (config_key, config_value, updated_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                            ON DUPLICATE KEY UPDATE config_value = VALUES(config_value), updated_at = CURRENT_TIMESTAMP
                        """, (actual_key, value.strip()))
            pariah_conn.commit()
            flash("System settings updated successfully.", "success")
        except Exception as e:
            current_app.logger.error(f"Failed to update config: {e}")
            flash("Database error while updating settings.", "error")

        return redirect(url_for('admin.system_settings'))

    # Fetch existing DB settings
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT config_key, config_value FROM config")
        db_rows = cursor.fetchall()
    
    # Convert to a flat dictionary for easy lookup
    db_settings = {row['config_key']: row['config_value'] for row in db_rows}

    # Identify "Custom" settings that are in the DB but not in our KNOWN_SETTINGS schema
    known_keys = [k for cat in KNOWN_SETTINGS.values() for k in cat.keys()]
    custom_settings = {k: v for k, v in db_settings.items() if k not in known_keys}

    return render_template(
        'admin/settings.html', 
        schema=KNOWN_SETTINGS, 
        db_settings=db_settings,
        custom_settings=custom_settings
    )

@admin_bp.route('/settings/add', methods=['POST'])
@require_admin
def add_setting():
    """Injects a new custom override key into the configuration table."""
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized.", "error")
        # Adjust 'admin.settings' if your route is named differently (e.g., 'admin.system_settings')
        return redirect(url_for('admin.settings'))

    new_key = request.form.get('new_key', '').strip()
    new_value = request.form.get('new_value', '').strip()

    if new_key and new_value:
        try:
            conn = get_pariah_db()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO config (config_key, config_value)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
                """, (new_key, new_value))
            conn.commit()
            flash(f"Custom setting '{new_key}' successfully added.", "success")
        except Exception as e:
            current_app.logger.error(f"Failed to add setting: {e}")
            flash("Error adding setting to database.", "error")
    else:
        flash("Both Key and Value are required.", "error")

    return redirect(url_for('admin.settings'))
