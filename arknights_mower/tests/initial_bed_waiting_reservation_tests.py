"""首次分床和后续换班共用等待预约，不将当前恢复任务当作外部预约。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_group_tests as native
from arknights_mower.tests import group_dorm_migration_tests as roles
from arknights_mower.utils.plan import LogicExpression, Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    dorm_rebalance_signature,
    find_next_task,
    scheduling,
)

solver = native.solver
isolated_agent_history = roles.isolated_agent_history
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def waiting_destination(solver, target_source, restore):
    data = solver.op_data
    main = data.global_plan["default_plan"].plan
    main["central"] = [Room("克洛丝", "候补", ["梓兰"])]
    main["room_1_1"] = [Room("芬", "独立", ["香草"])]
    main["dormitory_2"] = [Room("Free", "", []) for _ in range(5)]
    assert data.swap_plan([], refresh=True) is None
    native.apply_plan(
        solver,
        {
            "central": ["克洛丝"],
            "room_1_1": ["香草"],
            "dormitory_2": ["Current", "Current", "Current", "Current", "芬"],
        },
    )
    for name in data.groups["联动"]:
        data.operators[name].mood = 5
    assert data.group_is_resting("独立")
    protected = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "dormitory_2": [
                "克洛丝" if target_source == "plan" else "Current",
                *["Current"] * 4,
            ]
        },
    )
    protected.group_shift_waiting = {"独立"}
    protected.group_shift_predecessors = ()
    if target_source == "expected":
        protected.group_shift_expected = {("dormitory_2", 0): "克洛丝"}
    if restore:
        protected = pickle.loads(pickle.dumps(protected))
    solver.waiting_group_shifts, solver.tasks, solver.task = [protected], [], None
    return solver, data, protected


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_ordinary_first_admission_keeps_waiting_bed(waiting_destination):
    scheduler, data, protected = waiting_destination
    before = pickle.dumps(protected)
    positions = native_positions(data)
    plan, admissions = {}, {}

    assert scheduler.get_resting_plan(
        data.groups["联动"].copy(), [], plan, 0, dorm_admissions=admissions
    )

    assert ("dormitory_2", 0) not in admissions
    assert {admissions[("dormitory_2", index)] for index in (1, 2, 3)} == {
        "伊内丝",
        "银灰",
        "讯使",
    }
    assert native_positions(data) == positions
    assert pickle.dumps(protected) == before


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_requested_departure_keeps_waiting_bed_after_reordering(waiting_destination):
    scheduler, data, protected = waiting_destination
    current = SchedulerTask(
        task_type=TaskTypes.EXHAUST_OFF, meta_data="伊内丝,银灰,讯使"
    )
    scheduler.task, scheduler.tasks = current, [current]
    before, positions = pickle.dumps(protected), native_positions(data)

    scheduler.overtake_room()

    departures = [task for task in scheduler.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert len(departures) == 1
    final = data.project_arrangements([departures[0].plan])
    assert final.get_current_operator("dormitory_2", 0) is None
    assert all(
        final.operators[name].is_resting() for name in ("伊内丝", "银灰", "讯使")
    )
    assert native_positions(data) == positions
    assert pickle.dumps(protected) == before


def native_positions(data):
    return {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_backup_first_admission_stays_safe_through_final_preparation(
    waiting_destination,
):
    scheduler, data, protected = waiting_destination
    previous, beds = deepcopy(data.plan), deepcopy(data.all_dorms())
    layout = dorm_rebalance_signature(data)
    data.global_plan["backup_plans"].append(
        Plan(
            {},
            PlanConfig("", "", ""),
            trigger=LogicExpression("True", "==", "True"),
            task={"meeting": ["陈", "初雪"], "contact": ["红"]},
        )
    )
    assert data.swap_plan([True], refresh=True) is None
    before, positions = pickle.dumps(protected), native_positions(data)

    plan = scheduler._backup_transition_plan(previous, [False], [True], beds, layout)

    assert plan is not None
    projected = data.project_arrangements([plan])
    assert projected.get_current_operator("dormitory_2", 0) is None
    assert all(
        projected.operators[name].is_resting() for name in ("伊内丝", "银灰", "讯使")
    )
    task = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan=plan,
        time=datetime.now() - timedelta(minutes=1),
    )
    task.backup_explicit_slots = scheduler._backup_explicit_slots([False], [True])
    priority = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, time=datetime.now() + timedelta(minutes=9)
    )
    scheduler.tasks, scheduler.task = [task, priority], task
    scheduling(scheduler.tasks, op_data=data)
    assert find_next_task(scheduler.tasks, datetime.now(), op_data=data) is task
    scheduler._prepare_group_shift(task)
    scheduler._prepare_shift_cycle(task)
    scheduler._activate_shift_backup(task)
    scheduler._prepare_group_shift(task, remember_targets=True)
    final = scheduler.op_data.project_arrangements([task.plan])
    assert final.get_current_operator("dormitory_2", 0) is None
    assert all(
        final.operators[name].is_resting() for name in ("伊内丝", "银灰", "讯使")
    ), plan
    assert native_positions(scheduler.op_data) == positions
    assert pickle.dumps(protected) == before
    scheduler.enter_room.assert_not_called()


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_waiting_departure_does_not_reserve_against_itself(
    waiting_destination, restore
):
    scheduler, data, protected = waiting_destination
    request = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "初雪"], "contact": ["红"]},
        time=datetime.now() - timedelta(minutes=2),
    )
    request.group_shift_waiting, request.group_shift_predecessors = set(), ()
    scheduler.waiting_group_shifts.insert(0, request)
    independent = SchedulerTask(task_type=TaskTypes.CLUE)
    scheduler.tasks, scheduler.task = [independent], independent
    if restore:
        scheduler.tasks, scheduler.waiting_group_shifts = pickle.loads(
            pickle.dumps((scheduler.tasks, scheduler.waiting_group_shifts))
        )
        independent = scheduler.tasks[0]
        request, protected = scheduler.waiting_group_shifts
        scheduler.task = independent
    at, positions, before = (
        request.time,
        native_positions(data),
        pickle.dumps(protected),
    )

    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
        assert scheduler.waiting_group_shifts == [protected]
        assert sum(task is request for task in scheduler.tasks) == 1
        assert any(task is independent for task in scheduler.tasks)
        assert scheduler.task is independent
        assert request.time == at
        final = data.project_arrangements([request.plan])
        assert final.get_current_operator("dormitory_2", 0) is None
        assert all(
            final.operators[name].is_resting() for name in ("伊内丝", "银灰", "讯使")
        )
        assert native_positions(data) == positions
        assert pickle.dumps(protected) == before


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("entry", ["ordinary", "departed"])
def test_first_admission_remains_atomic_until_reserved_capacity_is_released(
    waiting_destination, entry
):
    scheduler, data, protected = waiting_destination
    protected.plan["dormitory_2"][1:4] = ["泥岩", "能天使", "年"]
    before, positions = pickle.dumps(protected), native_positions(data)
    original = (
        {"meeting": ["陈", "初雪"], "contact": ["红"]} if entry == "departed" else {}
    )
    plan = deepcopy(original)

    def admit():
        if entry == "departed":
            return scheduler._complete_departed_recovery(
                plan, ["伊内丝", "银灰", "讯使"]
            )
        return scheduler.get_resting_plan(data.groups["联动"].copy(), [], plan, 0)

    assert not admit()
    assert plan == original
    assert native_positions(data) == positions
    assert pickle.dumps(protected) == before
    protected.plan["dormitory_2"][1:4] = ["Current"] * 3

    assert admit()
    rearrangement = (
        scheduler._reorder_dorm_recovery(plan) if entry == "ordinary" else {}
    )
    final = data.project_arrangements([plan, rearrangement])
    assert final.get_current_operator("dormitory_2", 0) is None
    assert all(
        final.operators[name].is_resting() for name in ("伊内丝", "银灰", "讯使")
    ), plan
    assert native_positions(data) == positions
