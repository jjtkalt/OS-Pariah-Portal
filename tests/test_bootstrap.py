"""os-pariah-bootstrap: root-once CLI. Everything runs against a fake Host."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import os_pariah_bootstrap as boot

ADMIN = "11111111-2222-3333-4444-555555555555"
ROOT = Path(__file__).resolve().parent.parent
VHOST = (ROOT / "packaging" / "os-pariah.conf").read_text(encoding="utf-8")


class FakeAdminCursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.conn.executed.append((sql, tuple(params)))
        host = self.conn.host
        if "information_schema.SCHEMATA" in sql:
            self._row = (1,) if host.robust_db_exists else None
        elif "information_schema.TABLES" in sql:
            self._row = (1,) if host.user_accounts_exists else None
        elif "FROM mysql.user" in sql:
            self._row = (1,) if host.ro_user_exists else None
        else:
            self._row = None

    def fetchone(self):
        return self._row


class FakeAdminConn:
    def __init__(self, host):
        self.host = host
        self.executed = []
        self.closed = False

    def cursor(self):
        return FakeAdminCursor(self)

    def commit(self):
        pass

    def close(self):
        self.closed = True


class FakeHost:
    def __init__(self, *, root=True, files=None):
        self.root = root
        self.files = dict(files or {})
        self.written = {}
        self.commands = []
        self.robust_db_exists = True
        self.user_accounts_exists = True
        self.ro_user_exists = False
        self.admin = None
        self.nginx_ok = True
        self.verify_ok = True

    def is_root(self):
        return self.root

    def exists(self, path):
        return path in self.files or path in self.written

    def read_text(self, path):
        return self.written.get(path, self.files.get(path))

    def write_file(self, path, content, mode, owner, group):
        self.written[path] = content
        self.written[(path, "meta")] = (mode, owner, group)

    def copy_backup(self, path, suffix):
        dest = f"{path}.{suffix}"
        self.files[dest] = self.read_text(path)
        return dest

    def run(self, cmd):
        self.commands.append(list(cmd))
        if cmd[:2] == ["nginx", "-t"] and not self.nginx_ok:
            return 1, "bad config"
        return 0, ""

    def admin_connection(self, answers):
        self.admin = FakeAdminConn(self)
        return self.admin

    def user_connection(self, host, user, password, database):
        if not self.verify_ok:
            raise RuntimeError("access denied")
        return FakeAdminConn(self)


def _answers(**over):
    raw = {"admin_uuid": ADMIN, "portal_host": "portal.example.org"}
    raw.update(over)
    return boot.validate_answers(raw)


def _instance():
    return boot.instance_mod.resolve()


def _host(**kw):
    files = {_instance().vhost_path: VHOST}
    files.update(kw.pop("files", {}))
    return FakeHost(files=files, **kw)


def _run(argv, host=None):
    return boot.main(argv, host=host or _host())


# ----------------------------------------------------------------- answers file


def test_answers_file_must_declare_supported_version(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"admin_uuid": ADMIN}), encoding="utf-8")
    with pytest.raises(boot.BootstrapError, match="answers_version"):
        boot.load_answers_file(str(path))
    path.write_text(json.dumps({"answers_version": 99}), encoding="utf-8")
    with pytest.raises(boot.BootstrapError, match="Unsupported answers_version"):
        boot.load_answers_file(str(path))


def test_answers_file_rejects_unknown_keys(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps({"answers_version": 1, "admin_uuid": ADMIN, "mystery": 1}),
        encoding="utf-8",
    )
    with pytest.raises(boot.BootstrapError, match="mystery"):
        boot.load_answers_file(str(path))


def test_answers_file_roundtrip(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            {
                "answers_version": 1,
                "admin_uuid": ADMIN,
                "portal_host": "portal.example.org",
            }
        ),
        encoding="utf-8",
    )
    assert boot.load_answers_file(str(path))["admin_uuid"] == ADMIN


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"admin_uuid": "nope"}, "admin_uuid"),
        ({"db_host": "db.example.org"}, "must be local"),
        ({"robust_db_host": "10.0.0.5"}, "must be local"),
        ({"robust_db_name": "x; DROP DATABASE y"}, "robust_db_name"),
        ({"robust_ro_user": "a'b"}, "robust_ro_user"),
        ({"portal_db_password": "short"}, "portal_db_password"),
        ({"portal_host": "not a host"}, "portal_host"),
        ({"tls_cert": "/etc/c.pem"}, "both tls_cert and tls_key"),
        ({"tls_cert": "c.pem", "tls_key": "k.pem"}, "absolute"),
        ({"portal_host": "", "tls_cert": "/c", "tls_key": "/k"}, "portal_host"),
    ],
)
def test_validation_rejects_bad_input(over, needle):
    with pytest.raises(boot.BootstrapError, match=needle):
        _answers(**over)


def test_validation_generates_passwords_and_normalises():
    a = _answers(admin_uuid=ADMIN.upper(), portal_host="Portal.Example.ORG")
    assert a.admin_uuid == ADMIN
    assert a.portal_host == "portal.example.org"
    assert len(a.portal_db_password) >= 12 and len(a.robust_ro_password) >= 12
    assert a.portal_db_password != a.robust_ro_password
    assert not a.robust_ro_password_supplied


# --------------------------------------------------------------------- rendering


def test_conf_has_expected_keys_and_redaction():
    a = _answers()
    conf = boot.render_conf(a, _instance())
    assert "OS_PARIAH_INSTANCE=default" in conf
    assert "OS_PARIAH_DB_NAME=os_pariah" in conf
    assert f"OS_PARIAH_DB_PASS={a.portal_db_password}" in conf
    assert f"ADMIN_UUID={ADMIN}" in conf
    assert "OS_PARIAH_PORTAL_HOST=portal.example.org" in conf
    redacted = boot.render_conf(a, _instance(), redact=True)
    assert a.portal_db_password not in redacted
    assert a.robust_ro_password not in redacted


def test_patch_vhost_sets_names_redirect_and_certs():
    patched = boot.patch_vhost(VHOST, "p.example.org", "/c/full.pem", "/c/key.pem")
    assert "portal.example.com" not in patched
    assert "return 301 https://p.example.org$request_uri;" in patched
    assert re.search(r"ssl_certificate\s+/c/full\.pem;", patched)
    assert re.search(r"ssl_certificate_key\s+/c/key\.pem;", patched)


def test_patch_vhost_errors_without_server_name():
    with pytest.raises(boot.BootstrapError):
        boot.patch_vhost("server {}", "p.example.org")


# --------------------------------------------------------------- SQL safety rules


def test_grid_account_gets_select_only():
    statement, _ = boot.robust_grant_sql(_answers())
    assert statement.startswith("GRANT SELECT ON `robust`.* TO 'robust_ro'@'localhost'")
    assert "ALL" not in statement.upper().replace("SELECT", "")


def test_unsafe_identifiers_never_reach_sql():
    with pytest.raises(boot.BootstrapError):
        boot._q("robust`; DROP")


def test_plan_never_mentions_opensim_services_or_grid_writes():
    a = _answers()
    plan = boot.build_plan(a, _instance())
    text = json.dumps([boot.dataclasses.asdict(x) for x in plan]).lower()
    for needle in ("opensim.service", "robust.service", "opensim.ini", "robust.ini"):
        assert needle not in text
    # Grid database sees exactly one grant, and it is SELECT.
    grants = [
        s
        for x in plan
        for s in x.detail.get("statements", [])
        if "GRANT" in s and "robust" in s
    ]
    assert grants == ["GRANT SELECT ON `robust`.* TO 'robust_ro'@'localhost'"]


# ------------------------------------------------------------------------ dry run


def test_dry_run_changes_nothing_and_shows_plan(capsys):
    host = _host(root=False)  # root is not needed to preview
    code = _run(
        [
            "--dry-run",
            "--non-interactive",
            "--admin-uuid",
            ADMIN,
            "--portal-host",
            "portal.example.org",
        ],
        host,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "DRY RUN" in out
    assert "GRANT SELECT ON `robust`.*" in out
    assert "OS_PARIAH_DB_PASS=***" in out
    assert host.admin is None
    assert host.commands == []
    assert not [k for k in host.written if isinstance(k, str)]


def test_dry_run_json(capsys):
    code = _run(["--dry-run", "--json", "--non-interactive", "--admin-uuid", ADMIN])
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["dry_run"] is True and data["instance"] == "default"
    assert data["actions"]


def test_non_default_instance_is_rejected(capsys):
    code = _run(
        [
            "--instance",
            "second",
            "--dry-run",
            "--non-interactive",
            "--admin-uuid",
            ADMIN,
        ]
    )
    assert code == 1
    assert "second" in capsys.readouterr().err


def test_missing_admin_uuid_fails_when_non_interactive(capsys):
    assert _run(["--non-interactive", "--dry-run"]) == 1
    assert "admin_uuid" in capsys.readouterr().err


# ------------------------------------------------------------------------- execute


def _go(host, *extra):
    return _run(
        [
            "--non-interactive",
            "--json",
            "--admin-uuid",
            ADMIN,
            "--portal-host",
            "portal.example.org",
            *extra,
        ],
        host,
    )


def test_execute_happy_path(capsys):
    host = _host()
    assert _go(host) == 0
    result = json.loads(capsys.readouterr().out)
    inst = _instance()

    sql = [s for s, _ in host.admin.executed]
    assert any(s.startswith("CREATE DATABASE IF NOT EXISTS `os_pariah`") for s in sql)
    assert any("GRANT SELECT ON `robust`.*" in s for s in sql)
    assert not any("GRANT ALL" in s and "robust" in s for s in sql)
    # Never DROP, never touch other schemas.
    assert not any(s.upper().startswith(("DROP", "DELETE", "UPDATE")) for s in sql)

    conf = host.written[inst.conf_path]
    assert f"ADMIN_UUID={ADMIN}" in conf
    assert host.written[(inst.conf_path, "meta")] == (0o640, "os-pariah", "opensim")
    token = host.written[inst.setup_token_path].strip()
    assert token == result["setup_token"] and len(token) >= 32
    assert host.written[(inst.setup_token_path, "meta")][0] == 0o600

    assert "server_name portal.example.org;" in host.written[inst.vhost_path]
    assert ["nginx", "-t"] in host.commands
    assert ["systemctl", "enable", "--now", "os-pariah.service"] in host.commands
    assert result["setup_url"] == "https://portal.example.org/setup/unlock"


def test_execute_never_touches_opensim_units(capsys):
    host = _host()
    assert _go(host) == 0
    capsys.readouterr()
    for cmd in host.commands:
        assert cmd[0] in ("systemctl", "nginx")
        assert "opensim" not in " ".join(cmd).lower()
        assert "robust" not in " ".join(cmd).lower()
        assert cmd[:2] != ["systemctl", "restart"] or cmd[2] == "os-pariah.service"


def test_requires_root(capsys):
    host = _host(root=False)
    assert _go(host) == 1
    assert "root" in json.loads(capsys.readouterr().out)["error"]
    assert host.admin is None


def test_refuses_to_redo_bootstrapped_install_without_force(capsys):
    inst = _instance()
    host = _host(files={inst.conf_path: "OS_PARIAH_DB_PASS=RealSecretValue123\n"})
    assert _go(host) == 1
    assert "root-once" in json.loads(capsys.readouterr().out)["error"]
    assert host.admin is None


def test_force_redo_keeps_backup_and_restarts_service(capsys):
    inst = _instance()
    host = _host(files={inst.conf_path: "OS_PARIAH_DB_PASS=RealSecretValue123\n"})
    assert _go(host, "--force") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["conf_backup"]
    assert ["systemctl", "restart", "os-pariah.service"] in host.commands


def test_missing_grid_database_stops_before_any_write(capsys):
    host = _host()
    host.robust_db_exists = False
    assert _go(host) == 1
    assert "does not exist" in json.loads(capsys.readouterr().out)["error"]
    assert not [k for k in host.written if isinstance(k, str)]
    assert host.commands == []
    sql = [s for s, _ in host.admin.executed]
    assert not any(s.startswith(("CREATE", "GRANT", "ALTER")) for s in sql)


def test_non_robust_database_is_rejected(capsys):
    host = _host()
    host.user_accounts_exists = False
    assert _go(host) == 1
    assert "UserAccounts" in json.loads(capsys.readouterr().out)["error"]


def test_existing_ro_account_password_is_never_rotated(capsys):
    host = _host()
    host.ro_user_exists = True
    assert _go(host) == 1
    assert (
        "will not change its password" in json.loads(capsys.readouterr().out)["error"]
    )
    sql = [s for s, _ in host.admin.executed]
    assert not any(
        "robust_ro" in s and ("CREATE USER" in s or "ALTER USER" in s) for s in sql
    )


def test_existing_ro_account_is_reused_when_password_supplied(capsys, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(
        json.dumps({"answers_version": 1, "robust_ro_password": "ExistingRoPass-123"}),
        encoding="utf-8",
    )
    host = _host()
    host.ro_user_exists = True
    assert _go(host, "--answers", str(answers)) == 0
    sql = [s for s, _ in host.admin.executed]
    assert not any("CREATE USER 'robust_ro'" in s for s in sql)
    assert any("GRANT SELECT ON `robust`.*" in s for s in sql)


def test_verification_failure_leaves_no_files(capsys):
    host = _host()
    host.verify_ok = False
    assert _go(host) == 1
    assert "could not connect" in json.loads(capsys.readouterr().out)["error"]
    assert not [k for k in host.written if isinstance(k, str)]


def test_nginx_failure_restores_vhost(capsys):
    host = _host()
    host.nginx_ok = False
    inst = _instance()
    assert _go(host) == 1
    assert "nginx rejected" in json.loads(capsys.readouterr().out)["error"]
    assert host.written[inst.vhost_path] == VHOST


def test_new_token_only_writes_a_token(capsys):
    host = _host()
    assert _run(["--new-token", "--json"], host) == 0
    token = json.loads(capsys.readouterr().out)["setup_token"]
    inst = _instance()
    assert host.written[inst.setup_token_path].strip() == token
    assert host.admin is None and host.commands == []
    assert host.written[(inst.setup_token_path, "meta")][0] == 0o600


def test_new_token_requires_root(capsys):
    assert _run(["--new-token"], _host(root=False)) == 1


def test_real_host_write_file_is_never_wider_than_final_mode(tmp_path, monkeypatch):
    """Secrets files are created 0600 (no world-readable window) and renamed atomically."""
    import os
    import stat

    seen = {}
    real_chown = boot.shutil.chown

    def fake_chown(path, user=None, group=None):
        seen["mode_before_chown"] = stat.S_IMODE(os.stat(path).st_mode)

    monkeypatch.setattr(boot.shutil, "chown", fake_chown)
    target = tmp_path / "etc" / "os-pariah.conf"
    boot.Host().write_file(str(target), "SECRET=1\n", 0o640, "x", "y")
    monkeypatch.setattr(boot.shutil, "chown", real_chown)

    assert seen["mode_before_chown"] == 0o600
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert target.read_text() == "SECRET=1\n"
    assert not (tmp_path / "etc" / "os-pariah.conf.tmp").exists()
