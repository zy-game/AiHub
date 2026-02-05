"""Token estimation utilities - Provider-specific token estimation"""
import math
from enum import Enum
from typing import Dict


class Provider(Enum):
    """Model provider types"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    UNKNOWN = "unknown"


# Provider-specific multipliers for different character types
MULTIPLIERS: Dict[Provider, Dict[str, float]] = {
    Provider.GEMINI: {
        'word': 1.15,
        'number': 2.8,
        'cjk': 0.68,
        'symbol': 0.38,
        'math_symbol': 1.05,
        'url_delim': 1.2,
        'at_sign': 2.5,
        'emoji': 1.08,
        'newline': 1.15,
        'space': 0.2,
        'base_pad': 0
    },
    Provider.CLAUDE: {
        'word': 1.13,
        'number': 1.63,
        'cjk': 1.21,
        'symbol': 0.4,
        'math_symbol': 4.52,
        'url_delim': 1.26,
        'at_sign': 2.82,
        'emoji': 2.6,
        'newline': 0.89,
        'space': 0.39,
        'base_pad': 0
    },
    Provider.OPENAI: {
        'word': 1.02,
        'number': 1.55,
        'cjk': 0.85,
        'symbol': 0.4,
        'math_symbol': 2.68,
        'url_delim': 1.0,
        'at_sign': 2.0,
        'emoji': 2.12,
        'newline': 0.5,
        'space': 0.42,
        'base_pad': 0
    }
}


def detect_provider(model: str) -> Provider:
    """Detect provider from model name
    
    Args:
        model: Model name string
    
    Returns:
        Provider enum
    """
    if not model:
        return Provider.OPENAI
    
    model_lower = model.lower()
    
    if "gemini" in model_lower:
        return Provider.GEMINI
    elif "claude" in model_lower:
        return Provider.CLAUDE
    elif any(x in model_lower for x in ["gpt", "o1", "o3", "davinci", "curie", "babbage", "ada"]):
        return Provider.OPENAI
    else:
        return Provider.OPENAI  # Default to OpenAI


def get_multipliers(provider: Provider) -> Dict[str, float]:
    """Get multipliers for a provider
    
    Args:
        provider: Provider enum
    
    Returns:
        Dictionary of multipliers
    """
    return MULTIPLIERS.get(provider, MULTIPLIERS[Provider.OPENAI])


def is_cjk(code: int) -> bool:
    """Check if character is CJK (Chinese, Japanese, Korean)
    
    Args:
        code: Unicode code point
    
    Returns:
        True if CJK character
    """
    return (
        (0x4E00 <= code <= 0x9FFF) or      # CJK Unified Ideographs
        (0x3400 <= code <= 0x4DBF) or      # CJK Extension A
        (0x20000 <= code <= 0x2A6DF) or    # CJK Extension B
        (0x2A700 <= code <= 0x2B73F) or    # CJK Extension C
        (0x2B740 <= code <= 0x2B81F) or    # CJK Extension D
        (0x2B820 <= code <= 0x2CEAF) or    # CJK Extension E/F
        (0xF900 <= code <= 0xFAFF) or      # CJK Compatibility Ideographs
        (0x2F800 <= code <= 0x2FA1F) or    # CJK Compatibility Supplement
        (0x3040 <= code <= 0x309F) or      # Hiragana
        (0x30A0 <= code <= 0x30FF) or      # Katakana
        (0xAC00 <= code <= 0xD7AF)         # Hangul Syllables
    )


def is_emoji(code: int) -> bool:
    """Check if character is emoji
    
    Args:
        code: Unicode code point
    
    Returns:
        True if emoji
    """
    return (
        (0x1F600 <= code <= 0x1F64F) or    # Emoticons
        (0x1F300 <= code <= 0x1F5FF) or    # Misc Symbols and Pictographs
        (0x1F680 <= code <= 0x1F6FF) or    # Transport and Map
        (0x1F700 <= code <= 0x1F77F) or    # Alchemical Symbols
        (0x1F780 <= code <= 0x1F7FF) or    # Geometric Shapes Extended
        (0x1F800 <= code <= 0x1F8FF) or    # Supplemental Arrows-C
        (0x1F900 <= code <= 0x1F9FF) or    # Supplemental Symbols and Pictographs
        (0x1FA00 <= code <= 0x1FA6F) or    # Chess Symbols
        (0x1FA70 <= code <= 0x1FAFF) or    # Symbols and Pictographs Extended-A
        (0x2600 <= code <= 0x26FF) or      # Misc symbols
        (0x2700 <= code <= 0x27BF)         # Dingbats
    )


def is_math_symbol(code: int) -> bool:
    """Check if character is mathematical symbol
    
    Args:
        code: Unicode code point
    
    Returns:
        True if math symbol
    """
    return (
        (0x2200 <= code <= 0x22FF) or      # Mathematical Operators
        (0x2A00 <= code <= 0x2AFF) or      # Supplemental Mathematical Operators
        (0x1D400 <= code <= 0x1D7FF)       # Mathematical Alphanumeric Symbols
    )


def estimate_tokens(text: str, model: str = "") -> int:
    """Estimate token count for text using provider-specific multipliers
    
    This algorithm is based on new-api's token estimation with different weights for:
    - English words, numbers, CJK characters, symbols, emojis, etc.
    
    Args:
        text: Input text
        model: Model name (used to detect provider)
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    provider = detect_provider(model)
    m = get_multipliers(provider)
    
    count = 0.0
    current_word_type = None  # None, 'latin', 'number'
    
    for char in text:
        code = ord(char)
        
        # 1. Handle spaces and newlines
        if char.isspace():
            current_word_type = None
            if char in '\n\t':
                count += m['newline']
            else:
                count += m['space']
            continue
        
        # 2. Handle CJK characters
        if is_cjk(code):
            current_word_type = None
            count += m['cjk']
            continue
        
        # 3. Handle Emoji
        if is_emoji(code):
            current_word_type = None
            count += m['emoji']
            continue
        
        # 4. Handle Latin letters and numbers (English words)
        if char.isalnum():
            is_num = char.isdigit()
            new_type = 'number' if is_num else 'latin'
            
            # If not in a word, or type changed (letter<->number), count as new token
            if current_word_type is None or current_word_type != new_type:
                if new_type == 'number':
                    count += m['number']
                else:
                    count += m['word']
                current_word_type = new_type
            # Characters within a word don't add extra cost
            continue
        
        # 5. Handle symbols - use different weights by type
        current_word_type = None
        if is_math_symbol(code):
            count += m['math_symbol']
        elif char == '@':
            count += m['at_sign']
        elif char in '/:?&=;#%':
            count += m['url_delim']
        else:
            count += m['symbol']
    
    # Round up and add base padding
    return math.ceil(count) + int(m['base_pad'])
