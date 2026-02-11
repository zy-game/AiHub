import json
import uuid
import time
from .base import BaseConverter

class GLMConverter(BaseConverter):
    def __init__(self):
        super().__init__("glm")
    
    def _ensure_tools_format(self, tools: list) -> list:
        """Ensure tools have the correct format for GLM API"""
        formatted_tools = []
        for tool in tools:
            if isinstance(tool, dict):
                formatted_tool = tool.copy()
                if "type" not in formatted_tool:
                    formatted_tool["type"] = "function"
                if formatted_tool.get("type") == "function" and "function" in formatted_tool:
                    func = formatted_tool["function"]
                    if isinstance(func, dict) and "name" in func:
                        formatted_tools.append(formatted_tool)
                elif "name" in formatted_tool:
                    formatted_tools.append({
                        "type": "function",
                        "function": formatted_tool
                    })
                else:
                    formatted_tools.append(formatted_tool)
        return formatted_tools
    
    def convert_request(self, data: dict, target_format: str) -> dict:
        if target_format == "glm":
            result = data.copy()
            if "tools" in result:
                result["tools"] = self._ensure_tools_format(result["tools"])
            return result
        elif target_format == "openai":
            return data
        elif target_format == "claude":
            return self._to_claude_request(data)
        elif target_format == "gemini":
            return self._to_gemini_request(data)
        return data
    
    def convert_response(self, data: dict, source_format: str) -> dict:
        if source_format in ["glm", "openai"]:
            return data
        elif source_format == "claude":
            return self._from_claude_response(data)
        elif source_format == "gemini":
            return self._from_gemini_response(data)
        return data
    
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        if source_format in ["glm", "openai"]:
            return chunk
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
        
        result = {"contents": contents}
        
        if system_instruction:
            result["systemInstruction"] = system_instruction
        
        generation_config = {}
        if data.get("temperature") is not None:
            generation_config["temperature"] = data["temperature"]
        if data.get("top_p") is not None:
            generation_config["topP"] = data["top_p"]
        if data.get("max_tokens") is not None:
            generation_config["maxOutputTokens"] = data["max_tokens"]
        
        if generation_config:
            result["generationConfig"] = generation_config
        
        return result
    
    def _from_claude_response(self, data: dict) -> dict:
        return {
            "id": data.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", ""),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": data.get("content", [{}])[0].get("text", "")
                },
                "finish_reason": data.get("stop_reason", "stop")
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            }
        }
    
    def _from_gemini_response(self, data: dict) -> dict:
        candidates = data.get("candidates", [{}])
        first_candidate = candidates[0] if candidates else {}
        content = first_candidate.get("content", {})
        parts = content.get("parts", [{}])
        text = parts[0].get("text", "") if parts else ""
        
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("modelVersion", ""),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text
                },
                "finish_reason": first_candidate.get("finishReason", "STOP").lower()
            }],
            "usage": {
                "prompt_tokens": data.get("usageMetadata", {}).get("promptTokenCount", 0),
                "completion_tokens": data.get("usageMetadata", {}).get("candidatesTokenCount", 0),
                "total_tokens": data.get("usageMetadata", {}).get("totalTokenCount", 0)
            }
        }
    
    def _from_claude_stream(self, chunk: str) -> str:
        if not chunk.strip():
            return chunk
        
        try:
            data = json.loads(chunk)
            event_type = data.get("type")
            
            if event_type == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    openai_chunk = {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "",
                        "choices": [{
                            "index": data.get("index", 0),
                            "delta": {"content": delta.get("text", "")},
                            "finish_reason": None
                        }]
                    }
                    return f"data: {json.dumps(openai_chunk)}\n\n"
            elif event_type == "message_stop":
                openai_chunk = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                return f"data: {json.dumps(openai_chunk)}\n\ndata: [DONE]\n\n"
        except json.JSONDecodeError:
            pass
        
        return ""
    
    def _from_gemini_stream(self, chunk: str) -> str:
        if not chunk.strip():
            return chunk
        
        try:
            data = json.loads(chunk)
            candidates = data.get("candidates", [{}])
            first_candidate = candidates[0] if candidates else {}
            content = first_candidate.get("content", {})
            parts = content.get("parts", [{}])
            text = parts[0].get("text", "") if parts else ""
            finish_reason = first_candidate.get("finishReason")
            
            openai_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": data.get("modelVersion", ""),
                "choices": [{
                    "index": 0,
                    "delta": {"content": text} if text else {},
                    "finish_reason": finish_reason.lower() if finish_reason else None
                }]
            }
            
            result = f"data: {json.dumps(openai_chunk)}\n\n"
            if finish_reason:
                result += "data: [DONE]\n\n"
            
            return result
        except json.JSONDecodeError:
            pass
        
        return ""
