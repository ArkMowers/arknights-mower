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
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = multi_group.solver
dorm_solver = multi_group.dorm_solver
free_dorm_solver = multi_group.free_dorm_solver

pytestmark = pytest.mark.usefixtures("offline_maintenance")

PRODUCTS = [("制造站", "gold", "exp3"), ("贸易站", "lmd", "orundum")]


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


def test_unavailable_cover_and_protected_primary_roll_back(solver, monkeypatch):
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n == SHARED
    )
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
def test_protected_replacements_defer_while_shared_primary_is_required(
    solver, monkeypatch, blocking
):
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
    before = recovery(solver)
    plan = transition(solver)
    assert plan == {}
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.group_is_resting("甲")
    assert recovery(solver) == before


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


@pytest.mark.parametrize("full_cycle", [False, True])
@pytest.mark.parametrize("target", [SHARED, "黑角"])
def test_explicit_backup_task_retains_control(solver, full_cycle, target):
    assert shift_off(solver, "甲")[0]
    for bed in solver.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
            solver.op_data.operators[bed.name].mood = 5
    bp = backup(solver)
    bp.task = {"contact": [target]}
    assert transition(solver) == {"contact": [target]}
    task = next(t for t in solver.tasks if t.plan)
    solver.task = task
    solver._prepare_group_shift(task)
    if full_cycle:
        solver._prepare_shift_cycle(task)
        solver._defer_conflicting_product_shift_slots(task)
        solver._switch_products_before_arrangement(task)
        solver._activate_shift_backup(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["contact"] == [target]
    assert solver.op_data.group_is_resting("甲")
    assert solver.op_data.operators[SHARED].is_resting()


@pytest.mark.parametrize("explicit_current", [False, True])
@pytest.mark.parametrize("target", [SHARED, "黑角"])
def test_explicit_backup_survives_ordinary_task_coalescing(
    solver, explicit_current, target
):
    assert shift_off(solver, "甲")[0]
    for bed in solver.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
            solver.op_data.operators[bed.name].mood = 5
    bp = backup(solver)
    bp.task = {"contact": [target]}
    assert transition(solver) == {"contact": [target]}
    explicit = next(t for t in solver.tasks if t.plan)
    ordinary = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"contact": ["砾"]}
    )
    solver.tasks = [explicit, ordinary]
    solver.task = task = explicit if explicit_current else ordinary
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._activate_shift_backup(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["contact"] == [target]
    assert solver.tasks == [task]
    assert solver.op_data.group_is_resting("甲")


@pytest.mark.parametrize("full_cycle", [False, True])
@pytest.mark.parametrize("target", [SHARED, "黑角"])
def test_projected_backup_explicit_task_survives_final_revalidation(
    solver, full_cycle, target
):
    assert shift_off(solver, "甲")[0]
    for bed in solver.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
            solver.op_data.operators[bed.name].mood = 5
    bp = backup(solver)
    bp.task = {"contact": [target]}
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task)
    if full_cycle:
        solver._prepare_shift_cycle(task)
    else:
        solver._prepare_shift_backup(task)
    assert solver.op_data.plan_condition == [False]
    solver._activate_shift_backup(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["contact"] == [target]
    assert solver.op_data.group_is_resting("甲")


def test_explicit_shared_return_survives_partial_group_return_retry(solver):
    import pickle

    shared = solver.global_plan["default_plan"].plan["contact"][0]
    shared.group_bindings[0]["replacement"] = ["红"]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    bp = backup(solver)
    bp.task = {"contact": [SHARED], "meeting": [A, "Current"]}
    assert transition(solver)["contact"] == [SHARED]
    task = next(t for t in solver.tasks if t.plan)
    solver.task = task
    solver._prepare_group_shift(task, remember_targets=True)
    data = solver.op_data
    observed = data.project_arrangements([{"meeting": [A, "Current"]}])
    data.operators, data.dorm = observed.operators, observed.dorm
    assert not solver._complete_group_shift(task)
    assert task.plan == {"contact": [SHARED]}
    assert data.group_is_resting("甲") and data.group_is_resting("乙")
    task = pickle.loads(pickle.dumps(task))
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan == {"contact": [SHARED]}
    observed = data.project_arrangements([task.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")
    assert data.group_is_resting("乙")


def test_explicit_other_slot_still_reserves_its_operator(solver):
    assert shift_off(solver, "甲")[0]
    plan = {"meeting": ["红", "Current"], "contact": [SHARED]}
    assert not solver.op_data.normalize_shared_arrangement(
        plan, explicit_slots={("meeting", 0)}
    )
    assert plan == {"meeting": ["红", "Current"], "contact": [SHARED]}


@pytest.mark.parametrize("alternative", [False, True])
def test_explicit_shared_slot_does_not_bypass_other_shared_matching(
    solver, alternative
):
    candidates = ["红", "黑角"]
    solver.global_plan["default_plan"].plan["factory"] = [
        Room(
            "梅尔",
            "甲",
            candidates,
            group_bindings=[{"group": "乙", "replacement": candidates}],
        )
    ]
    assert solver.initialize_operators() is None
    data = solver.op_data
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
    if not alternative:
        data.operators["黑角"]._current_room = "room_2_1"
        data.operators["黑角"].current_index = 0
    data.commit_group_shifts({"甲": True, "乙": True})
    plan = {"contact": ["红"], "factory": ["梅尔"]}
    assert (
        data.normalize_shared_arrangement(plan, explicit_slots={("contact", 0)})
        is alternative
    )
    assert plan["contact"] == ["红"]
    assert plan["factory"] == (["黑角"] if alternative else ["梅尔"])


def test_backup_current_does_not_override_shared_revalidation(solver):
    assert shift_off(solver, "甲")[0]
    bp = backup(solver)
    bp.task = {"contact": ["Current"]}
    assert transition(solver) == {"contact": ["砾"]}
    task = next(t for t in solver.tasks if t.plan)
    task.plan["contact"] = [SHARED]
    solver._prepare_group_shift(task)
    assert task.plan["contact"] == ["砾"]


@pytest.mark.parametrize("available", [False, True])
def test_shift_projection_prefers_cover_before_primary(solver, available):
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
    if not available:
        with pytest.raises(multi_group.base_schedule.ProductSwitchDeferred):
            solver._prepare_shift_backup(task)
        assert solver.op_data.plan_condition == [False]
        return
    solver._prepare_shift_backup(task)
    if available:
        assert task.plan["contact"] == ["黑角"]
        assert task.plan["dormitory_1"][3] == SHARED
    else:
        assert task.plan["contact"] == [SHARED]
        assert SHARED not in task.plan["dormitory_1"]
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


def test_deferred_transition_retries_when_cover_becomes_available(solver, monkeypatch):
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n == SHARED
    )
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


@pytest.mark.parametrize("product_solver", PRODUCTS[:1], indirect=True)
def test_product_shortage_defers_shared_group_recall(product_solver, monkeypatch):
    s = product_solver
    assert shift_off(s, "甲")[0]
    for name in (A, SHARED):
        s.op_data.operators[name].mood = 0
        s.op_data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(hours=4)
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n == "砾"
    )
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    s.task = task
    before = recovery(s)
    with pytest.raises(multi_group.base_schedule.ProductSwitchDeferred):
        s._prepare_shift_cycle(task)
    assert s.op_data.group_is_resting("甲")
    assert recovery(s) == before


@pytest.mark.parametrize("blocking", ["busy", "reserved", "source_bed", "working"])
def test_recall_respects_primary_protection(solver, monkeypatch, blocking):
    s = solver
    assert shift_off(s, "甲")[0]
    backup(s, replacements=("黑角",))
    s.op_data.operators["黑角"].mood = 0
    if blocking == "busy":
        monkeypatch.setattr(
            multi_group.base_schedule, "_is_mastery_busy", lambda n: n == SHARED
        )
    elif blocking == "reserved":
        s.tasks = [SchedulerTask(task_plan={"factory": [SHARED]})]
    elif blocking == "source_bed":
        s.tasks = [
            SchedulerTask(
                task_plan={
                    "dormitory_1": ["Current", "Current", "Current", "Free", "Current"]
                }
            )
        ]
    else:
        apply(s, {"factory": [SHARED]})
    tasks = list(s.tasks)
    before = recovery(s)
    assert transition(s) == {}
    assert s.op_data.plan_condition == [False]
    assert s.tasks == tasks
    assert recovery(s) == before


@pytest.mark.parametrize("protected", [False, True])
def test_primary_recall_rebuilds_ordinary_return(solver, protected):
    s = solver
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.group, slot.group_bindings = "", []
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    apply(
        s,
        {
            "contact": ["红"],
            "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
        },
    )
    s.op_data.operators[SHARED].mood = 0
    due = datetime.now() + timedelta(hours=4)
    s.op_data.get_dorm_by_name(SHARED)[1].time = due
    backup(s, replacements=("陈",))
    s.op_data.operators["陈"].mood = 0
    pending = SchedulerTask(
        time=due, task_type=TaskTypes.SHIFT_ON, task_plan={"contact": [SHARED]}
    )
    if protected:
        pending.product_shift_locked = True
        pending.product_lock_names = {SHARED}
        pending.product_lock_slots = {("contact", 0)}
    s.tasks = [pending]
    plan = transition(s)
    assert s.op_data.plan_condition == [not protected]
    if protected:
        assert plan == {}
        assert pending in s.tasks
    else:
        assert plan == {"contact": [SHARED]}
        assert not any(t.type == TaskTypes.SHIFT_ON for t in s.tasks)
        apply(s, plan)
        assert SHARED not in recovery(s)


@pytest.mark.parametrize("protect_first", [False, True])
def test_shared_cover_matches_before_minimal_primary_recall(
    solver, monkeypatch, protect_first
):
    s = solver
    for slots in s.global_plan["default_plan"].plan.values():
        for slot in slots:
            slot.group, slot.group_bindings = "", []
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    apply(
        s,
        {
            "contact": ["红"],
            "meeting": ["陈", "Current"],
            "dormitory_1": ["Current", "Current", A, SHARED, "Current"],
        },
    )
    backup(s)
    meeting = deepcopy(s.op_data.plan["meeting"])
    meeting[0].replacement = ["砾"]
    s.op_data.backup_plans[0].plan["meeting"] = meeting
    if protect_first:
        monkeypatch.setattr(
            multi_group.base_schedule, "_is_mastery_busy", lambda n: n == A
        )
    plan = transition(s)
    assert s.op_data.plan_condition == [True]
    assigned = [plan["contact"][0], plan["meeting"][0]]
    assert assigned.count("砾") == 1
    assert sum(n in (A, SHARED) for n in assigned) == 1
    if protect_first:
        assert assigned == [SHARED, "砾"]


@pytest.mark.parametrize("product_solver", PRODUCTS[:1], indirect=True)
def test_product_change_keeps_explicit_staffing_priority(product_solver):
    s = product_solver
    assert shift_off(s, "甲")[0]
    s.op_data.backup_plans[0].task = {"room_1_2": [SHARED]}
    s.op_data.facility_states["room_1_2"] = {"product": "exp3"}
    assert transition(s) == {"room_1_2": [SHARED]}


def test_exit_defers_when_default_cover_and_primary_are_busy(solver, monkeypatch):
    assert shift_off(solver, "甲")[0]
    bp = backup(solver)
    apply(solver, transition(solver))
    solver.tasks = []
    solver.op_data.operators["红"]._current_room = "factory"
    solver.op_data.operators["红"].current_index = 0
    bp.trigger = LogicExpression("False", "==", "True")
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n == SHARED
    )
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
    solver.op_data.operators[SHARED].group_bindings[0]["replacement"] = ["红", "黑角"]
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


