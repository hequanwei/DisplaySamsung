"""
Mole 风格独立控制中心与实时日志面板 (Dashboard & Settings)
基于本地微型服务与原生 NSWindow + WKWebView 构建，
为用户提供沉浸式毛玻璃卡片、实时日志流、方向排布切换与平板卫士交互。
"""

import os
import sys
import json
import logging
import threading
import subprocess
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import (
    APP_VERSION,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    LOG_FILE_PATH,
    BASE_DIR,
)

logger = logging.getLogger("DisplaySamsung.Dashboard")

PORT = 49221
WEB_DIR = BASE_DIR / "assets" / "web"


class DashboardHandler(BaseHTTPRequestHandler):
    """处理前端与调度器之间的数据与动作桥接"""

    # 由外部注入的调度器主应用引用
    app_ref = None

    def log_message(self, format, *args):
        # 静默普通请求日志，保持终端清爽
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/status":
            self._handle_get_status()
        elif path == "/api/logs":
            self._handle_get_logs()
        elif path == "/api/logs/reveal":
            self._handle_reveal_logs()
        elif path == "/api/mode":
            self._handle_set_mode(qs.get("action", [""])[0])
        elif path == "/api/orientation":
            self._handle_set_orientation(qs.get("val", [""])[0])
        elif path == "/api/position":
            self._handle_set_position(qs.get("val", [""])[0])
        elif path == "/api/stay_awake":
            self._handle_stay_awake()
        elif path == "/api/tools/webui":
            self._handle_open_webui()
        elif path == "/api/tools/install_sunshine":
            self._handle_install_sunshine()
        elif path == "/api/tools/diagnostics":
            self._handle_run_diagnostics()
        else:
            self._serve_static_file(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/logs/clear":
            self._handle_clear_logs()
        else:
            self.send_error(404)

    def _serve_static_file(self, path):
        if path == "/" or not path:
            path = "/index.html"
        file_path = WEB_DIR / path.lstrip("/")

        if not file_path.is_file():
            self.send_error(404, "File Not Found")
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
        }
        ctype = content_types.get(file_path.suffix.lower(), "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_get_status(self):
        app = self.app_ref
        status_data = {
            "version": APP_VERSION,
            "mode": getattr(app, "current_mode", "idle"),
            "ip": getattr(app, "current_ip", ""),
            "iface": getattr(app, "current_iface", ""),
            "width": DISPLAY_WIDTH,
            "height": DISPLAY_HEIGHT,
            "orientation": getattr(app, "orientation", "landscape"),
            "position": getattr(app, "position", "right"),
            "is_sunshine_installed": True,
        }
        body = json.dumps(status_data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_logs(self):
        """读取日志文件最新 150 行"""
        lines = []
        if LOG_FILE_PATH.exists():
            try:
                with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
                    lines = all_lines[-150:]
            except Exception as e:
                lines = [f"读取日志异常: {e}\n"]
        else:
            lines = ["日志文件尚在创建中...\n"]

        body = "".join(lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_clear_logs(self):
        try:
            if LOG_FILE_PATH.exists():
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write("")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_reveal_logs(self):
        try:
            subprocess.run(["open", "-R", str(LOG_FILE_PATH)], check=False)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_set_mode(self, action):
        app = self.app_ref
        if not app:
            self.send_error(500)
            return

        if action == "usb":
            threading.Thread(target=app.start_usb_mode, args=(None,), daemon=True).start()
        elif action == "wifi":
            threading.Thread(target=app.start_wifi_mode, args=(None,), daemon=True).start()
        elif action == "hotspot":
            threading.Thread(target=app.start_hotspot_mode, args=(None,), daemon=True).start()
        elif action == "stop":
            threading.Thread(target=app.stop_service, args=(None,), daemon=True).start()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_set_orientation(self, orient):
        app = self.app_ref
        if app and orient in ["landscape", "portrait"]:
            app.set_orientation(orient)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_set_position(self, pos):
        app = self.app_ref
        if app and pos in ["left", "right", "top", "bottom"]:
            app.set_position(pos)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_stay_awake(self):
        from android_manager import enable_stay_awake
        ok = enable_stay_awake()
        msg = "已成功向连接的 Android 平板下发常亮指令！" if ok else "未检测到 ADB 授权连接的设备，请在平板中开启 USB 调试。"
        body = msg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_open_webui(self):
        app = self.app_ref
        if app:
            app.open_sunshine_webui(None)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_install_sunshine(self):
        app = self.app_ref
        if app:
            app.trigger_install_sunshine(None)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_run_diagnostics(self):
        app = self.app_ref
        if app:
            app.show_diagnostics(None)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


class DashboardManager:
    """控制中心窗口与服务器管理器"""

    def __init__(self, app_ref):
        self.app_ref = app_ref
        DashboardHandler.app_ref = app_ref
        self.server = None
        self.server_thread = None
        self.window = None
        self._start_server()

    def _start_server(self):
        try:
            self.server = HTTPServer(("127.0.0.1", PORT), DashboardHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            logger.info(f"控制中心微型服务已在 http://127.0.0.1:{PORT} 启动")
        except Exception as e:
            logger.warning(f"启动控制中心 HTTP 服务异常: {e}")

    def show_dashboard(self, initial_tab=None):
        """显示控制中心窗口（优先原生 NSWindow + WKWebView，降级浏览器）"""
        url = f"http://127.0.0.1:{PORT}/"
        if initial_tab:
            url += f"#{initial_tab}"

        # 尝试调用原生 WebKit 独立窗口
        try:
            self._open_native_window(url)
        except Exception as e:
            logger.info(f"呼出原生窗口异常 ({e})，降级使用独立浏览器模式打开")
            webbrowser.open(url)

    def _open_native_window(self, url_str):
        from AppKit import (
            NSApplication,
            NSWindow,
            NSMakeRect,
            NSTitledWindowMask,
            NSClosableWindowMask,
            NSMiniaturizableWindowMask,
            NSResizableWindowMask,
            NSBackingStoreBuffered,
            NSURL,
            NSURLRequest,
        )
        from WebKit import WKWebView

        if self.window is not None:
            self.window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            return

        # 创建 860x600 居中窗口
        rect = NSMakeRect(0, 0, 860, 620)
        style = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        window.setTitle_(f"DisplaySamsung 控制中心 (v{APP_VERSION})")
        window.center()

        webview = WKWebView.alloc().initWithFrame_(rect)
        ns_url = NSURL.URLWithString_(url_str)
        req = NSURLRequest.requestWithURL_(ns_url)
        webview.loadRequest_(req)

        window.setContentView_(webview)
        window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window = window

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass
