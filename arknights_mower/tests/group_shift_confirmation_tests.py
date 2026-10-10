"""换班确认保留有效目标，并允许预约所属任务和共同候补继续执行。"""

# ruff: noqa: E402

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.data import agent_list
from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_schedule import ProductSwitchDeferred
from arknights_mower.tests.multi_group_shift_tests import SHARED, A, B, shift_off
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_reorder,
)


@pytest.fixture
def shared_open_bed(solver):
    plans = solver.global_plan["default_plan"].plan
    plans["dormitory_1"][0] = Room(
        "塑心",
        "甲",
        ["Free"],
        group_bindings=[{"group": "乙", "replacement": ["Free"]}],
    )
    plans["contact"][0].replacement.append("黑角")
    plans["contact"][0].group_bindings[0]["replacement"] = ["红"]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    solver.op_data.operators["红"]._current_room = ""
    solver.op_data.operators["红"].current_index = -1
    return solver


@pytest.mark.parametrize("bed_first", [False, True])
@pytest.mark.parametrize("alternative", [False, True])
@pytest.mark.parametrize("resident", [False, True])
def test_named_shared_bed_participates_in_cover_matching(
    shared_open_bed, bed_first, alternative, resident
):
    from copy import deepcopy

    data = shared_open_bed.op_data
    if alternative:
        data.operators[SHARED].group_bindings[1]["replacement"].append("黑角")
    if bed_first:
        data.operators = dict(reversed(list(data.operators.items())))
    if resident:
        apply_plan = {"dormitory_1": ["红", *["Current"] * 4]}
        observed = data.project_arrangements([apply_plan])
        data.operators, data.dorm = observed.operators, observed.dorm
    plan = {
        "meeting": [A, "Current"],
        "contact": [SHARED],
        "dormitory_1": ["Current" if resident else "红", *["Current"] * 4],
    }
    before = deepcopy(plan)
    assert data.normalize_shared_arrangement(plan) is alternative
    if alternative:
        assert plan["contact"] == ["黑角"]
        projected = data.project_arrangements([plan])
        assert projected.get_current_operator("dormitory_1", 0).name == "红"
        assert projected.get_current_operator("contact", 0).name == "黑角"
    else:
        assert plan == before


