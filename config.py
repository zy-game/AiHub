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

# Content cleaning configuration
CONTENT_CLEANING_ENABLED = os.getenv('CONTENT_CLEANING_ENABLED', 'true').lower() == 'true'
CLEAN_SPECIAL_CHARS = os.getenv('CLEAN_SPECIAL_CHARS', 'true').lower() == 'true'
NORMALIZE_WHITESPACE = os.getenv('NORMALIZE_WHITESPACE', 'true').lower() == 'true'
FIX_CODE_FORMATTING = os.getenv('FIX_CODE_FORMATTING', 'true').lower() == 'true'
REMOVE_DEBUG_MARKERS = os.getenv('REMOVE_DEBUG_MARKERS', 'true').lower() == 'true'

# Prompt Cache configuration
PROMPT_CACHE_ENABLED = os.getenv('PROMPT_CACHE_ENABLED', 'true').lower() == 'true'

# Context Compression configuration
CONTEXT_COMPRESSION_ENABLED = os.getenv('CONTEXT_COMPRESSION_ENABLED', 'false').lower() == 'true'
CONTEXT_COMPRESSION_THRESHOLD = int(os.getenv('CONTEXT_COMPRESSION_THRESHOLD', '8000'))
CONTEXT_COMPRESSION_TARGET = int(os.getenv('CONTEXT_COMPRESSION_TARGET', '4000'))
CONTEXT_COMPRESSION_STRATEGY = os.getenv('CONTEXT_COMPRESSION_STRATEGY', 'sliding_window')  # sliding_window, summary, hybrid
