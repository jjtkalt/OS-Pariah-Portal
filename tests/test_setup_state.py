"""Setup step registry, persisted state, and provider guard rails."""

from __future__ import annotations

import re
from pathlib import Path

from fake_setup_db import FakeConn

from app.setup import providers, state
from app.setup.providers import Capability, ExternalGridProvider, get_provider
from app.setup.steps import STEPS, Step, StepContext, StepKind
from app.utils.schema import KNOWN_SETTINGS

ROOT = Path(__file__).resolve().parent.parent
BLOCKING = [s for s in STEPS if s.kind is StepKind.BLOCKING]


def _fresh(conn=None):
    conn = conn or FakeConn()
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=False
    )
    return conn


def _finish_first_boot(conn):
    for step in STEPS:
        state.mark_step(conn, step, state.STATUS_DONE)
    assert state.complete_first_boot_if_ready(conn, STEPS)


def _advisory_step(step_id="extra_opt", version=1):
    return Step(
        id=step_id,
        version=version,
        title="Extra",
        description="Added by a later release.",
        kind=StepKind.ADVISORY,
        settings=("smtp_server",),
        skippable=True,
    )


# ------------------------------------------------------------------ registry shape


def test_registry_ids_are_unique_and_pinned():
    ids = [s.id for s in STEPS]
    assert len(ids) == len(set(ids))
    # Ids are stable forever (stored in setup_state): adding is fine, renaming is not.
    assert ids[:6] == [
        "host_bootstrap",
        "grid_identity",
        "turnstile",
        "smtp",
        "notifications",
        "read_paths",
    ]


def test_shipped_steps_are_blocking_and_reference_real_settings():
    known = {k for fields in KNOWN_SETTINGS.values() for k in fields}
    for step in STEPS:
        assert step.kind is StepKind.BLOCKING
        assert step.version >= 1
        assert set(step.settings) <= known
        assert set(step.required) <= set(step.settings)
        assert set(step.must_change) <= set(step.settings)


def test_every_step_runs_without_touching_robust_or_the_filesystem_writes():
    """checks/prefill are read-only: only SELECTs against config."""
    conn = FakeConn()
    ctx = StepContext(conn=conn, robust_factory=None, env={})
    for step in STEPS:
        if step.auto:
            continue
        step.check(ctx)
        step.prefill(ctx)
    assert all(q.startswith("SELECT") for q, _ in conn.statements)


# ---------------------------------------------------------------------- reconcile


def test_fresh_install_creates_pending_rows_and_is_gated():
    conn = _fresh()
    assert state.first_boot_pending(conn)
    assert {s.id for s in STEPS} == set(state.read_steps(conn))
    assert all(r["status"] == "pending" for r in state.read_steps(conn).values())
    meta = state.read_meta(conn)
    assert meta["origin"] == "fresh"
    assert meta["instance_id"] == "default"
    assert meta["provider"] == "external"


def test_reconcile_is_idempotent():
    conn = _fresh()
    state.mark_step(conn, STEPS[0], state.STATUS_DONE)
    first = dict(conn.state)
    result = state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=False
    )
    assert result["created"] == [] and result["reopened"] == []
    assert conn.state == first


def test_upgraded_install_is_backfilled_done_and_never_gated():
    conn = FakeConn()
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=True
    )
    assert not state.first_boot_pending(conn)
    assert state.advisory_pending(conn, STEPS) == []
    assert all(r["status"] == "done" for r in state.read_steps(conn).values())
    assert state.read_meta(conn)["origin"] == "upgraded"


def test_runtime_reconcile_without_meta_creates_nothing():
    conn = FakeConn()
    assert (
        state.reconcile(conn, STEPS, provider_id="external", instance_id="default")
        is None
    )
    assert conn.state == {}
    assert not state.first_boot_pending(conn)


def test_origin_is_decided_once():
    conn = _fresh()
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=True
    )
    assert state.read_meta(conn)["origin"] == "fresh"


# -------------------------------------------------------------- blocking/advisory


def test_first_boot_needs_every_blocking_step():
    conn = _fresh()
    for step in BLOCKING:
        assert not state.complete_first_boot_if_ready(conn, STEPS)
        state.mark_step(conn, step, state.STATUS_DONE)
    assert state.complete_first_boot_if_ready(conn, STEPS)
    assert not state.first_boot_pending(conn)


