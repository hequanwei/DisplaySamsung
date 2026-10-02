#!/usr/bin/env bash
# ==============================================================================
# DisplaySamsung 一键启动与运行调度器
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================="
echo "  📱 Android 平板副屏自动化调度器 (DisplaySamsung)"
echo "=================================================="

# 1. 检查 Python 环境
PYTHON_BIN="python3"
if [ -d ".venv" ]; then
    echo "✓ 正在激活虚拟环境..."
    source .venv/bin/activate
else
    echo "⚡ 正在初始化虚拟环境..."
    $PYTHON_BIN -m venv .venv
    source .venv/bin/activate
    echo "⚡ 正在安装 Python 依赖项..."
    pip install -r requirements.txt
fi

# 2. 检查并确保原生虚拟显示器二进制可执行
if [ ! -f "tools/virtual_display" ]; then
    echo "⚡ 正在编译原生虚拟显示器驱动 (2800x1752 HiDPI)..."
    clang -fno-modules -fobjc-arc -framework Cocoa -framework CoreGraphics -o tools/virtual_display tools/virtual_display.m
fi
chmod +x tools/virtual_display

# 3. 检查 Sunshine 安装状态，若缺失则提供一键自动安装
SUNSHINE_FOUND=false
if command -v sunshine &> /dev/null || [ -d "/Applications/Sunshine.app" ] || [ -f "/opt/homebrew/bin/sunshine" ]; then
    SUNSHINE_FOUND=true
    echo "✓ Sunshine 串流服务已就绪"
else
    echo "--------------------------------------------------"
    echo "⚠️  检测到系统中尚未安装 Sunshine 串流服务端！"
    echo "    副屏串流需要 Sunshine 服务支持。"
    read -p "👉 是否现在为您一键自动安装 Sunshine？[Y/n]: " choice
    choice=${choice:-Y}
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        echo "⚡ 正在启动全自动下载与安装流程..."
        python installer.py --install-sunshine
    else
        echo "ℹ️  跳过 Sunshine 安装，后续可通过菜单栏或手动安装。"
    fi
    echo "--------------------------------------------------"
fi

echo "🚀 正在启动状态栏调度器 (菜单栏图标: 📱)..."
python app.py
