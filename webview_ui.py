#!/usr/bin/env python3

import webview
from server import app, mower_process

import os
import multiprocessing

from arknights_mower.utils.conf import load_conf, save_conf
from arknights_mower.__init__ import __version__

from threading import Thread
from PIL import Image
from pystray import Icon, Menu, MenuItem

import socket
import tkinter
from tkinter import messagebox
from time import sleep
import sys


quit_app = False
display = True


def on_resized(w, h):
    global width
    global height

    width = w
    height = h


def toggle_window():
    global window
    global display
    window.hide() if display else window.show()
    display = not display


def on_closing():
    if not quit_app:
        Thread(target=toggle_window).start()
        return False


def destroy_window():
    global quit_app
    global window
    quit_app = True
    window.destroy()


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


if __name__ == "__main__":
    multiprocessing.freeze_support()

    conf = load_conf()

    port = conf["webview"]["port"]
    token = conf["webview"]["token"]
    host = "0.0.0.0" if token else "127.0.0.1"

    if is_port_in_use(port):
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(
            "arknights-mower",
            f"端口{port}已被占用，无法启动！",
        )
        sys.exit()

    app.token = token
    Thread(
        target=app.run,
        kwargs={"host": host, "port": port},
        daemon=True,
    ).start()

    global width
    global height

    width = conf["webview"]["width"]
    height = conf["webview"]["height"]

    tray_img = Image.open(os.path.join(os.getcwd(), "logo.png"))
    icon = Icon(
        "arknights-mower",
        icon=tray_img,
        menu=Menu(
            MenuItem(
                text="显示/隐藏窗口",
                action=toggle_window,
                default=True,
            ),
            MenuItem(
                text="退出",
                action=destroy_window,
            ),
        ),
    )
    icon.run_detached()

    global window
    window = webview.create_window(
        f"Mower {__version__} (http://{host}:{port})",
        f"http://127.0.0.1:{port}?token={token}",
        width=width,
        height=height,
        text_select=True,
    )

    window.events.resized += on_resized
    window.events.closing += on_closing

    while not is_port_in_use(port):
        sleep(0.1)
    webview.start()

    global mower_process
    if mower_process:
        mower_process.terminate()
        mower_process = None

    icon.stop()

    conf = load_conf()
    conf["webview"]["width"] = width
    conf["webview"]["height"] = height
    save_conf(conf)
