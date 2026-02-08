"""协议转换模块 - Anthropic/OpenAI/Gemini <-> Kiro

增强版：参考 proxycast 实现
- 工具数量限制（最多 50 个）
- 工具描述截断（最多 500 字符）
- 历史消息交替修复
- OpenAI tool 角色消息处理
- tool_choice: required 支持
- web_search 特殊工具支持
- tool_results 去重
"""
import json
import hashlib
import re
from typing import List, Dict, Any, Tuple, Optional

# 常量
MAX_TOOLS = 50
MAX_TOOL_DESCRIPTION_LENGTH = 500


def generate_session_id(messages: list) -> str:
    """基于消息内容生成会话ID"""
    content = json.dumps(messages[:3], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def extract_images_from_content(content) -> Tuple[str, List[dict]]:
    """从消息内容中提取文本和图片
    
    Returns:
        (text_content, images_list)
    """
    if isinstance(content, str):
        return content, []
    
    if not isinstance(content, list):
        return str(content) if content else "", []
    
    text_parts = []
    images = []
    
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get("type", "")
            
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            
            elif block_type == "image":
                # Anthropic 格式
                source = block.get("source", {})
                media_type = source.get("media_type", "image/jpeg")
                data = source.get("data", "")
                
                fmt = "jpeg"
                if "png" in media_type:
                    fmt = "png"
                elif "gif" in media_type:
                    fmt = "gif"
                elif "webp" in media_type:
                    fmt = "webp"
                
                if data:
                    images.append({
                        "format": fmt,
                        "source": {"bytes": data}
                    })
            
            elif block_type == "image_url":
                # OpenAI 格式
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")
                
                if url.startswith("data:"):
                    match = re.match(r'data:image/(\w+);base64,(.+)', url)
                    if match:
                        fmt = match.group(1)
                        data = match.group(2)
                        images.append({
                            "format": fmt,
                            "source": {"bytes": data}
                        })
    
    return "\n".join(text_parts), images


def truncate_description(desc: str, max_length: int = MAX_TOOL_DESCRIPTION_LENGTH) -> str:
    """截断工具描述"""
    if len(desc) <= max_length:
        return desc
    return desc[:max_length - 3] + "..."


# ==================== Anthropic 转换 ====================

def convert_anthropic_tools_to_kiro(tools: List[dict]) -> List[dict]:
    """将 Anthropic 工具格式转换为 Kiro 格式
    
    增强：
    - 限制最多 50 个工具
    - 截断过长的描述
    - 支持 web_search 特殊工具
    """
    kiro_tools = []
    function_count = 0
    
    for tool in tools:
        name = tool.get("name", "")
        
        # 特殊工具：web_search
        if name in ("web_search", "web_search_20250305"):
            kiro_tools.append({
                "webSearchTool": {
                    "type": "web_search"
                }
            })
            continue
        
        # 限制工具数量
        if function_count >= MAX_TOOLS:
            continue
        function_count += 1
        
        description = tool.get("description", f"Tool: {name}")
        description = truncate_description(description)
        
        input_schema = tool.get("input_schema", {"type": "object", "properties": {}})
        
        kiro_tools.append({
            "toolSpecification": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": input_schema
                }
            }
        })
    
    return kiro_tools


