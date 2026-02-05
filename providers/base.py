from abc import ABC, abstractmethod
from typing import AsyncIterator
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
        pass
    
    def get_format(self) -> str:
        return self.name
