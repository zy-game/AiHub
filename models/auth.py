"""
Authentication module for user login, registration, and session management
"""
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from .database import get_db
from utils.logger import logger

class Auth:
    """Authentication utilities"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except:
            return False
    
    @staticmethod
    def generate_session_token() -> str:
        """Generate secure session token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_verification_token() -> str:
        """Generate email verification token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_invite_code() -> str:
        """Generate invite code"""
        return secrets.token_urlsafe(16)

async def get_user_by_email(email: str):
    """Get user by email"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return None

async def register_user(email: str, password: str, name: str, invite_code: str = None) -> Tuple[bool, str, dict]:
    """
    Register a new user
    invite_code is optional - used for marketing/referral tracking
    Returns: (success, message, user_data)
    """
    db = await get_db()
    
    try:
        invite_id = None
        
        # Validate invite code if provided
        if invite_code:
            async with db.execute(
                "SELECT * FROM invite_codes WHERE code = ? AND used_by IS NULL",
                (invite_code,)
            ) as cursor:
                invite = await cursor.fetchone()
                if not invite:
                    return False, "无效或已使用的邀请码", {}
                invite_id = invite[0]  # Get invite code ID
        
        # Check if email already exists
        existing_user = await get_user_by_email(email)
        if existing_user:
            return False, "该邮箱已被注册", {}
        
        # Hash password
        password_hash = Auth.hash_password(password)
        
        # Generate verification token
        verification_token = Auth.generate_verification_token()
        
        # Generate API key for backward compatibility
        import secrets
        api_key = f"sk-{secrets.token_hex(24)}"
        
        # Create user
        cursor = await db.execute(
            """INSERT INTO users (email, password_hash, name, role, email_verified, verification_token, quota, enabled, api_key)
               VALUES (?, ?, ?, 'user', 0, ?, -1, 1, ?)""",
            (email, password_hash, name, verification_token, api_key)
        )
        user_id = cursor.lastrowid
        
        # Mark invite code as used (if provided)
        if invite_code:
            await db.execute(
                "UPDATE invite_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?",
                (user_id, invite_code)
            )
        
        await db.commit()
        
        logger.info(f"New user registered: {email}")
        
        return True, "注册成功，请查收验证邮件", {
            "user_id": user_id,
            "email": email,
            "verification_token": verification_token
        }
        
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        await db.rollback()
        return False, f"注册失败: {str(e)}", {}

async def verify_email(verification_token: str) -> Tuple[bool, str]:
    """Verify user email"""
    db = await get_db()
    
    try:
        async with db.execute(
            "SELECT id FROM users WHERE verification_token = ? AND email_verified = 0",
            (verification_token,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, "无效的验证链接"
        
        user_id = row[0]
        await db.execute(
            "UPDATE users SET email_verified = 1, verification_token = NULL WHERE id = ?",
            (user_id,)
        )
        await db.commit()
        
        logger.info(f"Email verified for user {user_id}")
        return True, "邮箱验证成功"
        
    except Exception as e:
        logger.error(f"Email verification failed: {e}")
        await db.rollback()
        return False, f"验证失败: {str(e)}"

async def login(email: str, password: str) -> Tuple[bool, str, dict]:
    """
    Login user with email and password
    Returns: (success, message, user_data)
    """
    db = await get_db()
    
    try:
        # Find user
        user = await get_user_by_email(email)
        if not user:
            return False, "邮箱或密码错误", {}
        
        # Check if user is enabled
        if not user.get('enabled'):
            return False, "账号已被禁用", {}
        
        # Verify password
        if not Auth.verify_password(password, user.get('password_hash', '')):
            return False, "邮箱或密码错误", {}
        
        # Check email verification
        if not user.get('email_verified'):
            return False, "请先验证邮箱", {}
        
        # Generate session token
        session_token = Auth.generate_session_token()
        expires_at = datetime.now() + timedelta(days=7)
        
        # Create session
        await db.execute(
            "INSERT INTO sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user['id'], session_token, expires_at)
        )
        
        # Update last login time
        await db.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user['id'],)
        )
        
        await db.commit()
        
        logger.info(f"User logged in: {email}")
        
        return True, "登录成功", {
            "session_token": session_token,
            "user_id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "role": user['role']
        }
        
    except Exception as e:
        logger.error(f"Login failed: {e}")
        await db.rollback()
        return False, f"登录失败: {str(e)}", {}

