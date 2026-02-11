"""Kiro Converter - Anthropic/OpenAI/Gemini <-> Kiro format conversion

Enhanced version based on proxycast implementation:
- Tool count limit (max 50)
- Tool description truncation (max 500 chars)
- History message alternation fix
- OpenAI tool role message handling
- tool_choice: required support
- web_search special tool support
- tool_results deduplication
"""
import json
import hashlib
import re
import uuid
import time
from typing import List, Dict, Any, Tuple, Optional
from .base import BaseConverter

# Constants
MAX_TOOLS = 50
MAX_TOOL_DESCRIPTION_LENGTH = 500


def generate_session_id(messages: list) -> str:
    """Generate session ID based on message content"""
    content = json.dumps(messages[:3], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def extract_images_from_content(content) -> Tuple[str, List[dict]]:
    """Extract text and images from message content
    
    Returns:
        (text_content, images_list)
    """
    if isinstance(content, str):
        return content, []
    
    if not isinstance(content, list):
        return str(content) if content else "", []
    
    text_parts = []
    images = []
    
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get("type", "")
            
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            
            elif block_type == "image":
                # Anthropic format
                source = block.get("source", {})
                media_type = source.get("media_type", "image/jpeg")
                data = source.get("data", "")
                
                fmt = "jpeg"
                if "png" in media_type:
                    fmt = "png"
                elif "gif" in media_type:
                    fmt = "gif"
                elif "webp" in media_type:
                    fmt = "webp"
                
                if data:
                    images.append({
                        "format": fmt,
                        "source": {"bytes": data}
                    })
            
            elif block_type == "image_url":
                # OpenAI format
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")
                
                if url.startswith("data:"):
                    match = re.match(r'data:image/(\w+);base64,(.+)', url)
                    if match:
                        fmt = match.group(1)
                        data = match.group(2)
                        images.append({
                            "format": fmt,
                            "source": {"bytes": data}
                        })
    
    return "\n".join(text_parts), images


def truncate_description(desc: str, max_length: int = MAX_TOOL_DESCRIPTION_LENGTH) -> str:
    """Truncate tool description"""
    if len(desc) <= max_length:
        return desc
    return desc[:max_length - 3] + "..."


# ==================== Anthropic Conversion ====================

def convert_anthropic_tools_to_kiro(tools: List[dict]) -> List[dict]:
    """Convert Anthropic tool format to Kiro format
    
    Enhanced:
    - Limit to max 50 tools
    - Truncate long descriptions
    - Support web_search special tool
    """
    kiro_tools = []
    function_count = 0
    
    for tool in tools:
        name = tool.get("name", "")
        
        # Special tool: web_search
        if name in ("web_search", "web_search_20250305"):
            kiro_tools.append({
                "webSearchTool": {
                    "type": "web_search"
                }
            })
            continue
        
        # Limit tool count
        if function_count >= MAX_TOOLS:
            continue
        function_count += 1
        
        description = tool.get("description", f"Tool: {name}")
        description = truncate_description(description)
        
        input_schema = tool.get("input_schema", {"type": "object", "properties": {}})
        
        kiro_tools.append({
            "toolSpecification": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": input_schema
                }
            }
        })
    
    return kiro_tools


def fix_history_alternation(history: List[dict], model_id: str = "claude-sonnet-4") -> List[dict]:
    """Fix history to ensure strict user/assistant alternation and validate toolUses/toolResults pairing
    
    Kiro API rules:
    1. Messages must strictly alternate: user -> assistant -> user -> assistant
    2. When assistant has toolUses, next user must have corresponding toolResults
    3. When assistant has no toolUses, next user cannot have toolResults
    """
    if not history:
        return history
    
    import copy
    history = copy.deepcopy(history)
    
    fixed = []
    
    for i, item in enumerate(history):
        is_user = "userInputMessage" in item
        is_assistant = "assistantResponseMessage" in item
        
        if is_user:
            if fixed and "userInputMessage" in fixed[-1]:
                user_msg = item["userInputMessage"]
                ctx = user_msg.get("userInputMessageContext", {})
                has_tool_results = bool(ctx.get("toolResults"))
                
                if has_tool_results:
                    new_results = ctx["toolResults"]
                    last_user = fixed[-1]["userInputMessage"]
                    
                    if "userInputMessageContext" not in last_user:
                        last_user["userInputMessageContext"] = {}
                    
                    last_ctx = last_user["userInputMessageContext"]
                    if "toolResults" in last_ctx and last_ctx["toolResults"]:
                        last_ctx["toolResults"].extend(new_results)
                    else:
                        last_ctx["toolResults"] = new_results
                    continue
                else:
                    fixed.append({
                        "assistantResponseMessage": {
                            "content": "I understand."
                        }
                    })
            
            if fixed and "assistantResponseMessage" in fixed[-1]:
                last_assistant = fixed[-1]["assistantResponseMessage"]
                has_tool_uses = bool(last_assistant.get("toolUses"))
                
                user_msg = item["userInputMessage"]
                ctx = user_msg.get("userInputMessageContext", {})
                has_tool_results = bool(ctx.get("toolResults"))
                
                if has_tool_uses and not has_tool_results:
                    last_assistant.pop("toolUses", None)
                elif not has_tool_uses and has_tool_results:
                    item["userInputMessage"].pop("userInputMessageContext", None)
            
            fixed.append(item)
        
        elif is_assistant:
            if fixed and "assistantResponseMessage" in fixed[-1]:
                fixed.append({
                    "userInputMessage": {
                        "content": "Continue",
                        "modelId": model_id,
                        "origin": "AI_EDITOR"
                    }
                })
            
            if not fixed:
                fixed.append({
                    "userInputMessage": {
                        "content": "Continue",
                        "modelId": model_id,
                        "origin": "AI_EDITOR"
                    }
                })
            
            fixed.append(item)
    
    if fixed and "userInputMessage" in fixed[-1]:
        fixed.append({
            "assistantResponseMessage": {
                "content": "I understand."
            }
        })
    
    return fixed


