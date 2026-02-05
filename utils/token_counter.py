"""Token counting utilities - Main token counter"""
from typing import Dict, Any
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


def count_message_tokens(message: Dict[str, Any], model: str = "") -> int:
    """Count tokens for a single message
    
    Args:
        message: Message dict with 'role' and 'content'
        model: Model name
    
    Returns:
        Token count including formatting overhead
    """
    tokens = 0
    
    # Extract text content
    content = message.get("content", "")
    if isinstance(content, str):
        tokens += count_tokens(content, model)
    elif isinstance(content, list):
        # Handle multi-part content (text + images)
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text = part.get("text", "")
                    tokens += count_tokens(text, model)
                elif part.get("type") == "image_url":
                    # Image tokens - simplified, should be calculated separately
                    tokens += 85  # Base tokens for image
    
    # Add formatting overhead (role, delimiters, etc.)
    tokens += 3
    
    # Add name overhead if present
    if message.get("name"):
        tokens += 3
    
    return tokens


def count_messages_tokens(messages: list, model: str = "") -> int:
    """Count tokens for a list of messages
    
    Args:
        messages: List of message dicts
        model: Model name
    
    Returns:
        Total token count
    """
    total = 0
    
    for msg in messages:
        total += count_message_tokens(msg, model)
    
    # Add base overhead for message list
    total += 3
    
    return total


def count_request_tokens(
    messages: list,
    system: str = "",
    tools: list = None,
    model: str = ""
) -> int:
    """Count tokens for a complete request
    
    Args:
        messages: List of messages
        system: System message
        tools: List of tool definitions
        model: Model name
    
    Returns:
        Total input token count
    """
    total = 0
    
    # Count messages
    total += count_messages_tokens(messages, model)
    
    # Count system message
    if system:
        total += count_tokens(system, model)
        total += 3  # Formatting overhead
    
    # Count tools
    if tools:
        for tool in tools:
            # Simplified tool token counting
            tool_str = str(tool)
            total += count_tokens(tool_str, model)
            total += 8  # Per-tool overhead
    
    return total
