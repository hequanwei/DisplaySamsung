"""
ADB 端口反向映射与主机托管管理器
负责通过 ADB 隧道建立 Mac 与 Android 平板之间的端口映射，
彻底解决由于 macOS 缺失 RNDIS 驱动导致的 USB 网络断层问题。
恪守准则：主机全托管，平板端零 VPN、零代理冲突、零额外常驻负载。
"""

import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from config import BASE_DIR, TOOLS_DIR

logger = logging.getLogger("DisplaySamsung.ADB")

# 核心串流端口（TCP 协议反向代理至平板本地）
FORWARD_PORTS = [
    47984,  # HTTP / Web
    47989,  # HTTPS
    47990,  # Sunshine Web 控制台
    48010,  # RTSP 视频流控制握手
]


def get_adb_path() -> Optional[str]:
    """定位可用的 adb 二进制文件（优先项目内置 tools/adb，其次系统路径）"""
    # 1. 优先检查应用内置的 tools/adb
    local_adb = TOOLS_DIR / "adb"
    if local_adb.is_file() and os.access(local_adb, os.X_OK):
        return str(local_adb)

    # 2. 检查系统环境 PATH
    path_adb = shutil.which("adb")
    if path_adb:
        return path_adb

    # 3. 常见候选路径
    candidates = [
        Path("/opt/homebrew/bin/adb"),
        Path("/usr/local/bin/adb"),
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path.home() / ".local/bin/adb",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)

    return None


class ADBManager:
    """ADB 隧道与设备状态管理类"""

    def __init__(self):
        self.adb_bin = get_adb_path()
        self.is_forwarding_active: bool = False
        self.connected_device_serial: Optional[str] = None
        self.connected_device_model: Optional[str] = None

    def refresh_adb_path(self):
        self.adb_bin = get_adb_path()

    def get_devices(self) -> List[Dict[str, str]]:
        """检测当前连接的 Android 设备"""
        self.refresh_adb_path()
        if not self.adb_bin:
            return []

        devices = []
        try:
            # 使用系统默认 socket（已在系统 daemon 中启动）
            res = subprocess.run([self.adb_bin, "devices", "-l"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        serial = parts[0]
                        state = parts[1]
                        model = "Android 设备"
                        for item in parts[2:]:
                            if item.startswith("model:"):
                                model = item.split("model:")[1]
                        devices.append({"serial": serial, "state": state, "model": model})
        except Exception as e:
            logger.error(f"检测 ADB 设备异常: {e}")

        return devices

    def setup_reverse_forwarding(self) -> Tuple[bool, str]:
        """
        建立端口反向映射并自动下发充电防黑屏常亮
        返回: (是否成功, 提示消息)
        """
        self.refresh_adb_path()
        if not self.adb_bin:
            return False, "系统中未找到 ADB 工具，请确保已安装。"

        devices = self.get_devices()
        if not devices:
            return False, (
                "未检测到已连接并授权的 Android 设备。\n\n"
                "💡 请确认：\n"
                "1. 已使用 Type-C 数据线连接 Mac 与平板；\n"
                "2. 在平板进入【设置】->【开发者选项】-> 打开【USB 调试】；\n"
                "3. 平板弹出提示“是否允许 USB 调试”时，勾选【始终允许】并点击【允许】。"
            )

        unauthorized = [d for d in devices if d.get("state") == "unauthorized"]
        if unauthorized:
            return False, "平板已连接但尚未在屏幕上授权 USB 调试，请在平板屏幕上点击【允许】。"

        ready_devices = [d for d in devices if d.get("state") == "device"]
        if not ready_devices:
            return False, f"设备状态异常: {devices[0].get('state')}"

        target = ready_devices[0]
        serial = target["serial"]
        self.connected_device_serial = serial
        self.connected_device_model = target["model"]

        # 1. 执行端口反向映射
        for port in FORWARD_PORTS:
            cmd = [self.adb_bin, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode != 0:
                    logger.warning(f"映射端口 tcp:{port} 失败: {res.stderr}")
                else:
                    logger.info(f"已成功反向映射端口: tcp:{port} -> tcp:{port}")
            except Exception as e:
                logger.error(f"执行 adb reverse 异常: {e}")

        # 2. 自动下发充电常亮与长休眠指令（彻底防止副屏闲置黑屏与滑动锁）
        try:
            subprocess.run([self.adb_bin, "-s", serial, "shell", "svc", "power", "stayon", "true"], timeout=3)
            subprocess.run([self.adb_bin, "-s", serial, "shell", "settings", "put", "system", "screen_off_timeout", "86400000"], timeout=3)
            logger.info("已自动为平板下发防黑屏屏幕常亮指令")
        except Exception as e:
            logger.debug(f"下发常亮指令跳过: {e}")

        self.is_forwarding_active = True
        return True, f"成功打通与 {self.connected_device_model} 的 Type-C 极速直连通道！"

    def cleanup(self):
        """移除所有已建立的端口反向映射，保证优雅退场"""
        if not self.adb_bin:
            return

        try:
            if self.connected_device_serial:
                subprocess.run([self.adb_bin, "-s", self.connected_device_serial, "reverse", "--remove-all"], timeout=3)
            else:
                subprocess.run([self.adb_bin, "reverse", "--remove-all"], timeout=3)
            logger.info("已成功清理并释放全部 ADB 反向端口映射")
        except Exception as e:
            logger.debug(f"清理 ADB 映射异常: {e}")

        self.is_forwarding_active = False
        self.connected_device_serial = None
        self.connected_device_model = None
