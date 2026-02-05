import json
from aiohttp import web
from models import get_channel_by_model, Channel
from utils.logger import logger

class RequestContext:
    def __init__(self):
        self.user = None
        self.token = None
        self.channel: Channel = None
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

async def distribute(request: web.Request, ctx: RequestContext) -> Channel:
    """Select appropriate channel based on model name"""
    model, body, input_format = await extract_model_from_request(request)
    
    if not model:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": {"message": "Model name is required", "type": "invalid_request_error"}}),
            content_type="application/json"
        )
    
    ctx.model = model
    ctx.body = body
    ctx.input_format = input_format
    
    channel = await get_channel_by_model(model)
    if not channel:
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": {"message": f"No available channel for model: {model}", "type": "model_not_found"}}),
            content_type="application/json"
        )
    
    ctx.channel = channel
    
    return channel
