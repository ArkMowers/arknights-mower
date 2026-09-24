"""GUI 进程专属配置。

窗口几何这类只属于界面进程的设置与共享的 conf.yml 分离——父进程（调度/服务）
不读不写这里，避免两个进程同时管 conf.yml 时一方用旧值覆盖另一方的窗口尺寸，
导致重开窗口尺寸不固定。

持久化路径与原子写复用 config 模块的收敛方案：gui.yml 与其余应用配置一起落在
@app/config/，走 atomic_write，旧 @app/gui.yml 由 migrate_app_config_paths 搬进来。
"""

from threading import RLock

import yaml
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils.config import atomic_write, gui_path
from arknights_mower.utils.window_shell import WindowRatio

_gui_lock = RLock()


def _read_gui_data() -> dict:
    if not gui_path.is_file():
        return {}
    try:
        with gui_path.open("r", encoding="utf-8") as stream:
            data = yaml.load(stream, Loader=CoreLoader) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def _update_gui_data(**changes) -> None:
    # Window size and mode share the existing GUI-only file; preserve both
    # whenever either setting is saved.
    with _gui_lock:
        data = _read_gui_data()
        data.update(changes)

        def dump(stream):
            yaml.dump(
                data, stream, Dumper=CoreDumper, encoding="utf-8", allow_unicode=True
            )

        atomic_write(gui_path, dump)


def load_window_mode() -> str:
    mode = _read_gui_data().get("window_mode")
    return mode if mode in ("normal", "maximized") else "normal"


def save_window_mode(mode: str) -> None:
    if mode not in ("normal", "maximized"):
        raise ValueError("Unsupported window mode")
    _update_gui_data(window_mode=mode)


def load_window_ratio() -> WindowRatio | None:
    """读取窗口尺寸占屏幕工作区的比例（width/height 各一个 0~3 之间的数）。

    存比例而不是绝对像素：窗口大小是设备相关的配置，换电脑/换分辨率时绝对像素
    会不匹配；比例则始终按当前屏幕换算。文件缺失或内容非法返回 None。
    """
    try:
        ratio = _read_gui_data()["ratio"]
        width = float(ratio["width"])
        height = float(ratio["height"])
        if not (0 < width <= 3 and 0 < height <= 3):
            return None
        return WindowRatio(width, height)
    except (OSError, TypeError, KeyError, ValueError):
        return None


def save_window_ratio(ratio: WindowRatio) -> None:
    """写入窗口尺寸比例（调用方已消毒，非法值不进盘），走原子写。"""
    _update_gui_data(ratio={"width": ratio.width, "height": ratio.height})
