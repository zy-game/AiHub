import json
import aiohttp
import time
import asyncio
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
    
    async def chat(self, api_key: str, model: str, data: dict, account_id=None, user_id=None):
        url = f"{self.BASE_URL}/v1/chat/completions"
        
        # 应用速率限制
        await self._apply_rate_limit(
            account_id=account_id,
            user_id=user_id,
            estimated_tokens=1000  # 可以根据请求内容估算
        )
        
        # 构建请求头（带指纹伪装）
        base_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        headers = await self._build_request_headers(
            api_key=api_key,
            account_id=account_id,
            base_headers=base_headers
        )
        
        data["model"] = model
        data["stream"] = True
        
        # 创建带代理的会话
        session, proxy = await self._create_session_with_proxy(account_id)
        
        start_time = time.time()
        success = False
        error_type = None
        
        try:
            async with session:
                request_kwargs = {
                    "url": url,
                    "headers": headers,
                    "json": data
                }
                if proxy:
                    request_kwargs["proxy"] = proxy
                
                async with session.post(**request_kwargs) as resp:
                    if resp.status == 200:
                        success = True
                        async for line in resp.content:
                            yield line
                    elif resp.status == 429:
                        error_type = "rate_limit"
                        logger.warning(f"OpenAI rate limit hit for account {account_id}")
                        async for line in resp.content:
                            yield line
                    elif resp.status == 401:
                        error_type = "auth"
                        logger.error(f"OpenAI auth error for account {account_id}")
                        async for line in resp.content:
                            yield line
                    elif resp.status >= 500:
                        error_type = "server"
                        async for line in resp.content:
                            yield line
                    else:
                        async for line in resp.content:
                            yield line
        except asyncio.TimeoutError:
            error_type = "timeout"
            logger.error(f"OpenAI request timeout for account {account_id}")
            raise
        except Exception as e:
            logger.error(f"OpenAI request error for account {account_id}: {e}")
            raise
        finally:
            # 记录健康指标
            response_time = time.time() - start_time
            if account_id:
                await self._record_health_metrics(
                    account_id=account_id,
                    success=success,
                    response_time=response_time,
                    error_type=error_type
                )
    
    async def list_models(self, api_key: str) -> list:
        url = f"{self.BASE_URL}/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m["id"] for m in data.get("data", [])]
