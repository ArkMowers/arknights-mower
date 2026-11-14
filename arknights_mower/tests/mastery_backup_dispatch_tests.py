"""副表实际换人完成后才派发待开始的专精，保留原任务及时间。"""

from datetime import timedelta

import jsonpickle
import pytest

from arknights_mower.tests import backup_snapshot_tests as snapshots
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
backup_solver = snapshots.solver


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
    backup.plan = {}
    backup.__dict__.pop("execution_failure", None)
    solver.task = backup
    solver.infra_main()
    assert not getattr(start, "mastery_backup_predecessors", ())
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


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("status", ["training", "waiting_collect"])
@pytest.mark.parametrize("schedule_collect", [False, True])
def test_waiting_start_becomes_collection_without_old_backup_hold(
    dispatch, scheduler, restore, status, schedule_collect
):
    from arknights_mower.solvers.mastery_reader import _schedule_collect

    solver, start, state, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    solver.tasks.append(backup)
    solver.run()
    assert observed[-1] is backup
    solver._retain_failed_task(backup, "驻员未确认", ["central"])
    state["status"] = status
    solver.task = None
    if schedule_collect:
        _schedule_collect(
            solver,
            {**state, "char_name": "学员", "skill_index": 0, "target_level": 1},
            scheduler.clock.now(),
        )
        assert not getattr(start, "mastery_backup_predecessors", ())
    if restore:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        start = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
        backup = next(t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION)
    solver.run()
    assert observed[-1] is start
    assert not getattr(start, "mastery_backup_predecessors", ())
    assert any(task is backup for task in solver.tasks)
    assert backup.execution_failure
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("backup_age", [0, 20])
def test_overdue_cleanup_retains_unfinished_backup_dependency(
    dispatch, scheduler, restore, backup_age
):
    solver, start, _, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    solver.tasks.append(backup)
    solver.run()
    assert observed[-1] is backup
    if restore:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        start = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
        backup = next(t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION)
    original_time = start.time, backup.time
    scheduler.clock.current += timedelta(minutes=backup_age)
    for _ in range(3):
        stale = SchedulerTask(
            scheduler.clock.now() - timedelta(minutes=20),
            task_type=TaskTypes.SHIFT_OFF,
        )
        solver.tasks.append(stale)
        solver.run()
        assert any(task is backup for task in solver.tasks)
        assert all(task is not stale for task in solver.tasks)
        assert observed[-1] is backup
        assert (start.time, backup.time) == original_time
        assert backup.plan == {"central": ["阿米娅"]}
    scheduler.io.assert_not_called()


def test_missing_unresolved_backup_is_not_treated_as_completed(dispatch, scheduler):
    solver, start, _, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    solver.tasks.append(backup)
    solver.run()
    solver.tasks.remove(backup)
    assert start not in task_view(solver.tasks, TaskScope.DISPATCH)
    solver.run()
    assert observed[-1] is backup
    assert any(task is backup for task in solver.tasks)
    scheduler.io.assert_not_called()


def test_replanning_restores_missing_unresolved_backup(dispatch, scheduler):
    solver, start, _, _ = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["阿米娅"]},
        meta_data="副表内存收敛",
    )
    start.mastery_backup_predecessors = (backup,)
    tasks = replan_update_tasks({"tasks": solver.tasks})["tasks"]
    assert any(task is backup for task in tasks)
    assert start not in task_view(tasks, TaskScope.DISPATCH)


@pytest.mark.parametrize("restore", [False, True])
def test_new_backup_transfers_dependency_to_final_arrangement(backup_solver, restore):
    solver = backup_solver
    data = solver.op_data
    data.backup_plans[0].task = {"meeting": ["砾"]}
    data.operators["伊内丝"].mood = 5
    previous = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"meeting": ["陈"]},
        meta_data="副表内存收敛",
    )
    start = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    start.plan_key = "17"
    start.mastery_backup_predecessors = (previous,)
    solver.tasks = [previous, start]
    assert solver.backup_plan_solver()
    final = next(task for task in solver.tasks if task.plan)
    assert all(task is not previous for task in solver.tasks)
    assert len(start.mastery_backup_predecessors) == 1
    assert start.mastery_backup_predecessors[0] is final
    if restore:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        start = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
        final = next(t for t in solver.tasks if t.plan)
        assert len(start.mastery_backup_predecessors) == 1
        assert start.mastery_backup_predecessors[0] is final
    assert start not in task_view(solver.tasks, TaskScope.DISPATCH)
    assert all(
        task is not previous
        for task in replan_update_tasks({"tasks": solver.tasks})["tasks"]
    )


def test_complete_shift_transfers_consumed_backup_dependency(backup_solver):
    solver = backup_solver
    solver.op_data.backup_plans = []
    previous = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_1_1": ["香草"]},
        meta_data="副表内存收敛",
    )
    final = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"meeting": ["陈"]},
    )
    start = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    start.mastery_backup_predecessors = (previous,)
    solver.tasks = [previous, final, start]
    solver.task = final
    solver._prepare_shift_cycle(final)
    assert all(task is not previous for task in solver.tasks)
    assert len(start.mastery_backup_predecessors) == 1
    assert start.mastery_backup_predecessors[0] is final
    assert start not in task_view(solver.tasks, TaskScope.DISPATCH)


def test_validly_cancelled_backup_releases_start_at_completion(dispatch, scheduler):
    solver, start, _, observed = dispatch
    backup = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.RE_ORDER,
        task_plan={"dormitory_1": ["Current", "阿米娅"]},
        meta_data="副表内存收敛",
    )
    backup.backup_retention_admissions = {"阿米娅"}
    solver.tasks.append(backup)
    solver.run()
    assert observed[-1] is backup
    solver.op_data.is_free_room_excluded = lambda name: False
    solver._cancel_stale_retention_admissions()
    assert backup.plan == {}
    assert start not in task_view(solver.tasks, TaskScope.DISPATCH)
    solver.task = backup
    solver.infra_main()
    assert all(task is not backup for task in solver.tasks)
    assert not getattr(start, "mastery_backup_predecessors", ())
    solver.run()
    assert observed[-1] is start
    scheduler.io.assert_not_called()
