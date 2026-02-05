import json
import aiohttp
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger

class OpenAIProvider(BaseProvider):
    BASE_URL = "https://api.openai.com"
    
    def __init__(self):
        super().__init__("openai")
    
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
