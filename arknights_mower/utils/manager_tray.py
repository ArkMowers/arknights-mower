"""One tray for the instances launched by a manager, in a dedicated GUI process."""

import sys
from threading import Event, Thread

from arknights_mower.utils import update_runtime as runtime


def manager_menu(commands):
    from pystray import Menu, MenuItem

    def action(*message):
        return lambda: commands.put(message)

    def items():
        yield MenuItem("打开多开管理器", action("show"), default=True)
        yield Menu.SEPARATOR
        records = runtime.managed_instances()
        if not records:
            yield MenuItem("暂无运行中的实例", None, enabled=False)
        for record in records:
            name = record.get("name") or "未命名实例"
            port = record.get("port") or "启动中"
            yield MenuItem(
                f"{name} @{port}",
                Menu(
                    MenuItem(
                        "打开/关闭窗口", action("instance", record["id"], "toggle")
                    ),
                    MenuItem(
                        "在浏览器中打开网页面板",
                        action("instance", record["id"], "browser"),
                    ),
                    Menu.SEPARATOR,
                    MenuItem("关闭此实例", action("instance", record["id"], "exit")),
                ),
            )
        yield Menu.SEPARATOR
        yield MenuItem("关闭所有实例", action("close_instances"), enabled=bool(records))
        yield MenuItem("关闭多开管理器", action("close_manager"))

    return Menu(items)


def start_manager_tray(commands, ready):
    from arknights_mower.utils.desktop_process import watch_parent

    watch_parent()
    from PIL import Image
    from pystray import Icon

    from arknights_mower.utils.path import get_path

    runtime.hide_macos_dock_icon()
    icon = Icon(
        "arknights-mower-manager",
        Image.open(get_path("@internal/logo.png")),
        title="Mower 多开管理器",
        menu=manager_menu(commands),
    )
    stopped = Event()

    def refresh():
        previous = None
        while not stopped.wait(1):
            current = [
                (r["id"], r.get("name"), r.get("port"))
                for r in runtime.managed_instances()
            ]
            if current != previous:
                previous = current
                if sys.platform == "darwin":
                    from PyObjCTools import AppHelper

                    AppHelper.callAfter(icon.update_menu)
                else:
                    icon.update_menu()

    def setup(icon):
        icon.visible = True
        ready.set()

    thread = Thread(target=refresh, daemon=True)
    thread.start()
    try:
        icon.run(setup)
    finally:
        stopped.set()
        thread.join(2)
