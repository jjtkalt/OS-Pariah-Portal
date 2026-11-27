"""Versioned setup steps shared by the web wizard (and, later, other front ends).

Rules for adding or changing a step (docs/OPERATIONS.md "Setup steps"):

* ``id`` is stable forever; bump ``version`` when the requirements change so the step is
  reopened as pending on installs that already completed it.
* New steps added after the wizard shipped must be ``StepKind.ADVISORY``: they never
  gate or block a working portal, they only surface as an admin banner.
* ``apply`` is idempotent and re-runnable; ``check`` is read-only.
* Product settings are DB-backed ``KNOWN_SETTINGS`` (labels, types, defaults come from
  app/utils/schema.py: single source of truth). Bootstrap-level facts belong in the
  conf file and are the CLI's job, not a step's.
* Steps never touch OpenSim. Only a provider that declares a mutating capability may
  contribute steps that do (see providers.py).
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.utils.schema import KNOWN_SETTINGS

_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StepKind(StrEnum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"


@dataclass
class StepCheck:
    """Result of a read-only check: errors block completion, warnings do not."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class StepContext:
    """What steps may use: the portal DB connection and (lazily) the Robust one."""

    conn: Any
    robust_factory: Callable[[], Any] | None = None
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)

    def robust(self):
        if self.robust_factory is None:
            raise RuntimeError("No Robust connection available in this context.")
        return self.robust_factory()


def setting_meta(key: str) -> dict:
    for fields in KNOWN_SETTINGS.values():
        if key in fields:
            return fields[key]
    raise KeyError(f"{key!r} is not a KNOWN_SETTINGS key")


def setting_default(key: str) -> str:
    return str(setting_meta(key).get("default", ""))


def load_current(conn, keys) -> dict[str, str]:
    """Stored value (DB override) else schema default, for each key."""
    keys = list(keys)
    stored: dict[str, str] = {}
    if keys:
        placeholders = ", ".join(["%s"] * len(keys))
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT config_key, config_value FROM config "
                f"WHERE config_key IN ({placeholders})",
                keys,
            )
            for row in cursor.fetchall() or []:
                stored[row["config_key"]] = row["config_value"]
    return {k: stored.get(k, setting_default(k)) for k in keys}


def _clean_typed(key: str, raw: str, errors: list[str]) -> str:
    meta = setting_meta(key)
    label = meta.get("label", key)
    kind = meta.get("type", "text")
    if raw == "":
        return raw
    if kind == "number":
        try:
            int(raw)
        except ValueError:
            errors.append(f"{label} must be a whole number.")
    elif kind == "url":
        if not re.match(r"^https?://[^\s/]+", raw):
            errors.append(f"{label} must start with http:// or https://.")
    elif kind == "email":
        if not _EMAIL_RE.match(raw):
            errors.append(f"{label} must be a valid email address.")
    elif kind == "boolean":
        return "true" if raw.lower() in ("1", "true", "on", "yes") else "false"
    elif kind == "selectable":
        allowed = [
            x.strip() for x in (meta.get("options") or "").split(",") if x.strip()
        ]
        if allowed and raw not in allowed:
            errors.append(f"{label} must be one of: {', '.join(allowed)}.")
    return raw


