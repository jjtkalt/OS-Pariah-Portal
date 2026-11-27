"""Lightweight checks on packaging/*.service, timers, sudoers, and ops scripts.

No database or Flask app needed; these guard unit-dependency and privilege invariants.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
SCRIPTS = ROOT / "scripts"

TIMERS = (
    "os-pariah-worker-log.timer",
    "os-pariah-worker-iar.timer",
    "os-pariah-worker-calendar.timer",
    "os-pariah-cloudflare-ip.timer",
    "os-pariah-backup.timer",
)


def _unit_values(path: Path, key: str) -> list[str]:
    """All whitespace-separated values for *key* across the [Unit] section lines."""
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = re.match(rf"^{key}=(.*)$", stripped)
        if match:
            values.extend(match.group(1).split())
    return values


def test_master_unit_wants_iar_worker_but_requires_timers():
    unit = PACKAGING / "os-pariah.service"
    requires = _unit_values(unit, "Requires")
    wants = _unit_values(unit, "Wants")

    assert "os-pariah-worker-iar.service" in wants
    assert "os-pariah-worker-iar.service" not in requires
    for timer in TIMERS:
        assert timer in requires, f"{timer} must stay on Requires= of os-pariah.service"


def test_iar_worker_does_not_require_portal():
    requires = _unit_values(PACKAGING / "os-pariah-worker-iar.service", "Requires")
    assert "os-pariah.service" not in requires


def test_sync_requirements_runs_as_root_prestart():
    text = (PACKAGING / "os-pariah.service").read_text(encoding="utf-8")
    assert re.search(r"^ExecStartPre=\+.*sync_requirements\.py", text, re.M)


def test_calendar_timer_fires_every_minute():
    text = (PACKAGING / "os-pariah-worker-calendar.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=1min" in text


def test_sudoers_only_allows_starting_iar_worker():
    text = (PACKAGING / "os-pariah-worker.sudo").read_text(encoding="utf-8")
    control = next(
        line
        for line in text.splitlines()
        if line.startswith("Cmnd_Alias OS_PARIAH_CONTROL")
    )
    assert "start os-pariah-worker-iar.service" in control
    assert "stop" not in control
    assert "restart" not in control


def test_spec_locks_down_code_tree_and_sudoers():
    spec = (PACKAGING / "os-pariah.spec").read_text(encoding="utf-8")
    assert "chown -R root:root /opt/os-pariah" in spec
    assert "chown -R os-pariah:os-pariah /opt/os-pariah\n" not in spec
    # Satisfy rpm auto-Requires from %attr ownership; create accounts in %pre.
    assert "Requires(pre):  shadow" in spec
    assert "Provides:       group(opensim)" in spec
    assert "Provides:       user(os-pariah)" in spec
    assert "Provides:       group(os-pariah)" in spec
    assert "groupadd -r opensim" in spec
    # No ELF to strip — skip empty debuginfo/debugsource on Leap.
    assert "%global debug_package %{nil}" in spec
    assert "%attr(0440, root, root) /etc/sudoers.d/os-pariah-worker" in spec
    assert "%dir %attr(0750, os-pariah, opensim) /home/opensim/Backups/portal/" in spec
    assert "/var/lib/os-pariah/uploads/tickets" in spec
    assert "app/static/uploads" not in spec
    assert "pip install --require-hashes -r /opt/os-pariah/requirements.txt" in spec


def test_sync_requirements_requires_hashes():
    text = (SCRIPTS / "sync_requirements.py").read_text(encoding="utf-8")
    assert "--require-hashes" in text


def test_nginx_conf_has_no_duplicate_cloudflare_include():
    conf = (PACKAGING / "os-pariah.conf").read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*include\s+/etc/nginx/conf\.d/os-pariah-cloudflare-ip\.conf", conf, re.M
    )
    assert "limit_req_status 429;" in conf
    assert "Content-Security-Policy" in conf
    assert "object-src 'none'" in conf
    assert "Permissions-Policy" in conf
    assert "max-age=31536000" in conf
    assert "X-Frame-Options" in conf


def test_canonical_os_pariah_naming_in_packaging():
    spec = (PACKAGING / "os-pariah.spec").read_text(encoding="utf-8")
    assert re.search(r"^Name:\s+os-pariah\s*$", spec, re.M)
    assert "useradd -r -g os-pariah" in spec
    assert "os-pariah-bootstrap" in spec
    assert "/etc/os-pariah/os-pariah.conf" in spec

    unit = (PACKAGING / "os-pariah.service").read_text(encoding="utf-8")
    assert re.search(r"^User=os-pariah$", unit, re.M)
    assert re.search(r"^Group=nginx$", unit, re.M)
    assert "--bind unix:/run/os-pariah/os-pariah.sock" in unit
    assert "EnvironmentFile=/etc/os-pariah/os-pariah.conf" in unit
    assert "EnvironmentFile=-/etc/os-pariah/secrets" in unit

    vhost = (PACKAGING / "os-pariah.conf").read_text(encoding="utf-8")
    assert "unix:/run/os-pariah/os-pariah.sock" in vhost
    assert "dummy-os-pariah.crt" in vhost

    for name in (
        "dummy-os-pariah.crt",
        "dummy-os-pariah.key",
        "os-pariah-cloudflare-ip.conf",
    ):
        assert (PACKAGING / name).is_file(), name


def test_packaging_has_no_legacy_pariah_names():
    legacy = re.compile(
        r"(?<![\w-])pariah(?:[-_.]|\.service|\.timer)|/opt/os_pariah|/etc/os_pariah"
        r"|/run/os_pariah|/var/log/os_pariah|pariah_worker|dummypariah|pariahcache"
    )
    for path in sorted(PACKAGING.glob("os-pariah*")) + sorted(
        PACKAGING.glob("dummy-os-pariah*")
    ):
        if path.suffix in (".crt", ".key", ".pub"):
            continue
        text = path.read_text(encoding="utf-8")
        assert not legacy.search(text), f"legacy pariah name in {path.name}"


def test_sync_firewall_parses_only_our_rules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import sync_firewall

    ours = (
        "ipv4 filter INPUT 0 -p tcp --dport 8002 -m string --algo bm "
        "--string abc123 -j DROP"
    )
    assert sync_firewall.parse_host_id_rule(ours) == (ours.split(), "8002", "abc123")
    assert sync_firewall.build_rule_args("8002", "abc123") == ours.split()

    assert (
        sync_firewall.parse_host_id_rule("ipv4 filter INPUT 0 -p tcp -j ACCEPT") is None
    )
    assert sync_firewall.parse_host_id_rule("") is None
    # unbalanced quote must not raise
    assert sync_firewall.parse_host_id_rule("ipv4 'filter") is None
    sys.modules.pop("sync_firewall", None)


def test_bootstrap_wrapper_is_packaged():
    spec = (PACKAGING / "os-pariah.spec").read_text(encoding="utf-8")
    assert "%{_sbindir}/os-pariah-bootstrap" in spec
    wrapper = (PACKAGING / "os-pariah-bootstrap").read_text(encoding="utf-8")
    assert wrapper.startswith("#!/bin/sh")
    assert "/opt/os-pariah/scripts/os_pariah_bootstrap.py" in wrapper
