"""
XNBot主程序入口
"""

import asyncio
import logging
import os
import argparse
import signal

from xnbot.core.bot import Bot
from xnbot.config.config_manager import ConfigManager
from xnbot.utils.color_formatter import setup_colored_logging

# 设置日志
def setup_logging(log_level: str = "INFO"):
    """
    设置日志

    Args:
        log_level: 日志级别
    """
    # 创建日志目录
    os.makedirs("logs", exist_ok=True)

    # 使用彩色日志格式化器
    setup_colored_logging(
        level=log_level,
        log_file=os.path.join("logs", "xnbot.log")
    )

# 解析命令行参数
def parse_args():
    """
    解析命令行参数

    Returns:
        解析后的参数
    """
    parser = argparse.ArgumentParser(description="XNBot - 基于微信API的异步机器人")
    parser.add_argument("-c", "--config", default="config.json", help="配置文件路径")
    parser.add_argument("-l", "--log-level", default="INFO", help="日志级别")
    return parser.parse_args()

# 主函数
async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()

    # 设置日志
    setup_logging(args.log_level)

    # 创建机器人实例
    bot = Bot(args.config)

    # 设置信号处理
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot)))
    except NotImplementedError:
        # Windows不支持add_signal_handler
        pass

    # 启动机器人
    try:
        await bot.start()

        # 保持运行
        while bot.running:
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"运行时出错: {e}")
    finally:
        await bot.stop()

# 关闭函数
async def shutdown(bot: Bot):
    """
    关闭函数

    Args:
        bot: 机器人实例
    """
    logging.info("正在关闭...")
    await bot.stop()

# 入口点
if __name__ == "__main__":
    asyncio.run(main())