@dataclass(frozen=True)
class Step:
    id: str
    version: int
    title: str
    description: str
    kind: StepKind = StepKind.BLOCKING
    settings: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    # Values that must differ from the shipped placeholder default.
    must_change: tuple[str, ...] = ()
    skippable: bool = False
    # Auto steps complete themselves when their check passes (nothing to ask the admin).
    auto: bool = False
    # None = applies to every provider; otherwise the provider ids it applies to.
    providers: frozenset[str] | None = None
    check_fn: Callable[[StepContext], StepCheck] | None = None
    # Cross-field validation on cleaned values -> list of error strings.
    validate_fn: Callable[[dict[str, str]], list[str]] | None = None
    prefill_fn: Callable[[StepContext, dict[str, str]], dict[str, str]] | None = None

    def __post_init__(self):
        if not _STEP_ID_RE.match(self.id):
            raise ValueError(f"Invalid step id {self.id!r}")
        if self.version < 1:
            raise ValueError("Step version must be >= 1")
        for key in (*self.settings, *self.required, *self.must_change):
            setting_meta(key)  # raises KeyError for unknown settings

    def applies_to(self, provider_id: str) -> bool:
        return self.providers is None or provider_id in self.providers

    def is_password(self, key: str) -> bool:
        return setting_meta(key).get("type") == "password"

    def check(self, ctx: StepContext) -> StepCheck:
        """Read-only status check. Default: required/must-change settings are satisfied."""
        if self.check_fn is not None:
            return self.check_fn(ctx)
        current = load_current(ctx.conn, self.settings)
        result = StepCheck()
        for key in self.required:
            if not (current.get(key) or "").strip():
                result.errors.append(
                    f"{setting_meta(key).get('label', key)} is required."
                )
        for key in self.must_change:
            if current.get(key) == setting_default(key):
                result.errors.append(
                    f"{setting_meta(key).get('label', key)} still has the placeholder value."
                )
        return result

    def prefill(self, ctx: StepContext) -> dict[str, str]:
        """Values to show in the form: current settings, optionally hinted."""
        current = load_current(ctx.conn, self.settings)
        if self.prefill_fn is not None:
            current = {**current, **self.prefill_fn(ctx, current)}
        return current

    def validate(
        self, answers: Mapping[str, str], existing: Mapping[str, str]
    ) -> tuple[dict[str, str], list[str]]:
        """Return (cleaned values to store, errors). Blank password keeps the existing one."""
        errors: list[str] = []
        cleaned: dict[str, str] = {}
        for key in self.settings:
            raw = (answers.get(key) or "").strip()
            if raw == "" and self.is_password(key) and (existing.get(key) or "") != "":
                cleaned[key] = existing[key]
                continue
            value = _clean_typed(key, raw, errors)
            if value == "":
                value = setting_default(key)
            cleaned[key] = value
        for key in self.required:
            if not (cleaned.get(key) or "").strip():
                errors.append(f"{setting_meta(key).get('label', key)} is required.")
        for key in self.must_change:
            if cleaned.get(key) == setting_default(key):
                errors.append(
                    f"{setting_meta(key).get('label', key)} still has the placeholder "
                    f"value ({setting_default(key)}); enter your own."
                )
        if not errors and self.validate_fn is not None:
            errors.extend(self.validate_fn(cleaned))
        return cleaned, errors

    def apply(self, ctx: StepContext, cleaned: Mapping[str, str]) -> None:
        """Persist cleaned values. Idempotent: defaults delete the override row."""
        with ctx.conn.cursor() as cursor:
            for key, value in cleaned.items():
                if value == setting_default(key):
                    cursor.execute("DELETE FROM config WHERE config_key = %s", (key,))
                else:
                    cursor.execute(
                        """
                        INSERT INTO config (config_key, config_value, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON DUPLICATE KEY UPDATE
                            config_value = VALUES(config_value),
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (key, value),
                    )
        ctx.conn.commit()


# --------------------------------------------------------------------------- checks


def _check_host_bootstrap(ctx: StepContext) -> StepCheck:
    result = StepCheck()
    admin_uuid = (ctx.env.get("ADMIN_UUID") or "").strip()
    try:
        uuid.UUID(admin_uuid)
    except ValueError:
        result.errors.append(
            "ADMIN_UUID is missing or not a valid UUID in the portal conf. "
            "Re-run os-pariah-bootstrap with the OpenSim PrincipalID of your admin account."
        )
        admin_uuid = ""
    try:
        robust = ctx.robust()
        with robust.cursor() as cursor:
            cursor.execute("SELECT 1 FROM UserAccounts LIMIT 1")
            cursor.fetchall()
            if admin_uuid:
                cursor.execute(
                    "SELECT 1 FROM UserAccounts WHERE PrincipalID = %s", (admin_uuid,)
                )
                if not cursor.fetchone():
                    result.warnings.append(
                        "ADMIN_UUID was not found in the grid's UserAccounts; check the UUID."
                    )
    except Exception as exc:  # noqa: BLE001 - surfaced to the admin, never raised
        result.errors.append(
            "Cannot read the grid (Robust) database with the portal's read-only account: "
            f"{exc.__class__.__name__}. Re-run os-pariah-bootstrap to repair access."
        )
    return result


def _check_read_paths(ctx: StepContext) -> StepCheck:
    result = StepCheck()
    current = load_current(ctx.conn, _READ_PATH_KEYS)
    for key in _READ_PATH_KEYS:
        value = current[key]
        if not os.path.isabs(value):
            result.errors.append(
                f"{setting_meta(key)['label']} must be an absolute path."
            )
        elif not os.path.isdir(value):
            result.warnings.append(
                f"{setting_meta(key)['label']}: {value} was not found on this host "
                "(fine if it is created later or lives elsewhere)."
            )
    return result


# ----------------------------------------------------------------------- validators


def _validate_grid_identity(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    domain = values["grid_domain"].lower()
    if not _HOST_RE.match(domain):
        errors.append("Grid Base Domain must look like example.com.")
    for key in ("portal_subdomain", "robust_subdomain"):
        if not _LABEL_RE.match(values[key].lower()):
            errors.append(
                f"{setting_meta(key)['label']} must be a single DNS label (letters, digits, hyphens)."
            )
    if values["robust_protocol"] not in ("http", "https"):
        errors.append("Robust Protocol must be http or https.")
    for key in ("robust_public_port", "robust_private_port"):
        try:
            port = int(values[key])
        except ValueError:
            continue  # already reported by the type check
        if not 1 <= port <= 65535:
            errors.append(f"{setting_meta(key)['label']} must be between 1 and 65535.")
    return errors


def _validate_smtp(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    try:
        port = int(values["smtp_port"])
        if not 1 <= port <= 65535:
            errors.append("SMTP Port must be between 1 and 65535.")
    except ValueError:
        pass
    return errors


def _validate_notifications(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    matrix = [
        values[k]
        for k in ("matrix_webhook_url", "matrix_access_token", "matrix_room_id")
    ]
    if any(matrix) and not all(matrix):
        errors.append(
            "Matrix needs the server URL, access token, and room ID together "
            "(or leave all three blank)."
        )
    webhook = values["discord_webhook_url"]
    if webhook and not webhook.startswith("https://"):
        errors.append("Discord Webhook URL must start with https://.")
    return errors


def _validate_read_paths(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key in _READ_PATH_KEYS:
        value = values[key]
        if not os.path.isabs(value) or "\x00" in value or ".." in value.split("/"):
            errors.append(
                f"{setting_meta(key)['label']} must be an absolute path without '..'."
            )
    return errors


def _prefill_grid_identity(ctx: StepContext, current: dict[str, str]) -> dict[str, str]:
    """Hint grid_domain / portal_subdomain from OS_PARIAH_PORTAL_HOST (set by bootstrap)."""
    host = (ctx.env.get("OS_PARIAH_PORTAL_HOST") or "").strip().lower()
    if "." not in host:
        return {}
    sub, _, domain = host.partition(".")
    hint: dict[str, str] = {}
    if current.get("portal_subdomain") == setting_default(
        "portal_subdomain"
    ) and _LABEL_RE.match(sub):
        hint["portal_subdomain"] = sub
    if current.get("grid_domain") == setting_default("grid_domain") and _HOST_RE.match(
        domain
    ):
        hint["grid_domain"] = domain
    return hint


_READ_PATH_KEYS = (
    "gatekeeper_log_dir",
    "fsassets_path",
    "texture_cache_path",
    "IAR_OUTPUT_DIR",
    "portal_backup_dir",
)

# Display order matters: this is the wizard sequence.
STEPS: tuple[Step, ...] = (
    Step(
        id="host_bootstrap",
        version=1,
        title="Host and grid connection",
        description=(
            "Done by the root-once os-pariah-bootstrap command: portal database, "
            "read-only access to the existing grid database, and your admin account. "
            "This step only verifies it; it changes nothing."
        ),
        auto=True,
        check_fn=_check_host_bootstrap,
    ),
    Step(
        id="grid_identity",
        version=1,
        title="Grid identity",
        description="Name your grid and tell the portal where it lives on the web.",
        settings=(
            "grid_name",
            "grid_website_url",
            "grid_domain",
            "portal_subdomain",
            "robust_protocol",
            "robust_subdomain",
            "robust_public_port",
            "robust_private_port",
        ),
        required=("grid_name", "grid_domain", "portal_subdomain"),
        must_change=("grid_domain", "grid_website_url"),
        validate_fn=_validate_grid_identity,
        prefill_fn=_prefill_grid_identity,
    ),
    Step(
        id="turnstile",
        version=1,
        title="Cloudflare Turnstile",
        description=(
            "Login, registration, and tickets are protected by Turnstile and fail "
            "closed until both keys are set (Cloudflare dashboard, Turnstile)."
        ),
        settings=("TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"),
        required=("TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"),
    ),
    Step(
        id="smtp",
        version=1,
        title="Email (SMTP)",
        description=(
            "Needed for registration verification and password resets. You can skip "
            "this and add it later under System Settings."
        ),
        settings=("smtp_server", "smtp_port", "smtp_user", "smtp_pass", "smtp_from"),
        required=("smtp_server", "smtp_from"),
        must_change=("smtp_from",),
        skippable=True,
        validate_fn=_validate_smtp,
    ),
    Step(
        id="notifications",
        version=1,
        title="Matrix / Discord notifications",
        description="Optional staff notifications. Skip if you do not use them.",
        settings=(
            "discord_webhook_url",
            "matrix_webhook_url",
            "matrix_access_token",
            "matrix_room_id",
        ),
        skippable=True,
        validate_fn=_validate_notifications,
    ),
    Step(
        id="read_paths",
        version=1,
        title="Where the grid keeps its files",
        description=(
            "Confirm where the portal should read OpenSim data (gatekeeper logs, "
            "FSAssets) and keep its own cache and backups. Defaults match the "
            "OS-Pariah Installation layout; change them if your grid differs. "
            "The portal only reads grid files; it never modifies them."
        ),
        settings=_READ_PATH_KEYS,
        validate_fn=_validate_read_paths,
        check_fn=_check_read_paths,
    ),
)


def _assert_unique_ids() -> None:
    ids = [s.id for s in STEPS]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate setup step ids")


_assert_unique_ids()


def get_step(step_id: str, provider_id: str | None = None) -> Step | None:
    from app.setup.providers import get_provider

    for step in get_provider(provider_id).steps():
        if step.id == step_id:
            return step
    return None
