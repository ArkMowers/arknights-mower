"""T2 五项共享工具（实机脚本，不参与门禁 G1 收集）。

本模块在 `t1_common.py` 之上只加 T2 **点击类**验收需要的原语：

| 原语 | 用途 |
|---|---|
| `build_device` | `Device()` + `PCDevicePort` + `Recognizer` + `InfraKit` 一次装好 |
| `build_state` | 构造 `SchedulerState`，全程套 `no_save_conf()`（绝不写用户 `conf.yml`） |
| `abort_on_stop_class` | `request_stop()` 后 `wait_if_paused()` 抛 `MowerExit`，把控制流从 `Navigator` 内部**硬拽出来** |
| `db_backup_t2` | `tmp/mower.db` 的 `Copy-Item` 备份 + `finally` 还原（后缀 `.t2bak`） |
| `recording_port` / `counts` | 给真机 port 记 tap/swipe/swipe_path 调用（**转发**不拦截）；`counts()` 出增量 |
| `operator_rooms` | 只读 `mower.db` 的 `operator_mood` → `{干员名: current_room}` |
| `read_room_stable` | **T2.5 核心**：连读 N 次取一致值，不一致 → INVALID |
| `room_snapshot` | 把稳定读数规整成 `[干员名或"空"]` |
| `vary_slot` | 返回"多次读数不一致"的槽位下标 |

`read_room_stable` 的自证（人造不一致必须被判 INVALID）在
`t2_5_read_confidence.py` 内实现 —— 它需要 `MockRecognizer`/`MockDevicePort`
与吊销后的假存储，属**该脚本自己的证伪对照**，不放进共享工具。

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

import threading

from tests.live.t1_common import idle_wait  # noqa: F401  (再导出：调用方常用)

# 读数层已拆分到 `t2_read.py`：这里再导出，避免调用方改动 import 来源。
from tests.live.t2_read import (  # noqa: E402,F401
    DEFAULT_STABLE_READS,
    READ_GAP_SECONDS,
    ROOM_LOG_PREFIX,
    ROOM_SCROLL_NEEDED,
    ROOM_SCROLL_PROBE,
    capture_slots,
    impossible_duplicates,
    read_room_stable,
    reset_room_scroll,
    room_snapshot,
    vary_slot,
)

# 兼容旧调用名（拆分前叫 `_capture_slots`）。
_capture_slots = capture_slots


def db_backup_t2(db_path):
    """`tmp/mower.db` 的 Copy-Item 备份 + `finally` 还原，备份名带 `.t2bak`。

    与 `t1_common.db_backup` 是同一手法，只是后缀不同（T2 规约 7 明写 `.t2bak`），
    便于跑完后 `Get-ChildItem *.t2bak` 直接验证"无残留备份"。
    """
    import shutil
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        backup = db_path.with_name(db_path.name + ".t2bak")
        existed = db_path.is_file()
        if existed:
            shutil.copy2(db_path, backup)
        try:
            yield backup
        finally:
            if backup.is_file():
                if existed:
                    shutil.copy2(backup, db_path)
                backup.unlink()

    return _ctx()


def build_device(pause):
    """装好真机链路：`Device` / `PCDevicePort` / `Recognizer` / `InfraKit`。

    返回 `(device, recognizer, infra)`。调用方后续的猴补丁必须打在返回的
    `recognizer` 上 —— 它就是 `infra.navigator._recognizer` 同一个对象。
    """
    from arknights_mower.scheduler.bootstrap import _build_infra
    from arknights_mower.utils.device.device import Device

    v1 = Device()
    infra = _build_infra(v1, None, pause)
    return infra.device, infra.navigator._recognizer, infra


def build_state():
    """构造 `SchedulerState`，全程套 `no_save_conf()`（绝不写用户 `conf.yml`）。

    返回 `(state, workshop_settings, save_conf_calls)`：第 3 项是被拦截的
    `save_conf` 调用列表，长度 0 即"未写 `conf.yml`"的直接证据。
    """
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import build_global_plan

    from tests.live.t1_common import no_save_conf

    with no_save_conf() as calls:
        from arknights_mower.scheduler.state import SchedulerState

        state = SchedulerState(global_plan=build_global_plan())
        workshop = list(getattr(config.conf, "workshop_settings", []) or [])
    return state, workshop, calls


def abort_on_stop_class():
    """返回「stop 后立刻抛 `MowerExit`」的 PauseController 子类。

    继承而非替换 `wait_if_paused` 以保留 pause 语义；`Navigator.navigate` 已
    `except MowerExit: return False`，因此墙钟到点能真正打断导航循环，
    而不是等它自己走完。
    """
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.utils.csleep import MowerExit

    class AbortOnStop(ThreadPauseController):
        def wait_if_paused(self) -> None:
            super().wait_if_paused()
            if self.is_stopped:
                raise MowerExit

    return AbortOnStop


def resettable_pause_class():
    """返回一个 **stop 可复位、且 stop 时抛 `MowerExit`** 的 PauseController 子类。

    为什么需要可复位：`ThreadPauseController.request_stop()` 置位的是**粘性**
    `_stop_event`（`thread_pause.py:28-30`，没有 `clear()`）。T2.2/T2.4 要在
    "跑任务 → `request_stop()` 让 `MainLoop` 退出"**之后**继续导航去读房间终态，
    用粘性控制器会立刻抛 `MowerExit` 把复查腿打断。

    ⚠️ 为什么必须同时保留 `MowerExit`：初版只做了"可复位"，**没有**在 stop 时
    抛 `MowerExit`，结果 `Navigator.navigate` 的 `while current != target` 循环
    无法被墙钟打断 —— T2.1 实测在 201↔224 之间空转到日志刷满
    （`tmp/t2_1_run4.log`）。安全网因此**必须**建立在"stop ⇒ 抛 `MowerExit`"之上。

    安全性：`resume_run()` **拒绝**在墙钟已到时解除 stop
    （`mark_clock_timeout()` 由安全网置位），否则安全网会被自己解除。
    """
    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
    from arknights_mower.utils.csleep import MowerExit

    class Resettable(ThreadPauseController):
        def __init__(self) -> None:
            super().__init__()
            self._clock_timed_out = threading.Event()

        def wait_if_paused(self) -> None:
            super().wait_if_paused()
            if self.is_stopped:
                raise MowerExit

        def mark_clock_timeout(self) -> None:
            """由 `WallClockStop` 的回调调用，标记"这是安全网触发的停止"。"""
            self._clock_timed_out.set()
            self.request_stop()

        @property
        def clock_timed_out(self) -> bool:
            return self._clock_timed_out.is_set()

        def resume_run(self) -> bool:
            """解除**任务级** stop；墙钟已到则拒绝并返回 `False`。"""
            if self._clock_timed_out.is_set():
                return False
            self._stop_event.clear()
            self._event.set()
            return True

    return Resettable


def recording_port(port) -> list:
    """给真机 port 挂 `tap`/`swipe`/`swipe_path` 记录器（**转发**给原实现）。

    与 T1 的 `install_tap_guard` **不同**：T2 是点击类，必须真的点，所以这里是
    记账而非拦截（`enter_room` 内部直接调 `self._device.swipe`，绕过导航层包装）。
    列表元素是 `(kind, args)`，用 `counts()` 出增量。
    """
    calls: list = []
    for name in ("tap", "swipe", "swipe_path"):
        original = getattr(port, name)

        def _make(kind: str, fn):
            def _fn(*args, **kwargs):
                calls.append((kind, args))
                return fn(*args, **kwargs)

            return _fn

        setattr(port, name, _make(name, original))
    return calls


def counts(calls: list, kind: str) -> int:
    """统计记录器里某类调用的条数。"""
    return sum(1 for k, _ in calls if k == kind)


# ──────────────────────────────────────────────────── T2.5 稳定读数（核心）


def operator_rooms(db_path) -> dict:
    """只读 `mower.db` 的 `operator_mood`，返回 `{干员名: current_room}`。

    "无半成品排班"判据的取证手段：跑任务前后各读一次，比对房间归属是否变化。
    用 `mode=ro` 打开，绝不写库。
    """
    import json
    import sqlite3

    if not db_path.exists():
        return {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select data from kv_store where key='operator_mood'"
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {}
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return {name: rec.get("current_room") for name, rec in data.items()}
