"""
风控系统管理API
"""
from aiohttp import web
from utils.logger import logger
from utils.risk_control import get_risk_control_system
from utils.proxy_manager import get_proxy_pool, ProxyConfig, ProxyProtocol
from utils.rate_limiter import get_rate_limiter, init_rate_limiter, RateLimitConfig
from utils.health_monitor import get_health_monitor, init_health_monitor
from models.risk_control_config import get_risk_control_config, update_risk_control_config


async def api_risk_control_status(request: web.Request):
    """获取风控系统状态"""
    try:
        # Get config from database
        config = await get_risk_control_config()
        
        # Get actual system status
        system = get_risk_control_system()
        status = {
            "proxy_pool": {
                "enabled": config.get("proxy_pool", {}).get("enabled", False),
                "strategy": config.get("proxy_pool", {}).get("strategy", "sticky"),
                "initialized": get_proxy_pool() is not None
            },
            "rate_limit": {
                "enabled": config.get("rate_limit", {}).get("enabled", False),
                "global_rpm": config.get("rate_limit", {}).get("global", {}).get("requests_per_minute", 1000),
                "global_tpm": config.get("rate_limit", {}).get("global", {}).get("tokens_per_minute", 1000000),
                "initialized": get_rate_limiter() is not None
            },
            "health_monitor": {
                "enabled": config.get("health_monitor", {}).get("enabled", False),
                "interval": config.get("health_monitor", {}).get("check_interval", 60),
                "initialized": get_health_monitor() is not None
            },
            "fingerprint": {
                "enabled": config.get("fingerprint", {}).get("enabled", False)
            }
        }
        return web.json_response(status)
    except Exception as e:
        logger.error(f"Failed to get risk control status: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_proxy_pool_stats(request: web.Request):
    """获取代理池统计"""
    try:
        pool = get_proxy_pool()
        if not pool:
            # 返回空数据而不是404
            return web.json_response({
                "total_proxies": 0,
                "alive_proxies": 0,
                "dead_proxies": 0,
                "strategy": "not_initialized",
                "bound_accounts": 0,
                "proxies": []
            })
        
        stats = pool.get_stats()
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"Failed to get proxy pool stats: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_add_proxy(request: web.Request):
    """添加代理"""
    try:
        pool = get_proxy_pool()
        if not pool:
            return web.json_response({"error": "Proxy pool not initialized"}, status=404)
        
        data = await request.json()
        
        config = ProxyConfig(
            host=data["host"],
            port=data["port"],
            protocol=ProxyProtocol(data.get("protocol", "http")),
            username=data.get("username"),
            password=data.get("password"),
            country=data.get("country"),
            region=data.get("region"),
            isp=data.get("isp")
        )
        
        proxy = pool.add_proxy(config)
        
        # 立即进行健康检查
        await proxy.check_health()
        
        return web.json_response({
            "success": True,
            "proxy": str(proxy),
            "is_alive": proxy.stats.is_alive
        })
    except Exception as e:
        logger.error(f"Failed to add proxy: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_proxy_health_check(request: web.Request):
    """代理健康检查"""
    try:
        pool = get_proxy_pool()
        if not pool:
            return web.json_response({"error": "Proxy pool not initialized"}, status=404)
        
        await pool.health_check_all()
        
        stats = pool.get_stats()
        return web.json_response({
            "success": True,
            "alive_proxies": stats["alive_proxies"],
            "dead_proxies": stats["dead_proxies"]
        })
    except Exception as e:
        logger.error(f"Failed to check proxy health: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_rate_limit_stats(request: web.Request):
    """获取速率限制统计"""
    try:
        limiter = get_rate_limiter()
        if not limiter:
            # 返回空数据而不是404
            return web.json_response({
                "global": None,
                "accounts": {},
                "users": {}
            })
        
        stats = await limiter.get_all_stats()
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"Failed to get rate limit stats: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_health_monitor_stats(request: web.Request):
    """获取健康监控统计"""
    try:
        monitor = get_health_monitor()
        if not monitor:
            # 返回空数据而不是404
            return web.json_response({
                "summary": {
                    "total_accounts": 0,
                    "healthy": 0,
                    "degraded": 0,
                    "unhealthy": 0,
                    "banned": 0,
                    "available": 0
                },
                "accounts": []
            })
        
        summary = monitor.get_summary()
        all_stats = monitor.get_all_stats()
        
        return web.json_response({
            "summary": summary,
            "accounts": all_stats
        })
    except Exception as e:
        logger.error(f"Failed to get health monitor stats: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_account_health_detail(request: web.Request):
    """获取账号健康详情"""
    try:
        account_id = int(request.match_info["id"])
        
        monitor = get_health_monitor()
        if not monitor:
            return web.json_response({"error": "Health monitor not initialized"}, status=404)
        
        health = await monitor.get_account_health(account_id)
        stats = health.get_stats()
        
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"Failed to get account health: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_account_manual_degrade(request: web.Request):
    """手动降级账号"""
    try:
        account_id = int(request.match_info["id"])
        data = await request.json()
        duration = data.get("duration", 3600)
        
        monitor = get_health_monitor()
        if not monitor:
            return web.json_response({"error": "Health monitor not initialized"}, status=404)
        
        health = await monitor.get_account_health(account_id)
        await health.manual_degrade(duration)
        
        return web.json_response({
            "success": True,
            "account_id": account_id,
            "status": health.status.value,
            "degraded_until": health.degraded_until
        })
    except Exception as e:
        logger.error(f"Failed to degrade account: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_account_manual_ban(request: web.Request):
    """手动封禁账号"""
    try:
        account_id = int(request.match_info["id"])
        data = await request.json()
        duration = data.get("duration", 86400)
        
        monitor = get_health_monitor()
        if not monitor:
            return web.json_response({"error": "Health monitor not initialized"}, status=404)
        
        health = await monitor.get_account_health(account_id)
        await health.manual_ban(duration)
        
        return web.json_response({
            "success": True,
            "account_id": account_id,
            "status": health.status.value,
            "banned_until": health.banned_until
        })
    except Exception as e:
        logger.error(f"Failed to ban account: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_account_recover(request: web.Request):
    """恢复账号"""
    try:
        account_id = int(request.match_info["id"])
        
        monitor = get_health_monitor()
        if not monitor:
            return web.json_response({"error": "Health monitor not initialized"}, status=404)
        
        health = await monitor.get_account_health(account_id)
        await health.recover()
        
        return web.json_response({
            "success": True,
            "account_id": account_id,
            "status": health.status.value
        })
    except Exception as e:
        logger.error(f"Failed to recover account: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_update_risk_control_config(request: web.Request):
    """更新风控系统配置并动态应用"""
    try:
        data = await request.json()
        
        # Save to database
        success = await update_risk_control_config(data)
        if not success:
            return web.json_response({"error": "Failed to save config"}, status=500)
        
        # Apply changes dynamically
        changes_applied = []
        
        # 1. Update proxy pool
        if "proxy_pool" in data:
            proxy_config = data["proxy_pool"]
            enabled = proxy_config.get("enabled", False)
            strategy = proxy_config.get("strategy", "sticky")
            
            pool = get_proxy_pool()
            if pool is None and enabled:
                # Initialize if not exists
                from utils.proxy_manager import ProxyBindingStrategy
                strategy_enum = ProxyBindingStrategy[strategy.upper()]
                from utils.proxy_manager import init_proxy_pool
                init_proxy_pool(strategy_enum)
                pool = get_proxy_pool()
            
            if pool:
                pool.set_enabled(enabled)
                # Update strategy
                from utils.proxy_manager import ProxyBindingStrategy
                strategy_enum = ProxyBindingStrategy[strategy.upper()]
                pool.set_strategy(strategy_enum)
                changes_applied.append(f"代理池已{'启用' if enabled else '禁用'}，策略：{strategy}")
                logger.info(f"Proxy pool {'enabled' if enabled else 'disabled'}, strategy: {strategy}")
            else:
                changes_applied.append("代理池初始化失败")
        
        # 2. Update rate limiter
        if "rate_limit" in data:
            rate_config = data["rate_limit"]
            enabled = rate_config.get("enabled", False)
            
            if enabled:
                # Initialize or update rate limiter
                global_rpm = rate_config.get("global_rpm", 1000)
                global_tpm = rate_config.get("global_tpm", 1000000)
                
                global_limit = RateLimitConfig(
                    requests_per_minute=global_rpm,
                    tokens_per_minute=global_tpm,
                    burst_size=50,
                    min_interval=0.1
                )
                init_rate_limiter(global_limit)
                changes_applied.append("速率限制已启用")
                logger.info(f"Rate limiter enabled with RPM={global_rpm}, TPM={global_tpm}")
            else:
                # Disable rate limiter by setting very high limits
                global_limit = RateLimitConfig(
                    requests_per_minute=999999,
                    tokens_per_minute=999999999,
                    burst_size=999999,
                    min_interval=0.0
                )
                init_rate_limiter(global_limit)
                changes_applied.append("速率限制已禁用")
                logger.info("Rate limiter disabled")
        
        # 3. Update health monitor
        if "health_monitor" in data:
            health_config = data["health_monitor"]
            enabled = health_config.get("enabled", False)
            
            monitor = get_health_monitor()
            if monitor is None and enabled:
                # Initialize if not exists
                init_health_monitor()
                monitor = get_health_monitor()
            
            if monitor:
                monitor.set_enabled(enabled)
                changes_applied.append(f"健康监控已{'启用' if enabled else '禁用'}")
                logger.info(f"Health monitor {'enabled' if enabled else 'disabled'}")
            else:
                changes_applied.append("健康监控初始化失败")
        
        message = "配置已保存并应用：" + "、".join(changes_applied) if changes_applied else "配置已保存"
        
        logger.info(f"Risk control config updated and applied: {data}")
        
        return web.json_response({
            "success": True,
            "message": message,
            "changes_applied": changes_applied
        })
    except Exception as e:
        logger.error(f"Failed to update risk control config: {e}")
        return web.json_response({"error": str(e)}, status=500)
