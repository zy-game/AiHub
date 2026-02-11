import json
import uuid
import time
from .base import BaseConverter


class OpenAIToClaudeConverter:
    """Convert OpenAI SSE format to Claude SSE format"""
    
    def __init__(self):
        self.message_id = f"msg_{uuid.uuid4().hex[:8]}"
        self.has_sent_start = False
        self.has_sent_block_start = False
        self.input_tokens = 0
        self.output_tokens = 0
    
    def convert_chunk(self, openai_chunk: str) -> str:
        """Convert OpenAI SSE chunk to Claude SSE format"""
        if not openai_chunk.strip():
            return ""
        
        if not openai_chunk.startswith("data: "):
            return ""
        
        data_str = openai_chunk[6:].strip()
        
        if data_str == "[DONE]":
            return f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'
        
        try:
            data = json.loads(data_str)
        except:
            return ""
        
        result = ""
        
        if not self.has_sent_start:
            self.has_sent_start = True
            model = data.get("model", "")
            message_start = {
                "type": "message_start",
                "message": {
                    "id": self.message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0
                    }
                }
            }
            result += f'event: message_start\ndata: {json.dumps(message_start)}\n\n'
        
        choices = data.get("choices", [])
        if not choices:
            return result
        
        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")
        
        if "content" in delta and delta["content"]:
            if not self.has_sent_block_start:
                self.has_sent_block_start = True
                block_start = {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "text",
                        "text": ""
                    }
                }
                result += f'event: content_block_start\ndata: {json.dumps(block_start)}\n\n'
            
            content_delta = {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "text_delta",
                    "text": delta["content"]
                }
            }
            result += f'event: content_block_delta\ndata: {json.dumps(content_delta)}\n\n'
            self.output_tokens += 1
        
        if finish_reason:
            if self.has_sent_block_start:
                block_stop = {
                    "type": "content_block_stop",
                    "index": 0
                }
                result += f'event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n'
            
            usage = data.get("usage", {})
            if usage:
                self.input_tokens = usage.get("prompt_tokens", 0)
                self.output_tokens = usage.get("completion_tokens", self.output_tokens)
            
            stop_reason_map = {
                "stop": "end_turn",
                "length": "max_tokens",
                "tool_calls": "tool_use"
            }
            claude_stop_reason = stop_reason_map.get(finish_reason, "end_turn")
            
            message_delta = {
                "type": "message_delta",
                "delta": {
                    "stop_reason": claude_stop_reason
                },
                "usage": {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            }
            result += f'event: message_delta\ndata: {json.dumps(message_delta)}\n\n'
        
        return result


class OpenAIConverter(BaseConverter):
    def __init__(self):
        super().__init__("openai")
    
    def convert_request(self, data: dict, target_format: str) -> dict:
        if target_format == "openai":
            return data
        elif target_format == "glm":
            return self._to_glm_request(data)
        elif target_format == "claude":
            return self._to_claude_request(data)
        elif target_format == "gemini":
            return self._to_gemini_request(data)
        return data
    
    def convert_response(self, data: dict, source_format: str) -> dict:
        if source_format == "openai":
            return data
        elif source_format == "claude":
            return self._from_claude_response(data)
        elif source_format == "gemini":
            return self._from_gemini_response(data)
        return data
    
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        if source_format == "openai":
            return chunk
        elif source_format == "glm":
            return self._from_glm_stream(chunk)
        elif source_format == "claude":
            return self._from_claude_stream(chunk)
        elif source_format == "gemini":
            return self._from_gemini_stream(chunk)
        return chunk
    
    def _to_claude_request(self, data: dict) -> dict:
        messages = data.get("messages", [])
        claude_messages = []
        system_content = ""
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                system_content = content if isinstance(content, str) else json.dumps(content)
            elif role == "assistant":
                claude_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                claude_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content
                    }]
                })
            else:
                claude_messages.append({"role": "user", "content": content})
        
        result = {
            "model": data.get("model", ""),
            "messages": claude_messages,
            "max_tokens": data.get("max_tokens", 4096),
        }
        
        if system_content:
            result["system"] = system_content
        if data.get("temperature") is not None:
            result["temperature"] = data["temperature"]
        if data.get("top_p") is not None:
            result["top_p"] = data["top_p"]
        if data.get("stream"):
            result["stream"] = True
        if data.get("tools"):
            result["tools"] = self._convert_tools_to_claude(data["tools"])
        
        return result
    
    def _convert_tools_to_claude(self, tools: list) -> list:
        claude_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                claude_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        return claude_tools
    
    def _to_glm_request(self, data: dict) -> dict:
        """Convert OpenAI format to GLM format"""
        result = data.copy()
        
        # Ensure tools have the correct format for GLM
        # GLM requires: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        if "tools" in result and result["tools"]:
            formatted_tools = []
            for tool in result["tools"]:
                if not isinstance(tool, dict):
                    continue
                
                # OpenAI format: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
                # This is already the correct format for GLM
                if tool.get("type") == "function" and "function" in tool:
                    func = tool["function"]
                    # Ensure function has required fields
                    if "name" in func and "description" in func and "parameters" in func:
                        formatted_tools.append(tool)
                    elif "name" in func and "parameters" in func:
                        # Add default description if missing
                        formatted_tools.append({
                            "type": "function",
                            "function": {
                                "name": func["name"],
                                "description": func.get("description", func["name"]),
                                "parameters": func["parameters"]
                            }
                        })
            
            result["tools"] = formatted_tools if formatted_tools else None
            if not result["tools"]:
                del result["tools"]
        
        return result
    
    def _to_gemini_request(self, data: dict) -> dict:
        messages = data.get("messages", [])
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})
        
        result = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": data.get("max_tokens", 4096),
            }
        }
        
        if system_instruction:
            result["systemInstruction"] = system_instruction
        if data.get("temperature") is not None:
            result["generationConfig"]["temperature"] = data["temperature"]
        if data.get("top_p") is not None:
            result["generationConfig"]["topP"] = data["top_p"]
        
        return result
    
    def _from_claude_response(self, data: dict) -> dict:
        content = ""
        tool_calls = []
        
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}))
                    }
                })
        
        message = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        return {
            "id": f"chatcmpl-{data.get('id', '')}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", ""),
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": self._map_stop_reason(data.get("stop_reason"))
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            }
        }
    
    def _from_gemini_response(self, data: dict) -> dict:
        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                content += part.get("text", "")
        
        usage = data.get("usageMetadata", {})
        
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("modelVersion", ""),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0)
            }
        }
    
    def _from_claude_stream(self, chunk: str) -> str:
        if not chunk.startswith("data: "):
            return ""
        
        data_str = chunk[6:].strip()
        if data_str == "[DONE]":
            return "data: [DONE]\n\n"
        
        try:
            data = json.loads(data_str)
            event_type = data.get("type", "")
            
            if event_type == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    return f'data: {json.dumps({"id": "chatcmpl-stream", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": text}}]})}\n\n'
            elif event_type == "message_stop":
                return "data: [DONE]\n\n"
        except:
            pass
        return ""
    
    def _from_glm_stream(self, chunk: str) -> str:
        """Convert GLM stream format to OpenAI stream format"""
        # Handle both with and without "data: " prefix
        if chunk.startswith("data: "):
            data_str = chunk[6:].strip()
        else:
            data_str = chunk.strip()
        
        if not data_str:
            return ""
        
        if data_str == "[DONE]":
            return "data: [DONE]\n\n"
        
        try:
            data = json.loads(data_str)
            
            # GLM format is already OpenAI-compatible, but may have reasoning_content
            # We need to merge reasoning_content and content
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                
                # Combine reasoning_content and content
                combined_content = ""
                if "reasoning_content" in delta and delta["reasoning_content"]:
                    combined_content += delta["reasoning_content"]
                if "content" in delta and delta["content"]:
                    combined_content += delta["content"]
                
                # Build OpenAI format response
                if combined_content or "tool_calls" in delta or choices[0].get("finish_reason"):
                    openai_chunk = {
                        "id": data.get("id", "chatcmpl-stream"),
                        "object": "chat.completion.chunk",
                        "created": data.get("created", int(time.time())),
                        "model": data.get("model", ""),
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": choices[0].get("finish_reason")
                        }]
                    }
                    
                    # Add content if present
                    if combined_content:
                        openai_chunk["choices"][0]["delta"]["content"] = combined_content
                    
                    # Add role if present (only in first chunk)
                    if "role" in delta and not combined_content:
                        openai_chunk["choices"][0]["delta"]["role"] = delta["role"]
                    
                    # Add tool_calls if present
                    if "tool_calls" in delta:
                        openai_chunk["choices"][0]["delta"]["tool_calls"] = delta["tool_calls"]
                    
                    # Add usage if present (last chunk)
                    if "usage" in data:
                        openai_chunk["usage"] = data["usage"]
                    
                    return f'data: {json.dumps(openai_chunk)}\n\n'
        except Exception as e:
            # Log parsing errors for debugging
            import sys
            print(f"GLM stream conversion error: {e}, chunk: {chunk[:100]}", file=sys.stderr)
            return ""
        
        return ""
    
    def _from_gemini_stream(self, chunk: str) -> str:
        try:
            data = json.loads(chunk)
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    text = part.get("text", "")
                    if text:
                        return f'data: {json.dumps({"id": "chatcmpl-stream", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": text}}]})}\n\n'
        except:
            pass
        return ""
    
    def _map_stop_reason(self, reason: str) -> str:
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls"
        }
        return mapping.get(reason, "stop")
