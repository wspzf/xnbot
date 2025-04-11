"""
Dify插件
提供Dify AI聊天功能
"""

from xnbot.core.plugin_manager import PluginBase
from xnbot.utils.decorators import on_message
from loguru import logger
from .main import Dify as DifyImpl

class DifyPlugin(PluginBase):
    """Dify AI聊天插件"""

    name = "Dify"
    description = "Dify AI聊天插件"
    version = "1.3.2"
    author = "老夏的金库"

    def __init__(self, bot):
        """初始化插件"""
        super().__init__(bot)
        # 创建实际的实现实例
        self.impl = DifyImpl(bot)
        logger.info("Dify插件已初始化")

    async def on_load(self) -> bool:
        """插件加载时调用"""
        logger.info("Dify插件正在加载...")
        return await self.impl.on_load()

    async def on_unload(self) -> bool:
        """插件卸载时调用"""
        logger.info("Dify插件正在卸载...")
        return await self.impl.on_unload()

    @on_message(priority=100)  # 设置为标准优先级
    async def on_message(self, message: dict) -> bool:
        """处理消息"""
        try:
            # 检查是否是命令消息，如果是则跳过
            content = message.get("Content", "")
            if isinstance(content, dict) and "string" in content:
                content = content["string"]

            # 检查是否是命令
            if isinstance(content, str) and content.startswith("/"):
                logger.info(f"Dify插件: 检测到命令 {content}，跳过处理")
                return False  # 跳过命令处理，让admin插件处理

            return await self.impl.on_message(message)
        except Exception as e:
            logger.error(f"Dify插件处理消息时出错: {e}")
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
            return False
