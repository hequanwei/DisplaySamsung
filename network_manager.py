"""
精准网络路由模块
负责检测并提取 Wi-Fi 主网卡 IP 与 Android USB 共享网络（Tethering）以太网卡 IP。
"""

import time
import socket
import subprocess
import logging
from typing import Optional, Tuple, Dict, List
import psutil

from config import (
    IGNORED_INTERFACES,
    USB_DETECT_TIMEOUT,
    USB_DETECT_INTERVAL,
)

logger = logging.getLogger("DisplaySamsung.Network")


def is_valid_ipv4(ip: str) -> bool:
    """
    检查 IP 地址是否是有效的单播局域网 IPv4 地址
    排除 127.0.0.1 回环以及 169.254.x.x (APIPA 自动配置未连通地址)
    """
    if not ip or ip.startswith("127.") or ip.startswith("169.254."):
        return False
    # 验证是否为合法 IPv4 地址
    try:
        socket.inet_aton(ip)
        return ip.count(".") == 3
    except OSError:
        return False


def get_wifi_interface_name() -> str:
    """
    通过 macOS 系统的 networksetup 动态查询当前 Wi-Fi 网卡设备标识符（通常为 en0）
    """
    try:
        cmd = ["networksetup", "-listallhardwareports"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = res.stdout.splitlines()
        for idx, line in enumerate(lines):
            if "Hardware Port: Wi-Fi" in line:
                for next_line in lines[idx + 1 : idx + 4]:
                    if next_line.startswith("Device:"):
                        wifi_dev = next_line.split("Device:")[1].strip()
                        return wifi_dev
    except Exception as e:
        logger.warning(f"通过 networksetup 检测 Wi-Fi 接口失败: {e}")
    # 默认返回 en0
    return "en0"


def get_interface_ipv4(iface_name: str) -> Optional[str]:
    """
    获取指定网卡的 IPv4 地址
    """
    addrs = psutil.net_if_addrs()
    if iface_name not in addrs:
        return None

    for addr in addrs[iface_name]:
        if addr.family == socket.AF_INET:
            if is_valid_ipv4(addr.address):
                return addr.address
    return None


def get_wifi_ip() -> Tuple[str, Optional[str]]:
    """
    获取 Wi-Fi 模式下的网络配置
    返回: (网卡名称, IPv4地址)
    """
    wifi_iface = get_wifi_interface_name()
    ip = get_interface_ipv4(wifi_iface)
    return wifi_iface, ip


def is_ignored_interface(iface_name: str) -> bool:
    """
    判断网卡是否属于被忽略的系统虚拟接口或非目标接口
    """
    for ignored in IGNORED_INTERFACES:
        if iface_name.startswith(ignored):
            return True
    return False


def scan_usb_tethering_interfaces(wifi_iface: str) -> Dict[str, str]:
    """
    扫描当前系统中所有疑似 Android USB Tethering 产生的以太网卡
    规则：以太网接口（通常以 en 开头），非 Wi-Fi 网卡，非系统内置忽略列表，具有有效 IPv4
    返回: {网卡名称: IPv4地址}
    """
    candidates = {}
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface_name, addr_list in addrs.items():
        # 排除 Wi-Fi 网卡
        if iface_name == wifi_iface:
            continue
        # 排除忽略的接口
        if is_ignored_interface(iface_name):
            continue
        # 必须是已启用的网络接口
        if iface_name in stats and not stats[iface_name].isup:
            continue

        for addr in addr_list:
            if addr.family == socket.AF_INET:
                if is_valid_ipv4(addr.address):
                    candidates[iface_name] = addr.address

    return candidates


def get_all_physical_ethernet_interfaces(wifi_iface: str) -> List[str]:
    """获取系统中所有物理/虚拟以太网接口名称（排除 Wi-Fi 和已知虚拟隧道）"""
    stats = psutil.net_if_stats()
    result = []
    for iface_name, stat in stats.items():
        if iface_name == wifi_iface or is_ignored_interface(iface_name):
            continue
        if stat.isup:
            result.append(iface_name)
    return result


def detect_usb_tethering_ip(
    timeout: float = USB_DETECT_TIMEOUT,
    interval: float = USB_DETECT_INTERVAL,
    progress_callback=None
) -> Tuple[Optional[str], Optional[str]]:
    """
    带轮询机制的 Android USB 网络共享网卡探测
    在 timeout 时间内持续检测，若插入手机或正在获取 DHCP 地址则等待
    返回: (网卡名称, IPv4地址)，若未检测到返回 (None, None)
    """
    wifi_iface = get_wifi_interface_name()
    start_time = time.time()
    last_log_time = 0

    while time.time() - start_time <= timeout:
        elapsed = int(time.time() - start_time)
        remaining = max(0, int(timeout - elapsed))
        
        if progress_callback:
            try:
                progress_callback(remaining)
            except Exception:
                pass

        candidates = scan_usb_tethering_interfaces(wifi_iface)
        if candidates:
            # 优先匹配带有实际私有局域网 IP 的接口 (192.168.x.x, 172.x.x.x, 10.x.x.x)
            for iface, ip in candidates.items():
                if ip.startswith("192.168.") or ip.startswith("172.") or ip.startswith("10."):
                    logger.info(f"成功识别 Android USB 共享网卡: {iface} -> {ip}")
                    return iface, ip

            # 其次匹配常见的以太网卡命名前缀 en*
            for iface, ip in candidates.items():
                if iface.startswith("en"):
                    logger.info(f"成功识别以太网网卡: {iface} -> {ip}")
                    return iface, ip

            # 否则取第一个候选
            first_iface = next(iter(candidates.keys()))
            return first_iface, candidates[first_iface]

        if time.time() - last_log_time > 3.0:
            logger.info(f"正在等待 Android USB 网络共享连接... 剩余超时: {remaining}s")
            last_log_time = time.time()

        time.sleep(interval)

    logger.warning("在指定时间内未检测到可用的 Android USB 网络共享网卡")
    return None, None

