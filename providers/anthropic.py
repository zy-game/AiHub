import json
import aiohttp
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger

class AnthropicProvider(BaseProvider):
    BASE_URL = "https://api.anthropic.com"
    
    SUPPORTED_MODELS = [
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514"
    ]
    
    def __init__(self):
        super().__init__("claude")
    
    def get_supported_models(self) -> list:
        return self.SUPPORTED_MODELS
    
    def supports_model(self, model: str) -> bool:
        if model in self.SUPPORTED_MODELS:
            return True
        # 支持简化名称（如 claude-3-opus）
        return any(model in m for m in self.SUPPORTED_MODELS)
    
    async def chat(self, api_key: str, model: str, data: dict):
        url = f"{self.BASE_URL}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        data["model"] = model
        data["stream"] = True
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                async for line in resp.content:
                    yield line
    
    async def list_models(self, api_key: str) -> list:
        return self.SUPPORTED_MODELS
