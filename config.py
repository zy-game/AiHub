import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DATABASE_PATH = os.getenv("DATABASE_PATH", "aihub.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")  # Changed to DEBUG for troubleshooting
ADMIN_KEY = os.getenv("ADMIN_KEY", "admin123")
