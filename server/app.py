import os
from aiohttp import web
from models.database import get_db, close_db
from server.middleware import auth_middleware, error_middleware, cors_middleware
from server.routes import (
    handle_chat_completions, handle_messages, handle_responses,
    handle_gemini, handle_models
)
from server.api import (
    api_list_channels, api_create_channel, api_update_channel, api_delete_channel,
    api_list_all_accounts, api_list_accounts, api_create_account, api_batch_import_accounts, api_update_account, api_delete_account, api_clear_accounts,
    api_list_users, api_create_user, api_update_user, api_delete_user,
    api_list_logs, api_get_stats,
    api_kiro_device_auth, api_kiro_device_token,
    api_refresh_account_usage, api_refresh_channel_usage, api_refresh_all_usage
)
from utils.logger import logger
from config import HOST, PORT

async def on_startup(app: web.Application):
    await get_db()
    logger.info("Database connected")

async def on_cleanup(app: web.Application):
    await close_db()
    logger.info("Database closed")

def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware, error_middleware, auth_middleware])
    
    # Lifecycle
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    # API routes (relay)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_post("/v1/responses", handle_responses)
    app.router.add_post("/v1beta/models/{model}:generateContent", handle_gemini)
    app.router.add_post("/v1beta/models/{model}:streamGenerateContent", handle_gemini)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/v1/models/{model}", handle_models)
    
    # Admin API routes - Channels
    app.router.add_get("/api/channels", api_list_channels)
    app.router.add_post("/api/channels", api_create_channel)
    app.router.add_put("/api/channels/{id}", api_update_channel)
    app.router.add_delete("/api/channels/{id}", api_delete_channel)
    
    # Admin API routes - Accounts (per channel)
    app.router.add_get("/api/accounts", api_list_all_accounts)
    app.router.add_get("/api/channels/{channel_id}/accounts", api_list_accounts)
    app.router.add_post("/api/channels/{channel_id}/accounts", api_create_account)
    app.router.add_post("/api/channels/{channel_id}/accounts/import", api_batch_import_accounts)
    app.router.add_delete("/api/channels/{channel_id}/accounts", api_clear_accounts)
    app.router.add_put("/api/accounts/{id}", api_update_account)
    app.router.add_delete("/api/accounts/{id}", api_delete_account)
    
    # Admin API routes - Users
    app.router.add_get("/api/users", api_list_users)
    app.router.add_post("/api/users", api_create_user)
    app.router.add_put("/api/users/{id}", api_update_user)
    app.router.add_delete("/api/users/{id}", api_delete_user)
    
    app.router.add_get("/api/logs", api_list_logs)
    app.router.add_get("/api/stats", api_get_stats)
    
    # Kiro OAuth routes
    app.router.add_post("/api/kiro/device-auth", api_kiro_device_auth)
    app.router.add_post("/api/kiro/device-token", api_kiro_device_token)
    
    # Usage refresh routes
    app.router.add_post("/api/accounts/{id}/refresh-usage", api_refresh_account_usage)
    app.router.add_post("/api/channels/{id}/refresh-usage", api_refresh_channel_usage)
    app.router.add_post("/api/refresh-all-usage", api_refresh_all_usage)
    
    # Static files
    static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    app.router.add_static("/static", static_path)
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(static_path, "index.html")))
    
    return app

def run():
    app = create_app()
    logger.info(f"Starting AiHub server on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)
