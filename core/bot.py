"""
机器人核心
负责协调API客户端、插件管理器和消息处理
"""

import asyncio
import logging
import json
import time
import os
from typing import Dict, List, Optional, Callable, Any, Union

from xnbot.api.wechat_client import WeChatAPIClient
from xnbot.core.plugin_manager import PluginManager
from xnbot.core.service_manager import ServiceManager
from xnbot.config.config_manager import ConfigManager
# 导入彩色日志格式化器
try:
    from xnbot.utils.color_formatter import setup_colored_logging
except ImportError:
    pass

logger = logging.getLogger(__name__)

class Bot:
    """机器人核心类"""

    def __init__(self, config_path: str = "config.json"):
        """
        初始化机器人

        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config()

        # 初始化API客户端
        api_base_url = self.config.get("api", {}).get("base_url", "http://localhost:9011/VXAPI")
        self.client = WeChatAPIClient(api_base_url)

        # 初始化插件管理器
        self.plugin_manager = PluginManager(self)

        # 初始化服务管理器
        self.service_manager = ServiceManager(self)

        # 状态变量
        self.running = False
        self.logged_in = False
        self.wxid = None
        self.nickname = None
        self.user_info = {}

        # 消息处理器
        self.message_handlers = []

        # 心跳任务
        self._heartbeat_task = None

        # 消息同步任务
        self._sync_task = None

    async def start(self):
        """启动机器人"""
        if self.running:
            logger.warning("机器人已经在运行")
            return

        logger.info("正在启动机器人...")
        self.running = True

        # 先启动服务
        await self.service_manager.start_services()

        # 等待服务启动完成
        await asyncio.sleep(5)  # 等待5秒，确保服务完全启动

        # 加载插件
        await self.plugin_manager.load_plugins()

        # 登录
        await self.login()

        # 启动消息同步
        if self.logged_in:
            logger.info("正在启动消息同步...")
            await self.client.start_message_sync(self._on_message)
            logger.info("消息同步已启动")

            # 处理堆积消息
            logger.debug("处理堆积消息中")
            count = 0
            while True:
                response = await self.client.sync_message()
                if not response.get("Success"):
                    logger.debug(f"同步消息失败: {response.get('Message', '')}")
                    break

                msgs = response.get("AddMsgs", [])
                if not msgs:
                    if count > 2:
                        break
                    else:
                        count += 1
                        await asyncio.sleep(1)
                        continue

                logger.debug(f"处理堆积消息: {len(msgs)} 条")
                for msg in msgs:
                    await self._on_message(msg)
                await asyncio.sleep(1)
            logger.debug("处理堆积消息完毕")

            # 启动心跳任务
            logger.info("正在启动心跳任务...")
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("心跳任务已启动")

            # 启动自动消息同步任务
            logger.info("正在启动自动消息同步任务...")
            self._sync_task = asyncio.create_task(self._sync_loop())
            logger.info("自动消息同步任务已启动")

            logger.info("机器人启动完成")
        else:
            logger.error("机器人启动失败：登录失败")
            self.running = False

    async def stop(self):
        """
        停止机器人
        """
        self.running = False

        # 取消心跳任务
        if hasattr(self, '_heartbeat_task') and self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                logger.info("心跳任务已取消")

        # 取消消息同步任务
        if hasattr(self, '_sync_task') and self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                logger.info("消息同步任务已取消")

        # 关闭客户端
        if self.client:
            # 修复：使用session.close()而不是不存在的close()方法
            if hasattr(self.client, 'session') and self.client.session:
                await self.client.session.close()
            # 停止消息同步（如果还在运行）
            await self.client.stop_message_sync()

        logger.info("机器人已停止")

    async def login(self) -> bool:
        """
        登录微信

        Returns:
            是否登录成功
        """
        login_method = self.config.get("login", {}).get("method", "qrcode")

        # 检查是否已经登录
        if self.client.wxid and await self.client.is_logged_in():
            logger.info(f"已经登录，wxid: {self.client.wxid}")
            self.logged_in = True
            return True

        # 获取登录配置
        logger.info(f"配置内容: {self.config}")
        login_config = self.config.get("login", {})
        saved_wxid = login_config.get("wxid")
        device_name = login_config.get("device_name", "XNBot")
        device_id = login_config.get("device_id", "")
        logger.info(f"从配置中获取到的登录信息: wxid={saved_wxid}, device_name={device_name}, device_id={device_id}")

        # 根据登录方法选择不同的登录方式
        if login_method == "awaken" and saved_wxid:
            # 使用AwakenLogin方法
            try:
                logger.info(f"尝试使用AwakenLogin方法，wxid: {saved_wxid}")
                uuid = await self.client.awaken_login(saved_wxid)
                if uuid:
                    logger.info(f"AwakenLogin成功，获取到UUID: {uuid}")
                    # 检查登录状态
                    is_logged_in, login_data = await self.client.check_login_uuid(uuid)
                    if is_logged_in:
                        logger.info(f"通过AwakenLogin方法登录成功")
                        self.logged_in = True
                        self.wxid = saved_wxid
                        self.client.wxid = saved_wxid

                        # 尝试获取昵称
                        try:
                            profile = await self.client.get_profile()
                            self.nickname = profile.get("NickName") or profile.get("nickName")
                            logger.info(f"获取到用户昵称: {self.nickname}")
                        except Exception as e:
                            logger.warning(f"获取用户昵称失败: {e}")
                            self.nickname = f"微信用户{saved_wxid[-6:]}" if len(saved_wxid) > 6 else f"微信用户{saved_wxid}"

                        # 尝试初始化
                        try:
                            init_response = await self.client.new_init()
                            logger.debug(f"初始化成功: {init_response.get('Success')}")
                        except Exception as e:
                            logger.warning(f"初始化失败: {e}")

                        return True
                    else:
                        logger.warning(f"通过AwakenLogin方法登录失败: {login_data}")
                else:
                    logger.warning(f"AwakenLogin失败，未获取到UUID")
            except Exception as e:
                logger.error(f"AwakenLogin出错: {e}")

        # 如果AwakenLogin失败或者不是使用awaken方法，尝试唤醒登录
        if saved_wxid:
            # 首先尝试使用唤醒登录
            try:
                logger.info(f"尝试使用唤醒登录，wxid: {saved_wxid}, device_name: {device_name}, device_id: {device_id}")
                response = await self.client.login_awaken(saved_wxid, device_name, device_id)

                if response.get("Success"):
                    logger.info(f"唤醒登录成功，wxid: {saved_wxid}")
                    self.logged_in = True
                    self.wxid = saved_wxid
                    self.client.wxid = saved_wxid

                    # 尝试获取昵称
                    try:
                        profile = await self.client.get_profile()
                        self.nickname = profile.get("NickName") or profile.get("nickName")
                        logger.info(f"获取到用户昵称: {self.nickname}")
                    except Exception as e:
                        logger.warning(f"获取用户昵称失败: {e}")
                        self.nickname = f"微信用户{saved_wxid[-6:]}" if len(saved_wxid) > 6 else f"微信用户{saved_wxid}"

                    # 尝试初始化
                    try:
                        init_response = await self.client.new_init()
                        logger.debug(f"初始化成功: {init_response.get('Success')}")
                    except Exception as e:
                        logger.warning(f"初始化失败: {e}")

                    # 保存配置到文件
                    try:
                        # 确保配置中有wxid和设备信息
                        login_config = self.config.get("login", {})
                        login_config["wxid"] = saved_wxid
                        login_config["device_name"] = device_name
                        login_config["device_id"] = device_id
                        self.config["login"] = login_config
                        logger.info(f"唤醒登录后的配置: {self.config}")

                        result = self.config_manager.save_config(self.config)
                        logger.info(f"保存配置到文件结果: {result}")
                        if result:
                            logger.info("已成功保存登录配置到文件")
                        else:
                            logger.error("保存配置到文件失败")
                    except Exception as e:
                        logger.error(f"保存配置到文件时出错: {e}")

                    return True
                else:
                    logger.warning(f"唤醒登录失败，尝试使用二次登录(TwiceAutoAuth)")
                    # 唤醒登录失败，尝试使用二次登录
                    try:
                        from xnbot.utils.logger import BOLD, BRIGHT_YELLOW, RESET
                        logger.info(f"{BOLD}{BRIGHT_YELLOW}尝试使用二次登录(TwiceAutoAuth)...{RESET}")
                        # 尝试使用另一种唤醒登录方法
                        try:
                            logger.info(f"尝试使用AwakenLogin方法...")
                            uuid = await self.client.awaken_login(saved_wxid)
                            if uuid:
                                logger.info(f"AwakenLogin成功，获取到UUID: {uuid}")
                                # 检查登录状态
                                is_logged_in, login_data = await self.client.check_login_uuid(uuid)
                                if is_logged_in:
                                    logger.info(f"通过AwakenLogin方法登录成功")
                                    response = {"Success": True, "Message": "登录成功", "Data": login_data}
                                else:
                                    logger.warning(f"通过AwakenLogin方法登录失败: {login_data}")
                                    # 继续尝试TwiceAutoAuth
                                    response = await self.client.login_twice_auto_auth(saved_wxid, device_id, device_name)
                            else:
                                logger.warning(f"AwakenLogin失败，未获取到UUID")
                                # 继续尝试TwiceAutoAuth
                                response = await self.client.login_twice_auto_auth(saved_wxid, device_id, device_name)
                        except Exception as e:
                            logger.error(f"AwakenLogin出错: {e}")
                            # 继续尝试TwiceAutoAuth
                            response = await self.client.login_twice_auto_auth(saved_wxid, device_id, device_name)

                        if response.get("Success"):
                            logger.info(f"二次登录成功，wxid: {saved_wxid}")
                            self.logged_in = True
                            self.wxid = saved_wxid
                            self.client.wxid = saved_wxid

                            # 尝试获取昵称
                            try:
                                profile = await self.client.get_profile()
                                self.nickname = profile.get("NickName") or profile.get("nickName")
                                logger.info(f"获取到用户昵称: {self.nickname}")
                            except Exception as e:
                                logger.warning(f"获取用户昵称失败: {e}")
                                self.nickname = f"微信用户{saved_wxid[-6:]}" if len(saved_wxid) > 6 else f"微信用户{saved_wxid}"

                            # 尝试初始化
                            try:
                                init_response = await self.client.new_init()
                                logger.debug(f"初始化成功: {init_response.get('Success')}")
                            except Exception as e:
                                logger.warning(f"初始化失败: {e}")

                            # 保存配置到文件
                            try:
                                # 确保配置中有wxid和设备信息
                                login_config = self.config.get("login", {})
                                login_config["wxid"] = saved_wxid
                                login_config["device_name"] = device_name
                                login_config["device_id"] = device_id
                                self.config["login"] = login_config
                                logger.info(f"二次登录后的配置: {self.config}")

                                result = self.config_manager.save_config(self.config)
                                logger.info(f"保存配置到文件结果: {result}")
                                if result:
                                    logger.info("已成功保存登录配置到文件")
                                else:
                                    logger.error("保存配置到文件失败")
                            except Exception as e:
                                logger.error(f"保存配置到文件时出错: {e}")

                            return True
                        else:
                            logger.warning(f"二次登录失败，将尝试其他登录方式: {response.get('Message', '')}")
                    except Exception as e:
                        logger.error(f"二次登录时出错: {e}")
            except Exception as e:
                logger.error(f"唤醒登录时出错: {e}")

        try:
            if login_method == "qrcode":
                # 二维码登录
                device_name = self.config.get("login", {}).get("device_name", "")
                device_id = self.config.get("login", {}).get("device_id", "")

                # 如果没有设备名称，创建一个
                if not device_name:
                    device_name = self.client.create_device_name()

                # 如果没有设备ID，创建一个
                if not device_id:
                    device_id = self.client.create_device_id()

                # 获取登录二维码
                response = await self.client.login_qrcode(device_name, device_id)

                # 打印完整的响应信息，便于调试
                # 将二维码响应信息只记录到调试日志
                logger.debug(f"二维码响应信息: {response}")

                if response.get("Success"):
                    # 检查Data字段，这是实际数据所在的地方
                    data = response.get("Data", {})

                    # 尝试获取二维码图片或URL
                    qr_url = data.get("QrUrl", "")
                    qr_base64 = data.get("QrBase64", "")
                    qr_uuid = data.get("Uuid", "")

                    # 将二维码信息保存到文件
                    if qr_base64:
                        # 处理data:image/jpg;base64,前缀
                        if qr_base64.startswith('data:'):
                            # 分离出实际的base64数据
                            _, qr_base64_data = qr_base64.split(',', 1)
                        else:
                            qr_base64_data = qr_base64

                        # 将base64保存为图片文件
                        import base64
                        qr_file_path = "qrcode.png"
                        try:
                            with open(qr_file_path, "wb") as f:
                                f.write(base64.b64decode(qr_base64_data))

                            # 只显示二维码已保存的信息
                            logger.info(f"二维码已保存到: {qr_file_path}")
                        except Exception as e:
                            logger.error(f"保存二维码图片失败: {e}")

                    # 显示二维码链接和UUID，使用彩色和加粗显示
                    if qr_url:
                        # 尝试将URL转换为控制台二维码
                        try:
                            from xnbot.utils.qrcode_utils import generate_console_qrcode
                            from xnbot.utils.logger import BOLD, BRIGHT_CYAN, RESET
                            console_qrcode = generate_console_qrcode(qr_url)
                            # 在二维码下方显示链接，使用彩色和加粗
                            logger.info(f"{BOLD}请扫描二维码登录{RESET}\n{console_qrcode}\n{BRIGHT_CYAN}二维码链接: {qr_url}{RESET}")
                        except ImportError:
                            from xnbot.utils.logger import BOLD, BRIGHT_CYAN, RESET
                            logger.info(f"{BOLD}请扫描二维码登录{RESET}，{BRIGHT_CYAN}二维码URL: {qr_url}{RESET}")
                        except Exception as e:
                            logger.debug(f"生成控制台二维码失败: {e}")
                            from xnbot.utils.logger import BOLD, BRIGHT_CYAN, RESET
                            logger.info(f"{BOLD}请扫描二维码登录{RESET}，{BRIGHT_CYAN}二维码URL: {qr_url}{RESET}")

                    # 只显示UUID，不显示其他信息，使用彩色和加粗显示
                    if qr_uuid and not qr_url:
                        from xnbot.utils.logger import BOLD, BRIGHT_CYAN, RESET
                        logger.info(f"{BOLD}请扫描二维码登录{RESET}，{BRIGHT_CYAN}UUID: {qr_uuid}{RESET}")

                    if not (qr_url or qr_base64 or qr_uuid):
                        logger.info("请扫描二维码登录")

                    # 等待扫码登录
                    max_wait_time = 240  # 最长等待时间（秒）
                    wait_interval = 2  # 检查间隔（秒）

                    from xnbot.utils.logger import BOLD, BRIGHT_YELLOW, RESET
                    logger.info(f"{BOLD}{BRIGHT_YELLOW}等待扫码登录...{RESET}")

                    # 开始等待扫码
                    start_time = time.time()
                    last_log_time = 0  # 上次显示日志的时间
                    while time.time() - start_time < max_wait_time:
                        # 每30秒显示一次剩余时间
                        current_time = time.time()
                        if current_time - last_log_time >= 30:
                            remaining_time = max(0, max_wait_time - (current_time - start_time))
                            logger.info(f"等待扫码登录，剩余时间: {int(remaining_time)}秒")
                            last_log_time = current_time
                        # 检查登录状态
                        try:
                            # 如果有UUID，可以使用UUID查询登录状态
                            if qr_uuid:
                                # 使用客户端的check_login_uuid方法
                                is_logged_in, login_data = await self.client.check_login_uuid(qr_uuid, device_id)

                                if is_logged_in:
                                    # 登录成功
                                    logger.info(f"扫码登录成功，昵称: {login_data.get('nickname', '')}")

                                    # 从 acctSectResp 获取用户信息
                                    acct_sect_resp = login_data.get("acctSectResp", {})
                                    if acct_sect_resp:
                                        # 获取wxid和昵称
                                        self.wxid = acct_sect_resp.get("userName") or self.client.wxid
                                        self.nickname = acct_sect_resp.get("nickName") or login_data.get("nickname", "")
                                        self.client.wxid = self.wxid
                                        logger.debug(f"从 acctSectResp 获取到登录信息，wxid: {self.wxid}, 昵称: {self.nickname}")
                                    elif self.client.wxid:
                                        # 如果没有acctSectResp但客户端有wxid，使用客户端的wxid
                                        self.wxid = self.client.wxid
                                        self.nickname = login_data.get("nickname", "")
                                        logger.debug(f"使用客户端的wxid: {self.wxid}, 昵称: {self.nickname}")

                                    # 设置登录状态
                                    self.logged_in = True

                                    # 保存设备信息和微信ID到配置
                                    login_config = self.config.get("login", {})
                                    if device_name and device_id:
                                        login_config["device_name"] = device_name
                                        login_config["device_id"] = device_id

                                    # 保存微信ID以便二次登录
                                    if self.wxid:
                                        login_config["wxid"] = self.wxid
                                        logger.info(f"已保存微信ID到配置: {self.wxid}")
                                    else:
                                        logger.warning("没有wxid可以保存到配置")

                                    self.config["login"] = login_config
                                    logger.info(f"更新后的配置: {self.config}")

                                    # 保存配置到文件
                                    try:
                                        result = self.config_manager.save_config(self.config)
                                        logger.info(f"保存配置到文件结果: {result}")
                                        if result:
                                            logger.info("已成功保存登录配置到文件")
                                        else:
                                            logger.error("保存配置到文件失败")
                                    except Exception as e:
                                        logger.error(f"保存配置到文件时出错: {e}")

                                    # 如果昵称为空，使用默认昵称
                                    if not self.nickname and self.wxid:
                                        self.nickname = "微信用户" + self.wxid[-6:]
                                    elif not self.nickname:
                                        self.nickname = "未知用户"

                                    # 尝试初始化
                                    try:
                                        init_response = await self.client.new_init()
                                        logger.debug(f"初始化成功: {init_response.get('Success')}")
                                    except Exception as e:
                                        logger.warning(f"初始化失败: {e}")

                                    # 尝试启动心跳
                                    try:
                                        await self.client.heartbeat()
                                        logger.debug("发送心跳成功")

                                        # 如果有自动心跳方法，尝试启动
                                        if hasattr(self.client, 'start_auto_heartbeat'):
                                            await self.client.start_auto_heartbeat()
                                            logger.info("启动自动心跳成功")
                                    except Exception as e:
                                        logger.warning(f"心跳初始化失败: {e}")

                                    # 尝试获取用户信息
                                    try:
                                        profile = await self.client.get_profile()
                                        logger.debug(f"获取个人信息成功: {profile.get('Success')}")
                                    except Exception as e:
                                        logger.warning(f"获取个人信息失败: {e}")

                                    # 登录成功
                                    logger.info(f"登录成功，昵称: {self.nickname}")
                                    return True

                                # 如果未登录成功，检查状态
                                if isinstance(login_data, dict) and "status" in login_data:
                                    status = login_data.get("status")
                                    message = login_data.get("message", "")

                                    # 如果状态为1，表示已扫码但未确认
                                    if status == 1:
                                        nickname = login_data.get("nickname", "")
                                        from xnbot.utils.logger import BOLD, BRIGHT_CYAN, RESET
                                        logger.info(f"{BOLD}{BRIGHT_CYAN}已扫码，等待确认登录{RESET}，昵称: {BOLD}{nickname}{RESET}")
                                    # 如果状态为0，表示等待扫码
                                    elif status == 0:
                                        # 不输出过多的等待日志
                                        pass
                                    # 如果状态为-1，表示未知状态，可能需要再次检查
                                    elif status == -1:
                                        logger.debug(f"扫码状态: {message}")
                                        # 尝试再次检查状态
                                        status_response = await self.client.check_login_status(qr_uuid)
                                        # 只记录到调试日志，不在普通日志中显示
                                        logger.debug("再次检查扫码状态")

                                        # 检查是否有昵称或wxid或acctSectResp
                                        data = status_response.get("Data", {})
                                        nickname = data.get("nickName")
                                        wxid = data.get("wxid")
                                        acct_sect_resp = data.get("acctSectResp", {})

                                        if nickname or wxid or acct_sect_resp:
                                            logger.debug(f"检测到可能已登录成功，昵称: {nickname}, wxid: {wxid}")
                                            # 尝试强制设置登录状态
                                            self.logged_in = True

                                            # 如果有acctSectResp，优先使用它
                                            if acct_sect_resp:
                                                self.wxid = acct_sect_resp.get("userName", "")
                                                self.nickname = acct_sect_resp.get("nickName", "")
                                                self.client.wxid = self.wxid
                                                logger.debug(f"从 acctSectResp 获取到登录信息，wxid: {self.wxid}, 昵称: {self.nickname}")
                                            # 否则使用wxid和昵称
                                            elif wxid:
                                                self.wxid = wxid
                                                self.client.wxid = wxid
                                                self.nickname = nickname or "未知用户"
                                            else:
                                                self.wxid = f"user_{nickname}"
                                                self.client.wxid = self.wxid
                                                self.nickname = nickname or "未知用户"

                                            logger.info(f"登录成功，昵称: {self.nickname}")
                                            return True
                                    # 其他状态
                                    else:
                                        logger.debug(f"扫码状态: {message}")
                                else:
                                    # 如果没有状态信息，使用原来的方式检查状态
                                    status_response = await self.client.check_login_status(qr_uuid)
                                    # 只记录到调试日志，不在普通日志中显示
                                    logger.debug("检查扫码状态")

                                    # 检查是否有昵称或wxid
                                    data = status_response.get("Data", {})
                                    nickname = data.get("nickName")
                                    wxid = data.get("wxid")

                                    if nickname or wxid:
                                        logger.debug(f"检测到可能已登录成功，昵称: {nickname}, wxid: {wxid}")
                                        # 尝试强制设置登录状态
                                        self.logged_in = True
                                        if wxid:
                                            self.wxid = wxid
                                            self.client.wxid = wxid
                                        else:
                                            self.wxid = f"user_{nickname}"
                                            self.client.wxid = self.wxid

                                        self.nickname = nickname or "未知用户"
                                        from xnbot.utils.logger import BOLD, BRIGHT_GREEN, RESET
                                        logger.info(f"{BOLD}{BRIGHT_GREEN}登录成功！{RESET} 昵称: {BOLD}{self.nickname}{RESET}")
                                        return True

                                # 显示剩余时间
                                remaining_time = max_wait_time - (time.time() - start_time)
                                from xnbot.utils.logger import BRIGHT_YELLOW, RESET
                                logger.info(f"{BRIGHT_YELLOW}等待扫码登录... 剩余{int(remaining_time)}秒{RESET}")

                                # 等待一段时间再检查
                                await asyncio.sleep(wait_interval)
                        except Exception as e:
                            logger.error(f"检查登录状态时出错: {e}")

                        # 显示剩余时间
                        remaining_time = max_wait_time - (time.time() - start_time)
                        from xnbot.utils.logger import BRIGHT_YELLOW, RESET
                        logger.info(f"{BRIGHT_YELLOW}等待扫码登录... 剩余{int(remaining_time)}秒{RESET}")

                        # 等待一段时间再检查
                        await asyncio.sleep(wait_interval)

                logger.error("二维码登录失败或超时")
                return False

            elif login_method == "62data":
                # 62数据登录
                data62 = self.config.get("login", {}).get("data62", "")
                username = self.config.get("login", {}).get("username", "")
                password = self.config.get("login", {}).get("password", "")
                device_name = self.config.get("login", {}).get("device_name", "XNBot")

                if not data62:
                    logger.error("缺少62数据")
                    return False

                response = await self.client.login_with_62data(data62, username, password, device_name)

                if response.get("Success") and "Wxid" in response:
                    self.logged_in = True
                    self.wxid = response["Wxid"]
                    from xnbot.utils.logger import BOLD, BRIGHT_GREEN, RESET
                    logger.info(f"{BOLD}{BRIGHT_GREEN}62数据登录成功！{RESET} wxid: {BOLD}{self.wxid}{RESET}")
                    return True

                logger.error("62数据登录失败")
                return False

            else:
                logger.error(f"不支持的登录方式: {login_method}")
                return False

        except Exception as e:
            logger.error(f"登录时出错: {e}")
            return False

    async def _heartbeat_loop(self):
        """心跳循环"""
        try:
            while self.running and self.logged_in:
                try:
                    await self.client.heartbeat()
                    logger.debug("发送心跳")
                except Exception as e:
                    logger.error(f"发送心跳时出错: {e}")

                await asyncio.sleep(30)  # 每30秒发送一次心跳
        except asyncio.CancelledError:
            logger.info("心跳任务已取消")
            raise
        except Exception as e:
            logger.error(f"心跳循环出错: {e}")

    async def _on_message(self, message: Dict):
        """
        处理收到的消息

        Args:
            message: 消息数据
        """
        try:
            # 记录消息
            logger.info(f"收到消息: {message}")

            # 提取消息类型和内容
            msg_type = message.get("MsgType")
            content = message.get("Content", "")
            from_user = message.get("FromUserName", "")
            to_user = message.get("ToUserName", "")

            # 处理内容可能是字典的情况
            if isinstance(content, dict) and "string" in content:
                content = content["string"]
                logger.info(f"处理后的消息内容: {content}")

            # 处理发送者可能是字典的情况
            if isinstance(from_user, dict) and "string" in from_user:
                from_user = from_user["string"]
                logger.info(f"处理后的发送者: {from_user}")

            # 处理接收者可能是字典的情况
            if isinstance(to_user, dict) and "string" in to_user:
                to_user = to_user["string"]
                logger.info(f"处理后的接收者: {to_user}")

            logger.info(f"消息类型: {msg_type}, 发送者: {from_user}, 接收者: {to_user}, 内容: {content}")

            # 检查是否是管理员命令
            admin_wxids = self.config.get("bot", {}).get("admin_wxids", [])
            if from_user in admin_wxids and content and content.startswith("/"):
                logger.info(f"检测到管理员命令: {content}")

            # 交给插件处理
            logger.info("将消息交给插件管理器处理")
            await self.plugin_manager.handle_message(message)

            # 调用自定义处理器
            if self.message_handlers:
                logger.info(f"调用 {len(self.message_handlers)} 个自定义消息处理器")
                for handler in self.message_handlers:
                    try:
                        await handler(message)
                    except Exception as e:
                        logger.error(f"消息处理器出错: {e}")
                        import traceback
                        logger.error(f"异常详情: {traceback.format_exc()}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")

    def add_message_handler(self, handler: Callable):
        """
        添加消息处理器

        Args:
            handler: 消息处理函数
        """
        if handler not in self.message_handlers:
            self.message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable) -> bool:
        """
        移除消息处理器

        Args:
            handler: 消息处理函数

        Returns:
            是否成功移除
        """
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)
            return True
        return False

    # 便捷方法，用于发送消息
    async def send_text(self, to_wxid: str, content: str, at_list: Optional[List[str]] = None) -> Dict:
        """
        发送文本消息

        Args:
            to_wxid: 接收者wxid
            content: 消息内容
            at_list: 需要@的用户列表

        Returns:
            发送结果
        """
        logger.info(f"Bot准备发送文本消息: to={to_wxid}, content={content}, at_list={at_list}")

        # 处理接收者可能是字典的情况
        if isinstance(to_wxid, dict) and "string" in to_wxid:
            to_wxid = to_wxid["string"]
            logger.info(f"Bot处理后的接收者: {to_wxid}")

        try:
            logger.info(f"Bot调用client.send_text: to={to_wxid}, content={content}, at_list={at_list}")
            result = await self.client.send_text(to_wxid, content, at_list)
            logger.info(f"Bot发送文本消息结果: {result}")
            return result
        except Exception as e:
            logger.error(f"Bot发送文本消息出错: {e}")
            # 尝试打印异常详情
            import traceback
            logger.error(f"Bot发送文本消息异常详情: {traceback.format_exc()}")
            raise

    async def send_image(self, to_wxid: str, image_path: str) -> Dict:
        """
        发送图片消息

        Args:
            to_wxid: 接收者wxid
            image_path: 图片路径

        Returns:
            发送结果
        """
        # 读取图片并转为base64
        try:
            with open(image_path, "rb") as f:
                import base64
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            return await self.client.send_image(to_wxid, image_base64)
        except Exception as e:
            logger.error(f"发送图片时出错: {e}")
            raise

    async def send_voice(self, to_wxid: str, voice_path: str, voice_time: int = 1000) -> Dict:
        """
        发送语音消息

        Args:
            to_wxid: 接收者wxid
            voice_path: 语音文件路径
            voice_time: 语音时长（毫秒）

        Returns:
            发送结果
        """
        # 读取语音文件并转为base64
        try:
            with open(voice_path, "rb") as f:
                import base64
                voice_base64 = base64.b64encode(f.read()).decode("utf-8")

            return await self.client.send_voice(to_wxid, voice_base64, voice_time)
        except Exception as e:
            logger.error(f"发送语音时出错: {e}")
            raise

    async def send_link(self, to_wxid: str, title: str, desc: str, url: str, thumb_url: str) -> Dict:
        """
        发送链接消息

        Args:
            to_wxid: 接收者wxid
            title: 链接标题
            desc: 链接描述
            url: 链接URL
            thumb_url: 缩略图URL

        Returns:
            发送结果
        """
        return await self.client.send_link(to_wxid, title, desc, url, thumb_url)

    async def _sync_loop(self):
        """
        消息同步循环
        """
        try:
            logger.info("消息同步循环已启动")
            while self.running:
                try:
                    # 发送心跳包
                    heartbeat_response = await self.client.heartbeat()
                    logger.debug(f"心跳包响应状态: {heartbeat_response.get('Success')}")

                    # 如果心跳包中包含消息，处理消息
                    if heartbeat_response.get("Success") and "AddMsgs" in heartbeat_response.get("Data", {}):
                        msgs = heartbeat_response["Data"]["AddMsgs"]
                        if msgs:
                            logger.info(f"心跳包中收到 {len(msgs)} 条消息")
                            for msg in msgs:
                                await self._on_message(msg)

                    # 同步消息
                    response = await self.client.sync_message()
                    logger.debug(f"同步消息响应状态: {response.get('Success')}")

                    if not response.get("Success"):
                        logger.warning(f"同步消息失败: {response}")
                        await asyncio.sleep(5)  # 失败后等待时间长一些
                        continue

                    # 尝试从不同的字段获取消息
                    msgs = []

                    # 尝试直接从 AddMsgs 字段获取
                    if "AddMsgs" in response:
                        msgs = response["AddMsgs"]
                    # 尝试从 Data.AddMsgs 字段获取
                    elif "Data" in response and isinstance(response["Data"], dict) and "AddMsgs" in response["Data"]:
                        msgs = response["Data"]["AddMsgs"]

                    if msgs:
                        logger.info(f"收到 {len(msgs)} 条消息")
                        for msg in msgs:
                            await self._on_message(msg)

                    # 等待一小段时间再同步
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"同步消息出错: {e}")
                    await asyncio.sleep(5)  # 出错后等待时间长一些
        except asyncio.CancelledError:
            logger.info("消息同步循环已取消")
            raise
        except Exception as e:
            logger.error(f"消息同步循环出错: {e}")
