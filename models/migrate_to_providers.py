"""
Database migration script: Convert from channel-based to provider-based system
This script migrates the database from using channels table to using provider types directly.
"""
import asyncio
import aiosqlite
from models.database import get_db
from utils.logger import logger

async def migrate_database():
    """Migrate database from channel-based to provider-based system"""
    db = await get_db()
    
    logger.info("Starting database migration to provider-based system...")
    
    try:
        # Step 1: Check if migration is needed
        async with db.execute("PRAGMA table_info(accounts)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
        
        if "provider_type" in column_names:
            logger.info("Database already migrated to provider-based system")
            return
        
        # Step 2: Check if channels table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='channels'"
        ) as cursor:
            channels_exists = await cursor.fetchone() is not None
        
        if not channels_exists:
            logger.warning("Channels table does not exist, creating new schema directly")
            await create_new_schema(db)
            return
        
        # Step 3: Create mapping from channel_id to provider_type
        logger.info("Creating channel_id to provider_type mapping...")
        async with db.execute("SELECT id, type FROM channels") as cursor:
            channel_mapping = {row[0]: row[1] for row in await cursor.fetchall()}
        
        logger.info(f"Found {len(channel_mapping)} channels to migrate")
        
        # Step 4: Create new accounts table with provider_type
        logger.info("Creating new accounts table structure...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts_new (
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
        
        # Step 5: Migrate data from old accounts table
        logger.info("Migrating account data...")
        async with db.execute("SELECT * FROM accounts") as cursor:
            accounts = await cursor.fetchall()
        
        migrated_count = 0
        skipped_count = 0
        
        for account in accounts:
            account_dict = dict(account)
            channel_id = account_dict.get("channel_id")
            provider_type = channel_mapping.get(channel_id)
            
            if not provider_type:
                logger.warning(f"Skipping account {account_dict['id']}: channel_id {channel_id} not found in mapping")
                skipped_count += 1
                continue
            
            await db.execute("""
                INSERT INTO accounts_new 
                (id, provider_type, name, api_key, usage, "limit", input_tokens, output_tokens, total_tokens, last_used_at, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                account_dict["id"],
                provider_type,
                account_dict.get("name", ""),
                account_dict["api_key"],
                account_dict.get("usage", 0),
                account_dict.get("limit", 0),
                account_dict.get("input_tokens", 0),
                account_dict.get("output_tokens", 0),
                account_dict.get("total_tokens", 0),
                account_dict.get("last_used_at"),
                account_dict.get("enabled", 1),
                account_dict.get("created_at")
            ))
            migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} accounts, skipped {skipped_count}")
        
        # Step 6: Replace old accounts table with new one
        logger.info("Replacing old accounts table...")
        await db.execute("DROP TABLE accounts")
        await db.execute("ALTER TABLE accounts_new RENAME TO accounts")
        
        # Step 7: Create indexes
        logger.info("Creating indexes...")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_provider ON accounts(provider_type, enabled)")
        
        # Step 8: Backup and drop channels table
        logger.info("Backing up and removing channels table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels_backup AS SELECT * FROM channels
        """)
        await db.execute("DROP TABLE channels")
        
        # Step 9: Update logs table to use provider_type (optional - keep channel_id for historical data)
        logger.info("Updating logs table schema...")
        async with db.execute("PRAGMA table_info(logs)") as cursor:
            log_columns = await cursor.fetchall()
            log_column_names = [col[1] for col in log_columns]
        
        if "provider_type" not in log_column_names:
            # Add provider_type column and populate from channel_id mapping
            await db.execute("ALTER TABLE logs ADD COLUMN provider_type TEXT")
            
            for channel_id, provider_type in channel_mapping.items():
                await db.execute(
                    "UPDATE logs SET provider_type = ? WHERE channel_id = ?",
                    (provider_type, channel_id)
                )
            
            logger.info("Updated logs table with provider_type")
        
        await db.commit()
        logger.info("Database migration completed successfully!")
        
        # Print summary
        logger.info("=" * 60)
        logger.info("Migration Summary:")
        logger.info(f"  - Migrated {migrated_count} accounts")
        logger.info(f"  - Skipped {skipped_count} accounts")
        logger.info(f"  - Removed channels table (backed up to channels_backup)")
        logger.info(f"  - Updated logs table with provider_type")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        await db.rollback()
        raise

async def create_new_schema(db):
    """Create new schema directly without migration"""
    logger.info("Creating new provider-based schema...")
    
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
    
    # Update logs table
    async with db.execute("PRAGMA table_info(logs)") as cursor:
        log_columns = await cursor.fetchall()
        log_column_names = [col[1] for col in log_columns]
    
    if "provider_type" not in log_column_names:
        await db.execute("ALTER TABLE logs ADD COLUMN provider_type TEXT")
    
    await db.commit()
    logger.info("New schema created successfully")

async def rollback_migration():
    """Rollback migration (restore from backup)"""
    db = await get_db()
    
    logger.info("Rolling back migration...")
    
    try:
        # Check if backup exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='channels_backup'"
        ) as cursor:
            backup_exists = await cursor.fetchone() is not None
        
        if not backup_exists:
            logger.error("No backup found, cannot rollback")
            return
        
        # Restore channels table
        await db.execute("CREATE TABLE channels AS SELECT * FROM channels_backup")
        
        # Recreate old accounts table structure
        # This is complex and may lose data - better to restore from full database backup
        logger.warning("Rollback is partial - recommend restoring from full database backup")
        
        await db.commit()
        logger.info("Rollback completed")
        
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        await db.rollback()
        raise

if __name__ == "__main__":
    # Run migration
    asyncio.run(migrate_database())
