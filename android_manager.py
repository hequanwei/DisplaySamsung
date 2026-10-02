"""
Android 设备辅助调度与防锁屏管理器
专门针对三星 Galaxy Tab 等 Android 平板：
1. 诊断并提供彻底解决 Game Booster（游戏助推器）滑动锁/黑屏方案
2. 智能探测 ADB 环境与有线连接设备
3. 自动/手动下发保持屏幕常亮指令（防止副屏闲置黑屏）
"""

import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger("DisplaySamsung.Android")

# 常见 ADB 可执行文件搜索路径
ADB_SEARCH_PATHS = [
    Path("/opt/homebrew/bin/adb"),
    Path("/usr/local/bin/adb"),
    Path.home() / "Library/Android/sdk/platform-tools/adb",
    Path.home() / ".local/bin/adb",
]


def find_adb_binary() -> Optional[str]:
    """智能查找系统中可用的 adb 路径"""
    # 1. 优先使用系统 PATH
    path_adb = shutil.which("adb")
    if path_adb:
        return path_adb

    # 2. 扫描常见 Android SDK 与 Homebrew 安装路径
    for candidate in ADB_SEARCH_PATHS:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None


def get_connected_android_devices() -> List[Dict[str, str]]:
    """
    通过 ADB 检测当前已通过 USB 或网络连接的 Android 设备
    返回格式: [{"serial": "...", "state": "device/unauthorized", "model": "..."}]
    """
    adb_bin = find_adb_binary()
    if not adb_bin:
        return []

    devices = []
    try:
        res = subprocess.run([adb_bin, "devices", "-l"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines[1:]:  # 跳过第一行 "List of devices attached"
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
        logger.debug(f"ADB 设备检测异常: {e}")

    return devices


def enable_stay_awake() -> bool:
    """
    通过 ADB 尝试向已连接的 Android 平板下发保持屏幕常亮指令
    - svc power stayon true (充电/连接 USB 时屏幕保持常亮)
    - 设置系统屏幕超时为最大值
    """
    adb_bin = find_adb_binary()
    if not adb_bin:
        return False

    devices = get_connected_android_devices()
    valid_devices = [d for d in devices if d.get("state") == "device"]
    if not valid_devices:
        return False

    success = True
    for dev in valid_devices:
        serial = dev["serial"]
        try:
            # 开启充电/连线常亮
            subprocess.run([adb_bin, "-s", serial, "shell", "svc", "power", "stayon", "true"], timeout=3, check=True)
            # 设置屏幕休眠时间为极高值 (24小时)
            subprocess.run([adb_bin, "-s", serial, "shell", "settings", "put", "system", "screen_off_timeout", "86400000"], timeout=3)
            logger.info(f"已成功为设备 {serial} 开启屏幕常亮模式")
        except Exception as e:
            logger.warning(f"为设备 {serial} 下发常亮指令失败: {e}")
            success = False

    return success


def get_game_booster_solution_guide() -> str:
    """
    返回针对三星 One UI 游戏助推器（Game Booster）滑动锁/黑屏的专属图文解决方案说明
    """
    return (
        "【三星平板黑屏 / 出现滑动锁按钮的彻底解决方法】\n\n"
        "● 原因分析：\n"
        "三星 One UI 会默认将 Moonlight 识别为游戏应用，并在挂机 3 分钟后由「游戏助推器 (Game Booster)」"
        "自动启动『触摸保护锁』，导致屏幕变暗并要求手动拖动锁图标。\n\n"
        "----------------------------------------\n"
        "★ 解决方案一：关闭游戏助推器触摸保护（最直接有效！）\n"
        "1. 在三星平板上打开 Moonlight 进入串流；\n"
        "2. 从平板屏幕右侧或底部边缘向内滑动，调出系统导航条；\n"
        "3. 点击角落出现的【🎮 游戏助推器】图标；\n"
        "4. 点击右上角【⚙️ 齿轮设置】；\n"
        "5. 找到【触摸保护超时】，将其更改为【从不】；\n"
        "6. 关闭【自动屏幕锁定】开关。\n\n"
        "★ 解决方案二：开启平板“充电时保持屏幕常亮”\n"
        "1. 进入平板【设置】->【开发者选项】；\n"
        "2. 开启【不锁定屏幕 / 充电时保持唤醒状态】；\n"
        "只要插着 Type-C 线或充电线，屏幕永远不会熄灭！\n\n"
        "★ 解决方案三：Moonlight 防休眠开关\n"
        "在 Moonlight 平板端设置中，勾选【Keep display awake】（保持屏幕常亮）。"
    )
