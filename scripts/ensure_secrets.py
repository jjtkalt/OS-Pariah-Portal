"""Auto-generate SECRET_KEY in a dedicated secrets file on first run.

Platform standard (PlatformStandards ADR-013): the signing key lives in
/etc/os_pariah/secrets (mode 0600, owned by the pariah user), separate from the
main config file and never shipped in the RPM. Development falls back to a
project-root .secrets file.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

_SYSTEM_SECRETS = Path("/etc/os_pariah/secrets")
_DEV_SECRETS = Path(__file__).resolve().parent.parent / ".secrets"
_APP_USER = "pariah"


def resolve_secrets_path() -> Path:
    """Return the secrets file path for this environment."""
    override = (os.environ.get("PARIAH_SECRETS_FILE") or "").strip()
    if override:
        return Path(override)
    if _SYSTEM_SECRETS.parent.is_dir():
        return _SYSTEM_SECRETS
    return _DEV_SECRETS


def load_secrets_file(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from the secrets file without overriding existing env."""
    secrets_path = path or resolve_secrets_path()
    if not secrets_path.is_file():
        return
    for raw in secrets_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def ensure_secret_key(
    *, secrets_path: Path | None = None, app_user: str | None = _APP_USER
) -> bool:
    """Create a secrets file containing SECRET_KEY when missing.

    Skips when SECRET_KEY is already in the environment or the file exists.
    Returns True when a new file was written.
    """
    if os.environ.get("SECRET_KEY"):
        return False

    target = secrets_path or resolve_secrets_path()
    if target.is_file():
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(f"SECRET_KEY={key}\n", encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(target)

    if app_user:
        try:
            import pwd

            entry = pwd.getpwnam(app_user)
            os.chown(target, entry.pw_uid, entry.pw_gid)
        except (ImportError, KeyError, OSError):
            pass

    os.environ.setdefault("SECRET_KEY", key)
    print(f"Generated SECRET_KEY in {target}")
    return True
