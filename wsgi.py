import os
import logging
from dotenv import load_dotenv
from app import create_app

# Force Python to display INFO and DEBUG messages in the terminal
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Try the system config first, fallback to local dev file
if os.path.exists('/etc/os_pariah/os-pariah.conf'):
    load_dotenv('/etc/os_pariah/os-pariah.conf')
else:
    load_dotenv('.env')

# Execute the Application Factory
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
