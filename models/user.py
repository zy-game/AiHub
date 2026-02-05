import secrets
from typing import Optional
from .database import get_db

class User:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.api_key = row["api_key"]
        self.name = row["name"]
        self.quota = row["quota"]
        self.used_quota = row["used_quota"]
        self.input_tokens = row.get("input_tokens", 0) or 0
        self.output_tokens = row.get("output_tokens", 0) or 0
        self.total_tokens = row.get("total_tokens", 0) or 0
        self.enabled = row["enabled"]
    
    def has_quota(self) -> bool:
        return self.quota == -1 or self.used_quota < self.quota

async def get_user_by_api_key(api_key: str) -> Optional[User]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE api_key = ? AND enabled = 1",
        (api_key,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return User(dict(row))
    return None

async def get_user_by_id(user_id: int) -> Optional[User]:
    """Get user by ID"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return User(dict(row))
    return None

async def get_all_users():
    db = await get_db()
    async with db.execute("SELECT * FROM users ORDER BY id DESC") as cursor:
        rows = await cursor.fetchall()
        return [User(dict(row)) for row in rows]

async def create_user(name: str = None, quota: int = -1) -> tuple[int, str]:
    db = await get_db()
    api_key = f"sk-{secrets.token_hex(24)}"
    cursor = await db.execute(
        "INSERT INTO users (api_key, name, quota) VALUES (?, ?, ?)",
        (api_key, name, quota)
    )
    await db.commit()
    return cursor.lastrowid, api_key

async def update_user(id_: int, **kwargs) -> bool:
    db = await get_db()
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [id_]
    await db.execute(f"UPDATE users SET {fields} WHERE id = ?", values)
    await db.commit()
    return True

async def delete_user(id_: int) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM users WHERE id = ?", (id_,))
    await db.commit()
    return True

async def update_user_quota(user_id: int, tokens: int):
    db = await get_db()
    await db.execute(
        "UPDATE users SET used_quota = used_quota + ? WHERE id = ?",
        (tokens, user_id)
    )
    await db.commit()

async def add_user_tokens(user_id: int, input_tokens: int, output_tokens: int):
    """Add token usage to a user"""
    db = await get_db()
    await db.execute(
        """UPDATE users 
           SET input_tokens = input_tokens + ?, 
               output_tokens = output_tokens + ?,
               total_tokens = total_tokens + ?
           WHERE id = ?""",
        (input_tokens, output_tokens, input_tokens + output_tokens, user_id)
    )
    await db.commit()
