#!/bin/bash

ln -s ui/dist .

# 启动Xvfb
Xvfb :99 -screen 0 1280x1024x24 &

export DISPLAY=":99"

# 等待Xvfb启动完成
sleep 5

# 启动应用
dbus-run-session -- ./venv/bin/python /app/webview_ui.py