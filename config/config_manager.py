"""
配置管理器
负责加载和保存配置
"""

import os
import json
import logging
from typing import Dict, Any, Optional

from xnbot.utils.logger import setup_logger

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = "config.json"):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """
        获取默认配置

        Returns:
            默认配置字典
        """
        return {
            "api": {
                "base_url": "http://localhost:9011/VXAPI",
                "timeout": 30
            },
            "login": {
                "method": "qrcode",  # qrcode 或 62data
                "device_name": "XNBot",
                "data62": "",
                "username": "",
                "password": ""
            },
            "bot": {
                "admin_wxids": [],
                "log_level": "INFO",
                "plugin_dirs": ["plugins"]
            },
            "services": {
                "auto_start": True,
                "wechat_api": {
                    "enabled": True,
                    "auto_restart": True
                },
                "redis": {
                    "enabled": True,
                    "auto_restart": True
                }
            },
            "plugins": {}
        }

    def load_config(self) -> Dict[str, Any]:
        """
        加载配置

        Returns:
            配置字典
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)

                # 合并默认配置和加载的配置
                self._merge_config(self.config, loaded_config)
                logger.info(f"已从 {self.config_path} 加载配置")
            except Exception as e:
                logger.error(f"加载配置时出错: {e}")
                logger.info("使用默认配置")
        else:
            logger.warning(f"配置文件 {self.config_path} 不存在，使用默认配置")
            self.save_config()

        return self.config

    def _merge_config(self, default: Dict[str, Any], loaded: Dict[str, Any]):
        """
        合并配置

        Args:
            default: 默认配置
            loaded: 加载的配置
        """
        for key, value in loaded.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._merge_config(default[key], value)
            else:
                default[key] = value

    def save_config(self, config=None) -> bool:
        """
        保存配置

        Args:
            config: 要保存的配置，如果为None则使用实例的config

        Returns:
            是否成功保存
        """
        try:
            # 如果提供了配置，使用提供的配置
            if config is not None:
                self.config = config
                logger.info(f"使用提供的配置进行保存: {config}")

            # 确保目录存在
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            logger.info(f"配置文件目录: {config_dir}")
            os.makedirs(config_dir, exist_ok=True)

            # 尝试写入文件
            logger.info(f"尝试将配置写入文件: {self.config_path}")
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)

            logger.info(f"配置已成功保存到 {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置时出错: {e}")
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
            return False

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        获取插件配置

        Args:
            plugin_name: 插件名称

        Returns:
            插件配置
        """
        return self.config.get("plugins", {}).get(plugin_name, {})

    def set_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        """
        设置插件配置

        Args:
            plugin_name: 插件名称
            config: 插件配置

        Returns:
            是否成功设置
        """
        if "plugins" not in self.config:
            self.config["plugins"] = {}

        self.config["plugins"][plugin_name] = config
        return self.save_config()
