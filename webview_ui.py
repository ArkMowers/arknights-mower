#!/usr/bin/env python3
import multiprocessing as mp
import os
import platform
import sys
from urllib.parse import quote

# Linux 版独立包运行期需要宿主提供 GTK/WebKit2 原生库与 typelib，PyInstaller 只把
# pywebview 的 Python 依赖打进包。这份提示在窗口后端初始化失败时展示，直接给出
# 三个发行版的安装命令，避免用户对着裸 ImportError 无从下手。
_LINUX_WEBVIEW_INSTALL_HINT = (
    "Linux 版 mower 需要宿主安装 GTK/WebKit2 原生库，窗口后端无法初始化。\n\n"
    "Debian / Ubuntu：\n"
    "    sudo apt install libgtk-3-0 libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 gir1.2-gtk-3.0 gir1.2-soup-3.0\n"
    "Fedora：\n"
    "    sudo dnf install webkit2gtk4.1 gi-girepository libgtk-3\n"
    "Arch Linux：\n"
    "    sudo pacman -S webkit2gtk-4.1 gobject-introspection\n\n"
    "安装完成后重新运行 mower。更完整的说明见 README 的 Linux 打包一节。"
)


def linux_webview_backend_error() -> str | None:
    """Linux 上检查 pywebview 的窗口后端能否初始化；缺失时返回中文安装指引。"""
    if platform.system() not in ("Linux", "OpenBSD"):
        return None

    # 复刻 pywebview 5.1 guilib.initialize 的调度：PYWEBVIEW_GUI 优先，其次
    # KDE_FULL_SESSION 触发 Qt，否则默认 GTK 优先。
    requested_gui = os.environ.get("PYWEBVIEW_GUI", "").strip().lower()
    if requested_gui not in ("qt", "gtk"):
        requested_gui = "qt" if "KDE_FULL_SESSION" in os.environ else None
    candidates = (
        ["webview.platforms.qt", "webview.platforms.gtk"]
        if requested_gui == "qt"
        else ["webview.platforms.gtk", "webview.platforms.qt"]
    )
    for module in candidates:
        # GTK 后端还会因宿主缺 typelib 抛 ValueError，Qt 后端只抛 ImportError，
        # 与 guilib 的 import_gtk / import_qt 保持一致。
        errors = (
            (ImportError, ValueError) if module.endswith(".gtk") else (ImportError,)
        )
        try:
            __import__(module)
            return None  # 有一个后端可用即可，无需提示
        except errors:
            continue

    return _LINUX_WEBVIEW_INSTALL_HINT


