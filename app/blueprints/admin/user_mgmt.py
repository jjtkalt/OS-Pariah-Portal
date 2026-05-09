import os
import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.auth_helpers import rbac_required, has_permission
from app.utils.schema import *
from app.utils.robust_api import set_user_level, update_robust_name, update_robust_email
import time
import secrets
from app.utils.notifications import send_password_reset_email
from app.utils.audit import log_audit_action
from app.utils.password_resets import create_password_reset_token
from datetime import datetime, timezone

user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/admin/users')

@user_mgmt_bp.route('/lookup', methods=['GET'])
@rbac_required(PERM_USER_LOOKUP)
def gatekeeper_lookup():
    """Cross-references IP, MAC, HostID, and Inbound From to find alt accounts."""
    search_type = request.args.get('type', 'username')
    query_raw = request.args.get('q', '').strip()

    # Determine if this admin has clearance to view Protected Personal Information
    has_ppi_access = has_permission(PERM_VIEW_PPI)

    # ---------------------------------------------------------
    # SECURITY INTERCEPT: Block unauthorized PPI searches
    # ---------------------------------------------------------
    if query_raw and not has_ppi_access and search_type in ['ip', 'mac', 'host_id']:
        flash("Unauthorized: You do not have clearance to search by connection PPI.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup'))

    if not query_raw:
        return render_template('admin/lookup.html', results=None, search_type=search_type, query="")

    pariah_conn = get_pariah_db()
    robust_conn = get_robust_db()
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

        # 1B. Search Robust UserAccounts (Catches users who have never logged in)
        with robust_conn.cursor() as r_cursor:
            if search_type == 'username':
                r_cursor.execute("SELECT PrincipalID FROM useraccounts WHERE CONCAT(FirstName, ' ', LastName) LIKE %s", (f"%{query_raw}%",))
                uuids.update([row['PrincipalID'] for row in r_cursor.fetchall()])
                
            elif search_type == 'exact_username':
                r_cursor.execute("SELECT PrincipalID FROM useraccounts WHERE CONCAT(FirstName, ' ', LastName) = %s", (query_raw,))
                uuids.update([row['PrincipalID'] for row in r_cursor.fetchall()])
                
            elif search_type == 'uuid':
                # Validate that the UUID actually exists in Robust if we are searching explicitly
                r_cursor.execute("SELECT PrincipalID FROM useraccounts WHERE PrincipalID = %s", (query_raw,))
                if r_cursor.fetchone():
                    uuids.add(query_raw)

            # Changed sets to dictionaries to hold the timestamps
            results = {'usernames': set(), 'ips': {}, 'macs': {}, 'host_ids': {}}
            uuid_info = {}
            
            if uuids:
                format_strings = ','.join(['%s'] * len(uuids))
                uuid_tuple = tuple(uuids)

                with pariah_conn.cursor() as cursor:
                    # Fetch Gatekeeper Usernames
                    cursor.execute(f"SELECT DISTINCT user_name FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                    results['usernames'].update([r['user_name'] for r in cursor.fetchall() if r['user_name']])

                    # Fetch Hypergrid Origin Information
                    cursor.execute(f"SELECT user_uuid, MAX(inbound_from) as grid_from, MAX(date_time) as last_seen FROM gatekeeper_from WHERE user_uuid IN ({format_strings}) GROUP BY user_uuid", uuid_tuple)
                    grid_data = {row['user_uuid']: {'from': row['grid_from'], 'last_seen': format_dt(row['last_seen'])} for row in cursor.fetchall()}

                    # ISOLATED PPI FETCH: Only hits the DB if they have clearance
                    if has_ppi_access:
                        # Fetch IPs, MACs, HostIDs
                        cursor.execute(f"SELECT user_ip, MAX(date_time) as last_seen FROM gatekeeper_ip WHERE user_uuid IN ({format_strings}) GROUP BY user_ip ORDER BY last_seen DESC", uuid_tuple)
                        results['ips'] = {r['user_ip']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_ip']}

                        cursor.execute(f"SELECT user_mac, MAX(date_time) as last_seen FROM gatekeeper_mac WHERE user_uuid IN ({format_strings}) GROUP BY user_mac ORDER BY last_seen DESC", uuid_tuple)
                        results['macs'] = {r['user_mac']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_mac']}

                        cursor.execute(f"SELECT user_host_id, MAX(date_time) as last_seen FROM gatekeeper_host_id WHERE user_uuid IN ({format_strings}) GROUP BY user_host_id ORDER BY last_seen DESC", uuid_tuple)
                        results['host_ids'] = {r['user_host_id']: format_dt(r['last_seen']) for r in cursor.fetchall() if r['user_host_id']}

                # Fetch Robust Data (Names, Email, Level) mapped by PrincipalID
                robust_data = {}
                with robust_conn.cursor() as r_cursor:
                    r_cursor.execute(f"SELECT PrincipalID, FirstName, LastName, Email, userLevel FROM useraccounts WHERE PrincipalID IN ({format_strings})", uuid_tuple)
                    for r in r_cursor.fetchall():
                        robust_data[r['PrincipalID']] = r
                        results['usernames'].add(f"{r['FirstName']} {r['LastName']}")

                with pariah_conn.cursor() as cursor:
                    # We grab the most recent name captured in our logs for these UUIDs
                    cursor.execute(f"SELECT DISTINCT user_uuid, user_name FROM gatekeeper_ip WHERE user_uuid IN ({format_strings})", uuid_tuple)
                    for r in cursor.fetchall():
                        # If Robust didn't know them, but our logs do, add them to the display results
                        if r['user_name'] and r['user_name'] != "Unknown":
                            if r['user_uuid'] not in robust_data:
                                results['usernames'].add(r['user_name'])
                                # Create a stub for the template so it doesn't show "Unknown User"
                                robust_data[r['user_uuid']] = {
                                    'FirstName': r['user_name'],
                                    'LastName': '(HG/Visitor)',
                                    'Email': 'N/A',
                                    'userLevel': 'N/A'
                                }

                grid_fqdn = str(f"{get_dynamic_config('robust_subdomain')}.{get_dynamic_config('grid_domain')}").strip().lower()

                for u in uuids:
                    g_data = grid_data.get(u, {})
                    origin = str(g_data.get('from', '')).strip()
                    last_seen = g_data.get('last_seen', 'Never Logged In')

                    is_local = False
                    origin_lower = origin.lower()
                    
                    if not origin or origin == "None" or "127.0.0.1" in origin_lower or "localhost" in origin_lower or grid_fqdn in origin_lower:
                        is_local = True
                    
                    # Grab the specific Robust data for this UUID (or empty dict if HG visitor)
                    r_data = robust_data.get(u, {})
                    
                    uuid_info[u] = {
                        'grid_from': "Local Grid" if is_local else origin,
                        'is_local': is_local,
                        'last_seen': last_seen,
                        'avatar_name': f"{r_data.get('FirstName', 'Unknown')} {r_data.get('LastName', 'User')}".strip(),
                        'first_name': r_data.get('FirstName', ''),
                        'last_name': r_data.get('LastName', ''),
                        'current_email': r_data.get('Email', ''),
                        'current_level': r_data.get('userLevel', '')
                    }

                    uuid_info = dict(sorted(uuid_info.items(), key=lambda item: item[1]['avatar_name'].lower()))

    except Exception as e:
        current_app.logger.error(f"Gatekeeper lookup error: {e}")
        flash('Database query failed.', 'error')

    return render_template('admin/lookup.html', query=query_raw, search_type=search_type, results=results, uuid_info=uuid_info, uuids=list(uuids))

@user_mgmt_bp.route('/<uuid>/notes', methods=['GET', 'POST'])
@rbac_required(PERM_VIEW_NOTES)
def user_notes(uuid):
    pariah_conn = get_pariah_db()

    if request.method == 'POST':
        if not has_permission(PERM_ADD_NOTES):
            flash("Unauthorized: You do not have permission to add staff notes.", "error")
            return redirect(url_for('user_mgmt.user_notes', uuid=uuid))

        note_body = request.form.get('note', '').strip()
        admin_uuid = session.get('uuid')

        if note_body:
            with pariah_conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)",
                    (uuid, admin_uuid, note_body)
                )
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
@rbac_required(PERM_ISSUE_BANS)
def manage_bans():
    """Displays all active bans across all vectors."""
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        # Aggregate the linked ban data into a single row per ban
        cursor.execute("""
            SELECT m.banid, m.date, m.reason, m.type, m.notes,
                   GROUP_CONCAT(DISTINCT u.uuid SEPARATOR ', ') as uuids,
                   GROUP_CONCAT(DISTINCT ru.uuid SEPARATOR ', ') as related_uuids,
                   GROUP_CONCAT(DISTINCT i.ip SEPARATOR ', ') as ips,
                   GROUP_CONCAT(DISTINCT mac.mac SEPARATOR ', ') as macs,
                   GROUP_CONCAT(DISTINCT h.hostid SEPARATOR ', ') as hostids
            FROM bans_master m
            LEFT JOIN bans_uuid u ON m.banid = u.banid
            LEFT JOIN bans_related_uuid ru ON m.banid = ru.banid
            LEFT JOIN bans_ip i ON m.banid = i.banid
            LEFT JOIN bans_mac mac ON m.banid = mac.banid
            LEFT JOIN bans_host_id h ON m.banid = h.banid
            GROUP BY m.banid
            ORDER BY m.date DESC
        """)
        bans = cursor.fetchall()

    all_principal_ids = []
    for row in bans:
        for key in ("uuids", "related_uuids"):
            raw = row.get(key)
            if not raw:
                continue
            for part in str(raw).split(","):
                u = part.strip()
                if u:
                    all_principal_ids.append(u)
    seen_pid = set()
    unique_ids = []
    for u in all_principal_ids:
        if u not in seen_pid:
            seen_pid.add(u)
            unique_ids.append(u)

    uuid_to_name = _gatekeeper_latest_display_names(pariah_conn, unique_ids)

    for ban in bans:
        ordered_uuids = []
        dupe = set()
        for key in ("uuids", "related_uuids"):
            raw = ban.get(key)
            if not raw:
                continue
            for part in str(raw).split(","):
                u = part.strip()
                if u and u not in dupe:
                    dupe.add(u)
                    ordered_uuids.append(u)
        if ordered_uuids:
            labels = []
            for u in ordered_uuids:
                nm = uuid_to_name.get(u)
                if nm and str(nm).strip() and str(nm).strip().lower() != u.lower():
                    labels.append(str(nm).strip())
                else:
                    labels.append(u)
            ban["avatar_names_display"] = ", ".join(labels)
        else:
            ban["avatar_names_display"] = ""

    return render_template("admin/manage_bans.html", bans=bans)

def trigger_system_sync_workers(ban_id="Manual/Unknown"):
    """Triggers the secure background scripts to sync firewalld and Robust."""
    current_app.logger.info(f"Triggering system synchronizations for Ban ID {ban_id}...")
    sync_log = "/var/log/os_pariah/sync_workers.log"
    log_out = None
    try:
        os.makedirs(os.path.dirname(sync_log), exist_ok=True)
        log_out = open(sync_log, "ab", buffering=0)
    except OSError:
        pass

    try:
        cmds = [
            [
                "/usr/bin/sudo",
                "/opt/os_pariah/venv/bin/python",
                "/opt/os_pariah/scripts/sync_firewall.py",
            ],
            [
                "/usr/bin/sudo",
                "/opt/os_pariah/venv/bin/python",
                "/opt/os_pariah/scripts/sync_robust.py",
            ],
        ]
        for cmd in cmds:
            kwargs = dict(start_new_session=True)
            if log_out is not None:
                kwargs["stdout"] = log_out
                kwargs["stderr"] = subprocess.STDOUT
            else:
                kwargs["stdout"] = subprocess.DEVNULL
                kwargs["stderr"] = subprocess.DEVNULL
            subprocess.Popen(cmd, **kwargs)
        if log_out is not None:
            current_app.logger.info(
                "Sync worker output appended to %s (scripts also log failures there).",
                sync_log,
            )
    except Exception as e:
        current_app.logger.error(f"Failed to trigger sync workers: {e}")
    finally:
        if log_out is not None:
            log_out.close()

def _safe_fetchall(cursor):
    try:
        rows = cursor.fetchall()
    except Exception:
        return []
    return rows if isinstance(rows, list) else []

def _safe_fetchone(cursor):
    try:
        row = cursor.fetchone()
    except Exception:
        return None
    return row if isinstance(row, dict) else None

def _now_utc_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')


def _entered_ts_newer(a, b):
    """True if DB entered timestamp a should replace b as the newer observation."""
    if a is None:
        return False
    if b is None:
        return True
    try:
        return a > b
    except TypeError:
        return False


def _gatekeeper_latest_display_names(pariah_conn, unique_ids):
    """
    One display name per UUID from gatekeeper_* tables (Hypergrid logins, deleted Robust accounts).
    Picks the user_name from the row with the greatest `entered` across ip/mac/host_id/from tables.
    """
    if not unique_ids:
        return {}
    fmt = ",".join(["%s"] * len(unique_ids))
    tu = tuple(unique_ids)
    best = {}  # uuid -> (entered, display_name)
    tables = ("gatekeeper_ip", "gatekeeper_mac", "gatekeeper_host_id", "gatekeeper_from")
    try:
        with pariah_conn.cursor() as cursor:
            for table in tables:
                cursor.execute(
                    f"""
                    SELECT user_uuid, user_name, entered
                    FROM {table}
                    WHERE user_uuid IN ({fmt})
                      AND user_name IS NOT NULL AND TRIM(user_name) <> ''
                    """,
                    tu,
                )
                for row in cursor.fetchall():
                    uid = row.get("user_uuid")
                    nm = str(row.get("user_name") or "").strip()
                    if not uid or not nm:
                        continue
                    ent = row.get("entered")
                    prev = best.get(uid)
                    if prev is None:
                        best[uid] = (ent, nm)
                    elif _entered_ts_newer(ent, prev[0]):
                        best[uid] = (ent, nm)
        return {u: pair[1] for u, pair in best.items()}
    except Exception as e:
        current_app.logger.error(f"manage_bans: gatekeeper avatar name lookup failed: {e}")
        return {}


def _collect_ban_evidence(pariah_conn, robust_conn, *, seed_uuids, seed_ips, seed_macs, seed_hostids, ban_type):
    """
    Collects a best-effort snapshot of identifiers + linked accounts for review/reference.
    Enforcement is handled separately; this is for storage + staff notes.
    """
    seed_uuids = {u.strip() for u in (seed_uuids or []) if u and str(u).strip()}
    seed_ips = {i.strip() for i in (seed_ips or []) if i and str(i).strip()}
    seed_macs = {m.strip() for m in (seed_macs or []) if m and str(m).strip()}
    seed_hostids = {h.strip() for h in (seed_hostids or []) if h and str(h).strip()}

    linked_uuids = set(seed_uuids)
    observed = {
        "ips": set(seed_ips),
        "macs": set(seed_macs),
        "hostids": set(seed_hostids),
        "grids": {},  # uuid -> inbound_from
        "names": {},  # uuid -> set(names)
    }

    def add_names(uuid, name):
        if not uuid or not name:
            return
        observed["names"].setdefault(uuid, set()).add(str(name).strip())

    try:
        with pariah_conn.cursor() as cursor:
            # 1) Expand linked UUIDs based on the ban vector(s)
            if ban_type == "ip" and seed_ips:
                fmt = ",".join(["%s"] * len(seed_ips))
                cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_ip WHERE user_ip IN ({fmt})", tuple(seed_ips))
                linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])
            elif ban_type == "mac" and seed_macs:
                fmt = ",".join(["%s"] * len(seed_macs))
                cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_mac WHERE user_mac IN ({fmt})", tuple(seed_macs))
                linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])
            elif ban_type == "hostid" and seed_hostids:
                fmt = ",".join(["%s"] * len(seed_hostids))
                cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_host_id WHERE user_host_id IN ({fmt})", tuple(seed_hostids))
                linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])

            # 2) If this is an account ban, do a single "one hop" expansion:
            #    seed UUIDs -> identifiers -> other UUIDs sharing those identifiers.
            if ban_type == "account" and seed_uuids:
                fmt_u = ",".join(["%s"] * len(seed_uuids))
                cursor.execute(f"SELECT DISTINCT user_ip FROM gatekeeper_ip WHERE user_uuid IN ({fmt_u})", tuple(seed_uuids))
                hop_ips = {r.get("user_ip") for r in _safe_fetchall(cursor) if r.get("user_ip")}
                cursor.execute(f"SELECT DISTINCT user_mac FROM gatekeeper_mac WHERE user_uuid IN ({fmt_u})", tuple(seed_uuids))
                hop_macs = {r.get("user_mac") for r in _safe_fetchall(cursor) if r.get("user_mac")}
                cursor.execute(f"SELECT DISTINCT user_host_id FROM gatekeeper_host_id WHERE user_uuid IN ({fmt_u})", tuple(seed_uuids))
                hop_hosts = {r.get("user_host_id") for r in _safe_fetchall(cursor) if r.get("user_host_id")}

                observed["ips"].update(hop_ips)
                observed["macs"].update(hop_macs)
                observed["hostids"].update(hop_hosts)

                if hop_ips:
                    fmt = ",".join(["%s"] * len(hop_ips))
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_ip WHERE user_ip IN ({fmt})", tuple(hop_ips))
                    linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])
                if hop_macs:
                    fmt = ",".join(["%s"] * len(hop_macs))
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_mac WHERE user_mac IN ({fmt})", tuple(hop_macs))
                    linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])
                if hop_hosts:
                    fmt = ",".join(["%s"] * len(hop_hosts))
                    cursor.execute(f"SELECT DISTINCT user_uuid FROM gatekeeper_host_id WHERE user_host_id IN ({fmt})", tuple(hop_hosts))
                    linked_uuids.update([r.get("user_uuid") for r in _safe_fetchall(cursor) if r.get("user_uuid")])

            # 3) Collect identifiers + grid origins + seen names for all linked UUIDs
            if linked_uuids:
                fmt_u = ",".join(["%s"] * len(linked_uuids))
                u_tuple = tuple(linked_uuids)

                cursor.execute(f"SELECT DISTINCT user_uuid, user_ip, user_name FROM gatekeeper_ip WHERE user_uuid IN ({fmt_u})", u_tuple)
                for r in _safe_fetchall(cursor):
                    if r.get("user_ip"):
                        observed["ips"].add(r["user_ip"])
                    add_names(r.get("user_uuid"), r.get("user_name"))

                cursor.execute(f"SELECT DISTINCT user_uuid, user_mac, user_name FROM gatekeeper_mac WHERE user_uuid IN ({fmt_u})", u_tuple)
                for r in _safe_fetchall(cursor):
                    if r.get("user_mac"):
                        observed["macs"].add(r["user_mac"])
                    add_names(r.get("user_uuid"), r.get("user_name"))

                cursor.execute(f"SELECT DISTINCT user_uuid, user_host_id, user_name FROM gatekeeper_host_id WHERE user_uuid IN ({fmt_u})", u_tuple)
                for r in _safe_fetchall(cursor):
                    if r.get("user_host_id"):
                        observed["hostids"].add(r["user_host_id"])
                    add_names(r.get("user_uuid"), r.get("user_name"))

                cursor.execute(f"SELECT user_uuid, MAX(inbound_from) AS inbound_from, MAX(user_name) AS user_name FROM gatekeeper_from WHERE user_uuid IN ({fmt_u}) GROUP BY user_uuid", u_tuple)
                for r in _safe_fetchall(cursor):
                    if r.get("user_uuid"):
                        observed["grids"][r["user_uuid"]] = r.get("inbound_from")
                    add_names(r.get("user_uuid"), r.get("user_name"))

    except Exception as e:
        current_app.logger.error(f"Ban evidence collection failed (pariah DB): {e}")

    # 4) Pull Robust names/emails if available (best effort)
    try:
        if linked_uuids:
            with robust_conn.cursor() as r_cursor:
                fmt_u = ",".join(["%s"] * len(linked_uuids))
                r_cursor.execute(
                    f"SELECT PrincipalID, FirstName, LastName, Email FROM useraccounts WHERE PrincipalID IN ({fmt_u})",
                    tuple(linked_uuids)
                )
                for r in _safe_fetchall(r_cursor):
                    pid = r.get("PrincipalID")
                    if not pid:
                        continue
                    add_names(pid, f"{r.get('FirstName','')} {r.get('LastName','')}".strip())
    except Exception as e:
        current_app.logger.debug(f"Ban evidence collection skipped (robust DB): {e}")

    # Final evidence formatting (human-readable text, stored in bans_master.notes)
    linked_sorted = sorted([u for u in linked_uuids if u], key=lambda x: str(x))
    ips_sorted = sorted([i for i in observed["ips"] if i], key=lambda x: str(x))
    macs_sorted = sorted([m for m in observed["macs"] if m], key=lambda x: str(x))
    host_sorted = sorted([h for h in observed["hostids"] if h], key=lambda x: str(x))

    lines = []
    lines.append("=== Ban data snapshot ===")
    lines.append(f"CollectedAt(UTC): {_now_utc_iso()}")
    lines.append(f"SeedUuids: {', '.join(sorted(seed_uuids)) if seed_uuids else '(none)'}")
    lines.append(f"SeedIps: {', '.join(sorted(seed_ips)) if seed_ips else '(none)'}")
    lines.append(f"SeedMacs: {', '.join(sorted(seed_macs)) if seed_macs else '(none)'}")
    lines.append(f"SeedHostIDs: {', '.join(sorted(seed_hostids)) if seed_hostids else '(none)'}")
    lines.append("")
    lines.append(f"LinkedAccounts({len(linked_sorted)}):")
    for u in linked_sorted:
        grid = observed["grids"].get(u) or "Unknown/Local"
        names = sorted(list(observed["names"].get(u, set())))
        name_str = " | ".join([n for n in names if n]) if names else "Unknown"
        lines.append(f"- {u} :: {name_str} :: GridFrom={grid}")
    lines.append("")
    lines.append(f"ObservedIPs({len(ips_sorted)}): {', '.join(ips_sorted) if ips_sorted else '(none)'}")
    lines.append(f"ObservedMACs({len(macs_sorted)}): {', '.join(macs_sorted) if macs_sorted else '(none)'}")
    lines.append(f"ObservedHostIDs({len(host_sorted)}): {', '.join(host_sorted) if host_sorted else '(none)'}")

    return {
        "linked_uuids": linked_uuids,
        "observed_ips": observed["ips"],
        "observed_macs": observed["macs"],
        "observed_hostids": observed["hostids"],
        "grid_by_uuid": observed["grids"],
        "notes_text": "\n".join(lines),
    }

