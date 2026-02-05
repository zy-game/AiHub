import json
from typing import Optional
from .database import get_db

class Channel:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.name = row["name"]
        self.type = row["type"]
        self.priority = row["priority"]
        self.weight = row["weight"]
        self.enabled = row["enabled"]
        self.avg_response_time = row.get("avg_response_time", 0) or 0
        self.total_requests = row.get("total_requests", 0) or 0
        self.failed_requests = row.get("failed_requests", 0) or 0
    
    def supports_model(self, model: str) -> bool:
        """Check if this channel supports the given model"""
        from providers import get_provider
        provider = get_provider(self.type)
        return provider.supports_model(model) if provider else False
    
    def get_success_rate(self) -> float:
        """Get success rate (0-1)"""
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.failed_requests / self.total_requests)

async def get_channel_by_model(model: str) -> Optional[Channel]:
    db = await get_db()
    async with db.execute(
        """SELECT * FROM channels 
           WHERE enabled = 1 AND models LIKE ? 
           ORDER BY priority DESC, weight DESC 
           LIMIT 1""",
        (f'%"{model}"%',)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return Channel(dict(row))
    return None

async def get_all_channels():
    db = await get_db()
    async with db.execute("SELECT * FROM channels ORDER BY priority DESC") as cursor:
        rows = await cursor.fetchall()
        return [Channel(dict(row)) for row in rows]

async def get_channel_by_id(channel_id: int) -> Optional[Channel]:
    db = await get_db()
    async with db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return Channel(dict(row))
    return None

async def create_channel(name: str, type_: str,
                         priority: int = 0, weight: int = 1) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO channels (name, type, priority, weight)
           VALUES (?, ?, ?, ?)""",
        (name, type_, priority, weight)
    )
    await db.commit()
    return cursor.lastrowid

async def update_channel(id_: int, **kwargs) -> bool:
    db = await get_db()
    
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [id_]
    await db.execute(f"UPDATE channels SET {fields} WHERE id = ?", values)
    await db.commit()
    return True

async def delete_channel(id_: int) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM channels WHERE id = ?", (id_,))
    await db.commit()
    return True

async def update_channel_stats(channel_id: int, response_time_ms: int, success: bool = True):
    """Update channel statistics with response time and success/failure"""
    db = await get_db()
    
    # Get current stats
    async with db.execute(
        "SELECT avg_response_time, total_requests, failed_requests FROM channels WHERE id = ?",
        (channel_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return
        
        current_avg = row[0] or 0
        total_requests = row[1] or 0
        failed_requests = row[2] or 0
    
    # Calculate new average response time (exponential moving average)
    # New avg = 0.9 * old_avg + 0.1 * new_value
    if total_requests == 0:
        new_avg = response_time_ms
    else:
        new_avg = int(0.9 * current_avg + 0.1 * response_time_ms)
    
    # Update stats
    new_total = total_requests + 1
    new_failed = failed_requests + (0 if success else 1)
    
    await db.execute(
        """UPDATE channels 
           SET avg_response_time = ?, total_requests = ?, failed_requests = ?
           WHERE id = ?""",
        (new_avg, new_total, new_failed, channel_id)
    )
    await db.commit()

async def get_channels_by_model(model: str) -> list[Channel]:
    """Get all enabled channels that support the model, ordered by priority and weight"""
    db = await get_db()
    
    # 获取所有启用的渠道
    async with db.execute(
        "SELECT * FROM channels WHERE enabled = 1 ORDER BY priority DESC, weight DESC"
    ) as cursor:
        rows = await cursor.fetchall()
        all_channels = [Channel(dict(row)) for row in rows]
    
    # 动态检查每个渠道是否支持该模型
    supported_channels = [c for c in all_channels if c.supports_model(model)]
    
    return supported_channels
