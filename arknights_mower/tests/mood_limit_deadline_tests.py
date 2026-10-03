"""上限离宿提前避让阻塞窗口；已经到期的跑单／专精仍先执行。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config, operation_timing
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    protect_priority_tasks,
    scheduling,
)


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "run_order_delay", 5)
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})


def release_at(deadline, name="令", room="dormitory_2"):
    return SchedulerTask(
        time=deadline,
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={room: ["Current", "Current", "Free", "Current", "Current"]},
        meta_data=name,
        strict_mood_limit=True,
        mood_limit=12,
    )


def test_logged_two_order_windows_clear_before_first_order_without_moving_orders():
    now = datetime(2026, 9, 29, 3, 15)
    first = SchedulerTask(
        time=now.replace(minute=33, second=37),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
    )
    second = SchedulerTask(
        time=now.replace(minute=39, second=36),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_3_1": ["但书"]},
    )
    deadline = now.replace(minute=41, second=17)
    release = release_at(deadline)
    times = first.time, second.time
    tasks = [first, release, second]
    protect_priority_tasks(tasks, time_now=now)
    duration = timedelta(minutes=operation_timing.estimate_dorm_minutes("dormitory_2"))
    assert release.time + duration < first.time
    assert release.mood_limit_deadline == deadline
    assert (first.time, second.time) == times
    early = release.time
    protect_priority_tasks(tasks, time_now=now + timedelta(minutes=1))
    assert release.time == early


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
@pytest.mark.parametrize("offset", [-1, 0, 600])
def test_due_priority_wins_but_future_priority_allows_early_release(kind, offset):
    now = datetime.now()
    priority = SchedulerTask(
        time=now + timedelta(seconds=offset),
        task_type=kind,
        task_plan={"room_1_1": ["但书"]} if kind == TaskTypes.RUN_ORDER else {},
    )
    limit = release_at(priority.time + timedelta(minutes=2))
    tasks = [limit, priority]
    due = priority.time
    scheduling(tasks, time_now=now)
    assert priority.time == due
    if offset <= 0:
        assert tasks[0] is priority
    else:
        assert tasks[0] is limit
        assert limit.time + timedelta(minutes=1.5) < priority.time


def test_multiple_releases_have_separate_execution_time():
    now = datetime.now()
    deadline = now + timedelta(minutes=30)
    first, second = release_at(deadline), release_at(deadline, "夕", "dormitory_3")
    tasks = [first, second]
    protect_priority_tasks(tasks, time_now=now)
    assert tasks[0].time + timedelta(minutes=1.5) <= tasks[1].time
    assert tasks[1].time + timedelta(minutes=1.5) <= deadline
    original = [t.time for t in tasks]
    protect_priority_tasks(tasks, time_now=now)
    assert [t.time for t in tasks] == original


@pytest.mark.parametrize(
    "kind", [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY, TaskTypes.WORKSHOP]
)
def test_other_blocking_work_does_not_push_release_past_limit(kind):
    now = datetime.now()
    task = SchedulerTask(time=now + timedelta(minutes=10), task_type=kind)
    limit = release_at(task.time + timedelta(seconds=30))
    tasks = [task, limit]
    protect_priority_tasks(tasks, time_now=now)
    assert limit.time + timedelta(minutes=1.5) < task.time


def test_ordinary_release_keeps_original_timing(monkeypatch):
    now = datetime.now()
    limit = release_at(now + timedelta(minutes=30))
    ordinary = SchedulerTask(time=limit.time, task_type=TaskTypes.RELEASE_DORM)
    tasks = [limit, ordinary]
    protect_priority_tasks(tasks, time_now=now)
    assert limit.time < ordinary.time
    assert ordinary.time == now + timedelta(minutes=30)
    protect_priority_tasks([ordinary], time_now=now)
    assert ordinary.time == now + timedelta(minutes=30)


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
def test_dispatch_rechecks_priority_became_due_during_navigation(kind):
    now = datetime.now()
    limit = release_at(now - timedelta(minutes=3))
    priority = SchedulerTask(time=now - timedelta(seconds=1), task_type=kind)
    solver = object.__new__(BaseSchedulerSolver)
    solver.task, solver.tasks = limit, [limit, priority]
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.agent_arrange = MagicMock()
    assert solver.infra_main() is True
    assert solver.task is None
    assert solver.tasks[0] is priority
    solver.agent_arrange.assert_not_called()


def test_early_limit_release_skips_optional_workshop(monkeypatch):
    now = datetime.now()
    op = SimpleNamespace(
        current_room="dormitory_2",
        current_index=2,
        upper_limit=12,
        mood=11,
        is_high=lambda: False,
    )
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = SimpleNamespace(
        operators={"令": op},
        has_rest_mood_limit=lambda _: True,
    )
    solver.craft_material = MagicMock()
    monkeypatch.setattr(
        config.conf, "workshop_settings", [SimpleNamespace(operator="令")]
    )
    task = release_at(now + timedelta(minutes=1))
    assert solver.prepare_release_dorm(task)
    assert task.plan
    assert op.mood == 11
    solver.craft_material.assert_not_called()


def test_sleep_boundary_schedules_release_early_before_waiting():
    now = datetime.now()
    limit = release_at(now + timedelta(minutes=10))
    solver = object.__new__(BaseSchedulerSolver)
    solver.tasks = [limit]

    class StopBeforeSleep(Exception):
        pass

    solver.handle_idle_action = MagicMock(side_effect=StopBeforeSleep)
    with pytest.raises(StopBeforeSleep):
        solver.rest_until_next_task()
    assert limit.time + timedelta(minutes=1.5) == limit.mood_limit_deadline
    assert solver.handle_idle_action.call_args.args[0] < 9 * 60


def test_selected_ordinary_task_yields_to_newly_advanced_limit():
    now = datetime.now()
    limit = release_at(now + timedelta(minutes=1))
    ordinary = SchedulerTask(
        time=now - timedelta(seconds=1), task_type=TaskTypes.CLUE_PARTY
    )
    solver = object.__new__(BaseSchedulerSolver)
    solver.task, solver.tasks = ordinary, [ordinary, limit]
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver._run_clue_flow = MagicMock()
    assert solver.infra_main() is True
    assert solver.task is None
    assert solver.tasks[0] is limit
    solver._run_clue_flow.assert_not_called()


def test_unchanged_release_reuses_advanced_task_and_logs_only_changes(caplog):
    import logging

    from arknights_mower.utils.operators import Dormitory, Operator
    from arknights_mower.utils.scheduler_task import plan_mood_limit_releases

    now = datetime.now()
    op = Operator(
        "令",
        "dormitory_2",
        current_room="dormitory_2",
        current_index=2,
        mood=10,
        time_stamp=now,
    )
    op.upper_limit = 12
    bed = Dormitory(("dormitory_2", 2), "令", now + timedelta(minutes=40))
    data = SimpleNamespace(
        operators={"令": op},
        plan={"dormitory_2": [None] * 5},
        all_dorms=lambda: [bed],
        is_recovery_dorm=lambda *args: True,
        has_rest_mood_limit=lambda name: True,
        rest_mood_complete=lambda name: False,
    )
    caplog.set_level(logging.INFO)
    tasks = plan_mood_limit_releases(data)
    first = tasks[0]
    for _ in range(3):
        protect_priority_tasks(tasks, time_now=now)
        tasks = plan_mood_limit_releases(data, previous_tasks=tasks)
        assert tasks[0] is first
        assert first.time == bed.time - timedelta(minutes=1.5)
    assert len([r for r in caplog.records if "心情上限离宿提前至" in r.message]) == 1
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, tasks
    solver._emergency_replan_releases()
    assert solver.tasks[0] is first
    bed.time += timedelta(minutes=5)
    tasks = plan_mood_limit_releases(data, previous_tasks=tasks)
    assert tasks[0] is not first
    protect_priority_tasks(tasks, time_now=now)
    assert tasks[0].time == bed.time - timedelta(minutes=1.5)
    assert len([r for r in caplog.records if "心情上限离宿提前至" in r.message]) == 2
    first = tasks[0]
    bed.position = ("dormitory_2", 3)
    op.current_index = 3
    tasks = plan_mood_limit_releases(data, previous_tasks=tasks)
    assert tasks[0] is not first
    assert tasks[0].release_dorm_targets() == {"令": ("dormitory_2", 3)}
