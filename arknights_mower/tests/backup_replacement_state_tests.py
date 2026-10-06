"""Replacement-only backups preserve staffing state and recovery ownership."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import multi_group_shift_tests as multi_group
from arknights_mower.tests.multi_group_shift_tests import (
    SHARED,
    A,
    B,
    apply,
    shift_off,
)
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = multi_group.solver
dorm_solver = multi_group.dorm_solver
free_dorm_solver = multi_group.free_dorm_solver

pytestmark = pytest.mark.usefixtures("offline_maintenance")


def backup(solver, room="contact", replacements=("砾",), column=0):
    slots = deepcopy(solver.op_data.plan[room])
    if column:
        slots[0].group_bindings[column - 1]["replacement"] = list(replacements)
    else:
        slots[0].replacement = list(replacements)
    solver.op_data.backup_plans.append(
        Plan(
            {room: slots},
            PlanConfig("", "", ""),
            trigger=LogicExpression("True", "==", "True"),
        )
    )
    solver.op_data.plan_condition.append(False)
    return solver.op_data.backup_plans[-1]


def recovery(solver):
    return {
        bed.name: (bed.position, bed.time)
        for bed in solver.op_data.all_dorms()
        if bed.name
    }


def transition(solver):
    generated = []
    solver.backup_plan_solver(generated_tasks=generated)
    return next((t.plan for t in generated if t.plan), {})


@pytest.mark.parametrize("working", [False, True])
def test_entry_and_exit_preserve_primary_state(solver, working):
    if not working:
        assert shift_off(solver, "甲")[0]
        for bed in solver.op_data.dorm:
            if bed.name:
                bed.time = datetime.now() + timedelta(hours=4)
    before = recovery(solver)
    bp = backup(solver)
    plan = transition(solver)
    assert solver.op_data.plan_condition == [True]
    assert plan == ({} if working else {"contact": ["砾"]})
    apply(solver, plan)
    assert recovery(solver) == before
    assert (solver.op_data.operators[SHARED].current_room == "contact") == working
    solver.tasks = []
    bp.trigger = LogicExpression("False", "==", "True")
    plan = transition(solver)
    assert solver.op_data.plan_condition == [False]
    assert plan == ({} if working else {"contact": ["红"]})
    apply(solver, plan)
    assert recovery(solver) == before


def test_unavailable_cover_rolls_back_plan_and_queue(solver):
    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("黑角",))
    solver.op_data.operators["黑角"]._current_room = "factory"
    solver.op_data.operators["黑角"].current_index = 0
    pending = SchedulerTask(task_type=TaskTypes.DEPOT)
    solver.tasks = [pending]
    before = recovery(solver)
    assert transition(solver) == {}
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.operators[SHARED].replacement == ["红"]
    assert solver.tasks == [pending]
    assert recovery(solver) == before


@pytest.mark.parametrize("column", [0, 1])
def test_active_binding_is_retained(solver, column):
    assert shift_off(solver, "乙")[0]
    before = recovery(solver)
    backup(solver, column=column)
    plan = transition(solver)
    assert plan == ({} if column == 0 else {"contact": ["砾"]})
    apply(solver, plan)
    assert solver.op_data.operators[SHARED].group == "乙"
    assert recovery(solver) == before


@pytest.mark.parametrize("working", [False, True])
def test_dorm_primary_preserves_state(dorm_solver, working):
    s = dorm_solver
    if not working:
        assert shift_off(s, "甲")[0]
    before = recovery(s)
    backup(s, room="dormitory_1")
    plan = transition(s)
    assert plan == ({} if working else {"dormitory_1": ["砾", *["Current"] * 4]})
    apply(s, plan)
    assert recovery(s) == before
    assert s.op_data.get_current_operator("dormitory_1", 0).name == (
        "塑心" if working else "砾"
    )


@pytest.mark.parametrize("occupied", [False, True])
def test_free_dorm_cover_never_evicts_resident(free_dorm_solver, occupied):
    s = free_dorm_solver
    assert shift_off(s, "乙")[0]
    assert s.op_data.get_current_operator("dormitory_1", 0).name == B
    if not occupied:
        apply(s, {"dormitory_1": ["Free", "Current", B, "Current", "Current"]})
    before = recovery(s)
    backup(s, room="dormitory_1", column=1)
    plan = transition(s)
    assert s.op_data.plan_condition == [not occupied]
    if occupied:
        assert plan == {}
    else:
        assert plan["dormitory_1"][0] == "砾"
    apply(s, plan)
    assert recovery(s) == before


@pytest.mark.parametrize("blocking", ["busy", "reserved", "exhausted"])
def test_protected_replacements_defer(solver, monkeypatch, blocking):
    from arknights_mower.solvers import base_schedule

    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("黑角",))
    if blocking == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == "黑角"
        )
    elif blocking == "reserved":
        solver.tasks = [SchedulerTask(task_plan={"factory": ["黑角"]})]
    else:
        solver.op_data.operators["黑角"].mood = 0
    tasks = list(solver.tasks)
    assert transition(solver) == {}
    assert solver.op_data.plan_condition == [False]
    assert solver.tasks == tasks


@pytest.mark.parametrize("complete", [False, True])
def test_complete_matching_across_multiple_affected_slots(solver, complete):
    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("砾", "夜刀") if complete else ("砾",))
    meeting = deepcopy(solver.op_data.plan["meeting"])
    meeting[0].replacement = ["砾"]
    solver.op_data.backup_plans[0].plan["meeting"] = meeting
    plan = transition(solver)
    assert solver.op_data.plan_condition == [complete]
    assert plan == (
        {"contact": ["夜刀"], "meeting": ["砾", "Current"]} if complete else {}
    )


def test_explicit_backup_task_retains_control(solver):
    assert shift_off(solver, "甲")[0]
    bp = backup(solver)
    bp.task = {"contact": [SHARED]}
    assert transition(solver) == {"contact": [SHARED]}


@pytest.mark.parametrize("available", [False, True])
def test_shift_projection_changes_cover_without_recalling_primary(solver, available):
    from arknights_mower.solvers.base_schedule import ProductSwitchDeferred

    backup(solver, replacements=("黑角",))
    if not available:
        solver.op_data.operators["黑角"]._current_room = "factory"
        solver.op_data.operators["黑角"].current_index = 0
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "contact": ["红"],
            "dormitory_1": ["Current", "Current", A, SHARED, "Current"],
        },
    )
    original = deepcopy(task.plan)
    if available:
        solver._prepare_shift_backup(task)
        assert task.plan["contact"] == ["黑角"]
        assert task.plan["dormitory_1"][3] == SHARED
    else:
        with pytest.raises(ProductSwitchDeferred):
            solver._prepare_shift_backup(task)
        assert task.plan == original
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.operators[SHARED].current_room == "contact"


def test_full_shift_cycle_preserves_resting_group(solver):
    assert shift_off(solver, "甲")[0]
    for name in (A, SHARED):
        solver.op_data.operators[name].mood = 5
        solver.op_data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(
            hours=4
        )
    before = recovery(solver)
    backup(solver)
    generated = []
    solver.backup_plan_solver(generated_tasks=generated)
    task = next(t for t in generated if t.plan)
    solver.task = task
    solver._prepare_shift_cycle(task)
    assert task.plan["contact"] == ["砾"]
    assert A not in task.plan.get("meeting", [])
    apply(solver, task.plan)
    assert recovery(solver) == before


def test_matching_can_reassign_a_still_valid_cover(solver):
    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("红", "砾"))
    meeting = deepcopy(solver.op_data.plan["meeting"])
    meeting[0].replacement = ["红"]
    solver.op_data.backup_plans[0].plan["meeting"] = meeting
    assert transition(solver) == {"contact": ["砾"], "meeting": ["红", "Current"]}


def test_cover_swap_does_not_require_a_spare_operator(solver):
    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("陈",))
    meeting = deepcopy(solver.op_data.plan["meeting"])
    meeting[0].replacement = ["红"]
    solver.op_data.backup_plans[0].plan["meeting"] = meeting
    assert transition(solver) == {"contact": ["陈"], "meeting": ["红", "Current"]}


def test_dorm_to_free_retains_resting_group(dorm_solver):
    s = dorm_solver
    assert shift_off(s, "甲")[0]
    before = recovery(s)
    backup(s, room="dormitory_1", replacements=("Free",))
    plan = transition(s)
    assert s.op_data.plan_condition == [True]
    apply(s, plan)
    assert s.op_data.get_current_operator("dormitory_1", 0).name == "红"
    assert s.op_data.operators[A].is_resting()
    assert all(recovery(s)[name] == state for name, state in before.items())


def test_independent_standby_without_bed_remains_off_shift(solver):
    s = solver
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.group, slot.group_bindings = "", []
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
    apply(s, {"contact": ["红"]})
    backup(s)
    assert transition(s) == {"contact": ["砾"]}
    assert not s.op_data.operators[SHARED].current_room
    assert s.op_data.get_dorm_by_name(SHARED)[1] is None


def test_deferred_transition_retries_when_cover_becomes_available(solver):
    assert shift_off(solver, "甲")[0]
    backup(solver, replacements=("黑角",))
    solver.op_data.operators["黑角"]._current_room = "factory"
    solver.op_data.operators["黑角"].current_index = 0
    assert transition(solver) == {}
    assert solver.op_data.plan_condition == [False]
    solver.op_data.operators["黑角"]._current_room = ""
    solver.op_data.operators["黑角"].current_index = -1
    assert transition(solver) == {"contact": ["黑角"]}
    assert solver.op_data.plan_condition == [True]


def test_same_group_primary_cover_keeps_fixed_recovery(dorm_solver):
    s = dorm_solver
    s.global_plan["default_plan"].plan["dormitory_1"][0].replacement = [A]
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    assert shift_off(s, "甲")[0]
    assert s.op_data.get_current_operator("dormitory_1", 0).name == A
    bed = s.op_data.get_dorm_by_name(A)[1]
    bed.time = datetime.now() + timedelta(hours=4)
    before = recovery(s)
    backup(s, room="dormitory_1", replacements=(A, "砾"))
    assert transition(s) == {}
    assert s.op_data.plan_condition == [True]
    assert recovery(s) == before


def test_exit_defers_when_default_cover_is_busy(solver):
    assert shift_off(solver, "甲")[0]
    bp = backup(solver)
    apply(solver, transition(solver))
    solver.tasks = []
    solver.op_data.operators["红"]._current_room = "factory"
    solver.op_data.operators["红"].current_index = 0
    bp.trigger = LogicExpression("False", "==", "True")
    before = recovery(solver)
    assert transition(solver) == {}
    assert solver.op_data.plan_condition == [True]
    assert solver.op_data.get_current_operator("contact", 0).name == "砾"
    assert recovery(solver) == before


@pytest.mark.parametrize("resting", [False, True])
def test_new_same_group_primary_dorm_cover_respects_own_shift(dorm_solver, resting):
    s = dorm_solver
    assert shift_off(s, "甲")[0]
    if not resting:
        apply(s, {"meeting": [A, "Current"]})
    backup(s, room="dormitory_1", replacements=(A,))
    plan = transition(s)
    assert s.op_data.plan_condition == [resting]
    if resting:
        assert plan["dormitory_1"][0] == A
        apply(s, plan)
        assert s.op_data.operators[A].is_resting()
        assert s.op_data.get_dorm_by_name(A)[1].position == ("dormitory_1", 0)
    else:
        assert plan == {}
        assert s.op_data.operators[A].current_room == "meeting"


def test_explicit_other_slot_cannot_double_book_a_retained_cover(solver):
    assert shift_off(solver, "甲")[0]
    from arknights_mower.utils.resting_correction import preserve_backup_replacements

    solver.op_data.operators[SHARED].replacement = ["红", "黑角"]
    plan = {"factory": ["红"]}
    assert preserve_backup_replacements(
        solver.op_data,
        plan,
        {("contact", 0)},
        solver.op_data.all_dorms(),
        lambda _: False,
    )
    assert plan == {"factory": ["红"], "contact": ["黑角"]}


def test_unobserved_primary_uses_initial_correction(solver):
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index, op.time_stamp = "", -1, None
    backup(solver)
    assert transition(solver) == {"contact": [SHARED]}
    assert solver.op_data.plan_condition == [True]
