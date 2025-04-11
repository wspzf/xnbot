"""
SimplePlugin 主要实现
"""

from xnbot.core.plugin_manager import PluginBase
from xnbot.utils.decorators import on_text_message, on_command, on_message
import logging
import toml
import os

logger = logging.getLogger(__name__)

class SimplePlugin(PluginBase):
    """简单插件示例"""

    name = "simple"
    description = "一个简单的示例插件，展示XNBot插件开发的基本结构"
    version = "1.0.0"
    author = "XNBot"

    # __init__ 方法已移动到下面

    async def on_load(self) -> bool:
        """插件加载时调用"""
        logger.info("SimplePlugin 正在加载...")

        # 加载配置文件
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        try:
            if os.path.exists(config_path):
                self.config = toml.load(config_path)
                logger.info(f"已加载配置文件: {config_path}")
            else:
                logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
                self.config = {
                    "reply_message": "这是一个简单的回复",
                    "enable_auto_reply": True
                }
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self.config = {
                "reply_message": "这是一个简单的回复",
                "enable_auto_reply": True
            }

        logger.info("SimplePlugin 已加载")
        return True

    async def on_unload(self) -> bool:
        """插件卸载时调用"""
        logger.info("SimplePlugin 正在卸载...")
        logger.info(f"插件运行期间共处理了 {self.message_count} 条消息")
        logger.info("SimplePlugin 已卸载")
        return True

    # 删除多余的方法，只保留on_message方法

    # 插件管理器会直接调用这个方法
    @on_message(priority=10)  # 设置优先级为50
    async def on_message(self, message: dict) -> bool:
        """处理所有消息的方法"""
        # 这个方法会被插件管理器直接调用
        logger.info("SimplePlugin on_message 被调用，优先级为50")

        # 检查是否是命令消息
        content = message.get("Content")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        # 如果是 /simple 命令，直接调用命令处理器
        if content.startswith("/simple"):
            logger.info("SimplePlugin 检测到 /simple 命令，调用命令处理器")
            # 解析参数
            args = content[7:].strip() if len(content) > 7 else ""
            # 手动处理命令，而不是调用装饰器方法
            # 获取发送者
            from_user = message.get("FromUserName")
            if isinstance(from_user, dict) and "string" in from_user:
                from_user = from_user["string"]

            # 增加消息计数
            self.message_count += 1

            # 发送回复
            reply = self.config.get("reply_message", "这是一个简单的回复")
            if args:
                await self.bot.send_text(from_user, f"{reply}，你说: {args}")
            else:
                await self.bot.send_text(from_user, reply)

            return True

        # 返回 False 表示未处理消息，允许其他插件处理
        return False

    # 在初始化时设置优先级
    def __init__(self, bot):
        super().__init__(bot)
        self.config = {}
        self.message_count = 0
        self.config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        self.config_last_modified = 0

        # 不再手动设置优先级，而是使用装饰器设置
        logger.info("SimplePlugin 已初始化")

    # 设置优先级为50
    @on_text_message(priority=60)
    async def handle_text(self, message: dict) -> bool:
        """处理文本消息"""
        # 如果未启用自动回复，直接返回
        if not self.config.get("enable_auto_reply", True):
            return False

        # 获取消息内容
        content = message.get("Content")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        # 获取发送者
        from_user = message.get("FromUserName")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        # 检查是否包含关键词
        keywords = self.config.get("keywords", ["simple", "简单"])

        if any(keyword in content.lower() for keyword in keywords):
            # 增加消息计数
            self.message_count += 1

            # 发送回复
            reply = self.config.get("reply_message", "这是一个简单的回复")
            await self.bot.send_text(from_user, reply)
            return True

        return False
