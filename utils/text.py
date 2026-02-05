"""Text processing utilities"""


def get_content_text(message) -> str:
    """Extract text content from a message object
    
    Handles various message formats:
    - Plain string
    - List of content parts
    - Dict with content field
    """
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        texts = []
        for part in message:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    texts.append(str(part["text"]))
                elif part.get("text"):
                    texts.append(str(part["text"]))
        return "".join(texts)
    elif isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            texts = []
            for part in content:
                if isinstance(part, str):
                    texts.append(part)
                elif isinstance(part, dict):
                    if part.get("type") == "text" and part.get("text"):
                        texts.append(str(part["text"]))
                    elif part.get("text"):
                        texts.append(str(part["text"]))
            return "".join(texts)
        else:
            # content is not string or list, convert to string
            return str(content) if content else ""
    # Fallback: convert to string
    return str(message)


def is_quote_char_at(text: str, index: int) -> bool:
    """Check if character at index is a quote character"""
    if index < 0 or index >= len(text):
        return False
    return text[index] in {'"', "'", "`"}


def find_real_tag(text: str, tag: str, start_index: int = 0) -> int:
    """Find tag position that is not inside quotes
    
    Returns -1 if not found
    """
    search_start = max(0, start_index)
    while True:
        pos = text.find(tag, search_start)
        if pos == -1:
            return -1
        has_quote_before = is_quote_char_at(text, pos - 1)
        has_quote_after = is_quote_char_at(text, pos + len(tag))
        if not has_quote_before and not has_quote_after:
            return pos
        search_start = pos + 1
