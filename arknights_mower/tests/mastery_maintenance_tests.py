"""维护前提前专精换人，复用关键任务保护与实际协助执行。"""

import pickle
import sys
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower import __main__ as main  # noqa: E402
from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import mastery_support_swap as support_swap  # noqa: E402
from arknights_mower.tests.mastery_support_fixtures import swap_case  # noqa: E402
from arknights_mower.utils import config, operation_timing  # noqa: E402
from arknights_mower.utils import scheduler_task as scheduler  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.news_checker import (  # noqa: E402
    MaintenanceInfo,
    NewsChecker,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def maintenance(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 9, 9)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    info = MaintenanceInfo(
        start=datetime(2026, 10, 9, 10),
        end=datetime(2026, 10, 9, 16),
        update_type="major",
        title="停机维护",
        url="",
        announcement_id="offline-mastery-maintenance",
    )
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=True))
    for event in ("stop_mower", "wake_scheduler", "maintenance_recheck"):
        monkeypatch.setattr(config, event, Event())
    monkeypatch.setattr(config.conf.run_order_grandet_mode, "enable", False)
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: info)
    monkeypatch.setattr(scheduler, "datetime", Clock)
    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(operation_timing, "_work_durations", {})
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    monkeypatch.setattr(
        "requests.sessions.Session.request",
        MagicMock(side_effect=AssertionError("offline test requested network")),
    )
    return SimpleNamespace(info=info, clock=Clock)


