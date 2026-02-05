import json
import time
import asyncio
from aiohttp import web
from server.distributor import distribute, RequestContext
from converters import get_converter
from providers import get_provider
from models import create_log, update_user_quota, get_all_channels, get_available_account, add_user_tokens, add_account_tokens, update_token_quota, add_token_usage
from utils.logger import logger
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
        channel = await distribute(request, ctx)
    except web.HTTPException as e:
        return e
    
    # Check model access for token-based auth
    if ctx.token and ctx.token.model_limits_enabled:
        if not ctx.token.has_model_access(ctx.model):
            return web.json_response(
                {"error": {"message": f"Token does not have access to model: {ctx.model}", "type": "permission_error"}},
                status=403
            )
    
    # Get converter and provider
    input_converter = get_converter(input_format if input_format != "openai_responses" else "openai")
    provider = get_provider(channel.type)
    
    if not provider:
        return web.json_response(
            {"error": {"message": f"Unknown provider type: {channel.type}"}},
            status=500
        )
    
    # Convert request to provider format
    target_format = provider.get_format()
    converted_request = input_converter.convert_request(ctx.body, target_format)
    
    # Get mapped model name
    mapped_model = channel.get_mapped_model(ctx.model)
    
    # Retry logic with cross-group support
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Get available account from channel's pool
            account = await get_available_account(channel.id)
            
            # If no account and cross-group retry is enabled
            if not account and ctx.token and ctx.token.cross_group_retry and attempt > 0:
                logger.warning(f"No account in channel {channel.name}, trying cross-group retry...")
                # Try to find another channel with different group
                channels = await get_all_channels()
                for alt_channel in channels:
                    if alt_channel.id != channel.id and alt_channel.enabled and ctx.model in alt_channel.models:
                        alt_account = await get_available_account(alt_channel.id)
                        if alt_account:
                            channel = alt_channel
                            account = alt_account
                            mapped_model = channel.get_mapped_model(ctx.model)
                            provider = get_provider(channel.type)
                            target_format = provider.get_format()
                            converted_request = input_converter.convert_request(ctx.body, target_format)
                            logger.warning(f"Cross-group retry: switched to channel {channel.name}")
                            break
            
            if not account:
                if attempt < max_retries - 1:
                    last_error = "No available account"
                    await asyncio.sleep(1)  # Wait before retry
                    continue
                return web.json_response(
                    {"error": {"message": f"No available account for channel: {channel.name}", "type": "no_account"}},
                    status=503
                )
            
            if channel.type == "kiro":
                converted_request["_account_id"] = account.id

            return await _handle_stream(
                request, ctx, channel, account, provider, input_converter,
                mapped_model, converted_request, target_format, input_format
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
                channel_id=channel.id,
                model=ctx.model,
                duration_ms=duration_ms,
                status=500,
                error=str(e)
            )
            return web.json_response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=502
            )

async def _handle_stream(request, ctx, channel, account, provider, input_converter,
                          mapped_model, converted_request, target_format, input_format):
    output_converter = get_converter(input_format if input_format != "openai_responses" else "openai")
    
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
    await response.prepare(request)
    
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
            account.api_key, mapped_model,
            converted_request
        ):
            transport = request.transport
            if transport is None or transport.is_closing():
                break
            if isinstance(chunk, bytes):
                chunk_str = chunk.decode("utf-8")
            else:
                chunk_str = chunk
            
            # For Kiro provider, forward raw Claude SSE only when client expects Claude
            if channel.type == "kiro" and input_format == "claude":
                try:
                    await response.write(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
                    total_tokens += 1
                except Exception:
                    break
            else:
                for line in chunk_str.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    
                    converted = output_converter.convert_stream_chunk(line, target_format)
                    if converted:
                        try:
                            await response.write(converted.encode("utf-8"))
                            total_tokens += 1  # Rough estimate
                        except Exception:
                            break
        
        # Send final done marker if needed
        if input_format in ["openai", "openai_responses"]:
            await response.write(b"data: [DONE]\n\n")
    except Exception as e:
        logger.error(f"Stream error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        duration_ms = int((time.time() - ctx.start_time) * 1000)
        
        # Determine user_id for logging
        user_id = 0
        if ctx.token:
            user_id = ctx.token.user_id
        elif ctx.user:
            user_id = ctx.user.id
        
        await create_log(
            user_id=user_id,
            channel_id=channel.id,
            model=ctx.model,
            input_tokens=input_tokens,
            output_tokens=total_tokens,
            duration_ms=duration_ms,
            status=200
        )
        
        # Update token statistics
        if input_tokens > 0 or total_tokens > 0:
            # Calculate cost based on model pricing
            cost_info = calculate_cost(ctx.model, input_tokens, total_tokens)
            quota_usage = cost_info["quota_usage"]
            
            # Update token usage (new system)
            if ctx.token:
                await add_token_usage(ctx.token.id, input_tokens, total_tokens)
                # Update quota if not unlimited (use calculated quota_usage)
                if not ctx.token.unlimited_quota:
                    await update_token_quota(ctx.token.id, quota_usage)
            
            # Update user tokens (legacy system)
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
    """Handle /v1/models"""
    channels = await get_all_channels()
    models = set()
    
    for channel in channels:
        if channel.enabled:
            models.update(channel.models)
    
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
