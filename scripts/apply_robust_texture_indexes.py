#!/usr/bin/env python3
"""Apply additive Robust indexes used by the Texture Gallery (one-off ops).

OpenSimulator does not require these indexes; they only speed Pariah gallery /
snapshot queries. Safe to run while Robust is up (INPLACE / IF NOT EXISTS).

Uses a privileged MariaDB account (root via sudo socket, or ROBUST_DB_ADMIN_*).
Do NOT use the portal's read-only ``robust_ro`` user — it cannot CREATE INDEX.

Examples::

    # Preferred on the grid host (unix_socket as root):
    sudo /opt/os_pariah/venv/bin/python \\
        /opt/os_pariah/scripts/apply_robust_texture_indexes.py

    # Or pipe SQL:
    sudo mariadb robust < /opt/os_pariah/scripts/sql/robust_texture_gallery_indexes.sql

    # Dry-run (connect + SHOW INDEX, no DDL):
    sudo .../apply_robust_texture_indexes.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

import pymysql
from dotenv import load_dotenv

INDEXES = (
    {
        "name": "idx_pariah_fsassets_create_time",
        "table": "fsassets",
        "ddl": (
            "CREATE INDEX IF NOT EXISTS idx_pariah_fsassets_create_time "
            "ON fsassets (create_time)"
        ),
    },
    {
        "name": "idx_pariah_inventoryitems_assetid",
        "table": "inventoryitems",
        "ddl": (
            "CREATE INDEX IF NOT EXISTS idx_pariah_inventoryitems_assetid "
            "ON inventoryitems (assetID)"
        ),
    },
    {
        "name": "idx_pariah_inventoryitems_type_avatar",
        "table": "inventoryitems",
        "ddl": (
            "CREATE INDEX IF NOT EXISTS idx_pariah_inventoryitems_type_avatar "
            "ON inventoryitems (assetType, avatarID)"
        ),
    },
)


def _load_env() -> None:
    if os.path.exists("/etc/os_pariah/os-pariah.conf"):
        load_dotenv("/etc/os_pariah/os-pariah.conf")
    else:
        load_dotenv(".env")


def _connect():
    """Connect as DB admin. Prefer unix_socket when run via sudo as root."""
    _load_env()
    db_name = os.environ.get("ROBUST_DB_NAME", "robust")
    host = os.environ.get("ROBUST_DB_ADMIN_HOST") or os.environ.get(
        "ROBUST_DB_HOST", "127.0.0.1"
    )
    user = os.environ.get("ROBUST_DB_ADMIN_USER", "root")
    password = os.environ.get("ROBUST_DB_ADMIN_PASS", "")
    socket_path = os.environ.get("ROBUST_DB_ADMIN_SOCKET", "")

    kwargs = {
        "database": db_name,
        "user": user,
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }
    if socket_path:
        kwargs["unix_socket"] = socket_path
    elif os.geteuid() == 0 and host in ("127.0.0.1", "localhost"):
        # Root via sudo: try default MariaDB socket auth first.
        for candidate in (
            "/run/mysql/mysql.sock",
            "/var/run/mysql/mysql.sock",
            "/var/lib/mysql/mysql.sock",
        ):
            if os.path.exists(candidate):
                kwargs["unix_socket"] = candidate
                break
        else:
            kwargs["host"] = host
            if password:
                kwargs["password"] = password
    else:
        kwargs["host"] = host
        if password:
            kwargs["password"] = password

    return pymysql.connect(**kwargs), db_name


def _index_exists(cursor, schema: str, table: str, name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 AS ok
          FROM information_schema.statistics
         WHERE table_schema = %s
           AND table_name = %s
           AND index_name = %s
         LIMIT 1
        """,
        (schema, table, name),
    )
    return cursor.fetchone() is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which indexes are missing; do not CREATE INDEX.",
    )
    args = parser.parse_args(argv)

    try:
        conn, schema = _connect()
    except Exception as exc:
        print(f"ERROR: could not connect as MariaDB admin: {exc}", file=sys.stderr)
        print(
            "Hint: run via sudo for unix_socket root auth, or set "
            "ROBUST_DB_ADMIN_USER / ROBUST_DB_ADMIN_PASS / ROBUST_DB_ADMIN_SOCKET.",
            file=sys.stderr,
        )
        return 1

    try:
        with conn.cursor() as cursor:
            # Sanity: required tables exist (OpenSim FSAssets + inventory).
            for table in ("fsassets", "inventoryitems"):
                cursor.execute(
                    """
                    SELECT 1 AS ok
                      FROM information_schema.tables
                     WHERE table_schema = %s AND table_name = %s
                     LIMIT 1
                    """,
                    (schema, table),
                )
                if cursor.fetchone() is None:
                    print(
                        f"ERROR: table {schema}.{table} not found. "
                        "Aborting — wrong database or non-FSAssets Robust?",
                        file=sys.stderr,
                    )
                    return 2

            for spec in INDEXES:
                exists = _index_exists(cursor, schema, spec["table"], spec["name"])
                if exists:
                    print(f"OK  already present: {spec['name']} on {spec['table']}")
                    continue
                if args.dry_run:
                    print(f"DRY would create: {spec['name']} on {spec['table']}")
                    print(f"     {spec['ddl']}")
                    continue
                print(f"CREATE {spec['name']} on {spec['table']} ...")
                try:
                    cursor.execute(spec["ddl"])
                except pymysql.err.OperationalError as exc:
                    # Older MariaDB without IF NOT EXISTS on CREATE INDEX.
                    if exists:
                        continue
                    # Retry plain CREATE INDEX if IF NOT EXISTS unsupported.
                    if "IF NOT EXISTS" in str(exc) or exc.args[0] in (1064,):
                        plain = spec["ddl"].replace("IF NOT EXISTS ", "")
                        cursor.execute(plain)
                    else:
                        raise
                print(f"OK  created: {spec['name']}")
        print("Done. OpenSim/Robust were not restarted; additive indexes only.")
        return 0
    except Exception as exc:
        print(f"ERROR applying indexes: {exc}", file=sys.stderr)
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
