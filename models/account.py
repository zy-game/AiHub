import random
from typing import Optional
from .database import get_db

class Account:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.channel_id = row["channel_id"]
        self.name = row.get("name", "")
        self.api_key = row["api_key"]
        self.usage = row.get("usage", 0) or 0
        self.limit = row.get("limit", 0) or 0
        self.input_tokens = row.get("input_tokens", 0) or 0
        self.output_tokens = row.get("output_tokens", 0) or 0
        self.total_tokens = row.get("total_tokens", 0) or 0
        self.last_used_at = row.get("last_used_at")
        self.enabled = row.get("enabled", 1)

async def get_available_account(channel_id: int) -> Optional[Account]:
    """Get an available account from channel's pool (random selection)"""
    db = await get_db()
    async with db.execute(
        """SELECT * FROM accounts 
           WHERE channel_id = ? AND enabled = 1
           ORDER BY RANDOM()
           LIMIT 1""",
        (channel_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return Account(dict(row))

async def add_account_credit_usage(account_id: int, delta: int):
    """Add credit usage to an account (Kiro only)"""
    db = await get_db()
    await db.execute(
        "UPDATE accounts SET usage = usage + ?, last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
        (delta, account_id)
    )
    await db.commit()

async def add_account_tokens(account_id: int, input_tokens: int, output_tokens: int):
    """Add token usage to an account"""
    db = await get_db()
    await db.execute(
        """UPDATE accounts 
           SET input_tokens = input_tokens + ?, 
               output_tokens = output_tokens + ?,
               total_tokens = total_tokens + ?,
               last_used_at = CURRENT_TIMESTAMP 
           WHERE id = ?""",
        (input_tokens, output_tokens, input_tokens + output_tokens, account_id)
    )
    await db.commit()

async def get_accounts_by_channel(channel_id: int):
    """Get all accounts for a channel"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM accounts WHERE channel_id = ? ORDER BY id DESC",
        (channel_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [Account(dict(row)) for row in rows]

async def get_all_accounts_with_channels():
    db = await get_db()
    async with db.execute(
        """SELECT a.*, c.name as channel_name, c.type as channel_type
           FROM accounts a
           JOIN channels c ON a.channel_id = c.id
           ORDER BY a.id DESC"""
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def add_kiro_points_usage(account_id: int, delta: int, updated_at: str):
    """Deprecated: use add_account_credit_usage instead"""
    await add_account_credit_usage(account_id, delta)

async def create_account(channel_id: int, api_key: str, name: str = None) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO accounts (channel_id, api_key, name) VALUES (?, ?, ?)",
        (channel_id, api_key, name)
    )
    await db.commit()
    return cursor.lastrowid

async def batch_create_accounts(channel_id: int, accounts: list) -> int:
    """Batch import accounts: [{"api_key": "xxx", "name": "optional"}]"""
    db = await get_db()
    count = 0
    for acc in accounts:
        api_key = acc.get("api_key", "").strip()
        if not api_key:
            continue
        await db.execute(
            "INSERT INTO accounts (channel_id, api_key, name) VALUES (?, ?, ?)",
            (channel_id, api_key, acc.get("name", ""))
        )
        count += 1
    await db.commit()
    return count

async def update_account(id_: int, **kwargs) -> bool:
    db = await get_db()
    # Handle SQL reserved word 'limit'
    fields = []
    for k in kwargs.keys():
        if k == "limit":
            fields.append('"limit" = ?')
        else:
            fields.append(f"{k} = ?")
    fields_str = ", ".join(fields)
    values = list(kwargs.values()) + [id_]
    await db.execute(f"UPDATE accounts SET {fields_str} WHERE id = ?", values)
    await db.commit()
    return True

async def delete_account(id_: int) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM accounts WHERE id = ?", (id_,))
    await db.commit()
    return True

async def delete_accounts_by_channel(channel_id: int) -> int:
    db = await get_db()
    cursor = await db.execute("DELETE FROM accounts WHERE channel_id = ?", (channel_id,))
    await db.commit()
    return cursor.rowcount

async def get_account_usage_totals(channel_id: int) -> dict:
    """Get total usage and limit for all accounts in a channel"""
    db = await get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(usage), 0) as used, COALESCE(SUM(\"limit\"), 0) as limit_value FROM accounts WHERE channel_id = ?",
        (channel_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return {"used": row["used"], "limit": row["limit_value"]}
