"""
Prompt Cache Handler
处理 AI 提供商的 Prompt Cache 功能
"""
from typing import Dict, Optional, Tuple
from utils.logger import logger

class CacheHandler:
    """处理缓存相关的逻辑"""
    
    # 缓存价格倍率配置（相对于正常价格）
    CACHE_RATIOS = {
        "openai": {
            "cache_read": 0.5,  # OpenAI 缓存读取是正常价格的 50%
            "cache_creation": 1.25  # 缓存创建是正常价格的 125%
        },
        "claude": {
            "cache_read": 0.1,  # Claude 缓存读取是正常价格的 10%
            "cache_creation": 1.25  # 缓存创建是正常价格的 125%
        },
        "gemini": {
            "cache_read": 0.25,  # Gemini 缓存读取是正常价格的 25%
            "cache_creation": 1.0  # 缓存创建价格相同
        },
        "kiro": {
            "cache_read": 0.5,
            "cache_creation": 1.0
        }
    }
    
    @staticmethod
    def extract_cache_usage(provider_type: str, usage_data: Dict) -> Tuple[int, int, Optional[str]]:
        """
        从不同提供商的 usage 数据中提取缓存信息
        
        Args:
            provider_type: 提供商类型 (openai, claude, gemini, kiro)
            usage_data: 原始 usage 数据
            
        Returns:
            (cache_read_tokens, cache_creation_tokens, cache_key)
        """
        cache_read = 0
        cache_creation = 0
        cache_key = None
        
        try:
            if provider_type == "openai":
                # OpenAI 格式: usage.prompt_tokens_details.cached_tokens
                prompt_details = usage_data.get("prompt_tokens_details", {})
                cache_read = prompt_details.get("cached_tokens", 0)
                # OpenAI 可能没有明确的 cache_creation 字段
                
            elif provider_type == "claude":
                # Claude 格式: usage.cache_read_input_tokens, usage.cache_creation_input_tokens
                cache_read = usage_data.get("cache_read_input_tokens", 0)
                cache_creation = usage_data.get("cache_creation_input_tokens", 0)
                
            elif provider_type == "gemini":
                # Gemini 格式: usage_metadata.cached_content_token_count
                cache_read = usage_data.get("cached_content_token_count", 0)
                
            elif provider_type == "kiro":
                # Kiro 可能使用类似 Claude 的格式
                cache_read = usage_data.get("cache_read_input_tokens", 0)
                cache_creation = usage_data.get("cache_creation_input_tokens", 0)
                
        except Exception as e:
            logger.error(f"Error extracting cache usage for {provider_type}: {e}")
        
        return cache_read, cache_creation, cache_key
    
    @staticmethod
    def calculate_cache_cost(
        provider_type: str,
        base_price: float,
        normal_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int
    ) -> float:
        """
        计算包含缓存的总成本
        
        Args:
            provider_type: 提供商类型
            base_price: 基础价格（每 1M tokens）
            normal_tokens: 正常 token 数
            cache_read_tokens: 缓存读取 token 数
            cache_creation_tokens: 缓存创建 token 数
            
        Returns:
            总成本
        """
        ratios = CacheHandler.CACHE_RATIOS.get(provider_type, {
            "cache_read": 1.0,
            "cache_creation": 1.0
        })
        
        # 计算各部分成本
        normal_cost = (normal_tokens / 1_000_000) * base_price
        cache_read_cost = (cache_read_tokens / 1_000_000) * base_price * ratios["cache_read"]
        cache_creation_cost = (cache_creation_tokens / 1_000_000) * base_price * ratios["cache_creation"]
        
        total_cost = normal_cost + cache_read_cost + cache_creation_cost
        
        logger.debug(
            f"Cache cost calculation for {provider_type}: "
            f"normal={normal_tokens}@{base_price} = ${normal_cost:.6f}, "
            f"cache_read={cache_read_tokens}@{base_price * ratios['cache_read']} = ${cache_read_cost:.6f}, "
            f"cache_creation={cache_creation_tokens}@{base_price * ratios['cache_creation']} = ${cache_creation_cost:.6f}, "
            f"total=${total_cost:.6f}"
        )
        
        return total_cost
    
    @staticmethod
    def get_cache_savings(
        provider_type: str,
        base_price: float,
        cache_read_tokens: int
    ) -> float:
        """
        计算缓存节省的成本
        
        Args:
            provider_type: 提供商类型
            base_price: 基础价格（每 1M tokens）
            cache_read_tokens: 缓存读取 token 数
            
        Returns:
            节省的成本
        """
        ratios = CacheHandler.CACHE_RATIOS.get(provider_type, {"cache_read": 1.0})
        
        # 如果没有缓存，这些 tokens 会按正常价格计费
        normal_cost = (cache_read_tokens / 1_000_000) * base_price
        # 实际使用缓存的成本
        cache_cost = (cache_read_tokens / 1_000_000) * base_price * ratios["cache_read"]
        
        savings = normal_cost - cache_cost
        return savings
    
    @staticmethod
    def format_cache_stats(
        cache_read_tokens: int,
        cache_creation_tokens: int,
        total_input_tokens: int
    ) -> Dict:
        """
        格式化缓存统计信息
        
        Returns:
            包含缓存命中率等信息的字典
        """
        cache_hit_rate = 0.0
        if total_input_tokens > 0:
            cache_hit_rate = (cache_read_tokens / total_input_tokens) * 100
        
        return {
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "total_cached_tokens": cache_read_tokens + cache_creation_tokens
        }


# 全局实例
_cache_handler = CacheHandler()

def get_cache_handler() -> CacheHandler:
    """获取全局缓存处理器实例"""
    return _cache_handler
