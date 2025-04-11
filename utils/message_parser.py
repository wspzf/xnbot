"""
消息解析工具
提供解析微信消息的功能
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

def parse_text_message(message: Dict) -> Tuple[str, str, str]:
    """
    解析文本消息
    
    Args:
        message: 消息数据
        
    Returns:
        (发送者ID, 接收者ID, 消息内容)
    """
    from_user = message.get("FromUserName", "")
    to_user = message.get("ToUserName", "")
    content = message.get("Content", "")
    
    return from_user, to_user, content

def is_group_message(message: Dict) -> bool:
    """
    判断是否是群消息
    
    Args:
        message: 消息数据
        
    Returns:
        是否是群消息
    """
    from_user = message.get("FromUserName", "")
    return from_user.endswith("@chatroom")

def get_group_sender(message: Dict) -> Optional[str]:
    """
    获取群消息发送者
    
    Args:
        message: 消息数据
        
    Returns:
        群消息发送者ID，如果不是群消息则返回None
    """
    if not is_group_message(message):
        return None
    
    content = message.get("Content", "")
    
    # 尝试从消息内容中提取发送者ID
    # 群消息格式通常为: "发送者ID:消息内容"
    match = re.match(r"^(.*?):(.*)", content)
    if match:
        return match.group(1)
    
    return None

def get_message_content(message: Dict) -> str:
    """
    获取消息内容
    
    Args:
        message: 消息数据
        
    Returns:
        消息内容
    """
    content = message.get("Content", "")
    
    # 如果是群消息，去掉发送者前缀
    if is_group_message(message):
        match = re.match(r"^(.*?):(.*)", content)
        if match:
            return match.group(2).strip()
    
    return content

def is_at_message(message: Dict, target_wxid: str) -> bool:
    """
    判断是否是@消息
    
    Args:
        message: 消息数据
        target_wxid: 目标wxid
        
    Returns:
        是否是@消息
    """
    content = get_message_content(message)
    
    # 检查是否包含@格式
    at_pattern = f"@{target_wxid}"
    return at_pattern in content

def extract_command(content: str, prefix: str = "/") -> Tuple[Optional[str], str]:
    """
    提取命令
    
    Args:
        content: 消息内容
        prefix: 命令前缀
        
    Returns:
        (命令, 参数)，如果不是命令则命令为None
    """
    if not content.startswith(prefix):
        return None, content
    
    parts = content.split(maxsplit=1)
    command = parts[0][len(prefix):]
    args = parts[1] if len(parts) > 1 else ""
    
    return command, args