def test_shared_bed_conflict_defers_without_losing_work_confirmation(shared_open_bed):
    solver = shared_open_bed
    data = solver.op_data
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            "meeting": [A, "Current"],
            "contact": [SHARED],
            "dormitory_1": ["红", *["Current"] * 4],
        },
    )
    task.backup_shift_active = True
    solver.task, solver.tasks = task, [task]
    with pytest.raises(ProductSwitchDeferred):
        solver._prepare_group_shift(task, remember_targets=True)
    assert data.group_is_resting("甲")
    assert not getattr(task, "group_shift_expected", {})
    # A newly available alternative resolves the conflict on the same task.
    data.operators[SHARED].group_bindings[1]["replacement"].append("黑角")
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected["contact", 0] == "黑角"
    assert task.group_shift_expected["dormitory_1", 0] == "红"
    observed = data.project_arrangements([task.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    data.operators["黑角"]._current_room = ""
    data.operators["黑角"].current_index = -1
    assert not solver._complete_group_shift(task)
    assert data.group_is_resting("甲")
    observed = data.project_arrangements([task.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")
    assert data.group_is_resting("乙")


@pytest.mark.parametrize("reserved", [False, True])
def test_available_common_cover_is_considered(solver, reserved):
    data = solver.op_data
    shared = data.operators[SHARED]
    shared.group_bindings[0]["replacement"] = ["红", "黑角"]
    shared.group_bindings[1]["replacement"] = ["红", "黑角"]
    shared.replacement = ["红", "黑角"]
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    # The queued first return still requests the shared primary. The current
    # cover has subsequently been taken by another facility; 黑角 is idle.
    data.operators["红"]._current_room = "factory"
    data.operators["红"].current_index = 0
    assert not data.operators["黑角"].current_room
    plan = {"meeting": [A, "Current"], "contact": [SHARED]}
    if reserved:
        data.reserved_product_replacements = {"黑角"}
        assert not data.normalize_shared_arrangement(plan)
        assert plan["contact"] == [SHARED]
        return
    assert data.normalize_shared_arrangement(plan)
    assert plan["contact"] == ["黑角"]


@pytest.mark.parametrize("recovered", [False, True])
@pytest.mark.parametrize("contact_confirmed", [False, True])
def test_released_recovery_target_does_not_block_completed_shift(
    solver, recovered, contact_confirmed
):
    data = solver.op_data
    data.config.operator_mood_limits[B] = {"lower": 0, "upper": 12}
    data.operators[B].mood = 5
    data.operators[B].upper_limit = 12
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", B, SHARED, "Current"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    # Other rooms finish while contact stays pending. A personal-limit release
    # may execute during the pending shift and legitimately remove this resident.
    observed = data.project_arrangements([task.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    data.operators[B].mood = 12 if recovered else 5
    data.operators[B].time_stamp = datetime.now()
    data.operators[B].rest_mood_release_limit = 12 if recovered else None
    data.operators[B]._current_room = ""
    data.operators[B].current_index = -1
    assert bool(data.rest_mood_complete(B)) is recovered
    task.plan = {}
    assert not solver._complete_group_shift(task)
    assert task.plan["dormitory_1"][2] == B
    task.backup_shift_active = True
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._prepare_group_shift(task, remember_targets=True)
    # The real selection boundary correctly discards this expired recovery
    # target, but confirmation must also forget that obsolete expectation.
    solver.preserve_resting_crafters = lambda agents, room: None
    solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
    assert task.plan["dormitory_1"][2] == ("Free" if recovered else B)
    if not contact_confirmed:
        data.operators["黑角"]._current_room = ""
        data.operators["黑角"].current_index = -1
    task.plan = {}
    assert solver._complete_group_shift(task) is (recovered and contact_confirmed)
    assert data.group_is_resting("乙") is (recovered and contact_confirmed)
    if not contact_confirmed:
        assert task.group_shift_expected[("contact", 0)] == "黑角"


@pytest.mark.parametrize("other_owner", [False, True])
def test_product_lock_owner_can_retry_its_own_shift(solver, other_owner):
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "contact": ["红"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task)
    solver._reserve_deferred_product_shift(task, {("meeting", 0), ("contact", 0)})
    if other_owner:
        other = SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF,
            task_plan={
                "meeting": ["陈", "Current"],
                "contact": ["红"],
            },
        )
        solver.tasks.append(other)
        solver._reserve_deferred_product_shift(other, {("meeting", 0), ("contact", 0)})
    solver._refresh_deferred_product_reservations()
    assert "红" in solver.op_data.reserved_product_replacements
    # A retry must reach the product-switch operation to release its own lock.
    reserved = set(solver.op_data.reserved_product_replacements)
    if other_owner:
        with pytest.raises(ProductSwitchDeferred):
            solver._prepare_group_shift(task)
    else:
        solver._prepare_group_shift(task)
        assert task.plan["contact"] == ["红"]
    assert solver.op_data.reserved_product_replacements == reserved


def test_fixed_dorm_target_at_personal_limit_still_requires_confirmation(solver):
    data = solver.op_data
    data.config.operator_mood_limits["塑心"] = {"lower": 0, "upper": 12}
    op = data.operators["塑心"]
    op.mood = op.upper_limit = 12
    op._current_room, op.current_index = "", -1
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]},
    )
    task.group_shift_transitions = {"甲": True}
    task.group_shift_expected = {("dormitory_1", 0): "塑心"}
    solver.task, solver.tasks = task, [task]
    solver.preserve_resting_crafters = lambda agents, room: None
    solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
    assert task.plan["dormitory_1"][0] == "塑心"
    assert not solver._complete_group_shift(task)
    assert task.group_shift_expected == {("dormitory_1", 0): "塑心"}


def test_common_alternatives_allow_complete_matching_across_shared_slots(solver):
    plan = solver.global_plan["default_plan"].plan
    plan["contact"][0].replacement = ["红", "黑角"]
    plan["contact"][0].group_bindings[0]["replacement"] = ["红", "黑角"]
    plan["factory"] = [
        Room(
            "褐果",
            "甲",
            ["红"],
            group_bindings=[{"group": "乙", "replacement": ["红"]}],
        )
    ]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
    proposed = {"meeting": ["陈", "初雪"], "contact": ["红"], "factory": ["红"]}
    assert solver.op_data.normalize_shared_arrangement(proposed)
    assert proposed["contact"] == ["黑角"]
    assert proposed["factory"] == ["红"]
    assert not solver.op_data.group_is_resting("甲")


@pytest.mark.parametrize("exhausted", [False, True])
def test_shared_revalidation_allows_zero_mood_cover(solver, exhausted):
    data = solver.op_data
    shared = data.operators[SHARED]
    for binding in shared.group_bindings:
        binding["replacement"] = ["红", "黑角"]
    shared.replacement = ["红", "黑角"]
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    data.operators["红"]._current_room = "factory"
    data.operators["红"].current_index = 0
    data.operators[B].mood = 5
    data.operators[SHARED].mood = 5
    data.operators["黑角"].mood = 0 if exhausted else 24
    data.operators["黑角"].time_stamp = datetime.now()
    assert data.replacement_exhausted("黑角") is exhausted
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "contact": [SHARED]},
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["contact"] == ["黑角"]


@pytest.mark.parametrize("backup_active", [False, True])
@pytest.mark.parametrize("entry", ["solver", "utility"])
def test_replan_keeps_unconfirmed_shared_return(solver, backup_active, entry):
    assert shift_off(solver, "甲")[0]
    data = solver.op_data
    for bed in data.dorm:
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=1)
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "contact": [SHARED]},
    )
    other = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["Current", "初雪"]}
    )
    solver.task, solver.tasks = task, [task, other]
    solver._reserve_deferred_product_shift(other, {("meeting", 1)})
    solver._refresh_deferred_product_reservations()
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._activate_shift_backup(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert not getattr(task, "backup_shift_active", False)
    partial = data.project_arrangements([{"meeting": [A, "Current"]}])
    data.operators, data.dorm = partial.operators, partial.dorm
    assert not solver._complete_group_shift(task)
    assert task.plan == {"contact": [SHARED]}
    assert data.group_is_resting("甲")
    solver.task = None
    task.backup_shift_active = backup_active
    retry_time = task.time
    expected = dict(task.group_shift_expected)
    if entry == "solver":
        solver.plan_metadata()
    else:
        solver.tasks = plan_metadata(data, solver.tasks)
    assert task.time == retry_time
    assert task.group_shift_expected == expected
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert data.group_is_resting("甲")
    assert data.get_current_operator("contact", 0).name == "红"
    assert correction == {}
    assert not solver.get_resting_plan(data.groups["乙"], [], {}, 0)
    assert task in solver.tasks, [(t.type, t.plan) for t in solver.tasks]
    # 其他读房确认共享主班已回岗，也不能在提交组状态前删除待完成任务。
    data.operators["红"]._current_room, data.operators["红"].current_index = "", -1
    data.operators[SHARED]._current_room, data.operators[SHARED].current_index = (
        "contact",
        0,
    )
    solver._cancel_pending_shift_on(SHARED)
    assert task in solver.tasks
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")
    assert task.group_shift_expected == {}
    task.backup_shift_active = False
    solver.plan_metadata()
    assert task not in solver.tasks


def observe_arrangement(solver, plan):
    """读屏只更新位置和床位，组状态仍由完成确认提交。"""
    observed = solver.op_data.project_arrangements([plan])
    solver.op_data.operators, solver.op_data.dorm = observed.operators, observed.dorm


@pytest.mark.parametrize("returning", [False, True])
def test_product_conflict_defers_complete_group_arrangement(solver, returning):
    if returning:
        assert shift_off(solver, "甲")[0]
        plan = {"meeting": [A, "Current"], "contact": [SHARED]}
    else:
        plan = {}
        assert solver.get_resting_plan(solver.op_data.groups["甲"], [], plan, 0)
        plan.update(try_reorder(solver.op_data, plan) or {})
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON if returning else TaskTypes.SHIFT_OFF,
        task_plan=plan,
    )
    locked = SchedulerTask(
        time=datetime.now() + timedelta(hours=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"]},
    )
    solver.task, solver.tasks = task, [task, locked]
    solver._reserve_deferred_product_shift(locked, {("meeting", 0)})
    solver._refresh_deferred_product_reservations()
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    original = {room: list(names) for room, names in task.plan.items()}
    with pytest.raises(ProductSwitchDeferred):
        solver._defer_conflicting_product_shift_slots(task)
    assert task.plan == original
    assert solver.tasks == [task, locked]
    assert not getattr(task, "group_shift_expected", {})
    assert solver.op_data.group_is_resting("甲") is returning

    # 预约任务不被待确认状态阻塞，预约解除后原换班仍完整执行并确认。
    solver._prepare_group_shift(locked)
    solver.tasks.remove(locked)
    solver._refresh_deferred_product_reservations()
    solver._defer_conflicting_product_shift_slots(task)
    solver._prepare_group_shift(task, remember_targets=True)
    observe_arrangement(solver, task.plan)
    task.plan = {}
    assert solver._complete_group_shift(task)
    assert solver.op_data.group_is_resting("甲") is not returning


def prepare_emergency_confirmation(solver):
    solver._emergency_handoff = True
    solver.emergency_state = {
        "targets": {A: 12},
        "phase": "returning",
        "handoff_observing": True,
    }
    solver._emergency_read_rooms = MagicMock(return_value=True)
    solver._emergency_ready = MagicMock(return_value=True)
    solver._emergency_save = MagicMock()
    solver.run_order_solver = MagicMock()
    solver.plan_metadata = MagicMock()


@pytest.mark.parametrize("returned", [False, True])
def test_emergency_handoff_commits_observed_group_state(solver, returned):
    assert shift_off(solver, "甲")[0]
    if returned:
        observe_arrangement(solver, {"meeting": [A, "Current"], "contact": [SHARED]})
    else:
        # 救急期间主班已离岗，但原有组状态仍为上班。
        solver.op_data.commit_group_shifts({"甲": False})
        for name in (A, SHARED):
            solver.op_data.operators[name].mood = 5
    prepare_emergency_confirmation(solver)
    assert solver._emergency_finish_handoff()
    assert solver.op_data.group_is_resting("甲") is not returned
    assert solver.emergency_state is None
    admitted = solver.get_resting_plan(solver.op_data.groups["乙"], [], {}, 0)
    assert bool(admitted) is returned


@pytest.mark.parametrize("blocked_by", ["read", "ready", "mood", "shared"])
def test_incomplete_emergency_handoff_preserves_group_state(solver, blocked_by):
    assert shift_off(solver, "甲")[0]
    plan = {"meeting": [A, "Current"]}
    if blocked_by != "shared":
        plan["contact"] = [SHARED]
    observe_arrangement(solver, plan)
    prepare_emergency_confirmation(solver)
    if blocked_by == "read":
        solver._emergency_read_rooms.return_value = False
        solver._emergency_defer_read = MagicMock()
    elif blocked_by == "ready":
        solver._emergency_ready.return_value = False
    elif blocked_by == "mood":
        solver.op_data.operators[A].mood = 0
    before = dict(solver.op_data.group_shift_state)
    assert not solver._emergency_finish_handoff()
    assert solver.op_data.group_shift_state == before
    assert solver.emergency_state is not None
    solver.run_order_solver.assert_not_called()
    solver.plan_metadata.assert_not_called()
    if blocked_by == "shared":
        observe_arrangement(solver, {"contact": [SHARED]})
        assert solver._emergency_finish_handoff()
        assert not solver.op_data.group_is_resting("甲")


@pytest.mark.parametrize("released", [False, True])
def test_shared_revalidation_protects_fixed_dorm_cover(solver, released):
    plan = solver.global_plan["default_plan"].plan
    plan["contact"][0].replacement = ["红", "黑角"]
    plan["contact"][0].group_bindings[0]["replacement"] = ["红", "黑角"]
    plan["central"] = [Room("能天使", "丙", ["夜刀"])]
    plan["dormitory_1"][1] = Room("冰酿", "丙", ["黑角"])
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    observe_arrangement(
        solver,
        {
            "central": ["夜刀"],
            "dormitory_1": ["Current", "黑角", "Current", "Current", "Current"],
        },
    )
    data = solver.op_data
    data.commit_group_shifts({"丙": True})
    data.operators["红"]._current_room, data.operators["红"].current_index = (
        "factory",
        0,
    )
    assert data.is_dorm_replacement("黑角")
    proposed = {"meeting": [A, "Current"], "contact": [SHARED]}
    if released:
        proposed.update(
            central=["能天使"],
            dormitory_1=["Current", "冰酿", "Current", "Current", "Current"],
        )
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=proposed)
    solver.task, solver.tasks = task, [task]
    if released:
        solver._prepare_group_shift(task, remember_targets=True)
        assert task.plan["contact"] == ["黑角"]
        assert task.plan["dormitory_1"][1] == "冰酿"
        assert task.group_shift_expected["dormitory_1", 1] == "冰酿"
    else:
        with pytest.raises(ProductSwitchDeferred):
            solver._prepare_group_shift(task)
        assert task.plan["contact"] == [SHARED]
    assert data.get_current_operator("dormitory_1", 1).name == "黑角"
    assert data.group_is_resting("丙")


