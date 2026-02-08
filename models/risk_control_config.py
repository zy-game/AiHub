"""Risk Control Configuration Model"""
from models.database import get_db
from utils.logger import logger


async def get_risk_control_config() -> dict:
    """Get risk control configuration from database"""
    db = await get_db()
    async with db.execute("SELECT * FROM risk_control_config WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        if not row:
            return {}
        
        return {
            "proxy_pool": {
                "enabled": bool(row["proxy_pool_enabled"]),
                "strategy": row["proxy_pool_strategy"]
            },
            "rate_limit": {
                "enabled": bool(row["rate_limit_enabled"]),
                "global": {
                    "requests_per_minute": row["rate_limit_global_rpm"],
                    "tokens_per_minute": row["rate_limit_global_tpm"]
                }
            },
            "health_monitor": {
                "enabled": bool(row["health_monitor_enabled"]),
                "check_interval": row["health_monitor_interval"]
            },
            "fingerprint": {
                "enabled": bool(row["fingerprint_enabled"])
            }
        }


async def update_risk_control_config(config: dict) -> bool:
    """Update risk control configuration in database"""
    try:
        db = await get_db()
        
        updates = []
        params = []
        
        if "proxy_pool" in config:
            if "enabled" in config["proxy_pool"]:
                updates.append("proxy_pool_enabled = ?")
                params.append(1 if config["proxy_pool"]["enabled"] else 0)
            if "strategy" in config["proxy_pool"]:
                updates.append("proxy_pool_strategy = ?")
                params.append(config["proxy_pool"]["strategy"])
        
        if "rate_limit" in config:
            if "enabled" in config["rate_limit"]:
                updates.append("rate_limit_enabled = ?")
                params.append(1 if config["rate_limit"]["enabled"] else 0)
            if "global_rpm" in config["rate_limit"]:
                updates.append("rate_limit_global_rpm = ?")
                params.append(config["rate_limit"]["global_rpm"])
            if "global_tpm" in config["rate_limit"]:
                updates.append("rate_limit_global_tpm = ?")
                params.append(config["rate_limit"]["global_tpm"])
        
        if "health_monitor" in config:
            if "enabled" in config["health_monitor"]:
                updates.append("health_monitor_enabled = ?")
                params.append(1 if config["health_monitor"]["enabled"] else 0)
            if "interval" in config["health_monitor"]:
                updates.append("health_monitor_interval = ?")
                params.append(config["health_monitor"]["interval"])
        
        if "fingerprint" in config:
            if "enabled" in config["fingerprint"]:
                updates.append("fingerprint_enabled = ?")
                params.append(1 if config["fingerprint"]["enabled"] else 0)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE risk_control_config SET {', '.join(updates)} WHERE id = 1"
            await db.execute(sql, params)
            await db.commit()
            logger.info(f"Risk control config updated in database: {config}")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Failed to update risk control config: {e}")
        return False
