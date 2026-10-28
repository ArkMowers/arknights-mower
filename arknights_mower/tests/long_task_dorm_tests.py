"""大型任务暂缓普通宿舍维护，保留强制离宿和其他任务的截止时间。"""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

_skland = sys.modules.get("arknights_mower.utils.skland")
sys.modules["arknights_mower.utils.skland"] = MagicMock()
try:
    from arknights_mower.solvers import base_schedule, manual_tasks
finally:
    if _skland is None:
        sys.modules.pop("arknights_mower.utils.skland", None)
    else:
        sys.modules["arknights_mower.utils.skland"] = _skland


@pytest.fixture
def scheduler(monkeypatch):
    now = datetime(2026, 10, 28, 14, 0)

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(manual_tasks, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(manual_tasks.config, "conf", Conf(maa_rg_enable=True))
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.task = None
    solver.op_data = None
    release = SchedulerTask(now, task_type=TaskTypes.RELEASE_DORM)
    fill = SchedulerTask(now + timedelta(minutes=1), task_type=TaskTypes.FILL_DORM)
    order = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER)
    solver.tasks = [release, fill, order]
    return SimpleNamespace(
        solver=solver, now=now, release=release, fill=fill, order=order
    )


def test_automatic_admission_keeps_original_tasks_and_times(scheduler):
    solver = scheduler.solver
    solver.maa_plan_solver = MagicMock()
    original = [(id(task), task.time, task.plan) for task in solver.tasks]
    for _ in range(2):
        assert manual_tasks.run_long_task_if_dorm_pending(solver)
        assert [(id(task), task.time, task.plan) for task in solver.tasks] == original
        assert (
            manual_tasks.long_task_deadline(solver, datetime.max)
            == scheduler.order.time
        )
    assert find_next_task(solver.tasks) is scheduler.release
    solver.tasks.remove(scheduler.release)
    assert find_next_task(solver.tasks) is scheduler.fill
    solver.maa_plan_solver.assert_called_with([])


@pytest.mark.parametrize("flag", ["strict_mood_limit", "emergency_recovery_release"])
def test_protected_release_still_blocks_automatic_admission(scheduler, flag):
    setattr(scheduler.release, flag, True)
    scheduler.solver.maa_plan_solver = MagicMock()
    assert not manual_tasks.run_long_task_if_dorm_pending(scheduler.solver)
    assert (
        manual_tasks.long_task_deadline(scheduler.solver, datetime.max) == scheduler.now
    )
    scheduler.solver.maa_plan_solver.assert_not_called()


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.SHIFT_OFF,
        TaskTypes.SKILL_UPGRADE,
        TaskTypes.FLASH_UPDATE,
    ],
)
def test_other_deadlines_remain_binding(scheduler, kind):
    scheduler.order.type = kind
    scheduler.order.time = scheduler.now + timedelta(minutes=4)
    scheduler.solver.maa_plan_solver = MagicMock()
    assert not manual_tasks.run_long_task_if_dorm_pending(scheduler.solver)
    assert (
        manual_tasks.long_task_deadline(scheduler.solver, datetime.max)
        == scheduler.order.time
    )


def test_current_scheduler_pointer_cannot_exclude_an_ordinary_task(scheduler):
    scheduler.solver.task = scheduler.order
    assert (
        manual_tasks.long_task_deadline(scheduler.solver, datetime.max)
        == scheduler.order.time
    )


@pytest.mark.parametrize("kind", list(manual_tasks.LONG_TASKS))
def test_manual_long_task_ignores_dorm_maintenance_only(scheduler, kind):
    task = SchedulerTask(scheduler.now, task_type=kind)
    scheduler.solver.task = task
    scheduler.solver.tasks.insert(0, task)
    assert manual_tasks.manual_task_deadline(scheduler.solver) == scheduler.order.time
    scheduler.solver.tasks.remove(scheduler.order)
    assert manual_tasks.manual_task_deadline(
        scheduler.solver
    ) == scheduler.now + timedelta(hours=24)
    task.type = TaskTypes.DAILY
    assert manual_tasks.manual_task_deadline(scheduler.solver) == scheduler.release.time


@pytest.mark.parametrize("sleep_window", [("13:00", "15:00"), ("13:00", "01:00")])
def test_configured_sleep_prevents_automatic_long_run(scheduler, sleep_window):
    conf = manual_tasks.config.conf
    conf.maa_rg_sleep_min, conf.maa_rg_sleep_max = sleep_window
    scheduler.solver.maa_plan_solver = MagicMock()
    assert not manual_tasks.run_long_task_if_dorm_pending(scheduler.solver)
    scheduler.solver.maa_plan_solver.assert_not_called()


def test_running_maa_ignores_due_dorm_then_yields_to_new_strict_deadline(
    scheduler, monkeypatch
):
    solver = scheduler.solver
    solver.last_execution = {"maa": None}
    solver.recog = MagicMock()
    solver.MAA = MagicMock()
    solver.MAA.running.side_effect = [True, True]
    maa = solver.MAA
    solver.initialize_maa = MagicMock(side_effect=lambda: setattr(solver, "MAA", maa))
    for name in (
        "back_to_index",
        "release_maa",
        "report_maa_progress",
        "maa_stop",
        "restore_maa_theme",
        "rest_until_next_task",
    ):
        setattr(solver, name, MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    import threading

    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    ticks = []

    def tick(_):
        ticks.append(1)
        if len(ticks) == 2:
            assert solver.maa_stop.call_count == 0
            scheduler.release.strict_mood_limit = True

    monkeypatch.setattr(base_schedule, "csleep", tick)
    assert solver.maa_plan_solver([])
    assert len(ticks) == 2
    solver.maa_stop.assert_called_once()
    assert solver.tasks == [scheduler.release, scheduler.fill, scheduler.order]
    assert scheduler.release.time == scheduler.now
