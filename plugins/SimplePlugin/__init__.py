"""
SimplePlugin
一个简单的示例插件，展示XNBot插件开发的基本结构
"""

from .main import SimplePlugin

# 导出插件类，使插件管理器能够找到它
__plugin_class__ = SimplePlugin
