"""Cache configuration model"""
from .database import get_db

async def get_cache_config():
    """Get cache configuration"""
    db = await get_db()
    async with db.execute("SELECT * FROM cache_config WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {
            "prompt_cache_enabled": 1,
            "context_compression_enabled": 0,
            "context_compression_threshold": 8000,
            "context_compression_target": 4000,
            "context_compression_strategy": "sliding_window"
        }

async def update_cache_config(config: dict):
    """Update cache configuration"""
    db = await get_db()
    
    fields = []
    values = []
    
    if "prompt_cache_enabled" in config:
        fields.append("prompt_cache_enabled = ?")
        values.append(config["prompt_cache_enabled"])
    
    if "context_compression_enabled" in config:
        fields.append("context_compression_enabled = ?")
        values.append(config["context_compression_enabled"])
    
    if "context_compression_threshold" in config:
        fields.append("context_compression_threshold = ?")
        values.append(config["context_compression_threshold"])
    
    if "context_compression_target" in config:
        fields.append("context_compression_target = ?")
        values.append(config["context_compression_target"])
    
    if "context_compression_strategy" in config:
        fields.append("context_compression_strategy = ?")
        values.append(config["context_compression_strategy"])
    
    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE cache_config SET {', '.join(fields)} WHERE id = 1"
        await db.execute(query, values)
        await db.commit()
