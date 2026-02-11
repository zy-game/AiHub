import json
import uuid
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from aiohttp import web
from models import (
    get_all_channels, get_channel_by_id, create_channel, update_channel, delete_channel,
    get_accounts_by_channel, get_accounts_by_provider,
    get_all_accounts_with_channels, get_all_accounts_with_providers,
    create_account, batch_create_accounts, update_account, delete_account, 
    delete_accounts_by_channel, delete_accounts_by_provider,
    get_account_usage_totals,
    get_all_users, create_user, update_user, delete_user,
    get_logs, get_stats, get_model_stats, get_channel_token_usage, get_user_token_usage, get_hourly_stats, get_channel_stats, get_top_users,
    get_cache_config, update_cache_config
)
from providers import get_provider
from utils.logger import logger

# Channel API
async def api_list_channels(request: web.Request) -> web.Response:
    channels = await get_all_channels()
    result = []
    for c in channels:
        accounts = await get_accounts_by_channel(c.id)
        totals = await get_account_usage_totals(c.id)
        # Sum tokens from all accounts in this channel
        total_tokens = sum(a.total_tokens or 0 for a in accounts)
        
        # Check if provider supports usage refresh
        provider = get_provider(c.type)
        supports_refresh = provider.supports_usage_refresh() if provider else False
        
        result.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "priority": c.priority,
            "weight": c.weight,
            "enabled": c.enabled,
            "account_count": len(accounts),
            "enabled_account_count": sum(1 for a in accounts if a.enabled),
            "usage": totals["used"],
            "limit": totals["limit"],
            "total_tokens": total_tokens,
            "supports_usage_refresh": supports_refresh
        })
    return web.json_response(result)

async def api_create_channel(request: web.Request) -> web.Response:
    data = await request.json()
    id_ = await create_channel(
        name=data["name"],
        type_=data["type"],
        priority=data.get("priority", 0),
        weight=data.get("weight", 1)
    )
    return web.json_response({"id": id_, "success": True})

