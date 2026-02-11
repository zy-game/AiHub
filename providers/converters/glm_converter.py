"""GLM Provider Converter - Handles GLM to OpenAI format conversion"""
import json
import time

class GLMConverter:
    """Convert GLM requests and responses to OpenAI format"""
    
    @staticmethod
    def convert_request(openai_data: dict) -> dict:
        """Convert OpenAI request to GLM format (mostly compatible)"""
        result = openai_data.copy()
        
        # GLM format is mostly OpenAI-compatible
        # Ensure tools have correct format
        if "tools" in result and result["tools"]:
            formatted_tools = []
            for tool in result["tools"]:
                if not isinstance(tool, dict):
                    continue
                
                if tool.get("type") == "function" and "function" in tool:
                    func = tool["function"]
                    if "name" in func and "parameters" in func:
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
    
    @staticmethod
    def convert_stream_chunk(glm_chunk: bytes) -> str:
        """Convert GLM stream chunk to OpenAI SSE format"""
        try:
            chunk_str = glm_chunk.decode("utf-8", errors="ignore").strip()
        except:
            return ""
        
        if not chunk_str:
            return ""
        
        # Handle "data: " prefix
        if chunk_str.startswith("data: "):
            data_str = chunk_str[6:].strip()
        else:
            data_str = chunk_str
        
        if data_str == "[DONE]":
            return "data: [DONE]\n\n"
        
        try:
            data = json.loads(data_str)
        except:
            return ""
        
        # GLM format is mostly OpenAI-compatible
        # But may have reasoning_content that needs to be merged
        choices = data.get("choices", [])
        if not choices:
            return ""
        
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
        
        return ""