@user_mgmt_bp.route('/bans/create', methods=['GET', 'POST'])
@rbac_required(PERM_ISSUE_BANS)
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
    robust_conn = get_robust_db()
    try:
        with pariah_conn.cursor() as cursor:
            # 1. Master Record
            cursor.execute("INSERT INTO bans_master (reason, type) VALUES (%s, %s)", (reason, ban_type))
            ban_id = cursor.lastrowid

            evidence = _collect_ban_evidence(
                pariah_conn,
                robust_conn,
                seed_uuids=uuids,
                seed_ips=ips,
                seed_macs=macs,
                seed_hostids=hostids,
                ban_type=ban_type
            )

            # Persist the evidence snapshot on the ban record (for review and escalation decisions)
            cursor.execute("UPDATE bans_master SET notes = %s WHERE banid = %s", (evidence["notes_text"], ban_id))

            # 2. Cascading Data Inserts
            for ip in ips:
                cursor.execute("INSERT INTO bans_ip (banid, ip) VALUES (%s, %s)", (ban_id, ip))
            for mac in macs:
                cursor.execute("INSERT INTO bans_mac (banid, mac) VALUES (%s, %s)", (ban_id, mac))
            for hostid in hostids:
                cursor.execute("INSERT INTO bans_host_id (banid, hostid) VALUES (%s, %s)", (ban_id, hostid))

            # Every account tied to this ban (seed UUIDs + gatekeeper-linked alts) gets the tier-level ban.
            enforced_uuids = sorted([u for u in evidence["linked_uuids"] if u])
            explicit_uuids = set(uuids)

            # 3. bans_uuid + Robust user level for each linked account
            for uuid in enforced_uuids:
                grid_from = evidence["grid_by_uuid"].get(uuid)
                cursor.execute(
                    "INSERT INTO bans_uuid (banid, uuid, grid) VALUES (%s, %s, %s)",
                    (ban_id, uuid, grid_from),
                )
                set_user_level(uuid, target_level)
                current_app.logger.info(
                    "Ban level %s enforced on UUID %s (type=%s).",
                    target_level,
                    uuid,
                    ban_type,
                )

            # 3B. Related UUID linkage (discovered via lookup — not typed on the form; audit/review)
            for uuid in sorted([u for u in enforced_uuids if u and u not in explicit_uuids]):
                grid_from = evidence["grid_by_uuid"].get(uuid)
                cursor.execute(
                    "INSERT INTO bans_related_uuid (banid, uuid, grid) VALUES (%s, %s, %s)",
                    (ban_id, uuid, grid_from),
                )

            # 3C. Staff notes on all associated accounts
            admin_uuid = session.get('uuid', 'SYSTEM')
            note_lines = [
                f"[BAN #{ban_id}] CreatedAt(UTC)={_now_utc_iso()} Type={ban_type} EnforcedLevel={target_level}",
                f"Reason: {reason}",
                f"EnforcedUUIDs: {', '.join(enforced_uuids) if enforced_uuids else '(none)'}",
                f"RelatedUUIDs: {', '.join(sorted([u for u in enforced_uuids if u and u not in explicit_uuids])) or '(none)'}",
                "Snapshot stored on ban record (Manage Bans)."
            ]
            staff_note = "\n".join(note_lines)
            for uuid in sorted([u for u in evidence["linked_uuids"] if u]):
                cursor.execute(
                    "INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)",
                    (uuid, admin_uuid, staff_note)
                )

        pariah_conn.commit()

        # 4. Trigger Firewall & Robust Workers
        if ban_type in ['ip', 'mac', 'hostid']:
            trigger_system_sync_workers(ban_id)

        log_audit_action("Create Ban", f"Ban #{ban_id} created (type={ban_type}, level={target_level})")
        flash(f'Severity Level {target_level} Ban created and actively enforced successfully.', 'success')
    except Exception as e:
        current_app.logger.error(f"Ban creation failed: {e}")
        flash('Failed to create ban. Check logs.', 'error')

    return redirect(url_for('user_mgmt.manage_bans'))