def fix_history_alternation(history: List[dict], model_id: str = "claude-sonnet-4") -> List[dict]:
    """修复历史记录，确保 user/assistant 严格交替，并验证 toolUses/toolResults 配对
    
    Kiro API 规则：
    1. 消息必须严格交替：user -> assistant -> user -> assistant
    2. 当 assistant 有 toolUses 时，下一条 user 必须有对应的 toolResults
    3. 当 assistant 没有 toolUses 时，下一条 user 不能有 toolResults
    """
    if not history:
        return history
    
    # 深拷贝以避免修改原始数据
    import copy
    history = copy.deepcopy(history)
    
    fixed = []
    
    for i, item in enumerate(history):
        is_user = "userInputMessage" in item
        is_assistant = "assistantResponseMessage" in item
        
        if is_user:
            # 检查上一条是否也是 user
            if fixed and "userInputMessage" in fixed[-1]:
                # 检查当前消息是否有 tool_results
                user_msg = item["userInputMessage"]
                ctx = user_msg.get("userInputMessageContext", {})
                has_tool_results = bool(ctx.get("toolResults"))
                
                if has_tool_results:
                    # 合并 tool_results 到上一条 user 消息
                    new_results = ctx["toolResults"]
                    last_user = fixed[-1]["userInputMessage"]
                    
                    if "userInputMessageContext" not in last_user:
                        last_user["userInputMessageContext"] = {}
                    
                    last_ctx = last_user["userInputMessageContext"]
                    if "toolResults" in last_ctx and last_ctx["toolResults"]:
                        last_ctx["toolResults"].extend(new_results)
                    else:
                        last_ctx["toolResults"] = new_results
                    continue
                else:
                    # 插入一个占位 assistant 消息（不带 toolUses）
                    fixed.append({
                        "assistantResponseMessage": {
                            "content": "I understand."
                        }
                    })
            
            # 验证 toolResults 与前一个 assistant 的 toolUses 配对
            if fixed and "assistantResponseMessage" in fixed[-1]:
                last_assistant = fixed[-1]["assistantResponseMessage"]
                has_tool_uses = bool(last_assistant.get("toolUses"))
                
                user_msg = item["userInputMessage"]
                ctx = user_msg.get("userInputMessageContext", {})
                has_tool_results = bool(ctx.get("toolResults"))
                
                if has_tool_uses and not has_tool_results:
                    # assistant 有 toolUses 但 user 没有 toolResults
                    # 这是不允许的，需要清除 assistant 的 toolUses
                    last_assistant.pop("toolUses", None)
                elif not has_tool_uses and has_tool_results:
                    # assistant 没有 toolUses 但 user 有 toolResults
                    # 这是不允许的，需要清除 user 的 toolResults
                    item["userInputMessage"].pop("userInputMessageContext", None)
            
            fixed.append(item)
        
        elif is_assistant:
            # 检查上一条是否也是 assistant
            if fixed and "assistantResponseMessage" in fixed[-1]:
                # 插入一个占位 user 消息（不带 toolResults）
                fixed.append({
                    "userInputMessage": {
                        "content": "Continue",
                        "modelId": model_id,
                        "origin": "AI_EDITOR"
                    }
                })
            
            # 如果历史为空，先插入一个 user 消息
            if not fixed:
                fixed.append({
                    "userInputMessage": {
                        "content": "Continue",
                        "modelId": model_id,
                        "origin": "AI_EDITOR"
                    }
                })
            
            fixed.append(item)
    
    # 确保以 assistant 结尾（如果最后是 user，添加占位 assistant）
    if fixed and "userInputMessage" in fixed[-1]:
        # 不需要清除 toolResults，因为它是与前一个 assistant 的 toolUses 配对的
        # 占位 assistant 只是为了满足交替规则
        fixed.append({
            "assistantResponseMessage": {
                "content": "I understand."
            }
        })
    
    return fixed


def convert_anthropic_messages_to_kiro(messages: List[dict], system="") -> Tuple[str, List[dict], List[dict]]:
    """将 Anthropic 消息格式转换为 Kiro 格式
    
    Returns:
        (user_content, history, tool_results)
    """
    history = []
    user_content = ""
    current_tool_results = []
    
    # 处理 system
    system_text = ""
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                system_text += block.get("text", "") + "\n"
            elif isinstance(block, str):
                system_text += block + "\n"
        system_text = system_text.strip()
    elif isinstance(system, str):
        system_text = system
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        is_last = (i == len(messages) - 1)
        
        # 处理 content 列表
        tool_results = []
        text_parts = []
        
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        tr_content = block.get("content", "")
                        if isinstance(tr_content, list):
                            tr_text_parts = []
                            for tc in tr_content:
                                if isinstance(tc, dict) and tc.get("type") == "text":
                                    tr_text_parts.append(tc.get("text", ""))
                                elif isinstance(tc, str):
                                    tr_text_parts.append(tc)
                            tr_content = "\n".join(tr_text_parts)
                        
                        # 处理 is_error
                        status = "error" if block.get("is_error") else "success"
                        
                        tool_results.append({
                            "content": [{"text": str(tr_content)}],
                            "status": status,
                            "toolUseId": block.get("tool_use_id", "")
                        })
                elif isinstance(block, str):
                    text_parts.append(block)
            
            content = "\n".join(text_parts) if text_parts else ""
        
        # 处理工具结果
        if tool_results:
            # 去重
            seen_ids = set()
            unique_results = []
            for tr in tool_results:
                if tr["toolUseId"] not in seen_ids:
                    seen_ids.add(tr["toolUseId"])
                    unique_results.append(tr)
            tool_results = unique_results
            
            if is_last:
                current_tool_results = tool_results
                user_content = content if content else "Tool results provided."
            else:
                history.append({
                    "userInputMessage": {
                        "content": content if content else "Tool results provided.",
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": tool_results
                        }
                    }
                })
            continue
        
        if role == "user":
            if system_text and not history:
                content = f"{system_text}\n\n{content}" if content else system_text
            
            if is_last:
                user_content = content if content else "Continue"
            else:
                history.append({
                    "userInputMessage": {
                        "content": content if content else "Continue",
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR"
                    }
                })
        
        elif role == "assistant":
            tool_uses = []
            assistant_text = ""
            
            if isinstance(msg.get("content"), list):
                text_parts = []
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            tool_uses.append({
                                "toolUseId": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input": block.get("input", {})
                            })
                        elif block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                assistant_text = "\n".join(text_parts)
            else:
                assistant_text = content if isinstance(content, str) else ""
            
            # 确保 assistant 消息有内容
            if not assistant_text:
                assistant_text = "I understand."
            
            assistant_msg = {
                "assistantResponseMessage": {
                    "content": assistant_text
                }
            }
            # 只有在有 toolUses 时才添加这个字段
            if tool_uses:
                assistant_msg["assistantResponseMessage"]["toolUses"] = tool_uses
            
            history.append(assistant_msg)
    
    # 修复历史交替
    history = fix_history_alternation(history)
    
    return user_content, history, current_tool_results


