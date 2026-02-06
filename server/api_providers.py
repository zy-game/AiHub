"""
New Provider-based API endpoints
Replaces channel-based API with provider auto-discovery
"""
import json
import uuid
import asyncio
import aiohttp
from aiohttp import web
from providers import get_provider, get_all_providers, configure_provider
from models import (
    get_accounts_by_provider, get_all_accounts_with_providers, 
    create_account, batch_create_accounts, update_account, 
    delete_account, delete_accounts_by_provider, get_account_usage_totals
)
from utils.logger import logger

# Provider API
async def api_list_providers(request: web.Request) -> web.Response:
    """List all discovered providers with their configuration and statistics"""
    providers = get_all_providers()
    result = []
    
    for name, provider in providers.items():
        accounts = await get_accounts_by_provider(name)
        totals = await get_account_usage_totals(name)
        
        # Sum tokens from all accounts
        total_tokens = sum(a.total_tokens or 0 for a in accounts)
        
        result.append({
            "id": name,  # Use name as ID for backward compatibility
            "name": name,
            "type": name,
            "priority": provider.priority,
            "weight": provider.weight,
            "enabled": provider.enabled,
            "supported_models": provider.get_supported_models(),
            "supports_usage_refresh": provider.supports_usage_refresh(),
            "account_count": len(accounts),
            "enabled_account_count": sum(1 for a in accounts if a.enabled),
            "usage": totals["used"],
            "limit": totals["limit"],
            "total_tokens": total_tokens,
            "avg_response_time": provider.avg_response_time,
            "total_requests": provider.total_requests,
            "failed_requests": provider.failed_requests,
            "success_rate": provider.get_success_rate()
        })
    
    # Sort by priority (descending) then by name
    result.sort(key=lambda x: (-x["priority"], x["name"]))
    
    return web.json_response(result)

async def api_get_provider(request: web.Request) -> web.Response:
    """Get details for a specific provider"""
    provider_type = request.match_info["type"]
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    accounts = await get_accounts_by_provider(provider_type)
    totals = await get_account_usage_totals(provider_type)
    total_tokens = sum(a.total_tokens or 0 for a in accounts)
    
    return web.json_response({
        "name": provider.name,
        "type": provider.name,
        "priority": provider.priority,
        "weight": provider.weight,
        "enabled": provider.enabled,
        "supported_models": provider.get_supported_models(),
        "supports_usage_refresh": provider.supports_usage_refresh(),
        "account_count": len(accounts),
        "enabled_account_count": sum(1 for a in accounts if a.enabled),
        "usage": totals["used"],
        "limit": totals["limit"],
        "total_tokens": total_tokens,
        "avg_response_time": provider.avg_response_time,
        "total_requests": provider.total_requests,
        "failed_requests": provider.failed_requests,
        "success_rate": provider.get_success_rate()
    })

async def api_update_provider_config(request: web.Request) -> web.Response:
    """Update provider configuration (priority, weight, enabled)"""
    provider_type = request.match_info["type"]
    data = await request.json()
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    # Update configuration
    configure_provider(provider_type, **data)
    
    # TODO: Optionally persist to config file
    
    return web.json_response({"success": True})

async def api_provider_models(request: web.Request) -> web.Response:
    """Get supported models for a provider"""
    provider_type = request.match_info["type"]
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    models = provider.get_supported_models()
    
    return web.json_response({
        "provider_type": provider.name,
        "supported_models": models
    })

