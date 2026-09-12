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

# The frozen launcher has no standalone Python, so a MAA connectivity check that
# asked for "-c <script>" would spawn a second desktop window. Route it here
# instead; the process runs the check and exits before opening any window.
if __name__ == "__main__" and sys.argv[1:2] == ["--maa-check-worker"]:
    from arknights_mower.utils.maa_check import worker_main

    worker_main(sys.argv[2])
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


def splash_screen(queue):
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


def start_tray(queue, instance_name, port, url):
    from PIL import Image
    from pystray import Icon, Menu, MenuItem

    from arknights_mower.utils.path import get_path
    from arknights_mower.utils.update_runtime import hide_macos_dock_icon

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
                text="关闭实例",
                action=lambda: queue.put("exit"),
            ),
        ),
        title=title,
    )
    icon.run()


def webview_window(
    child_conn, global_space, instance_name, host, port, url, tray, log_queue=None
):
    import sys
    from threading import Thread

    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True

    from arknights_mower.utils import path

    path.global_space = global_space

    if log_queue is not None:
        from arknights_mower.utils import log as mower_log

        mower_log.bind_mp_queue(log_queue)

    from arknights_mower.utils import config
    from arknights_mower.utils.config.gui import load_window_ratio, save_window_ratio
    from arknights_mower.utils.window_shell import (
        DESKTOP_WINDOW_MIN_SIZE,
        WindowSize,
        attach_window_shell,
        default_desktop_window_size,
        is_windows,
        ratio_from_window_size,
        window_background_color,
        window_dpi_scale,
        window_size_from_ratio,
    )

    global width
    global height

    config.load_conf()
    theme = config.conf.theme
    ratio = load_window_ratio()
    if ratio:
        width, height = window_size_from_ratio(ratio)
    else:
        width, height = default_desktop_window_size()
    # 无边框自绘标题栏是 Windows 专属：原生非客户区缩放/DPI 都依赖下面的 Win32
    # hook，其余平台沿用原生窗口。否则会得到一个既不能拖拽也不能缩放的裸窗口。
    shell_enabled = is_windows()
    url = append_query_param(url, "window_shell", "1") if shell_enabled else url
    url = append_query_param(url, "window_theme", theme)
    url = append_query_param(url, "mower_version", title_version())

    def current_dpi_scale() -> float:
        # 窗口所在显示器 DPI 缩放（1.0 / 1.25 / 1.5 ...）。resized 回调给的是物理
        # 像素，存盘前要还原成逻辑值，否则物理值会被 create_window 当作逻辑再放大
        # 一次，越开越大。每次缩放时重新探测，窗口拖到不同 DPI 的显示器也能对上。
        if not shell_enabled:
            return 1.0
        try:
            from webview.platforms import winforms

            form = winforms.BrowserView.instances.get(window.uid)
            if form is not None:
                return window_dpi_scale(int(form.Handle.ToInt64()))
        except Exception:
            pass
        return 1.0

    def window_size(w, h):
        global width
        global height
        scale = current_dpi_scale()
        logical = sanitize_window_size(round(w / scale), round(h / scale))
        if logical is not None:
            width, height = logical

    window = webview.create_window(
        window_title(instance_name, port),
        url,
        text_select=True,
        confirm_close=not tray,
        width=width,
        height=height,
        min_size=DESKTOP_WINDOW_MIN_SIZE,
        resizable=True,
        frameless=shell_enabled,
        easy_drag=False,
        shadow=True,
        background_color=window_background_color(theme),
    )
    window.events.resized += window_size
    bridge = attach_window_shell(window, initial_size=WindowSize(width, height))
    if bridge.get_platform()["platform"] == "windows":
        from arknights_mower.utils.windows_frameless import (
            install_windows_frameless_resize,
        )

        install_windows_frameless_resize(
            window,
            WindowSize(width, height),
            DESKTOP_WINDOW_MIN_SIZE,
        )

    def recv_msg():
        while True:
            try:
                msg = child_conn.recv()
            except (EOFError, OSError):
                return
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
            ratio = ratio_from_window_size(WindowSize(*size))
            if ratio is not None:
                save_window_ratio(ratio)
        sys.exit()
    except Exception:
        from arknights_mower.utils.log import logger

        logger.exception("WebView 窗口启动失败，回退为浏览器打开")
        import webbrowser

        webbrowser.open(url)


def close_child(process, connection=None):
    """Reap auxiliary processes when their windows or tray close."""
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


def start_desktop_child(kind, *args, log_queue=None):
    if sys.platform == "darwin":
        from arknights_mower.utils.desktop_process import start_worker

        if log_queue is not None:
            return start_worker(kind, *args, log_queue=log_queue)
        return start_worker(kind, *args)
    target = {
        "splash": splash_screen,
        "tray": start_tray,
        "window": webview_window,
    }[kind]
    if kind == "window":
        parent, child = mp.Pipe()
        args = (*args, log_queue)
    else:
        parent = child = mp.Queue()
    process = mp.Process(target=target, args=(child, *args), daemon=True)
    process.start()
    if kind == "window":
        child.close()
    return process, parent


def background_requested():
    return os.environ.get("MOWER_BACKGROUND") == "1"


