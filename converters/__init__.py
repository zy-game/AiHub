# Converters package
from .base import BaseConverter
from .openai import OpenAIConverter
from .claude import ClaudeConverter
from .gemini import GeminiConverter
from .glm import GLMConverter

def get_converter(format_name: str) -> BaseConverter:
    converters = {
        "openai": OpenAIConverter(),
        "claude": ClaudeConverter(),
        "gemini": GeminiConverter(),
        "glm": GLMConverter(),
    }
    return converters.get(format_name)
