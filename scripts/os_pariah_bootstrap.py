#!/usr/bin/env python3
"""os-pariah-bootstrap: the one root-once step after ``zypper install os-pariah``.

Solves the chicken-and-egg that stops the portal from starting (no conf, no database),
then hands over to the web wizard at ``/setup``.

Does:
  1. Create the portal database (``os_pariah``) and a portal-only MariaDB account.
  2. Create a **SELECT-only** account on the *existing* grid (Robust) database. The grid
     must already exist; it is never modified.
  3. Write ``/etc/os-pariah/os-pariah.conf`` (0640 os-pariah:opensim).
  4. Optionally set the nginx ``server_name`` / certificate paths, ``nginx -t``, reload.
  5. Write a one-time setup token and ``systemctl enable --now os-pariah``.

Never does: touch OpenSim units, ``*.ini`` files, the Robust schema, or any OpenSim
service. The only units it controls are this instance's own unit and nginx (reload).

Automation: ``--non-interactive``, ``--answers FILE`` (JSON, ``answers_version: 1``),
``--json`` (machine-readable result), ``--dry-run`` (print the plan, change nothing).
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ANSWERS_VERSION = 1
PLACEHOLDER_DB_PASS = "ChangeMe-LocalDev"  # .env.example template value

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent


def _load_instance_module():
    """Load app/utils/instance.py by path: a root CLI should not import the whole app."""
    path = _REPO_ROOT / "app" / "utils" / "instance.py"
    spec = importlib.util.spec_from_file_location("os_pariah_instance", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


instance_mod = _load_instance_module()
Instance = instance_mod.Instance
ReservedInstanceError = instance_mod.ReservedInstanceError

_IDENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9_.@:+=,-]{12,128}$")
_LOCAL_DB_HOSTS = {"127.0.0.1", "localhost", "::1"}

_ANSWER_KEYS = {
    "answers_version",
    "db_host",
    "db_socket",
    "db_admin_user",
    "db_admin_password",
    "portal_db_password",
    "robust_db_host",
    "robust_db_name",
    "robust_ro_user",
    "robust_ro_password",
    "admin_uuid",
    "portal_host",
    "tls_cert",
    "tls_key",
    "force",
}


class BootstrapError(Exception):
    """A problem the admin can fix; message is shown verbatim."""


# ----------------------------------------------------------------------- answers


@dataclass
class Answers:
    admin_uuid: str = ""
    db_host: str = "127.0.0.1"
    db_socket: str = "/run/mysql/mysql.sock"
    db_admin_user: str = "root"
    db_admin_password: str = ""
    portal_db_password: str = ""
    robust_db_host: str = "127.0.0.1"
    robust_db_name: str = "robust"
    robust_ro_user: str = "robust_ro"
    robust_ro_password: str = ""
    portal_host: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    force: bool = False
    # Not answers: set during validation so the plan knows what was supplied.
    robust_ro_password_supplied: bool = field(default=False, repr=False)


def load_answers_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"Cannot read answers file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BootstrapError("The answers file must contain a JSON object.")
    version = raw.get("answers_version")
    if version != ANSWERS_VERSION:
        raise BootstrapError(
            f"Unsupported answers_version {version!r}; this bootstrap expects "
            f"{ANSWERS_VERSION}."
        )
    unknown = sorted(set(raw) - _ANSWER_KEYS)
    if unknown:
        raise BootstrapError(f"Unknown key(s) in answers file: {', '.join(unknown)}")
    return {k: v for k, v in raw.items() if k != "answers_version"}


def validate_answers(raw: dict) -> Answers:
    """Turn raw answers into a validated Answers or raise BootstrapError (all problems)."""
    answers = Answers()
    for key, value in raw.items():
        if key not in {f.name for f in dataclasses.fields(Answers)}:
            raise BootstrapError(f"Unknown answer {key!r}.")
        setattr(answers, key, value)

    errors: list[str] = []

    def need_ident(label: str, value: str):
        if not isinstance(value, str) or not _IDENT_RE.match(value):
            errors.append(f"{label} must be 1-64 letters, digits, '_' or '-'.")

    try:
        uuid.UUID(str(answers.admin_uuid))
    except ValueError:
        errors.append(
            "admin_uuid must be the OpenSim PrincipalID (a UUID) of the account that "
            "becomes Super Admin."
        )
    answers.admin_uuid = str(answers.admin_uuid).strip().lower()

    for label, host in (
        ("db_host", answers.db_host),
        ("robust_db_host", answers.robust_db_host),
    ):
        if host not in _LOCAL_DB_HOSTS:
            errors.append(
                f"{label} must be local (127.0.0.1/localhost): bootstrap only provisions a "
                "MariaDB on this host. For a remote database create the accounts by hand "
                "(docs/DEPLOYMENT.md)."
            )
    need_ident("robust_db_name", answers.robust_db_name)
    need_ident("robust_ro_user", answers.robust_ro_user)

    for label in ("portal_db_password", "robust_ro_password"):
        value = getattr(answers, label)
        if value and not _PASSWORD_RE.match(value):
            errors.append(
                f"{label} must be 12-128 characters from letters, digits and _.@:+=,- "
                "(it is stored in an env-style conf file)."
            )
    answers.robust_ro_password_supplied = bool(answers.robust_ro_password)

    host = (answers.portal_host or "").strip().lower()
    if host and not _HOST_RE.match(host):
        errors.append("portal_host must be a hostname like portal.example.com.")
    answers.portal_host = host

    if bool(answers.tls_cert) != bool(answers.tls_key):
        errors.append("Give both tls_cert and tls_key, or neither.")
    for label in ("tls_cert", "tls_key"):
        value = getattr(answers, label)
        if value and not os.path.isabs(value):
            errors.append(f"{label} must be an absolute path.")
    if (answers.tls_cert or answers.tls_key) and not host:
        errors.append(
            "tls_cert/tls_key need portal_host so nginx knows which name to serve."
        )

    if errors:
        raise BootstrapError("\n".join(f"- {e}" for e in errors))

    if not answers.portal_db_password:
        answers.portal_db_password = secrets.token_urlsafe(24)
    if not answers.robust_ro_password:
        answers.robust_ro_password = secrets.token_urlsafe(24)
    return answers


# --------------------------------------------------------------------- rendering


def render_conf(answers: Answers, instance, *, redact: bool = False) -> str:
    def secret(value: str) -> str:
        return "***" if redact else value

    lines = [
        "# OS-Pariah portal configuration, written by os-pariah-bootstrap.",
        "# Edit with care; restart the service afterwards. SECRET_KEY is generated on",
        f"# first start into {instance.secrets_path} (do not put it here).",
        f"OS_PARIAH_INSTANCE={instance.id}",
        f"OS_PARIAH_DB_HOST={answers.db_host}",
        f"OS_PARIAH_DB_USER={instance.db_user}",
        f"OS_PARIAH_DB_PASS={secret(answers.portal_db_password)}",
        f"OS_PARIAH_DB_NAME={instance.db_name}",
        "",
        "# Grid (Robust) database: SELECT-only account created by bootstrap.",
        f"ROBUST_DB_HOST={answers.robust_db_host}",
        f"ROBUST_DB_USER={answers.robust_ro_user}",
        f"ROBUST_DB_PASS={secret(answers.robust_ro_password)}",
        f"ROBUST_DB_NAME={answers.robust_db_name}",
        "",
        "# Portal Super Admin (OpenSim PrincipalID).",
        f"ADMIN_UUID={answers.admin_uuid}",
    ]
    if answers.portal_host:
        lines += [
            "",
            "# Hint for the setup wizard's grid identity step; the real values live in",
            "# System Settings once saved.",
            f"OS_PARIAH_PORTAL_HOST={answers.portal_host}",
        ]
    return "\n".join(lines) + "\n"


def patch_vhost(text: str, host: str, cert: str = "", key: str = "") -> str:
    """Set server_name / redirect target / active certificate paths in the packaged vhost."""
    patched, n_names = re.subn(
        r"(?m)^(\s*server_name\s+)[^;]+;", rf"\g<1>{host};", text
    )
    patched = re.sub(
        r"(?m)^(\s*return 301 https://)[^$\s]+(\$request_uri;)",
        rf"\g<1>{host}\g<2>",
        patched,
    )
    if n_names == 0:
        raise BootstrapError("Could not find server_name in the nginx vhost to update.")
    if cert and key:
        patched, n_cert = re.subn(
            r"(?m)^(\s*ssl_certificate\s+)[^;\s]+;", rf"\g<1>{cert};", patched
        )
        patched, n_key = re.subn(
            r"(?m)^(\s*ssl_certificate_key\s+)[^;\s]+;", rf"\g<1>{key};", patched
        )
        if n_cert == 0 or n_key == 0:
            raise BootstrapError(
                "Could not find ssl_certificate lines in the nginx vhost."
            )
    return patched


# ------------------------------------------------------------------------- plan


@dataclass
class Action:
    kind: str  # sql | check | file | nginx | command
    summary: str
    detail: dict = field(default_factory=dict)


def _q(ident: str) -> str:
    if not _IDENT_RE.match(ident):
        raise BootstrapError(f"Unsafe identifier {ident!r}")
    return f"`{ident}`"


def portal_sql(answers: Answers, instance) -> list[tuple[str, tuple]]:
    user = f"'{instance.db_user}'@'localhost'"
    db = _q(instance.db_name)
    return [
        (
            f"CREATE DATABASE IF NOT EXISTS {db} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
            (),
        ),
        (
            f"CREATE USER IF NOT EXISTS {user} IDENTIFIED BY %s",
            (answers.portal_db_password,),
        ),
        (f"ALTER USER {user} IDENTIFIED BY %s", (answers.portal_db_password,)),
        (f"GRANT ALL PRIVILEGES ON {db}.* TO {user}", ()),
    ]


def robust_grant_sql(answers: Answers) -> tuple[str, tuple]:
    """The ONLY statement bootstrap ever runs that touches the grid database: SELECT."""
    return (
        f"GRANT SELECT ON {_q(answers.robust_db_name)}.* TO "
        f"'{answers.robust_ro_user}'@'localhost'",
        (),
    )


def build_plan(answers: Answers, instance) -> list[Action]:
    actions = [
        Action(
            "sql",
            f"Create portal database {instance.db_name} and account "
            f"{instance.db_user}@localhost (ALL on that database only)",
            {"statements": [s for s, _ in portal_sql(answers, instance)]},
        ),
        Action(
            "check",
            f"Verify the existing grid database {answers.robust_db_name} is present "
            "and looks like Robust (UserAccounts table). Read-only.",
        ),
        Action(
            "sql",
            f"Create read-only account {answers.robust_ro_user}@localhost if missing and "
            f"grant SELECT on {answers.robust_db_name}.* (nothing else)",
            {"statements": [robust_grant_sql(answers)[0], "FLUSH PRIVILEGES"]},
        ),
        Action(
            "file",
            f"Write {instance.conf_path} (0640 os-pariah:opensim)",
            {
                "path": instance.conf_path,
                "preview": render_conf(answers, instance, redact=True),
            },
        ),
    ]
    if answers.portal_host:
        actions.append(
            Action(
                "nginx",
                f"Set nginx server_name to {answers.portal_host}"
                + (" and certificate paths" if answers.tls_cert else "")
                + f" in {instance.vhost_path}; nginx -t; reload",
            )
        )
    actions += [
        Action(
            "file",
            f"Write one-time setup token to {instance.setup_token_path} (0600)",
            {"path": instance.setup_token_path},
        ),
        Action("command", f"systemctl enable --now {instance.unit_name}"),
    ]
    return actions


# -------------------------------------------------------------------- execution


class Host:
    """Real system access. Tests substitute a fake with the same methods."""

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def write_file(
        self, path: str, content: str, mode: int, owner: str, group: str
    ) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.unlink(missing_ok=True)
        # Created 0600 and never wider while it holds secrets; the final mode is
        # applied (after chown) just before the atomic rename.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        try:
            shutil.chown(tmp, user=owner, group=group)
            os.chmod(tmp, mode)
        except (LookupError, PermissionError) as exc:
            tmp.unlink(missing_ok=True)
            raise BootstrapError(
                f"Cannot set owner {owner}:{group} on {path} ({exc}). "
                "Is the os-pariah RPM installed?"
            ) from exc
        tmp.replace(target)

    def copy_backup(self, path: str, suffix: str) -> str:
        dest = f"{path}.{suffix}"
        shutil.copy2(path, dest)
        return dest

    def run(self, cmd: list[str]) -> tuple[int, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def admin_connection(self, answers: Answers):
        import pymysql

        kwargs = {
            "user": answers.db_admin_user,
            "password": answers.db_admin_password or None,
            "charset": "utf8mb4",
        }
        if answers.db_admin_password == "" and os.path.exists(answers.db_socket):
            kwargs["unix_socket"] = answers.db_socket
        else:
            kwargs["host"] = answers.db_host
        return pymysql.connect(**kwargs)

    def user_connection(self, host: str, user: str, password: str, database: str):
        import pymysql

        return pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
        )


def _is_bootstrapped(host: Host, instance) -> bool:
    if not host.exists(instance.conf_path):
        return False
    for line in host.read_text(instance.conf_path).splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "OS_PARIAH_DB_PASS":
            return value.strip() not in ("", PLACEHOLDER_DB_PASS)
    return False


def preflight(answers: Answers, instance, host: Host, *, dry_run: bool) -> None:
    if not dry_run and not host.is_root():
        raise BootstrapError(
            "Run os-pariah-bootstrap as root (sudo os-pariah-bootstrap)."
        )
    if _is_bootstrapped(host, instance) and not answers.force:
        raise BootstrapError(
            f"{instance.conf_path} already holds bootstrapped credentials. Bootstrap is a "
            "root-once step; use --force to redo it (the old conf is kept as a backup and "
            "the portal DB password is rotated)."
        )
    if answers.tls_cert and not dry_run:
        for path in (answers.tls_cert, answers.tls_key):
            if not host.exists(path):
                raise BootstrapError(f"TLS file not found: {path}")


def execute(answers: Answers, instance, host: Host, log) -> dict:
    """Run the plan. Order matters: nothing is written to disk until the DB steps succeed."""
    preflight(answers, instance, host, dry_run=False)
    token = secrets.token_urlsafe(32)

    log("Connecting to MariaDB as an administrator...")
    try:
        admin = host.admin_connection(answers)
    except Exception as exc:  # noqa: BLE001
        raise BootstrapError(
            f"Cannot connect to MariaDB as {answers.db_admin_user}: {exc}. As root, "
            "unix-socket auth normally works; otherwise pass db_admin_password."
        ) from exc

    try:
        with admin.cursor() as cursor:
            # 1. Grid database must already exist and look like Robust. Read-only checks.
            cursor.execute(
                "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                (answers.robust_db_name,),
            )
            if not cursor.fetchone():
                raise BootstrapError(
                    f"The grid database {answers.robust_db_name!r} does not exist. "
                    "OS-Pariah reads an existing grid; set it up first (or pass "
                    "robust_db_name)."
                )
            cursor.execute(
                "SELECT 1 FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'UserAccounts'",
                (answers.robust_db_name,),
            )
            if not cursor.fetchone():
                raise BootstrapError(
                    f"{answers.robust_db_name!r} has no UserAccounts table; it does not "
                    "look like an OpenSim Robust database."
                )

            # 2. The read-only account: never rotate an existing account's password.
            cursor.execute(
                "SELECT 1 FROM mysql.user WHERE User = %s AND Host = 'localhost'",
                (answers.robust_ro_user,),
            )
            ro_exists = bool(cursor.fetchone())
            if ro_exists and not answers.robust_ro_password_supplied:
                raise BootstrapError(
                    f"MariaDB account {answers.robust_ro_user}@localhost already exists. "
                    "Bootstrap will not change its password: supply it as "
                    "robust_ro_password, or choose another robust_ro_user."
                )

            # 3. Portal database + account.
            for statement, params in portal_sql(answers, instance):
                cursor.execute(statement, params)

            # 4. Grid access: create if needed, then SELECT only.
            if not ro_exists:
                cursor.execute(
                    f"CREATE USER '{answers.robust_ro_user}'@'localhost' IDENTIFIED BY %s",
                    (answers.robust_ro_password,),
                )
            statement, params = robust_grant_sql(answers)
            cursor.execute(statement, params)
            cursor.execute("FLUSH PRIVILEGES")
        admin.commit()
    finally:
        admin.close()

    log("Verifying the new accounts...")
    for label, args in (
        (
            "portal account",
            (
                answers.db_host,
                instance.db_user,
                answers.portal_db_password,
                instance.db_name,
            ),
        ),
        (
            "read-only grid account",
            (
                answers.robust_db_host,
                answers.robust_ro_user,
                answers.robust_ro_password,
                answers.robust_db_name,
            ),
        ),
    ):
        try:
            conn = host.user_connection(*args)
            if "grid" in label:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM UserAccounts LIMIT 1")
            conn.close()
        except Exception as exc:  # noqa: BLE001
            raise BootstrapError(
                f"The {label} could not connect after creation: {exc}"
            ) from exc

    # Files only after the database side verified.
    backup = None
    if host.exists(instance.conf_path):
        backup = host.copy_backup(instance.conf_path, f"bak.{int(time.time())}")
        log(f"Kept the previous conf as {backup}")
    host.write_file(
        instance.conf_path,
        render_conf(answers, instance),
        0o640,
        "os-pariah",
        "opensim",
    )
    log(f"Wrote {instance.conf_path}")

    if answers.portal_host:
        _configure_nginx(answers, instance, host, log)

    host.write_file(
        instance.setup_token_path, token + "\n", 0o600, "os-pariah", "opensim"
    )
    log(f"Wrote setup token to {instance.setup_token_path}")

    code, out = host.run(["systemctl", "enable", "--now", instance.unit_name])
    if code != 0:
        raise BootstrapError(
            f"systemctl enable --now {instance.unit_name} failed: {out}\n"
            f"Check: journalctl -u {instance.unit_name} -n 100"
        )
    if answers.force:
        # Already-running service must pick up the rewritten conf.
        code, out = host.run(["systemctl", "restart", instance.unit_name])
        if code != 0:
            raise BootstrapError(
                f"systemctl restart {instance.unit_name} failed: {out}"
            )
    log(f"Started {instance.unit_name}")

    url_host = answers.portal_host or "<your-portal-host>"
    return {
        "setup_url": f"https://{url_host}/setup/unlock",
        "portal_host": answers.portal_host,
        "setup_token": token,
        "conf_path": instance.conf_path,
        "conf_backup": backup,
    }


def _configure_nginx(answers: Answers, instance, host: Host, log) -> None:
    if not host.exists(instance.vhost_path):
        raise BootstrapError(f"nginx vhost not found: {instance.vhost_path}")
    original = host.read_text(instance.vhost_path)
    patched = patch_vhost(
        original, answers.portal_host, answers.tls_cert, answers.tls_key
    )
    if patched == original:
        log("nginx vhost already up to date.")
        return
    backup = host.copy_backup(instance.vhost_path, f"bak.{int(time.time())}")
    host.write_file(instance.vhost_path, patched, 0o644, "root", "root")
    code, out = host.run(["nginx", "-t"])
    if code != 0:
        host.write_file(instance.vhost_path, original, 0o644, "root", "root")
        raise BootstrapError(
            f"nginx rejected the updated vhost ({out}); restored {instance.vhost_path} "
            f"(backup at {backup}). The database and conf steps already completed."
        )
    code, out = host.run(["systemctl", "reload", "nginx.service"])
    if code != 0:
        raise BootstrapError(f"nginx reload failed: {out}")
    log(f"Updated nginx ({instance.vhost_path}) and reloaded it.")


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="os-pariah-bootstrap",
        description="Root-once first-boot setup for OS-Pariah (never modifies OpenSim).",
    )
    p.add_argument(
        "--instance", default=None, help="Instance id (only 'default' exists today)."
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Never prompt; fail if answers are missing.",
    )
    p.add_argument(
        "--answers", metavar="FILE", help="JSON answers file (answers_version 1)."
    )
    p.add_argument(
        "--json", action="store_true", dest="as_json", help="Print a JSON result."
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Show the plan; change nothing."
    )
    p.add_argument(
        "--force", action="store_true", help="Redo an already bootstrapped install."
    )
    p.add_argument("--admin-uuid", help="OpenSim PrincipalID that becomes Super Admin.")
    p.add_argument("--portal-host", help="Public hostname, e.g. portal.example.com.")
    p.add_argument("--robust-db-name", help="Existing grid database (default: robust).")
    p.add_argument(
        "--robust-ro-user", help="Read-only account name (default: robust_ro)."
    )
    p.add_argument("--tls-cert", help="Existing certificate (fullchain) path.")
    p.add_argument("--tls-key", help="Existing certificate key path.")
    p.add_argument(
        "--db-socket", help="MariaDB socket (default: /run/mysql/mysql.sock)."
    )
    p.add_argument(
        "--new-token",
        action="store_true",
        help="Only write a fresh one-time setup token (lost token recovery); change nothing else.",
    )
    return p


def collect_answers(args, *, interactive: bool, prompt=input) -> Answers:
    raw: dict = {}
    if args.answers:
        raw.update(load_answers_file(args.answers))
    for flag, key in (
        ("admin_uuid", "admin_uuid"),
        ("portal_host", "portal_host"),
        ("robust_db_name", "robust_db_name"),
        ("robust_ro_user", "robust_ro_user"),
        ("tls_cert", "tls_cert"),
        ("tls_key", "tls_key"),
        ("db_socket", "db_socket"),
    ):
        value = getattr(args, flag, None)
        if value:
            raw[key] = value
    if args.force:
        raw["force"] = True

    if interactive:
        if not raw.get("admin_uuid"):
            raw["admin_uuid"] = prompt(
                "OpenSim PrincipalID (UUID) of your admin account: "
            ).strip()
        if "portal_host" not in raw:
            raw["portal_host"] = prompt(
                "Public portal hostname (e.g. portal.example.com), blank to skip: "
            ).strip()
        if "robust_db_name" not in raw:
            raw["robust_db_name"] = (
                prompt("Existing grid (Robust) database name [robust]: ").strip()
                or "robust"
            )
    return validate_answers(raw)


def main(argv=None, *, host: Host | None = None, prompt=input) -> int:
    args = build_parser().parse_args(argv)
    host = host or Host()
    quiet = args.as_json

    def log(message: str) -> None:
        print(message, file=sys.stderr if quiet else sys.stdout)

    try:
        try:
            instance = instance_mod.resolve(args.instance)
        except ReservedInstanceError as exc:
            raise BootstrapError(str(exc)) from exc

        if args.new_token:
            if not host.is_root():
                raise BootstrapError(
                    "Run as root (sudo os-pariah-bootstrap --new-token)."
                )
            token = secrets.token_urlsafe(32)
            host.write_file(
                instance.setup_token_path, token + "\n", 0o600, "os-pariah", "opensim"
            )
            if args.as_json:
                print(
                    json.dumps(
                        {"ok": True, "instance": instance.id, "setup_token": token}
                    )
                )
            else:
                print(f"New setup token written to {instance.setup_token_path}:")
                print(f"  {token}")
            return 0

        interactive = (
            (not args.non_interactive) and sys.stdin.isatty() and not args.dry_run
        )
        answers = collect_answers(args, interactive=interactive, prompt=prompt)
        if args.dry_run:
            preflight(answers, instance, host, dry_run=True)
            plan = build_plan(answers, instance)
            result = {
                "ok": True,
                "dry_run": True,
                "instance": instance.id,
                "actions": [dataclasses.asdict(a) for a in plan],
            }
            if args.as_json:
                print(json.dumps(result, indent=2))
            else:
                print(f"DRY RUN: nothing will be changed (instance: {instance.id}).\n")
                for i, action in enumerate(plan, 1):
                    print(f"{i}. [{action.kind}] {action.summary}")
                    for stmt in action.detail.get("statements", []):
                        print(f"     {stmt}")
                    if "preview" in action.detail:
                        for line in action.detail["preview"].splitlines():
                            print(f"     | {line}")
            return 0

        outcome = execute(answers, instance, host, log)
        result = {"ok": True, "dry_run": False, "instance": instance.id, **outcome}
        if args.as_json:
            print(json.dumps(result, indent=2))
        else:
            print()
            print("OS-Pariah bootstrap complete.")
            print(f"  Setup page : {outcome['setup_url']}")
            print(f"  Setup token: {outcome['setup_token']}")
            print("  (The token is also in " + instance.setup_token_path + ".)")
            print("Open the setup page, paste the token, and finish the wizard.")
        return 0
    except BootstrapError as exc:
        if args.as_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
