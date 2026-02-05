"""Rate limiting system for RPM and TPM"""
import time
from typing import Dict, List, Tuple
from collections import defaultdict
import asyncio


class RateLimiter:
    """Rate limiter for requests per minute (RPM) and tokens per minute (TPM)"""
    
    def __init__(self):
        # {token_id: [(timestamp, tokens)]}
        self.token_requests: Dict[int, List[Tuple[float, int]]] = defaultdict(list)
        # {user_id: [(timestamp, tokens)]}
        self.user_requests: Dict[int, List[Tuple[float, int]]] = defaultdict(list)
        # Lock for thread safety
        self.lock = asyncio.Lock()
    
    async def check_token_limit(
        self, 
        token_id: int, 
        rpm_limit: int = 0, 
        tpm_limit: int = 0,
        estimated_tokens: int = 0
    ) -> Tuple[bool, str]:
        """
        Check if token is within rate limits
        
        Args:
            token_id: Token ID
            rpm_limit: Requests per minute limit (0 = unlimited)
            tpm_limit: Tokens per minute limit (0 = unlimited)
            estimated_tokens: Estimated tokens for this request
        
        Returns:
            (allowed, error_message)
        """
        if rpm_limit == 0 and tpm_limit == 0:
            return True, ""
        
        async with self.lock:
            now = time.time()
            
            # Clean up old records (older than 60 seconds)
            self.token_requests[token_id] = [
                (ts, tokens) for ts, tokens in self.token_requests[token_id]
                if now - ts < 60
            ]
            
            # Check RPM
            if rpm_limit > 0:
                request_count = len(self.token_requests[token_id])
                if request_count >= rpm_limit:
                    return False, f"RPM limit exceeded: {request_count}/{rpm_limit}"
            
            # Check TPM
            if tpm_limit > 0:
                total_tokens = sum(tokens for _, tokens in self.token_requests[token_id])
                if total_tokens + estimated_tokens > tpm_limit:
                    return False, f"TPM limit exceeded: {total_tokens + estimated_tokens}/{tpm_limit}"
            
            # Record this request
            self.token_requests[token_id].append((now, estimated_tokens))
            
            return True, ""
    
    async def check_user_limit(
        self,
        user_id: int,
        rpm_limit: int = 0,
        tpm_limit: int = 0,
        estimated_tokens: int = 0
    ) -> Tuple[bool, str]:
        """
        Check if user is within rate limits
        
        Args:
            user_id: User ID
            rpm_limit: Requests per minute limit (0 = unlimited)
            tpm_limit: Tokens per minute limit (0 = unlimited)
            estimated_tokens: Estimated tokens for this request
        
        Returns:
            (allowed, error_message)
        """
        if rpm_limit == 0 and tpm_limit == 0:
            return True, ""
        
        async with self.lock:
            now = time.time()
            
            # Clean up old records
            self.user_requests[user_id] = [
                (ts, tokens) for ts, tokens in self.user_requests[user_id]
                if now - ts < 60
            ]
            
            # Check RPM
            if rpm_limit > 0:
                request_count = len(self.user_requests[user_id])
                if request_count >= rpm_limit:
                    return False, f"RPM limit exceeded: {request_count}/{rpm_limit}"
            
            # Check TPM
            if tpm_limit > 0:
                total_tokens = sum(tokens for _, tokens in self.user_requests[user_id])
                if total_tokens + estimated_tokens > tpm_limit:
                    return False, f"TPM limit exceeded: {total_tokens + estimated_tokens}/{tpm_limit}"
            
            # Record this request
            self.user_requests[user_id].append((now, estimated_tokens))
            
            return True, ""
    
    async def get_token_usage(self, token_id: int) -> Dict[str, int]:
        """Get current usage for a token"""
        async with self.lock:
            now = time.time()
            
            # Clean up old records
            self.token_requests[token_id] = [
                (ts, tokens) for ts, tokens in self.token_requests[token_id]
                if now - ts < 60
            ]
            
            requests = self.token_requests[token_id]
            return {
                "rpm": len(requests),
                "tpm": sum(tokens for _, tokens in requests)
            }
    
    async def get_user_usage(self, user_id: int) -> Dict[str, int]:
        """Get current usage for a user"""
        async with self.lock:
            now = time.time()
            
            # Clean up old records
            self.user_requests[user_id] = [
                (ts, tokens) for ts, tokens in self.user_requests[user_id]
                if now - ts < 60
            ]
            
            requests = self.user_requests[user_id]
            return {
                "rpm": len(requests),
                "tpm": sum(tokens for _, tokens in requests)
            }
    
    async def cleanup(self):
        """Cleanup old records (called periodically)"""
        async with self.lock:
            now = time.time()
            
            # Clean token requests
            for token_id in list(self.token_requests.keys()):
                self.token_requests[token_id] = [
                    (ts, tokens) for ts, tokens in self.token_requests[token_id]
                    if now - ts < 60
                ]
                if not self.token_requests[token_id]:
                    del self.token_requests[token_id]
            
            # Clean user requests
            for user_id in list(self.user_requests.keys()):
                self.user_requests[user_id] = [
                    (ts, tokens) for ts, tokens in self.user_requests[user_id]
                    if now - ts < 60
                ]
                if not self.user_requests[user_id]:
                    del self.user_requests[user_id]


# Global rate limiter instance
rate_limiter = RateLimiter()
