#!/bin/bash

# 清理 Xvfb 锁文件，防止容器因为异常关闭而重启失败
if [ -f /tmp/.X99-lock ]; then
    echo "Cleaning up Xvfb lock file"
    rm -f /tmp/.X99-lock
fi

# 启动 Xvfb
echo "Starting Xvfb on DISPLAY=:99"
Xvfb :99 -screen 0 1280x1024x24 &
sleep 2

# 检查 Xvfb 是否正常运行
if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "Xvfb failed to start"
    exit 1
fi

# 设置 DISPLAY 环境变量
export DISPLAY=:99
echo "DISPLAY is set to $DISPLAY"

# 创建符号链接
if [ ! -L "./dist" ]; then
    ln -s ui/dist ./dist
fi

# 启动mower应用
echo "Starting application..."
dbus-run-session -- ./venv/bin/python /app/webview_ui.py