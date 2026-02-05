import json
from typing import Optional
from .database import get_db

class Channel:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.name = row["name"]
        self.type = row["type"]
        self.models = json.loads(row["models"]) if isinstance(row["models"], str) else row["models"]
        self.model_mapping = json.loads(row["model_mapping"] or "{}") if isinstance(row.get("model_mapping"), str) else (row.get("model_mapping") or {})
        self.priority = row["priority"]
        self.weight = row["weight"]
        self.enabled = row["enabled"]
    
    def get_mapped_model(self, model: str) -> str:
        return self.model_mapping.get(model, model)

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
                         models: list, model_mapping: dict = None, 
                         priority: int = 0, weight: int = 1) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO channels (name, type, models, model_mapping, priority, weight)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, type_, json.dumps(models), 
         json.dumps(model_mapping or {}), priority, weight)
    )
    await db.commit()
    return cursor.lastrowid

async def update_channel(id_: int, **kwargs) -> bool:
    db = await get_db()
    if "models" in kwargs and isinstance(kwargs["models"], list):
        kwargs["models"] = json.dumps(kwargs["models"])
    if "model_mapping" in kwargs and isinstance(kwargs["model_mapping"], dict):
        kwargs["model_mapping"] = json.dumps(kwargs["model_mapping"])
    
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
