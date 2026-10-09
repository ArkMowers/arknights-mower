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

from arknights_mower import __system__
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan import (
    PlanModel,
    has_retired_dorm_options,
    migrate_legacy_dorm_order,
    retire_rescue_backups,
)
from arknights_mower.utils.network_settings import apply_http_proxy
from arknights_mower.utils.path import get_path
from arknights_mower.utils.riic_layout import RIGHT_SIDE_ROOM_ORDERS

apply_http_proxy()

logger = logging.getLogger(__name__)

# 应用配置文件统一收敛到 @app/config/。老路径（@app/xxx）由 migrate_app_config_paths
# 在启动时搬一次——不搬会静默生成默认配置、把老配置弄丢。
conf_path = get_path("@app/config/conf.yml")
plan_path = get_path("@app/config/plan.json")
app_state_path = get_path("@app/config/state.json")
weekly_plans_path = get_path("@app/config/weekly_plans.yml")
gui_path = get_path("@app/config/gui.yml")

_LEGACY_CONF_PATH = get_path("@app/conf.yml")
_LEGACY_PLAN_PATH = get_path("@app/plan.json")
_LEGACY_APP_STATE_PATH = get_path("@app/state.json")
_LEGACY_WEEKLY_PLANS_PATH = get_path("@app/weekly_plans.yml")
_LEGACY_GUI_PATH = get_path("@app/gui.yml")

_CONFIG_PATH_PAIRS = (
    (_LEGACY_CONF_PATH, conf_path),
    (_LEGACY_PLAN_PATH, plan_path),
    (_LEGACY_APP_STATE_PATH, app_state_path),
    (_LEGACY_WEEKLY_PLANS_PATH, weekly_plans_path),
    (_LEGACY_GUI_PATH, gui_path),
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
    的 TOCTOU）时检查目标是否已由另一进程迁移；否则中止启动，防止生成默认配置遮蔽旧文件。
    """
    for old, new in _CONFIG_PATH_PAIRS:
        if new.exists() or not old.exists():
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, new)
        except (FileNotFoundError, PermissionError) as exc:
            if not new.is_file():
                raise OSError(
                    f"迁移配置 {old} → {new} 失败；已停止启动以保留原配置，请检查目录权限或文件占用"
                ) from exc
            logger.info("配置已由另一进程迁移：%s", new)


migrate_app_config_paths()


def save_conf():
    conf.sync_legacy_device_fields()

    def dump(f):
        yaml.dump(
            conf.model_dump(exclude_unset=True),
            f,
            Dumper=CoreDumper,
            encoding="utf-8",
            default_flow_style=False,
            allow_unicode=True,
        )

    atomic_write(conf_path, dump)


_legacy_dorm_order = ""
_retired_dorm_conf = False
operation_feedback_avg: Optional[float] = None
operation_feedback_count: int = 0
operation_feedback_mode: Optional[str] = None
operation_feedback_cap: Optional[str] = None
operation_failure_streak: int = 0
operation_recovery_successes: int = 0


def load_conf():
    """读取全局配置，暂存旧全局宿舍顺序供排班迁移。"""
    global conf, _legacy_dorm_order, _retired_dorm_conf
    global operation_feedback_avg, operation_feedback_count, operation_feedback_mode
    global operation_feedback_cap, operation_failure_streak
    global operation_recovery_successes
    _legacy_dorm_order = ""
    _retired_dorm_conf = False
    operation_feedback_avg = None
    operation_feedback_count = 0
    operation_feedback_mode = None
    operation_feedback_cap = None
    operation_failure_streak = 0
    operation_recovery_successes = 0
    if not conf_path.is_file():
        conf_path.parent.mkdir(exist_ok=True)
        # A fresh Mac/Linux host has no chosen endpoint. Keep legacy migration
        # unchanged, but do not give new users the old MuMu default port.
        conf = (
            Conf(device={})
            if __system__ in {"darwin", "linux"}
            and os.environ.get("MOWER_ANDROID") != "1"
            else Conf()
        )
        save_conf()
        return
    with conf_path.open("r", encoding="utf-8") as f:
        # 旧键 → 新键的兼容（exipring_medicine_on_weekend）由 Conf 校验层统一处理，
        # 读文件与 /conf POST 等所有构造路径都走同一套迁移。
        raw = yaml.load(f, Loader=CoreLoader) or {}
    _legacy_dorm_order = str(raw.get("dorm_order", "") or "")
    _retired_dorm_conf = bool(
        {
            "experimental_dorm_logic",
            "refresh_backup_plan_after_mood",
            "workshop_low_priority_rest",
            "dorm_order",
        }
        & raw.keys()
    )
    order = raw.get("right_side_room_order")
    if (
        isinstance(order, list)
        and len(order) == 3
        and all(isinstance(room, str) for room in order)
        and set(order) == {"contact", "train", "recycle"}
        and tuple(order) not in RIGHT_SIDE_ROOM_ORDERS
    ):
        raw["right_side_room_order"] = [room for room in order if room != "recycle"] + [
            "recycle"
        ]
        logger.warning("旧配置的回收站位置不合法，已移回底部，请核对本机设施布局")
    conf = Conf(**raw)


conf: Conf
load_conf()


def save_plan():
    def dump(f):
        json.dump(plan.model_dump(exclude_none=True), f, ensure_ascii=False, indent=2)

    atomic_write(plan_path, dump)


def load_plan():
    global \
        plan, \
        _legacy_dorm_order, \
        _retired_dorm_conf, \
        retired_backup_indices, \
        retired_backup_migrated
    created = not plan_path.is_file()
    if created:
        plan_path.parent.mkdir(exist_ok=True)
        plan = PlanModel()
        data = {}
    else:
        # ZIP restores preserve original bytes, including an optional UTF-8 BOM.
        with plan_path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        migrated_data, retired_backup_indices = retire_rescue_backups(data)
        retired_backup_migrated = len(migrated_data.get("backup_plans", [])) != len(
            data.get("backup_plans", [])
        )
        if retired_backup_migrated:
            backup_path = plan_path.with_suffix(".pre-maa-emergency.json")
            if not backup_path.exists():
                atomic_write(
                    backup_path,
                    lambda f: json.dump(data, f, ensure_ascii=False, indent=2),
                )
            data = migrated_data
            plan = PlanModel(**data)
            save_plan()
        else:
            plan = PlanModel(**data)
    migrated = migrate_legacy_dorm_order(plan, data, _legacy_dorm_order)
    if created or migrated or has_retired_dorm_options(data):
        save_plan()
    # 排班迁移落盘后再清除旧全局字段，避免迁移中断丢失顺序。
    if _retired_dorm_conf:
        save_conf()
        _retired_dorm_conf = False


retired_backup_indices = {}
retired_backup_migrated = False
plan: PlanModel
load_plan()


stop_mower = Event()
stop_maa = Event()
# 一键专精建计划后唤醒调度休眠（web 线程 set，_idle_sleep 轮询检查清掉）
wake_scheduler = Event()
# 维护开始或大版本预备阈值生效时，退出调度器交由主循环重新检查公告。
maintenance_recheck = Event()

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
