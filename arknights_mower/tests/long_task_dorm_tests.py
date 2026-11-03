"""大型任务暂缓普通宿舍清退，空床补人和其他任务仍保留截止时间。"""

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
            return cls.current

    Clock.current = now
    monkeypatch.setattr(manual_tasks, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(manual_tasks.config, "conf", Conf(maa_rg_enable=True))
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.task = None
    solver.op_data = None
    release = SchedulerTask(now, task_type=TaskTypes.RELEASE_DORM)
    fill = SchedulerTask(now + timedelta(minutes=1), task_type=TaskTypes.FILL_DORM)
    order = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER)
    solver.tasks = [release, order]
    return SimpleNamespace(
        solver=solver, now=now, clock=Clock, release=release, fill=fill, order=order
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
    solver.maa_plan_solver.assert_called_with([])


@pytest.mark.parametrize(
    "flag", ["strict_mood_limit", "emergency_recovery_release", "execution_retained"]
)
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
        TaskTypes.FILL_DORM,
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


@pytest.fixture
def maa_solver(scheduler, monkeypatch):
    solver = scheduler.solver
    solver.device = MagicMock()
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
    return solver


@pytest.mark.parametrize("deadline_kind", ["strict", "fill"])
def test_running_maa_yields_to_new_deadline(
    scheduler, maa_solver, monkeypatch, deadline_kind
):
    solver = maa_solver
    ticks = []

    def tick(_):
        ticks.append(1)
        if len(ticks) == 2:
            assert solver.maa_stop.call_count == 0
            if deadline_kind == "strict":
                scheduler.release.strict_mood_limit = True
            else:
                scheduler.fill.time = scheduler.now
                solver.tasks.append(scheduler.fill)

    monkeypatch.setattr(base_schedule, "csleep", tick)
    assert solver.maa_plan_solver([])
    assert len(ticks) == 2
    solver.maa_stop.assert_called_once()
    expected = [scheduler.release, scheduler.order]
    if deadline_kind == "fill":
        expected.append(scheduler.fill)
    assert solver.tasks == expected
    assert scheduler.release.time == scheduler.now


def test_due_fill_prevents_automatic_long_task(scheduler):
    solver = scheduler.solver
    solver.tasks.append(scheduler.fill)
    scheduler.fill.time = scheduler.now
    solver.maa_plan_solver = MagicMock()
    assert not manual_tasks.run_long_task_if_dorm_pending(solver)
    solver.maa_plan_solver.assert_not_called()


def test_manual_long_task_yields_to_fill(scheduler):
    solver = scheduler.solver
    solver.tasks.append(scheduler.fill)
    solver.task = SchedulerTask(scheduler.now, task_type=TaskTypes.ROGUELIKE)
    assert manual_tasks.manual_task_deadline(solver) == scheduler.fill.time


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("outcome", ["complete", "error", "stop"])
def test_long_task_end_reschedules_only_overdue_ordinary_release(
    scheduler, maa_solver, monkeypatch, manual, outcome
):
    from arknights_mower.utils.csleep import MowerExit

    solver = maa_solver
    if manual:
        solver.task = SchedulerTask(scheduler.now, task_type=TaskTypes.ROGUELIKE)
        solver.tasks.insert(0, solver.task)
    future = SchedulerTask(
        scheduler.now + timedelta(minutes=10), task_type=TaskTypes.RELEASE_DORM
    )
    protected = [
        SchedulerTask(
            scheduler.now + timedelta(minutes=20), task_type=TaskTypes.RELEASE_DORM
        )
        for _ in range(3)
    ]
    protected[0].strict_mood_limit = True
    protected[1].emergency_recovery_release = True
    protected[2].execution_retained = True
    solver.tasks.extend([future, *protected])
    original_tasks = list(solver.tasks)
    original_plan = scheduler.release.plan
    solver.MAA.running.side_effect = [True, False]
    ended_at = scheduler.now + timedelta(minutes=2)
    solver.rest_until_next_task.side_effect = lambda: setattr(
        scheduler.clock, "current", ended_at + timedelta(minutes=5)
    )

    def tick(_):
        scheduler.clock.current = ended_at
        if outcome == "error":
            raise RuntimeError("模拟大型任务执行失败")
        if outcome == "stop":
            base_schedule.config.stop_mower.set()

    monkeypatch.setattr(base_schedule, "csleep", tick)
    if outcome == "stop" or outcome == "error" and manual:
        with pytest.raises(MowerExit if outcome == "stop" else RuntimeError):
            solver.maa_plan_solver([], manual=manual, long_task="rogue")
    else:
        assert solver.maa_plan_solver([], manual=manual, long_task="rogue")
    assert scheduler.release.time == ended_at
    assert all(
        current is original for current, original in zip(solver.tasks, original_tasks)
    )
    assert scheduler.release.plan is original_plan
    assert future.time == scheduler.now + timedelta(minutes=10)
    assert all(task.time == scheduler.now + timedelta(minutes=20) for task in protected)


@pytest.mark.parametrize(
    "kind,executor",
    [(TaskTypes.RA, "ReclamationAlgorithm"), (TaskTypes.SECRET_FRONT, "SecretFront")],
)
@pytest.mark.parametrize("failed", [False, True])
def test_native_long_task_resumes_release_at_return(
    scheduler, maa_solver, monkeypatch, kind, executor, failed
):
    solver = maa_solver
    solver.task = SchedulerTask(scheduler.now, task_type=kind)
    ended_at = scheduler.now + timedelta(minutes=2)

    def run(duration):
        assert duration == timedelta(hours=1)
        scheduler.clock.current = ended_at
        if failed:
            raise RuntimeError("模拟大型任务执行失败")

    monkeypatch.setattr(
        base_schedule, executor, MagicMock(return_value=SimpleNamespace(run=run))
    )
    if failed:
        with pytest.raises(RuntimeError):
            manual_tasks._run_single(solver, kind)
    else:
        assert manual_tasks._run_single(solver, kind)
    assert scheduler.release.time == ended_at


def test_no_large_task_started_keeps_release_time(scheduler, maa_solver):
    manual_tasks.config.conf.maa_rg_enable = False
    scheduler.clock.current = scheduler.now + timedelta(minutes=2)
    assert maa_solver.maa_plan_solver([])
    maa_solver.MAA.start.assert_not_called()
    assert scheduler.release.time == scheduler.now


@pytest.mark.parametrize(
    "flag", ["strict_mood_limit", "emergency_recovery_release", "execution_retained"]
)
def test_overdue_protected_release_keeps_time(scheduler, flag):
    setattr(scheduler.release, flag, True)
    scheduler.clock.current = scheduler.now + timedelta(minutes=2)
    manual_tasks.resume_dorm_releases(scheduler.solver)
    assert scheduler.release.time == scheduler.now
