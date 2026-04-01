#!/usr/bin/env python3
import os
import sys
import subprocess
import configparser
import pymysql

def get_db_connection():
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

def run_cmd(cmd_list):
    """Executes a system command and ignores errors (like flushing an empty set)."""
    subprocess.run(cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def sync_firewall():
    print("Starting Pariah Firewall Synchronization...")
    config = configparser.ConfigParser()
    config.read('/etc/os_pariah/os-pariah.conf')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Fetch active IPs
            cursor.execute("SELECT ip FROM bans_ip")
            banned_ips = set(row['ip'] for row in cursor.fetchall())

            # 2. Fetch active Host IDs (Id0)
            cursor.execute("SELECT hostid FROM bans_host_id")
            banned_hosts = set(row['hostid'] for row in cursor.fetchall())

        # --- SYNC IPSET (IP Bans) ---
        print(f"Syncing {len(banned_ips)} IP addresses...")
        # Flush the existing set to ensure we remove deleted bans
        run_cmd(['firewall-cmd', '--permanent', '--ipset=pariah_banned_ips', '--remove-entries-from-file=/dev/null']) 
        run_cmd(['firewall-cmd', '--ipset=pariah_banned_ips', '--flush'])
        
        for ip in banned_ips:
            run_cmd(['firewall-cmd', '--permanent', '--ipset=pariah_banned_ips', '--add-entry', ip])
            run_cmd(['firewall-cmd', '--ipset=pariah_banned_ips', '--add-entry', ip])

        # --- SYNC DIRECT RULES (HostID / Id0 Bans) ---
        # Note: OpenSim uses port 8002 by default for login. 
        # Boyer-Moore (bm) algorithm searches the packet payload for the exact HostID string.
        print(f"Syncing {len(banned_hosts)} Host ID Direct Rules...")
        
        # Unfortunately, firewalld doesn't have an easy "flush all direct rules" command that doesn't wipe custom admin rules.
        # So we remove all known rules first before re-adding them to avoid duplicates.
        # In a future update, we might track direct rule XMLs, but this is a solid V1 baseline.
        for host in banned_hosts:
            rule_args = ['ipv4', 'filter', 'INPUT', '0', '-p', 'tcp', '--dport', '8002', '-m', 'string', '--algo', 'bm', '--string', host, '-j', 'DROP']
            
            # Remove it if it exists
            run_cmd(['firewall-cmd', '--permanent', '--direct', '--remove-rule'] + rule_args)
            # Add it back
            run_cmd(['firewall-cmd', '--permanent', '--direct', '--add-rule'] + rule_args)

        # Apply all permanent changes to runtime
        print("Reloading firewalld to apply changes...")
        run_cmd(['firewall-cmd', '--reload'])
        
        print("Synchronization Complete.")

    finally:
        conn.close()

if __name__ == '__main__':
    # Ensure this is only run as root (via sudo)
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root.")
        sys.exit(1)
        
    sync_firewall()