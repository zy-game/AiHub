"""Token counting utilities - Main token counter"""
import json
from typing import Dict, Any, Union
from .token_estimator import estimate_tokens


def count_tokens(text: str, model: str = "") -> int:
    """Count tokens for text based on model type
    
    Args:
        text: Input text to count tokens
        model: Model name (e.g., "gpt-4", "claude-3", "gemini-pro")
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # For now, use estimation for all models
    # In the future, can add tiktoken for OpenAI models
    return estimate_tokens(text, model)


def _get_content_text(content: Union[str, list, dict]) -> str:
    """Extract text from various content formats
    
    Args:
        content: Content in string, list, or dict format
    
    Returns:
        Extracted text string
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    texts.append(_get_content_text(item.get("content", "")))
            elif isinstance(item, str):
                texts.append(item)
        return " ".join(texts)
    elif isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        return str(content)
    return str(content)


def count_message_tokens(message: Dict[str, Any], model: str = "", thinking_config: Dict[str, Any] = None) -> int:
    """Count tokens for a single message with support for various content types
    
    Args:
        message: Message dict with 'role' and 'content'
        model: Model name
        thinking_config: Optional thinking configuration for extended reasoning
    
    Returns:
        Token count including formatting overhead
    """
    tokens = 0
    
    # Extract text content
    content = message.get("content", "")
    if isinstance(content, str):
        tokens += count_tokens(content, model)
    elif isinstance(content, list):
        # Handle multi-part content (text, images, tools, documents, thinking, etc.)
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                
                if part_type == "text":
                    text = part.get("text", "")
                    tokens += count_tokens(text, model)
                
                elif part_type == "thinking":
                    # Kiro-specific: thinking content
                    thinking_text = part.get("thinking") or part.get("text") or ""
                    tokens += count_tokens(thinking_text, model)
                
                elif part_type == "tool_result":
                    # Tool result content
                    result_content = part.get("content", "")
                    tokens += count_tokens(_get_content_text(result_content), model)
                
                elif part_type == "tool_use":
                    # Tool use: name + input JSON
                    tool_name = part.get("name", "")
                    tool_input = part.get("input", {})
                    tokens += count_tokens(tool_name, model)
                    tokens += count_tokens(json.dumps(tool_input, ensure_ascii=False), model)
                
                elif part_type == "image":
                    # Kiro-specific: image tokens (fixed cost)
                    tokens += 1600
                
                elif part_type == "image_url":
                    # OpenAI-style image
                    tokens += 85  # Base tokens for image
                
                elif part_type == "document":
                    # Kiro-specific: document content (base64 encoded)
                    source = part.get("source") or {}
                    data = source.get("data", "")
                    if data:
                        # Estimate tokens from base64 data
                        estimated_chars = int(len(data) * 0.75)
                        tokens += max(1, (estimated_chars + 3) // 4)
            
            elif isinstance(part, str):
                tokens += count_tokens(part, model)
    
    # Add formatting overhead (role, delimiters, etc.)
    tokens += 3
    
    # Add name overhead if present
    if message.get("name"):
        tokens += 3
    
    return tokens


def count_messages_tokens(messages: list, model: str = "", thinking_config: Dict[str, Any] = None) -> int:
    """Count tokens for a list of messages
    
    Args:
        messages: List of message dicts
        model: Model name
        thinking_config: Optional thinking configuration
    
    Returns:
        Total token count
    """
    total = 0
    
    for msg in messages:
        total += count_message_tokens(msg, model, thinking_config)
    
    # Add base overhead for message list
    total += 3
    
    return total


def count_request_tokens(
    messages: list,
    system: str = "",
    tools: list = None,
    model: str = "",
    thinking_config: Dict[str, Any] = None
) -> int:
    """Count tokens for a complete request
    
    Args:
        messages: List of messages
        system: System message
        tools: List of tool definitions
        model: Model name
        thinking_config: Optional thinking configuration (Kiro-specific)
            Example: {"type": "enabled", "budget_tokens": 20000}
    
    Returns:
        Total input token count
    """
    total = 0
    
    # Count system message
    if system:
        total += count_tokens(_get_content_text(system), model)
        total += 3  # Formatting overhead
    
    # Count thinking mode prefix (Kiro-specific)
    if thinking_config and thinking_config.get("type") == "enabled":
        budget = thinking_config.get("budget_tokens", 20000)
        # Normalize budget to valid range
        if budget > 24576:
            budget = 24576
        elif budget < 1000:
            budget = 20000
        
        # Thinking mode tags
        prefix_text = f"<thinking_mode>enabled</thinking_mode><max_thinking_length>{budget}</max_thinking_length>"
        total += count_tokens(prefix_text, model)
    
    # Count messages
    total += count_messages_tokens(messages, model, thinking_config)
    
    # Count tools
    if tools:
        for tool in tools:
            # Count tool name, description, and schema
            tool_name = tool.get("name", "")
            tool_desc = tool.get("description", "")
            tool_schema = tool.get("input_schema", {})
            
            total += count_tokens(tool_name, model)
            total += count_tokens(tool_desc, model)
            total += count_tokens(json.dumps(tool_schema, ensure_ascii=False), model)
            total += 8  # Per-tool overhead
    
    return total
