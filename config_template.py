# config.py

OVERSEERR_API_URL = 'http://YOUR_IP_ADDRESS:5055/api/v1'
OVERSEERR_API_KEY = 'YOUR_OVERSEERR_API_KEY'
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'

# Access Control Configuration
# Set a password to protect access. If empty, no access control is applied.
PASSWORD = ""  # or "" for no access control

# Initial whitelist of user IDs that do not need to enter the password.
# You can leave this empty (as an empty list) if no user is pre-authorized.
# Once a user enters the correct password, they will be added here dynamically.
WHITELIST = []  # Telegram User IDs