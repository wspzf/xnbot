# XNBot - 基于微信 API 的异步机器人框架

XNBot 是一个基于 Python 异步编程的微信机器人框架，使用您自己的微信 API 实现各种自动化功能。框架会自动管理微信 API 服务和 Redis 服务，无需手动启动。

## 特性

- 基于异步编程（asyncio）
- 插件化架构，易于扩展
- 支持多种消息类型处理
- 内置管理员命令系统
- 简单易用的 API 客户端
- 自动管理微信 API 服务和 Redis 服务

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/xnbot.git
cd xnbot
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

## 配置

1. 复制示例配置文件：

```bash
cp config.json.example config.json
```

2. 编辑配置文件，设置 API 地址和管理员微信 ID：

```json
{
  "api": {
    "base_url": "http://localhost:9011/VXAPI",
    "timeout": 30
  },
  "login": {
    "method": "qrcode",
    "device_name": "XNBot"
  },
  "bot": {
    "admin_wxids": ["your_wxid_here"],
    "log_level": "INFO"
  },
  "services": {
    "auto_start": true,
    "wechat_api": {
      "enabled": true,
      "auto_restart": true
    },
    "redis": {
      "enabled": true,
      "auto_restart": true
    }
  }
}
```

## 运行

```bash
python main.py
```

启动后，机器人会自动启动微信 API 服务和 Redis 服务，然后进行登录和消息处理。

## 插件开发

XNBot 支持插件扩展，您可以轻松创建自己的插件。

### 创建插件

1. 在`plugins`目录下创建一个新的目录，例如`myplugin`
2. 在该目录中创建`__init__.py`文件
3. 在`__init__.py`中定义一个继承自`PluginBase`的类

示例：

```python
from xnbot_py.core.plugin_manager import PluginBase
from xnbot_py.utils.decorators import on_text_message

class MyPlugin(PluginBase):
    name = "myplugin"
    description = "我的第一个插件"
    version = "1.0.0"
    author = "Your Name"

    async def on_load(self) -> bool:
        print("插件已加载")
        return True

    @on_text_message()
    async def handle_text(self, message: dict) -> bool:
        # 处理文本消息
        from_user, to_user, content = parse_text_message(message)

        if content == "你好":
            await self.bot.send_text(from_user, "你好！我是机器人")
            return True

        return False
```

### 使用装饰器

XNBot 提供了多种装饰器，方便插件开发：

- `@on_message()` - 处理所有类型的消息
- `@on_text_message()` - 处理文本消息
- `@on_image_message()` - 处理图片消息
- `@on_voice_message()` - 处理语音消息
- `@on_command("cmd")` - 处理特定命令
- `@admin_required` - 要求管理员权限

## 管理员命令

XNBot 内置了一些管理员命令：

- `/help` - 显示帮助信息
- `/status` - 显示机器人状态
- `/plugins` - 列出所有插件
- `/enable <插件名>` - 启用插件
- `/disable <插件名>` - 禁用插件
- `/reload` - 重新加载所有插件
- `/restart` - 重启机器人

## 许可证

MIT
