# Providers package
from .base import BaseProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider
from .kiro import KiroProvider

def get_provider(provider_type: str) -> BaseProvider:
    providers = {
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "google": GoogleProvider(),
        "kiro": KiroProvider(),
    }
    return providers.get(provider_type)
