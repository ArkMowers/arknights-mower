"""迁移避开的等待床位在简化换班和最终准入后仍须保留。"""

import inspect
import pickle
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import legacy_backup_dorm_migration_tests as migration
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    dorm_rebalance_signature,
    find_next_task,
    scheduling,
)

solver = migration.solver
isolated_agent_history = migration.isolated_agent_history
covered_group_bed = migration.covered_group_bed
waiting_migration = migration.waiting_migration
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.mark.parametrize("boundary", ["priority", "active_backup", "product_lock"])
@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_migration_keeps_waiting_bed_through_fast_cycle_and_both_admissions(
    waiting_migration, boundary, target_source, restore, monkeypatch
):
    scheduler, data, task, protected, target = migration.prepare_waiting_destination(
        waiting_migration, target_source, restore
    )
    if boundary == "active_backup":
        data.add(Operator("能天使", ""))
        data.operators["能天使"].mood = 12
    before, physical, at = (
        pickle.dumps(protected),
        migration.actual_state(data),
        task.time,
    )
    scheduler._resume_waiting_group_shifts(refresh_migrations_only=True)
    assert task.plan["dormitory_2"][1] == "讯使"
    if boundary == "priority":
        upcoming = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER, time=datetime.now() + timedelta(minutes=9)
        )
        scheduler.tasks.append(upcoming)
    elif boundary == "active_backup":
        active = SchedulerTask(
            task_type=TaskTypes.SELF_CORRECTION,
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "Current", "能天使"]
            },
        )
        active.backup_shift_active = True
        scheduler.tasks.append(active)
    else:
        task.product_shift_locked = True
    scheduling(scheduler.tasks, op_data=data)
    assert find_next_task(scheduler.tasks, datetime.now(), op_data=data) is task
    scheduler.task = task
    allocations = []
    allocate = base.prioritize_new_dorm_recovery

    def observe_allocation(*args, **kwargs):
        if inspect.currentframe().f_back.f_code.co_name == "_prepare_shift_cycle":
            allocations.append(dict(args[0].reserved_product_beds))
        return allocate(*args, **kwargs)

    monkeypatch.setattr(base, "prioritize_new_dorm_recovery", observe_allocation)

    scheduler._prepare_group_shift(task)
    scheduler._prepare_shift_cycle(task)
    scheduler._activate_shift_backup(task)
    scheduler._prepare_group_shift(task, remember_targets=True)

    final = scheduler.op_data.project_arrangements([task.plan])
    assert final.get_current_operator(*target) is None
    assert final.get_current_operator("dormitory_2", 1).name == "讯使"
    assert len(allocations) == 1
    if boundary == "product_lock":
        assert allocations[0]
    assert pickle.dumps(protected) == before
    assert scheduler.waiting_group_shifts == [protected]
    assert task.time == at
    assert migration.actual_state(scheduler.op_data) == physical
    scheduler.enter_room.assert_not_called()


@pytest.mark.parametrize("target_source", ["plan", "expected"])
def test_ordinary_backup_migration_respects_waiting_destination(
    covered_group_bed, solver, target_source
):
    data = solver.op_data
    data.global_plan["default_plan"].plan["dormitory_2"] = [
        Room("Free", "", []) for _ in range(5)
    ]
    assert data.swap_plan([], refresh=True) is None
    previous, beds = deepcopy(data.plan), deepcopy(data.all_dorms())
    layout = dorm_rebalance_signature(data)
    data.global_plan["backup_plans"].append(
        Plan(
            {
                "dormitory_1": [
                    Room("Current", "", []),
                    Room("Current", "", []),
                    Room("Current", "", []),
                    Room("年", "", []),
                    Room("Current", "", []),
                ]
            },
            PlanConfig("", "", ""),
        )
    )
    assert data.swap_plan([True], refresh=True) is None
    target = ("dormitory_2", 0)
    protected = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "dormitory_2": [
                "陈" if target_source == "plan" else "Current",
                *["Current"] * 4,
            ]
        },
    )
    protected.group_shift_waiting = {"联动"}
    if target_source == "expected":
        protected.group_shift_expected = {target: "陈"}
    solver.waiting_group_shifts = [protected]
    solver.tasks, solver.task = [], None
    before, physical = pickle.dumps(protected), migration.actual_state(data)

    plan = solver._backup_transition_plan(previous, [False], [True], beds, layout)

    assert plan is not None
    final = data.project_arrangements([plan])
    assert final.get_current_operator(*target) is None
    assert final.get_current_operator("dormitory_2", 1).name == "讯使"
    assert pickle.dumps(protected) == before
    assert migration.actual_state(data) == physical


@pytest.mark.parametrize("target_source", ["plan", "expected"])
def test_release_reorder_preserves_another_waiting_destination(
    covered_group_bed, solver, monkeypatch, target_source
):
    data = solver.op_data
    data.global_plan["default_plan"].plan["dormitory_2"] = [
        Room("Free", "", []) for _ in range(5)
    ]
    assert data.swap_plan([], refresh=True) is None
    apply_plan(
        solver, {"dormitory_2": ["Current", "讯使", "泥岩", "Current", "Current"]}
    )
    data.operators["讯使"].mood = 12
    data.operators["泥岩"].mood = 24
    target = ("dormitory_2", 0)
    protected = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "dormitory_2": [
                "陈" if target_source == "plan" else "Current",
                "Current",
                "Current",
                "Current",
                "Current",
            ]
        },
    )
    protected.group_shift_waiting = {"联动"}
    if target_source == "expected":
        protected.group_shift_expected = {target: "陈"}
    solver.waiting_group_shifts = [protected]
    release = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        meta_data="泥岩",
        task_plan={"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
    )
    solver.tasks, solver.task = [release], release
    before = pickle.dumps(protected)

    def arrange(plan, get_time):
        data.update_detail("泥岩", 24, "", -1, True)
        plan.clear()
        return True

    monkeypatch.setattr(solver, "agent_arrange", arrange)
    assert solver.arrange_release_dorm()[0] is True

    reorders = [task.plan for task in solver.tasks if task.type == TaskTypes.RE_ORDER]
    final = data.project_arrangements(reorders)
    assert final.get_current_operator(*target) is None
    assert final.get_current_operator("dormitory_2", 1).name == "讯使"
    assert data.get_current_operator("dormitory_2", 2) is None
    assert data.operators["陈"].current_room == "meeting"
    assert pickle.dumps(protected) == before
