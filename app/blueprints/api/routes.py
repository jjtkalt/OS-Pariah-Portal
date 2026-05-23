import re
from flask import Blueprint, request, session, current_app
from app import cache
from app.utils.auth_helpers import has_permission
from app.utils.db import get_robust_db, get_pariah_db
from app.utils.schema import PERM_ONLINE_HUD_ALL, PERM_SUPER_ADMIN

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _rbac_mask_allows_full_online_list(mask):
    """Super-admin or explicit Online HUD permission."""
    try:
        m = int(mask)
    except (TypeError, ValueError):
        return False
    return bool(m & PERM_SUPER_ADMIN) or bool(m & PERM_ONLINE_HUD_ALL)


def has_admin_view_access():
    """
    Full /api/online list (all regions) when:
      - Portal session has PERM_ONLINE_HUD_ALL (super-admin implies all perms), or
      - Request from a region_host IP with X-Secondlife-Owner-Key set to a UUID whose user_rbac
        mask includes that permission (or super-admin).
    Otherwise only HUD-listable regions are shown (region_configs.hud_list_users).
    """
    if session.get('uuid') and has_permission(PERM_ONLINE_HUD_ALL):
        return True

    owner_uuid = (request.headers.get('X-Secondlife-Owner-Key') or '').strip()
    if not owner_uuid:
        return False

    client_ip = request.remote_addr
    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM region_hosts WHERE host_ip = %s LIMIT 1", (client_ip,))
        if not cursor.fetchone():
            return False
        cursor.execute("SELECT permissions FROM user_rbac WHERE user_uuid = %s", (owner_uuid,))
        rbac_row = cursor.fetchone()

    perms = rbac_row["permissions"] if rbac_row else 0
    return _rbac_mask_allows_full_online_list(perms)

@cache.cached(timeout=30, key_prefix='raw_online_users')
def fetch_all_online_users():
    """
    Queries the Robust database for all online users (Local and Hypergrid).
    This function's output is cached in memory for 30 seconds.
    """
    robust_conn = get_robust_db()
    users_online = []
    
    try:
        with robust_conn.cursor() as cursor:
            # 1. Local Users
            cursor.execute("""
                SELECT UA.FirstName, UA.LastName, r.regionName 
                FROM useraccounts UA 
                INNER JOIN presence p ON UA.PrincipalID = p.UserID 
                JOIN regions r ON r.uuid = p.RegionID
            """)
            for row in cursor.fetchall():
                # Clean up region name formatting as per original script
                region_use = re.sub(r"\s\d+$", "", row['regionName'])
                users_online.append({
                    'name': f"{row['FirstName']} {row['LastName']}",
                    'region': region_use,
                    'is_hg': False
                })

            # 2. Hypergrid Users
            cursor.execute("""
                SELECT 
                    SUBSTRING_INDEX(SUBSTRING_INDEX(g.UserId, ';', -1), ' ', 1) As FirstName, 
                    SUBSTRING_INDEX(SUBSTRING_INDEX(g.UserId, ';', -1), ' ', -1) As LastName, 
                    r.regionName 
                FROM griduser g 
                INNER JOIN presence p ON p.UserID = SUBSTRING(g.UserId, 1, 36) 
                JOIN regions r ON r.uuid = p.RegionID 
                WHERE LOCATE(';', g.UserId) <> 0
            """)
            for row in cursor.fetchall():
                region_use = re.sub(r"\s\d+$", "", row['regionName'])
                users_online.append({
                    'name': f"{row['FirstName']} {row['LastName']} (HG)",
                    'region': region_use,
                    'is_hg': True
                })
    except Exception as e:
        current_app.logger.error(f"Error fetching online users: {e}")
        
    # Sort alphabetically by name
    return sorted(users_online, key=lambda k: k['name'])


def filter_online_users_by_region(all_users, show_all):
    """Restrict to HUD-listable regions unless show_all is True."""
    if show_all:
        return list(all_users)
    listable_regions = _hud_listable_region_names()
    return [
        user for user in all_users
        if user["region"].lower() in listable_regions
    ]


def get_online_snapshot(show_all):
    """
    Grid-wide online count plus a viewer-filtered user list.
    Used by /api/online and the portal online page.
    """
    all_users = fetch_all_online_users()
    return {
        "total_online": len(all_users),
        "users": filter_online_users_by_region(all_users, show_all),
        "show_all_regions": show_all,
    }


def _hud_listable_region_names():
    """
    Region names where avatars may appear on the public HUD (/api/online).
    Only managed portal regions with hud_list_users=1 and is_active=1.
    Default for new regions is unlisted (hud_list_users=0).
    """
    names = set()
    try:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT region_name
                FROM region_configs
                WHERE hud_list_users = 1 AND is_active = 1
                """
            )
            for row in cursor.fetchall():
                if row.get("region_name"):
                    names.add(row["region_name"].strip().lower())
    except Exception as e:
        current_app.logger.error(f"Error fetching HUD-listable region names: {e}")
    return names


@api_bp.route('/online', methods=['GET'])
def online_lister():
    """
    The main endpoint for the in-world HUD and website widget.
    """
    snapshot = get_online_snapshot(has_admin_view_access())

    # Format output exactly as the HUD expects:
    # Total Online Users: X<br>
    # User Name,Region<br>
    output_lines = [f"Total Online Users: {snapshot['total_online']}<br>"]
    for user in snapshot["users"]:
        output_lines.append(f"{user['name']},{user['region']}<br>")

    return "".join(output_lines), 200, {'Content-Type': 'text/html; charset=utf-8'}
