"""First-boot gate and small per-process caches for the setup wizard.

Only a *fresh* install with unfinished blocking steps is ever gated. Every failure mode
(table missing, DB hiccup, never reconciled) fails open: a working portal must not be
locked out by wizard bookkeeping.
"""

from __future__ import annotations

import time

from flask import current_app

from app.setup import state
from app.utils.db import get_app_db

_RETRY_SECONDS = 15
_ADVISORY_TTL_SECONDS = 60
_MAX_UNLOCK_FAILURES = 10
_UNLOCK_WINDOW_SECONDS = 60

_cache: dict = {}
_failures: dict[str, list[float]] = {}


def reset() -> None:
    """Forget all cached state (tests; also after setup state is changed out of band)."""
    _cache.clear()
    _failures.clear()


def first_boot_pending() -> bool:
    """True while a fresh install still needs its first-boot wizard."""
    if _cache.get("first_boot_done"):
        return False
    if time.monotonic() < _cache.get("retry_after", 0.0):
        return False
    try:
        meta = state.read_meta(get_app_db())
    except Exception as exc:  # noqa: BLE001 - fail open
        current_app.logger.warning(f"Setup gate: cannot read setup state ({exc}).")
        _cache["retry_after"] = time.monotonic() + _RETRY_SECONDS
        return False
    if not meta:
        # migrate.py has not reconciled yet (or never will): never gate on that.
        _cache["retry_after"] = time.monotonic() + _RETRY_SECONDS
        return False
    pending = meta.get("origin") == state.ORIGIN_FRESH and not meta.get(
        "first_boot_complete"
    )
    if not pending:
        _cache["first_boot_done"] = True
    return pending


def mark_first_boot_done() -> None:
    _cache["first_boot_done"] = True
    _cache.pop("advisory", None)


def advisory_count(steps) -> int:
    """Number of pending steps to nag admins about (cached briefly; 0 on any error)."""
    cached = _cache.get("advisory")
    now = time.monotonic()
    if cached and now < cached[0]:
        return cached[1]
    try:
        count = len(state.advisory_pending(get_app_db(), steps))
    except Exception:  # noqa: BLE001 - a banner must never break a page
        count = 0
    _cache["advisory"] = (now + _ADVISORY_TTL_SECONDS, count)
    return count


def invalidate_advisory() -> None:
    _cache.pop("advisory", None)


def unlock_blocked(remote: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(remote, []) if now - t < _UNLOCK_WINDOW_SECONDS]
    _failures[remote] = recent
    return len(recent) >= _MAX_UNLOCK_FAILURES


def record_unlock_failure(remote: str) -> None:
    _failures.setdefault(remote, []).append(time.monotonic())
