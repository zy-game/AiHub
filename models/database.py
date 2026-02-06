import aiosqlite
from config import DATABASE_PATH
from utils.logger import logger

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
        await init_tables(_db)
    return _db

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None

async def init_tables(db: aiosqlite.Connection):
    # Check if channels table exists (old schema)
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='channels'"
    ) as cursor:
        channels_exists = await cursor.fetchone() is not None
    
    # If channels table exists, skip creating it (migration should have removed it)
    # Only create new provider-based schema
    
    # Check if accounts table exists and has the right schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns] if columns else []
    
    # Create accounts table with new schema if it doesn't exist or needs migration
    if not column_names or "channel_id" in column_names:
        # Table doesn't exist or has old schema - will be handled by migration script
        if not column_names:
            # Create new schema directly
            await db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_type TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    api_key TEXT NOT NULL,
                    usage INTEGER DEFAULT 0,
                    "limit" INTEGER DEFAULT 0,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_provider ON accounts(provider_type, enabled)")
    
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT,
            quota INTEGER DEFAULT -1,
            used_quota INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            key TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            status INTEGER DEFAULT 1,
            created_time INTEGER NOT NULL,
            accessed_time INTEGER DEFAULT 0,
            expired_time INTEGER DEFAULT -1,
            model_limits_enabled INTEGER DEFAULT 0,
            model_limits TEXT DEFAULT '',
            ip_whitelist TEXT DEFAULT '',
            "group" TEXT DEFAULT 'default',
            cross_group_retry INTEGER DEFAULT 0,
            rpm_limit INTEGER DEFAULT 0,
            tpm_limit INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            request_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            status INTEGER DEFAULT 200,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
        CREATE INDEX IF NOT EXISTS idx_tokens_key ON tokens(key);
        CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
    """)
    
    # Migrate users table: add token columns if missing
    async with db.execute("PRAGMA table_info(users)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if "input_tokens" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN input_tokens INTEGER DEFAULT 0")
        if "output_tokens" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN output_tokens INTEGER DEFAULT 0")
        if "total_tokens" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN total_tokens INTEGER DEFAULT 0")
    
    # Migrate tokens table: add cross_group_retry if missing
    async with db.execute("PRAGMA table_info(tokens)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if "cross_group_retry" not in column_names:
            await db.execute("ALTER TABLE tokens ADD COLUMN cross_group_retry INTEGER DEFAULT 0")
        if "rpm_limit" not in column_names:
            await db.execute("ALTER TABLE tokens ADD COLUMN rpm_limit INTEGER DEFAULT 0")
        if "tpm_limit" not in column_names:
            await db.execute("ALTER TABLE tokens ADD COLUMN tpm_limit INTEGER DEFAULT 0")
    
    # Add provider_type to logs table if missing
    async with db.execute("PRAGMA table_info(logs)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if "provider_type" not in column_names:
            await db.execute("ALTER TABLE logs ADD COLUMN provider_type TEXT")
    
    await db.commit()
    logger.info("Database tables initialized")