def convert_anthropic_messages_to_kiro(messages: List[dict], system="") -> Tuple[str, List[dict], List[dict]]:
    """Convert Anthropic message format to Kiro format
    
    Returns:
        (user_content, history, tool_results)
    """
    history = []
    user_content = ""
    current_tool_results = []
    
    system_text = ""
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                system_text += block.get("text", "") + "\n"
            elif isinstance(block, str):
                system_text += block + "\n"
        system_text = system_text.strip()
    elif isinstance(system, str):
        system_text = system
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        is_last = (i == len(messages) - 1)
        
        tool_results = []
        text_parts = []
        
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        tr_content = block.get("content", "")
                        if isinstance(tr_content, list):
                            tr_text_parts = []
                            for tc in tr_content:
                                if isinstance(tc, dict) and tc.get("type") == "text":
                                    tr_text_parts.append(tc.get("text", ""))
                                elif isinstance(tc, str):
                                    tr_text_parts.append(tc)
                            tr_content = "\n".join(tr_text_parts)
                        
                        status = "error" if block.get("is_error") else "success"
                        
                        tool_results.append({
                            "content": [{"text": str(tr_content)}],
                            "status": status,
                            "toolUseId": block.get("tool_use_id", "")
                        })
                elif isinstance(block, str):
                    text_parts.append(block)
            
            content = "\n".join(text_parts) if text_parts else ""
        
        if tool_results:
            seen_ids = set()
            unique_results = []
            for tr in tool_results:
                if tr["toolUseId"] not in seen_ids:
                    seen_ids.add(tr["toolUseId"])
                    unique_results.append(tr)
            tool_results = unique_results
            
            if is_last:
                current_tool_results = tool_results
                user_content = content if content else "Tool results provided."
            else:
                history.append({
                    "userInputMessage": {
                        "content": content if content else "Tool results provided.",
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": tool_results
                        }
                    }
                })
            continue
        
        if role == "user":
            if system_text and not history:
                content = f"{system_text}\n\n{content}" if content else system_text
            
            if is_last:
                user_content = content if content else "Continue"
            else:
                history.append({
                    "userInputMessage": {
                        "content": content if content else "Continue",
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR"
                    }
                })
        
        elif role == "assistant":
            tool_uses = []
            assistant_text = ""
            
            if isinstance(msg.get("content"), list):
                text_parts = []
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            tool_uses.append({
                                "toolUseId": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input": block.get("input", {})
                            })
                        elif block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                assistant_text = "\n".join(text_parts)
            else:
                assistant_text = content if isinstance(content, str) else ""
            
            if not assistant_text:
                assistant_text = "I understand."
            
            assistant_msg = {
                "assistantResponseMessage": {
                    "content": assistant_text
                }
            }
            if tool_uses:
                assistant_msg["assistantResponseMessage"]["toolUses"] = tool_uses
            
            history.append(assistant_msg)
    
    history = fix_history_alternation(history)
    
    return user_content, history, current_tool_results


# ==================== Kiro Stream Converter ====================

