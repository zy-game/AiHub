"""Model pricing and rate configuration"""

# Model pricing rates (based on New-API)
# Format: {model_name: {"input": price_per_1k, "output": price_per_1k, "ratio": completion_ratio}}

MODEL_RATES = {
    # OpenAI GPT-4 Series
    "gpt-4": {"input": 0.03, "output": 0.06, "ratio": 15},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-4-0125-preview": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-4-1106-preview": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-4-vision-preview": {"input": 0.01, "output": 0.03, "ratio": 10},
    "gpt-4-32k": {"input": 0.06, "output": 0.12, "ratio": 30},
    
    # OpenAI GPT-3.5 Series
    "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002, "ratio": 1},
    "gpt-3.5-turbo-0125": {"input": 0.0005, "output": 0.0015, "ratio": 0.5},
    "gpt-3.5-turbo-1106": {"input": 0.001, "output": 0.002, "ratio": 1},
    "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004, "ratio": 2},
    
    # OpenAI O1 Series
    "o1-preview": {"input": 0.015, "output": 0.06, "ratio": 15},
    "o1-mini": {"input": 0.003, "output": 0.012, "ratio": 3},
    
    # Claude 3 Series
    "claude-3-opus": {"input": 0.015, "output": 0.075, "ratio": 15},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075, "ratio": 15},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015, "ratio": 3},
    "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015, "ratio": 3},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125, "ratio": 0.25},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125, "ratio": 0.25},
    
    # Claude 3.5 Series
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015, "ratio": 3},
    "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015, "ratio": 3},
    
    # Google Gemini Series
    "gemini-pro": {"input": 0.00025, "output": 0.0005, "ratio": 0.5},
    "gemini-pro-vision": {"input": 0.00025, "output": 0.0005, "ratio": 0.5},
    "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105, "ratio": 3.5},
    "gemini-1.5-flash": {"input": 0.00035, "output": 0.00105, "ratio": 0.35},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0003, "ratio": 0.1},
    
    # Default fallback
    "default": {"input": 0.001, "output": 0.002, "ratio": 1}
}


def get_model_rate(model: str) -> dict:
    """
    Get pricing rate for a model
    
    Args:
        model: Model name
    
    Returns:
        Dict with input, output prices and ratio
    """
    # Exact match
    if model in MODEL_RATES:
        return MODEL_RATES[model]
    
    # Fuzzy match (check if model name contains key)
    model_lower = model.lower()
    for key, rate in MODEL_RATES.items():
        if key in model_lower:
            return rate
    
    # Default fallback
    return MODEL_RATES["default"]


def calculate_cost(model: str, input_tokens: int, output_tokens: int, 
                   cache_read_tokens: int = 0, cache_creation_tokens: int = 0,
                   provider_type: str = None) -> dict:
    """
    Calculate cost for a request (with cache support)
    
    Args:
        model: Model name
        input_tokens: Number of input tokens (non-cached)
        output_tokens: Number of output tokens
        cache_read_tokens: Number of cached tokens read
        cache_creation_tokens: Number of tokens used for cache creation
        provider_type: Provider type for cache ratio lookup
    
    Returns:
        Dict with cost breakdown
    """
    from utils.cache_handler import get_cache_handler
    
    rate = get_model_rate(model)
    
    # Calculate base costs (per 1000 tokens)
    input_cost = (input_tokens / 1000) * rate["input"]
    output_cost = (output_tokens / 1000) * rate["output"]
    
    # Calculate cache costs if applicable
    cache_read_cost = 0
    cache_creation_cost = 0
    cache_savings = 0
    
    if cache_read_tokens > 0 or cache_creation_tokens > 0:
        cache_handler = get_cache_handler()
        
        # Get cache ratios for this provider
        if provider_type:
            ratios = cache_handler.CACHE_RATIOS.get(provider_type, {
                "cache_read": 1.0,
                "cache_creation": 1.0
            })
        else:
            ratios = {"cache_read": 1.0, "cache_creation": 1.0}
        
        # Calculate cache costs
        cache_read_cost = (cache_read_tokens / 1000) * rate["input"] * ratios["cache_read"]
        cache_creation_cost = (cache_creation_tokens / 1000) * rate["input"] * ratios["cache_creation"]
        
        # Calculate savings (what we would have paid without cache)
        cache_savings = (cache_read_tokens / 1000) * rate["input"] * (1 - ratios["cache_read"])
    
    total_cost = input_cost + output_cost + cache_read_cost + cache_creation_cost
    
    # Calculate quota usage (based on ratio)
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens
    quota_usage = int(total_tokens * rate["ratio"])
    
    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cache_read_cost": round(cache_read_cost, 6),
        "cache_creation_cost": round(cache_creation_cost, 6),
        "cache_savings": round(cache_savings, 6),
        "total_cost": round(total_cost, 6),
        "quota_usage": quota_usage,
        "ratio": rate["ratio"]
    }


def get_all_models() -> list:
    """Get list of all configured models"""
    return [k for k in MODEL_RATES.keys() if k != "default"]


def get_models_by_provider(provider: str) -> list:
    """
    Get models for a specific provider
    
    Args:
        provider: Provider name (openai, claude, gemini)
    
    Returns:
        List of model names
    """
    provider_lower = provider.lower()
    
    if provider_lower in ["openai", "gpt"]:
        return [k for k in MODEL_RATES.keys() if k.startswith(("gpt-", "o1-"))]
    elif provider_lower in ["claude", "anthropic"]:
        return [k for k in MODEL_RATES.keys() if k.startswith("claude-")]
    elif provider_lower in ["gemini", "google"]:
        return [k for k in MODEL_RATES.keys() if k.startswith("gemini-")]
    else:
        return []