@pytest.mark.parametrize("contact_confirmed", [False, True])
def test_cap_cancellation_relocates_other_pending_dorm_targets(
    solver, contact_confirmed
):
    data = solver.op_data
    data.config.operator_mood_limits[B] = {"lower": 0, "upper": 12}
    data.config.free_blacklist = [
        name for name in agent_list if name not in {B, SHARED, "塑心", "冰酿"}
    ]
    data.operators[B].upper_limit = 12
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["塑心", "冰酿", B, SHARED, "Free"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    observe_arrangement(solver, task.plan)
    data.operators[B].mood = 12
    data.operators[B].time_stamp = datetime.now()
    data.operators[B].rest_mood_release_limit = 12
    data.get_dorm_by_name(B)[1].reset()
    data.operators[B]._current_room, data.operators[B].current_index = "", -1

    solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")

    assert task.plan["dormitory_1"] == ["塑心", "冰酿", SHARED, "", ""]
    assert task.group_shift_expected["dormitory_1", 2] == SHARED
    assert ("dormitory_1", 3) not in task.group_shift_expected
    assert B not in task.group_shift_expected.values()
    assert task.group_shift_expected["dormitory_1", 0] == "塑心"
    assert task.group_shift_expected["dormitory_1", 1] == "冰酿"
    # 单回临时名单中的第一个位置不能覆盖最终恢复床位。
    final_targets = dict(task.group_shift_expected)
    solver.prepare_dorm_selection([SHARED], "dormitory_1", preserve_dorm_occupants=True)
    assert task.group_shift_expected == final_targets
    observe_arrangement(solver, {"dormitory_1": task.plan["dormitory_1"]})
    if not contact_confirmed:
        data.operators["黑角"]._current_room, data.operators["黑角"].current_index = (
            "",
            -1,
        )
    task.plan.clear()
    assert solver._complete_group_shift(task) is contact_confirmed
    assert data.group_is_resting("乙") is contact_confirmed
    if not contact_confirmed:
        assert task.plan == {"contact": ["黑角"]}


@pytest.mark.parametrize("backup_active", [False, True])
@pytest.mark.parametrize("entry", ["solver", "utility"])
def test_pending_confirmation_refreshes_personal_limit_releases(
    solver, backup_active, entry
):
    data = solver.op_data
    data.config.operator_mood_limits[B] = {"lower": 0, "upper": 12}
    data.operators[B].upper_limit = 12
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", B, SHARED, "Current"],
        },
    )
    unrelated = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="meeting")
    solver.task, solver.tasks = task, [task, unrelated]
    solver._prepare_group_shift(task, remember_targets=True)
    observe_arrangement(
        solver, {room: row for room, row in task.plan.items() if room != "contact"}
    )
    data.operators[B].mood = 5
    data.operators[B].time_stamp = datetime.now()
    deadline = datetime.now() + timedelta(minutes=20)
    data.get_dorm_by_name(B)[1].time = deadline
    assert not solver._complete_group_shift(task)
    task.backup_shift_active = backup_active
    pending_plan = {room: list(row) for room, row in task.plan.items()}
    expected = dict(task.group_shift_expected)
    retry_time = task.time

    def rebuild():
        if entry == "solver":
            solver.plan_metadata()
        else:
            solver.tasks = plan_metadata(data, solver.tasks)
        assert task in solver.tasks and unrelated in solver.tasks
        assert task.plan == pending_plan and task.time == retry_time
        assert task.group_shift_expected == expected
        assert not data.group_is_resting("乙")
        return [queued for queued in solver.tasks if queued.strict_mood_limit]

    (release,) = rebuild()
    assert release.meta_data == B
    assert release.time == deadline
    assert release.plan == {
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"]
    }
    assert rebuild() == [release]
    # 失败重试的清退任务沿用原对象和重试时间，不能被换班保护重置。
    release.time += timedelta(minutes=1)
    assert rebuild()[0] is release
    assert release.time == deadline + timedelta(minutes=1)
    # 新实读改变恢复期限时刷新清退；已离宿时移除过期清退。
    data.get_dorm_by_name(B)[1].time = deadline + timedelta(minutes=5)
    (updated,) = rebuild()
    assert updated is not release
    assert updated.time == deadline + timedelta(minutes=5)
    observe_arrangement(
        solver, {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}
    )
    assert rebuild() == []


