import io
import json
import re
import subprocess
import tomllib
from typing import Optional, Union, Dict, List, Tuple
import time
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
from collections import defaultdict
from enum import Enum
import urllib.parse
import mimetypes
import base64
import os

import aiohttp
import filetype
from loguru import logger
import speech_recognition as sr
import asyncio
import traceback
from xnbot.api.wechat_client import WeChatAPIClient
from xnbot.utils.decorators import on_text_message, on_image_message, on_voice_message, on_message, on_at_message, on_quote_message, on_file_message
from xnbot.core.plugin_manager import PluginBase
from gtts import gTTS
import shutil
from PIL import Image
import xml.etree.ElementTree as ET

# 添加API代理导入
try:
    from api_manager_integrator import has_api_manager_feature
    has_api_proxy = has_api_manager_feature()
    if has_api_proxy:
        logger.info("API管理中心可用，Dify插件将使用API代理")
    else:
        logger.info("API管理中心不可用，Dify插件将使用直接连接")
except ImportError:
    has_api_proxy = False
    logger.warning("未找到API管理中心集成模块，Dify插件将使用直接连接")

# 常量定义
XYBOT_PREFIX = "-----老夏的金库-----\n"
DIFY_ERROR_MESSAGE = "🙅对不起，Dify出现错误！\n"
INSUFFICIENT_POINTS_MESSAGE = "😭你的积分不够啦！需要 {price} 积分"
VOICE_TRANSCRIPTION_FAILED = "\n语音转文字失败"
TEXT_TO_VOICE_FAILED = "\n文本转语音失败"
CHAT_TIMEOUT = 3600  # 1小时超时
CHAT_AWAY_TIMEOUT = 1800  # 30分钟自动离开
MESSAGE_BUFFER_TIMEOUT = 10  # 消息缓冲区超时时间（秒）
MAX_BUFFERED_MESSAGES = 10  # 最大缓冲消息数

# 聊天室消息模板
CHAT_JOIN_MESSAGE = """✨ 欢迎来到聊天室！让我们开始愉快的对话吧~

💡 基础指引：
   📝 直接发消息与我对话
   🚪 发送"退出聊天"离开
   ⏰ 5分钟不说话自动暂离
   🔄 30分钟无互动将退出

🎮 聊天指令：
   📊 发送"查看状态"
   📈 发送"聊天室排行"
   👤 发送"我的统计"
   💤 发送"暂时离开"

开始聊天吧！期待与你的精彩对话~ 🌟"""

CHAT_LEAVE_MESSAGE = "👋 已退出聊天室，需要再次@我才能继续对话"
CHAT_TIMEOUT_MESSAGE = "由于您已经1小时没有活动，已被移出聊天室。如需继续对话，请重新发送消息。"
CHAT_AWAY_MESSAGE = "💤 已设置为离开状态，其他人将看到你正在休息"
CHAT_BACK_MESSAGE = "🌟 欢迎回来！已恢复活跃状态"
CHAT_AUTO_AWAY_MESSAGE = "由于您已经30分钟没有活动，已被自动设置为离开状态。"

class UserStatus(Enum):
    ACTIVE = "活跃"
    AWAY = "离开"
    INACTIVE = "未加入"

# 添加数据库兼容层
class SimpleDB:
    """简单的数据库兼容层，用于模拟XYBotDB"""
    def __init__(self):
        self.points = {}
        self.thread_ids = {}
        self.whitelist = set()

    def get_points(self, user_id: str) -> int:
        """获取用户积分"""
        return self.points.get(user_id, 100)  # 默认给100积分

    def add_points(self, user_id: str, points: int) -> int:
        """添加用户积分"""
        self.points[user_id] = self.get_points(user_id) + points
        return self.points[user_id]

    def get_llm_thread_id(self, user_id: str, namespace: str) -> str:
        """获取对话线程ID

        Args:
            user_id: 用户ID
            namespace: 命名空间（模型名称）

        Returns:
            对话线程ID，如果不存在则返回空字符串
        """
        key = f"{user_id}:{namespace}"
        thread_id = self.thread_ids.get(key, "")
        logger.info(f"获取对话线程ID: user={user_id}, namespace={namespace}, thread_id={thread_id}")
        return thread_id

    def save_llm_thread_id(self, user_id: str, namespace: str, thread_id: str) -> None:
        """保存对话线程ID

        Args:
            user_id: 用户ID
            namespace: 命名空间（模型名称）
            thread_id: 对话线程ID
        """
        key = f"{user_id}:{namespace}"
        self.thread_ids[key] = thread_id
        logger.info(f"保存对话线程ID: user={user_id}, namespace={namespace}, thread_id={thread_id}")

    def get_whitelist(self, user_id: str) -> bool:
        """检查用户是否在白名单中"""
        return user_id in self.whitelist

    def add_to_whitelist(self, user_id: str) -> None:
        """添加用户到白名单"""
        self.whitelist.add(user_id)

    def remove_from_whitelist(self, user_id: str) -> None:
        """从白名单中移除用户"""
        if user_id in self.whitelist:
            self.whitelist.remove(user_id)

@dataclass
class UserStats:
    total_messages: int = 0
    total_chars: int = 0
    join_count: int = 0
    last_active: float = 0
    total_active_time: float = 0
    status: UserStatus = UserStatus.INACTIVE

@dataclass
class ChatRoomUser:
    wxid: str
    group_id: str
    last_active: float
    status: UserStatus = UserStatus.ACTIVE
    stats: UserStats = field(default_factory=UserStats)

@dataclass
class MessageBuffer:
    messages: list[str] = field(default_factory=list)
    last_message_time: float = 0.0
    timer_task: Optional[asyncio.Task] = None
    message_count: int = 0
    files: list[str] = field(default_factory=list)

