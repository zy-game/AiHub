"""Kiro Provider Converter - Handles Claude SSE to OpenAI SSE conversion"""
import json
import uuid
import time

class KiroConverter:
    """Convert Kiro (Claude format) requests and responses to OpenAI format"""
    
    @staticmethod
    def convert_request(openai_data: dict) -> dict:
        """Convert OpenAI request to Claude format for Kiro"""
        messages = []
        system_content = ""
        
        for msg in openai_data.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                system_content = content if isinstance(content, str) else json.dumps(content)
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content
                    }]
                })
            else:
                messages.append({"role": "user", "content": content})
        
        result = {
            "model": openai_data.get("model", ""),
            "messages": messages,
            "max_tokens": openai_data.get("max_tokens", 4096),
        }
        
        if system_content:
            result["system"] = system_content
        if openai_data.get("temperature") is not None:
            result["temperature"] = openai_data["temperature"]
        if openai_data.get("top_p") is not None:
            result["top_p"] = openai_data["top_p"]
        if openai_data.get("stream"):
            result["stream"] = True
        if openai_data.get("tools"):
            result["tools"] = KiroConverter._convert_tools_to_claude(openai_data["tools"])
        
        return result
    
    @staticmethod
    def _convert_tools_to_claude(tools: list) -> list:
        """Convert OpenAI tools to Claude format"""
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
    
    @staticmethod
    def convert_stream_chunk(claude_chunk: str) -> str:
        """Convert Claude SSE chunk to OpenAI SSE format"""
        if not claude_chunk.strip():
            return ""
        
        # Parse Claude SSE format: "event: xxx\ndata: {...}\n\n"
        lines = claude_chunk.strip().split("\n")
        event_type = None
        data_str = None
        
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:].strip()
        
        if not data_str:
            return ""
        
        try:
            data = json.loads(data_str)
        except:
            return ""
        
        # Convert based on event type
        if event_type == "message_start":
            # First chunk with role
            return f'data: {json.dumps({"id": "chatcmpl-" + str(uuid.uuid4().hex[:8]), "object": "chat.completion.chunk", "created": int(time.time()), "model": data.get("message", {}).get("model", ""), "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})}\n\n'
        
        elif event_type == "content_block_start":
            # Content block started, no output needed
            return ""
        
        elif event_type == "content_block_delta":
            # Text delta
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                return f'data: {json.dumps({"id": "chatcmpl-stream", "object": "chat.completion.chunk", "created": int(time.time()), "model": "", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]})}\n\n'
        
        elif event_type == "content_block_stop":
            # Content block ended, no output needed
            return ""
        
        elif event_type == "message_delta":
            # Message delta with stop reason
            delta = data.get("delta", {})
            stop_reason = delta.get("stop_reason", "stop")
            finish_reason = KiroConverter._map_stop_reason(stop_reason)
            chunk_data = {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": finish_reason
                }]
            }
            return f'data: {json.dumps(chunk_data)}\n\n'
        
        elif event_type == "message_stop":
            # End of stream
            return "data: [DONE]\n\n"
        
        return ""
    
    @staticmethod
    def _map_stop_reason(claude_reason: str) -> str:
        """Map Claude stop reason to OpenAI finish_reason"""
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls"
        }
        return mapping.get(claude_reason, "stop")
