"""
账号健康度监控系统
监控账号状态、风险等级、自动降级和恢复
"""
import time
import asyncio
from typing import Dict, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from utils.logger import logger


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"  # 健康
    DEGRADED = "degraded"  # 降级
    UNHEALTHY = "unhealthy"  # 不健康
    BANNED = "banned"  # 已封禁


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"  # 低风险
    MEDIUM = "medium"  # 中风险
    HIGH = "high"  # 高风险
    CRITICAL = "critical"  # 严重风险


@dataclass
class HealthMetrics:
    """健康指标"""
    total_requests: int = 0
    failed_requests: int = 0
    rate_limit_errors: int = 0  # 速率限制错误
    auth_errors: int = 0  # 认证错误
    server_errors: int = 0  # 服务器错误
    timeout_errors: int = 0  # 超时错误
    
    consecutive_failures: int = 0  # 连续失败次数
    consecutive_rate_limits: int = 0  # 连续速率限制次数
    
    total_response_time: float = 0.0  # 总响应时间
    last_success_at: float = 0.0  # 最后成功时间
    last_failure_at: float = 0.0  # 最后失败时间
    last_check_at: float = 0.0  # 最后检查时间
    
    # 时间窗口统计（最近1小时）
    recent_requests: List[float] = field(default_factory=list)
    recent_failures: List[float] = field(default_factory=list)
    
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
    
    @property
    def recent_failure_rate(self) -> float:
        """最近1小时失败率"""
        now = time.time()
        cutoff = now - 3600  # 1小时前
        
        # 清理过期数据
        self.recent_requests = [t for t in self.recent_requests if t > cutoff]
        self.recent_failures = [t for t in self.recent_failures if t > cutoff]
        
        if not self.recent_requests:
            return 0.0
        return len(self.recent_failures) / len(self.recent_requests)


class AccountHealth:
    """账号健康状态"""
    
    def __init__(self, account_id: int):
        self.account_id = account_id
        self.metrics = HealthMetrics()
        self.status = HealthStatus.HEALTHY
        self.risk_level = RiskLevel.LOW
        
        self.degraded_until: float = 0.0  # 降级截止时间
        self.banned_until: float = 0.0  # 封禁截止时间
        
        self._lock = asyncio.Lock()
    
    async def record_request(
        self,
        success: bool,
        response_time: float,
        error_type: Optional[str] = None
    ):
        """
        记录请求结果
        
        Args:
            success: 是否成功
            response_time: 响应时间（秒）
            error_type: 错误类型（rate_limit, auth, server, timeout）
        """
        async with self._lock:
            now = time.time()
            
            self.metrics.total_requests += 1
            self.metrics.total_response_time += response_time
            self.metrics.recent_requests.append(now)
            
            if success:
                self.metrics.consecutive_failures = 0
                self.metrics.consecutive_rate_limits = 0
                self.metrics.last_success_at = now
            else:
                self.metrics.failed_requests += 1
                self.metrics.consecutive_failures += 1
                self.metrics.last_failure_at = now
                self.metrics.recent_failures.append(now)
                
                # 记录错误类型
                if error_type == "rate_limit":
                    self.metrics.rate_limit_errors += 1
                    self.metrics.consecutive_rate_limits += 1
                elif error_type == "auth":
                    self.metrics.auth_errors += 1
                elif error_type == "server":
                    self.metrics.server_errors += 1
                elif error_type == "timeout":
                    self.metrics.timeout_errors += 1
            
            # 更新健康状态
            await self._update_health_status()
    
    async def _update_health_status(self):
        """更新健康状态"""
        now = time.time()
        
        # 检查是否在封禁期
        if self.banned_until > now:
            self.status = HealthStatus.BANNED
            self.risk_level = RiskLevel.CRITICAL
            return
        
        # 检查是否在降级期
        if self.degraded_until > now:
            self.status = HealthStatus.DEGRADED
            self.risk_level = RiskLevel.HIGH
            return
        
        # 严重情况：连续认证错误（可能账号被封）
        if self.metrics.auth_errors >= 3:
            self.status = HealthStatus.BANNED
            self.risk_level = RiskLevel.CRITICAL
            self.banned_until = now + 86400  # 封禁24小时
            logger.error(f"Account {self.account_id} marked as BANNED due to auth errors")
            return
        
        # 严重情况：连续速率限制
        if self.metrics.consecutive_rate_limits >= 5:
            self.status = HealthStatus.DEGRADED
            self.risk_level = RiskLevel.CRITICAL
            self.degraded_until = now + 3600  # 降级1小时
            logger.warning(f"Account {self.account_id} degraded due to rate limits")
            return
        
        # 严重情况：连续失败
        if self.metrics.consecutive_failures >= 10:
            self.status = HealthStatus.UNHEALTHY
            self.risk_level = RiskLevel.HIGH
            logger.warning(f"Account {self.account_id} marked as UNHEALTHY")
            return
        
        # 中等风险：最近失败率高
        recent_failure_rate = self.metrics.recent_failure_rate
        if recent_failure_rate > 0.5:
            self.status = HealthStatus.DEGRADED
            self.risk_level = RiskLevel.HIGH
        elif recent_failure_rate > 0.3:
            self.status = HealthStatus.DEGRADED
            self.risk_level = RiskLevel.MEDIUM
        elif recent_failure_rate > 0.1:
            self.status = HealthStatus.HEALTHY
            self.risk_level = RiskLevel.MEDIUM
        else:
            self.status = HealthStatus.HEALTHY
            self.risk_level = RiskLevel.LOW
    
    async def manual_degrade(self, duration: int = 3600):
        """手动降级账号"""
        async with self._lock:
            self.status = HealthStatus.DEGRADED
            self.risk_level = RiskLevel.HIGH
            self.degraded_until = time.time() + duration
            logger.info(f"Account {self.account_id} manually degraded for {duration}s")
    
    async def manual_ban(self, duration: int = 86400):
        """手动封禁账号"""
        async with self._lock:
            self.status = HealthStatus.BANNED
            self.risk_level = RiskLevel.CRITICAL
            self.banned_until = time.time() + duration
            logger.info(f"Account {self.account_id} manually banned for {duration}s")
    
    async def recover(self):
        """恢复账号"""
        async with self._lock:
            self.status = HealthStatus.HEALTHY
            self.risk_level = RiskLevel.LOW
            self.degraded_until = 0.0
            self.banned_until = 0.0
            self.metrics.consecutive_failures = 0
            self.metrics.consecutive_rate_limits = 0
            logger.info(f"Account {self.account_id} recovered")
    
    def is_available(self) -> bool:
        """账号是否可用"""
        return self.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
    
    def get_priority_penalty(self) -> float:
        """
        获取优先级惩罚系数（0-1）
        用于负载均衡时降低不健康账号的权重
        """
        if self.status == HealthStatus.BANNED:
            return 0.0
        elif self.status == HealthStatus.UNHEALTHY:
            return 0.1
        elif self.status == HealthStatus.DEGRADED:
            return 0.5
        else:
            return 1.0
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "account_id": self.account_id,
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "success_rate": f"{self.metrics.success_rate * 100:.1f}%",
            "recent_failure_rate": f"{self.metrics.recent_failure_rate * 100:.1f}%",
            "total_requests": self.metrics.total_requests,
            "failed_requests": self.metrics.failed_requests,
            "consecutive_failures": self.metrics.consecutive_failures,
            "rate_limit_errors": self.metrics.rate_limit_errors,
            "auth_errors": self.metrics.auth_errors,
            "avg_response_time": f"{self.metrics.avg_response_time:.2f}s",
            "degraded_until": self.degraded_until,
            "banned_until": self.banned_until,
        }


