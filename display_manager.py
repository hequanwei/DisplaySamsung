"""
虚拟显示器生命周期管理模块
负责创建指定分辨率 (2800x1752 HiDPI) 的虚拟副屏，捕获 DisplayID 与 UUID，
并在停止或异常退出时可靠销毁虚拟显示器，杜绝幽灵屏幕残留。
"""

import os
import sys
import json
import shutil
import signal
import logging
import subprocess
from typing import Optional, Dict, Any

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    ENABLE_HIDPI,
    DISPLAY_NAME,
    DISPLAY_DRIVER,
    TOOLS_DIR,
    NATIVE_DRIVER_BIN,
    NATIVE_DRIVER_SRC,
)

logger = logging.getLogger("DisplaySamsung.Display")


class VirtualDisplayManager:
    """虚拟显示器管理器"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.display_id: Optional[int] = None
        self.uuid: Optional[str] = None
        self.driver_type: str = "native"  # 'native' 或 'betterdisplay'
        self.is_active: bool = False

    def ensure_native_binary(self) -> bool:
        """检查并确保原生虚拟显示器二进制文件已编译可用"""
        if NATIVE_DRIVER_BIN.exists() and os.access(NATIVE_DRIVER_BIN, os.X_OK):
            return True

        logger.info("原生虚拟显示器工具尚未编译，正在执行自动编译...")
        try:
            cmd = [
                "clang",
                "-fno-modules",
                "-fobjc-arc",
                "-framework", "Cocoa",
                "-framework", "CoreGraphics",
                "-o", str(NATIVE_DRIVER_BIN),
                str(NATIVE_DRIVER_SRC),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("原生虚拟显示器工具编译成功")
            return True
        except Exception as e:
            logger.error(f"编译原生虚拟显示器工具失败: {e}")
            return False

    def check_betterdisplaycli(self) -> bool:
        """检查系统中是否存在 betterdisplaycli"""
        return shutil.which("betterdisplaycli") is not None

    def create_display(
        self,
        width: int = DISPLAY_WIDTH,
        height: int = DISPLAY_HEIGHT,
        hidpi: bool = ENABLE_HIDPI,
        name: str = DISPLAY_NAME,
        position: str = "right",
    ) -> Dict[str, Any]:
        """
        创建虚拟显示器并捕获 DisplayID 与 UUID
        position 支持: 'right', 'left', 'top', 'bottom'
        """
        if self.is_active:
            logger.info("当前已存在活跃的虚拟显示器，先销毁旧显示器")
            self.destroy_display()

        # 判断使用的驱动
        use_betterdisplay = False
        if DISPLAY_DRIVER == "betterdisplay":
            use_betterdisplay = True
        elif DISPLAY_DRIVER == "auto":
            # auto 优先检查 betterdisplaycli，如果不存在则使用内置原生驱动
            use_betterdisplay = self.check_betterdisplaycli()

        if use_betterdisplay:
            return self._create_via_betterdisplay(width, height, hidpi, name)
        else:
            return self._create_via_native(width, height, hidpi, name, position)

    def change_position(self, position: str) -> bool:
        """运行时动态改变副屏相对于主屏的摆放方位 (left, right, top, bottom)"""
        if not self.is_active or not self.process or not self.process.stdin:
            return False
        try:
            logger.info(f"向原生驱动发送方位切换指令: position {position}")
            self.process.stdin.write(f"position {position}\n")
            self.process.stdin.flush()
            return True
        except Exception as e:
            logger.error(f"切换副屏方位失败: {e}")
            return False

    def _create_via_native(
        self, width: int, height: int, hidpi: bool, name: str, position: str = "right"
    ) -> Dict[str, Any]:
        """使用内置原生 Swift/ObjC 虚拟驱动创建显示器"""
        if not self.ensure_native_binary():
            raise RuntimeError("无法准备原生虚拟显示器驱动二进制")

        cmd = [
            str(NATIVE_DRIVER_BIN),
            "--width", str(width),
            "--height", str(height),
            "--hidpi", "1" if hidpi else "0",
            "--name", name,
            "--position", position,
        ]

        logger.info(f"启动原生虚拟显示器驱动: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # 读取第一行输出获取 JSON
        output_line = self.process.stdout.readline()
        if not output_line:
            err_msg = self.process.stderr.read()
            raise RuntimeError(f"虚拟显示器驱动启动失败，无返回输出: {err_msg}")

        try:
            data = json.loads(output_line.strip())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析虚拟显示器驱动输出失败 ({e}): {output_line}")

        if data.get("status") != "ok":
            raise RuntimeError(f"虚拟显示器创建失败: {data.get('message', '未知错误')}")

        self.display_id = data.get("display_id")
        self.uuid = data.get("uuid")
        self.driver_type = "native"
        self.is_active = True

        logger.info(
            f"虚拟显示器创建成功 [Native] - DisplayID: {self.display_id}, UUID: {self.uuid}, 分辨率: {width}x{height} (HiDPI: {hidpi}, 方位: {position})"
        )
        return {
            "status": "ok",
            "display_id": self.display_id,
            "uuid": self.uuid,
            "driver": "native",
        }

    def _create_via_betterdisplay(
        self, width: int, height: int, hidpi: bool, name: str
    ) -> Dict[str, Any]:
        """使用 betterdisplaycli 命令行创建虚拟显示器"""
        logger.info(f"使用 betterdisplaycli 创建虚拟显示器: {name}")
        create_cmd = [
            "betterdisplaycli",
            "create",
            "-devicetype=virtualscreen",
            f"-virtualscreenname={name}",
            f"-aspectWidth={width}",
            f"-aspectHeight={height}",
        ]
        res = subprocess.run(create_cmd, capture_output=True, text=True, check=True)
        logger.debug(f"betterdisplaycli create 输出: {res.stdout}")

        # 获取当前显示器列表查找刚才创建的屏幕
        list_cmd = ["betterdisplaycli", "list"]
        list_res = subprocess.run(list_cmd, capture_output=True, text=True)

        display_id = None
        uuid_str = None
        for line in list_res.stdout.splitlines():
            if name in line:
                # 解析其中的 id 或 uuid
                parts = line.split()
                for p in parts:
                    if p.startswith("id:") or p.startswith("displayID:"):
                        try:
                            display_id = int(p.split(":")[1])
                        except ValueError:
                            pass
                    if p.startswith("uuid:"):
                        uuid_str = p.split(":")[1]

        self.display_id = display_id
        self.uuid = uuid_str
        self.driver_type = "betterdisplay"
        self.is_active = True

        return {
            "status": "ok",
            "display_id": self.display_id,
            "uuid": self.uuid,
            "driver": "betterdisplay",
        }

    def destroy_display(self):
        """
        销毁虚拟显示器，确保 100% 注销屏幕，防止幽灵屏幕残留
        """
        logger.info("正在执行虚拟显示器销毁注销流程...")
        if self.driver_type == "native" and self.process:
            try:
                # 尝试向 stdin 写入 quit 退出
                if self.process.stdin and not self.process.stdin.closed:
                    try:
                        self.process.stdin.write("quit\n")
                        self.process.stdin.flush()
                        self.process.stdin.close()
                    except Exception:
                        pass

                # 发送 SIGTERM
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    logger.warning("虚拟显示器进程未响应 SIGTERM，强制执行 SIGKILL")
                    self.process.kill()
                    self.process.wait(timeout=1.0)
            except Exception as e:
                logger.error(f"终止原生虚拟显示器进程出错: {e}")
            finally:
                if self.process.stdout and not self.process.stdout.closed:
                    self.process.stdout.close()
                if self.process.stderr and not self.process.stderr.closed:
                    self.process.stderr.close()
                self.process = None

        elif self.driver_type == "betterdisplay":
            try:
                discard_cmd = ["betterdisplaycli", "discard", f"-namelike={DISPLAY_NAME}"]
                subprocess.run(discard_cmd, capture_output=True, text=True)
            except Exception as e:
                logger.error(f"betterdisplaycli 销毁显示器出错: {e}")

        self.display_id = None
        self.uuid = None
        self.is_active = False
        logger.info("虚拟显示器已完全销毁注销")
