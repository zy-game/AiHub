"""
Initialize super admin user and initial invite code
"""
import asyncio
from models.auth import create_admin_user, get_user_by_email, create_invite_code
from models.database import get_db
from config import SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, SUPER_ADMIN_NAME, INITIAL_INVITE_CODE
from utils.logger import logger

async def init_super_admin():
    """Initialize super admin user if not exists"""
    try:
        # Check if super admin already exists
        user = await get_user_by_email(SUPER_ADMIN_EMAIL)
        if user:
            logger.info(f"Super admin already exists: {SUPER_ADMIN_EMAIL}")
            return user['id']
        
        # Create super admin
        user_id = await create_admin_user(
            email=SUPER_ADMIN_EMAIL,
            password=SUPER_ADMIN_PASSWORD,
            name=SUPER_ADMIN_NAME,
            role='super_admin'
        )
        
        logger.info("=" * 60)
        logger.info("Super Admin Created Successfully!")
        logger.info("=" * 60)
        logger.info(f"Email: {SUPER_ADMIN_EMAIL}")
        logger.info(f"Password: {SUPER_ADMIN_PASSWORD}")
        logger.info("=" * 60)
        logger.info("IMPORTANT: Please change the password after first login!")
        logger.info("=" * 60)
        
        return user_id
        
    except Exception as e:
        logger.error(f"Failed to initialize super admin: {e}")
        raise

async def init_invite_code():
    """Initialize initial invite code"""
    try:
        db = await get_db()
        
        # Check if initial invite code already exists
        async with db.execute(
            "SELECT id FROM invite_codes WHERE code = ?",
            (INITIAL_INVITE_CODE,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                logger.info(f"Initial invite code already exists: {INITIAL_INVITE_CODE}")
                return
        
        # Get super admin user id
        user = await get_user_by_email(SUPER_ADMIN_EMAIL)
        if not user:
            logger.error("Super admin not found, cannot create initial invite code")
            return
        
        # Create initial invite code
        await db.execute(
            "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
            (INITIAL_INVITE_CODE, user['id'])
        )
        await db.commit()
        
        logger.info("=" * 60)
        logger.info("Initial Invite Code Created!")
        logger.info("=" * 60)
        logger.info(f"Code: {INITIAL_INVITE_CODE}")
        logger.info("=" * 60)
        logger.info("Users can use this code to register")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Failed to initialize invite code: {e}")
        raise

async def init_auth_system():
    """Initialize authentication system"""
    await init_super_admin()
    await init_invite_code()

if __name__ == "__main__":
    asyncio.run(init_auth_system())