def test_skip_only_counts_for_skippable_steps():
    conn = _fresh()
    for step in BLOCKING:
        state.mark_step(
            conn,
            step,
            state.STATUS_SKIPPED if step.skippable else state.STATUS_DONE,
        )
    assert state.complete_first_boot_if_ready(conn, STEPS)

    conn = _fresh()
    for step in BLOCKING:
        state.mark_step(conn, step, state.STATUS_SKIPPED)
    assert not state.complete_first_boot_if_ready(conn, STEPS)


def test_advisory_steps_never_block_first_boot_or_gate():
    all_steps = (*STEPS, _advisory_step())
    conn = FakeConn()
    state.reconcile(
        conn,
        all_steps,
        provider_id="external",
        instance_id="default",
        preexisting=False,
    )
    for step in BLOCKING:
        state.mark_step(conn, step, state.STATUS_DONE)
    assert state.complete_first_boot_if_ready(conn, all_steps)
    assert [s.id for s in state.advisory_pending(conn, all_steps)] == ["extra_opt"]


def test_advisory_not_reported_before_first_boot_completes():
    conn = _fresh()
    assert state.advisory_pending(conn, STEPS) == []


def test_release_adding_a_step_to_upgraded_install_shows_it_without_gating():
    conn = FakeConn()
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=True
    )
    later = (*STEPS, _advisory_step())
    result = state.reconcile(conn, later, provider_id="external", instance_id="default")
    assert result["created"] == ["extra_opt"]
    assert not state.first_boot_pending(conn)
    assert [s.id for s in state.advisory_pending(conn, later)] == ["extra_opt"]


def test_version_bump_reopens_a_completed_step():
    conn = _fresh()
    _finish_first_boot(conn)
    bumped = [
        Step(**{**s.__dict__, "version": s.version + 1}) if s.id == "turnstile" else s
        for s in STEPS
    ]
    result = state.reconcile(
        conn, bumped, provider_id="external", instance_id="default"
    )
    assert result["reopened"] == ["turnstile"]
    assert conn.step_status("turnstile") == "pending"
    assert [s.id for s in state.advisory_pending(conn, bumped)] == ["turnstile"]
    # A reopened step is a nudge, not a lock-out.
    assert not state.first_boot_pending(conn)


def test_version_bump_on_pending_step_only_records_version():
    conn = _fresh()
    bumped = [
        Step(**{**s.__dict__, "version": 2}) if s.id == "smtp" else s for s in STEPS
    ]
    result = state.reconcile(
        conn, bumped, provider_id="external", instance_id="default"
    )
    assert result["reopened"] == []
    assert conn.state["smtp"]["step_version"] == 2
    assert conn.step_status("smtp") == "pending"


def test_pending_steps_keep_display_order():
    conn = _fresh()
    state.mark_step(conn, STEPS[1], state.STATUS_DONE)
    pending = [s.id for s in state.pending_steps(conn, STEPS)]
    assert pending == [s.id for s in STEPS if s.id != STEPS[1].id]


# ------------------------------------------------------------------ step behaviour


def _step(step_id):
    return next(s for s in STEPS if s.id == step_id)


def _identity(**over):
    values = {
        "grid_name": "Test Grid",
        "grid_website_url": "https://grid.test",
        "grid_domain": "grid.test",
        "portal_subdomain": "portal",
        "robust_protocol": "http",
        "robust_subdomain": "robust",
        "robust_public_port": "8002",
        "robust_private_port": "8003",
    }
    values.update(over)
    return values


def test_grid_identity_rejects_placeholder_values():
    step = _step("grid_identity")
    _, errors = step.validate(
        _identity(grid_domain="ospariah.local", grid_website_url="https://example.com"),
        {},
    )
    assert any("placeholder" in e for e in errors)


def test_grid_identity_validates_shape():
    step = _step("grid_identity")
    _, errors = step.validate(_identity(grid_domain="not a domain"), {})
    assert any("Base Domain" in e for e in errors)
    _, errors = step.validate(_identity(portal_subdomain="bad_label!"), {})
    assert any("DNS label" in e for e in errors)
    _, errors = step.validate(_identity(robust_public_port="99999"), {})
    assert any("between 1 and 65535" in e for e in errors)
    cleaned, errors = step.validate(_identity(), {})
    assert errors == []
    assert cleaned["grid_domain"] == "grid.test"


def test_blank_password_keeps_existing_and_secrets_are_not_required_twice():
    step = _step("smtp")
    cleaned, errors = step.validate(
        {
            "smtp_server": "mail.grid.test",
            "smtp_port": "587",
            "smtp_user": "u",
            "smtp_pass": "",
            "smtp_from": "noreply@grid.test",
        },
        {"smtp_pass": "stored-secret"},
    )
    assert errors == []
    assert cleaned["smtp_pass"] == "stored-secret"