@pytest.mark.parametrize("overdue", [False, True])
@pytest.mark.parametrize("backup_active", [False, True])
def test_timeout_cleanup_keeps_partial_group_return(solver, overdue, backup_active):
    assert shift_off(solver, "甲")[0]
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "contact": [SHARED]},
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    observe_arrangement(solver, {"meeting": [A, "Current"]})
    assert not solver._complete_group_shift(task)
    task.backup_shift_active = backup_active
    task.time = datetime.now() + timedelta(minutes=-20 if overdue else 5)
    retry_time, expected = task.time, dict(task.group_shift_expected)
    stale = SchedulerTask(
        time=datetime.now() - timedelta(minutes=20), task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks.append(stale)
    solver.error = False
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.task = None

    solver.handle_error(force=True)
    solver.plan_metadata()
    assert any(queued is task for queued in solver.tasks)
    assert all(queued is not stale for queued in solver.tasks)
    assert task.time == retry_time and task.group_shift_expected == expected
    assert task.plan == {"contact": [SHARED]}
    assert solver.op_data.group_is_resting("甲")
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    observe_arrangement(solver, task.plan)
    task.plan.clear()
    assert solver._complete_group_shift(task)
    assert not solver.op_data.group_is_resting("甲")


@pytest.mark.parametrize("protection", ["group_shift_expected", "backup_shift_active"])
def test_unfinished_shift_alone_does_not_trigger_timeout_rebuild(solver, protection):
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=20),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"contact": [SHARED]},
    )
    setattr(
        task,
        protection,
        {("contact", 0): SHARED} if protection == "group_shift_expected" else True,
    )
    ordinary = SchedulerTask(
        time=datetime.now() + timedelta(minutes=10), task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks = [task, ordinary]
    queue = solver.tasks
    solver.error = False
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.find_next_task = MagicMock(return_value=task)
    solver.handle_error(force=True)
    assert solver.tasks is queue
    assert solver.tasks == [task, ordinary]
