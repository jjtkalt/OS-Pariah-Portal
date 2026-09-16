#!/usr/bin/env python3
"""Local CI gate: Ruff (lint + format), pytest, and pip-audit.

Mirrors `.github/workflows/ci-tests.yml` and adds dependency advisory checks.
Intended for manual runs and as a pre-commit hook (see `.pre-commit-config.yaml`).

Usage (from repo root, with the project venv preferred):

    python3 scripts/check_local.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_python() -> Path | None:
    for relative in ("venv/bin/python", ".venv/bin/python", "venv/Scripts/python.exe"):
        candidate = ROOT / relative
        if candidate.is_file():
            return candidate
    return None


def _ensure_venv_python() -> None:
    """Re-exec under the project venv when available so tools resolve correctly."""
    venv_python = _venv_python()
    if venv_python is None:
        return
    try:
        if Path(sys.executable).resolve() == venv_python.resolve():
            return
    except OSError:
        return
    os.execv(str(venv_python), [str(venv_python), *sys.argv])


def _run(label: str, argv: list[str]) -> int:
    print(f"\n==> {label}")
    print(f"    {' '.join(argv)}")
    completed = subprocess.run(argv, cwd=ROOT, check=False)
    if completed.returncode != 0:
        print(f"FAILED: {label} (exit {completed.returncode})", file=sys.stderr)
    return completed.returncode


def main() -> int:
    _ensure_venv_python()
    python = sys.executable
    failures: list[str] = []

    steps: list[tuple[str, list[str]]] = [
        ("Ruff lint", [python, "-m", "ruff", "check", "."]),
        ("Ruff format check", [python, "-m", "ruff", "format", "--check", "."]),
        ("Pytest", [python, "-m", "pytest", "-v", "tests/"]),
        (
            "pip-audit (requirements.txt)",
            [python, "-m", "pip_audit", "-r", "requirements.txt"],
        ),
        (
            "pip-audit (requirements-dev.txt)",
            [python, "-m", "pip_audit", "-r", "requirements-dev.txt"],
        ),
    ]

    for label, argv in steps:
        if _run(label, argv) != 0:
            failures.append(label)

    print()
    if failures:
        print("Local checks failed:", file=sys.stderr)
        for label in failures:
            print(f"  - {label}", file=sys.stderr)
        return 1

    print("All local checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