class ChatRoomManager:
    def __init__(self):
        self.active_users = {}
        self.message_buffers = defaultdict(lambda: MessageBuffer([], 0.0, None))
        self.user_stats: Dict[tuple[str, str], UserStats] = defaultdict(UserStats)

    def add_user(self, group_id: str, user_wxid: str) -> None:
        key = (group_id, user_wxid)
        self.active_users[key] = ChatRoomUser(
            wxid=user_wxid,
            group_id=group_id,
            last_active=time.time()
        )
        stats = self.user_stats[key]
        stats.join_count += 1
        stats.last_active = time.time()
        stats.status = UserStatus.ACTIVE

    def remove_user(self, group_id: str, user_wxid: str) -> None:
        key = (group_id, user_wxid)
        if key in self.active_users:
            user = self.active_users[key]
            stats = self.user_stats[key]
            stats.total_active_time += time.time() - stats.last_active
            stats.status = UserStatus.INACTIVE
            del self.active_users[key]
        if key in self.message_buffers:
            buffer = self.message_buffers[key]
            if buffer.timer_task and not buffer.timer_task.done():
                buffer.timer_task.cancel()
            del self.message_buffers[key]

    def update_user_activity(self, group_id: str, user_wxid: str) -> None:
        key = (group_id, user_wxid)
        if key in self.active_users:
            self.active_users[key].last_active = time.time()
            stats = self.user_stats[key]
            stats.total_messages += 1
            stats.last_active = time.time()

    def set_user_status(self, group_id: str, user_wxid: str, status: UserStatus) -> None:
        key = (group_id, user_wxid)
        if key in self.active_users:
            self.active_users[key].status = status
            self.user_stats[key].status = status

    def get_user_status(self, group_id: str, user_wxid: str) -> UserStatus:
        key = (group_id, user_wxid)
        if key in self.active_users:
            return self.active_users[key].status
        return UserStatus.INACTIVE

    def get_user_stats(self, group_id: str, user_wxid: str) -> UserStats:
        return self.user_stats[(group_id, user_wxid)]

    def get_room_stats(self, group_id: str) -> List[tuple[str, UserStats]]:
        stats = []
        for (g_id, wxid), user_stats in self.user_stats.items():
            if g_id == group_id:
                stats.append((wxid, user_stats))
        return sorted(stats, key=lambda x: x[1].total_messages, reverse=True)

    def get_active_users_count(self, group_id: str) -> tuple[int, int, int]:
        active = 0
        away = 0
        total = 0
        for (g_id, _), user in self.active_users.items():
            if g_id == group_id:
                total += 1
                if user.status == UserStatus.ACTIVE:
                    active += 1
                elif user.status == UserStatus.AWAY:
                    away += 1
        return active, away, total

    async def add_message_to_buffer(self, group_id: str, user_wxid: str, message: str, files: list[str] = None) -> None:
        """添加消息到缓冲区"""
        if files is None:
            files = []

        key = (group_id, user_wxid)
        if key not in self.message_buffers:
            self.message_buffers[key] = MessageBuffer()

        buffer = self.message_buffers[key]
        buffer.messages.append(message)
        buffer.last_message_time = time.time()
        buffer.message_count += 1
        buffer.files.extend(files)  # 添加文件ID到缓冲区

        logger.debug(f"成功添加消息到缓冲区 - 用户: {user_wxid}, 消息: {message}, 当前消息数: {buffer.message_count}, 文件: {files}")

    def get_and_clear_buffer(self, group_id: str, user_wxid: str) -> Tuple[str, list[str]]:
        """获取并清空缓冲区"""
        key = (group_id, user_wxid)
        buffer = self.message_buffers.get(key)
        if buffer:
            messages = "\n".join(buffer.messages)
            files = buffer.files.copy()  # 复制文件ID列表
            logger.debug(f"合并并清空缓冲区 - 用户: {user_wxid}, 合并消息: {messages}, 文件: {files}")
            buffer.messages.clear()
            buffer.message_count = 0
            buffer.files.clear()  # 清空文件ID列表
            return messages, files
        return "", []

    def is_user_active(self, group_id: str, user_wxid: str) -> bool:
        key = (group_id, user_wxid)
        if key not in self.active_users:
            return False

        user = self.active_users[key]
        if time.time() - user.last_active > CHAT_TIMEOUT:
            self.remove_user(group_id, user_wxid)
            return False
        return True

    def check_and_remove_inactive_users(self) -> list[tuple[str, str]]:
        current_time = time.time()
        inactive_users = []

        for (group_id, user_wxid), user in list(self.active_users.items()):
            if user.status == UserStatus.ACTIVE and current_time - user.last_active > CHAT_AWAY_TIMEOUT:
                self.set_user_status(group_id, user_wxid, UserStatus.AWAY)
                inactive_users.append((group_id, user_wxid, "away"))
            elif current_time - user.last_active > CHAT_TIMEOUT:
                inactive_users.append((group_id, user_wxid, "timeout"))
                self.remove_user(group_id, user_wxid)

        return inactive_users

    def format_user_stats(self, group_id: str, user_wxid: str, nickname: str = "未知用户") -> str:
        stats = self.get_user_stats(group_id, user_wxid)
        status = self.get_user_status(group_id, user_wxid)
        active_time = int(stats.total_active_time / 60)
        return f"""📊 {nickname} 的聊天室数据：

🏷️ 当前状态：{status.value}
💬 发送消息：{stats.total_messages} 条
📝 总字数：{stats.total_chars} 字
🔄 加入次数：{stats.join_count} 次
⏱️ 活跃时间：{active_time} 分钟"""

    def format_room_status(self, group_id: str) -> str:
        active, away, total = self.get_active_users_count(group_id)
        return f"""🏠 聊天室状态：

👥 当前成员：{total} 人
✨ 活跃成员：{active} 人
💤 暂离成员：{away} 人"""

    async def format_room_ranking(self, group_id: str, bot: WeChatAPIClient, limit: int = 5) -> str:
        stats = self.get_room_stats(group_id)
        result = ["🏆 聊天室排行榜：\n"]

        for i, (wxid, user_stats) in enumerate(stats[:limit], 1):
            try:
                nickname = await bot.get_nickname(wxid) or "未知用户"
            except:
                nickname = "未知用户"
            result.append(f"{self._get_rank_emoji(i)} {nickname}")
            result.append(f"   💬 {user_stats.total_messages}条消息")
            result.append(f"   📝 {user_stats.total_chars}字")
        return "\n".join(result)

    @staticmethod
    def _get_rank_emoji(rank: int) -> str:
        if rank == 1:
            return "🥇"
        elif rank == 2:
            return "🥈"
        elif rank == 3:
            return "🥉"
        return f"{rank}."

@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    trigger_words: list[str]
    price: int
    wakeup_words: list[str] = field(default_factory=list)  # 添加唤醒词列表字段

