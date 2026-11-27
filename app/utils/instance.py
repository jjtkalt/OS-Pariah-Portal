"""Instance context: every name and path that would differ per grid on a shared host.

Today OS-Pariah supports exactly one instance (``default``) whose values are the
canonical layout in docs/NAMING.md. New wizard and bootstrap code must obtain paths and
names from here instead of hard-coding ``/etc/os-pariah``, ``os_pariah``, and friends,
so a future multi-grid design can change the mapping in one place.

Other instance ids are intentionally *reserved*: ``resolve("other")`` raises rather than
inventing a layout. See docs/INSTANCE-ASSUMPTIONS.md for the isolation checklist and the
list of legacy literals that still bypass this module.

This module is import-light (stdlib only) so CLI scripts and the Flask app can share it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_INSTANCE_ID = "default"
INSTANCE_ENV_VAR = "OS_PARIAH_INSTANCE"


class ReservedInstanceError(ValueError):
    """Raised for any instance id other than ``default`` (reserved for multi-grid)."""


@dataclass(frozen=True)
class Instance:
    id: str
    # Config / secrets (bootstrap-level facts live here; product settings live in the DB)
    conf_dir: str
    conf_path: str
    secrets_path: str
    setup_token_path: str
    # State and runtime
    state_dir: str
    uploads_dir: str
    run_dir: str
    socket_path: str
    log_dir: str
    # Database identity (portal DB; the Robust DB belongs to the grid, not to us)
    db_name: str
    db_user: str
    # Process / web front end
    unit_prefix: str
    unit_name: str
    vhost_path: str
    # Grid-adjacent shared directories
    texture_cache_dir: str
    backup_dir: str


def resolve(instance_id: str | None = None) -> Instance:
    """Return the Instance for ``instance_id`` (default: ``OS_PARIAH_INSTANCE`` or default)."""
    wanted = (
        instance_id
        if instance_id is not None
        else os.environ.get(INSTANCE_ENV_VAR) or DEFAULT_INSTANCE_ID
    ).strip()
    if wanted != DEFAULT_INSTANCE_ID:
        raise ReservedInstanceError(
            f"Instance {wanted!r} is reserved for future multi-grid support; "
            f"only {DEFAULT_INSTANCE_ID!r} is available."
        )
    return _default_instance()


def _default_instance() -> Instance:
    slug = "os-pariah"
    conf_dir = f"/etc/{slug}"
    state_dir = f"/var/lib/{slug}"
    run_dir = f"/run/{slug}"
    return Instance(
        id=DEFAULT_INSTANCE_ID,
        conf_dir=conf_dir,
        conf_path=f"{conf_dir}/{slug}.conf",
        secrets_path=f"{conf_dir}/secrets",
        setup_token_path=f"{conf_dir}/setup_token",
        state_dir=state_dir,
        uploads_dir=f"{state_dir}/uploads",
        run_dir=run_dir,
        socket_path=f"{run_dir}/{slug}.sock",
        log_dir=f"/var/log/{slug}",
        db_name="os_pariah",
        db_user=slug,
        unit_prefix=slug,
        unit_name=f"{slug}.service",
        vhost_path=f"/etc/nginx/vhosts.d/{slug}.conf",
        texture_cache_dir=f"/home/opensim/FSAssets/{slug}-cache",
        backup_dir="/home/opensim/Backups/portal",
    )


def current() -> Instance:
    """The instance selected by the environment (always ``default`` today)."""
    return resolve()
