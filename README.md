# DisplaySamsung - macOS Android 平板副屏自动化调度器

专为 Android 平板（特别是三星 Galaxy Tab S7+ / S8+ / S9+ 等 2800x1752 屏幕）设计的 macOS 状态栏副屏自动化调度器。通过 Sunshine / Moonlight 串流协议，支持 USB 有线极速直连与 Wi-Fi 便携模式的一键无缝切换。

---

## 🌟 核心特性

- 🖥️ **一键状态栏控制**：基于 `rumps` 原生菜单栏设计，实时显示连接状态，支持一键切换「启动 (USB 极速模式)」、「启动 (Wi-Fi 便携模式)」与「停止」。
- ⚡ **精准网络路由（核心技术）**：
  - **USB 模式**：自动轮询识别 Android USB 网络共享（USB Tethering）生成的虚拟以太网卡，提取 IPv4 并覆写 Sunshine `bind_address`，强制所有串流流量走 USB 极速通道，实现超低延迟、超高画质。未开启时弹窗友好引导。
  - **Wi-Fi 模式**：自动探测默认路由与 Wi-Fi 主网卡（en0），提取局域网 IP 供随航串流。
- 🖥️ **原生 2800x1752 HiDPI 虚拟屏幕**：
  - 内置基于 macOS `CGVirtualDisplay` API 的轻量级原生驱动，开箱即用，免去昂贵的第三方收费软件。
  - 自动捕获该显示器的 `DisplayID` 与 `UUID`。
  - 亦兼容 `betterdisplaycli` 拓展方案。
- 🛡️ **防幽灵屏幕优雅退场**：
  - 监听停止按钮、菜单退出事件以及系统信号（`SIGINT`/`SIGTERM`/`atexit`）。
  - 双重保险：100% 杀死 Sunshine 进程并同步销毁虚拟显示器，绝不在系统设置中残留幽灵假屏幕。

---

## 📁 项目目录结构

```
/Users/hequanwei/Desktop/DisplaySamsung/
├── config.py                 # 全局配置（分辨率 2800x1752、网卡规则、超时设置）
├── network_manager.py        # 精准网络路由模块（USB 共享网络与 Wi-Fi 探测）
├── display_manager.py        # 虚拟显示器生命周期管理（创建/捕获ID/销毁）
├── sunshine_manager.py       # Sunshine 配置覆写、进程调度与自动备份还原
├── app.py                    # rumps 状态栏主应用程序
├── tools/
│   ├── virtual_display.m     # 原生虚拟显示器驱动源码（基于 CoreGraphics）
│   └── virtual_display       # 编译后的独立二进制工具
├── test_suite.py             # 自动化测试与生命周期验证套件
├── requirements.txt          # Python 依赖清单
├── run.sh                    # 一键启动脚本
└── README.md                 # 使用说明文档
```

---

## 🚀 极速安装与使用方式

### 方式一：DMG 镜像拖拽安装（最推荐，免 Python 环境、开箱即用）
本项目已直接制作好标准 macOS `.dmg` 安装镜像包：
1. 打开文件：**`dist/DisplaySamsung-Installer.dmg`**；
2. 将 **`DisplaySamsung`** 图标直接拖入 **`Applications`** 文件夹；
3. 从启动台或应用程序中**双击打开**即可，菜单栏将常驻副屏图标，完全无需配置 Python 环境！

### 方式二：一键脚本运行与再次打包
* **源码运行**：
  ```bash
  ./run.sh
  ```
* **一键重新构建 DMG 安装镜像**：
  ```bash
  ./build_dmg.sh
  ```
  执行后会自动编译、打包并在 `dist/` 目录下生成全新的 `DisplaySamsung-Installer.dmg`。

---

## 📖 使用指南

### 启动 USB 极速模式（推荐）
1. 使用 USB-C 数据线将 Android 平板连接至 Mac。
2. 在 Android 平板中打开：**设置 -> 连接与共享 -> 开启「USB 网络共享」**。
3. 点击 macOS 顶部菜单栏的 `📱 副屏: 闲置` 图标，选择 **「启动 (USB 极速模式)」**。
4. 调度器将自动识别以太网卡 IP、创建 2800x1752 HiDPI 屏幕、覆写 Sunshine 配置并启动服务。
5. 在平板端 Moonlight 中输入对应 IP 即可享受超低延迟副屏。

### 启动 Wi-Fi 便携模式
1. 确保 Mac 与 Android 平板连接在同一个 Wi-Fi / 局域网下。
2. 点击菜单栏图标，选择 **「启动 (Wi-Fi 便携模式)」**。
3. 调度器将自动绑定 Mac Wi-Fi IP，打开平板 Moonlight 即可无线连接。

### 停止与退出
- 点击 **「停止副屏与串流」**：将立即安全结束 Sunshine 进程，并即时注销虚拟显示器，恢复 Sunshine 初始配置。
- 点击 **「退出应用」**：触发完整的优雅退场流程并退出。

---

## 🧪 运行自动化测试
```bash
source .venv/bin/activate
python test_suite.py
```
全部 4 项核心测试覆盖网卡识别、IP 校验、Sunshine 配置覆盖回滚以及虚拟显示器创建/注销全生命周期。
