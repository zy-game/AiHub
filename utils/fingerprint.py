"""
请求指纹伪装系统
模拟真实用户的浏览器指纹和请求特征
"""
import random
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from utils.logger import logger


@dataclass
class BrowserFingerprint:
    """浏览器指纹"""
    user_agent: str
    accept: str
    accept_language: str
    accept_encoding: str
    sec_ch_ua: Optional[str] = None
    sec_ch_ua_mobile: Optional[str] = None
    sec_ch_ua_platform: Optional[str] = None


class FingerprintGenerator:
    """指纹生成器"""
    
    # 真实的User-Agent池（2024-2026年主流浏览器）
    USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:122.0) Gecko/20100101 Firefox/122.0",
        
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    
    # Accept-Language池（常见语言偏好）
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9",
        "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "zh-CN,zh;q=0.9,en;q=0.8",
        "ja-JP,ja;q=0.9,en;q=0.8",
        "ko-KR,ko;q=0.9,en;q=0.8",
        "de-DE,de;q=0.9,en;q=0.8",
        "fr-FR,fr;q=0.9,en;q=0.8",
        "es-ES,es;q=0.9,en;q=0.8",
    ]
    
    # Sec-CH-UA池（Chrome客户端提示）
    SEC_CH_UA_LIST = [
        '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
        '"Not_A Brand";v="8", "Chromium";v="122", "Google Chrome";v="122"',
        '"Chromium";v="120", "Microsoft Edge";v="120", "Not=A?Brand";v="8"',
        '"Chromium";v="121", "Microsoft Edge";v="121", "Not=A?Brand";v="8"',
    ]
    
    # 平台列表
    PLATFORMS = [
        "Windows",
        "macOS",
        "Linux",
    ]
    
    def __init__(self):
        self.fingerprints_cache: List[BrowserFingerprint] = []
        self._generate_fingerprints_pool()
    
    def _generate_fingerprints_pool(self, count: int = 50):
        """预生成指纹池"""
        for _ in range(count):
            self.fingerprints_cache.append(self._generate_single_fingerprint())
        logger.info(f"Generated {count} browser fingerprints")
    
    def _generate_single_fingerprint(self) -> BrowserFingerprint:
        """生成单个指纹"""
        user_agent = random.choice(self.USER_AGENTS)
        
        # 根据User-Agent判断浏览器类型
        is_chrome = "Chrome" in user_agent and "Edg" not in user_agent
        is_edge = "Edg" in user_agent
        is_firefox = "Firefox" in user_agent
        is_safari = "Safari" in user_agent and "Chrome" not in user_agent
        
        # 基础headers
        accept = "application/json, text/plain, */*"
        accept_language = random.choice(self.ACCEPT_LANGUAGES)
        accept_encoding = "gzip, deflate, br"
        
        # Chrome/Edge特有的Client Hints
        sec_ch_ua = None
        sec_ch_ua_mobile = None
        sec_ch_ua_platform = None
        
        if is_chrome or is_edge:
            sec_ch_ua = random.choice(self.SEC_CH_UA_LIST)
            sec_ch_ua_mobile = "?0"
            
            # 根据User-Agent推断平台
            if "Windows" in user_agent:
                sec_ch_ua_platform = '"Windows"'
            elif "Macintosh" in user_agent:
                sec_ch_ua_platform = '"macOS"'
            elif "Linux" in user_agent:
                sec_ch_ua_platform = '"Linux"'
        
        return BrowserFingerprint(
            user_agent=user_agent,
            accept=accept,
            accept_language=accept_language,
            accept_encoding=accept_encoding,
            sec_ch_ua=sec_ch_ua,
            sec_ch_ua_mobile=sec_ch_ua_mobile,
            sec_ch_ua_platform=sec_ch_ua_platform
        )
    
    def get_random_fingerprint(self) -> BrowserFingerprint:
        """获取随机指纹"""
        return random.choice(self.fingerprints_cache)
    
    def get_fingerprint_for_account(self, account_id: int) -> BrowserFingerprint:
        """为账号获取固定指纹（基于账号ID哈希）"""
        # 使用账号ID作为种子，确保同一账号总是使用相同的指纹
        index = account_id % len(self.fingerprints_cache)
        return self.fingerprints_cache[index]


