"""
插件管理器
负责加载、管理和调用插件
"""

import os
import sys
import importlib
import inspect
import logging
import asyncio
from typing import Dict, List, Callable, Any, Optional, Set, Type, Union
import pkgutil

from xnbot.api.wechat_client import WeChatAPIClient

logger = logging.getLogger(__name__)

class PluginBase:
    """插件基类"""

    # 插件元数据
    name = "base_plugin"
    description = "基础插件"
    version = "1.0.0"
    author = "XNBot"

    def __init__(self, bot):
        """
        初始化插件

        Args:
            bot: 机器人实例
        """
        self.bot = bot
        self.enabled = False
        self.config = {}

    async def on_load(self) -> bool:
        """
        插件加载时调用

        Returns:
            加载是否成功
        """
        self.enabled = True
        return True

    async def on_unload(self) -> bool:
        """
        插件卸载时调用

        Returns:
            卸载是否成功
        """
        self.enabled = False
        return True

    async def on_message(self, message: Dict) -> bool:
        """
        收到消息时调用

        Args:
            message: 消息数据

        Returns:
            是否处理了消息
        """
        return False

    async def on_enable(self) -> bool:
        """
        插件启用时调用

        Returns:
            启用是否成功
        """
        self.enabled = True
        return True

    async def on_disable(self) -> bool:
        """
        插件禁用时调用

        Returns:
            禁用是否成功
        """
        self.enabled = False
        return True

    async def on_config_change(self, config: Dict) -> bool:
        """
        配置变更时调用

        Args:
            config: 新配置

        Returns:
            配置变更是否成功
        """
        self.config = config
        return True


