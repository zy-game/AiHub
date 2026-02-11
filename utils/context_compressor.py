"""
Context Compression
压缩长上下文以减少 token 使用
"""
import json
from typing import List, Dict, Optional
from utils.logger import logger
from utils.token_counter import count_tokens


class ContextCompressor:
    """上下文压缩器"""
    
    def __init__(self):
        self.enabled = False
        self.threshold = 8000
        self.target = 4000
        self.strategy = "sliding_window"
        self._config_loaded = False
    
    async def _load_config(self):
        """从数据库加载配置"""
        # 移除缓存机制，每次都重新加载以确保获取最新配置
        try:
            from models import get_cache_config
            config = await get_cache_config()
            self.enabled = config.get("context_compression_enabled", 0) == 1
            self.threshold = config.get("context_compression_threshold", 8000)
            self.target = config.get("context_compression_target", 4000)
            self.strategy = config.get("context_compression_strategy", "sliding_window")
            logger.debug(f"Loaded context compression config: enabled={self.enabled}, threshold={self.threshold}, target={self.target}, strategy={self.strategy}")
        except Exception as e:
            logger.error(f"Failed to load context compression config: {e}")
            # 使用默认值
            self.enabled = False
    
    async def compress_if_needed(self, messages: List[Dict], model: str) -> tuple[List[Dict], bool, int, int]:
        """
        如果需要，压缩消息列表
        
        Args:
            messages: 消息列表
            model: 模型名称
            
        Returns:
            (compressed_messages, was_compressed, original_tokens, compressed_tokens)
        """
        # 加载配置
        await self._load_config()
        
        logger.debug(f"Context compression check - enabled: {self.enabled}, threshold: {self.threshold}")
        
        if not self.enabled:
            logger.debug("Context compression is disabled")
            return messages, False, 0, 0
        
        # 计算当前 token 数
        original_tokens = self._estimate_tokens(messages, model)
        
        logger.info(f"Context compression check: {original_tokens} tokens (threshold: {self.threshold})")
        
        # 如果未超过阈值，不压缩
        if original_tokens < self.threshold:
            logger.debug(f"No compression needed: {original_tokens} < {self.threshold}")
            return messages, False, original_tokens, original_tokens
        
        logger.info(f"Context compression triggered: {original_tokens} tokens > {self.threshold} threshold")
        
        # 根据策略压缩
        if self.strategy == "sliding_window":
            compressed = self._sliding_window_compress(messages)
        elif self.strategy == "summary":
            compressed = await self._summary_compress(messages, model)
        elif self.strategy == "hybrid":
            compressed = await self._hybrid_compress(messages, model)
        else:
            compressed = self._sliding_window_compress(messages)
        
        compressed_tokens = self._estimate_tokens(compressed, model)
        
        logger.info(f"Context compressed: {original_tokens} -> {compressed_tokens} tokens "
                   f"(saved {original_tokens - compressed_tokens} tokens, "
                   f"{((original_tokens - compressed_tokens) / original_tokens * 100):.1f}%)")
        
        # Debug: log compressed message structure
        logger.debug(f"Compressed messages: {len(compressed)} messages")
        for i, msg in enumerate(compressed):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # Check content type
            if isinstance(content, list):
                content_types = [item.get('type') if isinstance(item, dict) else 'unknown' for item in content]
                logger.debug(f"  [{i}] role={role}, content_types={content_types}")
            else:
                content_preview = str(content)[:100] if content else 'empty'
                logger.debug(f"  [{i}] role={role}, content={content_preview}...")
        
        return compressed, True, original_tokens, compressed_tokens
    
    def _estimate_tokens(self, messages: List[Dict], model: str) -> int:
        """估算消息列表的 token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += count_tokens(content, model)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total += count_tokens(item["text"], model)
        return total
    
    def _sliding_window_compress(self, messages: List[Dict]) -> List[Dict]:
        """
        滑动窗口压缩：保留系统提示 + 最近的 N 条消息
        确保消息序列符合Anthropic规则：
        1. user/assistant消息必须交替
        2. 如果assistant有tool_use，下一条user必须有tool_result
        3. 最后一条必须是user消息
        """
        if not messages:
            return messages
        
        # 分离系统消息和对话消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        conversation_messages = [m for m in messages if m.get("role") != "system"]
        
        if not conversation_messages:
            return messages
        
        # 确保最后一条消息是用户消息
        last_user_idx = -1
        for i in range(len(conversation_messages) - 1, -1, -1):
            if conversation_messages[i].get("role") == "user":
                last_user_idx = i
                break
        
        if last_user_idx == -1:
            # 没有用户消息，无法压缩
            logger.warning("No user message found in conversation, skipping compression")
            return messages
        
        # 只考虑到最后一条用户消息为止的消息
        messages_to_compress = conversation_messages[:last_user_idx + 1]
        
        # 计算可以保留多少条消息
        system_tokens = self._estimate_tokens(system_messages, "gpt-3.5-turbo")
        remaining_budget = self.target - system_tokens
        
        # 从最后一条用户消息开始往前，逐条添加直到达到目标
        kept_messages = []
        current_tokens = 0
        
        for msg in reversed(messages_to_compress):
            msg_tokens = self._estimate_tokens([msg], "gpt-3.5-turbo")
            if current_tokens + msg_tokens <= remaining_budget:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        # 确保至少保留最后一条用户消息
        if not kept_messages or kept_messages[-1].get("role") != "user":
            # 强制保留最后一条用户消息
            kept_messages = [conversation_messages[last_user_idx]]
        
        # 清理消息序列，确保符合Anthropic规则
        kept_messages = self._clean_message_sequence(kept_messages)
        
        result = system_messages + kept_messages
        logger.debug(f"Sliding window: kept {len(kept_messages)}/{len(conversation_messages)} messages, "
                    f"last role: {kept_messages[-1].get('role') if kept_messages else 'none'}")
        
        return result
    
    def _clean_message_sequence(self, messages: List[Dict]) -> List[Dict]:
        """
        清理消息序列，确保符合Anthropic规则：
        1. 必须以user消息开始
        2. user/assistant必须交替
        3. 如果assistant有tool_use，必须保留下一条user的tool_result
        4. 如果user有tool_result但前面的assistant没有tool_use，移除tool_result
        """
        if not messages:
            return messages
        
        cleaned = []
        
        for i, msg in enumerate(messages):
            role = msg.get("role")
            
            # 确保第一条是user消息
            if not cleaned and role != "user":
                continue
            
            # 确保交替
            if cleaned:
                last_role = cleaned[-1].get("role")
                if last_role == role:
                    # 连续相同角色，跳过当前消息
                    continue
            
            # 检查tool_use和tool_result的匹配
            if role == "user" and cleaned:
                last_msg = cleaned[-1]
                if last_msg.get("role") == "assistant":
                    # 检查assistant是否有tool_use
                    last_content = last_msg.get("content", [])
                    has_tool_use = False
                    if isinstance(last_content, list):
                        has_tool_use = any(
                            isinstance(item, dict) and item.get("type") == "tool_use" 
                            for item in last_content
                        )
                    
                    # 检查当前user是否有tool_result
                    curr_content = msg.get("content", [])
                    has_tool_result = False
                    if isinstance(curr_content, list):
                        has_tool_result = any(
                            isinstance(item, dict) and item.get("type") == "tool_result"
                            for item in curr_content
                        )
                    
                    # 如果不匹配，需要清理
                    if has_tool_use and not has_tool_result:
                        # assistant有tool_use但user没有tool_result，移除assistant的tool_use
                        import copy
                        last_msg = copy.deepcopy(last_msg)
                        if isinstance(last_msg.get("content"), list):
                            last_msg["content"] = [
                                item for item in last_msg["content"]
                                if not (isinstance(item, dict) and item.get("type") == "tool_use")
                            ]
                        cleaned[-1] = last_msg
                    elif not has_tool_use and has_tool_result:
                        # user有tool_result但assistant没有tool_use，移除user的tool_result
                        import copy
                        msg = copy.deepcopy(msg)
                        if isinstance(msg.get("content"), list):
                            msg["content"] = [
                                item for item in msg["content"]
                                if not (isinstance(item, dict) and item.get("type") == "tool_result")
                            ]
            
            cleaned.append(msg)
        
        # 确保最后一条是user消息
        while cleaned and cleaned[-1].get("role") != "user":
            cleaned.pop()
        
        return cleaned
    
    async def _summary_compress(self, messages: List[Dict], model: str) -> List[Dict]:
        """
        摘要压缩：使用 GLM-4.6V-Flash 模型总结历史对话
        """
        try:
            from providers.glm import GLMProvider
            from models import get_accounts_by_provider
            
            # 获取 GLM 账号
            accounts = await get_accounts_by_provider("glm")
            if not accounts:
                logger.warning("No GLM account found, falling back to sliding window")
                return self._sliding_window_compress(messages)
            account = accounts[0]
            
            # 分离系统消息和对话消息
            system_messages = [m for m in messages if m.get("role") == "system"]
            conversation_messages = [m for m in messages if m.get("role") != "system"]
            
            if len(conversation_messages) <= 2:
                # 对话太短，不需要压缩
                return messages
            
            # 保留最后一条用户消息
            last_user_msg = None
            for msg in reversed(conversation_messages):
                if msg.get("role") == "user":
                    last_user_msg = msg
                    break
            
            if not last_user_msg:
                logger.warning("No user message found, falling back to sliding window")
                return self._sliding_window_compress(messages)
            
            # 提取需要总结的历史消息（排除最后一条用户消息）
            history_to_summarize = []
            for msg in conversation_messages:
                if msg == last_user_msg:
                    break
                history_to_summarize.append(msg)
            
            if not history_to_summarize:
                return messages
            
            # 构建总结提示
            history_text = self._format_messages_for_summary(history_to_summarize)
            summary_prompt = f"""请总结以下对话的关键信息，保留重要的上下文和决策点。要求：
