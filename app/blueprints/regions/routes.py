import subprocess
import os
import time
from flask import Blueprint, render_template, request, Response, flash, redirect, url_for, current_app, session
from app.utils.db import get_pariah_db, get_robust_db, get_dynamic_config
from app.utils.auth_helpers import require_admin

regions_bp = Blueprint('regions', __name__, url_prefix='/regions')

def format_uptime(seconds):
    """Converts raw seconds into a clean human-readable string like '2d 4h' or '45m'."""
    if not seconds or seconds <= 0:
        return "Just Started"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    if days > 0:
        return f"{int(days)}d {int(hours)}h"
    elif hours > 0:
        return f"{int(hours)}h {int(minutes)}m"
    else:
        return f"{int(minutes)}m"

@regions_bp.route('/api/config/<region_uuid>.xml', methods=['GET'])
def get_region_xml(region_uuid):
    client_ip = request.remote_addr
    region_hosts_str = get_dynamic_config('region_host_ips')
    authorized_ips = [ip.strip() for ip in region_hosts_str.split(',') if ip.strip()]

    if client_ip not in authorized_ips:
        current_app.logger.warning(f"Unauthorized WebXML request from {client_ip} for region {region_uuid}")
        return Response("<error>Unauthorized</error>", status=403, mimetype='application/xml')

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # UPDATED: Fetch the is_active flag
            cursor.execute("SELECT region_name, is_active FROM region_configs WHERE region_uuid = %s", (region_uuid,))
            region_info = cursor.fetchone()

            if not region_info:
                return Response("<error>Region Not Found</error>", status=404, mimetype='application/xml')
            
            # UPDATED: Reject the request if the region is disabled
            if region_info['is_active'] == 0:
                current_app.logger.info(f"Rejected WebXML request for DISABLED region: {region_info['region_name']}")
                return Response("<error>Region Disabled By Administrator</error>", status=403, mimetype='application/xml')

            cursor.execute("SELECT setting_key, setting_value FROM region_settings WHERE region_uuid = %s", (region_uuid,))
            settings = cursor.fetchall()

            cursor.execute("SELECT external_hostname FROM region_hosts WHERE host_ip = %s", (client_ip,))
            host_mapping = cursor.fetchone()

            if host_mapping and host_mapping.get('external_hostname'):
                external_host_name = host_mapping['external_hostname']
            else:
                external_host_name = "SYSTEMIP"

        xml_output = [f'<Nini>\n  <Section Name="{region_info["region_name"]}">']
        xml_output.append(f'    <Key Name="RegionUUID" Value="{region_uuid}" />')
        xml_output.append(f'    <Key Name="ExternalHostName" Value="{external_host_name}" />')
        xml_output.append('    <Key Name="InternalAddress" Value="0.0.0.0" />')
        xml_output.append('    <Key Name="ResolveAddress" Value="False" />')
        xml_output.append('    <Key Name="AllowAlternatePorts" Value="False" />')

        global_max_agents = get_dynamic_config('default_max_agents')
        xml_output.append(f'    <Key Name="MaxAgents" Value="{global_max_agents}" />')

        for setting in settings:
            if setting['setting_key'] != 'MaxAgents':
                xml_output.append(f'    <Key Name="{setting["setting_key"]}" Value="{setting["setting_value"]}" />')

        xml_output.append('  </Section>\n</Nini>')
        return Response("\n".join(xml_output), mimetype='application/xml')

    except Exception as e:
        current_app.logger.error(f"Failed to generate WebXML for {region_uuid}: {e}")
        return Response("<error>Internal Server Error</error>", status=500, mimetype='application/xml')