@user_mgmt_bp.route('/bans/<int:ban_id>/delete', methods=['POST'])
@rbac_required(PERM_ISSUE_BANS)
def delete_ban(ban_id):
    """Deletes a ban and attempts to restore associated accounts to Level 0."""
    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # First, fetch the UUIDs tied to this ban so we can unlock them
            cursor.execute("SELECT uuid FROM bans_uuid WHERE banid = %s", (ban_id,))
            banned_uuids = [row['uuid'] for row in cursor.fetchall()]

            cursor.execute("SELECT uuid FROM bans_related_uuid WHERE banid = %s", (ban_id,))
            related_uuids = [row['uuid'] for row in _safe_fetchall(cursor) if row.get('uuid')]

            # Foreign key cascading will delete the child records in bans_ip, bans_mac, etc.
            cursor.execute("DELETE FROM bans_master WHERE banid = %s", (ban_id,))

            # Staff notes: mark ban removed (do this before commit so it stays transactional)
            admin_uuid = session.get('uuid', 'SYSTEM')
            removed_note = f"[BAN #{ban_id}] RemovedAt(UTC)={_now_utc_iso()} (Ban record deleted; historic reference note retained)"
            for uuid in sorted(set(banned_uuids + related_uuids)):
                cursor.execute(
                    "INSERT INTO user_notes (user_uuid, admin_uuid, note) VALUES (%s, %s, %s)",
                    (uuid, admin_uuid, removed_note)
                )
        pariah_conn.commit()

        # Restore user levels via Robust
        for uuid in banned_uuids:
            set_user_level(uuid, 0)

        # --- Trigger System Synchronization ---
        trigger_system_sync_workers(ban_id)
        # --------------------------------------

        log_audit_action("Remove Ban", f"Ban #{ban_id} removed; restored {len(banned_uuids)} enforced UUID(s) to level 0.")
        flash(f"Ban removed. {len(banned_uuids)} associated avatars have been restored to Level 0.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete ban {ban_id}: {e}")
        flash("An error occurred while removing the ban.", "error")

    return redirect(url_for('user_mgmt.manage_bans'))

