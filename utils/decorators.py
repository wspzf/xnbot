"""
装饰器工具
提供插件开发中使用的装饰器
"""

import functools
import inspect
import logging
from typing import Callable, Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)

def on_message(msg_type: Optional[int] = None, priority: int = 100):
    """
    消息处理装饰器

    Args:
        msg_type: 消息类型，None表示所有类型
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, message):
            # 检查消息类型
            if msg_type is not None and message.get("MsgType") != msg_type:
                return False

            # 调用处理函数
            return await func(self, message)

        # 添加元数据
        wrapper.__on_message__ = True
        wrapper.__msg_type__ = msg_type
        wrapper.__priority__ = priority

        return wrapper

    return decorator

def on_text_message(priority: int = 100):
    """
    文本消息处理装饰器

    Args:
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    return on_message(msg_type=1, priority=priority)

def on_image_message(priority: int = 100):
    """
    图片消息处理装饰器

    Args:
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    return on_message(msg_type=3, priority=priority)

def on_voice_message(priority: int = 100):
    """
    语音消息处理装饰器

    Args:
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    return on_message(msg_type=34, priority=priority)

def on_video_message(priority: int = 100):
    """
    视频消息处理装饰器

    Args:
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    return on_message(msg_type=43, priority=priority)

def on_command(command: str, prefix: str = "/", priority: int = 100):
    """
    命令处理装饰器

    Args:
        command: 命令名称
        prefix: 命令前缀
        priority: 优先级，数字越小优先级越高

    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, message):
            # 检查是否是文本消息
            if message.get("MsgType") != 1:
                return False

            # 获取消息内容
            from xnbot.utils.message_parser import get_message_content
            content = get_message_content(message)

            # 检查是否是命令
            if not content.startswith(prefix):
                return False

            # 解析命令
            parts = content[len(prefix):].split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # 检查命令是否匹配
            if cmd != command.lower():
                return False

            # 调用处理函数
            return await func(self, message, args)

        # 添加元数据
        wrapper.__on_command__ = True
        wrapper.__command__ = command
        wrapper.__prefix__ = prefix
        wrapper.__priority__ = priority

        return wrapper

    return decorator

def admin_required(func):
    """
    管理员权限装饰器

    Args:
        func: 处理函数

    Returns:
        装饰后的函数
    """
    @functools.wraps(func)
    async def wrapper(self, message, *args, **kwargs):
        # 获取发送者ID
        from xnbot.utils.message_parser import parse_text_message
        from_user, _, _ = parse_text_message(message)

        # 检查是否是管理员
        admin_wxids = self.bot.config.get("bot", {}).get("admin_wxids", [])
        if from_user not in admin_wxids:
            return False

        # 调用处理函数
        return await func(self, message, *args, **kwargs)

    return wrapper

def on_at_message(priority: int = 100):
    """
    被@消息处理装饰器
    
    Args:
        priority: 优先级，数字越小优先级越高
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, message):
            # 检查是否是文本消息
            if message.get("MsgType") != 1:
                return False
                
            # 检查是否包含@
            content = message.get("Content", "")
            if "@" not in content:
                return False
                
            # 检查是否@了机器人
            # 这里需要根据实际情况添加检查逻辑
            robot_names = getattr(self, "robot_names", [])
            robot_wxid = getattr(self.bot, "wxid", None)
            is_at = False
            
            # 检查@昵称
            for name in robot_names:
                if f"@{name}" in content:
                    is_at = True
                    break
                    
            # 检查@wxid
            if robot_wxid and f"@{robot_wxid}" in content:
                is_at = True
                
            if not is_at:
                return False
                
            # 调用处理函数
            return await func(self, message)
            
        # 添加元数据
        wrapper.__on_message__ = True
        wrapper.__msg_type__ = 1  # 文本消息
        wrapper.__is_at__ = True
        wrapper.__priority__ = priority
        
        return wrapper
        
    return decorator

def on_quote_message(priority: int = 100):
    """
    引用消息处理装饰器
    
    Args:
        priority: 优先级，数字越小优先级越高
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, message):
            # 检查是否是文本消息
            if message.get("MsgType") != 1:
                return False
                
            # 检查是否是引用消息
            content = message.get("Content", "")
            if "<quote>" not in content and "引用" not in content:
                return False
                
            # 调用处理函数
            return await func(self, message)
            
        # 添加元数据
        wrapper.__on_message__ = True
        wrapper.__msg_type__ = 1  # 文本消息
        wrapper.__is_quote__ = True
        wrapper.__priority__ = priority
        
        return wrapper
        
    return decorator

def on_file_message(priority: int = 100):
    """
    文件消息处理装饰器
    
    Args:
        priority: 优先级，数字越小优先级越高
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, message):
            # 检查是否是文件消息
            # 根据微信API的消息类型定义调整
            file_msg_types = [49]  # 可能需要根据实际情况调整
            if message.get("MsgType") not in file_msg_types:
                return False
                
            # 可以添加更多的文件类型检查逻辑
                
            # 调用处理函数
            return await func(self, message)
            
        # 添加元数据
        wrapper.__on_message__ = True
        wrapper.__msg_type__ = 49  # 文件消息
        wrapper.__priority__ = priority
        
        return wrapper
        
    return decorator
