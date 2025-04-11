"""
微信API客户端
提供与微信API的异步交互功能
"""

import aiohttp
import asyncio
import json
import base64
import logging
import time
from typing import Dict, List, Optional, Union, Any

from xnbot.utils.logger import setup_logger

logger = logging.getLogger(__name__)

class WeChatAPIClient:
    """微信API异步客户端"""

    def __init__(self, api_base_url: str, timeout: int = 30):
        """
        初始化微信API客户端

        Args:
            api_base_url: API基础URL，例如 http://localhost:9011/VXAPI
            timeout: 请求超时时间（秒）
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.timeout = timeout
        self.session = None
        self.wxid = None
        self._message_queue = asyncio.Queue()
        self._sync_task = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                      params: Optional[Dict] = None) -> Dict:
        """
        发送API请求

        Args:
            method: HTTP方法 (GET, POST等)
            endpoint: API端点
            data: 请求体数据
            params: URL参数

        Returns:
            API响应数据
        """
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

        url = f"{self.api_base_url}{endpoint}"

        try:
            async with self.session.request(method, url, json=data, params=params) as response:
                response.raise_for_status()
                result = await response.json()
                return result
        except aiohttp.ClientResponseError as e:
            logger.error(f"API请求错误: {e}")
            # 如果是404错误，返回一个空的成功响应，而不是抛出异常
            if e.status == 404:
                return {"Success": True, "Data": {}, "Message": "接口不存在但继续执行"}
            raise
        except aiohttp.ClientError as e:
            logger.error(f"API连接错误: {e}")
            raise

    # 登录相关方法
    def create_device_name(self) -> str:
        """
        创建随机设备名称

        Returns:
            设备名称
        """
        import random
        import string
        prefix = "XNBot-"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return prefix + suffix

    def create_device_id(self) -> str:
        """
        创建随机设备ID

        Returns:
            设备ID
        """
        import random
        import string
        import uuid
        return str(uuid.uuid4())

    async def login_awaken(self, wxid: str, device_name: str = "XNBot", device_id: str = "", os_model: str = "Ipad") -> Dict:
        """
        唤醒登录（只限扫码登录）

        Args:
            wxid: 微信ID
            device_name: 设备名称 (仅用于记录，不发送给API)
            device_id: 设备ID (仅用于记录，不发送给API)
            os_model: 操作系统模型

        Returns:
            登录响应
        """
        # 根据API文档，只需要OSModel和Wxid两个参数
        data = {
            "OSModel": os_model,
            "Wxid": wxid
        }
        logger.info(f"尝试唤醒登录: {data}")
        try:
            response = await self._request("POST", "/Login/Awaken", data=data)
            logger.info(f"唤醒登录响应: {response}")

            # 如果登录成功，设置wxid
            if response.get("Success"):
                self.wxid = wxid
                logger.info(f"唤醒登录成功，wxid: {wxid}")
            return response
        except Exception as e:
            logger.error(f"唤醒登录失败: {e}")
            return {"Success": False, "Message": f"唤醒登录失败: {e}"}

    async def login_twice_auto_auth(self, wxid: str, device_id: str = "", device_name: str = "XNBot", os_model: str = "Ipad") -> Dict:
        """
        二次登录（自动认证）

        Args:
            wxid: 微信ID
            device_id: 设备ID (仅用于记录，不发送给API)
            device_name: 设备名称 (仅用于记录，不发送给API)
            os_model: 操作系统模型

        Returns:
            登录响应
        """
        # 根据API文档，只需要OSModel和Wxid两个参数
        data = {
            "OSModel": os_model,
            "Wxid": wxid
        }
        logger.info(f"尝试二次登录: {data}")
        try:
            response = await self._request("POST", "/Login/TwiceAutoAuth", data=data)
            logger.info(f"二次登录响应: {response}")

            # 如果登录成功，设置wxid
            if response.get("Success"):
                self.wxid = wxid
                logger.info(f"二次登录成功，wxid: {wxid}")
            return response
        except Exception as e:
            logger.error(f"二次登录失败: {e}")
            return {"Success": False, "Message": f"二次登录失败: {e}"}

    async def login_qrcode(self, device_name: str = "XNBot", device_id: str = "") -> Dict:
        """
        获取登录二维码

        Args:
            device_name: 设备名称
            device_id: 设备ID

        Returns:
            包含二维码信息的响应
        """
        if not device_name:
            device_name = self.create_device_name()
        if not device_id:
            device_id = self.create_device_id()

        # 尝试使用不同的参数格式和值
        data = {
            "DeviceName": device_name,
            "DeviceID": device_id,
            "OSModel": "Ipad",
            "Proxy": {}
        }
        # 发送请求获取二维码
        response = await self._request("POST", "/Login/GetQR", data=data)

        # 隐藏详细的响应信息，只记录到调试日志
        logger.debug(f"获取二维码响应: {response}")

        return response

    async def check_login_status(self, uuid: str) -> Dict:
        """
        检查登录状态

        Args:
            uuid: 二维码UUID

        Returns:
            登录状态响应
        """
        return await self._request("POST", "/Login/CheckQR", params={"uuid": uuid})

    async def check_login_uuid(self, uuid: str, device_id: str = "") -> tuple:
        """
        检查登录UUID状态

        Args:
            uuid: 二维码UUID
            device_id: 设备ID (仅用于记录，不发送给API)

        Returns:
            (bool, data) - 是否登录成功，成功时data为用户信息，失败时data为剩余时间
        """
        try:
            # 检查登录状态
            response = await self.check_login_status(uuid)

            # 获取状态信息
            data = response.get("Data", {})
            status = data.get("status")

            # 状态码含义：
            # 0: 等待扫码
            # 1: 已扫码，等待确认
            # 2: 已确认，登录成功
            # 3: 已取消
            # 4: 超时
            # None: 可能也表示登录成功，需要检查其他字段

            # 检查是否有登录成功的关键字段
            acct_sect_resp = data.get("acctSectResp", {})
            if acct_sect_resp:
                # 如果有acctSectResp字段，表示登录成功
                wxid = acct_sect_resp.get("userName")
                nickname = acct_sect_resp.get("nickName")

                # 如果没有wxid或昵称，尝试从其他字段获取
                if not wxid:
                    wxid = data.get("wxid") or ""
                if not nickname:
                    nickname = data.get("nickName") or ""

                # 如果还是没有wxid，生成一个临时ID
                if not wxid and nickname:
                    wxid = f"user_{int(time.time())}"
                    logger.warning(f"未找到真实wxid，使用临时ID: {wxid}")
                elif not wxid:
                    wxid = f"user_{int(time.time())}"
                    logger.warning(f"未找到真实wxid，使用临时ID: {wxid}")

                # 更新acctSectResp中的信息
                acct_sect_resp["userName"] = wxid
                acct_sect_resp["nickName"] = nickname

                user_info = {
                    "acctSectResp": acct_sect_resp,
                    "nickname": nickname  # 添加nickname字段到返回数据中
                }

                # 设置wxid和昵称
                self.wxid = wxid
                if nickname:
                    self.nickname = nickname
                    logger.debug(f"从 acctSectResp 获取到登录信息，wxid: {wxid}, 昵称: {nickname}")
                else:
                    # 如果没有昵称，生成一个默认昵称
                    self.nickname = f"微信用户{wxid[-6:]}" if len(wxid) > 6 else f"微信用户{wxid}"
                    logger.debug(f"从 acctSectResp 获取到登录信息，wxid: {wxid}，使用默认昵称: {self.nickname}")

                return True, user_info

            # 如果状态为2或者状态为None但有昵称，表示已确认登录
            nickname = data.get("nickName")
            if status == 2 or (status is None and nickname):
                # 获取用户信息
                try:
                    # 如果有二维码URL，尝试使用新设备登录接口
                    qr_url = data.get("QrUrl")
                    wxid = data.get("wxid")
                    nickname = data.get("nickName")

                    if wxid:
                        # 如果直接有wxid，使用它
                        user_info = {
                            "acctSectResp": {
                                "userName": wxid,
                                "nickName": nickname,
                                "alias": "",
                                "bindMobile": ""
                            },
                            "nickname": nickname  # 添加nickname字段到返回数据中
                        }
                        # 设置wxid和昵称
                        self.wxid = wxid
                        if nickname:
                            self.nickname = nickname
                            logger.info(f"从登录数据获取到登录信息，wxid: {wxid}, 昵称: {nickname}")
                        else:
                            # 如果没有昵称，生成一个默认昵称
                            self.nickname = f"微信用户{wxid[-6:]}" if len(wxid) > 6 else f"微信用户{wxid}"
                            logger.info(f"从登录数据获取到登录信息，wxid: {wxid}，使用默认昵称: {self.nickname}")
                        return True, user_info

                    if qr_url and "weixin.qq.com/x/" in qr_url:
                        # 提取URL中的关键部分
                        url_parts = qr_url.split("weixin.qq.com/x/")
                        if len(url_parts) > 1:
                            wx_url = f"http://weixin.qq.com/x/{url_parts[1]}"
                            logger.info(f"尝试使用新设备登录接口，URL: {wx_url}")

                            # 获取登录确认信息
                            confirm_info = await self.ext_device_login_confirm_get(wx_url)
                            logger.info(f"新设备登录确认信息: {confirm_info}")

                            # 检查是否有wxid
                            confirm_wxid = confirm_info.get("Data", {}).get("Wxid") or confirm_info.get("Wxid")

                            if confirm_wxid:
                                # 确认登录
                                user_info = await self.ext_device_login_confirm_ok(wx_url, confirm_wxid)
                                logger.info(f"新设备登录确认响应: {user_info}")

                                # 设置wxid
                                self.wxid = confirm_wxid

                                # 返回登录成功和用户信息
                                return True, user_info

                    # 如果没有成功获取wxid，使用状态信息和昵称生成一个用户名
                    if nickname:
                        user_info = {
                            "acctSectResp": {
                                "userName": f"user_{nickname}",
                                "nickName": nickname,
                                "alias": "",
                                "bindMobile": ""
                            }
                        }
                        return True, user_info

                except Exception as e:
                    logger.error(f"获取用户信息失败: {e}")
                    # 如果获取用户信息失败，使用状态信息
                    if nickname:
                        user_info = {
                            "acctSectResp": {
                                "userName": f"user_{nickname}",
                                "nickName": nickname,
                                "alias": "",
                                "bindMobile": ""
                            }
                        }
                        return True, user_info

            # 如果状态为1，表示已扫码但未确认
            elif status == 1:
                # 返回状态信息，包含昵称等
                return False, {"status": 1, "nickname": data.get("nickName"), "message": "已扫码，等待确认"}

            # 如果状态为None但没有昵称，可能是未知状态
            elif status is None and not nickname:
                # 返回未知状态
                return False, {"status": -1, "message": "未知状态"}

            # 如果状态为0，表示等待扫码
            elif status == 0:
                # 返回剩余时间
                expires_in = data.get("expiredTime", 0)
                return False, {"status": 0, "expires_in": expires_in, "message": "等待扫码"}

            # 如果有昵称或wxid，可能已经登录成功
            elif data.get("nickName") or data.get("wxid"):
                nickname = data.get("nickName", "")
                wxid = data.get("wxid", "")
                user_info = {
                    "acctSectResp": {
                        "userName": wxid or f"user_{nickname}",
                        "nickName": nickname,
                        "alias": "",
                        "bindMobile": ""
                    }
                }
                # 设置wxid
                if wxid:
                    self.wxid = wxid
                return True, user_info

            # 其他状态，返回失败
            else:
                return False, {"status": status, "message": f"未知状态: {status}"}

        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False, {"status": -1, "message": f"检查登录状态失败: {e}"}

    async def is_logged_in(self, wxid: str = None) -> bool:
        """
        检查是否已登录

        Args:
            wxid: 微信ID，如果为None则使用当前实例的wxid

        Returns:
            是否已登录
        """
        if wxid is None:
            wxid = self.wxid

        if not wxid:
            return False

        try:
            # 尝试获取个人信息
            response = await self._request("POST", "/Contact/GetProfile")
            return response.get("Success", False)
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False

    async def get_profile(self) -> Dict:
        """
        获取个人信息

        Returns:
            个人信息
        """
        response = await self._request("POST", "/Contact/GetProfile")
        return response.get("Data", {})

    async def get_cached_info(self, wxid: str) -> Dict:
        """
        获取缓存的用户信息

        Args:
            wxid: 微信ID

        Returns:
            缓存的用户信息
        """
        try:
            response = await self._request("POST", "/Contact/GetCachedInfo", data={"wxid": wxid})
            return response.get("Data", {})
        except Exception as e:
            logger.error(f"获取缓存的用户信息失败: {e}")
            return {}

    async def awaken_login(self, wxid: str) -> str:
        """
        唤醒登录

        Args:
            wxid: 微信ID

        Returns:
            登录UUID
        """
        try:
            response = await self._request("POST", "/Login/AwakenLogin", data={"wxid": wxid})
            return response.get("Data", {}).get("uuid", "")
        except Exception as e:
            logger.error(f"唤醒登录失败: {e}")
            return ""

    async def ext_device_login_confirm_get(self, url: str, wxid: str = "") -> Dict:
        """
        新设备扫码登录

        Args:
            url: 二维码URL
            wxid: 微信ID（可选）

        Returns:
            登录响应
        """
        data = {
            "Url": url,
            "Wxid": wxid
        }
        logger.info(f"调用新设备登录确认接口: {data}")
        response = await self._request("POST", "/Login/ExtDeviceLoginConfirmGet", data=data)
        logger.info(f"新设备登录确认响应: {response}")

        # 如果成功，尝试提取wxid
        if response.get("Success"):
            data = response.get("Data", {})
            if isinstance(data, dict):
                # 尝试从各种可能的字段获取wxid
                wxid = data.get("Wxid") or data.get("wxid") or data.get("UserName")
                if wxid:
                    self.wxid = wxid
                    logger.info(f"从 ExtDeviceLoginConfirmGet 响应中获取到wxid: {wxid}")

                # 如果有昵称，也记录下来
                nickname = data.get("NickName") or data.get("nickName")
                if nickname:
                    self.nickname = nickname
                    logger.info(f"从 ExtDeviceLoginConfirmGet 响应中获取到昵称: {nickname}")

        return response

    async def ext_device_login_confirm_ok(self, url: str, wxid: str) -> Dict:
        """
        新设备扫码确认登录

        Args:
            url: 二维码URL
            wxid: 微信ID

        Returns:
            登录响应
        """
        data = {
            "Url": url,
            "Wxid": wxid
        }
        logger.info(f"调用新设备登录确认OK接口: {data}")
        response = await self._request("POST", "/Login/ExtDeviceLoginConfirmOk", data=data)
        logger.info(f"新设备登录确认OK响应: {response}")

        # 如果登录成功，设置wxid
        if response.get("Success"):
            # 尝试从不同字段获取wxid
            real_wxid = None
            data = response.get("Data", {})

            if isinstance(data, dict):
                # 尝试从各种可能的字段获取wxid
                real_wxid = data.get("Wxid") or data.get("wxid") or data.get("UserName")

                # 如果有昵称，也记录下来
                nickname = data.get("NickName") or data.get("nickName")
                if nickname:
                    self.nickname = nickname
                    logger.info(f"从登录响应中获取到昵称: {nickname}")

            # 如果找到了真实的wxid，则更新
            if real_wxid:
                self.wxid = real_wxid
                logger.info(f"设置真实wxid: {self.wxid}")
            else:
                # 尝试从 acctSectResp 获取wxid
                acct_sect_resp = data.get("acctSectResp", {})
                if acct_sect_resp and isinstance(acct_sect_resp, dict):
                    user_name = acct_sect_resp.get("userName")
                    if user_name:
                        self.wxid = user_name
                        logger.info(f"从 acctSectResp 获取到wxid: {self.wxid}")

                        # 如果有昵称，也记录下来
                        nick_name = acct_sect_resp.get("nickName")
                        if nick_name:
                            self.nickname = nick_name
                            logger.info(f"从 acctSectResp 获取到昵称: {self.nickname}")
                    else:
                        logger.warning("无法从 acctSectResp 获取wxid")
                else:
                    logger.warning("无法从登录响应中获取真实wxid")

        return response

    async def login_with_62data(self, data62: str, username: str = "", password: str = "",
                               device_name: str = "XNBot") -> Dict:
        """
        使用62数据登录

        Args:
            data62: 62数据
            username: 用户名（可选）
            password: 密码（可选）
            device_name: 设备名称

        Returns:
            登录响应
        """
        data = {
            "Data62": data62,
            "UserName": username,
            "Password": password,
            "DeviceName": device_name,
            "Proxy": {}
        }
        response = await self._request("POST", "/Login/62data", data=data)
        if response.get("Success") and "Wxid" in response:
            self.wxid = response["Wxid"]
        return response

    async def get_cache_info(self) -> Dict:
        """
        获取登录缓存信息

        Returns:
            登录缓存信息
        """
        if not self.wxid:
            raise ValueError("未登录")

        params = {"wxid": self.wxid}
        logger.info(f"调用GetCacheInfo接口: {params}")
        response = await self._request("POST", "/Login/GetCacheInfo", params=params)
        logger.info(f"GetCacheInfo响应: {response}")
        return response

    async def new_init(self) -> Dict:
        """
        初始化

        Returns:
            初始化响应
        """
        if not self.wxid:
            raise ValueError("未登录")

        params = {"wxid": self.wxid}
        logger.info(f"调用Newinit接口: {params}")
        response = await self._request("POST", "/Login/Newinit", params=params)
        logger.info(f"Newinit响应: {response}")
        return response

    async def get_profile(self) -> Dict:
        """
        获取个人信息

        Returns:
            个人信息
        """
        if not self.wxid:
            raise ValueError("未登录")

        # 尝试多种可能的API端点
        api_endpoints = [
            {"method": "POST", "path": "/User/GetContractProfile", "params": {"wxid": self.wxid}},
            {"method": "GET", "path": "/User/GetProfile", "params": {"wxid": self.wxid}},
            {"method": "POST", "path": "/User/GetProfile", "params": {"wxid": self.wxid}},
            {"method": "POST", "path": "/Contact/GetProfile", "params": {"wxid": self.wxid}},
            {"method": "GET", "path": "/Contact/GetProfile", "params": {"wxid": self.wxid}},
            {"method": "POST", "path": "/Contact/GetContractProfile", "params": {"wxid": self.wxid}},
        ]

        # 尝试每个端点
        for endpoint in api_endpoints:
            try:
                logger.info(f"调用{endpoint['path']}接口获取个人信息: {endpoint['params']}")
                response = await self._request(endpoint['method'], endpoint['path'], params=endpoint['params'])
                logger.info(f"{endpoint['path']}响应: {response}")

                if response.get("Success"):
                    # 如果成功，更新昵称
                    data = response.get("Data", {})
                    if isinstance(data, dict):
                        nickname = data.get("nickName") or data.get("NickName")
                        if nickname:
                            self.nickname = nickname
                            logger.info(f"从个人信息中获取到昵称: {self.nickname}")
                    return response
            except Exception as e:
                logger.warning(f"使用{endpoint['path']}获取个人信息失败: {e}")

        # 如果所有方法都失败，返回一个成功的空响应
        logger.info("所有获取个人信息的方法都失败，返回默认信息")
        return {"Success": True, "Message": "成功", "Data": {"nickName": self.nickname or "未知用户"}}

    async def logout(self) -> Dict:
        """
        退出登录

        Returns:
            退出登录响应
        """
        if not self.wxid:
            raise ValueError("未登录")

        params = {"wxid": self.wxid}
        response = await self._request("POST", "/Login/LogOut", params=params)
        if response.get("Success"):
            self.wxid = None
        return response

    async def heartbeat(self) -> Dict:
        """
        发送心跳包

        Returns:
            心跳响应
        """
        if not self.wxid:
            raise ValueError("未登录")

        params = {"wxid": self.wxid}
        return await self._request("POST", "/Login/HeartBeat", params=params)

    # 用户信息相关方法
    # 注意: get_profile 方法已在前面定义，这里不再重复定义

    async def get_user_info(self, wxid: str) -> Dict:
        """
        获取用户信息

        Args:
            wxid: 用户wxid

        Returns:
            用户信息
        """
        if not self.wxid:
            raise ValueError("未登录")

        params = {"wxid": self.wxid, "toWxid": wxid}
        return await self._request("GET", "/User/GetInfo", params=params)

    # 消息相关方法
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
        logger.info(f"准备发送文本消息: to={to_wxid}, content={content}, at_list={at_list}")

        if not self.wxid:
            error_msg = "未登录无法发送消息"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 处理接收者可能是字典的情况
        if isinstance(to_wxid, dict) and "string" in to_wxid:
            to_wxid = to_wxid["string"]
            logger.info(f"处理后的接收者: {to_wxid}")

        data = {
            "Wxid": self.wxid,
            "ToWxid": to_wxid,
            "Content": content,
            "Type": 1
        }

        if at_list:
            data["At"] = ",".join(at_list)

        logger.info(f"发送文本消息请求数据: {data}")
        try:
            result = await self._request("POST", "/Msg/SendTxt", data=data)
            logger.info(f"发送文本消息响应: {result}")
            return result
        except Exception as e:
            logger.error(f"发送文本消息出错: {e}")
            raise

    async def send_image(self, to_wxid: str, image_base64: str) -> Dict:
        """
        发送图片消息

        Args:
            to_wxid: 接收者wxid
            image_base64: 图片的base64编码

        Returns:
            发送结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ToWxid": to_wxid,
            "Base64": image_base64
        }

        return await self._request("POST", "/Msg/UploadImg", data=data)

    async def send_voice(self, to_wxid: str, voice_base64: str, voice_time: int = 1000,
                        voice_type: int = 4) -> Dict:
        """
        发送语音消息

        Args:
            to_wxid: 接收者wxid
            voice_base64: 语音的base64编码
            voice_time: 语音时长（毫秒）
            voice_type: 语音类型 (0=AMR, 1=SPEEX, 2=MP3, 3=WAVE, 4=SILK)

        Returns:
            发送结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ToWxid": to_wxid,
            "Base64": voice_base64,
            "VoiceTime": voice_time,
            "Type": voice_type
        }

        return await self._request("POST", "/Msg/SendVoice", data=data)

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
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ToWxid": to_wxid,
            "Title": title,
            "Desc": desc,
            "Url": url,
            "ThumbUrl": thumb_url
        }

        return await self._request("POST", "/Msg/SendShareLink", data=data)

    async def revoke_message(self, to_wxid: str, client_msg_id: int,
                           create_time: int, new_msg_id: int) -> Dict:
        """
        撤回消息

        Args:
            to_wxid: 接收者wxid
            client_msg_id: 客户端消息ID
            create_time: 创建时间
            new_msg_id: 新消息ID

        Returns:
            撤回结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ToUserName": to_wxid,
            "ClientMsgId": client_msg_id,
            "CreateTime": create_time,
            "NewMsgId": new_msg_id
        }

        return await self._request("POST", "/Msg/Revoke", data=data)

    # 消息同步相关方法
    async def sync_message(self, scene: int = 1, sync_msg_digest: int = 1) -> Dict:
        """
        同步消息

        Args:
            scene: 场景值 (1=同步消息, 7=初始化消息)
            sync_msg_digest: 同步消息摘要

        Returns:
            同步结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "Scene": scene,
            "SyncMsgDigest": sync_msg_digest
        }

        # 尝试使用新的接口路径
        try:
            response = await self._request("POST", "/Msg/Sync", data=data)
            if response.get("Success") and "AddMsgs" in response.get("Data", {}):
                # 如果消息在 Data 字段中，将其提取出来
                response["AddMsgs"] = response["Data"]["AddMsgs"]
            return response
        except Exception as e:
            logger.error(f"同步消息出错: {e}")
            return {"Success": False, "Message": str(e)}

    async def start_message_sync(self, callback):
        """
        开始消息同步循环

        Args:
            callback: 收到消息时的回调函数
        """
        if self._sync_task is not None:
            return

        self._sync_task = asyncio.create_task(self._sync_loop(callback))

    async def stop_message_sync(self):
        """停止消息同步循环"""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

    async def _sync_loop(self, callback):
        """
        消息同步循环

        Args:
            callback: 收到消息时的回调函数
        """
        try:
            logger.info("消息同步循环已启动")

            # 先初始化消息
            logger.info("正在初始化消息同步...")
            init_response = await self.sync_message(scene=7, sync_msg_digest=1)
            logger.info(f"消息同步初始化响应: {init_response}")

            while True:
                try:
                    # 同步消息
                    response = await self.sync_message()

                    # 添加更多日志记录
                    logger.debug(f"消息同步响应: {response}")

                    # 处理消息
                    if response.get("Success") and "AddMsgs" in response:
                        msgs = response["AddMsgs"]
                        logger.debug(f"收到 {len(msgs)} 条消息")
                        for msg in msgs:
                            logger.debug(f"处理消息: {msg}")
                            await callback(msg)
                    else:
                        logger.debug("没有新消息")

                    # 发送心跳
                    await self.heartbeat()

                    # 等待一段时间再同步
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"消息同步错误: {e}")
                    await asyncio.sleep(5)  # 出错后等待更长时间
        except asyncio.CancelledError:
            logger.info("消息同步已取消")
            raise
        except Exception as e:
            logger.error(f"消息同步循环错误: {e}")

    # 联系人相关方法
    async def get_contact_list(self) -> Dict:
        """
        获取联系人列表

        Returns:
            联系人列表
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "CurrentWxcontactSeq": 0
        }

        return await self._request("POST", "/Friend/GetContractList", data=data)

    async def search_contact(self, keyword: str) -> Dict:
        """
        搜索联系人

        Args:
            keyword: 搜索关键词

        Returns:
            搜索结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ToUserName": keyword,
            "FromScene": 0,
            "SearchScene": 1
        }

        return await self._request("POST", "/Friend/Search", data=data)

    # 群组相关方法
    async def get_group_list(self) -> Dict:
        """
        获取群组列表

        Returns:
            群组列表
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "Key": ""
        }

        return await self._request("POST", "/Group/GroupListApi", data=data)

    async def get_group_members(self, group_id: str) -> Dict:
        """
        获取群成员

        Args:
            group_id: 群ID

        Returns:
            群成员列表
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "QID": group_id
        }

        return await self._request("POST", "/Group/GetChatRoomMemberDetail", data=data)

    async def create_group(self, member_list: List[str]) -> Dict:
        """
        创建群聊

        Args:
            member_list: 成员wxid列表

        Returns:
            创建结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        if len(member_list) < 2:
            raise ValueError("创建群聊至少需要2个成员")

        data = {
            "Wxid": self.wxid,
            "ToWxids": ",".join(member_list)
        }

        return await self._request("POST", "/Group/CreateChatRoom", data=data)

    async def add_group_member(self, group_id: str, member_list: List[str]) -> Dict:
        """
        添加群成员

        Args:
            group_id: 群ID
            member_list: 要添加的成员wxid列表

        Returns:
            添加结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ChatRoomName": group_id,
            "ToWxids": ",".join(member_list)
        }

        return await self._request("POST", "/Group/AddChatRoomMember", data=data)

    async def remove_group_member(self, group_id: str, member_list: List[str]) -> Dict:
        """
        删除群成员

        Args:
            group_id: 群ID
            member_list: 要删除的成员wxid列表

        Returns:
            删除结果
        """
        if not self.wxid:
            raise ValueError("未登录")

        data = {
            "Wxid": self.wxid,
            "ChatRoomName": group_id,
            "ToWxids": ",".join(member_list)
        }

        return await self._request("POST", "/Group/DelChatRoomMember", data=data)

    async def download_file(self, msg_id: str, attach_id = None, app_id: str = None, data_len: int = 0, user_name: str = None) -> Dict:
        """
        下载文件

        Args:
            msg_id: 消息ID
            attach_id: 附件ID，从 XML 中提取
            app_id: 应用ID，从 XML 中提取
            data_len: 文件大小，从 XML 中提取
            user_name: 用户名，从消息中提取

        Returns:
            下载结果，包含文件数据
        """
        if not self.wxid:
            raise ValueError("未登录")

        # 从消息中获取文件信息
        try:
            # 首先获取文件信息
            logger.info(f"尝试获取文件信息: MsgId={msg_id}, AttachId={attach_id}")

            # 如果有 attach_id，尝试使用 /Tools/DownloadFile 接口
            if attach_id:
                # 确保 attach_id 是字符串类型
                attach_id_str = str(attach_id)

                # 构建下载请求
                data = {
                    "AppID": app_id or "",
                    "AttachId": attach_id_str,  # 使用附件ID，确保是字符串类型
                    "DataLen": data_len or 0,
                    "Section": {
                        "DataLen": data_len or 0,
                        "StartPos": 0
                    },
                    "UserName": user_name or "",
                    "Wxid": self.wxid
                }

                # 尝试使用 /Tools/DownloadFile 接口
                logger.info(f"尝试使用 DownloadFile 下载文件: {data}")
                response = await self._request("POST", "/Tools/DownloadFile", data=data)

                if response.get("Success", False):
                    logger.info("使用 DownloadFile 下载文件成功")
                    # 输出完整的响应信息以便调试
                    logger.info(f"下载文件响应: {response}")

                    # 模拟成功响应的格式
                    if "Data" not in response:
                        response["Data"] = {}

                    # 确保有文件数据和文件名
                    if "FileData" not in response["Data"]:
                        # 如果没有文件数据，尝试从响应中提取
                        if "FileData" in response:
                            response["Data"]["FileData"] = response["FileData"]
                        elif "Data" in response and isinstance(response["Data"], str):
                            response["Data"] = {"FileData": response["Data"]}
                        elif "Data" in response and isinstance(response["Data"], dict):
                            # 检查所有可能的字段名
                            for field in ["FileData", "FileContent", "Content", "Data", "Base64Data", "Base64Content"]:
                                if field in response["Data"]:
                                    response["Data"]["FileData"] = response["Data"][field]
                                    logger.info(f"从响应中提取到文件数据，字段名: {field}")
                                    break

                    # 确保有文件名
                    if "FileName" not in response["Data"]:
                        response["Data"]["FileName"] = f"file_{msg_id}_{int(time.time())}"

                    return response
                else:
                    logger.error(f"使用 DownloadAppAttach 下载文件失败: {response}")

            # 如果上述方法失败或者没有 attach_id，尝试使用 /Tools/DownloadFile 接口
            # 构建下载请求
            data = {
                "AppID": app_id or "",
                "AttachId": str(attach_id or msg_id),  # 使用附件ID或消息ID，确保是字符串类型
                "DataLen": data_len or 0,
                "Section": {
                    "DataLen": data_len or 0,
                    "StartPos": 0
                },
                "UserName": user_name or "",
                "Wxid": self.wxid
            }

            # 如果 AttachId 不是以 @ 开头，尝试使用消息ID
            if attach_id and not attach_id.startswith("@"):
                logger.info(f"AttachId 不是以 @ 开头，尝试使用消息ID")
                data["AttachId"] = str(msg_id)

            # 尝试使用 /Tools/DownloadFile 接口
            logger.info(f"尝试使用 DownloadFile 下载文件: {data}")
            response = await self._request("POST", "/Tools/DownloadFile", data=data)

            if not response.get("Success", False):
                logger.error(f"下载文件失败: {response}")
                return {"Success": False, "Message": "下载文件失败", "Data": {}}

            # 模拟成功响应的格式
            if "Data" not in response:
                response["Data"] = {}

            # 确保有文件数据和文件名
            if "FileData" not in response["Data"]:
                # 如果没有文件数据，尝试从响应中提取
                if "FileData" in response:
                    response["Data"]["FileData"] = response["FileData"]
                elif "Data" in response and isinstance(response["Data"], str):
                    response["Data"] = {"FileData": response["Data"]}
                elif "Data" in response and isinstance(response["Data"], dict) and "FileContent" in response["Data"]:
                    response["Data"]["FileData"] = response["Data"]["FileContent"]

            # 确保有文件名
            if "FileName" not in response["Data"]:
                response["Data"]["FileName"] = f"file_{msg_id}_{int(time.time())}"

            return response
        except Exception as e:
            logger.error(f"下载文件出错: {e}")
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
            return {"Success": False, "Message": f"下载文件出错: {e}", "Data": {}}
