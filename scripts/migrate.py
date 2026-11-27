import contextlib
import glob
import os
import sys

import pymysql
from dotenv import load_dotenv
from pymysql.constants import CLIENT

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ensure_secrets import ensure_secret_key  # noqa: E402

# Try the system config first, fallback to local dev file
if os.path.exists("/etc/os-pariah/os-pariah.conf"):
    load_dotenv("/etc/os-pariah/os-pariah.conf")
else:
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))

DB_HOST = os.environ.get("OS_PARIAH_DB_HOST")
DB_USER = os.environ.get("OS_PARIAH_DB_USER")
DB_PASS = os.environ.get("OS_PARIAH_DB_PASS")
DB_NAME = os.environ.get("OS_PARIAH_DB_NAME")

# schema_versions marker written when migrations first run against an empty database.
# Not a real migration file; it lets the setup wizard tell a fresh install from an
# upgrade even when the first run is interrupted.
FRESH_INSTALL_SENTINEL = "__fresh_install__"


def get_connection():
    """Establishes a connection capable of running full SQL dump files."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
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

    OS-Pariah bootstraps admins via ADMIN_UUID (PlatformStandards ADR-012 /
    docs/NAMING.md). Login only auto-grants Super Admin when
    the authenticated UUID matches ADMIN_UUID. Idempotent and self-healing: it
    only ever adds the Super Admin bit and never downgrades an existing grant.
    """
    admin_uuid = (os.environ.get("ADMIN_UUID") or "").strip()
    if not admin_uuid:
        print(
            "No ADMIN_UUID set; skipping bootstrap admin. "
            "Set ADMIN_UUID to the OpenSim PrincipalID that should receive Super Admin."
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


def ensure_setup_state(conn, *, preexisting):
    """Reconcile the setup wizard's step table (issue #25). Never blocks startup.

    ``preexisting`` is True when the database already had migrations before this run,
    i.e. the portal was installed before the wizard existed: those installs are
    backfilled as complete and are never gated. A brand-new database is "fresh" and
    gets the first-boot wizard.
    """
    try:
        if _REPO_ROOT not in sys.path:
            sys.path.insert(0, _REPO_ROOT)
        from app.setup import state as setup_state
        from app.setup.providers import get_provider
        from app.utils import instance as instance_ctx

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT config_value FROM config WHERE config_key = 'grid_provider'"
            )
            row = cursor.fetchone()
        provider = get_provider(row[0] if row else None)
        result = setup_state.reconcile(
            conn,
            provider.steps(),
            provider_id=provider.id,
            instance_id=instance_ctx.current().id,
            preexisting=preexisting,
        )
        if result and (result["created"] or result["reopened"]):
            print(
                f"Setup wizard state ({result['origin']} install): "
                f"{len(result['created'])} step(s) added, "
                f"{len(result['reopened'])} reopened."
            )
    except Exception as e:  # noqa: BLE001 - bookkeeping must not stop the portal
        print(f"WARNING: could not reconcile setup wizard state: {e}")


def apply_migrations():
    """Scans the migrations folder and applies anything new."""
    # Platform standard: generate the signing key before any DB work (ADR-013).
    ensure_secret_key()
    conn = get_connection()
    try:
        init_migration_table(conn)
        applied = get_applied_migrations(conn)
        # Remember that this database started empty, even if this run fails halfway and a
        # later run finds migrations already applied (see ensure_setup_state).
        if not applied:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO schema_versions (version) VALUES (%s)",
                    (FRESH_INSTALL_SENTINEL,),
                )
            conn.commit()
            applied = {FRESH_INSTALL_SENTINEL}
        preexisting = FRESH_INSTALL_SENTINEL not in applied
        if not preexisting and not os.environ.get("OS_PARIAH_INSTANCE"):
            # Only installs created by os-pariah-bootstrap (which writes
            # OS_PARIAH_INSTANCE into the conf) get the first-boot gate. Hand-written
            # confs and local dev databases are configured by their owners and are
            # never locked behind /setup.
            print(
                "Not a bootstrap-managed install (OS_PARIAH_INSTANCE unset): "
                "first-boot setup gate disabled."
            )
            preexisting = True

        migrations_dir = os.path.join(_REPO_ROOT, "migrations")
        migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

        if not migration_files:
            print(f"No migration files found in {migrations_dir}.")
            print("CRITICAL ERROR: migrations directory is empty or missing.")
            sys.exit(1)

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
        ensure_setup_state(conn, preexisting=preexisting)
        print("Database is fully up to date!")

    except Exception as e:
        print(f"CRITICAL ERROR: Migration failed: {e}")
        with contextlib.suppress(Exception):
            conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    print("--- OS-Pariah Database Migration Engine ---")
    apply_migrations()
