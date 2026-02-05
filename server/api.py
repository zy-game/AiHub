import json
import uuid
import aiohttp
from datetime import datetime, timezone, timedelta
from aiohttp import web
from models import (
    get_all_channels, get_channel_by_id, create_channel, update_channel, delete_channel,
    get_accounts_by_channel, get_all_accounts_with_channels, create_account, batch_create_accounts, update_account, delete_account, delete_accounts_by_channel, get_account_usage_totals,
    get_all_users, create_user, update_user, delete_user,
    get_logs, get_stats, get_model_stats, get_channel_token_usage, get_user_token_usage, get_hourly_stats, get_channel_stats, get_top_users
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
        result.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "models": c.models,
            "model_mapping": c.model_mapping,
            "priority": c.priority,
            "weight": c.weight,
            "enabled": c.enabled,
            "account_count": len(accounts),
            "enabled_account_count": sum(1 for a in accounts if a.enabled),
            "usage": totals["used"],
            "limit": totals["limit"],
            "total_tokens": total_tokens
        })
    return web.json_response(result)

async def api_create_channel(request: web.Request) -> web.Response:
    data = await request.json()
    id_ = await create_channel(
        name=data["name"],
        type_=data["type"],
        models=data["models"],
        model_mapping=data.get("model_mapping", {}),
        priority=data.get("priority", 0),
        weight=data.get("weight", 1)
    )
    return web.json_response({"id": id_, "success": True})

async def api_update_channel(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    data = await request.json()
    await update_channel(id_, **data)
    return web.json_response({"success": True})

async def api_delete_channel(request: web.Request) -> web.Response:
    id_ = int(request.match_info["id"])
    await delete_accounts_by_channel(id_)
    await delete_channel(id_)
    return web.json_response({"success": True})

# Account API
async def api_list_all_accounts(request: web.Request) -> web.Response:
    accounts = await get_all_accounts_with_channels()
    result = []
    for row in accounts:
        result.append({
            "id": row["id"],
            "channel_id": row["channel_id"],
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
            "enabled": row.get("enabled", 1)
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
    stats = await get_stats(days)
    model_stats = await get_model_stats(days)
    hourly_stats = await get_hourly_stats(days)
    channel_stats = await get_channel_stats()
    top_users = await get_top_users(10)
    
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
    
    channel_type = account.get("channel_type")
    if channel_type != "kiro":
        return web.json_response({"error": "Usage refresh only supported for kiro channels"}, status=400)
    
    provider = get_provider("kiro")
    if not provider:
        return web.json_response({"error": "Kiro provider not available"}, status=500)
    
    try:
        usage_data = await provider.get_usage_limits(account["api_key"], account_id)
        used, limit = provider.extract_kiro_points(usage_data)
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
    
    if channel.type != "kiro":
        return web.json_response({"error": "Usage refresh only supported for kiro channels"}, status=400)
    
    provider = get_provider("kiro")
    if not provider:
        return web.json_response({"error": "Kiro provider not available"}, status=500)
    
    accounts = await get_accounts_by_channel(channel_id)
    results = {"success": 0, "failed": 0, "accounts": []}
    
    for account in accounts:
        try:
            usage_data = await provider.get_usage_limits(account.api_key, account.id)
            used, limit = provider.extract_kiro_points(usage_data)
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
    """Refresh usage for all kiro channels"""
    channels = await get_all_channels()
    kiro_channels = [c for c in channels if c.type == "kiro"]
    
    if not kiro_channels:
        return web.json_response({"error": "No kiro channels found"}, status=404)
    
    provider = get_provider("kiro")
    if not provider:
        return web.json_response({"error": "Kiro provider not available"}, status=500)
    
    results = {"channels": [], "total_success": 0, "total_failed": 0}
    
    for channel in kiro_channels:
        channel_result = {"id": channel.id, "name": channel.name, "success": 0, "failed": 0}
        accounts = await get_accounts_by_channel(channel.id)
        
        for account in accounts:
            try:
                usage_data = await provider.get_usage_limits(account.api_key, account.id)
                used, limit = provider.extract_kiro_points(usage_data)
                await update_account(account.id, usage=used, **{"limit": limit})
                channel_result["success"] += 1
                results["total_success"] += 1
            except Exception as e:
                channel_result["failed"] += 1
                results["total_failed"] += 1
                logger.error(f"Failed to refresh account {account.id}: {e}")
        
        results["channels"].append(channel_result)
    
    return web.json_response(results)
