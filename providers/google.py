import json
import aiohttp
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger

class GoogleProvider(BaseProvider):
    BASE_URL = "https://generativelanguage.googleapis.com"
    
    SUPPORTED_MODELS = [
        "gemini-pro",
        "gemini-pro-vision",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp"
    ]
    
    def __init__(self):
        super().__init__("gemini")
    
    def get_supported_models(self) -> list:
        return self.SUPPORTED_MODELS
    
    def supports_model(self, model: str) -> bool:
        if model in self.SUPPORTED_MODELS:
            return True
        # 支持变体（如 gemini-1.5-pro-001）
        return any(model.startswith(m) for m in self.SUPPORTED_MODELS)
    
    async def chat(self, api_key: str, model: str, data: dict):
        url = f"{self.BASE_URL}/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
        headers = {"Content-Type": "application/json"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                async for line in resp.content:
                    yield line
    
    async def list_models(self, api_key: str) -> list:
        url = f"{self.BASE_URL}/v1beta/models?key={api_key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m["name"].replace("models/", "") for m in data.get("models", [])]
