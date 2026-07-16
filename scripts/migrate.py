import glob
import os
import sys

import pymysql
from dotenv import load_dotenv
from pymysql.constants import CLIENT

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ensure_secrets import ensure_secret_key  # noqa: E402

# Try the system config first, fallback to local dev file
if os.path.exists("/etc/os_pariah/os-pariah.conf"):
    load_dotenv("/etc/os_pariah/os-pariah.conf")
else:
    load_dotenv(".env")

DB_HOST = os.environ.get("PARIAH_DB_HOST")
DB_USER = os.environ.get("PARIAH_DB_USER")
DB_PASS = os.environ.get("PARIAH_DB_PASS")
DB_NAME = os.environ.get("PARIAH_DB_NAME")


def get_connection():
    """Establishes a connection capable of running full SQL dump files."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        client_flag=CLIENT.MULTI_STATEMENTS,  # The magic flag for executing .sql files!
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


def ensure_bootstrap_admin(conn):
    """Grant portal Super Admin to a configured OpenSim account UUID when set.

    OS-Pariah normally bootstraps admins automatically: the first login by an OpenSim
    account with userLevel >= 250 is auto-granted PERM_SUPER_ADMIN (see
    app/blueprints/auth/routes.py). This hook is an optional, env-driven alternative
    (PlatformStandards ADR-012) for grids that want to pre-seed a known admin UUID
    without needing a 250+ account first. Idempotent and self-healing: it only ever
    adds the Super Admin bit and never downgrades an existing grant.
    """
    admin_uuid = (os.environ.get("ADMIN_UUID") or "").strip()
    if not admin_uuid:
        print(
            "No ADMIN_UUID set; skipping bootstrap admin. "
            "OS-Pariah auto-grants Super Admin to the first userLevel >= 250 login."
        )
        return

    try:
        # schema.py: PERM_SUPER_ADMIN = 1 << 0 (bit 0, master key).
        from app.utils.schema import PERM_SUPER_ADMIN
    except Exception:
        PERM_SUPER_ADMIN = 1

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT permissions FROM user_rbac WHERE user_uuid = %s", (admin_uuid,)
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO user_rbac (user_uuid, permissions) VALUES (%s, %s)",
                (admin_uuid, PERM_SUPER_ADMIN),
            )
            print(f"Bootstrap: granted Super Admin to {admin_uuid}.")
        else:
            current = int(
                (row["permissions"] if isinstance(row, dict) else row[0]) or 0
            )
            if current & PERM_SUPER_ADMIN:
                print(
                    f"Bootstrap admin {admin_uuid} already has Super Admin; skipping."
                )
            else:
                cursor.execute(
                    "UPDATE user_rbac SET permissions = permissions | %s "
                    "WHERE user_uuid = %s",
                    (PERM_SUPER_ADMIN, admin_uuid),
                )
                print(f"Bootstrap: added Super Admin bit to {admin_uuid}.")
    conn.commit()


def apply_migrations():
    """Scans the migrations folder and applies anything new."""
    # Platform standard: generate the signing key before any DB work (ADR-013).
    ensure_secret_key()
    conn = get_connection()
    try:
        init_migration_table(conn)
        applied = get_applied_migrations(conn)

        # Grab all .sql files and sort them (001_, 002_, etc.)
        migration_files = sorted(glob.glob(os.path.join("migrations", "*.sql")))

        if not migration_files:
            print("No migration files found in the migrations/ directory.")
            return

        for file_path in migration_files:
            filename = os.path.basename(file_path)

            if filename not in applied:
                print(f"Applying migration: {filename}...")
                with open(file_path, encoding="utf-8") as f:
                    sql_script = f.read()

                with conn.cursor() as cursor:
                    # Run the massive SQL script
                    cursor.execute(sql_script)
                    # Log that we successfully ran it
                    cursor.execute(
                        "INSERT INTO schema_versions (version) VALUES (%s)", (filename,)
                    )

                conn.commit()
                print(f"Successfully applied {filename}.")
            else:
                print(f"Skipping {filename} (Already applied to this database).")

        ensure_bootstrap_admin(conn)
        print("Database is fully up to date!")

    except Exception as e:
        print(f"CRITICAL ERROR: Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    print("--- OS Pariah Database Migration Engine ---")
    apply_migrations()