class Dify(PluginBase):
    description = "Dify插件"
    author = "老夏的金库"
    version = "1.3.2"  # 更新版本号
    name = "Dify"  # 添加名称属性

    def __init__(self, bot):
        """
        初始化插件

        Args:
            bot: 机器人实例
        """
        super().__init__(bot)

        # 加载配置
        self.config = self.load_config()

        # 配置项
        self.enable = self.config.get("enable", True)
        self.default_model_name = self.config.get("default-model", "学姐")
        self.commands = self.config.get("commands", ["聊天", "AI"])
        self.chatroom_enable = self.config.get("chatroom_enable", False)
        self.command_tip = self.config.get("command-tip", "")
        self.admin_ignore = self.config.get("admin_ignore", True)
        self.whitelist_ignore = self.config.get("whitelist_ignore", True)
        self.http_proxy = self.config.get("http-proxy", "")
        self.voice_reply_all = self.config.get("voice_reply_all", False)
        self.robot_names = self.config.get("robot-names", ["毛球", "DifyBot", "智能助手"])
        self.audio_to_text_url = self.config.get("audio-to-text-url", "")
        self.text_to_audio_url = self.config.get("text-to-audio-url", "")
        self.remember_user_model = self.config.get("remember_user_model", True)
        self.image_cache_timeout = 60

        # 模型配置
        self.models_config = self.config.get("models", {})

        # 初始化聊天管理器
        self.chat_manager = ChatRoomManager()

        # 初始化用户模型选择
        self.user_models = {}

        # 获取默认模型
        self.current_model = self.get_model_config(self.default_model_name)

        # 获取管理员列表
        self.admins = self.bot.config.get("bot", {}).get("admin_wxids", [])
        logger.info(f"已加载管理员列表: {self.admins}")

        # 消息处理中间任务
        self.current_tasks = {}

        # 图片缓存 - 用于处理发送后立即删除的图片问题
        self.image_cache = {}

        # 初始化数据库兼容层
        self.db = SimpleDB()

        # 为调试添加管理员到白名单
        for admin in self.admins:
            self.db.add_to_whitelist(admin)

        # 任务定时器
        self.check_inactive_task = None

        # 初始化API代理兼容
        self.api_proxy = None

        # 创建唤醒词到模型的映射
        self.wakeup_word_to_model = {}
        for model_name, model_config in self.models_config.items():
            model_obj = self.get_model_config(model_name)
            for wakeup_word in model_obj.wakeup_words:
                self.wakeup_word_to_model[wakeup_word] = model_obj

        logger.info(f"Dify插件已初始化，默认模型: {self.default_model_name}")

    def load_config(self):
        """加载配置文件"""
        try:
            # 尝试从插件目录加载config.toml
            config_path = os.path.join(os.path.dirname(__file__), "config.toml")
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            return config.get("Dify", {})
        except Exception as e:
            logger.error(f"加载Dify配置失败: {e}")
            return {}

    def get_model_config(self, model_name):
        """
        获取模型配置

        Args:
            model_name: 模型名称

        Returns:
            模型配置对象
        """
        try:
            model_data = self.models_config.get(model_name, {})
            if not model_data:
                logger.warning(f"未找到模型配置: {model_name}，使用默认配置")
                # 使用默认配置
                model_data = {
                    "api-key": "",
                    "base-url": "http://localhost:8080/v1",
                    "trigger-words": [],
                    "wakeup-words": [],
                    "price": 0
                }

            # 创建模型配置对象
            return ModelConfig(
                api_key=model_data.get("api-key", ""),
                base_url=model_data.get("base-url", "http://localhost:8080/v1"),
                trigger_words=model_data.get("trigger-words", []),
                price=model_data.get("price", 0),
                wakeup_words=model_data.get("wakeup-words", [])
            )
        except Exception as e:
            logger.error(f"获取模型配置失败: {e}")
            # 返回一个默认配置
            return ModelConfig(
                api_key="",
                base_url="http://localhost:8080/v1",
                trigger_words=[],
                price=0,
                wakeup_words=[]
            )

    async def on_load(self) -> bool:
        """
        插件加载时调用

        Returns:
            加载是否成功
        """
        logger.info("Dify插件正在加载...")

        # 扩展WeChatAPIClient的方法
        self._patch_wechat_client()

        # 启动定时检查任务
        if self.chatroom_enable:
            self.check_inactive_task = asyncio.create_task(self.check_inactive_users_loop())
            logger.info("聊天室功能已启用，开始定时检查不活跃用户")

        return True

    def _patch_wechat_client(self):
        """
        为WeChatAPIClient添加兼容方法，处理接口差异
        """
        # 保存原始方法
        original_send_text = self.bot.client.send_text

        # 添加兼容方法
        async def send_text_message(to_wxid, content):
            """兼容旧接口的发送文本消息方法"""
            return await original_send_text(to_wxid, content)

        async def send_at_message(group_id, content, at_list):
            """兼容旧接口的发送@消息方法"""
            return await original_send_text(group_id, content, at_list=at_list)

        async def get_nickname(wxid):
            """获取用户昵称"""
            try:
                info = await self.bot.client.get_cached_info(wxid)
                return info.get("Data", {}).get("nickName", "未知用户")
            except:
                return "未知用户"

        # 绑定新方法到WeChatAPIClient实例
        self.bot.client.send_text_message = send_text_message
        self.bot.client.send_at_message = send_at_message
        self.bot.client.get_nickname = get_nickname

        # 添加byte_to_base64方法
        def byte_to_base64(data):
            """将字节数据转换为base64编码"""
            if not isinstance(data, bytes):
                return ""
            return base64.b64encode(data).decode('utf-8')

        self.bot.client.byte_to_base64 = byte_to_base64

        logger.info("已为WeChatAPIClient添加兼容方法")

    async def on_unload(self) -> bool:
        """
        插件卸载时调用

        Returns:
            卸载是否成功
        """
        # 取消定时任务
        if self.check_inactive_task:
            self.check_inactive_task.cancel()
            try:
                await self.check_inactive_task
            except asyncio.CancelledError:
                pass

        return True

    async def check_inactive_users_loop(self):
        """定时检查不活跃用户的循环"""
        try:
            while True:
                try:
                    await self.check_and_notify_inactive_users(self.bot.client)
                except Exception as e:
                    logger.error(f"检查不活跃用户时出错: {e}")
                await asyncio.sleep(60)  # 每分钟检查一次
        except asyncio.CancelledError:
            logger.info("检查不活跃用户的任务已取消")
            raise

    def get_user_model(self, user_id: str) -> ModelConfig:
        """获取用户当前使用的模型"""
        if self.remember_user_model and user_id in self.user_models:
            return self.user_models[user_id]
        return self.current_model

    def set_user_model(self, user_id: str, model: ModelConfig):
        """设置用户当前使用的模型"""
        if self.remember_user_model:
            self.user_models[user_id] = model

    def get_model_from_message(self, content: str, user_id: str) -> tuple[ModelConfig, str, bool]:
        """
        从消息中解析模型信息

        Args:
            content: 消息内容
            user_id: 用户ID

        Returns:
            tuple: (模型配置, 处理后的消息内容, 是否触发了模型切换)
        """
        # 检查每个模型的触发词
        current_model = self.get_user_model(user_id)
        is_switch = False

        # 记录日志
        logger.debug(f"解析消息模型: content='{content}', user_id='{user_id}'")

        # 优先检查是否包含切换模型命令
        if content.endswith("切换"):
            for model_name, model_config in self.models_config.items():
                model_obj = self.get_model_config(model_name)
                for trigger in model_obj.trigger_words:
                    trigger = trigger.strip("@")
                    if content.startswith(trigger):
                        logger.info(f"检测到模型切换命令: '{trigger} 切换'")
                        self.set_user_model(user_id, model_obj)
                        return model_obj, "", True

        # 检查是否使用临时模型
        for model_name, model_config in self.models_config.items():
            model_obj = self.get_model_config(model_name)
            for trigger in model_obj.trigger_words:
                trigger = trigger.strip("@")
                if content.startswith(trigger + " "):
                    logger.info(f"检测到临时模型触发词: '{trigger}'")
                    # 移除前缀并返回
                    return model_obj, content[len(trigger):].strip(), False

            # 检查唤醒词
            for wakeup in model_obj.wakeup_words:
                # 更灵活的唤醒词检测
                wakeup_lower = wakeup.lower()
                content_lower = content.lower()

                # 检查各种可能的唤醒词形式
                if (content_lower.startswith(wakeup_lower + " ") or
                    f" {wakeup_lower} " in f" {content_lower} " or
                    content_lower.endswith(f" {wakeup_lower}")):

                    logger.info(f"检测到唤醒词: '{wakeup}' in '{content}'")

                    # 移除唤醒词
                    if content_lower.startswith(wakeup_lower + " "):
                        content = content[len(wakeup):].strip()
                    elif content_lower.endswith(f" {wakeup_lower}"):
                        content = content[:-(len(wakeup)+1)].strip()
                    else:
                        # 尝试在中间找到并移除唤醒词
                        pattern = re.compile(f"\\s+{re.escape(wakeup)}\\s+", re.IGNORECASE)
                        content = pattern.sub(" ", content)

                    return model_obj, content, False

        # 如果没有检测到特定模型，使用用户当前模型
        logger.debug(f"未检测到特定模型，使用用户当前模型")
        return current_model, content, False

    async def check_and_notify_inactive_users(self, bot: WeChatAPIClient):
        # 如果聊天室功能关闭，则直接返回，不进行检查和提醒
        if not self.chatroom_enable:
            return

        inactive_users = self.chat_manager.check_and_remove_inactive_users()
        for group_id, user_wxid, status in inactive_users:
            if status == "away":
                await bot.send_at_message(group_id, "\n" + CHAT_AUTO_AWAY_MESSAGE, [user_wxid])
            elif status == "timeout":
                await bot.send_at_message(group_id, "\n" + CHAT_TIMEOUT_MESSAGE, [user_wxid])

    async def process_buffered_messages(self, bot: WeChatAPIClient, group_id: str, user_wxid: str):
        logger.debug(f"开始处理缓冲消息 - 用户: {user_wxid}, 群组: {group_id}")
        messages, files = self.chat_manager.get_and_clear_buffer(group_id, user_wxid)
        logger.debug(f"从缓冲区获取到的消息: {messages}")
        logger.debug(f"从缓冲区获取到的文件: {files}")

        if messages is not None and messages.strip():
            logger.debug(f"合并后的消息: {messages}")
            message = {
                "FromWxid": group_id,
                "SenderWxid": user_wxid,
                "Content": messages,
                "IsGroup": True,
                "MsgType": 1
            }
            logger.debug(f"准备检查积分")
            if await self._check_point(bot, message):
                logger.debug("积分检查通过，开始调用 Dify API")
                try:
                    # 检查是否有唤醒词或触发词
                    model, processed_query, is_switch = self.get_model_from_message(messages, user_wxid)
                    await self.dify(bot, message, processed_query, files=files, specific_model=model)
                    logger.debug("成功调用 Dify API 并发送消息")
                except Exception as e:
                    logger.error(f"调用 Dify API 失败: {e}")
                    logger.error(traceback.format_exc())
                    await bot.send_at_message(group_id, "\n消息处理失败，请稍后重试。", [user_wxid])
        else:
            logger.debug("缓冲区为空或消息无效，无需处理")

    async def _delayed_message_processing(self, bot: WeChatAPIClient, group_id: str, user_wxid: str):
        key = (group_id, user_wxid)
        try:
            logger.debug(f"开始延迟处理 - 用户: {user_wxid}, 群组: {group_id}")
            await asyncio.sleep(MESSAGE_BUFFER_TIMEOUT)

            buffer = self.chat_manager.message_buffers.get(key)
            if buffer and buffer.messages:
                logger.debug(f"缓冲区消息数: {len(buffer.messages)}")
                logger.debug(f"最后消息时间: {time.time() - buffer.last_message_time:.2f}秒前")

                if time.time() - buffer.last_message_time >= MESSAGE_BUFFER_TIMEOUT:
                    logger.debug("开始处理缓冲消息")
                    await self.process_buffered_messages(bot, group_id, user_wxid)
                else:
                    logger.debug("跳过处理 - 有新消息，重新调度")
                    await self.schedule_message_processing(bot, group_id, user_wxid)
        except asyncio.CancelledError:
            logger.debug(f"定时器被取消 - 用户: {user_wxid}, 群组: {group_id}")
        except Exception as e:
            logger.error(f"处理消息缓冲区时出错: {e}")
            await bot.send_at_message(group_id, "\n消息处理发生错误，请稍后重试。", [user_wxid])

    async def schedule_message_processing(self, bot: WeChatAPIClient, group_id: str, user_wxid: str):
        key = (group_id, user_wxid)
        if key not in self.chat_manager.message_buffers:
            self.chat_manager.message_buffers[key] = MessageBuffer()

        buffer = self.chat_manager.message_buffers[key]
        logger.debug(f"安排消息处理 - 用户: {user_wxid}, 群组: {group_id}")

        # 获取buffer中的消息内容
        buffer_content = "\n".join(buffer.messages) if buffer.messages else ""

        # 检查是否有最近的图片
        image_content = await self.get_cached_image(group_id)
        if image_content:
            try:
                logger.debug("发现最近的图片，准备上传到 Dify")
                # 先检查是否有唤醒词获取对应模型
                wakeup_model = None
                for wakeup_word, model_config in self.wakeup_word_to_model.items():
                    wakeup_lower = wakeup_word.lower()
                    buffer_content_lower = buffer_content.lower()
                    if buffer_content_lower.startswith(wakeup_lower) or f" {wakeup_lower}" in buffer_content_lower:
                        wakeup_model = model_config
                        break

                # 如果没有找到唤醒词对应的模型，则使用用户当前的模型
                model_config = wakeup_model or self.get_user_model(user_wxid)

                file_id = await self.upload_file_to_dify(
                    image_content,
                    "image/jpeg",
                    group_id,
                    model_config=model_config  # 传递正确的模型配置
                )
                if file_id:
                    logger.debug(f"图片上传成功，文件ID: {file_id}")
                    buffer.files.append(file_id)  # 直接添加到buffer的files列表
                    logger.debug(f"当前buffer中的文件: {buffer.files}")
                else:
                    logger.error("图片上传失败")
            except Exception as e:
                logger.error(f"处理图片失败: {e}")

        if buffer.message_count >= MAX_BUFFERED_MESSAGES:
            logger.debug("缓冲区已满，立即处理消息")
            await self.process_buffered_messages(bot, group_id, user_wxid)
            return

        if buffer.timer_task and not buffer.timer_task.done():
            logger.debug("取消已有定时器")
            buffer.timer_task.cancel()

        logger.debug("创建新定时器")
        buffer.timer_task = asyncio.create_task(
            self._delayed_message_processing(bot, group_id, user_wxid)
        )
        logger.debug(f"定时器任务已创建 - 用户: {user_wxid}")

    async def on_message(self, message: Dict) -> bool:
        """
        处理所有消息

        Args:
            message: 消息数据

        Returns:
            是否处理了消息
        """
        logger.info(f"Dify插件收到消息: {message}")

        # 检查是否是管理员命令，如果是则跳过
        content = message.get("Content", "")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]

        # 检查是否是命令
        if content.startswith("/"):
            logger.info(f"Dify插件: 检测到命令 {content}，跳过处理")
            return False  # 跳过命令处理，让admin插件处理

        # 检查消息类型
        msg_type = message.get("MsgType")

        # 处理消息内容可能是字典的情况
        content = message.get("Content", "")
        if isinstance(content, dict) and "string" in content:
            content = content["string"]
            message["Content"] = content

        # 处理发送者可能是字典的情况
        from_user = message.get("FromUserName", "")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]
            message["FromUserName"] = from_user

        # 处理接收者可能是字典的情况
        to_user = message.get("ToUserName", "")
        if isinstance(to_user, dict) and "string" in to_user:
            to_user = to_user["string"]
            message["ToUserName"] = to_user

        # 检查是否为私聊消息
        is_private = not from_user.endswith("@chatroom")

        # 如果是私聊消息，直接处理
        if is_private and msg_type == 1:  # 私聊文本消息
            logger.info(f"处理私聊消息: {content}")
            # 所有私聊消息都直接调用Dify API
            model_config, cleaned_content, triggered = self.get_model_from_message(content, from_user)
            logger.info(f"获取到模型配置: {model_config}, 处理后内容: {cleaned_content}, 触发切换: {triggered}")

            # 创建新的消息对象，避免修改原始消息
            new_message = {
                "SenderWxid": from_user,  # 私聊中发送者就是FromUserName
                "FromUserName": from_user,
                "ToUserName": to_user,
                "Content": content,
                "IsGroup": False  # 标记为非群组消息
            }

            await self.dify(self.bot.client, new_message, cleaned_content, specific_model=model_config)
            return True

        # 如果不是私聊消息，根据消息类型处理
        if msg_type == 1:  # 文本消息
            return await self.handle_text(message)
        # 其他类型消息暂时不处理
        # 如果需要处理其他类型消息，可以在这里添加相应的处理逻辑

        return False

    @on_text_message(priority=100)
    async def handle_text(self, message: Dict) -> bool:
        """
        处理文本消息

        Args:
            message: 消息数据

        Returns:
            是否处理了消息
        """
        logger.info(f"Dify插件收到文本消息: {message}")

        if not self.enable:
            logger.info("Dify插件已禁用，跳过处理")
            return False

        try:
            # 获取消息信息，处理嵌套结构
            from_user = message.get("FromUserName", "")
            to_user = message.get("ToUserName", "")
            content = message.get("Content", "")
            msg_source = message.get("MsgSource", "")

            # 处理内容可能是字典的情况
            if isinstance(from_user, dict) and "string" in from_user:
                from_user = from_user["string"]
                logger.info(f"Dify插件: 处理后的发送者={from_user}")

            if isinstance(to_user, dict) and "string" in to_user:
                to_user = to_user["string"]
                logger.info(f"Dify插件: 处理后的接收者={to_user}")

            if isinstance(content, dict) and "string" in content:
                content = content["string"]
                logger.info(f"Dify插件: 处理后的内容={content}")

            # 检查是否为群聊消息
            is_group = from_user.endswith("@chatroom")

            # 解析发送者wxid
            sender_wxid = from_user  # 默认发送者就是 FromUserName

            # 如果是群聊消息，尝试从内容中提取真正的发送者
            if is_group and ":" in content:
                possible_sender = content.split(":", 1)[0].strip()
                content = content.split(":", 1)[1].strip()
                # 如果可能的发送者是一个有效的wxid，则使用它
                if possible_sender and not possible_sender.startswith("@"):
                    sender_wxid = possible_sender

            # 记录详细日志，帮助调试
            logger.info(f"处理消息: from={from_user}, to={to_user}, content={content}, is_group={is_group}, sender={sender_wxid}")

            # 检查是否@了机器人
            is_at = False
            if "<atuserlist>" in msg_source and self.bot.wxid in msg_source:
                is_at = True
                logger.info(f"检测到@消息: {msg_source}")

            # 处理群聊消息
            if is_group:
                logger.info(f"处理群聊消息: group={from_user}, sender={sender_wxid}, content={content}")
                # 如果开启了聊天室功能，并且用户已加入聊天
                if self.chatroom_enable and self.chat_manager.is_user_active(from_user, sender_wxid):
                    logger.info(f"用户 {sender_wxid} 已加入聊天室")
                    # 更新用户活动状态
                    self.chat_manager.update_user_activity(from_user, sender_wxid)

                    # 处理特殊命令
                    if content == "退出聊天":
                        logger.info(f"用户 {sender_wxid} 请求退出聊天室")
                        self.chat_manager.remove_user(from_user, sender_wxid)
                        await self.bot.client.send_text(from_user, CHAT_LEAVE_MESSAGE)
                        return True
                    elif content == "查看状态":
                        logger.info(f"用户 {sender_wxid} 请求查看聊天室状态")
                        status_text = self.chat_manager.format_room_status(from_user)
                        await self.bot.client.send_text(from_user, status_text)
                        return True
                    elif content == "聊天室排行":
                        logger.info(f"用户 {sender_wxid} 请求查看聊天室排行")
                        ranking_text = await self.chat_manager.format_room_ranking(from_user, self.bot.client)
                        await self.bot.client.send_text(from_user, ranking_text)
                        return True
                    elif content == "我的统计":
                        logger.info(f"用户 {sender_wxid} 请求查看个人统计")
                        # 获取用户昵称
                        nickname = "未知用户"
                        stats_text = self.chat_manager.format_user_stats(from_user, sender_wxid, nickname)
                        await self.bot.client.send_text(from_user, stats_text)
                        return True
                    elif content == "暂时离开":
                        logger.info(f"用户 {sender_wxid} 请求暂时离开")
                        self.chat_manager.set_user_status(from_user, sender_wxid, UserStatus.AWAY)
                        await self.bot.client.send_text(from_user, CHAT_AWAY_MESSAGE)
                        return True
                    elif content == "回来了":
                        logger.info(f"用户 {sender_wxid} 请求回来")
                        self.chat_manager.set_user_status(from_user, sender_wxid, UserStatus.ACTIVE)
                        await self.bot.client.send_text(from_user, CHAT_BACK_MESSAGE)
                        return True

                    # 添加消息到缓冲区
                    logger.info(f"将消息 '{content}' 添加到用户 {sender_wxid} 的缓冲区")
                    await self.chat_manager.add_message_to_buffer(from_user, sender_wxid, content)

                    # 安排消息处理
                    logger.info(f"安排处理用户 {sender_wxid} 的消息")
                    await self.schedule_message_processing(self.bot.client, from_user, sender_wxid)

                    return True

                # 如果是@机器人或者包含触发词或唤醒词，并且聊天室功能开启
                # 检查是否包含唤醒词
                has_wakeup_word = False
                for model_name, model_config in self.models_config.items():
                    model_obj = self.get_model_config(model_name)
                    for wakeup in model_obj.wakeup_words:
                        if content.startswith(wakeup + " ") or f" {wakeup} " in f" {content} ":
                            has_wakeup_word = True
                            logger.info(f"群聊中检测到唤醒词: '{wakeup}'")
                            break
                    if has_wakeup_word:
                        break

                if is_at or has_wakeup_word or any(cmd in content for cmd in self.commands):
                    logger.info(f"触发Dify响应: is_at={is_at}, content={content}")

                    # 如果聊天室功能开启，则添加用户到聊天室
                    if self.chatroom_enable and not self.chat_manager.is_user_active(from_user, sender_wxid):
                        logger.info(f"将用户 {sender_wxid} 添加到聊天室")
                        self.chat_manager.add_user(from_user, sender_wxid)
                        await self.bot.client.send_text(from_user, CHAT_JOIN_MESSAGE)
                        return True

                    # 获取模型配置
                    logger.info(f"解析用户 {sender_wxid} 的消息 '{content}' 获取模型信息")
                    model_config, cleaned_content, triggered = self.get_model_from_message(content, sender_wxid)
                    logger.info(f"获取到模型配置: {model_config}, 处理后内容: {cleaned_content}, 触发切换: {triggered}")

                    # 移除@部分
                    for name in self.robot_names:
                        cleaned_content = cleaned_content.replace(f"@{name}", "").strip()

                    # 调用Dify API
                    logger.info(f"准备调用Dify API, 消息内容: {cleaned_content}")
                    message["SenderWxid"] = sender_wxid  # 添加发送者wxid
                    message["IsGroup"] = True  # 标记为群组消息
                    await self.dify(self.bot.client, message, cleaned_content, specific_model=model_config)
                    return True

            # 处理私聊消息
            else:
                logger.info(f"处理私聊消息: {content}")
                # 所有私聊消息都直接调用Dify API
                model_config, cleaned_content, triggered = self.get_model_from_message(content, from_user)
                logger.info(f"获取到模型配置: {model_config}, 处理后内容: {cleaned_content}, 触发切换: {triggered}")
                # 创建新的消息对象，避免修改原始消息
                new_message = {
                    "SenderWxid": from_user,  # 私聊中发送者就是FromUserName
                    "FromUserName": from_user,
                    "ToUserName": to_user,
                    "Content": content,
                    "IsGroup": False  # 标记为非群组消息
                }
                await self.dify(self.bot.client, new_message, cleaned_content, specific_model=model_config)
                return True

        except Exception as e:
            logger.error(f"处理文本消息出错: {e}")
            logger.error(traceback.format_exc())

        return False

    @on_at_message(priority=100)
    async def handle_at(self, bot: WeChatAPIClient, message: dict):
        if not self.enable:
            return

        if not self.current_model.api_key:
            await bot.send_at_message(message["FromWxid"], "\n你还没配置Dify API密钥！", [message["SenderWxid"]])
            return False

        await self.check_and_notify_inactive_users(bot)

        content = message["Content"].strip()
        query = content
        for robot_name in self.robot_names:
            query = query.replace(f"@{robot_name}", "").strip()

        group_id = message["FromWxid"]
        user_wxid = message["SenderWxid"]

        if query == "退出聊天":
            if self.chat_manager.is_user_active(group_id, user_wxid):
                self.chat_manager.remove_user(group_id, user_wxid)
                await bot.send_at_message(group_id, "\n" + CHAT_LEAVE_MESSAGE, [user_wxid])
            return False

        if not self.chat_manager.is_user_active(group_id, user_wxid):
            # 根据配置决定是否加入聊天室并发送欢迎消息
            self.chat_manager.add_user(group_id, user_wxid)
            if self.chatroom_enable:
                await bot.send_at_message(group_id, "\n" + CHAT_JOIN_MESSAGE, [user_wxid])

        logger.debug(f"提取到的 query: {query}")

        if not query:
            await bot.send_at_message(message["FromWxid"], "\n请输入你的问题或指令。", [message["SenderWxid"]])
            return False

        # 检查唤醒词或触发词，在图片上传前获取对应模型
        model, processed_query, is_switch = self.get_model_from_message(query, message["SenderWxid"])
        if is_switch:
            model_name = next(name for name, config in self.models.items() if config == model)
            await bot.send_at_message(
                message["FromWxid"],
                f"\n已切换到{model_name.upper()}模型，将一直使用该模型直到下次切换。",
                [message["SenderWxid"]]
            )
            return False

        # 检查模型API密钥是否可用
        if not model.api_key:
            model_name = next((name for name, config in self.models.items() if config == model), '未知')
            logger.error(f"所选模型 '{model_name}' 的API密钥未配置")
            await bot.send_at_message(message["FromWxid"], f"\n此模型API密钥未配置，请联系管理员", [message["SenderWxid"]])
            return False

        # 检查是否有最近的图片
        files = []
        image_content = await self.get_cached_image(group_id)
        if image_content:
            try:
                logger.debug("@消息中发现最近的图片，准备上传到 Dify")
                file_id = await self.upload_file_to_dify(
                    image_content,
                    "image/jpeg",
                    group_id,
                    model_config=model  # 传递正确的模型配置
                )
                if file_id:
                    logger.debug(f"图片上传成功，文件ID: {file_id}")
                    files = [file_id]
                else:
                    logger.error("图片上传失败")
            except Exception as e:
                logger.error(f"处理图片失败: {e}")

        if await self._check_point(bot, message, model):  # 传递正确的模型参数
            # 使用上面已经获取的模型和处理过的查询
            logger.info(f"@消息使用模型 '{next((name for name, config in self.models.items() if config == model), '未知')}' 处理请求")
            await self.dify(bot, message, processed_query, files=files, specific_model=model)
        else:
            logger.info(f"积分检查失败，无法处理@消息请求")
        return False

    @on_quote_message(priority=100)
    async def handle_quote(self, bot: WeChatAPIClient, message: dict):
        """处理引用消息"""
        if not self.enable:
            return

        # 提取引用消息的内容
        content = message["Content"].strip()
        quote_info = message.get("Quote", {})
        quoted_content = quote_info.get("Content", "")
        quoted_sender = quote_info.get("Nickname", "")

        # 处理群聊和私聊的情况
        if message["IsGroup"]:
            group_id = message["FromWxid"]
            user_wxid = message["SenderWxid"]

            # 检查是否是@机器人
            is_at = self.is_at_message(message)

            if is_at:
                # 处理@机器人的引用消息
                query = content
                for robot_name in self.robot_names:
                    query = query.replace(f"@{robot_name}", "").strip()

                # 如果没有内容，则使用引用的内容
                if not query:
                    query = f"请回复这条消息: '{quoted_content}'"
                else:
                    query = f"{query} (引用消息: '{quoted_content}')"

                # 检查是否有唤醒词或触发词
                model, processed_query, is_switch = self.get_model_from_message(query, user_wxid)

                if is_switch:
                    model_name = next(name for name, config in self.models.items() if config == model)
                    await bot.send_at_message(
                        message["FromWxid"],
                        f"\n已切换到{model_name.upper()}模型，将一直使用该模型直到下次切换。",
                        [user_wxid]
                    )
                    return False

                # 检查模型API密钥是否可用
                if not model.api_key:
                    model_name = next((name for name, config in self.models.items() if config == model), '未知')
                    logger.error(f"所选模型 '{model_name}' 的API密钥未配置")
                    await bot.send_at_message(message["FromWxid"], f"\n此模型API密钥未配置，请联系管理员", [user_wxid])
                    return False

                # 检查是否有最近的图片
                files = []
                image_content = await self.get_cached_image(group_id)
                if image_content:
                    try:
                        logger.debug("引用消息中发现最近的图片，准备上传到 Dify")
                        file_id = await self.upload_file_to_dify(
                            image_content,
                            "image/jpeg",
                            group_id,
                            model_config=model
                        )
                        if file_id:
                            logger.debug(f"图片上传成功，文件ID: {file_id}")
                            files = [file_id]
                        else:
                            logger.error("图片上传失败")
                    except Exception as e:
                        logger.error(f"处理图片失败: {e}")

                if await self._check_point(bot, message, model):
                    logger.info(f"引用消息使用模型 '{next((name for name, config in self.models.items() if config == model), '未知')}' 处理请求")
                    await self.dify(bot, message, processed_query, files=files, specific_model=model)
                else:
                    logger.info(f"积分检查失败，无法处理引用消息请求")
        else:
            # 私聊引用消息处理
            user_wxid = message["SenderWxid"]

            # 如果没有内容，则使用引用的内容
            if not content:
                query = f"请回复这条消息: '{quoted_content}'"
            else:
                query = f"{content} (引用消息: '{quoted_content}')"

            # 检查是否有唤醒词或触发词
            model, processed_query, is_switch = self.get_model_from_message(query, user_wxid)

            if is_switch:
                model_name = next(name for name, config in self.models.items() if config == model)
                await bot.send_text_message(
                    message["FromWxid"],
                    f"已切换到{model_name.upper()}模型，将一直使用该模型直到下次切换。"
                )
                return False

            # 检查模型API密钥是否可用
            if not model.api_key:
                model_name = next((name for name, config in self.models.items() if config == model), '未知')
                logger.error(f"所选模型 '{model_name}' 的API密钥未配置")
                await bot.send_text_message(message["FromWxid"], "此模型API密钥未配置，请联系管理员")
                return False

            # 检查是否有最近的图片
            files = []
            image_content = await self.get_cached_image(message["FromWxid"])
            if image_content:
                try:
                    logger.debug("引用消息中发现最近的图片，准备上传到 Dify")
                    file_id = await self.upload_file_to_dify(
                        image_content,
                        "image/jpeg",
                        message["FromWxid"],
                        model_config=model
                    )
                    if file_id:
                        logger.debug(f"图片上传成功，文件ID: {file_id}")
                        files = [file_id]
                    else:
                        logger.error("图片上传失败")
                except Exception as e:
                    logger.error(f"处理图片失败: {e}")

            if await self._check_point(bot, message, model):
                logger.info(f"私聊引用消息使用模型 '{next((name for name, config in self.models.items() if config == model), '未知')}' 处理请求")
                await self.dify(bot, message, processed_query, files=files, specific_model=model)
            else:
                logger.info(f"积分检查失败，无法处理引用消息请求")

        return False

    @on_voice_message(priority=100)
    async def handle_voice(self, bot: WeChatAPIClient, message: dict):
        if not self.enable:
            return

        if message["IsGroup"]:
            return

        if not self.current_model.api_key:
            await bot.send_text_message(message["FromWxid"], "你还没配置Dify API密钥！")
            return False

        query = await self.audio_to_text(bot, message)
        if not query:
            await bot.send_text_message(message["FromWxid"], VOICE_TRANSCRIPTION_FAILED)
            return False

        logger.debug(f"语音转文字结果: {query}")

        # 识别可能的唤醒词
        model, processed_query, is_switch = self.get_model_from_message(query, message["SenderWxid"])
        if is_switch:
            model_name = next(name for name, config in self.models.items() if config == model)
            await bot.send_text_message(
                message["FromWxid"],
                f"已切换到{model_name.upper()}模型，将一直使用该模型直到下次切换。"
            )
            return False

        # 检查识别到的模型API密钥是否可用
        if not model.api_key:
            model_name = next((name for name, config in self.models.items() if config == model), '未知')
            logger.error(f"语音消息选择的模型 '{model_name}' 的API密钥未配置")
            await bot.send_text_message(message["FromWxid"], "所选模型的API密钥未配置，请联系管理员")
            return False

        # 积分检查
        if await self._check_point(bot, message, model):
            logger.info(f"语音消息使用模型 '{next((name for name, config in self.models.items() if config == model), '未知')}' 处理请求")
            await self.dify(bot, message, processed_query, specific_model=model)
        else:
            logger.info(f"积分检查失败，无法处理语音消息请求")
        return False

    def is_at_message(self, message: dict) -> bool:
        """
        检查是否是@消息

        Args:
            message: 消息数据

        Returns:
            是否是@消息
        """
        # 检查MsgSource中是否有atuserlist
        msg_source = message.get("MsgSource", "")
        if "<atuserlist>" in msg_source and self.bot.wxid in msg_source:
            return True

        # 检查Content中是否有@机器人名称
        content = message.get("Content", {}).get("string", "")
        for name in self.robot_names:
            if f"@{name}" in content:
                return True

        return False

    async def handle_error_in_private(self, api, user_id, error_message):
        """在私聊中发送错误消息"""
        try:
            await api.send_text(user_id, f"错误: {error_message}")
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")

    async def handle_error_in_group(self, api, group_id, user_id, error_message):
        """在群聊中发送错误消息"""
        try:
            if user_id:
                await api.send_at_message(group_id, f"\n错误: {error_message}", [user_id])
            else:
                await api.send_text(group_id, f"错误: {error_message}")
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")

    async def dify(self, api, message, text, specific_model=None):
        """
        调用Dify API

        Args:
            api: 微信API
            message: 消息数据
            text: 消息文本
            specific_model: 指定使用的模型配置
        """
        logger.info(f"dify方法被调用，消息: {text}, 指定模型: {specific_model}")

        # 获取用户wxid
        sender_wxid = message.get("SenderWxid", "")
        is_group = message.get("IsGroup", False)

        # 处理 FromUserName 和 ToUserName 可能是字典或字符串的情况
        from_user = message.get("FromUserName", "")
        if isinstance(from_user, dict) and "string" in from_user:
            from_user = from_user["string"]

        to_user = message.get("ToUserName", "")
        if isinstance(to_user, dict) and "string" in to_user:
            to_user = to_user["string"]

        logger.info(f"消息来源: sender_wxid={sender_wxid}, from_user={from_user}, to_user={to_user}, is_group={is_group}")

        # 获取对应的聊天窗口（群聊或私聊）
        reply_user = from_user if is_group else sender_wxid
        logger.info(f"回复目标: reply_user={reply_user}")

        # 如果没有指定模型，使用默认模型
        if not specific_model:
            logger.info(f"未指定模型，使用用户 {sender_wxid} 的默认模型")
            model_config = self.get_user_model(sender_wxid)
        else:
            model_config = specific_model

        logger.info(f"最终使用的模型配置: {model_config}")

        if not model_config:
            logger.warning(f"未找到可用的模型配置，跳过处理")
            return

        # 使用指定模型调用Dify API
        # 处理 ModelConfig 对象
        if isinstance(model_config, ModelConfig):
            name = self.default_model_name  # 使用默认模型名称
            base_url = model_config.base_url
            api_key = model_config.api_key
        else:
            # 兼容字典类型的模型配置
            name = model_config.get("api_name", "")
            base_url = model_config.get("api_base", "")
            api_key = model_config.get("api_key", "")

        if not (name and base_url and api_key):
            logger.error(f"模型配置不完整: name={name}, base_url={base_url}, api_key=有值:{bool(api_key)}")
            if is_group:
                # 发送错误消息到群聊
                await self.handle_error_in_group(api, reply_user, sender_wxid, "模型配置错误")
            else:
                # 发送错误消息到私聊
                await self.handle_error_in_private(api, sender_wxid, "模型配置错误")
            return

        logger.info(f"准备调用Dify API，模型: {name}")
        # 调用Dify API
        try:
            # 获取用户保留点数
            user_points = self.db.get_points(sender_wxid)
            if user_points <= 0:
                logger.warning(f"用户 {sender_wxid} 点数不足: {user_points}")
                if is_group:
                    await self.handle_error_in_group(api, reply_user, sender_wxid, "您的点数不足，无法继续对话")
                else:
                    await self.handle_error_in_private(api, reply_user, "您的点数不足，无法继续对话")
                return

            # 构建请求头
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # 检查是否需要创建新会话
            thread_id = self.db.get_llm_thread_id(sender_wxid, name)
            logger.info(f"用户 {sender_wxid} 的会话ID: {thread_id}")

            # 直接调用 Dify 的聊天消息 API
            logger.info(f"为用户 {sender_wxid} 发送消息")
            chat_url = f"{base_url}/chat-messages"

            # 准备请求参数
            payload = {
                "query": text,  # 用户输入内容
                "user": sender_wxid,  # 用户ID
                "inputs": {},  # 可选参数
                "response_mode": "streaming"  # 流式返回
            }

            # 如果有会话ID，添加到请求中
            if thread_id:
                payload["conversation_id"] = thread_id
                logger.info(f"使用现有会话: {thread_id}")

            async with aiohttp.ClientSession() as session:
                async with session.post(chat_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        logger.info("消息创建成功")
                        # 如果是流式返回，需要处理 SSE 流
                        if payload["response_mode"] == "streaming":
                            # 处理流式返回
                            full_response = ""
                            conversation_id = None
                            message_id = None

                            # 读取流式数据
                            async for line in response.content:
                                line = line.decode('utf-8').strip()
                                if line.startswith('data: '):
                                    data = line[6:]  # 去除 'data: ' 前缀
                                    try:
                                        event_data = json.loads(data)
                                        event_type = event_data.get("event")

                                        if event_type == "message":
                                            # 收到消息块
                                            message_id = event_data.get("message_id")
                                            conversation_id = event_data.get("conversation_id")
                                            answer_chunk = event_data.get("answer", "")
                                            full_response += answer_chunk

                                        elif event_type == "message_end":
                                            # 消息结束
                                            message_id = event_data.get("message_id")
                                            conversation_id = event_data.get("conversation_id")

                                            # 如果是新会话或会话ID变化，保存会话ID
                                            if conversation_id:
                                                # 始终保存最新的会话ID，确保下次对话能继续
                                                self.db.save_llm_thread_id(sender_wxid, name, conversation_id)
                                                logger.info(f"保存会话ID: {conversation_id}")

                                            # 发送完整回复
                                            logger.info(f"发送回复: {full_response}")
                                            if is_group:
                                                if sender_wxid:
                                                    await api.send_at_message(reply_user, f"\n{full_response}", [sender_wxid])
                                                else:
                                                    await api.send_text(reply_user, full_response)
                                            else:
                                                await api.send_text(reply_user, full_response)

                                            # 扣除点数
                                            self.db.add_points(sender_wxid, -1)
                                            return True

                                        elif event_type == "error":
                                            # 错误事件
                                            error_message = event_data.get("message", "未知错误")
                                            logger.error(f"流式返回错误: {error_message}")
                                            if is_group:
                                                await self.handle_error_in_group(api, reply_user, sender_wxid, f"生成回复失败: {error_message}")
                                            else:
                                                await self.handle_error_in_private(api, reply_user, f"生成回复失败: {error_message}")
                                            return False
                                    except json.JSONDecodeError:
                                        logger.error(f"解析流式数据失败: {data}")
                        else:
                            # 如果是阻塞模式，直接获取完整响应
                            message_result = await response.json()
                            message_id = message_result.get("message_id")
                            conversation_id = message_result.get("conversation_id")
                            answer = message_result.get("answer", "")

                            # 保存会话ID，确保下次对话能继续
                            if conversation_id:
                                self.db.save_llm_thread_id(sender_wxid, name, conversation_id)
                                logger.info(f"保存会话ID: {conversation_id}")

                            # 发送回复
                            logger.info(f"发送回复: {answer}")
                            if is_group:
                                if sender_wxid:
                                    await api.send_at_message(reply_user, f"\n{answer}", [sender_wxid])
                                else:
                                    await api.send_text(reply_user, answer)
                            else:
                                await api.send_text(reply_user, answer)

                            # 扣除点数
                            self.db.add_points(sender_wxid, -1)
                            return True

                    else:
                        error_text = await response.text()
                        logger.error(f"创建消息失败: {response.status}, {error_text}")
                        if is_group:
                            await self.handle_error_in_group(api, reply_user, sender_wxid, "创建消息失败")
                        else:
                            await self.handle_error_in_private(api, reply_user, "创建消息失败")
                        return False
        except Exception as e:
            logger.error(f"调用Dify API时出错: {e}")
            logger.error(traceback.format_exc())
            if is_group:
                await self.handle_error_in_group(api, reply_user, sender_wxid, "调用AI服务失败")
            else:
                await self.handle_error_in_private(api, reply_user, "调用AI服务失败")
            return False

    @property
    def models(self):
        """兼容models属性访问"""
        if not hasattr(self, "_models_cache"):
            self._models_cache = {}
            for model_name, _ in self.models_config.items():
                self._models_cache[model_name] = self.get_model_config(model_name)
        return self._models_cache
