"""替班检查通过真实调度入口保留期限、观察岗位并安排既有纠错。"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.replacement_check_tests import base
from arknights_mower.tests.replacement_check_tests import clock as clock
from arknights_mower.tests.replacement_check_tests import (
    replacement_solver as replacement_solver,
)
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.replacement_check import sync_replacement_checks
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)


@pytest.fixture
def dispatch_solver(replacement_solver):
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = replacement_solver.op_data
    instance.tasks, instance.task = replacement_solver.tasks, None
    instance.enter_room = replacement_solver.enter_room
    instance.back = replacement_solver.back
    instance.get_agent_from_room = replacement_solver.get_agent_from_room
    instance.reading = replacement_solver.reading
    instance.find = MagicMock(return_value=True)
    instance.scene = MagicMock(return_value=base.Scene.INFRA_MAIN)
    instance._initial_mood_read_pending = lambda: False
    instance._emergency_frozen = lambda: False
    instance._emergency_active = lambda: False
    instance._protected_training_names = lambda: set()
    instance._discard_product_switches = MagicMock()
    instance._refresh_deferred_product_reservations = MagicMock()
    instance.backup_plan_solver = MagicMock(return_value=False)
    instance._resume_waiting_group_shifts = MagicMock()
    instance.error = False
    return instance


def test_metadata_planning_preserves_one_observed_replacement_deadline(
    dispatch_solver, clock, monkeypatch, offline_maintenance
):
    solver = dispatch_solver
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (None, None))

    solver.plan_metadata()
    checks = [task for task in solver.tasks if getattr(task, "replacement_check", None)]
    assert len(checks) == 1
    check = checks[0]
    solver.task = check
    solver.infra_main()
    deadline = clock.now() + timedelta(hours=4)
    assert check.time == deadline

    for _ in range(3):
        solver.plan_metadata()
        assert [
            task for task in solver.tasks if getattr(task, "replacement_check", None)
        ] == [check]
        assert check.time == deadline


def test_due_dispatch_observes_before_generating_replacement_correction(
    dispatch_solver, clock
):
    solver = dispatch_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    solver.task = check
    solver.infra_main()
    assert solver.tasks == [check]
    assert check.time == clock.now() + timedelta(hours=4)

    clock.current = check.time
    solver.reading.update(mood=0, time=clock.now())
    solver.task = check
    solver.infra_main()

    assert all(task is not check for task in solver.tasks)
    assert len(solver.tasks) == 1
    correction = solver.tasks[0]
    assert correction.type == TaskTypes.SELF_CORRECTION
    assert correction.plan == {"central": ["赫默"]}
    assert solver.op_data.operators["歌蕾蒂娅"].current_room == "dormitory_1"
    assert solver.get_agent_from_room.call_count == 2
    sync_replacement_checks(solver)
    assert solver.tasks == [correction]


def test_failed_check_yields_to_independent_work_and_reopens_after_new_observation(
    dispatch_solver, clock
):
    solver = dispatch_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    solver.reading.update(mood=0, time=clock.now())
    spare = solver.op_data.operators["赫默"]
    spare.mood = 0
    solver.task = check
    solver.infra_main()
    original_time = check.time
    assert check.execution_failure
    calls = solver.get_agent_from_room.call_count
    independent = SchedulerTask(time=clock.now(), meta_data="独立任务")
    solver.tasks.append(independent)

    for _ in range(3):
        clock.current += timedelta(minutes=5)
        sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert check.execution_failure
        assert check.time == original_time
        assert find_next_task(solver.tasks) is independent
    assert solver.get_agent_from_room.call_count == calls

    spare.mood, spare.time_stamp = 20, clock.now()
    solver.task = check
    solver.infra_main()
    assert all(task is not check for task in solver.tasks)
    assert any(task.plan == {"central": ["赫默"]} for task in solver.tasks)


def test_queue_cleanup_preserves_check_and_original_deadline(dispatch_solver, clock):
    solver = dispatch_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    check.time = clock.now() + timedelta(hours=1)
    original_time = check.time
    stale = SchedulerTask(time=clock.now() - timedelta(hours=1))
    solver.tasks.append(stale)
    solver.error = True
    solver.find_next_task = base.BaseSchedulerSolver.find_next_task.__get__(solver)

    solver.handle_error()

    assert check in solver.tasks
    assert check.time == original_time
    assert stale not in solver.tasks


def test_run_selects_new_replacement_check_before_entering_game_loop(
    dispatch_solver, monkeypatch, offline_maintenance
):
    solver = dispatch_solver
    solver.party_time = None
    solver.free_clue = solver.credit_fight = None
    solver._emergency_filter_tasks = MagicMock()
    solver._schedule_maintenance_backup_check = MagicMock()
    solver._sync_run_order_tasks = MagicMock()
    solver._fill_empty_dorms = MagicMock()
    solver.queue_product_switches = MagicMock()
    monkeypatch.setattr(solver.op_data, "correct_dorm", MagicMock())
    enter_loop = MagicMock()
    monkeypatch.setattr(base.SceneGraphSolver, "run", enter_loop)

    solver.run()

    checks = [task for task in solver.tasks if getattr(task, "replacement_check", None)]
    assert len(checks) == 1
    assert solver.task is checks[0]
    assert solver.task.replacement_check == {
        "owner": "歌蕾蒂娅",
        "cover": "薇薇安娜",
        "room": "central",
        "index": 0,
    }
    enter_loop.assert_called_once()
    solver.get_agent_from_room.assert_not_called()
