"""Automatic process recovery using the existing saved high-level task queue."""

import copy
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arknights_mower.utils import update_runtime as runtime

_lock = threading.RLock()
_state_changed = threading.Condition(_lock)
_completed_episodes = 0
_cancelled = False
_progress = {}
RETRY_DELAYS = (2.0, 5.0, 15.0, 60.0, 300.0)


def notice_path():
    directory = os.environ.get("MOWER_SUPERVISOR_DIRECTORY")
    return Path(directory) / "recovery.json" if directory else None


def status():
    path = notice_path()
    if path is None or not path.exists():
        return {
            "active": False,
            "phase": "resolved",
            "message": "",
            "automatic": False,
            "attempt": 0,
            "next_retry_at": None,
        }
    value = runtime.read_json(path)
    if not isinstance(value, dict) or type(value.get("active")) is not bool:
        value = {
            "active": True,
            "phase": "waiting",
            "message": "进程恢复记录暂时无法读取；保留原记录，后台稍后重新检查。",
        }
    with _lock:
        automatic = (
            value["active"]
            and value.get(
                "resume_requested", os.environ.get("MOWER_RECOVERY_RUN") != "0"
            )
            and not _cancelled
        )
        result = {
            "attempt": 0,
            "next_retry_at": None,
            **value,
            "automatic": bool(automatic),
        }
        if result["active"]:
            result.update(_progress)
            if not automatic:
                result.update(
                    phase="stopped",
                    message="任务已停止，后台不会自动启动任务。",
                    next_retry_at=None,
                )
        return result


def _update(**values):
    path = notice_path()
    if path is None:
        raise RuntimeError("当前实例没有独立进程监督记录")
    with _lock:
        raw = runtime.read_json(path)
        if not isinstance(raw, dict) or type(raw.get("active")) is not bool:
            raise RuntimeError("进程恢复记录暂时无法读取，保留原记录等待重试")
        if not raw["active"]:
            raise RuntimeError("当前实例没有待恢复的进程故障")
        raw.update(values)
        runtime.write_json(path, raw, sync=True)
        _progress.clear()


def begin():
    if not status().get("automatic"):
        raise RuntimeError("自动恢复已被停止")
    _update(
        phase="observing",
        next_retry_at=None,
        message="正在重新观察设备、驻员和心情；保存检查点后按所选启动方式继续调度。",
    )


def failed(message="设备观察或恢复尚未完成；后台退避后自动重试。", **values):
    path = notice_path()
    raw = runtime.read_json(path) if path is not None else None
    if isinstance(raw, dict) and raw.get("active") is True:
        _update(phase="waiting", message=message, **values)
    else:
        with _lock:
            _progress.update(phase="waiting", message=message, **values)


def snapshot_failed():
    failed("已保存任务状态暂时无法完整读取；保留原缓存，后台稍后重新检查。")


def cancel():
    """Stop retry intent even if its durable status report cannot be written."""
    global _cancelled
    with _lock:
        _cancelled = True
        _progress.clear()
        path = notice_path()
        raw = runtime.read_json(path) if path is not None else None
        if isinstance(raw, dict) and raw.get("active") is True:
            _update(
                resume_requested=False,
                phase="stopped",
                next_retry_at=None,
                message="任务已停止，后台不会自动启动任务。",
            )


def cancelled():
    with _lock:
        return _cancelled


def initialize_intent(wanted):
    """Resolve an unready launch from its actual startup policy, honoring Stop."""
    with _lock:
        wanted = bool(wanted) and not _cancelled
        os.environ["MOWER_RECOVERY_RUN"] = "1" if wanted else "0"
        path = notice_path()
        raw = runtime.read_json(path) if path is not None else None
        if (
            isinstance(raw, dict)
            and raw.get("active") is True
            and "resume_requested" not in raw
        ):
            _update(resume_requested=wanted)
        return wanted


def request_resume(start_type="0"):
    """An existing ordinary Start control can explicitly restore run intent."""
    global _cancelled
    with _lock:
        _cancelled = False
        if status()["active"]:
            _update(
                resume_requested=True,
                start_type=start_type,
                phase="waiting",
                message="正在重新观察设备、驻员和心情，按所选启动方式继续调度。",
            )


def activate(message):
    """A failed Python worker uses the same recovery boundary as native exit."""
    path = notice_path()
    if path is None or _cancelled:
        return
    with _lock:
        raw = runtime.read_json(path)
        if path.exists() and (
            not isinstance(raw, dict) or type(raw.get("active")) is not bool
        ):
            return
        runtime.write_json(
            path,
            {
                "active": True,
                "phase": "waiting",
                "resume_requested": True,
                "start_type": raw.get("start_type", "0")
                if isinstance(raw, dict) and raw.get("active")
                else "0",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "message": message,
                "reason": "worker_exception",
                "next_retry_at": None,
            },
            sync=True,
        )
        _progress.clear()


