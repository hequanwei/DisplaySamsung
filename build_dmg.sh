#!/usr/bin/env bash
# ==============================================================================
# DisplaySamsung 自动化制作 macOS .app 与 .dmg 安装文件
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================="
echo "  📦 正在制作 DisplaySamsung macOS 安装镜像 (DMG)"
echo "=================================================="

# 1. 激活环境
if [ ! -d ".venv" ]; then
    echo "⚡ 正在初始化虚拟环境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install pyinstaller
else
    source .venv/bin/activate
fi

# 2. 编译原生驱动
echo "⚡ 编译原生虚拟显示器驱动..."
clang -fno-modules -fobjc-arc -framework Cocoa -framework CoreGraphics -o tools/virtual_display tools/virtual_display.m
chmod +x tools/virtual_display

# 2.1 确保打包包含独立可用的 adb
if [ ! -f "tools/adb" ]; then
    SYS_ADB=$(which adb || echo "/opt/homebrew/bin/adb")
    if [ -f "$SYS_ADB" ]; then
        echo "⚡ 正在拷贝系统 ADB ($SYS_ADB) 到 tools/adb 以便自包含打包..."
        cp "$SYS_ADB" tools/adb
        chmod +x tools/adb
    fi
fi


# 3. 检查/生成应用图标
if [ ! -f "assets/app.icns" ]; then
    echo "⚡ 生成应用图标..."
    mkdir -p assets
    python -c "
import os, subprocess
from Cocoa import NSImage, NSBitmapImageRep, NSColor, NSBezierPath, NSMakeRect
iconset_dir = 'assets/app.iconset'
os.makedirs(iconset_dir, exist_ok=True)
for s in [16, 32, 64, 128, 256, 512, 1024]:
    img = NSImage.alloc().initWithSize_((s, s))
    img.lockFocus()
    rect = NSMakeRect(s * 0.05, s * 0.05, s * 0.9, s * 0.9)
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, s * 0.2, s * 0.2).fill()
    inner = NSMakeRect(s * 0.18, s * 0.22, s * 0.64, s * 0.56)
    NSColor.whiteColor().setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inner, s * 0.06, s * 0.06).fill()
    img.unlockFocus()
    tiff = img.TIFFRepresentation()
    bitmap = NSBitmapImageRep.imageRepWithData_(tiff)
    png = bitmap.representationUsingType_properties_(4, None)
    png.writeToFile_atomically_(os.path.join(iconset_dir, f'icon_{s}x{s}.png'), True)
    if s <= 512:
        png.writeToFile_atomically_(os.path.join(iconset_dir, f'icon_{s}x{s}@2x.png'), True)
subprocess.run(['iconutil', '-c', 'icns', iconset_dir, '-o', 'assets/app.icns'], check=True)
"
fi

# 4. 执行 PyInstaller 打包
echo "⚡ 正在打包独立 macOS 应用 (DisplaySamsung.app)..."
rm -rf build dist .pyinstaller_cache
export PYINSTALLER_CONFIG_DIR="$PROJECT_DIR/.pyinstaller_cache"

pyinstaller \
    --noconfirm \
    --windowed \
    --name "DisplaySamsung" \
    --icon "assets/app.icns" \
    --add-binary "tools/virtual_display:tools" \
    --add-binary "tools/adb:tools" \
    --add-data "assets/web:assets/web" \
    --hidden-import "rumps" \
    --hidden-import "psutil" \
    --hidden-import "objc" \
    --hidden-import "Foundation" \
    --hidden-import "AppKit" \
    --hidden-import "WebKit" \
    --hidden-import "packaging" \
    app.py

APP_PATH="dist/DisplaySamsung.app"
if [ ! -d "$APP_PATH" ]; then
    echo "❌ 打包失败，未找到 $APP_PATH"
    exit 1
fi

# 5. 配置 Info.plist：开启 LSUIElement (菜单栏常驻纯净应用，不在 Dock 显示多余大图标)
echo "⚡ 配置 Info.plist (菜单栏纯净常驻)..."
PLIST_PATH="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST_PATH"

# 6. 制作 DMG 拖拽安装镜像
echo "⚡ 正在创建 DMG 安装镜像..."
DMG_STAGING="dist/dmg_staging"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

# 拷贝 .app 到暂存目录
cp -R "$APP_PATH" "$DMG_STAGING/"

# 创建 Applications 软链接供用户拖拽安装
ln -s /Applications "$DMG_STAGING/Applications"

# 生成 .dmg 文件
DMG_OUTPUT="dist/DisplaySamsung-Installer.dmg"
rm -f "$DMG_OUTPUT"

hdiutil create \
    -volname "DisplaySamsung 安装" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$DMG_OUTPUT"

# 清理暂存目录与本地解压的 app，避免 Launchpad/Spotlight 出现双 App 重复图标
rm -rf "$DMG_STAGING" "$APP_PATH"
touch dist/.metadata_never_index

echo "=================================================="
echo "🎉 DMG 安装镜像制作成功！"
echo "👉 文件位置: $PROJECT_DIR/$DMG_OUTPUT"
echo "💡 使用方法: 双击该 DMG 文件，将 DisplaySamsung 图标拖拽入 Applications 文件夹即可！"
echo "=================================================="
