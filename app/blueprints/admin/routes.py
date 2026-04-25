import os
import gzip
import re
import io
import cv2
import numpy as np
from flask import Blueprint, render_template, request, jsonify, current_app, session, flash, redirect, url_for, send_from_directory, send_file, abort
from app.utils.auth_helpers import rbac_required, has_permission
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.robust_api import set_user_level
from app.utils.notifications import send_matrix_discord_webhook, send_approval_email
from app.utils.schema import *

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/approvals', methods=['GET'])
@rbac_required(PERM_APPROVE_USERS)
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
@rbac_required(PERM_APPROVE_USERS)
def approve_user():
    """AJAX endpoint to approve a user and grant Level 0 access."""
    uuid = request.form.get('uuid')
    email = request.form.get('email')

    if not uuid:
        return jsonify({'status': 'error', 'message': 'Missing UUID.'}), 400

    try:
        # ROBUST Call: setaccount
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
@rbac_required(PERM_APPROVE_USERS)
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

@admin_bp.route('/settings', methods=['GET'])
@rbac_required(PERM_MANAGE_SETTINGS)
def system_settings():
    """Admin dashboard to configure dynamic portal settings."""
    pariah_conn = get_pariah_db()

    # Fetch existing DB settings
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT config_key, config_value FROM config")
        db_rows = cursor.fetchall()
    
    db_settings = {row['config_key']: row['config_value'] for row in db_rows}
    known_keys = [k for cat in KNOWN_SETTINGS.values() for k in cat.keys()]
    custom_settings = {k: v for k, v in db_settings.items() if k not in known_keys}

    return render_template(
        'admin/settings.html', 
        schema=KNOWN_SETTINGS, 
        db_settings=db_settings,
        custom_settings=custom_settings
    )

@admin_bp.route('/settings/update_single', methods=['POST'])
@rbac_required(PERM_MANAGE_SETTINGS)
def update_single_setting():
    """AJAX endpoint to update a single setting on the fly."""
    key = request.form.get('key')
    val = request.form.get('value', '').strip()

    if not key:
        return jsonify({'status': 'error', 'message': 'Missing configuration key.'}), 400

    # Strip the 'cfg_' prefix we use in the HTML IDs
    actual_key = key.replace('cfg_', '') if key.startswith('cfg_') else key

    # Check if the submitted value matches our schema default
    is_default = False
    for category, fields in KNOWN_SETTINGS.items():
        if actual_key in fields:
            if str(fields[actual_key].get('default', '')) == val:
                is_default = True
            break

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # If it is the default, DELETE it from the DB to keep things clean
            if is_default:
                cursor.execute("DELETE FROM config WHERE config_key = %s", (actual_key,))
            else:
                # Otherwise, save the custom override
                cursor.execute("""
                    INSERT INTO config (config_key, config_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE config_value = VALUES(config_value), updated_at = CURRENT_TIMESTAMP
                """, (actual_key, val))
        pariah_conn.commit()
        return jsonify({'status': 'success', 'is_default': is_default})
    except Exception as e:
        current_app.logger.error(f"Failed to update config {actual_key}: {e}")
        return jsonify({'status': 'error', 'message': 'Database error.'}), 500

@admin_bp.route('/settings/add', methods=['POST'])
@rbac_required(PERM_MANAGE_SETTINGS)
def add_setting():
    """Injects a new custom override key into the configuration table."""
    
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

    return redirect(url_for('admin.system_settings'))

@admin_bp.route('/settings/delete', methods=['POST'])
@rbac_required(PERM_MANAGE_SETTINGS)
def delete_setting():
    """Removes a configuration key from the database, reverting it to default."""

    target_key = request.form.get('target_key', '').strip()

    if target_key:
        try:
            conn = get_pariah_db()
            with conn.cursor() as cursor:
                # We do not prevent deleting KNOWN_SETTINGS because deleting them
                # simply causes the get_dynamic_config() function to fall back
                # to the safe defaults defined in schema.py.
                cursor.execute("DELETE FROM config WHERE config_key = %s", (target_key,))
            conn.commit()
            flash(f"Setting '{target_key}' deleted and reverted to system default.", "success")
        except Exception as e:
            current_app.logger.error(f"Failed to delete setting {target_key}: {e}")
            flash("Database error while deleting setting.", "error")
    else:
        flash("No target key specified.", "error")

    return redirect(url_for('admin.system_settings'))

