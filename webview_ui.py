#!/usr/bin/env python3
import multiprocessing as mp
import os
import platform
import sys
from urllib.parse import quote

if __name__ == "__main__" and sys.argv[1:2] == ["--process-control-worker"]:
    from arknights_mower.utils.process_control import worker_main

    worker_main(sys.argv[2])
    sys.exit()

# The copied frozen updater must run before importing Flask, config or any GUI.
if __name__ == "__main__" and sys.argv[1:2] == ["--software-update-worker"]:
    from arknights_mower.utils.software_update_worker import main as update_main

    update_main(sys.argv[2])
    sys.exit()

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


# 托盘开关窗口是杀进程重建（见 webview_window / start_tray），新窗口尺寸读
# gui.yml。Windows WebView2 在窗口初始化/销毁路径会触发极小/零尺寸 resized，
# 若当成立即写回配置，下次打开就缩成一团——下限钳制挡住这些残留事件。
MIN_WINDOW_SIZE = 100
# 仅在 gui.yml 缺失或内容损坏（极小/零/非数字）时兜底，避免坏尺寸被读进创建
# 并再次持久化。窗口尺寸唯一落在 GUI 进程专属的 gui.yml，不再进共享的 conf.yml。
DEFAULT_WINDOW_SIZE = (1450, 850)


def sanitize_window_size(width, height, min_size=MIN_WINDOW_SIZE):
    """返回合法的窗口尺寸；极小/零/非数字视为销毁路径的残留事件，返回 None。"""
    try:
        w = int(width)
        h = int(height)
    except (TypeError, ValueError, OverflowError):
        return None
    if w < min_size or h < min_size:
        return None
    return (w, h)


def resolve_window_size(width, height, min_size=MIN_WINDOW_SIZE):
    """校验并返回合法的初始尺寸；损坏（极小/零/非数字）时兜底到默认启动尺寸。"""
    return sanitize_window_size(width, height, min_size) or DEFAULT_WINDOW_SIZE


def splash_screen(queue: mp.Queue):
    import tkinter as tk
    from tkinter.font import Font

    from PIL import Image, ImageTk

    from arknights_mower.utils.path import get_path

    root = tk.Tk()
    from arknights_mower.utils.update_runtime import frozen, hide_macos_dock_icon

    if not frozen():
        hide_macos_dock_icon()
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


def title_version(resource_version=None):
    """窗口标题里的版本串：软件版本后追加资源包版本号（尽力读取，失败只显示软件版本）。"""
    from arknights_mower.__init__ import __version__

    if resource_version is None:
        try:
            from arknights_mower.utils.resource_version import check_resource_update

            resource_version = (
                check_resource_update(local_only=True).get("current_display") or ""
            )
        except Exception:
            resource_version = ""
    if resource_version:
        return f"{__version__} - {resource_version}"
    return __version__


def window_title(instance_name, port, resource_version=None):
    """完整窗口标题：应用版本 + 资源包版本（若有）+ 实例标识。"""
    return f"arknights-mower {title_version(resource_version)} - {build_window_title(instance_name, port)}"


def append_query_param(url, key, value):
    if not value:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={quote(value)}"


