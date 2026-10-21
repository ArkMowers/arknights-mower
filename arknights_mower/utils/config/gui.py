"""实例的窗口设置与界面偏好；读改写共用跨进程文件锁。"""

from threading import RLock

import yaml
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.config import atomic_write, gui_path
from arknights_mower.utils.window_shell import WindowRatio

_gui_lock = RLock()


def read_gui_data(*, strict=False) -> dict:
    if not gui_path.is_file():
        return {}
    try:
        with gui_path.open("r", encoding="utf-8") as stream:
            data = yaml.load(stream, Loader=CoreLoader)
        if data is None:
            return {}
        if not isinstance(data, dict):
            if strict:
                raise ValueError("gui.yml 必须包含配置对象")
            return {}
        return data
    except (OSError, ValueError, yaml.YAMLError):
        if strict:
            raise
        return {}


def update_gui_data(update):
    # 窗口与后端进程在锁内读取最新文件，再提交本次字段修改。
    with (
        _gui_lock,
        runtime.supervision_lock(gui_path.parent.parent / "tmp/gui-config", timeout=5),
    ):
        data = read_gui_data(strict=True)
        result = update(data)

        def dump(stream):
            yaml.dump(
                data, stream, Dumper=CoreDumper, encoding="utf-8", allow_unicode=True
            )

        atomic_write(gui_path, dump)
        return result


def _update_gui_data(**changes) -> None:
    update_gui_data(lambda data: data.update(changes))


def load_window_mode() -> str:
    mode = read_gui_data().get("window_mode")
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
        ratio = read_gui_data()["ratio"]
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


def load_close_preference() -> dict:
    value = read_gui_data().get("close_preference")
    if not isinstance(value, dict):
        return {"choice": "tray", "remember": False}
    return {
        "choice": value.get("choice")
        if value.get("choice") in ("tray", "exit")
        else "tray",
        "remember": value.get("remember") is True,
    }


def save_close_preference(choice: str, remember: bool) -> bool:
    if choice not in ("tray", "exit") or type(remember) is not bool:
        raise ValueError("Invalid close preference")
    _update_gui_data(close_preference={"choice": choice, "remember": remember})
    return True


def load_window_launch_mode() -> str:
    mode = read_gui_data().get("window_launch_mode")
    return mode if mode in ("last", "normal", "maximized") else "last"


def save_window_launch_mode(mode: str) -> bool:
    if mode not in ("last", "normal", "maximized"):
        raise ValueError("Invalid launch mode")
    _update_gui_data(window_launch_mode=mode)
    return True
