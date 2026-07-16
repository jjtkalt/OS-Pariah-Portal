import logging
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from ensure_secrets import load_secrets_file  # noqa: E402

from app import create_app  # noqa: E402

# Force Python to display INFO and DEBUG messages in the terminal
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Try the system config first, fallback to local dev file
if os.path.exists("/etc/os_pariah/os-pariah.conf"):
    load_dotenv("/etc/os_pariah/os-pariah.conf")
else:
    load_dotenv(".env")

# Load the auto-generated SECRET_KEY (systemd may not re-read a file created during
# the same ExecStartPre migrate run). Never overrides values already in the environment.
load_secrets_file()

# Execute the Application Factory
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
