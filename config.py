import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DATABASE_PATH = os.getenv("DATABASE_PATH", "aihub.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")  # Changed to DEBUG for troubleshooting
ADMIN_KEY = os.getenv("ADMIN_KEY", "admin123")

# Super admin configuration
SUPER_ADMIN_EMAIL = os.getenv('SUPER_ADMIN_EMAIL', 'admin@aihub.local')
SUPER_ADMIN_PASSWORD = os.getenv('SUPER_ADMIN_PASSWORD', 'admin123456')
SUPER_ADMIN_NAME = os.getenv('SUPER_ADMIN_NAME', 'Super Admin')

# Initial invite code for first user registration
INITIAL_INVITE_CODE = os.getenv('INITIAL_INVITE_CODE', 'WELCOME2024')
