"""
风控系统管理API
"""
from aiohttp import web
from utils.logger import logger
from utils.risk_control import get_risk_control_system
from utils.proxy_manager import get_proxy_pool, ProxyConfig, ProxyProtocol
from utils.rate_limiter import get_rate_limiter
from utils.health_monitor import get_health_monitor


async def api_risk_control_status(request: web.Request):
    """获取风控系统状态"""
    try:
        system = get_risk_control_system()
        status = system.get_status()
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
