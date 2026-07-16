#!/usr/bin/env python3
import os
import re
import subprocess
import sys

from pariah_env import (
    configure_sync_logging,
    get_dynamic_config_for_scripts,
    get_pariah_db_connection,
    load_pariah_dotenv,
)

# Full unit filename: templated (robust@main.service) or standalone (robust.service).
_SYSTEMD_UNIT_SAFE = re.compile(r"^[A-Za-z0-9:@._-]+\.service$")


def restart_robust_systemd(logger, unit: str) -> None:
    """
    Restart the configured systemd unit after the MAC list is written (templated or standalone).
    Runs as root when invoked via sudo from the portal; uses /bin/systemctl per packaging sudoers.
    """
    unit = (unit or "").strip()
    if not unit or unit.lower() == "none":
        unit = "robust@main.service"
    if not _SYSTEMD_UNIT_SAFE.match(unit):
        raise ValueError(
            f"Invalid robust_systemd_service {unit!r}; "
            "use a full unit name such as robust@main.service or robust.service."
        )

    logger.info("Restarting %s...", unit)
    r = subprocess.run(
        ["/bin/systemctl", "restart", unit],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(
            f"systemctl restart failed ({r.returncode}) for {unit}"
            + (f": {err}" if err else "")
        )
    logger.info("%s restarted successfully.", unit)


def sync_macs(logger):
    logger.info("Starting Robust MAC synchronization...")
    load_pariah_dotenv()
    conn = get_pariah_db_connection()
    try:
        raw_path = get_dynamic_config_for_scripts(conn, "robust_main_ini_path")
        robust_conf_path = str(raw_path).strip() if raw_path is not None else ""
        if not robust_conf_path or robust_conf_path.lower() == "none":
            raise ValueError(
                "robust_main_ini_path is not set in Portal Settings "
                "(System & Backend — Robust main.ini Path)."
            )

        if not os.path.exists(robust_conf_path):
            logger.error("Robust configuration file not found at %s", robust_conf_path)
            raise FileNotFoundError(robust_conf_path)

        raw_unit = get_dynamic_config_for_scripts(conn, "robust_systemd_service")
        systemd_unit = (
            str(raw_unit).strip() if raw_unit is not None else "robust@main.service"
        )
        if not systemd_unit or systemd_unit.lower() == "none":
            systemd_unit = "robust@main.service"

        with conn.cursor() as cursor:
            cursor.execute("SELECT mac FROM bans_mac")
            macs = [row["mac"] for row in cursor.fetchall()]
    finally:
        conn.close()

    mac_string = " ".join(macs)
    logger.info("Syncing %s MAC addresses to %s...", len(macs), robust_conf_path)

    with open(robust_conf_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    new_lines = []
    in_target_section = False
    replaced_in_section = False
    target_sections = ["GatekeeperService", "LoginService"]

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target_section and not replaced_in_section:
                new_lines.append(f'    DeniedMacs = "{mac_string}"\n')

            section_name = stripped[1:-1]
            if section_name in target_sections:
                in_target_section = True
                replaced_in_section = False
            else:
                in_target_section = False

        elif in_target_section and stripped.startswith("DeniedMacs"):
            indent = line[: len(line) - len(line.lstrip())]
            line = f'{indent}DeniedMacs = "{mac_string}"\n'
            replaced_in_section = True

        new_lines.append(line)

    if in_target_section and not replaced_in_section:
        new_lines.append(f'    DeniedMacs = "{mac_string}"\n')

    with open(robust_conf_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    logger.info("MAC list written to %s.", robust_conf_path)

    if os.name != "nt":
        restart_robust_systemd(logger, systemd_unit)
    else:
        logger.info(
            "Skipping systemctl restart on this platform; restart Robust manually if needed."
        )


if __name__ == "__main__":
    log = configure_sync_logging("sync_robust")
    try:
        if os.name != "nt" and os.geteuid() != 0:
            log.error("This script must be run as root.")
            sys.exit(1)
        sync_macs(log)
    except Exception:
        log.exception("sync_robust failed")
        sys.exit(1)
