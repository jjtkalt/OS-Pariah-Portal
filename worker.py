import os
import sys
import glob
import re
import time
import uuid
import subprocess
import pymysql
from dotenv import load_dotenv

# Try the system config first, fallback to local dev file
if os.path.exists('/etc/os_pariah/os-pariah.conf'):
    load_dotenv('/etc/os_pariah/os-pariah.conf')
else:
    load_dotenv('.env')

# Database 1: OS Pariah
PARIAH_DB_HOST = os.environ.get('PARIAH_DB_HOST', '127.0.0.1')
PARIAH_DB_USER = os.environ.get('PARIAH_DB_USER', 'pariah_user')
PARIAH_DB_PASS = os.environ.get('PARIAH_DB_PASS', 'pariah_password')
PARIAH_DB_NAME = os.environ.get('PARIAH_DB_NAME', 'os_pariah')

# Database 2: ROBUST (OpenSim)
ROBUST_DB_HOST = os.environ.get('ROBUST_DB_HOST', '127.0.0.1')
ROBUST_DB_USER = os.environ.get('ROBUST_DB_USER', 'robust_ro')
ROBUST_DB_PASS = os.environ.get('ROBUST_DB_PASS', 'robust_password')
ROBUST_DB_NAME = os.environ.get('ROBUST_DB_NAME', 'robust')

LOG_DIR = '/home/opensim/Log'

def get_pariah_db():
    return pymysql.connect(
        host=PARIAH_DB_HOST, user=PARIAH_DB_USER, 
        password=PARIAH_DB_PASS, database=PARIAH_DB_NAME, 
        cursorclass=pymysql.cursors.DictCursor
    )

def get_dynamic_config(key, default=None):
    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
            result = cursor.fetchone()
            if result:
                return result['config_value']
            return default
    finally:
        conn.close()

def get_robust_db():
    return pymysql.connect(
        host=ROBUST_DB_HOST, 
        user=ROBUST_DB_USER, 
        password=ROBUST_DB_PASS, 
        database=ROBUST_DB_NAME, 
        cursorclass=pymysql.cursors.DictCursor
    )

def parse_gatekeeper_logs():
    """Parses rotated Gatekeeper logs for the Admin Lookup tool."""
    
    # STRICTLY ONLY process rotated logs ending in a date/number
    rotated_logs = glob.glob(os.path.join(LOG_DIR, 'Robust-main.log.*'))
    
    # Prevent picking up logs we have already renamed to "Processed-..."
    rotated_logs = [f for f in rotated_logs if not os.path.basename(f).startswith('Processed-')]
    rotated_logs.sort(key=os.path.getmtime)

    gatekeeper_regex = re.compile(r'\[GATEKEEPER SERVICE\]: Login request')

    for log_path in rotated_logs:
        filename = os.path.basename(log_path)
        directory = os.path.dirname(log_path)

        print(f"Ingesting newly rotated log file: {filename}")
        conn = get_pariah_db()
        inserted_count = 0

        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as log_file:
                with conn.cursor() as cursor:
                    for line in log_file:
                        if gatekeeper_regex.search(line):
                            try:
                                uuid_match = re.search(r'\(([a-f0-9\-]{36})\)', line, re.IGNORECASE)
                                if not uuid_match: continue
                                user_uuid = uuid_match.group(1)

                                # Name and Origin URI via @
                                name_match = re.search(r'request for (.*?) @', line)
                                user_name = name_match.group(1).replace('.', ' ') if name_match else "Unknown"
                                from_match = re.search(r' @ (.*?) \(', line, re.IGNORECASE)

                                # Hardware & IP Identifiers
                                ip_match = re.search(r', IP[:\s=]+([^\s,]+)', line, re.IGNORECASE)
                                mac_match = re.search(r', Mac[:\s=]+([^\s,]+)', line, re.IGNORECASE)
                                hostid_match = re.search(r', Id0[:\s=]+([^\s,]+)', line, re.IGNORECASE)
                                
                                date_time = line[:19]
                                any_inserted = False

                                if from_match:
                                    cursor.execute("REPLACE INTO gatekeeper_from (user_uuid, date_time, user_name, inbound_from) VALUES (%s, %s, %s, %s)", 
                                                   (user_uuid, date_time, user_name, from_match.group(1)))
                                    any_inserted = True
                                if ip_match:
                                    cursor.execute("REPLACE INTO gatekeeper_ip (user_uuid, date_time, user_name, user_ip) VALUES (%s, %s, %s, %s)", 
                                                   (user_uuid, date_time, user_name, ip_match.group(1)))
                                    any_inserted = True
                                if mac_match:
                                    cursor.execute("REPLACE INTO gatekeeper_mac (user_uuid, date_time, user_name, user_mac) VALUES (%s, %s, %s, %s)", 
                                                   (user_uuid, date_time, user_name, mac_match.group(1)))
                                    any_inserted = True
                                if hostid_match:
                                    cursor.execute("REPLACE INTO gatekeeper_host_id (user_uuid, date_time, user_name, user_host_id) VALUES (%s, %s, %s, %s)", 
                                                   (user_uuid, date_time, user_name, hostid_match.group(1)))
                                    any_inserted = True
                                                   
                                # Prevent false positives in logging
                                if any_inserted:
                                    inserted_count += 1
                                else:
                                    print(f"REGEX MISS: Found login request but no network data extracted. Line: {line.strip()}")

                            except Exception as parse_error:
                                print(f"Error parsing line in {filename}: {parse_error}")
                                continue

                conn.commit()
            
            # The Sysadmin Win: Rename the file instead of tracking state!
            new_filename = f"Processed-{filename}"
            new_log_path = os.path.join(directory, new_filename)
            os.rename(log_path, new_log_path)
                
            print(f"Finished processing. Renamed to {new_filename}. Extracted {inserted_count} login records.")

        except Exception as e:
            print(f"Failed to process log file {filename}: {e}")
        finally:
            conn.close()

