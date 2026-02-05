# Converters package
from .base import BaseConverter
from .openai import OpenAIConverter
from .claude import ClaudeConverter
from .gemini import GeminiConverter

def get_converter(format_name: str) -> BaseConverter:
    converters = {
        "openai": OpenAIConverter(),
        "claude": ClaudeConverter(),
        "gemini": GeminiConverter(),
    }
    return converters.get(format_name)
