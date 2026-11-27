from pathlib import Path

import pytest

from app.utils import instance as inst

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_default_instance_is_canonical_layout():
    i = inst.resolve()
    assert i.id == "default"
    assert i.conf_path == "/etc/os-pariah/os-pariah.conf"
    assert i.secrets_path == "/etc/os-pariah/secrets"
    assert i.setup_token_path == "/etc/os-pariah/setup_token"
    assert i.state_dir == "/var/lib/os-pariah"
    assert i.uploads_dir == "/var/lib/os-pariah/uploads"
    assert i.socket_path == "/run/os-pariah/os-pariah.sock"
    assert i.unit_name == "os-pariah.service"
    assert i.db_name == "os_pariah"
    assert i.db_user == "os-pariah"


def test_default_instance_matches_packaging_and_naming_doc():
    """Pin the resolver to what the RPM, unit, and vhost actually ship."""
    i = inst.resolve()
    spec = _read("packaging/os-pariah.spec")
    unit = _read("packaging/os-pariah.service")
    vhost = _read("packaging/os-pariah.conf")
    naming = _read("docs/NAMING.md")

    assert i.conf_path in spec
    assert f"EnvironmentFile={i.conf_path}" in unit
    assert f"EnvironmentFile=-{i.secrets_path}" in unit
    assert f"--bind unix:{i.socket_path}" in unit
    assert f"unix:{i.socket_path}" in vhost
    assert f"RuntimeDirectory={i.unit_prefix}" in unit
    assert f"{i.state_dir}/uploads/tickets" in spec
    assert i.texture_cache_dir + "/" in spec
    assert i.backup_dir + "/" in spec
    assert i.log_dir + "/" in spec
    assert Path(i.vhost_path).name in spec
    for value in (i.conf_path, i.secrets_path, i.socket_path, i.vhost_path):
        assert value in naming
    assert i.db_name in naming


def test_instance_is_frozen():
    i = inst.resolve()
    with pytest.raises(AttributeError):
        i.conf_path = "/tmp/elsewhere"  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["grid2", "Default", "", " other "])
def test_non_default_instance_is_reserved(bad):
    # An explicit empty string is not "unset": it must not silently select a layout.
    with pytest.raises(inst.ReservedInstanceError):
        inst.resolve(bad)


def test_env_var_selects_instance(monkeypatch):
    monkeypatch.setenv(inst.INSTANCE_ENV_VAR, "default")
    assert inst.current().id == "default"
    monkeypatch.setenv(inst.INSTANCE_ENV_VAR, "grid2")
    with pytest.raises(inst.ReservedInstanceError):
        inst.current()
    monkeypatch.delenv(inst.INSTANCE_ENV_VAR)
    assert inst.current().id == "default"
