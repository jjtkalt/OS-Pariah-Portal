"""Persisted setup-wizard state (table ``setup_state``, migration 013).

One row per step plus a reserved bookkeeping row ``_install``:

    origin               "fresh" (first boot) or "upgraded" (portal predates the wizard)
    instance_id          which instance this install belongs to (always "default" today)
    provider             grid provider id the steps were reconciled for
    first_boot_complete  True once every blocking step is done/skipped (or origin=upgraded)

Gating rules (see docs/OPERATIONS.md "Setup steps"):

* Only a *fresh* install whose first boot is incomplete is ever gated.
* Upgraded installs are backfilled as done and never gated; steps added by later
  releases show up as pending *advisory* items for admins.
* A step whose version increases is reopened as pending (advisory once first boot is done).

All functions take a pymysql-style connection and use ``DictCursor`` explicitly, so the
same code runs from ``scripts/migrate.py`` (raw connection) and from the web app (pool).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pymysql

META_ID = "_install"
WIZARD_SCHEMA = 1

ORIGIN_FRESH = "fresh"
ORIGIN_UPGRADED = "upgraded"

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _decode(raw) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _upsert(conn, step_id: str, version: int, status: str, detail: dict) -> None:
    with _cursor(conn) as cursor:
        cursor.execute(
            """
            INSERT INTO setup_state (step_id, step_version, status, detail)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                step_version = VALUES(step_version),
                status = VALUES(status),
                detail = VALUES(detail)
            """,
            (step_id, version, status, json.dumps(detail, sort_keys=True)),
        )


def read_meta(conn) -> dict | None:
    """The ``_install`` bookkeeping dict, or None when never reconciled."""
    with _cursor(conn) as cursor:
        cursor.execute("SELECT detail FROM setup_state WHERE step_id = %s", (META_ID,))
        row = cursor.fetchone()
    if not row:
        return None
    return _decode(row["detail"])


def write_meta(conn, meta: dict) -> None:
    _upsert(conn, META_ID, WIZARD_SCHEMA, STATUS_DONE, meta)


def read_steps(conn) -> dict[str, dict]:
    """step_id -> {version, status, detail} for every real step row."""
    with _cursor(conn) as cursor:
        cursor.execute(
            "SELECT step_id, step_version, status, detail FROM setup_state "
            "WHERE step_id <> %s",
            (META_ID,),
        )
        rows = cursor.fetchall()
    return {
        row["step_id"]: {
            "version": int(row["step_version"]),
            "status": row["status"],
            "detail": _decode(row["detail"]),
        }
        for row in rows
    }


def reconcile(
    conn,
    steps,
    *,
    provider_id: str,
    instance_id: str,
    preexisting: bool | None = None,
) -> dict | None:
    """Bring ``setup_state`` in line with the registered steps. Idempotent.

    ``preexisting`` is only used when no ``_install`` row exists yet: True means the
    portal database already had migrations applied before the wizard shipped, so every
    step is backfilled as done. Passing None (runtime callers) never creates the
    bookkeeping row and returns None when it is missing.
    """
    meta = read_meta(conn)
    backfill = False
    if meta is None:
        if preexisting is None:
            return None
        origin = ORIGIN_UPGRADED if preexisting else ORIGIN_FRESH
        meta = {
            "origin": origin,
            "instance_id": instance_id,
            "provider": provider_id,
            "wizard_schema": WIZARD_SCHEMA,
            "first_boot_complete": origin == ORIGIN_UPGRADED,
            "created_at": _now(),
        }
        write_meta(conn, meta)
        backfill = origin == ORIGIN_UPGRADED

    existing = read_steps(conn)
    created: list[str] = []
    reopened: list[str] = []
    for step in steps:
        row = existing.get(step.id)
        if row is None:
            if backfill:
                _upsert(conn, step.id, step.version, STATUS_DONE, {"backfilled": True})
            else:
                _upsert(conn, step.id, step.version, STATUS_PENDING, {})
            created.append(step.id)
        elif row["version"] < step.version and row["status"] != STATUS_PENDING:
            detail = dict(row["detail"])
            detail["reopened_from_version"] = row["version"]
            _upsert(conn, step.id, step.version, STATUS_PENDING, detail)
            reopened.append(step.id)
        elif row["version"] < step.version:
            # Still pending from an older version: just record the new version.
            _upsert(conn, step.id, step.version, STATUS_PENDING, row["detail"])

    conn.commit()
    return {
        "origin": meta.get("origin"),
        "created": created,
        "reopened": reopened,
    }


def mark_step(conn, step, status: str, detail: dict | None = None) -> None:
    if status not in (STATUS_PENDING, STATUS_DONE, STATUS_SKIPPED):
        raise ValueError(f"Unknown setup status {status!r}")
    detail = dict(detail or {})
    detail["updated_at"] = _now()
    _upsert(conn, step.id, step.version, status, detail)
    conn.commit()


def first_boot_pending(conn) -> bool:
    """True only for a fresh install whose first-boot steps are not all finished."""
    meta = read_meta(conn)
    if not meta:
        return False
    return meta.get("origin") == ORIGIN_FRESH and not meta.get("first_boot_complete")


def _step_satisfied(step, row) -> bool:
    if not row:
        return False
    if row["status"] == STATUS_DONE:
        return True
    return row["status"] == STATUS_SKIPPED and step.skippable


def complete_first_boot_if_ready(conn, steps) -> bool:
    """Flip ``first_boot_complete`` once all blocking steps are satisfied.

    Returns True when first boot is complete (now or already), False otherwise.
    """
    meta = read_meta(conn)
    if meta is None:
        return False
    if meta.get("first_boot_complete"):
        return True
    rows = read_steps(conn)
    blocking = [s for s in steps if s.kind.value == "blocking"]
    if not all(_step_satisfied(s, rows.get(s.id)) for s in blocking):
        return False
    meta["first_boot_complete"] = True
    meta["completed_at"] = _now()
    write_meta(conn, meta)
    conn.commit()
    return True


def pending_steps(conn, steps) -> list:
    """Registered steps whose stored status is pending (display order preserved)."""
    rows = read_steps(conn)
    return [
        s
        for s in steps
        if (rows.get(s.id) or {"status": STATUS_PENDING})["status"] == STATUS_PENDING
    ]


def advisory_pending(conn, steps) -> list:
    """Pending steps to nag admins about: only once first boot is finished."""
    meta = read_meta(conn)
    if not meta or not meta.get("first_boot_complete"):
        return []
    rows = read_steps(conn)
    return [s for s in steps if rows.get(s.id, {}).get("status") == STATUS_PENDING]
