#!/usr/bin/env python3
import multiprocessing as mp

window = None
tray_process = None
width = None
height = None

if __name__ == "__main__":
    mp.freeze_support()

    import tkinter as tk
    from tkinter.font import Font

    class SplashScreen:
        def __init__(self):
            self.root = tk.Tk()

            self.container = tk.Frame(self.root)

            self.canvas = tk.Canvas(self.container, width=256, height=256)
            self.canvas.pack()

            self.title_font = Font(size=24)
            self.title_label = tk.Label(
                self.container, text="arknights-mower", font=self.title_font
            )
            self.title_label.pack()

            self.loading_label = tk.Label(self.container)
            self.loading_label.pack()

            self.container.pack(expand=1)
            self.root.overrideredirect(True)

            window_width = 500
            window_height = 400
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = int(screen_width / 2 - window_width / 2)
            y = int(screen_height / 2 - window_height / 2)
            self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        def load_img(self, img):
            self.img = ImageTk.PhotoImage(img)
            self.canvas.create_image(128, 128, image=self.img)

        def show_text(self, text):
            self.loading_label.config(text=text + "……")
            self.root.update()

        def hide(self):
            self.root.withdraw()

        def stop(self):
            self.root.destroy()

    splash = SplashScreen()

    splash.show_text("加载图标")

    from arknights_mower.utils.path import get_path
    from PIL import Image, ImageTk

    logo_path = get_path("@internal/logo.png")
    tray_img = Image.open(logo_path)
    splash.load_img(tray_img)

    splash.show_text("加载配置文件")

    import sys

    from arknights_mower.utils import path

    if len(sys.argv) == 2:
        path.global_space = sys.argv[1]

    from arknights_mower.utils.conf import load_conf, save_conf

    conf = load_conf()

    token = conf["webview"]["token"]
    host = "0.0.0.0" if token else "127.0.0.1"
    width = conf["webview"]["width"]
    height = conf["webview"]["height"]

    splash.show_text("检测端口占用")

    import socket

    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            return s.connect_ex(("localhost", port)) == 0

    if token:
        port = conf["webview"]["port"]

        if is_port_in_use(port):
            splash.hide()

            from tkinter import messagebox

            messagebox.showerror(
                "arknights-mower",
                f"端口{port}已被占用，无法启动！",
            )
            splash.stop()
            sys.exit()
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            port = s.getsockname()[1]

    splash.show_text("加载Flask依赖")

    from server import app

    splash.show_text("启动Flask网页服务器")

    from threading import Thread, Event
    from time import sleep

    app.token = token
    Thread(
        target=app.run,
        kwargs={"host": host, "port": port},
        daemon=True,
    ).start()

    while not is_port_in_use(port):
        sleep(0.1)

    show_window = Event()
    show_window.set()
    running = Event()
    running.set()

    if conf["webview"]["tray"]:

        def start_tray(queue: mp.Queue):
            from pystray import Icon, Menu, MenuItem

            title = (
                f"mower@{port}({path.global_space})"
                if path.global_space
                else f"mower@{port}"
            )

            icon = Icon(
                name="arknights-mower",
                icon=tray_img,
                menu=Menu(
                    MenuItem(
                        text="打开/关闭窗口",
                        action=lambda: queue.put("toggle"),
                        default=True,
                    ),
                    MenuItem(
                        text="退出",
                        action=lambda: queue.put("exit"),
                    ),
                ),
                title=title,
            )
            icon.run()

        splash.show_text("加载托盘图标")
        tray_queue = mp.Queue()
        tray_process = mp.Process(target=start_tray, args=(tray_queue,), daemon=True)
        tray_process.start()

        def tray_events():
            global window
            while True:
                msg = tray_queue.get()
                if msg == "toggle":
                    if show_window.is_set():
                        show_window.clear()
                        if window:
                            window.destroy()
                            window = None
                    else:
                        show_window.set()
                elif msg == "exit":
                    running.clear()
                    if window:
                        window.destroy()

        Thread(target=tray_events, daemon=True).start()

    splash.show_text("准备主窗口")

    import webview
    from arknights_mower.__init__ import __version__

    def create_window():
        global window

        def window_size(w, h):
            global width
            global height
            width = w
            height = h

        window = webview.create_window(
            f"arknights-mower {__version__} (http://{host}:{port})",
            f"http://127.0.0.1:{port}?token={token}",
            text_select=True,
            confirm_close=not conf["webview"]["tray"],
            width=width,
            height=height,
        )
        window.events.resized += window_size

    splash.stop()

    while running.is_set():
        if show_window.wait(1):
            create_window()
            webview.start()
            show_window.clear()
            window = None
            if not conf["webview"]["tray"]:
                running.clear()

    conf = load_conf()
    conf["webview"]["width"] = width
    conf["webview"]["height"] = height
    save_conf(conf)
