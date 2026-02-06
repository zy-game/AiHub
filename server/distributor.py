import json
from aiohttp import web
from providers import get_provider, get_all_providers
from utils.logger import logger
from utils.load_balancer import load_balancer

class RequestContext:
    def __init__(self):
        self.user = None
        self.token = None
        self.provider = None  # BaseProvider instance
        self.provider_type: str = None  # Provider type name
        self.model: str = None
        self.input_format: str = None  # openai, claude, gemini
        self.body: dict = None
        self.start_time: float = 0

async def extract_model_from_request(request: web.Request) -> tuple[str, dict, str]:
    """Extract model name from request body and determine input format"""
    path = request.path
    body = {}
    input_format = "openai"
    
    try:
        body = await request.json()
    except:
        pass
    
    model = body.get("model", "")
    
    # Determine input format based on path and headers
    if "/v1/messages" in path or request.headers.get("anthropic-version"):
        input_format = "claude"
    elif "/v1/responses" in path:
        input_format = "openai_responses"
    elif "/v1beta/models" in path or request.headers.get("x-goog-api-key"):
        input_format = "gemini"
        # Extract model from Gemini path: /v1beta/models/gemini-2.0-flash:generateContent
        if not model and "/models/" in path:
            parts = path.split("/models/")[-1].split(":")
            if parts:
                model = parts[0]
    else:
        input_format = "openai"
    
    return model, body, input_format

async def distribute(request: web.Request, ctx: RequestContext):
    """Select appropriate provider based on model name using load balancer"""
    model, body, input_format = await extract_model_from_request(request)
    
    if not model:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": {"message": "Model name is required", "type": "invalid_request_error"}}),
            content_type="application/json"
        )
    
    ctx.model = model
    ctx.body = body
    ctx.input_format = input_format
    
    # Get all providers that support this model
    all_providers = get_all_providers()
    
    # Filter providers that support the model and are enabled
    candidates = [
        provider for provider in all_providers.values()
        if provider.enabled and provider.supports_model(model)
    ]
    
    if not candidates:
        # Provide detailed error message
        supporting_providers = [
            p for p in all_providers.values()
            if p.supports_model(model)
        ]
        
        if not supporting_providers:
            error_msg = f"No provider supports model: {model}"
        else:
            disabled_count = sum(1 for p in supporting_providers if not p.enabled)
            if disabled_count == len(supporting_providers):
                error_msg = f"All providers supporting model '{model}' are disabled. Please enable at least one provider."
            else:
                error_msg = f"No available provider for model: {model}. Providers may be disabled or have no healthy accounts."
        
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": {"message": error_msg, "type": "model_not_found"}}),
            content_type="application/json"
        )
    
    # Sort by priority (descending) and weight (descending)
    candidates.sort(key=lambda p: (p.priority, p.weight), reverse=True)
    
    # Use load balancer to select from candidates (weighted selection)
    selected_provider = load_balancer.select_provider(candidates)
    
    if not selected_provider:
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": {"message": f"Failed to select provider for model: {model}", "type": "service_unavailable"}}),
            content_type="application/json"
        )
    
    ctx.provider = selected_provider
    ctx.provider_type = selected_provider.name
    
    return selected_provider
