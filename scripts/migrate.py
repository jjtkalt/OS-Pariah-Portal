import os
import glob
import pymysql
from pymysql.constants import CLIENT
from dotenv import load_dotenv

# Try the system config first, fallback to local dev file
if os.path.exists('/etc/os_pariah/os-pariah.conf'):
    load_dotenv('/etc/os_pariah/os-pariah.conf')
else:
    load_dotenv('.env')

DB_HOST = os.environ.get('PARIAH_DB_HOST')
DB_USER = os.environ.get('PARIAH_DB_USER')
DB_PASS = os.environ.get('PARIAH_DB_PASS')
DB_NAME = os.environ.get('PARIAH_DB_NAME')

def get_connection():
    """Establishes a connection capable of running full SQL dump files."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        client_flag=CLIENT.MULTI_STATEMENTS  # The magic flag for executing .sql files!
    )

def init_migration_table(conn):
    """Creates the tracking table if this is a brand new installation."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                version VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()

def get_applied_migrations(conn):
    """Fetches a list of everything we have already run."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_versions")
        return {row[0] for row in cursor.fetchall()}

def apply_migrations():
    """Scans the migrations folder and applies anything new."""
    conn = get_connection()
    try:
        init_migration_table(conn)
        applied = get_applied_migrations(conn)

        # Grab all .sql files and sort them (001_, 002_, etc.)
        migration_files = sorted(glob.glob(os.path.join('migrations', '*.sql')))

        if not migration_files:
            print("No migration files found in the migrations/ directory.")
            return

        for file_path in migration_files:
            filename = os.path.basename(file_path)
            
            if filename not in applied:
                print(f"Applying migration: {filename}...")
                with open(file_path, 'r', encoding='utf-8') as f:
                    sql_script = f.read()

                with conn.cursor() as cursor:
                    # Run the massive SQL script
                    cursor.execute(sql_script)
                    # Log that we successfully ran it
                    cursor.execute("INSERT INTO schema_versions (version) VALUES (%s)", (filename,))
                
                conn.commit()
                print(f"Successfully applied {filename}.")
            else:
                print(f"Skipping {filename} (Already applied to this database).")

        print("Database is fully up to date!")
        
    except Exception as e:
        print(f"CRITICAL ERROR: Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("--- OS Pariah Database Migration Engine ---")
    apply_migrations()
