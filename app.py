"""
macOS 状态栏应用（Android 平板副屏自动化调度器）
使用 rumps 库构建状态栏交互，实现 USB / Wi-Fi 模式切换、
虚拟显示器生命周期自动化调度、Sunshine 一键环境安装，以及 100% 优雅退场防幽灵屏幕机制。
"""

import sys
import atexit
import signal
import logging
import threading
import webbrowser
import rumps

from config import (
    APP_VERSION,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    ENABLE_HIDPI,
    SUNSHINE_WEB_UI_PORT,
    LOG_FILE_PATH,
)
from network_manager import (
    get_wifi_ip,
    detect_usb_tethering_ip,
)
from display_manager import VirtualDisplayManager
from sunshine_manager import SunshineManager
from installer import (
    is_sunshine_installed,
    install_sunshine,
    run_full_diagnostics,
)
from android_manager import (
    get_game_booster_solution_guide,
    enable_stay_awake,
    get_connected_android_devices,
)

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger("DisplaySamsung.App")


class DisplaySamsungApp(rumps.App):
    """三星平板副屏调度器状态栏应用"""

    def __init__(self):
        super(DisplaySamsungApp, self).__init__(
            name="DisplaySamsung",
            title="📱 副屏: 闲置",
            quit_button=None,  # 自定义退出按钮以确保退场钩子执行
        )

        # 核心管理器实例
        self.display_mgr = VirtualDisplayManager()
        self.sunshine_mgr = SunshineManager()

        # 运行状态
        self.current_mode: str = "idle"  # 'idle', 'usb', 'wifi'
        self.current_ip: str = ""
        self.current_iface: str = ""
        self.is_installing_sunshine: bool = False

        # 平板方向与布局偏好
        self.orientation: str = "landscape"  # 'landscape' (横屏 2800x1752), 'portrait' (竖屏 1752x2800)
        self.position: str = "right"  # 'right', 'left', 'top', 'bottom'

        # 构造菜单结构
        self.status_item = rumps.MenuItem("● 状态: 未连接", callback=self.show_status_details)
        self.usb_item = rumps.MenuItem("启动 (USB 极速模式)", callback=self.start_usb_mode)
        self.wifi_item = rumps.MenuItem("启动 (Wi-Fi 便携模式)", callback=self.start_wifi_mode)
        self.stop_item = rumps.MenuItem("停止副屏与串流", callback=self.stop_service)
        
        # 平板方向与布局子菜单
        self.layout_menu = rumps.MenuItem("📐 平板方向与布局")
        self.orient_landscape_item = rumps.MenuItem("✓ 🖥️ 横屏模式 (2800x1752)", callback=lambda _: self.set_orientation("landscape"))
        self.orient_portrait_item = rumps.MenuItem("  📱 竖屏模式 (1752x2800)", callback=lambda _: self.set_orientation("portrait"))
        self.pos_left_item = rumps.MenuItem("  ⬅️ 放在主屏左侧", callback=lambda _: self.set_position("left"))
        self.pos_right_item = rumps.MenuItem("✓ ➡️ 放在主屏右侧", callback=lambda _: self.set_position("right"))
        self.pos_top_item = rumps.MenuItem("  ⬆️ 放在主屏上方", callback=lambda _: self.set_position("top"))
        self.pos_bottom_item = rumps.MenuItem("  ⬇️ 放在主屏下方", callback=lambda _: self.set_position("bottom"))

        self.layout_menu.add(self.orient_landscape_item)
        self.layout_menu.add(self.orient_portrait_item)
        self.layout_menu.add(rumps.separator)
        self.layout_menu.add(self.pos_left_item)
        self.layout_menu.add(self.pos_right_item)
        self.layout_menu.add(self.pos_top_item)
        self.layout_menu.add(self.pos_bottom_item)

        # 工具项
        self.guide_lock_item = rumps.MenuItem("🛡️ 彻底解决平板黑屏/滑动锁", callback=self.show_game_booster_guide)
        self.guide_usb_item = rumps.MenuItem("⚡ Type-C 有线直连排障向导", callback=self.show_usb_tethering_guide)
        self.install_item = rumps.MenuItem("🛠️ 一键安装 Sunshine 串流服务端", callback=self.trigger_install_sunshine)
        self.diag_item = rumps.MenuItem("🔍 网络与环境诊断报告", callback=self.show_diagnostics)
        self.webui_item = rumps.MenuItem("打开 Sunshine 控制台", callback=self.open_sunshine_webui)
        self.quit_item = rumps.MenuItem("退出应用", callback=self.clean_and_quit)

        self.menu = [
            self.status_item,
            None,  # 分隔线
            self.usb_item,
            self.wifi_item,
            self.stop_item,
            None,
            self.layout_menu,
            None,
            self.guide_lock_item,
            self.guide_usb_item,
            None,
            self.install_item,
            self.diag_item,
            self.webui_item,
            None,
            self.quit_item,
        ]

        # 初始刷新菜单状态
        self.update_menu_states()

        # 注册退出清理钩子
        self._register_exit_handlers()

    def _register_exit_handlers(self):
        """注册异常中断与退场清理信号钩子"""
        atexit.register(self._cleanup_all)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"收到系统信号 {signum}，触发退场清理流程...")
        self._cleanup_all()
        sys.exit(0)

    def _cleanup_all(self):
        """确保 100% 终止 Sunshine 进程并销毁虚拟显示器，防止幽灵屏幕"""
        logger.info("执行全局资源回收清理...")
        try:
            self.sunshine_mgr.stop()
        except Exception as e:
            logger.error(f"清理 Sunshine 异常: {e}")

        try:
            self.display_mgr.destroy_display()
        except Exception as e:
            logger.error(f"销毁虚拟显示器异常: {e}")

        self.current_mode = "idle"
        self.current_ip = ""
        self.current_iface = ""

    def update_menu_states(self):
        """根据当前运行状态刷新菜单高亮与文本"""
        if self.is_installing_sunshine:
            self.title = "⏳ 正在安装 Sunshine..."
            return

        if self.current_mode == "idle":
            self.title = "📱 副屏: 闲置"
            self.status_item.title = "● 状态: 未连接"
            self.usb_item.set_callback(self.start_usb_mode)
            self.wifi_item.set_callback(self.start_wifi_mode)
            self.stop_item.set_callback(None)  # 禁用停止选项
        elif self.current_mode == "usb":
            self.title = "⚡️ 副屏: USB极速"
            self.status_item.title = f"● 运行中 [USB]: {self.current_ip} ({self.current_iface})"
            self.usb_item.set_callback(None)
            self.wifi_item.set_callback(None)
            self.stop_item.set_callback(self.stop_service)
        elif self.current_mode == "wifi":
            self.title = "📶 副屏: Wi-Fi"
            self.status_item.title = f"● 运行中 [Wi-Fi]: {self.current_ip} ({self.current_iface})"
            self.usb_item.set_callback(None)
            self.wifi_item.set_callback(None)
            self.stop_item.set_callback(self.stop_service)

    def show_status_details(self, _):
        """点击状态项查看详情弹窗"""
        if self.current_mode == "idle":
            sunshine_status = "已安装" if is_sunshine_installed() else "未安装 (请点击菜单一键安装)"
            rumps.alert(
                title=f"副屏调度器状态 (v{APP_VERSION})",
                message=f"当前服务处于闲置状态。\n版本: v{APP_VERSION}\nSunshine 串流服务: {sunshine_status}\n\n请选择「启动 (USB 极速模式)」或「启动 (Wi-Fi 便携模式)」。",
            )
        else:
            msg = (
                f"当前版本: v{APP_VERSION}\n"
                f"当前模式: {self.current_mode.upper()}\n"
                f"绑定网卡: {self.current_iface}\n"
                f"绑定 IP: {self.current_ip}\n"
                f"显示器分辨率: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT} (HiDPI: {'开启' if ENABLE_HIDPI else '关闭'})\n"
                f"DisplayID: {self.display_mgr.display_id}\n"
                f"Display UUID: {self.display_mgr.uuid}\n"
                f"Sunshine 运行状态: {'正常' if self.sunshine_mgr.is_running else '未运行'}"
            )
            rumps.alert(title=f"副屏连接详情 (v{APP_VERSION})", message=msg)

    def show_diagnostics(self, _):
        """运行网络与环境自检报告"""
        report = run_full_diagnostics()
        rumps.alert(title="系统与网络诊断报告", message=report)

    def trigger_install_sunshine(self, _=None):
        """一键触发安装 Sunshine"""
        if is_sunshine_installed():
            rumps.alert(title="环境检测", message="Sunshine 串流服务已安装，无需重复安装！")
            return

        response = rumps.alert(
            title="一键安装 Sunshine",
            message="即将自动为您从官方仓库下载并安装适合 Apple Silicon 的 Sunshine 串流服务端到 /Applications/ 目录。\n\n安装过程约需 10-30 秒，是否继续？",
            ok="立即开始安装",
            cancel="取消",
        )
        if response != 1:
            return

        self._start_install_thread()

    def _start_install_thread(self, then_activate_mode=None, iface=None, ip=None):
        """后台线程执行 Sunshine 安装流程"""
        self.is_installing_sunshine = True
        self.update_menu_states()

        def worker():
            try:
                logger.info("后台正在执行 Sunshine 一键安装流程...")
                success = install_sunshine()
                self.is_installing_sunshine = False
                if success:
                    rumps.notification(
                        title="Sunshine 安装成功！",
                        subtitle="环境配置完成",
                        message="Sunshine 串流服务已成功部署至 /Applications/Sunshine.app！",
                    )
                    if then_activate_mode and ip:
                        # 安装完毕后自动激活串流
                        self._activate_streaming(then_activate_mode, iface, ip)
                    else:
                        self.update_menu_states()
                else:
                    self.update_menu_states()
                    rumps.alert(
                        title="安装未完成",
                        message="自动安装 Sunshine 出现异常，请检查网络连接或手动执行: brew install sunshine",
                    )
            except Exception as e:
                self.is_installing_sunshine = False
                self.update_menu_states()
                logger.error(f"安装 Sunshine 出错: {e}")
                rumps.alert(title="安装失败", message=str(e))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def show_game_booster_guide(self, _=None):
        """弹出三星 Game Booster 游戏助推器滑动锁与防黑屏指引"""
        guide = get_game_booster_solution_guide()
        adb_ok = False
        try:
            adb_ok = enable_stay_awake()
        except Exception:
            pass

        extra = "\n\n【ADB 设备与常亮状态】\n" + ("已检测到 USB 连接的 Android 设备，并已自动下发系统常亮指令！" if adb_ok else "当前未检测到 ADB 调试连接（建议按上方步骤在平板系统设置中修改）。")
        rumps.alert(title="🛡️ 平板防黑屏与滑动锁终极方案", message=guide + extra)

    def show_usb_tethering_guide(self, _=None):
        """弹出 Type-C 直连排障与使用向导"""
        msg = (
            "【Type-C 数据线直连极速副屏指南】\n\n"
            "有线直连具备更高的抗干扰能力与 0ms 级的即时响应：\n\n"
            "步骤 1：连接数据线\n"
            "使用原装或高质量 Type-C 数据线（支持传输数据）连接 Mac 与三星平板。\n\n"
            "步骤 2：开启平板端 USB 网络共享\n"
            "进入三星平板【设置】->【连接】->【移动热点和网络共享】-> 开启【USB 网络共享】。\n"
            "（注意：必须在连接数据线后，该开关才能点击开启！）\n\n"
            "步骤 3：Mac 点击启动\n"
            "点击 Mac 菜单栏中的「启动 (USB 极速模式)」，调度器将在 15 秒内自动识别网卡。\n\n"
            "步骤 4：平板 Moonlight 连接\n"
            "在平板 Moonlight 中点击右上角添加对应的 IP，即可享受最高带宽有线副屏！"
        )
        rumps.alert(title="⚡ Type-C 有线直连向导", message=msg)

    def start_usb_mode(self, _):
        """启动 USB 极速模式（异步检测，避免主 UI 线程卡顿）"""
        if self.current_mode != "idle":
            return

        logger.info("用户请求启动 USB 极速模式...")
        self.title = "⏳ 正在检测 USB..."

        def worker():
            # 1. 尝试检测 ADB 并一键发送屏幕常亮指令
            try:
                if enable_stay_awake():
                    logger.info("已通过 ADB 自动为 Android 平板激活屏幕常亮！")
            except Exception as e:
                logger.debug(f"ADB 常亮设置跳过: {e}")

            # 2. 轮询检测 Android USB 网络共享网卡
            def on_progress(remaining):
                self.title = f"⏳ 探测 USB ({remaining}s)..."

            iface, ip = detect_usb_tethering_ip(progress_callback=on_progress)

            if not iface or not ip:
                logger.warning("未检测到 Android USB Tethering 共享网卡")
                self.update_menu_states()
                rumps.alert(
                    title="未检测到 USB 网络共享网卡",
                    message=(
                        "未能发现 Android 平板通过 Type-C 数据线共享的网络接口。\n\n"
                        "💡 常见排查与操作步骤：\n"
                        "1. 请确认连接的是【支持数据传输】的 Type-C 线（非纯充电线）；\n"
                        "2. 在三星平板上进入：【设置】->【连接】->【移动热点和网络共享】；\n"
                        "3. 将【USB 网络共享】开关手动开启（插线后才可点击）；\n"
                        "4. 开启后重新点击「启动 (USB 极速模式)」即可秒连！\n\n"
                        "若需详细排查，请点击菜单「⚡ Type-C 直连向导」或使用 Wi-Fi 模式。"
                    ),
                )
                return

            # 3. 检查 Sunshine 是否已安装
            if not is_sunshine_installed():
                self.update_menu_states()
                resp = rumps.alert(
                    title="尚未安装 Sunshine 服务",
                    message=(
                        f"已成功识别到 USB 共享网卡 ({iface} -> {ip})！\n\n"
                        "但系统中尚未检测到 Sunshine 串流服务端，无法推流给平板。\n"
                        "是否立即为您一键自动安装 Sunshine？"
                    ),
                    ok="一键自动安装并启动",
                    cancel="取消",
                )
                if resp == 1:
                    self._start_install_thread(then_activate_mode="usb", iface=iface, ip=ip)
                return

            # 4. 执行副屏与推流调度
            self._activate_streaming(mode="usb", iface=iface, ip=ip)
            rumps.notification(
                title="⚡ Type-C 极速直连已建立！",
                subtitle=f"绑定网卡: {iface} ({ip})",
                message="请在平板端 Moonlight 连接该 IP，尽享满血低延迟 120Hz 视网膜副屏！",
            )

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def start_wifi_mode(self, _):
        """启动 Wi-Fi 便携模式"""
        logger.info("用户请求启动 Wi-Fi 便携模式...")
        self.title = "🔄 正在获取 Wi-Fi IP..."

        # 1. 获取主 Wi-Fi 网卡 IP
        iface, ip = get_wifi_ip()
        if not ip:
            logger.warning("未能获取到当前 Wi-Fi 网卡的 IPv4 地址")
            self.update_menu_states()
            rumps.alert(
                title="Wi-Fi 未连接",
                message="未能获取到本机的 Wi-Fi 局域网 IP 地址，请检查 Wi-Fi 是否已连接到路由器。",
            )
            return

        # 2. 检查 Sunshine 是否已安装
        if not is_sunshine_installed():
            resp = rumps.alert(
                title="尚未安装 Sunshine 服务",
                message=(
                    f"已成功获取 Wi-Fi 局域网 IP ({ip})！\n\n"
                    "但系统中尚未检测到 Sunshine 串流服务端，无法推流给平板。\n"
                    "是否立即为您一键自动安装 Sunshine？"
                ),
                ok="一键自动安装并启动",
                cancel="取消",
            )
            if resp == 1:
                self._start_install_thread(then_activate_mode="wifi", iface=iface, ip=ip)
            return

        # 3. 执行副屏与推流调度
        self._activate_streaming(mode="wifi", iface=iface, ip=ip)

    def set_orientation(self, orient: str):
        """切换屏幕朝向：横屏 (landscape) / 竖屏 (portrait)"""
        if self.orientation == orient:
            return
        self.orientation = orient
        self.orient_landscape_item.title = "✓ 🖥️ 横屏模式 (2800x1752)" if orient == "landscape" else "  🖥️ 横屏模式 (2800x1752)"
        self.orient_portrait_item.title = "✓ 📱 竖屏模式 (1752x2800)" if orient == "portrait" else "  📱 竖屏模式 (1752x2800)"
        logger.info(f"已切换屏幕朝向为: {orient}")

        # 如果当前正处于串流状态，平滑热重载新分辨率
        if self.current_mode != "idle":
            rumps.notification(
                title="正在旋转屏幕方向",
                subtitle=f"切换至{'横屏' if orient == 'landscape' else '竖屏'}",
                message="正在重新调整虚拟屏幕比例并推流...",
            )
            self._activate_streaming(self.current_mode, self.current_iface, self.current_ip)

    def set_position(self, pos: str):
        """切换副屏相对主屏的摆放方位 (left, right, top, bottom)"""
        self.position = pos
        self.pos_left_item.title = "✓ ⬅️ 放在主屏左侧" if pos == "left" else "  ⬅️ 放在主屏左侧"
        self.pos_right_item.title = "✓ ➡️ 放在主屏右侧" if pos == "right" else "  ➡️ 放在主屏右侧"
        self.pos_top_item.title = "✓ ⬆️ 放在主屏上方" if pos == "top" else "  ⬆️ 放在主屏上方"
        self.pos_bottom_item.title = "✓ ⬇️ 放在主屏下方" if pos == "bottom" else "  ⬇️ 放在主屏下方"
        logger.info(f"已切换副屏相对位置为: {pos}")

        # 如果当前正在运行，无缝即时调整位置
        if self.current_mode != "idle":
            self.display_mgr.change_position(pos)
            pos_names = {"left": "左侧", "right": "右侧", "top": "上方", "bottom": "下方"}
            rumps.notification(
                title="副屏方位已更新",
                subtitle=f"当前排布: {pos_names.get(pos, pos)}",
                message="鼠标与窗口跨屏移动方向已即时调整生效！",
            )

    def _activate_streaming(self, mode: str, iface: str, ip: str):
        """创建虚拟屏幕、配置 Sunshine 并启动串流"""
        try:
            # 1. 根据当前选择的屏幕朝向确定宽高
            if self.orientation == "portrait":
                w, h = DISPLAY_HEIGHT, DISPLAY_WIDTH  # 1752 x 2800
            else:
                w, h = DISPLAY_WIDTH, DISPLAY_HEIGHT  # 2800 x 1752

            logger.info(f"正在创建虚拟显示器 ({w}x{h}, 朝向: {self.orientation}, 方位: {self.position})...")
            disp_info = self.display_mgr.create_display(
                width=w,
                height=h,
                hidpi=ENABLE_HIDPI,
                position=self.position,
            )
            display_id = disp_info.get("display_id")
            uuid_str = disp_info.get("uuid")

            # 等待 macOS 系统图形服务完全注册新创建的虚拟副屏
            import time
            time.sleep(1.2)

            # 2. 启动 Sunshine 并覆写绑定的 IP
            logger.info(f"正在配置并启动 Sunshine (目标 IP: {ip}, DisplayID: {display_id})...")
            self.sunshine_mgr.start(target_ip=ip, display_id=display_id)

            # 3. 更新状态
            self.current_mode = mode
            self.current_iface = iface
            self.current_ip = ip
            self.update_menu_states()

            orient_name = "横屏" if self.orientation == "landscape" else "竖屏"
            rumps.notification(
                title="副屏调度已启动",
                subtitle=f"{mode.upper()} 模式 | {orient_name} ({w}x{h})",
                message=f"虚拟副屏已就绪 (ID: {display_id})，请在平板 Moonlight 连接！",
            )

        except Exception as e:
            logger.error(f"激活副屏服务失败: {e}", exc_info=True)
            self._cleanup_all()
            self.update_menu_states()
            rumps.alert(
                title="启动失败",
                message=f"调度器启动过程中发生错误：\n{str(e)}",
            )

    def stop_service(self, _):
        """停止副屏与串流"""
        logger.info("用户请求停止副屏服务...")
        self._cleanup_all()
        self.update_menu_states()
        rumps.notification(
            title="副屏已断开",
            subtitle="服务已停止",
            message="已终止 Sunshine 进程并成功销毁虚拟显示器，无幽灵屏幕残留。",
        )


    def open_sunshine_webui(self, _):
        """快捷打开 Sunshine 管理后台"""
        host = self.current_ip if (self.current_ip and self.current_ip != "0.0.0.0") else "localhost"
        url = f"https://{host}:{SUNSHINE_WEB_UI_PORT}"
        logger.info(f"正在打开 Sunshine 管理控制台: {url}")
        webbrowser.open(url)

    def clean_and_quit(self, _):
        """安全退出应用"""
        logger.info("用户请求退出应用...")
        self._cleanup_all()
        rumps.quit_application()


if __name__ == "__main__":
    app = DisplaySamsungApp()
    app.run()