def handoff(time):
    task = SchedulerTask(time, task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "1"
    return task


@pytest.mark.parametrize("minutes", [-9, 0, 60, 345])
@pytest.mark.parametrize(
    "entry", [scheduler.scheduling, scheduler.protect_priority_tasks]
)
def test_maintenance_advances_handoff_through_both_dispatch_entries(
    maintenance, minutes, entry
):
    swap = handoff(maintenance.info.start + timedelta(minutes=minutes))
    identity = swap.plan_key
    tasks = [swap]
    entry(tasks)
    assert swap.time + timedelta(minutes=1) < maintenance.info.start - timedelta(
        minutes=10
    )
    assert swap.advance_support_swap is True
    assert swap.plan_key == identity
    first_time = swap.time
    entry(tasks)
    assert swap.time == first_time


def test_complete_announced_interval_includes_final_half_hour(maintenance):
    assert maintenance.info.resume_at < maintenance.info.end
    swap = handoff(maintenance.info.end - timedelta(minutes=15))
    scheduler.protect_priority_tasks([swap])
    assert swap.time < maintenance.info.start


def test_before_buffer_and_after_maintenance_keep_their_times(maintenance):
    for time in (
        maintenance.info.start - timedelta(minutes=11),
        maintenance.info.end,
        maintenance.info.end + timedelta(minutes=1),
    ):
        swap = handoff(time)
        scheduler.protect_priority_tasks([swap])
        assert swap.time == time
        assert not getattr(swap, "advance_support_swap", False)


@pytest.mark.parametrize("disabled", ["mastery", "announcement", "started"])
def test_unavailable_early_execution_keeps_task(maintenance, monkeypatch, disabled):
    swap = handoff(maintenance.info.start + timedelta(hours=1))
    before = swap.time
    if disabled == "mastery":
        config.conf.enable_mastery = False
    elif disabled == "announcement":
        monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    else:
        maintenance.clock.current = maintenance.info.start
    scheduler.protect_priority_tasks([swap])
    assert swap.time == before
    assert not getattr(swap, "advance_support_swap", False)


def test_late_notice_runs_immediately_and_never_postpones_due_handoff(maintenance):
    maintenance.clock.current = maintenance.info.start - timedelta(minutes=3)
    swap = handoff(maintenance.info.start + timedelta(hours=1))
    scheduler.protect_priority_tasks([swap])
    assert swap.time == maintenance.clock.now()
    assert swap.advance_support_swap is True
    maintenance.clock.current += timedelta(seconds=10)
    scheduler.protect_priority_tasks([swap])
    assert swap.time < maintenance.clock.now()


def test_operation_budgets_keep_multiple_handoffs_in_order(maintenance):
    first = handoff(maintenance.info.start)
    second = handoff(maintenance.info.start + timedelta(hours=1))
    scheduler.protect_priority_tasks([second, first], execution_time=2)
    assert first.time + timedelta(minutes=1) < second.time
    assert second.time < maintenance.info.start - timedelta(minutes=10)


def test_custom_buffer_and_observed_training_budget(maintenance, monkeypatch):
    monkeypatch.setattr(operation_timing, "_work_durations", {"train": [180]})
    swap = handoff(maintenance.info.start)
    swap.plan = {"train": ["艾丽妮", "Current"]}
    scheduler.protect_priority_tasks([swap], run_order_delay=8)
    assert swap.time + timedelta(minutes=3) < maintenance.info.start - timedelta(
        minutes=16
    )


def test_ordinary_work_yields_and_order_keeps_maintenance_behavior(maintenance):
    order = SchedulerTask(
        maintenance.info.start + timedelta(hours=1),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    swap = handoff(order.time)
    ordinary = SchedulerTask(
        maintenance.info.start - timedelta(minutes=12),
        task_type=TaskTypes.FIAMMETTA,
    )
    tasks = [ordinary, swap, order]
    scheduler.scheduling(tasks)
    assert order.time == maintenance.info.start - timedelta(minutes=10, seconds=1)
    assert swap.time < order.time
    assert ordinary.time > swap.time


def test_early_marker_survives_snapshot_restoration(maintenance):
    swap = handoff(maintenance.info.start)
    scheduler.protect_priority_tasks([swap])
    restored = pickle.loads(pickle.dumps(swap))
    scheduler.protect_priority_tasks([restored])
    assert restored.time == swap.time
    assert restored.advance_support_swap is True


def test_rest_uses_advanced_handoff_time(maintenance, monkeypatch):
    swap = handoff(maintenance.info.start + timedelta(hours=1))
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [swap]
    solver.op_data = None
    solver.task_count = 0
    solver._schedule_maintenance_backup_check = MagicMock()
    solver.handle_idle_action = MagicMock()
    solver._idle_sleep = MagicMock()
    solver.check_current_focus = MagicMock()
    monkeypatch.setattr(base, "send_message", MagicMock())
    monkeypatch.setattr(base.task_template, "render", MagicMock(return_value=""))
    solver.rest_until_next_task()
    assert swap.time < maintenance.info.start - timedelta(minutes=10)
    solver._idle_sleep.assert_called_once_with(
        (swap.time - maintenance.clock.now()).total_seconds()
    )


def test_main_protects_handoff_before_daily_work_budget(maintenance, monkeypatch):
    maintenance.clock.current = maintenance.info.start - timedelta(minutes=15)
    swap = handoff(maintenance.info.start + timedelta(hours=1))
    solver = MagicMock()
    solver.tasks = [swap]
    solver.initialize_operators.return_value = None
    solver.op_data.validate_backup_plans.return_value = {"success": True}
    solver._initial_mood_refresh_rooms = set()
    solver.rest_until_next_task.side_effect = MowerExit
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "initialize", MagicMock(return_value=solver))
    for name in (
        "_apply_version_update_resting_threshold",
        "_arm_maintenance_timer",
        "refresh_resource_at_boundary",
    ):
        monkeypatch.setattr(main, name, MagicMock())
    monkeypatch.setattr(main, "_handle_maintenance", MagicMock(return_value=False))
    config.stop_mower.clear()
    main.simulate(None)
    assert swap.time < maintenance.info.start - timedelta(minutes=10)
    solver.rest_until_next_task.assert_called_once()
    solver.visit_friend_plan_solver.assert_not_called()
    solver.run.assert_not_called()


def test_maintenance_handoff_executes_without_ideal_time_requeue(maintenance):
    task = handoff(maintenance.info.start + timedelta(hours=1))
    scheduler.protect_priority_tasks([task])
    plan, panel, solver, options = swap_case()
    panel.countdown += timedelta(hours=2)
    solver.task = task
    with (
        patch.object(support_swap, "candidates", return_value=(options, 0)),
        patch.object(support_swap, "schedule_context", return_value=({}, 0)),
        patch.object(support_swap, "confirm_training_panel", return_value=panel),
        patch.object(support_swap, "save_runtime"),
        patch.object(support_swap, "place_support", return_value=panel) as place,
        patch.object(support_swap, "finish_support_swap") as finish,
        patch.object(support_swap, "enqueue_support_swap") as enqueue,
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
    ):
        support_swap.perform_swap(solver, plan, panel, "快教官")
    place.assert_called_once_with(solver, plan, 2, "艾丽妮")
    finish.assert_called_once_with(solver, plan, 2, True)
    enqueue.assert_not_called()