1. 简洁明了，突出重点
2. 保留关键的技术细节和决策
3. 使用列表形式组织信息
4. 总结长度控制在原对话的30%以内

对话历史：
{history_text}

请提供总结："""
            
            # 调用 GLM-4.6V-Flash 进行总结
            glm_provider = GLMProvider()
            summary_request = {
                "messages": [{"role": "user", "content": summary_prompt}],
                "stream": False,
                "temperature": 0.3,
                "max_tokens": 1000
            }
            
            summary_text = ""
            async for chunk in glm_provider.chat(
                api_key=account.api_key,
                model="glm-4-flash",  # GLM-4.6V-Flash 对应的模型名
                data=summary_request,
                account_id=account.id
            ):
                response_data = json.loads(chunk.decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        summary_text = choice["message"]["content"]
            
            if not summary_text:
                logger.warning("Failed to generate summary, falling back to sliding window")
                return self._sliding_window_compress(messages)
            
            # 构建压缩后的消息列表
            compressed = system_messages.copy()
            
            # 添加总结消息（确保格式正确，只包含 role 和 content）
            compressed.append({
                "role": "user",
                "content": f"[历史对话总结]\n{summary_text}"
            })
            
            # 添加最后一条用户消息（确保格式正确，只保留 role 和 content）
            last_msg_content = self._extract_text_content(last_user_msg.get("content", ""))
            if not last_msg_content:
                logger.warning("Last user message has no text content, using placeholder")
                last_msg_content = "[Previous message]"
            
            compressed.append({
                "role": "user",
                "content": last_msg_content
            })
            
            # 验证消息序列
            logger.debug(f"Summary compressed message sequence:")
            for i, msg in enumerate(compressed):
                logger.debug(f"  [{i}] role={msg.get('role')}, content_type={type(msg.get('content')).__name__}")
            
            logger.info(f"Summary compression: {len(conversation_messages)} messages -> {len(compressed) - len(system_messages)} messages")
            
            return compressed
            
        except Exception as e:
            logger.error(f"Summary compression failed: {e}", exc_info=True)
            return self._sliding_window_compress(messages)
    
    async def _hybrid_compress(self, messages: List[Dict], model: str) -> List[Dict]:
        """
        混合压缩：总结旧消息 + 保留最近消息
        """
        try:
            from providers.glm import GLMProvider
            from models import get_accounts_by_provider
            
            # 获取 GLM 账号
            accounts = await get_accounts_by_provider("glm")
            if not accounts:
                logger.warning("No GLM account found, falling back to sliding window")
                return self._sliding_window_compress(messages)
            account = accounts[0]
            
            # 分离系统消息和对话消息
            system_messages = [m for m in messages if m.get("role") == "system"]
            conversation_messages = [m for m in messages if m.get("role") != "system"]
            
            if len(conversation_messages) <= 4:
                # 对话太短，不需要压缩
                return messages
            
            # 保留最后 2 轮对话（4条消息）
            recent_messages = conversation_messages[-4:]
            history_to_summarize = conversation_messages[:-4]
            
            if not history_to_summarize:
                return messages
            
            # 构建总结提示
            history_text = self._format_messages_for_summary(history_to_summarize)
            summary_prompt = f"""请总结以下对话的关键信息，保留重要的上下文和决策点。要求：