def test_notifications_matrix_is_all_or_nothing():
    step = _step("notifications")
    blank = dict.fromkeys(step.settings, "")
    _, errors = step.validate({**blank, "matrix_webhook_url": "https://m.test"}, {})
    assert any("together" in e for e in errors)
    _, errors = step.validate(blank, {})
    assert errors == []


def test_apply_upserts_changes_and_drops_default_rows():
    conn = FakeConn()
    ctx = StepContext(conn=conn, env={})
    step = _step("grid_identity")
    cleaned, errors = step.validate(_identity(), {})
    assert not errors
    step.apply(ctx, cleaned)
    assert conn.config["grid_domain"] == "grid.test"
    assert "robust_protocol" not in conn.config  # equals schema default -> no row
    step.apply(ctx, cleaned)  # idempotent
    assert conn.config["grid_domain"] == "grid.test"


def test_grid_identity_prefill_hints_from_portal_host():
    conn = FakeConn()
    ctx = StepContext(conn=conn, env={"OS_PARIAH_PORTAL_HOST": "portal.mygrid.org"})
    values = _step("grid_identity").prefill(ctx)
    assert values["grid_domain"] == "mygrid.org"
    assert values["portal_subdomain"] == "portal"
    # Nothing is stored by merely prefilling.
    assert conn.config == {}


def test_read_paths_warn_but_do_not_block_for_missing_directories():
    conn = FakeConn()
    ctx = StepContext(conn=conn, env={})
    conn.config["gatekeeper_log_dir"] = "/nonexistent/os-pariah-test"
    check = _step("read_paths").check(ctx)
    assert check.ok
    assert any("/nonexistent/os-pariah-test" in w for w in check.warnings)


def test_host_bootstrap_check_reports_bad_admin_uuid_and_robust_failure():
    ctx = StepContext(
        conn=FakeConn(),
        robust_factory=lambda: (_ for _ in ()).throw(RuntimeError("down")),
        env={"ADMIN_UUID": "nope"},
    )
    check = _step("host_bootstrap").check(ctx)
    assert not check.ok
    assert len(check.errors) == 2


# ----------------------------------------------------------------------- providers


def test_external_provider_is_read_only():
    provider = get_provider("external")
    assert isinstance(provider, ExternalGridProvider)
    assert provider.capabilities == {Capability.READ_GRID}
    assert not provider.mutating
    assert [s.id for s in provider.steps()] == [s.id for s in STEPS]


def test_unknown_provider_falls_back_to_read_only_external():
    assert get_provider("os-pariah-install").id == "external"
    assert get_provider(None).id == "external"
    assert get_provider("").id == "external"


def test_shipped_providers_are_all_non_mutating():
    for provider_id in providers.provider_ids():
        assert not get_provider(provider_id).mutating


def test_a_provider_with_mutating_capability_is_flagged_and_scopes_its_steps():
    class Installer(providers.GridProvider):
        id = "test-installer"
        capabilities = frozenset({Capability.READ_GRID, Capability.INSTALL_OPENSIM})

    assert Installer().mutating
    only = Step(
        id="installer_only",
        version=1,
        title="x",
        description="x",
        kind=StepKind.ADVISORY,
        providers=frozenset({"test-installer"}),
    )
    assert only.applies_to("test-installer")
    assert not only.applies_to("external")


def test_setup_code_never_touches_opensim_or_grid_mutators():
    """Install/first-boot is grid-safe: no ini writes, syncs, bans, or OpenSim services."""
    forbidden = re.compile(
        r"sync_robust|sync_firewall|apply_robust_texture_indexes|OpenSim\.ini|Robust\.ini|"
        r"opensim\.service|robust\.service|robust_systemd_service|"
        r"INSERT INTO (UserAccounts|auth|GridUser)|UPDATE (UserAccounts|auth|GridUser)|"
        r"DELETE FROM (UserAccounts|auth|GridUser)",
        re.IGNORECASE,
    )
    files = [
        *(ROOT / "app" / "setup").glob("*.py"),
        ROOT / "scripts/os_pariah_bootstrap.py",
    ]
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#") or '"""' in line:
                continue
            assert not forbidden.search(line), f"{path.name}:{lineno}: {line.strip()}"


def test_steps_module_has_no_unregistered_provider_ids():
    for step in STEPS:
        if step.providers is not None:
            assert step.providers <= set(providers.provider_ids())