def complete():
    global _completed_episodes

    from arknights_mower.utils import config
    from arknights_mower.utils.csleep import MowerExit

    with _state_changed:
        if config.stop_mower.is_set() or not status().get("automatic"):
            raise MowerExit
        _update(
            active=False,
            phase="resolved",
            next_retry_at=None,
            message="设备实际状态已重新观察并保存，正在自动接续调度。",
        )
        _completed_episodes += 1
        _state_changed.notify_all()


def observe_scheduler(scheduler):
    """Invalidate old positions, observe facilities and checkpoint before reentry."""
    from arknights_mower.data import base_room_list
    from arknights_mower.solvers.record import save_current_state
    from arknights_mower.utils import config
    from arknights_mower.utils.csleep import MowerExit

    def check_cancel():
        if config.stop_mower.is_set():
            raise MowerExit

    check_cancel()
    scheduler._state_restore_complete = False
    scheduler.task = None
    scheduler.defer_backup_plan_until_mood_read = True
    for operator in scheduler.op_data.operators.values():
        operator.current_room, operator.current_index, operator.time_stamp = (
            "",
            -1,
            None,
        )
    for dorm in scheduler.op_data.all_dorms():
        dorm.reset()
    scheduler.recog.reset_after_external_control()
    scheduler.back_to_infrastructure()
    compensation_rooms = {
        room
        for task in scheduler.tasks
        for room in (
            set(task.plan)
            | set(getattr(task, "run_order_original_roster", {}))
            | set(getattr(task, "emergency_original_roster", {}))
        )
    }
    rooms = sorted(set(scheduler.op_data.plan) | compensation_rooms)
    missing = set(rooms) - set(scheduler.op_data.plan)
    if missing:
        raise RuntimeError(
            f"原班补偿房间布局暂不可读取，等待重新检查：{sorted(missing)}"
        )
    for room in (room for room in rooms if room in base_room_list):
        check_cancel()
        scheduler.enter_room(room)
        if room == "train":
            from arknights_mower.solvers.mastery_reader import read_room_state

            observed = read_room_state(scheduler, enter=False)
            if observed.read_failed:
                raise RuntimeError("训练室实际状态暂不可读取，等待重新检查")
            scheduler.train_room_state = observed
        scheduler._read_room_mood(room, force_mood=True, strict_observation=True)
        scheduler.back()
    check_cancel()
    scheduler._initial_mood_refresh_rooms = set()
    replan_dynamic_tasks(scheduler)
    refresh_workshop_inventory(scheduler)
    check_cancel()
    scheduler._state_restore_complete = True
    try:
        if not save_current_state():
            raise RuntimeError("新的设备观察暂未保存，等待重新检查")
    except BaseException:
        scheduler._state_restore_complete = False
        raise
    check_cancel()


def reconcile_scheduler(scheduler):
    observe_scheduler(scheduler)
    complete()


