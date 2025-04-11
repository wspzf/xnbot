"""
管理员插件
提供机器人管理功能
"""

from xnbot.core.plugin_manager import PluginBase
from xnbot.utils.decorators import on_message
import logging
import re
import json
import asyncio
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class AdminPlugin(PluginBase):
    """管理员插件"""

    name = "admin"
    description = "提供机器人管理功能"
    version = "1.0.0"
    author = "XNBot"

    def __init__(self, bot):
        super().__init__(bot)
        self.commands = {
            "/help": self.cmd_help,
            "/status": self.cmd_status,
            "/plugins": self.cmd_plugins,
            "/enable": self.cmd_enable_plugin,
            "/disable": self.cmd_disable_plugin,
            "/reload": self.cmd_reload_plugins,
            "/restart": self.cmd_restart
        }

    async def on_load(self) -> bool:
        logger.info("管理员插件已加载")
        return True

    @on_message(priority=99)  # 设置最高优先级
    async def on_message(self, message: dict) -> bool:
        # 检查是否是文本消息
        logger.info(f"Admin插件收到消息: {message}")

        # 检查消息类型
        msg_type = message.get("MsgType")
        logger.info(f"Admin插件: 消息类型={msg_type}")

        if msg_type != 1:  # 假设1是文本消息类型
            logger.info("Admin插件: 不是文本消息，忽略")
            return False  # 返回 False 表示不处理，允许其他插件处理

        # 获取消息内容
        content = message.get("Content", "")
        logger.info(f"Admin插件: 原始内容={content}, 类型={type(content)}")

        # 处理内容可能是字典的情况
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        # 获取发送者wxid
        from_user = message.get("FromUserName", "")
        logger.info(f"Admin插件: 原始发送者={from_user}, 类型={type(from_user)}")

        # 处理发送者可能是字典的情况
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        logger.info(f"Admin插件: 解析后的消息 from={from_user}, content={content}")

        # 检查是否是管理员
        admin_wxids = self.bot.config.get("bot", {}).get("admin_wxids", [])
        logger.info(f"Admin插件: 管理员列表={admin_wxids}")

        if from_user not in admin_wxids:
            logger.info(f"Admin插件: 用户{from_user}不是管理员，忽略")
            return False

        # 检查内容是否为空
        if not content or not content.strip():
            logger.info("Admin插件: 消息内容为空，忽略")
            return False

        # 检查是否是命令
        if not content.startswith("/"):
            logger.info("Admin插件: 不是命令消息，忽略")
            return False  # 返回 False 表示不处理，允许其他插件处理

        # 解析命令
        command_parts = content.strip().split(maxsplit=1)
        command = command_parts[0].lower()
        args = command_parts[1] if len(command_parts) > 1 else ""

        logger.info(f"Admin插件: 解析命令={command}, 参数={args}")

        # 执行命令
        if command in self.commands:
            logger.info(f"Admin插件: 执行命令{command}")
            try:
                await self.commands[command](from_user, args)
                logger.info(f"Admin插件: 命令{command}执行完成")
                return True  # 命令已处理，阻止其他插件处理
            except Exception as e:
                logger.error(f"Admin插件: 执行命令{command}时出错: {e}")
                # 尝试发送错误消息给用户
                try:
                    await self.bot.send_text(from_user, f"执行命令{command}时出错: {e}")
                except Exception as send_error:
                    logger.error(f"Admin插件: 发送错误消息时出错: {send_error}")
                return True  # 返回 True 表示已处理，阻止其他插件处理
        else:
            logger.info(f"Admin插件: 未知命令{command}，允许其他插件处理")
            # 对于未知命令，返回 False 允许其他插件处理
            return False

    async def cmd_help(self, from_user: str, args: str):
        """帮助命令"""
        help_text = """管理员命令：
/help - 显示此帮助
/status - 显示机器人状态
/plugins - 列出所有插件
/enable <插件名> - 启用插件
/disable <插件名> - 禁用插件
/reload - 重新加载所有插件
/restart - 重启机器人
"""
        logger.info(f"Admin插件: 发送帮助信息给 {from_user}")
        result = await self.bot.send_text(from_user, help_text)
        logger.info(f"Admin插件: 发送帮助信息结果: {result}")

    async def cmd_status(self, from_user: str, args: str):
        """状态命令"""
        logger.info(f"Admin插件: 获取机器人状态")
        status = {
            "running": self.bot.running,
            "logged_in": self.bot.logged_in,
            "wxid": self.bot.wxid,
            "plugin_count": len(self.bot.plugin_manager.plugins)
        }

        status_text = f"""机器人状态：
运行中: {'是' if status['running'] else '否'}
已登录: {'是' if status['logged_in'] else '否'}
微信ID: {status['wxid'] or '未登录'}
已加载插件数: {status['plugin_count']}
"""
        logger.info(f"Admin插件: 发送状态信息给 {from_user}:\n{status_text}")
        try:
            result = await self.bot.send_text(from_user, status_text)
            logger.info(f"Admin插件: 发送状态信息结果: {result}")
        except Exception as e:
            logger.error(f"Admin插件: 发送状态信息时出错: {e}")

    async def cmd_plugins(self, from_user: str, args: str):
        """插件列表命令"""
        logger.info(f"Admin插件: 获取插件列表")
        plugins_info = self.bot.plugin_manager.get_plugin_info()
        logger.info(f"Admin插件: 获取到的插件信息: {plugins_info}")

        if not plugins_info:
            logger.info(f"Admin插件: 没有加载任何插件，发送消息给 {from_user}")
            result = await self.bot.send_text(from_user, "没有加载任何插件")
            logger.info(f"Admin插件: 发送消息结果: {result}")
            return

        plugins_text = "已加载的插件：\n"
        for plugin in plugins_info:
            status = "启用" if plugin["enabled"] else "禁用"
            plugins_text += f"{plugin['name']} v{plugin['version']} ({status}) - {plugin['description']}\n"

        logger.info(f"Admin插件: 发送插件列表给 {from_user}:\n{plugins_text}")
        result = await self.bot.send_text(from_user, plugins_text)
        logger.info(f"Admin插件: 发送插件列表结果: {result}")

    async def cmd_enable_plugin(self, from_user: str, args: str):
        """启用插件命令"""
        if not args:
            await self.bot.send_text(from_user, "请指定要启用的插件名")
            return

        plugin_name = args.strip()
        success = await self.bot.plugin_manager.enable_plugin(plugin_name)

        if success:
            await self.bot.send_text(from_user, f"插件 {plugin_name} 已启用")
        else:
            await self.bot.send_text(from_user, f"无法启用插件 {plugin_name}")

    async def cmd_disable_plugin(self, from_user: str, args: str):
        """禁用插件命令"""
        if not args:
            await self.bot.send_text(from_user, "请指定要禁用的插件名")
            return

        plugin_name = args.strip()
        success = await self.bot.plugin_manager.disable_plugin(plugin_name)

        if success:
            await self.bot.send_text(from_user, f"插件 {plugin_name} 已禁用")
        else:
            await self.bot.send_text(from_user, f"无法禁用插件 {plugin_name}")

    async def cmd_reload_plugins(self, from_user: str, args: str):
        """重新加载插件命令"""
        await self.bot.send_text(from_user, "正在重新加载插件...")

        # 保存原始插件管理器的必要属性
        original_plugin_dirs = self.bot.plugin_manager.plugin_dirs

        # 卸载所有插件
        for plugin_name in list(self.bot.plugin_manager.plugins.keys()):
            logger.info(f"Admin插件: 卸载插件 {plugin_name}")
            await self.bot.plugin_manager.unload_plugin(plugin_name)

        # 清除模块缓存
        import sys
        import importlib
        import types
        import gc

        # 找出所有插件相关的模块
        plugin_modules = []
        for module_name in list(sys.modules.keys()):
            if module_name.startswith('plugins.') or module_name == 'plugins':
                plugin_modules.append(module_name)

        # 从 sys.modules 中删除插件模块
        for module_name in plugin_modules:
            if module_name in sys.modules:
                logger.info(f"Admin插件: 删除模块缓存 {module_name}")
                # 递归删除所有子模块
                module = sys.modules[module_name]
                if hasattr(module, '__path__'):
                    # 这是一个包，递归删除子模块
                    for submodule_name in list(sys.modules.keys()):
                        if submodule_name.startswith(module_name + '.'):
                            logger.info(f"Admin插件: 删除子模块缓存 {submodule_name}")
                            del sys.modules[submodule_name]
                del sys.modules[module_name]

        # 强制运行垃圾回收，清除内存中的旧对象
        logger.info("Admin插件: 运行垃圾回收")
        gc.collect()

        # 重新创建插件管理器
        logger.info("Admin插件: 重新创建插件管理器")
        from xnbot.core.plugin_manager import PluginManager
        self.bot.plugin_manager = PluginManager(self.bot)

        # 恢复插件目录设置
        self.bot.plugin_manager.plugin_dirs = original_plugin_dirs

        # 强制重新导入 plugins 模块
        try:
            # 先尝试导入
            logger.info("Admin插件: 尝试导入 plugins 模块")
            plugins_module = importlib.import_module('plugins')
            # 然后重新加载
            logger.info("Admin插件: 重新加载 plugins 模块")
            importlib.reload(plugins_module)
            logger.info("Admin插件: 已重新导入 plugins 模块")

            # 确保所有子模块也被重新加载
            for module_name in plugin_modules:
                if module_name != 'plugins':
                    try:
                        logger.info(f"Admin插件: 尝试重新导入模块 {module_name}")
                        # 如果模块已经存在，先重新加载
                        if module_name in sys.modules:
                            logger.info(f"Admin插件: 模块 {module_name} 已存在，重新加载")
                            module = importlib.reload(sys.modules[module_name])
                        else:
                            # 否则导入新模块
                            module = importlib.import_module(module_name)

                        # 递归重新加载所有子模块
                        if hasattr(module, '__path__'):
                            # 这是一个包，递归重新加载子模块
                            for submodule_name in list(sys.modules.keys()):
                                if submodule_name.startswith(module_name + '.') and submodule_name in sys.modules:
                                    try:
                                        logger.info(f"Admin插件: 重新加载子模块 {submodule_name}")
                                        importlib.reload(sys.modules[submodule_name])
                                    except Exception as e:
                                        logger.error(f"Admin插件: 重新加载子模块 {submodule_name} 失败: {e}")

                        logger.info(f"Admin插件: 已重新导入模块 {module_name}")
                    except Exception as e:
                        logger.error(f"Admin插件: 重新导入模块 {module_name} 失败: {e}")
                        import traceback
                        logger.error(f"Admin插件: 异常详情: {traceback.format_exc()}")
        except Exception as e:
            logger.error(f"Admin插件: 重新导入 plugins 模块失败: {e}")
            import traceback
            logger.error(f"Admin插件: 异常详情: {traceback.format_exc()}")

        # 重新加载插件
        logger.info("Admin插件: 开始重新加载插件")

        # 重新加载配置文件
        logger.info("Admin插件: 重新加载配置文件")
        try:
            # 使用正确的配置管理器路径
            from config.config_manager import ConfigManager
            # 保存原始配置路径
            config_path = getattr(self.bot, 'config_path', 'config.json')
            # 重新加载配置
            config_manager = ConfigManager(config_path)
            self.bot.config = config_manager.load_config()
            logger.info(f"Admin插件: 配置文件重新加载成功: {config_path}")
        except Exception as e:
            logger.error(f"Admin插件: 重新加载配置文件失败: {e}")
            import traceback
            logger.error(f"Admin插件: 异常详情: {traceback.format_exc()}")

        # 加载插件
        await self.bot.plugin_manager.load_plugins()

        plugins_count = len(self.bot.plugin_manager.plugins)
        logger.info(f"Admin插件: 已重新加载 {plugins_count} 个插件")
        await self.bot.send_text(from_user, f"已重新加载 {plugins_count} 个插件")

    async def cmd_restart(self, from_user: str, args: str):
        """重启机器人命令"""
        import os
        import sys
        import subprocess

        await self.bot.send_text(from_user, "正在重启机器人...请稍等")

        # 获取当前脚本路径
        current_script = sys.argv[0]
        logger.info(f"Admin插件: 当前脚本路径: {current_script}")

        # 获取当前工作目录
        current_dir = os.getcwd()
        logger.info(f"Admin插件: 当前工作目录: {current_dir}")

        # 准备重启命令
        python_executable = sys.executable
        logger.info(f"Admin插件: Python 可执行文件: {python_executable}")

        # 使用 subprocess 启动新进程
        try:
            # 使用 subprocess.Popen 启动新进程，并将其与当前进程分离
            restart_command = [python_executable, current_script]
            logger.info(f"Admin插件: 重启命令: {restart_command}")

            # 在 Windows 上使用 subprocess.CREATE_NEW_CONSOLE 标志
            if sys.platform == 'win32':
                subprocess.Popen(restart_command, cwd=current_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                # 在 Unix 系统上使用 nohup 或类似机制
                subprocess.Popen(['nohup'] + restart_command + ['&'], cwd=current_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

            # 发送成功消息
            await self.bot.send_text(from_user, "重启命令已发送，机器人将在几秒后重新启动")

            # 等待一秒，然后退出当前进程
            import asyncio
            await asyncio.sleep(1)

            # 优雅地停止机器人
            logger.info("Admin插件: 准备停止机器人")
            await self.bot.stop()

            # 退出当前进程
            logger.info("Admin插件: 退出当前进程")
            os._exit(0)  # 使用 os._exit 而不是 sys.exit 以确保立即退出

        except Exception as e:
            logger.error(f"Admin插件: 重启机器人时出错: {e}")
            await self.bot.send_text(from_user, f"重启机器人时出错: {e}")