class HealthMonitor:
    """健康监控器"""
    
    def __init__(self):
        self.accounts: Dict[int, AccountHealth] = {}
        self._lock = asyncio.Lock()
        self.enabled = True  # Add enabled flag
    
    def set_enabled(self, enabled: bool):
        """Enable or disable health monitoring"""
        self.enabled = enabled
        logger.info(f"Health monitor {'enabled' if enabled else 'disabled'}")
    
    def is_enabled(self) -> bool:
        """Check if health monitoring is enabled"""
        return self.enabled
    
    async def get_account_health(self, account_id: int) -> AccountHealth:
        """获取账号健康状态"""
        async with self._lock:
            if account_id not in self.accounts:
                self.accounts[account_id] = AccountHealth(account_id)
            return self.accounts[account_id]
    
    async def record_request(
        self,
        account_id: int,
        success: bool,
        response_time: float,
        error_type: Optional[str] = None
    ):
        """记录请求"""
        if not self.enabled:
            return  # Skip recording if disabled
        health = await self.get_account_health(account_id)
        await health.record_request(success, response_time, error_type)
    
    async def get_available_accounts(self, account_ids: List[int]) -> List[int]:
        """
        获取可用账号列表（按健康度排序）
        
        Args:
            account_ids: 候选账号ID列表
        
        Returns:
            排序后的可用账号ID列表
        """
        available = []
        
        for account_id in account_ids:
            health = await self.get_account_health(account_id)
            if health.is_available():
                priority = health.get_priority_penalty()
                available.append((account_id, priority))
        
        # 按优先级排序（高到低）
        available.sort(key=lambda x: x[1], reverse=True)
        
        return [account_id for account_id, _ in available]
    
    async def auto_check_and_recover(self):
        """自动检查并恢复账号"""
        now = time.time()
        recovered = []
        
        async with self._lock:
            for account_id, health in self.accounts.items():
                # 检查降级期是否结束
                if health.status == HealthStatus.DEGRADED and health.degraded_until < now:
                    await health.recover()
                    recovered.append(account_id)
                
                # 检查封禁期是否结束
                elif health.status == HealthStatus.BANNED and health.banned_until < now:
                    await health.recover()
                    recovered.append(account_id)
        
        if recovered:
            logger.info(f"Auto recovered accounts: {recovered}")
    
    async def auto_monitor_loop(self, interval: int = 60):
        """自动监控循环（每分钟检查一次）"""
        while True:
            try:
                await self.auto_check_and_recover()
            except Exception as e:
                logger.error(f"Auto monitor error: {e}")
            await asyncio.sleep(interval)
    
    def get_all_stats(self) -> List[dict]:
        """获取所有账号统计"""
        return [health.get_stats() for health in self.accounts.values()]
    
    def get_summary(self) -> dict:
        """获取汇总统计"""
        total = len(self.accounts)
        healthy = sum(1 for h in self.accounts.values() if h.status == HealthStatus.HEALTHY)
        degraded = sum(1 for h in self.accounts.values() if h.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for h in self.accounts.values() if h.status == HealthStatus.UNHEALTHY)
        banned = sum(1 for h in self.accounts.values() if h.status == HealthStatus.BANNED)
        
        return {
            "total_accounts": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "banned": banned,
            "available": healthy + degraded,
        }


# 全局实例
_health_monitor: Optional[HealthMonitor] = None


def init_health_monitor() -> HealthMonitor:
    """初始化健康监控器"""
    global _health_monitor
    _health_monitor = HealthMonitor()
    logger.info("Health monitor initialized")
    return _health_monitor


def get_health_monitor() -> Optional[HealthMonitor]:
    """获取健康监控器"""
    return _health_monitor