def start_tray(queue: mp.Queue, instance_name, port, url):
    from PIL import Image
    from pystray import Icon, Menu, MenuItem

    from arknights_mower.utils.path import get_path
    from arknights_mower.utils.update_runtime import frozen, hide_macos_dock_icon

    if background_requested() or not frozen():
        hide_macos_dock_icon()

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

    from arknights_mower.utils import path

    path.global_space = global_space

    from arknights_mower.utils.config.gui import load_window_size, save_window_size

    global width
    global height

    size = load_window_size()
    width, height = resolve_window_size(*size) if size else DEFAULT_WINDOW_SIZE

    def window_size(w, h):
        global width
        global height
        size = sanitize_window_size(w, h)
        if size is not None:
            width, height = size

    window = webview.create_window(
        window_title(instance_name, port),
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
            if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "title":
                window.set_title(window_title(instance_name, port, msg[1]))
                continue
            if msg == "title":
                window.set_title(window_title(instance_name, port))
                continue
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

        size = sanitize_window_size(width, height)
        if size is not None:
            save_window_size(size)
        sys.exit()
    except Exception:
        from arknights_mower.utils.log import logger

        logger.exception("WebView 窗口启动失败，回退为浏览器打开")
        import webbrowser

        webbrowser.open(url)


def close_child(process, connection=None):
    """Reap auxiliary processes so closing a window leaves no Python Dock tile."""
    if process is None or process.pid is None:
        return
    if process.is_alive() and connection is not None:
        try:
            connection.send("exit")
        except (BrokenPipeError, OSError):
            pass
        process.join(3)
    if process.is_alive():
        process.terminate()
    process.join(3)
    if process.is_alive():
        process.kill()
        process.join(3)


def background_requested():
    return os.environ.get("MOWER_BACKGROUND") == "1"


def run_desktop():
    from queue import Empty, Queue
    from threading import Thread
    from time import sleep

    from arknights_mower.utils import path
    from arknights_mower.utils import update_runtime as runtime

    owner = runtime.read_json(runtime.state_dir() / "active/owner.json", {})
    if runtime.active_job() and os.environ.get("MOWER_RESTART_JOB") != owner.get("id"):
        sys.exit("软件更新或进程操作正在进行，请等待完成后启动 Mower")
    background = background_requested()
    if background or not runtime.frozen():
        runtime.hide_macos_dock_icon()
    exit_if_webview_backend_missing()
    path.global_space = sys.argv[1] if len(sys.argv) >= 2 else None
    instance_name = sys.argv[2] if len(sys.argv) >= 3 else ""
    splash_queue = Queue() if background else mp.Queue()
    splash_process = None
    tray_process = None
    registration = runtime.RuntimeRegistration(
        "instance", space=path.global_space, name=instance_name
    )
    if not background:
        splash_process = mp.Process(
            target=splash_screen, args=(splash_queue,), daemon=True
        )
        splash_process.start()
    splash_queue.put({"type": "text", "data": "加载配置文件"})
    from arknights_mower.utils import config
    from arknights_mower.utils.network import get_new_port, is_port_in_use

    conf = config.conf
    tray = conf.webview.tray or (background and sys.platform != "darwin")
    keep_running = tray or background or sys.platform == "darwin"
    token = conf.webview.token
    host = "0.0.0.0" if token else "127.0.0.1"
    restart_port = os.environ.get("MOWER_RESTART_PORT", "")
    port = (
        int(restart_port)
        if restart_port
        else (conf.webview.port if token else get_new_port())
    )
    if is_port_in_use(port):
        close_child(splash_process)
        registration.close()
        raise RuntimeError(f"端口{port}已被占用，无法启动！")
    from hashlib import sha256

    registration.record.update(
        port=port,
        listen_host=host,
        token_hash=sha256((token or "").encode()).hexdigest(),
    )
    registration.publish()
    splash_queue.put({"type": "text", "data": "加载 Flask 依赖"})
    import server

    registration.running = lambda: bool(
        server.mower_thread and server.mower_thread.is_alive()
    )
    url = f"http://127.0.0.1:{port}"
    if token:
        url += f"?token={token}"
    url = append_query_param(url, "instance_name", instance_name)
    Thread(
        target=server.app.run, kwargs={"host": host, "port": port}, daemon=True
    ).start()
    while not is_port_in_use(port):
        sleep(0.1)
    registration.record["ready"] = True
    registration.publish()
    tray_queue = mp.Queue() if tray else Queue()
    if tray:
        tray_process = mp.Process(
            target=start_tray,
            args=(tray_queue, instance_name or path.global_space, port, url),
            daemon=True,
        )
        tray_process.start()

    def open_window():
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
                keep_running,
            ),
            daemon=True,
        )
        config.webview_process.start()

    config.webview_process = None
    config.parent_conn = None
    if not background:
        open_window()
    close_child(splash_process)

    from arknights_mower.utils.software_update import check_on_launch

    Thread(target=check_on_launch, daemon=True).start()

    def resume_after_update():
        while runtime.active_job() and not registration.shutdown_requested():
            sleep(0.5)
        if registration.shutdown_requested():
            return
        with server.app.test_request_context(headers={"token": token or ""}):
            server.start("2" if os.environ.get("MOWER_RESTART_JOB") else "0")

    resume = (
        os.environ.get("MOWER_RESUME_RUN") == "1"
        if os.environ.get("MOWER_RESTART_JOB")
        else background and conf.start_automatically
    )
    if resume:
        Thread(target=resume_after_update, daemon=True).start()
    try:
        while True:
            if registration.shutdown_requested():
                if server._job_running(server.maa_update_job) or server._job_running(
                    server.maa_resource_update_job
                ):
                    sleep(0.5)
                    continue
                with server.app.test_request_context(headers={"token": token or ""}):
                    stopped = server.stop() == "true"
                if stopped and registration.shutdown_requested():
                    break
            if config.webview_process and not config.webview_process.is_alive():
                close_child(config.webview_process)
                config.webview_process = None
                if config.parent_conn is not None:
                    config.parent_conn.close()
                    config.parent_conn = None
                if not keep_running:
                    break
            if not tray:
                sleep(0.5)
                continue
            try:
                msg = tray_queue.get(timeout=0.5)
            except Empty:
                continue
            if msg == "toggle":
                if config.webview_process and config.webview_process.is_alive():
                    close_child(config.webview_process, config.parent_conn)
                else:
                    open_window()
            elif msg == "exit":
                break
    finally:
        config.stop_mower.set()
        close_child(config.webview_process, getattr(config, "parent_conn", None))
        close_child(tray_process)
        registration.close()


if __name__ == "__main__":
    mp.freeze_support()
    run_desktop()