class RequestHeadersBuilder:
    """请求头构建器"""
    
    def __init__(self, fingerprint_generator: FingerprintGenerator):
        self.fingerprint_generator = fingerprint_generator
    
    def build_headers(
        self,
        account_id: Optional[int] = None,
        api_key: Optional[str] = None,
        base_headers: Optional[Dict[str, str]] = None,
        sticky_fingerprint: bool = True
    ) -> Dict[str, str]:
        """
        构建请求头
        
        Args:
            account_id: 账号ID（用于固定指纹）
            api_key: API密钥
            base_headers: 基础headers（如Authorization）
            sticky_fingerprint: 是否使用固定指纹（True=账号绑定，False=随机）
        """
        # 获取指纹
        if sticky_fingerprint and account_id is not None:
            fingerprint = self.fingerprint_generator.get_fingerprint_for_account(account_id)
        else:
            fingerprint = self.fingerprint_generator.get_random_fingerprint()
        
        # 构建headers
        headers = base_headers.copy() if base_headers else {}
        
        # 添加指纹headers
        headers.update({
            "User-Agent": fingerprint.user_agent,
            "Accept": fingerprint.accept,
            "Accept-Language": fingerprint.accept_language,
            "Accept-Encoding": fingerprint.accept_encoding,
        })
        
        # Chrome/Edge特有的Client Hints
        if fingerprint.sec_ch_ua:
            headers["Sec-CH-UA"] = fingerprint.sec_ch_ua
        if fingerprint.sec_ch_ua_mobile:
            headers["Sec-CH-UA-Mobile"] = fingerprint.sec_ch_ua_mobile
        if fingerprint.sec_ch_ua_platform:
            headers["Sec-CH-UA-Platform"] = fingerprint.sec_ch_ua_platform
        
        # 添加常见的安全headers
        headers.update({
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        
        # 添加API Key（如果提供）
        if api_key:
            # 根据不同的API提供商使用不同的header名称
            # 这里使用通用的Authorization，具体provider会覆盖
            if "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {api_key}"
        
        return headers
    
    def add_timing_jitter(self, base_delay: float = 0.0) -> float:
        """
        添加时间抖动（模拟人类行为）
        
        Args:
            base_delay: 基础延迟（秒）
        
        Returns:
            实际延迟时间（秒）
        """
        # 添加0-2秒的随机抖动
        jitter = random.uniform(0, 2.0)
        total_delay = base_delay + jitter
        
        # 10%的概率添加更长的延迟（模拟用户思考）
        if random.random() < 0.1:
            total_delay += random.uniform(3.0, 8.0)
        
        return total_delay


# 全局实例
_fingerprint_generator: Optional[FingerprintGenerator] = None
_headers_builder: Optional[RequestHeadersBuilder] = None


def init_fingerprint_system():
    """初始化指纹系统"""
    global _fingerprint_generator, _headers_builder
    _fingerprint_generator = FingerprintGenerator()
    _headers_builder = RequestHeadersBuilder(_fingerprint_generator)
    logger.info("Fingerprint system initialized")


def get_fingerprint_generator() -> Optional[FingerprintGenerator]:
    """获取指纹生成器"""
    return _fingerprint_generator


def get_headers_builder() -> Optional[RequestHeadersBuilder]:
    """获取请求头构建器"""
    return _headers_builder


# 便捷函数
def build_request_headers(
    account_id: Optional[int] = None,
    api_key: Optional[str] = None,
    base_headers: Optional[Dict[str, str]] = None,
    sticky_fingerprint: bool = True
) -> Dict[str, str]:
    """
    构建请求头（便捷函数）
    """
    if not _headers_builder:
        init_fingerprint_system()
    
    return _headers_builder.build_request_headers(
        account_id=account_id,
        api_key=api_key,
        base_headers=base_headers,
        sticky_fingerprint=sticky_fingerprint
    )
