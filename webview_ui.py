#!/usr/bin/env python3

import webview
from server import app

import os
import multiprocessing


def start_server(app):
    app.run(host="127.0.0.1", port="8000")


if __name__ == "__main__":
    multiprocessing.freeze_support()

    webview.create_window(
        "Mower Web UI in WebView (尚不完善，测试用途，谨慎使用)",
        "http://127.0.0.1:8000",
        width=1200,
        height=900,
    )
    webview.start(start_server, app)

    os._exit(0)
