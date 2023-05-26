#!/usr/bin/env python3

import webview
from server import app

import os


def start_server(app):
    app.run(host="127.0.0.1", port="8000")


if __name__ == "__main__":
    webview.create_window("Mower Web UI in WebView (尚不完善，测试用途，谨慎使用)", "http://127.0.0.1:8000", width=900, height=600)
    webview.start(start_server, app)

    os._exit(0)