def convert_kiro_response_to_anthropic(result: dict, model: str, msg_id: str) -> dict:
    """将 Kiro 响应转换为 Anthropic 格式"""
    content = []
    text = "".join(result["content"])
    if text:
        content.append({"type": "text", "text": text})
    
    for tool_use in result["tool_uses"]:
        content.append(tool_use)
    
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": result["stop_reason"],
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 100}
    }


# ==================== OpenAI 转换 ====================

def is_tool_choice_required(tool_choice) -> bool:
    """检查 tool_choice 是否为 required"""
    if isinstance(tool_choice, dict):
        t = tool_choice.get("type", "")
        return t in ("any", "tool", "required")
    elif isinstance(tool_choice, str):
        return tool_choice in ("required", "any")
    return False


def convert_openai_tools_to_kiro(tools: List[dict]) -> List[dict]:
    """将 OpenAI 工具格式转换为 Kiro 格式"""
    kiro_tools = []
    function_count = 0
    
    for tool in tools:
        tool_type = tool.get("type", "function")
        
        # 特殊工具
        if tool_type == "web_search":
            kiro_tools.append({
                "webSearchTool": {
                    "type": "web_search"
                }
            })
            continue
        
        if tool_type != "function":
            continue
        
        # 限制工具数量
        if function_count >= MAX_TOOLS:
            continue
        function_count += 1
        
        func = tool.get("function", {})
        name = func.get("name", "")
        description = func.get("description", f"Tool: {name}")
        description = truncate_description(description)
        parameters = func.get("parameters", {"type": "object", "properties": {}})
        
        kiro_tools.append({
            "toolSpecification": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": parameters
                }
            }
        })
    
    return kiro_tools


