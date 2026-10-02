"""
Mac 独立便携热点管理模块
针对酒店弱网、咖啡馆拥堵 Wi-Fi、室外断网或酒店开启 AP 隔离场景：
利用 Mac 本地发射的专属 5GHz 局域网热点，实现完全脱机、零流量、2ms 极速 120Hz 视网膜副屏。
平板端零 VPN、零配置，原有代理/科学上网稳定共存。
"""

import socket
import subprocess
import logging
from typing import Optional, Tuple
import psutil

logger = logging.getLogger("DisplaySamsung.Hotspot")


def get_hotspot_gateway_ip() -> Tuple[Optional[str], Optional[str]]:
    """
    检测当前系统是否存在由 macOS 热点/共享网络生成的网关 IP
    通常热点网卡为 bridge100、bridge101 等网桥接口，常见网关 IP 为 192.168.2.1
    返回: (网卡名称, 网关IP)
    """
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    # 优先检测常见的 macOS 热点网桥设备 bridge100 ~ bridge109
    for iface_name, addr_list in addrs.items():
        if iface_name.startswith("bridge") and iface_name in stats and stats[iface_name].isup:
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                        logger.info(f"检测到 macOS 便携热点网关: {iface_name} -> {ip}")
                        return iface_name, ip

    return None, None


def open_macos_sharing_settings():
    """打开 macOS 系统设置中的互联网共享面板"""
    try:
        subprocess.run(["open", "x-apple.systempreferences:com.apple.Sharing-Settings.extension"], check=False)
    except Exception:
        try:
            subprocess.run(["open", "/System/Library/PreferencePanes/SharingPref.prefPane"], check=False)
        except Exception as e:
            logger.warning(f"打开共享设置失败: {e}")


def get_hotspot_guide() -> str:
    """返回 Mac 便携热点开启与配对指引"""
    return (
        "【Mac 独立 5GHz 便携热点模式指南】\n\n"
        "💡 为什么使用此模式？\n"
        "在酒店、高铁或户外无网络时，外部 Wi-Fi 往往极慢，或者酒店 Wi-Fi 开启了「AP 隔离」"
        "导致副屏无法连接。\n"
        "开启 Mac 本地热点后，Mac 与平板直接在半米内点对点无线连接，延迟仅 2ms，"
        "彻底摆脱路由器束缚，且完全不占用平板的 VPN！\n\n"
        "----------------------------------------\n"
        "★ 首次开启步骤（仅需 30 秒）：\n"
        "1. 打开 Mac【系统设置】->【通用】->【共享】；\n"
        "2. 找到【互联网共享】右侧的 ℹ️ 图标，将「共享以下来源的连接」选为当前网络或关闭，"
        "「至电脑端口」勾选【Wi-Fi】；\n"
        "3. 在「Wi-Fi 选项」中设置热点名称与密码，频段推荐选择【5 GHz】；\n"
        "4. 将【互联网共享】开关开启！\n\n"
        "★ 连接与使用：\n"
        "1. 三星平板打开 Wi-Fi 搜索并连入 Mac 的专属热点；\n"
        "2. 点击本应用菜单中的「启动 (Mac 便携热点模式)」；\n"
        "3. 平板 Moonlight 输入显示的网关 IP（通常为 192.168.2.1）即可秒连！"
    )