@pytest.fixture
def product_solver(solver, request, monkeypatch):
    monkeypatch.setattr(config.conf.product_switching, "enable", True)
    facility, default, target = request.param
    plan = solver.global_plan["default_plan"]
    slots = plan.plan.pop("contact")
    slots[0].facility, slots[0].product = facility, default
    plan.plan["room_1_2"] = slots
    plan.products = {"room_1_2": default}
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    solver.op_data.first_init = False
    bp = backup(solver, room="room_1_2")
    bp.plan["room_1_2"][0].product = target
    bp.products = {"room_1_2": target}
    return solver


@pytest.mark.parametrize("product_solver", PRODUCTS, indirect=True)
@pytest.mark.parametrize("working", [False, True])
@pytest.mark.parametrize("change_replacements", [False, True])
def test_product_entry_exit_preserve_primary_state(
    product_solver, working, change_replacements
):
    s = product_solver
    bp = s.op_data.backup_plans[0]
    if not change_replacements:
        bp.plan["room_1_2"][0].replacement = ["红"]
    if not working:
        assert shift_off(s, "甲")[0]
        for bed in s.op_data.all_dorms():
            if bed.name:
                bed.time = datetime.now() + timedelta(hours=4)
    before = recovery(s)
    default = s.op_data.products["room_1_2"]
    target = bp.products["room_1_2"]
    for active, product in [(True, target), (False, default)]:
        s.tasks = []
        bp.trigger = LogicExpression(str(active), "==", "True")
        s.op_data.facility_states["room_1_2"] = {"product": product}
        plan = transition(s)
        assert s.op_data.plan_condition == [active]
        assert s.op_data.products["room_1_2"] == product
        assert plan == (
            {"room_1_2": ["砾" if active else "红"]}
            if not working and change_replacements
            else {}
        )
        apply(s, plan)
        assert recovery(s) == before
        assert s.op_data.operators[SHARED].is_working() == working


