"""
代理池管理系统
支持多种代理协议和智能轮换策略
"""
import asyncio
import random
import time
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
import aiohttp
from utils.logger import logger


class ProxyProtocol(Enum):
    """代理协议类型"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    SOCKS4 = "socks4"


class ProxyBindingStrategy(Enum):
    """代理绑定策略"""
    RANDOM = "random"  # 每次请求随机选择
    STICKY = "sticky"  # 账号绑定固定代理
    ROUND_ROBIN = "round_robin"  # 轮询
    LEAST_USED = "least_used"  # 最少使用


@dataclass
class ProxyConfig:
    """代理配置"""
    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None  # 代理所在国家
    region: Optional[str] = None  # 代理所在地区
    isp: Optional[str] = None  # ISP提供商
    
    def get_url(self) -> str:
        """获取代理URL"""
        if self.username and self.password:
            return f"{self.protocol.value}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol.value}://{self.host}:{self.port}"
    
    def __str__(self):
        return f"{self.protocol.value}://{self.host}:{self.port}"


@dataclass
class ProxyStats:
    """代理统计信息"""
    total_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    last_used_at: float = 0.0
    last_check_at: float = 0.0
    is_alive: bool = True
    consecutive_failures: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.failed_requests / self.total_requests)
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间（秒）"""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time / self.total_requests


class Proxy:
    """代理实例"""
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.stats = ProxyStats()
        self.bound_accounts: set = set()  # 绑定的账号ID
    
    def record_request(self, response_time: float, success: bool):
        """记录请求结果"""
        self.stats.total_requests += 1
        self.stats.total_response_time += response_time
        self.stats.last_used_at = time.time()
        
        if not success:
            self.stats.failed_requests += 1
            self.stats.consecutive_failures += 1
        else:
            self.stats.consecutive_failures = 0
        
        # 连续失败3次标记为不可用
        if self.stats.consecutive_failures >= 3:
            self.stats.is_alive = False
            logger.warning(f"Proxy {self.config} marked as dead after 3 consecutive failures")
    
    async def check_health(self, timeout: int = 10) -> bool:
        """健康检查"""
        self.stats.last_check_at = time.time()
        
        try:
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.ipify.org?format=json",
                    proxy=self.config.get_url(),
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        response_time = time.time() - start_time
                        self.stats.is_alive = True
                        self.stats.consecutive_failures = 0
                        logger.info(f"Proxy {self.config} health check passed, IP: {data.get('ip')}, time: {response_time:.2f}s")
                        return True
        except Exception as e:
            logger.error(f"Proxy {self.config} health check failed: {e}")
        
        self.stats.is_alive = False
        return False
    
    def __str__(self):
        return str(self.config)


