from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Tuple, Dict, List
import aiohttp
import time
import asyncio

class BaseProvider(ABC):
    BASE_URL = ""
    
    # Default configuration values
    DEFAULT_PRIORITY = 0
    DEFAULT_WEIGHT = 1
    DEFAULT_ENABLED = True
    
    # Default supported models (to be overridden by subclasses)
    DEFAULT_SUPPORTED_MODELS = []
    
    def __init__(self, name: str):
        self.name = name
        self.priority = self.DEFAULT_PRIORITY
        self.weight = self.DEFAULT_WEIGHT
        self.enabled = self.DEFAULT_ENABLED
        self.enabled_models = []  # Empty means all models are enabled
        self._supported_models = []  # Will be loaded from DB or use default
        # Statistics (runtime only, not persisted)
        self.avg_response_time = 0
        self.total_requests = 0
        self.failed_requests = 0
    
    async def initialize(self):
        """Initialize provider, load models from database"""
        from models.database import load_provider_models, save_provider_models
        
        # Try to load models from database
        db_models = await load_provider_models(self.name)
        
        if db_models:
            # Use models from database
            self._supported_models = db_models
        else:
            # No models in database, use default and save to DB
            default_models = self.get_default_supported_models()
            if default_models:
                self._supported_models = default_models
                await save_provider_models(self.name, default_models)
    
    def get_default_supported_models(self) -> List[str]:
        """Get default supported models (to be overridden by subclasses)"""
        return self.DEFAULT_SUPPORTED_MODELS.copy() if self.DEFAULT_SUPPORTED_MODELS else []
    
    def configure(self, priority=None, weight=None, enabled=None, enabled_models=None):
        """Configure provider settings from config file or database"""
        if priority is not None:
            self.priority = priority
        if weight is not None:
            self.weight = weight
        if enabled is not None:
            self.enabled = enabled
        if enabled_models is not None:
            # Parse comma-separated string to list
            if isinstance(enabled_models, str):
                self.enabled_models = [m.strip() for m in enabled_models.split(',') if m.strip()]
            else:
                self.enabled_models = enabled_models if enabled_models else []
    
    def get_success_rate(self) -> float:
        """Get success rate (0-1)"""
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.failed_requests / self.total_requests)
    
    def update_stats(self, response_time_ms: int, success: bool = True):
        """Update provider statistics"""
        if self.total_requests == 0:
            self.avg_response_time = response_time_ms
        else:
            # Exponential moving average
            self.avg_response_time = int(0.9 * self.avg_response_time + 0.1 * response_time_ms)
        
        self.total_requests += 1
        if not success:
            self.failed_requests += 1
    
    async def _create_session_with_proxy(self, account_id: Optional[int] = None) -> aiohttp.ClientSession:
        """
        创建带代理的HTTP会话
        
        Args:
            account_id: 账号ID（用于获取绑定的代理）
        
        Returns:
            aiohttp.ClientSession
        """
        from utils.proxy_manager import get_proxy_pool
        
        proxy_pool = get_proxy_pool()
        proxy = None
        
        if proxy_pool and account_id:
            proxy = await proxy_pool.get_proxy_for_account(account_id)
        
        if proxy:
            return aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=60)
            ), proxy.config.get_url()
        else:
            return aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            ), None
    
    async def _build_request_headers(
        self,
        api_key: str,
        account_id: Optional[int] = None,
        base_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        构建请求头（带指纹伪装）
        
        Args:
            api_key: API密钥
            account_id: 账号ID
            base_headers: 基础headers
        
        Returns:
            完整的请求头
        """
        from utils.fingerprint import get_headers_builder
        
        headers_builder = get_headers_builder()
        
        if headers_builder:
            return headers_builder.build_headers(
                account_id=account_id,
                api_key=api_key,
                base_headers=base_headers,
                sticky_fingerprint=True  # 账号绑定固定指纹
            )
        else:
            # 降级：使用基础headers
            headers = base_headers.copy() if base_headers else {}
            headers["Authorization"] = f"Bearer {api_key}"
            return headers
    
    async def _apply_rate_limit(
        self,
        account_id: Optional[int] = None,
        user_id: Optional[int] = None,
        estimated_tokens: int = 1000
    ) -> float:
        """
        应用速率限制
        
        Args:
            account_id: 账号ID
            user_id: 用户ID
            estimated_tokens: 预估token数
        
        Returns:
            建议延迟时间（秒）
        """
        from utils.rate_limiter import get_rate_limiter, RateLimitConfig
        
        rate_limiter = get_rate_limiter()
        
        if rate_limiter:
            # 这里可以根据不同provider设置不同的限制
            account_config = RateLimitConfig(
                requests_per_minute=60,
                tokens_per_minute=90000,
                burst_size=10,
                min_interval=0.5
            )
            
            delay = await rate_limiter.acquire(
                estimated_tokens=estimated_tokens,
                account_id=account_id,
                user_id=user_id,
                account_config=account_config
            )
            
            if delay > 0:
                await asyncio.sleep(delay)
            
            return delay
        
        return 0.0
    
    async def _record_health_metrics(
        self,
        account_id: int,
        success: bool,
        response_time: float,
        error_type: Optional[str] = None
    ):
        """
        记录健康指标
        
        Args:
            account_id: 账号ID
            success: 是否成功
            response_time: 响应时间（秒）
            error_type: 错误类型
        """
        from utils.health_monitor import get_health_monitor
        
        monitor = get_health_monitor()
        
        if monitor:
            await monitor.record_request(
                account_id=account_id,
                success=success,
                response_time=response_time,
                error_type=error_type
            )
    
    @abstractmethod
    async def chat(self, api_key: str, model: str, data: dict, account_id: Optional[int] = None, user_id: Optional[int] = None) -> AsyncIterator[bytes]:
        """
        发送聊天请求
        
        Args:
            api_key: API密钥
            model: 模型名称
            data: 请求数据（包含stream参数）
            account_id: 账号ID（用于代理绑定、指纹、健康监控）
            user_id: 用户ID（用于速率限制）
            
        Yields:
            bytes: 如果stream=True，返回SSE格式的chunk；如果stream=False，返回完整JSON的bytes
        """
        pass
    
    @abstractmethod
    async def list_models(self, api_key: str) -> list:
        """List all available models (may require API call)"""
        pass
    
    def get_supported_models(self) -> list:
        """Get supported models from database or default"""
        return self._supported_models if self._supported_models else self.get_default_supported_models()
    
    def get_all_models(self) -> list:
        """Get all available models (before filtering by enabled_models)"""
        return self.get_supported_models()
    
    def get_enabled_models(self) -> list:
        """Get only enabled models"""
        all_models = self.get_all_models()
        if not self.enabled_models:  # Empty list means all models are enabled
            return all_models
        return [m for m in all_models if m in self.enabled_models]
    
    def supports_model(self, model: str) -> bool:
        """Check if this provider supports the given model"""
        # Check against enabled models only
        enabled = self.get_enabled_models()
        return model in enabled
    
    def get_mapped_model(self, model: str) -> str:
        """Get the actual model name to use (for internal mapping)"""
        return model
    
    def get_format(self) -> str:
        return self.name
    
    def supports_usage_refresh(self) -> bool:
        """Check if this provider supports usage refresh"""
        return False
    
    async def refresh_usage(self, api_key: str, account_id: int) -> Optional[Tuple[int, int]]:
        """
        Refresh usage for an account
        
        Args:
            api_key: Account API key
            account_id: Account ID
            
        Returns:
            Tuple of (used, limit) or None if not supported
        """
        return None
