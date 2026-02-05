"""Health check system for channels and accounts"""
import asyncio
import time
from typing import Optional
from models import get_all_channels, get_accounts_by_channel, update_channel, update_account
from providers import get_provider
from utils.logger import logger


class HealthChecker:
    """Health checker for channels and accounts"""
    
    def __init__(self):
        self.check_interval = 300  # 5 minutes
        self.timeout = 10  # 10 seconds
        self.running = False
    
    async def start(self):
        """Start health check loop"""
        self.running = True
        logger.info("Health checker started")
        
        while self.running:
            try:
                await self.check_all_channels()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def stop(self):
        """Stop health check loop"""
        self.running = False
        logger.info("Health checker stopped")
    
    async def check_all_channels(self):
        """Check health of all channels"""
        channels = await get_all_channels()
        
        for channel in channels:
            if not channel.enabled:
                continue
            
            try:
                await self.check_channel(channel)
            except Exception as e:
                logger.error(f"Error checking channel {channel.name}: {e}")
    
    async def check_channel(self, channel):
        """Check health of a specific channel"""
        logger.info(f"Checking channel: {channel.name} (ID: {channel.id})")
        
        # Get accounts for this channel
        from models import get_accounts_by_channel
        accounts = await get_accounts_by_channel(channel.id)
        
        if not accounts:
            logger.warning(f"Channel {channel.name} has no accounts")
            return
        
        # Check each account
        healthy_count = 0
        for account in accounts:
            if not account.enabled:
                continue
            
            is_healthy = await self.check_account(channel, account)
            if is_healthy:
                healthy_count += 1
        
        logger.info(f"Channel {channel.name}: {healthy_count}/{len(accounts)} accounts healthy")
        
        # Auto-disable channel if no healthy accounts
        if healthy_count == 0 and channel.enabled:
            logger.warning(f"Auto-disabling channel {channel.name} (no healthy accounts)")
            await update_channel(channel.id, enabled=0)
    
    async def check_account(self, channel, account) -> bool:
        """
        Check health of a specific account
        
        Returns:
            True if healthy, False otherwise
        """
        provider = get_provider(channel.type)
        if not provider:
            logger.error(f"Unknown provider type: {channel.type}")
            return False
        
        # Get a test model for this channel
        test_model = channel.models[0] if channel.models else None
        if not test_model:
            logger.warning(f"Channel {channel.name} has no models configured")
            return False
        
        # Apply model mapping
        mapped_model = channel.get_mapped_model(test_model)
        
        # Prepare test request
        test_request = {
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "stream": False
        }
        
        try:
            # Test the account with timeout
            start_time = time.time()
            
            # For streaming providers, we need to consume the stream
            response_received = False
            async with asyncio.timeout(self.timeout):
                async for chunk in provider.chat(account.api_key, mapped_model, test_request):
                    response_received = True
                    break  # Just check if we get first chunk
            
            response_time = int((time.time() - start_time) * 1000)
            
            if response_received:
                logger.info(f"Account {account.name or account.id} (Channel: {channel.name}) is healthy (response time: {response_time}ms)")
                return True
            else:
                logger.warning(f"Account {account.name or account.id} (Channel: {channel.name}) returned no data")
                await self.handle_unhealthy_account(account)
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"Account {account.name or account.id} (Channel: {channel.name}) timeout")
            await self.handle_unhealthy_account(account)
            return False
        except Exception as e:
            logger.warning(f"Account {account.name or account.id} (Channel: {channel.name}) error: {e}")
            await self.handle_unhealthy_account(account)
            return False
    
    async def handle_unhealthy_account(self, account):
        """Handle unhealthy account (auto-disable after multiple failures)"""
        # For now, just log. In the future, could implement:
        # - Failure counter
        # - Auto-disable after N failures
        # - Alert notifications
        logger.warning(f"Account {account.name or account.id} is unhealthy")
        
        # Optional: Auto-disable account
        # await update_account(account.id, enabled=0)
    
    async def check_single_channel(self, channel_id: int) -> dict:
        """
        Check a single channel and return results
        
        Returns:
            {
                "channel_id": int,
                "channel_name": str,
                "total_accounts": int,
                "healthy_accounts": int,
                "unhealthy_accounts": int,
                "accounts": [
                    {"id": int, "name": str, "healthy": bool, "error": str}
                ]
            }
        """
        from models import get_channel_by_id, get_accounts_by_channel
        
        channel = await get_channel_by_id(channel_id)
        if not channel:
            return {"error": "Channel not found"}
        
        accounts = await get_accounts_by_channel(channel_id)
        
        results = {
            "channel_id": channel.id,
            "channel_name": channel.name,
            "total_accounts": len(accounts),
            "healthy_accounts": 0,
            "unhealthy_accounts": 0,
            "accounts": []
        }
        
        for account in accounts:
            if not account.enabled:
                results["accounts"].append({
                    "id": account.id,
                    "name": account.name,
                    "healthy": False,
                    "error": "Account disabled"
                })
                results["unhealthy_accounts"] += 1
                continue
            
            is_healthy = await self.check_account(channel, account)
            
            results["accounts"].append({
                "id": account.id,
                "name": account.name,
                "healthy": is_healthy,
                "error": None if is_healthy else "Health check failed"
            })
            
            if is_healthy:
                results["healthy_accounts"] += 1
            else:
                results["unhealthy_accounts"] += 1
        
        return results


# Global health checker instance
health_checker = HealthChecker()