@regions_bp.route('/manage', methods=['GET'])
@require_admin
def manage_regions():
    combined_regions = {}

    try:
        conn_pariah = get_pariah_db()
        with conn_pariah.cursor() as cursor:
            cursor.execute("""
                SELECT c.region_uuid as uuid, c.region_name as regionName, c.is_active,
                       MAX(IF(s.setting_key = 'InternalPort', s.setting_value, NULL)) AS serverPort
                FROM region_configs c
                LEFT JOIN region_settings s ON c.region_uuid = s.region_uuid
                GROUP BY c.region_uuid, c.region_name, c.is_active
            """)
            for r in cursor.fetchall():
                combined_regions[r['uuid']] = {
                    'uuid': r['uuid'],
                    'regionName': r['regionName'],
                    'serverIP': 'Managed (See DNS Mapping)',
                    'serverPort': r['serverPort'] or 'Unknown',
                    'is_managed': True,
                    'is_active': bool(r['is_active']),
                    'is_online': False,
                    'uptime': 'N/A'
                }

        conn_robust = get_robust_db()
        with conn_robust.cursor() as cursor:
            cursor.execute("SELECT uuid, regionName, serverIP, serverPort FROM regions")
            for r in cursor.fetchall():
                if r['uuid'] in combined_regions:
                    combined_regions[r['uuid']]['is_online'] = True
                    combined_regions[r['uuid']]['serverIP'] = r['serverIP']
                    combined_regions[r['uuid']]['serverPort'] = r['serverPort']
                else:
                    combined_regions[r['uuid']] = {
                        'uuid': r['uuid'],
                        'regionName': r['regionName'],
                        'serverIP': r['serverIP'],
                        'serverPort': r['serverPort'],
                        'is_managed': False,
                        'is_active': True,
                        'is_online': True,
                        'uptime': 'External' # We can't fetch uptime for remote/unmanaged regions
                    }

        # --- SYSTEMD UPTIME FETCHING ---
        managed_safe_names = [r['regionName'].replace(" ", "_") for r in combined_regions.values() if r['is_managed']]
        uptimes = {}
        
        if managed_safe_names:
            try:
                # Ask systemd for all region statuses in one single, fast command
                services = [f"opensim@{name}.service" for name in managed_safe_names]
                cmd = ["/usr/bin/systemctl", "show"] + services + ["-p", "Id,ActiveState,ExecMainStartTimestampMonotonic"]
                output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.DEVNULL)
                
                # Systemd tracks time against the system Monotonic clock (in microseconds)
                current_mono_usec = time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000
                
                current_id, active_state, start_mono = None, None, 0
                
                # Parse the raw systemctl output blocks
                for line in output.split('\n'):
                    line = line.strip()
                    if line.startswith('Id='):
                        current_id = line.split('=', 1)[1]
                    elif line.startswith('ActiveState='):
                        active_state = line.split('=', 1)[1]
                    elif line.startswith('ExecMainStartTimestampMonotonic='):
                        try:
                            start_mono = int(line.split('=', 1)[1])
                        except ValueError:
                            start_mono = 0
                    elif not line:
                        # Blank line = end of block for one service
                        if current_id and current_id.startswith('opensim@') and current_id.endswith('.service'):
                            r_name_safe = current_id[8:-8]
                            if active_state == 'active' and start_mono > 0:
                                uptime_sec = (current_mono_usec - start_mono) / 1_000_000
                                uptimes[r_name_safe] = format_uptime(uptime_sec)
                        current_id, active_state, start_mono = None, None, 0
                        
                # Process the final block just in case the output doesn't end with a trailing newline
                if current_id and current_id.startswith('opensim@') and current_id.endswith('.service'):
                    r_name_safe = current_id[8:-8]
                    if active_state == 'active' and start_mono > 0:
                        uptime_sec = (current_mono_usec - start_mono) / 1_000_000
                        uptimes[r_name_safe] = format_uptime(uptime_sec)

            except Exception as e:
                # If they are running on a dev env without systemd, just ignore gracefully
                current_app.logger.warning(f"Unable to fetch systemd uptimes: {e}")

        # Map the calculated uptimes back to the main region dictionary
        for r in combined_regions.values():
            if r['is_managed'] and r['is_online']:
                safe_name = r['regionName'].replace(" ", "_")
                r['uptime'] = uptimes.get(safe_name, "Starting...")

    except Exception as e:
        current_app.logger.error(f"Region Management Sync Error: {e}")
        flash(f"Database sync failed: {e}", "error")

    final_list = sorted(combined_regions.values(), key=lambda x: x['regionName'])
    return render_template('admin/manage_regions.html', regions=final_list)

