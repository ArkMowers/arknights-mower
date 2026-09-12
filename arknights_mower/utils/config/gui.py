"""GUI 进程专属配置。

窗口几何这类只属于界面进程的设置与共享的 conf.yml 分离——父进程（调度/服务）
不读不写这里，避免两个进程同时管 conf.yml 时一方用旧值覆盖另一方的窗口尺寸，
导致重开窗口尺寸不固定。

持久化路径与原子写复用 config 模块的收敛方案：gui.yml 与其余应用配置一起落在
@app/config/，走 atomic_write，旧 @app/gui.yml 由 migrate_app_config_paths 搬进来。
"""

import yaml
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils.config import atomic_write, gui_path
from arknights_mower.utils.window_shell import WindowRatio


def load_window_ratio() -> WindowRatio | None:
    """读取窗口尺寸占屏幕工作区的比例（width/height 各一个 0~3 之间的数）。

    存比例而不是绝对像素：窗口大小是设备相关的配置，换电脑/换分辨率时绝对像素
    会不匹配；比例则始终按当前屏幕换算。文件缺失或内容非法返回 None。
    """
    if not gui_path.is_file():
        return None
    try:
        with gui_path.open("r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=CoreLoader) or {}
        ratio = data["ratio"]
        width = float(ratio["width"])
        height = float(ratio["height"])
        if not (0 < width <= 3 and 0 < height <= 3):
            return None
        return WindowRatio(width, height)
    except (OSError, TypeError, KeyError, ValueError):
        return None


def save_window_ratio(ratio: WindowRatio) -> None:
    """写入窗口尺寸比例（调用方已消毒，非法值不进盘），走原子写。"""
    width, height = ratio.width, ratio.height

    def dump(f):
        yaml.dump(
            {"ratio": {"width": width, "height": height}},
            f,
            Dumper=CoreDumper,
            encoding="utf-8",
            allow_unicode=True,
        )

    atomic_write(gui_path, dump)
