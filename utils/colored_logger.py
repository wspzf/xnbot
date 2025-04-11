"""
彩色日志模块
提供彩色日志输出功能
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any

# ANSI 颜色代码
RESET = "\033[0m"
BOLD = "\033[1m"
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BRIGHT_BLACK = "\033[90m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

# 日志级别颜色映射
LEVEL_COLORS = {
    logging.DEBUG: BRIGHT_BLACK,
    logging.INFO: GREEN,
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: BRIGHT_RED + BOLD,
}

# 日志级别名称映射
LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, style: str = '%', 
                 colored: bool = True, step_info: bool = False):
        """
        初始化彩色日志格式化器

        Args:
            fmt: 日志格式
            datefmt: 日期格式
            style: 格式化风格
            colored: 是否启用彩色输出
            step_info: 是否显示步骤信息
        """
        super().__init__(fmt, datefmt, style)
        self.colored = colored
        self.step_info = step_info
        self.step_count = 0
        self.total_steps = 0
        
    def set_steps(self, total: int):
        """
        设置总步骤数
        
        Args:
            total: 总步骤数
        """
        self.total_steps = total
        self.step_count = 0
        
    def next_step(self):
        """
        进入下一步
        """
        self.step_count += 1
        if self.step_count > self.total_steps:
            self.step_count = self.total_steps

    def format(self, record):
        """
        格式化日志记录

        Args:
            record: 日志记录

        Returns:
            格式化后的日志字符串
        """
        # 获取原始格式化的消息
        message = super().format(record)
        
        if not self.colored:
            return message
        
        # 获取日志级别对应的颜色
        level_color = LEVEL_COLORS.get(record.levelno, RESET)
        level_name = LEVEL_NAMES.get(record.levelno, "UNKNOWN")
        
        # 格式化日期时间
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建彩色日志消息
        if self.step_info and self.total_steps > 0 and record.levelno == logging.INFO:
            colored_message = f"{BRIGHT_BLACK}{timestamp}{RESET} | {level_color}{level_name}{RESET} | {BOLD}执行步骤 {self.step_count}/{self.total_steps}{RESET} | {record.message}"
        else:
            colored_message = f"{BRIGHT_BLACK}{timestamp}{RESET} | {level_color}{level_name}{RESET} | {record.message}"
        
        # 如果有异常信息，添加到消息中
        if record.exc_info:
            # 获取原始异常信息
            exc_text = self.formatException(record.exc_info)
            colored_message += f"\n{RED}{exc_text}{RESET}"
        
        return colored_message

def setup_colored_logger(level: str = "INFO", log_file: Optional[str] = None, 
                         colored: bool = True, step_info: bool = False):
    """
    设置彩色日志记录器

    Args:
        level: 日志级别
        log_file: 日志文件路径
        colored: 是否启用彩色输出
        step_info: 是否显示步骤信息
    
    Returns:
        根日志记录器
    """
    # 获取根日志记录器
    root_logger = logging.getLogger()
    
    # 设置日志级别
    level_num = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(level_num)
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level_num)
    
    # 设置格式化器
    formatter = ColoredFormatter(colored=colored, step_info=step_info)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到根日志记录器
    root_logger.addHandler(console_handler)
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        # 确保日志目录存在
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level_num)
        
        # 设置文件格式化器（不带颜色）
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        
        # 添加处理器到根日志记录器
        root_logger.addHandler(file_handler)
    
    # 设置第三方库的日志级别
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    
    return root_logger, formatter

# 全局格式化器实例，用于步骤信息
global_formatter = None

def set_total_steps(total: int):
    """
    设置总步骤数
    
    Args:
        total: 总步骤数
    """
    global global_formatter
    if global_formatter:
        global_formatter.set_steps(total)

def next_step():
    """
    进入下一步
    """
    global global_formatter
    if global_formatter:
        global_formatter.next_step()
