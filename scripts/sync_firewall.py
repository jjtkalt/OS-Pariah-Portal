#!/usr/bin/env python3
"""
Sync Host-ID bans to firewalld direct rules.

Inbound TCP to the grid login port (Robust public port) is inspected with the
iptables string/Boyer–Moore match so Login/Gatekeeper payloads containing a
banned Id0 (Host ID) are dropped. IP-based banning via ipset is not used.

Requires root / sudo (see packaging/os-pariah-worker.sudo).
"""

import os
import shlex
import subprocess
import sys

from os_pariah_env import (
    configure_sync_logging,
    get_app_db_connection,
    get_dynamic_config_for_scripts,
)


def run_cmd(logger, cmd_list):
    """Run a firewall-cmd (or other) command and log failures."""
    r = subprocess.run(cmd_list, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        logger.error(
            "Command failed (exit %s): %s%s",
            r.returncode,
            " ".join(cmd_list),
            (" — " + err) if err else "",
        )


def build_rule_args(login_port, host):
    """Argument list (after --add-rule/--remove-rule) for one Host-ID DROP rule."""
    return [
        "ipv4",
        "filter",
        "INPUT",
        "0",
        "-p",
        "tcp",
        "--dport",
        str(login_port),
        "-m",
        "string",
        "--algo",
        "bm",
        "--string",
        host,
        "-j",
        "DROP",
    ]


def parse_host_id_rule(line):
    """Return ``(rule_args, port, host)`` if *line* is one of our Host-ID DROP rules.

    Matches the exact shape produced by :func:`build_rule_args`; anything else
    (other direct rules an admin added) returns ``None`` and is left untouched.
    """
    try:
        tokens = shlex.split(line.strip())
    except ValueError:
        return None
    if len(tokens) != 16:
        return None
    if tokens[:3] != ["ipv4", "filter", "INPUT"] or tokens[4:6] != ["-p", "tcp"]:
        return None
    if tokens[6] != "--dport" or tokens[8:12] != ["-m", "string", "--algo", "bm"]:
        return None
    if tokens[12] != "--string" or tokens[14:] != ["-j", "DROP"]:
        return None
    return tokens, tokens[7], tokens[13]


def get_existing_host_id_rules(logger):
    """Parse permanent direct rules into ``{(port, host): rule_args}`` for our pattern."""
    r = subprocess.run(
        ["firewall-cmd", "--permanent", "--direct", "--get-all-rules"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        logger.error(
            "Could not list existing direct rules (exit %s)%s",
            r.returncode,
            (" — " + err) if err else "",
        )
        return {}
    existing = {}
    for line in (r.stdout or "").splitlines():
        parsed = parse_host_id_rule(line)
        if parsed:
            args, port, host = parsed
            existing[(port, host)] = args
    return existing


def sync_firewall(logger):
    logger.info("Starting OS-Pariah firewall synchronization (Host ID rules)...")
    conn = get_app_db_connection()
    try:
        login_port = str(
            get_dynamic_config_for_scripts(conn, "robust_public_port", default="8002")
        ).strip()
        if not login_port:
            login_port = "8002"

        with conn.cursor() as cursor:
            cursor.execute("SELECT hostid FROM bans_host_id")
            banned_hosts = {row["hostid"] for row in cursor.fetchall()}

        logger.info(
            "Using Robust public port %s from portal settings for HostID rules.",
            login_port,
        )
        logger.info("Syncing %s Host ID direct rules...", len(banned_hosts))

        existing = get_existing_host_id_rules(logger)
        wanted = {(login_port, host) for host in banned_hosts}

        # Remove rules for hosts that are no longer banned (or on a stale port).
        stale = [key for key in existing if key not in wanted]
        logger.info("Removing %s stale Host ID direct rules...", len(stale))
        for key in stale:
            run_cmd(
                logger,
                ["firewall-cmd", "--permanent", "--direct", "--remove-rule"]
                + existing[key],
            )

        # Add rules that are missing; leave already-present rules alone.
        missing = sorted(key for key in wanted if key not in existing)
        logger.info("Adding %s new Host ID direct rules...", len(missing))
        for port, host in missing:
            run_cmd(
                logger,
                ["firewall-cmd", "--permanent", "--direct", "--add-rule"]
                + build_rule_args(port, host),
            )

        logger.info("Reloading firewalld to apply changes...")
        run_cmd(logger, ["firewall-cmd", "--reload"])

        logger.info("Firewall synchronization complete.")

    finally:
        conn.close()


if __name__ == "__main__":
    log = configure_sync_logging("sync_firewall")
    try:
        if os.name != "nt" and os.geteuid() != 0:
            log.error("This script must be run as root.")
            sys.exit(1)
        sync_firewall(log)
    except Exception:
        log.exception("sync_firewall failed")
        sys.exit(1)
