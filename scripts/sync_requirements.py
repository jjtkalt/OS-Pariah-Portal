"""Install or upgrade venv packages to match requirements.txt before service start."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"


def main():
    if not REQUIREMENTS.is_file():
        print(f"requirements.txt not found: {REQUIREMENTS}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(REQUIREMENTS),
    ]
    print(f"Syncing Python dependencies from {REQUIREMENTS}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("pip install failed.", file=sys.stderr)
        sys.exit(result.returncode)
    print("Python dependencies are up to date.")


if __name__ == "__main__":
    main()
