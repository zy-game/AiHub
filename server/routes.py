import json
import time
import asyncio
from aiohttp import web
from server.distributor import distribute, RequestContext
from providers import get_provider, get_all_providers
from models import create_log, update_user_quota, get_available_account, add_user_tokens, add_account_tokens, add_token_usage, get_user_by_id
from utils.logger import logger, get_provider_logger
from utils.text import get_content_text
from utils.token_counter import count_tokens
from utils.model_pricing import calculate_cost

async def handle_chat_completions(request: web.Request) -> web.Response:
    """Handle OpenAI /v1/chat/completions"""
    return await _handle_relay(request, "openai")

async def handle_messages(request: web.Request) -> web.Response:
    """Handle Claude /v1/messages"""
    return await _handle_relay(request, "claude")

async def handle_responses(request: web.Request) -> web.Response:
    """Handle OpenAI /v1/responses"""
    return await _handle_relay(request, "openai_responses")

async def handle_gemini(request: web.Request) -> web.Response:
    """Handle Gemini /v1beta/models/*"""
    return await _handle_relay(request, "gemini")

async def _handle_relay(request: web.Request, input_format: str) -> web.Response:
    ctx = RequestContext()
    ctx.start_time = time.time()
    ctx.user = request.get("user")
    ctx.token = request.get("token")
    
    try:
        provider = await distribute(request, ctx)
    except web.HTTPException as e:
        return e
    
    # Check model access for token-based auth
    if ctx.token and ctx.token.model_limits_enabled:
        if not ctx.token.has_model_access(ctx.model):
            return web.json_response(
                {"error": {"message": f"Token does not have access to model: {ctx.model}", "type": "permission_error"}},
                status=403
            )
    
    if not provider:
        return web.json_response(
            {"error": {"message": f"Unknown provider type: {ctx.provider_type}"}},
            status=500
        )
    
    # Get mapped model name from provider
    mapped_model = provider.get_mapped_model(ctx.model)
    
    # Retry logic with cross-group support
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Get available account from provider's pool
            account = await get_available_account(ctx.provider_type)
            
            # If no account and cross-group retry is enabled
            if not account and ctx.token and ctx.token.cross_group_retry and attempt > 0:
                logger.warning(f"No account in provider {ctx.provider_type}, trying cross-group retry...")
                # Try to find another provider with different group
                all_providers = get_all_providers()
                for alt_name, alt_provider in all_providers.items():
                    if alt_name != ctx.provider_type and alt_provider.enabled and alt_provider.supports_model(ctx.model):
                        alt_account = await get_available_account(alt_name)
                        if alt_account:
                            provider = alt_provider
                            ctx.provider = alt_provider
                            ctx.provider_type = alt_name
                            mapped_model = provider.get_mapped_model(ctx.model)
                            account = alt_account
                            logger.warning(f"Cross-group retry: switched to provider {alt_name}")
                            break
            
            if not account:
                if attempt < max_retries - 1:
                    last_error = "No available account"
                    await asyncio.sleep(1)  # Wait before retry
                    continue
                return web.json_response(
                    {"error": {"message": f"No available account for provider: {ctx.provider_type}", "type": "no_account"}},
                    status=503
                )
            
            if ctx.provider_type == "kiro":
                ctx.body["_account_id"] = account.id

            return await _handle_response(
                request, ctx, provider, account,
                mapped_model, ctx.body
            )
            
        except Exception as e:
            last_error = str(e)
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Wait before retry
                continue
            # Last attempt failed
            logger.exception(f"All retries failed: {e}")
            duration_ms = int((time.time() - ctx.start_time) * 1000)
            
            user_id = 0
            if ctx.token:
                user_id = ctx.token.user_id
            elif ctx.user:
                user_id = ctx.user.id
            
            await create_log(
                user_id=user_id,
                channel_id=0,  # No channel_id in new system
                model=ctx.model,
                duration_ms=duration_ms,
                status=500,
                error=str(e)
            )
            
            # Update provider statistics (failed request)
            provider.update_stats(duration_ms, success=False)
            
            return web.json_response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=502
            )

