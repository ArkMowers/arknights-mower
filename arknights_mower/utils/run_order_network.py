"""按近期网络等待为单次跑单计算临时确认时间。"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps

from arknights_mower.utils.network_adaptation import (
    SlowNetworkEvent,
    get_network_adaptation,
)
from arknights_mower.utils.scheduler_task import TaskTypes, blocked_run_order_ids


@dataclass
class RunOrderNetworkTiming:
    base_time: datetime
    applied_time: datetime
    entry_seconds: float
    buffer_seconds: float
    event: SlowNetworkEvent
    started: bool = False


def _enabled(task, conf):
    return (
        getattr(conf, "run_order_network_adaptive", False)
        and conf.run_order_buffer_time > 0
        and task.type == TaskTypes.RUN_ORDER
        and bool(task.meta_data)
        and not task.adjusted
    )


def _timing(task):
    timing = getattr(task, "run_order_network_timing", None)
    return timing if isinstance(timing, RunOrderNetworkTiming) else None


def run_order_entry_seconds(task, conf):
    timing = _timing(task)
    if timing is not None and (timing.started or _enabled(task, conf)):
        return timing.entry_seconds
    return conf.run_order_delay * 60


def run_order_buffer_seconds(task, conf):
    timing = _timing(task)
    if timing is not None and (timing.started or _enabled(task, conf)):
        return timing.buffer_seconds
    return conf.run_order_buffer_time


def run_order_network_allowance(task):
    timing = _timing(task)
    return (
        timing.event.compensation_seconds
        if timing is not None and timing.started
        else 0
    )


def refresh_run_order_network(tasks, owner, conf, now, *, op_data=None):
    """只预览最近一单，重复规划不消费记录，也不累计提前任务。"""
    candidates = []
    blocked = blocked_run_order_ids(tasks, op_data)
    for task in tasks:
        timing = _timing(task)
        if timing is not None:
            if timing.started or task.retains_execution:
                continue
            # 无人机或维护流程另行调整过时间时，沿用其新截止时间。
            if task.time != timing.applied_time or task.adjusted:
                del task.run_order_network_timing
                timing = None
            else:
                task.time = timing.base_time
                del task.run_order_network_timing
        if (
            _enabled(task, conf)
            and id(task) not in blocked
            and not getattr(task, "run_order_restore_pending", False)
            and not task.retains_execution
        ):
            candidates.append(task)
    if not candidates or not getattr(conf, "run_order_network_adaptive", False):
        return
    task = min(candidates, key=lambda item: item.time)
    if task.time - now > timedelta(minutes=15):
        return
    event = get_network_adaptation(owner).peek_run_order(
        now, base_seconds=conf.run_order_buffer_time
    )
    if event is None:
        return
    base_entry = conf.run_order_delay * 60
    buffer_seconds = conf.run_order_buffer_time + event.compensation_seconds
    # 确认提前后仍给进站、选人保留现有调度使用的45秒操作窗口。
    entry_seconds = max(base_entry, buffer_seconds + 45)
    base_time = task.time
    applied_time = base_time + timedelta(seconds=base_entry - entry_seconds)
    task.run_order_network_timing = RunOrderNetworkTiming(
        base_time, applied_time, entry_seconds, buffer_seconds, event
    )
    task.time = applied_time


def begin_run_order_network(task, owner, conf, now):
    timing = _timing(task)
    if timing is not None and timing.started:
        return timing
    refresh_run_order_network([task], owner, conf, now)
    timing = _timing(task)
    if task.retains_execution and _enabled(task, conf):
        # 未开始的保留任务按当前基础设置重新选取补偿，失败时间保持不变。
        event = get_network_adaptation(owner).peek_run_order(
            now, base_seconds=conf.run_order_buffer_time
        )
        if event is not None:
            buffer_seconds = conf.run_order_buffer_time + event.compensation_seconds
            timing = RunOrderNetworkTiming(
                task.time,
                task.time,
                max(conf.run_order_delay * 60, buffer_seconds + 45),
                buffer_seconds,
                event,
            )
            task.run_order_network_timing = timing
    if timing is None:
        return None
    event = get_network_adaptation(owner).take_run_order(
        now,
        event_id=timing.event.event_id,
        base_seconds=conf.run_order_buffer_time,
    )
    if event is None:
        if not task.retains_execution:
            task.time = timing.base_time
        del task.run_order_network_timing
        return None
    timing.started = True
    from arknights_mower.utils.log import logger

    logger.info(
        "近15分钟内出现过网络卡顿，本次 %s 跑单的葛朗台缓冲时间由%s秒增加至%s秒。",
        task.meta_data,
        f"{conf.run_order_buffer_time:g}",
        f"{timing.buffer_seconds:g}",
    )
    return timing


@contextmanager
def _network_scope(solver):
    from arknights_mower.utils import config

    task = solver.task
    if (
        not _enabled(task, config.conf)
        or getattr(task, "run_order_restore_pending", False)
        or id(task) in blocked_run_order_ids(solver.tasks, solver.op_data)
    ):
        yield
        return
    timing = begin_run_order_network(task, solver.recog, config.conf, datetime.now())
    previous = solver.recog.__dict__.get("_run_order_network_compensation")
    previous_active = solver.recog.__dict__.get("_run_order_network_active")
    solver.recog._run_order_network_active = True
    solver.recog._run_order_network_compensation = (
        timing.event.compensation_seconds if timing is not None else 0
    )
    try:
        yield
    finally:
        if (
            task.plan
            and not getattr(task, "run_order_restore_pending", False)
            and not hasattr(task, "run_order_original_roster")
            and not getattr(task, "mood_physical_started", False)
        ):
            # 原班准入失败未开始换人；保留失败时间，不长期冻结过期补偿。
            task.__dict__.pop("run_order_network_timing", None)
        if previous is None:
            solver.recog.__dict__.pop("_run_order_network_compensation", None)
        else:
            solver.recog._run_order_network_compensation = previous
        if previous_active is None:
            solver.recog.__dict__.pop("_run_order_network_active", None)
        else:
            solver.recog._run_order_network_active = previous_active


def with_run_order_network(method):
    @wraps(method)
    def wrapped(solver, *args, **kwargs):
        with _network_scope(solver):
            return method(solver, *args, **kwargs)

    return wrapped
