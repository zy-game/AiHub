# Providers package
import inspect
import sys
from typing import Dict, Optional
from .base import BaseProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider
from .kiro import KiroProvider

# Global provider registry
_PROVIDERS: Dict[str, BaseProvider] = {}

def discover_providers() -> Dict[str, BaseProvider]:
    """Automatically discover all Provider classes that inherit from BaseProvider"""
    providers = {}
    
    # Get current module
    current_module = sys.modules[__name__]
    
    # Iterate through all attributes in this module
    for name in dir(current_module):
        obj = getattr(current_module, name)
        
        # Check if it's a class and inherits from BaseProvider (but not BaseProvider itself)
        if (inspect.isclass(obj) and 
            issubclass(obj, BaseProvider) and 
            obj is not BaseProvider):
            try:
                # Instantiate the provider
                instance = obj()
                providers[instance.name] = instance
            except Exception as e:
                print(f"Warning: Failed to instantiate provider {name}: {e}")
    
    return providers

def initialize_providers():
    """Initialize the global provider registry"""
    global _PROVIDERS
    _PROVIDERS = discover_providers()
    print(f"Discovered {len(_PROVIDERS)} providers: {list(_PROVIDERS.keys())}")

def get_provider(provider_type: str) -> Optional[BaseProvider]:
    """Get a provider by type name"""
    return _PROVIDERS.get(provider_type)

def get_all_providers() -> Dict[str, BaseProvider]:
    """Get all registered providers"""
    return _PROVIDERS.copy()

def configure_provider(provider_type: str, **config):
    """Configure a provider with custom settings"""
    provider = get_provider(provider_type)
    if provider:
        provider.configure(**config)
        return True
    return False

# Auto-initialize on import
initialize_providers()
