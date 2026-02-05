"""Background tasks for AiHub"""
import asyncio
from utils.logger import logger
from models import check_and_update_token_status


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


async def start_background_tasks():
    """Start all background tasks"""
    logger.info("Starting background tasks...")
    asyncio.create_task(token_cleanup_task())