async def logout(session_token: str):
    """Delete session"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
        await db.commit()
        logger.info("User logged out")
    except Exception as e:
        logger.error(f"Logout failed: {e}")

async def verify_session(session_token: str):
    """Verify session and return user"""
    db = await get_db()
    
    try:
        async with db.execute(
            """SELECT u.* FROM users u
               JOIN sessions s ON u.id = s.user_id
               WHERE s.session_token = ? AND s.expires_at > CURRENT_TIMESTAMP AND u.enabled = 1""",
            (session_token,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None
    except Exception as e:
        logger.error(f"Session verification failed: {e}")
        return None

async def create_admin_user(email: str, password: str, name: str, role: str = 'admin'):
    """Create admin user (super_admin or admin)"""
    db = await get_db()
    
    try:
        # Check if user already exists
        existing_user = await get_user_by_email(email)
        if existing_user:
            logger.info(f"Admin user already exists: {email}")
            return existing_user['id']
        
        # Hash password
        password_hash = Auth.hash_password(password)
        
        # Generate API key for backward compatibility
        import secrets
        api_key = f"sk-{secrets.token_hex(24)}"
        
        # Create user (admin users don't need email verification)
        cursor = await db.execute(
            """INSERT INTO users (email, password_hash, name, role, email_verified, quota, enabled, api_key)
               VALUES (?, ?, ?, ?, 1, -1, 1, ?)""",
            (email, password_hash, name, role, api_key)
        )
        user_id = cursor.lastrowid
        
        await db.commit()
        
        logger.info(f"Admin user created: {email} (role: {role})")
        return user_id
        
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        await db.rollback()
        raise

async def create_invite_code(created_by: int) -> str:
    """Create a new invite code"""
    db = await get_db()
    
    try:
        code = Auth.generate_invite_code()
        await db.execute(
            "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
            (code, created_by)
        )
        await db.commit()
        
        logger.info(f"Invite code created by user {created_by}")
        return code
        
    except Exception as e:
        logger.error(f"Failed to create invite code: {e}")
        await db.rollback()
        raise

async def get_invite_codes(created_by: int = None):
    """Get invite codes"""
    db = await get_db()
    
    try:
        if created_by:
            async with db.execute(
                """SELECT ic.*, u.email as used_by_email 
                   FROM invite_codes ic
                   LEFT JOIN users u ON ic.used_by = u.id
                   WHERE ic.created_by = ?
                   ORDER BY ic.created_at DESC""",
                (created_by,)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT ic.*, u.email as used_by_email 
                   FROM invite_codes ic
                   LEFT JOIN users u ON ic.used_by = u.id
                   ORDER BY ic.created_at DESC"""
            ) as cursor:
                rows = await cursor.fetchall()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"Failed to get invite codes: {e}")
        return []

async def change_password(user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
    """Change user password"""
    db = await get_db()
    
    try:
        # Get current password hash
        async with db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, "用户不存在"
        
        # Verify old password
        if not Auth.verify_password(old_password, row[0]):
            return False, "原密码错误"
        
        # Hash new password
        new_password_hash = Auth.hash_password(new_password)
        
        # Update password
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user_id)
        )
        await db.commit()
        
        logger.info(f"Password changed for user {user_id}")
        return True, "密码修改成功"
        
    except Exception as e:
        logger.error(f"Failed to change password: {e}")
        await db.rollback()
        return False, f"密码修改失败: {str(e)}"
