import json
import uuid
import time
from .base import BaseConverter

class ClaudeConverter(BaseConverter):
    def __init__(self):
        super().__init__("claude")
    
    def convert_request(self, data: dict, target_format: str) -> dict:
        if target_format == "claude":
            return data
        elif target_format == "openai":
            return self._to_openai_request(data)
        elif target_format == "gemini":
            return self._to_gemini_request(data)
        return data
    
    def convert_response(self, data: dict, source_format: str) -> dict:
        if source_format == "claude":
            return data
        elif source_format == "openai":
            return self._from_openai_response(data)
        elif source_format == "gemini":
            return self._from_gemini_response(data)
        return data
    
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        if source_format == "claude":
            return chunk
        elif source_format == "openai":
            return self._from_openai_stream(chunk)
        elif source_format == "gemini":
            return self._from_gemini_stream(chunk)
        return chunk
    
    def _to_openai_request(self, data: dict) -> dict:
        messages = []
        
        if data.get("system"):
            system = data["system"]
            if isinstance(system, str):
                messages.append({"role": "system", "content": system})
            elif isinstance(system, list):
                text = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
                messages.append({"role": "system", "content": text})
        
        for msg in data.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                # Handle tool_result
                for item in content:
                    if item.get("type") == "tool_result":
                        messages.append({
                            "role": "tool",
                            "tool_call_id": item.get("tool_use_id", ""),
                            "content": str(item.get("content", ""))
                        })
                    elif item.get("type") == "text":
                        messages.append({"role": role, "content": item.get("text", "")})
            else:
                messages.append({"role": role, "content": content})
        
        result = {
            "model": data.get("model", ""),
            "messages": messages,
            "max_tokens": data.get("max_tokens", 4096),
        }
        
        if data.get("temperature") is not None:
            result["temperature"] = data["temperature"]
        if data.get("top_p") is not None:
            result["top_p"] = data["top_p"]
        if data.get("stream"):
            result["stream"] = True
        if data.get("tools"):
            result["tools"] = self._convert_tools_to_openai(data["tools"])
        
        return result
    
    def _convert_tools_to_openai(self, tools: list) -> list:
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            })
        return openai_tools
    
    def _to_gemini_request(self, data: dict) -> dict:
        contents = []
        system_instruction = None
        
        if data.get("system"):
            system = data["system"]
            if isinstance(system, str):
                system_instruction = {"parts": [{"text": system}]}
            elif isinstance(system, list):
                text = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
                system_instruction = {"parts": [{"text": text}]}
        
        for msg in data.get("messages", []):
            role = "model" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")
            
            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
                if text:
                    contents.append({"role": role, "parts": [{"text": text}]})
        
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
    
    def _from_openai_response(self, data: dict) -> dict:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content_blocks = []
        
        if message.get("content"):
            content_blocks.append({"type": "text", "text": message["content"]})
        
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except:
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": args
                })
        
        usage = data.get("usage", {})
        
        return {
            "id": data.get("id", f"msg_{uuid.uuid4().hex[:8]}"),
            "type": "message",
            "role": "assistant",
            "model": data.get("model", ""),
            "content": content_blocks,
            "stop_reason": self._map_finish_reason(choice.get("finish_reason")),
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0)
            }
        }
    
    def _from_gemini_response(self, data: dict) -> dict:
        content_blocks = []
        candidates = data.get("candidates", [])
        
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if part.get("text"):
                    content_blocks.append({"type": "text", "text": part["text"]})
        
        usage = data.get("usageMetadata", {})
        
        return {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "type": "message",
            "role": "assistant",
            "model": data.get("modelVersion", ""),
            "content": content_blocks,
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": usage.get("promptTokenCount", 0),
                "output_tokens": usage.get("candidatesTokenCount", 0)
            }
        }
    
    def _from_openai_stream(self, chunk: str) -> str:
        if not chunk.startswith("data: "):
            return ""
        
        data_str = chunk[6:].strip()
        if data_str == "[DONE]":
            return f'data: {json.dumps({"type": "message_stop"})}\n\n'
        
        try:
            data = json.loads(data_str)
            choice = data.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            
            if delta.get("content"):
                return f'data: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": delta["content"]}})}\n\n'
        except:
            pass
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
                        return f'data: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}})}\n\n'
        except:
            pass
        return ""
    
    def _map_finish_reason(self, reason: str) -> str:
        mapping = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use"
        }
        return mapping.get(reason, "end_turn")
