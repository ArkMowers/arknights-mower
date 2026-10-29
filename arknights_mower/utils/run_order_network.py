"""按联网等待为普通葛朗台任务绑定临时确认时间。"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from math import isfinite

from arknights_mower.utils.network_adaptation import (
    MAX_COMPENSATION_SECONDS,
    SlowNetworkEvent,
    get_network_adaptation,
)
from arknights_mower.utils.scheduler_task import TaskTypes

RUN_ORDER_BINDING_WINDOW = timedelta(minutes=20)


@dataclass
class RunOrderNetworkTiming:
    base_time: datetime
    applied_time: datetime
    entry_seconds: float
    buffer_seconds: float
    event: SlowNetworkEvent
    base_entry_seconds: float
    base_buffer_seconds: float
    started: bool = False


def _grandet(task, conf):
    return (
        task is not None
        and conf.run_order_buffer_time > 0
        and task.type == TaskTypes.RUN_ORDER
        and not task.adjusted
    )


def _enabled(task, conf):
    return (
        getattr(conf, "run_order_network_adaptive", False)
        and _grandet(task, conf)
        and bool(task.meta_data)
    )


def _timing(task):
    timing = getattr(task, "run_order_network_timing", None)
    return timing if isinstance(timing, RunOrderNetworkTiming) else None


def clear_run_order_network(task, *, restore_time=True):
    """撤销未开始的临时提前，不覆盖其他流程重新实读的时间。"""
    timing = _timing(task)
    if timing is None:
        return
    if (
        restore_time
        and not timing.started
        and not task.retains_execution
        and task.time == timing.applied_time
    ):
        task.time = timing.base_time
    del task.run_order_network_timing


def finish_run_order_network(task, owner=None):
    """任务收尾或原班恢复完成后，只清理本任务的临时参数。"""
    clear_run_order_network(task, restore_time=False)
    task.__dict__.pop("run_order_network_started", None)
    if owner is not None and owner.__dict__.get("_run_order_network_task") is task:
        owner._run_order_network_active = False
        owner._run_order_network_compensation = 0


def reconcile_run_order_network(tasks, conf):
    """派发前只撤销无效的未启动绑定，不读取观测或创建绑定。"""
    for task in tasks:
        timing = _timing(task)
        if timing is None or timing.started:
            continue
        if not _enabled(task, conf) or task.time != timing.applied_time:
            clear_run_order_network(task)


def run_order_entry_seconds(task, conf):
    timing = _timing(task)
    if timing is not None and _grandet(task, conf):
        if timing.started or _enabled(task, conf):
            return timing.entry_seconds
    return conf.run_order_delay * 60


def run_order_buffer_seconds(task, conf):
    timing = _timing(task)
    if timing is not None and _grandet(task, conf):
        if timing.started or _enabled(task, conf):
            return timing.buffer_seconds
    return conf.run_order_buffer_time


def run_order_network_allowance(task, conf=None):
    if conf is None:
        from arknights_mower.utils import config

        conf = config.conf
    timing = _timing(task)
    return (
        timing.event.compensation_seconds
        if timing is not None and timing.started and _grandet(task, conf)
        else 0
    )


def run_order_network_compensation(owner, conf):
    """每次等待前核验任务模式，途中改用无人机即停止继承补偿。"""
    if owner.__dict__.get("_run_order_network_active") is not True:
        return 0
    task = owner.__dict__.get("_run_order_network_task")
    solver = owner.__dict__.get("_run_order_network_solver")
    if solver is not None and solver.task is not task:
        return 0
    if task is not None:
        timing = _timing(task)
        if not _grandet(task, conf) or timing is None or not timing.started:
            clear_run_order_network(task)
            owner._run_order_network_active = False
            owner._run_order_network_compensation = 0
            return 0
    allowance = owner.__dict__.get("_run_order_network_compensation", 0)
    if type(allowance) not in (int, float) or not isfinite(allowance):
        return 0
    return max(0, min(allowance, MAX_COMPENSATION_SECONDS))


def bind_run_order_network(tasks, owner, conf, now, *, op_data=None):
    """在观测结束时绑定未来二十分钟任务，开始后不再重算。"""
    event = (
        get_network_adaptation(owner).peek_run_order(
            now, base_seconds=conf.run_order_buffer_time
        )
        if getattr(conf, "run_order_network_adaptive", False)
        and conf.run_order_buffer_time > 0
        else None
    )
    for task in tasks:
        timing = _timing(task)
        if not _grandet(task, conf) or (
            timing is not None and not timing.started and not _enabled(task, conf)
        ):
            clear_run_order_network(task)
            continue
        if (
            timing is not None
            and timing.started
            or owner.__dict__.get("_run_order_network_dispatch_task") is task
            or getattr(task, "run_order_network_started", False)
            or getattr(task, "run_order_restore_pending", False)
            or not _enabled(task, conf)
        ):
            continue
        if timing is not None and task.time != timing.applied_time:
            clear_run_order_network(task, restore_time=False)
            timing = None
        base_time = timing.base_time if timing is not None else task.time
        until_base_start = base_time - now
        if (
            event is None
            or not timedelta(0) <= until_base_start <= RUN_ORDER_BINDING_WINDOW
        ):
            continue
        base_entry = conf.run_order_delay * 60
        base_buffer = conf.run_order_buffer_time
        buffer_seconds = base_buffer + event.compensation_seconds
        entry_seconds = (
            base_entry + buffer_seconds
            if buffer_seconds >= base_entry / 2
            else base_entry
        )
        applied_time = (
            task.time
            if task.retains_execution
            else base_time + timedelta(seconds=base_entry - entry_seconds)
        )
        task.run_order_network_timing = RunOrderNetworkTiming(
            base_time,
            applied_time,
            entry_seconds,
            buffer_seconds,
            event,
            base_entry,
            base_buffer,
        )
        task.time = applied_time


refresh_run_order_network = bind_run_order_network


def begin_run_order_network(task, owner, conf, now):
    """实际派发只启用已有快照，不读取历史或消费共享记录。"""
    timing = _timing(task)
    if not _grandet(task, conf):
        clear_run_order_network(task)
        return None
    if timing is not None and timing.started:
        task.run_order_network_started = True
        return timing
    if not _enabled(task, conf):
        clear_run_order_network(task)
        return None
    task.run_order_network_started = True
    if timing is None:
        return None
    if task.time != timing.applied_time:
        clear_run_order_network(task, restore_time=False)
        return None
    timing.started = True
    from arknights_mower.utils.log import logger

    logger.info(
        "本次 %s 跑单沿用联网等待补偿，葛朗台缓冲时间由%s秒增加至%s秒。",
        task.meta_data,
        f"{timing.base_buffer_seconds:g}",
        f"{timing.buffer_seconds:g}",
    )
    return timing


@contextmanager
def run_order_network_scope(solver):
    """挂入本次派发及原班恢复的参数，退出调用不消费任务快照。"""
    from arknights_mower.utils import config

    task = solver.task
    owner = solver.recog
    if owner.__dict__.get("_run_order_network_dispatch_task") is task:
        yield
        return
    keys = (
        "_run_order_network_dispatch_task",
        "_run_order_network_task",
        "_run_order_network_solver",
        "_run_order_network_active",
        "_run_order_network_compensation",
    )
    missing = object()
    previous = {key: owner.__dict__.get(key, missing) for key in keys}
    owner._run_order_network_dispatch_task = task
    try:
        timing = begin_run_order_network(task, owner, config.conf, datetime.now())
        if timing is None:
            owner._run_order_network_active = False
            owner._run_order_network_compensation = 0
            yield
            return
        owner._run_order_network_task = task
        owner._run_order_network_solver = solver
        owner._run_order_network_active = True
        owner._run_order_network_compensation = timing.event.compensation_seconds
        yield
    finally:
        for key, value in previous.items():
            if value is missing:
                owner.__dict__.pop(key, None)
            else:
                setattr(owner, key, value)


def with_run_order_network(method):
    @wraps(method)
    def wrapped(solver, *args, **kwargs):
        with run_order_network_scope(solver):
            return method(solver, *args, **kwargs)

    return wrapped
