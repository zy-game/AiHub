"""
Permission management for role-based access control
"""
from functools import wraps
from aiohttp import web

# Permission matrix
PERMISSIONS = {
    'super_admin': {
        'dashboard': ['view'],
        'providers': ['view', 'edit', 'delete', 'toggle'],
        'accounts': ['view', 'create', 'import', 'edit', 'delete'],
        'users': ['view', 'create', 'edit', 'delete'],
        'tokens': ['view', 'create', 'edit', 'delete'],
        'logs': ['view'],
        'invite_codes': ['view', 'create']
    },
    'admin': {
        'dashboard': ['view'],
        'providers': ['view'],  # 只能查看，不能编辑/删除/切换状态
        'accounts': ['view', 'import'],  # 只能查看和导入，不能删除/编辑
        'users': [],  # 无权限
        'tokens': [],  # 无权限
        'logs': ['view'],
        'invite_codes': []
    },
    'user': {
        'dashboard': [],  # 普通用户只能使用 API，不能访问管理面板
        'providers': [],
        'accounts': [],
        'users': [],
        'tokens': [],
        'logs': [],
        'invite_codes': []
    }
}

def has_permission(role: str, resource: str, action: str) -> bool:
    """Check if role has permission for resource and action"""
    return action in PERMISSIONS.get(role, {}).get(resource, [])

def require_permission(resource: str, action: str):
    """Decorator to check permission"""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: web.Request):
            user = request.get('current_user')
            if not user:
                return web.json_response({'error': 'Unauthorized'}, status=401)
            
            role = user.get('role', 'user')
            if not has_permission(role, resource, action):
                return web.json_response({
                    'error': 'Forbidden',
                    'message': f'您没有权限执行此操作 (需要: {resource}.{action})'
                }, status=403)
            
            return await handler(request)
        return wrapper
    return decorator

def require_role(*allowed_roles):
    """Decorator to check if user has one of the allowed roles"""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: web.Request):
            user = request.get('current_user')
            if not user:
                return web.json_response({'error': 'Unauthorized'}, status=401)
            
            role = user.get('role', 'user')
            if role not in allowed_roles:
                return web.json_response({
                    'error': 'Forbidden',
                    'message': f'需要以下角色之一: {", ".join(allowed_roles)}'
                }, status=403)
            
            return await handler(request)
        return wrapper
    return decorator

def get_user_permissions(role: str) -> dict:
    """Get all permissions for a role"""
    return PERMISSIONS.get(role, {})
