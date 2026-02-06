"""
风控系统初始化模块
"""
import json
import os
import asyncio
from typing import Optional
from utils.logger import logger
from utils.proxy_manager import (
    init_proxy_pool, 
    get_proxy_pool, 
    ProxyBindingStrategy,
    load_proxies_from_config
)
from utils.rate_limiter import (
    init_rate_limiter,
    get_rate_limiter,
    RateLimitConfig
)
from utils.fingerprint import init_fingerprint_system
from utils.health_monitor import init_health_monitor, get_health_monitor


class RiskControlSystem:
    """风控系统管理器"""
    
    def __init__(self):
        self.config = {}
        self.initialized = False
        self._background_tasks = []
    
    async def initialize(self, config_path: str = "risk_control_config.json"):
        """
        初始化风控系统
        
        Args:
            config_path: 配置文件路径
        """
        if self.initialized:
            logger.warning("Risk control system already initialized")
            return
        
        # 加载配置
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"Loaded risk control config from {config_path}")
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")
            self.config = self._get_default_config()
        
        # 检查是否启用
        if not self.config.get("risk_control", {}).get("enabled", False):
            logger.info("Risk control system is disabled")
            return
        
        # 1. 初始化代理池
        if self.config.get("proxy_pool", {}).get("enabled", False):
            await self._init_proxy_pool()
        
        # 2. 初始化速率限制器
        if self.config.get("rate_limit", {}).get("enabled", False):
            self._init_rate_limiter()
        
        # 3. 初始化指纹系统
        if self.config.get("fingerprint", {}).get("enabled", False):
            init_fingerprint_system()
            logger.info("Fingerprint system initialized")
        
        # 4. 初始化健康监控
        if self.config.get("health_monitor", {}).get("enabled", False):
            self._init_health_monitor()
        
        self.initialized = True
        logger.info("Risk control system initialized successfully")
    
    async def _init_proxy_pool(self):
        """初始化代理池"""
        proxy_config = self.config.get("proxy_pool", {})
        
        # 获取策略
        strategy_name = proxy_config.get("strategy", "sticky")
        strategy = ProxyBindingStrategy[strategy_name.upper()]
        
        # 初始化代理池
        init_proxy_pool(strategy)
        
        # 加载代理
        await load_proxies_from_config(proxy_config)
        
        # 启动自动健康检查
        if proxy_config.get("auto_health_check", True):
            pool = get_proxy_pool()
            if pool:
                interval = proxy_config.get("health_check_interval", 300)
                task = asyncio.create_task(pool.auto_health_check(interval))
                self._background_tasks.append(task)
                logger.info(f"Started proxy auto health check (interval: {interval}s)")
    
    def _init_rate_limiter(self):
        """初始化速率限制器"""
        rate_config = self.config.get("rate_limit", {})
        
        # 全局限制配置
        global_config = rate_config.get("global", {})
        if global_config:
            global_limit = RateLimitConfig(
                requests_per_minute=global_config.get("requests_per_minute", 1000),
                tokens_per_minute=global_config.get("tokens_per_minute", 1000000),
                burst_size=global_config.get("burst_size", 50),
                min_interval=global_config.get("min_interval", 0.1)
            )
            init_rate_limiter(global_limit)
            logger.info(f"Rate limiter initialized with global limit: {global_limit.requests_per_minute} RPM")
        else:
            init_rate_limiter()
            logger.info("Rate limiter initialized without global limit")
    
    def _init_health_monitor(self):
        """初始化健康监控"""
        health_config = self.config.get("health_monitor", {})
        
        # 初始化监控器
        init_health_monitor()
        
        # 启动自动恢复
        if health_config.get("auto_recovery", True):
            monitor = get_health_monitor()
            if monitor:
                interval = health_config.get("check_interval", 60)
                task = asyncio.create_task(monitor.auto_monitor_loop(interval))
                self._background_tasks.append(task)
                logger.info(f"Started health auto monitor (interval: {interval}s)")
    
    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "risk_control": {"enabled": False},
            "proxy_pool": {"enabled": False},
            "rate_limit": {"enabled": False},
            "fingerprint": {"enabled": False},
            "health_monitor": {"enabled": False}
        }
    
    async def shutdown(self):
        """关闭风控系统"""
        logger.info("Shutting down risk control system...")
        
        # 取消所有后台任务
        for task in self._background_tasks:
            task.cancel()
        
        # 等待任务完成
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self.initialized = False
        logger.info("Risk control system shut down")
    
    def get_status(self) -> dict:
        """获取系统状态"""
        status = {
            "initialized": self.initialized,
            "components": {}
        }
        
        if not self.initialized:
            return status
        
        # 代理池状态
        proxy_pool = get_proxy_pool()
        if proxy_pool:
            status["components"]["proxy_pool"] = proxy_pool.get_stats()
        
        # 速率限制器状态
        rate_limiter = get_rate_limiter()
        if rate_limiter:
            status["components"]["rate_limiter"] = {
                "enabled": True,
                "note": "Use /api/risk-control/rate-limit/stats for detailed stats"
            }
        
        # 健康监控状态
        health_monitor = get_health_monitor()
        if health_monitor:
            status["components"]["health_monitor"] = health_monitor.get_summary()
        
        return status


# 全局实例
_risk_control_system: Optional[RiskControlSystem] = None


def get_risk_control_system() -> RiskControlSystem:
    """获取风控系统实例"""
    global _risk_control_system
    if _risk_control_system is None:
        _risk_control_system = RiskControlSystem()
    return _risk_control_system


async def init_risk_control(config_path: str = "risk_control_config.json"):
    """初始化风控系统（便捷函数）"""
    system = get_risk_control_system()
    await system.initialize(config_path)
    return system
