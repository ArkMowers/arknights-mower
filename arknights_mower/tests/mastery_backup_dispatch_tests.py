"""副表实际换人完成后才派发待开始的专精，保留原任务及时间。"""

from datetime import timedelta

import jsonpickle
import pytest

from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    replan_update_tasks,
    task_view,
)

scheduler = recovery.scheduler


@pytest.fixture
def dispatch(scheduler, monkeypatch):
    from arknights_mower.utils import mastery_db

    solver = scheduler.solver
    solver.op_data.run_order_rooms = []
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    state = {"id": 17, "status": "idle"}
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda _: dict(state))
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [dict(state)])
    start = SchedulerTask(
        scheduler.clock.now() - timedelta(minutes=1),
        task_type=TaskTypes.SKILL_UPGRADE,
    )
    start.plan_key = "17"
    solver.tasks = [start]
    observed = []

    def device_dispatch(_):
        observed.append(solver.task)

    monkeypatch.setattr(scheduler.module.SceneGraphSolver, "run", device_dispatch)
    return solver, start, state, observed


@pytest.mark.parametrize("task_type", [TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER])
def test_new_backup_arrangement_precedes_already_selected_start(
    scheduler, dispatch, task_type
):
    solver, start, _, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=task_type,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )

    def activate_backup():
        if not any(task is backup for task in solver.tasks):
            solver.tasks.append(backup)
        return True

    solver.backup_plan_solver.side_effect = activate_backup
    solver.run()
    assert observed == [backup]
    assert start in solver.tasks
    assert start.time == scheduler.clock.now() - timedelta(minutes=1)
    assert start.plan_key == "17"
    assert solver._train_mastery_active()
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("restore", [False, True])
def test_failed_backup_yields_to_independent_work_and_releases_same_start(
    scheduler, dispatch, restore
):
    solver, start, _, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    independent = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.extend([backup, independent])
    solver.run()
    assert observed == [backup]
    updated = replan_update_tasks({"tasks": solver.tasks})["tasks"]
    assert any(task is backup for task in updated)
    solver._retain_failed_task(backup, "驻员未确认", ["central"])
    original_time = start.time
    if restore:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        start, backup, independent = (
            next(task for task in solver.tasks if task.type == kind)
            for kind in (
                TaskTypes.SKILL_UPGRADE,
                TaskTypes.SELF_CORRECTION,
                TaskTypes.DEPOT,
            )
        )
    for _ in range(3):
        scheduler.clock.current += timedelta(minutes=1)
        assert task_view(solver.tasks, TaskScope.DISPATCH) == [independent]
        assert start.time == original_time
        assert solver._train_mastery_active()
        solver.run()
        assert observed[-1] is independent
    solver.tasks.remove(backup)
    solver.run()
    assert observed[-1] is start
    assert start.time == original_time
    assert start.plan_key == "17"
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("status", ["training", "waiting_collect"])
def test_active_training_collection_keeps_original_dispatch(
    dispatch, scheduler, status
):
    solver, start, state, observed = dispatch
    state["status"] = status
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    solver.tasks.append(backup)
    solver.run()
    assert observed == [start]


@pytest.mark.parametrize("task_type", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
def test_no_backup_keeps_original_dispatch(dispatch, task_type):
    solver, start, _, observed = dispatch
    start.type = task_type
    solver.run()
    assert observed == [start]
    solver.backup_plan_solver.assert_called_once()


def test_due_support_swap_keeps_priority_over_backup(dispatch, scheduler):
    solver, start, _, observed = dispatch
    start.type = TaskTypes.SWAP_SUPPORT
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    solver.tasks.append(backup)
    solver.run()
    assert observed == [start]


def test_backup_without_staffing_changes_does_not_hold_start(dispatch, scheduler):
    solver, start, _, observed = dispatch
    solver.tasks.append(SchedulerTask(scheduler.clock.now(), meta_data="副表内存收敛"))
    solver.run()
    assert observed == [start]