@user_mgmt_bp.route('/<uuid>/set_level', methods=['POST'])
@rbac_required(PERM_MANAGE_ROLES)
def update_user_level(uuid):
    """Allows Super Admins to manually adjust a user's level (e.g., Promotions)."""
    is_super = has_permission(PERM_SUPER_ADMIN)
    if not is_super and uuid == session.get('uuid'):
        flash("Security Violation: You cannot modify your own permissions.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

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

@user_mgmt_bp.route('/<uuid>/rename', methods=['POST'])
@rbac_required(PERM_RENAME_USERS)
def rename_user(uuid):
    """Allows Admins to rename a user's avatar."""

    new_first = request.form.get('first_name', '').strip()
    new_last = request.form.get('last_name', '').strip()

    if not new_first or not new_last:
        flash("Both First and Last name are required.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup'))

    # UPDATED: Use the Robust API instead of direct SQL
    if update_robust_name(uuid, new_first, new_last):
        flash(f"User successfully renamed to {new_first} {new_last}. (Note: The user may need to clear their viewer cache).", "success")
    else:
        flash("Failed to update name via Robust API.", "error")

    return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

@user_mgmt_bp.route('/<uuid>/roles', methods=['GET', 'POST'])
@rbac_required(PERM_MANAGE_ROLES)
def manage_roles(uuid):
    # Prevent self-modification
    is_super = has_permission(PERM_SUPER_ADMIN)
    if not is_super and uuid == session.get('uuid'):
        flash("Security Violation: You cannot modify your own permissions.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

    pariah_conn = get_pariah_db()
    robust_conn = get_robust_db()
    
    
    # 1. Fetch user's real name and level from Robust
    with robust_conn.cursor() as r_cursor:
        r_cursor.execute("SELECT FirstName, LastName, userLevel FROM useraccounts WHERE PrincipalID = %s", (uuid,))
        account = r_cursor.fetchone()
        
    if not account:
        flash("User not found.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup'))
        
    avatar_name = f"{account['FirstName']} {account['LastName']}"

    # 2. Fetch current permissions for the target
    current_permissions = 0
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT permissions FROM user_rbac WHERE user_uuid = %s", (uuid,))
        row = cursor.fetchone()
        if row:
            current_permissions = row['permissions']

    if request.method == 'POST':
        selected_bits = request.form.getlist('permissions')
        new_bitmask = 0
        
        # Calculate new bits from form input
        for bit_str in selected_bits:
            try:
                bit_val = int(bit_str)
                # Only allow adding this bit if it's not super_only OR if the admin is a Super Admin
                is_this_bit_super = False
                for cat, perms in RBAC_SCHEMA.items():
                    if bit_val in perms and perms[bit_val].get('super_only'):
                        is_this_bit_super = True
                        break
                
                if not is_this_bit_super or is_super:
                    new_bitmask |= bit_val
            except ValueError:
                pass
        
        # If the admin is NOT a super-user, we MUST preserve any existing super_only bits that were already on the target user.
        if not is_super:
            for cat, perms in RBAC_SCHEMA.items():
                for bit_val, details in perms.items():
                    if details.get('super_only') and (current_permissions & bit_val):
                        new_bitmask |= bit_val

        try:
            # NOTE: We intentionally treat userLevel=200 as "in-world admin, no portal RBAC"
            # and userLevel=201 as "in-world admin that should load portal RBAC on login".
            raw_level = account.get('userLevel', 0)
            try:
                current_level = int(raw_level)
            except (TypeError, ValueError):
                current_level = 0

            with pariah_conn.cursor() as cursor:
                if new_bitmask == 0:
                    cursor.execute("DELETE FROM user_rbac WHERE user_uuid = %s", (uuid,))
                else:
                    cursor.execute("""
                        INSERT INTO user_rbac (user_uuid, permissions) 
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE permissions = VALUES(permissions)
                    """, (uuid, new_bitmask))
            pariah_conn.commit()

            # Normalize Robust level tiers when RBAC is cleared/applied.
            if new_bitmask == 0:
                if current_level == 1:
                    set_user_level(uuid, 0)
                elif current_level == 201:
                    set_user_level(uuid, 200)
            else:
                if current_level == 0:
                    set_user_level(uuid, 1)
                elif current_level == 200:
                    set_user_level(uuid, 201)

            log_audit_action("Update Roles", f"Changed bitmask to {new_bitmask}", target_uuid=uuid)
            flash(f"Permissions updated for {avatar_name}.", "success")
        except Exception as e:
            current_app.logger.error(f"Update roles error: {e}")
            flash("Database error.", "error")
            
        return redirect(url_for('user_mgmt.manage_roles', uuid=uuid))

    return render_template('admin/roles.html', 
                           target_uuid=uuid, 
                           avatar_name=avatar_name, 
                           current_permissions=current_permissions,
                           is_super=is_super)

@user_mgmt_bp.route('/<uuid>/update_email', methods=['POST'])
@rbac_required(PERM_UPDATE_EMAIL)
def admin_update_email(uuid):
    """Allows authorized admins to manually correct a user's email address."""
    new_email = request.form.get('new_email', '').strip()
    
    if not new_email:
        flash("Email address cannot be blank.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

    if update_robust_email(uuid, new_email):
        log_audit_action("Update Email", f"Changed email to {new_email}", target_uuid=uuid)
        flash(f"User's email successfully updated to {new_email}.", "success")
    else:
        flash("Failed to update email via Robust API.", "error")

    return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

@user_mgmt_bp.route('/<uuid>/force_password_reset', methods=['POST'])
@rbac_required(PERM_FORCE_PWRESET)
def admin_force_password_reset(uuid):
    """Generates a secure password reset link and emails it to the user."""
    robust_conn = get_robust_db()
    with robust_conn.cursor() as r_cursor:
        r_cursor.execute("SELECT Email FROM useraccounts WHERE PrincipalID = %s", (uuid,))
        account = r_cursor.fetchone()

    if not account or not account['Email']:
        flash("Cannot send reset link: This user has no email address on file in the grid.", "error")
        return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))

    pariah_conn = get_pariah_db()
    try:
        token, _expires_at = create_password_reset_token(pariah_conn, uuid, ttl_seconds=3600)

        send_password_reset_email(account['Email'], token)
        log_audit_action("Force Password Reset", f"Forced a password reset", target_uuid=uuid)
        flash(f"A secure password reset link has been dispatched to {account['Email']}.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to generate admin password reset for {uuid}: {e}")
        flash("A database error occurred while generating the reset token.", "error")

    return redirect(url_for('user_mgmt.gatekeeper_lookup', type='uuid', q=uuid))