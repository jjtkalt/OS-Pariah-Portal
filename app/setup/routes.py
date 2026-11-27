"""Gated web setup wizard (``/setup``).

Access: during first boot, the one-time token the bootstrap CLI wrote to the instance's
``setup_token`` file (Turnstile and login are not configured yet, so a normal login cannot
work); at any time, a logged-in Super Admin (re-opening steps, advisory steps after
upgrades). No route here touches OpenSim.
"""

from __future__ import annotations

import contextlib
import hmac
import os
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.setup import gate, state
from app.setup.providers import get_provider
from app.setup.steps import StepContext, load_current, setting_meta
from app.utils import instance as instance_ctx
from app.utils.audit import log_audit_action
from app.utils.auth_helpers import has_permission
from app.utils.db import get_app_db, get_dynamic_config, get_robust_db
from app.utils.schema import PERM_SUPER_ADMIN

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")


def _provider():
    return get_provider(get_dynamic_config("grid_provider"))


def _context() -> StepContext:
    return StepContext(conn=get_app_db(), robust_factory=get_robust_db)


def _read_token() -> str:
    path = instance_ctx.current().setup_token_path
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _remove_token() -> None:
    with contextlib.suppress(OSError):
        os.unlink(instance_ctx.current().setup_token_path)


def _is_super_admin() -> bool:
    return bool(session.get("uuid")) and has_permission(PERM_SUPER_ADMIN)


def _authorized() -> bool:
    if _is_super_admin():
        return True
    return bool(session.get("setup_authorized")) and gate.first_boot_pending()


def setup_access(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if _authorized():
            return view(*args, **kwargs)
        if gate.first_boot_pending():
            return redirect(url_for("setup.unlock"))
        flash("Setup is limited to portal Super Admins. Please log in.", "error")
        return redirect(url_for("auth.login"))

    return wrapper


@setup_bp.route("/unlock", methods=["GET", "POST"])
def unlock():
    """Exchange the one-time setup token for a setup session (first boot only)."""
    if not gate.first_boot_pending():
        return redirect(url_for("setup.index"))

    token_path = instance_ctx.current().setup_token_path
    expected = _read_token()
    if request.method == "POST":
        remote = request.remote_addr or "unknown"
        if gate.unlock_blocked(remote):
            current_app.logger.warning(f"Setup unlock rate-limited for {remote}.")
            abort(429)
        candidate = (request.form.get("token") or "").strip()
        if expected and hmac.compare_digest(candidate, expected):
            session.clear()
            session["setup_authorized"] = True
            session.permanent = False
            return redirect(url_for("setup.index"))
        gate.record_unlock_failure(remote)
        current_app.logger.warning(f"Invalid setup token from {remote}.")
        flash("That setup token was not accepted.", "error")
    return render_template(
        "setup/unlock.html", token_missing=not expected, token_path=token_path
    )


def _auto_evaluate(steps, ctx, rows):
    """Run read-only checks for auto steps; complete the ones that pass."""
    results = {}
    for step in steps:
        if not step.auto:
            continue
        check = step.check(ctx)
        results[step.id] = check
        status = (rows.get(step.id) or {}).get("status")
        if check.ok and status != state.STATUS_DONE:
            state.mark_step(ctx.conn, step, state.STATUS_DONE, {"auto": True})
        elif not check.ok and status == state.STATUS_DONE:
            # Regressed (for example DB access broke): show it, keep the record honest.
            state.mark_step(ctx.conn, step, state.STATUS_PENDING, {"auto": True})
    return results


@setup_bp.route("/", methods=["GET"])
@setup_access
def index():
    provider = _provider()
    steps = provider.steps()
    ctx = _context()
    conn = ctx.conn

    reconciled = state.reconcile(
        conn,
        steps,
        provider_id=provider.id,
        instance_id=instance_ctx.current().id,
    )
    if reconciled is None:
        return render_template(
            "setup/index.html",
            uninitialised=True,
            steps=[],
            rows={},
            auto_checks={},
            complete=False,
            first_boot=False,
        )

    was_pending = state.first_boot_pending(conn)
    rows = state.read_steps(conn)
    auto_checks = _auto_evaluate(steps, ctx, rows)
    rows = state.read_steps(conn)
    complete = state.complete_first_boot_if_ready(conn, steps)

    if was_pending and complete:
        _remove_token()
        session.pop("setup_authorized", None)
        gate.mark_first_boot_done()
        flash("First-boot setup is complete. You can log in now.", "success")
        log_audit_action("Setup Wizard", "First-boot setup completed.")

    gate.invalidate_advisory()
    return render_template(
        "setup/index.html",
        uninitialised=False,
        steps=steps,
        rows=rows,
        auto_checks=auto_checks,
        complete=complete,
        first_boot=state.first_boot_pending(conn),
        just_completed=was_pending and complete,
    )


def _field_specs(step, values):
    specs = []
    for key in step.settings:
        meta = setting_meta(key)
        kind = meta.get("type", "text")
        options = [
            x.strip() for x in (meta.get("options") or "").split(",") if x.strip()
        ]
        specs.append(
            {
                "key": key,
                "label": meta.get("label", key),
                "type": kind,
                "options": options,
                "desc": meta.get("desc", ""),
                "required": key in step.required,
                # Never echo stored secrets back into HTML.
                "value": "" if kind == "password" else values.get(key, ""),
                "has_secret": kind == "password" and bool(values.get(key, "")),
                "default": meta.get("default", ""),
            }
        )
    return specs


@setup_bp.route("/step/<step_id>", methods=["GET", "POST"])
@setup_access
def step_form(step_id):
    provider = _provider()
    step = next((s for s in provider.steps() if s.id == step_id), None)
    if step is None:
        abort(404)
    if step.auto:
        return redirect(url_for("setup.index"))

    ctx = _context()
    existing = step.prefill(ctx)
    values = existing

    if request.method == "POST":
        if request.form.get("action") == "skip":
            if not step.skippable:
                abort(400)
            state.mark_step(ctx.conn, step, state.STATUS_SKIPPED)
            gate.invalidate_advisory()
            flash(f"Skipped: {step.title}. You can configure it later.", "info")
            return redirect(url_for("setup.index"))

        answers = {}
        for key in step.settings:
            if setting_meta(key).get("type") == "boolean":
                answers[key] = "true" if request.form.get(key) else "false"
            else:
                answers[key] = request.form.get(key, "")
        current = load_current(ctx.conn, step.settings)
        cleaned, errors = step.validate(answers, current)
        if errors:
            for message in errors:
                flash(message, "error")
            values = {**existing, **answers}
        else:
            step.apply(ctx, cleaned)
            state.mark_step(
                ctx.conn, step, state.STATUS_DONE, {"keys": sorted(cleaned)}
            )
            gate.invalidate_advisory()
            # Key names only: never write secret values into the audit log.
            log_audit_action(
                "Setup Wizard",
                f"Configured step '{step.id}' (settings: {', '.join(sorted(cleaned))}).",
            )
            flash(f"Saved: {step.title}.", "success")
            return redirect(url_for("setup.index"))

    check = step.check(ctx)
    return render_template(
        "setup/step.html",
        step=step,
        fields=_field_specs(step, values),
        check=check,
    )
