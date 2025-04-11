"""
二维码工具模块
提供二维码相关的工具函数
"""

import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

def generate_console_qrcode(data: str) -> str:
    """
    生成控制台可显示的二维码，使用彩色和样式增强

    Args:
        data: 二维码数据，可以是URL或其他文本

    Returns:
        控制台可显示的二维码字符串
    """
    try:
        import qrcode
        from io import StringIO
        from xnbot.utils.logger import BRIGHT_BLACK, BRIGHT_WHITE, RESET

        # 创建二维码对象
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1
        )

        # 添加数据
        qr.add_data(data)
        qr.make(fit=True)

        # 创建ASCII二维码
        output = StringIO()
        qr.print_ascii(out=output)
        output.seek(0)
        ascii_qr = output.read()

        # 增强二维码显示效果，替换ASCII字符为彩色版本
        enhanced_qr = ascii_qr.replace('█', f'{BRIGHT_WHITE}█{RESET}')
        enhanced_qr = enhanced_qr.replace('▄', f'{BRIGHT_WHITE}▄{RESET}')
        enhanced_qr = enhanced_qr.replace('▀', f'{BRIGHT_WHITE}▀{RESET}')
        enhanced_qr = enhanced_qr.replace(' ', f'{BRIGHT_BLACK}·{RESET}')

        # 返回增强的ASCII二维码
        return enhanced_qr
    except ImportError:
        logger.warning("未安装qrcode库，无法生成控制台二维码，请使用pip install qrcode安装")
        return f"请扫描二维码: {data}"
    except Exception as e:
        logger.error(f"生成控制台二维码失败: {e}")
        return f"请扫描二维码: {data}"

def save_qrcode_image(data: str, file_path: Optional[str] = None) -> str:
    """
    保存二维码图片

    Args:
        data: 二维码数据，可以是URL或其他文本
        file_path: 保存路径，如果为None则使用临时文件

    Returns:
        保存的文件路径
    """
    try:
        import qrcode

        # 如果未指定路径，使用临时文件
        if file_path is None:
            file_path = os.path.join(tempfile.gettempdir(), "qrcode.png")

        # 创建二维码对象
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4
        )

        # 添加数据
        qr.add_data(data)
        qr.make(fit=True)

        # 创建图片
        img = qr.make_image(fill_color="black", back_color="white")

        # 保存图片
        img.save(file_path)

        return file_path
    except ImportError:
        logger.warning("未安装qrcode库，无法生成二维码图片，请使用pip install qrcode[pil]安装")
        return ""
    except Exception as e:
        logger.error(f"保存二维码图片失败: {e}")
        return ""
