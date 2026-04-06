import os
import sys
import time
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

def get_pariah_db():
    return pymysql.connect(
        host=PARIAH_DB_HOST, user=PARIAH_DB_USER,
        password=PARIAH_DB_PASS, database=PARIAH_DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def check_connection():
    conn = None
    try:
        conn = get_pariah_db()
        # Force an actual query to ensure the engine is fully initialized
        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES;")
            cursor.fetchall()
            
        print("MariaDB connection and query successful. Database is fully ready.")
        return True
    except pymysql.Error as e:
        print(f"Waiting for MariaDB... ({e})")
        return False
    finally:
        # Ensure the connection is closed regardless of success or failure
        if conn:
            conn.close()

if __name__ == "__main__":
    # Simple retry logic as MariaDB might take a moment to fully initialize
    for _ in range(10):
        if check_connection():
            sys.exit(0)
        time.sleep(2) # Wait a bit before retrying
    sys.exit(1) # Exit with failure if connection never succeeded