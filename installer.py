"""
环境自动化安装与自检模块 (installer.py)
负责自动检测并一键安装 Sunshine 串流服务端、驱动依赖与系统权限检查。
"""

import os
import sys
import json
import shutil
import urllib.request
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

from config import (
    SUNSHINE_BIN_CANDIDATES,
    NATIVE_DRIVER_BIN,
    NATIVE_DRIVER_SRC,
)

logger = logging.getLogger("DisplaySamsung.Installer")

# Sunshine 官方 GitHub 仓库
SUNSHINE_REPO = "LizardByte/Sunshine"
APPLICATIONS_DIR = Path("/Applications")
SUNSHINE_APP_PATH = APPLICATIONS_DIR / "Sunshine.app"


def is_sunshine_installed() -> bool:
    """检查 Sunshine 是否已安装"""
    if shutil.which("sunshine") is not None:
        return True
    for p in SUNSHINE_BIN_CANDIDATES:
        if p.exists() and os.access(p, os.X_OK):
            return True
    return False


def get_latest_sunshine_dmg_url() -> Tuple[Optional[str], Optional[str]]:
    """
    通过 GitHub API 获取 Sunshine 最新 Release 的 arm64 DMG 下载链接与版本号
    """
    api_url = f"https://api.github.com/repos/{SUNSHINE_REPO}/releases/latest"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "DisplaySamsung-Installer"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "latest")
            assets = data.get("assets", [])

            # 寻找适合 Apple Silicon macOS 的 arm64 dmg
            dmg_url = None
            for asset in assets:
                name = asset.get("name", "").lower()
                if "macos" in name and "arm64" in name and name.endswith(".dmg"):
                    dmg_url = asset.get("browser_download_url")
                    break

            if not dmg_url:
                # 兼容旧版本可能命名的 macos.dmg
                for asset in assets:
                    name = asset.get("name", "").lower()
                    if "macos" in name and name.endswith(".dmg"):
                        dmg_url = asset.get("browser_download_url")
                        break

            return dmg_url, tag
    except Exception as e:
        logger.warning(f"通过 GitHub API 获取最新 Sunshine release 失败: {e}")
        return None, None


def install_sunshine_via_dmg(progress_callback=None) -> bool:
    """
    直接通过 GitHub Release 下载 DMG 并安装到 /Applications
    """
    logger.info("准备通过官方 DMG 安装 Sunshine...")
    dmg_url, tag = get_latest_sunshine_dmg_url()

    # 如果 API 请求未返回，使用已知的官方兜底版本下载地址
    if not dmg_url:
        dmg_url = "https://github.com/LizardByte/Sunshine/releases/download/v2025.211.235948/sunshine-macos-arm64.dmg"
        tag = "v2025.211.235948"

    logger.info(f"目标下载地址: {dmg_url} (版本: {tag})")
    if progress_callback:
        progress_callback(f"正在下载 Sunshine {tag}...")

    download_dir = Path("/tmp/sunshine_install")
    download_dir.mkdir(parents=True, exist_ok=True)
    dmg_path = download_dir / "sunshine.dmg"

    try:
        # 下载 DMG
        curl_cmd = [
            "curl",
            "-L",
            "--progress-bar",
            "-o", str(dmg_path),
            dmg_url,
        ]
        logger.info(f"执行下载: {' '.join(curl_cmd)}")
        subprocess.run(curl_cmd, check=True)

        if progress_callback:
            progress_callback("下载完成，正在挂载并安装 Sunshine.app...")

        # 挂载 DMG
        mount_point = "/Volumes/Sunshine"
        # 若之前挂载过先尝试卸载
        subprocess.run(["hdiutil", "detach", mount_point, "-quiet", "-force"], check=False)

        attach_cmd = [
            "hdiutil", "attach", str(dmg_path),
            "-mountpoint", mount_point,
            "-nobrowse", "-quiet"
        ]
        subprocess.run(attach_cmd, check=True)

        try:
            source_app = Path(mount_point) / "Sunshine.app"
            if not source_app.exists():
                # 遍历挂载点查找 .app
                found = list(Path(mount_point).glob("*.app"))
                if found:
                    source_app = found[0]

            logger.info(f"找到应用: {source_app}，正在安装到 /Applications/...")
            dest_app = APPLICATIONS_DIR / source_app.name
            if dest_app.exists():
                shutil.rmtree(dest_app, ignore_errors=True)

            # 拷贝 App
            shutil.copytree(source_app, dest_app)
            logger.info(f"Sunshine.app 成功复制到 {dest_app}")

            # 移除隔离属性 (quarantine) 避免首次打开被 Gatekeeper 拦截
            subprocess.run(["xattr", "-rd", "com.apple.quarantine", str(dest_app)], check=False)

        finally:
            # 卸载挂载点
            subprocess.run(["hdiutil", "detach", mount_point, "-quiet", "-force"], check=False)
            dmg_path.unlink(missing_ok=True)

        if is_sunshine_installed():
            logger.info("Sunshine 安装成功！")
            return True
        else:
            return False

    except Exception as e:
        logger.error(f"通过 DMG 安装 Sunshine 失败: {e}")
        return False


