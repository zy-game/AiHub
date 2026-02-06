"""
速率限制和请求频率控制系统
支持多级限流：用户级、账号级、全局级
"""
import asyncio
import time
import random
from typing import Dict, Optional
from collections import deque
from dataclasses import dataclass
from utils.logger import logger


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    requests_per_minute: int = 60  # RPM
    tokens_per_minute: int = 90000  # TPM
    burst_size: int = 10  # 突发请求数
    min_interval: float = 0.5  # 最小请求间隔（秒）


class TokenBucket:
    """令牌桶算法实现"""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶容量
            refill_rate: 每秒填充速率
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """
        消费令牌
        
        Args:
            tokens: 需要消费的令牌数
        
        Returns:
            是否成功消费
        """
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def wait_for_tokens(self, tokens: int = 1, timeout: float = 30.0):
        """
        等待令牌可用
        
        Args:
            tokens: 需要的令牌数
            timeout: 超时时间（秒）
        """
        start_time = time.time()
        
        while True:
            if await self.consume(tokens):
                return True
            
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Failed to acquire {tokens} tokens within {timeout}s")
            
            # 计算需要等待的时间
            wait_time = min(tokens / self.refill_rate, 1.0)
            await asyncio.sleep(wait_time)
    
    def _refill(self):
        """填充令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # 计算应该填充的令牌数
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_available_tokens(self) -> int:
        """获取当前可用令牌数"""
        self._refill()
        return int(self.tokens)


class SlidingWindowCounter:
    """滑动窗口计数器"""
    
    def __init__(self, window_size: int = 60):
        """
        Args:
            window_size: 窗口大小（秒）
        """
        self.window_size = window_size
        self.requests = deque()
        self._lock = asyncio.Lock()
    
    async def add_request(self, tokens: int = 0):
        """添加请求记录"""
        async with self._lock:
            now = time.time()
            self.requests.append((now, tokens))
            self._cleanup(now)
    
    async def get_count(self) -> tuple[int, int]:
        """
        获取窗口内的请求数和token数
        
        Returns:
            (请求数, token数)
        """
        async with self._lock:
            now = time.time()
            self._cleanup(now)
            
            request_count = len(self.requests)
            token_count = sum(tokens for _, tokens in self.requests)
            
            return request_count, token_count
    
    def _cleanup(self, now: float):
        """清理过期记录"""
        cutoff = now - self.window_size
        while self.requests and self.requests[0][0] < cutoff:
            self.requests.popleft()


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        
        # 令牌桶（用于请求数限制）
        self.request_bucket = TokenBucket(
            capacity=config.burst_size,
            refill_rate=config.requests_per_minute / 60.0
        )
        
        # 令牌桶（用于token数限制）
        self.token_bucket = TokenBucket(
            capacity=config.tokens_per_minute,
            refill_rate=config.tokens_per_minute / 60.0
        )
        
        # 滑动窗口计数器
        self.window_counter = SlidingWindowCounter(window_size=60)
        
        # 最后请求时间（用于最小间隔控制）
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self, estimated_tokens: int = 1000) -> float:
        """
        获取请求许可
        
        Args:
            estimated_tokens: 预估的token数
        
        Returns:
            建议的延迟时间（秒）
        """
        async with self._lock:
            # 1. 检查最小请求间隔
            now = time.time()
            time_since_last = now - self.last_request_time
            
            if time_since_last < self.config.min_interval:
                min_delay = self.config.min_interval - time_since_last
            else:
                min_delay = 0.0
            
            # 2. 等待请求令牌
            await self.request_bucket.wait_for_tokens(1)
            
            # 3. 等待token令牌
            await self.token_bucket.wait_for_tokens(estimated_tokens)
            
            # 4. 记录请求
            await self.window_counter.add_request(estimated_tokens)
            self.last_request_time = time.time()
            
            # 5. 添加随机抖动（模拟人类行为）
            jitter = random.uniform(0, 0.5)
            
            return min_delay + jitter
    
    async def get_stats(self) -> dict:
        """获取统计信息"""
        request_count, token_count = await self.window_counter.get_count()
        
        return {
            "requests_last_minute": request_count,
            "tokens_last_minute": token_count,
            "available_request_tokens": self.request_bucket.get_available_tokens(),
            "available_token_quota": self.token_bucket.get_available_tokens(),
            "rpm_limit": self.config.requests_per_minute,
            "tpm_limit": self.config.tokens_per_minute,
        }


class MultiLevelRateLimiter:
    """多级速率限制器"""
    
    def __init__(self):
        # 全局限制器
        self.global_limiter: Optional[RateLimiter] = None
        
        # 账号级限制器
        self.account_limiters: Dict[int, RateLimiter] = {}
        
        # 用户级限制器
        self.user_limiters: Dict[int, RateLimiter] = {}
        
        self._lock = asyncio.Lock()
    
    def set_global_limit(self, config: RateLimitConfig):
        """设置全局限制"""
        self.global_limiter = RateLimiter(config)
        logger.info(f"Set global rate limit: {config.requests_per_minute} RPM, {config.tokens_per_minute} TPM")
    
    async def get_account_limiter(self, account_id: int, config: RateLimitConfig) -> RateLimiter:
        """获取账号级限制器"""
        async with self._lock:
            if account_id not in self.account_limiters:
                self.account_limiters[account_id] = RateLimiter(config)
            return self.account_limiters[account_id]
    
    async def get_user_limiter(self, user_id: int, config: RateLimitConfig) -> RateLimiter:
        """获取用户级限制器"""
        async with self._lock:
            if user_id not in self.user_limiters:
                self.user_limiters[user_id] = RateLimiter(config)
            return self.user_limiters[user_id]
    
    async def acquire(
        self,
        estimated_tokens: int = 1000,
        account_id: Optional[int] = None,
        user_id: Optional[int] = None,
        account_config: Optional[RateLimitConfig] = None,
        user_config: Optional[RateLimitConfig] = None
    ) -> float:
        """
        多级获取请求许可
        
        Args:
            estimated_tokens: 预估token数
            account_id: 账号ID
            user_id: 用户ID
            account_config: 账号级配置
            user_config: 用户级配置
        
        Returns:
            建议的延迟时间（秒）
        """
        total_delay = 0.0
        
        # 1. 全局限制
        if self.global_limiter:
            delay = await self.global_limiter.acquire(estimated_tokens)
            total_delay = max(total_delay, delay)
        
        # 2. 账号级限制
        if account_id and account_config:
            limiter = await self.get_account_limiter(account_id, account_config)
            delay = await limiter.acquire(estimated_tokens)
            total_delay = max(total_delay, delay)
        
        # 3. 用户级限制
        if user_id and user_config:
            limiter = await self.get_user_limiter(user_id, user_config)
            delay = await limiter.acquire(estimated_tokens)
            total_delay = max(total_delay, delay)
        
        return total_delay
    
    async def get_all_stats(self) -> dict:
        """获取所有限制器的统计信息"""
        stats = {}
        
        if self.global_limiter:
            stats["global"] = await self.global_limiter.get_stats()
        
        stats["accounts"] = {}
        for account_id, limiter in self.account_limiters.items():
            stats["accounts"][account_id] = await limiter.get_stats()
        
        stats["users"] = {}
        for user_id, limiter in self.user_limiters.items():
            stats["users"][user_id] = await limiter.get_stats()
        
        return stats


# 全局实例
_rate_limiter: Optional[MultiLevelRateLimiter] = None


def init_rate_limiter(global_config: Optional[RateLimitConfig] = None) -> MultiLevelRateLimiter:
    """初始化速率限制器"""
    global _rate_limiter
    _rate_limiter = MultiLevelRateLimiter()
    
    if global_config:
        _rate_limiter.set_global_limit(global_config)
    
    logger.info("Rate limiter initialized")
    return _rate_limiter


def get_rate_limiter() -> Optional[MultiLevelRateLimiter]:
    """获取速率限制器"""
    return _rate_limiter
