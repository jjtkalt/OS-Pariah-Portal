#!/usr/bin/env python3
import os
import sys

from pariah_env import (
    configure_sync_logging,
    get_dynamic_config_for_scripts,
    get_pariah_db_connection,
    load_pariah_dotenv,
)


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

        with conn.cursor() as cursor:
            cursor.execute("SELECT mac FROM bans_mac")
            macs = [row["mac"] for row in cursor.fetchall()]
    finally:
        conn.close()

    mac_string = ",".join(macs)
    logger.info("Syncing %s MAC addresses to %s...", len(macs), robust_conf_path)

    with open(robust_conf_path, "r", encoding="utf-8", errors="replace") as f:
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

    logger.info(
        "MAC synchronization complete. (Restart Robust for MAC bans to take effect.)"
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
