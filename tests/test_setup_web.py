"""First-boot gate and the /setup wizard routes (portal DB faked, Robust mocked)."""

from __future__ import annotations

import pytest
from fake_setup_db import FakeConn

from app.setup import gate, state
from app.setup.steps import STEPS, Step, StepKind
from app.utils.schema import PERM_SUPER_ADMIN

ADMIN = "11111111-2222-3333-4444-555555555555"
TOKEN = "correct-horse-battery-staple-token"

IDENTITY_FORM = {
    "grid_name": "Test Grid",
    "grid_website_url": "https://grid.test",
    "grid_domain": "grid.test",
    "portal_subdomain": "portal",
    "robust_protocol": "http",
    "robust_subdomain": "robust",
    "robust_public_port": "8002",
    "robust_private_port": "8003",
}


@pytest.fixture
def web(app, monkeypatch):
    """Wizard wiring: gate enabled, fake portal DB, fixed token, recorded token removal."""
    app.config["SETUP_GATE_IN_TESTS"] = True
    gate.reset()
    conn = FakeConn()
    removed = []
    monkeypatch.setattr("app.setup.gate.get_app_db", lambda: conn)
    monkeypatch.setattr("app.setup.routes.get_app_db", lambda: conn)
    monkeypatch.setattr(
        "app.setup.routes.get_dynamic_config", lambda key, default=None: "external"
    )
    monkeypatch.setattr("app.setup.routes._read_token", lambda: TOKEN)
    monkeypatch.setattr("app.setup.routes._remove_token", lambda: removed.append(True))
    monkeypatch.setenv("ADMIN_UUID", ADMIN)
    conn.removed = removed
    yield conn
    gate.reset()


def _fresh(conn):
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=False
    )


def _upgraded(conn):
    state.reconcile(
        conn, STEPS, provider_id="external", instance_id="default", preexisting=True
    )


def _unlock(client):
    return client.post("/setup/unlock", data={"token": TOKEN})


def _admin_session(client):
    with client.session_transaction() as sess:
        sess["uuid"] = ADMIN
        sess["name"] = "Admin Resident"
        sess["permissions"] = PERM_SUPER_ADMIN


def _redirects_to_setup(response):
    return response.status_code == 302 and "/setup" in response.headers.get(
        "Location", ""
    )


# ------------------------------------------------------------------------- gate


def test_fresh_install_redirects_the_portal_to_setup(client, web):
    _fresh(web)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup/")


def test_gate_leaves_auth_and_manual_alone(client, web):
    _fresh(web)
    for path in ("/auth/login", "/manual.html"):
        assert not _redirects_to_setup(client.get(path)), path


def test_gate_answers_api_with_503(client, web):
    _fresh(web)
    response = client.get("/api/online")
    assert response.status_code == 503
    assert "setup" in response.get_json()["error"].lower()


def test_upgraded_install_is_never_gated(client, web):
    _upgraded(web)
    assert not _redirects_to_setup(client.get("/"))


def test_gate_fails_open_when_setup_state_is_missing_or_broken(
    client, web, monkeypatch
):
    # Never reconciled: no _install row.
    assert not _redirects_to_setup(client.get("/"))

    def boom():
        raise RuntimeError("db down")

    gate.reset()
    monkeypatch.setattr("app.setup.gate.get_app_db", boom)
    assert gate.first_boot_pending() is False


def test_gate_is_off_in_default_test_config(client, web, app):
    app.config["SETUP_GATE_IN_TESTS"] = False
    _fresh(web)
    assert not _redirects_to_setup(client.get("/"))


# ----------------------------------------------------------------------- unlock


def test_setup_requires_unlock_on_first_boot(client, web):
    _fresh(web)
    response = client.get("/setup/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup/unlock")


def test_wrong_token_is_rejected(client, web):
    _fresh(web)
    response = client.post("/setup/unlock", data={"token": "nope"})
    assert response.status_code == 200
    assert b"not accepted" in response.data
    assert client.get("/setup/").status_code == 302


def test_right_token_opens_the_wizard(client, web):
    _fresh(web)
    assert _unlock(client).status_code == 302
    response = client.get("/setup/")
    assert response.status_code == 200
    for step in STEPS:
        assert step.title.encode() in response.data


def test_unlock_is_rate_limited(client, web):
    _fresh(web)
    for _ in range(10):
        client.post("/setup/unlock", data={"token": "nope"})
    assert client.post("/setup/unlock", data={"token": TOKEN}).status_code == 429


def test_unlock_shows_recovery_hint_when_token_file_is_missing(
    client, web, monkeypatch
):
    _fresh(web)
    monkeypatch.setattr("app.setup.routes._read_token", lambda: "")
    response = client.get("/setup/unlock")
    assert b"os-pariah-bootstrap --new-token" in response.data
    # An empty token must never unlock anything.
    assert client.post("/setup/unlock", data={"token": ""}).status_code == 200
    assert client.get("/setup/").status_code == 302


def test_token_cannot_be_used_after_first_boot(client, web):
    _upgraded(web)
    assert client.get("/setup/unlock").status_code == 302
    assert client.get("/setup/").headers["Location"].endswith("/auth/login")


def test_setup_session_does_not_open_the_rest_of_the_portal(client, web):
    _fresh(web)
    _unlock(client)
    response = client.get("/admin/settings")
    assert response.status_code == 302
    assert "/setup/" in response.headers["Location"]


# ------------------------------------------------------------------------ steps


def test_auto_step_completes_when_check_passes(client, web):
    _fresh(web)
    _unlock(client)
    client.get("/setup/")
    assert web.step_status("host_bootstrap") == "done"


