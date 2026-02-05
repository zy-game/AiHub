import json
import time
from aiohttp import web
from models import get_user_by_api_key, create_log, update_user_quota
from utils.logger import logger
from config import ADMIN_KEY

@web.middleware
async def auth_middleware(request: web.Request, handler):
    # Skip auth for static files, index page, and favicon
    if request.path.startswith("/static") or request.path == "/" or request.path == "/favicon.ico":
        return await handler(request)
    
    # Admin API routes
    if request.path.startswith("/api/"):
        admin_key = request.headers.get("X-Admin-Key", "")
        if admin_key != ADMIN_KEY:
            return web.json_response(
                {"error": {"message": "Invalid admin key", "type": "authentication_error"}},
                status=401
            )
        return await handler(request)
    
    # API routes - extract API key
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("x-api-key", "")  # Claude style
    
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    
    if not api_key:
        return web.json_response(
            {"error": {"message": "API key is required", "type": "authentication_error"}},
            status=401
        )
    
    user = await get_user_by_api_key(api_key)
    if not user:
        return web.json_response(
            {"error": {"message": "Invalid API key", "type": "authentication_error"}},
            status=401
        )
    
    if not user.has_quota():
        return web.json_response(
            {"error": {"message": "Quota exceeded", "type": "quota_exceeded"}},
            status=429
        )
    
    request["user"] = user
    request["start_time"] = time.time()
    
    return await handler(request)

@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        return web.json_response(
            {"error": {"message": str(e), "type": "internal_error"}},
            status=500
        )

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Key, x-api-key, anthropic-version",
            }
        )
    
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