class KiroStreamConverter:
    """Convert Kiro streaming response to Anthropic SSE format"""
    
    def __init__(self, thinking_start_tag: str = "<thinking>", thinking_end_tag: str = "</thinking>"):
        self.thinking_start_tag = thinking_start_tag
        self.thinking_end_tag = thinking_end_tag
        self.reset()
    
    def reset(self):
        """Reset converter state"""
        self.stream_state = {
            "buffer": "",
            "in_thinking": False,
            "thinking_extracted": False,
            "thinking_block_index": None,
            "text_block_index": None,
            "next_block_index": 0,
            "stopped_blocks": set()
        }
        self.tool_calls = []
        self.current_tool_call = None
        self.total_content = ""
        self.last_content_event = None
        # Cache token tracking
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
    
    def ensure_block_start(self, block_type: str) -> list:
        """Ensure a content block is started and return start events"""
        if block_type == "thinking":
            if self.stream_state["thinking_block_index"] is not None:
                return []
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            self.stream_state["thinking_block_index"] = idx
            return [{"type": "content_block_start", "index": idx, "content_block": {"type": "thinking", "thinking": ""}}]
        if block_type == "text":
            if self.stream_state["text_block_index"] is not None:
                return []
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            self.stream_state["text_block_index"] = idx
            return [{"type": "content_block_start", "index": idx, "content_block": {"type": "text", "text": ""}}]
        return []
    
    def stop_block(self, index: int | None) -> list:
        """Stop a content block and return stop events"""
        if index is None or index in self.stream_state["stopped_blocks"]:
            return []
        self.stream_state["stopped_blocks"].add(index)
        return [{"type": "content_block_stop", "index": index}]
    
    def create_text_delta_events(self, text: str) -> list:
        """Create text delta events"""
        events = []
        events.extend(self.ensure_block_start("text"))
        events.append({"type": "content_block_delta", "index": self.stream_state["text_block_index"], "delta": {"type": "text_delta", "text": text}})
        return events
    
    def create_thinking_delta_events(self, thinking_text: str) -> list:
        """Create thinking delta events"""
        events = []
        events.extend(self.ensure_block_start("thinking"))
        events.append({"type": "content_block_delta", "index": self.stream_state["thinking_block_index"], "delta": {"type": "thinking_delta", "thinking": thinking_text}})
        return events
    
    def process_content_event(self, content_piece: str, thinking_requested: bool) -> list:
        """Process a content event and return SSE events"""
        from utils.text import find_real_tag
        
        if content_piece == self.last_content_event:
            return []
        self.last_content_event = content_piece
        self.total_content += content_piece
        
        if not thinking_requested:
            return self.create_text_delta_events(content_piece)
        
        self.stream_state["buffer"] += content_piece
        pending = []
        
        while self.stream_state["buffer"]:
            if not self.stream_state["in_thinking"] and not self.stream_state["thinking_extracted"]:
                start_pos = find_real_tag(self.stream_state["buffer"], self.thinking_start_tag)
                if start_pos != -1:
                    before = self.stream_state["buffer"][:start_pos]
                    if before:
                        pending.extend(self.create_text_delta_events(before))
                    self.stream_state["buffer"] = self.stream_state["buffer"][start_pos + len(self.thinking_start_tag):]
                    self.stream_state["in_thinking"] = True
                    continue
                safe_len = max(0, len(self.stream_state["buffer"]) - len(self.thinking_start_tag))
                if safe_len > 0:
                    safe_text = self.stream_state["buffer"][:safe_len]
                    if safe_text:
                        pending.extend(self.create_text_delta_events(safe_text))
                    self.stream_state["buffer"] = self.stream_state["buffer"][safe_len:]
                break
            
            if self.stream_state["in_thinking"]:
                end_pos = find_real_tag(self.stream_state["buffer"], self.thinking_end_tag)
                if end_pos != -1:
                    thinking_part = self.stream_state["buffer"][:end_pos]
                    if thinking_part:
                        pending.extend(self.create_thinking_delta_events(thinking_part))
                    self.stream_state["buffer"] = self.stream_state["buffer"][end_pos + len(self.thinking_end_tag):]
                    self.stream_state["in_thinking"] = False
                    self.stream_state["thinking_extracted"] = True
                    pending.extend(self.create_thinking_delta_events(""))
                    pending.extend(self.stop_block(self.stream_state["thinking_block_index"]))
                    if self.stream_state["buffer"].startswith("\n\n"):
                        self.stream_state["buffer"] = self.stream_state["buffer"][2:]
                    continue
                safe_len = max(0, len(self.stream_state["buffer"]) - len(self.thinking_end_tag))
                if safe_len > 0:
                    safe_thinking = self.stream_state["buffer"][:safe_len]
                    if safe_thinking:
                        pending.extend(self.create_thinking_delta_events(safe_thinking))
                    self.stream_state["buffer"] = self.stream_state["buffer"][safe_len:]
                break
            
            if self.stream_state["thinking_extracted"]:
                rest = self.stream_state["buffer"]
                self.stream_state["buffer"] = ""
                if rest:
                    pending.extend(self.create_text_delta_events(rest))
                break
        
        return pending
    
    def process_tool_use_event(self, tool_data: dict) -> None:
        """Process a tool use event"""
        if tool_data.get("name"):
            self.total_content += tool_data["name"]
        if tool_data.get("input"):
            self.total_content += tool_data["input"]
        
        if tool_data.get("name") and tool_data.get("toolUseId"):
            if self.current_tool_call and self.current_tool_call["toolUseId"] == tool_data["toolUseId"]:
                self.current_tool_call["input"] += tool_data.get("input") or ""
            else:
                if self.current_tool_call:
                    try:
                        self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
                    except Exception:
                        pass
                    self.tool_calls.append(self.current_tool_call)
                self.current_tool_call = {
                    "toolUseId": tool_data["toolUseId"],
                    "name": tool_data["name"],
                    "input": tool_data.get("input") or ""
                }
            if tool_data.get("stop"):
                try:
                    self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
                except Exception:
                    pass
                self.tool_calls.append(self.current_tool_call)
                self.current_tool_call = None
    
    def process_tool_use_input_event(self, input_piece: str) -> None:
        """Process a tool use input event"""
        if input_piece:
            self.total_content += input_piece
        if self.current_tool_call:
            self.current_tool_call["input"] += input_piece or ""
    
    def process_tool_use_stop_event(self, stop: bool) -> None:
        """Process a tool use stop event"""
        if self.current_tool_call and stop:
            try:
                self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
            except Exception:
                pass
            self.tool_calls.append(self.current_tool_call)
            self.current_tool_call = None
    
    def finalize_thinking_buffer(self, thinking_requested: bool) -> list:
        """Finalize any remaining thinking buffer content"""
        if not thinking_requested or not self.stream_state["buffer"]:
            return []
        
        events = []
        if self.stream_state["in_thinking"]:
            events.extend(self.create_thinking_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
            events.extend(self.create_thinking_delta_events(""))
            events.extend(self.stop_block(self.stream_state["thinking_block_index"]))
        elif not self.stream_state["thinking_extracted"]:
            events.extend(self.create_text_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
        else:
            events.extend(self.create_text_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
        
        return events
    
    def finalize_current_tool_call(self) -> None:
        """Finalize any pending tool call"""
        if self.current_tool_call:
            try:
                self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
            except Exception:
                pass
            self.tool_calls.append(self.current_tool_call)
            self.current_tool_call = None
    
    def generate_tool_call_events(self) -> list:
        """Generate tool call events for all collected tool calls"""
        events = []
        
        for tc in self.tool_calls:
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            tool_id = tc.get("toolUseId") or f"tool_{uuid.uuid4().hex}"
            tool_name = tc.get("name") or ""
            tool_input = tc.get("input")
            partial_json = tool_input if isinstance(tool_input, str) else json.dumps(tool_input or {})
            
            tool_start = {
                "type": "content_block_start",
                "index": idx,
                "content_block": {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}}
            }
            tool_delta = {
                "type": "content_block_delta",
                "index": idx,
                "delta": {"type": "input_json_delta", "partial_json": partial_json}
            }
            tool_stop = {"type": "content_block_stop", "index": idx}
            
            events.extend([tool_start, tool_delta, tool_stop])
        
        return events
    
    def get_total_content(self) -> str:
        """Get total content including tool calls"""
        output_text = self.total_content
        if self.tool_calls:
            output_text += json.dumps(self.tool_calls, ensure_ascii=False)
        return output_text
    
    def get_tool_calls(self) -> list:
        """Get collected tool calls"""
        return self.tool_calls
    
    def get_text_block_index(self) -> int | None:
        """Get text block index"""
        return self.stream_state["text_block_index"]
    
    def parse_aws_event_stream_buffer(self, buffer: str) -> tuple[list, str]:
        """Parse AWS event stream buffer and extract events"""
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


class KiroConverter(BaseConverter):
    """Kiro Converter - handles Claude format conversions for Kiro provider"""
    
    def __init__(self):
        super().__init__("kiro")
    
    def convert_request(self, data: dict, target_format: str) -> dict:
        """Convert request to target format (Kiro uses Claude format)"""
        if target_format == "kiro" or target_format == "claude":
            return data
        return data
    
    def convert_response(self, data: dict, source_format: str) -> dict:
        """Convert response from source format"""
        if source_format == "kiro" or source_format == "claude":
            return data
        return data
    
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        """Convert streaming chunk from source format"""
        if source_format == "kiro" or source_format == "claude":
            return chunk
        return chunk
