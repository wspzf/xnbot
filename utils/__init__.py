# 工具模块
# 包含各种辅助功能

from xnbot.utils.color_formatter import setup_colored_logging

# 尝试导入二维码工具，如果安装了qrcode库
try:
    from xnbot.utils.qrcode_utils import generate_console_qrcode, save_qrcode_image
except ImportError:
    pass