def install_sunshine_via_brew(progress_callback=None) -> bool:
    """
    通过 Homebrew Tap 安装 Sunshine
    """
    brew_bin = shutil.which("brew")
    if not brew_bin:
        logger.error("未找到 Homebrew，无法通过 brew 安装")
        return False

    logger.info("准备通过 Homebrew 安装 Sunshine...")
    if progress_callback:
        progress_callback("正在添加 LizardByte/homebrew tap 并安装 Sunshine...")

    try:
        # 添加 tap
        subprocess.run([brew_bin, "tap", "LizardByte/homebrew"], check=True)
        # 安装
        subprocess.run([brew_bin, "install", "sunshine"], check=True)
        return is_sunshine_installed()
    except Exception as e:
        logger.error(f"通过 Homebrew 安装 Sunshine 失败: {e}")
        return False


def install_sunshine(progress_callback=None) -> bool:
    """
    一键自动安装 Sunshine 综合入口
    优先尝试官方 DMG 安装（最快且包含 App 界面），失败时回退到 Homebrew
    """
    if is_sunshine_installed():
        logger.info("Sunshine 已经安装，无需重复操作。")
        return True

    # 优先使用 DMG 安装
    ok = install_sunshine_via_dmg(progress_callback)
    if not ok:
        logger.info("DMG 安装未完成，正在尝试通过 Homebrew 备用方案安装...")
        ok = install_sunshine_via_brew(progress_callback)

    return ok


def run_full_diagnostics() -> str:
    """
    运行完整的环境与网络接口诊断，生成人类可读报告
    """
    report = []
    report.append("=== DisplaySamsung 系统诊断报告 ===")

    # 1. 软件环境
    report.append("\n【软件依赖状态】")
    report.append(f"- Python: {sys.version.split()[0]}")
    sunshine_ok = is_sunshine_installed()
    report.append(f"- Sunshine 串流服务: {'✓ 已安装' if sunshine_ok else '✗ 未安装 (可一键自动安装)'}")
    driver_ok = NATIVE_DRIVER_BIN.exists() and os.access(NATIVE_DRIVER_BIN, os.X_OK)
    report.append(f"- 原生虚拟显示器驱动: {'✓ 就绪' if driver_ok else '✗ 需编译 (run.sh 会自动处理)'}")

    # 2. 网络状态
    report.append("\n【当前网络接口】")
    import psutil
    from network_manager import get_wifi_interface_name, scan_usb_tethering_interfaces

    wifi_iface = get_wifi_interface_name()
    report.append(f"- 系统主 Wi-Fi 设备: {wifi_iface}")

    usb_candidates = scan_usb_tethering_interfaces(wifi_iface)
    if usb_candidates:
        report.append(f"- 检测到的 USB 共享以太网卡: {usb_candidates}")
    else:
        report.append("- 未检测到处于活跃连接状态的 USB 网络共享网卡 (以太网)")

    report.append("\n【接口 IPv4 地址明细】")
    addrs = psutil.net_if_addrs()
    for name, addr_list in addrs.items():
        ipv4s = [a.address for a in addr_list if a.family.name == "AF_INET"]
        if ipv4s:
            report.append(f"  • {name}: {', '.join(ipv4s)}")

    return "\n".join(report)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DisplaySamsung 环境安装与诊断工具")
    parser.add_argument("--install-sunshine", action="store_true", help="安装 Sunshine")
    parser.add_argument("--diagnose", action="store_true", help="运行诊断")
    args = parser.parse_args()

    if args.install_sunshine:
        print("开始安装 Sunshine...")
        success = install_sunshine(progress_callback=print)
        print("安装结果:", "成功" if success else "失败")
    elif args.diagnose:
        print(run_full_diagnostics())
    else:
        print(run_full_diagnostics())
