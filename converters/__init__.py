# Converters package
from .base import BaseConverter
from .openai import OpenAIConverter, OpenAIToClaudeConverter
from .claude import ClaudeConverter
from .gemini import GeminiConverter
from .glm import GLMConverter, GLMStreamConverter
from .kiro import KiroConverter, KiroStreamConverter, convert_anthropic_messages_to_kiro, convert_anthropic_tools_to_kiro

def get_converter(format_name: str) -> BaseConverter:
    converters = {
        "openai": OpenAIConverter(),
        "claude": ClaudeConverter(),
        "gemini": GeminiConverter(),
        "glm": GLMConverter(),
        "kiro": KiroConverter(),
    }
    return converters.get(format_name)
