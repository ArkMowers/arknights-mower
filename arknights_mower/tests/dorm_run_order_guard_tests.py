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
    defer_dorm_before_run_order,
    scheduling,
)


@pytest.fixture
def schedule(monkeypatch):
    monkeypatch.setattr(config.conf, "experimental_dorm_logic", True)
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


def test_observed_duration_moves_dorm_but_legacy_uses_original_estimate(
    schedule, monkeypatch
):
    now, dorm, order = schedule
    operation_timing._dorm_durations["dormitory_1"] = deque([120])
    tasks = [dorm, order]
    scheduling(tasks, time_now=now)
    assert tasks[0] is order
    assert dorm.time > order.time
    monkeypatch.setattr(config.conf, "experimental_dorm_logic", False)
    dorm.time = now
    tasks = [dorm, order]
    scheduling(tasks, time_now=now)
    assert tasks[0] is dorm
    assert dorm.time == now


@pytest.mark.parametrize("strict", [False, True])
def test_guard_rechecks_room_and_does_not_delay_strict_limit(schedule, strict):
    now, dorm, order = schedule
    dorm.strict_mood_limit = strict
    order.time = now + timedelta(seconds=30)
    tasks = [dorm, order]
    assert defer_dorm_before_run_order(dorm, tasks, "dormitory_1", now) == (not strict)
    assert dorm.plan == {"dormitory_1": ["Free"]}
    assert dorm.time == (now if strict else order.time + timedelta(seconds=1))
    if strict:
        scheduling(tasks, time_now=now)
        assert dorm.time == now


def test_runtime_guard_keeps_unfinished_room_only(schedule):
    _, dorm, order = schedule
    instance = object.__new__(BaseSchedulerSolver)
    instance.task = dorm
    instance.tasks = [dorm, order]
    instance.op_data = MagicMock(experimental_dorm_logic=True)
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


@pytest.mark.parametrize("experimental", [False, True])
def test_only_experimental_vacancy_fill_bypasses_run_order_scheduling(
    schedule, monkeypatch, experimental
):
    now, dorm, order = schedule
    monkeypatch.setattr(config.conf, "experimental_dorm_logic", experimental)
    dorm.type = TaskTypes.FILL_DORM
    order.time = now + timedelta(seconds=10)
    original_order_time = order.time
    tasks = [dorm, order]
    scheduling(tasks, time_now=now)
    assert (tasks[0] is dorm) == experimental
    assert order.time == original_order_time
    if experimental:
        assert dorm.time == now
        assert not defer_dorm_before_run_order(dorm, tasks, "dormitory_1", now)
    else:
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
    assert tasks == [fill, order, dorm]
    assert fill.time == now
    assert dorm.time > order.time


def test_real_room_dispatch_runs_vacancy_fill_before_imminent_order(schedule):
    now, dorm, order = schedule
    dorm.type = TaskTypes.FILL_DORM
    order.time = now + timedelta(seconds=5)
    instance = object.__new__(BaseSchedulerSolver)
    instance.task, instance.tasks = dorm, [dorm, order]
    instance.op_data = MagicMock(experimental_dorm_logic=True)
    dorm.plan["dormitory_2"] = ["Free"]

    def arrange(new_plan, room, plan, **kwargs):
        del plan[room]
        return new_plan

    instance.agent_arrange_room = MagicMock(side_effect=arrange)
    assert instance.agent_arrange(dorm.plan, True) is not False
    assert instance.agent_arrange_room.call_count == 2
    assert dorm.plan == {}
    assert dorm.time == now
