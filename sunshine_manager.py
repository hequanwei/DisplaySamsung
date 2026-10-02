"""
Sunshine 串流服务调度管理模块
负责动态覆写 sunshine.conf（绑定指定 IP 走特定通道）、备份与恢复配置、
启动 Sunshine 推流进程，以及优雅终止 Sunshine 进程。
"""

import os
import shutil
import signal
import logging
import subprocess
from typing import Optional, List
from pathlib import Path

from config import (
    SUNSHINE_CONFIG_DIR,
    SUNSHINE_CONFIG_PATH,
    SUNSHINE_BACKUP_PATH,
    SUNSHINE_BIN_CANDIDATES,
)

logger = logging.getLogger("DisplaySamsung.Sunshine")


class SunshineManager:
    """Sunshine 串流管理器"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.is_running: bool = False
        self.has_backed_up: bool = False
        self.active_bind_ip: Optional[str] = None

    def find_sunshine_binary(self) -> Optional[Path]:
        """自动查找 Sunshine 可执行文件路径"""
        # 首先检查系统 PATH
        in_path = shutil.which("sunshine")
        if in_path:
            return Path(in_path)

        # 检查候选路径列表
        for candidate in SUNSHINE_BIN_CANDIDATES:
            if candidate.exists() and os.access(candidate, os.X_OK):
                return candidate

        return None

    def ensure_config_dir(self):
        """确保配置目录存在"""
        SUNSHINE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def backup_config(self):
        """备份原始 sunshine.conf"""
        if SUNSHINE_CONFIG_PATH.exists():
            shutil.copy2(SUNSHINE_CONFIG_PATH, SUNSHINE_BACKUP_PATH)
            self.has_backed_up = True
            logger.info(f"已备份原始 Sunshine 配置到 {SUNSHINE_BACKUP_PATH}")
        else:
            # 如果原配置文件不存在，记录标记
            self.has_backed_up = False

    def restore_config(self):
        """恢复原始 sunshine.conf 或清理临时配置文件"""
        try:
            if self.has_backed_up and SUNSHINE_BACKUP_PATH.exists():
                shutil.copy2(SUNSHINE_BACKUP_PATH, SUNSHINE_CONFIG_PATH)
                SUNSHINE_BACKUP_PATH.unlink(missing_ok=True)
                logger.info("已成功恢复原始 Sunshine 配置文件")
            elif not self.has_backed_up and SUNSHINE_CONFIG_PATH.exists():
                # 如果最初没有该配置，将 bind_address 注释掉或重置为 0.0.0.0
                self._update_bind_address("0.0.0.0")
                logger.info("已将 sunshine.conf 监听地址重置为 0.0.0.0")
        except Exception as e:
            logger.error(f"恢复 Sunshine 配置时出错: {e}")

    def _update_bind_address(self, ip_address: str, display_id: Optional[int] = None):
        """
        覆写配置文件中的 bind_address、csrf_allowed_origins 与 output_name
        """
        self.ensure_config_dir()
        lines = []
        if SUNSHINE_CONFIG_PATH.exists():
            with open(SUNSHINE_CONFIG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        bind_found = False
        output_found = False
        csrf_found = False

        # 构造需要放行的 CSRF 来源列表
        allowed_origins = [
            "https://localhost:47990",
            "http://localhost:47990",
            "https://127.0.0.1:47990",
            "http://127.0.0.1:47990",
            f"https://{ip_address}:47990",
            f"http://{ip_address}:47990",
        ]
        # 兼容当前活跃的所有 IPv4 地址
        try:
            import psutil
            for iface, addr_list in psutil.net_if_addrs().items():
                for addr in addr_list:
                    if addr.family.name == "AF_INET":
                        allowed_origins.append(f"https://{addr.address}:47990")
                        allowed_origins.append(f"http://{addr.address}:47990")
        except Exception:
            pass

        csrf_str = f"csrf_allowed_origins = {', '.join(sorted(set(allowed_origins)))}\n"

        # Sunshine 在 macOS 下以 display_id 作为显示器 display_name (如 "57")，内建主屏通常为 "1"
        target_output = str(display_id) if display_id is not None else None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("bind_address"):
                new_lines.append(f"bind_address = {ip_address}\n")
                bind_found = True
            elif stripped.startswith("csrf_allowed_origins"):
                new_lines.append(csrf_str)
                csrf_found = True
            elif target_output is not None and stripped.startswith("output_name"):
                new_lines.append(f"output_name = {target_output}\n")
                output_found = True
            else:
                new_lines.append(line)

        if not bind_found:
            new_lines.append(f"bind_address = {ip_address}\n")

        if not csrf_found:
            new_lines.append(csrf_str)

        if target_output is not None and not output_found:
            new_lines.append(f"output_name = {target_output}\n")

        # 保证允许配对
        if not any(l.strip().startswith("origin_pin_allowed") for l in new_lines):
            new_lines.append("origin_pin_allowed = pc\n")

        with open(SUNSHINE_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"已覆写 Sunshine 配置: bind_address = {ip_address}, csrf_allowed_origins 已配置, output_name = {target_output}")

    def _kill_all_sunshine_instances(self):
        """扫描全系统杀死所有残留的 Sunshine 进程，彻底释放 48010 等端口，避免旧进程推流主屏"""
        try:
            import psutil, time
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = p.info.get('name') or ''
                    cmdline = p.info.get('cmdline') or []
                    if 'sunshine' in name.lower() or any('sunshine' in str(c).lower() for c in cmdline):
                        if p.pid != os.getpid():
                            logger.info(f"强力清理系统残留 Sunshine 进程: PID {p.pid}")
                            p.kill()
                except Exception:
                    pass
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"清理旧 Sunshine 进程时警告: {e}")

    def start(self, target_ip: str, display_id: Optional[int] = None) -> bool:
        """
        根据指定 IP 覆写配置并启动 Sunshine
        """
        # 无论之前状态如何，必须先清理全系统所有旧 Sunshine 实例，防止老实例霸占 48010 端口
        self._kill_all_sunshine_instances()

        sunshine_bin = self.find_sunshine_binary()
        if not sunshine_bin:
            raise FileNotFoundError(
                "未找到 Sunshine 可执行程序。请确保已安装 Sunshine（例如通过 Homebrew 或官方 dmg 安装）。"
            )

        # 备份并写入新配置
        self.backup_config()
        self._update_bind_address(target_ip, display_id)
        self.active_bind_ip = target_ip

        # 启动 Sunshine 进程
        logger.info(f"正在以绑定的 IP [{target_ip}] 启动 Sunshine (推流 DisplayID: {display_id}): {sunshine_bin}")
        try:
            self.process = subprocess.Popen(
                [str(sunshine_bin)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.is_running = True
            logger.info(f"Sunshine 进程已启动，PID: {self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"启动 Sunshine 进程失败: {e}")
            self.restore_config()
            self.is_running = False
            raise

    def stop(self):
        """
        优雅杀死 Sunshine 进程并恢复配置
        """
        logger.info("正在执行 Sunshine 停止清理流程...")
        self._kill_all_sunshine_instances()
        self.process = None

        # 还原配置文件
        self.restore_config()
        self.is_running = False
        self.active_bind_ip = None
