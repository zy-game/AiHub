"""Background tasks for AiHub"""
import asyncio
from utils.logger import logger
from models import check_and_update_token_status
from utils.health_checker import health_checker


async def token_cleanup_task():
    """Periodically check and update expired/exhausted tokens"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            logger.info("Running token cleanup task...")
            await check_and_update_token_status()
            logger.info("Token cleanup task completed")
        except Exception as e:
            logger.error(f"Token cleanup task error: {e}")


async def rate_limiter_cleanup_task():
    """Periodically cleanup rate limiter old records"""
    while True:
        try:
            await asyncio.sleep(60)  # Run every 1 minute
            # Rate limiter cleanup is handled internally by the risk control system
            # This task is kept for backward compatibility
        except Exception as e:
            logger.error(f"Rate limiter cleanup task error: {e}")


async def health_check_task():
    """Periodically check health of all channels and accounts"""
    await health_checker.start()


async def start_background_tasks():
    """Start all background tasks"""
    logger.info("Starting background tasks...")
    asyncio.create_task(token_cleanup_task())
    asyncio.create_task(rate_limiter_cleanup_task())
    asyncio.create_task(health_check_task())
