"""Token model for API key management"""
import secrets
import time
from typing import Optional, List
from .database import get_db


class Token:
    """Token model with advanced features"""
    
    def __init__(self, row: dict):
        self.id = row["id"]
        self.user_id = row["user_id"]
        self.key = row["key"]
        self.name = row.get("name", "")
        self.status = row["status"]  # 1:enabled 2:disabled 3:exhausted 4:expired
        self.unlimited_quota = row["unlimited_quota"]
        self.remain_quota = row.get("remain_quota", 0) or 0
        self.used_quota = row.get("used_quota", 0) or 0
        self.created_time = row["created_time"]
        self.accessed_time = row.get("accessed_time", 0) or 0
        self.expired_time = row["expired_time"]  # -1 means never expired
        self.model_limits_enabled = row["model_limits_enabled"]
        self.model_limits = row.get("model_limits", "")
        self.ip_whitelist = row.get("ip_whitelist", "")
        self.group = row.get("group", "default")
        self.cross_group_retry = row.get("cross_group_retry", 0) or 0
        
        # Token statistics
        self.input_tokens = row.get("input_tokens", 0) or 0
        self.output_tokens = row.get("output_tokens", 0) or 0
        self.total_tokens = row.get("total_tokens", 0) or 0
        self.request_count = row.get("request_count", 0) or 0
    
    def is_valid(self) -> tuple[bool, str]:
        """Check if token is valid"""
        if self.status != 1:
            status_msg = {
                2: "Token is disabled",
                3: "Token quota exhausted",
                4: "Token expired"
            }
            return False, status_msg.get(self.status, "Token is not available")
        
        # Check expiration
        if self.expired_time != -1 and self.expired_time < int(time.time()):
            return False, "Token expired"
        
        # Check quota
        if not self.unlimited_quota and self.remain_quota <= 0:
            return False, "Token quota exhausted"
        
        return True, ""
    
    def has_model_access(self, model: str) -> bool:
        """Check if token has access to the model"""
        if not self.model_limits_enabled:
            return True
        
        if not self.model_limits:
            return True
        
        allowed_models = [m.strip() for m in self.model_limits.split(",") if m.strip()]
        return model in allowed_models
    
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is in whitelist"""
        if not self.ip_whitelist:
            return True
        
        allowed_ips = [i.strip() for i in self.ip_whitelist.split("\n") if i.strip()]
        return ip in allowed_ips
    
    def get_allowed_models(self) -> List[str]:
        """Get list of allowed models"""
        if not self.model_limits_enabled or not self.model_limits:
            return []
        return [m.strip() for m in self.model_limits.split(",") if m.strip()]


async def get_token_by_key(key: str) -> Optional[Token]:
    """Get token by key"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM tokens WHERE key = ?",
        (key,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return Token(dict(row))
    return None


async def get_all_tokens(user_id: int = None) -> List[Token]:
    """Get all tokens, optionally filtered by user_id"""
    db = await get_db()
    if user_id:
        query = "SELECT * FROM tokens WHERE user_id = ? ORDER BY id DESC"
        params = (user_id,)
    else:
        query = "SELECT * FROM tokens ORDER BY id DESC"
        params = ()
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [Token(dict(row)) for row in rows]


async def create_token(
    name: str = "",
    unlimited_quota: bool = False,
    remain_quota: int = 0,
    expired_time: int = -1,
    model_limits_enabled: bool = False,
    model_limits: str = "",
    ip_whitelist: str = "",
    group: str = "default",
    cross_group_retry: bool = False,
    user_id: int = 0
) -> tuple[int, str]:
    """Create a new token"""
    db = await get_db()
    key = f"sk-{secrets.token_hex(24)}"
    created_time = int(time.time())
    
    cursor = await db.execute(
        """INSERT INTO tokens 
           (user_id, key, name, status, unlimited_quota, remain_quota, 
            created_time, expired_time, model_limits_enabled, model_limits, 
            ip_whitelist, "group", cross_group_retry)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, key, name, unlimited_quota, remain_quota, created_time, 
         expired_time, model_limits_enabled, model_limits, ip_whitelist, group, cross_group_retry)
    )
    await db.commit()
    return cursor.lastrowid, key


async def update_token(token_id: int, **kwargs) -> bool:
    """Update token fields"""
    db = await get_db()
    
    # Handle special fields that need quotes
    fields = []
    values = []
    for k, v in kwargs.items():
        if k == "group":
            fields.append('"group" = ?')
        else:
            fields.append(f"{k} = ?")
        values.append(v)
    
    values.append(token_id)
    query = f"UPDATE tokens SET {', '.join(fields)} WHERE id = ?"
    
    await db.execute(query, values)
    await db.commit()
    return True


async def delete_token(token_id: int) -> bool:
    """Delete a token"""
    db = await get_db()
    await db.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
    await db.commit()
    return True


async def update_token_quota(token_id: int, used: int):
    """Update token quota usage"""
    db = await get_db()
    await db.execute(
        """UPDATE tokens 
           SET used_quota = used_quota + ?,
               remain_quota = remain_quota - ?,
               accessed_time = ?
           WHERE id = ?""",
        (used, used, int(time.time()), token_id)
    )
    await db.commit()


async def add_token_usage(token_id: int, input_tokens: int, output_tokens: int):
    """Add token usage statistics"""
    db = await get_db()
    await db.execute(
        """UPDATE tokens 
           SET input_tokens = input_tokens + ?,
               output_tokens = output_tokens + ?,
               total_tokens = total_tokens + ?,
               request_count = request_count + 1,
               accessed_time = ?
           WHERE id = ?""",
        (input_tokens, output_tokens, input_tokens + output_tokens, 
         int(time.time()), token_id)
    )
    await db.commit()


async def check_and_update_token_status():
    """Check and update expired tokens status"""
    db = await get_db()
    current_time = int(time.time())
    
    # Update expired tokens
    await db.execute(
        """UPDATE tokens 
           SET status = 4 
           WHERE status = 1 
           AND expired_time != -1 
           AND expired_time < ?""",
        (current_time,)
    )
    
    # Update exhausted tokens
    await db.execute(
        """UPDATE tokens 
           SET status = 3 
           WHERE status = 1 
           AND unlimited_quota = 0 
           AND remain_quota <= 0""",
    )
    
    await db.commit()