def convert_openai_messages_to_kiro(
    messages: List[dict], 
    model: str,
    tools: List[dict] = None,
    tool_choice = None
) -> Tuple[str, List[dict], List[dict], List[dict]]:
    """将 OpenAI 消息格式转换为 Kiro 格式
    
    增强：
    - 支持 tool 角色消息
    - 支持 assistant 的 tool_calls
    - 支持 tool_choice: required
    - 历史交替修复
    
    Returns:
        (user_content, history, tool_results, kiro_tools)
    """
    system_content = ""
    history = []
    user_content = ""
    current_tool_results = []
    pending_tool_results = []  # 待处理的 tool 消息
    
    # 处理 tool_choice: required
    tool_instruction = ""
    if is_tool_choice_required(tool_choice) and tools:
        tool_instruction = "\n\n[CRITICAL INSTRUCTION] You MUST use one of the provided tools to respond. Do NOT respond with plain text. Call a tool function immediately."
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        is_last = (i == len(messages) - 1)
        
        # 提取文本内容
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
        if not content:
            content = ""
        
        if role == "system":
            system_content = content + tool_instruction
        
        elif role == "tool":
            # OpenAI tool 角色消息 -> Kiro toolResults
            tool_call_id = msg.get("tool_call_id", "")
            pending_tool_results.append({
                "content": [{"text": str(content)}],
                "status": "success",
                "toolUseId": tool_call_id
            })
        
        elif role == "user":
            # 如果有待处理的 tool results，先处理
            if pending_tool_results:
                # 去重
                seen_ids = set()
                unique_results = []
                for tr in pending_tool_results:
                    if tr["toolUseId"] not in seen_ids:
                        seen_ids.add(tr["toolUseId"])
                        unique_results.append(tr)
                
                if is_last:
                    current_tool_results = unique_results
                else:
                    history.append({
                        "userInputMessage": {
                            "content": "Tool results provided.",
                            "modelId": model,
                            "origin": "AI_EDITOR",
                            "userInputMessageContext": {
                                "toolResults": unique_results
                            }
                        }
                    })
                pending_tool_results = []
            
            # 合并 system prompt
            if system_content and not history:
                content = f"{system_content}\n\n{content}"
            
            if is_last:
                user_content = content
            else:
                history.append({
                    "userInputMessage": {
                        "content": content,
                        "modelId": model,
                        "origin": "AI_EDITOR"
                    }
                })
        
        elif role == "assistant":
            # 如果有待处理的 tool results，先创建 user 消息
            if pending_tool_results:
                seen_ids = set()
                unique_results = []
                for tr in pending_tool_results:
                    if tr["toolUseId"] not in seen_ids:
                        seen_ids.add(tr["toolUseId"])
                        unique_results.append(tr)
                
                history.append({
                    "userInputMessage": {
                        "content": "Tool results provided.",
                        "modelId": model,
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": unique_results
                        }
                    }
                })
                pending_tool_results = []
            
            # 处理 tool_calls
            tool_uses = []
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except:
                    args = {}
                
                tool_uses.append({
                    "toolUseId": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": args
                })
            
            assistant_text = content if content else "I understand."
            
            assistant_msg = {
                "assistantResponseMessage": {
                    "content": assistant_text
                }
            }
            # 只有在有 toolUses 时才添加这个字段
            if tool_uses:
                assistant_msg["assistantResponseMessage"]["toolUses"] = tool_uses
            
            history.append(assistant_msg)
    
    # 处理末尾的 tool results
    if pending_tool_results:
        seen_ids = set()
        unique_results = []
        for tr in pending_tool_results:
            if tr["toolUseId"] not in seen_ids:
                seen_ids.add(tr["toolUseId"])
                unique_results.append(tr)
        current_tool_results = unique_results
        if not user_content:
            user_content = "Tool results provided."
    
    # 如果没有用户消息
    if not user_content:
        user_content = messages[-1].get("content", "") if messages else "Continue"
        if isinstance(user_content, list):
            user_content = " ".join([c.get("text", "") for c in user_content if c.get("type") == "text"])
        if not user_content:
            user_content = "Continue"
    
    # 历史不包含最后一条用户消息
    if history and "userInputMessage" in history[-1]:
        history = history[:-1]
    
    # 修复历史交替
    history = fix_history_alternation(history, model)
    
    # 转换工具
    kiro_tools = convert_openai_tools_to_kiro(tools) if tools else []
    
    return user_content, history, current_tool_results, kiro_tools


def convert_kiro_response_to_openai(result: dict, model: str, msg_id: str) -> dict:
    """将 Kiro 响应转换为 OpenAI 格式"""
    text = "".join(result["content"])
    tool_calls = []
    
    for tool_use in result.get("tool_uses", []):
        if tool_use.get("type") == "tool_use":
            tool_calls.append({
                "id": tool_use.get("id", ""),
                "type": "function",
                "function": {
                    "name": tool_use.get("name", ""),
                    "arguments": json.dumps(tool_use.get("input", {}))
                }
            })
    
    # 映射 stop_reason
    stop_reason = result.get("stop_reason", "stop")
    finish_reason = "tool_calls" if tool_calls else "stop"
    if stop_reason == "max_tokens":
        finish_reason = "length"
    
    message = {
        "role": "assistant",
        "content": text if text else None
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    
    return {
        "id": msg_id,
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason
        }],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 100,
            "total_tokens": 200
        }
    }


# ==================== Gemini 转换 ====================

def convert_gemini_tools_to_kiro(tools: List[dict]) -> List[dict]:
    """将 Gemini 工具格式转换为 Kiro 格式
    
    Gemini 工具格式：
    {
        "functionDeclarations": [
            {
                "name": "get_weather",
                "description": "Get weather info",
                "parameters": {...}
            }
        ]
    }
    """
    kiro_tools = []
    function_count = 0
    
    for tool in tools:
        # Gemini 的工具定义在 functionDeclarations 中
        declarations = tool.get("functionDeclarations", [])
        
        for func in declarations:
            # 限制工具数量
            if function_count >= MAX_TOOLS:
                break
            function_count += 1
            
            name = func.get("name", "")
            description = func.get("description", f"Tool: {name}")
            description = truncate_description(description)
            parameters = func.get("parameters", {"type": "object", "properties": {}})
            
            kiro_tools.append({
                "toolSpecification": {
                    "name": name,
                    "description": description,
                    "inputSchema": {
                        "json": parameters
                    }
                }
            })
    
    return kiro_tools