def exit_if_webview_backend_missing():
    """Linux 上窗口后端缺失时输出安装指引并退出；其它平台直接返回。"""
    backend_error = linux_webview_backend_error()
    if backend_error is None:
        return
    print(backend_error, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("arknights-mower", backend_error)
        root.destroy()
    except Exception:
        pass  # 无显示环境（如 headless）时 stderr 已足够
    sys.exit(1)


def splash_screen(queue: mp.Queue):
    import tkinter as tk
    from tkinter.font import Font

    from PIL import Image, ImageTk

    from arknights_mower.utils.path import get_path

    root = tk.Tk()
    container = tk.Frame(root)

    logo_path = get_path("@internal/logo.png")
    img = Image.open(logo_path)
    img = ImageTk.PhotoImage(img)
    canvas = tk.Canvas(container, width=256, height=256)
    canvas.create_image(128, 128, image=img)
    canvas.pack()

    title_font = Font(size=24)
    title_label = tk.Label(
        container,
        text="arknights-mower",
        font=title_font,
    )
    title_label.pack()

    loading_label = tk.Label(container)
    loading_label.pack()

    container.pack(expand=1)
    root.overrideredirect(True)

    window_width = 500
    window_height = 400
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = int(screen_width / 2 - window_width / 2)
    y = int(screen_height / 2 - window_height / 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    def recv_msg():
        try:
            msg = queue.get(False)
            if msg["type"] == "text":
                loading_label.config(text=msg["data"] + "……")
                root.after(100, recv_msg)
            elif msg["type"] == "dialog":
                from tkinter import messagebox

                root.withdraw()
                messagebox.showerror("arknights-mower", msg["data"])
                root.destroy()
        except Exception:
            pass

    root.after(100, recv_msg)
    root.mainloop()


def build_window_title(instance_name, port):
    if instance_name:
        return f"mower@{port}({instance_name})"
    return f"mower@{port}"


def append_query_param(url, key, value):
    if not value:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={quote(value)}"


def start_tray(queue: mp.Queue, instance_name, port, url):
    from PIL import Image
    from pystray import Icon, Menu, MenuItem

    from arknights_mower.utils.path import get_path

    logo_path = get_path("@internal/logo.png")
    img = Image.open(logo_path)

    title = build_window_title(instance_name, port)

    def open_browser():
        import webbrowser

        webbrowser.open(url)

    icon = Icon(
        name="arknights-mower",
        icon=img,
        menu=Menu(
            MenuItem(
                text=title,
                action=None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem(
                text="打开/关闭窗口",
                action=lambda: queue.put("toggle"),
                default=True,
            ),
            MenuItem(
                text="在浏览器中打开网页面板",
                action=open_browser,
            ),
            Menu.SEPARATOR,
            MenuItem(
                text="退出",
                action=lambda: queue.put("exit"),
            ),
        ),
        title=title,
    )
    icon.run()


def webview_window(child_conn, global_space, instance_name, host, port, url, tray):
    import sys
    from threading import Thread

    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True

    from arknights_mower.__init__ import __version__
    from arknights_mower.utils import config, path

    path.global_space = global_space

    global width
    global height

    config.load_conf()
    width = config.conf.webview.width
    height = config.conf.webview.height

    def window_size(w, h):
        global width
        global height
        width = w
        height = h

    window = webview.create_window(
        f"arknights-mower {__version__} - {build_window_title(instance_name, port)}",
        url,
        text_select=True,
        confirm_close=not tray,
        width=width,
        height=height,
    )
    window.events.resized += window_size

    def recv_msg():
        while True:
            msg = child_conn.recv()
            if msg == "exit":
                window.confirm_close = False
                window.destroy()
                return
            if msg == "file":
                result = window.create_file_dialog(
                    dialog_type=webview.OPEN_DIALOG,
                )
            elif msg == "folder":
                result = window.create_file_dialog(
                    dialog_type=webview.FOLDER_DIALOG,
                )
            if result is None:
                result = ""
            elif not isinstance(result, str):
                if len(result) == 0:
                    result = ""
                else:
                    result = result[0]
            child_conn.send(result)

    Thread(target=recv_msg, daemon=True).start()

    try:
        webview.start()

        config.load_conf()
        config.conf.webview.width = width
        config.conf.webview.height = height
        config.save_conf()
        sys.exit()
    except Exception:
        import webbrowser

        webbrowser.open(url)


if __name__ == "__main__":
    mp.freeze_support()

    # 先检查窗口后端是否可用。Linux 独立包若宿主缺 GTK/WebKit2 原生库，在这里给出
    # 中文安装指引并退出，而不是让 webview 子进程走到裸 ImportError 后悄悄开浏览器。
    exit_if_webview_backend_missing()

    splash_queue = mp.Queue()
    splash_process = mp.Process(target=splash_screen, args=(splash_queue,), daemon=True)
    splash_process.start()

    splash_queue.put({"type": "text", "data": "加载配置文件"})

    import sys

    from arknights_mower.utils import path

    instance_name = ""
    if len(sys.argv) >= 2:
        path.global_space = sys.argv[1]
    if len(sys.argv) >= 3:
        instance_name = sys.argv[2]

    from arknights_mower.utils import config

    conf = config.conf
    tray = conf.webview.tray
    token = conf.webview.token
    host = "0.0.0.0" if token else "127.0.0.1"

    splash_queue.put({"type": "text", "data": "检测端口占用"})

    from arknights_mower.utils.network import get_new_port, is_port_in_use

    if token:
        port = conf.webview.port

        if is_port_in_use(port):
            splash_queue.put(
                {"type": "dialog", "data": f"端口{port}已被占用，无法启动！"}
            )
            sys.exit()
    else:
        port = get_new_port()

    url = f"http://127.0.0.1:{port}"
    if token:
        url += f"?token={token}"
    url = append_query_param(url, "instance_name", instance_name)

    splash_queue.put({"type": "text", "data": "加载Flask依赖"})

    from server import app

    splash_queue.put({"type": "text", "data": "启动Flask网页服务器"})

    from threading import Thread
    from time import sleep

    flask_thread = Thread(
        target=app.run,
        kwargs={"host": host, "port": port},
        daemon=True,
    )
    flask_thread.start()

    while not is_port_in_use(port):
        sleep(0.1)

    url = f"http://127.0.0.1:{port}"
    if token:
        url += f"?token={token}"
    url = append_query_param(url, "instance_name", instance_name)

    if tray:
        splash_queue.put({"type": "text", "data": "加载托盘图标"})
        tray_queue = mp.Queue()
        tray_process = mp.Process(
            target=start_tray,
            args=(tray_queue, instance_name or path.global_space, port, url),
            daemon=True,
        )
        tray_process.start()

    splash_queue.put({"type": "text", "data": "创建主窗口"})

    config.parent_conn, child_conn = mp.Pipe()
    config.webview_process = mp.Process(
        target=webview_window,
        args=(child_conn, path.global_space, instance_name, host, port, url, tray),
        daemon=True,
    )
    config.webview_process.start()

    splash_process.terminate()

    if tray:
        while True:
            msg = tray_queue.get()
            if msg == "toggle":
                if config.webview_process.is_alive():
                    config.parent_conn.send("exit")
                    if config.webview_process.join(3) is None:
                        config.webview_process.terminate()
                else:
                    config.parent_conn, child_conn = mp.Pipe()
                    config.webview_process = mp.Process(
                        target=webview_window,
                        args=(
                            child_conn,
                            path.global_space,
                            instance_name,
                            host,
                            port,
                            url,
                            tray,
                        ),
                        daemon=True,
                    )
                    config.webview_process.start()
            elif msg == "exit":
                # 退出前先让 mower 线程停止：否则 daemon 线程仍在跑 adb 操作，
                # 会占着 DroidCast/scrcpy 连接（需关模拟器才释放），且影响进程退出
                config.stop_mower.set()
                config.parent_conn.send("exit")
                if config.webview_process.join(3) is None:
                    config.webview_process.terminate()
                break
    else:
        config.webview_process.join()