async def _handle_response(request, ctx, provider, account, mapped_model, request_data):
    """Handle both streaming and non-streaming responses"""
    is_stream = request_data.get("stream", True)
    if is_stream:
        # Streaming response
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(request)
    else:
        # Will collect complete response
        response = None
        complete_data = b""
    
    # Estimate input tokens from request
    input_tokens = 0
    try:
        messages = ctx.body.get("messages", [])
        for msg in messages:
            content = get_content_text(msg)
            if content and isinstance(content, str):
                tokens = count_tokens(content, ctx.model)
                input_tokens += tokens
        # Add system message if present
        system = ctx.body.get("system", "")
        if system and isinstance(system, str):
            system_tokens = count_tokens(system, ctx.model)
            input_tokens += system_tokens
    except Exception as e:
        logger.error(f"Error estimating input tokens: {e}")
        input_tokens = 0
    
    total_tokens = 0
    
    try:
        async for chunk in provider.chat(
            account.api_key, mapped_model, request_data
        ):
            if is_stream:
                # Streaming mode: write chunks directly
                transport = request.transport
                if transport is None or transport.is_closing():
                    break
                
                try:
                    chunk_bytes = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
                    await response.write(chunk_bytes)
                    total_tokens += 1  # Rough estimate
                except Exception as write_err:
                    logger.error(f"Failed to write chunk: {write_err}")
                    break
            else:
                # Non-streaming mode: collect all data
                complete_data += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        
        if not is_stream:
            # Parse complete JSON to extract token count
            try:
                response_json = json.loads(complete_data.decode("utf-8"))
                usage = response_json.get("usage", {})
                total_tokens = usage.get("completion_tokens", 0)
                if usage.get("prompt_tokens"):
                    input_tokens = usage["prompt_tokens"]
            except:
                pass
            
            # Return complete JSON response
            return web.Response(
                body=complete_data,
                status=200,
                content_type="application/json"
            )
    except Exception as e:
        logger.error(f"Response error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        if not is_stream:
            duration_ms = int((time.time() - ctx.start_time) * 1000)
            user_id = 0
            if ctx.token:
                user_id = ctx.token.user_id
            elif ctx.user:
                user_id = ctx.user.id
            
            await create_log(
                user_id=user_id,
                channel_id=0,
                model=ctx.model,
                duration_ms=duration_ms,
                status=500,
                error=str(e)
            )
            provider.update_stats(duration_ms, success=False)
            
            return web.json_response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=502
            )
    finally:
        if is_stream:
            duration_ms = int((time.time() - ctx.start_time) * 1000)
            
            # Determine user_id for logging
            user_id = 0
            if ctx.token:
                user_id = ctx.token.user_id
            elif ctx.user:
                user_id = ctx.user.id
            
            await create_log(
                user_id=user_id,
                channel_id=0,  # No channel_id in new system
                model=ctx.model,
                input_tokens=input_tokens,
                output_tokens=total_tokens,
                duration_ms=duration_ms,
                status=200
            )
            
            # Update provider statistics
            provider.update_stats(duration_ms, success=True)
            
            # Update token statistics
            if input_tokens > 0 or total_tokens > 0:
                # Calculate cost based on model pricing
                cost_info = calculate_cost(ctx.model, input_tokens, total_tokens)
                quota_usage = cost_info["quota_usage"]
                
                # Update token usage statistics
                if ctx.token:
                    await add_token_usage(ctx.token.id, input_tokens, total_tokens)
                    # Get token owner and update their quota and token statistics
                    token_owner = await get_user_by_id(ctx.token.user_id)
                    if token_owner:
                        # Update user's token statistics
                        await add_user_tokens(token_owner.id, input_tokens, total_tokens)
                        # Update user quota with calculated usage
                        if token_owner.quota != -1:
                            await update_user_quota(token_owner.id, quota_usage)
                
                # Update user tokens (legacy system - direct API key auth)
                if ctx.user:
                    await add_user_tokens(ctx.user.id, input_tokens, total_tokens)
                    # Update user quota with calculated usage
                    if ctx.user.quota != -1:
                        await update_user_quota(ctx.user.id, quota_usage)
                
                # Update account tokens
                await add_account_tokens(account.id, input_tokens, total_tokens)
            
            try:
                await response.write_eof()
            except Exception:
                pass
    
    return response

async def handle_models(request: web.Request) -> web.Response:
    """Handle /v1/models - list all models from all enabled providers"""
    providers = get_all_providers()
    models = set()
    
    for provider in providers.values():
        if provider.enabled:
            models.update(provider.get_supported_models())
    
    # Determine response format based on headers
    if request.headers.get("anthropic-version"):
        return web.json_response({
            "data": [{"id": m, "display_name": m} for m in sorted(models)]
        })
    else:
        return web.json_response({
            "object": "list",
            "data": [{"id": m, "object": "model", "owned_by": "aihub"} for m in sorted(models)]
        })
