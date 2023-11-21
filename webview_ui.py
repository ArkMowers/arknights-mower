#!/usr/bin/env python3

import webview
import server
from server import app

import multiprocessing

from arknights_mower.utils.conf import load_conf, save_conf
from arknights_mower.utils.path import get_path
from arknights_mower.__init__ import __version__

from threading import Thread
from PIL import Image, ImageTk
from pystray import Icon, Menu, MenuItem

import socket
import tkinter as tk
from tkinter.font import Font
from tkinter import messagebox
from time import sleep
import sys


quit_app = False
display = True
window = None


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
    if quit_app:
        return True
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


logo_path = get_path("@internal/logo.png")
tray_img = Image.open(logo_path)


class SplashScreen:
    def __init__(self):
        self.root = tk.Tk()

        self.canvas = tk.Canvas(self.root, width=256, height=256)
        self.canvas.pack()
        self.img = ImageTk.PhotoImage(tray_img)
        self.canvas.create_image(128, 128, image=self.img)

        self.title_font = Font(size=24)
        self.title_label = tk.Label(
            self.root, text=f"arknights-mower {__version__}", font=self.title_font
        )
        self.title_label.pack()

        self.loading_label = tk.Label(self.root)
        self.loading_label.pack()
        self.root.overrideredirect(True)

    def show_text(self, text):
        self.loading_label.config(text=text)
        self.center()

    def center(self):
        self.root.eval("tk::PlaceWindow . center")
        self.root.update()

    def stop(self):
        self.root.destroy()


if __name__ == "__main__":
    multiprocessing.freeze_support()

    splash = SplashScreen()
    splash.show_text("加载配置文件")

    conf = load_conf()

    port = conf["webview"]["port"]
    token = conf["webview"]["token"]
    host = "0.0.0.0" if token else "127.0.0.1"

    if is_port_in_use(port):
        messagebox.showerror(
            "arknights-mower",
            f"端口{port}已被占用，无法启动！",
        )
        sys.exit()

    splash.show_text("启动flask网页服务器")

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

    splash.show_text("加载托盘图标")

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

    splash.show_text("准备主窗口")

    window = webview.create_window(
        f"arknights-mower {__version__} (http://{host}:{port})",
        f"http://127.0.0.1:{port}?token={token}",
        width=width,
        height=height,
        text_select=True,
    )

    window.events.resized += on_resized
    window.events.closing += on_closing

    while not is_port_in_use(port):
        sleep(0.1)

    splash.stop()
    webview.start()

    window = None

    if server.mower_process:
        server.mower_process.terminate()
        server.mower_process = None

    icon.stop()

    conf = load_conf()
    conf["webview"]["width"] = width
    conf["webview"]["height"] = height
    save_conf(conf)