class ProxyPool:
    """代理池"""
    def __init__(self, strategy: ProxyBindingStrategy = ProxyBindingStrategy.STICKY):
        self.proxies: List[Proxy] = []
        self.strategy = strategy
        self.account_proxy_map: Dict[int, Proxy] = {}  # 账号ID -> 代理映射
        self.round_robin_index = 0
        self._lock = asyncio.Lock()
    
    def add_proxy(self, config: ProxyConfig) -> Proxy:
        """添加代理"""
        proxy = Proxy(config)
        self.proxies.append(proxy)
        logger.info(f"Added proxy: {proxy}")
        return proxy
    
    def add_proxies_batch(self, configs: List[ProxyConfig]):
        """批量添加代理"""
        for config in configs:
            self.add_proxy(config)
        logger.info(f"Added {len(configs)} proxies to pool")
    
    def remove_proxy(self, proxy: Proxy):
        """移除代理"""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            # 清理绑定关系
            for account_id, bound_proxy in list(self.account_proxy_map.items()):
                if bound_proxy == proxy:
                    del self.account_proxy_map[account_id]
            logger.info(f"Removed proxy: {proxy}")
    
    def get_alive_proxies(self) -> List[Proxy]:
        """获取存活的代理"""
        return [p for p in self.proxies if p.stats.is_alive]
    
    async def get_proxy_for_account(self, account_id: int) -> Optional[Proxy]:
        """为账号获取代理"""
        async with self._lock:
            alive_proxies = self.get_alive_proxies()
            
            if not alive_proxies:
                logger.warning("No alive proxies available")
                return None
            
            # STICKY策略：账号绑定固定代理
            if self.strategy == ProxyBindingStrategy.STICKY:
                if account_id in self.account_proxy_map:
                    proxy = self.account_proxy_map[account_id]
                    if proxy.stats.is_alive:
                        return proxy
                    else:
                        # 原代理不可用，重新分配
                        del self.account_proxy_map[account_id]
                
                # 选择使用最少的代理
                proxy = min(alive_proxies, key=lambda p: len(p.bound_accounts))
                proxy.bound_accounts.add(account_id)
                self.account_proxy_map[account_id] = proxy
                logger.info(f"Bound account {account_id} to proxy {proxy}")
                return proxy
            
            # RANDOM策略：随机选择
            elif self.strategy == ProxyBindingStrategy.RANDOM:
                return random.choice(alive_proxies)
            
            # ROUND_ROBIN策略：轮询
            elif self.strategy == ProxyBindingStrategy.ROUND_ROBIN:
                proxy = alive_proxies[self.round_robin_index % len(alive_proxies)]
                self.round_robin_index += 1
                return proxy
            
            # LEAST_USED策略：选择使用最少的
            elif self.strategy == ProxyBindingStrategy.LEAST_USED:
                return min(alive_proxies, key=lambda p: p.stats.total_requests)
            
            return None
    
    async def health_check_all(self):
        """对所有代理进行健康检查"""
        logger.info(f"Starting health check for {len(self.proxies)} proxies")
        tasks = [proxy.check_health() for proxy in self.proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        alive_count = sum(1 for r in results if r is True)
        logger.info(f"Health check completed: {alive_count}/{len(self.proxies)} proxies alive")
    
    async def auto_health_check(self, interval: int = 300):
        """自动健康检查（每5分钟）"""
        while True:
            try:
                await self.health_check_all()
            except Exception as e:
                logger.error(f"Auto health check error: {e}")
            await asyncio.sleep(interval)
    
    def get_stats(self) -> dict:
        """获取代理池统计信息"""
        alive_proxies = self.get_alive_proxies()
        return {
            "total_proxies": len(self.proxies),
            "alive_proxies": len(alive_proxies),
            "dead_proxies": len(self.proxies) - len(alive_proxies),
            "strategy": self.strategy.value,
            "bound_accounts": len(self.account_proxy_map),
            "proxies": [
                {
                    "proxy": str(p.config),
                    "country": p.config.country,
                    "region": p.config.region,
                    "is_alive": p.stats.is_alive,
                    "total_requests": p.stats.total_requests,
                    "success_rate": f"{p.stats.success_rate * 100:.1f}%",
                    "avg_response_time": f"{p.stats.avg_response_time:.2f}s",
                    "bound_accounts": len(p.bound_accounts)
                }
                for p in self.proxies
            ]
        }


# 全局代理池实例
_proxy_pool: Optional[ProxyPool] = None


def init_proxy_pool(strategy: ProxyBindingStrategy = ProxyBindingStrategy.STICKY) -> ProxyPool:
    """初始化代理池"""
    global _proxy_pool
    _proxy_pool = ProxyPool(strategy)
    logger.info(f"Initialized proxy pool with strategy: {strategy.value}")
    return _proxy_pool


def get_proxy_pool() -> Optional[ProxyPool]:
    """获取代理池实例"""
    return _proxy_pool


async def load_proxies_from_config(config_data: dict):
    """从配置加载代理"""
    pool = get_proxy_pool()
    if not pool:
        logger.warning("Proxy pool not initialized")
        return
    
    proxies = config_data.get("proxies", [])
    configs = []
    
    for proxy_data in proxies:
        try:
            config = ProxyConfig(
                host=proxy_data["host"],
                port=proxy_data["port"],
                protocol=ProxyProtocol(proxy_data.get("protocol", "http")),
                username=proxy_data.get("username"),
                password=proxy_data.get("password"),
                country=proxy_data.get("country"),
                region=proxy_data.get("region"),
                isp=proxy_data.get("isp")
            )
            configs.append(config)
        except Exception as e:
            logger.error(f"Failed to parse proxy config: {e}")
    
    pool.add_proxies_batch(configs)
    
    # 启动健康检查
    if configs:
        await pool.health_check_all()
