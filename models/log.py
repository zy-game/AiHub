from datetime import datetime, timedelta
from .database import get_db

async def create_log(user_id: int, channel_id: int, model: str, 
                     input_tokens: int = 0, output_tokens: int = 0,
                     duration_ms: int = 0, status: int = 200, error: str = None,
                     cache_read_tokens: int = 0, cache_creation_tokens: int = 0,
                     prompt_cache_key: str = None, provider_type: str = None,
                     context_compressed: int = 0, original_tokens: int = 0, compressed_tokens: int = 0):
    db = await get_db()
    await db.execute(
        """INSERT INTO logs (user_id, channel_id, model, input_tokens, output_tokens, 
           duration_ms, status, error, cache_read_tokens, cache_creation_tokens, prompt_cache_key, provider_type,
           context_compressed, original_tokens, compressed_tokens) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, channel_id, model, input_tokens, output_tokens, duration_ms, status, error,
         cache_read_tokens, cache_creation_tokens, prompt_cache_key, provider_type,
         context_compressed, original_tokens, compressed_tokens)
    )
    await db.commit()

async def get_logs(limit: int = 100, offset: int = 0):
    db = await get_db()
    async with db.execute(
        """SELECT l.*, u.name as user_name 
           FROM logs l 
           LEFT JOIN users u ON l.user_id = u.id
           ORDER BY l.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]

async def get_stats(days: int = 7, user_id: int = None):
    db = await get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Build query based on whether user_id is provided
    if user_id:
        query = """SELECT COUNT(*) as total_requests,
                  SUM(input_tokens) as total_input_tokens,
                  SUM(output_tokens) as total_output_tokens,
                  SUM(cache_read_tokens) as total_cache_read_tokens,
                  SUM(cache_creation_tokens) as total_cache_creation_tokens,
                  AVG(duration_ms) as avg_duration,
                  SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as error_count
           FROM logs WHERE created_at >= ? AND user_id = ?"""
        params = (since, user_id)
    else:
        query = """SELECT COUNT(*) as total_requests,
                  SUM(input_tokens) as total_input_tokens,
                  SUM(output_tokens) as total_output_tokens,
                  SUM(cache_read_tokens) as total_cache_read_tokens,
                  SUM(cache_creation_tokens) as total_cache_creation_tokens,
                  AVG(duration_ms) as avg_duration,
                  SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as error_count
           FROM logs WHERE created_at >= ?"""
        params = (since,)
    
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()
        result = dict(row) if row else {}
        
        # Calculate cache hit rate
        if result:
            total_input = result.get("total_input_tokens", 0) or 0
            cache_read = result.get("total_cache_read_tokens", 0) or 0
            if total_input > 0:
                result["cache_hit_rate"] = round((cache_read / total_input) * 100, 2)
            else:
                result["cache_hit_rate"] = 0.0
        
        return result

async def get_model_stats(days: int = 7, user_id: int = None):
    db = await get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Build query based on whether user_id is provided
    if user_id:
        query = """SELECT model, COUNT(*) as count, 
                  SUM(input_tokens + output_tokens) as total_tokens,
                  SUM(cache_read_tokens) as cache_read_tokens,
                  SUM(cache_creation_tokens) as cache_creation_tokens
           FROM logs WHERE created_at >= ? AND user_id = ?
           GROUP BY model ORDER BY count DESC"""
        params = (since, user_id)
    else:
        query = """SELECT model, COUNT(*) as count, 
                  SUM(input_tokens + output_tokens) as total_tokens,
                  SUM(cache_read_tokens) as cache_read_tokens,
                  SUM(cache_creation_tokens) as cache_creation_tokens
           FROM logs WHERE created_at >= ?
           GROUP BY model ORDER BY count DESC"""
        params = (since,)
    
    async with db.execute(query, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]

async def get_channel_token_usage(channel_id: int) -> dict:
    """Get total token usage for a channel"""
    db = await get_db()
    async with db.execute(
        """SELECT COALESCE(SUM(input_tokens), 0) as input_tokens,
                  COALESCE(SUM(output_tokens), 0) as output_tokens,
                  COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens
           FROM logs WHERE channel_id = ?""",
        (channel_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

async def get_user_token_usage(user_id: int) -> dict:
    """Get total token usage for a user"""
    db = await get_db()
    async with db.execute(
        """SELECT COALESCE(SUM(input_tokens), 0) as input_tokens,
                  COALESCE(SUM(output_tokens), 0) as output_tokens,
                  COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                  COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                  COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
                  COUNT(*) as request_count
           FROM logs WHERE user_id = ?""",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {
            "input_tokens": 0, 
            "output_tokens": 0, 
            "total_tokens": 0, 
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "request_count": 0
        }

async def get_hourly_stats(days: int = 7, user_id: int = None):
    """Get hourly request and token statistics"""
    db = await get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Build query based on whether user_id is provided
    if user_id:
        query = """SELECT 
                strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(input_tokens + output_tokens) as total_tokens,
                SUM(cache_read_tokens) as cache_read_tokens,
                SUM(cache_creation_tokens) as cache_creation_tokens
           FROM logs 
           WHERE created_at >= ? AND user_id = ?
           GROUP BY hour
           ORDER BY hour"""
        params = (since, user_id)
    else:
        query = """SELECT 
                strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(input_tokens + output_tokens) as total_tokens,
                SUM(cache_read_tokens) as cache_read_tokens,
                SUM(cache_creation_tokens) as cache_creation_tokens
           FROM logs 
           WHERE created_at >= ?
           GROUP BY hour
           ORDER BY hour"""
        params = (since,)
    
    async with db.execute(query, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]

async def get_channel_stats():
    """Get statistics for all providers"""
    from providers import get_all_providers
    
    db = await get_db()
    providers = get_all_providers()
    result = []
    
    for name, provider in providers.items():
        # Get account statistics for this provider
        async with db.execute(
            """SELECT 
                    COUNT(DISTINCT id) as total_accounts,
                    COUNT(DISTINCT CASE WHEN enabled = 1 THEN id END) as active_accounts,
                    COALESCE(SUM(total_tokens), 0) as total_tokens
               FROM accounts
               WHERE provider_type = ?""",
            (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result.append({
                    "id": name,
                    "name": name,
                    "type": name,
                    "enabled": provider.enabled,
                    "total_accounts": row["total_accounts"] or 0,
                    "active_accounts": row["active_accounts"] or 0,
                    "total_tokens": row["total_tokens"] or 0
                })
    
    # Sort by total_tokens descending
    result.sort(key=lambda x: x["total_tokens"], reverse=True)
    return result

async def get_top_users(limit: int = 10):
    """Get top users by token usage"""
    db = await get_db()
    async with db.execute(
        """SELECT 
                id,
                name,
                total_tokens,
                input_tokens,
                output_tokens
           FROM users
           WHERE total_tokens > 0
           ORDER BY total_tokens DESC
           LIMIT ?""",
        (limit,)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