def process_iar_backups():
    """Processes all pending IARs using the GridTools screen injection method."""
    conn = get_pariah_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE iar_backups SET status = 'pending' WHERE status = 'processing'")
        conn.commit()

        while True:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, user_uuid FROM iar_backups WHERE status = 'pending' LIMIT 1")
                backup = cursor.fetchone()
                
            if not backup:
                print("IAR queue is empty. No pending backups.")
                break

            backup_id = backup['id']
            user_uuid = backup['user_uuid']
            
            with conn.cursor() as cursor:
                cursor.execute("UPDATE iar_backups SET status = 'processing' WHERE id = %s", (backup_id,))
            conn.commit()
            
            print(f"Processing IAR for User UUID: {user_uuid}")

            try:
                robust_conn = get_robust_db()
                with robust_conn.cursor() as r_cursor:
                    r_cursor.execute("SELECT FirstName, LastName FROM useraccounts WHERE PrincipalID = %s", (user_uuid,))
                    account = r_cursor.fetchone()
                    if not account:
                        raise Exception("Avatar not found in Robust database.")
                    first_name = account['FirstName']
                    last_name = account['LastName']
                robust_conn.close()

                iar_output_dir = get_dynamic_config('IAR_OUTPUT_DIR')
                os.makedirs(iar_output_dir, exist_ok=True)
                
                timestamp = int(time.time())
                clean_name = f"{first_name}_{last_name}".replace(" ", "_")
                filename = f"backup_{clean_name}_{timestamp}.iar"
                full_path = os.path.join(iar_output_dir, filename)

                script_path = f"/tmp/loadscript-{uuid.uuid4().hex}"
                with open(script_path, "w") as f:
                    f.write(f"save iar --skipbadassets {first_name} {last_name} / {full_path}\n")

                env = os.environ.copy()
                env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
                IAR_REGION_SCREEN = os.environ.get('IAR_REGION_SCREEN', 'OpenSim-Admin2')
                
                cmd = ["/usr/bin/screen", "-p", "0", "-S", IAR_REGION_SCREEN, "-X", "stuff", f"command-script {script_path}\r"]
                print(f"Injecting command into screen session: {IAR_REGION_SCREEN}")
                subprocess.run(cmd, env=env, check=True)

                print(f"Command injected. Waiting for {filename} to appear...")
                file_appeared = False
                for _ in range(60):
                    if os.path.exists(full_path):
                        file_appeared = True
                        break
                    time.sleep(1)

                if not file_appeared:
                    raise Exception(f"OpenSim never started writing the IAR. Check {IAR_REGION_SCREEN} console.")

                print(f"File detected. Waiting for write to finish...")
                stable_count = 0
                last_size = -1
                while stable_count < 3:
                    time.sleep(2)
                    if os.path.exists(full_path):
                        current_size = os.path.getsize(full_path)
                        if current_size == last_size and current_size > 0:
                            stable_count += 1
                        else:
                            stable_count = 0
                            last_size = current_size

                if os.path.exists(script_path):
                    os.remove(script_path)

                with conn.cursor() as cursor:
                    relative_path = f"iars/{filename}"
                    cursor.execute("UPDATE iar_backups SET status = 'completed', file_path = %s, completed_at = CURRENT_TIMESTAMP WHERE id = %s", 
                                   (relative_path, backup_id))
                                   
                    success_msg = f"Your Inventory Archive (IAR) backup has completed successfully and is ready for download."
                    cursor.execute("INSERT INTO user_notices (user_uuid, message) VALUES (%s, %s)", (user_uuid, success_msg))
                    
                print(f"IAR backup completed successfully for {first_name} {last_name}.")
                    
            except Exception as iar_error:
                print(f"IAR generation failed: {iar_error}")
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE iar_backups SET status = 'failed' WHERE id = %s", (backup_id,))
                    fail_msg = "Your Inventory Archive (IAR) backup failed to generate. Please contact support."
                    cursor.execute("INSERT INTO user_notices (user_uuid, message) VALUES (%s, %s)", (user_uuid, fail_msg))

            conn.commit()
            
    except Exception as e:
        print(f"IAR processor encountered a critical error: {e}")
    finally:
        conn.close()

