"""scripts/migrate.py: setup_state bookkeeping, fresh-vs-upgraded detection, migration 013."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fake_setup_db import FakeConn, FakeCursor

from app.setup import state
from app.setup.steps import STEPS
from scripts import migrate

ROOT = Path(__file__).resolve().parent.parent


class MigrateCursor(FakeCursor):
    """Adds the raw statements migrate.py itself issues (tuple rows, like pymysql)."""

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        db = self.db
        if q.startswith("SELECT version FROM schema_versions"):
            self._rows = [(v,) for v in sorted(db.versions)]
        elif q.startswith("INSERT INTO schema_versions"):
            db.versions.add(params[0])
            self._rows = []
        elif "config_key = 'grid_provider'" in q:
            self._rows = []
        else:
            try:
                super().execute(sql, params)
            except AssertionError:
                # DDL and whole .sql migration scripts: pretend they ran.
                self._rows = []


class MigrateConn(FakeConn):
    def __init__(self, applied=()):
        super().__init__()
        self.versions = set(applied)

    def cursor(self, *args, **kwargs):
        return MigrateCursor(self)


@pytest.fixture
def run_migrate(monkeypatch):
    monkeypatch.setattr(migrate, "ensure_secret_key", lambda: None)
    monkeypatch.delenv("ADMIN_UUID", raising=False)

    def _run(conn, *, instance_env="default"):
        if instance_env is None:
            monkeypatch.delenv("OS_PARIAH_INSTANCE", raising=False)
        else:
            monkeypatch.setenv("OS_PARIAH_INSTANCE", instance_env)
        monkeypatch.setattr(migrate, "get_connection", lambda: conn)
        migrate.apply_migrations()
        return conn

    return _run


def test_bootstrap_managed_fresh_database_is_gated(run_migrate):
    conn = run_migrate(MigrateConn())
    assert migrate.FRESH_INSTALL_SENTINEL in conn.versions
    assert state.read_meta(conn)["origin"] == "fresh"
    assert state.first_boot_pending(conn)
    assert {s.id for s in STEPS} == set(state.read_steps(conn))


def test_fresh_database_without_bootstrap_marker_is_never_gated(run_migrate):
    conn = run_migrate(MigrateConn(), instance_env=None)
    assert state.read_meta(conn)["origin"] == "upgraded"
    assert not state.first_boot_pending(conn)
    assert all(r["status"] == "done" for r in state.read_steps(conn).values())


def test_existing_install_is_backfilled_and_not_gated(run_migrate):
    conn = run_migrate(MigrateConn(applied={"001_init.sql", "012_unify.sql"}))
    assert state.read_meta(conn)["origin"] == "upgraded"
    assert not state.first_boot_pending(conn)
    assert state.advisory_pending(conn, STEPS) == []


def test_interrupted_first_run_still_counts_as_fresh(run_migrate):
    conn = run_migrate(
        MigrateConn(applied={migrate.FRESH_INSTALL_SENTINEL, "001_init.sql"})
    )
    assert state.read_meta(conn)["origin"] == "fresh"


def test_second_run_keeps_progress(run_migrate):
    conn = run_migrate(MigrateConn())
    state.mark_step(conn, STEPS[0], state.STATUS_DONE)
    run_migrate(conn)
    assert state.read_meta(conn)["origin"] == "fresh"
    assert conn.step_status(STEPS[0].id) == "done"


def test_setup_state_problems_never_block_startup(capsys):
    class Broken:
        def cursor(self, *a, **k):
            raise RuntimeError("table missing")

    migrate.ensure_setup_state(Broken(), preexisting=False)  # must not raise
    assert "WARNING" in capsys.readouterr().out


def test_migration_013_pins_collation_and_shape():
    sql = (ROOT / "migrations" / "013_setup_state.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS `setup_state`" in sql
    assert "COLLATE=utf8mb4_unicode_ci" in sql
    assert "PRIMARY KEY (`step_id`)" in sql


def test_new_tables_after_012_declare_explicit_collation():
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if int(path.name.split("_", 1)[0]) < 13:
            continue
        sql = path.read_text(encoding="utf-8")
        for match in re.finditer(r"CREATE TABLE[^;]*;", sql, re.IGNORECASE | re.DOTALL):
            assert "utf8mb4_unicode_ci" in match.group(0), path.name
