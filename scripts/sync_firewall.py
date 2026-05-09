#!/usr/bin/env python3
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
    logger.info("Starting Pariah firewall synchronization...")
    conn = get_pariah_db_connection()
    try:
        login_port = str(
            get_dynamic_config_for_scripts(conn, "robust_public_port", default="8002")
        ).strip()
        if not login_port:
            login_port = "8002"

        with conn.cursor() as cursor:
            cursor.execute("SELECT ip FROM bans_ip")
            banned_ips = set(row["ip"] for row in cursor.fetchall())

            cursor.execute("SELECT hostid FROM bans_host_id")
            banned_hosts = set(row["hostid"] for row in cursor.fetchall())

        logger.info(
            "Using Robust public port %s from portal settings for HostID rules.",
            login_port,
        )
        logger.info("Syncing %s IP addresses (ipset)...", len(banned_ips))
        run_cmd(
            logger,
            [
                "firewall-cmd",
                "--permanent",
                "--ipset=pariah_banned_ips",
                "--remove-entries-from-file=/dev/null",
            ],
        )
        run_cmd(logger, ["firewall-cmd", "--ipset=pariah_banned_ips", "--flush"])

        for ip in banned_ips:
            run_cmd(
                logger,
                [
                    "firewall-cmd",
                    "--permanent",
                    "--ipset=pariah_banned_ips",
                    "--add-entry",
                    ip,
                ],
            )
            run_cmd(
                logger,
                ["firewall-cmd", "--ipset=pariah_banned_ips", "--add-entry", ip],
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