def replan_dynamic_tasks(scheduler):
    """Discard stale dynamic phases through existing high-level planning types."""
    from arknights_mower.data import base_room_list
    from arknights_mower.utils.scheduler_task import TaskTypes

    now = datetime.now()
    try:
        cutoff = (
            datetime.fromisoformat(scheduler._process_recovery_occurred_at)
            .astimezone()
            .replace(tzinfo=None)
        )
    except (AttributeError, TypeError, ValueError):
        cutoff = now
    for index, task in enumerate(scheduler.tasks):
        if task.retains_execution:
            continue
        if task.time > cutoff:
            continue
        if (
            task.type == TaskTypes.RUN_ORDER
            and task.meta_data in base_room_list
            and task.meta_data.startswith("room_")
            and not getattr(task, "run_order_restore_pending", False)
        ):
            replacement = copy.deepcopy(task)
            roster = getattr(task, "run_order_original_roster", None) or getattr(
                task, "emergency_original_roster", None
            )
            if roster:
                replacement.run_order_original_roster = copy.deepcopy(roster)
                replacement.run_order_restore_pending = True
                replacement.prepare_run_order_restoration()
            else:
                replacement.type = TaskTypes.REFRESH_TIME
                replacement.plan = {}
            scheduler.tasks[index] = replacement
        elif task.type == TaskTypes.FIAMMETTA and (not task.plan or task.meta_data):
            fia = scheduler.op_data.operators.get("菲亚梅塔")
            target = scheduler.op_data.operators.get(task.meta_data)
            if fia is None:
                continue
            if not task.plan and fia.current_mood() >= 24:
                continue
            if task.plan and (
                target is None
                or fia.current_mood() >= 24
                and target.current_mood() < 24
            ):
                continue
            # A saved return-phase task has empty meta_data and is retained.
            _, dorm = scheduler.op_data.get_dorm_by_name("菲亚梅塔")
            ready_at = getattr(dorm, "time", None)
            roster = getattr(task, "emergency_original_roster", None)
            observed_deadline = isinstance(ready_at, datetime)
            rooms = set(task.plan) | {
                getattr(fia, "current_room", "") or getattr(fia, "room", "")
            }
            rooms.discard("")
            if not observed_deadline and not (task.plan and roster):
                task.process_recovery_fia_wait = True
                scheduler._retain_failed_task(task, "菲亚梅塔回满时间未核实", rooms)
                continue
            replacement = copy.deepcopy(task)
            replacement.plan, replacement.meta_data = {}, ""
            replacement.initial_fia = False
            replacement.time = max(now, ready_at) if observed_deadline else task.time
            if task.plan and roster:
                returning = copy.deepcopy(task)
                returning.plan, returning.meta_data, returning.time = (
                    copy.deepcopy(roster),
                    "",
                    now,
                )
                scheduler.tasks[index] = returning
                scheduler.tasks.append(replacement)
                if not observed_deadline:
                    replacement.process_recovery_fia_wait = True
                    scheduler._retain_failed_task(
                        replacement, "菲亚梅塔回满时间未核实", rooms
                    )
            else:
                scheduler.tasks[index] = replacement


def workshop_inventory_names():
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import config
    from arknights_mower.utils.workshop_limits import recipe_quantities

    names = set()
    for setting in config.conf.workshop_settings:
        if not setting.enabled:
            continue
        for item in setting.items:
            for name in item.item_names:
                recipe = workshop_formula.get(name)
                quantities = recipe_quantities(name, recipe) if recipe else None
                if quantities is not None:
                    output, _, costs = quantities
                    names.update((output, *costs))
                    if recipe.get("goldCost"):
                        names.add("龙门币")
    return names


def refresh_workshop_inventory(scheduler):
    from arknights_mower.solvers.record import invalidate_workshop_inventory

    names = workshop_inventory_names()
    if not names:
        return
    invalidate_workshop_inventory(names)
    scheduler.仓库扫描()


def prepare_resume(saved):
    """Keep every saved task; its existing solver owns observation and reentry."""
    result = dict(saved or {})
    result["tasks"] = list(result.get("tasks", []))
    result["_process_crash_recovery"] = True
    result["_process_crash_no_snapshot"] = saved is None
    result["_process_crash_occurred_at"] = status().get("occurred_at")
    return result


class AutomaticRecovery(threading.Thread):
    """Retry recovery boundaries; ordinary Stop and shutdown cancel new attempts."""

    def __init__(self, attempt, *, running, closing, delays=RETRY_DELAYS):
        super().__init__(name="process-recovery", daemon=True)
        self.attempt, self.running, self.closing = attempt, running, closing
        self.delays = delays
        self._closing = threading.Event()

    def close(self):
        with _state_changed:
            self._closing.set()
            _state_changed.notify_all()
        if self.ident is not None:
            self.join(2)

    def run(self):
        attempts = 0
        with _lock:
            completed_episodes = _completed_episodes
        while not self._closing.is_set() and not self.closing():
            with _lock:
                current = status()
                if completed_episodes != _completed_episodes:
                    attempts = 0
                    completed_episodes = _completed_episodes
            if not current["active"]:
                attempts = 0
                self._closing.wait(0.5)
                continue
            if not current["automatic"] or self.running():
                self._closing.wait(0.2)
                continue
            if attempts:
                delay = self.delays[min(attempts - 1, len(self.delays) - 1)]
                deadline = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat()
                try:
                    failed(attempt=attempts, next_retry_at=deadline)
                except Exception:
                    with _lock:
                        _progress.update(
                            phase="waiting", attempt=attempts, next_retry_at=deadline
                        )
                with _state_changed:
                    if _state_changed.wait_for(
                        lambda: (
                            self._closing.is_set()
                            or completed_episodes != _completed_episodes
                        ),
                        timeout=delay,
                    ):
                        continue
            if self.closing() or not status().get("automatic"):
                continue
            attempts += 1
            try:
                self.attempt()
            except Exception:
                from arknights_mower.utils.log import logger

                logger.exception("自动恢复暂未完成，保留任务等待下一次尝试")
                try:
                    failed()
                except Exception:
                    pass