@regions_bp.route('/control/<action>/<region_uuid>', methods=['POST'])
@require_admin
def control_region(action, region_uuid):
    if int(session.get('user_level', 0)) < 200:
        flash("Unauthorized.", "error")
        return redirect(url_for('regions.manage_regions'))

    allowed_actions = ['start', 'stop', 'restart', 'oar']
    if action not in allowed_actions:
        return redirect(url_for('regions.manage_regions'))

    pariah_conn = get_pariah_db()
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
        region = cursor.fetchone()

    if not region:
        flash("Region config not found in Portal database.", "error")
        return redirect(url_for('regions.manage_regions'))

    region_name = region['region_name']
    safe_region_name = region_name.replace(" ", "_")
    
    env = os.environ.copy()
    
    try:
        # --- NEW SYSTEMD INTEGRATION ---
        if action == 'start':
            cmd = ["/usr/bin/sudo", "/bin/systemctl", "start", f"opensim@{safe_region_name}.service"]
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            flash(f"Start signal sent to systemd for '{region_name}'.", "info")
            
        elif action == 'stop':
            cmd = ["/usr/bin/sudo", "/bin/systemctl", "stop", f"opensim@{safe_region_name}.service"]
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            flash(f"Stop signal sent to systemd for '{region_name}'.", "info")
            
        elif action == 'restart':
            cmd = ["/usr/bin/sudo", "/bin/systemctl", "restart", f"opensim@{safe_region_name}.service"]
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            flash(f"Restart initiated via systemd for '{region_name}'.", "info")
            
        # --- OAR BACKUPS (Still requires screen injection) ---
        elif action == 'oar':
            backup_dir = os.path.join(current_app.root_path, 'static', 'downloads', 'oars')
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"{backup_dir}/{safe_region_name}_{timestamp}.oar"
            
            screen_name = f"OpenSim-{safe_region_name}"
            stuff_cmd = f"save oar {filename}\r"
            # Note: We use sudo here assuming the screen session is owned by the 'opensim' user
            cmd = ["/usr/bin/sudo", "-u", "opensim", "/usr/bin/screen", "-p", "0", "-S", screen_name, "-X", "stuff", stuff_cmd]
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            flash(f"OAR backup requested for '{region_name}'.", "info")

    except Exception as e:
        current_app.logger.error(f"Subprocess execution failed for action {action} on {region_name}: {e}")
        flash(f"Fatal error executing control script. Check server logs.", "error")

    return redirect(url_for('regions.manage_regions'))

@regions_bp.route('/add', methods=['GET', 'POST'])
@require_admin
def add_region():
    if request.method == 'POST':
        region_name = request.form.get('region_name', '').strip()
        region_uuid = request.form.get('region_uuid', '').strip()

        if not region_name or not region_uuid:
            flash("Region Name and UUID are required.", "error")
            return redirect(url_for('regions.add_region'))

        size = request.form.get('Size', '256')
        settings_to_insert = {
            'Location': request.form.get('Location', '1000,1000'),
            'InternalPort': request.form.get('InternalPort', '9000'),
            'MaxPrims': request.form.get('MaxPrims', '15000'),
            'SizeX': size,
            'SizeY': size
        }

        pariah_conn = get_pariah_db()
        try:
            with pariah_conn.cursor() as cursor:
                cursor.execute("INSERT INTO region_configs (region_uuid, region_name) VALUES (%s, %s)", (region_uuid, region_name))
                for key, value in settings_to_insert.items():
                    cursor.execute("""
                        INSERT INTO region_settings (region_uuid, setting_key, setting_value)
                        VALUES (%s, %s, %s)
                    """, (region_uuid, key, value))
            pariah_conn.commit()
            flash(f"Region '{region_name}' added successfully.", "success")
            return redirect(url_for('regions.manage_regions'))
        except Exception as e:
            current_app.logger.error(f"Failed to add region: {e}")
            flash("Failed to add region. The UUID might already exist.", "error")

    max_multiplier = int(get_dynamic_config('max_region_size_multiplier'))
    sizes = [i * 256 for i in range(1, max_multiplier + 1)]
    return render_template('admin/add_region.html', sizes=sizes)

