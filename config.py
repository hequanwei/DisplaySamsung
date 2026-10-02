"""
全局配置模块
包含显示器规格、网络识别过滤规则、Sunshine 路径与配置等。
"""

import os
from pathlib import Path

# ===========================
# 虚拟显示器规格配置
# ===========================
# 默认适配三星 Galaxy Tab S7+/S8+/S9+ 等 12.4 英寸屏幕分辨率
DISPLAY_WIDTH = 2800
DISPLAY_HEIGHT = 1752
ENABLE_HIDPI = True
DISPLAY_NAME = "SamsungTab"

# 虚拟显示器驱动方案：'auto' (优先 betterdisplaycli，无则用原生 Swift), 'betterdisplay', 'native'
DISPLAY_DRIVER = "auto"

# 原生虚拟显示器驱动及应用路径自适应 (兼容源码运行与 PyInstaller 打包应用)
import sys
if getattr(sys, "frozen", False):
    # 打包运行环境
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    TOOLS_DIR = BASE_DIR / "tools"
    NATIVE_DRIVER_BIN = TOOLS_DIR / "virtual_display"
    if not NATIVE_DRIVER_BIN.exists():
        NATIVE_DRIVER_BIN = Path(sys.executable).parent / "tools" / "virtual_display"
else:
    BASE_DIR = Path(__file__).resolve().parent
    TOOLS_DIR = BASE_DIR / "tools"
    NATIVE_DRIVER_BIN = TOOLS_DIR / "virtual_display"

NATIVE_DRIVER_SRC = TOOLS_DIR / "virtual_display.m"

# ===========================
# 网络检测规则配置
# ===========================
# 过滤掉的网卡前缀或名称（回环、蓝牙、雷雳网桥、VPN 虚拟通道等）
IGNORED_INTERFACES = [
    "lo0",
    "awdl0",
    "llw0",
    "bridge0",
    "gif0",
    "stf0",
    "anpi",
    "utun",
    "ap1",
]

# USB 网络共享检测轮询参数
USB_DETECT_TIMEOUT = 5.0  # 超时时间（秒）
USB_DETECT_INTERVAL = 0.5  # 轮询间隔（秒）

# ===========================
# Sunshine 串流配置
# ===========================
# Sunshine 配置文件默认路径
SUNSHINE_CONFIG_DIR = Path.home() / ".config" / "sunshine"
SUNSHINE_CONFIG_PATH = SUNSHINE_CONFIG_DIR / "sunshine.conf"
SUNSHINE_BACKUP_PATH = SUNSHINE_CONFIG_DIR / "sunshine.conf.bak"

# 自动探测 Sunshine 可执行文件候选路径
SUNSHINE_BIN_CANDIDATES = [
    Path("/Applications/Sunshine.app/Contents/MacOS/Sunshine"),
    Path("/Applications/Sunshine.app/Contents/MacOS/sunshine"),
    Path("/opt/homebrew/bin/sunshine"),
    Path("/usr/local/bin/sunshine"),
    Path.home() / ".local/bin/sunshine",
]

# Sunshine Web 管理面板地址（默认端口 47990）
SUNSHINE_WEB_UI_PORT = 47990

# 日志输出文件路径
if getattr(sys, "frozen", False):
    LOG_DIR = Path.home() / "Library" / "Logs" / "DisplaySamsung"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE_PATH = LOG_DIR / "scheduler.log"
else:
    LOG_FILE_PATH = BASE_DIR / "scheduler.log"