class PluginManager:
    """插件管理器"""

    def __init__(self, bot):
        """
        初始化插件管理器

        Args:
            bot: 机器人实例
        """
        self.bot = bot
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_dirs = ["plugins"]
        self.message_handlers: List[Callable] = []

    def add_plugin_dir(self, directory: str):
        """
        添加插件目录

        Args:
            directory: 插件目录路径
        """
        if directory not in self.plugin_dirs and os.path.isdir(directory):
            self.plugin_dirs.append(directory)

    async def load_plugins(self):
        """加载所有插件"""
        logger.info(f"开始加载插件，插件目录: {self.plugin_dirs}")

        # 清除已加载的插件
        self.plugins.clear()
        logger.info("已清除已加载的插件")

        for plugin_dir in self.plugin_dirs:
            logger.info(f"从目录 {plugin_dir} 加载插件")
            await self._load_plugins_from_dir(plugin_dir)
        logger.info(f"插件加载完成，已加载: {list(self.plugins.keys())}")

    async def _load_plugins_from_dir(self, directory: str):
        """
        从目录加载插件

        Args:
            directory: 插件目录路径
        """
        logger.info(f"开始从目录 {directory} 加载插件")

        if not os.path.exists(directory):
            logger.warning(f"插件目录不存在: {directory}")
            return

        # 确保目录在Python路径中
        if directory not in sys.path:
            sys.path.insert(0, os.path.abspath(directory))
            logger.info(f"将 {directory} 添加到Python路径")
        else:
            # 如果目录已经在Python路径中，确保它是第一个
            sys.path.remove(directory)
            sys.path.insert(0, os.path.abspath(directory))
            logger.info(f"重新排序 Python 路径，将 {directory} 放在最前面")

        # 遍历目录中的所有模块
        modules = list(pkgutil.iter_modules([directory]))
        logger.info(f"在目录 {directory} 中找到 {len(modules)} 个模块")

        for _, name, is_pkg in modules:
            logger.info(f"检查模块: {name}, 是否为包: {is_pkg}")

            if is_pkg:  # 如果是包
                try:
                    # 导入包
                    logger.info(f"尝试导入包: {name}")
                    # 强制重新加载模块
                    if name in sys.modules:
                        logger.info(f"模块 {name} 已存在，强制重新加载")
                        # 先删除模块缓存
                        del sys.modules[name]
                        # 然后重新导入
                        module = importlib.import_module(name)
                        logger.info(f"模块 {name} 已重新导入")
                    else:
                        module = importlib.import_module(name)
                        logger.info(f"模块 {name} 导入成功")

                    # 强制重新加载所有子模块
                    if hasattr(module, '__path__'):
                        # 这是一个包，递归重新加载子模块
                        for submodule_name in list(sys.modules.keys()):
                            if submodule_name.startswith(name + '.') and submodule_name in sys.modules:
                                try:
                                    logger.info(f"重新加载子模块 {submodule_name}")
                                    # 先删除子模块缓存
                                    del sys.modules[submodule_name]
                                    # 然后重新导入
                                    importlib.import_module(submodule_name)
                                    logger.info(f"子模块 {submodule_name} 已重新导入")
                                except Exception as e:
                                    logger.error(f"重新加载子模块 {submodule_name} 失败: {e}")

                    logger.info(f"包 {name} 导入成功")

                    # 查找插件类
                    plugin_classes = []
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (inspect.isclass(attr) and
                            issubclass(attr, PluginBase) and
                            attr is not PluginBase):
                            plugin_classes.append(attr_name)

                    logger.info(f"在包 {name} 中找到的插件类: {plugin_classes}")

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (inspect.isclass(attr) and
                            issubclass(attr, PluginBase) and
                            attr is not PluginBase):

                            # 创建插件实例
                            logger.info(f"创建插件实例: {attr_name}")
                            plugin = attr(self.bot)
                            logger.info(f"插件实例创建成功: {plugin.name}")

                            # 加载插件
                            logger.info(f"尝试加载插件: {plugin.name}")
                            success = await plugin.on_load()
                            if success:
                                self.plugins[plugin.name] = plugin
                                logger.info(f"已加载插件: {plugin.name} v{plugin.version}")

                                # 检查插件配置中的启用状态
                                plugin_config = self.bot.config.get("plugins", {}).get(plugin.name, {})
                                if plugin_config.get("enabled", True):
                                    await plugin.on_enable()
                                    logger.info(f"插件 {plugin.name} 已启用")
                                else:
                                    logger.info(f"插件 {plugin.name} 在配置中被禁用")
                            else:
                                logger.warning(f"插件加载失败: {plugin.name}")

                except Exception as e:
                    logger.error(f"加载插件 {name} 时出错: {e}")
                    # 打印异常详情
                    import traceback
                    logger.error(f"异常详情: {traceback.format_exc()}")

    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        卸载插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功卸载
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            success = await plugin.on_unload()
            if success:
                del self.plugins[plugin_name]
                logger.info(f"已卸载插件: {plugin_name}")
                return True
            else:
                logger.warning(f"插件卸载失败: {plugin_name}")
        return False

    async def enable_plugin(self, plugin_name: str) -> bool:
        """
        启用插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功启用
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            success = await plugin.on_enable()
            if success:
                logger.info(f"已启用插件: {plugin_name}")
                return True
            else:
                logger.warning(f"插件启用失败: {plugin_name}")
        return False

    async def disable_plugin(self, plugin_name: str) -> bool:
        """
        禁用插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功禁用
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            success = await plugin.on_disable()
            if success:
                logger.info(f"已禁用插件: {plugin_name}")
                return True
            else:
                logger.warning(f"插件禁用失败: {plugin_name}")
        return False

    async def handle_message(self, message: Dict):
        """
        处理消息

        Args:
            message: 消息数据
        """
        logger.info(f"插件管理器开始处理消息: {message}")
        logger.info(f"当前加载的插件: {list(self.plugins.keys())}")

        # 获取消息类型
        msg_type = message.get("MsgType")
        content = message.get("Content")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        # 检查是否是命令消息
        is_command = False
        command = ""
        args = ""
        if msg_type == 1 and isinstance(content, str) and content.startswith("/"):
            is_command = True
            parts = content[1:].split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            logger.info(f"检测到命令: {command}, 参数: {args}")

        # 收集所有插件的所有处理方法
        handlers_with_priority = []

        for plugin_name, plugin in self.plugins.items():
            if not plugin.enabled:
                continue

            # 1. 收集 on_message 方法
            on_message_method = getattr(plugin, "on_message", None)
            if on_message_method:
                # 获取优先级
                priority = 100  # 默认优先级

                # 首先检查插件实例是否有__priority__属性
                if hasattr(plugin, "__priority__"):
                    priority = getattr(plugin, "__priority__")
                    logger.info(f"插件 {plugin_name} 实例有__priority__属性: {priority}")
                # 然后检查on_message方法是否有__priority__属性
                elif hasattr(on_message_method, "__priority__"):
                    priority = getattr(on_message_method, "__priority__")
                    logger.info(f"插件 {plugin_name} 的on_message方法有__priority__属性: {priority}")
                # 最后检查装饰器方法是否有__priority__属性
                elif hasattr(on_message_method, "__wrapped__") and hasattr(on_message_method.__wrapped__, "__priority__"):
                    priority = getattr(on_message_method.__wrapped__, "__priority__")
                    logger.info(f"插件 {plugin_name} 的on_message方法的__wrapped__有__priority__属性: {priority}")

                # 如果是管理员插件，给予最高优先级
                if plugin_name.lower() == "admin":
                    priority = 0

                # 添加到处理器列表
                handlers_with_priority.append((plugin_name, plugin, on_message_method, priority, "on_message", None))

            # 2. 收集特定消息类型的处理方法
            for attr_name in dir(plugin):
                attr = getattr(plugin, attr_name)
                if not callable(attr) or attr_name.startswith("_"):
                    continue

                # 检查是否是装饰器方法
                if hasattr(attr, "__on_message__") and attr != on_message_method:
                    # 获取装饰器方法的优先级
                    handler_priority = getattr(attr, "__priority__", 100)
                    handler_msg_type = getattr(attr, "__msg_type__", None)

                    # 检查消息类型是否匹配
                    if handler_msg_type is None or handler_msg_type == msg_type:
                        logger.info(f"插件 {plugin_name} 的 {attr_name} 方法可处理消息类型 {msg_type}, 优先级: {handler_priority}")
                        handlers_with_priority.append((plugin_name, plugin, attr, handler_priority, "specific", None))

                # 3. 收集命令处理方法
                if is_command and hasattr(attr, "__on_command__"):
                    handler_command = getattr(attr, "__command__", "").lower()
                    handler_priority = getattr(attr, "__priority__", 100)

                    # 检查命令是否匹配
                    if handler_command == command:
                        logger.info(f"插件 {plugin_name} 的 {attr_name} 方法可处理命令 {command}, 优先级: {handler_priority}")
                        handlers_with_priority.append((plugin_name, plugin, attr, handler_priority, "command", args))

        # 按优先级排序处理器（数字越小优先级越高）
        handlers_with_priority.sort(key=lambda x: x[3])

        logger.info(f"按优先级排序后的处理器: {[(name, method_type, priority) for name, _, _, priority, method_type, _ in handlers_with_priority]}")

        # 按优先级顺序处理消息
        for plugin_name, plugin, handler, priority, handler_type, handler_args in handlers_with_priority:
            try:
                logger.info(f"尝试使用插件 {plugin_name} 的 {handler_type} 处理器处理消息, 优先级: {priority}")

                # 根据处理器类型调用不同的方法
                if handler_type == "command":
                    handled = await handler(message, handler_args)
                else:
                    handled = await handler(message)

                logger.info(f"插件 {plugin_name} 的 {handler_type} 处理器处理结果: {handled}")

                if handled:
                    logger.info(f"消息被插件 {plugin_name} 的 {handler_type} 处理器成功处理")
                    break
            except Exception as e:
                logger.error(f"插件 {plugin_name} 的 {handler_type} 处理器处理消息时出错: {e}")
                # 打印异常详情
                import traceback
                logger.error(f"异常详情: {traceback.format_exc()}")

        logger.info("所有处理器处理完成")

    def get_plugin_info(self) -> List[Dict]:
        """
        获取所有插件信息

        Returns:
            插件信息列表
        """
        return [
            {
                "name": plugin.name,
                "description": plugin.description,
                "version": plugin.version,
                "author": plugin.author,
                "enabled": plugin.enabled
            }
            for plugin in self.plugins.values()
        ]