def convert_gemini_contents_to_kiro(
    contents: List[dict], 
    system_instruction: dict, 
    model: str,
    tools: List[dict] = None,
    tool_config: dict = None
) -> Tuple[str, List[dict], List[dict], List[dict]]:
    """将 Gemini 消息格式转换为 Kiro 格式
    
    增强：
    - 支持 functionCall 和 functionResponse
    - 支持 tool_config
    
    Returns:
        (user_content, history, tool_results, kiro_tools)
    """
    history = []
    user_content = ""
    current_tool_results = []
    pending_tool_results = []
    
    # 处理 system instruction
    system_text = ""
    if system_instruction:
        parts = system_instruction.get("parts", [])
        system_text = " ".join(p.get("text", "") for p in parts if "text" in p)
    
    # 处理 tool_config（类似 tool_choice）
    tool_instruction = ""
    if tool_config:
        mode = tool_config.get("functionCallingConfig", {}).get("mode", "")
        if mode in ("ANY", "REQUIRED"):
            tool_instruction = "\n\n[CRITICAL INSTRUCTION] You MUST use one of the provided tools to respond. Do NOT respond with plain text."
    
    for i, content in enumerate(contents):
        role = content.get("role", "user")
        parts = content.get("parts", [])
        is_last = (i == len(contents) - 1)
        
        # 提取文本和工具调用
        text_parts = []
        tool_calls = []
        tool_responses = []
        
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                # Gemini 的工具调用
                fc = part["functionCall"]
                tool_calls.append({
                    "toolUseId": fc.get("name", "") + "_" + str(i),  # Gemini 没有 ID，生成一个
                    "name": fc.get("name", ""),
                    "input": fc.get("args", {})
                })
            elif "functionResponse" in part:
                # Gemini 的工具响应
                fr = part["functionResponse"]
                response_content = fr.get("response", {})
                if isinstance(response_content, dict):
                    response_text = json.dumps(response_content)
                else:
                    response_text = str(response_content)
                
                tool_responses.append({
                    "content": [{"text": response_text}],
                    "status": "success",
                    "toolUseId": fr.get("name", "") + "_" + str(i - 1)  # 匹配上一个调用
                })
        
        text = " ".join(text_parts)
        
        if role == "user":
            # 处理待处理的 tool responses
            if pending_tool_results:
                seen_ids = set()
                unique_results = []
                for tr in pending_tool_results:
                    if tr["toolUseId"] not in seen_ids:
                        seen_ids.add(tr["toolUseId"])
                        unique_results.append(tr)
                
                history.append({
                    "userInputMessage": {
                        "content": "Tool results provided.",
                        "modelId": model,
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": unique_results
                        }
                    }
                })
                pending_tool_results = []
            
            # 处理 functionResponse（用户消息中的工具响应）
            if tool_responses:
                pending_tool_results.extend(tool_responses)
            
            # 合并 system prompt
            if system_text and not history:
                text = f"{system_text}{tool_instruction}\n\n{text}"
            
            if is_last:
                user_content = text
                if pending_tool_results:
                    current_tool_results = pending_tool_results
                    pending_tool_results = []
            else:
                if text:
                    history.append({
                        "userInputMessage": {
                            "content": text,
                            "modelId": model,
                            "origin": "AI_EDITOR"
                        }
                    })
        
        elif role == "model":
            # 处理待处理的 tool responses
            if pending_tool_results:
                seen_ids = set()
                unique_results = []
                for tr in pending_tool_results:
                    if tr["toolUseId"] not in seen_ids:
                        seen_ids.add(tr["toolUseId"])
                        unique_results.append(tr)
                
                history.append({
                    "userInputMessage": {
                        "content": "Tool results provided.",
                        "modelId": model,
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": unique_results
                        }
                    }
                })
                pending_tool_results = []
            
            assistant_text = text if text else "I understand."
            
            assistant_msg = {
                "assistantResponseMessage": {
                    "content": assistant_text
                }
            }
            # 只有在有 toolUses 时才添加这个字段
            if tool_calls:
                assistant_msg["assistantResponseMessage"]["toolUses"] = tool_calls
            
            history.append(assistant_msg)
    
    # 处理末尾的 tool results
    if pending_tool_results:
        current_tool_results = pending_tool_results
        if not user_content:
            user_content = "Tool results provided."
    
    # 如果没有用户消息
    if not user_content:
        if contents:
            last_parts = contents[-1].get("parts", [])
            user_content = " ".join(p.get("text", "") for p in last_parts if "text" in p)
        if not user_content:
            user_content = "Continue"
    
    # 修复历史交替
    history = fix_history_alternation(history, model)
    
    # 移除最后一条（当前用户消息）
    if history and "userInputMessage" in history[-1]:
        history = history[:-1]
    
    # 转换工具
    kiro_tools = convert_gemini_tools_to_kiro(tools) if tools else []
    
    return user_content, history, current_tool_results, kiro_tools


