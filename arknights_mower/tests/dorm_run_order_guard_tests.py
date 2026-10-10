"""宿舍按实际耗时让跑单先执行，已完成房间不重做，强制上限不延期。"""

from collections import deque
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config, operation_timing
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    defer_dorm_before_priority_task,
    protect_priority_tasks,
    scheduling,
    simplify_dorm_fill,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def schedule(monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    now = datetime.now()
    dorm = SchedulerTask(
        time=now, task_type=TaskTypes.RE_ORDER, task_plan={"dormitory_1": ["Free"]}
    )
    order = SchedulerTask(
        time=now + timedelta(minutes=2),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
    )
    return now, dorm, order


def test_observed_duration_moves_dorm(schedule, monkeypatch):
    now, dorm, order = schedule
    operation_timing._dorm_durations["dormitory_1"] = deque([120])
    tasks = [dorm, order]
    scheduling(tasks, time_now=now)
    assert tasks[0] is order
    assert dorm.time > order.time


@pytest.mark.parametrize("strict", [False, True])
def test_guard_rechecks_room_and_does_not_delay_strict_limit(schedule, strict):
    now, dorm, order = schedule
    dorm.strict_mood_limit = strict
    order.time = now + timedelta(seconds=30)
    tasks = [dorm, order]
    assert defer_dorm_before_priority_task(dorm, tasks, "dormitory_1", now) == (
        not strict
    )
    assert dorm.plan == {"dormitory_1": ["Free"]}
    assert dorm.time == (now if strict else order.time + timedelta(seconds=1))
    if strict:
        scheduling(tasks, time_now=now)
        assert dorm.time <= now


def test_runtime_guard_keeps_unfinished_room_only(schedule):
    now, dorm, order = schedule
    order.time = now + timedelta(minutes=4)
    instance = object.__new__(BaseSchedulerSolver)
    instance.task = dorm
    instance.tasks = [dorm, order]
    instance.op_data = MagicMock()
    instance.preserve_resting_crafters = MagicMock()
    dorm.plan["dormitory_2"] = ["Free"]

    def arrange(new_plan, room, plan, **kwargs):
        del plan[room]
        # 第一间耗时超出原估计，下一间必须交回调度，先跑单。
        order.time = datetime.now() + timedelta(seconds=30)
        return new_plan

    instance.agent_arrange_room = MagicMock(side_effect=arrange)
    assert instance.agent_arrange(dorm.plan, True) is False
    assert instance.agent_arrange_room.call_count == 1
    assert dorm.plan == {"dormitory_2": ["Free"]}
    assert instance.tasks[0] is order


def test_successful_room_measurement_updates_estimate(monkeypatch):
    from collections import defaultdict

    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    ticks = iter([0, 120])
    monkeypatch.setattr(operation_timing, "perf_counter", lambda: next(ticks))

    @operation_timing.timed_room
    def room_action(room):
        return None

    assert operation_timing.estimate_dorm_minutes("dormitory_1") == 1.5
    room_action("dormitory_1")
    assert (
        operation_timing.estimate_dorm_minutes("dormitory_1") == (120 * 1.2 + 15) / 60
    )


def test_vacancy_fill_yields_to_imminent_order(schedule, monkeypatch):
    now, dorm, order = schedule
    dorm.type = TaskTypes.FILL_DORM
    order.time = now + timedelta(seconds=10)
    original_order_time = order.time
    tasks = [dorm, order]
    scheduling(tasks, time_now=now)
    assert tasks[0] is order
    assert order.time == original_order_time
    assert dorm.time > order.time


def test_vacancy_fill_does_not_protect_unrelated_ordinary_dorm_work(schedule):
    now, dorm, order = schedule
    order.time = now + timedelta(seconds=10)
    fill = SchedulerTask(
        time=now,
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_2": ["Current"] * 4 + ["红"]},
    )
    tasks = [dorm, fill, order]
    scheduling(tasks, time_now=now)
    assert tasks[0] is order
    assert fill.time > order.time
    assert dorm.time > order.time


def test_real_room_dispatch_skips_vacancy_fill_before_imminent_order(schedule):
    now, dorm, order = schedule
    dorm.type = TaskTypes.FILL_DORM
    order.time = now + timedelta(seconds=5)
    instance = object.__new__(BaseSchedulerSolver)
    instance.task, instance.tasks = dorm, [dorm, order]
    instance.op_data = MagicMock()
    instance.preserve_resting_crafters = MagicMock()
    dorm.plan["dormitory_2"] = ["Free"]

    def arrange(new_plan, room, plan, **kwargs):
        del plan[room]
        return new_plan

    instance.agent_arrange_room = MagicMock(side_effect=arrange)
    assert instance.agent_arrange(dorm.plan, True) is False
    instance.agent_arrange_room.assert_not_called()
    assert set(dorm.plan) == {"dormitory_1", "dormitory_2"}
    assert dorm.time > order.time


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
@pytest.mark.parametrize(
    "seconds,allowed", [(-30, False), (30, False), (150, False), (181, True)]
)
def test_fill_uses_same_deadline_and_margin(
    schedule, monkeypatch, kind, seconds, allowed
):
    now, dorm, deadline = schedule
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    dorm.type = TaskTypes.FILL_DORM
    deadline.type = kind
    deadline.time = now + timedelta(seconds=seconds)
    original = deadline.time
    tasks = [dorm, deadline]
    scheduling(tasks, time_now=now)
    assert (tasks[0] is dorm) == allowed
    assert deadline.time == original
    assert dorm.simple_dorm_fill
    assert dorm.plan == {"dormitory_1": ["Free"]}
    if not allowed:
        assert dorm.time > max(now, deadline.time)
        tasks.remove(deadline)
        assert not defer_dorm_before_priority_task(dorm, tasks, "dormitory_1", now)


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
def test_cumulative_fills_yield_and_do_not_move_future_fill_forward(
    schedule, monkeypatch, kind
):
    now, first, deadline = schedule
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    first.type = TaskTypes.FILL_DORM
    second = SchedulerTask(
        time=now, task_plan={"dormitory_2": ["Free"]}, task_type=TaskTypes.FILL_DORM
    )
    future = SchedulerTask(
        time=now + timedelta(hours=1),
        task_plan={"dormitory_3": ["Free"]},
        task_type=TaskTypes.FILL_DORM,
    )
    deadline.type = kind
    deadline.time = now + timedelta(minutes=4)
    tasks = [first, second, deadline, future]
    protect_priority_tasks(tasks, time_now=now)
    assert first.time == now
    assert second.time > deadline.time
    assert future.time == now + timedelta(hours=1)
    assert not getattr(future, "simple_dorm_fill", False)


def test_simplify_pending_fill_restores_only_remaining_original_rooms(schedule):
    now, fill, order = schedule
    fill.type = TaskTypes.FILL_DORM
    fill.dorm_fill_plan = {
        "dormitory_1": ["Current", "甲"],
        "dormitory_2": ["Current", "乙"],
    }
    # 第一间已完成；单回竞争额外增加的第三间不应继续执行。
    fill.plan = {"dormitory_2": ["Current", "丙"], "dormitory_3": ["Current", "乙"]}
    simplify_dorm_fill(fill, [fill, order], now)
    assert fill.plan == {"dormitory_2": ["Current", "乙"]}
    assert fill.simple_dorm_fill


def test_started_recovery_restoration_is_not_interrupted(schedule):
    now, dorm, order = schedule
    dorm.type = TaskTypes.FILL_DORM
    dorm.dorm_recovery_restore = ["dormitory_1"]
    order.time = now
    tasks = [dorm, order]
    simplify_dorm_fill(dorm, tasks, now)
    assert not getattr(dorm, "simple_dorm_fill", False)
    assert not defer_dorm_before_priority_task(dorm, tasks, "dormitory_1", now)


def test_dorm_duration_counts_toward_later_work_before_swap(schedule, monkeypatch):
    now, dorm, swap = schedule
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    dorm.type = TaskTypes.FILL_DORM
    swap.type = TaskTypes.SWAP_SUPPORT
    swap.time = now + timedelta(minutes=4, seconds=30)
    ordinary = SchedulerTask(time=now, task_type=TaskTypes.FIAMMETTA)
    tasks = [dorm, ordinary, swap]
    protect_priority_tasks(tasks, time_now=now)
    assert dorm.time == now
    assert ordinary.time > swap.time


def test_disabled_mastery_does_not_delay_or_simplify_fill(schedule):
    now, fill, swap = schedule
    fill.type = TaskTypes.FILL_DORM
    swap.type = TaskTypes.SWAP_SUPPORT
    swap.time = now
    protect_priority_tasks([fill, swap], time_now=now)
    assert fill.time == now
    assert not getattr(fill, "simple_dorm_fill", False)