1. 简洁明了，突出重点
2. 保留关键的技术细节和决策
3. 使用列表形式组织信息
4. 总结长度控制在原对话的30%以内

对话历史：
{history_text}

请提供总结："""
            
            # 调用 GLM-4.6V-Flash 进行总结
            glm_provider = GLMProvider()
            summary_request = {
                "messages": [{"role": "user", "content": summary_prompt}],
                "stream": False,
                "temperature": 0.3,
                "max_tokens": 1000
            }
            
            summary_text = ""
            async for chunk in glm_provider.chat(
                api_key=account.api_key,
                model="glm-4-flash",
                data=summary_request,
                account_id=account.id
            ):
                response_data = json.loads(chunk.decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        summary_text = choice["message"]["content"]
            
            if not summary_text:
                logger.warning("Failed to generate summary, falling back to sliding window")
                return self._sliding_window_compress(messages)
            
            # 构建压缩后的消息列表
            compressed = system_messages.copy()
            
            # 添加总结消息（确保格式正确，只包含 role 和 content）
            compressed.append({
                "role": "user",
                "content": f"[历史对话总结]\n{summary_text}"
            })
            
            # 添加最近的消息（确保格式正确，只保留 role 和 content）
            for msg in recent_messages:
                msg_content = self._extract_text_content(msg.get("content", ""))
                if not msg_content:
                    logger.warning(f"Message has no text content, skipping")
                    continue
                compressed.append({
                    "role": msg.get("role"),
                    "content": msg_content
                })
            
            # 验证消息序列
            logger.debug(f"Hybrid compressed message sequence:")
            for i, msg in enumerate(compressed):
                logger.debug(f"  [{i}] role={msg.get('role')}, content_type={type(msg.get('content')).__name__}")
            
            logger.info(f"Hybrid compression: {len(conversation_messages)} messages -> {len(compressed) - len(system_messages)} messages")
            
            return compressed
            
        except Exception as e:
            logger.error(f"Hybrid compression failed: {e}", exc_info=True)
            return self._sliding_window_compress(messages)
    
    def _format_messages_for_summary(self, messages: List[Dict]) -> str:
        """
        格式化消息列表用于总结
        """
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if isinstance(content, str):
                formatted.append(f"{role}: {content}")
            elif isinstance(content, list):
                # 处理多模态内容
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            # 提取 tool_result 中的文本
                            tool_content = item.get("content", "")
                            if isinstance(tool_content, str):
                                text_parts.append(f"[Tool Result: {tool_content[:100]}...]")
                            elif isinstance(tool_content, list):
                                for sub_item in tool_content:
                                    if isinstance(sub_item, dict) and sub_item.get("type") == "text":
                                        text_parts.append(f"[Tool Result: {sub_item.get('text', '')[:100]}...]")
                if text_parts:
                    formatted.append(f"{role}: {' '.join(text_parts)}")
        
        return "\n\n".join(formatted)
    
    def _extract_text_content(self, content) -> str:
        """
        从消息内容中提取纯文本
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        # 提取 tool_result 中的文本
                        tool_content = item.get("content", "")
                        if isinstance(tool_content, str):
                            text_parts.append(tool_content)
                        elif isinstance(tool_content, list):
                            for sub_item in tool_content:
                                if isinstance(sub_item, dict) and sub_item.get("type") == "text":
                                    text_parts.append(sub_item.get("text", ""))
            return " ".join(text_parts)
        return ""


# 全局实例
_compressor = None

def get_context_compressor() -> ContextCompressor:
    """获取全局上下文压缩器实例"""
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor
