import os
from aiohttp import web
from models.database import get_db, close_db
from models.init_admin import init_auth_system
from server.middleware import auth_middleware, error_middleware, cors_middleware
from server.routes import (
    handle_chat_completions, handle_messages, handle_responses,
    handle_gemini, handle_models
)
# Import new provider-based API
from server.api_providers import (
    api_list_providers, api_get_provider, api_update_provider_config, api_provider_models,
    api_list_provider_accounts, api_create_provider_account, api_batch_import_provider_accounts, api_clear_provider_accounts,
    api_refresh_provider_usage, api_refresh_all_providers_usage,
    api_kiro_device_auth, api_kiro_device_token
)
# Import authentication API
from server.api_auth import (
    api_register, api_verify_email, api_login, api_logout,
    api_current_user, api_change_password, api_user_tokens,
    api_create_invite_code, api_list_invite_codes
)
# Import legacy APIs (users, tokens, logs, stats)
from server.api import (
    api_list_all_accounts, api_update_account, api_delete_account,
    api_list_users, api_create_user, api_update_user, api_delete_user,
    api_list_tokens, api_create_token, api_update_token, api_delete_token, api_token_stats, api_model_pricing,
    api_list_logs, api_get_stats,
    api_refresh_account_usage,
    api_health_check_all
)
from server.api_risk_control import (
    api_risk_control_status, api_proxy_pool_stats, api_add_proxy, api_proxy_health_check,
    api_rate_limit_stats, api_health_monitor_stats, api_account_health_detail,
    api_account_manual_degrade, api_account_manual_ban, api_account_recover
)
from server.tasks import start_background_tasks
from utils.logger import logger
from config import HOST, PORT

async def on_startup(app: web.Application):
    await get_db()
    logger.info("Database connected")
    await init_auth_system()  # Initialize super admin and invite code
    logger.info("Authentication system initialized")
    
    # Initialize risk control system
    from utils.risk_control import init_risk_control
    try:
        await init_risk_control()
        logger.info("Risk control system initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize risk control system: {e}")
    
    await start_background_tasks()
    logger.info("Background tasks started")

async def on_cleanup(app: web.Application):
    # Shutdown risk control system
    from utils.risk_control import get_risk_control_system
    try:
        system = get_risk_control_system()
        await system.shutdown()
    except Exception as e:
        logger.warning(f"Error shutting down risk control system: {e}")
    
    await close_db()
    logger.info("Database closed")

def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware, error_middleware, auth_middleware])
    
    # Lifecycle
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    # Authentication routes (public)
    app.router.add_get("/login", lambda r: web.FileResponse("static/login.html"))
    app.router.add_get("/register", lambda r: web.FileResponse("static/register.html"))
    app.router.add_get("/verify-email", lambda r: web.FileResponse("static/verify-email.html"))
    app.router.add_post("/api/auth/register", api_register)
    app.router.add_get("/api/auth/verify-email", api_verify_email)
    app.router.add_post("/api/auth/login", api_login)
    app.router.add_post("/api/auth/logout", api_logout)
    app.router.add_get("/api/auth/me", api_current_user)
    app.router.add_post("/api/auth/change-password", api_change_password)
    app.router.add_get("/api/auth/tokens", api_user_tokens)
    app.router.add_post("/api/auth/invite-codes", api_create_invite_code)
    app.router.add_get("/api/auth/invite-codes", api_list_invite_codes)
    
    # API routes (relay)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_post("/v1/responses", handle_responses)
    app.router.add_post("/v1beta/models/{model}:generateContent", handle_gemini)
    app.router.add_post("/v1beta/models/{model}:streamGenerateContent", handle_gemini)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/v1/models/{model}", handle_models)
    
    # Admin API routes - Providers (NEW)
    app.router.add_get("/api/providers", api_list_providers)
    app.router.add_get("/api/providers/{type}", api_get_provider)
    app.router.add_put("/api/providers/{type}/config", api_update_provider_config)
    app.router.add_get("/api/providers/{type}/models", api_provider_models)
    
    # Admin API routes - Accounts (per provider) (NEW)
    app.router.add_get("/api/providers/{type}/accounts", api_list_provider_accounts)
    app.router.add_post("/api/providers/{type}/accounts", api_create_provider_account)
    app.router.add_post("/api/providers/{type}/accounts/import", api_batch_import_provider_accounts)
    app.router.add_delete("/api/providers/{type}/accounts", api_clear_provider_accounts)
    
    # Backward compatibility - map old /api/channels to /api/providers
    app.router.add_get("/api/channels", api_list_providers)  # Same as providers
    app.router.add_get("/api/channels/{type}/models", api_provider_models)
    app.router.add_get("/api/channels/{type}/accounts", api_list_provider_accounts)
    app.router.add_post("/api/channels/{type}/accounts", api_create_provider_account)
    app.router.add_post("/api/channels/{type}/accounts/import", api_batch_import_provider_accounts)
    app.router.add_delete("/api/channels/{type}/accounts", api_clear_provider_accounts)
    app.router.add_put("/api/channels/{type}", api_update_provider_config)  # Map to config update
    app.router.add_post("/api/channels/{type}/refresh-usage", api_refresh_provider_usage)
    
    # Admin API routes - Accounts (global)
    app.router.add_get("/api/accounts", api_list_all_accounts)
    app.router.add_put("/api/accounts/{id}", api_update_account)
    app.router.add_delete("/api/accounts/{id}", api_delete_account)
    
    # Admin API routes - Users
    app.router.add_get("/api/users", api_list_users)
    app.router.add_post("/api/users", api_create_user)
    app.router.add_put("/api/users/{id}", api_update_user)
    app.router.add_delete("/api/users/{id}", api_delete_user)
    
    # Admin API routes - Tokens
    app.router.add_get("/api/tokens", api_list_tokens)
    app.router.add_post("/api/tokens", api_create_token)
    app.router.add_put("/api/tokens/{id}", api_update_token)
    app.router.add_delete("/api/tokens/{id}", api_delete_token)
    app.router.add_get("/api/tokens/stats", api_token_stats)
    
    # Model pricing
    app.router.add_get("/api/models/pricing", api_model_pricing)
    
    app.router.add_get("/api/logs", api_list_logs)
    app.router.add_get("/api/stats", api_get_stats)
    
    # Kiro OAuth routes (NEW - provider-based)
    app.router.add_post("/api/kiro/device-auth", api_kiro_device_auth)
    app.router.add_post("/api/kiro/device-token", api_kiro_device_token)
    
    # Usage refresh routes (NEW - provider-based)
    app.router.add_post("/api/accounts/{id}/refresh-usage", api_refresh_account_usage)
    app.router.add_post("/api/providers/{type}/refresh-usage", api_refresh_provider_usage)
    app.router.add_post("/api/refresh-all-usage", api_refresh_all_providers_usage)
    
    # Health check routes
    app.router.add_post("/api/health-check-all", api_health_check_all)
    
    # Risk Control API routes (NEW)
    app.router.add_get("/api/risk-control/status", api_risk_control_status)
    app.router.add_get("/api/risk-control/proxy-pool/stats", api_proxy_pool_stats)
    app.router.add_post("/api/risk-control/proxy-pool/add", api_add_proxy)
    app.router.add_post("/api/risk-control/proxy-pool/health-check", api_proxy_health_check)
    app.router.add_get("/api/risk-control/rate-limit/stats", api_rate_limit_stats)
    app.router.add_get("/api/risk-control/health-monitor/stats", api_health_monitor_stats)
    app.router.add_get("/api/risk-control/accounts/{id}/health", api_account_health_detail)
    app.router.add_post("/api/risk-control/accounts/{id}/degrade", api_account_manual_degrade)
    app.router.add_post("/api/risk-control/accounts/{id}/ban", api_account_manual_ban)
    app.router.add_post("/api/risk-control/accounts/{id}/recover", api_account_recover)
    
    # Static files path (must be defined before use)
    static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    
    # Risk Control Management Page (super_admin only)
    app.router.add_get("/risk-control", lambda r: web.FileResponse(os.path.join(static_path, "risk-control.html")))
    
    # Static files
    app.router.add_static("/static", static_path)
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(static_path, "index.html")))
    
    return app

def run():
    app = create_app()
    logger.info(f"Starting AiHub server on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)
