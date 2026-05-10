#!/usr/bin/env python3
"""
Sync Host-ID bans to firewalld direct rules.

Inbound TCP to the grid login port (Robust public port) is inspected with the
iptables string/Boyer–Moore match so Login/Gatekeeper payloads containing a
banned Id0 (Host ID) are dropped. IP-based banning via ipset is not used.

Requires root / sudo (see packaging/pariah_worker.sudo).
"""
import os
import subprocess
import sys

from pariah_env import (
    configure_sync_logging,
    get_dynamic_config_for_scripts,
    get_pariah_db_connection,
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


def sync_firewall(logger):
    logger.info("Starting Pariah firewall synchronization (Host ID rules)...")
    conn = get_pariah_db_connection()
    try:
        login_port = str(
            get_dynamic_config_for_scripts(conn, "robust_public_port", default="8002")
        ).strip()
        if not login_port:
            login_port = "8002"

        with conn.cursor() as cursor:
            cursor.execute("SELECT hostid FROM bans_host_id")
            banned_hosts = set(row["hostid"] for row in cursor.fetchall())

        logger.info(
            "Using Robust public port %s from portal settings for HostID rules.",
            login_port,
        )
        logger.info("Syncing %s Host ID direct rules...", len(banned_hosts))

        for host in banned_hosts:
            rule_args = [
                "ipv4",
                "filter",
                "INPUT",
                "0",
                "-p",
                "tcp",
                "--dport",
                login_port,
                "-m",
                "string",
                "--algo",
                "bm",
                "--string",
                host,
                "-j",
                "DROP",
            ]
            run_cmd(
                logger,
                ["firewall-cmd", "--permanent", "--direct", "--remove-rule"]
                + rule_args,
            )
            run_cmd(
                logger,
                ["firewall-cmd", "--permanent", "--direct", "--add-rule"] + rule_args,
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