# --- SMART TEXTURE PROXY ---
@admin_bp.route('/texture/<hash_val>')
@rbac_required(PERM_VIEW_ASSETS)
def serve_texture(hash_val):
    """Fetches a texture from FSAssets, decodes JP2 to JPG via OpenCV, caches it, and serves it."""
    if not re.match(r'^[a-fA-F0-9]+$', hash_val):
        abort(400)

    # 1. Check Configurable Cache Path
    cache_dir = get_dynamic_config('texture_cache_path')
    cached_file = os.path.join(cache_dir, f"{hash_val}.jpg")
    can_cache = False

    try:
        os.makedirs(cache_dir, exist_ok=True)
        if os.access(cache_dir, os.W_OK):
            can_cache = True
    except Exception:
        pass # We will fallback to memory-only conversion

    # 2. Serve from Cache if available
    if can_cache and os.path.exists(cached_file):
        return send_from_directory(cache_dir, f"{hash_val}.jpg")

    # 3. Locate Raw Blob
    fsassets_root = get_dynamic_config('fsassets_path')
    if len(hash_val) < 10:
        abort(404)
        
    rel_path = os.path.join(hash_val[0:2], hash_val[2:4], hash_val[4:6], hash_val[6:10], f"{hash_val}.gz")
    full_path = os.path.join(fsassets_root, rel_path)

    if not os.path.exists(full_path):
        abort(404)

    try:
        # Unzip -> Decode
        with gzip.open(full_path, 'rb') as f:
            uncompressed_bytes = f.read()
            
        file_bytes = np.asarray(bytearray(uncompressed_bytes), dtype=np.uint8)
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if img is None:
            abort(500)

        # 4. Save to Disk OR Serve from RAM
        if can_cache:
            cv2.imwrite(cached_file, img)
            return send_from_directory(cache_dir, f"{hash_val}.jpg")
        else:
            # Fallback: Encode to JPG in memory and send directly
            is_success, buffer = cv2.imencode(".jpg", img)
            if is_success:
                return send_file(io.BytesIO(buffer), mimetype='image/jpeg')
            abort(500)
            
    except Exception as e:
        current_app.logger.error(f"Failed to decode texture {hash_val}: {e}")
        abort(500)

# --- GALLERY UI ROUTE ---
@admin_bp.route('/gallery')
@rbac_required(PERM_VIEW_ASSETS)
def texture_gallery():
    """Renders a paginated gallery of grid textures."""
    
    # Check permissions and warn Admin (RESTORED)
    cache_dir = get_dynamic_config('texture_cache_path')
    try:
        if not os.path.exists(cache_dir) or not os.access(cache_dir, os.W_OK):
            flash(f"Warning: Texture cache dir ({cache_dir}) is missing or not writable by the 'pariah' user. Images are decoding in RAM (High CPU overhead).", "warning")
    except Exception:
        flash(f"Warning: Unable to verify cache directory permissions at {cache_dir}.", "warning")

    page = int(request.args.get('page', 1))
    per_page = 48 
    offset = (page - 1) * per_page
    target_uuid = request.args.get('uuid', '').strip()
    
    textures = []
    robust_conn = get_robust_db()
    
    try:
        with robust_conn.cursor() as cursor:
            # Base query joining inventoryitems (i), fsassets (f), and useraccounts (u)
            base_query = """
                SELECT f.id, f.hash, MAX(i.inventoryName) as name, MAX(f.create_time) as create_time,
                       MAX(i.avatarID) as owner_uuid, MAX(CONCAT(u.FirstName, ' ', u.LastName)) as owner_name
                FROM inventoryitems i
                JOIN fsassets f ON i.assetID = f.id
                LEFT JOIN useraccounts u ON i.avatarID = u.PrincipalID
                WHERE i.assetType = 0 
                  AND i.inventoryName NOT LIKE '%%Baked%%' 
                  AND i.inventoryName NOT LIKE '%%Mesh%%'
            """

            if target_uuid:
                cursor.execute(base_query + """
                  AND i.avatarID = %s 
                  GROUP BY f.hash 
                  ORDER BY MAX(f.create_time) DESC LIMIT %s OFFSET %s
                """, (target_uuid, per_page, offset))
            else:
                cursor.execute(base_query + """
                  GROUP BY f.hash 
                  ORDER BY MAX(f.create_time) DESC LIMIT %s OFFSET %s
                """, (per_page, offset))
            
            raw_textures = cursor.fetchall()
            
            # Map unresolved names for Hypergrid or orphaned system items
            for t in raw_textures:
                if not t['owner_name']:
                    t['owner_name'] = "System / Orphaned / HG"
            
            textures = raw_textures

    except Exception as e:
        current_app.logger.error(f"Gallery Query Failed: {e}")
        flash("Failed to load textures from the database.", "error")

    return render_template('admin/gallery.html', 
                           textures=textures, 
                           page=page, 
                           target_uuid=target_uuid)