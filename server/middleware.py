import json
import time
from aiohttp import web
from models import get_user_by_api_key, get_token_by_key, get_user_by_id, create_log, update_user_quota
from models.auth import verify_session
from utils.logger import logger
from config import ADMIN_KEY

@web.middleware
async def auth_middleware(request: web.Request, handler):
    # Public paths that don't require authentication
    public_paths = [
        '/login', '/register', '/verify-email',
        '/api/auth/login', '/api/auth/register', '/api/auth/verify-email',
        '/static', '/favicon.ico'
    ]
    
    # Check if path is public
    for public_path in public_paths:
        if request.path == public_path or request.path.startswith(public_path):
            return await handler(request)
    
    # Risk control page - require super_admin
    if request.path == '/risk-control':
        session_token = request.cookies.get('session_token')
        if not session_token:
            return web.HTTPFound('/login')
        
        user = await verify_session(session_token)
        if not user or user.get('role') != 'super_admin':
            return web.Response(text='权限不足：仅超级管理员可访问', status=403)
        
        request['current_user'] = user
        return await handler(request)
    
    # Root path (/) - redirect to login if not authenticated
    if request.path == '/':
        session_token = request.cookies.get('session_token')
        if not session_token:
            # Not authenticated, redirect to login
            return web.HTTPFound('/login')
        
        # Verify session
        user = await verify_session(session_token)
        if not user:
            # Invalid session, redirect to login
            return web.HTTPFound('/login')
        
        # Authenticated, store user and continue
        request['current_user'] = user
        return await handler(request)
    
    # Admin panel API routes (/api/*) - require session authentication
    if request.path.startswith('/api/'):
        session_token = request.cookies.get('session_token')
        
        if not session_token:
            return web.json_response({
                'error': 'Not authenticated',
                'message': '请先登录'
            }, status=401)
        
        # Verify session
        user = await verify_session(session_token)
        if not user:
            return web.json_response({
                'error': 'Invalid session',
                'message': '登录已过期，请重新登录'
            }, status=401)
        
        # Risk control API routes - require super_admin
        if request.path.startswith('/api/risk-control/'):
            if user.get('role') != 'super_admin':
                return web.json_response({
                    'error': 'Permission denied',
                    'message': '权限不足：仅超级管理员可访问风控系统'
                }, status=403)
        
        # Store user in request
        request['current_user'] = user
        return await handler(request)
    
    # API routes (v1/*) - use API key authentication
    if request.path.startswith('/v1/'):
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("x-api-key", "")
        
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        
        if not api_key:
            return web.json_response(
                {"error": {"message": "API key is required", "type": "authentication_error"}},
                status=401
            )
        
        # Try to authenticate with Token
        token = await get_token_by_key(api_key)
        if token:
            # Validate token
            is_valid, error_msg = token.is_valid()
            if not is_valid:
                return web.json_response(
                    {"error": {"message": error_msg, "type": "authentication_error"}},
                    status=401
                )
            
            # Check token owner's quota
            token_owner = await get_user_by_id(token.user_id)
            if token_owner:
                if not token_owner.has_quota():
                    return web.json_response(
                        {"error": {"message": "User quota exhausted", "type": "quota_exceeded"}},
                        status=429
                    )
            
            # Check IP whitelist
            client_ip = request.remote
            if not token.is_ip_allowed(client_ip):
                return web.json_response(
                    {"error": {"message": "IP not allowed", "type": "authentication_error"}},
                    status=403
                )
            
            # Check rate limits
            estimated_tokens = 0
            try:
                body = await request.json()
                messages = body.get("messages", [])
                for msg in messages:
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        estimated_tokens += len(content) // 4
            except:
                estimated_tokens = 1000
            
            # Check token rate limits (if rate limiter is available)
            try:
                from utils.rate_limiter import get_rate_limiter
                rate_limiter = get_rate_limiter()
                
                if rate_limiter and (token.rpm_limit > 0 or token.tpm_limit > 0):
                    # TODO: Implement token-level rate limiting
                    pass
            except ImportError:
                pass  # Rate limiter not initialized yet
            
            request["token"] = token
            request["user"] = None
            request["start_time"] = time.time()
            return await handler(request)
        
        # No valid token found
        return web.json_response(
            {"error": {"message": "Invalid API key", "type": "authentication_error"}},
            status=401
        )
    
    # Other paths - deny access
    return web.json_response(
        {"error": "Not found"},
        status=404
    )

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
