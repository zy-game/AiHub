import json
import aiohttp
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger

class OpenAIProvider(BaseProvider):
    BASE_URL = "https://api.openai.com"
    
    SUPPORTED_MODELS = [
        "gpt-4", "gpt-4-turbo", "gpt-4-turbo-preview",
        "gpt-4-0125-preview", "gpt-4-1106-preview",
        "gpt-4-vision-preview", "gpt-4-32k",
        "gpt-3.5-turbo", "gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-16k",
        "o1-preview", "o1-mini"
    ]
    
    def __init__(self):
        super().__init__("openai")
    
    def get_supported_models(self) -> list:
        return self.SUPPORTED_MODELS
    
    def supports_model(self, model: str) -> bool:
        # 支持精确匹配或前缀匹配
        if model in self.SUPPORTED_MODELS:
            return True
        # 检查是否是某个模型的变体（如 gpt-4-0613）
        return any(model.startswith(m) for m in self.SUPPORTED_MODELS)
    
    async def chat(self, api_key: str, model: str, data: dict):
        url = f"{self.BASE_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data["model"] = model
        data["stream"] = True
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                async for line in resp.content:
                    yield line
    
    async def list_models(self, api_key: str) -> list:
        url = f"{self.BASE_URL}/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m["id"] for m in data.get("data", [])]
