import random
from typing import Optional
from .database import get_db

class Account:
    def __init__(self, row: dict):
        self.id = row["id"]
        # Support both old (channel_id) and new (provider_type) schema
        self.provider_type = row.get("provider_type") or row.get("channel_id")
        self.channel_id = self.provider_type  # Backward compatibility
        self.name = row.get("name", "")
        self.api_key = row["api_key"]
        self.usage = row.get("usage", 0) or 0
        self.limit = row.get("limit", 0) or 0
        self.input_tokens = row.get("input_tokens", 0) or 0
        self.output_tokens = row.get("output_tokens", 0) or 0
        self.total_tokens = row.get("total_tokens", 0) or 0
        self.last_used_at = row.get("last_used_at")
        self.enabled = row.get("enabled", 1)
        self.created_by = row.get("created_by")  # User ID who created this account

async def get_available_account(provider_type: str) -> Optional[Account]:
    """Get an available account from provider's pool (random selection)"""
    db = await get_db()
    
    # Try new schema first (provider_type column)
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        # New schema
        async with db.execute(
            """SELECT * FROM accounts 
               WHERE provider_type = ? AND enabled = 1
               ORDER BY RANDOM()
               LIMIT 1""",
            (provider_type,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Account(dict(row))
    else:
        # Old schema - provider_type is actually channel_id (integer)
        # This is for backward compatibility during migration
        async with db.execute(
            """SELECT * FROM accounts 
               WHERE channel_id = ? AND enabled = 1
               ORDER BY RANDOM()
               LIMIT 1""",
            (provider_type,)
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

async def get_accounts_by_provider(provider_type: str):
    """Get all accounts for a provider"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        async with db.execute(
            "SELECT * FROM accounts WHERE provider_type = ? ORDER BY id DESC",
            (provider_type,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [Account(dict(row)) for row in rows]
    else:
        # Old schema compatibility
        async with db.execute(
            "SELECT * FROM accounts WHERE channel_id = ? ORDER BY id DESC",
            (provider_type,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [Account(dict(row)) for row in rows]

# Backward compatibility alias
async def get_accounts_by_channel(channel_id):
    """Deprecated: use get_accounts_by_provider instead"""
    return await get_accounts_by_provider(channel_id)

async def get_all_accounts_with_providers():
    """Get all accounts with their provider information"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        # New schema - no join needed
        async with db.execute(
            "SELECT *, provider_type as channel_type FROM accounts ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                row_dict = dict(row)
                row_dict["channel_name"] = row_dict["provider_type"]  # Use provider_type as name
                result.append(row_dict)
            return result
    else:
        # Old schema - join with channels table
        async with db.execute(
            """SELECT a.*, c.name as channel_name, c.type as channel_type
               FROM accounts a
               JOIN channels c ON a.channel_id = c.id
               ORDER BY a.id DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

# Backward compatibility alias
async def get_all_accounts_with_channels():
    """Deprecated: use get_all_accounts_with_providers instead"""
    return await get_all_accounts_with_providers()

async def add_kiro_points_usage(account_id: int, delta: int, updated_at: str):
    """Deprecated: use add_account_credit_usage instead"""
    await add_account_credit_usage(account_id, delta)

async def create_account(provider_type: str, api_key: str, name: str = None, created_by: int = None) -> int:
    """Create an account for a provider"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        if "created_by" in column_names:
            cursor = await db.execute(
                "INSERT INTO accounts (provider_type, api_key, name, created_by) VALUES (?, ?, ?, ?)",
                (provider_type, api_key, name, created_by)
            )
        else:
            cursor = await db.execute(
                "INSERT INTO accounts (provider_type, api_key, name) VALUES (?, ?, ?)",
                (provider_type, api_key, name)
            )
    else:
        # Old schema - provider_type is channel_id
        cursor = await db.execute(
            "INSERT INTO accounts (channel_id, api_key, name) VALUES (?, ?, ?)",
            (provider_type, api_key, name)
        )
    await db.commit()
    return cursor.lastrowid

async def batch_create_accounts(provider_type: str, accounts: list, created_by: int = None) -> int:
    """Batch import accounts: [{"api_key": "xxx", "name": "optional"}]"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    count = 0
    for acc in accounts:
        api_key = acc.get("api_key", "").strip()
        if not api_key:
            continue
        
        if "provider_type" in column_names:
            if "created_by" in column_names:
                await db.execute(
                    "INSERT INTO accounts (provider_type, api_key, name, created_by) VALUES (?, ?, ?, ?)",
                    (provider_type, api_key, acc.get("name", ""), created_by)
                )
            else:
                await db.execute(
                    "INSERT INTO accounts (provider_type, api_key, name) VALUES (?, ?, ?)",
                    (provider_type, api_key, acc.get("name", ""))
                )
        else:
            await db.execute(
                "INSERT INTO accounts (channel_id, api_key, name) VALUES (?, ?, ?)",
                (provider_type, api_key, acc.get("name", ""))
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

async def delete_accounts_by_provider(provider_type: str) -> int:
    """Delete all accounts for a provider"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        cursor = await db.execute("DELETE FROM accounts WHERE provider_type = ?", (provider_type,))
    else:
        cursor = await db.execute("DELETE FROM accounts WHERE channel_id = ?", (provider_type,))
    
    await db.commit()
    return cursor.rowcount

# Backward compatibility alias
async def delete_accounts_by_channel(channel_id):
    """Deprecated: use delete_accounts_by_provider instead"""
    return await delete_accounts_by_provider(channel_id)

async def get_account_usage_totals(provider_type: str) -> dict:
    """Get total usage and limit for all accounts of a provider"""
    db = await get_db()
    
    # Check schema
    async with db.execute("PRAGMA table_info(accounts)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
    
    if "provider_type" in column_names:
        async with db.execute(
            "SELECT COALESCE(SUM(usage), 0) as used, COALESCE(SUM(\"limit\"), 0) as limit_value FROM accounts WHERE provider_type = ?",
            (provider_type,)
        ) as cursor:
            row = await cursor.fetchone()
            return {"used": row["used"], "limit": row["limit_value"]}
    else:
        async with db.execute(
            "SELECT COALESCE(SUM(usage), 0) as used, COALESCE(SUM(\"limit\"), 0) as limit_value FROM accounts WHERE channel_id = ?",
            (provider_type,)
        ) as cursor:
            row = await cursor.fetchone()
            return {"used": row["used"], "limit": row["limit_value"]}
