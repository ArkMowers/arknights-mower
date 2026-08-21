import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from queue import Queue
from threading import Event
from typing import Any, Optional

import requests
import yaml
from pydantic import BaseModel
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.path import get_path

logger = logging.getLogger(__name__)

# 应用配置文件统一收敛到 @app/config/。老路径（@app/xxx）由 migrate_app_config_paths
# 在启动时搬一次——不搬会静默生成默认配置、把老配置弄丢。
conf_path = get_path("@app/config/conf.yml")
plan_path = get_path("@app/config/plan.json")
app_state_path = get_path("@app/config/state.json")
weekly_plans_path = get_path("@app/config/weekly_plans.yml")

_LEGACY_CONF_PATH = get_path("@app/conf.yml")
_LEGACY_PLAN_PATH = get_path("@app/plan.json")
_LEGACY_APP_STATE_PATH = get_path("@app/state.json")
_LEGACY_WEEKLY_PLANS_PATH = get_path("@app/weekly_plans.yml")

_CONFIG_PATH_PAIRS = (
    (_LEGACY_CONF_PATH, conf_path),
    (_LEGACY_PLAN_PATH, plan_path),
    (_LEGACY_APP_STATE_PATH, app_state_path),
    (_LEGACY_WEEKLY_PLANS_PATH, weekly_plans_path),
)


_ATOMIC_WRITE_LOCKS = {}
_ATOMIC_WRITE_LOCKS_GUARD = threading.Lock()


def _path_write_lock(path):
    key = os.path.normcase(str(path))
    with _ATOMIC_WRITE_LOCKS_GUARD:
        return _ATOMIC_WRITE_LOCKS.setdefault(key, threading.Lock())


def atomic_write(path, writer, replace_retries=3):
    """writer(f) 写入 path：先写同目录临时文件再 os.replace，读方永远看不到半截文件。

    web/调度线程可能并发写同一文件（如 cultivate.json）——每路径锁串行化写方；
    Windows 上读方持句柄时 os.replace 会瞬时 PermissionError，重试顶过去。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with _path_write_lock(path):
        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        )
        try:
            with temporary as f:
                writer(f)
            for attempt in range(replace_retries):
                try:
                    os.replace(temporary.name, path)
                    break
                except PermissionError:
                    if attempt == replace_retries - 1:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            try:
                os.unlink(temporary.name)
            except FileNotFoundError:
                pass


def migrate_app_config_paths():
    """新路径缺失且旧路径存在 → os.replace 搬过去；两边都在 → 不动。

    os.replace 失败（Windows 上 AV/另一进程瞬时锁住旧文件，或双进程并发首次迁移
    的 TOCTOU）时记 warning 跳过——旧文件保留在旧路径，不拖垮整个启动。
    """
    for old, new in _CONFIG_PATH_PAIRS:
        if new.exists() or not old.exists():
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, new)
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("迁移配置 %s → %s 失败，保留旧文件：%s", old, new, exc)


migrate_app_config_paths()


def save_conf():
    def dump(f):
        yaml.dump(
            conf.model_dump(),
            f,
            Dumper=CoreDumper,
            encoding="utf-8",
            default_flow_style=False,
            allow_unicode=True,
        )

    atomic_write(conf_path, dump)


def load_conf():
    global conf
    if not conf_path.is_file():
        conf_path.parent.mkdir(exist_ok=True)
        conf = Conf()
        save_conf()
        return
    with conf_path.open("r", encoding="utf-8") as f:
        conf = Conf(**yaml.load(f, Loader=CoreLoader))


conf: Conf
load_conf()


def save_plan():
    def dump(f):
        json.dump(plan.model_dump(exclude_none=True), f, ensure_ascii=False, indent=2)

    atomic_write(plan_path, dump)


def load_plan():
    global plan
    if not plan_path.is_file():
        plan_path.parent.mkdir(exist_ok=True)
        plan = PlanModel()
        save_plan()
        return
    with plan_path.open("r", encoding="utf-8") as f:
        plan = PlanModel(**json.load(f))


plan: PlanModel
load_plan()


stop_mower = Event()
stop_maa = Event()
# #141：一键专精建计划后唤醒调度休眠（web 线程 set，_idle_sleep 轮询检查清掉）
wake_scheduler = Event()

# 日志
log_queue = Queue()
wh = None


class DroidCast(BaseModel):
    session: Any = requests.Session()
    port: int = 0
    process: Any = None


droidcast = DroidCast()

screenshot_time: datetime = datetime.now() - timedelta(
    milliseconds=conf.screenshot_interval
)
screenshot_avg: Optional[int] = None
screenshot_count: int = 0


# 常量
APP_ACTIVITY_NAME = "com.u8.sdk.U8UnityContext"
MAX_RETRYTIME = 5
MNT_COMPATIBILITY_MODE = False
MNT_PORT = 20937
