from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.auth_helpers import require_admin
from app.utils.robust_api import set_user_level

user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/admin/users')

@user_mgmt_bp.route('/lookup', methods=['GET'])
@require_admin
def gatekeeper_lookup():
    """Cross-references IP, MAC, HostID, and Inbound From to find alt accounts."""
    search_type = request.args.get('type', 'username') # Default to partial username
    query_raw = request.args.get('q', '').strip()

    if not query_raw:
        return render_template('admin/lookup.html', results=None)

    pariah_conn = get_pariah_db()
    uuids = set()

    table_map = {
        'ip': ('gatekeeper_ip', 'user_ip'),
        'mac': ('gatekeeper_mac', 'user_mac'),
        'host_id': ('gatekeeper_host_id', 'user_host_id'),
        'from': ('gatekeeper_from', 'inbound_from')
    }

    try:
        with pariah_conn.cursor() as cursor:
            if search_type == 'username':
                # PARTIAL NAME SEARCH RESTORED
                like_query = f"%{query_raw}%"
                for table in ['gatekeeper_ip', 'gatekeeper_mac', 'gatekeeper_from', 'gatekeeper_host_id']:
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE user_name LIKE %s", (like_query,))
                    uuids.update([row['user_uuid'] for row in cursor.fetchall()])

            elif search_type in table_map:
                table, column = table_map[search_type]
                cursor.execute(f"SELECT DISTINCT user_uuid FROM {table} WHERE {column} = %s", (query_raw,))
                uuids.update([row['user_uuid'] for row in cursor.fetchall()])

            elif search_type == 'uuid':
                uuids.add(query_raw)

            results = {'usernames': set(), 'ips': set(), 'macs': set(), 'host_ids': set()}
            
            if uuids:
                format_strings = ','.join(['%s'] * len(uuids))
                uuid_tuple = tuple(uuids)

                # Fetch all known names so admins can see exactly who the alts are!
                cursor.execute(f"SELECT DISTINCT user_name FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['usernames'].update([r['user_name'] for r in cursor.fetchall() if r['user_name']])

                cursor.execute(f"SELECT DISTINCT user_ip FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['ips'].update([r['user_ip'] for r in cursor.fetchall() if r['user_ip']])

                cursor.execute(f"SELECT DISTINCT user_mac FROM gatekeeper_mac WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['macs'].update([r['user_mac'] for r in cursor.fetchall() if r['user_mac']])

                cursor.execute(f"SELECT DISTINCT user_host_id FROM gatekeeper_host_id WHERE user_uuid IN ({format_strings})", uuid_tuple)
                results['host_ids'].update([r['user_host_id'] for r in cursor.fetchall() if r['user_host_id']])

    except Exception as e:
        current_app.logger.error(f"Gatekeeper lookup error: {e}")
        flash('Database query failed.', 'error')

    return render_template('admin/lookup.html', query=query_raw, search_type=search_type, results=results, uuids=list(uuids))

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

@user_mgmt_bp.route('/bans/create', methods=['GET', 'POST'])
@require_admin
def create_ban():
    if request.method == 'GET':
        # Accept pre-population arguments from the Gatekeeper Lookup buttons
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

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute("INSERT INTO bans_master (reason, type) VALUES (%s, %s)", (reason, ban_type))
            ban_id = cursor.lastrowid

            for ip in ips:
                cursor.execute("INSERT INTO bans_ip (banid, ip) VALUES (%s, %s)", (ban_id, ip))
            for mac in macs:
                cursor.execute("INSERT INTO bans_mac (banid, mac) VALUES (%s, %s)", (ban_id, mac))
            for hostid in hostids:
                cursor.execute("INSERT INTO bans_host_id (banid, hostid) VALUES (%s, %s)", (ban_id, hostid))

            for uuid in uuids:
                cursor.execute("INSERT INTO bans_uuid (banid, uuid) VALUES (%s, %s)", (ban_id, uuid))
                # ACTIVE ENFORCEMENT: Pull from dynamic config!
                banned_level = int(get_dynamic_config('rejected_user_level'))
                if ban_type in ['account', 'mixed']:
                    set_user_level(uuid, banned_level)
                    current_app.logger.info(f"Actively enforced ban on UUID {uuid} via Robust API.")

        pariah_conn.commit()
        flash(f'Ban created and actively enforced successfully.', 'success')
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

        flash(f"Ban removed. {len(banned_uuids)} associated avatars have been restored to Level 0.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete ban {ban_id}: {e}")
        flash("An error occurred while removing the ban.", "error")

    return redirect(url_for('user_mgmt.manage_bans'))
