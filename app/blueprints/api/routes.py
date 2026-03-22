import re
from flask import Blueprint, request, session, current_app
from app import cache
from app.utils.db import get_robust_db, get_pariah_db, get_dynamic_config

api_bp = Blueprint('api', __name__, url_prefix='/api')

def has_admin_view_access():
    """
    Determines if the requester should see ALL regions (ignoring the public listable filter).
    Replaces the legacy override password.
    """
    # Condition 1: Logged into the portal as an Admin
    if session.get('uuid') and session.get('is_admin'):
        return True

    # Condition 2: Request comes from an authorized Region Host IP AND the UUID belongs to an Admin
    # X-Forwarded-For is safe to use here because we configured ProxyFix in __init__.py
    client_ip = request.remote_addr 
    owner_uuid = request.headers.get('X-Secondlife-Owner-Key')
    
    # Fetch configured region host IPs from OS_Pariah config
    region_hosts_str = get_dynamic_config('region_host_ips', '')
    authorized_ips = [ip.strip() for ip in region_hosts_str.split(',') if ip.strip()]

    if client_ip in authorized_ips and owner_uuid:
        # Verify if the owner_uuid has admin view access
        robust_conn = get_robust_db()
        with robust_conn.cursor() as cursor:
            cursor.execute("SELECT userLevel FROM useraccounts WHERE PrincipalID = %s", (owner_uuid,))
            account = cursor.fetchone()
            if account and account['userLevel'] >= 200:
                return True

    return False

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


@api_bp.route('/online', methods=['GET'])
def online_lister():
    """
    The main endpoint for the in-world HUD and website widget.
    """
    # 1. Fetch the raw list from memory cache
    all_users = fetch_all_online_users()
    
    # 2. Check Permissions
    show_all = has_admin_view_access()
    
    # 3. Filter regions if not an admin
    filtered_users = []
    if show_all:
        filtered_users = all_users
    else:
        # Fetch the list of allowed public regions from OS_Pariah DB
        # Replaces the hardcoded ["Sandbox", "Sea ", "Welcome"] list
        listable_str = get_dynamic_config('listable_regions', 'Welcome, Sandbox')
        listable_regions = [r.strip().lower() for r in listable_str.split(',') if r.strip()]
        
        for user in all_users:
            if user['region'].lower() in listable_regions:
                filtered_users.append(user)

    # 4. Format Output exactly as the HUD expects (for now):
    # Total Online Users: X<br>
    # User Name,Region<br>
    output_lines = [f"Total Online Users: {len(filtered_users)}<br>"]
    for user in filtered_users:
        output_lines.append(f"{user['name']},{user['region']}<br>")

    # Return as raw text/html so the HUD parser doesn't break
    return "".join(output_lines), 200, {'Content-Type': 'text/html; charset=utf-8'}