@pytest.mark.parametrize("product_solver", PRODUCTS[:1], indirect=True)
def test_product_and_cover_change_survive_full_shift_cycle(product_solver):
    s = product_solver
    assert shift_off(s, "甲")[0]
    for name in (A, SHARED):
        s.op_data.operators[name].mood = 5
        s.op_data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(hours=4)
    before = recovery(s)
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    s.task = task
    s._prepare_shift_cycle(task)
    assert task.backup_shift_conditions == [True]
    assert task.plan["room_1_2"] == ["砾"]
    assert A not in task.plan.get("meeting", [])
    apply(s, task.plan)
    assert s.op_data.operators[SHARED].is_resting()
    assert recovery(s) == before


@pytest.mark.parametrize("product_solver", PRODUCTS[:1], indirect=True)
def test_product_change_waits_for_observation_and_available_cover(
    product_solver, monkeypatch
):
    s = product_solver
    assert shift_off(s, "甲")[0]
    before = recovery(s)
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n in ("砾", SHARED)
    )
    assert transition(s) == {}
    assert s.op_data.plan_condition == [False]
    pending = next(t for t in s.tasks if t.type == TaskTypes.SWITCH_PRODUCT)
    assert pending.pending_product_targets == {"room_1_2": "exp3"}
    assert recovery(s) == before
    s.op_data.facility_states["room_1_2"] = {"product": "exp3"}
    s.tasks.remove(pending)
    assert transition(s) == {}
    assert s.op_data.plan_condition == [False]
    assert recovery(s) == before
    monkeypatch.setattr(
        multi_group.base_schedule, "_is_mastery_busy", lambda n: n == SHARED
    )
    assert transition(s) == {"room_1_2": ["砾"]}
    assert s.op_data.plan_condition == [True]
    assert recovery(s) == before