@regions_bp.route('/toggle_state/<region_uuid>', methods=['POST'])
@require_admin
def toggle_state(region_uuid):
    """Flips a managed region between Enabled (1) and Disabled (0)."""
    if int(session.get('user_level', 0)) < 200:
        flash("Unauthorized.", "error")
        return redirect(url_for('regions.manage_regions'))

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # Fetch current state
            cursor.execute("SELECT is_active, region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
            region = cursor.fetchone()
            
            if not region:
                flash("Region not found in the Portal Database.", "error")
                return redirect(url_for('regions.manage_regions'))

            # Flip it!
            new_state = 0 if region['is_active'] == 1 else 1
            cursor.execute("UPDATE region_configs SET is_active = %s WHERE region_uuid = %s", (new_state, region_uuid))
            pariah_conn.commit()
            
            status_word = "Enabled" if new_state == 1 else "Disabled"
            flash(f"Region '{region['region_name']}' is now {status_word}.", "success")
            
            # Warn them if they disabled a region that is currently running
            if new_state == 0:
                flash("Note: If this region is currently online, you still need to send a 'Stop' or 'Restart' signal for the simulator to drop it.", "info")

    except Exception as e:
        current_app.logger.error(f"Failed to toggle region state: {e}")
        flash("A database error occurred.", "error")

    return redirect(url_for('regions.manage_regions'))

@regions_bp.route('/delete/<region_uuid>', methods=['POST'])
@require_admin
def delete_region(region_uuid):
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized.", "error")
        return redirect(url_for('regions.manage_regions'))

    pariah_conn = get_pariah_db()
    try:
        with pariah_conn.cursor() as cursor:
            # UPDATED: Enforce the Guardrail!
            cursor.execute("SELECT is_active, region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
            region = cursor.fetchone()
            
            if region and region['is_active'] == 1:
                flash(f"SAFETY LOCK: You must Disable '{region['region_name']}' before you can delete it.", "error")
                return redirect(url_for('regions.manage_regions'))

            cursor.execute("DELETE FROM region_configs WHERE region_uuid = %s", (region_uuid,))
        pariah_conn.commit()
        flash("Region configuration deleted successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete region: {e}")
        flash("An error occurred while deleting the region.", "error")

    return redirect(url_for('regions.manage_regions'))

@regions_bp.route('/edit/<region_uuid>', methods=['GET', 'POST'])
@require_admin
def edit_region(region_uuid):
    if request.method == 'POST':
        size = request.form.get('Size', '256')
        settings_to_update = {
            'Location': request.form.get('Location'),
            'InternalPort': request.form.get('InternalPort'),
            'MaxPrims': request.form.get('MaxPrims', '10000'),
            'SizeX': size,
            'SizeY': size
        }
        try:
            pariah_conn = get_pariah_db()
            with pariah_conn.cursor() as cursor:
                new_name = request.form.get('region_name')
                if new_name:
                    cursor.execute("UPDATE region_configs SET region_name = %s WHERE region_uuid = %s", (new_name, region_uuid))
                for key, value in settings_to_update.items():
                    if value:
                        cursor.execute("""
                            INSERT INTO region_settings (region_uuid, setting_key, setting_value)
                            VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                        """, (region_uuid, key, value))
            pariah_conn.commit()
            flash('Region configuration updated successfully.', 'success')
        except Exception as e:
            current_app.logger.error(f"Failed to update region config: {e}")
            flash('An error occurred.', 'error')
        return redirect(url_for('regions.edit_region', region_uuid=region_uuid))

    try:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("SELECT region_name FROM region_configs WHERE region_uuid = %s", (region_uuid,))
            region = cursor.fetchone()
            cursor.execute("SELECT setting_key, setting_value FROM region_settings WHERE region_uuid = %s", (region_uuid,))
            current_settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

        # Pass the dynamic size options to the template
        max_multiplier = int(get_dynamic_config('max_region_size_multiplier'))
        sizes = [i * 256 for i in range(1, max_multiplier + 1)]

        return render_template('admin/edit_region.html', region=region, settings=current_settings, region_uuid=region_uuid, sizes=sizes)
    except Exception as e:
        current_app.logger.error(f"Failed to load edit page: {e}")
        flash('An error occurred loading the region.', 'error')
        return redirect(url_for('regions.manage_regions'))

@regions_bp.route('/import/<region_uuid>', methods=['POST'])
@require_admin
def import_region(region_uuid):
    try:
        robust_conn = get_robust_db()
        with robust_conn.cursor() as cursor:
            cursor.execute("SELECT regionName, serverIP, serverPort, locX, locY FROM regions WHERE uuid = %s", (region_uuid,))
            region_data = cursor.fetchone()

        if not region_data:
            flash("Region not found in the Robust database.", "error")
            return redirect(url_for('regions.manage_regions'))

        loc_x = int(region_data['locX'])
        loc_y = int(region_data['locY'])
        grid_x = loc_x // 256 if loc_x > 10000 else loc_x
        grid_y = loc_y // 256 if loc_y > 10000 else loc_y

        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("""
                INSERT IGNORE INTO region_configs (region_uuid, region_name) 
                VALUES (%s, %s)
            """, (region_uuid, region_data['regionName']))

            default_settings = {
                'InternalPort': region_data['serverPort'],
                'Location': f"{grid_x},{grid_y}",
                'MaxPrims': '10000',
                'MaxAgents': '100',
                'SizeX': '256',
                'SizeY': '256'
            }

            for key, value in default_settings.items():
                if value is not None:
                    cursor.execute("""
                        INSERT INTO region_settings (region_uuid, setting_key, setting_value)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                    """, (region_uuid, key, str(value)))

        pariah_conn.commit()
        flash(f"Successfully imported {region_data['regionName']}.", "success")
        return redirect(url_for('regions.edit_region', region_uuid=region_uuid))

    except Exception as e:
        current_app.logger.error(f"Failed to import region {region_uuid}: {e}")
        flash(f"Import failed: {e}", "error")
        return redirect(url_for('regions.manage_regions'))

@regions_bp.route('/hosts', methods=['GET', 'POST'])
@require_admin
def manage_hosts():
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized: Only Level 250+ Senior Admins can modify DNS mappings.", "error")
        return redirect(url_for('regions.manage_regions'))

    pariah_conn = get_pariah_db()

    if request.method == 'POST':
        host_ip = request.form.get('host_ip', '').strip()
        external_hostname = request.form.get('external_hostname', '').strip()

        if host_ip and external_hostname:
            try:
                with pariah_conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO region_hosts (host_ip, external_hostname)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE external_hostname = VALUES(external_hostname)
                    """, (host_ip, external_hostname))
                pariah_conn.commit()
                flash(f"Mapping for {host_ip} updated to {external_hostname}.", "success")
            except Exception as e:
                current_app.logger.error(f"Failed to update region_hosts: {e}")
                flash("Database error while saving the mapping.", "error")
        else:
            flash("Both IP Address and External Hostname are required.", "error")

        return redirect(url_for('regions.manage_hosts'))

    try:
        with pariah_conn.cursor() as cursor:
            cursor.execute("SELECT host_ip, external_hostname FROM region_hosts ORDER BY host_ip ASC")
            hosts = cursor.fetchall()
        return render_template('admin/manage_hosts.html', hosts=hosts)
    except Exception as e:
        current_app.logger.error(f"Failed to load region_hosts: {e}")
        flash("Could not load the DNS mapping table.", "error")
        return redirect(url_for('regions.manage_regions'))


@regions_bp.route('/hosts/<ip>/delete', methods=['POST'])
@require_admin
def delete_host(ip):
    if int(session.get('user_level', 0)) < 250:
        flash("Unauthorized.", "error")
        return redirect(url_for('regions.manage_regions'))

    try:
        pariah_conn = get_pariah_db()
        with pariah_conn.cursor() as cursor:
            cursor.execute("DELETE FROM region_hosts WHERE host_ip = %s", (ip,))
        pariah_conn.commit()
        flash(f"Mapping for {ip} deleted permanently.", "success")
    except Exception as e:
        current_app.logger.error(f"Failed to delete host mapping for {ip}: {e}")
        flash("An error occurred during deletion.", "error")

    return redirect(url_for('regions.manage_hosts'))
