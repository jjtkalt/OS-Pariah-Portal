#!/usr/bin/env python3
import os
import sys
import configparser
import pymysql

def get_db_connection(config):
    # Fallback to dev paths if not on production server
    if not config.sections():
        config.read(os.path.join(os.path.dirname(__file__), '..', '.env'))

    return pymysql.connect(
        host=config.get('Pariah Database', 'PARIAH_DB_HOST', fallback='127.0.0.1'),
        user=config.get('Pariah Database', 'PARIAH_DB_USER', fallback='pariah_user'),
        password=config.get('Pariah Database', 'PARIAH_DB_PASS', fallback=''),
        database=config.get('Pariah Database', 'PARIAH_DB_NAME', fallback='os_pariah'),
        cursorclass=pymysql.cursors.DictCursor
    )

def sync_macs():
    print("Starting Robust MAC Synchronization...")
    config = configparser.ConfigParser()
    config.read('/etc/os_pariah/os-pariah.conf')
    
    # We allow the path to be overridden in the config, but default to your specific setup!
    robust_conf_path = config.get('System & Backend', 'ROBUST_CONF_PATH', fallback='/home/opensim/Configs/Robust/main')
    
    if not os.path.exists(robust_conf_path):
        print(f"ERROR: Robust configuration file not found at {robust_conf_path}")
        sys.exit(1)

    conn = get_db_connection(config)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT mac FROM bans_mac")
            macs = [row['mac'] for row in cursor.fetchall()]
    finally:
        conn.close()

    mac_string = ",".join(macs)
    print(f"Syncing {len(macs)} MAC addresses to {robust_conf_path}...")

    # Safely parse and update the INI file line-by-line to preserve all comments
    with open(robust_conf_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_target_section = False
    replaced_in_section = False
    target_sections = ['GatekeeperService', 'LoginService']
    
    for line in lines:
        stripped = line.strip()
        
        # Check for section headers
        if stripped.startswith('[') and stripped.endswith(']'):
            # If we are leaving a target section and haven't written DeniedMacs yet, inject it!
            if in_target_section and not replaced_in_section:
                new_lines.append(f"    DeniedMacs = \"{mac_string}\"\n")
            
            section_name = stripped[1:-1]
            if section_name in target_sections:
                in_target_section = True
                replaced_in_section = False
            else:
                in_target_section = False
                
        # Check for existing DeniedMacs line inside the target sections
        elif in_target_section and stripped.startswith('DeniedMacs'):
            # Safely replace it while keeping original indentation
            indent = line[:len(line) - len(line.lstrip())]
            line = f"{indent}DeniedMacs = \"{mac_string}\"\n"
            replaced_in_section = True
            
        new_lines.append(line)
        
    # Edge case: If the file ends exactly on a target section with no trailing lines
    if in_target_section and not replaced_in_section:
        new_lines.append(f"    DeniedMacs = \"{mac_string}\"\n")

    with open(robust_conf_path, 'w') as f:
        f.writelines(new_lines)
        
    print("MAC synchronization complete. (Note: Robust must be restarted for MAC bans to take effect)")

if __name__ == '__main__':
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root.")
        sys.exit(1)
    sync_macs()