def test_grid_identity_rejects_placeholder_and_saves_nothing(client, web):
    _fresh(web)
    _unlock(client)
    response = client.post(
        "/setup/step/grid_identity",
        data={**IDENTITY_FORM, "grid_domain": "ospariah.local", "action": "save"},
    )
    assert response.status_code == 200
    assert b"placeholder" in response.data
    assert web.config == {}
    assert web.step_status("grid_identity") == "pending"


def test_grid_identity_saves_settings_and_marks_done(client, web):
    _fresh(web)
    _unlock(client)
    response = client.post(
        "/setup/step/grid_identity", data={**IDENTITY_FORM, "action": "save"}
    )
    assert response.status_code == 302
    assert web.config["grid_domain"] == "grid.test"
    assert web.config["grid_name"] == "Test Grid"
    assert web.step_status("grid_identity") == "done"


def test_secret_values_are_never_rendered_back(client, web):
    _fresh(web)
    web.config["TURNSTILE_SECRET_KEY"] = "super-secret-turnstile"
    _unlock(client)
    response = client.get("/setup/step/turnstile")
    assert response.status_code == 200
    assert b"super-secret-turnstile" not in response.data


def test_blank_secret_keeps_stored_value(client, web):
    _fresh(web)
    web.config["TURNSTILE_SECRET_KEY"] = "stored-secret"
    _unlock(client)
    response = client.post(
        "/setup/step/turnstile",
        data={
            "TURNSTILE_SITE_KEY": "site-key",
            "TURNSTILE_SECRET_KEY": "",
            "action": "save",
        },
    )
    assert response.status_code == 302
    assert web.config["TURNSTILE_SECRET_KEY"] == "stored-secret"
    assert web.config["TURNSTILE_SITE_KEY"] == "site-key"


def test_only_optional_steps_can_be_skipped(client, web):
    _fresh(web)
    _unlock(client)
    response = client.post("/setup/step/turnstile", data={"action": "skip"})
    assert response.status_code == 400
    assert web.step_status("turnstile") == "pending"
    response = client.post("/setup/step/smtp", data={"action": "skip"})
    assert response.status_code == 302
    assert web.step_status("smtp") == "skipped"


def test_unknown_step_is_404(client, web):
    _fresh(web)
    _unlock(client)
    assert client.get("/setup/step/does_not_exist").status_code == 404


def test_step_changes_are_audited_without_secret_values(client, web, monkeypatch):
    _fresh(web)
    _unlock(client)
    logged = []
    monkeypatch.setattr(
        "app.setup.routes.log_audit_action",
        lambda action, details, *a: logged.append(details),
    )
    client.post(
        "/setup/step/turnstile",
        data={
            "TURNSTILE_SITE_KEY": "site-key",
            "TURNSTILE_SECRET_KEY": "very-secret-value",
            "action": "save",
        },
    )
    assert logged
    assert "very-secret-value" not in " ".join(logged)
    assert "turnstile" in logged[0]


# ------------------------------------------------------------------- completion


def _finish_all_but(conn, last_id):
    for step in STEPS:
        if step.id != last_id:
            state.mark_step(
                conn,
                step,
                state.STATUS_SKIPPED if step.skippable else state.STATUS_DONE,
            )


def test_finishing_the_last_blocking_step_completes_setup_and_ungates(client, web):
    _fresh(web)
    _finish_all_but(web, "grid_identity")
    _unlock(client)
    assert gate.first_boot_pending()
    client.post("/setup/step/grid_identity", data={**IDENTITY_FORM, "action": "save"})
    response = client.get("/setup/")
    assert response.status_code == 200
    assert b"First-boot setup is complete" in response.data

    assert state.read_meta(web)["first_boot_complete"] is True
    assert web.removed == [True]  # one-time token deleted
    assert not gate.first_boot_pending()
    # The setup session no longer works; the portal is open for normal use.
    with client.session_transaction() as sess:
        assert "setup_authorized" not in sess
    assert not _redirects_to_setup(client.get("/"))


def test_incomplete_setup_stays_gated(client, web):
    _fresh(web)
    _unlock(client)
    client.get("/setup/")
    assert gate.first_boot_pending()
    assert web.removed == []


# -------------------------------------------------------------- admin re-entry


def test_super_admin_can_reopen_setup_after_first_boot(client, web):
    _upgraded(web)
    _admin_session(client)
    assert client.get("/setup/").status_code == 200
    assert client.get("/setup/step/grid_identity").status_code == 200


def test_anonymous_cannot_reach_setup_after_first_boot(client, web):
    _upgraded(web)
    response = client.get("/setup/step/grid_identity")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_new_release_step_is_an_advisory_nudge_not_a_lockout(client, web, monkeypatch):
    _upgraded(web)
    extra = Step(
        id="extra_opt",
        version=1,
        title="Brand new optional step",
        description="Added by a later release.",
        kind=StepKind.ADVISORY,
        settings=("smtp_server",),
        skippable=True,
    )
    later = (*STEPS, extra)
    monkeypatch.setattr(
        "app.setup.providers.ExternalGridProvider.steps", lambda self: list(later)
    )
    state.reconcile(web, later, provider_id="external", instance_id="default")
    _admin_session(client)

    assert not gate.first_boot_pending()
    page = client.get("/setup/")
    assert b"Brand new optional step" in page.data
    assert b"Needs attention" in page.data
    assert not _redirects_to_setup(client.get("/"))

    # Admins see a banner on normal pages; everyone else does not.
    gate.invalidate_advisory()
    home = client.get("/policies/")
    assert b"Open setup" in home.data
    assert b"1 step" in home.data
    anonymous = client.application.test_client().get("/policies/")
    assert b"Open setup" not in anonymous.data