def convert_kiro_response_to_gemini(result: dict, model: str) -> dict:
    """将 Kiro 响应转换为 Gemini 格式"""
    text = "".join(result.get("content", []))
    tool_uses = result.get("tool_uses", [])
    
    parts = []
    
    # 添加文本部分
    if text:
        parts.append({"text": text})
    
    # 添加工具调用
    for tool_use in tool_uses:
        if tool_use.get("type") == "tool_use":
            parts.append({
                "functionCall": {
                    "name": tool_use.get("name", ""),
                    "args": tool_use.get("input", {})
                }
            })
    
    # 映射 stop_reason
    stop_reason = result.get("stop_reason", "STOP")
    finish_reason = "STOP"
    if tool_uses:
        finish_reason = "TOOL_CALLS"
    elif stop_reason == "max_tokens":
        finish_reason = "MAX_TOKENS"
    
    return {
        "candidates": [{
            "content": {
                "parts": parts,
                "role": "model"
            },
            "finishReason": finish_reason,
            "index": 0
        }],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 100,
            "totalTokenCount": 200
        }
    }


# ==================== Kiro Stream Converter ====================

class KiroStreamConverter:
    """Convert Kiro streaming response to Anthropic SSE format"""
    
    def __init__(self, thinking_start_tag: str = "<thinking>", thinking_end_tag: str = "</thinking>"):
        self.thinking_start_tag = thinking_start_tag
        self.thinking_end_tag = thinking_end_tag
        self.reset()
    
    def reset(self):
        """Reset converter state"""
        self.stream_state = {
            "buffer": "",
            "in_thinking": False,
            "thinking_extracted": False,
            "thinking_block_index": None,
            "text_block_index": None,
            "next_block_index": 0,
            "stopped_blocks": set()
        }
        self.tool_calls = []
        self.current_tool_call = None
        self.total_content = ""
        self.last_content_event = None
    
    def ensure_block_start(self, block_type: str) -> list:
        """Ensure a content block is started and return start events"""
        if block_type == "thinking":
            if self.stream_state["thinking_block_index"] is not None:
                return []
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            self.stream_state["thinking_block_index"] = idx
            return [{"type": "content_block_start", "index": idx, "content_block": {"type": "thinking", "thinking": ""}}]
        if block_type == "text":
            if self.stream_state["text_block_index"] is not None:
                return []
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            self.stream_state["text_block_index"] = idx
            return [{"type": "content_block_start", "index": idx, "content_block": {"type": "text", "text": ""}}]
        return []
    
    def stop_block(self, index: int | None) -> list:
        """Stop a content block and return stop events"""
        if index is None or index in self.stream_state["stopped_blocks"]:
            return []
        self.stream_state["stopped_blocks"].add(index)
        return [{"type": "content_block_stop", "index": index}]
    
    def create_text_delta_events(self, text: str) -> list:
        """Create text delta events"""
        events = []
        events.extend(self.ensure_block_start("text"))
        events.append({"type": "content_block_delta", "index": self.stream_state["text_block_index"], "delta": {"type": "text_delta", "text": text}})
        return events
    
    def create_thinking_delta_events(self, thinking_text: str) -> list:
        """Create thinking delta events"""
        events = []
        events.extend(self.ensure_block_start("thinking"))
        events.append({"type": "content_block_delta", "index": self.stream_state["thinking_block_index"], "delta": {"type": "thinking_delta", "thinking": thinking_text}})
        return events
    
    def process_content_event(self, content_piece: str, thinking_requested: bool) -> list:
        """Process a content event and return SSE events
        
        Args:
            content_piece: Content text from Kiro
            thinking_requested: Whether thinking mode is enabled
            
        Returns:
            List of SSE events to yield
        """
        from utils.text import find_real_tag
        
        if content_piece == self.last_content_event:
            return []
        self.last_content_event = content_piece
        self.total_content += content_piece
        
        if not thinking_requested:
            return self.create_text_delta_events(content_piece)
        
        self.stream_state["buffer"] += content_piece
        pending = []
        
        while self.stream_state["buffer"]:
            if not self.stream_state["in_thinking"] and not self.stream_state["thinking_extracted"]:
                start_pos = find_real_tag(self.stream_state["buffer"], self.thinking_start_tag)
                if start_pos != -1:
                    before = self.stream_state["buffer"][:start_pos]
                    if before:
                        pending.extend(self.create_text_delta_events(before))
                    self.stream_state["buffer"] = self.stream_state["buffer"][start_pos + len(self.thinking_start_tag):]
                    self.stream_state["in_thinking"] = True
                    continue
                safe_len = max(0, len(self.stream_state["buffer"]) - len(self.thinking_start_tag))
                if safe_len > 0:
                    safe_text = self.stream_state["buffer"][:safe_len]
                    if safe_text:
                        pending.extend(self.create_text_delta_events(safe_text))
                    self.stream_state["buffer"] = self.stream_state["buffer"][safe_len:]
                break
            
            if self.stream_state["in_thinking"]:
                end_pos = find_real_tag(self.stream_state["buffer"], self.thinking_end_tag)
                if end_pos != -1:
                    thinking_part = self.stream_state["buffer"][:end_pos]
                    if thinking_part:
                        pending.extend(self.create_thinking_delta_events(thinking_part))
                    self.stream_state["buffer"] = self.stream_state["buffer"][end_pos + len(self.thinking_end_tag):]
                    self.stream_state["in_thinking"] = False
                    self.stream_state["thinking_extracted"] = True
                    pending.extend(self.create_thinking_delta_events(""))
                    pending.extend(self.stop_block(self.stream_state["thinking_block_index"]))
                    if self.stream_state["buffer"].startswith("\n\n"):
                        self.stream_state["buffer"] = self.stream_state["buffer"][2:]
                    continue
                safe_len = max(0, len(self.stream_state["buffer"]) - len(self.thinking_end_tag))
                if safe_len > 0:
                    safe_thinking = self.stream_state["buffer"][:safe_len]
                    if safe_thinking:
                        pending.extend(self.create_thinking_delta_events(safe_thinking))
                    self.stream_state["buffer"] = self.stream_state["buffer"][safe_len:]
                break
            
            if self.stream_state["thinking_extracted"]:
                rest = self.stream_state["buffer"]
                self.stream_state["buffer"] = ""
                if rest:
                    pending.extend(self.create_text_delta_events(rest))
                break
        
        return pending
    
    def process_tool_use_event(self, tool_data: dict) -> None:
        """Process a tool use event
        
        Args:
            tool_data: Tool data from Kiro
        """
        if tool_data.get("name"):
            self.total_content += tool_data["name"]
        if tool_data.get("input"):
            self.total_content += tool_data["input"]
        
        if tool_data.get("name") and tool_data.get("toolUseId"):
            if self.current_tool_call and self.current_tool_call["toolUseId"] == tool_data["toolUseId"]:
                self.current_tool_call["input"] += tool_data.get("input") or ""
            else:
                if self.current_tool_call:
                    try:
                        self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
                    except Exception:
                        pass
                    self.tool_calls.append(self.current_tool_call)
                self.current_tool_call = {
                    "toolUseId": tool_data["toolUseId"],
                    "name": tool_data["name"],
                    "input": tool_data.get("input") or ""
                }
            if tool_data.get("stop"):
                try:
                    self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
                except Exception:
                    pass
                self.tool_calls.append(self.current_tool_call)
                self.current_tool_call = None
    
    def process_tool_use_input_event(self, input_piece: str) -> None:
        """Process a tool use input event"""
        if input_piece:
            self.total_content += input_piece
        if self.current_tool_call:
            self.current_tool_call["input"] += input_piece or ""
    
    def process_tool_use_stop_event(self, stop: bool) -> None:
        """Process a tool use stop event"""
        if self.current_tool_call and stop:
            try:
                self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
            except Exception:
                pass
            self.tool_calls.append(self.current_tool_call)
            self.current_tool_call = None
    
    def finalize_thinking_buffer(self, thinking_requested: bool) -> list:
        """Finalize any remaining thinking buffer content
        
        Returns:
            List of SSE events to yield
        """
        if not thinking_requested or not self.stream_state["buffer"]:
            return []
        
        events = []
        if self.stream_state["in_thinking"]:
            events.extend(self.create_thinking_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
            events.extend(self.create_thinking_delta_events(""))
            events.extend(self.stop_block(self.stream_state["thinking_block_index"]))
        elif not self.stream_state["thinking_extracted"]:
            events.extend(self.create_text_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
        else:
            events.extend(self.create_text_delta_events(self.stream_state["buffer"]))
            self.stream_state["buffer"] = ""
        
        return events
    
    def finalize_current_tool_call(self) -> None:
        """Finalize any pending tool call"""
        if self.current_tool_call:
            try:
                self.current_tool_call["input"] = json.loads(self.current_tool_call["input"])
            except Exception:
                pass
            self.tool_calls.append(self.current_tool_call)
            self.current_tool_call = None
    
    def generate_tool_call_events(self) -> list:
        """Generate tool call events for all collected tool calls
        
        Returns:
            List of SSE events for tool calls
        """
        import uuid
        events = []
        
        for tc in self.tool_calls:
            idx = self.stream_state["next_block_index"]
            self.stream_state["next_block_index"] += 1
            tool_id = tc.get("toolUseId") or f"tool_{uuid.uuid4().hex}"
            tool_name = tc.get("name") or ""
            tool_input = tc.get("input")
            partial_json = tool_input if isinstance(tool_input, str) else json.dumps(tool_input or {})
            
            tool_start = {
                "type": "content_block_start",
                "index": idx,
                "content_block": {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}}
            }
            tool_delta = {
                "type": "content_block_delta",
                "index": idx,
                "delta": {"type": "input_json_delta", "partial_json": partial_json}
            }
            tool_stop = {"type": "content_block_stop", "index": idx}
            
            events.extend([tool_start, tool_delta, tool_stop])
        
        return events
    
    def get_total_content(self) -> str:
        """Get total content including tool calls"""
        output_text = self.total_content
        if self.tool_calls:
            output_text += json.dumps(self.tool_calls, ensure_ascii=False)
        return output_text
    
    def get_tool_calls(self) -> list:
        """Get collected tool calls"""
        return self.tool_calls
    
    def get_text_block_index(self) -> int | None:
        """Get text block index"""
        return self.stream_state["text_block_index"]
    
    def parse_aws_event_stream_buffer(self, buffer: str) -> tuple[list, str]:
        """Parse AWS event stream buffer and extract events
        
        Args:
            buffer: Raw buffer string from AWS response
            
        Returns:
            Tuple of (events list, remaining buffer)
        """
        import re
        events = []
        remaining = buffer
        search_start = 0
        while True:
            content_start = remaining.find('{"content":', search_start)
            name_start = remaining.find('{"name":', search_start)
            followup_start = remaining.find('{"followupPrompt":', search_start)
            input_start = remaining.find('{"input":', search_start)
            stop_start = remaining.find('{"stop":', search_start)
            context_usage_start = remaining.find('{"contextUsagePercentage":', search_start)
            usage_start = remaining.find('{"unit":', search_start)
            candidates = [pos for pos in [content_start, name_start, followup_start, input_start, stop_start, context_usage_start, usage_start] if pos >= 0]
            if not candidates:
                break
            json_start = min(candidates)
            brace_count = 0
            json_end = -1
            in_string = False
            escape_next = False
            for i in range(json_start, len(remaining)):
                char = remaining[i]
                if escape_next:
                    escape_next = False
                    continue
                if char == "\\":
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i
                            break
            if json_end < 0:
                remaining = remaining[json_start:]
                break
            json_str = remaining[json_start:json_end + 1]
            try:
                parsed = json.loads(json_str)
                if parsed.get("content") is not None and not parsed.get("followupPrompt"):
                    events.append({"type": "content", "data": parsed.get("content", "")})
                elif parsed.get("name") and parsed.get("toolUseId"):
                    events.append({
                        "type": "toolUse",
                        "data": {
                            "name": parsed.get("name"),
                            "toolUseId": parsed.get("toolUseId"),
                            "input": parsed.get("input", ""),
                            "stop": parsed.get("stop", False)
                        }
                    })
                elif "input" in parsed and not parsed.get("name"):
                    events.append({"type": "toolUseInput", "data": {"input": parsed.get("input", "")}})
                elif "stop" in parsed and "contextUsagePercentage" not in parsed:
                    events.append({"type": "toolUseStop", "data": {"stop": parsed.get("stop")}})
                elif "usage" in parsed:
                    events.append({
                        "type": "usage",
                        "data": {
                            "usage": parsed.get("usage"),
                            "unit": parsed.get("unit"),
                            "unitPlural": parsed.get("unitPlural")
                        }
                    })
            except Exception:
                pass
            search_start = json_end + 1
            if search_start >= len(remaining):
                remaining = ""
                break
        if search_start > 0 and remaining:
            remaining = remaining[search_start:]
        return events, remaining