# Account API for Providers
async def api_list_provider_accounts(request: web.Request) -> web.Response:
    """List all accounts for a specific provider"""
    provider_type = request.match_info["type"]
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    accounts = await get_accounts_by_provider(provider_type)
    
    return web.json_response([{
        "id": a.id,
        "provider_type": a.provider_type,
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

async def api_create_provider_account(request: web.Request) -> web.Response:
    """Create an account for a provider"""
    provider_type = request.match_info["type"]
    data = await request.json()
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    id_ = await create_account(
        provider_type=provider_type,
        api_key=data["api_key"],
        name=data.get("name", "")
    )
    return web.json_response({"id": id_, "success": True})

async def api_batch_import_provider_accounts(request: web.Request) -> web.Response:
    """Batch import accounts for a provider"""
    provider_type = request.match_info["type"]
    content_type = request.content_type
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    accounts = []
    
    if "json" in content_type:
        data = await request.json()
        if isinstance(data, list):
            raw_accounts = data
        else:
            raw_accounts = data.get("accounts", [])
        
        for acc in raw_accounts:
            if provider_type == "kiro":
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
                    if provider_type == "kiro" and "refreshToken" in acc:
                        accounts.append({
                            "api_key": json.dumps(acc),
                            "name": acc.get("clientId", "")[:20] if acc.get("clientId") else ""
                        })
                    elif "api_key" in acc:
                        accounts.append(acc)
        except json.JSONDecodeError:
            # Plain text, one api_key per line
            accounts = [{"api_key": line.strip()} for line in text.split("\n") if line.strip()]
    
    count = await batch_create_accounts(provider_type, accounts)
    return web.json_response({"imported": count, "success": True})

async def api_clear_provider_accounts(request: web.Request) -> web.Response:
    """Clear all accounts for a provider"""
    provider_type = request.match_info["type"]
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    count = await delete_accounts_by_provider(provider_type)
    return web.json_response({"deleted": count, "success": True})

# Usage Refresh API
async def api_refresh_provider_usage(request: web.Request) -> web.Response:
    """Refresh usage for all accounts in a provider"""
    provider_type = request.match_info["type"]
    
    provider = get_provider(provider_type)
    if not provider:
        return web.json_response({"error": "Provider not found"}, status=404)
    
    # Check if provider supports usage refresh
    if not provider.supports_usage_refresh():
        return web.json_response(
            {"error": f"Usage refresh not supported for {provider_type} provider"}, 
            status=400
        )
    
    accounts = await get_accounts_by_provider(provider_type)
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

async def api_refresh_all_providers_usage(request: web.Request) -> web.Response:
    """Refresh usage for all providers that support it"""
    providers = get_all_providers()
    
    # Filter providers that support usage refresh
    supported_providers = {
        name: provider for name, provider in providers.items()
        if provider.supports_usage_refresh()
    }
    
    if not supported_providers:
        return web.json_response({"error": "No providers support usage refresh"}, status=404)
    
    results = {"providers": [], "total_success": 0, "total_failed": 0}
    
    for name, provider in supported_providers.items():
        provider_result = {
            "name": name, 
            "type": name, 
            "success": 0, 
            "failed": 0
        }
        accounts = await get_accounts_by_provider(name)
        
        for account in accounts:
            try:
                result = await provider.refresh_usage(account.api_key, account.id)
                if result is None:
                    raise Exception("Provider returned None")
                
                used, limit = result
                await update_account(account.id, usage=used, **{"limit": limit})
                provider_result["success"] += 1
                results["total_success"] += 1
            except Exception as e:
                provider_result["failed"] += 1
                results["total_failed"] += 1
                logger.error(f"Failed to refresh account {account.id}: {e}")
        
        results["providers"].append(provider_result)
    
    return web.json_response(results)

# Kiro OAuth API (unchanged, but uses provider_type)
KIRO_SSO_OIDC_URL = "https://oidc.us-east-1.amazonaws.com"
KIRO_BUILDER_ID_START_URL = "https://view.awsapps.com/start"

async def api_kiro_device_auth(request: web.Request) -> web.Response:
    """Start Kiro device authorization flow with Builder ID"""
    try:
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
            
            # Start device authorization
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
    provider_type = req_data.get("provider_type", "kiro")
    
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
                if "accessToken" in data:
                    account_data = {
                        "accessToken": data.get("accessToken"),
                        "refreshToken": data.get("refreshToken"),
                        "clientId": client_id,
                        "clientSecret": client_secret,
                        "region": "us-east-1",
                        "expiresAt": data.get("expiresIn")
                    }
                    
                    # Import the account
                    count = await batch_create_accounts(provider_type, [{
                        "api_key": json.dumps(account_data),
                        "name": f"BuilderID-{str(uuid.uuid4())[:8]}"
                    }])
                    
                    return web.json_response({"success": True, "imported": count})
                
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
