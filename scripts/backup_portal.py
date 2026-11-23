#!/usr/bin/env python3
"""
Portal self-backup: MariaDB dump of the OS-Pariah database plus persistent
config and upload trees.

Includes ticket attachments and other durable files under /var/lib/os-pariah
and /etc/os-pariah. Excludes caches and user IAR download trees (those have
their own retention workers). Also syncs os-pariah-worker-iar.timer
OnUnitActiveSec from iar_sweep_interval_days.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from scripts.os_pariah_env import (  # noqa: E402
    get_app_db_connection,
    get_dynamic_config_for_scripts,
    load_app_dotenv,
)

# Explicit high-value paths (also covered if present under ETC_DIR).
SIGNIFICANT_FILES = (
    "/etc/os-pariah/os-pariah.conf",
    "/etc/os-pariah/secrets",
    "/etc/nginx/vhosts.d/os-pariah.conf",
    "/etc/nginx/conf.d/os-pariah-cloudflare-ip.conf",
)

# Copy every regular file in this directory (conf, secrets, oidc_private.pem, …).
ETC_OS_PARIAH_DIR = "/etc/os-pariah"

# Durable application state outside MariaDB (ticket attachments, etc.).
# Not caches, logs, or IAR download trees.
SIGNIFICANT_DIRS = ("/var/lib/os-pariah/uploads",)

IAR_TIMER_DROPIN_DIR = "/etc/systemd/system/os-pariah-worker-iar.timer.d"
IAR_TIMER_DROPIN_FILE = os.path.join(IAR_TIMER_DROPIN_DIR, "interval.conf")

BACKUP_OWNER = "os-pariah"
BACKUP_GROUP = "opensim"
BACKUP_DIR_MODE = 0o750


def _config_int(conn, key: str, minimum: int = 1) -> int:
    raw = get_dynamic_config_for_scripts(conn, key)
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        value = minimum
    if value < minimum:
        value = minimum
    return value


def _find_dump_binary() -> str:
    for name in ("mariadb-dump", "mysqldump"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("Neither mariadb-dump nor mysqldump found on PATH.")


def ensure_backup_dir_ownership(path: Path) -> None:
    """Ensure backup roots are os-pariah:opensim (0750) when running as root."""
    path.mkdir(parents=True, exist_ok=True)
    if os.geteuid() != 0:
        return
    try:
        shutil.chown(path, user=BACKUP_OWNER, group=BACKUP_GROUP)
        os.chmod(path, BACKUP_DIR_MODE)
    except (OSError, LookupError, PermissionError) as exc:
        print(f"Portal Backup: could not set ownership on {path}: {exc}")


def _copy_file_into_files_tree(src_path: Path, files_dir: Path) -> str | None:
    if not src_path.is_file():
        return None
    rel = src_path.as_posix().lstrip("/")
    target = files_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, target)
    if src_path.name == "secrets":
        os.chmod(target, 0o600)
    return src_path.as_posix()


def dump_portal_database(dest_sql_gz: Path) -> None:
    load_app_dotenv()
    host = os.environ.get("OS_PARIAH_DB_HOST", "127.0.0.1")
    user = os.environ.get("OS_PARIAH_DB_USER", "os-pariah")
    password = os.environ.get("OS_PARIAH_DB_PASS", "os-pariah-password")
    database = os.environ.get("OS_PARIAH_DB_NAME", "os_pariah")
    dump_bin = _find_dump_binary()

    with tempfile.NamedTemporaryFile(
        mode="w", prefix="os-pariah-backup-my-", suffix=".cnf", delete=False
    ) as cfg:
        cfg.write(f"[client]\nhost={host}\nuser={user}\npassword={password}\n")
        cfg_path = cfg.name

    try:
        os.chmod(cfg_path, 0o600)
        proc = subprocess.run(
            [
                dump_bin,
                f"--defaults-extra-file={cfg_path}",
                "--single-transaction",
                "--routines",
                "--triggers",
                database,
            ],
            check=False,
            capture_output=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{dump_bin} failed (exit {proc.returncode}): {err}")

        with gzip.open(dest_sql_gz, "wb") as out:
            out.write(proc.stdout)
    finally:
        with suppress(OSError):
            os.unlink(cfg_path)


def copy_significant_files(dest_dir: Path) -> list[str]:
    copied: list[str] = []
    files_dir = dest_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()

    def _record(path: str | None) -> None:
        if path and path not in seen:
            seen.add(path)
            copied.append(path)
            print(f"Portal Backup: copied {path}")

    for src in SIGNIFICANT_FILES:
        src_path = Path(src)
        if not src_path.is_file():
            print(f"Portal Backup: skip missing {src}")
            continue
        _record(_copy_file_into_files_tree(src_path, files_dir))

    etc_dir = Path(ETC_OS_PARIAH_DIR)
    if etc_dir.is_dir():
        for child in sorted(etc_dir.iterdir()):
            if child.is_file():
                _record(_copy_file_into_files_tree(child, files_dir))
    else:
        print(f"Portal Backup: skip missing directory {ETC_OS_PARIAH_DIR}")

    return copied


def copy_significant_dirs(dest_dir: Path) -> list[str]:
    """Copy durable directory trees (ticket uploads, etc.)."""
    copied: list[str] = []
    files_dir = dest_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    for src in SIGNIFICANT_DIRS:
        src_path = Path(src)
        if not src_path.is_dir():
            print(f"Portal Backup: skip missing directory {src}")
            continue
        rel = src_path.as_posix().lstrip("/")
        target = files_dir / rel
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src_path, target, symlinks=False, dirs_exist_ok=False)
        copied.append(src)
        print(f"Portal Backup: copied directory {src}")
    return copied


def finalize_run_dir_ownership(run_dir: Path) -> None:
    """chown -R os-pariah:opensim on a completed run; keep secrets 0600."""
    if os.geteuid() != 0:
        return
    try:
        for dirpath, _dirnames, filenames in os.walk(run_dir):
            shutil.chown(dirpath, user=BACKUP_OWNER, group=BACKUP_GROUP)
            os.chmod(dirpath, BACKUP_DIR_MODE)
            for name in filenames:
                fpath = Path(dirpath) / name
                shutil.chown(fpath, user=BACKUP_OWNER, group=BACKUP_GROUP)
                if name == "secrets":
                    os.chmod(fpath, 0o600)
    except (OSError, LookupError, PermissionError) as exc:
        print(f"Portal Backup: could not finalize ownership on {run_dir}: {exc}")


def purge_old_backups(backup_root: Path, retention_days: int) -> int:
    if not backup_root.is_dir():
        return 0
    cutoff = datetime.now(UTC).timestamp() - (retention_days * 86400)
    removed = 0
    for child in sorted(backup_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
            print(f"Portal Backup: purged expired run {child.name}")
    return removed


def sync_iar_timer_interval(days: int) -> None:
    """Write a systemd drop-in so the IAR timer honors iar_sweep_interval_days."""
    days = max(1, int(days))
    try:
        os.makedirs(IAR_TIMER_DROPIN_DIR, mode=0o755, exist_ok=True)
        content = (
            "# Generated by scripts/backup_portal.py — do not edit by hand.\n"
            "# Source of truth: portal setting iar_sweep_interval_days\n"
            "[Timer]\n"
            "# Empty assignment resets the unit-file value before setting ours.\n"
            "OnUnitActiveSec=\n"
            f"OnUnitActiveSec={days}d\n"
        )
        with open(IAR_TIMER_DROPIN_FILE, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(IAR_TIMER_DROPIN_FILE, 0o644)
        reload = subprocess.run(
            ["/bin/systemctl", "daemon-reload"],
            check=False,
            capture_output=True,
            text=True,
        )
        if reload.returncode != 0:
            print(
                f"Portal Backup: wrote IAR timer drop-in ({days}d) but "
                f"daemon-reload failed: {(reload.stderr or '').strip()}"
            )
        else:
            print(
                f"Portal Backup: synced os-pariah-worker-iar.timer to every {days} day(s)."
            )
    except OSError as exc:
        print(f"Portal Backup: could not sync IAR timer interval: {exc}")


def run_backup() -> int:
    conn = get_app_db_connection()
    try:
        backup_dir = str(
            get_dynamic_config_for_scripts(conn, "portal_backup_dir")
            or "/home/opensim/Backups/portal"
        ).strip()
        retention_days = _config_int(conn, "portal_backup_retention_days", minimum=1)
        sweep_days = _config_int(conn, "iar_sweep_interval_days", minimum=1)
    finally:
        conn.close()

    root = Path(backup_dir)
    ensure_backup_dir_ownership(root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    ensure_backup_dir_ownership(run_dir)

    print(f"Portal Backup: writing {run_dir}")
    try:
        dump_portal_database(run_dir / "os_pariah.sql.gz")
        print("Portal Backup: database dump complete.")
        copied_files = copy_significant_files(run_dir)
        copied_dirs = copy_significant_dirs(run_dir)
        finalize_run_dir_ownership(run_dir)
        manifest = run_dir / "MANIFEST.txt"
        with open(manifest, "w", encoding="utf-8") as fh:
            fh.write(f"created_utc={stamp}\n")
            fh.write("database=os_pariah.sql.gz\n")
            for path in copied_files:
                fh.write(f"file={path}\n")
            for path in copied_dirs:
                fh.write(f"dir={path}\n")
        if os.geteuid() == 0:
            with suppress(OSError, LookupError, PermissionError):
                shutil.chown(manifest, user=BACKUP_OWNER, group=BACKUP_GROUP)
        purged = purge_old_backups(root, retention_days)
        if purged:
            print(
                f"Portal Backup: removed {purged} run(s) older than {retention_days} day(s)."
            )
        sync_iar_timer_interval(sweep_days)
        print("Portal Backup: success.")
        return 0
    except Exception as exc:
        print(f"Portal Backup: FAILED: {exc}", file=sys.stderr)
        shutil.rmtree(run_dir, ignore_errors=True)
        return 1


if __name__ == "__main__":
    sys.exit(run_backup())
