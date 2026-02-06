"""
Database migration: Add user authentication and role-based access control
"""
import asyncio
import aiosqlite
from models.database import get_db
from utils.logger import logger

async def migrate_add_auth_system():
    """Add authentication and RBAC to the database"""
    db = await get_db()
    
    logger.info("Starting authentication system migration...")
    
    try:
        # Check current users table schema
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
        
        # Add new columns to users table
        if "email" not in column_names:
            logger.info("Adding email column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        
        if "password_hash" not in column_names:
            logger.info("Adding password_hash column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        
        if "role" not in column_names:
            logger.info("Adding role column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        
        if "last_login_at" not in column_names:
            logger.info("Adding last_login_at column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP")
        
        if "email_verified" not in column_names:
            logger.info("Adding email_verified column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
        
        if "verification_token" not in column_names:
            logger.info("Adding verification_token column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
        
        # Create sessions table
        logger.info("Creating sessions table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
        
        # Create invite_codes table
        logger.info("Creating invite_codes table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                created_by INTEGER NOT NULL,
                used_by INTEGER,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_invite_codes_code ON invite_codes(code)")
        
        await db.commit()
        
        logger.info("=" * 60)
        logger.info("Authentication system migration completed successfully!")
        logger.info("=" * 60)
        logger.info("New features added:")
        logger.info("  - User email and password authentication")
        logger.info("  - Role-based access control (super_admin, admin, user)")
        logger.info("  - Session management")
        logger.info("  - Email verification")
        logger.info("  - Invite code system")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        await db.rollback()
        raise

if __name__ == "__main__":
    asyncio.run(migrate_add_auth_system())
