import json
import aiohttp
import time
import asyncio
from typing import AsyncIterator
from .base import BaseProvider
from .converters import GLMConverter, OpenAIToClaudeConverter
from utils.logger import logger

class GLMProvider(BaseProvider):
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    
    DEFAULT_SUPPORTED_MODELS = [
        "glm-4-flash",
        "glm-4-plus",
        "glm-4-air",
        "glm-4-airx",
        "glm-4-long",
        "glm-4-flashx",
        "glm-4-0520",
        "glm-4",
        "glm-3-turbo"
    ]
    
    def __init__(self):
        super().__init__("glm")
    
    def get_default_supported_models(self) -> list:
        return self.DEFAULT_SUPPORTED_MODELS.copy()
    
    def supports_model(self, model: str) -> bool:
        supported = self.get_supported_models()
        if model in supported:
            return True
        return any(model.startswith(m) for m in supported)
    
    async def chat(self, api_key: str, model: str, data: dict, account_id=None, user_id=None):
        url = f"{self.BASE_URL}/chat/completions"
        
        await self._apply_rate_limit(
            account_id=account_id,
            user_id=user_id,
            estimated_tokens=1000
        )
        
        base_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        headers = await self._build_request_headers(
            api_key=api_key,
            account_id=account_id,
            base_headers=base_headers
        )
        
        # Convert OpenAI format to GLM format
        glm_data = GLMConverter.convert_request(data)
        glm_data["model"] = model
        is_stream = data.get("stream", True)
        glm_data["stream"] = is_stream
        
        # Debug: Log request data to console (not file)
        logger.info(f"GLM request to {url}")
        logger.debug(f"GLM request headers: {json.dumps({k: v for k, v in headers.items() if k.lower() != 'authorization'}, ensure_ascii=False)}")
        if "tools" in glm_data:
            logger.debug(f"GLM request tools count: {len(glm_data['tools'])}")
        
        session, proxy = await self._create_session_with_proxy(account_id)
        
        start_time = time.time()
        success = False
        error_type = None
        has_received_data = False
        
        try:
            async with session:
                request_kwargs = {
                    "url": url,
                    "headers": headers,
                    "json": glm_data
                }
                if proxy:
                    request_kwargs["proxy"] = proxy
                
                async with session.post(**request_kwargs) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"GLM API error ({resp.status}): {error_text}")
                        
                        if resp.status == 429:
                            error_type = "rate_limit"
                            raise Exception(f"GLM rate limit exceeded: {error_text}")
                        elif resp.status == 401:
                            error_type = "auth"
                            raise Exception(f"GLM authentication failed: {error_text}")
                        elif resp.status >= 500:
                            error_type = "server"
                            raise Exception(f"GLM server error ({resp.status}): {error_text}")
                        else:
                            raise Exception(f"GLM API error ({resp.status}): {error_text}")
                    
                    success = True
                    logger.info(f"GLM API response status: {resp.status}")
                    
                    if is_stream:
                        # Streaming mode: convert to Claude SSE format
                        chunk_count = 0
                        logged_count = 0
                        claude_converter = OpenAIToClaudeConverter()
                        
                        try:
                            async for line in resp.content:
                                if not line:
                                    continue
                                has_received_data = True
                                chunk_count += 1
                                
                                # Convert GLM format to OpenAI format, then to Claude format
                                openai_chunk = GLMConverter.convert_stream_chunk(line)
                                if openai_chunk:
                                    logged_count += 1
                                    claude_chunk = claude_converter.convert_chunk(openai_chunk)
                                    if claude_chunk:
                                        yield claude_chunk.encode("utf-8")
                        except aiohttp.ClientPayloadError as e:
                            if not has_received_data:
                                logger.error(f"GLM stream error: request ended without sending any chunks - {e}")
                                raise Exception("Request ended without sending any chunks. The upstream service may be unavailable or rate limited.")
                            logger.warning(f"GLM stream interrupted after receiving data: {e}")
                        except Exception as e:
                            logger.error(f"GLM stream error: {e}")
                            raise
                        
                        if not has_received_data:
                            logger.error("GLM stream completed without receiving any data")
                            raise Exception("Request ended without sending any chunks. The upstream service may be unavailable.")
                        else:
                            logger.info(f"GLM stream completed: {chunk_count} total chunks, {logged_count} data messages")
                    else:
                        # Non-streaming mode: return complete JSON
                        response_data = await resp.json()
                        has_received_data = True
                        # GLM returns OpenAI-compatible JSON, yield directly
                        yield json.dumps(response_data).encode("utf-8")
                        logger.info(f"GLM complete response returned")
                        
        except asyncio.TimeoutError:
            error_type = "timeout"
            logger.error(f"GLM request timeout for account {account_id}")
            raise Exception("GLM request timeout")
        except Exception as e:
            if "Request ended without sending any chunks" not in str(e):
                logger.error(f"GLM request error for account {account_id}: {e}")
            raise
        finally:
            response_time = time.time() - start_time
            if account_id:
                await self._record_health_metrics(
                    account_id=account_id,
                    success=success,
                    response_time=response_time,
                    error_type=error_type
                )
    
    async def list_models(self, api_key: str) -> list:
        return self.get_supported_models()
