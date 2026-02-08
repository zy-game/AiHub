# -*- coding: utf-8 -*-
import json
import uuid
import httpx
from datetime import datetime, timezone
from models import update_account, add_account_credit_usage
from urllib.parse import urlencode
from .base import BaseProvider
from utils.logger import logger
from utils.text import get_content_text
from utils.token_counter import count_tokens, count_request_tokens
from utils.converters import (
    convert_anthropic_messages_to_kiro,
    convert_anthropic_tools_to_kiro,
    KiroStreamConverter
)

class KiroProvider(BaseProvider):
    
    BASE_URL_TEMPLATE = "https://q.{region}.amazonaws.com/generateAssistantResponse"
    
    DEFAULT_REGION = "us-east-1"
    KIRO_VERSION = "0.8.140"
    USAGE_RESOURCE_TYPE = "AGENTIC_REQUEST"
    ORIGIN_AI_EDITOR = "AI_EDITOR"
    TOTAL_CONTEXT_TOKENS = 172500
    
    MODEL_MAPPING = {
        "claude-sonnet-4-5": "CLAUDE_SONNET_4_5_20250929_V1_0",
        "claude-sonnet-4-5-20250929": "CLAUDE_SONNET_4_5_20250929_V1_0",
        "claude-haiku-4-5": "claude-haiku-4.5",
        "claude-opus-4-5": "claude-opus-4.5",
    }
    THINKING_MAX_BUDGET_TOKENS = 24576
    THINKING_DEFAULT_BUDGET_TOKENS = 20000
    THINKING_START_TAG = "<thinking>"
    THINKING_END_TAG = "</thinking>"
    THINKING_MODE_TAG = "<thinking_mode>"
    THINKING_MAX_LEN_TAG = "<max_thinking_length>"
    
    def __init__(self):
        super().__init__("kiro")
    
    def get_supported_models(self) -> list:
        return list(self.MODEL_MAPPING.keys())
    
    def supports_model(self, model: str) -> bool:
        return model in self.MODEL_MAPPING
    
    def get_mapped_model(self, model: str) -> str:
        return self.MODEL_MAPPING.get(model, model)
    
    def get_format(self) -> str:
        return "claude"
    
    def supports_usage_refresh(self) -> bool:
        return True
    
    async def refresh_usage(self, api_key: str, account_id: int):
        usage_data = await self.get_usage_limits(api_key, account_id)
        used, limit = self.extract_kiro_points(usage_data)
        return (used, limit)
    
    def _get_base_url(self, region: str = None) -> str:
        return self.BASE_URL_TEMPLATE.format(region=region or self.DEFAULT_REGION)
    
    def _build_headers(self, access_token: str) -> dict:
        machine_id = uuid.uuid4().hex
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "amz-sdk-request": "attempt=1; max=1",
            "amz-sdk-invocation-id": str(uuid.uuid4()),
            "x-amzn-kiro-agent-mode": "vibe",
            "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{self.KIRO_VERSION}-{machine_id}",
            "user-agent": f"aws-sdk-js/1.0.0 ua/2.1 os/windows lang/js md/nodejs api/codewhispererruntime#1.0.0 m/E KiroIDE-{self.KIRO_VERSION}-{machine_id}",
        }

    def _build_usage_limits_url(self, region: str, profile_arn: str | None = None) -> str:
        base_url = self._get_base_url(region)
        usage_url = base_url.replace("generateAssistantResponse", "getUsageLimits")
        params = {
            "isEmailRequired": "true",
            "origin": self.ORIGIN_AI_EDITOR,
            "resourceType": self.USAGE_RESOURCE_TYPE
        }
        if profile_arn:
            params["profileArn"] = profile_arn
        return f"{usage_url}?{urlencode(params)}"

    async def _request_usage_limits(self, access_token: str, region: str, profile_arn: str | None) -> dict:
        url = self._build_usage_limits_url(region, profile_arn)
        headers = self._build_headers(access_token)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"Kiro usage limits error ({response.status_code}): {error_text}")
            return response.json()

    def extract_kiro_points(self, usage_data: dict) -> tuple[int, int]:
        if not usage_data:
            return 0, 0
        
        used_count = usage_data.get("usedCount")
        limit_count = usage_data.get("limitCount")
        if used_count is not None and limit_count is not None:
            return int(used_count), int(limit_count)
        
        breakdowns = usage_data.get("usageBreakdownList") or []
        
        candidate = None
        for item in breakdowns:
            if item.get("resourceType") == self.USAGE_RESOURCE_TYPE:
                candidate = item
                break
        if not candidate:
            for item in breakdowns:
                display_name = (item.get("displayName") or "").lower()
                if "agent" in display_name:
                    candidate = item
                    break
        if not candidate and breakdowns:
            candidate = breakdowns[0]
        if not candidate:
            return 0, 0
        
        monthly_used = candidate.get("currentUsageWithPrecision")
        if monthly_used is None:
            monthly_used = candidate.get("currentUsage")
        monthly_limit = candidate.get("usageLimitWithPrecision")
        if monthly_limit is None:
            monthly_limit = candidate.get("usageLimit")
        
        try:
            monthly_used_val = float(monthly_used) if monthly_used is not None else 0
        except (TypeError, ValueError):
            monthly_used_val = 0
        try:
            monthly_limit_val = float(monthly_limit) if monthly_limit is not None else 0
        except (TypeError, ValueError):
            monthly_limit_val = 0
        
        free_trial_used_val = 0
        free_trial_limit_val = 0
        free_trial_info = candidate.get("freeTrialInfo")
        if free_trial_info:
            ft_used = free_trial_info.get("currentUsageWithPrecision")
            if ft_used is None:
                ft_used = free_trial_info.get("currentUsage")
            ft_limit = free_trial_info.get("usageLimitWithPrecision")
            if ft_limit is None:
                ft_limit = free_trial_info.get("usageLimit")
            try:
                free_trial_used_val = float(ft_used) if ft_used is not None else 0
            except (TypeError, ValueError):
                free_trial_used_val = 0
            try:
                free_trial_limit_val = float(ft_limit) if ft_limit is not None else 0
            except (TypeError, ValueError):
                free_trial_limit_val = 0
        
        total_used = int(monthly_used_val + free_trial_used_val)
        total_limit = int(monthly_limit_val + free_trial_limit_val)
        
        return total_used, total_limit

    async def _persist_credentials(self, account_id: int | None, creds: dict) -> None:
        if not account_id:
            return
        await update_account(account_id, api_key=json.dumps(creds, ensure_ascii=False))

    def _parse_credentials(self, api_key: str) -> dict:
        try:
            return json.loads(api_key) if isinstance(api_key, str) else dict(api_key)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Kiro credentials JSON: {e}")
            raise Exception(f"Invalid Kiro credentials. JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing Kiro credentials: {e}")
            raise Exception(f"Invalid Kiro credentials: {e}")

    def _extract_credentials(self, creds: dict) -> tuple:
        return (
            creds.get("accessToken") or creds.get("access_token"),
            creds.get("refreshToken") or creds.get("refresh_token"),
            creds.get("clientId") or creds.get("client_id"),
            creds.get("clientSecret") or creds.get("client_secret"),
            creds.get("region") or self.DEFAULT_REGION,
            creds.get("profileArn") or creds.get("profile_arn")
        )

    def _apply_refresh_result(self, creds: dict, refresh_result: dict) -> None:
        creds["accessToken"] = refresh_result["accessToken"]
        creds["expiresIn"] = refresh_result["expiresIn"]
        creds["refreshedAt"] = refresh_result["refreshedAt"]

    async def _ensure_valid_token(self, creds: dict, account_id: int | None = None) -> str | None:
        access_token, refresh_token, client_id, client_secret, region, _ = self._extract_credentials(creds)
        
        can_refresh = refresh_token and client_id and client_secret
        
        if self._is_token_expired(creds) and can_refresh:
            logger.info("Access token expired, refreshing...")
            refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
            if refresh_result:
                self._apply_refresh_result(creds, refresh_result)
                await self._persist_credentials(account_id, creds)
                logger.info(f"Access token refreshed successfully")
                return creds["accessToken"]
            return None
        
        if not access_token and can_refresh:
            refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
            if refresh_result:
                self._apply_refresh_result(creds, refresh_result)
                await self._persist_credentials(account_id, creds)
                return creds["accessToken"]
            return None
        
        return access_token

    async def get_usage_limits(self, api_key: str, account_id: int | None = None) -> dict:
        creds = self._parse_credentials(api_key)
        access_token, refresh_token, client_id, client_secret, region, profile_arn = self._extract_credentials(creds)
        
        access_token = await self._ensure_valid_token(creds, account_id)
        if not access_token:
            raise Exception("Missing access token")
        
        try:
            return await self._request_usage_limits(access_token, region, profile_arn)
        except Exception as e:
            if "403" in str(e) and refresh_token and client_id and client_secret:
                refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
                if refresh_result:
                    self._apply_refresh_result(creds, refresh_result)
                    await self._persist_credentials(account_id, creds)
                    return await self._request_usage_limits(refresh_result["accessToken"], region, profile_arn)
            raise

    def _normalize_thinking_budget_tokens(self, budget_tokens) -> int:
        try:
            value = int(budget_tokens)
        except (TypeError, ValueError):
            value = self.THINKING_DEFAULT_BUDGET_TOKENS
        if value <= 0:
            value = self.THINKING_DEFAULT_BUDGET_TOKENS
        return min(value, self.THINKING_MAX_BUDGET_TOKENS)

    def _generate_thinking_prefix(self, thinking) -> str | None:
        if not thinking or thinking.get("type") != "enabled":
            return None
        budget = self._normalize_thinking_budget_tokens(thinking.get("budget_tokens"))
        return f"{self.THINKING_MODE_TAG}enabled{self.THINKING_MODE_TAG.replace('<', '</')}{self.THINKING_MAX_LEN_TAG}{budget}{self.THINKING_MAX_LEN_TAG.replace('<', '</')}"

    def _has_thinking_prefix(self, text: str) -> bool:
        if not text:
            return False
        return self.THINKING_MODE_TAG in text or self.THINKING_MAX_LEN_TAG in text
    
    def _build_request(self, messages: list, model: str, system: str = None, tools: list = None, thinking: dict = None) -> dict:
        conversation_id = str(uuid.uuid4())
        kiro_model = self.get_mapped_model(model)
        
        system_prompt = get_content_text(system) if system else ""
        thinking_prefix = self._generate_thinking_prefix(thinking)
        if thinking_prefix:
            if not system_prompt:
                system_prompt = thinking_prefix
            elif not self._has_thinking_prefix(system_prompt):
                system_prompt = f"{thinking_prefix}\n{system_prompt}"
        
        user_content, history, tool_results = convert_anthropic_messages_to_kiro(messages, system_prompt)
        kiro_tools = convert_anthropic_tools_to_kiro(tools) if tools else []
        
        request = {
            "conversationState": {
                "chatTriggerType": "MANUAL",
                "conversationId": conversation_id,
                "currentMessage": {
                    "userInputMessage": {
                        "content": user_content,
                        "modelId": kiro_model,
                        "origin": "AI_EDITOR"
                    }
                }
            }
        }
        
        if history:
            request["conversationState"]["history"] = history
        
        if tool_results or kiro_tools:
            context = {}
            if tool_results:
                context["toolResults"] = tool_results
            if kiro_tools:
                context["tools"] = kiro_tools
            request["conversationState"]["currentMessage"]["userInputMessage"]["userInputMessageContext"] = context
        
        return request
    
    def _estimate_input_tokens(self, messages: list, system: str = None, tools: list = None, thinking: dict = None, model: str = "") -> int:
        return count_request_tokens(
            messages=messages or [],
            system=system or "",
            tools=tools,
            model=model,
            thinking_config=thinking
        )
    
    async def _refresh_token(self, refresh_token: str, client_id: str, client_secret: str, region: str) -> str:
        try:
            sso_url = f"https://oidc.{region}.amazonaws.com/token"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    sso_url,
                    json={
                        "clientId": client_id,
                        "clientSecret": client_secret,
                        "refreshToken": refresh_token,
                        "grantType": "refresh_token"
                    },
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    new_access_token = data.get("accessToken")
                    expires_in = data.get("expiresIn", 3600)
                    if new_access_token:
                        return {
                            "accessToken": new_access_token,
                            "expiresIn": expires_in,
                            "refreshedAt": int(datetime.now(timezone.utc).timestamp())
                        }
                    else:
                        logger.error("Token refresh response missing accessToken")
                        return None
                else:
                    error = response.text
                    logger.error(f"Token refresh failed ({response.status_code}): {error}")
                    return None
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None
    
    def _is_token_expired(self, creds: dict) -> bool:
        refreshed_at = creds.get("refreshedAt", 0)
        expires_in = creds.get("expiresIn", 3600)
        
        if refreshed_at == 0 and "expiresAt" in creds:
            try:
                expires_at_str = creds.get("expiresAt")
                if expires_at_str:
                    expires_at_dt = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    expires_at_timestamp = int(expires_at_dt.timestamp())
                    refreshed_at = expires_at_timestamp - expires_in
                    logger.info(f"Converted expiresAt '{expires_at_str}' to refreshedAt={refreshed_at}, expiresIn={expires_in}")
            except Exception as e:
                logger.warning(f"Failed to parse expiresAt from credentials: {e}")
        
        if refreshed_at == 0:
            logger.info(f"No refreshedAt or valid expiresAt found in credentials, assuming token expired")
            return True
        
        current_time = int(datetime.now(timezone.utc).timestamp())
        expiry_time = refreshed_at + expires_in - 60
        is_expired = current_time >= expiry_time
        return is_expired
    
    async def chat(self, api_key: str, model: str, data: dict):
        creds = self._parse_credentials(api_key)
        access_token, refresh_token, client_id, client_secret, region, profile_arn = self._extract_credentials(creds)
        account_id = data.get("_account_id")
        
        access_token = await self._ensure_valid_token(creds, account_id)
        if not access_token:
            raise Exception("Missing accessToken in Kiro credentials")
        
        messages = data.get("messages", [])
        system = data.get("system")
        tools = data.get("tools")
        thinking = data.get("thinking")
        
        request_data = self._build_request(messages, model, system, tools, thinking)
        
        if profile_arn:
            request_data["profileArn"] = profile_arn
        
        url = self._get_base_url(region)
        headers = self._build_headers(access_token)
        
        try:
            async for chunk in self._chat_stream(url, headers, request_data, model, thinking, messages, system, tools, account_id):
                yield chunk
        except Exception as e:
            if "403" in str(e) and refresh_token and client_id and client_secret:
                refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
                if refresh_result:
                    self._apply_refresh_result(creds, refresh_result)
                    await self._persist_credentials(account_id, creds)
                    headers = self._build_headers(refresh_result["accessToken"])
                    async for chunk in self._chat_stream(url, headers, request_data, model, thinking, messages, system, tools, account_id):
                        yield chunk
                else:
                    raise
            else:
                raise

    async def _chat_stream(self, url: str, headers: dict, data: dict, model: str, thinking: dict = None, messages: list = None, system: str = None, tools: list = None, account_id: int | None = None):
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=data) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    logger.error(f"Kiro API error ({resp.status_code}): {error_text}")
                    raise Exception(f"Kiro API error: {resp.status_code}")
                
                start_event = {
                    "type": "message_start",
                    "message": {
                        "id": f"msg_{uuid.uuid4().hex[:8]}",
                        "type": "message",
                        "role": "assistant",
                        "model": model,
                        "content": [],
                        "usage": {
                            "input_tokens": self._estimate_input_tokens(messages, system, tools, thinking),
                            "output_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0
                        }
                    }
                }
                yield f"event: message_start\ndata: {json.dumps(start_event)}\n\n".encode("utf-8")

                thinking_requested = bool(thinking and thinking.get("type") == "enabled")
                converter = KiroStreamConverter(self.THINKING_START_TAG, self.THINKING_END_TAG)
                
                def encode_events(events: list) -> list:
                    return [f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode("utf-8") for ev in events]

                buffer = ""
                usage_delta = None

                async for chunk in resp.aiter_bytes():
                    buffer += chunk.decode("utf-8", errors="ignore")
                    events, remaining = converter.parse_aws_event_stream_buffer(buffer)
                    buffer = remaining

                    for event in events:
                        if event["type"] == "content" and event.get("data") is not None:
                            sse_events = converter.process_content_event(event["data"], thinking_requested)
                            for out in encode_events(sse_events):
                                yield out
                        elif event["type"] == "toolUse":
                            converter.process_tool_use_event(event.get("data") or {})
                        elif event["type"] == "toolUseInput":
                            converter.process_tool_use_input_event(event.get("data", {}).get("input") or "")
                        elif event["type"] == "toolUseStop":
                            converter.process_tool_use_stop_event(event.get("data", {}).get("stop", False))
                        elif event["type"] == "usage":
                            usage_data = event.get("data") or {}
                            unit = (usage_data.get("unit") or "").lower()
                            unit_plural = (usage_data.get("unitPlural") or "").lower()
                            if unit == "credit" or unit_plural == "credits":
                                try:
                                    usage_delta = float(usage_data.get("usage"))
                                except (TypeError, ValueError):
                                    pass

                converter.finalize_current_tool_call()

                for out in encode_events(converter.finalize_thinking_buffer(thinking_requested)):
                    yield out

                for out in encode_events(converter.stop_block(converter.get_text_block_index())):
                    yield out

                for out in encode_events(converter.generate_tool_call_events()):
                    yield out

                output_tokens = count_tokens(converter.get_total_content())
                input_tokens = self._estimate_input_tokens(messages, system, tools, thinking)
                
                if account_id and usage_delta and usage_delta > 0:
                    await add_account_credit_usage(account_id, usage_delta)
                
                tool_calls = converter.get_tool_calls()
                message_delta = {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use" if tool_calls else "end_turn"},
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
                }
                yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n".encode("utf-8")
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n".encode("utf-8")
    
    async def list_models(self, api_key: str) -> list:
        return list(self.MODEL_MAPPING.keys())
