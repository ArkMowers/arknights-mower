"""专精前置经真实存档迁移后绑定原队列，等待任务不越过准入边界。"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.tests import mastery_backup_dispatch_tests as dispatch_tests
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    replan_update_tasks,
    task_view,
)

scheduler = dispatch_tests.scheduler
dispatch = dispatch_tests.dispatch


@pytest.fixture
def restart(dispatch, scheduler, monkeypatch, tmp_path):
    from arknights_mower.solvers import record
    from arknights_mower.utils import crash_recovery, mastery_db

    solver, start, _, observed = dispatch
    mower = scheduler.main
    original_data = solver.op_data
    original_data.backup_plans = []
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path / "state.db" if path.endswith(".db") else tmp_path,
    )
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    monkeypatch.setattr(mastery_db, "get_reconcile_plans", lambda: [])
    monkeypatch.setattr(config, "retired_backup_migrated", False)
    monkeypatch.setattr(config, "retired_backup_indices", {})
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: solver)
    monkeypatch.setattr(
        mower, "_apply_version_update_resting_threshold", lambda *a: None
    )
    monkeypatch.setattr(mower, "get_server_time", scheduler.clock.now)

    class Restored(BaseException):
        pass

    def restored():
        raise Restored

    monkeypatch.setattr(mower, "refresh_resource_at_boundary", restored)

    def load(tasks, waiting=(), *, retired=False):
        now = scheduler.clock.now()
        saved = {
            "tasks": tasks,
            "waiting_group_shifts": list(waiting),
            "operators": {},
            "dorm": [],
            "backup_plan_names": ["专精副表"],
            "party_time": None,
            "daily_visit_friend": now.date(),
            "daily_report": now.date(),
            "daily_skland": now.date(),
            "daily_mail": now.date(),
            "task_count": 7,
        }
        assert record.save_state_to_db(saved)
        saved = record.load_state(strict=True)
        solver.tasks, solver.task = [], None
        solver.op_data = MagicMock(
            operators={},
            backup_plans=[] if retired else [SimpleNamespace(name="专精副表")],
            mood_calculation_enabled=False,
        )
        solver.op_data.validate_backup_plans.return_value = {"success": True}
        with pytest.raises(Restored):
            mower.simulate(saved)
        solver.op_data = original_data
        return saved

    return SimpleNamespace(
        load=load, solver=solver, start=start, observed=observed, clock=scheduler.clock
    )


def backup(now):
    task = SchedulerTask(
        now,
        task_plan={"central": ["阿米娅"]},
        task_type=TaskTypes.SELF_CORRECTION,
        meta_data="副表内存收敛",
    )
    task.backup_shift_conditions = [True]
    return task


@pytest.mark.parametrize("start_first", [False, True])
@pytest.mark.parametrize("orphan", [False, True])
def test_real_saved_restart_rebinds_start_to_migrated_predecessor(
    restart, start_first, orphan
):
    previous = backup(restart.clock.now())
    start = restart.start
    start.mastery_backup_predecessors = (previous,)
    tasks = [start, previous] if start_first else [previous, start]
    if orphan:
        tasks = [start]
    saved = restart.load(tasks)
    solver = restart.solver
    current = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
    owner = next(t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION)
    assert current.mastery_backup_predecessors[0] is owner
    assert current is not next(
        t for t in saved["tasks"] if t.type == TaskTypes.SKILL_UPGRADE
    )
    for _ in range(3):
        solver.handle_error(True)
        assert sum(t.type == TaskTypes.SELF_CORRECTION for t in solver.tasks) == 1
        assert current.mastery_backup_predecessors[0] is owner
        assert current not in task_view(solver.tasks, TaskScope.DISPATCH)
    owner.plan.clear()
    solver.task = owner
    solver.infra_main()
    assert not getattr(current, "mastery_backup_predecessors", ())
    solver.run()
    assert restart.observed[-1] is current


@pytest.mark.parametrize("location", ["active", "orphan", "waiting"])
def test_retired_predecessor_is_not_resurrected_after_real_restart(restart, location):
    previous = backup(restart.clock.now())
    start = restart.start
    start.mastery_backup_predecessors = (previous,)
    if location == "waiting":
        previous.group_shift_waiting = {"恢复组"}
    restart.load(
        [start, previous] if location == "active" else [start],
        [previous] if location == "waiting" else [],
        retired=True,
    )
    solver = restart.solver
    current = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
    assert not getattr(current, "mastery_backup_predecessors", ())
    assert not solver.waiting_group_shifts
    for _ in range(3):
        solver.handle_error(True)
        assert all(t.type != TaskTypes.SELF_CORRECTION for t in solver.tasks)
    solver.run()
    assert restart.observed[-1] is current


@pytest.mark.parametrize("restart_first", [False, True])
def test_suspended_predecessor_stays_waiting_until_group_release(
    restart, scheduler, restart_first
):
    solver, start = restart.solver, restart.start
    previous = backup(restart.clock.now())
    start.mastery_backup_predecessors = (previous,)
    independent = SchedulerTask(restart.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks = [start, previous, independent]
    solver._suspend_group_shift(previous, {"恢复组"})
    if restart_first:
        restart.load(solver.tasks, solver.waiting_group_shifts)
        start = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
        previous = solver.waiting_group_shifts[0]
        independent = next(t for t in solver.tasks if t.type == TaskTypes.DEPOT)
    assert start.mastery_backup_predecessors[0] is previous
    resting = {"value": True}
    solver.op_data.group_is_resting = lambda group: resting["value"]
    solver._prepare_group_shift = Mock()
    for _ in range(3):
        solver.run()
        assert all(t is not previous for t in solver.tasks)
        assert solver.waiting_group_shifts[0] is previous
        assert restart.observed[-1] is independent
    resting["value"] = False
    solver._resume_waiting_group_shifts()
    assert not solver.waiting_group_shifts
    assert sum(t is previous for t in solver.tasks) == 1
    assert start.mastery_backup_predecessors[0] is previous
    previous.plan.clear()
    solver.task = previous
    solver.infra_main()
    solver.run()
    assert restart.observed[-1] is start
    scheduler.io.assert_not_called()


def test_update_replanning_preserves_waiting_ownership(dispatch, scheduler):
    solver, start, _, _ = dispatch
    previous = backup(scheduler.clock.now())
    start.mastery_backup_predecessors = (previous,)
    solver.tasks = [start, previous]
    solver._suspend_group_shift(previous, {"恢复组"})
    saved = {"tasks": solver.tasks, "waiting_group_shifts": solver.waiting_group_shifts}
    for _ in range(3):
        saved = replan_update_tasks(saved)
        assert all(t is not previous for t in saved["tasks"])
        assert saved["waiting_group_shifts"][0] is previous
        assert start.mastery_backup_predecessors[0] is previous


@pytest.mark.parametrize("location", ["active", "both", "orphan"])
def test_restart_routes_suspended_predecessor_to_waiting_owner(restart, location):
    previous = backup(restart.clock.now())
    previous.group_shift_waiting = {"恢复组"}
    start = restart.start
    start.mastery_backup_predecessors = (previous,)
    restart.load(
        [start] if location == "orphan" else [start, previous],
        [previous] if location == "both" else [],
    )
    solver = restart.solver
    assert all(t.type != TaskTypes.SELF_CORRECTION for t in solver.tasks)
    assert len(solver.waiting_group_shifts) == 1
    owner = solver.waiting_group_shifts[0]
    current = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
    assert current.mastery_backup_predecessors[0] is owner
    solver.op_data.group_is_resting = lambda _: True
    for _ in range(3):
        solver.handle_error(True)
        solver._resume_waiting_group_shifts()
        assert all(t is not owner for t in solver.tasks)
        assert solver.waiting_group_shifts[0] is owner
        assert current not in task_view(solver.tasks, TaskScope.DISPATCH)


def test_restart_rebinds_merged_waiting_copy_to_earliest_owner(restart):
    early = SchedulerTask(
        restart.clock.now(),
        task_plan={"central": ["阿米娅"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    early.group_shift_waiting = {"恢复组"}
    later = SchedulerTask(
        restart.clock.now() + timedelta(seconds=2),
        task_plan={"central": ["阿米娅"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    later.group_shift_waiting = {"恢复组"}
    start = restart.start
    start.mastery_backup_predecessors = (later,)
    restart.load([start], [later, early])
    solver = restart.solver
    current = next(t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE)
    assert len(solver.waiting_group_shifts) == 1
    owner = solver.waiting_group_shifts[0]
    assert owner.time == early.time
    assert current.mastery_backup_predecessors[0] is owner
    solver.handle_error(True)
    assert all(t.type != TaskTypes.SHIFT_ON for t in solver.tasks)


def test_repeated_real_restart_preserves_distinct_equal_time_predecessors(restart):
    first, second = backup(restart.clock.now()), backup(restart.clock.now())
    assert first == second and first is not second
    start = restart.start
    start.mastery_backup_predecessors = (first, second)
    tasks = [start, first, second]
    for _ in range(3):
        restart.load(tasks)
        tasks = restart.solver.tasks
        current = next(t for t in tasks if t.type == TaskTypes.SKILL_UPGRADE)
        owners = [t for t in tasks if t.type == TaskTypes.SELF_CORRECTION]
        assert len(owners) == 2
        assert all(a is b for a, b in zip(current.mastery_backup_predecessors, owners))
        restart.solver.handle_error(True)
        assert sum(t.type == TaskTypes.SELF_CORRECTION for t in tasks) == 2
    owners[0].plan.clear()
    restart.solver.task = owners[0]
    restart.solver.infra_main()
    assert len(current.mastery_backup_predecessors) == 1
    assert current.mastery_backup_predecessors[0] is owners[1]
    assert current not in task_view(restart.solver.tasks, TaskScope.DISPATCH)


def test_new_start_registers_backup_already_in_waiting_area(dispatch, scheduler):
    solver, start, _, observed = dispatch
    previous = backup(scheduler.clock.now())
    independent = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks = [start, previous, independent]
    solver._suspend_group_shift(previous, {"恢复组"})
    solver.op_data.group_is_resting = lambda _: True
    solver.run()
    assert start.mastery_backup_predecessors[0] is previous
    assert all(t is not previous for t in solver.tasks)
    assert observed[-1] is independent


def test_update_replanning_places_orphan_suspended_predecessor_in_waiting(
    dispatch, scheduler
):
    _, start, _, _ = dispatch
    previous = backup(scheduler.clock.now())
    previous.group_shift_waiting = {"恢复组"}
    start.mastery_backup_predecessors = (previous,)
    saved = replan_update_tasks({"tasks": [start]})
    assert all(t is not previous for t in saved["tasks"])
    assert saved["waiting_group_shifts"][0] is previous
    assert start not in task_view(saved["tasks"], TaskScope.DISPATCH)
