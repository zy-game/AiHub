from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Tuple
import aiohttp

class BaseProvider(ABC):
    BASE_URL = ""
    
    def __init__(self, name: str):
        self.name = name
    
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
