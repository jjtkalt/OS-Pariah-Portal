import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.auth_helpers import require_admin
from app.utils.robust_api import set_user_level

user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/admin/users')

@user_mgmt_bp.route('/lookup', methods=['GET'])
@require_admin
def gatekeeper_lookup():
    """Cross-references IP, MAC, HostID, and Inbound From to find alt accounts."""
    search_type = request.args.get('type', 'username')
    query_raw = request.args.get('q', '').strip()

    if not query_raw:
        return render_template('admin/lookup.html', results=None, search_type=search_type, query="")

    pariah_conn = get_pariah_db()
    uuids = set()

    table_map = {
        'ip': ('gatekeeper_ip', 'user_ip'),
        'mac': ('gatekeeper_mac', 'user_mac'),
        'host_id': ('gatekeeper_host_id', 'user_host_id'),
        'from': ('gatekeeper_from', 'inbound_from')
    }

    # Helper to safely format datetime objects for the template
    def format_dt(dt):
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m-%d %H:%M')
        return str(dt) if dt else 'Unknown'

    try:
        with pariah_conn.cursor() as cursor:
            if search_type == 'username':
                like_query = f"%{query_raw}%"
                for table in ['gatekeeper_ip', 'gatekeeper_mac', 'gatekeeper_from', 'gatekeeper_host_id']:
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE user_name LIKE %s", (like_query,))
                    uuids.update([row['user_uuid'] for row in cursor.fetchall()])
            
            elif search_type == 'exact_username':
                for table in ['gatekeeper_ip', 'gatekeeper_mac', 'gatekeeper_from', 'gatekeeper_host_id']:
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE user_name = %s", (query_raw,))
                    uuids.update([row['user_uuid'] for row in cursor.fetchall()])

            elif search_type in table_map:
                table, column = table_map[search_type]
                cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE {column} = %s", (query_raw,))
                uuids.update([row['user_uuid'] for row in cursor.fetchall()])

            elif search_type == 'uuid':
                uuids.add(query_raw)

            # Changed sets to dictionaries to hold the timestamps
            results = {'usernames': set(), 'ips': {}, 'macs': {}, 'host_ids': {}}
            uuid_info = {}
            
            if uuids:
                format_strings = ','.join(['%s'] * len(uuids))
                uuid_tuple = tuple(uuids)

                cursor.execute(f"SELECT DISTINCT user_name FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['usernames'].update([r['user_name'] for r in cursor.fetchall() if r['user_name']])

                # Fetch IPs, group by IP, get most recent date, and sort!
                cursor.execute(f"SELECT user_ip, MAX(date_time) as last_seen FROM gatekeeper_ip WHERE user_uuid IN ({format_strings}) GROUP BY user_ip ORDER BY last_seen DESC", uuid_tuple)
                results['ips'] = {r['user_ip']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_ip']}

                # Fetch MACs
                cursor.execute(f"SELECT user_mac, MAX(date_time) as last_seen FROM gatekeeper_mac WHERE user_uuid IN ({format_strings}) GROUP BY user_mac ORDER BY last_seen DESC", uuid_tuple)
                results['macs'] = {r['user_mac']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_mac']}

                # Fetch Host IDs
                cursor.execute(f"SELECT user_host_id, MAX(date_time) as last_seen FROM gatekeeper_host_id WHERE user_uuid IN ({format_strings}) GROUP BY user_host_id ORDER BY last_seen DESC", uuid_tuple)
                results['host_ids'] = {r['user_host_id']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_host_id']}

                # Fetch Hypergrid Origin Information & Timestamp
                cursor.execute(f"SELECT user_uuid, MAX(inbound_from) as grid_from, MAX(date_time) as last_seen FROM gatekeeper_from WHERE user_uuid IN ({format_strings}) GROUP BY user_uuid", uuid_tuple)
                grid_data = {row['user_uuid']: {'from': row['grid_from'], 'last_seen': format_dt(row['last_seen'])} for row in cursor.fetchall()}
                
                for u in uuids:
                    g_data = grid_data.get(u, {})
                    origin = g_data.get('from')
                    last_seen = g_data.get('last_seen', 'Unknown')
                    is_local = not origin or "127.0.0.1" in origin or origin == ""
                    
                    uuid_info[u] = {
                        'grid_from': "Local Grid" if is_local else origin,
                        'is_local': is_local,
                        'last_seen': last_seen
                    }

    except Exception as e:
        current_app.logger.error(f"Gatekeeper lookup error: {e}")
        flash('Database query failed.', 'error')

    return render_template('admin/lookup.html', query=query_raw, search_type=search_type, results=results, uuid_info=uuid_info)

@user_mgmt_bp.route('/<uuid>/notes', methods=['GET', 'POST'])
@require_admin
def user_notes(uuid):
    pariah_conn = get_pariah_db()
    if request.method == 'POST':
        note_body = request.form.get('note', '').strip()
        admin_uuid = session.get('uuid')
        if note_body:
            with pariah_conn.cursor() as cursor:
                cursor.execute("INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)", (uuid, admin_uuid, note_body))
            pariah_conn.commit()
            flash('Note added successfully.', 'success')
            return redirect(url_for('user_mgmt.user_notes', uuid=uuid))

    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM user_notes WHERE user_uuid = %s ORDER BY created_at DESC", (uuid,))
        notes = cursor.fetchall()

    if notes:
        robust_conn = get_robust_db()
        admin_uuids = list(set([note['admin_uuid'] for note in notes]))
        format_strings = ','.join(['%s'] * len(admin_uuids))
        admin_names = {}

        try:
            with robust_conn.cursor() as r_cursor:
                r_cursor.execute(f"SELECT PrincipalID, FirstName, LastName FROM useraccounts WHERE PrincipalID IN ({format_strings})", tuple(admin_uuids))
                for row in r_cursor.fetchall():
                    admin_names[row['PrincipalID']] = f"{row['FirstName']} {row['LastName']}"
        except Exception as e:
            current_app.logger.error(f"Failed to fetch admin names for notes: {e}")

        for note in notes:
            note['admin_name'] = admin_names.get(note['admin_uuid'], 'Unknown Admin')

    return render_template('admin/user_notes.html', target_uuid=uuid, notes=notes)

@user_mgmt_bp.route('/bans', methods=['GET'])
@require_admin
def manage_bans():
    """Displays all active bans across all vectors."""
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Aggregate the linked ban data into a single row per ban
        cursor.execute("""
            SELECT m.banid, m.date, m.reason, m.type,
                   GROUP_CONCAT(DISTINCT u.uuid SEPARATOR ', ') as uuids,
                   GROUP_CONCAT(DISTINCT i.ip SEPARATOR ', ') as ips,
                   GROUP_CONCAT(DISTINCT mac.mac SEPARATOR ', ') as macs,
                   GROUP_CONCAT(DISTINCT h.hostid SEPARATOR ', ') as hostids
            FROM bans_master m
            LEFT JOIN bans_uuid u ON m.banid = u.banid
            LEFT JOIN bans_ip i ON m.banid = i.banid
            LEFT JOIN bans_mac mac ON m.banid = mac.banid
            LEFT JOIN bans_host_id h ON m.banid = h.banid
            GROUP BY m.banid
            ORDER BY m.date DESC
        """)
        bans = cursor.fetchall()
        
    return render_template('admin/manage_bans.html', bans=bans)

def trigger_system_sync_workers(ban_id="Manual/Unknown"):
    """Triggers the secure background scripts to sync firewalld and Robust."""
    current_app.logger.info(f"Triggering system synchronizations for Ban ID {ban_id}...")
    try:
        # 1. Fire the IP/HostID Firewall Sync
        subprocess.Popen(
            ["/usr/bin/sudo", "/opt/os_pariah/venv/bin/python", "/opt/os_pariah/scripts/sync_firewall.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        # 2. Fire the Robust MAC Sync
        subprocess.Popen(
            ["/usr/bin/sudo", "/opt/os_pariah/venv/bin/python", "/opt/os_pariah/scripts/sync_robust.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
    except Exception as e:
        current_app.logger.error(f"Failed to trigger sync workers: {e}")

@user_mgmt_bp.route('/bans/create', methods=['GET', 'POST'])
@require_admin
def create_ban():
    if request.method == 'GET':
        prep_uuid = request.args.get('uuid', '')
        prep_ip = request.args.get('ip', '')
        prep_mac = request.args.get('mac', '')
        prep_hostid = request.args.get('hostid', '')
        return render_template('admin/create_ban.html', prep_uuid=prep_uuid, prep_ip=prep_ip, prep_mac=prep_mac, prep_hostid=prep_hostid)

    reason = request.form.get('reason', '').strip()
    ban_type = request.form.get('type', 'account').strip()

    uuids = [u.strip() for u in request.form.get('uuids', '').split('\n') if u.strip()]
    ips = [i.strip() for i in request.form.get('ips', '').split('\n') if i.strip()]
    macs = [m.strip() for m in request.form.get('macs', '').split('\n') if m.strip()]
    hostids = [h.strip() for h in request.form.get('hostids', '').split('\n') if h.strip()]

    # --- SEVERITY DATA FILTERING ---
    # If the admin downgrades the ban type, we discard the higher-level identifiers 
    # so we don't accidentally enforce a firewall block on an "Account Only" ban.
    if ban_type == 'account':
        ips, macs, hostids = [], [], []
    elif ban_type == 'ip':
        macs, hostids = [], []
    elif ban_type == 'mac':
        hostids = []
    # If 'hostid', we keep everything (the ultimate ban).

    # --- Determine Severity Level ---
    target_level = int(get_dynamic_config('ban_level_account'))
    if ban_type == 'hostid':
        target_level = int(get_dynamic_config('ban_level_host'))
    elif ban_type == 'mac':
        target_level = int(get_dynamic_config('ban_level_mac'))
    elif ban_type == 'ip':
        target_level = int(get_dynamic_config('ban_level_ip'))

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # 1. Master Record
            cursor.execute("INSERT INTO bans_master (reason, type) VALUES (%s, %s)", (reason, ban_type))
            ban_id = cursor.lastrowid

            # 2. Cascading Data Inserts
            for ip in ips:
                cursor.execute("INSERT INTO bans_ip (banid, ip) VALUES (%s, %s)", (ban_id, ip))
            for mac in macs:
                cursor.execute("INSERT INTO bans_mac (banid, mac) VALUES (%s, %s)", (ban_id, mac))
            for hostid in hostids:
                cursor.execute("INSERT INTO bans_host_id (banid, hostid) VALUES (%s, %s)", (ban_id, hostid))

            # 3. Robust Execution
            for uuid in uuids:
                cursor.execute("INSERT INTO bans_uuid (banid, uuid) VALUES (%s, %s)", (ban_id, uuid))
                
                # Push the exact tier to Robust
                set_user_level(uuid, target_level)
                current_app.logger.info(f"Ban Level {target_level} actively enforced on UUID {uuid}.")

        pariah_conn.commit()

        # 4. Trigger Firewall & Robust Workers
        if ban_type in ['ip', 'mac', 'hostid']:
            trigger_system_sync_workers(ban_id)

        flash(f'Severity Level {target_level} Ban created and actively enforced successfully.', 'success')
    except Exception as e:
        current_app.logger.error(f"Ban creation failed: {e}")
        flash('Failed to create ban. Check logs.', 'error')

    return redirect(url_for('user_mgmt.manage_bans'))

@user_mgmt_bp.route('/bans/<int:ban_id>/delete', methods=['POST'])
@require_admin
def delete_ban(ban_id):
    """Deletes a ban and attempts to restore associated accounts to Level 0."""
    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # First, fetch the UUIDs tied to this ban so we can unlock them
            cursor.execute("SELECT uuid FROM bans_uuid WHERE banid = %s", (ban_id,))
            banned_uuids = [row['uuid'] for row in cursor.fetchall()]

            # Foreign key cascading will delete the child records in bans_ip, bans_mac, etc.
            cursor.execute("DELETE FROM bans_master WHERE banid = %s", (ban_id,))
        pariah_conn.commit()

        # Restore user levels via Robust
        for uuid in banned_uuids:
            set_user_level(uuid, 0)

        # --- Trigger System Synchronization ---
        trigger_system_sync_workers(ban_id)
        # --------------------------------------

        flash(f"Ban removed. {len(banned_uuids)} associated avatars have been restored to Level 0.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete ban {ban_id}: {e}")
        flash("An error occurred while removing the ban.", "error")

    return redirect(url_for('user_mgmt.manage_bans'))

@user_mgmt_bp.route('/<uuid>/set_level', methods=['POST'])
@require_admin
def update_user_level(uuid):
    """Allows Super Admins to manually adjust a user's level (e.g., Promotions)."""
    if int(session.get('user_level', 0)) < 250:
        flash("Only Level 250+ Admins can manually adjust user access levels.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup'))

    new_level = request.form.get('new_level')
    
    try:
        new_level = int(new_level)
        set_user_level(uuid, new_level)
        flash(f"User level successfully updated to {new_level}.", "success")
    except ValueError:
        flash("Invalid level provided.", "error")
    except Exception as e:
        current_app.logger.error(f"Failed to update level for {uuid}: {e}")
        flash("A database error occurred.", "error")

    return redirect(url_for('user_mgmt.gatekeeper_lookup'))