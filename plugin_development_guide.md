# XNBot 插件开发指南

## 目录

1. [插件系统概述](#插件系统概述)
2. [创建基本插件](#创建基本插件)
3. [插件生命周期](#插件生命周期)
4. [消息处理](#消息处理)
5. [使用装饰器](#使用装饰器)
6. [消息解析工具](#消息解析工具)
7. [发送消息](#发送消息)
8. [插件配置](#插件配置)
9. [插件优先级](#插件优先级)
10. [最佳实践](#最佳实践)
11. [示例插件](#示例插件)

## 插件系统概述

XNBot 的插件系统基于 Python 的模块和类机制，允许开发者通过继承 `PluginBase` 类来创建自定义插件。插件可以处理各种类型的消息，执行特定的命令，并与微信 API 交互。

插件系统的主要组件：

- `PluginBase`：所有插件的基类
- `PluginManager`：负责加载、卸载和管理插件
- 装饰器：提供便捷的消息处理方式
- 消息解析工具：帮助解析和处理微信消息

## 创建基本插件

要创建一个基本插件，需要以下步骤：

1. 在 `plugins` 目录下创建一个新的包（文件夹）
2. 在包中创建 `__init__.py` 和 `main.py` 文件
3. 在 `main.py` 中定义一个继承自 `PluginBase` 的类
4. 在 `__init__.py` 中导入并导出这个类

### 推荐的插件结构

最简洁的插件结构只需要三个文件：

```
plugins/
  └── MyPlugin/
      ├── __init__.py     # 插件入口点
      ├── main.py         # 主要实现代码
      └── config.toml     # 插件配置文件
```

对于复杂的插件，可以根据需要扩展：

```
plugins/
  └── MyPlugin/
      ├── __init__.py     # 插件入口点
      ├── main.py         # 主要实现代码
      ├── config.toml     # 插件配置文件
      ├── utils.py        # 工具函数（可选）
      ├── database.py     # 数据库操作（可选）
      └── resources/      # 资源文件（可选）
```

### **init**.py

```python
"""
MyPlugin
我的第一个插件
"""

from .main import MyPlugin

# 导出插件类，使插件管理器能够找到它
__plugin_class__ = MyPlugin
```

### main.py

```python
"""
MyPlugin 主要实现
"""

from xnbot.core.plugin_manager import PluginBase
import logging

logger = logging.getLogger(__name__)

class MyPlugin(PluginBase):
    """我的插件"""

    name = "myplugin"  # 插件名称，必须唯一
    description = "我的第一个插件"  # 插件描述
    version = "1.0.0"  # 插件版本
    author = "Your Name"  # 插件作者

    def __init__(self, bot):
        super().__init__(bot)
        logger.info("MyPlugin 已初始化")

    async def on_load(self) -> bool:
        logger.info("MyPlugin 已加载")
        return True

    async def on_message(self, message: dict) -> bool:
        # 处理消息
        logger.info(f"收到消息: {message}")
        return False  # 返回 False 表示未处理消息，允许其他插件处理
```

这种模块化的结构有以下优点：

1. **关注点分离**：每个文件负责特定的功能
2. **可维护性**：更容易理解和维护代码
3. **可扩展性**：更容易添加新功能
4. **可测试性**：更容易编写单元测试

## 插件生命周期

插件有以下生命周期方法：

1. `__init__(self, bot)` - 初始化插件，设置初始状态
2. `on_load(self) -> bool` - 插件加载时调用，返回 `True` 表示加载成功
3. `on_unload(self) -> bool` - 插件卸载时调用，返回 `True` 表示卸载成功
4. `on_enable(self) -> bool` - 插件启用时调用，返回 `True` 表示启用成功
5. `on_disable(self) -> bool` - 插件禁用时调用，返回 `True` 表示禁用成功
6. `on_message(self, message: Dict) -> bool` - 收到消息时调用，返回 `True` 表示已处理消息
7. `on_config_change(self, config: Dict) -> bool` - 配置变更时调用，返回 `True` 表示配置变更成功

## 消息处理

处理消息是插件的核心功能。有两种方式处理消息：

1. 重写 `on_message` 方法
2. 使用装饰器

### 重写 `on_message` 方法

```python
async def on_message(self, message: dict) -> bool:
    # 检查是否是文本消息
    if message.get("MsgType") != 1:  # 1 表示文本消息
        return False

    # 获取消息内容
    content = message.get("Content")
    if isinstance(content, dict) and "string" in content:
        content = content["string"]

    # 获取发送者
    from_user = message.get("FromUserName")
    if isinstance(from_user, dict) and "string" in from_user:
        from_user = from_user["string"]

    # 处理消息
    if content == "你好":
        await self.bot.send_text(from_user, "你好！我是机器人")
        return True  # 返回 True 表示已处理消息

    return False  # 返回 False 表示未处理消息
```

## 使用装饰器

XNBot 提供了多种装饰器，使消息处理更加便捷：

### 基本消息装饰器

```python
from xnbot.utils.decorators import on_message, on_text_message, on_image_message

# 处理所有消息
@on_message(priority=100)  # 设置优先级，数字越小优先级越高
async def handle_all_messages(self, message: dict) -> bool:
    # 处理所有类型的消息
    return False

# 处理文本消息
@on_text_message(priority=100)
async def handle_text(self, message: dict) -> bool:
    # 处理文本消息
    return False

# 处理图片消息
@on_image_message(priority=100)
async def handle_image(self, message: dict) -> bool:
    # 处理图片消息
    return False
```

### 命令装饰器

```python
from xnbot.utils.decorators import on_command

# 处理 /hello 命令
@on_command("hello", priority=50)  # 命令处理器通常需要较高的优先级
async def handle_hello_command(self, message: dict, args: str) -> bool:
    # 处理 /hello 命令
    # args 包含命令后的参数
    from_user = message.get("FromUserName")
    if isinstance(from_user, dict) and "string" in from_user:
        from_user = from_user["string"]
    await self.bot.send_text(from_user, f"Hello! 参数: {args}")
    return True
```

> **重要提示：命令处理器的注意事项**
>
> 1. 装饰器方法不会自动被调用，需要在 `on_message` 方法中手动检测命令并处理
> 2. 如果想要直接处理命令，可以在 `on_message` 方法中添加以下代码：
>
> ```python
> async def on_message(self, message: dict) -> bool:
> ```

    # 获取消息内容
    content = message.get("Content")
    if isinstance(content, dict) and "string" in content:
        content = content["string"]

    # 如果是 /hello 命令，直接处理
    if content.startswith("/hello"):
        # 解析参数
        args = content[6:].strip() if len(content) > 6 else ""
        # 获取发送者
        from_user = message.get("FromUserName")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]
        # 发送回复
        await self.bot.send_text(from_user, f"Hello! 参数: {args}")
        return True

    return False

````

### 权限装饰器

```python
from xnbot.utils.decorators import admin_required

# 要求管理员权限
@on_command("restart")
@admin_required
async def handle_restart_command(self, message: dict, args: str) -> bool:
    # 只有管理员才能执行此命令
    from_user = message.get("FromUserName")
    if isinstance(from_user, dict) and "string" in from_user:
        from_user = from_user["string"]
    await self.bot.send_text(from_user, "正在重启...")
    # 执行重启逻辑
    return True
````

### 其他装饰器

```python
from xnbot.utils.decorators import on_at_message, on_quote_message, on_file_message

# 处理@消息
@on_at_message(priority=100)
async def handle_at(self, message: dict) -> bool:
    # 处理被@的消息
    return False

# 处理引用消息
@on_quote_message(priority=100)
async def handle_quote(self, message: dict) -> bool:
    # 处理引用消息
    return False

# 处理文件消息
@on_file_message(priority=100)
async def handle_file(self, message: dict) -> bool:
    # 处理文件消息
    return False
```

## 消息解析工具

XNBot 提供了多种消息解析工具，帮助处理微信消息：

```python
from xnbot.utils.message_parser import (
    parse_text_message,
    is_group_message,
    get_group_sender,
    get_message_content,
    is_at_message,
    extract_command
)

# 解析文本消息
from_user, to_user, content = parse_text_message(message)

# 判断是否是群消息
if is_group_message(message):
    # 获取群消息发送者
    sender = get_group_sender(message)

# 获取消息内容
content = get_message_content(message)

# 判断是否是@消息
if is_at_message(message, self.bot.wxid):
    # 处理@消息

# 提取命令
command, args = extract_command(content)
```

## 发送消息

XNBot 提供了多种发送消息的方法：

```python
# 发送文本消息
await self.bot.send_text(to_wxid, "Hello, world!")

# 发送带@的文本消息
await self.bot.send_text(group_wxid, "Hello, @user", at_list=[user_wxid])

# 发送图片消息
await self.bot.send_image(to_wxid, "path/to/image.jpg")

# 发送语音消息
await self.bot.send_voice(to_wxid, "path/to/voice.mp3", voice_time=5000)

# 发送链接消息
await self.bot.send_link(to_wxid, "标题", "描述", "https://example.com", "https://example.com/thumb.jpg")
```

## 插件配置

插件可以通过 `self.config` 访问配置：

```python
async def on_load(self) -> bool:
    # 获取插件配置
    self.config = self.bot.config.get("plugins", {}).get(self.name, {})

    # 使用配置
    self.enabled_features = self.config.get("enabled_features", [])

    return True

async def on_config_change(self, config: Dict) -> bool:
    # 更新配置
    self.config = config

    # 使用新配置
    self.enabled_features = self.config.get("enabled_features", [])

    return True
```

## 插件优先级

插件可以设置优先级，数字越小优先级越高。这意味着优先级为 10 的插件会先于优先级为 100 的插件处理消息。

### 设置方法

有两种方式设置插件的优先级：

1. **使用装饰器设置优先级**（推荐）：

```python
# 在 on_message 方法上使用装饰器设置优先级
@on_message(priority=50)  # 设置优先级为50
async def on_message(self, message: dict) -> bool:
    # 处理消息
    return False
```

2. **在其他方法上使用装饰器设置优先级**：

```python
@on_text_message(priority=10)  # 高优先级
async def handle_high_priority(self, message: dict) -> bool:
    # 高优先级处理
    return False

@on_text_message(priority=100)  # 默认优先级
async def handle_normal_priority(self, message: dict) -> bool:
    # 普通优先级处理
    return False

@on_text_message(priority=200)  # 低优先级
async def handle_low_priority(self, message: dict) -> bool:
    # 低优先级处理
    return False
```

### 常用优先级值

- **0-10**：最高优先级，用于管理员插件等需要最先处理的插件
- **50**：高优先级，用于重要的功能插件
- **100**：默认优先级，用于一般功能插件
- **150-200**：低优先级，用于备用或辅助功能插件

### 优先级处理机制

当收到消息时，插件管理器会按照优先级从高到低的顺序调用插件的 `on_message` 方法。如果某个插件的 `on_message` 方法返回 `True`，表示已处理消息，插件管理器将不再调用优先级更低的插件。

### 注意事项

1. **返回值的重要性**：如果插件已经处理了消息，应该返回 `True`，这样可以避免其他插件重复处理同一消息。

2. **命令处理**：对于命令处理，应该只在成功处理了命令时返回 `True`，如果不认识该命令，应该返回 `False`，允许其他插件处理。

3. **热重载注意事项**：当使用 `/reload` 命令热重载插件时，装饰器设置的优先级会被正确重新加载。

## 最佳实践

1. **模块化设计**：将复杂插件拆分为多个模块，使用主类作为入口点
2. **错误处理**：使用 try-except 捕获异常，避免插件崩溃影响整个系统
3. **日志记录**：使用 logger 记录关键信息，方便调试
4. **配置验证**：在加载时验证配置，确保必要的配置项存在
5. **资源清理**：在 `on_unload` 中清理资源，如关闭文件、数据库连接等
6. **异步编程**：使用 `async/await` 进行异步操作，避免阻塞主线程
7. **权限检查**：在处理敏感命令前检查权限
8. **优先级设置**：合理设置优先级，避免冲突

## 常见问题与解决方案

### 1. 插件优先级设置不生效

**问题描述**：设置了插件的优先级，但在日志中显示的优先级仍然是默认值。

**解决方案**：

1. 确保在 `on_message` 方法上正确使用了装饰器：

   ```python
   @on_message(priority=50)
   async def on_message(self, message: dict) -> bool:
       # 处理消息
       return False
   ```

2. 如果使用热重载，确保重新启动应用程序，因为某些情况下热重载可能不会完全更新装饰器元数据。

### 2. 命令处理器不被调用

**问题描述**：使用 `@on_command` 装饰器定义了命令处理器，但它不会自动被调用。

**解决方案**：

1. 在 `on_message` 方法中手动检测命令并处理：

   ```python
   async def on_message(self, message: dict) -> bool:
       # 获取消息内容
       content = message.get("Content")
       if isinstance(content, dict) and "string" in content:
           content = content["string"]

       # 如果是 /command 命令，直接处理
       if content.startswith("/command"):
           # 解析参数
           args = content[8:].strip() if len(content) > 8 else ""
           # 处理命令
           # ...
           return True

       return False
   ```

### 3. 参数数量不匹配错误

**问题描述**：尝试直接调用装饰器方法时出现参数数量不匹配错误。

**解决方案**：

1. 不要直接调用装饰器方法，而是在 `on_message` 方法中手动实现相同的逻辑。

2. 如果必须调用装饰器方法，请注意参数数量：

   ```python
   # 错误的调用方式
   await self.handle_command(message, args)  # 这会传递 self, message, args 三个参数

   # 正确的调用方式
   await self.handle_command.__wrapped__(self, message, args)  # 访问原始方法
   ```

### 4. 插件热重载不完全

**问题描述**：使用 `/reload` 命令重新加载插件时，只有配置文件被重新加载，代码文件的更改没有生效。

**解决方案**：

1. 完全重启应用程序，这是最可靠的方法。

2. 改进 `/reload` 命令的实现，确保它能正确清除模块缓存并重新加载所有文件：
   ```python
   # 在 admin 插件的 cmd_reload_plugins 方法中
   # 清除所有插件相关的模块缓存
   for module_name in list(sys.modules.keys()):
       if module_name.startswith('plugins.') or module_name == 'plugins':
           if module_name in sys.modules:
               del sys.modules[module_name]
   ```

### 5. 插件之间的冲突

**问题描述**：多个插件处理相同的命令或消息，导致行为不一致。

**解决方案**：

1. 正确设置插件优先级，确保重要的插件有更高的优先级。

2. 在插件的 `on_message` 方法中正确返回值：

   - 如果插件已经处理了消息，应该返回 `True`
   - 如果插件没有处理消息，应该返回 `False`

3. 对于命令处理，确保插件只处理自己认识的命令，对于不认识的命令应该返回 `False`。

## 示例插件

### 简单的回复插件

```python
"""
Echo插件
简单的消息回显插件
"""

from xnbot.core.plugin_manager import PluginBase
from xnbot.utils.decorators import on_text_message, on_command
import logging

logger = logging.getLogger(__name__)

class EchoPlugin(PluginBase):
    """回显插件"""

    name = "echo"
    description = "简单的消息回显插件"
    version = "1.0.0"
    author = "XNBot"

    def __init__(self, bot):
        super().__init__(bot)
        logger.info("Echo插件已初始化")

    async def on_load(self) -> bool:
        logger.info("Echo插件已加载")
        return True

    @on_command("echo")
    async def handle_echo_command(self, message: dict, args: str) -> bool:
        """处理 /echo 命令"""
        from_user = message.get("FromUserName")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        if not args:
            await self.bot.send_text(from_user, "请提供要回显的内容")
            return True

        await self.bot.send_text(from_user, f"Echo: {args}")
        return True

    @on_text_message(priority=200)  # 低优先级，让其他插件先处理
    async def handle_text(self, message: dict) -> bool:
        """处理文本消息"""
        content = message.get("Content")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        from_user = message.get("FromUserName")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        # 只回复特定格式的消息
        if content.startswith("echo:"):
            text = content[5:].strip()
            await self.bot.send_text(from_user, f"Echo: {text}")
            return True

        return False
```

### 高级插件示例

```python
"""
Weather插件
提供天气查询功能
"""

from xnbot.core.plugin_manager import PluginBase
from xnbot.utils.decorators import on_command
import logging
import aiohttp
import json

logger = logging.getLogger(__name__)

class WeatherPlugin(PluginBase):
    """天气查询插件"""

    name = "weather"
    description = "提供天气查询功能"
    version = "1.0.0"
    author = "XNBot"

    def __init__(self, bot):
        super().__init__(bot)
        self.api_key = ""
        self.session = None
        logger.info("Weather插件已初始化")

    async def on_load(self) -> bool:
        """插件加载时调用"""
        logger.info("Weather插件正在加载...")

        # 加载配置
        self.config = self.bot.config.get("plugins", {}).get(self.name, {})
        self.api_key = self.config.get("api_key", "")

        if not self.api_key:
            logger.warning("Weather插件未配置API密钥，将使用演示数据")

        # 创建HTTP会话
        self.session = aiohttp.ClientSession()

        logger.info("Weather插件已加载")
        return True

    async def on_unload(self) -> bool:
        """插件卸载时调用"""
        logger.info("Weather插件正在卸载...")

        # 关闭HTTP会话
        if self.session:
            await self.session.close()
            self.session = None

        logger.info("Weather插件已卸载")
        return True

    @on_command("weather")
    async def handle_weather_command(self, message: dict, args: str) -> bool:
        """处理 /weather 命令"""
        from_user = message.get("FromUserName")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        if not args:
            await self.bot.send_text(from_user, "请提供城市名称，例如：/weather 北京")
            return True

        city = args.strip()
        weather_info = await self.get_weather(city)

        await self.bot.send_text(from_user, weather_info)
        return True

    async def get_weather(self, city: str) -> str:
        """获取天气信息"""
        if not self.api_key:
            # 演示数据
            return f"{city}天气：晴，温度25°C，湿度60%，风力3级"

        try:
            url = f"https://api.example.com/weather?city={city}&key={self.api_key}"
            async with self.session.get(url) as response:
                if response.status != 200:
                    return f"获取{city}天气失败：HTTP {response.status}"

                data = await response.json()
                if data.get("status") != "ok":
                    return f"获取{city}天气失败：{data.get('message', '未知错误')}"

                weather = data.get("weather", {})
                return (
                    f"{city}天气：{weather.get('condition', '未知')}，"
                    f"温度{weather.get('temperature', '未知')}°C，"
                    f"湿度{weather.get('humidity', '未知')}%，"
                    f"风力{weather.get('wind_level', '未知')}级"
                )
        except Exception as e:
            logger.error(f"获取天气信息时出错: {e}")
            return f"获取{city}天气失败：{str(e)}"
```

## 结语

通过本指南，您应该能够开发自己的 XNBot 插件。记住，好的插件应该是模块化的、健壮的、易于维护的。遵循最佳实践，充分利用 XNBot 提供的工具和 API，您可以创建功能强大的插件，扩展 XNBot 的功能。

如果您有任何问题或需要进一步的帮助，请随时咨询。祝您编码愉快！
