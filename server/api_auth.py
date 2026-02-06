"""
Authentication API endpoints
"""
from aiohttp import web
from models.auth import (
    login, logout, register_user, verify_email, verify_session,
    create_invite_code, get_invite_codes, change_password
)
from models.token import get_all_tokens
from server.permissions import require_role, get_user_permissions
from utils.logger import logger

async def api_register(request: web.Request) -> web.Response:
    """POST /api/auth/register - User registration"""
    try:
        data = await request.json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        # Handle invite_code - optional field for marketing/referral
        invite_code = data.get('invite_code')
        if invite_code:
            invite_code = invite_code.strip() or None
        else:
            invite_code = None
        
        # Validate input
        if not email or not password or not name:
            return web.json_response({
                'error': '请填写所有必填字段（邮箱、密码、用户名）'
            }, status=400)
        
        if len(password) < 6:
            return web.json_response({
                'error': '密码长度至少为6位'
            }, status=400)
        
        # Register user (invite_code is optional)
        success, message, user_data = await register_user(email, password, name, invite_code)
        
        if not success:
            return web.json_response({'error': message}, status=400)
        
        # TODO: Send verification email
        # For now, we'll just return success
        logger.info(f"Verification token for {email}: {user_data.get('verification_token')}")
        
        return web.json_response({
            'success': True,
            'message': message,
            'verification_url': f'/verify-email?token={user_data.get("verification_token")}'
        })
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_verify_email(request: web.Request) -> web.Response:
    """GET /api/auth/verify-email?token=xxx - Verify email"""
    try:
        token = request.query.get('token', '')
        if not token:
            return web.json_response({'error': '缺少验证令牌'}, status=400)
        
        success, message = await verify_email(token)
        
        if not success:
            return web.json_response({'error': message}, status=400)
        
        return web.json_response({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_login(request: web.Request) -> web.Response:
    """POST /api/auth/login - User login"""
    try:
        data = await request.json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return web.json_response({
                'error': '请输入邮箱和密码'
            }, status=400)
        
        # Login
        success, message, user_data = await login(email, password)
        
        if not success:
            return web.json_response({'error': message}, status=401)
        
        # Set session cookie
        response = web.json_response({
            'success': True,
            'user': {
                'id': user_data['user_id'],
                'email': user_data['email'],
                'name': user_data['name'],
                'role': user_data['role'],
                'permissions': get_user_permissions(user_data['role'])
            }
        })
        
        response.set_cookie(
            'session_token',
            user_data['session_token'],
            max_age=7*24*3600,  # 7 days
            httponly=True,
            samesite='Lax'
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_logout(request: web.Request) -> web.Response:
    """POST /api/auth/logout - User logout"""
    try:
        session_token = request.cookies.get('session_token')
        if session_token:
            await logout(session_token)
        
        response = web.json_response({'success': True})
        response.del_cookie('session_token')
        
        return response
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_current_user(request: web.Request) -> web.Response:
    """GET /api/auth/me - Get current user info"""
    try:
        user = request.get('current_user')
        if not user:
            return web.json_response({'error': 'Not authenticated'}, status=401)
        
        return web.json_response({
            'id': user['id'],
            'email': user['email'],
            'name': user['name'],
            'role': user['role'],
            'quota': user.get('quota', -1),
            'used_quota': user.get('used_quota', 0),
            'total_tokens': user.get('total_tokens', 0),
            'input_tokens': user.get('input_tokens', 0),
            'output_tokens': user.get('output_tokens', 0),
            'last_login_at': user.get('last_login_at'),
            'permissions': get_user_permissions(user['role'])
        })
        
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_change_password(request: web.Request) -> web.Response:
    """POST /api/auth/change-password - Change password"""
    try:
        user = request.get('current_user')
        if not user:
            return web.json_response({'error': 'Not authenticated'}, status=401)
        
        data = await request.json()
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return web.json_response({
                'error': '请输入旧密码和新密码'
            }, status=400)
        
        if len(new_password) < 6:
            return web.json_response({
                'error': '新密码长度至少为6位'
            }, status=400)
        
        success, message = await change_password(user['id'], old_password, new_password)
        
        if not success:
            return web.json_response({'error': message}, status=400)
        
        return web.json_response({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def api_user_tokens(request: web.Request) -> web.Response:
    """GET /api/auth/tokens - Get current user's API tokens"""
    try:
        user = request.get('current_user')
        if not user:
            return web.json_response({'error': 'Not authenticated'}, status=401)
        
        tokens = await get_all_tokens(user['id'])
        
        return web.json_response([{
            'id': t.id,
            'user_id': t.user_id,
            'key': t.key,
            'name': t.name,
            'status': t.status,
            'created_time': t.created_time,
            'accessed_time': t.accessed_time,
            'expired_time': t.expired_time,
            'model_limits_enabled': t.model_limits_enabled,
            'model_limits': t.model_limits,
            'ip_whitelist': t.ip_whitelist,
            'group': t.group or 'default',  # 添加默认值
            'input_tokens': t.input_tokens,
            'output_tokens': t.output_tokens,
            'total_tokens': t.total_tokens,
            'request_count': t.request_count,
            'rpm_limit': t.rpm_limit,
            'tpm_limit': t.tpm_limit,
            'cross_group_retry': t.cross_group_retry
        } for t in tokens])
        
    except Exception as e:
        logger.error(f"Get user tokens error: {e}")
        return web.json_response({'error': str(e)}, status=500)

@require_role('super_admin', 'admin')
async def api_create_invite_code(request: web.Request) -> web.Response:
    """POST /api/auth/invite-codes - Create invite code"""
    try:
        user = request.get('current_user')
        code = await create_invite_code(user['id'])
        
        return web.json_response({
            'success': True,
            'code': code
        })
        
    except Exception as e:
        logger.error(f"Create invite code error: {e}")
        return web.json_response({'error': str(e)}, status=500)

@require_role('super_admin', 'admin')
async def api_list_invite_codes(request: web.Request) -> web.Response:
    """GET /api/auth/invite-codes - List invite codes"""
    try:
        user = request.get('current_user')
        
        # Super admin can see all codes, admin only sees their own
        if user['role'] == 'super_admin':
            codes = await get_invite_codes()
        else:
            codes = await get_invite_codes(user['id'])
        
        return web.json_response([{
            'id': c['id'],
            'code': c['code'],
            'used_by': c.get('used_by'),
            'used_by_email': c.get('used_by_email'),
            'used_at': c.get('used_at'),
            'created_at': c['created_at']
        } for c in codes])
        
    except Exception as e:
        logger.error(f"List invite codes error: {e}")
        return web.json_response({'error': str(e)}, status=500)
