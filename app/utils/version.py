import os
import subprocess


def get_portal_version() -> str:
    """
    Best-effort portal version string.

    Order of precedence:
    - OS_PARIAH_VERSION env var (runtime override)
    - git describe (for manual/dev installs with a .git folder)
    - app.version.__version__ (RPM workflow writes this into the tarball)
    """
    env_ver = (os.environ.get("OS_PARIAH_VERSION") or "").strip()
    if env_ver:
        return env_ver

    # Manual/dev installs: pull the closest tag if git is available.
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--dirty", "--always"],
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        ver = out.decode("utf-8", errors="ignore").strip()
        if ver:
            return ver
    except Exception:
        pass

    try:
        from app.version import __version__

        return (__version__ or "").strip() or "unknown"
    except Exception:
        return "unknown"
