import json
import uuid
import time
from .base import BaseConverter

class GeminiConverter(BaseConverter):
    def __init__(self):
        super().__init__("gemini")
    
    def convert_request(self, data: dict, target_format: str) -> dict:
        if target_format == "gemini":
            return data
        elif target_format == "openai":
            return self._to_openai_request(data)
        elif target_format == "claude":
            return self._to_claude_request(data)
        return data
    
    def convert_response(self, data: dict, source_format: str) -> dict:
        if source_format == "gemini":
            return data
        elif source_format == "openai":
            return self._from_openai_response(data)
        elif source_format == "claude":
            return self._from_claude_response(data)
        return data
    
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        if source_format == "gemini":
            return chunk
        elif source_format == "openai":
            return self._from_openai_stream(chunk)
        elif source_format == "claude":
            return self._from_claude_stream(chunk)
        return chunk
    
    def _to_openai_request(self, data: dict) -> dict:
        messages = []
        
        if data.get("systemInstruction"):
            parts = data["systemInstruction"].get("parts", [])
            text = " ".join(p.get("text", "") for p in parts)
            if text:
                messages.append({"role": "system", "content": text})
        
        for content in data.get("contents", []):
            role = "assistant" if content.get("role") == "model" else "user"
            parts = content.get("parts", [])
            text = " ".join(p.get("text", "") for p in parts)
            if text:
                messages.append({"role": role, "content": text})
        
        gen_config = data.get("generationConfig", {})
        
        result = {
            "model": data.get("model", ""),
            "messages": messages,
            "max_tokens": gen_config.get("maxOutputTokens", 4096),
        }
        
        if gen_config.get("temperature") is not None:
            result["temperature"] = gen_config["temperature"]
        if gen_config.get("topP") is not None:
            result["top_p"] = gen_config["topP"]
        
        return result
    
    def _to_claude_request(self, data: dict) -> dict:
        messages = []
        system = None
        
        if data.get("systemInstruction"):
            parts = data["systemInstruction"].get("parts", [])
            system = " ".join(p.get("text", "") for p in parts)
        
        for content in data.get("contents", []):
            role = "assistant" if content.get("role") == "model" else "user"
            parts = content.get("parts", [])
            text = " ".join(p.get("text", "") for p in parts)
            if text:
                messages.append({"role": role, "content": text})
        
        gen_config = data.get("generationConfig", {})
        
        result = {
            "model": data.get("model", ""),
            "messages": messages,
            "max_tokens": gen_config.get("maxOutputTokens", 4096),
        }
        
        if system:
            result["system"] = system
        if gen_config.get("temperature") is not None:
            result["temperature"] = gen_config["temperature"]
        if gen_config.get("topP") is not None:
            result["top_p"] = gen_config["topP"]
        
        return result
    
    def _from_openai_response(self, data: dict) -> dict:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        
        usage = data.get("usage", {})
        
        return {
            "candidates": [{
                "content": {
                    "parts": [{"text": content}],
                    "role": "model"
                },
                "finishReason": "STOP"
            }],
            "usageMetadata": {
                "promptTokenCount": usage.get("prompt_tokens", 0),
                "candidatesTokenCount": usage.get("completion_tokens", 0),
                "totalTokenCount": usage.get("total_tokens", 0)
            },
            "modelVersion": data.get("model", "")
        }
    
    def _from_claude_response(self, data: dict) -> dict:
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        
        usage = data.get("usage", {})
        
        return {
            "candidates": [{
                "content": {
                    "parts": [{"text": text}],
                    "role": "model"
                },
                "finishReason": "STOP"
            }],
            "usageMetadata": {
                "promptTokenCount": usage.get("input_tokens", 0),
                "candidatesTokenCount": usage.get("output_tokens", 0),
                "totalTokenCount": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            },
            "modelVersion": data.get("model", "")
        }
    
    def _from_openai_stream(self, chunk: str) -> str:
        if not chunk.startswith("data: "):
            return ""
        
        data_str = chunk[6:].strip()
        if data_str == "[DONE]":
            return ""
        
        try:
            data = json.loads(data_str)
            choice = data.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            
            if delta.get("content"):
                return json.dumps({
                    "candidates": [{
                        "content": {
                            "parts": [{"text": delta["content"]}],
                            "role": "model"
                        }
                    }]
                }) + "\n"
        except:
            pass
        return ""
    
    def _from_claude_stream(self, chunk: str) -> str:
        if not chunk.startswith("data: "):
            return ""
        
        data_str = chunk[6:].strip()
        
        try:
            data = json.loads(data_str)
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    return json.dumps({
                        "candidates": [{
                            "content": {
                                "parts": [{"text": delta.get("text", "")}],
                                "role": "model"
                            }
                        }]
                    }) + "\n"
        except:
            pass
        return ""