async def api_update_channel(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    data = await request.json()
    await update_channel(id_, **data)
    return web.json_response({"success": True})

async def api_channel_models(request: web.Request) -> web.Response:
    """Get supported models for a channel"""
    id_ = int(request.match_info["id"])
    
    channel = await get_channel_by_id(id_)
    if not channel:
        return web.json_response({"error": "Channel not found"}, status=404)
    
    from providers import get_provider
    provider = get_provider(channel.type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    models = provider.get_supported_models()
    
    return web.json_response({
        "channel_id": channel.id,
        "channel_name": channel.name,
        "channel_type": channel.type,
        "supported_models": models
    })

async def api_delete_channel(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    await delete_accounts_by_channel(id_)
    await delete_channel(id_)
    return web.json_response({"success": True})

# Account API
async def api_list_all_accounts(request: web.Request) -> web.Response:
    accounts = await get_all_accounts_with_providers()
    result = []
    for row in accounts:
        result.append({
            "id": row["id"],
            "channel_id": row.get("provider_type") or row.get("channel_id", ""),  # Use provider_type as channel_id
            "channel_name": row.get("channel_name", ""),
            "channel_type": row.get("channel_type", ""),
            "name": row.get("name", ""),
            "api_key": row.get("api_key", "")[:20] + "..." if len(row.get("api_key", "")) > 20 else row.get("api_key", ""),
            "api_key_full": row.get("api_key", ""),
            "usage": row.get("usage") or 0,
            "limit": row.get("limit") or 0,
            "input_tokens": row.get("input_tokens") or 0,
            "output_tokens": row.get("output_tokens") or 0,
            "total_tokens": row.get("total_tokens") or 0,
            "last_used_at": row.get("last_used_at"),
            "enabled": row.get("enabled", 1),
            "created_by": row.get("created_by")
        })
    return web.json_response(result)

async def api_list_accounts(request: web.Request) -> web.Response:
    channel_id = int(request.match_info["channel_id"])
    accounts = await get_accounts_by_channel(channel_id)
    return web.json_response([{
        "id": a.id,
        "channel_id": a.channel_id,
        "name": a.name,
        "api_key": a.api_key[:20] + "..." if len(a.api_key) > 20 else a.api_key,
        "api_key_full": a.api_key,
        "usage": a.usage or 0,
        "limit": a.limit or 0,
        "input_tokens": a.input_tokens or 0,
        "output_tokens": a.output_tokens or 0,
        "total_tokens": a.total_tokens or 0,
        "last_used_at": a.last_used_at,
        "enabled": a.enabled
    } for a in accounts])

async def api_create_account(request: web.Request) -> web.Response:
    channel_id = int(request.match_info["channel_id"])
    data = await request.json()
    id_ = await create_account(
        channel_id=channel_id,
        api_key=data["api_key"],
        name=data.get("name", "")
    )
    return web.json_response({"id": id_, "success": True})

async def api_batch_import_accounts(request: web.Request) -> web.Response:
    """Batch import accounts. Accepts:
    - JSON array of Kiro accounts: [{"refreshToken": "...", "clientId": "...", ...}]
    - JSON array of simple accounts: [{"api_key": "xxx", "name": "optional"}]
    - Or plain text with one api_key per line
    """
    channel_id = int(request.match_info["channel_id"])
    content_type = request.content_type
    
    # Get channel type to determine import format
    from models import get_all_channels
    channels = await get_all_channels()
    channel = next((c for c in channels if c.id == channel_id), None)
    channel_type = channel.type if channel else "openai"
    
    accounts = []
    
    if "json" in content_type:
        data = await request.json()
        if isinstance(data, list):
            raw_accounts = data
        else:
            raw_accounts = data.get("accounts", [])
        
        for acc in raw_accounts:
            if channel_type == "kiro":
                # Kiro format: store entire credential object as api_key JSON
                if "refreshToken" in acc:
                    accounts.append({
                        "api_key": json.dumps(acc),
                        "name": acc.get("clientId", "")[:20] if acc.get("clientId") else ""
                    })
                elif "api_key" in acc:
                    accounts.append(acc)
            else:
                # Standard format
                if "api_key" in acc:
                    accounts.append(acc)
    else:
        text = await request.text()
        # Try to parse as JSON first (for file upload)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for acc in data:
                    if channel_type == "kiro" and "refreshToken" in acc:
                        accounts.append({
                            "api_key": json.dumps(acc),
                            "name": acc.get("clientId", "")[:20] if acc.get("clientId") else ""
                        })
                    elif "api_key" in acc:
                        accounts.append(acc)
        except json.JSONDecodeError:
            # Plain text, one api_key per line
            accounts = [{"api_key": line.strip()} for line in text.split("\n") if line.strip()]
    
    count = await batch_create_accounts(channel_id, accounts)
    return web.json_response({"imported": count, "success": True})

async def api_update_account(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    data = await request.json()
    await update_account(id_, **data)
    return web.json_response({"success": True})

async def api_delete_account(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    await delete_account(id_)
    return web.json_response({"success": True})

async def api_clear_accounts(request: web.Request) -> web.Response:
    channel_id = int(request.match_info["channel_id"])
    count = await delete_accounts_by_channel(channel_id)
    return web.json_response({"deleted": count, "success": True})

# User API
async def api_list_users(request: web.Request) -> web.Response:
    users = await get_all_users()
    return web.json_response([{
        "id": u.id,
        "api_key": u.api_key,
        "name": u.name,
        "email": u.email or '',
        "role": u.role or 'user',
        "quota": u.quota,
        "used_quota": u.used_quota,
        "enabled": u.enabled,
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "total_tokens": u.total_tokens or 0
    } for u in users])

async def api_create_user(request: web.Request) -> web.Response:
    data = await request.json()
    id_, api_key = await create_user(
        name=data.get("name"),
        quota=data.get("quota", -1)
    )
    return web.json_response({"id": id_, "api_key": api_key, "success": True})

async def api_update_user(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    data = await request.json()
    await update_user(id_, **data)
    return web.json_response({"success": True})

async def api_delete_user(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    await delete_user(id_)
    return web.json_response({"success": True})

# Logs & Stats API
async def api_list_logs(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", 100))
    offset = int(request.query.get("offset", 0))
    logs = await get_logs(limit, offset)
    return web.json_response(logs)

async def api_get_stats(request: web.Request) -> web.Response:
    days = int(request.query.get("days", 7))
    
    # Get current user from request
    current_user = request.get('current_user')
    user_id = None
    
    # If not super_admin, filter by current user
    if current_user and current_user.get('role') != 'super_admin':
        user_id = current_user.get('id')
    
    # Get stats (filtered by user_id if not super_admin)
    stats = await get_stats(days, user_id)
    model_stats = await get_model_stats(days, user_id)
    hourly_stats = await get_hourly_stats(days, user_id)
    
    # Channel stats - show for all users
    channel_stats = await get_channel_stats()
    
    # Top users - only for super_admin
    if current_user and current_user.get('role') == 'super_admin':
        top_users = await get_top_users(10)
    else:
        top_users = []
    
    return web.json_response({
        "overview": stats,
        "models": model_stats,
        "hourly": hourly_stats,
        "channels": channel_stats,
        "top_users": top_users
    })

# Kiro OAuth API
import aiohttp
import uuid

KIRO_SSO_OIDC_URL = "https://oidc.us-east-1.amazonaws.com"
KIRO_BUILDER_ID_START_URL = "https://view.awsapps.com/start"

async def api_kiro_device_auth(request: web.Request) -> web.Response:
    """Start Kiro device authorization flow with Builder ID"""
    try:
        # 1. Register OIDC client first
        async with aiohttp.ClientSession() as session:
            # Register client
            async with session.post(
                f"{KIRO_SSO_OIDC_URL}/client/register",
                json={
                    "clientName": "AiHub",
                    "clientType": "public",
                    "scopes": [
                        "codewhisperer:completions",
                        "codewhisperer:analysis",
                        "codewhisperer:conversations"
                    ]
                },
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AiHub/1.0"
                }
            ) as resp:
                if resp.status != 201:
                    error = await resp.text()
                    return web.json_response({"error": {"message": f"Client registration failed: {error}"}}, status=400)
                
                reg_data = await resp.json()
                client_id = reg_data.get("clientId")
                client_secret = reg_data.get("clientSecret")
            
            # 2. Start device authorization
            async with session.post(
                f"{KIRO_SSO_OIDC_URL}/device_authorization",
                json={
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "startUrl": KIRO_BUILDER_ID_START_URL
                },
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return web.json_response({"error": {"message": f"Device auth failed: {error}"}}, status=400)
                
                data = await resp.json()
                # Store client credentials for token exchange
                data["_clientId"] = client_id
                data["_clientSecret"] = client_secret
                return web.json_response(data)
                
    except Exception as e:
        return web.json_response({"error": {"message": str(e)}}, status=500)

async def api_kiro_device_token(request: web.Request) -> web.Response:
    """Poll for Kiro device token and import account"""
    req_data = await request.json()
    device_code = req_data.get("device_code")
    client_id = req_data.get("client_id")
    client_secret = req_data.get("client_secret")
    channel_id = req_data.get("channel_id")
    
    if not device_code or not client_id or not client_secret:
        return web.json_response({"error": "missing_parameters"}, status=400)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{KIRO_SSO_OIDC_URL}/token",
                json={
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "deviceCode": device_code,
                    "grantType": "urn:ietf:params:oauth:grant-type:device_code"
                },
                headers={"Content-Type": "application/json"}
            ) as resp:
                data = await resp.json()
                
                if resp.status != 200:
                    return web.json_response(data)
                
                # Successfully got tokens, create account
                if "accessToken" in data and channel_id:
                    account_data = {
                        "accessToken": data.get("accessToken"),
                        "refreshToken": data.get("refreshToken"),
                        "clientId": client_id,
                        "clientSecret": client_secret,
                        "region": "us-east-1",
                        "expiresAt": data.get("expiresIn")
                    }
                    
                    # Import the account
                    count = await batch_create_accounts(channel_id, [{
                        "api_key": json.dumps(account_data),
                        "name": f"BuilderID-{str(uuid.uuid4())[:8]}"
                    }])
                    
                    return web.json_response({"success": True, "imported": count})
                
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Usage Refresh API
async def api_refresh_account_usage(request: web.Request) -> web.Response:
    """Refresh usage for a single account"""
    account_id = int(request.match_info["id"])
    
    # Get account info
    accounts = await get_all_accounts_with_channels()
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        return web.json_response({"error": "Account not found"}, status=404)
    
    # Get provider
    channel_type = account.get("channel_type")
    provider = get_provider(channel_type)
    if not provider:
        return web.json_response({"error": f"Provider {channel_type} not available"}, status=500)
    
    # Check if provider supports usage refresh
    if not provider.supports_usage_refresh():
        return web.json_response({"error": f"Usage refresh not supported for {channel_type} channels"}, status=400)
    
    try:
        result = await provider.refresh_usage(account["api_key"], account_id)
        if result is None:
            return web.json_response({"error": "Failed to refresh usage"}, status=500)
        
        used, limit = result
        await update_account(account_id, usage=used, **{"limit": limit})
        return web.json_response({
            "success": True,
            "usage": used,
            "limit": limit
        })
    except Exception as e:
        logger.error(f"Failed to refresh account {account_id} usage: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_refresh_channel_usage(request: web.Request) -> web.Response:
    """Refresh usage for all accounts in a channel"""
    channel_id = int(request.match_info["id"])
    
    channel = await get_channel_by_id(channel_id)
    if not channel:
        return web.json_response({"error": "Channel not found"}, status=404)
    
    # Get provider
    provider = get_provider(channel.type)
    if not provider:
        return web.json_response({"error": f"Provider {channel.type} not available"}, status=500)
    
    # Check if provider supports usage refresh
    if not provider.supports_usage_refresh():
        return web.json_response({"error": f"Usage refresh not supported for {channel.type} channels"}, status=400)
    
    accounts = await get_accounts_by_channel(channel_id)
    results = {"success": 0, "failed": 0, "accounts": []}
    
    for account in accounts:
        try:
            result = await provider.refresh_usage(account.api_key, account.id)
            if result is None:
                raise Exception("Provider returned None")
            
            used, limit = result
            await update_account(account.id, usage=used, **{"limit": limit})
            results["success"] += 1
            results["accounts"].append({
                "id": account.id,
                "name": account.name,
                "usage": used,
                "limit": limit,
                "success": True
            })
        except Exception as e:
            results["failed"] += 1
            results["accounts"].append({
                "id": account.id,
                "name": account.name,
                "error": str(e),
                "success": False
            })
    
    return web.json_response(results)

async def api_refresh_all_usage(request: web.Request) -> web.Response:
    """Refresh usage for all channels that support it"""
    channels = await get_all_channels()
    
    # Filter channels that support usage refresh
    supported_channels = []
    for channel in channels:
        provider = get_provider(channel.type)
        if provider and provider.supports_usage_refresh():
            supported_channels.append(channel)
    
    if not supported_channels:
        return web.json_response({"error": "No channels support usage refresh"}, status=404)
    
    results = {"channels": [], "total_success": 0, "total_failed": 0}
    
    for channel in supported_channels:
        channel_result = {"id": channel.id, "name": channel.name, "type": channel.type, "success": 0, "failed": 0}
        accounts = await get_accounts_by_channel(channel.id)
        provider = get_provider(channel.type)
        
        for account in accounts:
            try:
                result = await provider.refresh_usage(account.api_key, account.id)
                if result is None:
                    raise Exception("Provider returned None")
                
                used, limit = result
                await update_account(account.id, usage=used, **{"limit": limit})
                channel_result["success"] += 1
                results["total_success"] += 1
            except Exception as e:
                channel_result["failed"] += 1
                results["total_failed"] += 1
                logger.error(f"Failed to refresh account {account.id}: {e}")
        
        results["channels"].append(channel_result)
    
    return web.json_response(results)


# Token API
async def api_list_tokens(request: web.Request) -> web.Response:
    """Get all tokens"""
    from models import get_all_tokens
    user_id = request.query.get("user_id")
    if user_id:
        user_id = int(user_id)
    
    tokens = await get_all_tokens(user_id)
    result = []
    for t in tokens:
        result.append({
            "id": t.id,
            "user_id": t.user_id,
            "key": t.key,
            "name": t.name,
            "status": t.status,
            "created_time": t.created_time,
            "accessed_time": t.accessed_time,
            "expired_time": t.expired_time,
            "model_limits_enabled": t.model_limits_enabled,
            "model_limits": t.model_limits,
            "ip_whitelist": t.ip_whitelist,
            "group": t.group or "default",  # 添加默认值
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "total_tokens": t.total_tokens,
            "request_count": t.request_count,
            "rpm_limit": t.rpm_limit,
            "tpm_limit": t.tpm_limit,
            "cross_group_retry": t.cross_group_retry
        })
    return web.json_response(result)


async def api_create_token(request: web.Request) -> web.Response:
    """Create a new token"""
    from models import create_token
    data = await request.json()
    
    token_id, key = await create_token(
        name=data.get("name", ""),
        expired_time=data.get("expired_time", -1),
        model_limits_enabled=data.get("model_limits_enabled", False),
        model_limits=data.get("model_limits", ""),
        ip_whitelist=data.get("ip_whitelist", ""),
        group=data.get("group", "default"),
        cross_group_retry=data.get("cross_group_retry", False),
        rpm_limit=data.get("rpm_limit", 0),
        tpm_limit=data.get("tpm_limit", 0),
        user_id=data.get("user_id", 0)
    )
    
    return web.json_response({"id": token_id, "key": key})


async def api_update_token(request: web.Request) -> web.Response:
    """Update a token"""
    from models import update_token
    token_id = int(request.match_info["id"])
    data = await request.json()
    
    await update_token(token_id, **data)
    return web.json_response({"success": True})


async def api_delete_token(request: web.Request) -> web.Response:
    """Delete a token"""
    from models import delete_token
    token_id = int(request.match_info["id"])
    await delete_token(token_id)
    return web.json_response({"success": True})


async def api_token_stats(request: web.Request) -> web.Response:
    """Get token usage statistics"""
    from models import get_all_tokens, get_db
    
    days = int(request.query.get("days", 7))
    
    # Get all tokens with stats
    tokens = await get_all_tokens()
    
    # Get detailed usage from logs
    db = await get_db()
    
    # Token usage over time
    async with db.execute(
        """SELECT 
            DATE(created_at) as date,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            COUNT(*) as requests
           FROM logs
           WHERE created_at >= datetime('now', '-' || ? || ' days')
           GROUP BY DATE(created_at)
           ORDER BY date""",
        (days,)
    ) as cursor:
        daily_stats = [dict(row) for row in await cursor.fetchall()]
    
    # Top tokens by usage
    token_usage = []
    for token in tokens:
        token_usage.append({
            "id": token.id,
            "name": token.name,
            "key": token.key[:20] + "...",
            "input_tokens": token.input_tokens,
            "output_tokens": token.output_tokens,
            "total_tokens": token.total_tokens,
            "request_count": token.request_count,
            "used_quota": token.used_quota,
            "remain_quota": token.remain_quota,
            "group": token.group
        })
    
    # Sort by total tokens
    token_usage.sort(key=lambda x: x["total_tokens"], reverse=True)
    
    return web.json_response({
        "daily_stats": daily_stats,
        "top_tokens": token_usage[:10],
        "all_tokens": token_usage
    })


async def api_model_pricing(request: web.Request) -> web.Response:
    """Get model pricing information"""
    from utils.model_pricing import get_all_models, get_model_rate, MODEL_RATES
    
    model = request.query.get("model")
    
    if model:
        # Get specific model rate
        rate = get_model_rate(model)
        return web.json_response({
            "model": model,
            "rate": rate
        })
    else:
        # Get all models
        return web.json_response({
            "models": MODEL_RATES
        })


async def api_health_check_channel(request: web.Request) -> web.Response:
    """Health check a specific channel/provider"""
    from utils.health_checker import health_checker
    
    provider_type = request.match_info["id"]  # Now it's a string like "kiro", "claude", etc.
    result = await health_checker.check_single_provider(provider_type)
    
    return web.json_response(result)


async def api_health_check_all(request: web.Request) -> web.Response:
    """Trigger health check for all channels"""
    from utils.health_checker import health_checker
    
    # Run health check in background
    asyncio.create_task(health_checker.check_all_channels())
    
    return web.json_response({
        "message": "Health check started",
        "status": "running"
    })

# Cache Config API
async def api_get_cache_config(request: web.Request) -> web.Response:
    """Get cache configuration"""
    config = await get_cache_config()
    return web.json_response(config)

async def api_update_cache_config(request: web.Request) -> web.Response:
    """Update cache configuration"""
    data = await request.json()
    await update_cache_config(data)
    return web.json_response({"message": "Cache config updated"})