def cleanup_old_iars():
    """Deletes old IAR files, database records, and user notices that exceed the retention policy."""
    conn = get_pariah_db()
    retention_days = int(get_dynamic_config('iar_retention_days'))
    iar_output_dir = get_dynamic_config('IAR_OUTPUT_DIR')

    try:
        with conn.cursor() as cursor:
            # 1. Grab all completed or failed backups older than X days
            # Using 'requested_at' since it is guaranteed to exist for every record
            cursor.execute("""
                SELECT id, file_path
                FROM iar_backups
                WHERE status IN ('completed', 'failed')
                AND requested_at < DATE_SUB(NOW(), INTERVAL %s DAY)
            """, (retention_days,))

            old_backups = cursor.fetchall()

            if old_backups:
                deleted_count = 0
                for backup in old_backups:
                    # Nuke the physical file
                    if backup['file_path']:
                        filename = os.path.basename(backup['file_path'])
                        full_path = os.path.join(iar_output_dir, filename)
                        if os.path.exists(full_path):
                            try:
                                os.remove(full_path)
                            except Exception as e:
                                print(f"Failed to delete physical file {full_path}: {e}")

                    # Nuke the database record
                    cursor.execute("DELETE FROM iar_backups WHERE id = %s", (backup['id'],))
                    deleted_count += 1
                print(f"Storage Cleanup: Purged {deleted_count} IAR backups exceeding {retention_days} days.")
            else:
                print("No old IARs to clean up.")

            # 2. Wipe old system messages/notices to reduce database clutter
            # Using 'created_at' to match the user_notices schema
            cursor.execute("DELETE FROM user_notices WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)", (retention_days,))
            notices_deleted = cursor.rowcount
            if notices_deleted > 0:
                print(f"System Cleanup: Purged {notices_deleted} old user notices.")

            conn.commit()

    except Exception as e:
        print(f"IAR Cleanup encountered a critical error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "logs":
            parse_gatekeeper_logs()
        elif sys.argv[1] == "iar":
            process_iar_backups()
            cleanup_old_iars()  # <--- NEW: Runs immediately after queue!
        else:
            print("Unknown argument. Use 'logs' or 'iar'.")
    else:
        print("Usage: python worker.py [logs|iar]")
