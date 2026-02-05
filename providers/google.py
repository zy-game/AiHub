import json
import aiohttp
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger

class GoogleProvider(BaseProvider):
    BASE_URL = "https://generativelanguage.googleapis.com"
    
    def __init__(self):
        super().__init__("gemini")
    
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
