"""OpenAI to Claude SSE Converter"""
import json
import uuid
import time

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
        
        # Parse OpenAI SSE format
        if not openai_chunk.startswith("data: "):
            return ""
        
        data_str = openai_chunk[6:].strip()
        
        if data_str == "[DONE]":
            # Send message_stop event
            return f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'
        
        try:
            data = json.loads(data_str)
        except:
            return ""
        
        result = ""
        
        # Send message_start if not sent yet
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
        
        # Handle content delta
        if "content" in delta and delta["content"]:
            # Send content_block_start if not sent yet
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
            
            # Send content_block_delta
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
        
        # Handle finish
        if finish_reason:
            # Send content_block_stop
            if self.has_sent_block_start:
                block_stop = {
                    "type": "content_block_stop",
                    "index": 0
                }
                result += f'event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n'
            
            # Extract usage if available
            usage = data.get("usage", {})
            if usage:
                self.input_tokens = usage.get("prompt_tokens", 0)
                self.output_tokens = usage.get("completion_tokens", self.output_tokens)
            
            # Send message_delta
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
