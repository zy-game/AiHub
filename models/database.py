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
    # Check if we need to migrate old schema (remove base_url column)
    async with db.execute("PRAGMA table_info(channels)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "base_url" in column_names:
            logger.info("Migrating database: removing base_url column from channels")
            # SQLite doesn't support DROP COLUMN directly, need to recreate table
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS channels_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    models TEXT NOT NULL,
                    model_mapping TEXT DEFAULT '{}',
                    priority INTEGER DEFAULT 0,
                    weight INTEGER DEFAULT 1,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO channels_new (id, name, type, models, model_mapping, priority, weight, enabled, created_at)
                    SELECT id, name, type, models, model_mapping, priority, weight, enabled, created_at FROM channels;
                DROP TABLE channels;
                ALTER TABLE channels_new RENAME TO channels;
            """)
            await db.commit()
            logger.info("Database migration completed")
    
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            models TEXT NOT NULL,
            model_mapping TEXT DEFAULT '{}',
            priority INTEGER DEFAULT 0,
            weight INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            api_key TEXT NOT NULL,
            usage INTEGER DEFAULT 0,
            "limit" INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT,
            quota INTEGER DEFAULT -1,
            used_quota INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        CREATE INDEX IF NOT EXISTS idx_channels_enabled ON channels(enabled);
        CREATE INDEX IF NOT EXISTS idx_channels_models ON channels(models);
        CREATE INDEX IF NOT EXISTS idx_accounts_channel ON accounts(channel_id, enabled);
        CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
        CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
    """)
    # Migrate accounts table: add usage/limit columns if missing
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if "usage" not in column_names:
            await db.execute("ALTER TABLE accounts ADD COLUMN usage INTEGER DEFAULT 0")
        if "limit" not in column_names:
            await db.execute("ALTER TABLE accounts ADD COLUMN \"limit\" INTEGER DEFAULT 0")
        if "input_tokens" not in column_names:
            await db.execute("ALTER TABLE accounts ADD COLUMN input_tokens INTEGER DEFAULT 0")
        if "output_tokens" not in column_names:
            await db.execute("ALTER TABLE accounts ADD COLUMN output_tokens INTEGER DEFAULT 0")
        if "total_tokens" not in column_names:
            await db.execute("ALTER TABLE accounts ADD COLUMN total_tokens INTEGER DEFAULT 0")
    
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
    
    await db.commit()
    logger.info("Database tables initialized")
