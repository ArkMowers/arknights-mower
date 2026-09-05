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


def load_window_size():
    """读取窗口尺寸；文件缺失或内容非法时返回 None，由调用方兜底默认值。"""
    if not gui_path.is_file():
        return None
    try:
        with gui_path.open("r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=CoreLoader) or {}
        return (int(data["width"]), int(data["height"]))
    except (OSError, TypeError, KeyError, ValueError):
        return None


def save_window_size(size):
    """写入窗口尺寸（调用方已消毒，保证非法尺寸不进盘）。"""
    width, height = size

    def dump(f):
        yaml.dump(
            {"width": width, "height": height},
            f,
            Dumper=CoreDumper,
            encoding="utf-8",
            allow_unicode=True,
        )

    atomic_write(gui_path, dump)
