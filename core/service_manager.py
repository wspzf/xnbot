"""
服务管理器
负责启动和管理微信API服务
"""

import os
import sys
import asyncio
import subprocess
import logging
import signal
import time
import platform
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ServiceManager:
    """服务管理器"""

    def __init__(self, bot):
        """
        初始化服务管理器

        Args:
            bot: 机器人实例
        """
        self.bot = bot
        self.services = {}
        self.processes = {}
        self.running = False

        # 获取服务目录
        self.services_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services")

        # 初始化服务配置
        self._init_services()

    def _init_services(self):
        """初始化服务配置"""
        # 微信API服务
        self.services["wechat_api"] = {
            "name": "微信API服务",
            "path": os.path.join(self.services_dir, "pad"),
            "executable": "main.exe" if platform.system() == "Windows" else "linuxService",
            "args": [],
            "env": {},
            "auto_restart": True,
            "process": None
        }

        # Redis服务
        self.services["redis"] = {
            "name": "Redis服务",
            "path": os.path.join(self.services_dir, "redis"),
            "executable": "redis-server.exe" if platform.system() == "Windows" else "redis-server",
            "args": ["redis.windows.conf" if platform.system() == "Windows" else "redis.conf"],
            "env": {},
            "auto_restart": True,
            "process": None
        }

    async def start_services(self):
        """启动所有服务"""
        if self.running:
            logger.warning("服务已经在运行")
            return

        logger.info("正在启动服务...")
        self.running = True

        # 先启动Redis
        await self.start_service("redis")

        # 等待Redis启动完成
        await asyncio.sleep(2)

        # 再启动微信API
        await self.start_service("wechat_api")

        logger.info("所有服务已启动")

    async def stop_services(self):
        """停止所有服务"""
        if not self.running:
            logger.warning("服务未在运行")
            return

        logger.info("正在停止服务...")
        self.running = False

        # 先停止微信API
        await self.stop_service("wechat_api")

        # 再停止Redis
        await self.stop_service("redis")

        logger.info("所有服务已停止")

    async def start_service(self, service_id: str):
        """
        启动服务

        Args:
            service_id: 服务ID
        """
        if service_id not in self.services:
            logger.error(f"未知服务: {service_id}")
            return

        service = self.services[service_id]

        if service.get("process") is not None:
            logger.warning(f"服务 {service['name']} 已经在运行")
            return

        logger.info(f"正在启动服务: {service['name']}")

        try:
            # 构建命令
            executable_path = os.path.join(service["path"], service["executable"])
            cmd = [executable_path] + service["args"]

            # 启动进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=service["path"],
                env=dict(os.environ, **service["env"])
            )

            service["process"] = process
            logger.info(f"服务 {service['name']} 已启动，PID: {process.pid}")

            # 启动日志监控任务
            asyncio.create_task(self._monitor_service_logs(service_id, process))

            # 如果配置了自动重启，启动监控任务
            if service.get("auto_restart", False):
                asyncio.create_task(self._monitor_service(service_id, process))

        except Exception as e:
            logger.error(f"启动服务 {service['name']} 时出错: {e}")

    async def stop_service(self, service_id: str):
        """
        停止服务

        Args:
            service_id: 服务ID
        """
        if service_id not in self.services:
            logger.error(f"未知服务: {service_id}")
            return

        service = self.services[service_id]
        process = service.get("process")

        if process is None:
            logger.warning(f"服务 {service['name']} 未在运行")
            return

        logger.info(f"正在停止服务: {service['name']}")

        try:
            # 发送终止信号
            process.terminate()

            # 等待进程结束
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.info(f"服务 {service['name']} 已停止")
            except asyncio.TimeoutError:
                # 如果超时，强制结束进程
                logger.warning(f"服务 {service['name']} 未响应，强制结束")
                process.kill()
                await process.wait()

        except Exception as e:
            logger.error(f"停止服务 {service['name']} 时出错: {e}")

        finally:
            service["process"] = None

    async def restart_service(self, service_id: str):
        """
        重启服务

        Args:
            service_id: 服务ID
        """
        logger.info(f"正在重启服务: {self.services[service_id]['name']}")
        await self.stop_service(service_id)
        await asyncio.sleep(1)  # 等待一秒，确保服务完全停止
        await self.start_service(service_id)

    async def _monitor_service(self, service_id: str, process):
        """
        监控服务进程

        Args:
            service_id: 服务ID
            process: 进程对象
        """
        try:
            # 等待进程结束
            await process.wait()

            # 如果服务仍在运行状态且配置了自动重启，则重启服务
            if self.running and self.services[service_id].get("auto_restart", False):
                logger.warning(f"服务 {self.services[service_id]['name']} 意外退出，正在重启")
                self.services[service_id]["process"] = None
                await asyncio.sleep(1)  # 等待一秒，确保资源释放
                await self.start_service(service_id)

        except asyncio.CancelledError:
            logger.info(f"服务 {self.services[service_id]['name']} 监控任务已取消")
            raise

        except Exception as e:
            logger.error(f"监控服务 {self.services[service_id]['name']} 时出错: {e}")

    async def _monitor_service_logs(self, service_id: str, process):
        """
        监控服务日志

        Args:
            service_id: 服务ID
            process: 进程对象
        """
        service_name = self.services[service_id]["name"]

        # 创建日志目录
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # 打开日志文件
        log_file_path = os.path.join(logs_dir, f"{service_id}.log")
        log_file = open(log_file_path, "a", encoding="utf-8")

        try:
            # 使用更健壮的方式读取日志
            async def read_stream(stream, is_stderr=False):
                """读取流并处理日志"""
                try:
                    while True:
                        try:
                            # 使用更大的缓冲区读取数据
                            chunk = await stream.read(8192)  # 增加缓冲区大小到 8KB
                            if not chunk:
                                break

                            # 按行处理
                            lines = chunk.decode("utf-8", errors="replace").splitlines()
                            for log_line in lines:
                                if not log_line.strip():
                                    continue

                                # 写入日志文件
                                stream_type = "stderr" if is_stderr else "stdout"
                                log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{stream_type}] {log_line}\n")
                                log_file.flush()

                                # 输出日志到控制台
                                if is_stderr:
                                    logger.error(f"{service_name} (stderr): {log_line}")
                                else:
                                    if "error" in log_line.lower() or "exception" in log_line.lower():
                                        logger.error(f"{service_name}: {log_line}")
                                    elif "warning" in log_line.lower():
                                        logger.warning(f"{service_name}: {log_line}")
                                    else:
                                        logger.debug(f"{service_name}: {log_line}")
                        except Exception as e:
                            logger.error(f"读取{service_name}日志时出错: {e}")
                            # 等待一会再重试
                            await asyncio.sleep(1)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"监控{service_name}日志时出错: {e}")

            # 并行读取标准输出和标准错误
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )

        except asyncio.CancelledError:
            logger.info(f"服务 {service_name} 日志监控任务已取消")
            raise

        except Exception as e:
            logger.error(f"监控服务 {service_name} 日志时出错: {e}")

        finally:
            log_file.close()

    def get_service_status(self) -> Dict[str, Dict]:
        """
        获取所有服务状态

        Returns:
            服务状态字典
        """
        status = {}

        for service_id, service in self.services.items():
            process = service.get("process")
            status[service_id] = {
                "name": service["name"],
                "running": process is not None,
                "pid": process.pid if process else None
            }

        return status
