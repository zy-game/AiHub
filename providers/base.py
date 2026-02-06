from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Tuple
import aiohttp

class BaseProvider(ABC):
    BASE_URL = ""
    
    # Default configuration values
    DEFAULT_PRIORITY = 0
    DEFAULT_WEIGHT = 1
    DEFAULT_ENABLED = True
    
    def __init__(self, name: str):
        self.name = name
        self.priority = self.DEFAULT_PRIORITY
        self.weight = self.DEFAULT_WEIGHT
        self.enabled = self.DEFAULT_ENABLED
        # Statistics (runtime only, not persisted)
        self.avg_response_time = 0
        self.total_requests = 0
        self.failed_requests = 0
    
    def configure(self, priority=None, weight=None, enabled=None):
        """Configure provider settings from config file or database"""
        if priority is not None:
            self.priority = priority
        if weight is not None:
            self.weight = weight
        if enabled is not None:
            self.enabled = enabled
    
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
    
    @abstractmethod
    async def chat(self, api_key: str, model: str, data: dict) -> AsyncIterator[bytes]:
        pass
    
    @abstractmethod
    async def list_models(self, api_key: str) -> list:
        """List all available models (may require API call)"""
        pass
    
    def get_supported_models(self) -> list:
        """Get statically defined supported models (no API call needed)"""
        return []
    
    def supports_model(self, model: str) -> bool:
        """Check if this provider supports the given model"""
        return model in self.get_supported_models()
    
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
