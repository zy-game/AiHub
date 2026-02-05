import json
import uuid
import re
import aiohttp
from datetime import datetime, timezone
from models import update_account, add_account_credit_usage
from urllib.parse import urlencode
from typing import AsyncIterator
from .base import BaseProvider
from utils.logger import logger
from utils.text import get_content_text, find_real_tag
from utils.token_counter import count_tokens

class KiroProvider(BaseProvider):
    """Kiro Provider - AWS CodeWhisperer based Claude access"""
    
    # Kiro uses regional endpoints
    BASE_URL_TEMPLATE = "https://q.{region}.amazonaws.com/generateAssistantResponse"
    REFRESH_URL_TEMPLATE = "https://prod.{region}.auth.desktop.kiro.dev/refreshToken"
    
    DEFAULT_REGION = "us-east-1"
    KIRO_VERSION = "0.8.140"
    USAGE_RESOURCE_TYPE = "AGENTIC_REQUEST"
    ORIGIN_AI_EDITOR = "AI_EDITOR"
    TOTAL_CONTEXT_TOKENS = 172500
    
    # Model mapping: external name -> internal Kiro model ID
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
    
    def get_format(self) -> str:
        """Kiro uses Claude message format"""
        return "claude"
    
    def _get_base_url(self, region: str = None) -> str:
        return self.BASE_URL_TEMPLATE.format(region=region or self.DEFAULT_REGION)
    
    def _get_refresh_url(self, region: str = None) -> str:
        return self.REFRESH_URL_TEMPLATE.format(region=region or self.DEFAULT_REGION)
    
    def _get_kiro_model(self, model: str) -> str:
        return self.MODEL_MAPPING.get(model, self.MODEL_MAPPING.get("claude-sonnet-4-5"))
    
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
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Kiro usage limits error ({resp.status}): {error_text}")
                return await resp.json(content_type=None)

    def extract_kiro_points(self, usage_data: dict) -> tuple[int, int]:
        """Extract total usage and limit from Kiro usage data.
        
        Kiro has two types of credits:
        1. Monthly credits (currentUsage/usageLimit in breakdown)
        2. Free trial credits (freeTrialInfo.currentUsage/usageLimit)
        
        Total = monthly + freeTrial
        """
        if not usage_data:
            return 0, 0
        
        # Check for simple format first
        used_count = usage_data.get("usedCount")
        limit_count = usage_data.get("limitCount")
        if used_count is not None and limit_count is not None:
            return int(used_count), int(limit_count)
        
        breakdowns = usage_data.get("usageBreakdownList") or []
        
        # Find the AGENTIC_REQUEST breakdown
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
        
        # Extract monthly credits
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
        
        # Extract free trial credits
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
        
        # Total = monthly + freeTrial
        total_used = int(monthly_used_val + free_trial_used_val)
        total_limit = int(monthly_limit_val + free_trial_limit_val)
        
        return total_used, total_limit

    async def _persist_credentials(self, account_id: int | None, creds: dict) -> None:
        if not account_id:
            return
        await update_account(account_id, api_key=json.dumps(creds, ensure_ascii=False))

    async def get_usage_limits(self, api_key: str, account_id: int | None = None) -> dict:
        try:
            creds = json.loads(api_key) if isinstance(api_key, str) else dict(api_key)
        except Exception:
            raise Exception("Invalid Kiro credentials")
        access_token = creds.get("accessToken") or creds.get("access_token")
        refresh_token = creds.get("refreshToken") or creds.get("refresh_token")
        client_id = creds.get("clientId") or creds.get("client_id")
        client_secret = creds.get("clientSecret") or creds.get("client_secret")
        region = creds.get("region") or self.DEFAULT_REGION
        profile_arn = creds.get("profileArn") or creds.get("profile_arn")
        
        # Check if token is expired and refresh if needed
        if self._is_token_expired(creds) and refresh_token and client_id and client_secret:
            logger.info(f"Access token expired, refreshing before usage check...")
            refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
            if refresh_result:
                creds["accessToken"] = refresh_result["accessToken"]
                creds["expiresIn"] = refresh_result["expiresIn"]
                creds["refreshedAt"] = refresh_result["refreshedAt"]
                access_token = refresh_result["accessToken"]
                await self._persist_credentials(account_id, creds)
                logger.info(f"Access token refreshed successfully")
        
        if not access_token and refresh_token and client_id and client_secret:
            refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
            if refresh_result:
                creds["accessToken"] = refresh_result["accessToken"]
                creds["expiresIn"] = refresh_result["expiresIn"]
                creds["refreshedAt"] = refresh_result["refreshedAt"]
                access_token = refresh_result["accessToken"]
                await self._persist_credentials(account_id, creds)
        if not access_token:
            raise Exception("Missing access token")
        try:
            return await self._request_usage_limits(access_token, region, profile_arn)
        except Exception as e:
            if "403" in str(e) and refresh_token and client_id and client_secret:
                refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
                if refresh_result:
                    creds["accessToken"] = refresh_result["accessToken"]
                    creds["expiresIn"] = refresh_result["expiresIn"]
                    creds["refreshedAt"] = refresh_result["refreshedAt"]
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
        kiro_model = self._get_kiro_model(model)
        system_prompt = get_content_text(system) if system else ""
        processed_messages = list(messages)
        if not processed_messages:
            raise Exception("No messages provided")

        thinking_prefix = self._generate_thinking_prefix(thinking)
        if thinking_prefix:
            if not system_prompt:
                system_prompt = thinking_prefix
            elif not self._has_thinking_prefix(system_prompt):
                system_prompt = f"{thinking_prefix}\n{system_prompt}"

        last_message = processed_messages[-1]
        if last_message.get("role") == "assistant":
            last_content = last_message.get("content")
            if isinstance(last_content, list) and last_content:
                first_part = last_content[0]
                if isinstance(first_part, dict) and first_part.get("type") == "text" and first_part.get("text") == "{":
                    processed_messages.pop()
                    if not processed_messages:
                        raise Exception("No messages provided")

        merged_messages = []
        for message in processed_messages:
            current = dict(message)
            content = current.get("content")
            if isinstance(content, list):
                current["content"] = list(content)
            if not merged_messages:
                merged_messages.append(current)
                continue
            last_msg = merged_messages[-1]
            if current.get("role") == last_msg.get("role"):
                last_content = last_msg.get("content")
                cur_content = current.get("content")
                if isinstance(last_content, list) and isinstance(cur_content, list):
                    last_content.extend(cur_content)
                elif isinstance(last_content, str) and isinstance(cur_content, str):
                    last_msg["content"] = f"{last_content}\n{cur_content}"
                elif isinstance(last_content, list) and isinstance(cur_content, str):
                    last_content.append({"type": "text", "text": cur_content})
                elif isinstance(last_content, str) and isinstance(cur_content, list):
                    last_msg["content"] = [{"type": "text", "text": last_content}] + cur_content
                else:
                    last_msg["content"] = f"{get_content_text(last_msg)}\n{get_content_text(current)}"
            else:
                merged_messages.append(current)

        processed_messages = merged_messages

        tools_context = {}
        if tools and isinstance(tools, list) and tools:
            filtered_tools = []
            for tool in tools:
                name = (tool.get("name") or "").lower()
                if name in {"web_search", "websearch"}:
                    continue
                filtered_tools.append(tool)
            if filtered_tools:
                kiro_tools = []
                for tool in filtered_tools:
                    description = tool.get("description", "") or ""
                    if len(description) > 9216:
                        description = description[:9216] + "..."
                    kiro_tools.append({
                        "toolSpecification": {
                            "name": tool.get("name", ""),
                            "description": description,
                            "inputSchema": {"json": tool.get("input_schema", {})}
                        }
                    })
                if kiro_tools:
                    tools_context = {"tools": kiro_tools}

        def _dedupe_tool_results(tool_results: list) -> list:
            seen_ids = set()
            unique_results = []
            for tr in tool_results:
                tool_id = tr.get("toolUseId")
                if tool_id and tool_id not in seen_ids:
                    seen_ids.add(tool_id)
                    unique_results.append(tr)
            return unique_results

        history = []
        start_index = 0
        if system_prompt:
            if processed_messages[0].get("role") == "user":
                first_user_content = get_content_text(processed_messages[0])
                history.append({
                    "userInputMessage": {
                        "content": f"{system_prompt}\n\n{first_user_content}",
                        "modelId": kiro_model,
                        "origin": "AI_EDITOR"
                    }
                })
                start_index = 1
            else:
                history.append({
                    "userInputMessage": {
                        "content": system_prompt,
                        "modelId": kiro_model,
                        "origin": "AI_EDITOR"
                    }
                })

        keep_image_threshold = 5
        for i in range(start_index, len(processed_messages) - 1):
            message = processed_messages[i]
            role = message.get("role")
            distance_from_end = (len(processed_messages) - 1) - i
            should_keep_images = distance_from_end <= keep_image_threshold
            if role == "user":
                user_input_message = {
                    "content": "",
                    "modelId": kiro_model,
                    "origin": "AI_EDITOR"
                }
                image_count = 0
                tool_results = []
                images = []
                if isinstance(message.get("content"), list):
                    for part in message["content"]:
                        if isinstance(part, dict) and part.get("type") == "text":
                            user_input_message["content"] += part.get("text", "")
                        elif isinstance(part, dict) and part.get("type") == "tool_result":
                            tool_results.append({
                                "content": [{"text": get_content_text(part.get("content"))}],
                                "status": part.get("status", "success"),
                                "toolUseId": part.get("tool_use_id", "")
                            })
                        elif isinstance(part, dict) and part.get("type") == "image":
                            source = part.get("source", {})
                            media_type = source.get("media_type", "")
                            data = source.get("data", "")
                            if should_keep_images and media_type and data:
                                images.append({
                                    "format": media_type.split("/")[-1],
                                    "source": {"bytes": data}
                                })
                            else:
                                image_count += 1
                        elif isinstance(part, str):
                            user_input_message["content"] += part
                else:
                    user_input_message["content"] = get_content_text(message)
                if images:
                    user_input_message["images"] = images
                if image_count > 0:
                    placeholder = f"[此消息包含 {image_count} 张图片，已在历史记录中省略]"
                    user_input_message["content"] = user_input_message["content"] + "\n" + placeholder if user_input_message["content"] else placeholder
                if tool_results:
                    unique_tool_results = _dedupe_tool_results(tool_results)
                    if unique_tool_results:
                        user_input_message["userInputMessageContext"] = {"toolResults": unique_tool_results}
                if not user_input_message["content"]:
                    user_input_message["content"] = "Tool results provided." if tool_results else "Continue"
                history.append({"userInputMessage": user_input_message})
            elif role == "assistant":
                assistant_response_message = {"content": ""}
                tool_uses = []
                thinking_text = ""
                if isinstance(message.get("content"), list):
                    for part in message["content"]:
                        if isinstance(part, dict) and part.get("type") == "text":
                            assistant_response_message["content"] += part.get("text", "")
                        elif isinstance(part, dict) and part.get("type") == "thinking":
                            thinking_text += part.get("thinking") or part.get("text", "")
                        elif isinstance(part, dict) and part.get("type") == "tool_use":
                            tool_uses.append({
                                "input": part.get("input"),
                                "name": part.get("name"),
                                "toolUseId": part.get("id")
                            })
                else:
                    assistant_response_message["content"] = get_content_text(message)
                if thinking_text:
                    assistant_response_message["content"] = assistant_response_message["content"] or ""
                    assistant_response_message["content"] = f"{self.THINKING_START_TAG}{thinking_text}{self.THINKING_END_TAG}\n\n{assistant_response_message['content']}" if assistant_response_message["content"] else f"{self.THINKING_START_TAG}{thinking_text}{self.THINKING_END_TAG}"
                if tool_uses:
                    assistant_response_message["toolUses"] = tool_uses
                history.append({"assistantResponseMessage": assistant_response_message})

        current_message = processed_messages[-1]
        current_content = ""
        current_tool_results = []
        current_images = []
        if current_message.get("role") == "assistant":
            assistant_response_message = {"content": "", "toolUses": []}
            thinking_text = ""
            if isinstance(current_message.get("content"), list):
                for part in current_message["content"]:
                    if isinstance(part, dict) and part.get("type") == "text":
                        assistant_response_message["content"] += part.get("text", "")
                    elif isinstance(part, dict) and part.get("type") == "thinking":
                        thinking_text += part.get("thinking") or part.get("text", "")
                    elif isinstance(part, dict) and part.get("type") == "tool_use":
                        assistant_response_message["toolUses"].append({
                            "input": part.get("input"),
                            "name": part.get("name"),
                            "toolUseId": part.get("id")
                        })
            else:
                assistant_response_message["content"] = get_content_text(current_message)
            if thinking_text:
                assistant_response_message["content"] = assistant_response_message["content"] or ""
                assistant_response_message["content"] = f"{self.THINKING_START_TAG}{thinking_text}{self.THINKING_END_TAG}\n\n{assistant_response_message['content']}" if assistant_response_message["content"] else f"{self.THINKING_START_TAG}{thinking_text}{self.THINKING_END_TAG}"
            if not assistant_response_message["toolUses"]:
                assistant_response_message.pop("toolUses", None)
            history.append({"assistantResponseMessage": assistant_response_message})
            current_content = "Continue"
        else:
            if history:
                last_history_item = history[-1]
                if "assistantResponseMessage" not in last_history_item:
                    history.append({"assistantResponseMessage": {"content": "Continue"}})
            if isinstance(current_message.get("content"), list):
                for part in current_message["content"]:
                    if isinstance(part, dict) and part.get("type") == "text":
                        current_content += part.get("text", "")
                    elif isinstance(part, dict) and part.get("type") == "tool_result":
                        current_tool_results.append({
                            "content": [{"text": get_content_text(part.get("content"))}],
                            "status": part.get("status", "success"),
                            "toolUseId": part.get("tool_use_id", "")
                        })
                    elif isinstance(part, dict) and part.get("type") == "image":
                        source = part.get("source", {})
                        media_type = source.get("media_type", "")
                        data = source.get("data", "")
                        if media_type and data:
                            current_images.append({
                                "format": media_type.split("/")[-1],
                                "source": {"bytes": data}
                            })
                    elif isinstance(part, str):
                        current_content += part
            else:
                current_content = get_content_text(current_message)
            if not current_content:
                current_content = "Tool results provided." if current_tool_results else "Continue"

        request = {
            "conversationState": {
                "chatTriggerType": "MANUAL",
                "conversationId": conversation_id,
                "currentMessage": {}
            }
        }
        if history:
            request["conversationState"]["history"] = history

        user_input_message = {
            "content": current_content,
            "modelId": kiro_model,
            "origin": "AI_EDITOR"
        }
        if current_images:
            user_input_message["images"] = current_images

        user_input_message_context = {}
        if current_tool_results:
            user_input_message_context["toolResults"] = _dedupe_tool_results(current_tool_results)
        if tools_context.get("tools"):
            user_input_message_context["tools"] = tools_context["tools"]
        if user_input_message_context:
            user_input_message["userInputMessageContext"] = user_input_message_context

        request["conversationState"]["currentMessage"]["userInputMessage"] = user_input_message
        return request
    
    def _parse_response(self, raw_data: str) -> tuple[str, list]:
        """Parse Kiro SSE response to extract content and tool calls"""
        raw_str = raw_data.decode("utf-8", errors="ignore") if isinstance(raw_data, (bytes, bytearray)) else str(raw_data)
        full_content = ""
        tool_calls = []
        current_tool = None
        
        sse_matches = re.findall(r":message-typeevent(\{[\s\S]*?(?=:event-type|$))", raw_str)
        legacy_matches = re.findall(r"event(\{.*?(?=event\{|$))", raw_str, flags=re.S)
        matches = sse_matches if sse_matches else legacy_matches
        
        for block in matches:
            if not block or not block.strip():
                continue
            search_pos = 0
            while True:
                end_pos = block.find("}", search_pos + 1)
                if end_pos == -1:
                    break
                json_candidate = block[:end_pos + 1].strip()
                try:
                    event_data = json.loads(json_candidate)
                except json.JSONDecodeError:
                    search_pos = end_pos
                    continue
                
                if event_data.get("name") and event_data.get("toolUseId"):
                    if current_tool and current_tool.get("toolUseId") != event_data["toolUseId"]:
                        tool_calls.append(self._finalize_tool(current_tool))
                        current_tool = None
                    if not current_tool:
                        current_tool = {
                            "toolUseId": event_data["toolUseId"],
                            "name": event_data["name"],
                            "input": ""
                        }
                    if event_data.get("input"):
                        current_tool["input"] += event_data["input"]
                    if event_data.get("stop"):
                        tool_calls.append(self._finalize_tool(current_tool))
                        current_tool = None
                elif not event_data.get("followupPrompt") and event_data.get("content"):
                    decoded_content = event_data["content"]
                    decoded_content = re.sub(r"(?<!\\)\\n", "\n", decoded_content)
                    full_content += decoded_content
                break
        
        if current_tool:
            tool_calls.append(self._finalize_tool(current_tool))
        
        return full_content, tool_calls

    def _parse_aws_event_stream_buffer(self, buffer: str) -> tuple[list, str]:
        events = []
        remaining = buffer
        search_start = 0
        while True:
            content_start = remaining.find('{"content":', search_start)
            name_start = remaining.find('{"name":', search_start)
            followup_start = remaining.find('{"followupPrompt":', search_start)
            input_start = remaining.find('{"input":', search_start)
            stop_start = remaining.find('{"stop":', search_start)
            context_usage_start = remaining.find('{"contextUsagePercentage":', search_start)
            usage_start = remaining.find('{"unit":', search_start)
            usage_match = re.search(r'"usage"\s*:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', remaining)
            candidates = [pos for pos in [content_start, name_start, followup_start, input_start, stop_start, context_usage_start, usage_start] if pos >= 0]
            if not candidates:
                break
            json_start = min(candidates)
            brace_count = 0
            json_end = -1
            in_string = False
            escape_next = False
            for i in range(json_start, len(remaining)):
                char = remaining[i]
                if escape_next:
                    escape_next = False
                    continue
                if char == "\\":
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i
                            break
            if json_end < 0:
                remaining = remaining[json_start:]
                break
            json_str = remaining[json_start:json_end + 1]
            try:
                parsed = json.loads(json_str)
                if parsed.get("content") is not None and not parsed.get("followupPrompt"):
                    events.append({"type": "content", "data": parsed.get("content", "")})
                elif parsed.get("name") and parsed.get("toolUseId"):
                    events.append({
                        "type": "toolUse",
                        "data": {
                            "name": parsed.get("name"),
                            "toolUseId": parsed.get("toolUseId"),
                            "input": parsed.get("input", ""),
                            "stop": parsed.get("stop", False)
                        }
                    })
                elif "input" in parsed and not parsed.get("name"):
                    events.append({"type": "toolUseInput", "data": {"input": parsed.get("input", "")}})
                elif "stop" in parsed and "contextUsagePercentage" not in parsed:
                    events.append({"type": "toolUseStop", "data": {"stop": parsed.get("stop")}})
                elif "usage" in parsed:
                    events.append({
                        "type": "usage",
                        "data": {
                            "usage": parsed.get("usage"),
                            "unit": parsed.get("unit"),
                            "unitPlural": parsed.get("unitPlural")
                        }
                    })
            except Exception:
                pass
            search_start = json_end + 1
            if search_start >= len(remaining):
                remaining = ""
                break
        if search_start > 0 and remaining:
            remaining = remaining[search_start:]
        return events, remaining

    def _estimate_input_tokens(self, messages: list, system: str = None, tools: list = None, thinking: dict = None) -> int:
        total = 0
        if system:
            total += count_tokens(get_content_text(system))
        if thinking and thinking.get("type") == "enabled":
            budget = self._normalize_thinking_budget_tokens(thinking.get("budget_tokens"))
            prefix_text = f"{self.THINKING_MODE_TAG}enabled{self.THINKING_MODE_TAG.replace('<', '</')}{self.THINKING_MAX_LEN_TAG}{budget}{self.THINKING_MAX_LEN_TAG.replace('<', '</')}"
            total += count_tokens(prefix_text)
        for message in messages or []:
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        part_type = part.get("type")
                        if part_type == "text":
                            total += count_tokens(part.get("text") or "")
                        elif part_type == "thinking":
                            total += count_tokens(part.get("thinking") or part.get("text") or "")
                        elif part_type == "tool_result":
                            total += count_tokens(get_content_text(part.get("content")))
                        elif part_type == "tool_use":
                            total += count_tokens(part.get("name") or "")
                            total += count_tokens(json.dumps(part.get("input") or {}, ensure_ascii=False))
                        elif part_type == "image":
                            total += 1600
                        elif part_type == "document":
                            source = part.get("source") or {}
                            data = source.get("data")
                            if data:
                                estimated_chars = int(len(data) * 0.75)
                                total += max(1, (estimated_chars + 3) // 4)
                    elif isinstance(part, str):
                        total += count_tokens(part)
            else:
                total += count_tokens(get_content_text(message))
        if tools and isinstance(tools, list):
            for tool in tools:
                total += count_tokens(tool.get("name") or "")
                total += count_tokens(tool.get("description") or "")
                schema = tool.get("input_schema") or {}
                total += count_tokens(json.dumps(schema, ensure_ascii=False))
        return total
    
    def _finalize_tool(self, tool: dict) -> dict:
        """Convert internal tool format to Claude format"""
        input_data = tool.get("input", "")
        try:
            input_obj = json.loads(input_data) if isinstance(input_data, str) else input_data
        except:
            input_obj = {"raw": input_data}
        
        return {
            "type": "tool_use",
            "id": tool["toolUseId"],
            "name": tool["name"],
            "input": input_obj
        }
    
    async def chat(self, api_key: str, model: str, data: dict):
        """
        Chat with Kiro API (streaming only).
        
        api_key format: JSON string containing:
        {
            "accessToken": "...",
            "refreshToken": "...",
            "clientId": "...",      // for token refresh
            "clientSecret": "...",  // for token refresh
            "region": "us-east-1",  // optional
            "profileArn": "...",    // optional, for social auth
            "refreshedAt": 1234567890,  // timestamp when token was refreshed
            "expiresIn": 3600       // token expiry in seconds
        }
        """
        try:
            creds = json.loads(api_key)
        except:
            raise Exception("Invalid Kiro credentials format. Expected JSON with accessToken.")
        
        access_token = creds.get("accessToken")
        refresh_token = creds.get("refreshToken")
        client_id = creds.get("clientId")
        client_secret = creds.get("clientSecret")
        region = creds.get("region", self.DEFAULT_REGION)
        profile_arn = creds.get("profileArn")
        account_id = data.get("_account_id")
        
        # Check if token is expired and refresh if needed
        if self._is_token_expired(creds) and refresh_token and client_id and client_secret:
            logger.info(f"Access token expired, refreshing...")
            refresh_result = await self._refresh_token(refresh_token, client_id, client_secret, region)
            if refresh_result:
                creds["accessToken"] = refresh_result["accessToken"]
                creds["expiresIn"] = refresh_result["expiresIn"]
                creds["refreshedAt"] = refresh_result["refreshedAt"]
                access_token = refresh_result["accessToken"]
                await self._persist_credentials(account_id, creds)
                logger.info(f"Access token refreshed successfully for account {account_id} with time {creds["refreshedAt"]}")
            else:
                logger.warning(f"Failed to refresh access token for account {account_id}")
        
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
                    creds["accessToken"] = refresh_result["accessToken"]
                    creds["expiresIn"] = refresh_result["expiresIn"]
                    creds["refreshedAt"] = refresh_result["refreshedAt"]
                    await self._persist_credentials(account_id, creds)
                    headers = self._build_headers(refresh_result["accessToken"])
                    async for chunk in self._chat_stream(url, headers, request_data, model, thinking, messages, system, tools, account_id):
                        yield chunk
                else:
                    raise
            else:
                raise
    
    async def _refresh_token(self, refresh_token: str, client_id: str, client_secret: str, region: str) -> str:
        """Refresh access token using refresh token"""
        try:
            sso_url = f"https://oidc.{region}.amazonaws.com/token"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    sso_url,
                    json={
                        "clientId": client_id,
                        "clientSecret": client_secret,
                        "refreshToken": refresh_token,
                        "grantType": "refresh_token"
                    },
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        new_access_token = data.get("accessToken")
                        expires_in = data.get("expiresIn", 3600)  # Default 1 hour in seconds
                        if new_access_token:
                            # Return both token and expiry time
                            return {
                                "accessToken": new_access_token,
                                "expiresIn": expires_in,
                                "refreshedAt": int(datetime.now(timezone.utc).timestamp())
                            }
                        else:
                            logger.error("Token refresh response missing accessToken")
                            return None
                    else:
                        error = await resp.text()
                        logger.error(f"Token refresh failed ({resp.status}): {error}")
                        return None
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None
    
    def _is_token_expired(self, creds: dict) -> bool:
        """Check if access token is expired or about to expire"""
        refreshed_at = creds.get("refreshedAt", 0)
        expires_in = creds.get("expiresIn", 3600)
        
        if refreshed_at == 0:
            # No refresh time recorded, assume expired
            logger.info(f"No refreshedAt found in credentials, assuming token expired")
            return True
        
        current_time = int(datetime.now(timezone.utc).timestamp())
        # Add 60 second buffer to refresh before actual expiry
        expiry_time = refreshed_at + expires_in - 60
        
        is_expired = current_time >= expiry_time
        if is_expired:
            logger.info(f"Token expired: current={current_time}, expiry={expiry_time}, refreshed_at={refreshed_at}, expires_in={expires_in}")
        else:
            remaining = expiry_time - current_time
            logger.info(f"Token valid for {remaining} more seconds")
        
        return is_expired
    
    async def _chat_stream(self, url: str, headers: dict, data: dict, model: str, thinking: dict = None, messages: list = None, system: str = None, tools: list = None, account_id: int | None = None):

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Kiro API error ({resp.status}): {error_text}")
                    raise Exception(f"Kiro API error: {resp.status}")
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
                stream_state = {
                    "buffer": "",
                    "in_thinking": False,
                    "thinking_extracted": False,
                    "thinking_block_index": None,
                    "text_block_index": None,
                    "next_block_index": 0,
                    "stopped_blocks": set()
                }

                def ensure_block_start(block_type: str) -> list:
                    if block_type == "thinking":
                        if stream_state["thinking_block_index"] is not None:
                            return []
                        idx = stream_state["next_block_index"]
                        stream_state["next_block_index"] += 1
                        stream_state["thinking_block_index"] = idx
                        return [{
                            "type": "content_block_start",
                            "index": idx,
                            "content_block": {"type": "thinking", "thinking": ""}
                        }]
                    if block_type == "text":
                        if stream_state["text_block_index"] is not None:
                            return []
                        idx = stream_state["next_block_index"]
                        stream_state["next_block_index"] += 1
                        stream_state["text_block_index"] = idx
                        return [{
                            "type": "content_block_start",
                            "index": idx,
                            "content_block": {"type": "text", "text": ""}
                        }]
                    return []

                def stop_block(index: int | None) -> list:
                    if index is None or index in stream_state["stopped_blocks"]:
                        return []
                    stream_state["stopped_blocks"].add(index)
                    return [{"type": "content_block_stop", "index": index}]

                def create_text_delta_events(text: str) -> list:
                    events = []
                    events.extend(ensure_block_start("text"))
                    events.append({
                        "type": "content_block_delta",
                        "index": stream_state["text_block_index"],
                        "delta": {"type": "text_delta", "text": text}
                    })
                    return events

                def create_thinking_delta_events(thinking_text: str) -> list:
                    events = []
                    events.extend(ensure_block_start("thinking"))
                    events.append({
                        "type": "content_block_delta",
                        "index": stream_state["thinking_block_index"],
                        "delta": {"type": "thinking_delta", "thinking": thinking_text}
                    })
                    return events

                async def push_events(events: list):
                    for ev in events:
                        yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode("utf-8")

                buffer = ""
                last_content_event = None
                tool_calls = []
                current_tool_call = None
                total_content = ""
                context_usage_percentage = None
                usage_delta = None

                async for chunk in resp.content.iter_any():
                    buffer += chunk.decode("utf-8", errors="ignore")
                    events, remaining = self._parse_aws_event_stream_buffer(buffer)
                    buffer = remaining

                    for event in events:
                        if event["type"] == "content" and event.get("data") is not None:
                            content_piece = event["data"]
                            if last_content_event == content_piece:
                                continue
                            last_content_event = content_piece
                            total_content += content_piece
                            if not thinking_requested:
                                async for out in push_events(create_text_delta_events(content_piece)):
                                    yield out
                                continue
                            stream_state["buffer"] += content_piece
                            pending = []
                            while stream_state["buffer"]:
                                if not stream_state["in_thinking"] and not stream_state["thinking_extracted"]:
                                    start_pos = find_real_tag(stream_state["buffer"], self.THINKING_START_TAG)
                                    if start_pos != -1:
                                        before = stream_state["buffer"][:start_pos]
                                        if before:
                                            pending.extend(create_text_delta_events(before))
                                        stream_state["buffer"] = stream_state["buffer"][start_pos + len(self.THINKING_START_TAG):]
                                        stream_state["in_thinking"] = True
                                        continue
                                    safe_len = max(0, len(stream_state["buffer"]) - len(self.THINKING_START_TAG))
                                    if safe_len > 0:
                                        safe_text = stream_state["buffer"][:safe_len]
                                        if safe_text:
                                            pending.extend(create_text_delta_events(safe_text))
                                        stream_state["buffer"] = stream_state["buffer"][safe_len:]
                                    break
                                if stream_state["in_thinking"]:
                                    end_pos = find_real_tag(stream_state["buffer"], self.THINKING_END_TAG)
                                    if end_pos != -1:
                                        thinking_part = stream_state["buffer"][:end_pos]
                                        if thinking_part:
                                            pending.extend(create_thinking_delta_events(thinking_part))
                                        stream_state["buffer"] = stream_state["buffer"][end_pos + len(self.THINKING_END_TAG):]
                                        stream_state["in_thinking"] = False
                                        stream_state["thinking_extracted"] = True
                                        pending.extend(create_thinking_delta_events(""))
                                        pending.extend(stop_block(stream_state["thinking_block_index"]))
                                        if stream_state["buffer"].startswith("\n\n"):
                                            stream_state["buffer"] = stream_state["buffer"][2:]
                                        continue
                                    safe_len = max(0, len(stream_state["buffer"]) - len(self.THINKING_END_TAG))
                                    if safe_len > 0:
                                        safe_thinking = stream_state["buffer"][:safe_len]
                                        if safe_thinking:
                                            pending.extend(create_thinking_delta_events(safe_thinking))
                                        stream_state["buffer"] = stream_state["buffer"][safe_len:]
                                    break
                                if stream_state["thinking_extracted"]:
                                    rest = stream_state["buffer"]
                                    stream_state["buffer"] = ""
                                    if rest:
                                        pending.extend(create_text_delta_events(rest))
                                    break
                            async for out in push_events(pending):
                                yield out
                        elif event["type"] == "toolUse":
                            tc = event.get("data") or {}
                            if tc.get("name"):
                                total_content += tc["name"]
                            if tc.get("input"):
                                total_content += tc["input"]
                            if tc.get("name") and tc.get("toolUseId"):
                                if current_tool_call and current_tool_call["toolUseId"] == tc["toolUseId"]:
                                    current_tool_call["input"] += tc.get("input") or ""
                                else:
                                    if current_tool_call:
                                        try:
                                            current_tool_call["input"] = json.loads(current_tool_call["input"])
                                        except Exception:
                                            pass
                                        tool_calls.append(current_tool_call)
                                    current_tool_call = {
                                        "toolUseId": tc["toolUseId"],
                                        "name": tc["name"],
                                        "input": tc.get("input") or ""
                                    }
                                if tc.get("stop"):
                                    try:
                                        current_tool_call["input"] = json.loads(current_tool_call["input"])
                                    except Exception:
                                        pass
                                    tool_calls.append(current_tool_call)
                                    current_tool_call = None
                        elif event["type"] == "toolUseInput":
                            input_piece = event.get("data", {}).get("input")
                            if input_piece:
                                total_content += input_piece
                            if current_tool_call:
                                current_tool_call["input"] += input_piece or ""
                        elif event["type"] == "toolUseStop":
                            if current_tool_call and event.get("data", {}).get("stop"):
                                try:
                                    current_tool_call["input"] = json.loads(current_tool_call["input"])
                                except Exception:
                                    pass
                                tool_calls.append(current_tool_call)
                                current_tool_call = None
                        elif event["type"] == "contextUsage":
                            context_usage_percentage = event.get("data", {}).get("contextUsagePercentage")
                        elif event["type"] == "usage":
                            usage_data = event.get("data") or {}
                            unit = (usage_data.get("unit") or "").lower()
                            unit_plural = (usage_data.get("unitPlural") or "").lower()
                            if unit == "credit" or unit_plural == "credits":
                                try:
                                    usage_delta = float(usage_data.get("usage"))
                                except (TypeError, ValueError):
                                    pass

                if current_tool_call:
                    try:
                        current_tool_call["input"] = json.loads(current_tool_call["input"])
                    except Exception:
                        pass
                    tool_calls.append(current_tool_call)
                    current_tool_call = None

                if thinking_requested and stream_state["buffer"]:
                    if stream_state["in_thinking"]:
                        async for out in push_events(create_thinking_delta_events(stream_state["buffer"])):
                            yield out
                        stream_state["buffer"] = ""
                        async for out in push_events(create_thinking_delta_events("")):
                            yield out
                        async for out in push_events(stop_block(stream_state["thinking_block_index"])):
                            yield out
                    elif not stream_state["thinking_extracted"]:
                        async for out in push_events(create_text_delta_events(stream_state["buffer"])):
                            yield out
                        stream_state["buffer"] = ""
                    else:
                        async for out in push_events(create_text_delta_events(stream_state["buffer"])):
                            yield out
                        stream_state["buffer"] = ""

                async for out in push_events(stop_block(stream_state["text_block_index"])):
                    yield out

                if tool_calls:
                    for tc in tool_calls:
                        idx = stream_state["next_block_index"]
                        stream_state["next_block_index"] += 1
                        tool_id = tc.get("toolUseId") or f"tool_{uuid.uuid4().hex}"
                        tool_name = tc.get("name") or ""
                        tool_input = tc.get("input")
                        partial_json = tool_input if isinstance(tool_input, str) else json.dumps(tool_input or {})
                        tool_start = {
                            "type": "content_block_start",
                            "index": idx,
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": tool_name,
                                "input": {}
                            }
                        }
                        tool_delta = {
                            "type": "content_block_delta",
                            "index": idx,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": partial_json
                            }
                        }
                        tool_stop = {"type": "content_block_stop", "index": idx}
                        for ev in [tool_start, tool_delta, tool_stop]:
                            yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode("utf-8")

                output_text = total_content
                if tool_calls:
                    output_text += json.dumps(tool_calls, ensure_ascii=False)
                output_tokens = count_tokens(output_text)
                input_tokens = self._estimate_input_tokens(messages, system, tools, thinking)
                
                # Only use usage_delta from usage event, ignore contextUsagePercentage
                points_delta = usage_delta if usage_delta is not None else None
                if account_id and points_delta and points_delta > 0:
                    await add_account_credit_usage(account_id, points_delta)
                message_delta = {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use" if tool_calls else "end_turn"},
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0
                    }
                }
                yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n".encode("utf-8")
                final_event = {"type": "message_stop"}
                yield f"event: message_stop\ndata: {json.dumps(final_event)}\n\n".encode("utf-8")
    
    async def list_models(self, api_key: str) -> list:
        return list(self.MODEL_MAPPING.keys())