def run_desktop():
    from queue import Empty
    from threading import Thread
    from time import monotonic, sleep

    from arknights_mower.utils import path
    from arknights_mower.utils import update_runtime as runtime

    owner = runtime.read_json(runtime.state_dir() / "active/owner.json", {})
    if runtime.active_job() and os.environ.get("MOWER_RESTART_JOB") != owner.get("id"):
        sys.exit("软件更新或进程操作正在进行，请等待完成后启动 Mower")
    background = background_requested()
    managed = os.environ.get("MOWER_MANAGED") == "1"
    manager_owned = managed
    exit_if_webview_backend_missing()
    space = sys.argv[1] if len(sys.argv) >= 2 else None
    if space is not None and space.startswith("-"):
        # A CLI option (e.g. "-c") reached us via argv rather than a config-space
        # name. Spaces are always a filesystem path or data-dir label, which can
        # never start with "-" (Windows drive letter / POSIX "/"), so treat it as
        # absent instead of resolving "@app/..." under an "install/-c" directory.
        space = None
    path.global_space = space
    instance_name = sys.argv[2] if len(sys.argv) >= 3 else ""
    from arknights_mower.utils.log import init_file_logging, start_mp_listener

    # 文件日志只由主进程建立。子进程（webview_window 等）不调用 init_file_logging，
    # 否则它们经 title_version→resource_version import log.py 时会各自打开
    # runtime.log，Windows 上整点切换日志文件（os.rename 需独占）就会因多进程同时持有而失败。
    init_file_logging()
    splash_queue = None
    splash_process = None
    tray_process = None
    registration = runtime.RuntimeRegistration(
        "instance", space=path.global_space, name=instance_name
    )
    if not background:
        splash_process, splash_queue = start_desktop_child("splash")
        splash_queue.put({"type": "text", "data": "加载配置文件"})
    from arknights_mower.utils import config
    from arknights_mower.utils.network import get_new_port, is_port_in_use

    conf = config.conf
    tray = conf.webview.tray or background or managed
    keep_running = tray or sys.platform == "darwin"
    # Keep the single file writer on every platform. macOS uses a pipe instead
    # of shared semaphores so closing GUI helpers leaves no resource tracker.
    log_listener = None
    mp_log_queue = None
    if not background or tray:
        if sys.platform == "darwin":
            from arknights_mower.utils.desktop_process import log_channel

            mp_log_queue = log_channel()
        else:
            mp_log_queue = mp.Queue()
        start_mp_listener(mp_log_queue)
        from arknights_mower.utils import log as mower_log

        log_listener = mower_log.mp_listener
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
    if splash_queue is not None:
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
    tray_queue = None
    tray_retry_at = 0

    def close_tray():
        nonlocal tray_process, tray_queue
        close_child(tray_process)
        if tray_queue is not None:
            tray_queue.close()
        tray_process = None
        tray_queue = None

    def ensure_tray():
        nonlocal tray_process, tray_queue, tray_retry_at
        if tray_process is not None and tray_process.is_alive():
            return
        close_tray()
        if monotonic() < tray_retry_at:
            return
        # A missing desktop backend must not cause a rapid restart loop.
        tray_retry_at = monotonic() + 5
        try:
            tray_process, tray_queue = start_desktop_child(
                "tray", instance_name or path.global_space, port, url
            )
        except OSError:
            from arknights_mower.utils.log import logger

            logger.exception("托盘启动失败，实例继续运行，稍后重试")

    if tray and not managed:
        ensure_tray()

    def open_window():
        close_child(config.webview_process)
        if config.parent_conn is not None:
            config.parent_conn.close()
        config.webview_process, config.parent_conn = start_desktop_child(
            "window",
            path.global_space,
            instance_name,
            host,
            port,
            url,
            keep_running,
            log_queue=mp_log_queue,
        )

    config.webview_process = None
    config.parent_conn = None
    if not background:
        open_window()
    close_child(splash_process)

    from arknights_mower.utils.software_update import request_auto_check

    request_auto_check()

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
    manager_missing_since = None
    try:
        while True:
            if registration.shutdown_requested():
                if (
                    server._job_running(server.maa_update_job)
                    or server._job_running(server.maa_resource_update_job)
                    or server.resource_update.running()
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
            if manager_owned:
                if runtime.unified_managers():
                    manager_missing_since = None
                    if not managed:
                        close_tray()
                        managed = True
                elif manager_missing_since is None:
                    manager_missing_since = monotonic()
                elif managed and monotonic() - manager_missing_since >= 5:
                    # A closed or crashed manager must not strand an instance.
                    managed = False
            if tray and not managed:
                ensure_tray()
            messages = registration.take_commands() if manager_owned else []
            if tray_queue is not None:
                try:
                    messages.append(tray_queue.get(timeout=0.5))
                except Empty:
                    pass
                except (EOFError, OSError):
                    # A tray crash is not a user's request to close the instance.
                    close_tray()
                    tray_retry_at = monotonic() + 5
            else:
                sleep(0.5)
            for msg in messages:
                if msg == "toggle":
                    if config.webview_process and config.webview_process.is_alive():
                        close_child(config.webview_process, config.parent_conn)
                    else:
                        open_window()
                elif msg == "browser":
                    import webbrowser

                    webbrowser.open(url)
            if "exit" in messages:
                break
    finally:
        config.stop_mower.set()
        close_child(config.webview_process, getattr(config, "parent_conn", None))
        close_tray()
        if config.parent_conn is not None:
            config.parent_conn.close()
            config.parent_conn = None
        if log_listener is not None:
            log_listener.stop()
        if mp_log_queue is not None:
            mp_log_queue.close()
        registration.close()


if __name__ == "__main__":
    mp.freeze_support()
    if sys.argv[1:2] == ["--desktop-worker"]:
        from arknights_mower.utils.desktop_process import run_worker

        target = {
            "splash": splash_screen,
            "tray": start_tray,
            "window": webview_window,
        }[sys.argv[2]]
        run_worker(target, *sys.argv[3:])
    else:
        run_desktop()
